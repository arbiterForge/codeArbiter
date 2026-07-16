#!/usr/bin/env python3
# codeArbiter — descriptor-driven markdown-surface generator.
#
# core/surface/ holds the CANONICAL templates for every host-facing markdown
# surface: commands/, skills/, includes/, agents/, and root persona/catalog
# documents. core/hosts.json supplies every target, token value, capability,
# ordered source-to-output rule, managed subtree, and optional catalog.
#
# Template grammar uses {{PLUGIN_ROOT}}, {{PROJECT_DIR}}, {{CMD:name}}, and
# single-level {{IF:<descriptor-name>}} / {{ELSE}} / {{END}} regions. Unknown
# tags and unresolved tokens are hard errors. Descriptor output patterns expand
# {relative}, {stem}, and {name}; the first matching surface rule wins.
#
# Rendered outputs carry NO provenance header: the Claude tree must stay
# byte-identical to the hand tree it replaced, and the drift guard is this
# tool's --check (run in CI), not a banner. Edit core/surface/, run this tool,
# commit templates and outputs together.
#
# Comparison and IO are BYTE-level; templates must be LF-only (a CR anywhere is
# a hard error, matching the repo's .gitattributes contract). Stdlib only
# (ADR-0004). Modes mirror tools/sync-core.py:
#
#   python tools/build-surface.py                  # write all plugin trees
#   python tools/build-surface.py --check          # verify, exit 1 on drift
#   python tools/build-surface.py --host pi        # limit to one host

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from host_descriptors import DescriptorError, load_host_descriptors  # noqa: E402

# Compatibility views for callers that imported the old generator constants.
# They are derived from core/hosts.json and are not a second host registry.
_ROOT_DESCRIPTORS = load_host_descriptors(REPO)
HOSTS = tuple(item.name for item in _ROOT_DESCRIPTORS)
PLUGIN_DIR = {item.name: item.plugin_dir for item in _ROOT_DESCRIPTORS}
TOKEN_VALUES = {item.name: item.tokens for item in _ROOT_DESCRIPTORS}
CMD_FORM = {item.name: item.command_form for item in _ROOT_DESCRIPTORS}

_MARKER = re.compile(r"\{\{(IF:([a-z][a-z0-9-]*)|ELSE|END)\}\}")
_CMD = re.compile(r"\{\{CMD:([a-z][a-z0-9-]*)\}\}")
_TOKEN = re.compile(r"\{\{(PLUGIN_ROOT|PROJECT_DIR)\}\}")
_CMD_LITERAL = re.compile(r"/ca:([a-z][a-z0-9-]*)")
_COMMAND_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/commands/([a-z0-9-]+)\.md")
_SKILLS_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/skills/(?!ca-)")
_PI_ONLY_AGENT_FRONTMATTER = re.compile(
    r"^(?:classification|pi-skills):[^\n]*\n", re.MULTILINE
)
_PI_ROLE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class SurfaceError(Exception):
    """A template or output-tree contract violation. Always names the file."""


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _read_template(path, where):
    data = _read_bytes(path)
    if b"\r" in data:
        raise SurfaceError(f"{where}: template contains CR bytes; the surface "
                           "is LF-only (.gitattributes pins this)")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SurfaceError(f"{where}: not valid UTF-8: {e}")


def _span_owns_line(text, start, end):
    """True when [start,end) sits alone on its line (drop the whole line)."""
    at_line_start = start == 0 or text[start - 1] == "\n"
    return at_line_start and text[end:end + 1] == "\n"


def resolve_conditionals(text, host, where, host_names=None):
    """Resolve single-level {{IF:host}}/{{ELSE}}/{{END}} regions for `host`."""
    host_names = set(host_names or (item.name for item in load_host_descriptors(REPO)))
    if host not in host_names:
        raise SurfaceError(f"{where}: unknown render host {host!r}")
    out = []
    pos = 0
    keeping = True     # whether non-marker text is currently emitted
    in_region = False  # inside an IF..END region
    if_matches = False
    for m in _MARKER.finditer(text):
        if keeping:
            out.append(text[pos:m.start()])
        kind = m.group(1)
        if kind.startswith("IF:"):
            if in_region:
                raise SurfaceError(f"{where}: nested {{{{IF:...}}}} is not supported")
            if m.group(2) not in host_names:
                raise SurfaceError(f"{where}: unknown host condition {m.group(2)!r}")
            in_region = True
            if_matches = (m.group(2) == host)
            keeping = if_matches
        elif kind == "ELSE":
            if not in_region:
                raise SurfaceError(f"{where}: {{{{ELSE}}}} outside {{{{IF:...}}}}")
            keeping = not if_matches
        else:  # END
            if not in_region:
                raise SurfaceError(f"{where}: {{{{END}}}} outside {{{{IF:...}}}}")
            in_region = False
            keeping = True
        pos = m.end()
        # A marker alone on its line takes the line's newline with it, so block
        # conditionals leave no residue. Only relevant on the emitting side.
        if keeping and _span_owns_line(text, m.start(), m.end()):
            if text[pos] == "\n":
                pos += 1
    if in_region:
        raise SurfaceError(f"{where}: unclosed {{{{IF:...}}}} region")
    if keeping:
        out.append(text[pos:])
    return "".join(out)


