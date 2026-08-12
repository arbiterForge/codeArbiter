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
import ast
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
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


def _git():
    """The real git, resolved once. `_githooks.install` needs a genuine
    repository, so these tests cannot fake one."""
    found = shutil.which("git")
    if not found:
        raise unittest.SkipTest("git is unavailable")
    return found


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
        # Parsed, not grepped. A line-based regex misses `marker_root(\n)`, so
        # the exact call it forbids could be reintroduced across two lines and
        # this guard would report clean — a green check measuring nothing.
        tree = ast.parse((PYSRC / "session-start.py").read_text(encoding="utf-8"))
        offenders = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) == "marker_root"
                 or getattr(node.func, "attr", None) == "marker_root")
            and not node.args and not node.keywords
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
        # stdin is SUPPLIED, never inherited. `main()` reads it for the hook
        # payload, and a non-tty stdin that nobody closes (a CI runner, a
        # backgrounded shell) makes that read block forever — a test that hangs
        # depending on how it was launched is worse than one that fails.
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({
            "hook_event_name": "SessionStart", "session_id": "guard", "cwd": root}))
        try:
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    ss.run(_RaisingModeRootHost())
        finally:
            sys.stdin = saved_stdin
            ss._STDIN_PAYLOAD = None   # the payload cache is module-level
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

    def test_the_enforcer_is_actually_installed_in_an_enabled_repository(self):
        """The claim in this class's name, proved where it can be false.

        The dormant fixture above exits at the activation gate, which sits
        ABOVE the install — so both tests there would pass even if a mode-plane
        failure did prevent hook installation. They pin "startup survives"; only
        this pins "the backstop is there afterwards", which is the property
        that matters. Needs a real git repository, because `_githooks.install`
        writes into `.git/hooks/`.
        """
        root = _fresh_repo()
        subprocess.run([_git(), "init", "-q", "-b", "feature/mode-guard"], cwd=root,
                       check=True, capture_output=True)
        with open(os.path.join(root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")

        prev = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = root
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({
            "hook_event_name": "SessionStart", "session_id": "enabled-guard", "cwd": root}))
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    ss.run(_RaisingModeRootHost())
                except SystemExit as exc:
                    self.assertIn(exc.code, (0, None))
        finally:
            sys.stdin = saved_stdin
            ss._STDIN_PAYLOAD = None
            if prev is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = prev

        hooks = os.path.join(root, ".git", "hooks")
        for name in ("pre-commit", "pre-push"):
            self.assertTrue(
                os.path.isfile(os.path.join(hooks, name)),
                "a raising mode plane cost the repository its {} enforcer; "
                ".git/hooks holds {}".format(name, sorted(os.listdir(hooks))))


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



class TestSeenAnchorIsSessionKeyed(unittest.TestCase):
    """The anchor must answer "has THIS session started before?", per session.

    It was a single repo-global scalar, so two live sessions in one repository
    overwrote each other's record: A starts (seen=A), B starts (seen=B), then
    A compacts and reads `mode_seen == False` — the compaction clears A's live
    mode and mints an `exit` row for a mode A never exited.

    That is the SAME observable failure the anchor was introduced to fix; it
    was merely moved from "a concurrent session owns the legacy marker" to
    "a concurrent session started at all". The mode marker itself is keyed by
    session id, and this record has to be keyed the same way or it cannot
    answer a per-session question.
    """

    def test_a_concurrent_session_start_does_not_erase_our_anchor(self):
        root = _fresh_repo()
        ss.clear_mode_marker(root, host_name="claude", session_id="A")
        _modelib.write_mode("A", "dangerous", root=root)
        ss.clear_mode_marker(root, host_name="claude", session_id="B")   # B starts
        ss.clear_mode_marker(root, host_name="claude", session_id="A")   # A compacts
        mode, _ = _modelib.current_mode("A", root=root)
        self.assertEqual(mode, "dangerous",
                         "a second session's SessionStart erased the first session's anchor")

    def test_many_interleaved_sessions_each_keep_their_own_mode(self):
        root = _fresh_repo()
        for sid, mode in (("A", "dangerous"), ("B", "ops"), ("C", "dangerous")):
            ss.clear_mode_marker(root, host_name="claude", session_id=sid)
            _modelib.write_mode(sid, mode, root=root)
        for sid in ("C", "A", "B"):
            ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        self.assertEqual(_modelib.current_mode("A", root=root)[0], "dangerous")
        self.assertEqual(_modelib.current_mode("B", root=root)[0], "ops")
        self.assertEqual(_modelib.current_mode("C", root=root)[0], "dangerous")

    def test_an_unseen_session_is_still_cleared(self):
        """The keying must not turn the anchor into "always seen"."""
        root = _fresh_repo()
        _modelib.write_mode("never-started", "dangerous", root=root)
        ss.clear_mode_marker(root, host_name="claude", session_id="never-started")
        self.assertEqual(_modelib.current_mode("never-started", root=root)[0], ARBITER)

    def test_an_anchor_clobbered_by_a_concurrent_start_is_retried(self):
        """The anchor write is a read-modify-write, and a lost update is not
        benign: the next compaction finds no record, clears a live mode, and
        mints an exit row for a mode the user never left.

        Set up so the ANCHOR is the only thing that can save the mode. A
        DIFFERENT live session owns the legacy marker, which forces `is_owner`
        False and skips the owner branch's early return — otherwise
        `dev-session-owner.json` preserves the mode on its own and the test
        passes no matter what the anchor does. (It did, before this setup:
        the first version of this test survived reverting the fix.)
        """
        root = _fresh_repo()
        open(_legacy_marker(root), "w").close()
        ss._write_dev_session_owner(root, "another-live-session", time.time())

        original = ss.write_text_atomic
        calls = {"n": 0}

        def clobbering(path, text, **kwargs):
            original(path, text, **kwargs)
            if os.path.basename(path) == "mode-session-seen.json":
                calls["n"] += 1
                if calls["n"] == 1:                      # a concurrent start lands after us
                    original(path, json.dumps({"someone-else": 1.0}), **kwargs)

        ss.write_text_atomic = clobbering
        try:
            ss.clear_mode_marker(root, host_name="claude", session_id="mine")
        finally:
            ss.write_text_atomic = original
        self.assertGreaterEqual(calls["n"], 1, "the clobber never fired — this measures nothing")

        _modelib.write_mode("mine", "dangerous", root=root)
        ss.clear_mode_marker(root, host_name="claude", session_id="mine")   # compaction
        self.assertEqual(_modelib.current_mode("mine", root=root)[0], "dangerous",
                         "a clobbered anchor let a compaction clear a live mode")


class TestCorruptModeStateBlocksTheLegacyMigration(unittest.TestCase):
    """Unreadable state is not evidence that there is nothing to preserve.

    `_read_mode_state` returns `{}` WITH a diagnostic for a corrupt or
    unreadable file. Reading that as "no entry" let the legacy conversion write
    `dangerous` over a user who had explicitly returned to `arbiter` — gates
    off, on the strength of state nobody could read. Absence is the only clean
    "nothing to convert over".
    """

    def test_a_corrupt_mode_file_does_not_trigger_the_conversion(self):
        root = _fresh_repo()
        sid = "owner"
        open(_legacy_marker(root), "w").close()
        ss._write_dev_session_owner(root, sid, time.time())
        with open(_modelib.mode_marker_path(root=root), "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        self.assertEqual(_modelib.current_mode(sid, root=root)[0], ARBITER,
                         "an unreadable mode file was treated as consent to re-arm dangerous")


class TestLegacyConversionRespectsAnExplicitMode(unittest.TestCase):
    """A live `dev-active` marker must not re-arm a mode the user left.

    The conversion writes `dangerous` unconditionally whenever the legacy
    marker is live. Marker removal is best-effort, so a marker that survived
    one pass is still live on the next: an owner who flipped back to `arbiter`
    mid-session then has gates turned OFF again by a compaction — with no
    operator action and no audit row. The comment above it claimed the
    mode-plane entry "stays untouched either way"; the call did the opposite.

    The conversion is a MIGRATION, so it applies only where there is nothing
    to migrate over: the arbiter default.
    """

    def _live_marker_owned_by(self, root, sid):
        open(_legacy_marker(root), "w").close()
        ss._write_dev_session_owner(root, sid, time.time())

    def test_a_flip_back_to_arbiter_survives_the_conversion(self):
        root = _fresh_repo()
        sid = "owner"
        self._live_marker_owned_by(root, sid)
        _modelib.write_mode(sid, ARBITER, root=root)   # the user flipped back: gates ON
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        self.assertEqual(_modelib.current_mode(sid, root=root)[0], ARBITER,
                         "a legacy marker silently re-armed dangerous mode")

    def test_an_explicit_ops_mode_is_not_rewritten_to_dangerous(self):
        root = _fresh_repo()
        sid = "owner"
        self._live_marker_owned_by(root, sid)
        _modelib.write_mode(sid, "ops", root=root)
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        self.assertEqual(_modelib.current_mode(sid, root=root)[0], "ops")

    def test_the_migration_still_happens_when_there_is_nothing_to_preserve(self):
        """The conversion must keep working for its actual case."""
        root = _fresh_repo()
        sid = "owner"
        self._live_marker_owned_by(root, sid)
        ss.clear_mode_marker(root, host_name="claude", session_id=sid)
        self.assertEqual(_modelib.current_mode(sid, root=root)[0], "dangerous",
                         "a live legacy marker must still migrate to the mode plane")


if __name__ == "__main__":
    unittest.main()
