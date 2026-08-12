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
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PYSRC = ROOT / "core" / "pysrc"
sys.path.insert(0, str(PYSRC))

import _modelib  # noqa: E402
import hostapi  # noqa: E402

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


class TestMarkerRootIsPayloadResolved(unittest.TestCase):
    """`marker_root()` with no payload can SPAWN GIT. That is the regression.

    `_activationlib.marker_root(payload=None)` delegates to the host, whose
    docstring says to pass the raw hook JSON "for production-correct
    resolution" and warns that a linked-worktree escalation costs "the extra
    git spawn". A no-argument call therefore introduces a git subprocess into
    `SessionStart`.

    On Windows a bare `git` can resolve from the current directory, so a
    project containing a `git.exe` gets ITS git executed — which is precisely
    what `test_pi_package.py::test_real_rpc_enabled_start_never_executes_project_git…`
    poisons a fixture to prove cannot happen. When that spawn misbehaves,
    startup dies before reaching the git-enforcer install, and the repo loses
    the H-01/H-02 backstop that closes `--no-verify` (ADR-0015) — silently.

    Asserted at the source rather than behaviourally because the failure needs
    a real Pi RPC session plus a poisoned PATH to reproduce, and this pins the
    one-token difference that causes it. The behavioural proof is the RPC test
    above going green.
    """

    def test_session_start_resolves_marker_root_from_the_payload(self):
        """Scoped to `session-start.py` deliberately.

        Three PRE-EXISTING argument-less call sites also exist — `_bashguardlib.py`,
        `migration-pass.py`, `security-pass.py`. They are NOT in scope here and are
        not asserted: two are standalone gate producers invoked deliberately rather
        than on every session start, and none of them was introduced by this branch.
        Widening this guard to them would block this PR on unrelated code. They are
        filed separately instead — the same hazard may or may not apply, and that
        needs its own look rather than a blanket sweep.
        """
        src = (PYSRC / "session-start.py").read_text(encoding="utf-8")
        offenders = [
            n for n, line in enumerate(src.splitlines(), 1)
            if re.search(r"\bmarker_root\(\s*\)", line.split("#", 1)[0])
        ]
        self.assertEqual(
            offenders, [],
            "session-start.py must call marker_root WITH the hook payload. An argument-less "
            "call can spawn git during SessionStart; on Windows that can execute a "
            "project-local git.exe, and if the spawn misbehaves startup dies before the "
            "git-enforcer install runs. Offending lines: {}".format(offenders))


class _RaisingModeRootHost(hostapi.Host):
    """A host whose `marker_root` raises — the one seam the mode plane needs.

    Not a stub of the whole resolution: `marker_root()` in `_activationlib`
    delegates to `get_host().marker_root(payload)`, so this exercises the real
    call chain `session-start.py` takes and raises at exactly the point
    `hostapi.git_toplevel` can. That function calls `git_executable()` as its
    FIRST statement, outside its own `try`, and
    `_gitexec._trusted_environment_path` raises `RuntimeError` when
    `CODEARBITER_GIT_EXECUTABLE` is relative or names a path that is no longer
    a file — a live possibility on the Pi bridge, which supplies that identity.
    """

    name = "fake"
    has_statusline = False

    def marker_root(self, payload=None):
        raise RuntimeError("CODEARBITER_GIT_EXECUTABLE is unavailable")


class TestModePlaneFailureNeverCostsTheEnforcer(unittest.TestCase):
    """SessionStart must survive an unresolvable mode plane.

    The git-enforcer install (`_install_git_hooks`) runs AFTER the mode-plane
    block in `main()`. An exception escaping that block therefore takes the
    repository's git-level H-01/H-02 backstop — the one that closes
    `--no-verify` (ADR-0015) — with it, SILENTLY: the hook is simply never
    written, and nothing in the session says so. Losing a mode is a papercut;
    losing the enforcer is a security regression, so the mode plane is never
    allowed to be the thing that prevents it.

    Direction of the fallback is `arbiter` (gates ON) per ADR-0030: a failed
    transition INTO dangerous mode is safe, a failed transition OUT of it is
    not.
    """

    def _run_dormant(self):
        """`run()` in a repo with no arbiter frontmatter, returning stderr.

        Dormant deliberately: `main()` exits at the activation gate, which sits
        BELOW the mode-plane block and above the enforcer install, so this
        isolates the guard from every later concern (statusline healing, the
        install itself, the startup-state emitters) while still executing the
        real `main()` rather than a rehearsal of it.
        """
        root = _fresh_repo()
        prev = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = root   # no git spawn for project_root
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    ss.run(_RaisingModeRootHost())
        finally:
            if prev is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = prev
        return raised.exception.code, err.getvalue()

    def test_a_raising_mode_plane_does_not_abort_session_start(self):
        code, _err = self._run_dormant()
        self.assertIn(code, (0, None),
                      "a mode-plane failure aborted SessionStart before the enforcer install")

    def test_the_failure_is_announced_rather_than_swallowed(self):
        """A silently-absent mode plane is indistinguishable from a working one.

        The breadcrumb is what makes "mode never flips on this host" a
        diagnosable condition instead of a mystery, and it must name the
        posture the session actually fell back to.
        """
        _code, err = self._run_dormant()
        self.assertIn("mode plane unavailable", err)
        self.assertIn(ARBITER, err, "the breadcrumb must name the posture it fell back to")


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
