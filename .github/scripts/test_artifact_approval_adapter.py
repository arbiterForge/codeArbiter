#!/usr/bin/env python3
"""Regression tests for host-owned structured-artifact approval capture."""

import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORE_PYSRC = REPO / "core" / "pysrc"
sys.path.insert(0, str(CORE_PYSRC))
from _gitexec import root_bound_git_env  # noqa: E402


def git_run(argv, **kwargs):
    return subprocess.run(argv, env=root_bound_git_env(), **kwargs)


class _FakeClient:
    def __init__(self, root):
        self.root = root
        self.identity = {
            "artifact_id": "SPEC-EXAMPLE",
            "kind": "spec",
            "revision": 7,
            "model_sha256": "1" * 64,
            "normative_sha256": "2" * 64,
        }
        self.calls = []
        self.failure = None
        self.capture_result = {
            "receipt": ".codearbiter/.artifacts/receipts/" + "3" * 64 + ".json",
            "receipt_sha256": "3" * 64,
        }

    def call(self, operation, request=None, **_kwargs):
        request = dict(request or {})
        self.calls.append((operation, request))
        if operation == self.failure:
            raise RuntimeError(f"{operation} failed")
        if operation == "identity":
            return dict(self.identity)
        if operation == "validate":
            return {
                **self.identity,
                "valid": True,
                "gate": "ready",
                "authority": {
                    "state": "draft",
                    "authority_verified": False,
                },
            }
        if operation == "evidence-context":
            context = {
                "format": "codearbiter.evidence-context/0.1.0",
                "activity": "approval",
                "subject": {"artifact_id": self.identity["artifact_id"], "normative_sha256": self.identity["normative_sha256"], "record_id": self.identity["artifact_id"]},
                "input_sha256": self.identity["normative_sha256"],
                "prompt_sha256": request["prompt_sha256"],
                "record": dict(self.identity),
            }
            raw_record = json.dumps(context["record"], ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            context["record_sha256"] = hashlib.sha256(raw_record).hexdigest()
            raw = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path(".codearbiter/.artifacts/evidence-contexts") / f"{digest}.json"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"context_ref": relative.as_posix(), "context_sha256": digest}
        if operation == "capture-observation":
            return dict(self.capture_result)
        if operation == "approve":
            return {"artifact_id": "SPEC-EXAMPLE", "revision": 8}
        raise AssertionError(operation)


