"""Tests for taskwrite.py — the sanctioned task-board mutator behind /ca:task
(#271 C-1/C-3). taskwrite.py has no other test coverage today; this file is
the first.

E-6 (pre-release-hardening): the original version of this file proved its
contention properties with two THREADS inside one interpreter. That is the
wrong instrument. #271's real bug is two SEPARATE /ca:task invocations — two
OS PROCESSES — racing on the same `.codearbiter/open-tasks.md` + its lock
sidecar. A thread harness shares one `_hooklib` module instance between both
"writers", so it can silently pass for reasons that say nothing about the
cross-process lock taskwrite.py actually depends on. This file now spawns
REAL `taskwrite.py` subprocesses.

To make two independent processes' critical sections *provably* overlap
(not just "launched close together and hopefully raced"), each subprocess
runs against a private copy of the hook sources with one test-only
instrumentation line appended to the copied `_hooklib.py`: when
`CA_TEST_LOCK_HOLD_MS` is set, `acquire_lock` sleeps for that many
milliseconds AFTER the real OS lock is taken and BEFORE returning the handle
to its caller — extending, never faking, the real hold. When
`CA_TEST_ACQUIRED_MARKER` is also set, the wrapper writes a wall-clock
timestamp to that file the instant the real lock succeeds, so the test
harness can observe precisely when a subprocess entered its held window
without guessing at wall-clock timing. Neither knob exists in the real
`core/pysrc/_hooklib.py` — this is scaffolding added only to the throwaway
copy, never the shipped hook.

Covers the lock-free read-modify-write race that let two concurrent
`taskwrite` invocations silently drop one writer's edit and mint a DUPLICATE
dotted task ID (both readers saw the same stale board, so `next_seq`
computed the same "next" number for both), plus the D-4 guarantee that an
out-of-band Edit (the harvest/decompose path, which never takes this lock)
is preserved rather than silently clobbered by a lock-holder writing back a
stale in-memory snapshot.

Stdlib only: subprocess + a temp-dir source copy, no third-party deps, no
real ~/.codearbiter.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

CONCURRENCY_TEST_WAIT = 10.0

BOARD = """\
# Open tasks

## In-flight
- [ ] mvp1.store.0001 - existing queued task
"""

# Appended verbatim to the COPIED `_hooklib.py` only (never core/pysrc/ or the
# vendored plugin copy). Guarded by an env var so importing the copy with no
# env vars set behaves byte-identically to the real module.
_HOLD_HOOK = '''

# ---- test-only instrumentation (E-6 subprocess contention harness) ----
# Appended by plugins/ca/hooks/tests/test_taskwrite.py to a private COPY of
# this file. Never present in core/pysrc/_hooklib.py or any shipped plugin.
import os as _ca_test_os
import time as _ca_test_time

_CA_TEST_HOLD_MS = float(_ca_test_os.environ.get("CA_TEST_LOCK_HOLD_MS", "0") or 0)
_CA_TEST_MARKER = _ca_test_os.environ.get("CA_TEST_ACQUIRED_MARKER")

if _CA_TEST_HOLD_MS > 0:
    _ca_test_real_acquire_lock = acquire_lock

    def acquire_lock(path):
        token = _ca_test_real_acquire_lock(path)
        if token is not None:
            if _CA_TEST_MARKER:
                with open(_CA_TEST_MARKER, "w", encoding="utf-8") as _marker_f:
                    _marker_f.write(str(_ca_test_time.time()))
            _ca_test_time.sleep(_CA_TEST_HOLD_MS / 1000.0)
        return token
'''


def _wait_for_file(path, timeout=CONCURRENCY_TEST_WAIT):
    """Bounded poll for a marker file's existence. Returns True/False; never
    raises, never blocks past `timeout`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.005)
    return False


