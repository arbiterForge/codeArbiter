"""Real-Git recovery and refusal obligations for the missing H-22 merge operation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


CORE = Path(__file__).resolve().parents[4] / "core" / "pysrc"
sys.path.insert(0, str(CORE))
import _artifactlib
import _bashguardlib


CLI = CORE / "resolve-context-conflict.py"
TARGET = ".codearbiter/code-map.md"
PROVENANCE = ".codearbiter/.provenance/code-map.json"


class ContextMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q", "-b", "current")
        self.git("config", "user.name", "Context merge fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "merge.conflictStyle", "merge")
        self.write(TARGET, b"# Code map\n\n- ca 2.24.0\n- ca-codex 0.15.4\n- ca-pi 0.16.0\n")
        self.write(PROVENANCE, b'{"schema":1,"doc":"code-map","created":"2026-10-07","interview_derived":false,"entries":[]}\n')
        self.write("untouched.txt", b"keep unrelated bytes\n")
        self.commit("base")
        self.git("branch", "incoming")
        self.write(TARGET, b"# Code map\n\n- ca 2.25.0\n- ca-codex 0.16.0\n- ca-pi 0.17.0\n")
        self.commit("prepared current versions")
        self.head = self.git("rev-parse", "HEAD").stdout.strip().decode()
        self.ours = self.git("cat-file", "blob", "HEAD:" + TARGET).stdout
        self.git("checkout", "-q", "incoming")
        self.write(TARGET, b"# Code map\n\n- ca 2.24.1\n- ca-codex 0.15.5\n- ca-pi 0.16.1\n")
        self.commit("incoming patch versions")
        self.git("checkout", "-q", "current")
        merged = self.git("merge", "--no-commit", "incoming", check=False)
        self.assertEqual(merged.returncode, 1, merged.stderr)
        self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)
        self.assertIn(b"<<<<<<< HEAD", (self.root / TARGET).read_bytes())

    def git(self, *args, check=True):
        return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, *args],
                              cwd=self.root, env=self.env, capture_output=True,
                              shell=False, check=check)

    def write(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def commit(self, message):
        self.git("add", "--", ".")
        self.git("commit", "-qm", message, "--no-gpg-sign")

    def state(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts}

    def invoke(self, *args):
        self.assertTrue(CLI.is_file(),
                        "No shipped context-conflict recovery operation exists; H-22 blocks ordinary HEAD restore")
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              cwd=self.root, env=self.env, capture_output=True, text=True,
                              shell=False)

    def inspect(self):
        result = self.invoke("inspect")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_context_merge_restore_head_legacy_conflict(self):
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        with mock.patch.object(_artifactlib, "context_writer_qualified", return_value=True), \
                mock.patch.object(_bashguardlib, "block", side_effect=lambda code, _message: (_ for _ in ()).throw(RuntimeError(code))):
            for command in ("git restore --source=HEAD --worktree -- " + TARGET,
                            "echo replacement > " + TARGET):
                with self.subTest(command=command), self.assertRaisesRegex(RuntimeError, "H-22"):
                    _bashguardlib._check_h22_state(command, str(self.root))
            _bashguardlib._check_h22_state(f'python "{CLI}" --root "{self.root}" inspect', str(self.root))
        inspected = self.inspect()
        self.assertEqual(inspected["head"], self.head)
        self.assertEqual(inspected["target"], TARGET)
        self.assertEqual(inspected["head_sha256"], hashlib.sha256(self.ours).hexdigest())
        self.assertEqual(self.state(), before)
        result = self.invoke("restore-head", "--expected", inspected["binding"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "restored")
        self.assertEqual(self.state(), {**before, TARGET: self.ours})
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)

    def test_context_merge_refusals_preserve_state(self):
        inspected = self.inspect()
        original = self.state()
        index_path = self.root / ".git/index"
        index = index_path.read_bytes()
        merge = (self.root / ".git/MERGE_HEAD").read_bytes()

        def incoming_native():
            self.git("merge", "--abort")
            self.git("checkout", "-q", "incoming")
            self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n')
            self.commit("incoming native ownership")
            self.git("checkout", "-q", "current")
            self.assertEqual(self.git("merge", "--no-commit", "incoming", check=False).returncode, 1)
            self.write(PROVENANCE, original[PROVENANCE])

        cases = (
            ("stale binding", lambda: None, ["restore-head", "--expected", "0" * 64]),
            ("worktree changed", lambda: self.write(TARGET, original[TARGET] + b"human note\n"), None),
            ("provenance changed", lambda: self.write(PROVENANCE, original[PROVENANCE] + b"\n"), None),
            ("native provenance", lambda: self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n'), None),
            ("uncertain journal", lambda: self.write(".codearbiter/.artifacts/transactions/context-unknown.json", b"{"), None),
            ("missing conflict", lambda: (self.root / ".git/MERGE_HEAD").unlink(), None),
            ("changed merge", lambda: (self.root / ".git/MERGE_HEAD").write_text(self.head + "\n"), None),
            ("changed head", lambda: self.git("update-ref", "HEAD", self.git("rev-parse", "HEAD^").stdout.strip().decode()), None),
            ("changed index", lambda: self.git("add", "--", "untouched.txt"), None),
            ("arbitrary target", lambda: None, ["restore-head", "--expected", inspected["binding"], "--target", "untouched.txt"]),
            ("arbitrary revision", lambda: None, ["restore-head", "--expected", inspected["binding"], "--revision", "incoming"]),
            ("arbitrary content", lambda: None, ["restore-head", "--expected", inspected["binding"], "--content", "replacement"]),
            ("incoming native", incoming_native, None),
        )
        for name, mutate, arguments in cases:
            with self.subTest(case=name):
                if name == "changed index":
                    self.write("untouched.txt", b"staged unrelated change\n")
                mutate()
                before = self.state()
                before_index = index_path.read_bytes()
                if name in {"native provenance", "uncertain journal", "incoming native"}:
                    self.assertNotEqual(self.invoke("inspect").returncode, 0,
                                        "fresh inspection must refuse native or uncertain ownership")
                result = self.invoke(*(arguments or ["restore-head", "--expected", inspected["binding"]]))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.state(), before)
                self.assertEqual(index_path.read_bytes(), before_index)
                for path, raw in original.items():
                    self.write(path, raw)
                journal = self.root / ".codearbiter/.artifacts/transactions/context-unknown.json"
                if journal.exists():
                    journal.unlink()
                index_path.write_bytes(index)
                (self.root / ".git/MERGE_HEAD").write_bytes(merge)
                self.git("update-ref", "HEAD", self.head)


if __name__ == "__main__":
    unittest.main()