def render_text(text, host, cmd_names, where, repo=REPO, descriptor=None,
                host_names=None):
    """Resolve conditionals, descriptor path rules, and descriptor tokens."""
    if descriptor is None or host_names is None:
        descriptors = load_host_descriptors(repo)
        if descriptor is None:
            descriptor = next(
                (item for item in descriptors if item.name == host), None
            )
        if host_names is None:
            host_names = tuple(item.name for item in descriptors)
    if descriptor is None:
        raise SurfaceError(f"{where}: unknown render host {host!r}")
    text = resolve_conditionals(text, host, where, host_names=host_names)
    if where.startswith("core/surface/agents/") and host != "pi":
        text = _PI_ONLY_AGENT_FRONTMATTER.sub("", text)

    def _command_path(match):
        rel = f"commands/{match.group(1)}.md"
        dst, _rule = _output_rel(rel, descriptor)
        if dst is None:
            raise SurfaceError(
                f"{where}: {rel} has no {descriptor.name} surface; guard it "
                "with a host conditional"
            )
        return "{{PLUGIN_ROOT}}/" + dst

    text = _COMMAND_PATH.sub(_command_path, text)
    skill_rule = next(
        (rule for rule in descriptor.surface_rules
         if rule.source_prefix == "skills/"), None
    )
    if skill_rule and "{relative}" in skill_rule.output_pattern:
        output_prefix = skill_rule.output_pattern.format(
            relative="", stem="", name=""
        )
        if output_prefix != "skills/":
            text = _SKILLS_PATH.sub("{{PLUGIN_ROOT}}/" + output_prefix, text)

    def _cmd(m):
        name = m.group(1)
        if name not in cmd_names:
            raise SurfaceError(f"{where}: {{{{CMD:{name}}}}} names no command template")
        dst, _rule = _output_rel(f"commands/{name}.md", descriptor)
        if dst is None:
            raise SurfaceError(
                f"{where}: {{{{CMD:{name}}}}} has no {descriptor.name} surface; "
                "guard it with a host conditional")
        return descriptor.command_form.format(name=name)

    text = _CMD.sub(_cmd, text)
    text = _TOKEN.sub(lambda m: descriptor.tokens[m.group(1)], text)
    if "{{" in text:
        line = text[:text.index("{{")].count("\n") + 1
        raise SurfaceError(f"{where}: unresolved '{{{{' at line {line}")
    return text


def extract(text):
    """Reverse-substitute a hand-written Claude surface file into template form.

    Library helper for the one-time M3 extraction (and future surface
    additions authored Claude-first). render_text(extract(x), 'claude') == x.
    """
    if "{{" in text:
        raise SurfaceError("extract: input already contains '{{' template syntax")
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", "{{PLUGIN_ROOT}}")
    text = text.replace("${CLAUDE_PROJECT_DIR}", "{{PROJECT_DIR}}")
    return _CMD_LITERAL.sub(r"{{CMD:\1}}", text)