class TaskwriteContentionTest(unittest.TestCase):
    """Cross-PROCESS contention proof for taskwrite.py's lock + re-read-under-
    lock CAS (#271 C-2/C-3)."""

    @classmethod
    def setUpClass(cls):
        # One instrumented source copy shared by every test in this class:
        # taskwrite.py, hostapi.py, _taskboardlib.py, _hooklib.py are the
        # complete, stdlib-only dependency closure (verified — none of them
        # imports anything else project-local).
        cls._copy_dir = tempfile.mkdtemp(prefix="ca-taskwrite-hookscopy-")
        for name in ("taskwrite.py", "hostapi.py", "_taskboardlib.py", "_hooklib.py"):
            shutil.copy2(os.path.join(_HOOKS_DIR, name),
                        os.path.join(cls._copy_dir, name))
        hooklib_copy = os.path.join(cls._copy_dir, "_hooklib.py")
        with open(hooklib_copy, "a", encoding="utf-8") as f:
            f.write(_HOLD_HOOK)
        cls._taskwrite_script = os.path.join(cls._copy_dir, "taskwrite.py")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._copy_dir, ignore_errors=True)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)
        self.board_path = os.path.join(self.cad, "open-tasks.md")
        with open(self.board_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(BOARD)
        self._markers = tempfile.mkdtemp(prefix="ca-taskwrite-markers-")

    def tearDown(self):
        self._tmp.cleanup()
        shutil.rmtree(self._markers, ignore_errors=True)

    def _read(self):
        with open(self.board_path, encoding="utf-8") as f:
            return f.read()

    def _marker(self, name):
        return os.path.join(self._markers, name)

    def _popen(self, argv, hold_ms=0, marker=None):
        """Launch a REAL taskwrite.py subprocess against the fixture board."""
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = self.root
        if hold_ms:
            env["CA_TEST_LOCK_HOLD_MS"] = str(hold_ms)
        else:
            env.pop("CA_TEST_LOCK_HOLD_MS", None)
        if marker:
            env["CA_TEST_ACQUIRED_MARKER"] = marker
        else:
            env.pop("CA_TEST_ACQUIRED_MARKER", None)
        return subprocess.Popen(
            [sys.executable, self._taskwrite_script] + argv,
            cwd=self.root, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _finish(self, proc):
        out, err = proc.communicate(timeout=CONCURRENCY_TEST_WAIT)
        return proc.returncode, out, err

    def test_concurrent_add_entries_both_survive_no_lost_update(self):
        """Two concurrent `taskwrite add` PROCESSES must BOTH land — the
        classic lost-update shape: without a lock + re-read, the second
        os.replace() silently discards the first writer's edit.

        Genuine overlap (not a lucky race) is proven directly: each process
        stamps a wall-clock timestamp into its own marker file the instant it
        holds the REAL OS lock, then holds it for `hold_ms`. If the lock
        truly serializes, the second stamp cannot land before
        (first stamp + hold_ms) — that gap is asserted below, not assumed."""
        hold_ms = 150
        m1, m2 = self._marker("m1"), self._marker("m2")
        p1 = self._popen(["add", "first concurrent task", "--id", "mvp1.store"],
                         hold_ms=hold_ms, marker=m1)
        p2 = self._popen(["add", "second concurrent task", "--id", "mvp1.store"],
                         hold_ms=hold_ms, marker=m2)
        self.assertTrue(_wait_for_file(m1), "process 1 never acquired the real lock")
        self.assertTrue(_wait_for_file(m2), "process 2 never acquired the real lock")
        with open(m1, encoding="utf-8") as f:
            t1 = float(f.read())
        with open(m2, encoding="utf-8") as f:
            t2 = float(f.read())

        rc1, out1, err1 = self._finish(p1)
        rc2, out2, err2 = self._finish(p2)
        self.assertEqual(rc1, 0, err1)
        self.assertEqual(rc2, 0, err2)

        # The proof: whichever writer acquired second could not have stamped
        # its marker until the first released — i.e. at least ~hold_ms after
        # the first's own stamp. A generous floor (60% of hold_ms) absorbs
        # scheduler jitter while still ruling out "both acquired at once".
        gap = abs(t2 - t1)
        self.assertGreaterEqual(
            gap, (hold_ms / 1000.0) * 0.6,
            f"lock did not serialize the two acquisitions: gap={gap:.3f}s, "
            f"expected >= {(hold_ms / 1000.0) * 0.6:.3f}s (hold_ms={hold_ms})")

        text = self._read()
        self.assertIn("first concurrent task", text,
                      "the first writer's edit was silently lost")
        self.assertIn("second concurrent task", text,
                      "the second writer's edit was silently lost")

    def test_concurrent_add_entries_do_not_mint_duplicate_dotted_id(self):
        """Both concurrent adds mint a dotted ID in the SAME group.type
        namespace. Reading the board fresh under the lock (not the stale
        snapshot each process opened with) is what makes next_seq allocate
        two DISTINCT ids instead of both computing the same 'max + 1'."""
        hold_ms = 150
        m1, m2 = self._marker("m1"), self._marker("m2")
        p1 = self._popen(["add", "first concurrent task", "--id", "mvp1.store"],
                         hold_ms=hold_ms, marker=m1)
        p2 = self._popen(["add", "second concurrent task", "--id", "mvp1.store"],
                         hold_ms=hold_ms, marker=m2)
        self.assertTrue(_wait_for_file(m1), "process 1 never acquired the real lock")
        self.assertTrue(_wait_for_file(m2), "process 2 never acquired the real lock")
        rc1, _out1, err1 = self._finish(p1)
        rc2, _out2, err2 = self._finish(p2)
        self.assertEqual(rc1, 0, err1)
        self.assertEqual(rc2, 0, err2)

        text = self._read()
        ids = sorted(set(re.findall(r"mvp1\.store\.\d{4}", text)))
        # The seed board already holds mvp1.store.0001; the two new adds must
        # mint 0002 and 0003 — never the SAME id twice.
        self.assertEqual(len(ids), 3, f"expected 3 distinct dotted ids, got {ids}")

    def test_external_edit_while_lock_held_is_not_silently_clobbered(self):
        """D-4: an out-of-band Edit (harvest/decompose writing the board
        directly, never taking the lock) that lands WHILE a taskwrite process
        holds the lock must still be present afterward — re-reading the
        board under the lock, rather than writing back the stale snapshot the
        process opened with, is what preserves it (a detected-loss-free
        outcome, not a silent clobber).

        The marker file pins the exact moment: the holder has the REAL lock
        and (thanks to the injected hold) has not yet even called
        `tb.read_board()` — so any write landing before the marker's hold
        window closes is guaranteed to be visible to the holder's own
        re-read, exactly the ordering C-3 exists to guarantee.

        `hold_ms` is deliberately kept UNDER production's own fail-soft
        `LOCK_WAIT` (0.2s, core/pysrc/_hooklib.py) — this test proves the
        real, unmodified contention behavior end-to-end, including the
        second writer's own real (unpatched) retry budget; it must not need
        a longer deadline than production actually gives a real second
        `/ca:task` invocation."""
        hold_ms = 120
        m1 = self._marker("holder")
        p1 = self._popen(["add", "lock holder's task", "--id", "mvp1.store"],
                         hold_ms=hold_ms, marker=m1)
        self.assertTrue(_wait_for_file(m1), "lock holder never acquired the real lock")

        # The out-of-band Edit: the host's own Edit tool writing the board
        # directly (harvest/decompose), never taking taskwrite's lock.
        current = self._read()
        with open(self.board_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(current + "- [ ] out-of-band harvested item\n")

        # A second REAL taskwrite writer, contending for the same lock while
        # the first is still (per the marker) inside its held window.
        p2 = self._popen(["add", "second writer's task", "--id", "mvp1.store"])

        rc1, _out1, err1 = self._finish(p1)
        rc2, _out2, err2 = self._finish(p2)
        self.assertEqual(rc1, 0, err1)
        self.assertEqual(rc2, 0, err2)

        text = self._read()
        self.assertIn("out-of-band harvested item", text,
                      "an interleaved external Edit must not be silently clobbered")
        self.assertIn("lock holder's task", text)
        self.assertIn("second writer's task", text)


if __name__ == "__main__":
    unittest.main()
