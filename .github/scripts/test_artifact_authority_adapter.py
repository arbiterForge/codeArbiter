#!/usr/bin/env python3
"""Regression tests for production structured-artifact authority producers."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORE_PYSRC = REPO / "core" / "pysrc"
sys.path.insert(0, str(CORE_PYSRC))


class FakeClient:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.receipt = ".codearbiter/.artifacts/receipts/" + "9" * 64 + ".json"
        self.context = {
            "format": "codearbiter.evidence-context/0.1.0",
            "activity": "verification",
            "subject": {"artifact_id": "PLAN-EXAMPLE", "normative_sha256": "2" * 64, "record_id": "T-001"},
            "input_sha256": "3" * 64,
            "spec_sha256": "4" * 64,
            "plan_sha256": "2" * 64,
            "input_manifest": {},
            "task_sha256": "5" * 64,
            "task": {"id": "T-001", "criterion_refs": ["AC-001", "AC-002"]},
            "commands": [{
                "definition_sha256": "6" * 64,
                "definition": {
                    "argv": ["python", "-m", "unittest", "tests.test_config"],
                    "cwd": "candidate worktree",
                    "expected_exit": 0,
                    "required_tests": ["test_environment_overrides"],
                },
            }],
        }

    def call(self, operation, request=None, **_kwargs):
        request = dict(request or {})
        self.calls.append((operation, request))
        if operation == "evidence-context":
            raw = json.dumps(self.context, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path(".codearbiter/.artifacts/evidence-contexts") / f"{digest}.json"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"context_ref": relative.as_posix(), "context_sha256": digest,
                    "activity": self.context["activity"], "subject": self.context["subject"],
                    "input_sha256": self.context["input_sha256"]}
        if operation == "capture-observation":
            return {"receipt": self.receipt, "receipt_sha256": "9" * 64}
        raise AssertionError(operation)


class AuthorityAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "fixture.txt").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "fixture.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "--quiet", "-m", "fixture"], check=True)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.client = FakeClient(self.root)
        self.adapter = importlib.import_module("_artifactauthoritylib")
        self.original_registry_parent = self.adapter.REGISTRY_PARENT
        self.adapter.REGISTRY_PARENT = self.root
        self.linked = None

    def tearDown(self):
        if self.linked is not None and self.linked.exists():
            subprocess.run(["git", "-C", str(self.root), "worktree", "remove", "--force", str(self.linked)], check=False)
        self.adapter.REGISTRY_PARENT = self.original_registry_parent
        self.temp.cleanup()

    def _authorize(self, armed, suffix="1"):
        command = (
            f'python "{CORE_PYSRC / "artifact-authority.py"}" verify '
            f'--root "{self.root}" --request-id {armed["request_id"]}'
        )
        base = {
            "tool_name": "exec_command", "tool_input": {"cmd": command},
            "session_id": f"session-{suffix}", "turn_id": f"turn-{suffix}",
            "tool_use_id": f"tool-{suffix}",
        }
        self.adapter.observe_verifier_hook(
            self.candidate, {**base, "hook_event_name": "PreToolUse"}
        )
        return base

    def _run(self, armed, runner, suffix="1"):
        base = self._authorize(armed, suffix)
        with mock.patch.object(self.adapter, "_run_contained", side_effect=runner):
            result = self.adapter.run_verification(
                self.root, self.client, armed["request_id"]
            )
        return result, base

    def _corroborate(self, base):
        return self.adapter.observe_verifier_hook(
            self.candidate,
            {**base, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 0}},
        )

    def test_closed_request_rejects_caller_authority_and_verdict(self):
        for extras in (
            {"authority_kind": "verification_runner"},
            {"verdict": "passed"},
            {"payload": {}},
        ):
            with self.subTest(extras=extras), self.assertRaisesRegex(
                RuntimeError, "INVALID_AUTHORITY_REQUEST"
            ):
                self.adapter.arm_request(
                    self.root,
                    self.client,
                    "PLAN-EXAMPLE",
                    "T-001",
                    "verification",
                    request_nonce="request-nonce-0001",
                    **extras,
                )

        self.assertEqual(self.client.calls, [])

    def test_verifier_executes_engine_argv_without_shell_and_publishes_observation(self):
        armed = self.adapter.arm_request(
            self.root,
            self.client,
            "PLAN-EXAMPLE",
            "T-001",
            "verification",
            request_nonce="request-nonce-0001",
        )
        launches = []

        def runner(argv, **kwargs):
            launches.append((argv, kwargs))
            return subprocess.CompletedProcess(
                argv, 0, b"test_environment_overrides ... ok\n", b""
            )

        result, base = self._run(armed, runner)

        self.assertEqual(launches[0][0][1:], ["-m", "unittest", "tests.test_config"])
        self.assertTrue(Path(launches[0][0][0]).is_absolute())
        self.assertEqual(launches[0][1]["cwd"], str(self.root.resolve()))
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["commands"][0]["tests"], [
            {"name": "test_environment_overrides", "status": "pass"}
        ])

        self._corroborate(base)
        published = self.adapter.publish_request(
            self.root, self.client, armed["request_id"]
        )
        source = json.loads(
            (self.root / published["authority_source"]).read_text(encoding="utf-8")
        )
        self.assertEqual(source["kind"], "verification")
        self.assertEqual(source["authority_kind"], "verification_runner")
        self.assertEqual(source["verdict"], "passed")
        self.assertEqual(source["payload"]["commands"], result["commands"])
        self.assertIn("source_text", source)
        observation = json.loads((self.root / source["observation_ref"]).read_text("utf-8"))
        self.assertEqual(set(observation), {
            "format", "kind", "subject", "context_ref", "context_sha256",
            "payload_sha256", "producer_profile", "producer_run_id",
            "producer_result", "producer_result_sha256",
        })
        self.assertEqual(observation["producer_profile"], "declared-command/0.1.0")
        canonical_result = json.dumps(
            observation["producer_result"], ensure_ascii=True, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode()
        self.assertEqual(
            observation["producer_result_sha256"], hashlib.sha256(canonical_result).hexdigest()
        )
        self.assertEqual(self.client.calls[-1][0], "capture-observation")

    def test_production_verifier_requires_exact_wrapper_authorization_and_corroborates(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-wrapper",
        )
        command = (
            f'python "{CORE_PYSRC / "artifact-authority.py"}" verify '
            f'--root "{self.root}" --request-id {armed["request_id"]}'
        )
        base = {
            "tool_name": "exec_command", "tool_input": {"cmd": command},
            "session_id": "session-1", "turn_id": "turn-1", "tool_use_id": "tool-1",
        }
        authorized = self.adapter.observe_verifier_hook(
            self.candidate, {**base, "hook_event_name": "PreToolUse"}
        )
        self.assertEqual(authorized["state"], "AUTHORIZED")
        with self.assertRaisesRegex(RuntimeError, "compound"):
            self.adapter._verification_selector({
                "tool_name": "exec_command", "tool_input": {"cmd": command + "; whoami"},
            })

        with mock.patch.object(
            self.adapter, "_run_contained",
            return_value=subprocess.CompletedProcess(
                [], 0, b"test_environment_overrides ... ok\n", b""
            ),
        ):
            self.adapter.run_verification(
                self.root, self.client, armed["request_id"],
            )
        with self.assertRaisesRegex(RuntimeError, "uncorroborated"):
            self.adapter.publish_request(self.root, self.client, armed["request_id"])
        with self.assertRaisesRegex(RuntimeError, "did not report exit 0"):
            self.adapter.observe_verifier_hook(
                self.candidate,
                {**base, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 1}},
            )
        corroborated = self.adapter.observe_verifier_hook(
            self.candidate, {**base, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 0}}
        )
        self.assertEqual(corroborated["state"], "CORROBORATED")

    def test_production_verifier_binds_internal_worktree_and_executable(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-workspaces",
        )
        request = self.adapter._load(self.root, armed["request_id"])
        binding = request["command_bindings"][0]
        self.assertEqual(binding["workspace_root"], str(self.root.resolve()))
        self.assertTrue(Path(binding["argv"][0]).is_absolute())
        self.assertRegex(binding["executable_sha256"], r"^[0-9a-f]{64}$")
        linked = self.root.parent / (self.root.name + "-linked")
        self.linked = linked
        subprocess.run([
            "git", "-C", str(self.root), "worktree", "add", "--quiet", "-b",
            "authority-linked", str(linked),
        ], check=True)
        mapped = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-linked-workspace",
            workspace_roots={"candidate worktree": linked},
        )
        mapped_request = self.adapter._load(self.root, mapped["request_id"])
        self.assertEqual(mapped_request["command_bindings"][0]["workspace_root"], str(linked.resolve()))
        with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED_WORKSPACE"):
            self.adapter.arm_request(
                self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
                request_nonce="request-nonce-missing-workspace",
                workspace_roots={"candidate worktree": self.candidate},
            )

    def test_authority_spool_uses_canonical_repository_for_aliases(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-root-alias",
        )
        relative_alias = Path(os.path.relpath(self.root, Path.cwd()))
        self.assertEqual(
            self.adapter._load(relative_alias, armed["request_id"])["request_id"],
            armed["request_id"],
        )

    def test_workspace_snapshot_binds_dirty_tracked_and_untracked_bytes(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-byte-frozen-workspace",
        )
        request = self.adapter._load(self.root, armed["request_id"])
        dirty = self.root / "fixture.txt"
        extra = self.root / "untracked-test.py"
        dirty.write_text("dirty-one", encoding="utf-8")
        extra.write_text("print('one')\n", encoding="utf-8")
        before = self.adapter._workspace_snapshots(request["command_bindings"])
        dirty.write_text("dirty-two", encoding="utf-8")
        extra.write_text("print('two')\n", encoding="utf-8")
        after = self.adapter._workspace_snapshots(request["command_bindings"])
        self.assertEqual(before[0]["status_sha256"], after[0]["status_sha256"])
        self.assertNotEqual(before[0]["content_sha256"], after[0]["content_sha256"])

    def test_interrupted_attempt_recovery_is_terminal_and_retained(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-recovery",
        )
        request = self.adapter._load(self.root, armed["request_id"])
        request["state"] = "RUNNING"
        request["attempt"] = "uncertain-attempt"
        self.adapter._save(self.root, request)
        recovered = self.adapter.recover_request(
            self.root, armed["request_id"], "abandoned"
        )
        self.assertEqual(recovered["state"], "ABANDONED")
        self.assertFalse(recovered["rerun_permitted"])
        with self.assertRaisesRegex(RuntimeError, "INTERRUPTED_ATTEMPT"):
            self.adapter.run_verification(self.root, self.client, armed["request_id"])

    def test_lost_wrapper_after_pretool_authorization_is_recoverable_not_rerun(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-lost-after-pretool",
        )
        self._authorize(armed, "lost-after-pretool")
        recovered = self.adapter.recover_request(
            self.root, armed["request_id"], "abandoned"
        )
        self.assertEqual("ABANDONED", recovered["state"])
        with self.assertRaisesRegex(RuntimeError, "INTERRUPTED_ATTEMPT"):
            self.adapter.run_verification(self.root, self.client, armed["request_id"])

    @unittest.skipUnless(sys.platform == "win32", "native Windows Job Object coverage")
    def test_windows_job_object_runs_child_with_bounded_native_supervisor(self):
        completed = self.adapter._run_contained(
            [sys.executable, "-c", "print('contained')"],
            cwd=str(self.root), env=dict(__import__("os").environ),
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), b"contained")

        script = (
            "import subprocess,sys; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
            "print(p.pid,flush=True)"
        )
        tree = self.adapter._run_contained(
            [sys.executable, "-c", script], cwd=str(self.root),
            env=dict(__import__("os").environ),
        )
        pid = int(tree.stdout.strip())
        import ctypes
        import time
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        alive = True
        for _ in range(40):
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                alive = False
                break
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            if code.value != 259:
                alive = False
                break
            time.sleep(0.05)
        self.assertFalse(alive, "Job Object close must terminate surviving descendants")

    def test_fast_exit_oversized_output_is_rejected_after_drain(self):
        with mock.patch.object(self.adapter, "MAX_OUTPUT", 128):
            with self.assertRaisesRegex(RuntimeError, "OUTPUT_TOO_LARGE"):
                self.adapter._run_contained(
                    [sys.executable, "-c", "import os;os.write(1,b'x'*4096)"],
                    cwd=str(self.root), env=dict(os.environ), timeout_seconds=5,
                )

    @unittest.skipIf(sys.platform == "win32", "POSIX process-group coverage")
    def test_posix_timeout_and_overflow_kill_the_process_group(self):
        pid_file = self.root / "descendant.pid"
        script = (
            "import pathlib,subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
            "time.sleep(30)"
        )
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.adapter._run_contained(
                [sys.executable, "-c", script], cwd=str(self.root), env=dict(os.environ),
                timeout_seconds=0.5,
            )
        pid = int(pid_file.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            __import__("time").sleep(0.02)
        else:
            self.fail("timed-out POSIX process group left a live descendant")

        with mock.patch.object(self.adapter, "MAX_OUTPUT", 128):
            with self.assertRaisesRegex(RuntimeError, "OUTPUT_TOO_LARGE"):
                self.adapter._run_contained(
                    [sys.executable, "-c", "print('x'*4096)"],
                    cwd=str(self.root), env=dict(os.environ), timeout_seconds=5,
                )

    def test_verifier_failure_and_unsupported_collector_never_publish_success(self):
        self.client.context["commands"][0]["definition"]["argv"] = [sys.executable, "custom"]
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-0002",
        )
        with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED_COLLECTOR"):
            self._authorize(armed)
        self.assertNotIn("capture-observation", [name for name, _ in self.client.calls])

    def test_closed_singedterra_collectors_require_explicit_named_output(self):
        self.assertEqual(
            self.adapter._named_line_collector(
                b"PASS: ordered movement replay convergence\n", b"",
                ["ordered movement replay convergence"],
            ),
            [{"name": "ordered movement replay convergence", "status": "pass"}],
        )
        with self.assertRaisesRegex(RuntimeError, "MISSING_TEST_RESULT"):
            self.adapter._named_line_collector(
                b"MOVEMENT CHECK: PASSED\n", b"",
                ["ordered movement replay convergence"],
            )
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_TEST_RESULT"):
            self.adapter._named_line_collector(
                b"PASS: duplicate\nPASS: duplicate\n", b"", ["duplicate"]
            )
        self.assertEqual(
            self.adapter._vitest_verbose_collector(
                "✓ src/ui/example.test.ts > scoreboard > rendered empty state 4ms\n".encode(),
                b"", ["rendered empty state"],
            ),
            [{"name": "rendered empty state", "status": "pass"}],
        )
        with self.assertRaisesRegex(RuntimeError, "exit-only profile"):
            self.adapter._exit_only_collector(b"", b"", ["invented success"])

    def test_duplicate_declared_required_test_is_rejected_before_execution(self):
        required = self.client.context["commands"][0]["definition"]["required_tests"]
        required.append(required[0])
        with self.assertRaisesRegex(RuntimeError, "INVALID_EVIDENCE_CONTEXT"):
            self.adapter.arm_request(
                self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
                request_nonce="duplicate-required-test",
            )

    def test_completed_process_is_not_silently_rerun_after_lost_response(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-0003",
        )
        calls = []

        def runner(argv, **_kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(
                argv, 0, b"test_environment_overrides ... ok\n", b""
            )

        _result, _base = self._run(armed, runner, "rerun")
        again = self.adapter.run_verification(
            self.root, self.client, armed["request_id"],
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(again["state"], "COMPLETED")

    def test_input_drift_after_execution_blocks_publication(self):
        armed = self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "verification",
            request_nonce="request-nonce-0004",
        )
        _result, base = self._run(
            armed, lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 0, b"test_environment_overrides ... ok\n", b""
            ),
        )
        self._corroborate(base)
        self.client.context["input_sha256"] = "8" * 64
        with self.assertRaisesRegex(RuntimeError, "STALE_AUTHORITY_REQUEST"):
            self.adapter.publish_request(self.root, self.client, armed["request_id"])
        self.assertNotIn("capture-observation", [name for name, _ in self.client.calls])

    def _arm_review(self, nonce="review-request-0001"):
        self.client.context["activity"] = "spec_review"
        self.client.context.pop("commands", None)
        return self.adapter.arm_request(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "spec_review",
            request_nonce=nonce,
        )

    def test_codex_review_binds_launch_and_child_hook_identity(self):
        armed = self._arm_review()
        request_id = armed["request_id"]
        prompt = armed["dispatch_prompt"]
        self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "PreToolUse",
            "session_id": "parent-session",
            "turn_id": "turn-1",
            "tool_name": "spawn_agent",
            "tool_use_id": "tool-use-1",
            "tool_input": armed["launch_envelope"],
        })
        self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "PostToolUse",
            "session_id": "parent-session",
            "turn_id": "turn-1",
            "tool_name": "spawn_agent",
            "tool_use_id": "tool-use-1",
            "tool_response": {"task_name": armed["launch_envelope"]["task_name"]},
        })
        self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "SubagentStart",
            "session_id": "parent-session",
            "turn_id": "turn-1",
            "agent_id": "child-agent-1",
            "agent_type": "default",
        })
        decision = {
            "format": "codearbiter.review-decision/0.1.0",
            "request_id": request_id,
            "target_sha256": "3" * 64,
            "contract_sha256": armed["review_contract_sha256"],
            "decision": "pass",
            "coverage": ["AC-001", "AC-002"],
            "findings": [],
            "assessment": "The frozen task satisfies the approved criteria.",
        }
        completed = self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "SubagentStop",
            "session_id": "parent-session",
            "turn_id": "turn-1",
            "agent_id": "child-agent-1",
            "agent_type": "default",
            "last_assistant_message": json.dumps(decision),
            "agent_transcript_path": "ignored/unstable.jsonl",
        })
        self.assertEqual(completed["state"], "COMPLETED")
        published = self.adapter.publish_request(self.root, self.client, request_id)
        event = json.loads(
            (self.root / published["authority_source"]).read_text(encoding="utf-8")
        )
        self.assertEqual(event["authority_kind"], "review_workflow")
        self.assertEqual(event["origin"], "codex:subagent:child-agent-1")
        self.assertEqual(event["verdict"], "passed")

    def test_ordinary_spawn_and_subagent_hooks_pass_through(self):
        ordinary = {
            "session_id": "ordinary-session", "turn_id": "ordinary-turn",
            "tool_name": "spawn_agent", "tool_use_id": "ordinary-tool",
        }
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, {
            **ordinary, "hook_event_name": "PreToolUse",
            "tool_input": {"task_name": "ordinary", "fork_turns": "all", "message": "Review this code."},
        }))
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, {
            **ordinary, "hook_event_name": "PostToolUse",
            "tool_response": {"task_name": "ordinary"},
        }))
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "SubagentStart", "session_id": "ordinary-session",
            "turn_id": "ordinary-turn", "agent_id": "ordinary-child", "agent_type": "default",
        }))

    def test_same_turn_ordinary_spawn_makes_authority_launch_terminally_rejected(self):
        armed = self._arm_review("review-overlap-before")
        ordinary = {
            "hook_event_name": "PreToolUse", "session_id": "overlap-session",
            "turn_id": "overlap-turn", "tool_name": "spawn_agent",
            "tool_use_id": "ordinary-tool",
            "tool_input": {"task_name": "ordinary", "fork_turns": "all", "message": "Other work"},
        }
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, ordinary))
        with self.assertRaisesRegex(RuntimeError, "cannot share"):
            self.adapter.observe_codex_hook(self.root, {
                "hook_event_name": "PreToolUse", "session_id": "overlap-session",
                "turn_id": "overlap-turn", "tool_name": "spawn_agent",
                "tool_use_id": "authority-tool", "tool_input": armed["launch_envelope"],
            })
        state = self.adapter._load(self.root, armed["request_id"])
        self.assertEqual("REJECTED", state["state"])
        self.assertFalse(state["recovery"]["rerun_permitted"])

        later = self._arm_review("review-overlap-after")
        self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "PreToolUse", "session_id": "later-session",
            "turn_id": "later-turn", "tool_name": "spawn_agent",
            "tool_use_id": "authority-later", "tool_input": later["launch_envelope"],
        })
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "PreToolUse", "session_id": "later-session",
            "turn_id": "later-turn", "tool_name": "spawn_agent",
            "tool_use_id": "ordinary-later",
            "tool_input": {"task_name": "ordinary", "fork_turns": "all", "message": "Other work"},
        }))
        self.assertEqual("REJECTED", self.adapter._load(self.root, later["request_id"])["state"])

    def test_review_launch_rejects_unpinned_model_or_isolation_change(self):
        armed = self._arm_review("review-envelope-tamper")
        changed = dict(armed["launch_envelope"])
        changed["model"] = "caller-selected-model"
        with self.assertRaisesRegex(RuntimeError, "launch envelope was changed"):
            self.adapter.observe_codex_hook(self.root, {
                "hook_event_name": "PreToolUse", "session_id": "parent-envelope",
                "turn_id": "turn-envelope", "tool_name": "spawn_agent",
                "tool_use_id": "tool-envelope", "tool_input": changed,
            })

    def test_review_hooks_route_to_explicit_repository_from_another_cwd(self):
        armed = self._arm_review("review-request-cross-repo")
        other = self.root / "other-repository"
        other.mkdir()
        self.adapter.observe_codex_hook(other, {
            "hook_event_name": "PreToolUse", "session_id": "parent-cross",
            "turn_id": "turn-cross",
            "tool_name": "spawn_agent", "tool_use_id": "tool-cross",
            "tool_input": armed["launch_envelope"],
        })
        self.adapter.observe_codex_hook(other, {
            "hook_event_name": "PostToolUse", "session_id": "parent-cross",
            "turn_id": "turn-cross",
            "tool_name": "spawn_agent", "tool_use_id": "tool-cross",
            "tool_response": {"task_name": armed["launch_envelope"]["task_name"]},
        })
        state = json.loads((self.root / armed["request_path"]).read_text("utf-8"))
        self.assertEqual(state["state"], "LAUNCHING")
        self.assertEqual(state["repository"]["path"], str(self.root.resolve()))
        self.assertFalse((other / ".codearbiter").exists())

    def test_wrong_child_incomplete_coverage_and_blocking_finding_fail_closed(self):
        for suffix, mutate in (
            ("wrong-child", lambda event, decision: event.update(agent_id="other-child")),
            ("missing-coverage", lambda event, decision: decision.update(coverage=["AC-001"])),
            ("blocking", lambda event, decision: decision.update(findings=[{
                "severity": "BLOCK", "code": "SPEC_GAP", "message": "Gap remains."
            }])),
        ):
            with self.subTest(case=suffix):
                armed = self._arm_review("review-request-" + suffix)
                self.adapter.observe_codex_hook(self.root, {
                    "hook_event_name": "PreToolUse", "session_id": "parent-session",
                    "turn_id": "turn-" + suffix,
                    "tool_name": "spawn_agent", "tool_use_id": "tool-" + suffix,
                    "tool_input": armed["launch_envelope"],
                })
                self.adapter.observe_codex_hook(self.root, {
                    "hook_event_name": "PostToolUse", "session_id": "parent-session",
                    "turn_id": "turn-" + suffix,
                    "tool_name": "spawn_agent", "tool_use_id": "tool-" + suffix,
                    "tool_response": {"task_name": armed["launch_envelope"]["task_name"]},
                })
                self.adapter.observe_codex_hook(self.root, {
                    "hook_event_name": "SubagentStart", "session_id": "parent-session",
                    "turn_id": "turn-" + suffix,
                    "agent_id": "child-" + suffix, "agent_type": "default",
                })
                decision = {
                    "format": "codearbiter.review-decision/0.1.0",
                    "request_id": armed["request_id"], "target_sha256": "3" * 64,
                    "contract_sha256": armed["review_contract_sha256"], "decision": "pass",
                    "coverage": ["AC-001", "AC-002"], "findings": [],
                    "assessment": "Looks correct.",
                }
                event = {
                    "hook_event_name": "SubagentStop", "session_id": "parent-session",
                    "turn_id": "turn-" + suffix,
                    "agent_id": "child-" + suffix, "agent_type": "default",
                    "last_assistant_message": json.dumps(decision),
                }
                mutate(event, decision)
                event["last_assistant_message"] = json.dumps(decision)
                with self.assertRaises(RuntimeError):
                    self.adapter.observe_codex_hook(self.root, event)

    def test_review_request_requires_supported_codex_hook_seam(self):
        armed = self._arm_review("review-request-unsupported")
        self.assertIsNone(self.adapter.observe_codex_hook(self.root, {
            "hook_event_name": "SubagentStart",
            "session_id": "parent-session",
            "turn_id": "turn-unsupported",
            "agent_id": "child-agent-1",
            "agent_type": "default",
        }))
        with self.assertRaisesRegex(RuntimeError, "AUTHORITY_NOT_COMPLETE"):
            self.adapter.publish_request(self.root, self.client, armed["request_id"])

    def test_tampered_durable_request_is_rejected(self):
        armed = self._arm_review("review-request-tamper")
        path = self.root / armed["request_path"]
        value = json.loads(path.read_text(encoding="utf-8"))
        value["activity"] = "quality_review"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_AUTHORITY_STATE"):
            self.adapter.publish_request(self.root, self.client, armed["request_id"])


if __name__ == "__main__":
    unittest.main()
