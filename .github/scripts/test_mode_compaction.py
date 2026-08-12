#!/usr/bin/env python3
"""Integration tests for the mode plane's compaction seam (AC-4 x AC-25).

This file exists because the defect it pins lives BETWEEN two lanes' contracts
and neither lane's suite could see it:

  AC-4  a new session restores `arbiter`
  AC-25 after a compaction, the next turn re-injects the CURRENT mode's persona

`SessionStart` fires on `compact` as well as on a genuinely new session, and
nothing in this repo reads the event's `source` field — so `clear_mode_marker`
cannot distinguish the two directly. It infers it from an owner record.

The trap: that owner record is OVERLOADED. `dev-session-owner.json` anchors the
legacy `dev-active` marker's force-close, and the mode plane was reading the
SAME record to decide "have I seen this session before". When a DIFFERENT live
session owns the legacy marker, `clear_mode_marker` returns early to protect
that session's record — correctly — which leaves the mode plane with no anchor
of its own. A compaction then reads `is_owner == False` and clears the user's
mode out from under them.

Direction of failure is safe (it drops to `arbiter`, i.e. gates ON) and the
window is the legacy-marker migration only, but it is silent: the user leaves
dangerous mode without asking, and an `exit` row is logged for a mode they never
exited.

Note that a session-keyed mode file makes AC-4 hold STRUCTURALLY — a brand-new
session has no entry and reads `arbiter` without anything being cleared. So the
clear in `clear_mode_marker` can only ever fire for a session that already
flipped, which is precisely the case that must be preserved. The fix is a
mode-plane-owned "seen" record, independent of the legacy marker's.

Run: python .github/scripts/test_mode_compaction.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PYSRC = ROOT / "core" / "pysrc"
sys.path.insert(0, str(PYSRC))

import _modelib  # noqa: E402

_spec = importlib.util.spec_from_file_location("session_start", str(PYSRC / "session-start.py"))
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

ARBITER = _modelib.MODES[0]


def _fresh_repo():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".codearbiter", ".markers"))
    return d


def _legacy_marker(root):
    return os.path.join(root, ".codearbiter", ".markers", "dev-active")


class TestModeSurvivesCompaction(unittest.TestCase):
    def test_new_session_still_restores_arbiter(self):
        """AC-4 must not regress: a session that never flipped reads `arbiter`."""
        root = _fresh_repo()
        ss.clear_mode_marker(root, host_name="claude", session_id="brand-new")
        mode, _ = _modelib.current_mode("brand-new", root=root)
        self.assertEqual(mode, ARBITER)

    def test_a_second_sessions_mode_is_never_cleared_by_the_first(self):
        """The clear is scoped to the invoking session, never a sibling's entry."""
        root = _fresh_repo()
        _modelib.write_mode("other-session", "dangerous", root=root)
        ss.clear_mode_marker(root, host_name="claude", session_id="me")
        mode, _ = _modelib.current_mode("other-session", root=root)
        self.assertEqual(mode, "dangerous", "a sibling session's mode must be untouched")

    def test_mode_survives_compaction_in_a_clean_repo(self):
        """AC-25, the ordinary path: no legacy marker anywhere."""
        root = _fresh_repo()
        sid = "sess-clean"
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)   # first SessionStart
        _modelib.write_mode(sid, "dangerous", root=root)                 # the user flips
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)   # SessionStart(compact)
        mode, _ = _modelib.current_mode(sid, root=root)
        self.assertEqual(mode, "dangerous", "a compaction must not change the mode")

    def test_mode_survives_compaction_while_another_live_session_owns_the_legacy_marker(self):
        """The defect this file was written for.

        A concurrent session holds a live `dev-active` marker inside its liveness
        window, so our first `SessionStart` returns early to avoid stomping that
        session's owner record. The mode plane must NOT depend on that record.
        """
        root = _fresh_repo()
        sid, other = "sess-shadowed", "another-live-session"
        open(_legacy_marker(root), "w").close()
        ss._write_dev_session_owner(root, other, time.time())            # fresh, in-window

        ss.clear_mode_marker(root, host_name="claude", session_id=sid)   # first SessionStart
        _modelib.write_mode(sid, "dangerous", root=root)                 # the user flips
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)   # SessionStart(compact)

        mode, _ = _modelib.current_mode(sid, root=root)
        self.assertEqual(
            mode, "dangerous",
            "a compaction cleared the mode because a DIFFERENT session owned the legacy marker")

    def test_the_shadowing_sessions_own_record_is_still_protected(self):
        """The early return exists for a reason; the fix must not defeat it.

        Fixing the above by simply seeding our own id into the shared record
        would clobber the concurrent owner and force-close its marker early.
        """
        root = _fresh_repo()
        sid, other = "sess-shadowed", "another-live-session"
        open(_legacy_marker(root), "w").close()
        ss._write_dev_session_owner(root, other, time.time())

        ss.clear_mode_marker(root, host_name="claude", session_id=sid)

        prev_sid, _ts = ss._read_dev_session_owner(root)
        self.assertEqual(prev_sid, other,
                         "the concurrent owner's record must survive our SessionStart")
        self.assertTrue(os.path.isfile(_legacy_marker(root)),
                        "a live in-window marker must not be force-closed by a bystander")

    def test_an_unseen_session_holding_a_mode_is_cleared_not_retained(self):
        """The fail DIRECTION, which is the whole point of the anchor.

        A mode entry exists for this session id, but no `seen` record backs it —
        a reused session id, a corrupt record, or a failed write. The anchor is
        unproven, so the mode must be cleared to `arbiter` (gates ON). Retaining
        a gates-off posture on state we cannot vouch for is the unsafe
        direction, and ADR-0030 records that a failed transition OUT of
        dangerous mode is the dangerous one.
        """
        root = _fresh_repo()
        sid = "sess-unvouched"
        _modelib.write_mode(sid, "dangerous", root=root)   # mode present...
        # ...deliberately NO seen record written for it.
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        mode, _ = _modelib.current_mode(sid, root=root)
        self.assertEqual(mode, ARBITER,
                         "an unvouched session must fall back to arbiter, never retain gates-off")

    def test_a_corrupt_seen_record_clears_rather_than_retains(self):
        """Same direction, via the corruption path specifically."""
        root = _fresh_repo()
        sid = "sess-corrupt"
        _modelib.write_mode(sid, "dangerous", root=root)
        with open(ss._mode_session_seen_path(root), "w", encoding="utf-8") as f:
            f.write("{not json at all")
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        mode, _ = _modelib.current_mode(sid, root=root)
        self.assertEqual(mode, ARBITER, "a corrupt anchor must clear, not retain")

    def test_repeated_compactions_keep_the_mode(self):
        """The anchor must persist, not merely survive one round."""
        root = _fresh_repo()
        sid = "sess-many"
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        _modelib.write_mode(sid, "ops", root=root)
        for _ in range(4):
            ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        mode, _ = _modelib.current_mode(sid, root=root)
        self.assertEqual(mode, "ops")


if __name__ == "__main__":
    unittest.main()
