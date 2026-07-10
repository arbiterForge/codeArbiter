#!/usr/bin/env python3
# codeArbiter — markdown-surface generator (ADR-0011, codex-support M3).
#
# core/surface/ holds the CANONICAL templates for every host-facing markdown
# surface: commands/, skills/, includes/, COMMANDS.md, SPRINT.md, and
# ORCHESTRATOR.md. This tool renders them into each plugin tree:
#
#   claude -> plugins/ca/{commands,skills,includes}/**, COMMANDS.md, SPRINT.md,
#             ORCHESTRATOR.md  (byte-identical to the pre-template hand tree)
#   codex  -> plugins/ca-codex/skills/ca-<cmd>/SKILL.md (user-invocable entry
#             skills; commands carry a `ca-` prefix because Codex has no plugin
#             command namespace), routines/** (orchestrator-routine bodies,
#             kept OUT of the skill-discovery root so they never register
#             unprefixed), includes/**, COMMANDS.md, SPRINT.md, ORCHESTRATOR.md,
#             plus a generated skills/INDEX.md catalog.
#
# Template grammar (three tokens + host conditionals; single level, no nesting):
#   {{PLUGIN_ROOT}}   -> ${CLAUDE_PLUGIN_ROOT} on BOTH hosts (Codex ships the
#                        compat alias — verified against the Codex source, M0)
#   {{PROJECT_DIR}}   -> ${CLAUDE_PROJECT_DIR} (claude) | <project-root> (codex)
#   {{CMD:name}}      -> /ca:name (claude) | $ca-name (codex); hard error if
#                        `name` is not a command template or is excluded on the
#                        target host — that error is what forces a {{IF:...}}
#                        conditional around every host-impossible reference.
#   {{IF:claude}} A {{ELSE}} B {{END}}  (and {{IF:codex}} ...) — a marker alone
#   on its line is removed together with the line, so block conditionals leave
#   no blank-line residue; inline markers are spliced out in place.
#
# Codex renders additionally rewrite paths BEFORE token substitution:
#   {{PLUGIN_ROOT}}/skills/...        -> {{PLUGIN_ROOT}}/routines/...
#   {{PLUGIN_ROOT}}/commands/<n>.md   -> {{PLUGIN_ROOT}}/skills/ca-<n>/SKILL.md
# (in that order — the reverse would clobber rewritten command paths).
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
#   python tools/build-surface.py                  # write both plugin trees
#   python tools/build-surface.py --check          # verify, exit 1 on drift
#   python tools/build-surface.py --host codex     # limit to one host

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOSTS = ("claude", "codex")

PLUGIN_DIR = {
    "claude": os.path.join("plugins", "ca"),
    "codex": os.path.join("plugins", "ca-codex"),
}

TOKEN_VALUES = {
    "claude": {"PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
               "PROJECT_DIR": "${CLAUDE_PROJECT_DIR}"},
    "codex": {"PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
              "PROJECT_DIR": "<project-root>"},
}

CMD_FORM = {"claude": "/ca:{name}", "codex": "$ca-{name}"}

# Commands with no Codex surface (ledgered in docs/parity.md): statusline has
# no Codex analogue; the prune ENGINE is ledgered out (the audit staleness-warn
# half runs hook-side without a command).
CODEX_EXCLUDED_CMDS = frozenset({"statusline", "prune"})

# Surface-relative template paths rendered ONLY into the Codex tree.
CODEX_ONLY = frozenset({"includes/codex-host-notes.md"})

# Surface-root files that document the template tree and are never rendered.
UNRENDERED = frozenset({"README.md"})

ROOT_DOCS = frozenset({"COMMANDS.md", "SPRINT.md", "ORCHESTRATOR.md"})

# Subtrees of each plugin dir that are wholly generated: --check treats any
# file in them that the render did not produce as drift (orphan), and write
# mode deletes it. agents/ and hooks/ are deliberately NOT here (agents are
# hand-maintained until M4; hooks belong to tools/sync-core.py).
MANAGED_SUBTREES = {
    "claude": ("commands", "skills", "includes"),
    "codex": ("skills", "routines", "includes"),
}

