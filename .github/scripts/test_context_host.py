#!/usr/bin/env python3
"""Source-contract tests for context-onboarding scout containment.

These checks do not qualify a live child or turn a host capability claim into
observed read-only enforcement. That requires an authorized host exercise.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pathlib import PurePosixPath
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/pysrc"))
import _contextselectlib as selector
import _readinjectlib as readinject
DESCRIPTORS = ROOT / "tools/host_descriptors.py"
_spec = importlib.util.spec_from_file_location("host_descriptors", DESCRIPTORS)
_hosts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hosts)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


NATIVE_CATALOG = ROOT / ".github/fixtures/context-onboarding/host-cells.json"
NATIVE_FORMAT = "codearbiter.native-loading-cells/0.1"


CONTEXT_PROFILE_FORMAT = "codearbiter.context-scout-profile/0.1"


def context_hash_command(path: str) -> str:
    """Return one canonical read-only Git command for a frozen source path."""
    rel = _context_rel(path)
    # The closed grammar is independent of a caller's shell or shlex settings.
    return "git hash-object -- '" + rel.replace("'", "'\\''") + "'"


def _context_rel(path: str) -> str:
    rel = _native_rel(path)
    parts = PurePosixPath(rel).parts
    if (any(part == ".git" or part == ".env" or
            (part.startswith(".env.") and part != ".env.example") for part in parts) or
            any(ord(char) < 32 for char in rel)):
        raise ValueError("excluded context source path")
    return rel


def _context_regular_file(root: Path, rel: str) -> Path:
    target = root
    for part in PurePosixPath(rel).parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("context source path uses a symlink")
    if not target.is_file() or not target.resolve().is_relative_to(root):
        raise ValueError("context source path is not an in-snapshot regular file")
    return target


def _context_git_binding(root: Path, paths: list[str], git_identity: dict) -> dict:
    """Bind effective Git/config/attributes before any plain hash is allowed."""
    # The Bash tool may evaluate a startup file before the exact command runs,
    # and Git can load process code before its clean-filter attributes are read.
    # The caller must launch the native phase with these absent; the guard
    # rechecks them on every hash attempt. A source check is not OS containment.
    hazardous = [key for key in os.environ if
                 key in {"BASH_ENV", "ENV", "BASHOPTS", "SHELLOPTS", "IFS",
                         "GCONV_PATH", "LOCPATH", "LIBPATH", "SHLIB_PATH"} or
                 key.startswith(("BASH_FUNC_", "LD_", "DYLD_", "GIT_TRACE"))]
    if hazardous:
        raise ValueError("untrusted shell or loader environment")
    if (not isinstance(git_identity, dict) or
            set(git_identity) != {"executable", "sha256"} or
            not isinstance(git_identity["executable"], str) or
            not Path(git_identity["executable"]).is_absolute() or
            not isinstance(git_identity["sha256"], str) or
            not re.fullmatch(r"[0-9a-f]{64}", git_identity["sha256"])):
        raise ValueError("pinned trusted Git identity required")
    resolved = Path(git_identity["executable"]).resolve(strict=True)
    selected = shutil.which("git")
    if (not resolved.is_file() or resolved.is_relative_to(root) or
            not selected or Path(selected).resolve(strict=True) != resolved or
            sha256_file(resolved) != git_identity["sha256"]):
        raise ValueError("Git executable differs from pinned trusted identity")
    env = {key: value for key, value in os.environ.items()
           if key.startswith("GIT_") or key in ("PATH", "HOME", "XDG_CONFIG_HOME")}
    commands = (("config", "--show-origin", "--list", "-z"),
                ("check-attr", "-z", "filter", "--", *paths))
    captured = []
    for argv in commands:
        try:
            result = subprocess.run([str(resolved), *argv], cwd=root,
                                    capture_output=True, check=False, timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Git configuration check timed out") from exc
        if result.returncode or len(result.stdout) > 1_048_576:
            raise ValueError("effective Git configuration or attributes unavailable")
        captured.append(result.stdout)
    attributes = captured[1].split(b"\0")
    if attributes[-1:] == [b""]:
        attributes.pop()
    if len(attributes) != 3 * len(paths):
        raise ValueError("incomplete Git attribute result")
    for index, rel in enumerate(paths):
        path, name, value = attributes[index * 3:index * 3 + 3]
        if (path != rel.encode("utf-8") or name != b"filter" or
                value not in (b"unspecified", b"unset")):
            raise ValueError("active or unknown Git clean filter")
    environment_digest = hashlib.sha256(json.dumps(
        env, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"executable": str(resolved), "executable_sha256": sha256_file(resolved),
            "environment_keys": sorted(env), "environment_sha256": environment_digest,
            "effective_config_sha256": hashlib.sha256(captured[0]).hexdigest(),
            "filter_attributes_sha256": hashlib.sha256(captured[1]).hexdigest()}


def prepare_context_scout_profile(source: Path, assignments: dict[str, list[str]], *,
                                  source_sha256: str, package_sha256: str,
                                  runtime_id: str, model: str,
                                  git_identity: dict) -> dict:
    """Build inert inputs for a caller-owned, session-only Claude profile.

    The caller must independently qualify its OS boundary and observed native
    children. This function never invokes Claude or marks a profile qualified.
    """
    if (not isinstance(assignments, dict) or not assignments or
            set(assignments) - set("ABCDEF") or len(assignments) > 6 or
            any(not isinstance(paths, list) or not paths or len(paths) > 4096 or
                len(paths) != len(set(paths)) or
                not all(isinstance(path, str) for path in paths)
                for paths in assignments.values())):
        raise ValueError("context assignment paths must be closed and bounded")
    if not all(re.fullmatch(r"[0-9a-f]{64}", d or "")
               for d in (source_sha256, package_sha256)):
        raise ValueError("source and package digests must be explicit SHA-256")
    if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", v or "")
               for v in (runtime_id, model)):
        raise ValueError("runtime and exact model identities are required")
    root = source.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("context source is not a directory")
    files = sorted({_context_rel(path) for paths in assignments.values() for path in paths})
    if len(files) > 4096:
        raise ValueError("context source list exceeds bound")
    commands = {}
    frozen = {}
    for rel in files:
        target = _context_regular_file(root, rel)
        frozen[rel] = sha256_file(target)
    for assignment, paths in assignments.items():
        commands[assignment] = {
            context_hash_command(rel): {"path": rel, "sha256_raw": frozen[rel]}
            for rel in paths}
    computed_source = hashlib.sha256(json.dumps(
        frozen, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if source_sha256 != computed_source:
        raise ValueError("context source snapshot digest mismatch")
    return {
        "format": CONTEXT_PROFILE_FORMAT, "qualification": "unverified",
        "phase": "scout-read-only",
        "host": "claude", "source_sha256": source_sha256,
        "package_sha256": package_sha256, "runtime_id": runtime_id,
        "model": model, "source_root": str(root), "hash_commands": commands,
        "assignment_files": assignments, "git_binding": _context_git_binding(
            root, files, git_identity),
        "admitted_children": {},
        "agents": {"context-scout": {
            "description": "Context creation evidence scout for an authorized read-only phase.",
            "prompt": "Read only the assigned source scope. Return the bound closed context report; no edits, nested agents, or raw excerpts. Use only exact approved git hash-object commands for cited files.",
            "tools": ["Read", "Grep", "Glob", "Bash"], "model": model}},
        "boundary_requirements": ["fresh native child IDs for six assignments",
                                  "atomic external parent launch reservations: at most one per assignment, six total, before SubagentStart",
                                  "sanitized inherited Bash and Git environment, independently verified at native launch",
                                  "read-only OS sandbox for parent and children",
                                  "external admission and report collector",
                                  "actual read, hash, guard denial, OS denial, report observations"],
    }


def bind_context_child(profile: dict, event: dict, assignment: str) -> dict:
    """Bind one observed native SubagentStart ID to a fixed root assignment."""
    if (profile.get("format") != CONTEXT_PROFILE_FORMAT or
            event.get("hook_event_name") != "SubagentStart" or
            event.get("agent_type") != "context-scout" or
            assignment not in profile.get("assignment_files", {})):
        raise ValueError("invalid context child admission")
    child_id = event.get("agent_id")
    admitted = profile.get("admitted_children")
    if (not isinstance(child_id, str) or not child_id or not isinstance(admitted, dict) or
            child_id in admitted or assignment in admitted.values() or len(admitted) >= 6):
        raise ValueError("duplicate or missing context child identity")
    return {**profile, "admitted_children": {**admitted, child_id: assignment}}


def _context_profile_valid(profile: object) -> bool:
    """Reject malformed or widened guard input before issuing any allow."""
    if not isinstance(profile, dict):
        return False
    try:
        if (profile["format"] != CONTEXT_PROFILE_FORMAT or
                profile["phase"] != "scout-read-only" or
                profile["qualification"] != "unverified" or
                profile["agents"]["context-scout"]["tools"] !=
                ["Read", "Grep", "Glob", "Bash"] or
                profile["agents"]["context-scout"]["model"] != profile["model"]):
            return False
        assignments = profile["assignment_files"]
        commands = profile["hash_commands"]
        admitted = profile["admitted_children"]
        if (not isinstance(assignments, dict) or not assignments or
                set(assignments) - set("ABCDEF") or set(commands) != set(assignments) or
                not isinstance(admitted, dict) or len(admitted) > 6 or
                len(set(admitted.values())) != len(admitted) or
                set(admitted.values()) - set(assignments)):
            return False
        for assignment, paths in assignments.items():
            if (not isinstance(paths, list) or not paths or
                    len(paths) != len(set(paths)) or
                    any(_context_rel(rel) != rel for rel in paths) or
                    set(commands[assignment]) !=
                    {context_hash_command(rel) for rel in paths}):
                return False
            for command, detail in commands[assignment].items():
                if (detail["path"] not in paths or
                        command != context_hash_command(detail["path"]) or
                        not re.fullmatch(r"[0-9a-f]{64}", detail["sha256_raw"])):
                    return False
        binding = profile["git_binding"]
        if (not Path(profile["source_root"]).is_absolute() or
                not re.fullmatch(r"[0-9a-f]{64}", profile["source_sha256"]) or
                not re.fullmatch(r"[0-9a-f]{64}", profile["package_sha256"]) or
                not re.fullmatch(r"[0-9a-f]{64}", binding["executable_sha256"]) or
                not re.fullmatch(r"[0-9a-f]{64}", binding["environment_sha256"]) or
                not re.fullmatch(r"[0-9a-f]{64}", binding["effective_config_sha256"]) or
                not re.fullmatch(r"[0-9a-f]{64}", binding["filter_attributes_sha256"])):
            return False
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return True


def _context_assigned_file_fresh(profile: dict, assignment: str, path: str) -> bool:
    """Require the exact assigned regular file to still match its raw snapshot."""
    root = Path(profile["source_root"])
    for rel in profile["assignment_files"][assignment]:
        if path != str(root / rel):
            continue
        try:
            target = _context_regular_file(root, rel)
            expected = profile["hash_commands"][assignment][
                context_hash_command(rel)]["sha256_raw"]
            return sha256_file(target) == expected
        except (OSError, ValueError, KeyError, TypeError):
            return False
    return False


def context_scout_tool_decision(profile: dict, event: dict) -> dict:
    """Fail-closed PreToolUse decision for the caller's read-only phase."""
    allowed = False
    if (_context_profile_valid(profile) and
            isinstance(event, dict) and event.get("hook_event_name") == "PreToolUse"):
        name, actor = event.get("tool_name"), event.get("agent_type")
        child_id = event.get("agent_id")
        source = Path(profile.get("source_root", ""))
        same_cwd = (isinstance(event.get("cwd"), str) and
                    Path(event["cwd"]).resolve() == source)
        if (actor == "context-scout" and isinstance(child_id, str) and
                child_id in profile["admitted_children"] and same_cwd):
            params = event.get("tool_input")
            assignment = profile["admitted_children"][child_id]
            scope = {str(source / rel) for rel in profile.get("assignment_files", {}).get(
                assignment, [])}
            if name == "Read" and isinstance(params, dict):
                path = params.get("file_path")
                allowed = (isinstance(path, str) and path in scope and
                           _context_assigned_file_fresh(profile, assignment, path))
            elif name == "Grep" and isinstance(params, dict):
                path = params.get("path")
                allowed = (isinstance(path, str) and path in scope and
                           _context_assigned_file_fresh(profile, assignment, path))
            elif name == "Glob" and isinstance(params, dict):
                path, pattern = params.get("path"), params.get("pattern")
                selected = str(Path(path) / pattern) if (isinstance(path, str) and
                                                      isinstance(pattern, str)) else ""
                allowed = (selected in scope and
                           not any(char in pattern for char in "*?[]{}!\\") and
                           path == str(Path(selected).parent) and
                           pattern == Path(selected).name and
                           _context_assigned_file_fresh(profile, assignment, selected))
            elif name == "Bash" and isinstance(params, dict):
                try:
                    bound_git = profile["git_binding"]
                    current_git = _context_git_binding(source, sorted({
                        rel for paths in profile["assignment_files"].values()
                        for rel in paths}), {"executable": bound_git["executable"],
                                            "sha256": bound_git["executable_sha256"]})
                except (OSError, ValueError, TypeError, KeyError):
                    current_git = None
                allowed = (isinstance(params.get("command"), str) and
                           set(params) <= {"command", "description"} and
                           params.get("command") in profile["hash_commands"].get(
                               assignment, {}) and
                           profile.get("git_binding") == current_git and
                           _context_assigned_file_fresh(
                               profile, assignment, str(source / profile["hash_commands"]
                                   [assignment][params["command"]]["path"])))
        elif actor is None and child_id is None:
            params = event.get("tool_input")
            # This allows only the intended agent type. It cannot reserve a
            # launch: PreToolUse calls precede asynchronous SubagentStart and
            # may race. A trusted external atomic ledger must enforce the
            # six-launch, one-per-assignment limit before invoking Agent.
            allowed = (same_cwd and name == "Agent" and isinstance(params, dict) and
                       set(params) <= {"subagent_type", "prompt", "description"} and
                       params.get("subagent_type") == "context-scout" and
                       len(profile["admitted_children"]) < len(profile["assignment_files"]))
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "allow" if allowed else "deny",
                                   "permissionDecisionReason":
                                       "closed context scout profile" if allowed else
                                       "outside closed context scout profile"}}


