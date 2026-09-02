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
import ntpath
import os
import posixpath
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
_TOKEN = re.compile(r"\{\{(PLUGIN_ROOT|EXECUTABLE_PLUGIN_ROOT|PROJECT_DIR)\}\}")
_CMD_LITERAL = re.compile(r"/ca:([a-z][a-z0-9-]*)")
_COMMAND_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/commands/([a-z0-9-]+)\.md")
_SKILLS_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/skills/(?!ca-)")
_ROOT_RESOURCE = re.compile(
    r"(?P<tick>`?)\{\{PLUGIN_ROOT\}\}/(?P<path>[A-Za-z0-9_./<>:\\-]+)(?P=tick)"
)
_EXECUTABLE_PY_PREFIX = re.compile(
    r"(?:^|[ \t`|;&(])(?:[\"']?\$PY[\"']?|python3?)[ \t]+[\"']?$",
    re.MULTILINE,
)
_CLAUDE_ONLY_AGENT_FRONTMATTER = re.compile(
    r"^(?:classification|pi-skills):[^\n]*\n", re.MULTILINE
)
_CODEX_ONLY_AGENT_FRONTMATTER = re.compile(
    r"^(?:tools|pi-skills|model):[^\n]*\n", re.MULTILINE
)
_MARKDOWN_LINK_TARGET = re.compile(r"\]\(([^)]+)\)")
_AGENT_FRONTMATTER_STRIPPERS = {
    "host-native": _CLAUDE_ONLY_AGENT_FRONTMATTER,
    "relative": _CODEX_ONLY_AGENT_FRONTMATTER,
}
_PI_ROLE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_MODE_NAME = re.compile(r"^(?:--)?[a-z][a-z0-9-]*$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RETAIN_THROUGH = re.compile(r"^(0|[1-9][0-9]*)\.x$")
_COMMAND_MODE_MARKER = re.compile(
    r"<!-- command-mode:(?P<mode>(?:--)?[a-z][a-z0-9-]*) "
    r"legacy-route:(?P<route>[a-z][a-z0-9-]*) -->"
)
_VISIBILITY_ORDER = ("core", "advanced", "alias", "internal", "deprecated")
_WORKFLOW_ORDER = (
    "evaluate", "initialize", "change", "review", "decide", "ship",
    "operate", "extend", "help",
)
_REGISTRY_KEYS = frozenset({
    "schemaVersion", "visibilityOrder", "workflowOrder", "compatibility", "commands",
})
_COMMAND_METADATA_KEYS = frozenset({
    "visibility", "workflow", "canonical", "legacyRoutes", "modes", "replacement",
})
_CODEX_POLICY_NAMES = {
    "author": frozenset({"backend-author", "frontend-author", "infra-author"}),
    "read-only reviewer/extractor": frozenset({
        "architecture-drift-reviewer", "auth-crypto-reviewer", "coverage-auditor",
        "decision-challenger", "dependency-reviewer", "design-quality-reviewer",
        "finding-triage", "grader", "map-deps", "map-structure",
        "migration-reviewer", "scout", "security-reviewer", "verdict-aggregator",
    }),
    "bounded writer/aggregator": frozenset({
        "checkpoint-aggregator", "tribunal-lens-reviewer",
    }),
}


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


def _render_relative_resources(text, output_path, where, resource_paths=None):
    """Render Codex Markdown resources as POSIX links from `output_path`."""
    if not output_path:
        raise SurfaceError(f"{where}: Codex relative-resource rendering needs an output path")

    def replace(match):
        path = match.group("path")
        suffix = ""
        while path and path[-1] in ".,;:":
            suffix = path[-1] + suffix
            path = path[:-1]
        if not path:
            return match.group(0)
        validation_path = path.replace("\\", "/")
        if (posixpath.isabs(validation_path) or os.path.isabs(path)
                or ntpath.isabs(path)):
            raise SurfaceError(
                f"{where}: Codex resource path must be relative: {path!r}"
            )
        if any(part in (".", "..") for part in validation_path.split("/")):
            raise SurfaceError(
                f"{where}: Codex resource path cannot contain '.' or '..': {path!r}"
            )
        normalized = validation_path.rstrip("/")
        if (normalized.startswith("hooks/") and normalized.endswith(".py")
                and resource_paths is not None and normalized in resource_paths
                and _EXECUTABLE_PY_PREFIX.search(text[:match.start()])):
            return f"{{{{EXECUTABLE_PLUGIN_ROOT}}}}/{normalized}{suffix}"
        prefix = normalized + "/"
        if (resource_paths is not None and "<" not in path and ">" not in path
                and normalized not in resource_paths
                and not any(item.startswith(prefix) for item in resource_paths)):
            tick = match.group("tick")
            return f"{tick}{validation_path}{tick}{suffix}"
        relative = posixpath.relpath(validation_path, posixpath.dirname(output_path) or ".")
        return f"[{validation_path}]({relative}){suffix}"

    text = _ROOT_RESOURCE.sub(replace, text)
    if "{{PLUGIN_ROOT}}" in text:
        text = text.replace("{{PLUGIN_ROOT}}", "the validated selected-skill root")
    return text


def render_text(text, host, cmd_names, where, repo=REPO, descriptor=None,
                host_names=None, output_path=None, resource_paths=None):
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
    if where.startswith("core/surface/agents/"):
        stripper = _AGENT_FRONTMATTER_STRIPPERS.get(
            descriptor.root_contract.ordinary_markdown
        )
        if stripper is not None:
            text = stripper.sub("", text)

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
    if descriptor.root_contract.ordinary_markdown == "relative":
        text = _render_relative_resources(
            text, output_path, where, resource_paths=resource_paths
        )
    def _token_value(match):
        name = match.group(1)
        if name == "EXECUTABLE_PLUGIN_ROOT":
            return descriptor.tokens["PLUGIN_ROOT"]
        return descriptor.tokens[name]

    text = _TOKEN.sub(_token_value, text)
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


def _decoded_frontmatter_description(text, where):
    description = _frontmatter_description(text, where)
    if description.startswith('"'):
        try:
            description = json.loads(description)
        except json.JSONDecodeError as error:
            raise SurfaceError(f"{where}: invalid quoted description: {error}") from error
    return description


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


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _registry_string_list(value, key, where, pattern=_PI_ROLE_NAME):
    if not isinstance(value, list):
        raise SurfaceError(f"{where}: {key} must be an array")
    if any(not isinstance(item, str) or not pattern.fullmatch(item) for item in value):
        raise SurfaceError(f"{where}: {key} contains an invalid value")
    if len(set(value)) != len(value):
        raise SurfaceError(f"{where}: {key} contains a duplicate value")
    if value != sorted(value):
        raise SurfaceError(f"{where}: {key} must be sorted")
    return tuple(value)


def _validate_compatibility_policy(value, descriptors, where):
    if not isinstance(value, dict):
        raise SurfaceError(f"{where}: compatibility must be an object")
    expected_keys = {"clockStarts", "removalRequires", "targets"}
    if set(value) != expected_keys:
        raise SurfaceError(
            f"{where}: compatibility requires exactly {sorted(expected_keys)!r}"
        )
    if value["clockStarts"] != "published-release":
        raise SurfaceError(f"{where}: compatibility.clockStarts must be 'published-release'")
    if value["removalRequires"] != "separately-approved-major":
        raise SurfaceError(
            f"{where}: compatibility.removalRequires must be 'separately-approved-major'"
        )
    targets = value["targets"]
    host_names = {descriptor.name for descriptor in descriptors}
    if not isinstance(targets, dict) or set(targets) != host_names:
        raise SurfaceError(
            f"{where}: compatibility.targets must match hosts {sorted(host_names)!r}"
        )
    target_keys = {
        "publishedWithoutMetadata",
        "firstContainingRelease",
        "retainThrough",
        "earliestRemoval",
    }
    for host in sorted(targets):
        target = targets[host]
        target_where = f"{where}: compatibility.targets.{host}"
        if not isinstance(target, dict) or set(target) != target_keys:
            raise SurfaceError(
                f"{target_where} requires exactly {sorted(target_keys)!r}"
            )
        published_without_metadata = target["publishedWithoutMetadata"]
        first_containing_release = target["firstContainingRelease"]
        retention = target["retainThrough"]
        removal = target["earliestRemoval"]
        baseline_match = (
            _SEMVER.fullmatch(published_without_metadata)
            if isinstance(published_without_metadata, str)
            else None
        )
        first_containing_match = (
            _SEMVER.fullmatch(first_containing_release)
            if isinstance(first_containing_release, str)
            else None
        )
        retention_match = (
            _RETAIN_THROUGH.fullmatch(retention) if isinstance(retention, str) else None
        )
        removal_match = _SEMVER.fullmatch(removal) if isinstance(removal, str) else None
        if (
            not baseline_match
            or first_containing_release is not None and not first_containing_match
            or not retention_match
            or not removal_match
        ):
            raise SurfaceError(f"{target_where} has an invalid version boundary")
        retained_major = int(retention_match.group(1))
        if int(baseline_match.group(1)) != retained_major:
            raise SurfaceError(
                f"{target_where}: publishedWithoutMetadata is outside retainThrough"
            )
        if first_containing_match:
            baseline_version = tuple(map(int, baseline_match.groups()))
            first_containing_version = tuple(map(int, first_containing_match.groups()))
            if int(first_containing_match.group(1)) != retained_major:
                raise SurfaceError(
                    f"{target_where}: firstContainingRelease is outside retainThrough"
                )
            if first_containing_version <= baseline_version:
                raise SurfaceError(
                    f"{target_where}: firstContainingRelease must follow "
                    "publishedWithoutMetadata"
                )
        if tuple(map(int, removal_match.groups())) != (retained_major + 1, 0, 0):
            raise SurfaceError(
                f"{target_where}: earliestRemoval must be the next major boundary"
            )


def _load_command_registry(repo, command_names, descriptors):
    rel = "command-routes.json"
    where = "core/surface/command-routes.json"
    path = os.path.join(repo, "core", "surface", rel)
    try:
        text = _read_template(path, where)
    except OSError as error:
        raise SurfaceError(f"{where}: missing canonical command registry") from error
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise SurfaceError(f"{where}: invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise SurfaceError(f"{where}: registry root must be an object")
    unknown = sorted(set(document) - _REGISTRY_KEYS)
    missing = sorted(_REGISTRY_KEYS - set(document))
    if unknown:
        raise SurfaceError(f"{where}: unknown top-level field(s) {unknown!r}")
    if missing:
        raise SurfaceError(f"{where}: missing top-level field(s) {missing!r}")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise SurfaceError(f"{where}: schemaVersion must be 1")
    if document["visibilityOrder"] != list(_VISIBILITY_ORDER):
        raise SurfaceError(f"{where}: visibilityOrder must be {list(_VISIBILITY_ORDER)!r}")
    if document["workflowOrder"] != list(_WORKFLOW_ORDER):
        raise SurfaceError(f"{where}: workflowOrder must be {list(_WORKFLOW_ORDER)!r}")
    _validate_compatibility_policy(document["compatibility"], descriptors, where)

    commands = document["commands"]
    if not isinstance(commands, dict):
        raise SurfaceError(f"{where}: commands must be an object")
    if list(commands) != sorted(commands):
        raise SurfaceError(f"{where}: command keys must be sorted")
    registry_names = set(commands)
    source_names = set(command_names)
    if registry_names != source_names:
        missing_routes = sorted(source_names - registry_names)
        extra_routes = sorted(registry_names - source_names)
        raise SurfaceError(
            f"{where}: command inventory mismatch; missing={missing_routes!r}, "
            f"extra={extra_routes!r}"
        )

    normalized = {}
    canonical_visibilities = frozenset({"core", "advanced", "internal"})
    for name, metadata in commands.items():
        command_where = f"{where}: commands.{name}"
        if not _PI_ROLE_NAME.fullmatch(name):
            raise SurfaceError(f"{command_where}: invalid route slug")
        if not isinstance(metadata, dict):
            raise SurfaceError(f"{command_where}: metadata must be an object")
        unknown_fields = sorted(set(metadata) - _COMMAND_METADATA_KEYS)
        if unknown_fields:
            raise SurfaceError(f"{command_where}: unknown field(s) {unknown_fields!r}")
        visibility = metadata.get("visibility")
        workflow = metadata.get("workflow")
        if visibility not in _VISIBILITY_ORDER:
            raise SurfaceError(f"{command_where}: visibility must be one of {_VISIBILITY_ORDER!r}")
        if workflow not in _WORKFLOW_ORDER:
            raise SurfaceError(f"{command_where}: workflow must be one of {_WORKFLOW_ORDER!r}")

        item = {"visibility": visibility, "workflow": workflow}
        if visibility in canonical_visibilities:
            required = {"visibility", "workflow", "canonical", "legacyRoutes"}
            if not required.issubset(metadata):
                raise SurfaceError(
                    f"{command_where}: canonical metadata requires canonical and legacyRoutes"
                )
            if metadata["canonical"] != name:
                raise SurfaceError(
                    f"{command_where}: canonical must equal its route slug {name!r}"
                )
            legacy_routes = _registry_string_list(
                metadata["legacyRoutes"], "legacyRoutes", command_where
            )
            item.update(canonical=name, legacyRoutes=legacy_routes)
            if legacy_routes:
                if "modes" not in metadata:
                    raise SurfaceError(
                        f"{command_where}: modes is required when legacyRoutes is non-empty"
                    )
                item["modes"] = _registry_string_list(
                    metadata["modes"], "modes", command_where, pattern=_MODE_NAME
                )
            elif "modes" in metadata:
                raise SurfaceError(
                    f"{command_where}: modes is only allowed with non-empty legacyRoutes"
                )
            if "replacement" in metadata:
                raise SurfaceError(f"{command_where}: canonical routes cannot declare replacement")
        elif visibility == "alias":
            required = {"visibility", "workflow", "canonical", "replacement"}
            if set(metadata) != required:
                raise SurfaceError(
                    f"{command_where}: alias metadata requires exactly {sorted(required)!r}"
                )
            canonical = metadata["canonical"]
            replacement = metadata["replacement"]
            if not isinstance(canonical, str) or not _PI_ROLE_NAME.fullmatch(canonical):
                raise SurfaceError(f"{command_where}: canonical is not a valid route slug")
            if not isinstance(replacement, str) or not replacement:
                raise SurfaceError(f"{command_where}: replacement must be a non-empty string")
            item.update(canonical=canonical, replacement=replacement)
        else:
            required = {"visibility", "workflow", "replacement"}
            allowed = required | {"canonical"}
            if not required.issubset(metadata) or not set(metadata).issubset(allowed):
                raise SurfaceError(
                    f"{command_where}: deprecated metadata requires replacement guidance"
                )
            replacement = metadata["replacement"]
            if not isinstance(replacement, str) or not replacement:
                raise SurfaceError(f"{command_where}: replacement must be a non-empty string")
            item["replacement"] = replacement
            if "canonical" in metadata:
                canonical = metadata["canonical"]
                if not isinstance(canonical, str) or not _PI_ROLE_NAME.fullmatch(canonical):
                    raise SurfaceError(f"{command_where}: canonical is not a valid route slug")
                item["canonical"] = canonical
        normalized[name] = item

    forward = {
        name: metadata for name, metadata in normalized.items()
        if metadata["visibility"] == "alias"
    }
    expected_reverse = {name: [] for name in normalized}
    replacement_modes = {name: [] for name in normalized}
    for alias, metadata in forward.items():
        alias_where = f"{where}: commands.{alias}"
        target_name = metadata["canonical"]
        target = normalized.get(target_name)
        if target is None:
            raise SurfaceError(f"{alias_where}: alias target {target_name!r} is missing")
        if target["visibility"] not in canonical_visibilities:
            raise SurfaceError(
                f"{alias_where}: alias target {target_name!r} is not a canonical route"
            )
        tokens = metadata["replacement"].split()
        if len(tokens) != 2 or tokens[0] != target_name:
            raise SurfaceError(
                f"{alias_where}: replacement canonical must be exactly {target_name!r}"
            )
        mode = tokens[1]
        if not _MODE_NAME.fullmatch(mode):
            raise SurfaceError(f"{alias_where}: replacement mode is invalid")
        if mode not in target.get("modes", ()):
            raise SurfaceError(
                f"{alias_where}: replacement mode {mode!r} is not declared by {target_name!r}"
            )
        expected_reverse[target_name].append(alias)
        replacement_modes[target_name].append(mode)
        for descriptor in descriptors:
            alias_output, _ = _output_rel(f"commands/{alias}.md", descriptor)
            target_output, _ = _output_rel(f"commands/{target_name}.md", descriptor)
            if alias_output is not None and target_output is None:
                raise SurfaceError(
                    f"{alias_where}: target {target_name!r} is not installed on {descriptor.name}"
                )

    for name, metadata in normalized.items():
        if metadata["visibility"] not in canonical_visibilities:
            continue
        actual_routes = tuple(sorted(expected_reverse[name]))
        if metadata["legacyRoutes"] != actual_routes:
            raise SurfaceError(
                f"{where}: commands.{name}: legacy route closure mismatch; "
                f"declared={list(metadata['legacyRoutes'])!r}, actual={list(actual_routes)!r}"
            )
        actual_modes = tuple(sorted(replacement_modes[name]))
        if metadata.get("modes", ()) != actual_modes:
            raise SurfaceError(
                f"{where}: commands.{name}: modes must exactly close replacement modes; "
                f"declared={list(metadata.get('modes', ()))!r}, actual={list(actual_modes)!r}"
            )
        command_path = os.path.join(
            repo, "core", "surface", "commands", name + ".md"
        )
        command_where = f"core/surface/commands/{name}.md"
        command_text = _read_template(command_path, command_where)
        markers = [
            (match.group("mode"), match.group("route"))
            for match in _COMMAND_MODE_MARKER.finditer(command_text)
        ]
        expected_markers = sorted(
            (forward[route]["replacement"].split()[1], route)
            for route in metadata["legacyRoutes"]
        )
        if len(markers) != len(expected_markers) or set(markers) != set(expected_markers):
            missing_markers = sorted(set(expected_markers) - set(markers))
            extra_markers = sorted(set(markers) - set(expected_markers))
            raise SurfaceError(
                f"{command_where}: command-mode marker closure mismatch; "
                f"missing={missing_markers!r}, extra={extra_markers!r}"
            )

    result = dict(document)
    result["commands"] = normalized
    return result


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


def _codex_dispatch_policy(out):
    """Generate the explicit Codex dispatch policy from charter frontmatter."""
    entries = {}
    expected = frozenset().union(*_CODEX_POLICY_NAMES.values())
    for path in sorted(item for item in out if item.startswith("agents/")
                       and item.endswith(".md") and item != "agents/INDEX.md"):
        where = "plugins/ca-codex/" + path
        text = out[path].decode("utf-8")
        name = _frontmatter_value(text, "name", where)
        if not _PI_ROLE_NAME.fullmatch(name) or path != f"agents/{name}.md":
            raise SurfaceError(f"{where}: Codex charter name must match its filename")
        if name in entries:
            raise SurfaceError(f"{where}: duplicate Codex charter name {name!r}")
        entries[name] = _frontmatter_value(text, "classification", where)
    if frozenset(entries) != expected:
        missing = sorted(expected - set(entries))
        extra = sorted(set(entries) - expected)
        raise SurfaceError(
            f"plugins/ca-codex/agents: requires exactly the canonical {len(expected)} "
            f"charters (missing={missing!r}, extra={extra!r})"
        )
    for name in _CODEX_POLICY_NAMES["author"]:
        if entries[name] != "author":
            raise SurfaceError(
                f"plugins/ca-codex/agents/{name}.md: author policy requires "
                "classification: author"
            )
    for policy in ("read-only reviewer/extractor", "bounded writer/aggregator"):
        for name in _CODEX_POLICY_NAMES[policy]:
            if entries[name] != "reviewer":
                raise SurfaceError(
                    f"plugins/ca-codex/agents/{name}.md: {policy} requires "
                    "classification: reviewer"
                )

    def roles(policy):
        return ", ".join(
            f"`{name}`" for name in sorted(_CODEX_POLICY_NAMES[policy])
        )

    return "\n".join([
        "", "## Codex resource-charter dispatch", "",
        "These are packaged Markdown resource charters, not native Codex registrations.",
        "Read the named charter, create a host-provided generic agent thread with the charter and concrete assignment, and retain the returned thread ID/receipt whenever the workflow requires isolated evidence.",
        "Block a required review, isolation, or write-containment workflow when the host cannot provide it; use an inline fallback only where its canonical workflow explicitly permits one.",
        "", "## Codex dispatch policy (generated from charter frontmatter)", "",
        "| Policy class | Canonical roles | Codex type preference | Permission/write contract | Isolation and fallback | Model behavior |",
        "|---|---|---|---|---|---|",
        "| author | " + roles("author") + " | `worker` | write-enabled only inside the assigned worktree/scope; all writes still pass codeArbiter hooks | fresh isolated worktree/thread required; block if the workflow requires isolation and the host cannot provide it | host-supported configured model if an approved mapping exists; otherwise host default and record parity degradation |",
        "| read-only reviewer/extractor | " + roles("read-only reviewer/extractor") + " | `explorer` when available, otherwise `default` | no file mutation; use a host-enforced read-only sandbox when available | fresh thread; `scout`, map roles, and any workflow declaring isolated evidence block if isolation is unavailable; inline fallback only where the existing canonical workflow explicitly permits it | do not translate Claude `haiku`/`sonnet` names into invented Codex tiers; use an approved host mapping or record host-default degradation |",
        "| bounded writer/aggregator | " + roles("bounded writer/aggregator") + " | `worker` | writes limited to the charter-declared checkpoint/finding output path; all other writes prohibited and hooks remain active | fresh thread; no inline fallback where an exact per-agent receipt is required | approved host mapping or documented host-default degradation |",
        "", "Codex built-in type preference is not a permission boundary. Mandatory isolation or write containment blocks when unavailable; it must not silently degrade to prompt-only guidance.", "",
    ])


def _codex_agent_route_contract(out):
    """Generate the route-count receipt from the rendered Codex surface.

    The installed-package checker reads this receipt rather than relying on a
    hand-maintained count. Regeneration therefore changes the expected
    literal and generic route closure only when the canonical rendered surface
    changes deliberately.
    """
    literal_lines, generic_lines = set(), set()
    literal_occurrences = generic_occurrences = 0
    for source, payload in out.items():
        if not source.endswith(".md") or source == "agents/INDEX.md":
            continue
        for line_number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
            for match in _MARKDOWN_LINK_TARGET.finditer(line):
                target = match.group(1).strip().split("#", 1)[0]
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1].strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(source), target.replace("\\", "/"))
                )
                parts = resolved.split("/")
                if len(parts) != 2 or parts[0] != "agents" or not parts[1].endswith(".md"):
                    continue
                name = parts[1][:-len(".md")]
                if name in {"<agent>", "<name>"}:
                    generic_lines.add((source, line_number))
                    generic_occurrences += 1
                else:
                    literal_lines.add((source, line_number))
                    literal_occurrences += 1
    return (
        "\n<!-- codearbiter-codex-agent-route-contract: "
        f"literal_route_lines={len(literal_lines)} "
        f"literal_route_occurrences={literal_occurrences} "
        f"generic_route_lines={len(generic_lines)} "
        f"generic_route_occurrences={generic_occurrences} -->\n"
    )


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
            if rel == "command-routes.json":
                continue
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
    registry = _load_command_registry(repo, cmd_names, descriptors)
    resource_paths = set()
    for rel in rels:
        dst, _rule = _output_rel(rel, descriptor)
        if dst is not None:
            resource_paths.add(dst)
    plugin_root = os.path.join(repo, descriptor.plugin_dir.replace("/", os.sep))
    if os.path.isdir(plugin_root):
        managed = tuple(item.rstrip("/") for item in descriptor.managed_subtrees)
        for current, _dirs, files in os.walk(plugin_root):
            for filename in files:
                path = os.path.relpath(
                    os.path.join(current, filename), plugin_root
                ).replace(os.sep, "/")
                if any(path == item or path.startswith(item + "/") for item in managed):
                    continue
                resource_paths.add(path)
    resource_paths = frozenset(resource_paths)
    out = {}
    catalog = []  # installed command records for host catalogs and JSON sidecars
    for rel in rels:
        dst, rule = _output_rel(rel, descriptor)
        if dst is None:
            continue
        where = f"core/surface/{rel}"
        text = _read_template(os.path.join(surface, rel.replace("/", os.sep)), where)
        rendered = render_text(
            text, host, cmd_names, where, repo=repo,
            descriptor=descriptor, host_names=host_names, output_path=dst,
            resource_paths=resource_paths,
        )
        command_name = (
            rel[len("commands/"):-len(".md")]
            if rel.startswith("commands/") and rel.endswith(".md")
            else None
        )
        if rule.add_skill_frontmatter:
            name = command_name
            rendered = _synth_skill_frontmatter(rendered, name, where)
            frontmatter_end = rendered.find("\n---\n", 4)
            body = rendered[frontmatter_end + len("\n---\n"):]
            if "</skill>" in body:
                raise SurfaceError(
                    f"{where}: reserved </skill> terminator in generated skill body"
                )
        if command_name is not None:
            metadata = registry["commands"][command_name]
            entry = {
                "name": command_name,
                "description": _decoded_frontmatter_description(rendered, where),
                ("skillPath" if rule.add_skill_frontmatter else "commandPath"): dst,
                "visibility": metadata["visibility"],
                "workflow": metadata["workflow"],
            }
            for key in ("canonical", "replacement"):
                if key in metadata:
                    entry[key] = metadata[key]
            if "legacyRoutes" in metadata:
                entry["legacyRoutes"] = list(metadata["legacyRoutes"])
            catalog.append(entry)
        if dst in out:
            raise SurfaceError(f"{where}: output collision at "
                               f"{descriptor.plugin_dir}/{dst}")
        out[dst] = rendered.encode("utf-8")
    command_catalog = "COMMANDS.md"
    if command_catalog in out:
        rendered_catalog = out[command_catalog].decode("utf-8")
        marker = "<!-- command-visibility-summary -->"
        if rendered_catalog.count(marker) != 1:
            raise SurfaceError(
                "core/surface/COMMANDS.md: expected exactly one "
                f"{marker} marker"
            )
        out[command_catalog] = rendered_catalog.replace(
            marker, _visibility_count_table(catalog)
        ).encode("utf-8")
    if descriptor.catalog is not None:
        dst = descriptor.catalog
        if dst in out:
            raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the "
                               "generated skill catalog")
        out[dst] = _host_catalog(descriptor, catalog, registry).encode("utf-8")
    if descriptor.name == "codex" and "agents/INDEX.md" in out:
        dst = "agents/INDEX.md"
        out[dst] += _codex_dispatch_policy(out).encode("utf-8")
        out[dst] += _codex_agent_route_contract(out).encode("utf-8")
    dst = "generated/command-catalog.json"
    if dst in out:
        raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the "
                           "generated command catalog")
    catalog_document = {
        "schemaVersion": registry["schemaVersion"],
        "visibilityOrder": registry["visibilityOrder"],
        "workflowOrder": registry["workflowOrder"],
        "compatibility": registry["compatibility"],
        "commands": {
            entry["name"]: entry
            for entry in sorted(catalog, key=lambda item: item["name"])
        },
    }
    out[dst] = (
        json.dumps(catalog_document, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    if descriptor.name == "pi":
        dst = "generated/roles.json"
        if dst in out:
            raise SurfaceError(f"{descriptor.plugin_dir}/{dst} collides with the generated role catalog")
        out[dst] = (json.dumps(_pi_role_catalog(out), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return out


def _host_native_replacement(descriptor, entry):
    replacement = entry.get("replacement")
    if not replacement:
        return ""
    if entry["visibility"] != "alias":
        return replacement
    command, mode = replacement.split(" ", 1)
    return descriptor.command_form.format(name=command) + " " + mode


def _visibility_counts(entries):
    return {
        visibility: sum(entry["visibility"] == visibility for entry in entries)
        for visibility in _VISIBILITY_ORDER
    }


def _visibility_count_table(entries):
    counts = _visibility_counts(entries)
    canonical_count = counts["core"] + counts["advanced"]
    return "\n".join([
        "## Installed surface",
        "",
        "| Visibility | Count |",
        "|---|---:|",
        f"| Core | {counts['core']} |",
        f"| Advanced | {counts['advanced']} |",
        f"| Canonical total | {canonical_count} |",
        f"| Compatibility aliases | {counts['alias']} |",
        f"| Internal | {counts['internal']} |",
        f"| Deprecated | {counts['deprecated']} |",
        f"| **Total** | **{len(entries)}** |",
    ])


def _host_catalog(descriptor, entries, registry):
    labels = {
        "core": "Core",
        "advanced": "Advanced",
        "alias": "Compatibility aliases",
        "internal": "Internal",
        "deprecated": "Deprecated",
    }
    workflow_labels = {name: name.capitalize() for name in _WORKFLOW_ORDER}
    counts = _visibility_counts(entries)
    canonical_count = counts["core"] + counts["advanced"]
    lines = [
        f"# ca-{descriptor.name} skills — catalog (surface scan)",
        "",
        "Generated by tools/build-surface.py — edit core/surface/, never this file.",
        "Each entry skill wraps one governance command; a body loads only when its",
        "skill is invoked — never bulk-read this directory.",
        "",
        "## Installed surface",
        "",
        "| Visibility | Count |",
        "|---|---:|",
        f"| Core | {counts['core']} |",
        f"| Advanced | {counts['advanced']} |",
        f"| Canonical total | {canonical_count} |",
        f"| Compatibility aliases | {counts['alias']} |",
        f"| Internal | {counts['internal']} |",
        f"| Deprecated | {counts['deprecated']} |",
        f"| **Total** | **{len(entries)}** |",
    ]
    for visibility in registry["visibilityOrder"]:
        visibility_entries = [
            entry for entry in entries if entry["visibility"] == visibility
        ]
        if not visibility_entries:
            continue
        lines += ["", f"## {labels[visibility]}"]
        for workflow in registry["workflowOrder"]:
            group = sorted(
                (entry for entry in visibility_entries if entry["workflow"] == workflow),
                key=lambda entry: entry["name"],
            )
            if not group:
                continue
            with_replacement = visibility in ("alias", "deprecated")
            lines += ["", f"### {workflow_labels[workflow]}", ""]
            if with_replacement:
                lines += ["| Skill | Purpose | Replacement |", "|---|---|---|"]
            else:
                lines += ["| Skill | Purpose |", "|---|---|"]
            for entry in group:
                route = descriptor.command_form.format(name=entry["name"])
                if with_replacement:
                    replacement = _host_native_replacement(descriptor, entry)
                    replacement_cell = (
                        f"`{replacement}`" if visibility == "alias" else replacement
                    )
                    lines.append(
                        f"| `{route}` | {entry['description']} | {replacement_cell} |"
                    )
                else:
                    lines.append(f"| `{route}` | {entry['description']} |")
    return "\n".join(lines) + "\n"


def _disk_files(repo, descriptor):
    """Plugin-relative paths currently on disk inside the managed output set."""
    plugin = os.path.join(repo, descriptor.plugin_dir)
    found = set()
    managed_subtrees = descriptor.managed_subtrees
    if (descriptor.catalog is not None
            and descriptor.catalog not in managed_subtrees):
        managed_subtrees = managed_subtrees + (descriptor.catalog,)
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
