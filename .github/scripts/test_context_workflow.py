#!/usr/bin/env python3
"""Regressions for shared activation parsing and passive pre-session inspection."""

import contextlib
import builtins
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core" / "pysrc"
sys.path.insert(0, str(CORE))

import _activationlib as activation  # noqa: E402
import _arbiterstatelib as status  # noqa: E402
import _artifactlib  # noqa: E402
import _artifactauthoritylib  # noqa: E402
import _bashguardlib  # noqa: E402
import _protectedlib  # noqa: E402
import _protectedstatelib  # noqa: E402
import _contextsnapshotlib as context_snapshot  # noqa: E402
import _provenancelib as provenance  # noqa: E402


def _script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), CORE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


initializer = _script("init-codearbiter.py")
startup = _script("session-start.py")
doctor = _script("doctor.py")


class TestSharedInitializationParser(unittest.TestCase):
    def shortDescription(self):
        return None

    def _assert_readers(self, text, *, enabled, malformed, initialized):
        self.assertEqual(activation.frontmatter_enabled_text(text), (enabled, malformed))
        self.assertEqual(status._arbiter_enabled("unused", ctx_text=text), enabled)
        self.assertEqual(getattr(activation, "initialized_body_text", lambda _text: None)(text),
                         initialized)
        self.assertEqual(getattr(startup, "initialized_body_text", lambda _text: None)(text),
                         initialized)
        with tempfile.TemporaryDirectory() as tmp:
            ctx = Path(tmp) / ".codearbiter" / "CONTEXT.md"
            ctx.parent.mkdir()
            ctx.write_text(text, encoding="utf-8")
            before = ctx.read_bytes()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                initializer.main(["--root", tmp, "--check"])
            self.assertIn("arbiter: " + ("enabled" if enabled else "not enabled"), out.getvalue())
            self.assertIn("initialized body: " + ("yes" if initialized else "no"), out.getvalue())
            self.assertEqual(ctx.read_bytes(), before)
            self.assertEqual(activation.frontmatter_enabled(ctx), (enabled, malformed))
            if enabled:
                commands = [
                    SimpleNamespace(returncode=0, stdout=tmp),
                    SimpleNamespace(returncode=0, stdout="maintainer@example.test"),
                ]
                with (mock.patch.object(doctor, "_run_cmd", side_effect=commands),
                      mock.patch.object(doctor, "get_host") as host,
                      mock.patch.object(doctor, "ok") as ok,
                      mock.patch.object(doctor, "warn") as warn):
                    host.return_value.cmd_ref.return_value = "$ca-create-context"
                    self.assertEqual(doctor.check_repo(), tmp)
                diagnostics = ([call.args[0] for call in ok.call_args_list] +
                               [call.args[0] for call in warn.call_args_list])
                self.assertEqual(any("project is initialized" in line for line in diagnostics),
                                 initialized)
                self.assertEqual(any("no <!--INITIALIZED--> marker" in line
                                     for line in diagnostics), not initialized)
                self.assertEqual(ctx.read_bytes(), before)

    def test_t019_shared_initialization_parser_positive_controls(self):
        """Real standalone markers preserve valid state across every reader."""
        for text in (
            "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n# Project\n",
            "\ufeff---\narbiter: enabled\n---\n```md\n<!--INITIALIZED-->\n```\n\n  <!-- INITIALIZED -->  \n",
        ):
            with self.subTest(text=text):
                self._assert_readers(text, enabled=True, malformed=False, initialized=True)
        self.assertTrue(hasattr(doctor, "initialized_body_text"))

    def test_t019_shared_initialization_parser_negative_controls(self):
        """Examples, comments, malformed headers and stubs remain uninitialized."""
        cases = (
            ("---\narbiter: enabled\n---\n# Stub\n", True, False),
            ("---\narbiter: enabled\n---\n```md\n<!--INITIALIZED-->\n```\n", True, False),
            ("---\narbiter: enabled\n---\n~~~\n<!--INITIALIZED-->\n~~~\n", True, False),
            ("---\narbiter: enabled\n---\n<!-- Explanation:\n<!--INITIALIZED-->\n-->\n", True, False),
            ("---\narbiter: enabled\n---\n<!-- example <!--INITIALIZED--> -->\n", True, False),
            ("---\narbiter: enabled\n<!--INITIALIZED-->\n", False, True),
            ("---\nother: value\n---\narbiter: enabled\n<!--INITIALIZED-->\n", False, False),
            ("---\narbiter: enabled\n---\ntext <!--INITIALIZED--> text\n", True, False),
        )
        for text, enabled, malformed in cases:
            with self.subTest(text=text):
                self._assert_readers(text, enabled=enabled, malformed=malformed,
                                     initialized=False)
        self.assertTrue(hasattr(doctor, "initialized_body_text"))


class TestPassiveBeforeActivation(unittest.TestCase):
    def shortDescription(self):
        return None

    def _inspect(self, root):
        out = io.StringIO()
        real_open = builtins.open

        def read_only_open(*args, **kwargs):
            mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
            self.assertEqual(mode, "r", "passive inspection opened a file for writing")
            return real_open(*args, **kwargs)

        with (contextlib.redirect_stdout(out),
              mock.patch("builtins.open", side_effect=read_only_open),
              mock.patch.object(initializer, "project_root", side_effect=AssertionError("git root")),
              mock.patch.object(initializer._hooklib, "get_host",
                                side_effect=AssertionError("host activation")),
              mock.patch.object(initializer.subprocess, "run",
                                side_effect=AssertionError("command execution")),
              mock.patch.object(initializer.subprocess, "Popen",
                                side_effect=AssertionError("process spawn")),
              mock.patch("socket.create_connection",
                         side_effect=AssertionError("network transport")),
              mock.patch("urllib.request.urlopen",
                         side_effect=AssertionError("network transport")),
              mock.patch.object(startup, "spawn_background_fetch",
                                side_effect=AssertionError("fetch")),
              mock.patch.object(startup, "spawn_background_update_refresh",
                                side_effect=AssertionError("update")),
              mock.patch.object(startup, "heal_statusline_wiring",
                                side_effect=AssertionError("host settings write"))):
            initializer.main(["--root", str(root), "--check", "--passive"])
        return json.loads(out.getvalue())

    def test_t020_passive_before_activation_positive_controls(self):
        """An explicit-root read inventories denied effects and preserves active state."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".codearbiter"
            state.mkdir()
            ctx = state / "CONTEXT.md"
            ctx.write_text("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n",
                           encoding="utf-8")
            before = ctx.read_bytes()
            report = self._inspect(root)
            self.assertEqual(report["profile"], "passive-before-activation")
            self.assertEqual(report["context"], {
                "exists": True, "enabled": True, "initialized": True, "malformed": False})
            self.assertEqual(ctx.read_bytes(), before)
            self.assertEqual(set(report["effects"]), {
                "git_hooks_exclusions", "git_fetch", "update_refresh", "inference_transport"})
            for effect in report["effects"].values():
                self.assertEqual(effect["capability"], "unverified")
                self.assertEqual(effect["authorization"], "not_established")
                self.assertFalse(effect["performed"])
            self.assertEqual({name: effect["activation_behavior"]
                              for name, effect in report["effects"].items()}, {
                "git_hooks_exclusions": "scaffold may write Git-local exclusions and hooks; active startup may refresh hooks",
                "git_fetch": "active startup may spawn detached Git fetch",
                "update_refresh": "active startup may spawn detached update refresh",
                "inference_transport": "host-selected model may receive approved source after authorization",
            })
            self.assertEqual(report["source_reads"], "none")
            self.assertEqual(report["sensitive_path_inventory"], "pending")
            with contextlib.redirect_stdout(io.StringIO()) as active_out:
                initializer.main(["--root", tmp, "--check"])
            self.assertIn("arbiter: enabled", active_out.getvalue())
            self.assertEqual(ctx.read_bytes(), before)
            calls = []
            startup.spawn_background_fetch(tmp, spawner=lambda args, path: calls.append(
                ("fetch", args, path)))
            startup.spawn_background_update_refresh(tmp, spawner=lambda path: calls.append(
                ("update", path)))
            self.assertEqual(calls, [
                ("fetch", ["fetch", "--quiet", "--no-tags"], tmp),
                ("update", tmp),
            ])

    def test_t020_passive_before_activation_negative_controls(self):
        """Unqualified or malformed roots never promote authority or run effects."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self._inspect(root)
            self.assertEqual(report["context"]["exists"], False)
            self.assertFalse(report["context"]["enabled"])
            state = root / ".codearbiter"
            state.mkdir()
            ctx = state / "CONTEXT.md"
            ctx.write_text("---\narbiter: enabled\n<!--INITIALIZED-->\n", encoding="utf-8")
            before = ctx.read_bytes()
            report = self._inspect(root)
            self.assertTrue(report["context"]["malformed"])
            self.assertFalse(report["context"]["enabled"])
            self.assertFalse(report["context"]["initialized"])
            self.assertEqual(ctx.read_bytes(), before)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    initializer.main(["--check", "--passive"])
                with self.assertRaises(SystemExit):
                    initializer.main(["--root", tmp, "--passive"])
            with self.assertRaises(SystemExit):
                initializer.main(["--root", str(root / "missing"), "--check", "--passive"])
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    initializer.main(["--root", tmp, "--check", "--passive", "--stage", "2"])
            self.assertEqual(ctx.read_bytes(), before)
            ctx.write_bytes(b"---\narbiter: enabled\n---\n<!--INITIALIZED-->\n\xff")
            with self.assertRaises(SystemExit):
                self._inspect(root)
            ctx.unlink()
            ctx.mkdir()
            with self.assertRaises(SystemExit):
                self._inspect(root)