def assess_supplied_context_observations(profile: dict, cases: list[dict]) -> dict:
    """Check completeness of supplied data without promoting it to host proof."""
    if (profile.get("format") != CONTEXT_PROFILE_FORMAT or
            profile.get("phase") != "scout-read-only"):
        raise ValueError("unknown or writable context profile")
    admitted = profile.get("admitted_children")
    if (not isinstance(admitted, dict) or len(admitted) != 6 or
            set(admitted.values()) != set("ABCDEF") or not isinstance(cases, list) or
            len(cases) != 6):
        raise ValueError("six distinct admitted child observations required")
    seen = set()
    missing = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("malformed child observation")
        child = case.get("agent_id")
        if child not in admitted or child in seen or case.get("assignment") != admitted[child]:
            raise ValueError("unknown, duplicate or mismatched child observation")
        seen.add(child)
        lacks = [field for field in ("source_read", "hash_result", "guard_write_denied",
                                    "os_write_denied", "target_unchanged", "report_delivered")
                 if case.get(field) is not True]
        missing[child] = lacks
    return {"qualification": "unverified", "supplied_complete":
            not any(missing.values()), "missing": missing}


def context_profile_settings(profile_file: Path) -> dict:
    """Render inert native settings for later protected caller qualification."""
    command = _native_hook_command([
        sys.executable, str(Path(__file__).resolve()),
        "--guard-context-profile", str(profile_file.resolve())])
    return {"sandbox": {"enabled": True, "failIfUnavailable": True,
                        "allowUnsandboxedCommands": False,
                        "excludedCommands": []},
            "permissions": {"deny": ["Write", "Edit", "NotebookEdit"]},
            "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": command}]}]}}


def context_profile_main(argv: list[str]) -> int:
    """Prepare inert caller inputs or answer one native PreToolUse event."""
    if len(argv) == 10 and argv[0] == "--prepare-context-profile":
        (_, source, paths_json, source_digest, package_digest, runtime, model,
         git_executable, git_sha256, output) = argv
        paths_file = Path(paths_json)
        if paths_file.stat().st_size > 8_388_608:
            raise ValueError("context assignment input exceeds bound")
        paths = json.loads(paths_file.read_text(encoding="utf-8"))
        profile = prepare_context_scout_profile(
            Path(source), paths, source_sha256=source_digest,
            package_sha256=package_digest, runtime_id=runtime, model=model,
            git_identity={"executable": git_executable, "sha256": git_sha256})
        target = Path(output)
        settings_target = target.with_name(target.name + ".settings.json")
        if target.exists() or settings_target.exists():
            raise FileExistsError("context profile output already exists")
        with target.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(profile, out, indent=2, sort_keys=True)
            out.write("\n")
        with settings_target.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(context_profile_settings(target), out, indent=2, sort_keys=True)
            out.write("\n")
        return 0
    if len(argv) == 2 and argv[0] == "--guard-context-profile":
        profile_file = Path(argv[1])
        if profile_file.is_symlink() or profile_file.stat().st_size > 8_388_608:
            raise ValueError("context profile unavailable or exceeds bound")
        profile = json.loads(profile_file.read_text(encoding="utf-8"))
        raw = sys.stdin.buffer.read(65_537)
        if len(raw) > 65_536:
            raise ValueError("context tool event exceeds bound")
        event = json.loads(raw)
        print(json.dumps(context_scout_tool_decision(profile, event), sort_keys=True))
        return 0
    raise ValueError("unknown context profile mode")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_git_identity() -> dict:
    """Pin the fixture's known system Git before adversarial PATH changes."""
    executable = shutil.which("git")
    if not executable:
        raise unittest.SkipTest("Git unavailable to test fixture")
    resolved = Path(executable).resolve(strict=True)
    return {"executable": str(resolved), "sha256": sha256_file(resolved)}


