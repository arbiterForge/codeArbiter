"""Tests for boardsync.py — thin board-drift reconcile entrypoint (AC-12).

Mirrors test_standup.py style: sys.path manipulation + plain unittest. boardsync.py
has no hyphen so it imports directly (no importlib.util dance needed).
"""
import contextlib
import datetime
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boardsync  # noqa: E402


class TestReconcileReport(unittest.TestCase):
    """reconcile_report(board_text, log_text, today) -> str — pure, never raises."""

    TODAY = datetime.date(2026, 6, 26)

    _BOARD_IN_PROGRESS = (
        "## In-flight\n"
        "- [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)\n"
        "  - Desc: reject expired/forged tokens at the auth middleware\n"
        "  - Done when: an expired token returns 401; a valid one passes\n"
        "  - Boundaries: auth, secrets\n"
    )

    def test_in_progress_task_appears_as_drifted(self):
        # A [~] task whose id is mentioned in the log text must appear in the DRIFTED
        # section — work merged but board not yet flipped to [x].
        log = "fix: implement poc.auth.0001 — session token validation\n"
        report = boardsync.reconcile_report(self._BOARD_IN_PROGRESS, log, self.TODAY)
        self.assertIn("DRIFTED", report)
        self.assertIn("poc.auth.0001", report)
        self.assertIn("in_progress", report)

    def test_queued_task_appears_as_drifted(self):
        # A [ ] (queued) task whose id is in the log is also drifted (not yet started
        # but work already landed).
        board = (
            "## Backlog\n"
            "- [ ] poc.auth.0002 - Token expiry check\n"
        )
        log = "feat: poc.auth.0002 expiry enforcement merged\n"
        report = boardsync.reconcile_report(board, log, self.TODAY)
        self.assertIn("DRIFTED", report)
        self.assertIn("poc.auth.0002", report)
        self.assertIn("queued", report)

    def test_done_task_produces_no_drift(self):
        # A [x] task referenced in the log is already closed — no drift at all.
        board = (
            "## Done\n"
            "- [x] poc.auth.0001 - Validate session tokens  (done 2026-06-20)\n"
        )
        log = "fix: poc.auth.0001 merged\n"
        report = boardsync.reconcile_report(board, log, self.TODAY)
        self.assertNotIn("DRIFTED", report)
        self.assertIn("no drift", report)

    def test_no_ids_in_log_produces_no_drift(self):
        # A log with no task-id tokens → merged_ids=[] → nothing to check → no drift.
        report = boardsync.reconcile_report(
            self._BOARD_IN_PROGRESS, "fix: generic typo correction\n", self.TODAY
        )
        self.assertNotIn("DRIFTED", report)
        self.assertIn("no drift", report)

    def test_unknown_id_listed_not_drifted(self):
        # An id that is in the log but absent from the board → reported as UNKNOWN
        # (informational) and NOT listed under DRIFTED.
        board = "## In-flight\n- [~] poc.ui.0001 - UI task  (started 2026-06-18)\n"
        log = "fix: poc.auth.9999 some id absent from board\n"
        report = boardsync.reconcile_report(board, log, self.TODAY)
        self.assertIn("UNKNOWN", report)
        self.assertIn("poc.auth.9999", report)
        self.assertNotIn("DRIFTED", report)

    def test_report_contains_sweep_date(self):
        # The report header must carry the observation date so the reader knows when
        # the sweep ran.
        report = boardsync.reconcile_report(self._BOARD_IN_PROGRESS, "", self.TODAY)
        self.assertIn(self.TODAY.isoformat(), report)

    def test_empty_board_degrades_no_raise(self):
        report = boardsync.reconcile_report("", "poc.auth.0001 log line\n", self.TODAY)
        self.assertIsInstance(report, str)

    def test_none_board_degrades_no_raise(self):
        report = boardsync.reconcile_report(None, "poc.auth.0001 log\n", self.TODAY)
        self.assertIsInstance(report, str)

    def test_empty_log_produces_no_drift(self):
        # Empty stdin (no merged-commit text) → no ids extracted → no drift.
        report = boardsync.reconcile_report(self._BOARD_IN_PROGRESS, "", self.TODAY)
        self.assertIsInstance(report, str)
        self.assertIn("no drift", report)

    def test_garbled_board_and_log_degrade_no_raise(self):
        # Totally garbled input must not raise — crash-safe invariant mirrors all
        # other _taskboardlib pure functions.
        report = boardsync.reconcile_report(
            "\x00\xff binary garbage \x01\x02",
            "more gar\x00bage here",
            self.TODAY,
        )
        self.assertIsInstance(report, str)


class TestReconcileMain(unittest.TestCase):
    """main(argv) — thin I/O shell; reconcile subcommand is purely advisory."""

    def _run_reconcile(self, board_path, stdin_text):
        """Run boardsync.main with a synthetic stdin and capture stdout.

        contextlib.redirect_stdin is absent from some Python builds; patch
        sys.stdin directly (same semantics, guaranteed stdlib-compatible).
        """
        buf = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(buf):
                boardsync.main(["reconcile", "--board", board_path])
        finally:
            sys.stdin = old_stdin
        return buf.getvalue()

    def test_reconcile_prints_drift_report_to_stdout(self):
        board = (
            "## In-flight\n"
            "- [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(board)
            tmppath = fh.name
        try:
            out = self._run_reconcile(tmppath, "fix: poc.auth.0001 merged\n")
            # The drift report must be printed to stdout and contain the task id.
            self.assertIn("poc.auth.0001", out)
        finally:
            os.unlink(tmppath)

    def test_reconcile_missing_board_degrades_no_raise(self):
        # A non-existent board path must produce a clean report, never a crash.
        # read_board() returns None on OSError; reconcile_report handles None.
        buf = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("poc.auth.0001 fix\n")
        try:
            with contextlib.redirect_stdout(buf):
                boardsync.main(["reconcile", "--board", "/nonexistent/path/open-tasks.md"])
        finally:
            sys.stdin = old_stdin
        out = buf.getvalue()
        self.assertIsInstance(out, str)  # printed something; no exception

    # AC-12 read-only proof --------------------------------------------------------
    def test_board_file_byte_identical_after_reconcile(self):
        """AC-12: the reconcile sweep must write NOTHING to the board file.

        Write a temp open-tasks.md, snapshot its bytes, run main() with synthetic
        stdin, then re-read the bytes. They must be IDENTICAL — reconcile is purely
        advisory and must never open the board for writing.
        """
        board = (
            "## In-flight\n"
            "- [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)\n"
            "  - Desc: reject expired/forged tokens at the auth middleware\n"
            "  - Done when: an expired token returns 401; a valid one passes\n"
            "  - Boundaries: auth, secrets\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(board)
            tmppath = fh.name

        try:
            with open(tmppath, "rb") as fh:
                before_bytes = fh.read()

            stdout_buf = io.StringIO()
            old_stdin = sys.stdin
            sys.stdin = io.StringIO("Merged: poc.auth.0001 session token validation\n")
            try:
                with contextlib.redirect_stdout(stdout_buf):
                    boardsync.main(["reconcile", "--board", tmppath])
            finally:
                sys.stdin = old_stdin

            with open(tmppath, "rb") as fh:
                after_bytes = fh.read()

            self.assertEqual(
                before_bytes,
                after_bytes,
                "reconcile wrote to the board file — AC-12 violation: must be purely advisory",
            )
        finally:
            os.unlink(tmppath)


if __name__ == "__main__":
    unittest.main()
