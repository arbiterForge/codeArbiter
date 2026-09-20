#!/usr/bin/env python3
"""Cold, multi-process lifecycle proof for one extracted host package."""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile


_BRIDGE_IMPORTS = frozenset({
    "__future__", "ctypes", "hashlib", "json", "msvcrt", "os", "pathlib",
    "platform", "re", "stat", "subprocess", "tempfile", "threading", "typing",
})
_CTYPES_ATTRIBUTES = frozenset({
    "WinDLL", "c_uint32", "c_void_p", "c_wchar_p", "get_last_error",
})
_PROCESS_ESCAPE_CALLS = frozenset({
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
    "execvpe", "fork", "forkpty", "popen", "posix_spawn", "posix_spawnp",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp",
    "spawnvpe", "startfile", "system",
})
_NETWORK_AUDIT_EVENTS = frozenset({
    "socket.bind", "socket.connect", "socket.connect_ex", "socket.getaddrinfo",
    "socket.gethostbyaddr", "socket.gethostbyname", "socket.gethostbyname_ex",
    "socket.getnameinfo", "socket.getservbyname", "socket.getservbyport",
    "socket.sendmsg", "socket.sendto",
})
_KERNEL32_PROCEDURES = frozenset({
    "CloseHandle", "CreateFileW", "GetFileAttributesW",
})


def assert_offline_bridge(source: bytes) -> None:
    """Fail closed if the exact packaged bridge gains network/process escape."""
    try:
        tree = ast.parse(source.decode("utf-8", "strict"))
    except (SyntaxError, UnicodeError) as exc:
        raise AssertionError("installed bridge is not valid UTF-8 Python") from exc
    imports: set[str] = set()
    popen_calls = 0
    native_loads: list[ast.Call] = []
    reviewed_native_loads: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.asname is not None for alias in node.names):
                raise AssertionError("installed bridge aliases an imported capability")
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = (node.module or "").split(".", 1)[0]
            if imported in {"ctypes", "msvcrt", "os", "subprocess"}:
                raise AssertionError("installed bridge imports an unreviewed capability directly")
            imports.add(imported)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "__import__", "compile", "eval", "exec",
            }:
                raise AssertionError("installed bridge permits dynamic code/import escape")
            if isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (
                    isinstance(owner, ast.Name)
                    and owner.id == "os"
                    and node.func.attr in _PROCESS_ESCAPE_CALLS
                ):
                    raise AssertionError("installed bridge permits an alternate process escape")
                if (
                    isinstance(owner, ast.Name)
                    and owner.id == "subprocess"
                    and node.func.attr != "Popen"
                ):
                    raise AssertionError("installed bridge permits an unreviewed subprocess path")
                if isinstance(owner, ast.Name) and owner.id == "subprocess":
                    popen_calls += 1
                    if any(keyword.arg == "shell" for keyword in node.keywords):
                        raise AssertionError("installed bridge subprocess may invoke a shell")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "ctypes" and node.attr not in _CTYPES_ATTRIBUTES:
                raise AssertionError("installed bridge permits unreviewed native-library access")
            if node.value.id == "msvcrt" and node.attr != "open_osfhandle":
                raise AssertionError("installed bridge permits unreviewed Windows runtime access")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "ctypes"
            and node.value.func.attr == "WinDLL"
        ):
            if node.attr not in _KERNEL32_PROCEDURES:
                raise AssertionError("installed bridge accesses an unreviewed kernel32 procedure")
            reviewed_native_loads.add(id(node.value))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ctypes"
            and node.func.attr == "WinDLL"
            and (
                not node.args
                or not isinstance(node.args[0], ast.Constant)
                or str(node.args[0].value).casefold() != "kernel32"
            )
        ):
            raise AssertionError("installed bridge loads an unreviewed native library")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ctypes"
            and node.func.attr == "WinDLL"
        ):
            native_loads.append(node)
    unexpected = imports - _BRIDGE_IMPORTS
    if unexpected:
        raise AssertionError(
            "installed bridge imports unreviewed modules: " + ", ".join(sorted(unexpected))
        )
    if popen_calls != 1:
        raise AssertionError("installed bridge must retain one reviewed native-binary launch")
    if any(id(call) not in reviewed_native_loads for call in native_loads):
        raise AssertionError("installed bridge retains an unconstrained native-library handle")


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def subprocess_failure(label: str, completed: subprocess.CompletedProcess) -> AssertionError:
    stderr = completed.stderr if isinstance(completed.stderr, bytes) else b""
    return AssertionError(
        f"{label} failed with exit {completed.returncode}; "
        f"stderr_bytes={len(stderr)}; stderr_sha256={hashlib.sha256(stderr).hexdigest()}"
    )


