#!/usr/bin/env python3
"""Bounded stdlib bridge to an installation-pinned ca-artifact executable.

No imports perform I/O. No PATH search, environment-selected executable, schema
parser duplication, command execution from a document, or new host registration.
The caller supplies a trusted installation directory, never a repository setting.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile
import threading
from typing import Any

PROTOCOL = "codearbiter.artifact-api/0.1.0"
SCHEMA_VERSION = "0.3.1"
MAX_REQUEST = 8 << 20
MAX_RESPONSE = 65536
READ_OPERATIONS = frozenset({"capabilities", "schema", "read", "outline", "identity", "validate", "index", "snapshot", "diff", "repair-preview", "eligible", "farm-verify", "migration-preview"})


class ArtifactError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArtifactError("INVALID_RESPONSE", "duplicate JSON key")
        value[key] = item
    return value


def _decode(raw: bytes) -> Any:
    if len(raw) > MAX_RESPONSE:
        raise ArtifactError("INVALID_RESPONSE", "oversized JSON envelope")
    # Bound nesting independently of the interpreter's recursion-limit setting.
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 128:
                raise ArtifactError("INVALID_RESPONSE", "JSON nesting exceeds 128 levels")
        elif byte in (93, 125):
            depth -= 1
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ArtifactError("INVALID_RESPONSE", "invalid bounded JSON") from exc


def helper_installation(helper_file: str) -> Path:
    """Shipped helpers live in <plugin>/hooks; the trusted payload is a sibling.

    Source-checkout callers use an explicit installation instead of guessing a
    binary under the repository being governed.
    """
    return Path(helper_file).resolve().parent.parent / "helpers" / "artifacts"


def _open_pinned_regular(path: Path) -> int:
    """Open without following the final link and pin Windows replacement.

    The Windows handle shares reads only, so a verified executable cannot be
    replaced or opened for writing before CreateProcess consumes its path.
    """
    if os.name != "nt":
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        return os.open(path, flags)
    import ctypes
    import msvcrt
    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_void_p]
    create_file.restype = ctypes.c_void_p
    handle = create_file(str(path), 0x80000000, 0x00000001, None, 3,
                         0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateFileW failed", str(path))
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        raise


def _stage_darwin_executable(fd: int, directory: Path) -> Path:
    """Materialize verified descriptor bytes for macOS executable launch.

    macOS exposes inherited descriptors below /dev/fd but does not permit
    executing a native binary through that path. The caller supplies a fresh,
    private temporary directory; no installation or repository pathname is
    reopened while producing the executable image.
    """
    target = directory / "ca-artifact"
    output = os.open(
        target,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while chunk := os.read(fd, 1 << 20):
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(output, remaining)
                if written <= 0:
                    raise OSError("short write while staging verified executable")
                remaining = remaining[written:]
        os.fsync(output)
        os.fchmod(output, stat.S_IRUSR | stat.S_IXUSR)
    finally:
        os.close(output)
    return target


def _trusted_directory(path: str | Path, code: str) -> Path:
    requested = Path(path).absolute()
    try:
        if os.name == "nt":
            import ctypes
            attributes = ctypes.WinDLL("kernel32", use_last_error=True).GetFileAttributesW
            attributes.argtypes = [ctypes.c_wchar_p]
            attributes.restype = ctypes.c_uint32
            current = requested
            while current != current.parent:
                value = attributes(str(current))
                if value == 0xffffffff or value & 0x400:
                    raise OSError("reparse point or unreadable component")
                current = current.parent
        elif Path(os.path.realpath(requested)) != requested:
            raise OSError("symlink component")
        resolved = requested.resolve(strict=True)
        if not resolved.is_dir():
            raise OSError("not a directory")
        return resolved
    except OSError as exc:
        raise ArtifactError(code, "directory must be an existing real path without links or reparse points") from exc


def _workflow_path_exists(root: Path, path: Path) -> bool:
    """Inspect one canonical artifact path without following links or writing."""
    for parent in (root / ".codearbiter", path.parent):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ArtifactError(
                "UNSAFE_ARTIFACT_PATH", "canonical artifact directory is unreadable"
            ) from exc
        reparse = getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
        )
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise ArtifactError(
                "UNSAFE_ARTIFACT_PATH",
                "canonical artifact directory must be a real directory",
            )
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ArtifactError(
            "UNSAFE_ARTIFACT_PATH", "canonical artifact path is unreadable"
        ) from exc
    reparse = getattr(info, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
    )
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISREG(info.st_mode):
        raise ArtifactError(
            "UNSAFE_ARTIFACT_PATH", "canonical artifact path must be a regular file"
        )
    return True


def _resolve_workflow_pair(root: str | Path, slug: str) -> dict[str, object]:
    """Select an exact-format spec/plan authority without parsing or writing it."""
    trusted_root = _trusted_directory(root, "UNSAFE_ROOT")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,99}", slug):
        raise ArtifactError("INVALID_SLUG", "slug must match the canonical artifact slug grammar")

    candidates = {
        kind: {
            extension: trusted_root / ".codearbiter" / f"{kind}s" / f"{slug}.{extension}"
            for extension in ("md", "html")
        }
        for kind in ("spec", "plan")
    }
    present = {
        kind: [
            extension
            for extension, path in paths.items()
            if _workflow_path_exists(trusted_root, path)
        ]
        for kind, paths in candidates.items()
    }
    if len(present["spec"]) > 1 or len(present["plan"]) > 1:
        raise ArtifactError(
            "AMBIGUOUS_ARTIFACT", "multiple canonical files claim the workflow slug"
        )
    if present["plan"] and not present["spec"]:
        raise ArtifactError("ORPHAN_PLAN", "canonical plan has no matching spec")
    if present["spec"] and present["plan"] and present["spec"] != present["plan"]:
        raise ArtifactError(
            "AMBIGUOUS_ARTIFACT", "spec and plan use different authority formats"
        )

    extension = present["spec"][0] if present["spec"] else "html"
    state = "pair" if present["plan"] else "spec" if present["spec"] else "absent"
    return {
        "slug": slug,
        "format": extension,
        "state": state,
        "spec_path": candidates["spec"][extension],
        "plan_path": candidates["plan"][extension],
    }


def _installed_workflow_preflight(installation: Path) -> dict[str, object]:
    """Inspect installed prerequisites, not host trust or live-event evidence.

    This never imports an adapter, executes a hook, or writes consumer state.
    Package integrity and the actual authority boundaries remain separate checks.
    A successful engine capabilities call alone cannot admit a host workflow.
    """
    result: dict[str, object] = {
        "host": None, "adapter_version": None, "resources_available": False,
        "evidence_kind": "installed-resource-preflight", "live_host_verified": False,
        "missing": [],
    }
    missing: list[str] = []
    if installation.name != "artifacts" or installation.parent.name != "helpers":
        result["missing"] = ["installed host package layout"]
        return result
    plugin = installation.parent.parent

    def resource(relative: str, *, document: bool = False):
        path = plugin / relative
        try:
            _trusted_directory(installation, "HOST_WORKFLOW_UNAVAILABLE")
            _trusted_directory(path.parent, "HOST_WORKFLOW_UNAVAILABLE")
            descriptor = _open_pinned_regular(path)
            try:
                info = os.fstat(descriptor)
                reparse = getattr(info, "st_file_attributes", 0) & getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                if reparse or not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                    raise OSError("required installed resource is not a nonempty regular file")
                return _decode(os.read(descriptor, MAX_RESPONSE + 1)) if document else True
            finally:
                os.close(descriptor)
        except (OSError, ArtifactError):
            missing.append(relative)
            return None

    manifests = [("claude", "ca", ".claude-plugin/plugin.json"),
                 ("codex", "ca-codex", ".codex-plugin/plugin.json")]
    present = [row for row in manifests if (plugin / row[2]).exists()
               or (plugin / row[2]).is_symlink()]
    if not present:
        present = [("pi", "ca-pi", "package.json")]
    if len(present) != 1:
        result["missing"] = ["one unambiguous installed host manifest"]
        return result
    host, name, manifest_path = present[0]
    manifest = resource(manifest_path, document=True)
    if (not isinstance(manifest, dict) or manifest.get("name") != name
            or not isinstance(manifest.get("version"), str)
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?",
                            manifest["version"]) is None):
        result["missing"] = ["matching installed host identity"]
        return result
    result.update(host=host, adapter_version=manifest["version"])
    if host == "pi":
        result["missing"] = ["Pi production prompt, verification and review authority"]
        return result

    for filename in ("_approvallib.py", "_prerequisitelib.py", "_sprintapprovallib.py",
                     "_reconciliationlib.py", "_artifactauthoritylib.py", "_gitexec.py", "_replylib.py",
                     "artifact-authority.py", "artifact-authority-hook.py", "prompt-submit.py"):
        resource("hooks/" + filename)
    if host == "claude":
        resource("agents/authority-reviewer.md")
    registry = resource("hooks/hooks.json", document=True)
    hooks = registry.get("hooks") if isinstance(registry, dict) else None
    if not isinstance(hooks, dict):
        result["missing"] = sorted(set(missing + ["valid installed hook registry"]))
        return result

    token = "${CLAUDE_PLUGIN_ROOT}" if host == "claude" else "${PLUGIN_ROOT}"
    command_field = "commandWindows" if host == "codex" and platform.system() == "Windows" else "command"

    def registered(event: str, tool: str | None, script: str) -> bool:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            return False
        commands = {f'{python} "{token}/hooks/{script}"' for python in ("python", "python3")}
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher", "")
            if not isinstance(matcher, str):
                continue
            # Check the shipped literal alternatives, not a second regex DSL.
            if (tool is None and matcher not in {"", "*"}) or (
                    tool is not None and tool not in matcher.split("|")):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            if any(isinstance(entry, dict) and entry.get("type") == "command"
                   and entry.get("async", False) is False
                   and isinstance(entry.get(command_field), str)
                   and entry[command_field] in commands for entry in entries):
                return True
        return False

    required = [("UserPromptSubmit", None, "prompt-submit.py")]
    tools = ("Bash", "Agent") if host == "claude" else (
        "Bash", "shell_command", "exec_command", "unified_exec", "spawn_agent")
    required += [(event, tool, "artifact-authority-hook.py")
                 for event in ("PreToolUse", "PostToolUse") for tool in tools]
    required += [(event, None, "artifact-authority-hook.py")
                 for event in ("SubagentStart", "SubagentStop")]
    if host == "claude":
        required += [("PostToolUseFailure", "Bash", "artifact-authority-hook.py"),
                     ("PreToolUse", "SendMessage", "artifact-authority-hook.py")]
    missing.extend(f"{event}:{tool or '*'}:{script}"
                   for event, tool, script in required if not registered(event, tool, script))
    result["missing"] = sorted(set(missing))
    result["resources_available"] = not missing
    return result


def _require_host_workflow(client: "ArtifactClient") -> None:
    readiness = client.workflow_preflight()
    if readiness["resources_available"] is not True:
        raise ArtifactError(
            "HOST_WORKFLOW_UNAVAILABLE",
            ("installed HTML workflow prerequisites are unavailable: "
             + ", ".join(readiness["missing"]))[:400]
            + "; repair this package or use a supported host; no fallback artifacts",
        )


# The native engine ships only through the release distribution channels, never
# through a main-branch checkout, so the repair is always "install from the
# channel". Named concretely so the user is not left to guess (ADR-0040).
PAYLOAD_REPAIR_HINT = (
    "Claude Code: /plugin marketplace update codearbiter, then /plugin update ca@codearbiter; "
    "Codex (registered without --ref): codex plugin remove ca-codex@codearbiter, "
    "codex plugin marketplace remove codearbiter, "
    "codex plugin marketplace add arbiterForge/codeArbiter --ref ca-codex-marketplace, "
    "then codex plugin add ca-codex@codearbiter; Pi: pi install npm:@arbiterforge/ca-pi"
)


def _require_authoring_capability(client: "ArtifactClient") -> None:
    """Fail one default-HTML route with a bounded repair diagnostic."""
    try:
        capabilities = client.call("capabilities")
    except ArtifactError as exc:
        raise ArtifactError(
            "CAPABILITY_MISSING",
            f"repair or reinstall the pinned artifact payload ({exc.code}); "
            f"new HTML work cannot fall back to Markdown. Repair: {PAYLOAD_REPAIR_HINT}",
        ) from exc
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("repository_operations_available") is not True
        or capabilities.get("host_default_enabled") is not True
    ):
        raise ArtifactError(
            "CAPABILITY_MISSING",
            "repair or reinstall the qualified default-on artifact payload; "
            f"new HTML work cannot fall back to Markdown. Repair: {PAYLOAD_REPAIR_HINT}",
        )


def _select_authoring_route(
    root: str | Path,
    slug: str,
    *,
    workflow: str,
    lane: str,
    client: object | None = None,
    html_requested: bool = False,
) -> dict[str, object]:
    """Select inline or exact-format authoring without creating artifacts."""
    if workflow not in {"feature", "sprint"}:
        raise ArtifactError("INVALID_WORKFLOW", "workflow must be feature or sprint")
    if lane not in {"small", "full"}:
        raise ArtifactError("INVALID_LANE", "lane must be small or full")
    if type(html_requested) is not bool:
        raise ArtifactError(
            "INVALID_ROUTE", "html_requested must be an explicit boolean"
        )
    # Retain the rollout-era keyword for internal caller compatibility. It no
    # longer opts an absent full-lane slug back into Markdown authority.
    if lane == "small":
        return {
            "workflow": workflow,
            "lane": lane,
            "mode": "inline",
            "slug": slug,
            "spec_path": None,
            "plan_path": None,
        }

    selected = _resolve_workflow_pair(root, slug)
    if selected["format"] == "html":
        trusted_root = Path(selected["spec_path"]).parent.parent.parent
        if type(client) is not ArtifactClient or client.root != trusted_root:
            raise ArtifactError(
                "CAPABILITY_MISSING",
                "an installation-pinned artifact client bound to this repository is required",
            )
        _require_authoring_capability(client)
        if _resolve_workflow_pair(root, slug) != selected:
            raise ArtifactError("STALE_ROUTE", "artifact namespace changed during the capability probe")
        _require_host_workflow(client)
        if _resolve_workflow_pair(root, slug) != selected:
            raise ArtifactError(
                "STALE_ROUTE",
                "artifact namespace changed during the installed host preflight",
            )
    return {"workflow": workflow, "lane": lane, "mode": "artifact", **selected}


def _preflight_plan_authoring(
    selected: dict[str, object],
    client: object,
    *,
    spec_artifact_id: str,
    spec_normative_sha256: str,
    draft_for_pair: bool = False,
) -> Path:
    """Verify the exact spec. Only initial sprint-pair preparation admits a ready draft.

    Draft preparation never approves the spec or plan and never permits execution.
    The ordinary feature/sequential path still requires an approved spec.
    """
    if type(draft_for_pair) is not bool:
        raise ArtifactError("INVALID_ROUTE", "draft_for_pair must be an explicit boolean")
    if draft_for_pair and (not isinstance(selected, dict) or selected.get("workflow") != "sprint" or selected.get("lane") != "full"):
        raise ArtifactError("INVALID_ROUTE", "draft preview is limited to full-lane initial sprint pairs")
    if not isinstance(selected, dict):
        raise ArtifactError("INVALID_ROUTE", "plan authoring requires a selected route")
    slug = selected.get("slug")
    spec_path = selected.get("spec_path")
    plan_path = selected.get("plan_path")
    if (
        selected.get("mode") != "artifact"
        or selected.get("format") != "html"
        or selected.get("state") != "spec"
        or not isinstance(slug, str)
        or not isinstance(spec_path, Path)
        or not isinstance(plan_path, Path)
    ):
        raise ArtifactError(
            "INVALID_ROUTE",
            "plan authoring requires one existing HTML spec and no plan",
        )
    root = spec_path.parent.parent.parent
    current = _resolve_workflow_pair(root, slug)
    if any(
        current.get(field) != selected.get(field)
        for field in ("slug", "format", "state", "spec_path", "plan_path")
    ):
        raise ArtifactError("STALE_ROUTE", "selected artifact route is no longer current")
    if (
        spec_path != root / ".codearbiter" / "specs" / f"{slug}.html"
        or plan_path != root / ".codearbiter" / "plans" / f"{slug}.html"
    ):
        raise ArtifactError("INVALID_ROUTE", "plan target must match the HTML spec slug")
    if type(client) is not ArtifactClient or client.root != root:
        raise ArtifactError(
            "CAPABILITY_MISSING",
            "an installation-pinned artifact client must be bound to the selected repository",
        )
    if not isinstance(spec_artifact_id, str) or not spec_artifact_id:
        raise ArtifactError("AUTHORITY_MISMATCH", "spec artifact identity is required")
    if not isinstance(spec_normative_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", spec_normative_sha256
    ):
        raise ArtifactError("AUTHORITY_MISMATCH", "spec normative digest is invalid")

    _require_host_workflow(client)
    identity = client.call("identity", {"artifact_id": spec_artifact_id})
    expected_path = f".codearbiter/specs/{slug}.html"
    if (
        identity.get("artifact_id") != spec_artifact_id
        or identity.get("kind") != "spec"
        or identity.get("path") != expected_path
        or identity.get("normative_sha256") != spec_normative_sha256
    ):
        raise ArtifactError(
            "AUTHORITY_MISMATCH",
            "caller spec identity does not match the selected current HTML spec",
        )
    approved = client.call(
        "validate",
        {"artifact_id": spec_artifact_id, "gate": "ready" if draft_for_pair else "approved"},
        permit_invalid=True,
    )
    authority = approved.get("authority")
    if (
        approved.get("valid") is not True
        or approved.get("artifact_id") != spec_artifact_id
        or approved.get("normative_sha256") != spec_normative_sha256
        or not isinstance(authority, dict)
        or approved.get("model_sha256") != identity.get("model_sha256")
        or authority.get("state") != ("draft" if draft_for_pair else "approved")
        or authority.get("authority_verified") is not (not draft_for_pair)
    ):
        raise ArtifactError(
            "AUTHORITY_UNVERIFIED",
            "plan authoring requires the exact current ready and approved spec",
        )
    if _resolve_workflow_pair(root, slug) != current:
        raise ArtifactError(
            "STALE_ROUTE",
            "artifact namespace changed during plan-authoring preflight",
        )
    return plan_path


def _preflight_current_acceptance(
    selected: dict[str, object],
    client: object,
    *,
    spec_artifact_id: str,
    plan_artifact_id: str,
) -> dict[str, object]:
    """Return engine-bound proof that one exact HTML pair is currently accepted.

    This is a private workflow boundary, not a public command. Caller-provided
    labels, hashes, state, or receipts are deliberately outside its input shape.
    """
    route_fields = {"slug", "format", "state", "spec_path", "plan_path"}
    if not isinstance(selected, dict) or set(selected) != route_fields:
        raise ArtifactError(
            "INVALID_ROUTE",
            "current acceptance requires an exact resolver-produced route",
        )
    slug = selected.get("slug")
    spec_path = selected.get("spec_path")
    plan_path = selected.get("plan_path")
    if (
        selected.get("format") != "html"
        or selected.get("state") != "pair"
        or not isinstance(slug, str)
        or not isinstance(spec_path, Path)
        or not isinstance(plan_path, Path)
    ):
        raise ArtifactError(
            "INVALID_ROUTE", "current acceptance requires one complete HTML pair"
        )
    root = spec_path.parent.parent.parent
    if (
        spec_path != root / ".codearbiter" / "specs" / f"{slug}.html"
        or plan_path != root / ".codearbiter" / "plans" / f"{slug}.html"
    ):
        raise ArtifactError(
            "INVALID_ROUTE", "selected paths must be the canonical same-slug HTML pair"
        )
    current = _resolve_workflow_pair(root, slug)
    if any(current.get(field) != selected.get(field) for field in route_fields):
        raise ArtifactError(
            "STALE_ROUTE", "selected HTML pair is no longer the sole current authority"
        )
    if type(client) is not ArtifactClient or client.root != root:
        raise ArtifactError(
            "CAPABILITY_MISSING",
            "an installation-pinned artifact client must be bound to the selected repository",
        )
    if not all(
        isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_-]{0,127}", value)
        for value in (spec_artifact_id, plan_artifact_id)
    ):
        raise ArtifactError(
            "AUTHORITY_MISMATCH", "exact spec and plan artifact identities are required"
        )

    expected = {
        "spec": f".codearbiter/specs/{slug}.html",
        "plan": f".codearbiter/plans/{slug}.html",
    }
    entries = {}
    for kind, artifact_id in (
        ("spec", spec_artifact_id),
        ("plan", plan_artifact_id),
    ):
        matches = [entry for entry in client.index(kind) if entry.get("path") == expected[kind]]
        if len(matches) != 1 or matches[0].get("artifact_id") != artifact_id:
            raise ArtifactError(
                "AUTHORITY_MISMATCH",
                f"caller {kind} identity does not match the selected HTML pair",
            )
        entries[kind] = matches[0]

    identities = {}
    for kind, artifact_id in (
        ("spec", spec_artifact_id),
        ("plan", plan_artifact_id),
    ):
        identity = client.call("identity", {"artifact_id": artifact_id})
        authority = identity.get("authority")
        if (
            identity.get("artifact_id") != artifact_id
            or identity.get("kind") != kind
            or identity.get("path") != expected[kind]
            or identity.get("model_sha256") != entries[kind].get("model_sha256")
            or identity.get("normative_sha256")
            != entries[kind].get("normative_sha256")
            or not isinstance(authority, dict)
            or authority.get("state") != "approved"
            or authority.get("authority_verified") is not True
        ):
            raise ArtifactError(
                "AUTHORITY_UNVERIFIED",
                f"selected {kind} lacks exact current workflow approval",
            )
        identities[kind] = identity

    eligible = client.call("eligible", {"artifact_id": plan_artifact_id})
    if (
        eligible.get("artifact_id") != plan_artifact_id
        or eligible.get("model_sha256") != identities["plan"].get("model_sha256")
        or eligible.get("all_accepted_and_current") is not True
        or not isinstance(eligible.get("tasks"), list)
        or not eligible["tasks"]
        or any(
            not isinstance(task, dict)
            or task.get("state") != "ACCEPTED"
            or task.get("current_evidence") is not True
            for task in eligible["tasks"]
        )
    ):
        raise ArtifactError(
            "ACCEPTANCE_REQUIRED",
            "the exact selected HTML plan is not fully accepted with current evidence",
        )

    task_ids = [
        record.get("id")
        for record in client.outline(plan_artifact_id)
        if record.get("kind") == "tasks" and record.get("retired") is False
    ]
    if not task_ids or any(not isinstance(task_id, str) for task_id in task_ids):
        raise ArtifactError("INVALID_RESPONSE", "accepted plan has no live task identity")
    pages = list(client.contextual_pages(plan_artifact_id, task_ids[0], 65536))
    if not pages:
        raise ArtifactError("INVALID_RESPONSE", "engine returned no acceptance context")
    records = {
        item.get("key"): item.get("record")
        for page in pages
        for item in page.get("items", [])
        if isinstance(item, dict)
    }
    plan_context = records.get(f"{plan_artifact_id}#@context")
    spec_context = records.get(f"{spec_artifact_id}#@context")
    spec_ref = plan_context.get("spec_ref") if isinstance(plan_context, dict) else None
    if (
        not isinstance(spec_context, dict)
        or not isinstance(spec_ref, dict)
        or spec_ref.get("artifact_id") != spec_artifact_id
        or spec_ref.get("normative_sha256")
        != identities["spec"].get("normative_sha256")
        or spec_ref.get("binding_mode") != "approved_source"
    ):
        raise ArtifactError(
            "AUTHORITY_MISMATCH",
            "selected plan is not bound to the exact approved HTML spec",
        )
    final_page = pages[-1]
    receipts = {
        "context_ticket": final_page.get("context_ticket"),
        "vector_sha256": final_page.get("vector_sha256"),
        "manifest_sha256": final_page.get("manifest_sha256"),
        "input_sha256": eligible.get("input_sha256"),
    }
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in receipts.values()
    ):
        raise ArtifactError(
            "INVALID_RESPONSE", "engine acceptance proof lacks bounded receipt identities"
        )

    final_spec = client.call("identity", {"artifact_id": spec_artifact_id})
    final_plan = client.call("identity", {"artifact_id": plan_artifact_id})
    final_eligible = client.call("eligible", {"artifact_id": plan_artifact_id})
    if (
        final_spec.get("model_sha256") != identities["spec"].get("model_sha256")
        or final_plan.get("model_sha256") != identities["plan"].get("model_sha256")
        or final_eligible != eligible
    ):
        raise ArtifactError(
            "STALE_ROUTE", "artifact identity or acceptance changed during preflight"
        )
    final_route = _resolve_workflow_pair(root, slug)
    if final_route != selected:
        raise ArtifactError(
            "STALE_ROUTE", "selected HTML pair changed during acceptance preflight"
        )
    return {
        "spec_identity": identities["spec"],
        "plan_identity": identities["plan"],
        "eligible": eligible,
        "receipts": receipts,
    }


def _bounded_child(argv: list[str], request: bytes, fd: int, timeout: float) -> tuple[int, bytes, bytes]:
    options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   close_fds=True, start_new_session=True, env={})
    if os.name != "nt":
        options["pass_fds"] = (fd,)
    process = subprocess.Popen(argv, **options)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(pipe, slot, limit):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    return
                if len(buffers[slot]) + len(chunk) > limit:
                    overflow.set()
                    process.kill()
                    return
                buffers[slot].extend(chunk)
        finally:
            pipe.close()

    def write():
        try:
            process.stdin.write(request)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threads = [threading.Thread(target=drain, args=(process.stdout, 0, MAX_RESPONSE), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, 1, 8192), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join(timeout=2)
    if timed_out:
        raise ArtifactError("TIMEOUT", "subprocess interrupted; reconcile mutation operation_id before retry")
    if overflow.is_set() or any(t.is_alive() for t in threads):
        raise ArtifactError("RESPONSE_TOO_LARGE", "subprocess output exceeded its contract")
    return process.returncode, bytes(buffers[0]), bytes(buffers[1])


class ArtifactClient:
    def __init__(self, root: str | Path, installation: str | Path, *, timeout: float = 30):
        self.root = _trusted_directory(root, "UNSAFE_ROOT")
        self.installation = _trusted_directory(installation, "CAPABILITY_MISSING")
        self.timeout = timeout

    def workflow_preflight(self) -> dict[str, object]:
        """Read fresh installed prerequisites; never attest live host authority."""
        return _installed_workflow_preflight(self.installation)

    def _open_binary(self) -> int:
        system = {"Linux":"linux", "Darwin":"darwin", "Windows":"windows"}.get(platform.system())
        arch = {"x86_64":"amd64", "amd64":"amd64", "aarch64":"arm64", "arm64":"arm64"}.get(platform.machine().lower())
        if system is None or arch is None:
            raise ArtifactError("UNSUPPORTED_PLATFORM", "unsupported architecture")
        manifest_path = self.installation / "release.json"
        try:
            mf = _open_pinned_regular(manifest_path)
            try:
                info = os.fstat(mf)
                if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                    raise ArtifactError("INVALID_INSTALLATION", "release manifest must be a bounded regular file")
                raw = os.read(mf, 65537)
                if len(raw) > 65536:
                    raise ArtifactError("INVALID_INSTALLATION", "oversized release manifest")
            finally:
                os.close(mf)
            try:
                manifest = _decode(raw)
            except ArtifactError as exc:
                raise ArtifactError("INVALID_INSTALLATION", "invalid release manifest JSON") from exc
            if not isinstance(manifest, dict) or set(manifest) != {"format", "version", "protocol", "schema_version", "binaries"}:
                raise ArtifactError("INVALID_INSTALLATION", "unexpected release manifest")
            if manifest["format"] != "codearbiter.artifact-release/0.1.0" or manifest["protocol"] != PROTOCOL or manifest["schema_version"] != SCHEMA_VERSION:
                raise ArtifactError("UNSUPPORTED_VERSION", "installed binary/adapter version mismatch")
            if not isinstance(manifest["binaries"], dict) or not isinstance(manifest["version"], str):
                raise ArtifactError("INVALID_INSTALLATION", "malformed release manifest fields")
            entry = manifest["binaries"].get(f"{system}/{arch}")
            if not isinstance(entry, dict) or set(entry) != {"file", "sha256", "native_tested"}:
                raise ArtifactError("CAPABILITY_MISSING", "no matching tested binary in the installation")
            if entry["native_tested"] is not True:
                raise ArtifactError("UNVERIFIED_PLATFORM", "cross-compilation is not native qualification")
            name = entry["file"]
            expected_name = f"ca-artifact-{system}-{arch}" + (".exe" if system == "windows" else "")
            if name != expected_name:
                raise ArtifactError("INVALID_INSTALLATION", "binary filename does not match the selected platform")
            if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise ArtifactError("INVALID_INSTALLATION", "binary digest is malformed")
            binary_path = self.installation / name
            fd = _open_pinned_regular(binary_path)
        except OSError as exc:
            raise ArtifactError("CAPABILITY_MISSING", "install the pinned artifact payload; no PATH fallback is permitted") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_size > 32 << 20
                    or (system != "windows" and not info.st_mode & stat.S_IXUSR)):
                raise ArtifactError("INVALID_INSTALLATION", "binary is not a bounded executable regular file")
            digest = hashlib.sha256()
            while chunk := os.read(fd, 1 << 20):
                digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ArtifactError("PACKAGE_INTEGRITY", "installed executable bytes differ from release manifest")
            os.lseek(fd, 0, os.SEEK_SET)
            header = os.read(fd, 4)
            magic = {"linux":(b"\x7fELF",), "darwin":(b"\xcf\xfa\xed\xfe",b"\xca\xfe\xba\xbe",b"\xbe\xba\xfe\xca"), "windows":(b"MZ",)}[system]
            if not header.startswith(magic):
                raise ArtifactError("INVALID_INSTALLATION", "unexpected native executable format")
            os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def call(self, operation: str, request: dict[str, Any] | None = None, *, permit_invalid: bool = False) -> dict:
        if not re.fullmatch(r"[a-z][a-z-]{0,39}", operation):
            raise ArtifactError("UNKNOWN_OPERATION", "invalid internal operation name")
        request = dict(request or {})
        if "protocol" in request and request["protocol"] != PROTOCOL:
            raise ArtifactError("UNSUPPORTED_VERSION", "request protocol mismatch")
        request["protocol"] = PROTOCOL
        try:
            raw = json.dumps(request, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise ArtifactError("INVALID_REQUEST", "request must contain finite JSON values") from exc
        if len(raw) > MAX_REQUEST:
            raise ArtifactError("REQUEST_TOO_LARGE", "request exceeds 8 MiB")
        fd = self._open_binary()
        try:
            # Execute the verified open descriptor, not a raceable pathname.
            if platform.system() == "Linux":
                executable = f"/proc/self/fd/{fd}"
            elif platform.system() == "Darwin":
                with tempfile.TemporaryDirectory(prefix="ca-artifact-exec-") as temporary:
                    try:
                        directory = Path(os.path.realpath(temporary))
                        executable = _stage_darwin_executable(fd, directory)
                        os.chmod(directory, stat.S_IRUSR | stat.S_IXUSR)
                        code, stdout, stderr = _bounded_child(
                            [str(executable), operation, "--root", str(self.root), "--request", "-"],
                            raw, fd, self.timeout)
                    except OSError as exc:
                        raise ArtifactError(
                            "CAPABILITY_MISSING",
                            "could not stage the verified macOS artifact executable",
                        ) from exc
                    finally:
                        os.chmod(directory, stat.S_IRWXU)
                executable = None
            else:
                executable = str(self.installation / self._binary_name())
            if executable is not None:
                code, stdout, stderr = _bounded_child(
                    [executable, operation, "--root", str(self.root), "--request", "-"],
                    raw, fd, self.timeout)
        finally:
            os.close(fd)
        result = _decode(stdout)
        if not isinstance(result, dict) or result.get("protocol") != PROTOCOL or result.get("operation") != operation or not isinstance(result.get("ok"), bool):
            raise ArtifactError("INVALID_RESPONSE", "subprocess response does not match request")
        if not result["ok"]:
            error = result.get("error")
            if (set(result) != {"protocol", "operation", "ok", "error"}
                    or not isinstance(error, dict)
                    or not {"code", "message"} <= set(error)
                    or set(error) - {"code", "message", "symbol", "field", "operation_id"}
                    or any(not isinstance(v, str) for v in error.values())
                    or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", error["code"])
                    or code == 0):
                raise ArtifactError("INVALID_RESPONSE", "malformed failure envelope")
            raise ArtifactError(error["code"], error["message"][:512])
        if set(result) != {"protocol", "operation", "ok", "result"} or not isinstance(result.get("result"), dict):
            raise ArtifactError("INVALID_RESPONSE", "malformed success envelope")
        if code != 0 and not (permit_invalid and operation == "validate" and code == 2 and result["result"].get("valid") is False):
            raise ArtifactError("SUBPROCESS_FAILED", f"operation returned exit {code}")
        if not isinstance(result.get("result"), dict):
            raise ArtifactError("INVALID_RESPONSE", "subprocess result must be an object")
        return result["result"]

    @staticmethod
    def _binary_name() -> str:
        system = {"Linux":"linux", "Darwin":"darwin", "Windows":"windows"}[platform.system()]
        arch = {"x86_64":"amd64", "amd64":"amd64", "aarch64":"arm64", "arm64":"arm64"}[platform.machine().lower()]
        return f"ca-artifact-{system}-{arch}" + (".exe" if system == "windows" else "")

    @staticmethod
    def _check_page(page: dict, offset: int, field: str):
        values = page.get(field)
        if not isinstance(values, list) or "next_offset" not in page:
            raise ArtifactError("INVALID_RESPONSE", "malformed bounded page")
        next_offset = page["next_offset"]
        if next_offset is not None and (type(next_offset) is not int or next_offset <= offset or not values):
            raise ArtifactError("INVALID_RESPONSE", "pagination must make forward progress")

    def index(self, kind: str | None = None):
        request = {"budget": 16384}
        if kind:
            request["kind"] = kind
        for _ in range(1025):
            page = self.call("index", request)
            self._check_page(page, request.get("offset", 0), "entries")
            yield from page["entries"]
            if page["next_offset"] is None:
                return
            request.update(offset=page["next_offset"], catalog_sha256=page["catalog_sha256"])
        raise ArtifactError("INVALID_RESPONSE", "index did not terminate")

    def outline(self, artifact_id: str):
        request = {"artifact_id": artifact_id, "budget": 16384}
        for _ in range(8193):
            page = self.call("outline", request)
            self._check_page(page, request.get("offset", 0), "records")
            yield from page["records"]
            if page["next_offset"] is None:
                return
            request.update(offset=page["next_offset"], model_sha256=page["model_sha256"])
        raise ArtifactError("INVALID_RESPONSE", "outline did not terminate")

    def contextual_pages(self, artifact_id: str, symbol: str, budget: int = 16384):
        request = {"artifact_id": artifact_id, "symbol": symbol, "mode": "contextual", "budget": budget}
        for _ in range(8193):
            page = self.call("read", request)
            complete = page.get("context_complete")
            if type(complete) is not bool:
                raise ArtifactError("INVALID_RESPONSE", "context page lacks a completeness flag")
            if not complete and (not page.get("next_cursor") or page["next_cursor"] == request.get("cursor")):
                raise ArtifactError("INCOMPLETE_CONTEXT", "incomplete context must have an advancing continuation")
            yield page
            if complete:
                return
            request["cursor"] = page["next_cursor"]
        raise ArtifactError("INVALID_RESPONSE", "context did not terminate")


def has_html(root: str | Path) -> bool:
    root = Path(root)
    return any(
        next((root / ".codearbiter" / kind).glob("*.html"), None) is not None for kind in ("specs", "plans"))


def checked_spec_index(root, installation) -> list[dict]:
    """Fresh per-call authority validation, deliberately not an mtime cache."""
    if not has_html(root):
        return []
    client = ArtifactClient(root, installation)
    return [{"spec": x["artifact_id"], "path": x["path"], "globs": x.get("governs") or [], "artifact_html": True}
            for x in client.index("spec") if x["authority"]["authority_verified"] and x.get("governs")]


def resolve_spec_file(filename, installation) -> tuple[ArtifactClient, dict]:
    path = Path(filename).absolute()
    if path.suffix != ".html" or path.parent.name != "specs" or path.parent.parent.name != ".codearbiter":
        raise ArtifactError("INVALID_PATH", "expected canonical HTML spec path")
    root = path.parent.parent.parent
    client = ArtifactClient(root, installation)
    relative = path.relative_to(root).as_posix()
    matches = [x for x in client.index("spec") if x["path"] == relative]
    if len(matches) != 1:
        raise ArtifactError("SPEC_NOT_FOUND", "canonical path did not resolve uniquely")
    return client, matches[0]
