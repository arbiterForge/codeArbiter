"""Tests for taskwrite.py — the sanctioned task-board mutator behind /ca:task
(#271 C-1/C-3). taskwrite.py has no test coverage today; this file is the
first.

Covers the lock-free read-modify-write race that let two concurrent
`taskwrite` invocations silently drop one writer's edit and mint a DUPLICATE
dotted task ID (both readers see the same stale board, so `next_seq` computes
the same "next" number for both). Pattern-matches the contention harness in
test_ledgerlib.py's `_serialize_transactions` (the `while_first_holds` shape
used by `test_same_session_concurrent_updates_do_not_regress_accounting`):
serialize two writers via the REAL lock, inject a third-party mutation (an
out-of-band harvest/decompose Edit) while the first holds the lock, then
assert nothing is lost and no duplicate ID is minted.

Stdlib unittest only; no real ~/.codearbiter, no subprocess (in-process
`taskwrite.run(host, argv)` calls against a throwaway fixture repo).
"""
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _hooklib
import hostapi
import taskwrite as TW

CONCURRENCY_TEST_WAIT = 5.0

BOARD = """\
# Open tasks

## In-flight
- [ ] mvp1.store.0001 - existing queued task
"""


class _FixtureHost(hostapi.Host):
    name = "fixture"

    def __init__(self, root):
        self._root = root

    def project_root(self, payload=None):
        return self._root


class TaskwriteContentionTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)
        self.board_path = os.path.join(self.cad, "open-tasks.md")
        with open(self.board_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(BOARD)
        self.host = _FixtureHost(self.root)
        _hooklib._reset_root_cache()

    def tearDown(self):
        _hooklib.reset_host()
        _hooklib._reset_root_cache()
        self._tmp.cleanup()

    def _read(self):
        with open(self.board_path, encoding="utf-8") as f:
            return f.read()

    def _run(self, argv):
        # Fresh Host injection per call (mirrors production: run(host, argv)
        # is the entry point, exactly as the __main__ guard invokes it).
        return TW.run(self.host, argv)

    def _serialize_writers(self, first, second, while_first_holds=None):
        """Prove the second writer cannot observe/mutate the board until the
        first releases the lock — the exact shape of
        test_ledgerlib._serialize_transactions."""
        real_acquire = _hooklib.acquire_lock
        first_acquired = threading.Event()
        second_attempted = threading.Event()
        second_acquired = threading.Event()
        release_first = threading.Event()
        outputs = {}

        def coordinated_acquire(path):
            if threading.current_thread().name == "taskwrite-second":
                second_attempted.set()
            token = real_acquire(path)
            if token is not None and threading.current_thread().name == "taskwrite-first":
                first_acquired.set()
                self.assertTrue(release_first.wait(CONCURRENCY_TEST_WAIT))
            elif token is not None and threading.current_thread().name == "taskwrite-second":
                second_acquired.set()
            return token

        one = threading.Thread(target=lambda: outputs.setdefault("first", first()),
                               name="taskwrite-first")
        two = threading.Thread(target=lambda: outputs.setdefault("second", second()),
                               name="taskwrite-second")
        with mock.patch.object(TW, "acquire_lock", side_effect=coordinated_acquire):
            one.start()
            self.assertTrue(first_acquired.wait(CONCURRENCY_TEST_WAIT))
            if while_first_holds:
                while_first_holds()
            two.start()
            self.assertTrue(second_attempted.wait(CONCURRENCY_TEST_WAIT))
            self.assertFalse(second_acquired.is_set())
            release_first.set()
            self.assertTrue(second_acquired.wait(CONCURRENCY_TEST_WAIT))
            one.join(CONCURRENCY_TEST_WAIT)
            two.join(CONCURRENCY_TEST_WAIT)
        self.assertFalse(one.is_alive())
        self.assertFalse(two.is_alive())
        return outputs

    def test_concurrent_add_entries_both_survive_no_lost_update(self):
        """Two concurrent `taskwrite add` calls must BOTH land — the classic
        lost-update shape: without a lock + re-read, the second os.replace()
        silently discards the first writer's edit."""
        outputs = self._serialize_writers(
            lambda: self._run(["add", "first concurrent task", "--id", "mvp1.store"]),
            lambda: self._run(["add", "second concurrent task", "--id", "mvp1.store"]))
        self.assertEqual(outputs["first"], 0)
        self.assertEqual(outputs["second"], 0)
        text = self._read()
        self.assertIn("first concurrent task", text,
                       "the first writer's edit was silently lost")
        self.assertIn("second concurrent task", text,
                       "the second writer's edit was silently lost")

    def test_concurrent_add_entries_do_not_mint_duplicate_dotted_id(self):
        """Both concurrent adds mint a dotted ID in the SAME group.type
        namespace. Reading the board fresh under the lock (not the stale
        snapshot each thread opened with) is what makes next_seq allocate two
        DISTINCT ids instead of both computing the same 'max + 1'."""
        self._serialize_writers(
            lambda: self._run(["add", "first concurrent task", "--id", "mvp1.store"]),
            lambda: self._run(["add", "second concurrent task", "--id", "mvp1.store"]))
        text = self._read()
        ids = sorted(set(__import__("re").findall(r"mvp1\.store\.\d{4}", text)))
        # The seed board already holds mvp1.store.0001; the two new adds must
        # mint 0002 and 0003 — never the SAME id twice.
        self.assertEqual(len(ids), 3, f"expected 3 distinct dotted ids, got {ids}")

    def test_external_edit_while_lock_held_is_not_silently_clobbered(self):
        """D-4: an out-of-band Edit (harvest/decompose writing the board
        directly, never taking the lock) that lands WHILE the lock-holder is
        mid-transaction must still be present afterward — re-reading the
        board under the lock, rather than writing back the stale snapshot the
        writer opened with, is what preserves it."""
        def external_edit():
            # Simulate the host's own Edit tool call mutating the board
            # directly while the lock-holder is still inside its critical
            # section — exactly the harvest/decompose path (D-4), which never
            # takes taskwrite's lock.
            current = self._read()
            with open(self.board_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(current + "- [ ] out-of-band harvested item\n")

        outputs = self._serialize_writers(
            lambda: self._run(["add", "lock holder's task", "--id", "mvp1.store"]),
            lambda: self._run(["add", "second writer's task", "--id", "mvp1.store"]),
            while_first_holds=external_edit)
        self.assertEqual(outputs["first"], 0)
        self.assertEqual(outputs["second"], 0)
        text = self._read()
        self.assertIn("out-of-band harvested item", text,
                       "an interleaved external Edit must not be silently clobbered")
        self.assertIn("lock holder's task", text)
        self.assertIn("second writer's task", text)


if __name__ == "__main__":
    unittest.main()