def expected_binary(installation: Path, expected_sha256: str) -> Path:
    manifest = json.loads((installation / "release.json").read_text(encoding="utf-8"))
    matches = [
        installation / entry["file"]
        for entry in manifest["binaries"].values()
        if entry.get("sha256") == expected_sha256 and entry.get("native_tested") is True
    ]
    if len(matches) != 1:
        raise AssertionError("installed workflow did not bind one qualified binary")
    binary = matches[0].resolve(strict=True)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != expected_sha256:
        raise AssertionError("installed workflow binary bytes do not match qualification")
    return binary


def enforce_runtime_event(
    event: str,
    details: tuple,
    *,
    binary: Path,
    binary_sha256: str,
    permit_verifier_children: bool,
) -> None:
    """Audit-hook policy: no network and only the pinned expected processes."""
    if event in _NETWORK_AUDIT_EVENTS:
        raise RuntimeError("installed-host verification forbids network access")
    if event in {
        "os.system", "os.exec", "os.fork", "os.forkpty", "os.posix_spawn", "os.spawn",
    }:
        raise RuntimeError("installed-host verification forbids process escape")
    if event == "ctypes.dlopen":
        library = str(details[0]).casefold() if details else ""
        if library not in {"kernel32", "kernel32.dll"}:
            raise RuntimeError("installed-host verification forbids native-library escape")
    if event != "subprocess.Popen":
        return
    executable, argv, _cwd, environment = details
    verifier = Path(__file__).resolve(strict=True)
    python = Path(sys.executable).resolve(strict=True)
    if executable is None and os.name == "nt" and isinstance(argv, str):
        binary_prefix = subprocess.list2cmdline([str(binary)])
        python_prefix = subprocess.list2cmdline([str(python)])
        if argv == binary_prefix or argv.startswith(binary_prefix + " "):
            if environment != {}:
                raise RuntimeError("native binary launch escaped its pinned empty environment")
            return
        if permit_verifier_children and (
            argv == python_prefix or argv.startswith(python_prefix + " ")
        ):
            verifier_token = subprocess.list2cmdline([str(verifier)])
            if (
                verifier_token not in argv
                or not isinstance(environment, dict)
                or environment.get("PATH") != os.environ.get("PATH")
                or environment.get("PYTHONPATH")
            ):
                raise RuntimeError("verifier child launch escaped its constrained environment")
            return
        raise RuntimeError("installed-host verification blocked an unreviewed process")
    launched = Path(executable).resolve(strict=True)
    arguments = [str(value) for value in argv]
    if launched == binary:
        if not arguments or Path(arguments[0]).resolve(strict=True) != binary or environment != {}:
            raise RuntimeError("native binary launch escaped its pinned empty environment")
        return
    if platform.system() == "Darwin" and environment == {}:
        requested = Path(executable).absolute()
        info = requested.lstat()
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            requested == launched
            and launched.name == "ca-artifact"
            and launched.parent.name.startswith("ca-artifact-exec-")
            and launched.parent.parent.resolve(strict=True) == temp_root
            and stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == stat.S_IRUSR | stat.S_IXUSR
            and hashlib.sha256(launched.read_bytes()).hexdigest() == binary_sha256
            and arguments
            and Path(arguments[0]).resolve(strict=True) == launched
        ):
            return
    if permit_verifier_children and launched == python:
        if (
            len(arguments) < 2
            or Path(arguments[1]).resolve(strict=True) != verifier
            or not isinstance(environment, dict)
            or environment.get("PATH") != os.environ.get("PATH")
            or environment.get("PYTHONPATH")
        ):
            raise RuntimeError("verifier child launch escaped its constrained environment")
        return
    raise RuntimeError("installed-host verification blocked an unreviewed process")


def install_runtime_guard(
    binary: Path, *, binary_sha256: str, permit_verifier_children: bool
) -> None:
    def audit(event: str, details: tuple) -> None:
        enforce_runtime_event(
            event,
            details,
            binary=binary,
            binary_sha256=binary_sha256,
            permit_verifier_children=permit_verifier_children,
        )

    sys.addaudithook(audit)


