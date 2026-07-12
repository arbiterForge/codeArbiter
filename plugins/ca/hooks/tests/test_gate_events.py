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
import threading
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

    def test_record_carries_the_resolved_host_name(self):
        # ADR-0012/observability-001: two hosts (Claude, Codex) can share one
        # gate-events.log — each line must be attributable to the host that
        # wrote it via get_host().name. project_root() itself is threaded
        # through get_host() too (#260), so the fake host must resolve a real
        # root, not just carry a `.name`.
        fake_host = mock.Mock()
        fake_host.name = "codex"
        fake_host.project_root.return_value = self.root
        with mock.patch.object(_hooklib, "get_host", return_value=fake_host):
            _hooklib.warn("host-attributed line")
        text = _read_log(self.cad)
        self.assertIn("host=codex", text)

    def test_host_field_precedes_hook_field_and_both_present(self):
        fake_host = mock.Mock()
        fake_host.name = "claude"
        fake_host.project_root.return_value = self.root
        with mock.patch.object(_hooklib, "get_host", return_value=fake_host), \
             mock.patch.object(sys, "argv", ["/path/to/pre-write.py"]):
            _hooklib.remind("H-01", "ordering check")
        text = _read_log(self.cad)
        self.assertIn("host=claude hook=pre-write.py", text)

    def test_host_resolution_failure_does_not_break_fail_open_contract(self):
        # host resolution must never turn a BLOCK into a raised exception or
        # change its exit code — mirrors the other AC-2 fail-open guarantees.
        # project_root() succeeds (it needs a real host to resolve a real
        # root, #260); only the `.name` access fails, isolating the guard
        # this test targets from the unrelated project_root() fail-open path
        # already covered by test_block_still_exits_2_when_project_root_raises.
        class _BoomNameHost:
            def project_root(self, payload=None):
                return self.root_value

        boom_host = _BoomNameHost()
        boom_host.root_value = self.root
        type(boom_host).name = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        with mock.patch.object(_hooklib, "get_host", return_value=boom_host):
            with self.assertRaises(SystemExit) as cm:
                _hooklib.block("H-07", "must still block despite host resolution failure")
        self.assertEqual(cm.exception.code, 2)
        text = _read_log(self.cad)
        self.assertIn("host=unknown", text)


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
        self.assertIn("host=claude hook=pre-bash.py", log)


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


