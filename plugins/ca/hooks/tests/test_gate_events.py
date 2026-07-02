"""observability-001 (#186): durable gate-events sink for block()/remind()/warn().

AC-1: a repo-local run of a hook that hits block()/remind()/warn() produces a
durable, greppable record in .codearbiter/gate-events.log, outside the live
stderr transcript.

AC-2 (load-bearing): the write path is FAIL-OPEN — a locked/missing/unwritable
gate-events.log (or a project_root() that itself misbehaves) must NEVER change
the caller's exit code and must NEVER raise. block() still exits 2 with its
stderr message intact; remind()/warn() still return normally.

CONFIRM-09: the paired staleness-warn (_hooklib.staleness_warning) is WARN-only
— it never has side effects and never raises, and a stale /dev or /sprint flow
is detected purely from the markers the framework already drops.

Stdlib only. Fail-open is proven via a directory-collision on the log path and
via a patched writer that raises — never by unsetting PATH/env (that changes
an unrelated resolution mechanism, not writability).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _hooklib  # noqa: E402

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")


def _read_log(cad):
    path = os.path.join(cad, "gate-events.log")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


class _GateEventsFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)
        self._env_patch = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        self._tmp.cleanup()


class TestDurableRecordAC1(_GateEventsFixture):
    def test_block_writes_greppable_record_and_still_exits_2(self):
        with self.assertRaises(SystemExit) as cm:
            _hooklib.block("H-01", "example block reason")
        self.assertEqual(cm.exception.code, 2)
        text = _read_log(self.cad)
        self.assertIn("BLOCK", text)
        self.assertIn("[H-01]", text)
        self.assertIn("example block reason", text)
        # ISO-8601 UTC timestamp, bracketed.
        self.assertRegex(text, r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\]")

    def test_remind_writes_record_and_does_not_raise(self):
        _hooklib.remind("H-05", "example reminder")
        text = _read_log(self.cad)
        self.assertIn("REMIND", text)
        self.assertIn("[H-05]", text)
        self.assertIn("example reminder", text)

    def test_warn_writes_record_and_does_not_raise(self):
        _hooklib.warn("example degradation")
        text = _read_log(self.cad)
        self.assertIn("WARN", text)
        self.assertIn("example degradation", text)

    def test_multiple_events_append_rather_than_overwrite(self):
        _hooklib.warn("first")
        _hooklib.remind("TAG", "second")
        text = _read_log(self.cad)
        self.assertIn("first", text)
        self.assertIn("second", text)
        self.assertEqual(len(text.splitlines()), 2)

    def test_record_carries_the_invoking_hook_name(self):
        # "hook/tool if available" — sys.argv[0] is the one signal available
        # at this shared layer without threading a new param through every
        # call site.
        with mock.patch.object(sys, "argv", ["/path/to/pre-bash.py"]):
            _hooklib.warn("hook-attributed line")
        text = _read_log(self.cad)
        self.assertIn("hook=pre-bash.py", text)


class TestRealHookIntegrationAC1(unittest.TestCase):
    """AC-1, end-to-end: a REAL hook (pre-bash.py) run against a real
    throwaway git repo, hitting an actual H-20 block, must leave a durable
    record in that repo's .codearbiter/gate-events.log — outside the live
    transcript (here: outside the subprocess's own stderr)."""

    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        self._git(["init", "-q", "-b", "feat/work"])
        self._git(["config", "user.email", "h@example.com"])
        self._git(["config", "user.name", "harness"])
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8") as f:
            f.write(self.ARBITER)

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.root}
        r = subprocess.run(["git"] + args, cwd=self.root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=60, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
        return r

    def test_h20_block_leaves_durable_record_outside_the_transcript(self):
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "git commit --no-verify -m x"}})
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.root}
        res = subprocess.run([sys.executable, PRE_BASH], cwd=self.root, input=payload,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60, env=env)
        self.assertEqual(res.returncode, 2)
        self.assertIn("H-20", res.stderr)
        log_path = os.path.join(self.root, ".codearbiter", "gate-events.log")
        self.assertTrue(os.path.isfile(log_path), "gate-events.log was not created")
        with open(log_path, encoding="utf-8") as f:
            log = f.read()
        self.assertIn("BLOCK", log)
        self.assertIn("[H-20]", log)
        self.assertIn("hook=pre-bash.py", log)