def _native_rel(path: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ValueError("native fixture path must be POSIX relative")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("native fixture path escapes isolated repository")
    return str(pure)


def _validate_native_rule(path: str, content: str) -> None:
    if not path.startswith(".claude/rules/"):
        return
    lines = content.splitlines()
    if (len(lines) < 5 or lines[:2] != ["---", "paths:"] or
            lines[2] != "  - 'packages/a/**'" or lines[3] != "---"):
        raise ValueError("path rule lacks bounded paths frontmatter")


def _native_hook_command(argv: list[str]) -> str:
    """Render the command string consumed by Claude's command hook."""
    if os.name == "nt":
        return subprocess.list2cmdline([arg.replace("\\", "/") for arg in argv])
    return shlex.join(argv)


def load_native_catalog() -> dict:
    """Read an inert catalog; loading it never invokes a host."""
    catalog = json.loads(NATIVE_CATALOG.read_text(encoding="utf-8"))
    if catalog.get("format") != NATIVE_FORMAT or not isinstance(catalog.get("cells"), list):
        raise ValueError("unsupported native loading catalog")
    ids = set()
    for cell in catalog["cells"]:
        if set(cell) != {"id", "host", "profile", "availability", "phase", "actor",
                         "target", "files", "required", "excluded"}:
            raise ValueError("native loading cell has unexpected fields")
        if cell["id"] in ids or not cell["id"].replace("-", "").isalnum():
            raise ValueError("duplicate or unsafe native loading cell id")
        ids.add(cell["id"])
        if cell["availability"] not in ("selected", "unselected", "disabled"):
            raise ValueError("unsupported native loading availability")
        _native_rel(cell["target"])
        if not isinstance(cell["files"], dict) or not cell["files"]:
            raise ValueError("native loading cell has no files")
        for path, content in cell["files"].items():
            _native_rel(path)
            if not isinstance(content, str) or not content:
                raise ValueError("native loading file must have inert text")
            _validate_native_rule(path, content)
        for key in ("required", "excluded"):
            if not isinstance(cell[key], list) or not all(
                    isinstance(marker, str) and marker.startswith("T039_")
                    for marker in cell[key]):
                raise ValueError("native loading sentinels must be inert and explicit")
        if set(cell["required"]) & set(cell["excluded"]):
            raise ValueError("native loading sentinel is both required and excluded")
        file_text = "\n".join(cell["files"].values())
        if any(marker not in file_text for marker in cell["required"] + cell["excluded"]):
            raise ValueError("native loading sentinel is absent from staged files")
    return catalog


def prepare_native_cell(cell: dict, base: Path) -> dict:
    """Stage only declared harmless files under a fresh home and repository."""
    _native_rel(cell["id"])
    files = {_native_rel(path): content for path, content in cell["files"].items()}
    _native_rel(cell["target"])
    for rel, content in files.items():
        _validate_native_rule(rel, content)
    base.mkdir(parents=True, exist_ok=True)
    case_dir = base / cell["id"]
    case_dir.mkdir()  # Existing cells, including human-owned files, are preserved.
    home, repo = case_dir / "home", case_dir / "repo"
    home.mkdir()
    repo.mkdir()
    digests = {}
    for rel, content in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("x", encoding="utf-8", newline="\n") as out:
            out.write(content)
        digests[rel] = sha256_file(dest)
    target = repo / cell["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=False)
    settings = case_dir / "settings.json"
    event_log = case_dir / "instructions-loaded.jsonl"
    settings.write_text(json.dumps({"hooks": {"InstructionsLoaded": [{"hooks": [{
        "type": "command", "command": _native_hook_command([
            sys.executable, str(Path(__file__).resolve()), "--capture-native-event",
            str(event_log)]),
    }]}]}}, indent=2) + "\n", encoding="utf-8")
    template = {
        "note": "Template only: verify authorization, host version, settings and isolation before invocation.",
        "cwd": str(repo), "home": str(home), "target": str(target),
        "minimum_cli_version_for_restricted": "2.1.248",
        "environment_template": {"HOME": str(home), "USERPROFILE": str(home),
                                 "XDG_CONFIG_HOME": str(home / ".config")},
        "argv": ["claude", "--restricted", "--settings", str(settings), "-p",
                 "--output-format", "stream-json", "--verbose", "--include-hook-events",
                 "--max-turns", "1", "--max-budget-usd", "<AUTHORIZED_BUDGET_USD>",
                 "<AUTHORIZED_READ_ONLY_PROMPT>"],
        "limitations": ["No host is invoked by preparation.",
                        "--init-only event completeness is unobserved.",
                        "Events report CLAUDE.md/rules loads, not direct AGENTS.md loads.",
                        "Native Windows Bash sandboxing is not established by this template."],
    }
    (case_dir / "collector-template.json").write_text(
        json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return {"id": cell["id"], "home": str(home), "repo": str(repo),
            "files": digests, "settings": str(settings), "event_log": str(event_log),
            "collector_template": str(case_dir / "collector-template.json")}


def synthetic_native_observation(cell: dict, prepared: dict, text: str | None) -> dict:
    """Construct unit data explicitly labeled synthetic, never host evidence."""
    return {"host": cell["host"], "profile": cell["profile"], "version": "synthetic",
            "source_kind": "synthetic", "file_digests": dict(prepared["files"]),
            "input_text": text, "input_complete": text is not None, "load_events": []}


def assess_native_cell(cell: dict, prepared: dict, observation: dict) -> dict:
    """Assess supplied capture; never emit a host qualification or approval."""
    paths = []
    repo = Path(prepared["repo"]).resolve()
    for event in observation.get("load_events", []):
        if not isinstance(event, dict) or event.get("hook_event_name") != "InstructionsLoaded":
            raise ValueError("invalid native load event")
        if event.get("memory_type") not in ("User", "Project", "Local", "Managed"):
            raise ValueError("invalid native load event scope")
        if event.get("load_reason") not in ("session_start", "nested_traversal",
                                            "path_glob_match", "include", "compact"):
            raise ValueError("invalid native load reason")
        path = Path(event.get("file_path", ""))
        if not path.is_absolute():
            raise ValueError("native load event path is not absolute")
        try:
            relative = path.resolve().relative_to(repo).as_posix()
        except ValueError as exc:
            raise ValueError("native load event escaped isolated repository") from exc
        paths.append(relative)
    result = {"id": cell["id"], "sentinels": "unverified", "qualification": "unverified",
              "provenance": observation.get("source_kind", "unknown"),
              "observed_event_paths": paths, "eager_load_prevented": False,
              "scope": "loader_only", "reason": "effective host input not completely observed"}
    if cell["availability"] == "unselected":
        result.update(sentinels="not_applicable", reason="projection unselected")
        return result
    if cell["availability"] == "disabled":
        result.update(reason="capability disabled; host behavior unverified")
        return result
    if (observation.get("host") != cell["host"] or
            observation.get("profile") != cell["profile"] or
            not observation.get("version")):
        result.update(sentinels="contradicted", reason="host/profile/version binding mismatch")
        return result
    if observation.get("file_digests") != prepared["files"]:
        result.update(sentinels="contradicted", reason="fixture bytes changed")
        return result
    text = observation.get("input_text")
    if observation.get("input_complete") is not True or not isinstance(text, str):
        return result
    missing = [marker for marker in cell["required"] if marker not in text]
    leaked = [marker for marker in cell["excluded"] if marker in text]
    stale = "T039_STALE_NATIVE_A" in text
    if missing or leaked or stale:
        result.update(sentinels="contradicted", reason="missing, excluded or stale sentinel in supplied input",
                      missing=missing, leaked=leaked, stale_loaded=stale)
    else:
        result.update(sentinels="matched", reason="sentinels match supplied input; independent host proof pending")
    return result


def capture_native_event(destination: Path, raw: str) -> None:
    """Append one bounded raw hook event to the prepared cell's local log."""
    if (destination.name != "instructions-loaded.jsonl" or
            not (destination.parent / "home").is_dir() or
            not (destination.parent / "repo").is_dir() or destination.is_symlink()):
        raise ValueError("event destination is not a prepared isolated cell")
    if len(raw.encode("utf-8")) > 16_384:
        raise ValueError("native event exceeds capture bound")
    event = json.loads(raw)
    if not isinstance(event, dict) or event.get("hook_event_name") != "InstructionsLoaded":
        raise ValueError("not an InstructionsLoaded event")
    line = json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def native_loading_main(argv: list[str]) -> int:
    """Prepare/capture/assess source fixtures; no mode launches a native host."""
    if len(argv) == 2 and argv[0] == "--prepare-native-cells":
        base = Path(argv[1])
        base.mkdir()  # Requires a new location; never adopts existing content.
        catalog = load_native_catalog()
        prepared = {cell["id"]: prepare_native_cell(cell, base)
                    for cell in catalog["cells"]}
        manifest = {"format": NATIVE_FORMAT, "catalog_sha256": sha256_file(NATIVE_CATALOG),
                    "cells": prepared, "qualification": "unverified"}
        (base / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return 0
    if len(argv) == 4 and argv[0] == "--assess-native-cells":
        base, input_path, output_path = map(Path, argv[1:])
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("catalog_sha256") != sha256_file(NATIVE_CATALOG):
            raise ValueError("native catalog changed after fixture preparation")
        raw = input_path.read_bytes()
        supplied = json.loads(raw)
        if supplied.get("format") != NATIVE_FORMAT or not isinstance(supplied.get("cases"), dict):
            raise ValueError("invalid native observation document")
        catalog = load_native_catalog()
        if set(supplied["cases"]) - set(manifest["cells"]):
            raise ValueError("unknown native observation cell")
        results = []
        event_log_sha256 = {}
        for cell in catalog["cells"]:
            prepared = manifest["cells"][cell["id"]]
            case_dir = (base / cell["id"]).resolve()
            if (Path(prepared["repo"]).resolve() != case_dir / "repo" or
                    Path(prepared["home"]).resolve() != case_dir / "home" or
                    Path(prepared["event_log"]).resolve() != case_dir / "instructions-loaded.jsonl"):
                raise ValueError("native preparation manifest path changed")
            for rel, digest in prepared["files"].items():
                _native_rel(rel)
                if sha256_file(Path(prepared["repo"]) / rel) != digest:
                    raise ValueError("native fixture changed after preparation")
            observed = dict(supplied["cases"].get(cell["id"], {}))
            event_log = Path(prepared["event_log"])
            if event_log.exists():
                if observed.get("load_events"):
                    raise ValueError("native events must come from one retained source")
                event_bytes = event_log.read_bytes()
                if len(event_bytes) > 1_048_576:
                    raise ValueError("native event log exceeds bound")
                observed["load_events"] = [json.loads(line) for line in event_bytes.splitlines()]
                event_log_sha256[cell["id"]] = hashlib.sha256(event_bytes).hexdigest()
            results.append(assess_native_cell(cell, prepared, observed))
        assessment = {"format": NATIVE_FORMAT, "qualification": "unverified",
                      "scope": "loader_only", "source_observation_sha256": hashlib.sha256(raw).hexdigest(),
                      "event_log_sha256": event_log_sha256,
                      "results": results,
                      "note": "Assessment of supplied data, not trusted host collection or task correctness."}
        with output_path.open("x", encoding="utf-8") as out:
            json.dump(assessment, out, indent=2)
            out.write("\n")
        return 0
    if len(argv) == 2 and argv[0] == "--capture-native-event":
        capture_native_event(Path(argv[1]), sys.stdin.read())
        return 0
    raise ValueError("unknown native fixture mode")


class ContextScoutContainmentSourceTest(unittest.TestCase):
    """Bound the new context path without changing the legacy scout consumer."""

    def shortDescription(self):
        return None

    def test_t024_scout_containment_profile_positive_controls(self):
        """Require an enforced profile, distinct children and report-only delivery."""
        trusted_git = _fixture_git_identity()
        workflow = _text("core/surface/skills/context-creation/SKILL.md")
        scout = _text("core/surface/agents/scout.md")
        hosts = {host.name: host for host in _hosts.load_host_descriptors(str(ROOT))}

        self.assertEqual(set(hosts), {"claude", "codex", "pi"})
        self.assertFalse(hosts["codex"].capabilities["agents"])
        self.assertTrue(hosts["claude"].capabilities["agents"])
        self.assertTrue(hosts["pi"].capabilities["agents"])
        self.assertIn("## Context-creation containment profile", workflow)
        for requirement in (
            "fresh child identity", "host-enforced read-only", "source read",
            "benign write", "denied", "bounded report", "report-only synthesis",
            "unavailable", "BLOCK before dispatch",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, workflow)
        self.assertIn("## Context-creation assignment", scout)
        self.assertIn("decision-variance", scout)
        self.assertIn("context-creation", scout)
        self.assertIn("report-only synthesis", scout)

        projections = {
            "claude": ("plugins/ca/agents/scout.md", "plugins/ca/skills/context-creation/SKILL.md"),
            "codex": ("plugins/ca-codex/agents/scout.md", "plugins/ca-codex/routines/context-creation/SKILL.md"),
            "pi": ("plugins/ca-pi/agents/scout.md", "plugins/ca-pi/routines/context-creation/SKILL.md"),
        }
        for host, (scout_path, workflow_path) in projections.items():
            with self.subTest(host=host):
                self.assertIn("## Context-creation assignment", _text(scout_path))
                self.assertIn("## Context-creation containment profile", _text(workflow_path))
        self.assertTrue(callable(globals().get("prepare_context_scout_profile")))
        with tempfile.TemporaryDirectory() as location:
            source = Path(location)
            file = source / "src" / "alpha.py"
            file.parent.mkdir()
            file.write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            assignments = {letter: ["src/alpha.py"] for letter in "ABCDEF"}
            snapshot = hashlib.sha256(json.dumps(
                {"src/alpha.py": sha256_file(file)}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            profile = prepare_context_scout_profile(
                source, assignments, source_sha256=snapshot,
                package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            profile = bind_context_child(profile, {
                "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                "agent_id": "child-a"}, "A")
            self.assertEqual(profile["qualification"], "unverified")
            self.assertEqual(profile["agents"]["context-scout"]["tools"],
                             ["Read", "Grep", "Glob", "Bash"])
            self.assertEqual(profile["agents"]["context-scout"]["model"],
                             "claude-haiku-4-5-20251001")
            command = context_hash_command("src/alpha.py")
            self.assertEqual(profile["hash_commands"]["A"][command]["sha256_raw"],
                             sha256_file(file))
            self.assertEqual(len(subprocess.run(
                ["git", "hash-object", "--", "src/alpha.py"], cwd=source,
                check=True, capture_output=True, text=True).stdout.strip()), 40)
            paths_file = source / "paths.json"
            paths_file.write_text(json.dumps(assignments), encoding="utf-8")
            prepared_file = source / "prepared.json"
            self.assertEqual(context_profile_main([
                "--prepare-context-profile", str(source), str(paths_file), snapshot,
                "b" * 64, "linux-claude-2.1.283", "claude-haiku-4-5-20251001",
                trusted_git["executable"], trusted_git["sha256"],
                str(prepared_file)]), 0)
            self.assertEqual(json.loads(prepared_file.read_text(encoding="utf-8"))
                             ["hash_commands"], profile["hash_commands"])
            settings = json.loads(prepared_file.with_name(
                prepared_file.name + ".settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["sandbox"]["failIfUnavailable"], True)
            self.assertEqual(settings["sandbox"]["allowUnsandboxedCommands"], False)
            self.assertIn("--guard-context-profile", settings["hooks"]["PreToolUse"]
                          [0]["hooks"][0]["command"])
            self.assertEqual(settings["permissions"]["deny"],
                             ["Write", "Edit", "NotebookEdit"])
            for name, params in (("Read", {"file_path": str(file)}),
                                 ("Grep", {"path": str(file), "pattern": "value"}),
                                 ("Glob", {"path": str(file.parent),
                                           "pattern": file.name}),
                                 ("Bash", {"command": command})):
                decision = context_scout_tool_decision(profile, {
                    "hook_event_name": "PreToolUse", "tool_name": name,
                    "tool_input": params, "agent_type": "context-scout",
                    "agent_id": "child-a", "cwd": str(source)})
                self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"],
                                 "allow")
            self.assertEqual(context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Agent",
                "tool_input": {"subagent_type": "context-scout"},
                "cwd": str(source)})
                ["hookSpecificOutput"]["permissionDecision"], "allow")
            # Two pre-start approvals are possible: the trusted caller must
            # atomically reserve each of six assignment launches itself.
            pre_start = {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "tool_input": {"subagent_type": "context-scout"},
                         "cwd": str(source)}
            self.assertEqual(context_scout_tool_decision(profile, pre_start)
                             ["hookSpecificOutput"]["permissionDecision"], "allow")
            self.assertIn("atomic external parent launch reservations",
                          " ".join(profile["boundary_requirements"]))
            profile_file = source / "protected-profile.json"
            profile_file.write_text(json.dumps(profile), encoding="utf-8")
            native_event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {"command": command},
                            "agent_type": "context-scout", "agent_id": "child-a",
                            "cwd": str(source)}
            guarded = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--guard-context-profile", str(profile_file)],
                input=json.dumps(native_event), text=True, capture_output=True,
                check=True)
            self.assertEqual(json.loads(guarded.stdout)["hookSpecificOutput"]
                             ["permissionDecision"], "allow")
            # Synthetic schema fixture only: this does not observe a native child.
            for assignment in "BCDEF":
                profile = bind_context_child(profile, {
                    "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                    "agent_id": "child-" + assignment.lower()}, assignment)
            self.assertEqual(context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Agent",
                "tool_input": {"subagent_type": "context-scout"},
                "cwd": str(source)})["hookSpecificOutput"]["permissionDecision"],
                "deny")
            supplied = [{"agent_id": child, "assignment": assignment,
                         "source_read": True, "hash_result": True,
                         "guard_write_denied": True, "os_write_denied": True,
                         "target_unchanged": True, "report_delivered": True}
                        for child, assignment in profile["admitted_children"].items()]
            assessment = assess_supplied_context_observations(profile, supplied)
            self.assertTrue(assessment["supplied_complete"])
            self.assertEqual(assessment["qualification"], "unverified")
            (source / ".gitattributes").write_text(
                "src/alpha.py filter=marker\n", encoding="utf-8")
            changed_attributes = context_scout_tool_decision(profile, native_event)
            self.assertEqual(changed_attributes["hookSpecificOutput"]
                             ["permissionDecision"], "deny")

    def test_t024_scout_containment_profile_negative_controls(self):
        """A writable scout label or agent capability cannot pass containment."""
        trusted_git = _fixture_git_identity()
        workflow = _text("core/surface/skills/context-creation/SKILL.md")
        scout = _text("core/surface/agents/scout.md")
        frontmatter = scout.split("---", 2)[1]
        self.assertIn("Bash", frontmatter)
        pi_roles = json.loads(_text("plugins/ca-pi/generated/roles.json"))
        pi_scout = next(role for role in pi_roles if role["name"] == "scout")
        self.assertIn("bash", pi_scout["tools"])
        self.assertFalse(any(role["name"] == "context-scout" for role in pi_roles))
        self.assertIn("decision-variance", scout)
        self.assertIn("MUST NOT dispatch the existing `scout` role", workflow)
        self.assertIn("Bash", workflow)
        self.assertIn("A role label", workflow)
        self.assertIn("does not qualify", workflow)
        self.assertIn("agents capability", workflow)
        self.assertIn("No inline fallback", workflow)
        self.assertIn("failed or missing report", workflow)
        self.assertIn("MUST NOT proceed to Phase 3", workflow)
        self.assertTrue(callable(globals().get("context_scout_tool_decision")))
        with tempfile.TemporaryDirectory() as location:
            source = Path(location)
            file = source / "alpha.py"
            file.write_text("original\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            assignments = {letter: ["alpha.py"] for letter in "ABCDEF"}
            snapshot = hashlib.sha256(json.dumps(
                {"alpha.py": sha256_file(file)}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            profile = prepare_context_scout_profile(
                source, assignments, source_sha256=snapshot,
                package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            unbound = profile
            profile = bind_context_child(profile, {
                "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                "agent_id": "child-a"}, "A")
            before = file.read_bytes()
            attempts = [
                ("Write", {"file_path": str(file), "content": "changed"}),
                ("Bash", {"command": "echo changed > alpha.py"}),
                ("Bash", {"command": "git hash-object -w -- 'alpha.py'"}),
                ("Bash", {"command": "git hash-object -- 'alpha.py'; echo changed > alpha.py"}),
                ("Bash", {"command": "git hash-object -- '../outside'"}),
                ("Bash", {"command": "git hash-object -- 'alpha.py'",
                          "dangerouslyDisableSandbox": True}),
                ("Agent", {"subagent_type": "general-purpose"}),
            ]
            for tool, params in attempts:
                with self.subTest(tool=tool, params=params):
                    decision = context_scout_tool_decision(profile, {
                        "hook_event_name": "PreToolUse", "tool_name": tool,
                        "tool_input": params, "agent_type": "context-scout",
                        "agent_id": "child-a", "cwd": str(source)})
                    self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"],
                                     "deny")
            self.assertEqual(file.read_bytes(), before)
            file.write_text("changed outside frozen snapshot\n", encoding="utf-8")
            stale = context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Read",
                "tool_input": {"file_path": str(file)},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})
            self.assertEqual(stale["hookSpecificOutput"]["permissionDecision"], "deny")
            file.write_bytes(before)
            dot_glob = context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Glob",
                "tool_input": {"path": str(file), "pattern": "."},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})
            self.assertEqual(dot_glob["hookSpecificOutput"]["permissionDecision"],
                             "deny")
            for altered in ({"cwd": str(source.parent)},
                            {"agent_id": "unadmitted-child"},
                            {"tool_input": {"command": context_hash_command("alpha.py"),
                                            "run_in_background": True}}):
                event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": context_hash_command("alpha.py")},
                         "agent_type": "context-scout", "agent_id": "child-a",
                         "cwd": str(source), **altered}
                self.assertEqual(context_scout_tool_decision(profile, event)
                                 ["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(context_scout_tool_decision(
                {**profile, "phase": "author-writable"}, {
                    "hook_event_name": "PreToolUse", "tool_name": "Read",
                    "tool_input": {"file_path": str(file)},
                    "agent_type": "context-scout", "agent_id": "child-a",
                    "cwd": str(source)})["hookSpecificOutput"]["permissionDecision"],
                "deny")
            corrupted = json.loads(json.dumps(profile))
            corrupted["hash_commands"]["A"]["echo changed > alpha.py"] = {
                "path": "alpha.py", "sha256_raw": sha256_file(file)}
            self.assertEqual(context_scout_tool_decision(corrupted, {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "echo changed > alpha.py"},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})["hookSpecificOutput"]["permissionDecision"],
                "deny")
            profile_file = source / "protected-profile.json"
            profile_file.write_text(json.dumps(profile), encoding="utf-8")
            guarded = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--guard-context-profile", str(profile_file)],
                input=json.dumps({"hook_event_name": "PreToolUse",
                                  "tool_name": "Bash", "tool_input": {
                                      "command": "echo changed > alpha.py"},
                                  "agent_type": "context-scout", "agent_id": "child-a",
                                  "cwd": str(source)}),
                text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(guarded.stdout)["hookSpecificOutput"]
                             ["permissionDecision"], "deny")
            for malformed in ("{", "x" * 65_537):
                rejected = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()),
                     "--guard-context-profile", str(profile_file)],
                    input=malformed, text=True, capture_output=True, check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(rejected.stdout, "")
            self.assertEqual(file.read_bytes(), before)
            for bad in ({"agent_type": "scout", "agent_id": "child-a"},
                        {"agent_type": "context-scout"},
                        {"agent_type": "context-scout", "agent_id": ""},
                        {"agent_type": "context-scout", "agent_id": "child-b"}):
                event = {"hook_event_name": "PreToolUse", "tool_name": "Read",
                         "tool_input": {"file_path": str(file)},
                         "cwd": str(source), **bad}
                self.assertEqual(context_scout_tool_decision(profile, event)
                                 ["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(context_scout_tool_decision(unbound, {
                "hook_event_name": "PreToolUse", "tool_name": "Read",
                "tool_input": {"file_path": str(file)},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})
                ["hookSpecificOutput"]["permissionDecision"], "deny")
            for extra in ({"model": "unbound-model"},
                          {"run_in_background": True},
                          {"resume": "old-child"}):
                parent_event = {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                "tool_input": {"subagent_type": "context-scout",
                                               **extra}, "cwd": str(source)}
                self.assertEqual(context_scout_tool_decision(unbound, parent_event)
                                 ["hookSpecificOutput"]["permissionDecision"], "deny")
            with self.assertRaises(ValueError):
                bind_context_child(profile, {"hook_event_name": "SubagentStart",
                                             "agent_type": "context-scout",
                                             "agent_id": "child-a"}, "B")
            with self.assertRaises(ValueError):
                bind_context_child(profile, {"hook_event_name": "SubagentStart",
                                             "agent_type": "context-scout",
                                             "agent_id": "child-new"}, "AB")
            with self.assertRaises(ValueError):
                assess_supplied_context_observations(
                    {**profile, "phase": "author-writable"}, [])
            for assignment in "BCDEF":
                profile = bind_context_child(profile, {
                    "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                    "agent_id": "child-" + assignment.lower()}, assignment)
            supplied = [{"agent_id": child, "assignment": assignment,
                         "source_read": True, "hash_result": True,
                         "guard_write_denied": True, "os_write_denied": True,
                         "target_unchanged": True, "report_delivered": True}
                        for child, assignment in profile["admitted_children"].items()]
            for field in ("source_read", "hash_result", "guard_write_denied",
                          "os_write_denied", "target_unchanged", "report_delivered"):
                weakened = [dict(case) for case in supplied]
                weakened[0][field] = False
                self.assertFalse(assess_supplied_context_observations(
                    profile, weakened)["supplied_complete"])
            with self.assertRaises(ValueError):
                assess_supplied_context_observations(profile, supplied[:-1])
            with self.assertRaises(ValueError):
                assess_supplied_context_observations(profile, supplied[:-1] + [supplied[0]])
            for bad_files in (["../outside"], [".git/config"], [".env"],
                              [".env.private"], ["alpha.py", "alpha.py"],
                              ["missing.py"]):
                with self.subTest(files=bad_files), self.assertRaises(ValueError):
                    prepare_context_scout_profile(
                        source, {"A": bad_files}, source_sha256=snapshot,
                        package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                        model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            with self.assertRaises(ValueError):
                prepare_context_scout_profile(
                    source, assignments, source_sha256=snapshot,
                    package_sha256="b" * 64, runtime_id="unknown", model="", git_identity=trusted_git)
            with self.assertRaises(ValueError):
                prepare_context_scout_profile(
                    source, assignments, source_sha256="a" * 64,
                    package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                    model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            fake_dir = source / "fake-bin"
            fake_dir.mkdir()
            fake_git = fake_dir / ("git.cmd" if os.name == "nt" else "git")
            marker = source / "fake-git-executed"
            fake_git.write_text("@echo off\r\necho BAD > fake-git-executed\r\n" if
                                os.name == "nt" else
                                "#!/bin/sh\nprintf BAD > fake-git-executed\n",
                                encoding="utf-8")
            fake_git.chmod(0o755)
            with mock.patch.dict(os.environ, {
                    "PATH": str(fake_dir) + os.pathsep + os.environ.get("PATH", "")}):
                with self.assertRaisesRegex(ValueError, "pinned trusted identity"):
                    prepare_context_scout_profile(
                        source, assignments, source_sha256=snapshot,
                        package_sha256="b" * 64,
                        runtime_id="linux-claude-2.1.283",
                        model="claude-haiku-4-5-20251001", git_identity=trusted_git)
                with self.assertRaisesRegex(ValueError, "pinned trusted identity"):
                    prepare_context_scout_profile(
                        source, assignments, source_sha256=snapshot,
                        package_sha256="b" * 64,
                        runtime_id="linux-claude-2.1.283",
                        model="claude-haiku-4-5-20251001",
                        git_identity={"executable": str(fake_git.resolve()),
                                      "sha256": sha256_file(fake_git)})
            self.assertFalse(marker.exists())
            private = source / ".env"
            private.write_text("PRIVATE=fixture\n", encoding="utf-8")
            (source / ".env.private").write_text("PRIVATE=fixture\n", encoding="utf-8")
            for forbidden in (".env", ".env.private"):
                with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                    prepare_context_scout_profile(
                        source, {"A": [forbidden]}, source_sha256=snapshot,
                        package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                        model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            link = source / "linked"
            try:
                link.symlink_to(source, target_is_directory=True)
            except (OSError, NotImplementedError):
                pass  # Windows may deny creation; the runtime rejection still applies.
            else:
                with self.assertRaises(ValueError):
                    prepare_context_scout_profile(
                        source, {"A": ["linked/alpha.py"]}, source_sha256=snapshot,
                        package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                        model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            git_trace = source / "git-trace.log"
            for hostile_key, hostile_value in (("BASH_ENV", str(private)),
                                               ("LD_PRELOAD", str(private)),
                                               ("BASH_FUNC_git%%", "() { :; }"),
                                               ("GIT_TRACE", str(git_trace)),
                                               ("GIT_TRACE2_EVENT", str(git_trace))):
                with self.subTest(hostile_key=hostile_key):
                    with mock.patch.dict(os.environ, {hostile_key: hostile_value}):
                        with self.assertRaisesRegex(ValueError, "environment"):
                            prepare_context_scout_profile(
                                source, assignments, source_sha256=snapshot,
                                package_sha256="b" * 64,
                                runtime_id="linux-claude-2.1.283",
                                model="claude-haiku-4-5-20251001", git_identity=trusted_git)
                        denied = context_scout_tool_decision(profile, {
                            "hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {"command": context_hash_command("alpha.py")},
                            "agent_type": "context-scout", "agent_id": "child-a",
                            "cwd": str(source)})
                        self.assertEqual(denied["hookSpecificOutput"]
                                         ["permissionDecision"], "deny")
                    self.assertFalse(git_trace.exists())
            denied_grep = context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Grep",
                "tool_input": {"path": str(source), "pattern": "PRIVATE"},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})
            self.assertEqual(denied_grep["hookSpecificOutput"]["permissionDecision"],
                             "deny")
            denied_glob = context_scout_tool_decision(profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Glob",
                "tool_input": {"path": str(source), "pattern": ".env"},
                "agent_type": "context-scout", "agent_id": "child-a",
                "cwd": str(source)})
            self.assertEqual(denied_glob["hookSpecificOutput"]["permissionDecision"],
                             "deny")
            other = source / "other.py"
            other.write_text("other\n", encoding="utf-8")
            two = {"alpha.py": sha256_file(file), "other.py": sha256_file(other)}
            two_snapshot = hashlib.sha256(json.dumps(
                two, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            shared = prepare_context_scout_profile(
                source, {"A": ["alpha.py"], "B": ["other.py"],
                         **{letter: ["alpha.py"] for letter in "CDEF"}},
                source_sha256=two_snapshot,
                package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            shared = bind_context_child(shared, {
                "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                "agent_id": "child-b"}, "B")
            cross = context_scout_tool_decision(shared, {
                "hook_event_name": "PreToolUse", "tool_name": "Read",
                "tool_input": {"file_path": str(file)},
                "agent_type": "context-scout", "agent_id": "child-b",
                "cwd": str(source)})
            self.assertEqual(cross["hookSpecificOutput"]["permissionDecision"], "deny")
            bracketed = source / "data[1].py"
            matching = source / "data1.py"
            bracketed.write_text("assigned\n", encoding="utf-8")
            matching.write_text("unassigned\n", encoding="utf-8")
            bracket_digest = hashlib.sha256(json.dumps({
                bracketed.name: sha256_file(bracketed)}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            bracket_profile = prepare_context_scout_profile(
                source, {"A": [bracketed.name]}, source_sha256=bracket_digest,
                package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                model="claude-haiku-4-5-20251001", git_identity=trusted_git)
            bracket_profile = bind_context_child(bracket_profile, {
                "hook_event_name": "SubagentStart", "agent_type": "context-scout",
                "agent_id": "bracket-child"}, "A")
            broadened = context_scout_tool_decision(bracket_profile, {
                "hook_event_name": "PreToolUse", "tool_name": "Glob",
                "tool_input": {"path": str(source), "pattern": bracketed.name},
                "agent_type": "context-scout", "agent_id": "bracket-child",
                "cwd": str(source)})
            self.assertEqual(broadened["hookSpecificOutput"]["permissionDecision"],
                             "deny")
        with tempfile.TemporaryDirectory() as filtered_dir:
            filtered = Path(filtered_dir)
            subprocess.run(["git", "init", "-q", str(filtered)], check=True)
            (filtered / "marker.txt").write_text("marker\n", encoding="utf-8")
            (filtered / ".gitattributes").write_text(
                "marker.txt filter=marker\n", encoding="utf-8")
            subprocess.run(["git", "config", "filter.marker.clean", "cat"],
                           cwd=filtered, check=True)
            marker_digest = hashlib.sha256(json.dumps({
                "marker.txt": sha256_file(filtered / "marker.txt")},
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with self.assertRaises(ValueError):
                prepare_context_scout_profile(
                    filtered, {"A": ["marker.txt"]}, source_sha256=marker_digest,
                    package_sha256="b" * 64, runtime_id="linux-claude-2.1.283",
                    model="claude-haiku-4-5-20251001", git_identity=trusted_git)


class TestContextResumeEpochs(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def packet(paths, instruction_epoch="instruction-1"):
        return {
            "admission": "requires_actor_check", "task_paths": list(paths),
            "map": [], "commands": [], "constraints": [], "unresolved": [],
            "instructions": [{"id": "ROOT", "path": "AGENTS.md", "scope": ".",
                              "epoch": instruction_epoch, "text": "Keep owner files."}],
        }

    @staticmethod
    def selected(paths):
        return selector.select_task_context(
            paths, code_map=("## Work\n- `packages/a/src` -- source A\n"
                                  "- `packages/b/src` -- source B\n"),
            provenance={"identity": "current", "coverage": "complete"},
            commands=[], constraints=[{
                "record": {"id": "SHARED", "kind": "existing_applicable",
                           "source_ref": "AGENTS.md", "scope": ".",
                           "statement": "SHARED-CONSTRAINT", "evidence_refs": ["E1"]},
                "owner": "root", "authority": "native", "epoch": "instruction-1",
                "status": "current"}],
            effective_instructions=[
                {"id": "ROOT", "path": "AGENTS.md", "scope": ".",
                 "epoch": "instruction-1", "text": "ROOT-INSTRUCTION"},
                {"id": "A", "path": "packages/a/AGENTS.md", "scope": "packages/a",
                 "epoch": "instruction-1", "text": "PACKAGE-A-INSTRUCTION"},
                {"id": "B", "path": "packages/b/AGENTS.md", "scope": "packages/b",
                 "epoch": "instruction-1", "text": "PACKAGE-B-INSTRUCTION"}],
            evidence_ids={"E1"})

    def test_t038_context_resume_epochs_positive_controls(self):
        """A fresh actor, expanded scope, changed source or worktree gets delivery."""
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as sibling:
            base = dict(actor="author-1", task_id="T-038", worktree=first,
                        source_epoch="source-a", host_epoch="compact-0")
            packet_a = self.selected(["packages/a/src/app.py"])
            first_delivery = selector.prepare_actor_delivery(packet_a, **base)
            self.assertEqual(first_delivery["action"], "deliver")
            self.assertEqual(first_delivery["attempt"]["number"], 1)
            self.assertEqual(first_delivery["observation"], "unknown")
            self.assertIn("PACKAGE-A-INSTRUCTION", first_delivery["delivery_text"])
            self.assertIn("SHARED-CONSTRAINT", first_delivery["delivery_text"])
            self.assertNotIn("PACKAGE-B-INSTRUCTION", first_delivery["delivery_text"])
            for route in ("core/surface/skills/subagent-driven-development/SKILL.md",
                          "core/surface/skills/tdd/SKILL.md",
                          "core/surface/commands/fix.md",
                          "core/surface/commands/review.md"):
                with self.subTest(route=route):
                    self.assertIn("_contextselectlib.prepare_actor_delivery", _text(route))
            attempts = [first_delivery["attempt"]]
            receipt = {"binding": first_delivery["binding"], "actor": "author-1",
                       "observed": True, "source": "host-load-event"}
            confirmed = selector.prepare_actor_delivery(
                packet_a, **base, attempts=attempts, receipt=receipt)
            self.assertEqual(confirmed["action"], "observed")
            self.assertEqual(confirmed["observation"], "reported")
            self.assertEqual(selector.prepare_actor_delivery(
                packet_a, **{**base, "actor": "reviewer-1"},
                attempts=attempts, receipt=receipt)["action"], "deliver")
            expanded = self.selected(["packages/a/src/app.py", "packages/b/src/app.py"])
            expanded_delivery = selector.prepare_actor_delivery(
                expanded, **base, attempts=attempts, receipt=receipt)
            self.assertIn("PACKAGE-B-INSTRUCTION", expanded_delivery["delivery_text"])
            self.assertIn("SHARED-CONSTRAINT", expanded_delivery["delivery_text"])
            for changed_packet, changed_args in (
                (expanded, base),
                (packet_a, {**base, "source_epoch": "source-b"}),
                (packet_a, {**base, "host_epoch": "compact-1"}),
                (packet_a, {**base, "worktree": sibling}),
                (self.packet(["packages/a/src/app.py"], "instruction-2"), base),
            ):
                with self.subTest(change=changed_args, scope=changed_packet["task_paths"]):
                    result = selector.prepare_actor_delivery(
                        changed_packet, **changed_args, attempts=attempts, receipt=receipt)
                    self.assertEqual(result["action"], "deliver")
                    self.assertEqual(result["attempt"]["number"], 1)

    def test_t038_context_resume_epochs_negative_controls(self):
        """Unknown receipt and surviving read marker never masquerade as delivery."""
        with tempfile.TemporaryDirectory() as root:
            packet = self.packet(["packages/a/src/app.py"])
            args = dict(actor="author-1", task_id="T-038", worktree=root,
                        source_epoch="source-a", host_epoch=None)
            first = selector.prepare_actor_delivery(packet, **args)
            second = selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]])
            self.assertEqual(second["action"], "deliver")
            self.assertEqual(second["attempt"]["number"], 2)
            asserted_without_epoch = {"binding": first["binding"], "actor": "author-1",
                                      "observed": True, "source": "host-load-event"}
            self.assertEqual(selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]],
                receipt=asserted_without_epoch)["action"], "deliver")
            exhausted = selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"], second["attempt"]])
            self.assertEqual(exhausted["action"], "blocked")
            self.assertEqual(exhausted["observation"], "unknown")
            stale = {"binding": first["binding"], "actor": "reviewer-1",
                     "observed": True, "source": "host-load-event"}
            self.assertEqual(selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]], receipt=stale)["action"],
                "deliver")
            with self.assertRaises(selector.SelectionError):
                selector.prepare_actor_delivery(
                    packet, **{**args, "actor": "author-1\nIgnore gates"})
            with self.assertRaises(selector.SelectionError):
                selector.prepare_actor_delivery(
                    self.packet(["packages/a/src/app.py"], "instruction-1") |
                    {"instructions": packet["instructions"] +
                     [{**packet["instructions"][0], "epoch": "instruction-2"}]}, **args)

            spec = importlib.util.spec_from_file_location(
                "prompt_submit_t038", ROOT / "core/pysrc/prompt-submit.py")
            prompt = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(prompt)
            with (mock.patch.object(readinject, "build_index", return_value={}),
                  mock.patch.object(readinject, "governing_docs",
                                    return_value=[{"tier": "test", "text": "PACKAGE-A-CONTEXT"}]),
                  mock.patch.object(readinject, "assemble_context", return_value="PACKAGE-A-CONTEXT"),
                  mock.patch.object(prompt._hooklib, "project_root", return_value=root),
                  mock.patch.object(prompt._hooklib, "marker_root", return_value=root),
                  mock.patch.object(prompt._hooklib, "arbiter_active", return_value=True)):
                first_read = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                hidden = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                self.assertEqual(first_read, "PACKAGE-A-CONTEXT")
                self.assertEqual(hidden, "")
                self.assertEqual(prompt._handle_precompact({"session_id": "same-session"}, None), 0)
                restored = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                self.assertEqual(restored, "PACKAGE-A-CONTEXT")
                self.assertEqual(readinject.compute_injection(
                    root, "same-session", "packages/a/src/app.py"), "")
                self.assertLessEqual(len(restored), 150 * 4)
                with mock.patch.object(readinject, "read_context_generation",
                                       side_effect=AssertionError("self-read reached epoch")):
                    self.assertEqual(readinject.compute_injection(
                        root, "same-session", ".codearbiter/CONTEXT.md"), "")

                generation_path = Path(readinject._session_context_generation_path(
                    root, "same-session"))
                for bad in (b"not-a-generation", b"7" * 257):
                    with self.subTest(bad_length=len(bad)):
                        generation_path.write_bytes(bad)
                        self.assertIsNone(readinject.read_context_generation(
                            root, "same-session"))
                        self.assertFalse(readinject.bump_context_generation(
                            root, "same-session"))
                        self.assertEqual(generation_path.read_bytes(), bad)
                        markers_before = set((Path(root) / ".codearbiter/.markers").glob(
                            "readinject-*.marker"))
                        self.assertEqual(readinject.compute_injection(
                            root, "same-session", "packages/a/src/app.py"),
                            "PACKAGE-A-CONTEXT")
                        self.assertEqual(readinject.compute_injection(
                            root, "same-session", "packages/a/src/app.py"),
                            "PACKAGE-A-CONTEXT")
                        self.assertEqual(set((Path(root) / ".codearbiter/.markers").glob(
                            "readinject-*.marker")), markers_before)

            sessions = ["actor-" + str(index) for index in range(8)]
            self.assertEqual(len({readinject._session_context_generation_path(root, sid)
                                  for sid in sessions}), len(sessions))
            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(lambda sid: [readinject.bump_context_generation(
                    root, sid) for _ in range(3)], sessions))
            self.assertTrue(all(all(each) for each in outcomes))
            self.assertEqual([readinject.read_context_generation(root, sid)
                              for sid in sessions], [3] * len(sessions))


class TestNativeContextLoading(unittest.TestCase):
    """Source fixture checks; a later host collection still needs separate review."""

    def shortDescription(self):
        return None

    def test_t039_native_context_loading_positive_controls(self):
        """Prepare isolated cells and distinguish supplied input from host proof."""
        catalog = load_native_catalog()
        self.assertEqual(catalog["format"], "codearbiter.native-loading-cells/0.1")
        self.assertGreaterEqual(len(catalog["cells"]), 8)
        with tempfile.TemporaryDirectory() as root:
            for cell in catalog["cells"]:
                with self.subTest(cell=cell["id"]):
                    prepared = prepare_native_cell(cell, Path(root))
                    self.assertTrue(Path(prepared["home"]).is_dir())
                    self.assertEqual(list(Path(prepared["home"]).iterdir()), [])
                    for rel, digest in prepared["files"].items():
                        self.assertEqual(sha256_file(Path(prepared["repo"]) / rel), digest)
                    template = json.loads(Path(prepared["collector_template"])
                                          .read_text(encoding="utf-8"))
                    self.assertEqual(template["environment_template"]["HOME"], prepared["home"])
                    self.assertIn("--restricted", template["argv"])
                    self.assertIn("--settings", template["argv"])
                    observation = synthetic_native_observation(
                        cell, prepared, "\n".join(cell["required"]))
                    result = assess_native_cell(cell, prepared, observation)
                    if cell["availability"] == "selected":
                        self.assertEqual(result["sentinels"], "matched")
                        self.assertEqual(result["qualification"], "unverified")
                        self.assertEqual(result["provenance"], "synthetic")
                    elif cell["availability"] == "unselected":
                        self.assertEqual(result["sentinels"], "not_applicable")
                    else:
                        self.assertEqual(result["sentinels"], "unverified")
                        self.assertEqual(result["qualification"], "unverified")
            nested = next(c for c in catalog["cells"] if c["id"] == "claude-nested")
            prepared = prepare_native_cell(nested, Path(root) / "event only")
            event_only = synthetic_native_observation(nested, prepared, None)
            event_only["load_events"] = [{
                "hook_event_name": "InstructionsLoaded",
                "file_path": str(Path(prepared["repo"]) / "CLAUDE.md"),
                "memory_type": "Project", "load_reason": "session_start",
            }]
            result = assess_native_cell(nested, prepared, event_only)
            self.assertEqual(result["sentinels"], "unverified")
            self.assertEqual(result["observed_event_paths"], ["CLAUDE.md"])
            configured = json.loads(Path(prepared["settings"]).read_text(encoding="utf-8"))[
                "hooks"]["InstructionsLoaded"][0]["hooks"][0]
            self.assertEqual(set(configured), {"type", "command"})
            probe = subprocess.run(configured["command"], shell=True,
                                   input=json.dumps(event_only["load_events"][0]).encode(),
                                   capture_output=True, check=False)
            self.assertEqual(probe.returncode, 0, probe.stderr.decode(errors="replace"))
            expected_events = 1
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            if os.name == "nt" and git_bash.is_file():
                bash_probe = subprocess.run([str(git_bash), "-lc", configured["command"]],
                                            input=json.dumps(event_only["load_events"][0]).encode(),
                                            capture_output=True, check=False)
                self.assertEqual(bash_probe.returncode, 0,
                                 bash_probe.stderr.decode(errors="replace"))
                expected_events += 1
            self.assertEqual(len(Path(prepared["event_log"]).read_text(encoding="utf-8").splitlines()),
                             expected_events)
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "prepared"
            self.assertEqual(native_loading_main(["--prepare-native-cells", str(base)]), 0)
            manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["cells"]), {c["id"] for c in catalog["cells"]})
            supplied = {"format": NATIVE_FORMAT, "cases": {
                cell["id"]: synthetic_native_observation(
                    cell, manifest["cells"][cell["id"]], "\n".join(cell["required"]))
                for cell in catalog["cells"]}}
            root_cell = manifest["cells"]["claude-root"]
            capture_native_event(Path(root_cell["event_log"]), json.dumps({
                "hook_event_name": "InstructionsLoaded",
                "file_path": str(Path(root_cell["repo"]) / "CLAUDE.md"),
                "memory_type": "Project", "load_reason": "session_start"}))
            observation_path, assessment_path = base / "supplied.json", base / "assessment.json"
            observation_path.write_text(json.dumps(supplied), encoding="utf-8")
            self.assertEqual(native_loading_main([
                "--assess-native-cells", str(base), str(observation_path), str(assessment_path)]), 0)
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
            self.assertEqual(assessment["qualification"], "unverified")
            self.assertEqual(len(assessment["results"]), len(catalog["cells"]))
            self.assertEqual({r["provenance"] for r in assessment["results"]}, {"synthetic"})
            self.assertEqual(next(r for r in assessment["results"] if r["id"] == "claude-root")
                             ["observed_event_paths"], ["CLAUDE.md"])
            self.assertIn("claude-root", assessment["event_log_sha256"])

    def test_t039_native_context_loading_negative_controls(self):
        """Missing, leaked, stale and unobserved content cannot pass."""
        catalog = load_native_catalog()
        nested = next(c for c in catalog["cells"] if c["id"] == "claude-nested")
        with tempfile.TemporaryDirectory() as root:
            prepared = prepare_native_cell(nested, Path(root))
            matched = synthetic_native_observation(
                nested, prepared, "\n".join(nested["required"]))
            self.assertEqual(assess_native_cell(nested, prepared, matched)["sentinels"],
                             "matched")
            for text in (nested["required"][0],
                         "\n".join(nested["required"] + nested["excluded"])):
                bad = synthetic_native_observation(nested, prepared, text)
                self.assertEqual(assess_native_cell(nested, prepared, bad)["sentinels"],
                                 "contradicted")
            missing_capture = synthetic_native_observation(nested, prepared, None)
            self.assertEqual(assess_native_cell(nested, prepared, missing_capture)
                             ["sentinels"], "unverified")
            incomplete = dict(matched, input_complete=False)
            self.assertEqual(assess_native_cell(nested, prepared, incomplete)
                             ["sentinels"], "unverified")
            wrong_bytes = dict(matched, file_digests={"CLAUDE.md": "0" * 64})
            self.assertEqual(assess_native_cell(nested, prepared, wrong_bytes)
                             ["sentinels"], "contradicted")
            stale = dict(matched, input_text=matched["input_text"] + "\nT039_STALE_NATIVE_A")
            result = assess_native_cell(nested, prepared, stale)
            self.assertEqual(result["sentinels"], "contradicted")
            self.assertFalse(result["eager_load_prevented"])
            with self.assertRaises(FileExistsError):
                prepare_native_cell(nested, Path(root))
            self.assertEqual(sha256_file(Path(prepared["repo"]) / "CLAUDE.md"),
                             prepared["files"]["CLAUDE.md"])
            configured = json.loads(Path(prepared["settings"]).read_text(encoding="utf-8"))[
                "hooks"]["InstructionsLoaded"][0]["hooks"][0]
            bad_probe = subprocess.run(configured["command"], shell=True,
                                       input=b'{"hook_event_name":"Other"}',
                                       capture_output=True, check=False)
            self.assertNotEqual(bad_probe.returncode, 0)
            self.assertFalse(Path(prepared["event_log"]).exists())
            with self.assertRaises(ValueError):
                prepare_native_cell({**nested, "files": {"../outside": "bad"}},
                                    Path(root) / "unsafe")
            with self.assertRaises(ValueError):
                prepare_native_cell({**nested, "files": {
                    ".claude/rules/global.md": "T039_UNSCOPED_RULE"}},
                    Path(root) / "unscoped")
            self.assertFalse((Path(root) / "unscoped" / nested["id"]).exists())
            with self.assertRaises(ValueError):
                assess_native_cell(nested, prepared, dict(matched, load_events=[{
                    "hook_event_name": "InstructionsLoaded", "file_path": "../outside",
                    "memory_type": "Project", "load_reason": "session_start"}]))
            with self.assertRaises(ValueError):
                capture_native_event(Path(prepared["event_log"]), '{"hook_event_name":"Other"}')
            with self.assertRaises(FileExistsError):
                native_loading_main(["--prepare-native-cells", str(Path(root))])
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "prepared"
            native_loading_main(["--prepare-native-cells", str(base)])
            observation_path = base / "supplied.json"
            observation_path.write_text(json.dumps({
                "format": NATIVE_FORMAT, "cases": {}}), encoding="utf-8")
            first_file = base / "claude-root" / "repo" / "CLAUDE.md"
            first_file.write_text("T039_TAMPERED\n", encoding="utf-8")
            assessment_path = base / "assessment.json"
            with self.assertRaises(ValueError):
                native_loading_main(["--assess-native-cells", str(base),
                                     str(observation_path), str(assessment_path)])
            self.assertFalse(assessment_path.exists())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {
            "--prepare-context-profile", "--guard-context-profile"}:
        try:
            raise SystemExit(context_profile_main(sys.argv[1:]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print(f"context profile error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    if len(sys.argv) > 1 and sys.argv[1] in {
            "--prepare-native-cells", "--assess-native-cells", "--capture-native-event"}:
        try:
            raise SystemExit(native_loading_main(sys.argv[1:]))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"native loading fixture error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    unittest.main()
