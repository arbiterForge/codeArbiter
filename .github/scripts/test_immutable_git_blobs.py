"""Finite immutable-reader transport contracts; disposable Git fixtures only."""
from contextlib import nullcontext
from pathlib import Path
import importlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import major_readiness as owner
import _immutable_git_blobs as transport

class ImmutableBlobReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ca-immutable-git-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Disposable reader fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.expected = {"data/file%d.txt" % n: b"exact\x00bytes\n" + bytes([n]) for n in range(12)}
        for name, value in self.expected.items():
            p = self.repo / name
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(value)
        self.git("add", ".")
        self.git("commit", "-qm", "Reader fixture")
        self.source = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.run(["git", "--no-replace-objects", "--no-lazy-fetch", *args], cwd=self.repo,
                              capture_output=True, check=True).stdout

    def test_transaction_reads_exact_bytes_with_one_git_process(self):
        calls = []
        real_start = owner.start
        def counted(*a, **kw):
            calls.append(a[0])
            return real_start(*a, **kw)
        with mock.patch.object(owner, "start", counted):
            try:
                transport = importlib.import_module("_immutable_git_blobs")
            except ModuleNotFoundError:
                transport = None
            patch = mock.patch.object(transport, "start", counted) if transport else nullcontext()
            transaction = getattr(owner, "blob_transaction", lambda repo: nullcontext())
            with patch, transaction(self.repo):
                for name, value in self.expected.items():
                    self.assertEqual(owner.blob(self.repo, self.source, name), value)
                self.assertEqual(owner.blob(self.repo, self.source, "data/file0.txt"), self.expected["data/file0.txt"])
        self.assertEqual(len(calls), 1, "immutable transaction must use one Git child, not per-blob process starts")

    def test_invalid_source_and_literal_path_reject_before_spawn(self):
        bad = [(source, "data/file0.txt") for source in ("HEAD", "a" * 39, "0" * 40, "a" * 40 + "\nHEAD")]
        bad += [(self.source, path) for path in ("", ".", "../x", "/x", "data//x", "data/./x",
                                                 "x:y", "x\\y", "x\ny", "x\ry", "x\0y", "x" * 4097)]
        with mock.patch.object(transport, "start") as spawn, owner.blob_transaction(self.repo):
            for source, path in bad:
                with self.subTest(source=source, path=path), self.assertRaises(owner.ReadinessError):
                    owner.blob(self.repo, source, path)
        spawn.assert_not_called()

    def test_missing_is_not_cached_or_absence_and_does_not_poison_other_reads(self):
        with transport.transaction(self.repo) as reader:
            for _ in range(2):
                with self.assertRaisesRegex(transport.BlobReadError, "unavailable"):
                    reader.read(self.source, "missing.txt")
            self.assertNotIn((self.source, "missing.txt"), reader.cache)
            self.assertEqual(reader.queries, 2)
            self.assertEqual(reader.read(self.source, "data/file0.txt"), self.expected["data/file0.txt"])
        self.assertEqual(reader.cache, {})
        self.assertFalse(reader.worker.is_alive())
        self.assertEqual(reader.process.returncode, 0)

    def test_no_replace_objects_and_repository_selectors_cannot_redirect(self):
        original = self.git("rev-parse", self.source + ":data/file0.txt").decode().strip()
        replacement = self.repo / "replacement.txt"
        replacement.write_bytes(b"forged replacement")
        other = self.git("hash-object", "-w", str(replacement)).decode().strip()
        self.git("replace", original, other)
        env = {"GIT_DIR": str(self.repo / "wrong.git"), "GIT_WORK_TREE": str(self.repo / "wrong"),
               "GIT_OBJECT_DIRECTORY": str(self.repo / "wrong-objects"), "GIT_REPLACE_REF_BASE": "refs/evil/"}
        with mock.patch.dict(os.environ, env), mock.patch.object(transport, "start", wraps=owner.start) as spawn:
            self.assertEqual(owner.blob(self.repo, self.source, "data/file0.txt"), self.expected["data/file0.txt"])
        argv = spawn.call_args.args[0]
        child_env = spawn.call_args.kwargs["env"]
        self.assertIn("--no-replace-objects", argv)
        self.assertIn("--no-lazy-fetch", argv)
        self.assertEqual(argv[argv.index("-C") + 1], str(self.repo.resolve()))
        for key in env:
            self.assertNotIn(key, child_env)
        self.assertEqual(child_env["GIT_NO_LAZY_FETCH"], "1")

    def test_cache_is_transaction_repo_and_source_local(self):
        path = "data/file0.txt"
        before = self.expected[path]
        (self.repo / path).write_bytes(b"new committed bytes")
        self.git("add", path)
        self.git("commit", "-qm", "Different immutable source")
        after = self.git("rev-parse", "HEAD").decode().strip()
        with mock.patch.object(transport, "start", wraps=owner.start) as spawn:
            with transport.transaction(self.repo) as first:
                self.assertEqual(owner.blob(self.repo, self.source, path), before)
                self.assertEqual(owner.blob(self.repo, after, path), b"new committed bytes")
                with transport.transaction(self.repo.parent) as other:
                    self.assertIsNot(first, other)
                    self.assertEqual(other.cache, {})
                self.assertIs(transport._active.get(), first)
            self.assertEqual(first.cache, {})
            with transport.transaction(self.repo) as second:
                self.assertIsNot(first, second)
                self.assertEqual(second.cache, {})
                self.assertEqual(owner.blob(self.repo, self.source, path), before)
        self.assertEqual(spawn.call_count, 2)
        self.assertIsNone(transport._active.get())

    def _fake_spawn(self, body):
        processes = []
        def spawn(argv, **kwargs):
            child = owner.start([sys.executable, "-B", "-u", "-c", body], **kwargs)
            processes.append(child)
            return child
        return mock.patch.object(transport, "start", spawn), processes

    def test_corrupt_headers_types_payloads_framing_and_bounds_kill_transaction(self):
        responses = [b"bad\n", b"a" * 40 + b" tree 1\nx\n", b"a" * 40 + b" blob 3\nab",
                     b"a" * 40 + b" blob 1\nx!", b"a" * 40 + b" blob 16777217\n", b"x" * 4352]
        for response in responses:
            with self.subTest(response=response[:90]):
                seam, children = self._fake_spawn("import sys;sys.stdin.buffer.readline();sys.stdout.buffer.write(" + repr(response) + ");sys.stdout.buffer.flush()")
                with seam, transport.transaction(self.repo) as reader:
                    with self.assertRaises(transport.BlobReadError):
                        reader.read(self.source, "data/file0.txt")
                    self.assertTrue(reader.closed)
                    self.assertEqual(reader.cache, {})
                    with self.assertRaisesRegex(transport.BlobReadError, "closed"):
                        transport.read(self.repo, self.source, "data/file1.txt")
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
                self.assertFalse(reader.worker.is_alive())

    def test_timeout_has_bounded_cleanup_and_dead_transaction(self):
        seam, children = self._fake_spawn("import sys,time;sys.stdin.buffer.readline();time.sleep(30)")
        started = time.monotonic()
        with seam, mock.patch.object(transport, "QUERY_SECONDS", 0.1), transport.transaction(self.repo) as reader:
            with self.assertRaisesRegex(transport.BlobReadError, "timed out; containment="):
                reader.read(self.source, "data/file0.txt")
            self.assertTrue(reader.closed)
            self.assertEqual(reader.cache, {})
        self.assertLess(time.monotonic() - started, 20)
        self.assertIsNotNone(children[0].poll())
        self.assertFalse(reader.worker.is_alive())

    def test_query_total_and_transaction_deadline_bounds(self):
        with mock.patch.object(transport, "MAX_QUERIES", 1), transport.transaction(self.repo) as reader:
            self.assertEqual(reader.read(self.source, "data/file0.txt"), self.expected["data/file0.txt"])
            with self.assertRaisesRegex(transport.BlobReadError, "query bound"):
                reader.read(self.source, "data/file1.txt")
        with mock.patch.object(transport, "MAX_TOTAL", 1), transport.transaction(self.repo) as reader:
            with self.assertRaisesRegex(transport.BlobReadError, "byte bound"):
                reader.read(self.source, "data/file0.txt")
        with transport.transaction(self.repo) as reader:
            reader.deadline = time.monotonic() - 1
            with self.assertRaisesRegex(transport.BlobReadError, "deadline"):
                reader.read(self.source, "data/file0.txt")

    def test_trailing_stdout_and_failed_final_exit_refuse(self):
        for tail in ("sys.stdout.buffer.write(b'EXTRA');sys.stdout.buffer.flush()", "sys.exit(3)"):
            response = b"a" * 40 + b" blob 1\nx\n"
            body = "import sys;sys.stdin.buffer.readline();sys.stdout.buffer.write(" + repr(response) + ");sys.stdout.buffer.flush();sys.stdin.buffer.read();" + tail
            seam, children = self._fake_spawn(body)
            with self.subTest(tail=tail), seam, self.assertRaises(transport.BlobReadError):
                with transport.transaction(self.repo) as reader:
                    self.assertEqual(reader.read(self.source, "data/file0.txt"), b"x")
            self.assertIsNotNone(children[0].poll())
            self.assertFalse(reader.worker.is_alive())

    def test_owning_validate_keeps_injected_loader_and_its_blob_reads(self):
        import check_state_contracts_integration as integration
        def load(commit, path):
            return owner.blob(self.repo, commit, path)
        def validate(repo, source, injected):
            self.assertIs(injected, load)
            return [injected(source, path) for path in self.expected]
        with mock.patch.object(integration, "_validate", side_effect=validate), mock.patch.object(transport, "start", wraps=owner.start) as spawn:
            self.assertEqual(integration.validate(self.repo, self.source, load), list(self.expected.values()))
        self.assertEqual(spawn.call_count, 1)

    def test_abandoned_response_cannot_block_worker_cleanup(self):
        reader = transport.Reader(self.repo)
        reader.process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), wait=lambda: 0)
        reader.results.put((True, b"abandoned result after caller timeout"))
        reader.requests.put(None)
        worker = threading.Thread(target=reader._io, daemon=True)
        worker.start()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive(), "an unconsumed response must not block EOF cleanup")
        self.assertTrue(reader.process.stdin.closed)
        self.assertTrue(reader.process.stdout.closed)

    def test_primary_exception_cause_and_context_survive_cleanup_failure(self):
        for tail in ("sys.stdout.buffer.write(b'EXTRA');sys.stdout.buffer.flush()", "sys.exit(3)"):
            response = b"a" * 40 + b" blob 1\nx\n"
            body = "import sys;sys.stdin.buffer.readline();sys.stdout.buffer.write(" + repr(response) + ");sys.stdout.buffer.flush();sys.stdin.buffer.read();" + tail
            seam, children = self._fake_spawn(body)
            previous = transport.Reader(self.repo.parent)
            token = transport._active.set(previous)
            primary = TypeError("original validation failure")
            cause = ValueError("original validation cause")
            try:
                with self.subTest(tail=tail), seam:
                    try:
                        with transport.transaction(self.repo) as reader:
                            self.assertIs(transport._active.get(), reader)
                            self.assertEqual(reader.read(self.source, "data/file0.txt"), b"x")
                            raise primary from cause
                    except BaseException as observed:
                        self.assertIs(observed, primary, "cleanup must not replace the validation error")
                        self.assertIs(observed.__cause__, cause)
                        self.assertTrue(any("cleanup" in note for note in observed.__notes__))
                    else:
                        self.fail("primary validation failure was swallowed")
                    self.assertIs(transport._active.get(), previous)
                    self.assertIsNotNone(children[0].poll())
                    self.assertFalse(reader.worker.is_alive())
            finally:
                transport._active.reset(token)

if __name__ == "__main__":
    unittest.main()