class TestContextWriterBridge(unittest.TestCase):
    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        state = self.root / ".codearbiter"
        state.mkdir()
        self.human = state / "tech-stack.md"
        self.human.write_bytes(b"# Human notes\n")
        self.task = state / "open-tasks.md"
        self.task.write_bytes(b"# Existing tasks\n")
        self.preview = {
            "operation_id": "context-bridge-001", "mode": "update",
            "document_id": "tech-stack", "target_path": ".codearbiter/tech-stack.md",
            "typed": {"format": "codearbiter.repository-context/0.1.0",
                      "document_id": "tech-stack", "entries": []},
            "selections": [], "expected_document_sha256": "a" * 64,
            "expected_provenance_sha256": "b" * 64,
            "proposed_provenance": {"format": "fixture"},
        }

    def _request(self, data):
        path = self.root / "request.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_t021_context_writer_bridge_positive_controls(self):
        """Init's closed request reaches existing preview and receipt-only native apply."""
        calls = []

        class FixtureClient:
            def __init__(inner, root, installation):
                calls.append(("client", Path(root), Path(installation)))

            def require_context_workflow(inner):
                calls.append(("qualified",))

            def call(inner, operation, request):
                calls.append((operation, request))
                return {"target_path": ".codearbiter/tech-stack.md", "status": "committed"}

        def arm(root, client, preview):
            calls.append(("arm", Path(root), client, preview))
            return {"reply": "approve-context CONTEXT-TECH-STACK fixture-token"}

        class QualifiedClient(FixtureClient):
            pass

        before = (self.human.read_bytes(), self.task.read_bytes())
        with (mock.patch.object(_artifactlib, "ArtifactClient", QualifiedClient),
              mock.patch("_artifactauthoritylib.arm_context_preview", side_effect=arm)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(self._request({"operation": "preview", "preview": self.preview}))])
            self.assertEqual(json.loads(out.getvalue())["reply"].split()[0], "approve-context")
            self.assertEqual([item[0] for item in calls], ["client", "qualified", "arm"])
            self.assertEqual(calls[-1][3], self.preview)
            calls.clear()
            creation = {**self.preview, "operation_id": "context-bridge-002",
                        "mode": "create", "document_id": "code-map",
                        "target_path": ".codearbiter/code-map.md",
                        "typed": {**self.preview["typed"], "document_id": "code-map"},
                        "expected_document_sha256": None,
                        "expected_provenance_sha256": None}
            with contextlib.redirect_stdout(io.StringIO()):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(self._request({"operation": "preview", "preview": creation}))])
            self.assertEqual([item[0] for item in calls], ["client", "qualified", "arm"])
            self.assertEqual(calls[-1][3], creation)
            self.assertFalse((self.root / ".codearbiter" / "code-map.md").exists())
            calls.clear()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(self._request({"operation": "apply", "receipt":
                                                     ".codearbiter/.artifacts/receipts/" + "f" * 64 + ".json"}))])
            self.assertEqual(json.loads(out.getvalue())["status"], "committed")
            self.assertEqual([item[0] for item in calls], ["client", "qualified", "context-apply"])
            self.assertEqual(calls[-1][1], {"receipt":
                             ".codearbiter/.artifacts/receipts/" + "f" * 64 + ".json"})
            policies = _protectedstatelib.context_writer_protection()
            self.assertEqual(set(policies), {
                ".codearbiter/CONTEXT.md", ".codearbiter/tech-stack.md",
                ".codearbiter/coding-standards.md", ".codearbiter/security-controls.md",
                ".codearbiter/code-map.md"})
            self.assertTrue(all(policy == _protectedstatelib.ProtectedPolicy.HELPER_ONLY
                                for policy in policies.values()))
            self.assertIn("state", _protectedlib.classify_protected(
                str(self.human), str(self.root)))
            prewrite = _script("pre-write.py")
            self.assertIn("state", prewrite.classify_protected(
                str(self.human), str(self.root)))
            def reject(code, _message):
                raise RuntimeError(code)
            with (mock.patch.object(prewrite, "block", side_effect=reject),
                  mock.patch.object(prewrite, "get_host") as host):
                host.return_value.cmd_ref.return_value = "$ca-override"
                for path, content in (
                    (self.human, "# Replaced by direct Write\n"),
                    (self.root / ".codearbiter" / "CONTEXT.md",
                     "---\narbiter: enabled\n---\n# Replaced by direct Write\n"),
                ):
                    with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, "H-22"):
                        prewrite._guard_op(str(self.root), {
                            "kind": "write", "file_path": str(path), "content": content})
            with mock.patch.object(_bashguardlib, "block", side_effect=reject):
                with self.assertRaisesRegex(RuntimeError, "H-22"):
                    _bashguardlib._check_h22_state(
                        "echo changed > .codearbiter/tech-stack.md", str(self.root))
        self.assertEqual((self.human.read_bytes(), self.task.read_bytes()), before)
        self.assertFalse((self.root / ".codearbiter" / "CONTEXT.md").exists())

    def test_t021_context_writer_bridge_negative_controls(self):
        """Unavailable, malformed and caller-authorized requests preserve all state."""
        before = (self.human.read_bytes(), self.task.read_bytes())
        class PendingClient:
            def __init__(inner, root, installation):
                pass

            def require_context_workflow(inner):
                raise _artifactlib.ArtifactError("CONTEXT_WORKFLOW_UNAVAILABLE", "pending")

        with mock.patch.object(_artifactlib, "ArtifactClient", PendingClient), \
             mock.patch("_artifactauthoritylib.arm_context_preview",
                        side_effect=AssertionError("writer reached")):
            with self.assertRaisesRegex(SystemExit, "CONTEXT_WORKFLOW_UNAVAILABLE"):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(self._request({"operation": "preview", "preview": self.preview}))])
        self.assertEqual((self.human.read_bytes(), self.task.read_bytes()), before)
        self.assertFalse((self.root / ".codearbiter" / "CONTEXT.md").exists())
        for data in (
            {"operation": "write", "path": ".codearbiter/tech-stack.md", "content": "takeover"},
            {"operation": "apply", "receipt": "fixture", "approved": True},
            {"operation": "preview", "preview": {**self.preview, "approved": True}},
            {"operation": "preview", "preview": {**self.preview, "document_id": []}},
            {"operation": "preview", "preview": {**self.preview, "mode": []}},
            {"operation": "preview", "preview": {**self.preview,
                                                  "target_path": ".codearbiter/open-tasks.md"}},
        ):
            with self.subTest(data=data), mock.patch.object(
                    _artifactlib, "ArtifactClient", side_effect=AssertionError("client reached")):
                with self.assertRaisesRegex(SystemExit, "INVALID_CONTEXT_REQUEST"):
                    initializer.main(["--root", str(self.root), "--context-request",
                                      str(self._request(data))])
        self.assertEqual((self.human.read_bytes(), self.task.read_bytes()), before)
        self.assertFalse(_artifactlib.context_writer_qualified())
        probe = importlib.util.spec_from_file_location(
            "protected_state_import_probe", CORE / "_protectedstatelib.py")
        module = importlib.util.module_from_spec(probe)
        with mock.patch.object(_artifactlib, "context_writer_qualified",
                               side_effect=AssertionError("import-time package probe")):
            probe.loader.exec_module(module)
        with mock.patch.object(_artifactlib, "context_writer_qualified", return_value=False):
            self.assertIsNone(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root))
            with mock.patch.object(_bashguardlib, "block",
                                   side_effect=AssertionError("unexpected shell block")):
                _bashguardlib._check_h22_state(
                    "echo changed > .codearbiter/tech-stack.md", str(self.root))
            transactions = self.root / ".codearbiter" / ".artifacts" / "transactions"
            transactions.mkdir(parents=True)
            self.assertIsNone(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root))
            journal = {
                "format": "codearbiter.transaction/0.2.0",
                "operation_id": "context-bridge-003", "request_sha256": "d" * 64,
                "state": "committed", "entries": [
                    {"path": ".codearbiter/tech-stack.md",
                     "stage": ".codearbiter/.ca-artifact-context-bridge-003-0.new",
                     "backup": ".codearbiter/.artifacts/history/context-bridge-003-0.before",
                     "before_sha256": "a" * 64,
                     "after_sha256": "b" * 64, "size": 12},
                    {"path": ".codearbiter/.provenance/tech-stack.json",
                     "stage": ".codearbiter/.provenance/.ca-artifact-context-bridge-003-1.new",
                     "backup": ".codearbiter/.artifacts/history/context-bridge-003-1.before",
                     "before_sha256": "c" * 64, "after_sha256": "e" * 64,
                     "size": 12},
                ],
                "result": {"document_id": "tech-stack",
                           "target_path": ".codearbiter/tech-stack.md",
                           "document_sha256": "b" * 64,
                           "provenance_sha256": "e" * 64, "mode": "update"},
            }
            (transactions / "context-bridge-003.json").write_text(
                json.dumps(journal), encoding="utf-8")
            self.assertEqual(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root),
                _protectedstatelib.ProtectedPolicy.HELPER_ONLY)
            self.assertIn("state", _protectedlib.classify_protected(
                str(self.human), str(self.root)))
            def reject_shell(code, _message):
                raise RuntimeError(code)
            with mock.patch.object(_bashguardlib, "block", side_effect=reject_shell):
                with self.assertRaisesRegex(RuntimeError, "H-22"):
                    _bashguardlib._check_h22_state(
                        "echo changed > .codearbiter/tech-stack.md", str(self.root))
            journal["state"] = "rolled_back"
            (transactions / "context-bridge-003.json").write_text(
                json.dumps(journal), encoding="utf-8")
            self.assertIsNone(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root))
            legacy = {key: value for key, value in journal.items() if key != "result"}
            legacy["format"] = "codearbiter.transaction/0.1.0"
            legacy["entries"] = [{
                "path": ".codearbiter/specs/example.html",
                "stage": ".codearbiter/specs/.ca-artifact-context-bridge-003-0.new",
                "backup": ".codearbiter/.artifacts/history/context-bridge-003-0.before",
                "before_sha256": None, "after_sha256": "b" * 64, "size": 12,
            }]
            legacy["state"] = "committed"
            (transactions / "context-bridge-003.json").write_text(
                json.dumps(legacy), encoding="utf-8")
            self.assertIsNone(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root))
            (transactions / "context-bridge-003.json").write_text("{", encoding="utf-8")
            self.assertEqual(_protectedstatelib.lookup_policy(
                ".codearbiter/tech-stack.md", root=self.root),
                _protectedstatelib.ProtectedPolicy.HELPER_ONLY)
            with mock.patch.object(_artifactlib, "context_writer_qualified",
                                   side_effect=AssertionError("unrelated path probed")):
                self.assertIsNone(_protectedstatelib.lookup_policy(
                    "README.md", root=self.root))
                with mock.patch.object(_bashguardlib, "block",
                                       side_effect=AssertionError("unrelated shell block")):
                    _bashguardlib._check_h22_state("echo changed > README.md", str(self.root))