class ApprovalAdapterTest(unittest.TestCase):
    def setUp(self):
        from test_artifact_authoring import physical_test_directory
        self.temp = tempfile.TemporaryDirectory()
        self.root = physical_test_directory(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.client = _FakeClient(self.root)
        self.adapter = importlib.import_module("_approvallib")
        self.routes = importlib.import_module("_artifactpromptlib")
        self.original_registry_parent = self.routes.REGISTRY_PARENT
        self.routes.REGISTRY_PARENT = self.root
        self.replies = importlib.import_module("_replylib")
        self.original_code_parent = self.replies.REGISTRY_PARENT
        self.replies.REGISTRY_PARENT = self.root

    def tearDown(self):
        self.routes.REGISTRY_PARENT = self.original_registry_parent
        self.replies.REGISTRY_PARENT = self.original_code_parent
        self.temp.cleanup()

    def hook(self, prompt, root=None):
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            return self.adapter.consume_from_hook(
                root=root or self.root, plugin_root=self.root, prompt=prompt,
                host="claude", session_id="session-lenient",
            )

    def test_short_code_from_hook_approves_and_records_the_full_reply(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-short")
        self.assertRegex(armed["code"], r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$")
        self.assertEqual(armed["short_reply"], f"approve {armed['code']}")
        other = self.root / "elsewhere"
        other.mkdir()
        text = self.hook(f"  Approve {armed['code'].lower()}.\n", root=other)
        self.assertIn("workflow approval recorded", text)
        source = next((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["source_text"], armed["reply"])
        self.assertIn("matches no armed request", self.replies.expand(armed["short_reply"])["notice"])

    def test_padded_full_reply_from_hook_approves(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-pad")
        text = self.hook("\u200b\u00a0`" + armed["reply"] + "`\r\n")
        self.assertIn("workflow approval recorded", text)

    def test_hook_reports_misses_instead_of_silence(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-miss")
        before = list(self.client.calls)
        cases = {
            "  approve ZZZZ": "matches no armed request",
            f"approve SPEC-OTHER {armed['code']}": "belongs to SPEC-EXAMPLE",
            armed["reply"] + ", please": "Send only the reply line",
            "approve SPEC-EXAMPLE wrong-token-value": "Send only the reply line",
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                self.assertIn(expected, self.hook(prompt))
        self.assertEqual(self.hook("yes"), "")
        self.assertEqual(self.hook("please approve it"), "")
        self.assertEqual(self.client.calls, before)
        self.assertTrue((self.root / self.adapter.PENDING).exists())

    def ask_payload(self, event, tool_input, *, call="toolu_1", session="session-ask", response=None):
        payload = {"hook_event_name": event, "tool_name": "AskUserQuestion", "session_id": session,
                   "tool_use_id": call, "tool_input": tool_input}
        if response is not None:
            payload["tool_response"] = response
        return payload

    def choose(self, armed, label, **kw):
        question = armed["ask_envelope"]["questions"][0]["question"]
        return {"questions": armed["ask_envelope"]["questions"], "answers": {question: label}}

    def test_click_approve_on_a_clean_call_records_the_ask_seam(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-ask")
        envelope = armed["ask_envelope"]
        options = [o["label"] for o in envelope["questions"][0]["options"]]
        self.assertEqual(options, [f"Approve {armed['code']}", "Not yet"])
        self.assertLessEqual(len(envelope["questions"][0]["header"]), 12)
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", envelope))
        chosen = self.replies.observe_ask_post(self.ask_payload(
            "PostToolUse", envelope, response=self.choose(armed, f"Approve {armed['code']}")))
        self.assertEqual(chosen["prompt"], armed["short_reply"])
        self.assertEqual(Path(chosen["root"]).resolve(), self.root.resolve())
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            text = self.adapter.consume_from_hook(root=chosen["root"], plugin_root=self.root,
                                                  prompt=chosen["prompt"], host="claude",
                                                  session_id="session-ask", seam="AskUserQuestion")
        self.assertIn("workflow approval recorded", text)
        event = json.loads(next((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json")).read_text())
        self.assertEqual(event["origin"], "claude:AskUserQuestion:session-ask")
        self.assertEqual(event["source_text"], armed["reply"])

    def test_prefilled_answers_are_denied_and_retire_click_approval(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-pre")
        envelope = armed["ask_envelope"]
        forged = dict(envelope, answers={envelope["questions"][0]["question"]: f"Approve {armed['code']}"})
        with self.assertRaises(self.replies.ReplyCodeError):
            self.replies.observe_ask_pre(self.ask_payload("PreToolUse", forged))
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", envelope, call="toolu_2"))
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload(
            "PostToolUse", envelope, call="toolu_2", response=self.choose(armed, f"Approve {armed['code']}"))))
        # The typed code still works after a refused click.
        self.assertIn("workflow approval recorded", self.hook(armed["short_reply"]))

    def test_click_needs_a_clean_pretooluse_for_the_same_call_and_the_approve_option(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-seq")
        envelope = armed["ask_envelope"]
        approve = self.choose(armed, f"Approve {armed['code']}")
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload("PostToolUse", envelope, response=approve)))
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", envelope, call="toolu_a"))
        self.assertIsNone(self.replies.observe_ask_post(
            self.ask_payload("PostToolUse", envelope, call="toolu_b", response=approve)))
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", envelope, call="toolu_c"))
        self.assertIsNone(self.replies.observe_ask_post(
            self.ask_payload("PostToolUse", envelope, call="toolu_c", response=self.choose(armed, "Not yet"))))
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", envelope, call="toolu_d"))
        self.assertIsNone(self.replies.observe_ask_post(
            self.ask_payload("PostToolUse", envelope, call="toolu_d", session="other-session", response=approve)))
        self.assertTrue((self.root / self.adapter.PENDING).exists())

    def test_a_clean_call_cannot_be_reused_for_another_envelope_or_answered_twice(self):
        first = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-one")
        other_root = self.root / "second-repo"
        (other_root / ".codearbiter").mkdir(parents=True)
        other_client = _FakeClient(other_root)
        second = self.adapter.arm_user_approval(other_root, other_client, "SPEC-EXAMPLE", token="fixed-token-two")
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", first["ask_envelope"], call="toolu_x"))
        swapped = self.ask_payload("PostToolUse", second["ask_envelope"], call="toolu_x",
                                   response=self.choose(second, f"Approve {second['code']}"))
        self.assertIsNone(self.replies.observe_ask_post(swapped))

        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", first["ask_envelope"], call="toolu_y"))
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload(
            "PostToolUse", first["ask_envelope"], call="toolu_y", response=self.choose(first, "Not yet"))))
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload(
            "PostToolUse", first["ask_envelope"], call="toolu_y",
            response=self.choose(first, f"Approve {first['code']}"))))

    def test_altered_or_ordinary_questions_are_never_touched(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-alt")
        altered = json.loads(json.dumps(armed["ask_envelope"]))
        altered["questions"][0]["question"] += " (edited)"
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", altered))
        answer = {"questions": altered["questions"],
                  "answers": {altered["questions"][0]["question"]: f"Approve {armed['code']}"}}
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload("PostToolUse", altered, response=answer)))
        ordinary = {"questions": [{"question": "Pick one?", "header": "Pick", "multiSelect": False,
                                   "options": [{"label": "A", "description": "a"}, {"label": "B", "description": "b"}]}],
                    "answers": {"Pick one?": "A"}}
        self.replies.observe_ask_pre(self.ask_payload("PreToolUse", ordinary))
        self.assertIsNone(self.replies.observe_ask_post(self.ask_payload("PostToolUse", ordinary, response=ordinary)))

    def test_hook_entry_denies_a_prefilled_armed_question(self):
        armed = self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-hook")
        envelope = armed["ask_envelope"]
        forged = dict(envelope, answers={envelope["questions"][0]["question"]: f"Approve {armed['code']}"})
        spec = importlib.util.spec_from_file_location("artifact_authority_hook", CORE_PYSRC / "artifact-authority-hook.py")
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        import io
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            hook._claude_ask("PreToolUse", self.ask_payload("PreToolUse", forged))
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_near_miss_log_is_bounded_escaped_and_only_when_active(self):
        self.adapter.arm_user_approval(self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-log")
        log = self.root / ".codearbiter/.markers/reply-diagnostics.log"
        self.hook("approve ZZZZ\u200b")
        self.assertFalse(log.exists())
        (self.root / ".codearbiter" / "CONTEXT.md").write_text("---\nfixture: active\n---\n", encoding="utf-8")
        self.hook("approve ZZZZ\u200b " + "pasted-text " * 60)
        line = log.read_text(encoding="ascii")
        self.assertIn("U+200B", line)
        self.assertLess(len(line), 1400)
        self.assertNotIn("pasted-text " * 20, line)

    def test_cross_repository_hook_routes_exact_prompt_and_ambiguity_fails_closed(self):
        other = self.root / "other"
        other.mkdir()
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-route"
        )
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            result = self.adapter.consume_from_hook(
                root=other, plugin_root=self.root, prompt=armed["reply"],
                host="codex", session_id="session-route",
            )
        self.assertIn("workflow approval recorded", result)
        self.assertFalse((self.root / self.adapter.PENDING).exists())

        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        prompt = "approve SPEC-COLLISION fixed-token-route"
        self.routes.register(first, "approval", "SPEC-COLLISION", prompt)
        self.routes.register(second, "approval", "SPEC-COLLISION", prompt)
        with self.assertRaisesRegex(RuntimeError, "multiple repositories"):
            self.routes.resolve("approval", prompt)

    def test_new_pending_prompt_replaces_stale_route_for_the_same_artifact(self):
        stale = "approve SPEC-EXAMPLE stale-token"
        current = "approve SPEC-EXAMPLE current-token"
        self.routes.register(self.root, "approval", "SPEC-EXAMPLE", stale)
        self.routes.register(self.root, "approval", "SPEC-EXAMPLE", current)
        self.assertIsNone(self.routes.resolve("approval", stale))
        self.assertEqual(self.routes.resolve("approval", current), self.root.resolve())

    def test_native_linked_worktree_identity_is_routable(self):
        repository = self.root / "repository"
        linked = self.root / "linked"
        git_run(["git", "init", "--quiet", str(repository)], check=True)
        git_run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
        git_run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        (repository / "tracked.txt").write_text("x", encoding="utf-8")
        git_run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
        git_run(["git", "-C", str(repository), "commit", "--quiet", "-m", "fixture"], check=True)
        git_run(["git", "-C", str(repository), "worktree", "add", "--quiet", "-b", "linked", str(linked)], check=True)
        prompt = "approve SPEC-LINKED fixed-token-linked"
        self.routes.register(linked, "approval", "SPEC-LINKED", prompt)
        self.assertEqual(self.routes.resolve("approval", prompt), linked.resolve())

    def test_linked_worktree_fixture_ignores_inherited_git_location(self):
        ambient = {
            "GIT_DIR": str(self.root / "ambient.git"),
            "GIT_WORK_TREE": str(self.root / "ambient-worktree"),
            "GIT_INDEX_FILE": str(self.root / "ambient-index"),
        }
        with mock.patch.dict(os.environ, ambient):
            self.test_native_linked_worktree_identity_is_routable()

    def test_exact_host_prompt_captures_and_approves_current_identity(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        self.assertEqual(
            armed["reply"], "approve SPEC-EXAMPLE fixed-token-1"
        )

        result = self.adapter.consume_user_approval(
            self.root,
            self.client,
            armed["reply"],
            host="codex",
            session_id="session-1",
        )

        self.assertTrue(result["approved"])
        source = self.root / result["authority_source"]
        event = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(event["source_text"], armed["reply"])
        self.assertEqual(event["origin"], "codex:UserPromptSubmit:session-1")
        self.assertEqual(event["subject"]["normative_sha256"], "2" * 64)
        self.assertEqual([name for name, _ in self.client.calls][-2:], ["capture-observation", "approve"])
        self.assertFalse((self.root / ".codearbiter" / ".markers" / "pending-user-approval.json").exists())

    def test_plain_yes_wrong_token_and_unrelated_prompt_confer_no_authority(self):
        self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        before = list(self.client.calls)
        for prompt in ("yes", "approve SPEC-EXAMPLE wrong", "please continue"):
            result = self.adapter.consume_user_approval(
                self.root, self.client, prompt, host="codex", session_id="session-1"
            )
            self.assertFalse(result["matched"])
        self.assertEqual(self.client.calls, before)

    def test_stale_artifact_blocks_before_authority_source_or_capture(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        self.client.identity["model_sha256"] = "9" * 64

        with self.assertRaisesRegex(RuntimeError, "STALE_APPROVAL"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )

        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_pending_request_blocks_rearm_until_exact_artifact_is_cancelled(self):
        self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        with self.assertRaisesRegex(RuntimeError, "PENDING_APPROVAL"):
            self.adapter.arm_user_approval(
                self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-2"
            )
        with self.assertRaisesRegex(RuntimeError, "PENDING_APPROVAL_MISMATCH"):
            self.adapter.cancel_user_approval(self.root, "SPEC-OTHER")

        result = self.adapter.cancel_user_approval(self.root, "SPEC-EXAMPLE")

        self.assertEqual(result, {"artifact_id": "SPEC-EXAMPLE", "cancelled": True})
        self.assertFalse(
            (self.root / ".codearbiter" / ".markers" / "pending-user-approval.json").exists()
        )
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_malformed_pending_values_and_host_context_fail_closed(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        pending_path = (
            self.root / ".codearbiter" / ".markers" / "pending-user-approval.json"
        )
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending["token_sha256"] = 7
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_PENDING_APPROVAL"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )

        pending["token_sha256"] = hashlib.sha256(b"fixed-token-1").hexdigest()
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_HOST_CONTEXT"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="bad session",
            )
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_capture_and_approve_failures_never_report_success_and_remain_retryable(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        pending = self.root / self.adapter.PENDING

        self.client.capture_result = {}
        with self.assertRaisesRegex(RuntimeError, "INVALID_RECEIPT"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )
        self.assertTrue(pending.exists())
        self.assertNotIn("approve", [name for name, _ in self.client.calls])

        self.client.capture_result = {
            "receipt": ".codearbiter/.artifacts/receipts/" + "3" * 64 + ".json"
        }
        self.client.failure = "approve"
        with self.assertRaisesRegex(RuntimeError, "approve failed"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )
        self.assertTrue(pending.exists())

        self.client.failure = None
        result = self.adapter.consume_user_approval(
            self.root,
            self.client,
            armed["reply"],
            host="codex",
            session_id="session-1",
        )
        self.assertTrue(result["approved"])
        self.assertFalse(pending.exists())

    def test_hook_contains_oserror_without_hiding_an_explicit_approval_failure(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE"
        )
        with mock.patch.object(
            self.adapter._artifactlib,
            "ArtifactClient",
            side_effect=OSError("helper startup failed"),
        ):
            unrelated = self.adapter.consume_from_hook(
                root=self.root,
                plugin_root=self.root,
                prompt="continue with unrelated work",
                host="codex",
                session_id="session-1",
            )
            result = self.adapter.consume_from_hook(
                root=self.root,
                plugin_root=self.root,
                prompt=armed["reply"],
                host="codex",
                session_id="session-1",
            )

        self.assertEqual(unrelated, "")
        self.assertEqual(
            result,
            "codeArbiter: approval capture failed: helper startup failed",
        )
        self.assertTrue((self.root / self.adapter.PENDING).exists())

    def test_write_new_removes_partial_file_after_io_failure(self):
        real_close = self.adapter.os.close

        def close_then_fail(fd):
            real_close(fd)
            raise OSError("close failed")

        failures = (
            (
                "write",
                mock.patch.object(
                    self.adapter.os, "write", side_effect=OSError("write failed")
                ),
            ),
            (
                "fsync",
                mock.patch.object(
                    self.adapter.os, "fsync", side_effect=OSError("fsync failed")
                ),
            ),
            (
                "close",
                mock.patch.object(
                    self.adapter.os, "close", side_effect=close_then_fail
                ),
            ),
        )
        for operation, failure in failures:
            with self.subTest(operation=operation):
                relative = (
                    Path(".codearbiter")
                    / ".markers"
                    / f"write-new-{operation}-test.json"
                )
                path = self.root / relative
                with failure, self.assertRaisesRegex(OSError, f"{operation} failed"):
                    self.adapter._write_new(self.root, relative, b"partial")

                self.assertFalse(path.exists())
                self.adapter._write_new(self.root, relative, b"retry")
                self.assertEqual(path.read_bytes(), b"retry")
                path.unlink()



class _PlanClient(_FakeClient):
    def __init__(self, root):
        super().__init__(root)
        self.identity.update(artifact_id="PLAN-EXAMPLE", kind="plan")
        self.tasks = [{"id": "T-001", "verification": [{
            "availability": "proposed", "cwd": ".",
            "argv": ["python", "-m", "unittest", "-v", "tests.future_test"],
            "required_tests": ["test_future_behavior"], "expected_exit": 0,
        }]}]
        self.snapshot_error = None
        self.drift_after = None
        self.bad_next_offset = False

    def call(self, operation, request=None, **kwargs):
        request = dict(request or {})
        if operation not in {"outline", "read", "snapshot"}:
            return super().call(operation, request, **kwargs)
        self.calls.append((operation, request))
        identity = dict(self.identity)
        if operation == "outline":
            offset = request.get("offset", 0)
            task = self.tasks[offset]
            result = {**identity, "offset": offset, "total": len(self.tasks),
                      "records": [{"id": task["id"], "kind": "tasks", "retired": False}],
                      "next_offset": offset if self.bad_next_offset else
                      (offset + 1 if offset + 1 < len(self.tasks) else None)}
        elif operation == "read":
            result = {**identity, "mode": "exact", "context_complete": False,
                      "record": next(task for task in self.tasks if task["id"] == request["symbol"])}
        else:
            if self.snapshot_error:
                raise self.snapshot_error
            result = {"sha256": "8" * 64, "entry_count": 1,
                      "platform": "fixture", "roots": ["."], "exclude_directories": []}
        if operation == self.drift_after:
            self.identity["model_sha256"] = "9" * 64
        return result


class PlanApprovalPreflightTest(unittest.TestCase):
    setUp = ApprovalAdapterTest.setUp
    tearDown = ApprovalAdapterTest.tearDown

    def test_offline_bridge_does_not_import_runner_capabilities(self):
        from test_artifact_installed_host import assert_offline_bridge
        assert_offline_bridge((CORE_PYSRC / "_artifactlib.py").read_bytes())

    def plan(self):
        self.client = _PlanClient(self.root)
        return self.client

    def arm(self):
        return self.adapter.arm_user_approval(
            self.root, self.client, "PLAN-EXAMPLE", token="plan-preflight-token"
        )

    def test_reports_all_commands_and_snapshot_before_pending_approval(self):
        client = self.plan()
        client.tasks = [
            {"id": task, "verification": [{"availability": "proposed", "cwd": ".",
             "argv": [runner, "test"], "required_tests": ["named_test"], "expected_exit": 0}]}
            for task, runner in (("T-001", "unsupported-one"), ("T-002", "unsupported-two"))
        ]
        client.snapshot_error = self.adapter._artifactlib.ArtifactError(
            "MAX_BYTES", "site/node_modules/pagefind.exe exceeds 33554432 bytes"
        )
        with self.assertRaisesRegex(RuntimeError, "PLAN_VERIFICATION_UNAVAILABLE") as caught:
            self.arm()
        for detail in ("T-001", "T-002", "unsupported-one", "unsupported-two", "pagefind.exe", "MAX_BYTES"):
            self.assertIn(detail, str(caught.exception))
        self.assertEqual([r[1]["symbol"] for r in client.calls if r[0] == "read"], ["T-001", "T-002"])
        self.assertFalse((self.root / self.adapter.PENDING).exists())

    def test_snapshot_failure_alone_blocks_plan_approval(self):
        client = self.plan()
        client.snapshot_error = self.adapter._artifactlib.ArtifactError("UNSAFE_PATH", "included source is a link")
        with self.assertRaisesRegex(RuntimeError, "UNSAFE_PATH"):
            self.arm()
        self.assertFalse((self.root / self.adapter.PENDING).exists())

    def test_readiness_keeps_actionable_input_policy_diagnostics(self):
        client = self.plan()
        original = client.call
        def diagnosed(operation, request=None, **kwargs):
            result = original(operation, request, **kwargs)
            if operation == "validate":
                result.update(valid=False, diagnostics=[{
                    "code": "INVALID_INPUT_POLICY", "field": "verification_inputs.exclude_directories",
                    "message": "node_modules must be qualified as a repository-relative path such as site/node_modules",
                }])
            return result
        with mock.patch.object(client, "call", side_effect=diagnosed):
            with self.assertRaisesRegex(RuntimeError, "NOT_READY.*site/node_modules"):
                self.arm()

    def test_identity_change_during_read_never_arms(self):
        self.plan().drift_after = "read"
        with self.assertRaisesRegex(RuntimeError, "STALE_PLAN_PREFLIGHT"):
            self.arm()
        self.assertFalse((self.root / self.adapter.PENDING).exists())

    def test_identity_change_during_snapshot_never_arms(self):
        self.plan().drift_after = "snapshot"
        with self.assertRaisesRegex(RuntimeError, "STALE_PLAN_PREFLIGHT"):
            self.arm()
        self.assertFalse((self.root / self.adapter.PENDING).exists())

    def test_nonadvancing_outline_never_arms(self):
        self.plan().bad_next_offset = True
        with self.assertRaisesRegex(RuntimeError, "INVALID_RESPONSE"):
            self.arm()
        self.assertFalse((self.root / self.adapter.PENDING).exists())

    def test_proposed_test_does_not_need_to_exist_or_execute(self):
        self.plan()
        self.assertFalse((self.root / "tests/future_test.py").exists())
        with mock.patch("subprocess.Popen", side_effect=AssertionError("preflight executed a process")):
            result = self.arm()
        self.assertEqual(result["artifact_id"], "PLAN-EXAMPLE")
        self.assertIn("snapshot", [operation for operation, _ in self.client.calls])


class ApprovalFixturePathTest(unittest.TestCase):
    def test_plan_fixture_uses_a_physical_temporary_root(self):
        from test_artifact_authoring import physical_test_directory
        with tempfile.TemporaryDirectory(prefix="ca-approval-fixture-path-") as temporary:
            base = physical_test_directory(temporary)
            physical, linked = base / "physical", base / "linked"
            physical.mkdir()
            if os.name == "nt":
                made = subprocess.run(
                    ["cmd", "/d", "/c", "mklink", "/J", str(linked), str(physical)],
                    capture_output=True, text=True,
                )
                self.assertEqual(made.returncode, 0, made.stderr)
            else:
                linked.symlink_to(physical, target_is_directory=True)
            with mock.patch.object(tempfile, "tempdir", str(linked)):
                fixture = PlanApprovalPreflightTest(
                    "test_proposed_test_does_not_need_to_exist_or_execute"
                )
                fixture.setUp()
                try:
                    self.assertEqual(fixture.root, physical_test_directory(fixture.root))
                    fixture.test_proposed_test_does_not_need_to_exist_or_execute()
                finally:
                    fixture.tearDown()


class SprintPairIntegrationTest(unittest.TestCase):
    """Real installed-engine fixtures, not authenticated model-turn proof."""
    @classmethod
    def setUpClass(cls):
        from test_artifact_authoring import build_installation
        cls.owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls):
        if cls.owner is not None:
            cls.owner.cleanup()

    def setUp(self):
        from test_artifact_authoring import physical_test_directory, WorkflowHarness
        self.temp = tempfile.TemporaryDirectory(prefix="ca-sprint-pair-")
        self.addCleanup(self.temp.cleanup)
        self.root = physical_test_directory(self.temp.name) / "repo"
        self.root.mkdir()
        self.h = WorkflowHarness(self.root, self.installation)
        self.spec, self.plan = self.h.create_pair()
        self.approval = importlib.import_module("_approvallib")
        self.pair = importlib.import_module("_sprintapprovallib")
        self.lib = importlib.import_module("_artifactlib")
        self.routes = importlib.import_module("_artifactpromptlib")
        previous = self.routes.REGISTRY_PARENT
        self.routes.REGISTRY_PARENT = self.root.parent
        self.addCleanup(setattr, self.routes, "REGISTRY_PARENT", previous)
        self.replies = importlib.import_module("_replylib")
        previous_codes = self.replies.REGISTRY_PARENT
        self.replies.REGISTRY_PARENT = self.root.parent
        self.addCleanup(setattr, self.replies, "REGISTRY_PARENT", previous_codes)

    def arm(self, delegate=True):
        return self.pair.arm(self.root, self.h.client, "SPEC-FLOW", "PLAN-FLOW", delegate_methods=delegate, token="synthetic-pair-token")

    def consume(self, reply):
        return self.approval.consume_user_approval(self.root, self.h.client, reply, host="codex", session_id="synthetic-host-turn")

    def identities(self):
        return [self.h.client.call("identity", {"artifact_id": i}) for i in ("SPEC-FLOW", "PLAN-FLOW")]

    def decision(self):
        lenses = {k: {"verdict": "Adequate", "reason": "The recorded contract and bounded verification remain unchanged."} for k in ("Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable")}
        return {"task_id": "T-001", "options": [{"label": "Explicit precedence table", "steps": ["Retain the negative oracle.", "Implement precedence with a bounded table lookup."], "lenses": lenses}], "selected": 0, "strength": "moderate", "rationale": "The recorded spec requires environment precedence. This method conforms without changing paths, criteria or verification."}

    def test_unsupported_runner_blocks_pair_before_any_pending_approval(self):
        command = {"availability": "proposed", "cwd": ".", "argv": ["unsupported-pair", "test"],
                   "required_tests": ["test_environment_overrides"], "expected_exit": 0,
                   "assertion": "The named test must pass."}
        self.h.mutate("apply", "PLAN-FLOW", changes=[{"op": "record.update", "symbol": "T-001",
                                                      "fields": {"verification": [command]}}])
        before = self.identities()
        with self.assertRaisesRegex(RuntimeError, "PLAN_VERIFICATION_UNAVAILABLE.*T-001"):
            self.arm()
        self.assertEqual(self.identities(), before)
        self.assertFalse((self.root / self.approval.PENDING).exists())

    def test_pair_preflight_reports_oversized_present_input_without_requiring_proposed_test(self):
        self.assertFalse((self.root / "tests/test_config.py").exists())
        with (self.root / "generated.exe").open("wb") as output:
            output.truncate((32 << 20) + 1)
        before = self.identities()
        with self.assertRaisesRegex(RuntimeError, "PLAN_VERIFICATION_UNAVAILABLE.*generated.exe.*33554432"):
            self.arm()
        self.assertEqual(self.identities(), before)
        self.assertFalse((self.root / self.approval.PENDING).exists())

    def test_one_reply_approves_both_without_individual_approve_calls(self):
        armed = self.arm()
        before = self.identities()
        with mock.patch.object(self.h.client, "call", wraps=self.h.client.call) as calls:
            result = self.consume(armed["reply"])
        operations = [v.args[0] for v in calls.call_args_list]
        self.assertEqual(operations.count("sprint-approve"), 1)
        self.assertNotIn("approve", operations)
        self.assertNotIn("capture-observation", operations)
        self.assertTrue(result["approved"])
        self.assertIsInstance(result["grant_receipt"], str)
        after = self.identities()
        self.assertTrue(all(v["authority"]["authority_verified"] for v in after))
        self.assertEqual(before[0]["normative_sha256"], after[0]["normative_sha256"])
        self.assertNotEqual(before[1]["normative_sha256"], after[1]["normative_sha256"])
        sources = list((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        self.assertEqual(len(sources), 2)
        self.assertTrue(all(json.loads(p.read_text())["source_text"] == armed["reply"] for p in sources))
        self.assertFalse((self.root / self.approval.PENDING).exists())
        self.assertFalse(list((self.root / ".codearbiter/specs").glob("*.md")))
        self.assertFalse(list((self.root / ".codearbiter/plans").glob("*.md")))

    def test_reply_mode_and_nonce_are_not_implicit_delegation(self):
        armed = self.arm(False)
        before = self.identities()
        for reply in ("yes", "continue", armed["reply"].replace("approve-only", "delegate-methods"), armed["reply"] + " trailing"):
            self.assertFalse(self.consume(reply)["matched"])
        self.assertEqual(self.identities(), before)
        self.assertFalse((self.root / ".codearbiter/.artifacts/authority-sources").exists())
        self.assertIsNone(self.consume(armed["reply"])["grant_receipt"])

    def test_stale_spec_refused_before_observation(self):
        armed = self.arm()
        self.h.mutate("apply", "SPEC-FLOW", changes=[{"op": "header.update", "fields": {"summary": "Changed during the user review."}}])
        with self.assertRaisesRegex(RuntimeError, "STALE_APPROVAL"):
            self.consume(armed["reply"])
        self.assertFalse((self.root / ".codearbiter/.artifacts/authority-sources").exists())

    def test_stale_plan_refused_before_observation(self):
        armed = self.arm()
        self.h.mutate("apply", "PLAN-FLOW", changes=[{"op": "header.update", "fields": {"summary": "Changed during the user review."}}])
        with self.assertRaisesRegex(RuntimeError, "STALE_APPROVAL"):
            self.consume(armed["reply"])
        self.assertFalse((self.root / ".codearbiter/.artifacts/authority-sources").exists())

    def test_unobserved_arm_cannot_be_resumed_as_approval(self):
        self.arm()
        with self.assertRaisesRegex(RuntimeError, "NO_OBSERVED_APPROVAL"):
            self.pair.resume(self.root, self.h.client, "PLAN-FLOW")
        self.assertFalse(any(v["authority"]["authority_verified"] for v in self.identities()))

    def test_lost_success_response_replays_without_a_second_user_reply(self):
        armed = self.arm()
        original = self.h.client.call
        def lose_response(operation, request=None, **kwargs):
            result = original(operation, request, **kwargs)
            if operation == "sprint-approve":
                raise self.lib.ArtifactError("EXECUTION_FAILED", "Synthetic transport loss after committed response")
            return result
        with mock.patch.object(self.h.client, "call", side_effect=lose_response):
            with self.assertRaisesRegex(RuntimeError, "EXECUTION_FAILED"):
                self.consume(armed["reply"])
        approved = self.identities()
        self.assertTrue(all(v["authority"]["authority_verified"] for v in approved))
        result = self.pair.resume(self.root, self.h.client, "PLAN-FLOW")
        self.assertTrue(result["approved"])
        self.assertEqual(self.identities(), approved)
        self.assertFalse((self.root / self.approval.PENDING).exists())

    def test_failure_before_native_commit_retains_observed_submission(self):
        armed = self.arm()
        original = self.h.client.call
        def fail(operation, request=None, **kwargs):
            if operation == "sprint-approve":
                raise self.lib.ArtifactError("EXECUTION_FAILED", "Synthetic interruption before commit")
            return original(operation, request, **kwargs)
        with mock.patch.object(self.h.client, "call", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "EXECUTION_FAILED"):
                self.consume(armed["reply"])
        with self.assertRaisesRegex(RuntimeError, "SUBMITTED_APPROVAL"):
            self.approval.cancel_user_approval(self.root, "PLAN-FLOW")
        self.assertTrue(self.pair.resume(self.root, self.h.client, "PLAN-FLOW")["approved"])

    def test_cancel_before_reply_retains_no_authority(self):
        self.arm()
        self.assertTrue(self.approval.cancel_user_approval(self.root, "PLAN-FLOW")["cancelled"])
        self.assertFalse(any(v["authority"]["authority_verified"] for v in self.identities()))

    def test_smarts_produces_scoped_approval_without_another_prompt(self):
        result = self.consume(self.arm()["reply"])
        before = self.h.client.call("read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"})["record"]
        out = self.h.mutate("smarts-apply", "PLAN-FLOW", grant_receipt=result["grant_receipt"], decision=self.decision())
        after = self.h.client.call("read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"})["record"]
        self.assertEqual(out["authority_kind"], "smarts_workflow")
        self.assertFalse(out["acceptance_granted"])
        self.assertNotEqual(before["steps"], after["steps"])
        self.assertEqual({k: v for k, v in before.items() if k != "steps"}, {k: v for k, v in after.items() if k != "steps"})
        self.assertTrue(self.h.client.call("validate", {"artifact_id": "PLAN-FLOW", "gate": "approved"})["valid"])
        self.assertFalse(self.h.client.call("eligible", {"artifact_id": "PLAN-FLOW"})["all_accepted_and_current"])
        self.assertFalse((self.root / self.approval.PENDING).exists())

    def test_no_delegation_and_scope_expansion_refused(self):
        result = self.consume(self.arm(False)["reply"])
        before = self.identities()
        with self.assertRaisesRegex(RuntimeError, "DELEGATION_REQUIRED"):
            self.h.mutate("smarts-apply", "PLAN-FLOW", grant_receipt=result["receipt"], decision=self.decision())
        self.assertEqual(self.identities(), before)

    def test_unknown_fields_cannot_weaken_verification(self):
        result = self.consume(self.arm()["reply"])
        decision = self.decision()
        decision["options"][0]["verification"] = []
        before = self.identities()
        with self.assertRaises(self.lib.ArtifactError):
            self.h.mutate("smarts-apply", "PLAN-FLOW", grant_receipt=result["grant_receipt"], decision=decision)
        self.assertEqual(self.identities(), before)

    def test_preview_is_explicit_and_does_not_relax_feature_preflight(self):
        from test_artifact_authoring import WorkflowHarness
        root = self.root.parent / "preview"
        root.mkdir()
        h = WorkflowHarness(root, self.installation)
        spec = h.create_spec()
        selected = self.lib._select_authoring_route(root, "flow", workflow="sprint", lane="full", client=h.client)
        kwargs = {"spec_artifact_id": "SPEC-FLOW", "spec_normative_sha256": spec["normative_sha256"]}
        with self.assertRaisesRegex(RuntimeError, "AUTHORITY_UNVERIFIED"):
            self.lib._preflight_plan_authoring(selected, h.client, **kwargs)
        target = self.lib._preflight_plan_authoring(selected, h.client, draft_for_pair=True, **kwargs)
        self.assertFalse(target.exists())
        selected["workflow"] = "feature"
        with self.assertRaisesRegex(RuntimeError, "INVALID_ROUTE"):
            self.lib._preflight_plan_authoring(selected, h.client, draft_for_pair=True, **kwargs)

    def test_hook_routes_pair_reply_from_another_working_directory(self):
        armed = self.arm()
        other = self.root.parent / "other"
        other.mkdir()
        with mock.patch.object(self.approval._artifactlib, "ArtifactClient", return_value=self.h.client):
            text = self.approval.consume_from_hook(root=other, plugin_root=self.root, prompt=armed["reply"], host="codex", session_id="fixture-route")
        self.assertIn("workflow approval recorded", text)
        self.assertTrue(all(v["authority"]["authority_verified"] for v in self.identities()))

    def test_padded_short_sprint_reply_passes_the_real_engine(self):
        armed = self.arm()
        self.assertEqual(armed["short_reply"], f"approve-sprint delegate {armed['code']}")
        other = self.root.parent / "other-short"
        other.mkdir()
        with mock.patch.object(self.approval._artifactlib, "ArtifactClient", return_value=self.h.client):
            wrong = self.approval.consume_from_hook(
                root=other, plugin_root=self.root, host="codex", session_id="fixture-short",
                prompt=f"approve-sprint approve-only {armed['code']}")
            text = self.approval.consume_from_hook(
                root=other, plugin_root=self.root, host="codex", session_id="fixture-short",
                prompt=f"  Approve-Sprint Delegate {armed['code'].lower()}.")
        self.assertIn("delegate", wrong)
        self.assertIn("workflow approval recorded", text)
        self.assertTrue(all(v["authority"]["authority_verified"] for v in self.identities()))
        sources = list((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        self.assertTrue(sources and all(json.loads(p.read_text())["source_text"] == armed["reply"] for p in sources))

    def test_malformed_pair_marker_does_not_route_to_legacy_approval(self):
        self.arm()
        p = self.root / self.approval.PENDING
        pending = json.loads(p.read_text())
        pending["pair"]["delegate_methods"] = "true"
        p.write_text(json.dumps(pending))
        with self.assertRaisesRegex(RuntimeError, "INVALID_PENDING_APPROVAL"):
            self.approval.consume_user_approval(self.root, self.h.client, "yes", host="codex", session_id="fixture")


    def test_changed_spec_after_observation_retires_only_uncommitted_submission(self):
        armed = self.arm()
        original = self.h.client.call
        def fail(operation, request=None, **kwargs):
            if operation == "sprint-approve":
                raise self.lib.ArtifactError("EXECUTION_FAILED", "Synthetic interruption before mutation")
            return original(operation, request, **kwargs)
        with mock.patch.object(self.h.client, "call", side_effect=fail):
            with self.assertRaises(self.lib.ArtifactError):
                self.consume(armed["reply"])
        self.h.mutate("apply", "SPEC-FLOW", changes=[{"op": "header.update", "fields": {"summary": "A real updated requirement."}}])
        result = self.pair.resume(self.root, self.h.client, "PLAN-FLOW")
        self.assertFalse(result["approved"])
        self.assertTrue(result["reapproval_required"])
        self.assertEqual(result["diagnostic"], "REVISION_CONFLICT")
        self.assertFalse((self.root / self.approval.PENDING).exists())
        self.assertEqual(len(list((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))), 2)

    def test_active_task_method_change_refuses_without_mutation(self):
        result = self.consume(self.arm()["reply"])
        self.h.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=self.h.context_ticket("T-001"))
        before = self.identities()
        with self.assertRaisesRegex(RuntimeError, "ACTIVE_WORK"):
            self.h.mutate("smarts-apply", "PLAN-FLOW", grant_receipt=result["grant_receipt"], decision=self.decision())
        self.assertEqual(self.identities(), before)

    def test_private_smarts_request_path_executes_the_native_producer(self):
        result = self.consume(self.arm()["reply"])
        current = self.h.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        request = {"artifact_id": "PLAN-FLOW", "operation_id": "fixture-private-smarts-request",
                   "expected": {key: current[key] for key in ("revision", "model_sha256")},
                   "grant_receipt": result["grant_receipt"], "decision": self.decision()}
        path = self.root.parent / "decision-request.json"
        path.write_text(json.dumps(request))
        self.assertEqual(self.pair.apply_decision(self.h.client, path)["authority_kind"], "smarts_workflow")


    def test_concurrent_observers_complete_once_without_erasing_a_new_request(self):
        from concurrent.futures import ThreadPoolExecutor
        armed = self.arm()
        def observe(reply):
            try:
                return self.consume(reply)
            except self.approval.ApprovalError as exc:
                # The real bounded lock may expire before a slower native
                # transaction completes. Only this explicit non-writing result
                # is allowed; unrelated errors and a second approval still fail.
                if exc.code != "APPROVAL_BUSY":
                    raise
                return {"approved": False, "diagnostic": exc.code}

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(observe, [armed["reply"], armed["reply"]]))
        self.assertEqual(sum(r["approved"] for r in results), 1)
        self.assertEqual(len(list((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))), 2)
        approved = self.identities()
        self.assertTrue(all(v["authority"]["authority_verified"] for v in approved))
        self.assertFalse((self.root / self.approval.PENDING).exists())
        # After the winning observer finishes, retrying the same observed input
        # is non-mutating and does not require a second interactive decision.
        self.assertFalse(self.consume(armed["reply"])["approved"])
        self.assertEqual(self.identities(), approved)

    def test_contended_approval_refuses_without_writing_then_succeeds(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        prerequisite = importlib.import_module("_prerequisitelib")
        armed = self.arm()
        before = self.identities()
        pending_bytes = (self.root / self.approval.PENDING).read_bytes()
        entered, release = Event(), Event()

        def hold_real_lock():
            with prerequisite._pending_transition_lock(self.root, "sprint-pair-approval"):
                entered.set()
                if not release.wait(30):
                    raise AssertionError("test did not release its real approval lock")

        with ThreadPoolExecutor(max_workers=1) as workers:
            holder = workers.submit(hold_real_lock)
            try:
                self.assertTrue(entered.wait(10), "lock holder did not start")
                with self.assertRaises(self.approval.ApprovalError) as refused:
                    self.consume(armed["reply"])
                self.assertEqual(refused.exception.code, "APPROVAL_BUSY")
                self.assertEqual(self.identities(), before)
                self.assertEqual((self.root / self.approval.PENDING).read_bytes(), pending_bytes)
                self.assertFalse((self.root / ".codearbiter/.artifacts/authority-sources").exists())
            finally:
                release.set()
            holder.result(timeout=10)
        self.assertTrue(self.consume(armed["reply"])["approved"])
        self.assertTrue(all(v["authority"]["authority_verified"] for v in self.identities()))
        self.assertEqual(len(list((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))), 2)

    def test_stale_cancel_does_not_remove_a_new_pair_arm(self):
        self.arm()
        original = self.approval._load_pending(self.root)
        self.assertTrue(self.approval.cancel_user_approval(self.root, "PLAN-FLOW")["cancelled"])
        new = self.pair.arm(self.root, self.h.client, "SPEC-FLOW", "PLAN-FLOW", token="different-fixture-nonce")
        with self.assertRaisesRegex(RuntimeError, "PENDING_APPROVAL_MISMATCH"):
            self.pair.cancel(self.root, original)
        self.assertFalse(self.consume("approve-sprint SPEC-FLOW PLAN-FLOW delegate-methods synthetic-pair-token")["matched"])
        self.assertTrue(self.consume(new["reply"])["approved"])


if __name__ == "__main__":
    unittest.main()