def spec_normative() -> dict:
    return {
        "title": "Configuration precedence",
        "summary": "Select present validated values without treating false as absent.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"},
        "sections": [], "sources": [], "retired_symbols": [],
        "intent": {"id": "INTENT-01", "problem": "Configuration precedence is ambiguous.", "caller": "Application initialization", "outcome": "Deterministic effective configuration", "source_refs": []},
        "approach": {"id": "APPROACH-01", "choice": "Resolve validated values in explicit order.", "tradeoff": "Validation remains a separate boundary.", "binding_decision_refs": []},
        "constraints": [],
        "scope": [{"id": "SCOPE-01", "statement": "Resolve present values."}],
        "non_goals": [{"id": "NON-GOAL-01", "statement": "Parse raw configuration."}],
        "decisions": [], "governs": ["src/*.py"], "open_decisions": [],
        "criteria": [{
            "id": "AC-001", "title": "Select the environment value", "kind": "behavior", "obligation": "must", "intent_refs": ["SCOPE-01"],
            "statement": "When both sources are valid, select the environment value.", "preconditions": ["Both values are validated."], "trigger": "Resolve a supported key.", "guarantees": ["The effective value equals the environment value."],
            "scenarios": [{"id": "SCN-AC-001", "given": "Environment=false and file=true.", "when": "Resolve the key.", "then": "The effective value is false."}],
            "verification": {"id": "VER-AC-001", "method": "automated", "planned_target": "test_environment_overrides", "oracle": "Assert the effective value is false.", "negative_control": "A file-first resolver returns true.", "evidence_state": "planned"},
            "source_refs": [], "constraint_refs": [], "applicability": {"mode": "conditional", "rationale": "Both sources are present."},
        }],
    }


def plan_normative(spec_hash: str) -> dict:
    verification = {"availability": "proposed", "cwd": ".", "argv": ["python", "-m", "unittest", "tests.test_config"], "expected_exit": 0, "assertion": "The named test runs and passes.", "required_tests": ["test_environment_overrides"]}
    task = {"id": "T-001", "title": "Implement configuration precedence", "checkpoint": "CP-01", "execution_scope": "CP-01", "depends_on": [], "paths": [{"path": "src/config.py", "action": "modify"}], "criterion_refs": ["SPEC-FLOW#AC-001"], "steps": ["Write the negative test.", "Implement the contract."], "verification": [verification], "done_when": ["The named test passes."], "rollback": "Revert the implementation change.", "source_refs": []}
    return {
        "title": "Configuration precedence implementation", "summary": "Implement and verify the approved precedence contract.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"}, "sections": [], "sources": [], "retired_symbols": [],
        "spec_ref": {"artifact_id": "SPEC-FLOW", "normative_sha256": spec_hash, "binding_mode": "draft_preview"}, "tasks": [task],
        "checkpoints": [{"id": "CP-01", "title": "Complete implementation", "tasks": ["T-001"], "exit": "The combined scope is verified and reviewed.", "depends_on": []}], "prerequisites": [], "criterion_dispositions": [],
    }