class TestContextFinalization(unittest.TestCase):
    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".codearbiter").mkdir()
        self.preview = {
            "operation_id": "context-final-0001", "mode": "finalize",
            "document_id": "CONTEXT", "target_path": ".codearbiter/CONTEXT.md",
            "expected": {path: "a" * 64 for path in _artifactlib._CONTEXT_FINALIZE_PATHS},
        }

    def _request(self, value):
        path = self.root / "request.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _native(self, name):
        result = subprocess.run(
            ["go", "test", "./internal/contextdocument", "-run", f"^{name}$", "-count=1", "-v"],
            cwd=ROOT / "core" / "artifacts", capture_output=True, text=True, timeout=120,
            check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        passes = re.findall(r"(?m)^--- PASS: " + re.escape(name) + r" \(", result.stdout)
        self.assertEqual(len(passes), 1, result.stdout + result.stderr)
        self.assertNotIn("--- SKIP:", result.stdout)

    def test_t022_context_finalization_positive_controls(self):
        """Exact preview routes through installed authority; native empty-state pair commits."""
        calls = []

        class Client:
            def __init__(inner, root, installation):
                calls.append(("client", Path(root)))

            def require_context_workflow(inner):
                calls.append(("qualified",))

        def arm(root, client, preview):
            calls.append(("arm", preview))
            return {"preview_binding_sha256": "b" * 64}

        with mock.patch.object(_artifactlib, "ArtifactClient", Client), \
             mock.patch("_artifactauthoritylib.arm_context_preview", side_effect=arm):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(self._request({"operation": "preview", "preview": self.preview}))])
            self.assertEqual(json.loads(out.getvalue())["preview_binding_sha256"], "b" * 64)
        self.assertEqual([call[0] for call in calls], ["client", "qualified", "arm"])
        self.assertEqual(calls[-1][1], self.preview)
        prompt = "approve-context CONTEXT-CONTEXT fixture-token"
        binding = "c" * 64
        document = "---\narbiter: enabled\nstage: 1\n---\n<!--INITIALIZED-->\n# Project: Sample\n"
        digest = lambda data: hashlib.sha256(data).hexdigest()
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        subject = {"artifact_id": "CONTEXT-CONTEXT", "record_id": "CONTEXT-CONTEXT",
                   "normative_sha256": binding}
        record = {"preview_binding_sha256": binding}
        context = {
            "format": "codearbiter.evidence-context/0.1.0", "activity": "context_approval",
            "subject": subject, "input_sha256": binding,
            "prompt_sha256": digest(prompt.encode()), "record_sha256": digest(canonical(record)),
            "record": record, "preview": self.preview, "preview_document": document,
            "after_document_sha256": digest(document.encode()),
            "before_document_base64": None, "before_provenance_base64": None,
        }
        raw = canonical(context)
        context_hash = digest(raw)
        rel = Path(".codearbiter/.artifacts/evidence-contexts") / f"{context_hash}.json"
        stored = self.root / rel
        stored.parent.mkdir(parents=True)
        stored.write_bytes(raw)

        class PreviewClient:
            def call(inner, operation, request):
                calls.append((operation, request))
                return {"context_ref": rel.as_posix(), "context_sha256": context_hash,
                        "preview_binding_sha256": binding, "subject": subject,
                        "preview_document": document,
                        "after_document_sha256": context["after_document_sha256"]}

        issued = _artifactauthoritylib._context_preview_context(
            self.root, PreviewClient(), self.preview, prompt)
        self.assertEqual(issued[3], binding)
        self.assertEqual(calls[-1][0], "context-finalize-evidence-context")
        self.assertEqual(calls[-1][1]["expected"], self.preview["expected"])
        self._native("TestContextFinalizationPositiveControls")

    def test_t022_context_finalization_negative_controls(self):
        """Malformed authority input and missing, changed or unapproved outputs block."""
        for preview in (
            {**self.preview, "approved": True},
            {**self.preview, "document_id": "tech-stack"},
            {**self.preview, "expected": {}},
            {**self.preview, "expected": {**self.preview["expected"],
                                          ".codearbiter/open-tasks.md": "bad"}},
        ):
            with self.subTest(preview=preview), mock.patch.object(
                    _artifactlib, "ArtifactClient", side_effect=AssertionError("client reached")):
                with self.assertRaisesRegex(SystemExit, "INVALID_CONTEXT_REQUEST"):
                    initializer.main(["--root", str(self.root), "--context-request",
                                      str(self._request({"operation": "preview", "preview": preview}))])
        self.assertFalse((self.root / ".codearbiter" / "CONTEXT.md").exists())
        self._native("TestContextFinalizationNegativeControls")