_MARKER = re.compile(r"\{\{(IF:(claude|codex)|ELSE|END)\}\}")
_CMD = re.compile(r"\{\{CMD:([a-z][a-z0-9-]*)\}\}")
_TOKEN = re.compile(r"\{\{(PLUGIN_ROOT|PROJECT_DIR)\}\}")
_CMD_LITERAL = re.compile(r"/ca:([a-z][a-z0-9-]*)")
_CODEX_CMD_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/commands/([a-z0-9-]+)\.md")
_CODEX_SKILLS_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/skills/(?!ca-)")


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


def resolve_conditionals(text, host, where):
    """Resolve single-level {{IF:host}}/{{ELSE}}/{{END}} regions for `host`."""
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


def render_text(text, host, cmd_names, where):
    """Conditionals -> codex path rewrites -> tokens; hard-fail on leftovers."""
    text = resolve_conditionals(text, host, where)
    if host == "codex":
        # skills/ca-* is exempt: entry-skill paths (from codex-side
        # conditionals or the commands rewrite below) are already codex-native,
        # and no Claude-side routine is named ca-*.
        text = _CODEX_SKILLS_PATH.sub("{{PLUGIN_ROOT}}/routines/", text)
        text = _CODEX_CMD_PATH.sub(r"{{PLUGIN_ROOT}}/skills/ca-\1/SKILL.md", text)

    def _cmd(m):
        name = m.group(1)
        if name not in cmd_names:
            raise SurfaceError(f"{where}: {{{{CMD:{name}}}}} names no command template")
        if host == "codex" and name in CODEX_EXCLUDED_CMDS:
            raise SurfaceError(
                f"{where}: {{{{CMD:{name}}}}} has no Codex surface (ledgered "
                "exception) — wrap the reference in {{IF:claude}}...{{END}}")
        return CMD_FORM[host].format(name=name)

    text = _CMD.sub(_cmd, text)
    text = _TOKEN.sub(lambda m: TOKEN_VALUES[host][m.group(1)], text)
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


def _synth_skill_frontmatter(text, cmd_name, where):
    if not text.startswith("---\n"):
        raise SurfaceError(f"{where}: command template lacks '---' frontmatter")
    return f"---\nname: ca-{cmd_name}\n" + text[4:]


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


def _surface_files(repo):
    """Sorted surface-relative template paths, classified or rejected."""
    surface = os.path.join(repo, "core", "surface")
    if not os.path.isdir(surface):
        raise SurfaceError(f"no template tree at {surface}")
    rels = []
    for dirpath, dirnames, filenames in os.walk(surface):
        dirnames.sort()
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), surface)
            rel = rel.replace(os.sep, "/")
            if rel in UNRENDERED:
                continue
            top = rel.split("/", 1)[0]
            if rel in ROOT_DOCS or top in ("commands", "skills", "includes"):
                rels.append(rel)
            else:
                raise SurfaceError(f"core/surface/{rel}: unrecognized surface "
                                   "location (commands/, skills/, includes/, "
                                   "COMMANDS.md, SPRINT.md, ORCHESTRATOR.md)")
    return rels


def _command_names(rels):
    return frozenset(r[len("commands/"):-len(".md")]
                     for r in rels
                     if r.startswith("commands/") and r.endswith(".md"))


def _output_rel(rel, host):
    """Map a surface-relative template path to a plugin-relative output path.

    Returns None when the template does not render for `host`.
    """
    if host == "claude":
        if rel in CODEX_ONLY:
            return None
        return rel
    if rel in ROOT_DOCS or rel in CODEX_ONLY:
        return rel
    if rel.startswith("commands/"):
        name = rel[len("commands/"):-len(".md")]
        if name in CODEX_EXCLUDED_CMDS:
            return None
        return f"skills/ca-{name}/SKILL.md"
    if rel.startswith("skills/"):
        return "routines/" + rel[len("skills/"):]
    return rel  # includes/**