def load_bridge(plugin_root: Path):
    bridge_path = plugin_root / "hooks" / "_artifactlib.py"
    assert_offline_bridge(bridge_path.read_bytes())
    spec = importlib.util.spec_from_file_location("cold_installed_artifact_bridge", bridge_path)
    if spec is None or spec.loader is None:
        raise AssertionError("installed host bridge cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not Path(module.__file__).resolve(strict=True).is_relative_to(plugin_root):
        raise AssertionError("artifact bridge escaped the extracted package root")
    return module


class Workflow:
    def __init__(self, bridge, root: Path, installation: Path, phase: str,
                 host: str, plugin_root: Path):
        self.bridge = bridge
        self.root = root
        self.client = bridge.ArtifactClient(root, installation)
        self.phase = phase
        self.host = host
        self.plugin_root = plugin_root
        self.sequence = 0

    def operation_id(self, purpose: str) -> str:
        self.sequence += 1
        return f"cold-{self.phase}-{purpose}-{self.sequence:04d}"

    def mutate(self, operation: str, artifact_id: str, **request: object) -> dict:
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        return self.client.call(operation, {"artifact_id": artifact_id, "operation_id": self.operation_id(operation), "expected": {"revision": identity["revision"], "model_sha256": identity["model_sha256"]}, **request})

    def stage_policy_event(self, artifact_id: str, record_id: str, kind: str, authority_kind: str, verdict: str, payload: dict) -> str:
        """Test-only stand-in for a pre-existing host policy receipt producer."""
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        event = {"format": "codearbiter.workflow-event/0.1.0", "kind": kind, "authority_kind": authority_kind, "subject": {"artifact_id": artifact_id, "normative_sha256": identity["normative_sha256"], "record_id": record_id}, "actor": "synthetic installed-host verifier", "origin": f"cold package {self.operation_id('policy-event')}", "verdict": verdict, "payload": payload, "source_text": "Synthetic CI policy event; not production authority."}
        raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("ascii")
        digest = hashlib.sha256(raw).hexdigest()
        source_ref = f".codearbiter/.artifacts/authority-sources/{digest}.json"
        target = self.root / source_ref
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        return self.client.call("capture", {"source_ref": source_ref, "source_sha256": digest})["receipt"]

    def approve(self, artifact_id: str) -> None:
        if self.host == "pi":
            # Pi 0.84.1 exposes no pre-model event carrying the user's exact
            # prompt. Keep its cold lifecycle proof synthetic and fail closed
            # rather than manufacturing host-observed approval authority.
            receipt = self.stage_policy_event(
                artifact_id,
                artifact_id,
                "approval",
                "user_workflow",
                "approved",
                {},
            )
            self.mutate("approve", artifact_id, receipt=receipt)
            return
        adapter = self.plugin_root / "hooks" / "_approvallib.py"
        prompt_submit = self.plugin_root / "hooks" / "prompt-submit.py"
        if not adapter.is_file() or not prompt_submit.is_file():
            raise AssertionError("installed host omits the approval prompt seam")
        hooks = str(adapter.parent)
        sys.path.insert(0, hooks)
        try:
            approval_spec = importlib.util.spec_from_file_location(
                "_approvallib", adapter
            )
            if approval_spec is None or approval_spec.loader is None:
                raise AssertionError("installed approval CLI cannot be loaded")
            approval_adapter = importlib.util.module_from_spec(approval_spec)
            sys.modules["_approvallib"] = approval_adapter
            approval_spec.loader.exec_module(approval_adapter)
            arm_output = io.StringIO()
            with contextlib.redirect_stdout(arm_output):
                arm_result = approval_adapter.main(
                    [
                        "arm",
                        "--root",
                        str(self.root),
                        "--artifact-id",
                        artifact_id,
                    ]
                )
            if arm_result != 0:
                raise AssertionError("installed approval CLI could not arm the artifact")
            armed = json.loads(arm_output.getvalue())

            prompt_spec = importlib.util.spec_from_file_location(
                "cold_installed_prompt_submit", prompt_submit
            )
            if prompt_spec is None or prompt_spec.loader is None:
                raise AssertionError("installed prompt seam cannot be loaded")
            prompt_module = importlib.util.module_from_spec(prompt_spec)
            prompt_spec.loader.exec_module(prompt_module)
        finally:
            sys.path.remove(hooks)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": armed["reply"],
            "session_id": f"installed-{self.phase}",
            "cwd": str(self.root),
            "transcript_path": "",
        }
        prompt_environment = dict(os.environ)
        if self.host == "codex":
            prompt_environment["PLUGIN_ROOT"] = str(self.plugin_root)
        elif self.host == "claude":
            prompt_environment["CLAUDE_PLUGIN_ROOT"] = str(self.plugin_root)
        prior_environment = dict(os.environ)
        prior_stdin = sys.stdin
        prompt_output = io.StringIO()
        prompt_error = io.StringIO()
        try:
            os.environ.clear()
            os.environ.update(prompt_environment)
            sys.stdin = io.StringIO(json.dumps(payload))
            with contextlib.redirect_stdout(prompt_output), contextlib.redirect_stderr(
                prompt_error
            ):
                prompt_result = prompt_module.run(prompt_module.hostapi.load_host())
        finally:
            sys.stdin = prior_stdin
            os.environ.clear()
            os.environ.update(prior_environment)
        if prompt_result != 0 or (
            f"workflow approval recorded for {artifact_id}" not in prompt_output.getvalue()
        ):
            raise AssertionError(
                "installed prompt seam did not capture interactive approval: "
                + prompt_error.getvalue()
            )
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        if identity.get("authority", {}).get("state") != "approved":
            raise AssertionError("installed prompt seam did not approve the artifact")

    def ticket(self) -> str:
        return list(self.client.contextual_pages("PLAN-FLOW", "T-001", 65536))[-1]["context_ticket"]

    def task_payload(self) -> tuple[dict, list[dict]]:
        task = self.client.call("read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"})["record"]
        spec = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        payload = {"input_sha256": snapshot["sha256"], "spec_sha256": spec["normative_sha256"], "task_sha256": canonical_hash(task)}
        commands = [{"definition_sha256": canonical_hash(definition), "exit": 0, "tests": [{"name": name, "status": "pass"} for name in definition["required_tests"]], "stdout_sha256": hashlib.sha256(b"fixture PASS").hexdigest(), "stderr_sha256": hashlib.sha256(b"").hexdigest()} for definition in task["verification"]]
        return payload, commands

    def review(self) -> None:
        payload, commands = self.task_payload()
        verification = self.stage_policy_event("PLAN-FLOW", "T-001", "verification", "verification_runner", "passed", {**payload, "commands": commands})
        review = self.stage_policy_event("PLAN-FLOW", "T-001", "spec_review", "review_workflow", "passed", {**payload, "assessment": "Synthetic installed-host spec review."})
        self.mutate("task-review", "PLAN-FLOW", task="T-001", verification_receipt=verification, review_receipt=review)

    def accept(self) -> None:
        plan = self.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        spec = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        task = self.client.call("read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"})["record"]
        receipt = self.stage_policy_event("PLAN-FLOW", "CP-01", "quality_review", "review_workflow", "passed", {"input_sha256": snapshot["sha256"], "spec_sha256": spec["normative_sha256"], "base_input_sha256": snapshot["sha256"], "task_hashes": {"T-001": canonical_hash(task)}, "assessment": "Synthetic installed-host combined-scope review."})
        self.mutate("accept-scope", plan["artifact_id"], scope="CP-01", receipt=receipt)