class TestBoundedScoutJoin(unittest.TestCase):
    def shortDescription(self):
        return None

    def _run(self, *, mode="full"):
        categories = sorted(("stack", "infrastructure", "architecture",
                             "security", "tests", "data"))
        selected = categories if mode == "full" else ["tests"]
        assignments = [{"assignment_id": "root_" + category,
                        "parent_id": None,
                        "scope": {"paths": (["src/a", "src/b"] if category == "architecture"
                                            else ["src/" + category]),
                                  "categories": [category]}}
                       for category in selected]
        return {"mode": mode, "snapshot_id": "a" * 64,
                "deadline_ms": 1000,
                "budgets": {"time_limit_ms": 1000, "token_limit": 10000,
                            "tool_limit": 100},
                "assignments": assignments}

    def _attempts(self, run):
        return [{"assignment_id": item["assignment_id"],
                 "attempt_id": "try_" + item["assignment_id"]}
                for item in run["assignments"]]

    def _payload(self, run, attempt, *, transport="complete", status="ambiguous"):
        assignment = next(item for item in run["assignments"]
                          if item["assignment_id"] == attempt["assignment_id"])
        outcomes = []
        if transport == "complete":
            outcomes = [{"category": category, "status": status,
                         "confidence": None, "reason": "Evidence remains uncertain",
                         "coverage": {"searched_paths": [], "predicates": [],
                                      "excluded": []},
                         "evidence": [], "findings": []}
                        for category in assignment["scope"]["categories"]]
        return json.dumps({"schema_version": 1,
                           "assignment_id": attempt["assignment_id"],
                           "attempt_id": attempt["attempt_id"],
                           "snapshot_id": run["snapshot_id"],
                           "scope": assignment["scope"],
                           "transport": transport,
                           "diagnostic": None if transport == "complete" else "SCOPE_TOO_LARGE",
                           "outcomes": outcomes})

    def test_t025_bounded_scout_join_positive_controls(self):
        """Full and affected joins preserve complete logical coverage and gaps."""
        import _contextreportlib as reports
        self.assertTrue(hasattr(reports, "admit_scout_attempt"))
        self.assertTrue(hasattr(reports, "join_scout_reports"))

        run = self._run()
        attempts = self._attempts(run)
        for prior, candidate in enumerate(attempts):
            admitted = reports.admit_scout_attempt(run, attempts[:prior], candidate,
                                                    now_ms=10)
            self.assertEqual(admitted, candidate)
        payloads = {item["attempt_id"]: self._payload(run, item)
                    for item in attempts}
        joined = reports.join_scout_reports(run, attempts, payloads, now_ms=20)
        self.assertEqual(joined["coverage"], sorted(
            ("stack", "infrastructure", "architecture", "security", "tests", "data")))
        self.assertTrue(joined["full_coverage"])
        self.assertEqual(joined["attempt_count"], 6)
        self.assertEqual(len(joined["reports"]), 6)
        self.assertEqual(len(joined["gaps"]), 6)

        scoped = self._run(mode="scoped")
        scoped_attempts = self._attempts(scoped)
        scoped_join = reports.join_scout_reports(
            scoped, scoped_attempts,
            {scoped_attempts[0]["attempt_id"]: self._payload(scoped, scoped_attempts[0])},
            now_ms=20)
        self.assertEqual(scoped_join["coverage"], ["tests"])
        self.assertFalse(scoped_join["full_coverage"])
        self.assertEqual(len(scoped_join["reports"]), 1)

        retried = self._attempts(run)
        retried.append({"assignment_id": "root_data", "attempt_id": "retry_data"})
        retry_payloads = dict(payloads)
        data_attempt = next(item for item in retried if item["attempt_id"] ==
                            "try_root_data")
        retry_payloads["try_root_data"] = self._payload(
            run, data_attempt, transport="oversize")
        retry_payloads["retry_data"] = self._payload(run, retried[-1])
        self.assertEqual(reports.join_scout_reports(
            run, retried, retry_payloads, now_ms=20)["attempt_count"], 7)

        architecture = next(item for item in run["assignments"]
                            if item["assignment_id"] == "root_architecture")
        for suffix, path in (("a", "src/a"), ("b", "src/b")):
            run["assignments"].append({"assignment_id": "child_" + suffix,
                                       "parent_id": architecture["assignment_id"],
                                       "scope": {"paths": [path],
                                                 "categories": ["architecture"]}})
        attempts += [{"assignment_id": "child_" + suffix,
                      "attempt_id": "try_child_" + suffix} for suffix in ("a", "b")]
        payloads["try_root_architecture"] = self._payload(
            run, next(item for item in attempts if item["attempt_id"] ==
                      "try_root_architecture"), transport="oversize")
        for item in attempts[-2:]:
            payloads[item["attempt_id"]] = self._payload(run, item)
        joined = reports.join_scout_reports(run, attempts, payloads, now_ms=20)
        self.assertTrue(joined["full_coverage"])
        self.assertEqual(joined["attempt_count"], 8)
        self.assertEqual(len(joined["reports"]), 7)
        self.assertEqual({item["parent_id"] for item in joined["reports"]
                          if item["assignment_id"].startswith("child_")},
                         {"root_architecture"})

        overlap = self._run()
        overlap["assignments"] += [
            {"assignment_id": "child_a", "parent_id": "root_architecture",
             "scope": {"paths": ["src/a"], "categories": ["architecture"]},
             "overlap_reason": "shared entry point"},
            {"assignment_id": "child_b", "parent_id": "root_architecture",
             "scope": {"paths": ["src/a", "src/b"],
                       "categories": ["architecture"]},
             "overlap_reason": "shared entry point"},
        ]
        overlap_attempts = self._attempts(overlap)
        overlap_payloads = {item["attempt_id"]: self._payload(overlap, item)
                            for item in overlap_attempts}
        overlap_payloads["try_root_architecture"] = self._payload(
            overlap, next(item for item in overlap_attempts
                          if item["assignment_id"] == "root_architecture"),
            transport="oversize")
        self.assertTrue(reports.join_scout_reports(
            overlap, overlap_attempts, overlap_payloads, now_ms=20)["full_coverage"])

    def test_t025_bounded_scout_join_negative_controls(self):
        """Missing, conflicting and unbounded runs cannot enter synthesis."""
        import _contextreportlib as reports
        self.assertTrue(hasattr(reports, "admit_scout_attempt"))
        self.assertTrue(hasattr(reports, "join_scout_reports"))

        run = self._run()
        attempts = self._attempts(run)
        payloads = {item["attempt_id"]: self._payload(run, item)
                    for item in attempts}

        def rejects(code, candidate_run=run, candidate_attempts=attempts,
                    candidate_payloads=payloads):
            with self.assertRaises(reports.ReportError) as caught:
                reports.join_scout_reports(candidate_run, candidate_attempts,
                                           candidate_payloads, now_ms=20)
            self.assertEqual(caught.exception.code, code)

        rejects("MISSING_REPORT", candidate_payloads={key: value for key, value
                in payloads.items() if key != "try_root_data"})
        missing_category = self._run()
        missing_category["assignments"] = missing_category["assignments"][:-1]
        rejects("CATEGORY_COVERAGE", candidate_run=missing_category)
        no_budget = self._run()
        del no_budget["budgets"]["tool_limit"]
        rejects("MISSING_FIELD", candidate_run=no_budget)
        wrong_snapshot = dict(payloads)
        stale = json.loads(wrong_snapshot["try_root_data"])
        stale["snapshot_id"] = "b" * 64
        wrong_snapshot["try_root_data"] = json.dumps(stale)
        rejects("BINDING_MISMATCH", candidate_payloads=wrong_snapshot)
        failed = dict(payloads)
        failed["try_root_data"] = self._payload(run, attempts[0], transport="oversize")
        rejects("BINDING_MISMATCH", candidate_payloads=failed)
        # Failed transport cannot be laundered through a complete sibling report.
        failed["try_root_data"] = self._payload(
            run, next(a for a in attempts if a["assignment_id"] == "root_data"),
            transport="oversize")
        rejects("INCOMPLETE_TRANSPORT", candidate_payloads=failed)
        with self.assertRaises(reports.ReportError) as caught:
            reports.admit_scout_attempt(run, attempts,
                {"assignment_id": "root_data", "attempt_id": "retry_data"},
                now_ms=1000)
        self.assertEqual(caught.exception.code, "RUN_DEADLINE")
        with self.assertRaises(reports.ReportError) as caught:
            reports.admit_scout_attempt(run, attempts + [
                {"assignment_id": "root_data", "attempt_id": "retry_data"}],
                {"assignment_id": "root_data", "attempt_id": "third_data"},
                now_ms=20)
        self.assertEqual(caught.exception.code, "RETRY_LIMIT")
        with self.assertRaises(reports.ReportError) as caught:
            reports.admit_scout_attempt(run, attempts * 4,
                {"assignment_id": "root_data", "attempt_id": "more_data"},
                now_ms=20)
        self.assertEqual(caught.exception.code, "ATTEMPT_LIMIT")
        split = self._run()
        split["assignments"].append({"assignment_id": "child_a",
            "parent_id": "root_architecture",
            "scope": {"paths": ["src/a"], "categories": ["architecture"]}})
        rejects("SUBDIVISION_FANOUT", candidate_run=split)
        split["assignments"].append({"assignment_id": "child_b",
            "parent_id": "root_architecture",
            "scope": {"paths": ["src/a", "src/b"],
                      "categories": ["architecture"]}})
        rejects("OVERLAPPING_SCOPE", candidate_run=split)
        for child in split["assignments"][-2:]:
            child["overlap_reason"] = "shared entry point"
        split_attempts = self._attempts(split)
        split_payloads = {item["attempt_id"]: self._payload(split, item)
                          for item in split_attempts}
        split_payloads["try_root_architecture"] = self._payload(
            split, next(a for a in split_attempts if a["assignment_id"] ==
                  "root_architecture"), transport="oversize")
        split_payloads["try_child_a"] = self._payload(
            split, next(a for a in split_attempts if a["assignment_id"] == "child_a"),
            status="not_inspected")
        rejects("CONTRADICTORY_OVERLAP", candidate_run=split,
                candidate_attempts=split_attempts, candidate_payloads=split_payloads)
        for name, value in (("child_a", "entry one"),
                            ("child_b", "entry two")):
            item = next(a for a in split_attempts if a["assignment_id"] == name)
            report = json.loads(self._payload(split, item))
            report["outcomes"][0].update(
                status="observed", reason=None, confidence="high",
                coverage={"searched_paths": ["src/a"],
                          "predicates": ["source"], "excluded": []},
                evidence=[{"id": "e0", "path": "src/a/entry.py",
                           "start_line": 1, "end_line": 1,
                           "digest_method": "sha256-raw", "digest": "b" * 64}],
                findings=[{"id": "f0", "name": "entry_point",
                           "value": value, "evidence_refs": ["e0"]}])
            split_payloads[item["attempt_id"]] = json.dumps(report)
        rejects("CONTRADICTORY_OVERLAP", candidate_run=split,
                candidate_attempts=split_attempts, candidate_payloads=split_payloads)
        split["assignments"][1]["parent_id"] = "child_a"
        rejects("PARENT_REQUIRED", candidate_run=split)
        split = self._run()
        split["assignments"].append({"assignment_id": "child_a",
            "parent_id": "root_architecture",
            "scope": {"paths": ["src/a"], "categories": ["architecture"]}})
        split["assignments"].append({"assignment_id": "child_b",
            "parent_id": "root_architecture",
            "scope": {"paths": ["src/b"], "categories": ["architecture"]}})
        split["assignments"].append({"assignment_id": "grandchild_a",
            "parent_id": "child_a",
            "scope": {"paths": ["src/a"], "categories": ["architecture"]}})
        split["assignments"].append({"assignment_id": "greatgrandchild_a",
            "parent_id": "grandchild_a",
            "scope": {"paths": ["src/a"], "categories": ["architecture"]}})
        split["assignments"].append({"assignment_id": "too_deep",
            "parent_id": "greatgrandchild_a",
            "scope": {"paths": ["src/a"], "categories": ["architecture"]}})
        with self.assertRaises(reports.ReportError) as caught:
            reports.admit_scout_attempt(split, [],
                {"assignment_id": "too_deep", "attempt_id": "try_deep"},
                now_ms=20)
        self.assertEqual(caught.exception.code, "SUBDIVISION_DEPTH")
        oversized = dict(payloads)
        oversized["try_root_data"] = self._payload(run,
            next(a for a in attempts if a["assignment_id"] == "root_data"),
            status="not_inspected")
        joined = reports.join_scout_reports(run, attempts, oversized, now_ms=20)
        self.assertIn("data", joined["gaps"])

        large_payloads = {}
        for item in attempts:
            report = json.loads(self._payload(run, item))
            category = report["scope"]["categories"][0]
            root_path = report["scope"]["paths"][0]
            outcome = report["outcomes"][0]
            outcome.update(status="not_applicable", confidence="medium",
                           coverage={"searched_paths": [root_path],
                                     "predicates": ["source"], "excluded": []},
                           evidence=[{"id": "e" + str(index),
                                      "path": root_path + "/file" + str(index),
                                      "start_line": 1, "end_line": 1,
                                      "digest_method": "sha256-raw", "digest": "b" * 64}
                                     for index in range(64)])
            large_payloads[item["attempt_id"]] = json.dumps(report)
        rejects("JOIN_TOO_LARGE", candidate_payloads=large_payloads)

        data_attempt = next(item for item in attempts
                            if item["assignment_id"] == "root_data")
        bounded_report = json.loads(self._payload(run, data_attempt))
        bounded_report["outcomes"][0].update(
            status="not_applicable", confidence="medium",
            coverage={"searched_paths": ["src/data"],
                      "predicates": ["data"], "excluded": []},
            evidence=[{"id": "e" + str(index),
                       "path": "src/data/" + "x" * 640 + "/e" + str(index),
                       "start_line": 1, "end_line": 1,
                       "digest_method": "sha256-raw", "digest": "b" * 64}
                      for index in range(64)])
        bounded_payload = json.dumps(bounded_report, separators=(",", ":"))
        self.assertGreater(len(bounded_payload.encode("utf-8")), 48 * 1024)
        self.assertLess(len(bounded_payload.encode("utf-8")), 64 * 1024)
        normalized = reports.decode_report(bounded_payload, expected={
            "assignment_id": data_attempt["assignment_id"],
            "attempt_id": data_attempt["attempt_id"],
            "snapshot_id": run["snapshot_id"],
            "scope": bounded_report["scope"]})
        self.assertGreater(len(json.dumps(normalized, ensure_ascii=False,
                            sort_keys=True, separators=(",", ":")).encode("utf-8")),
                           48 * 1024)
        self.assertEqual(normalized["transport"], "complete")
        bounded_payloads = dict(payloads)
        bounded_payloads[data_attempt["attempt_id"]] = bounded_payload
        rejects("JOIN_TOO_LARGE", candidate_payloads=bounded_payloads)
        with self.assertRaises(reports.ReportError) as caught:
            reports.decode_report(bounded_payload + " " * (64 * 1024),
                expected={"assignment_id": data_attempt["assignment_id"],
                          "attempt_id": data_attempt["attempt_id"],
                          "snapshot_id": run["snapshot_id"],
                          "scope": bounded_report["scope"]})
        self.assertEqual(caught.exception.code, "REPORT_TOO_LARGE")

        def report_with_evidence(counts):
            candidate = json.loads(self._payload(run, data_attempt))
            candidate["scope"]["categories"] = sorted(counts)
            candidate["outcomes"] = []
            for category, count in counts.items():
                outcome = json.loads(self._payload(run, data_attempt))["outcomes"][0]
                outcome.update(category=category, status="not_applicable",
                               confidence="medium",
                               coverage={"searched_paths": ["src/data"],
                                         "predicates": ["data"], "excluded": []},
                               evidence=[{"id": "e" + str(index),
                                          "path": "src/data/" + category + "/e" + str(index),
                                          "start_line": 1, "end_line": 1,
                                          "digest_method": "sha256-raw", "digest": "b" * 64}
                                         for index in range(count)])
                candidate["outcomes"].append(outcome)
            expected = {key: candidate[key] for key in
                        ("assignment_id", "attempt_id", "snapshot_id", "scope")}
            raw = json.dumps(candidate, separators=(",", ":"))
            self.assertLess(len(raw.encode("utf-8")), 64 * 1024)
            return raw, expected

        single_raw, single_binding = report_with_evidence({"data": 65})
        self.assertEqual(len(reports.decode_report(single_raw, expected=single_binding)
                             ["outcomes"][0]["evidence"]), 65)
        distributed_raw, distributed_binding = report_with_evidence(
            {"data": 64, "tests": 64})
        distributed = reports.decode_report(distributed_raw,
                                            expected=distributed_binding)
        self.assertEqual(sum(len(item["evidence"]) for item in distributed["outcomes"]),
                         128)
        over_raw, over_binding = report_with_evidence({"data": 65, "tests": 64})
        with self.assertRaises(reports.ReportError) as caught:
            reports.decode_report(over_raw, expected=over_binding)
        self.assertEqual(caught.exception.code, "REPORT_EVIDENCE_LIMIT")

        record = {"id": "CON-1", "kind": "existing_applicable",
                  "source_ref": "AGENTS.md#test-convention", "scope": ".",
                  "statement": "Use the local test convention.",
                  "evidence_refs": ["e" + str(index) for index in range(64)]}
        self.assertEqual(len(reports.validate_constraint_reference(
            record, evidence_ids=set(record["evidence_refs"]))["evidence_refs"]), 64)
        record["evidence_refs"].append("e64")
        with self.assertRaises(reports.ReportError) as caught:
            reports.validate_constraint_reference(
                record, evidence_ids=set(record["evidence_refs"]))
        self.assertEqual(caught.exception.code, "ITEM_LIMIT")