class TestWindowsLockAC3(_GateEventsFixture):
    """FINDING 3 (HIGH/coverage): the msvcrt.locking byte-range lock around
    gate-events.log appends (_hooklib._log_gate_event, os.name == "nt" leg)
    has no direct coverage. These tests inject a fake `msvcrt` module into
    sys.modules and force os.name == "nt" so the locking branch runs
    deterministically on ANY host OS (not just when CI happens to run on
    Windows) — the real Windows-only exercise still happens for free whenever
    this suite runs on an actual Windows box, since os.name is genuinely
    "nt" there and the local `import msvcrt` picks up the real module unless
    this fixture's sys.modules patch is active."""

    class _FakeMsvcrt:
        LK_LOCK = 1
        LK_UNLCK = 0

        def __init__(self, on_unlock=None):
            self.calls = []
            self._on_unlock = on_unlock

        def locking(self, fd, mode, nbytes):
            kind = "lock" if mode == self.LK_LOCK else "unlock"
            self.calls.append((kind, fd, nbytes))
            if kind == "unlock" and self._on_unlock is not None:
                self._on_unlock()

    def test_lock_called_before_write_and_unlock_called_after(self):
        fake = self._FakeMsvcrt()
        order = []
        real_write = os.write

        def spy_write(fd, data):
            order.append("write")
            return real_write(fd, data)

        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}), \
             mock.patch("os.write", side_effect=spy_write):
            _hooklib.warn("lock ordering check")

        kinds = [c[0] for c in fake.calls]
        self.assertIn("lock", kinds)
        self.assertIn("unlock", kinds)
        lock_idx = kinds.index("lock")
        unlock_idx = kinds.index("unlock")
        # The write happened strictly between the lock and unlock calls.
        self.assertEqual(order, ["write"])
        self.assertLess(lock_idx, unlock_idx)
        self.assertEqual(unlock_idx, len(fake.calls) - 1,
                         "unlock must be the last locking() call")
        # Both calls lock/unlock exactly the same 1-byte range.
        for _, _, nbytes in fake.calls:
            self.assertEqual(nbytes, 1)

    def test_unlock_oserror_is_caught_and_does_not_propagate(self):
        def _boom():
            raise OSError("simulated unlock failure")

        fake = self._FakeMsvcrt(on_unlock=_boom)
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}):
            try:
                _hooklib.warn("unlock failure must not propagate")
            except Exception as e:  # noqa: BLE001
                self.fail(f"warn() raised despite unlock-failure catch: {e!r}")
        # The write itself happens before the (failing) unlock, so the line
        # must still have landed durably despite the unlock error.
        text = _read_log(self.cad)
        self.assertIn("unlock failure must not propagate", text)
        kinds = [c[0] for c in fake.calls]
        self.assertIn("unlock", kinds)

    def test_lock_oserror_does_not_break_fail_open_contract(self):
        class _BoomLockMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 0

            def locking(self, fd, mode, nbytes):
                if mode == self.LK_LOCK:
                    raise OSError("simulated lock failure")

        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": _BoomLockMsvcrt()}):
            with self.assertRaises(SystemExit) as cm:
                _hooklib.block("H-08", "must still block despite lock failure")
        self.assertEqual(cm.exception.code, 2)

    def test_transient_lock_contention_is_retried_and_event_lands(self):
        class _TransientMsvcrt(self._FakeMsvcrt):
            LK_NBLCK = 2

            def __init__(self):
                super().__init__()
                self.lock_attempts = 0

            def locking(self, fd, mode, nbytes):
                if mode == self.LK_NBLCK:
                    self.lock_attempts += 1
                    self.calls.append(("lock", fd, nbytes))
                    if self.lock_attempts < 3:
                        raise OSError(36, "simulated transient contention")
                    return
                return super().locking(fd, mode, nbytes)

        fake = _TransientMsvcrt()
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}), \
             mock.patch("time.sleep") as sleep:
            _hooklib.warn("transient contention must not drop this event")

        self.assertEqual(fake.lock_attempts, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("transient contention must not drop this event", _read_log(self.cad))
        self.assertEqual([call[0] for call in fake.calls].count("unlock"), 1)

    def test_windows_lock_violation_is_retried_and_event_lands(self):
        class _WinLockViolationMsvcrt(self._FakeMsvcrt):
            LK_NBLCK = 2

            def __init__(self):
                super().__init__()
                self.lock_attempts = 0

            def locking(self, fd, mode, nbytes):
                if mode == self.LK_NBLCK:
                    self.lock_attempts += 1
                    self.calls.append(("lock", fd, nbytes))
                    if self.lock_attempts == 1:
                        error = OSError(0, "simulated Windows lock violation")
                        error.winerror = 33
                        raise error
                    return
                return super().locking(fd, mode, nbytes)

        fake = _WinLockViolationMsvcrt()
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}), \
             mock.patch("time.sleep") as sleep:
            _hooklib.warn("Windows lock violation must be retried")

        self.assertEqual(fake.lock_attempts, 2)
        sleep.assert_called_once()
        self.assertIn("Windows lock violation must be retried", _read_log(self.cad))
        self.assertEqual([call[0] for call in fake.calls].count("unlock"), 1)

    def test_non_contention_lock_oserror_fails_open_without_retry_or_unlock(self):
        class _InvalidHandleMsvcrt(self._FakeMsvcrt):
            LK_NBLCK = 2

            def locking(self, fd, mode, nbytes):
                kind = "lock" if mode == self.LK_NBLCK else "unlock"
                self.calls.append((kind, fd, nbytes))
                if kind == "lock":
                    error = OSError(9, "simulated invalid file descriptor")
                    error.winerror = 6
                    raise error

        fake = _InvalidHandleMsvcrt()
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}), \
             mock.patch("time.sleep") as sleep:
            _hooklib.warn("invalid handle must fail open immediately")

        self.assertEqual([call[0] for call in fake.calls], ["lock"])
        sleep.assert_not_called()
        self.assertEqual(_read_log(self.cad), "")

    def test_lock_failure_never_attempts_unlock_without_acquisition(self):
        class _PermanentContentionMsvcrt(self._FakeMsvcrt):
            LK_NBLCK = 2

            def locking(self, fd, mode, nbytes):
                kind = "lock" if mode == self.LK_NBLCK else "unlock"
                self.calls.append((kind, fd, nbytes))
                if kind == "lock":
                    raise OSError(36, "simulated permanent contention")

        fake = _PermanentContentionMsvcrt()
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"msvcrt": fake}), \
             mock.patch("time.sleep"):
            _hooklib.warn("fail open without an unowned unlock")

        self.assertNotIn("unlock", [call[0] for call in fake.calls])


class TestConcurrentAppendNoInterleaving(_GateEventsFixture):
    """Same-process concurrent-append coverage (FINDING 3c): many threads
    calling warn() concurrently must each land as exactly one intact line —
    no interleaving of two threads' text within a line and no truncation."""

    def test_concurrent_warn_calls_land_as_intact_non_interleaved_lines(self):
        n_threads = 16
        messages = [f"thread-payload-{i:03d}-{'x' * 40}" for i in range(n_threads)]

        def worker(msg):
            _hooklib.warn(msg)

        threads = [threading.Thread(target=worker, args=(m,)) for m in messages]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        text = _read_log(self.cad)
        lines = text.splitlines()
        self.assertEqual(len(lines), n_threads,
                         f"expected {n_threads} intact lines, got {len(lines)}: {lines}")
        for msg in messages:
            matches = [line for line in lines if msg in line]
            self.assertEqual(len(matches), 1,
                             f"message {msg!r} missing or duplicated: {lines}")
        for line in lines:
            self.assertIn("WARN", line)

    @unittest.skipUnless(os.name == "nt", "Windows lock contention regression")
    def test_repeated_windows_thread_bursts_land_every_message_without_stair_step(self):
        n_rounds = 3
        n_threads = 16
        messages = [
            f"burst-{round_no:02d}-payload-{thread_no:03d}"
            for round_no in range(n_rounds)
            for thread_no in range(n_threads)
        ]

        started = time.monotonic()
        for round_no in range(n_rounds):
            round_messages = messages[round_no * n_threads:(round_no + 1) * n_threads]
            threads = [
                threading.Thread(target=_hooklib.warn, args=(message,))
                for message in round_messages
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive(), "gate-event writer thread stalled")
        elapsed = time.monotonic() - started

        lines = _read_log(self.cad).splitlines()
        self.assertEqual(len(lines), len(messages))
        for message in messages:
            self.assertEqual(sum(message in line for line in lines), 1, message)
        self.assertLess(elapsed, 5.0, f"Windows lock retries stair-stepped for {elapsed:.2f}s")


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