def _yaml_safe_scalar(value):
    """Quote a command-frontmatter scalar when YAML could reinterpret it."""
    if value.startswith('"'):
        try:
            if isinstance(json.loads(value), str):
                return value
        except json.JSONDecodeError:
            return json.dumps(value, ensure_ascii=False)
    if value.startswith(("[", "{")) or ": " in value or " | " in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def _synth_skill_frontmatter(text, cmd_name, where):
    if not text.startswith("---\n"):
        raise SurfaceError(f"{where}: command template lacks '---' frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SurfaceError(f"{where}: unterminated frontmatter")
    lines = []
    for line in text[4:end].split("\n"):
        if line.startswith(("description:", "argument-hint:")):
            key, value = line.split(":", 1)
            line = f"{key}: {_yaml_safe_scalar(value.strip())}"
        lines.append(line)
    frontmatter = "\n".join(lines)
    return f"---\nname: ca-{cmd_name}\n{frontmatter}" + text[end:]


def _frontmatter_description(text, where):
    if not text.startswith("---\n"):
        raise SurfaceError(f"{where}: missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SurfaceError(f"{where}: unterminated frontmatter")
    for line in text[4:end].split("\n"):
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    raise SurfaceError(f"{where}: frontmatter has no description")


def _frontmatter_value(text, key, where):
    """Return one simple scalar from rendered agent frontmatter."""
    if not text.startswith("---\n"):
        raise SurfaceError(f"{where}: missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SurfaceError(f"{where}: unterminated frontmatter")
    prefix = key + ":"
    for line in text[4:end].splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            if value:
                return value
    raise SurfaceError(f"{where}: frontmatter has no {key}")


def _frontmatter_list(text, key, where):
    """Return one explicit, duplicate-free inline list from frontmatter."""
    value = _frontmatter_value(text, key, where)
    if not value.startswith("[") or not value.endswith("]"):
        raise SurfaceError(f"{where}: {key} must be an explicit inline list")
    body = value[1:-1].strip()
    items = [] if not body else [item.strip() for item in body.split(",")]
    if any(not _PI_ROLE_NAME.fullmatch(item) for item in items):
        raise SurfaceError(f"{where}: {key} contains an invalid skill name")
    if len(set(items)) != len(items):
        raise SurfaceError(f"{where}: {key} contains a duplicate skill")
    return items


def _pi_role_catalog(out):
    """Generate bounded Pi role launch data from rendered canonical charters."""
    tool_map = {
        "Read": "read", "Grep": "read", "Glob": "read",
        "Bash": "bash", "PowerShell": "bash", "WebFetch": "bash",
        "Edit": "edit", "MultiEdit": "edit", "Write": "write",
    }
    tool_order = ("read", "bash", "edit", "write")
    entries = []
    names = set()
    for path in sorted(item for item in out if item.startswith("agents/")
                       and item.endswith(".md") and item != "agents/INDEX.md"):
        where = "plugins/ca-pi/" + path
        text = out[path].decode("utf-8")
        name = _frontmatter_value(text, "name", where)
        if not _PI_ROLE_NAME.fullmatch(name) or path != f"agents/{name}.md":
            raise SurfaceError(f"{where}: Pi role name must match its charter filename")
        if name in names:
            raise SurfaceError(f"{where}: duplicate Pi role name {name!r}")
        names.add(name)
        classification = _frontmatter_value(text, "classification", where)
        if classification not in ("author", "reviewer"):
            raise SurfaceError(f"{where}: classification must be author or reviewer")
        skill_names = _frontmatter_list(text, "pi-skills", where)
        skill_paths = [f"routines/{skill}/SKILL.md" for skill in skill_names]
        missing_skills = [skill for skill in skill_paths if skill not in out]
        if missing_skills:
            raise SurfaceError(f"{where}: Pi role skills are missing from the rendered package: {missing_skills!r}")
        declared = [item.strip() for item in
                    _frontmatter_value(text, "tools", where).split(",")]
        unknown = sorted(set(declared) - set(tool_map))
        if unknown:
            raise SurfaceError(f"{where}: unmapped Pi role tools {unknown!r}")
        mapped = {tool_map[item] for item in declared}
        entries.append({
            "name": name,
            "classification": classification,
            "charterPath": path,
            "skillPaths": skill_paths,
            "tools": [item for item in tool_order if item in mapped],
        })
    return entries


def _surface_files(repo, descriptors=None):
    """Sorted surface-relative template paths, classified or rejected."""
    surface = os.path.join(repo, "core", "surface")
    if not os.path.isdir(surface):
        raise SurfaceError(f"no template tree at {surface}")
    descriptors = tuple(descriptors or load_host_descriptors(repo))
    rels = []
    for dirpath, dirnames, filenames in os.walk(surface):
        dirnames.sort()
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), surface)
            rel = rel.replace(os.sep, "/")
            if any(rel.startswith(rule.source_prefix)
                   for host in descriptors for rule in host.surface_rules):
                rels.append(rel)
            else:
                raise SurfaceError(f"core/surface/{rel}: unrecognized surface "
                                   "location (no host descriptor rule matches)")
    return rels


def _command_names(rels):
    return frozenset(r[len("commands/"):-len(".md")]
                     for r in rels
                     if r.startswith("commands/") and r.endswith(".md"))


def _output_rel(rel, descriptor):
    """Map a surface-relative template path to a plugin-relative output path.

    Returns (None, rule) when an exclusion suppresses it and (None, None) when
    this host has no matching rule. The first matching rule always wins.
    """
    for rule in descriptor.surface_rules:
        if not rel.startswith(rule.source_prefix):
            continue
        if rel in rule.exclude:
            return None, rule
        relative = rel[len(rule.source_prefix):]
        basename = os.path.basename(relative or rel)
        stem = os.path.splitext(basename)[0]
        output = rule.output_pattern.format(
            relative=relative, stem=stem, name=stem
        )
        normalized = os.path.normpath(output).replace(os.sep, "/")
        if normalized.startswith("../") or normalized in (".", ".."):
            raise SurfaceError(
                f"core/surface/{rel}: descriptor output escapes plugin root"
            )
        return normalized, rule
    return None, None


def render_all(repo, host, descriptors=None):
    """Render every template for `host` -> {plugin-relative path: bytes}."""
    descriptors = tuple(descriptors or load_host_descriptors(repo))
    descriptor = next((item for item in descriptors if item.name == host), None)
    if descriptor is None:
        raise SurfaceError(f"unknown render host {host!r}")
    host_names = tuple(item.name for item in descriptors)
    surface = os.path.join(repo, "core", "surface")
    rels = _surface_files(repo, descriptors)
    cmd_names = _command_names(rels)
    out = {}
    catalog = []  # (skill name, description) for an optional host catalog
    for rel in rels:
        dst, rule = _output_rel(rel, descriptor)
        if dst is None:
            continue
        where = f"core/surface/{rel}"
        text = _read_template(os.path.join(surface, rel.replace("/", os.sep)), where)
        rendered = render_text(
            text, host, cmd_names, where, repo=repo,
            descriptor=descriptor, host_names=host_names,
        )
        if rule.add_skill_frontmatter:
            name = rel[len("commands/"):-len(".md")]
            rendered = _synth_skill_frontmatter(rendered, name, where)
            frontmatter_end = rendered.find("\n---\n", 4)
            body = rendered[frontmatter_end + len("\n---\n"):]
            if "</skill>" in body:
                raise SurfaceError(
                    f"{where}: reserved </skill> terminator in generated skill body"
                )
            catalog.append((name,
                            _frontmatter_description(rendered, where)))
        if dst in out:
            raise SurfaceError(f"{where}: output collision at "
                               f"{descriptor.plugin_dir}/{dst}")
        out[dst] = rendered.encode("utf-8")
    if descriptor.catalog is not None:
        dst = descriptor.catalog
        if dst in out:
            raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the "
                               "generated skill catalog")
        out[dst] = _host_catalog(descriptor, sorted(catalog)).encode("utf-8")
    if descriptor.command_form == "/ca-{name}":
        dst = "generated/command-catalog.json"
        if dst in out:
            raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the "
                               "generated command catalog")
        entries = []
        for name, description in sorted(catalog):
            if description.startswith('"'):
                try:
                    description = json.loads(description)
                except json.JSONDecodeError as error:
                    raise SurfaceError(
                        f"core/surface/commands/{name}.md: invalid quoted description: {error}"
                    ) from error
            entries.append({
                "name": name,
                "description": description,
                "skillPath": f"skills/ca-{name}/SKILL.md",
            })
        out[dst] = (json.dumps(entries, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if descriptor.name == "pi":
        dst = "generated/roles.json"
        if dst in out:
            raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the generated role catalog")
        out[dst] = (json.dumps(_pi_role_catalog(out), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return out


def _host_catalog(descriptor, entries):
    lines = [
        f"# ca-{descriptor.name} skills — catalog (surface scan)",
        "",
        "Generated by tools/build-surface.py — edit core/surface/, never this file.",
        "Each entry skill wraps one governance command; a body loads only when its",
        "skill is invoked — never bulk-read this directory.",
        "",
        "| Skill | Purpose |",
        "|---|---|",
    ]
    lines += [f"| `{descriptor.command_form.format(name=name)}` | {desc} |"
              for name, desc in entries]
    return "\n".join(lines) + "\n"


def _disk_files(repo, descriptor):
    """Plugin-relative paths currently on disk inside the managed output set."""
    plugin = os.path.join(repo, descriptor.plugin_dir)
    found = set()
    managed_subtrees = descriptor.managed_subtrees
    if descriptor.command_form == "/ca-{name}":
        managed_subtrees = managed_subtrees + ("generated",)
    for sub in managed_subtrees:
        base = os.path.join(plugin, sub)
        if os.path.isfile(base):
            found.add(sub.replace(os.sep, "/"))
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, name), plugin)
                found.add(rel.replace(os.sep, "/"))
    return found


def check_all(repo, hosts=None):
    """Return drift lines (empty = clean): modified, missing, and orphans."""
    descriptors = load_host_descriptors(repo)
    hosts = tuple(hosts or (item.name for item in descriptors))
    by_name = {item.name: item for item in descriptors}
    drift = []
    for host in hosts:
        descriptor = by_name.get(host)
        if descriptor is None:
            raise SurfaceError(f"unknown render host {host!r}")
        expected = render_all(repo, host, descriptors=descriptors)
        plugin_rel = descriptor.plugin_dir
        plugin = os.path.join(repo, descriptor.plugin_dir)
        on_disk = _disk_files(repo, descriptor)
        for rel in sorted(expected):
            path = os.path.join(plugin, rel.replace("/", os.sep))
            try:
                same = _read_bytes(path) == expected[rel]
            except OSError:
                drift.append(f"{plugin_rel}/{rel}: missing (not rendered to disk)")
                continue
            if not same:
                drift.append(f"{plugin_rel}/{rel}: differs from its template render")
        for rel in sorted(on_disk - set(expected)):
            drift.append(f"{plugin_rel}/{rel}: orphan (no template renders it)")
    return drift


def write_all(repo, hosts=None):
    """Write every render to disk, delete orphans; return changed-file count."""
    descriptors = load_host_descriptors(repo)
    hosts = tuple(hosts or (item.name for item in descriptors))
    by_name = {item.name: item for item in descriptors}
    changed = 0
    for host in hosts:
        descriptor = by_name.get(host)
        if descriptor is None:
            raise SurfaceError(f"unknown render host {host!r}")
        expected = render_all(repo, host, descriptors=descriptors)
        plugin = os.path.join(repo, descriptor.plugin_dir)
        for rel in sorted(expected):
            path = os.path.join(plugin, rel.replace("/", os.sep))
            try:
                if _read_bytes(path) == expected[rel]:
                    continue
            except OSError:
                pass
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:  # binary: byte-exact, LF preserved
                f.write(expected[rel])
            changed += 1
        for rel in sorted(
            _disk_files(repo, descriptor) - set(expected)
        ):
            path = os.path.join(plugin, rel.replace("/", os.sep))
            os.remove(path)
            print(f"build-surface: removed orphan "
                  f"{descriptor.plugin_dir}/{rel}")
            changed += 1
    return changed


def main(argv=None, repo=REPO):
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    argv = [a for a in argv if a != "--check"]
    try:
        available = tuple(item.name for item in load_host_descriptors(repo))
    except DescriptorError as error:
        sys.stderr.write(f"build-surface: {error}\n")
        return 2
    hosts = available
    if "--host" in argv:
        i = argv.index("--host")
        if i + 1 >= len(argv) or argv[i + 1] not in available:
            sys.stderr.write(
                f"build-surface: --host needs one of {', '.join(available)}\n"
            )
            return 2
        hosts = (argv[i + 1],)
        del argv[i:i + 2]
    if argv:
        sys.stderr.write(
            f"build-surface: unknown argument(s): {' '.join(argv)}\n"
            "usage: python tools/build-surface.py [--check] [--host NAME]\n")
        return 2

    try:
        if check:
            drift = check_all(repo, hosts)
            if drift:
                print("build-surface --check: rendered surface out of sync "
                      "with core/surface/ templates:")
                for line in drift:
                    print(f"  {line}")
                print("edit core/surface/ (never the rendered files) and run "
                      "`python tools/build-surface.py`.")
                return 1
            print(f"build-surface --check: OK ({', '.join(hosts)} in sync)")
            return 0
        changed = write_all(repo, hosts)
        print(f"build-surface: {changed} file(s) changed "
              f"({', '.join(hosts)})")
        return 0
    except (SurfaceError, DescriptorError) as e:
        sys.stderr.write(f"build-surface: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
