import io
import json
import os
import sys
import tempfile
import time
import unittest

# Ensure hooks/ is on the path for _prunelib and the CLI module itself.
_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

import importlib.util
_SCRIPT = os.path.join(_HOOKS_DIR, "prune-transcript.py")
_spec = importlib.util.spec_from_file_location("prune_transcript", _SCRIPT)
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

import _prunelib as P  # noqa: E402
from _helpers import make_transcript, redirect_home, restore_home  # noqa: E402


def _write_transcript(path, data=None):
    """Write `data` (bytes) to path. Defaults to a minimal valid transcript."""
    if data is None:
        data = make_transcript(n_pairs=2, result_bytes=100)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _write_jsonl(path, lines):
    """Write a list of dicts as JSONL to path."""
    with open(path, "w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    return path


class TestCmdAudit(unittest.TestCase):
    """cmd_audit(path): calls audit() from _prunelib, returns correct structure."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_audit_clean_transcript_returns_0(self):
        path = os.path.join(self.tmp.name, "clean.jsonl")
        _write_transcript(path)
        rc = pt.cmd_audit(path)
        self.assertEqual(rc, 0)

    def test_audit_corrupt_transcript_returns_1(self):
        path = os.path.join(self.tmp.name, "corrupt.jsonl")
        # Write deliberately unparseable JSONL
        with open(path, "wb") as f:
            f.write(b'{"type":"user","uuid":"u1"}\n')
            f.write(b'{BROKEN JSON\n')
        rc = pt.cmd_audit(path)
        self.assertEqual(rc, 1)

    def test_audit_output_contains_ok_or_fail(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        _write_transcript(path)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            pt.cmd_audit(path)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertTrue("OK" in output or "WARN" in output or "FAIL" in output)

    def test_audit_each_line_has_level_prefix(self):
        path = os.path.join(self.tmp.name, "t2.jsonl")
        _write_transcript(path)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            pt.cmd_audit(path)
        finally:
            sys.stdout = old_stdout
        for line in captured.getvalue().splitlines():
            if line.strip():
                # Each output line should start with a level keyword
                self.assertTrue(
                    line.startswith("OK") or line.startswith("WARN") or
                    line.startswith("FAIL"),
                    f"unexpected output line: {line!r}")


class TestCmdReport(unittest.TestCase):
    """cmd_report(path): formats a report from audit results."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, path):
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = pt.cmd_report(path)
        finally:
            sys.stdout = old_stdout
        return captured.getvalue(), rc

    def test_report_returns_0(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        _write_transcript(path)
        _, rc = self._run(path)
        self.assertEqual(rc, 0)

    def test_report_contains_bytes_info(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        _write_transcript(path)
        output, _ = self._run(path)
        self.assertIn("bytes", output)

    def test_report_contains_filename(self):
        path = os.path.join(self.tmp.name, "mysession.jsonl")
        _write_transcript(path)
        output, _ = self._run(path)
        self.assertIn("mysession.jsonl", output)

    def test_report_contains_line_count(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        _write_transcript(path)
        output, _ = self._run(path)
        self.assertIn("lines", output)

    def test_report_contains_token_estimate(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        _write_transcript(path)
        output, _ = self._run(path)
        # est_tokens output uses ≈ or "est" prefix
        self.assertTrue("est" in output.lower() or "token" in output.lower()
                        or "≈" in output)


class TestIsLive(unittest.TestCase):
    """is_live(path): True for recently-modified file, False for old one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recently_touched_file_is_live(self):
        path = os.path.join(self.tmp.name, "live.jsonl")
        open(path, "w").close()
        # File was just created — should be live within a generous threshold.
        self.assertTrue(pt.is_live(path, live_secs=300))

    def test_old_file_is_not_live(self):
        path = os.path.join(self.tmp.name, "old.jsonl")
        open(path, "w").close()
        # Back-date the file to 10 minutes ago.
        old_time = time.time() - 600
        os.utime(path, (old_time, old_time))
        self.assertFalse(pt.is_live(path, live_secs=300))

    def test_nonexistent_file_is_not_live(self):
        path = os.path.join(self.tmp.name, "does_not_exist.jsonl")
        self.assertFalse(pt.is_live(path, live_secs=300))

    def test_threshold_boundary(self):
        path = os.path.join(self.tmp.name, "boundary.jsonl")
        open(path, "w").close()
        # Just over the threshold.
        old_time = time.time() - 61
        os.utime(path, (old_time, old_time))
        self.assertFalse(pt.is_live(path, live_secs=60))
        # Just within the threshold.
        recent_time = time.time() - 30
        os.utime(path, (recent_time, recent_time))
        self.assertTrue(pt.is_live(path, live_secs=60))


class TestResolve(unittest.TestCase):
    """resolve(pattern): resolves a session-id glob to actual transcript paths."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def test_direct_path_returned_as_is(self):
        path = os.path.join(self.tmp.name, "direct.jsonl")
        open(path, "w").close()
        result = pt.resolve(path)
        self.assertEqual(result, path)

    def test_session_id_resolved_under_home(self):
        # Build the ~/.claude/projects/<proj>/<session>.jsonl structure.
        proj_dir = os.path.join(self.tmp.name, ".claude", "projects", "myproj")
        os.makedirs(proj_dir)
        session_file = os.path.join(proj_dir, "abc123.jsonl")
        open(session_file, "w").close()
        result = pt.resolve("abc123")
        self.assertEqual(os.path.normcase(result), os.path.normcase(session_file))

    def test_ambiguous_session_id_exits(self):
        # Two projects have a transcript with the same session id.
        for proj in ("proj1", "proj2"):
            d = os.path.join(self.tmp.name, ".claude", "projects", proj)
            os.makedirs(d)
            open(os.path.join(d, "ambig.jsonl"), "w").close()
        with self.assertRaises(SystemExit):
            pt.resolve("ambig")

    def test_nonexistent_session_id_exits(self):
        with self.assertRaises(SystemExit):
            pt.resolve("session-that-does-not-exist")


class TestArgparseDispatch(unittest.TestCase):
    """CLI: `audit <path>` and `report <path>` dispatch to the right command."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "sess.jsonl")
        _write_transcript(self.path)
        self._home = redirect_home(self.tmp.name)

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _run_main(self, argv):
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        rc = None
        try:
            rc = pt.main(argv)
        except SystemExit as e:
            rc = e.code
        finally:
            sys.stdout = old_stdout
        return captured.getvalue(), rc

    def test_audit_subcommand_dispatches(self):
        output, rc = self._run_main(["audit", self.path])
        # A clean transcript should exit 0 and print level-prefixed lines.
        self.assertEqual(rc, 0)
        self.assertTrue(len(output.strip()) > 0)

    def test_report_subcommand_dispatches(self):
        output, rc = self._run_main(["report", self.path])
        self.assertEqual(rc, 0)
        self.assertIn("bytes", output)

    def test_audit_missing_path_arg_exits(self):
        _, rc = self._run_main(["audit"])
        self.assertNotEqual(rc, 0)

    def test_report_missing_path_arg_exits(self):
        _, rc = self._run_main(["report"])
        self.assertNotEqual(rc, 0)

    def test_dry_run_default_for_direct_path(self):
        """Without --execute, a dry-run reports but does not modify the file."""
        size_before = os.path.getsize(self.path)
        # Use a transcript large enough that prune strategies would act.
        large_path = os.path.join(self.tmp.name, "large.jsonl")
        _write_transcript(large_path,
                          make_transcript(n_pairs=5, result_bytes=20000))
        size_large = os.path.getsize(large_path)
        output, rc = self._run_main([large_path, "--tier", "gentle"])
        # Dry-run: file must not shrink.
        self.assertEqual(os.path.getsize(large_path), size_large)

    def test_execute_on_live_transcript_exits(self):
        """--execute on a file modified < live_secs ago must abort."""
        # The file was just created, so it IS live.
        _, rc = self._run_main([self.path, "--execute",
                                "--tier", "gentle"])
        # Should exit non-zero because file is live.
        self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