def phase_run(args, bridge, installation: Path) -> dict[str, object]:
    workflow = Workflow(
        bridge, args.repository, installation, args.phase, args.host, args.plugin_root
    )
    if args.phase == "author-dispatch":
        spec = spec_normative()
        workflow.client.call("create", {"operation_id": workflow.operation_id("create-spec"), "artifact_id": "SPEC-FLOW", "kind": "spec", "slug": "flow", "title": spec["title"], "summary": spec["summary"], "normative": spec})
        if workflow.client.call("validate", {"artifact_id": "SPEC-FLOW", "gate": "ready"}, permit_invalid=True)["valid"] is not True:
            raise AssertionError("installed host did not create a ready spec")
        workflow.approve("SPEC-FLOW")
        spec_identity = workflow.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        route = bridge._select_authoring_route(args.repository, "flow", workflow="feature", lane="full", client=workflow.client)
        bridge._preflight_plan_authoring(route, workflow.client, spec_artifact_id="SPEC-FLOW", spec_normative_sha256=spec_identity["normative_sha256"])
        plan = plan_normative(spec_identity["normative_sha256"])
        workflow.client.call("create", {"operation_id": workflow.operation_id("create-plan"), "artifact_id": "PLAN-FLOW", "kind": "plan", "slug": "flow", "title": plan["title"], "summary": plan["summary"], "spec_id": "SPEC-FLOW", "normative": plan})
        workflow.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        workflow.approve("PLAN-FLOW")
        plan_identity = workflow.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        ticket = workflow.ticket()
        workflow.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        return {"spec_sha256": spec_identity["normative_sha256"], "plan_sha256": plan_identity["normative_sha256"], "ticket": ticket}
    if args.phase == "reconcile-review":
        interrupted = workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        if interrupted["tasks"][0]["state"] != "IN_PROGRESS":
            raise AssertionError("interrupted state was not preserved across process recreation")
        task = workflow.client.call("read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"})["record"]
        snapshot = workflow.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        receipt = workflow.stage_policy_event("PLAN-FLOW", "T-001", "reconciliation", "user_workflow", "reconciled", {"input_sha256": snapshot["sha256"], "task_sha256": canonical_hash(task), "target_state": "PENDING", "assessment": "Synthetic interrupted-process reconciliation."})
        workflow.mutate("task-reconcile", "PLAN-FLOW", task="T-001", receipt=receipt, state="PENDING", reason="Verifier process ended before completion was established.")
        ticket = workflow.ticket()
        workflow.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        workflow.review()
        return {"ticket": ticket, "state": "REVIEW"}
    if args.phase == "accept":
        if workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})["tasks"][0]["state"] != "REVIEW":
            raise AssertionError("review state was not preserved across process recreation")
        workflow.accept()
        return {"accepted": workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})["all_accepted_and_current"]}
    if args.phase in {"commit-proof", "finalization-proof"}:
        proof = bridge._preflight_current_acceptance(bridge._resolve_workflow_pair(args.repository, "flow"), workflow.client, spec_artifact_id="SPEC-FLOW", plan_artifact_id="PLAN-FLOW")
        return {"proof": proof["eligible"]["all_accepted_and_current"], "plan_sha256": proof["plan_identity"]["normative_sha256"]}
    raise AssertionError(f"unknown phase: {args.phase}")