class TestFailOpenAC2(_GateEventsFixture):
    """AC-2: the sink must NEVER turn a fail-open hook fail-closed, and must
    NEVER suppress a BLOCK. Failure is injected by making the log path
    unwritable (a directory collision) or by making the writer itself raise
    — never by unsetting PATH/env vars."""

    def test_block_still_exits_2_when_log_path_is_a_directory(self):
        # gate-events.log exists as a DIRECTORY, not a file -> open(path, "a")
        # raises (IsADirectoryError / PermissionError depending on platform).
        os.makedirs(os.path.join(self.cad, "gate-events.log"))
        with self.assertRaises(SystemExit) as cm:
            _hooklib.block("H-02", "must still block")
        self.assertEqual(cm.exception.code, 2)

    def test_warn_does_not_raise_when_log_path_is_a_directory(self):
        os.makedirs(os.path.join(self.cad, "gate-events.log"))
        try:
            _hooklib.warn("must not raise")
        except Exception as e:  # noqa: BLE001
            self.fail(f"warn() raised despite fail-open contract: {e!r}")

    def test_remind_does_not_raise_when_log_path_is_a_directory(self):
        os.makedirs(os.path.join(self.cad, "gate-events.log"))
        try:
            _hooklib.remind("TAG", "must not raise")
        except Exception as e:  # noqa: BLE001
            self.fail(f"remind() raised despite fail-open contract: {e!r}")

    def test_block_still_exits_2_when_open_itself_raises(self):
        with mock.patch("builtins.open", side_effect=OSError("locked")):
            with self.assertRaises(SystemExit) as cm:
                _hooklib.block("H-03", "must still block despite locked log")
        self.assertEqual(cm.exception.code, 2)

    def test_block_still_exits_2_when_project_root_raises(self):
        with mock.patch.object(_hooklib, "project_root", side_effect=RuntimeError("boom")):
            with self.assertRaises(SystemExit) as cm:
                _hooklib.block("H-04", "must still block despite root resolution failure")
        self.assertEqual(cm.exception.code, 2)

    def test_warn_is_silent_no_op_when_codearbiter_dir_is_missing(self):
        # A repo that never opted in (no .codearbiter/ at all) must not have
        # one conjured into existence just to hold this log.
        missing_root = os.path.join(self.root, "not-a-repo")
        os.makedirs(missing_root)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": missing_root}):
            _hooklib.warn("no dir to write into")  # must not raise
        self.assertFalse(os.path.isdir(os.path.join(missing_root, ".codearbiter")))

    def test_block_exit_code_and_stderr_unchanged_by_sink_failure(self):
        # The stderr message itself (the pre-existing contract) must be
        # unaffected by a sink failure — capture it directly.
        import io
        buf = io.StringIO()
        with mock.patch("builtins.open", side_effect=OSError("locked")):
            with mock.patch.object(sys, "stderr", buf):
                with self.assertRaises(SystemExit) as cm:
                    _hooklib.block("H-06", "stderr must still say this")
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("BLOCKED [H-06]: stderr must still say this", buf.getvalue())


class TestStalenessWarnCONFIRM09(_GateEventsFixture):
    """CONFIRM-09: active-flow audit-log staleness is a WARN, never a gate.
    Detected from EXISTING markers (.markers/dev-active, sprint-active) —
    no new state invented."""

    def _touch(self, path, age_seconds=0):
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        t = time.time() - age_seconds
        os.utime(path, (t, t))

    def test_no_markers_present_yields_no_warnings(self):
        self.assertEqual(_hooklib.staleness_warning(self.root), [])

    def test_fresh_dev_marker_is_not_stale(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=5)
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [])

    def test_stale_dev_marker_with_no_log_activity_warns(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        msgs = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(len(msgs), 1)
        self.assertIn("/dev", msgs[0])
        self.assertIn("CONFIRM-09", msgs[0])

    def test_stale_dev_marker_but_recent_log_write_is_not_stale(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        # overrides.log was written recently -> the flow IS producing audit
        # activity even though the marker itself is old.
        self._touch(os.path.join(self.cad, "overrides.log"), age_seconds=5)
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [])

    def test_stale_sprint_marker_with_no_log_activity_warns(self):
        self._touch(os.path.join(self.cad, "sprint-active"), age_seconds=3600)
        msgs = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(len(msgs), 1)
        self.assertIn("/sprint", msgs[0])

    def test_both_flows_stale_yields_two_warnings(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        self._touch(os.path.join(self.cad, "sprint-active"), age_seconds=3600)
        msgs = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(len(msgs), 2)

    def test_never_raises_on_a_stat_failure(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        with mock.patch("os.path.getmtime", side_effect=OSError("boom")):
            try:
                msgs = _hooklib.staleness_warning(self.root, window_minutes=30)
            except Exception as e:  # noqa: BLE001
                self.fail(f"staleness_warning raised: {e!r}")
        self.assertEqual(msgs, [])

    def test_has_no_side_effects_pure_function(self):
        os.makedirs(os.path.join(self.cad, ".markers"))
        self._touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        before = set(os.listdir(self.cad))
        _hooklib.staleness_warning(self.root, window_minutes=30)
        after = set(os.listdir(self.cad))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