class TestContextSynthesis(unittest.TestCase):
    """Source contracts for T-026; live scout and model behavior needs separate proof."""

    def shortDescription(self):
        return None

    def _sections(self):
        skill = (ROOT / "core" / "surface" / "skills" /
                 "context-creation" / "SKILL.md").read_text(encoding="utf-8")
        scout = (ROOT / "core" / "surface" / "agents" /
                 "scout.md").read_text(encoding="utf-8")
        phase3 = skill.split("## Phase 3 — Synthesis", 1)[1].split(
            "## Phase 4 — Gap interview", 1)[0]
        phase4 = skill.split("## Phase 4 — Gap interview", 1)[1].split(
            "## Phase 5 — Project-state write", 1)[0]
        return phase3, phase4, scout

    def test_t026_context_synthesis_authority_positive_controls(self):
        """Drafts preserve evidence and reach only the relevant decision set."""
        phase3, phase4, scout = self._sections()
        for clause in (
            "observed, inferred, proposed and approved",
            "purpose, owning source and actual consumer",
            "existing effective local instructions",
            "not_applicable", "not_found_in_scope",
            "no database question",
            "source-bound ADR reference",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, phase3)
        for clause in (
            "smallest independent reinspection",
            "both conflicting citations",
            "batch independent user-owned decisions",
            "bounded relevant question set",
            "explicitly defers", "dependent work",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, phase4)
        self.assertIn("scope and predicates", scout)
        self.assertIn("not_applicable", scout)

    def test_t026_context_synthesis_authority_negative_controls(self):
        """No confidence, source label or deferral silently grants authority."""
        phase3, phase4, scout = self._sections()
        for clause in (
            "confidence never grants normative authority",
            "never convert a package script into a passed verification",
            "no blanket security claim from absence",
            "no new task or ADR from an observed pattern",
            "upstream instruction",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, phase3)
        for clause in (
            "unresolved permission", "never treat a deferral as approval",
            "do not re-ask", "no synthesized deferral",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, phase4)
        self.assertIn("never assign approval or policy authority", scout)
        self.assertNotIn("Ask ONE targeted question per item", phase4)
        self.assertNotIn("Write it as fact", phase3)