def render_all(repo, host):
    """Render every template for `host` -> {plugin-relative path: bytes}."""
    surface = os.path.join(repo, "core", "surface")
    rels = _surface_files(repo)
    cmd_names = _command_names(rels)
    out = {}
    catalog = []  # (skill name, description) for the generated Codex catalog
    for rel in rels:
        dst = _output_rel(rel, host)
        if dst is None:
            continue
        where = f"core/surface/{rel}"
        text = _read_template(os.path.join(surface, rel.replace("/", os.sep)), where)
        rendered = render_text(text, host, cmd_names, where)
        if host == "codex" and rel.startswith("commands/"):
            name = rel[len("commands/"):-len(".md")]
            rendered = _synth_skill_frontmatter(rendered, name, where)
            catalog.append((f"ca-{name}",
                            _frontmatter_description(rendered, where)))
        if dst in out:
            raise SurfaceError(f"{where}: output collision at "
                               f"{PLUGIN_DIR[host]}/{dst}")
        out[dst] = rendered.encode("utf-8")
    if host == "codex":
        dst = "skills/INDEX.md"
        if dst in out:
            raise SurfaceError(f"{PLUGIN_DIR[host]}/{dst} collides with the "
                               "generated skill catalog")
        out[dst] = _codex_catalog(sorted(catalog)).encode("utf-8")
    return out


def _codex_catalog(entries):
    lines = [
        "# ca-codex skills — catalog (surface scan)",
        "",
        "Generated by tools/build-surface.py — edit core/surface/, never this file.",
        "Each entry skill wraps one governance command; a body loads only when its",
        "skill is invoked — never bulk-read this directory.",
        "",
        "| Skill | Purpose |",
        "|---|---|",
    ]
    lines += [f"| `${name}` | {desc} |" for name, desc in entries]
    return "\n".join(lines) + "\n"


def _disk_files(repo, host):
    """Plugin-relative paths currently on disk inside the managed output set."""
    plugin = os.path.join(repo, PLUGIN_DIR[host])
    found = set()
    for sub in MANAGED_SUBTREES[host]:
        base = os.path.join(plugin, sub)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, name), plugin)
                found.add(rel.replace(os.sep, "/"))
    for doc in sorted(ROOT_DOCS):
        if os.path.isfile(os.path.join(plugin, doc)):
            found.add(doc)
    return found


def check_all(repo, hosts=HOSTS):
    """Return drift lines (empty = clean): modified, missing, and orphans."""
    drift = []
    for host in hosts:
        expected = render_all(repo, host)
        plugin_rel = PLUGIN_DIR[host].replace(os.sep, "/")
        plugin = os.path.join(repo, PLUGIN_DIR[host])
        on_disk = _disk_files(repo, host)
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


def write_all(repo, hosts=HOSTS):
    """Write every render to disk, delete orphans; return changed-file count."""
    changed = 0
    for host in hosts:
        expected = render_all(repo, host)
        plugin = os.path.join(repo, PLUGIN_DIR[host])
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
        for rel in sorted(_disk_files(repo, host) - set(expected)):
            path = os.path.join(plugin, rel.replace("/", os.sep))
            os.remove(path)
            print(f"build-surface: removed orphan "
                  f"{PLUGIN_DIR[host].replace(os.sep, '/')}/{rel}")
            changed += 1
    return changed


def main(argv=None, repo=REPO):
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    argv = [a for a in argv if a != "--check"]
    hosts = HOSTS
    if "--host" in argv:
        i = argv.index("--host")
        if i + 1 >= len(argv) or argv[i + 1] not in HOSTS:
            sys.stderr.write("build-surface: --host needs 'claude' or 'codex'\n")
            return 2
        hosts = (argv[i + 1],)
        del argv[i:i + 2]
    if argv:
        sys.stderr.write(
            f"build-surface: unknown argument(s): {' '.join(argv)}\n"
            "usage: python tools/build-surface.py [--check] [--host claude|codex]\n")
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
    except SurfaceError as e:
        sys.stderr.write(f"build-surface: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
