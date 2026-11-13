#!/usr/bin/env python3
"""Real installed helper/native work journeys in disposable host fixtures."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


class InstalledRecoveryFixture:
    @classmethod
    def isolate_environment(cls):
        # Establish the home and a credential-free environment before importing
        # any installation/native/auth-aware owner, including fixture helpers.
        owner = tempfile.TemporaryDirectory(prefix="ca-recovery-import-home-")
        cls.addClassCleanup(owner.cleanup)
        safe = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH",
                                                "ARTIFACT_TEST_INSTALLATION") if key in os.environ}
        safe.update(HOME=owner.name, USERPROFILE=owner.name, PYTHONDONTWRITEBYTECODE="1")
        patch = mock.patch.dict(os.environ, safe, clear=True)
        patch.start()
        cls.addClassCleanup(patch.stop)

    @classmethod
    def setUpClass(cls):
        cls.isolate_environment()
        from test_artifact_authoring import build_installation
        cls.native_owner, cls.native = build_installation()
        cls.host_owner = tempfile.TemporaryDirectory(prefix="ca-recovery-installed-hosts-")
        cls.hosts = {}
        for host, directory in (("claude", "ca"), ("codex", "ca-codex"), ("pi", "ca-pi")):
            source = ROOT / "plugins" / directory
            target = Path(cls.host_owner.name).resolve() / directory
            def source_only(directory_path, names):
                ignored = set(shutil.ignore_patterns("node_modules", "__pycache__")(directory_path, names))
                if Path(directory_path) == source / "helpers":
                    ignored.add("artifacts")
                return ignored
            shutil.copytree(source, target, ignore=source_only)
            shutil.copytree(cls.native, target / "helpers/artifacts")
            # A stale generated copy is a real failure, not permission to patch
            # the installation fixture with unreviewed alternate bytes.
            for filename in ("_workflowrecoverylib.py", "workflow-recovery.py"):
                assert (target / "hooks" / filename).read_bytes() == (ROOT / "core/pysrc" / filename).read_bytes(), filename
            cls.hosts[host] = target

    @classmethod
    def tearDownClass(cls):
        cls.host_owner.cleanup()
        if cls.native_owner is not None:
            cls.native_owner.cleanup()

    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="ca-recovery-installed-repo-")
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name).resolve()
        self.home = self.root / "disposable-home"
        self.home.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".codearbiter").mkdir()
        (self.root / ".codearbiter/CONTEXT.md").write_text("---\narbiter: enabled\n---\n<!--INITIALIZED-->\n")
        (self.root / ".codearbiter/open-tasks.md").write_text("# Tasks\n\n## Backlog\n")
        self.source = self.root / "finding.md"
        self.source.write_text("Source of an exact bounded follow-up\n")

    def environment(self, host, *, package=None):
        package = package or self.hosts[host]
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   CODEARBITER_PYTHON_EXECUTABLE=sys.executable,
                   CODEARBITER_GIT_EXECUTABLE=str(Path(shutil.which("git")).resolve()),
                   PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        if host == "claude":
            env["CLAUDE_PLUGIN_ROOT"] = str(package)
        elif host == "codex":
            env["PLUGIN_ROOT"] = str(package)
        return env

    def offer(self, number=0):
        return {"kind": "terminal-harvest", "workflow_run_id": "installed-run", "work_ref": "none",
                "origin": "checkpoint:installed#deferrable-" + str(number),
                "source": {"workflow": "checkpoint:deferrable", "locator": "finding.md",
                           "fingerprint": "sha256:" + hashlib.sha256(self.source.read_bytes()).hexdigest()},
                "candidate": {"kind": "work", "blocking": "nonblocking", "title": "Installed follow-up " + str(number),
                              "description": "A retained source-bound candidate", "provenance": "finding.md"}}

    def cli(self, host, action, request=None, *, oid=None, revision=None, extra=(), package=None):
        package = package or self.hosts[host]
        argv = [sys.executable, "-B", str(package / "hooks/workflow-recovery.py"), action]
        if oid is not None:
            argv += ["--obligation-id", oid]
        if revision is not None:
            argv += ["--expected-revision", str(revision)]
        argv += list(extra)
        result = subprocess.run(argv, cwd=self.root, env=self.environment(host, package=package),
                                input=json.dumps(request) if request is not None else "", text=True,
                                capture_output=True, encoding="utf-8", timeout=30)
        try:
            value = json.loads(result.stdout)
        except ValueError:
            value = None
        return result, value

class InstalledRecoveryTest(InstalledRecoveryFixture, unittest.TestCase):
    def test_all_three_authenticated_helpers_capture_and_observe_same_local_store(self):
        ids = []
        for number, host in enumerate(self.hosts):
            result, registered = self.cli(host, "register", {"candidates": [self.offer(number)]})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(registered["durable"])
            ids.append(registered["items"][0]["obligation_id"])
        for host in self.hosts:
            result, observed = self.cli(host, "scan")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(observed["status"], "complete")
            self.assertEqual([item["obligation_id"] for item in observed["items"]], ids)
            self.assertLessEqual(observed["bytes_read"], 262144)
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text(), "# Tasks\n\n## Backlog\n")

    def test_real_native_work_effect_is_reconciled_after_actual_process_death(self):
        (self.root / ".codearbiter/open-tasks.md").unlink()
        _, registration = self.cli("codex", "register", {"candidates": [self.offer()]})
        self.assertTrue(registration["durable"], registration)
        oid = registration["items"][0]["obligation_id"]
        script = ("import sys,json,os;sys.path.insert(0,sys.argv[1]);import _workflowrecoverylib as r;"
                  "\ndef crash(point):\n if point=='after-target':os._exit(79)\n"
                  "r.dispatch(sys.argv[2],'resume',{'obligation_id':sys.argv[3],'expected_revision':1},fault=crash)\n")
        process = subprocess.run([sys.executable, "-B", "-c", script, str(self.hosts["codex"] / "hooks"), str(self.root), oid],
                                 env=self.environment("codex"), cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 79, process.stderr + process.stdout)
        work = self.root / ".codearbiter/work"
        files = {path.name: path.read_bytes() for path in work.glob("*.html")}
        self.assertEqual(len(files), 1)
        _, record = self.cli("pi", "get", oid=oid)
        self.assertEqual(record["record"]["state"], "claimed")
        result, reconciled = self.cli("pi", "reconcile", oid=oid, revision=record["record"]["record_revision"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(reconciled["status"], "settled", reconciled)
        self.assertEqual(reconciled["record"]["effect"]["owner"], "native-work")
        self.assertEqual(files, {path.name: path.read_bytes() for path in work.glob("*.html")})
        self.assertFalse((self.root / ".codearbiter/open-tasks.md").exists())

    def test_unknown_helper_foreign_manifest_and_arbitrary_storage_argument_refuse(self):
        foreign = self.root / "foreign" / "ca"
        shutil.copytree(self.hosts["claude"], foreign)
        manifest = foreign / ".claude-plugin/plugin.json"
        value = json.loads(manifest.read_text())
        value["name"] = "foreign-package"
        manifest.write_text(json.dumps(value))
        result, observed = self.cli("claude", "register", {"candidates": [self.offer()]}, package=foreign)
        self.assertEqual(observed["reason"], "untrusted-helper", result.stderr + result.stdout)
        self.assertFalse((self.root / ".git/codearbiter/workflow-recovery").exists())
        result, _ = self.cli("claude", "scan", extra=("--storage-root", str(self.root / "not-an-owner")))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "not-an-owner").exists())

    def test_changed_native_project_and_dual_owner_hold_only_affected_obligation(self):
        board = self.root / ".codearbiter/open-tasks.md"
        board.unlink()
        _, initial = self.cli("claude", "register", {"candidates": [self.offer()]})
        oid = initial["items"][0]["obligation_id"]
        _, promoted = self.cli("claude", "resume", oid=oid, revision=1)
        self.assertEqual(promoted["status"], "settled", promoted)
        _, pending = self.cli("codex", "register", {"candidates": [self.offer(1)]})
        other = pending["items"][0]["obligation_id"]
        project = self.root / ".codearbiter/work/project.json"
        original = project.read_bytes()
        changed = json.loads(original)
        changed["project_id"] = "PROJECT-" + "A" * 32
        project.write_text(json.dumps(changed))
        before = {p.name: p.read_bytes() for p in project.parent.glob("*.html")}
        _, held = self.cli("codex", "resume", oid=other, revision=1)
        self.assertEqual(held["reason"], "changed-binding", held)
        self.assertEqual(before, {p.name: p.read_bytes() for p in project.parent.glob("*.html")})
        project.write_bytes(original)
        board.write_text("# Legacy owner\n\n## Backlog\n")
        _, another = self.cli("pi", "register", {"candidates": [self.offer(2)]})
        third = another["items"][0]["obligation_id"]
        _, ambiguous = self.cli("pi", "resume", oid=third, revision=1)
        self.assertEqual(ambiguous["reason"], "owner-ambiguous", ambiguous)
        self.assertEqual(board.read_text(), "# Legacy owner\n\n## Backlog\n")
        self.assertEqual(before, {p.name: p.read_bytes() for p in project.parent.glob("*.html")})

    def test_automatic_scan_child_environment_has_no_provider_credentials(self):
        _, registered = self.cli("pi", "register", {"candidates": [self.offer()]})
        self.assertTrue(registered["durable"])
        script = ("import sys,json;sys.path.insert(0,sys.argv[1]);import _workflowrecoverylib as r;"
                  "real=r.subprocess.run\ndef observe(*args,**kw):\n"
                  " assert 'FARM_API_KEY' not in kw['env']\n assert 'CLAUDE_CODE_OAUTH_TOKEN' not in kw['env']\n"
                  " assert 'PYTHONPATH' not in kw['env']\n return real(*args,**kw)\n"
                  "r.subprocess.run=observe;print(json.dumps(r.automatic_snapshot(sys.argv[2])))\n")
        env = self.environment("pi")
        env["FARM_API_KEY"] = secrets.token_urlsafe(32)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = secrets.token_urlsafe(32)
        process = subprocess.run([sys.executable, "-B", "-c", script, str(self.hosts["pi"] / "hooks"), str(self.root)],
                                 env=env, cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        observed = json.loads(process.stdout)
        self.assertEqual(observed["status"], "complete", observed)
        self.assertEqual(observed["pending"], 1)

    def test_real_stalled_optional_scan_child_is_killed_and_independent_code_continues(self):
        _, registered = self.cli("codex", "register", {"candidates": [self.offer()]})
        self.assertTrue(registered["durable"])
        store = self.root / ".git/codearbiter/workflow-recovery/v1"
        before = {p.relative_to(store).as_posix(): p.read_bytes() for p in store.rglob("*") if p.is_file()}
        helper = self.hosts["codex"] / "hooks/workflow-recovery.py"
        original = helper.read_bytes()
        # A source-fixture-only stall injection, restored before any other
        # journey. It is not presented as exact retained-package admission.
        helper.write_bytes(original.replace(b"import argparse", b"import time; time.sleep(5)\nimport argparse", 1))
        try:
            script = ("import sys,json;sys.path.insert(0,sys.argv[1]);import _workflowrecoverylib as r;"
                      "print(json.dumps(r.automatic_snapshot(sys.argv[2])));print('independent-continued')")
            started = time.monotonic()
            process = subprocess.run([sys.executable, "-B", "-c", script, str(helper.parent), str(self.root)],
                                     env=self.environment("codex"), cwd=self.root, text=True, capture_output=True, timeout=8)
            elapsed = time.monotonic() - started
        finally:
            helper.write_bytes(original)
        self.assertEqual(process.returncode, 0, process.stderr)
        lines = process.stdout.splitlines()
        self.assertEqual(json.loads(lines[0])["reason"], "scan-timeout")
        self.assertEqual(lines[1], "independent-continued")
        self.assertGreaterEqual(elapsed, .8)
        self.assertLess(elapsed, 4)
        self.assertEqual(before, {p.relative_to(store).as_posix(): p.read_bytes() for p in store.rglob("*") if p.is_file()})

    def test_old_install_read_preserves_pending_recovery_and_targets(self):
        _, registered = self.cli("claude", "register", {"candidates": [self.offer()]})
        self.assertTrue(registered["durable"])
        store = self.root / ".git/codearbiter/workflow-recovery/v1"
        before = {p.relative_to(store).as_posix(): p.read_bytes() for p in store.rglob("*") if p.is_file()}
        board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", "--format=tar", "97e1ecac795138cacb83a9d5e81c39d4c234867a", "plugins/ca"])
        old = self.root / "old-install"
        old.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as payload:
            for member in payload:
                parts = Path(member.name).parts
                self.assertFalse(member.issym() or member.islnk())
                self.assertNotIn("..", parts)
                self.assertFalse(Path(member.name).is_absolute())
                target = old.joinpath(*parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    self.assertTrue(member.isfile())
                    self.assertLessEqual(member.size, 2 << 20)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload.extractfile(member).read())
        package = old / "plugins/ca"
        process = subprocess.run([sys.executable, "-B", str(package / "hooks/work.py"), "list"],
                                 env=self.environment("claude", package=package), cwd=self.root,
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())
        self.assertEqual(before, {p.relative_to(store).as_posix(): p.read_bytes() for p in store.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