class TestInitializedRefreshRoutes(unittest.TestCase):
    """T-027: existing routes and real owners distinguish refresh from creation."""

    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / ".codearbiter"
        self.state.mkdir()
        (self.state / "CONTEXT.md").write_text(
            "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"
            "# Project: Fixture\n\nHuman context.\n", encoding="utf-8")
        (self.state / "open-tasks.md").write_bytes(b"# Human tasks\n")
        (self.state / "overrides.log").write_bytes(b"# Audit\nHuman event\n")
        (self.state / "tech-stack.md").write_bytes(b"# Human stack\n")

    def _state(self):
        return {p.relative_to(self.state).as_posix(): p.read_bytes()
                for p in self.state.rglob("*") if p.is_file()}

    def _surface(self, path):
        return (ROOT / "core" / "surface" / path).read_text(encoding="utf-8")

    def _native(self, subcase):
        name = "TestContextMutationAdmission/" + subcase
        result = subprocess.run(
            ["go", "test", "./internal/contextdocument", "-count=1", "-v",
             "-run", "^TestContextMutationAdmission$/^" + subcase + "$"],
            cwd=ROOT / "core" / "artifacts", capture_output=True,
            text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = re.findall(r"(?m)^\s*--- (PASS|FAIL|SKIP): " +
                              re.escape(name) + r" \(", result.stdout)
        self.assertEqual(selected, ["PASS"], result.stdout + result.stderr)

    def test_t027_initialized_refresh_routes_positive_controls(self):
        """Selected refresh uses the bounded writer, retains state and limits coverage."""
        before = self._state()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            initializer.main(["--root", str(self.root), "--check"])
        self.assertIn("initialized body: yes", out.getvalue())
        self.assertEqual(self._state(), before)

        owner = self._surface("skills/context-check/SKILL.md")
        create = self._surface("skills/context-creation/SKILL.md")
        init = self._surface("commands/init.md")
        status_route = self._surface("commands/status.md")
        for text in (owner, create, init, status_route):
            self.assertIn("initialized refresh", text.lower())
        self.assertIn("init-codearbiter.py\" --root", owner)
        self.assertIn("--context-request", owner)
        self.assertIn("join_scout_reports", owner)
        self.assertIn("full_coverage", owner)
        self.assertIn("assess_context_provenance", owner)
        self.assertIn("v2_stale", owner)
        self.assertIn("<!--INITIALIZED-->", owner)
        self.assertIn("receipt", owner)
        self.assertIn("read-only", status_route)
        self._native("approved_field_update_preserves_human_neighbors")

        import _contextreportlib as reports
        fixture = TestBoundedScoutJoin()
        scoped = fixture._run(mode="scoped")
        attempts = fixture._attempts(scoped)
        joined = reports.join_scout_reports(
            scoped, attempts,
            {attempts[0]["attempt_id"]: fixture._payload(scoped, attempts[0])},
            now_ms=20)
        self.assertEqual(joined["coverage"], ["tests"])
        self.assertFalse(joined["full_coverage"])
        self.assertEqual(self._state(), before)

    def test_t027_initialized_refresh_routes_negative_controls(self):
        """Passive requests and invalid writes preserve marker, boards and audit."""
        before = self._state()
        status_route = self._surface("commands/status.md")
        owner = self._surface("skills/context-check/SKILL.md")
        self.assertIn("no-argument snapshot", status_route)
        self.assertIn("Report first", owner)
        self.assertIn("selected", owner)
        self.assertIn("never", owner.lower())
        self.assertIn("selected owned-field metadata refresh", owner)
        self.assertIn("unchanged proposed provenance refuse", owner)
        with self.assertRaisesRegex(SystemExit, "REFUSING"):
            initializer.main(["--root", str(self.root)])
        self.assertEqual(self._state(), before)
        request = self.root / "bad-request.json"
        request.write_text(json.dumps({"operation": "preview", "preview": {
            "operation_id": "refresh-bad", "mode": "update",
            "document_id": "open-tasks", "target_path": ".codearbiter/open-tasks.md"
        }}), encoding="utf-8")
        with mock.patch.object(_artifactlib, "ArtifactClient",
                               side_effect=AssertionError("unauthorized client reached")):
            with self.assertRaisesRegex(SystemExit, "INVALID_CONTEXT_REQUEST"):
                initializer.main(["--root", str(self.root), "--context-request",
                                  str(request)])
        self.assertEqual(self._state(), before)
        self._native("stale_document_and_provenance_pair_do_not_mutate")
        self._native("conflicting_document_provenance_identity_rejected")
        self._native("provenance_only_update_refuses_without_mutation")


class TestPartialOnboardingRecovery(unittest.TestCase):
    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / ".codearbiter"

    def _init(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            initializer.main(["--root", str(self.root)])
        return out.getvalue()

    def _snapshot(self):
        return {p.name: p.read_bytes() for p in self.state.iterdir() if p.is_file()}

    def _native_recovery(self, subcase):
        result = subprocess.run(
            ["go", "test", "./internal/contextdocument", "-count=1", "-v",
             "-run", "^TestContextRecoveryAndPaths/" + subcase + "$"],
            cwd=ROOT / "core" / "artifacts", capture_output=True,
            text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--- PASS: TestContextRecoveryAndPaths/" + subcase,
                      result.stdout)

    def test_t023_partial_onboarding_recovery_positive_controls(self):
        """Every interrupted scaffold stage creates only absent files and keeps prior bytes."""
        self._init()
        original = self._snapshot()
        order = ["CONTEXT.md", *initializer.FILES]
        self.assertGreaterEqual(len(order), 6)
        for prefix in range(1, len(order)):
            with self.subTest(interrupted_after=order[prefix - 1]):
                for name, data in original.items():
                    (self.state / name).write_bytes(data)
                for name in order[prefix:]:
                    (self.state / name).unlink()
                before = self._snapshot()
                self.assertEqual(set(before), set(order[:prefix]))
                output = self._init()
                self.assertIn("RECOVERED", output)
                self.assertEqual(self._snapshot(), original)
                for name, data in before.items():
                    self.assertEqual((self.state / name).read_bytes(), data)
        (self.state / "CONTEXT.md").unlink()
        before = self._snapshot()
        output = self._init()
        self.assertIn("RECOVERED", output)
        self.assertEqual(self._snapshot(), original)
        self.assertEqual({name: data for name, data in self._snapshot().items()
                          if name != "CONTEXT.md"}, before)
        audit = self.state / "overrides.log"
        tasks = self.state / "open-tasks.md"
        audit.write_bytes(audit.read_bytes() + b"# retained event\n")
        tasks.write_bytes(tasks.read_bytes() + b"\n- [ ] poc.ui.0001 - Human task\n")
        preserved = (audit.read_bytes(), tasks.read_bytes())
        (self.state / "open-questions.md").unlink()
        self.assertIn("RECOVERED", self._init())
        self.assertEqual((audit.read_bytes(), tasks.read_bytes()), preserved)
        with self.assertRaisesRegex(SystemExit, "REFUSING"):
            self._init()
        # Exercise an actual failure between exclusive file creations, then
        # resume from the bytes left by that failed call.
        for name in ("open-questions.md", "last-checkpoint"):
            (self.state / name).unlink()
        partial_before = self._snapshot()
        write = initializer._create_scaffold_file
        calls = []
        def interrupt_after_first(path, content, *, newline=None):
            write(path, content, newline=newline)
            calls.append(path)
            if len(calls) == 1:
                raise OSError("injected post-create interruption")
        with mock.patch.object(initializer, "_create_scaffold_file",
                               side_effect=interrupt_after_first):
            with self.assertRaisesRegex(OSError, "injected post-create"):
                self._init()
        self.assertEqual(len(calls), 1)
        for name, data in partial_before.items():
            self.assertEqual((self.state / name).read_bytes(), data)
        self.assertIn("RECOVERED", self._init())
        self.assertEqual((audit.read_bytes(), tasks.read_bytes()), preserved)
        ctx = self.state / "CONTEXT.md"
        ctx.write_bytes(ctx.read_bytes() + b"\n```yaml\nstage: 2\n```\n")
        kept_context = ctx.read_bytes()
        (self.state / "open-questions.md").unlink()
        self.assertIn("RECOVERED", self._init())
        self.assertEqual(ctx.read_bytes(), kept_context)
        # The real native transaction retains an identical replay outcome after
        # a lost response; a different operation payload cannot reuse its ID.
        self._native_recovery("lost_response_replay_and_duplicate_operation_ids")

    def test_t023_partial_onboarding_recovery_negative_controls(self):
        """Initialized, malformed and changed state is preserved without takeover."""
        self._init()
        ctx = self.state / "CONTEXT.md"
        missing = self.state / "open-questions.md"
        missing.unlink()
        for changed in (
            b"human context without activation\n",
            ctx.read_bytes() + b"\n<!--INITIALIZED-->\n",
        ):
            with self.subTest(changed=changed[:30]):
                ctx.write_bytes(changed)
                before = self._snapshot()
                with self.assertRaisesRegex(SystemExit, "REFUSING"):
                    self._init()
                self.assertEqual(self._snapshot(), before)
                self.assertFalse(missing.exists())
        ctx.write_bytes(initializer.CONTEXT.format(
            stage=1, name=self.root.name,
            create_context="/ca:create-context", decompose="/ca:decompose"
        ).encode())
        (self.state / "overrides.log").write_bytes(b"human edit\n")
        before = self._snapshot()
        with self.assertRaisesRegex(SystemExit, "REFUSING"):
            self._init()
        self.assertEqual(self._snapshot(), before)
        self.assertFalse(missing.exists())
        with tempfile.TemporaryDirectory() as stray_root:
            stray = Path(stray_root) / ".codearbiter"
            (stray / ".provenance").mkdir(parents=True)
            (stray / ".provenance" / "tech-stack.json").write_bytes(b"human record\n")
            with self.assertRaisesRegex(SystemExit, "existing state without a scaffold"):
                initializer.main(["--root", stray_root])
            self.assertFalse((stray / "CONTEXT.md").exists())
            self.assertEqual((stray / ".provenance" / "tech-stack.json").read_bytes(),
                             b"human record\n")
        # A pending native write with a later human edit refuses both recovery
        # choices while keeping the journal pending and both current files.
        self._native_recovery("divergent_human_edits_preserve_pending_transaction")


class TestHumanContextPreservation(unittest.TestCase):
    """T-028: unsupported human state remains usable and outside mutation lanes."""

    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.state = self.root / ".codearbiter"
        self.state.mkdir(parents=True)
        self.context = self.state / "CONTEXT.md"
        self.context.write_bytes(
            b"---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"
            b"# Project: Fixture\nHuman context.\n")
        self.stack = self.state / "tech-stack.md"
        self.stack.write_bytes(
            b"# Human stack\r\n## Test\r\ncustom syntax\r\n"
            b"## Test\r\nsecond human section\r\n")
        self.tasks = self.state / "open-tasks.md"
        self.tasks.write_bytes(b"# Open tasks\n- [ ] human.task.0001 - Retain me\n")
        self.audit = self.state / "overrides.log"
        self.audit.write_bytes(b"# codeArbiter override log\nHuman event\n")

    def _state(self):
        return {p.relative_to(self.state).as_posix(): p.read_bytes()
                for p in self.state.rglob("*") if p.is_file()}

    def _native(self, case, subcase):
        name = case + "/" + subcase
        result = subprocess.run(
            ["go", "test", "./internal/contextdocument", "-count=1", "-v",
             "-run", "^" + case + "$/^" + subcase + "$"],
            cwd=ROOT / "core" / "artifacts", capture_output=True,
            text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = re.findall(r"(?m)^\s*--- (PASS|FAIL|SKIP): " +
                              re.escape(name) + r" \(", result.stdout)
        self.assertEqual(selected, ["PASS"], result.stdout + result.stderr)

    def test_t028_human_context_preservation_positive_controls(self):
        """Advisory reads work and owned field updates preserve human neighbors."""
        before = self._state()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            initializer.main(["--root", str(self.root), "--check"])
        self.assertIn("initialized body: yes", out.getvalue())
        self.assertEqual(self._state(), before)
        owner = (ROOT / "core" / "surface" / "skills" /
                 "context-check" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("unsupported human", owner.lower())
        self.assertIn("task-time", owner.lower())
        self.assertIn("actual precedence", owner.lower())
        self._native("TestContextMutationAdmission",
                     "approved_field_update_preserves_human_neighbors")
        self._native("TestContextMarkdownPreservation",
                     "legacy_context_crlf_roundtrip")
        self.assertEqual(self._state(), before)

    def test_t028_human_context_preservation_negative_controls(self):
        """Unsupported or unowned writes and reparse aliases leave bytes intact."""
        before = self._state()
        with self.assertRaisesRegex(SystemExit, "REFUSING"):
            initializer.main(["--root", str(self.root)])
        self.assertEqual(self._state(), before)
        self._native("TestContextMarkdownPreservation",
                     "duplicate_known_headings_rejected")
        self._native("TestContextMarkdownPreservation",
                     "unsupported_and_malformed_unchanged")
        self._native("TestContextMutationAdmission",
                     "unowned_or_unsupported_provenance_is_preserved")
        self._native("TestContextMutationAdmission",
                     "missing_authority_and_hash_only_do_not_admit")
        self.assertEqual(self._state(), before)

        if os.name == "nt":
            with tempfile.TemporaryDirectory() as fixture:
                base = Path(fixture) / "project"
                base.mkdir()
                outside = Path(fixture) / "human-state"
                outside.mkdir()
                sentinel = outside / "human.txt"
                sentinel.write_bytes(b"owned outside the project\n")
                existing = outside / "CONTEXT.md"
                existing.write_bytes(initializer.CONTEXT.format(
                    stage=1, name="Fixture", create_context="/ca:create-context",
                    decompose="/ca:decompose").encode("utf-8"))
                existing_bytes = existing.read_bytes()
                alias = base / ".codearbiter"
                created = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(alias), str(outside)],
                    capture_output=True, text=True, check=False)
                self.assertEqual(created.returncode, 0,
                                 created.stdout + created.stderr)
                try:
                    self.assertTrue(os.lstat(alias).st_file_attributes &
                                    stat.FILE_ATTRIBUTE_REPARSE_POINT)
                    with self.assertRaisesRegex(SystemExit,
                                                "regular project-state directory"):
                        initializer.main(["--root", str(base)])
                    self.assertEqual(sentinel.read_bytes(),
                                     b"owned outside the project\n")
                    self.assertEqual(existing.read_bytes(), existing_bytes)
                    self.assertEqual(set(outside.iterdir()), {sentinel, existing})
                finally:
                    os.rmdir(alias)
        owner = (ROOT / "core" / "surface" / "skills" /
                 "context-check" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("raw Write/Edit", owner)
        self.assertIn("actual owner", owner)


class TestFirstRealContextInput(unittest.TestCase):
    """T-040: an interview-derived stub acquires its first real manifest."""

    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        subprocess.run(["git", "-C", str(self.root), "init", "-q", "-b", "main"],
                       check=True, capture_output=True)
        self.state = self.root / ".codearbiter"
        self.store = self.state / ".provenance"
        self.store.mkdir(parents=True)
        (self.state / "CONTEXT.md").write_bytes(
            b"---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"
            b"# Intended architecture\nA future database package is proposed.\n")
        (self.state / "tech-stack.md").write_bytes(
            b"# Intended stack\nPackage tooling not yet observed.\n")
        (self.state / "open-tasks.md").write_bytes(b"# Human tasks\n")
        (self.state / "overrides.log").write_bytes(b"# Human audit\n")
        provenance.write_stub(self.store / "tech-stack.json", "tech-stack",
                              created="2026-09-27")
        subprocess.run(["git", "-C", str(self.root), "add", "--", ".codearbiter"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.test", "commit", "-qm",
                        "interview context"], check=True, capture_output=True)
        self.snapshot = self._snapshot()

    def _snapshot(self):
        return context_snapshot.context_snapshot(
            self.root, membership=(("manifests", (".",)),),
            target_paths=(".codearbiter/tech-stack.md",),
            allowed_effect_paths=(".codearbiter/.provenance/tech-stack.json",))

    def _state(self):
        return {p.relative_to(self.state).as_posix(): p.read_bytes()
                for p in self.state.rglob("*") if p.is_file()}

    def _assess(self):
        return provenance.assess_context_provenance(
            self.store, ["tech-stack"], self.snapshot)

    def test_t040_first_real_context_input_positive_controls(self):
        """First manifest opens only a bounded stack refresh and preserves intent."""
        before = self._state()
        empty = self._assess()
        self.assertEqual(empty["documents"], {"tech-stack": "legacy_unverified"})
        self.assertEqual(empty.get("first_input"), {})
        self.assertEqual(self._state(), before)
        (self.root / "package.json").write_bytes(b'{"name":"first"}\n')
        self.assertEqual(self._assess()["first_input"],
                         {"tech-stack": {"paths": ["package.json"],
                                         "refresh_docs": ["tech-stack"]}},
                         "a complete prior empty membership detects a real addition")
        self.snapshot = self._snapshot()  # Ordinary new task, after manifest creation.
        acquired = self._assess()
        self.assertEqual(acquired["documents"],
                         {"tech-stack": "first_input_pending"})
        self.assertEqual(acquired["first_input"],
                         {"tech-stack": {"paths": ["package.json"],
                                         "refresh_docs": ["tech-stack"]}})
        self.assertEqual(acquired["coverage"], "incomplete")
        self.assertEqual(acquired["semantic"], "unverified")
        self.assertFalse(acquired["verified_fresh"])
        self.assertEqual(self._assess(), acquired)
        self.assertEqual(self._state(), before)
        owner = (ROOT / "core/surface/skills/decompose/SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("first_input_pending", owner)
        self.assertIn("assess_context_provenance", owner)

    def test_t040_first_real_context_input_negative_controls(self):
        """Unrelated leaves and unsafe snapshots cannot invent package guidance."""
        before = self._state()
        (self.root / "notes.txt").write_bytes(b"unrelated leaf\n")
        self.assertEqual(self._assess().get("first_input"), {})
        self.assertEqual(self._state(), before)
        (self.root / "package.json").write_bytes(b'{"name":"first"}\n')
        self.snapshot = self._snapshot()
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        (other / ".codearbiter/.provenance").mkdir(parents=True)
        (other / ".codearbiter/.provenance/tech-stack.json").write_bytes(
            (self.store / "tech-stack.json").read_bytes())
        sibling = provenance.assess_context_provenance(
            other / ".codearbiter/.provenance", ["tech-stack"], self.snapshot)
        self.assertEqual(sibling["first_input"], {})
        forged = json.loads(json.dumps(self.snapshot))
        forged["source"]["membership"][0]["digest"] = "0" * 64
        invalid = provenance.assess_context_provenance(
            self.store, ["tech-stack"], forged)
        self.assertEqual(invalid["first_input"], {})
        (self.store / "tech-stack.json").write_bytes(b'{"schema":99}\n')
        unsupported = self._assess()
        self.assertEqual(unsupported["first_input"], {})
        self.assertEqual(unsupported["documents"]["tech-stack"], "unsupported")
        self.assertEqual((self.state / "CONTEXT.md").read_bytes(),
                         before["CONTEXT.md"])
        self.assertEqual((self.state / "tech-stack.md").read_bytes(),
                         before["tech-stack.md"])
        self.assertEqual((self.state / "open-tasks.md").read_bytes(),
                         before["open-tasks.md"])
        self.assertEqual((self.state / "overrides.log").read_bytes(),
                         before["overrides.log"])


class TestContextUpgradeAndRollback(unittest.TestCase):
    """T-059: a selective source upgrade leaves canonical and legacy state intact."""

    def shortDescription(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / ".codearbiter"
        self.store = self.state / ".provenance"
        self.store.mkdir(parents=True)
        self.context = self.state / "CONTEXT.md"
        self.context.write_bytes(
            b"---\r\narbiter: enabled\r\nstage: 2\r\n---\r\n"
            b"<!--INITIALIZED-->\r\n# Project: Human fixture\r\n")
        self.stack = self.state / "tech-stack.md"
        self.stack.write_bytes(b"# Stack\r\n## Human notes\r\nKeep these bytes.\r\n")
        self.map = self.state / "code-map.md"
        self.map.write_bytes(b"# Human map\n- `src/` -- current owner\n")
        (self.root / "go.mod").write_bytes(b"module example.test/human\n")
        (self.state / "open-tasks.md").write_bytes(
            b"# Tasks\n- [ ] human.task.0001 - Preserve me\n")
        (self.state / "overrides.log").write_bytes(
            b"# Audit\n2026-09-27 | BY: human | retained\n")
        for doc in ("tech-stack", "code-map"):
            provenance.write_provenance(
                self.store / f"{doc}.json",
                provenance.new_record(doc, created="2026-09-27"))

    def _state_bytes(self):
        return {path.relative_to(self.state).as_posix(): path.read_bytes()
                for path in self.state.rglob("*") if path.is_file()}

    def _v2_stack(self):
        return {
            "schema": 2, "doc": "tech-stack", "created": "2026-09-27",
            "document": {"path": ".codearbiter/tech-stack.md",
                         "digest_method": "sha256-raw",
                         "digest": hashlib.sha256(self.stack.read_bytes()).hexdigest()},
            "fields": [{"id": "FIELD-STACK", "owner_ref": "fixture:adopted-stack",
                        "claims": [{"id": "CLAIM-MODULE",
                                    "semantic_review": {"state": "reviewed",
                                                        "reference": "fixture:review"},
                                    "evidence": [{"kind": "content", "path": "go.mod",
                                                  "digest_method": "sha256-raw",
                                                  "digest": hashlib.sha256(
                                                      (self.root / "go.mod").read_bytes()
                                                  ).hexdigest()}],
                                    "effective_authority_refs": []}]}],
        }

    def _adopt_stack(self):
        path = self.store / "tech-stack.json"
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
        capability = lambda contract, hosts: {
            "contract": contract,
            "producer": {"status": "supported", "contract": contract},
            "consumers": {host: {"status": "supported", "contract": contract}
                          for host in hosts},
        }
        ownership = lambda digest, doc, fields: {
            "status": "accepted", "record_digest": digest,
            "doc": doc, "field_ids": list(fields),
        }
        provenance.write_provenance(
            path, self._v2_stack(), capability_probe=capability,
            ownership_probe=ownership, expected_previous_sha256=previous)
        return path

    def _assess(self):
        record = self._v2_stack()
        snapshot = {
            "source": {"files": {"go.mod": {"digest_method": "sha256-raw",
                                               "digest": record["fields"][0]["claims"][0]
                                               ["evidence"][0]["digest"]}},
                       "membership": []},
            "targets": {".codearbiter/tech-stack.md": {
                "status": "file", "digest_method": "sha256-raw",
                "digest": record["document"]["digest"]}},
        }
        return provenance.assess_context_provenance(
            self.store, ["tech-stack", "code-map"], snapshot,
            snapshot_probe=lambda _: {"source_current": True,
                                      "targets_current": True})

    def _native(self, case, subcase):
        name = case + "/" + subcase
        result = subprocess.run(
            ["go", "test", "./internal/contextdocument", "-count=1", "-v",
             "-run", "^" + case + "$/^" + subcase + "$"],
            cwd=ROOT / "core" / "artifacts", capture_output=True,
            text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = re.findall(r"(?m)^\s*--- (PASS|FAIL|SKIP): " +
                              re.escape(name) + r" \(", result.stdout)
        self.assertEqual(selected, ["PASS"], result.stdout + result.stderr)

    def test_t059_context_upgrade_and_rollback_positive_controls(self):
        """Only selected provenance upgrades; readers retain human Markdown."""
        original = self._state_bytes()
        upgraded = self._adopt_stack()
        self.assertEqual(provenance.read_provenance(upgraded)["schema"], 2)
        self.assertEqual(provenance.read_provenance(
            self.store / "code-map.json")["schema"], 1)
        self.assertEqual(self._assess()["documents"], {
            "tech-stack": "v2_current", "code-map": "legacy_unverified"})
        self.assertEqual(self._assess()["coverage"], "incomplete")
        self.assertFalse(self._assess()["verified_fresh"])
        self.assertEqual(provenance.load_provenance_dir(self.store)["code-map"]
                         ["schema"], 1)
        self.assertIn("incomplete", provenance.startup_context_coverage_line(
            self.root))
        out = io.StringIO()
        with (mock.patch.object(_artifactlib, "context_writer_qualified",
                                return_value=False),
              contextlib.redirect_stdout(out)):
            initializer.main(["--root", str(self.root), "--check"])
        self.assertIn("initialized body: yes", out.getvalue())
        after = self._state_bytes()
        self.assertEqual(set(after), set(original))
        for name, content in original.items():
            if name != ".provenance/tech-stack.json":
                self.assertEqual(after[name], content, name)
        self._native("TestContextRecoveryAndPaths",
                     "interruptions_before_and_after_each_replacement")
        self._native("TestContextMutationAdmission",
                     "approved_field_update_preserves_human_neighbors")

    def test_t059_context_upgrade_and_rollback_negative_controls(self):
        """Downgrade, unsupported neighbors and divergent recovery preserve bytes."""
        upgraded = self._adopt_stack()
        unsupported = self.store / "code-map.json"
        unsupported.write_bytes(b'{"schema":99,"human":"retain exactly"}\n')
        before = self._state_bytes()
        with self.assertRaisesRegex(ValueError, "V2_DOWNGRADE_UNSUPPORTED"):
            provenance.write_provenance(
                upgraded, provenance.new_record("tech-stack", created="2026-09-27"))
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_PREVIOUS_RECORD"):
            provenance.write_provenance(
                unsupported, provenance.new_record("code-map", created="2026-09-27"))
        assessed = self._assess()
        self.assertEqual(assessed["documents"], {
            "tech-stack": "v2_current", "code-map": "unsupported"})
        self.assertEqual(assessed["coverage"], "incomplete")
        self.assertFalse(assessed["verified_fresh"])
        with self.assertRaisesRegex(SystemExit, "REFUSING"):
            initializer.main(["--root", str(self.root)])
        self.assertEqual(self._state_bytes(), before)
        human = self.stack.read_bytes() + b"Later human edit.\r\n"
        self.stack.write_bytes(human)
        stale = self._assess()
        self.assertEqual(stale["documents"]["tech-stack"], "v2_stale")
        self.assertFalse(stale["verified_fresh"])
        self.assertEqual(self.stack.read_bytes(), human)
        self.assertEqual(upgraded.read_bytes(), before[".provenance/tech-stack.json"])
        self._native("TestContextRecoveryAndPaths",
                     "divergent_human_edits_preserve_pending_transaction")
        self._native("TestContextRecoveryAndPaths",
                     "unsupported_journal_blocks_context_write_without_replacement")


if __name__ == "__main__":
    unittest.main()