def child(args, phase: str) -> dict[str, object]:
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--host", args.host, "--plugin-root", str(args.plugin_root), "--repository", str(args.repository), "--expected-binary-sha256", args.expected_binary_sha256, "--phase", phase], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=40, cwd=args.repository, env=dict(os.environ))
    if completed.returncode != 0 or completed.stderr:
        raise subprocess_failure(f"installed-host phase {phase}", completed)
    return json.loads(completed.stdout)


def assert_packaged_consumers(plugin_root: Path) -> None:
    routines = plugin_root / ("skills" if (plugin_root / "skills" / "commit-gate").is_dir() else "routines")
    for name in ("commit-gate", "finishing-a-development-branch"):
        if "_preflight_current_acceptance" not in (routines / name / "SKILL.md").read_text(encoding="utf-8"):
            raise AssertionError(f"packaged {name} omits current acceptance proof")
    if "task-reconcile" not in (routines / "executing-plans" / "SKILL.md").read_text(encoding="utf-8"):
        raise AssertionError("packaged execution workflow omits interruption reconciliation")


def orchestrate(args, installation: Path) -> dict[str, object]:
    assert_packaged_consumers(args.plugin_root)
    state = args.repository / ".codearbiter"
    state.mkdir()
    (state / "CONTEXT.md").write_text(
        "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"
        "# Installed-host workflow fixture\n",
        encoding="utf-8",
    )
    first = child(args, "author-dispatch")
    resumed = child(args, "reconcile-review")
    if resumed["ticket"] == first["ticket"]:
        raise AssertionError("redispatch reused the interrupted context ticket")
    accepted = child(args, "accept")
    commit = child(args, "commit-proof")
    finalization = child(args, "finalization-proof")
    if not accepted["accepted"] or not commit["proof"] or not finalization["proof"]:
        raise AssertionError("installed workflow did not reach current atomic acceptance")
    if commit["plan_sha256"] != first["plan_sha256"] or finalization["plan_sha256"] != first["plan_sha256"]:
        raise AssertionError("installed workflow changed normative plan identity")
    markdown_shadows = [
        path
        for directory in (state / "specs", state / "plans")
        if directory.is_dir()
        for path in directory.rglob("*.md")
    ]
    if markdown_shadows:
        raise AssertionError("installed HTML workflow created a Markdown shadow")
    return {"format": "codearbiter.installed-host-workflow/0.1.0", "host": args.host, "bridge_sha256": hashlib.sha256((args.plugin_root / "hooks" / "_artifactlib.py").read_bytes()).hexdigest(), "binary_sha256": args.expected_binary_sha256, "spec_artifact_id": "SPEC-FLOW", "spec_normative_sha256": first["spec_sha256"], "plan_artifact_id": "PLAN-FLOW", "plan_normative_sha256": first["plan_sha256"], "interruption_reconciled": True, "redispatched": True, "commit_proof": True, "finalization_proof": True, "all_accepted_and_current": True, "markdown_shadow_count": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=("claude", "codex", "pi"), required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--phase", choices=("author-dispatch", "reconcile-review", "accept", "commit-proof", "finalization-proof"))
    args = parser.parse_args()
    args.plugin_root = args.plugin_root.resolve(strict=True)
    args.repository = args.repository.resolve(strict=True)
    path = os.environ.get("PATH")
    if not path or not Path(path).is_dir() or any(Path(path).iterdir()) or os.environ.get("PYTHONPATH"):
        raise AssertionError("installed-host workflow requires an empty PATH and no PYTHONPATH")
    installation = (args.plugin_root / "helpers" / "artifacts").resolve(strict=True)
    binary = expected_binary(installation, args.expected_binary_sha256)
    install_runtime_guard(
        binary,
        binary_sha256=args.expected_binary_sha256,
        permit_verifier_children=args.phase is None,
    )
    if args.phase:
        bridge = load_bridge(args.plugin_root)
        result = phase_run(args, bridge, installation)
    else:
        assert_offline_bridge((args.plugin_root / "hooks" / "_artifactlib.py").read_bytes())
        result = orchestrate(args, installation)
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
