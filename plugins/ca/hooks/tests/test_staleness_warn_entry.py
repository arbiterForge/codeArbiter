"""CONFIRM-09: prune-transcript.py's UserPromptSubmit entry point wires
_hooklib.staleness_warning into a real WARN — via _hooklib.warn(), which is
non-blocking and also writes the durable gate-events.log record
(observability-001, #186), so the two features are proven together here.

WARN-only contract: the hook-mode entry point (staleness_check / main())
must NEVER raise and must NEVER change prune-transcript.py's hook-mode exit
code (always 0), regardless of whether a flow is stale.

#437 (mode-plane-deterministic-flip): repointed from the retired
'dev-active' presence marker onto the mode plane's `{session_id: mode}`
JSON marker (`.codearbiter/.markers/mode`) — `_hooklib._STALE_FLOWS`'s
'dev' entry was renamed to 'mode' and gained a content check (a session
must be recorded as something OTHER than 'arbiter' to count as "active";
presence of the file alone is not enough, since it is a persistent map
that legitimately keeps existing with only-arbiter entries long after
every non-arbiter session has flipped back). Both directions are kept
here, matching AC-36: a stale non-arbiter session warns, a stale
all-arbiter marker never does — the negative arm is what would catch a
matcher that (wrongly) fires on file presence alone, the retired
dev-active marker's exact shape.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

_SCRIPT = os.path.join(_HOOKS_DIR, "prune-transcript.py")
_spec = importlib.util.spec_from_file_location("prune_transcript", _SCRIPT)
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

import _hooklib  # noqa: E402
from _helpers import redirect_home, restore_home  # noqa: E402


def _write_mode_marker(cad, entries, age_seconds=0):
    """Seed `<cad>/.markers/mode` with `entries` ({session_id: mode}) and
    back-date its mtime — the #437 mode plane's direct successor to the
    retired `dev-active` presence marker this file used to `_touch`."""
    path = os.path.join(cad, ".markers", "mode")
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(entries))
    t = time.time() - age_seconds
    os.utime(path, (t, t))


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self._tmp.name)
        self.root = os.path.join(self._tmp.name, "repo")
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)
        with open(os.path.join(self.cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")

    def tearDown(self):
        restore_home(self._home)
        self._tmp.cleanup()

    def payload(self):
        return {"hook_event_name": "UserPromptSubmit", "cwd": self.root}


class TestStalenessCheckFunction(_Fixture):
    def test_stale_dangerous_mode_emits_a_warn_and_durable_record(self):
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        buf = io.StringIO()
        # _hooklib.warn()'s durable-sink half resolves its own root via
        # project_root() (CLAUDE_PROJECT_DIR, else a git spawn) independently
        # of the payload["cwd"] staleness_check reads its flow state from — as
        # every production hook invocation does, pin it to the same repo.
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}):
            with mock.patch.object(sys, "stderr", buf):
                pt.staleness_check(self.payload())
        self.assertIn("codeArbiter hook:", buf.getvalue())
        self.assertIn("CONFIRM-09", buf.getvalue())
        with open(os.path.join(self.cad, "gate-events.log"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("WARN", log)
        self.assertIn("CONFIRM-09", log)

    def test_stale_ops_mode_emits_a_warn_too(self):
        # AC-36 covers every non-arbiter mode, not just 'dangerous'.
        _write_mode_marker(self.cad, {"sess-x": "ops"}, age_seconds=3600)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}):
            with mock.patch.object(sys, "stderr", buf):
                pt.staleness_check(self.payload())
        self.assertIn("CONFIRM-09", buf.getvalue())

    def test_stale_arbiter_only_mode_marker_never_warns(self):
        # AC-36 negative arm: the marker file EXISTS and IS old, but every
        # session recorded in it is 'arbiter'. This is the case that would
        # catch a matcher keyed on file PRESENCE alone — the retired
        # dev-active boolean marker's exact shape, and the failure mode
        # that would make this WARN fire on every repo that has ever used
        # the mode plane at all, arbiter included.
        _write_mode_marker(self.cad, {"sess-x": "arbiter"}, age_seconds=3600)
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            pt.staleness_check(self.payload())
        self.assertEqual(buf.getvalue(), "")

    def test_fresh_dangerous_mode_emits_nothing(self):
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=5)
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            pt.staleness_check(self.payload())
        self.assertEqual(buf.getvalue(), "")
        self.assertFalse(os.path.isfile(os.path.join(self.cad, "gate-events.log")))

    def test_no_active_flow_emits_nothing(self):
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            pt.staleness_check(self.payload())
        self.assertEqual(buf.getvalue(), "")

    def test_dormant_repo_never_warns_even_when_stale(self):
        # arbiter NOT enabled -> the check must not fire at all.
        with open(os.path.join(self.cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: disabled\n---\n# ctx\n")
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            pt.staleness_check(self.payload())
        self.assertEqual(buf.getvalue(), "")

    def test_subdir_cwd_still_resolves_active_repo_via_host_seam(self):
        # #264 (reliability-006): a session whose cwd is a repo SUBDIRECTORY
        # must still resolve the repo root through the host seam
        # (CLAUDE_PROJECT_DIR first) rather than reading payload["cwd"]
        # verbatim — else `<subdir>/.codearbiter/CONTEXT.md` (which doesn't
        # exist) reads as not-enabled and the WARN silently never fires.
        subdir = os.path.join(self.root, "src", "nested")
        os.makedirs(subdir)
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": subdir}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}):
            with mock.patch.object(sys, "stderr", buf):
                pt.staleness_check(payload)
        self.assertIn("codeArbiter hook:", buf.getvalue())
        self.assertIn("CONFIRM-09", buf.getvalue())

    def test_linked_worktree_mode_marker_is_found_via_marker_root_resolution(self):
        """FIXED (#437, mode-plane-deterministic-flip, Lane E — the same
        root-resolution-split ruling applied to session-start.py's
        clear_mode_marker, extended to this second site once Lane F found
        it). Was `@unittest.expectedFailure` / KNOWN DEFECT; flipped to a
        real passing assertion now that `staleness_check` resolves its root
        via `_hooklib.get_host().marker_root(payload)` instead of
        `project_root(payload)`.

        `staleness_check` used to resolve a LINKED WORKTREE's own checkout.
        But the mode marker itself is written and read at `marker_root`
        (`_modelib.mode_marker_path`), which ESCALATES to the MAIN checkout
        in a linked worktree (#604) — `.codearbiter/.markers/` is
        gitignored, so a linked worktree's own checkout never has a fresh
        copy of it. In a linked worktree these used to be two DIFFERENT
        directories, so a genuinely stale non-arbiter session recorded in
        the main checkout's mode marker was silently invisible to this WARN
        when prune-transcript.py ran from the worktree — the CONFIRM-09
        staleness signal went quiet exactly where #604 says it must not,
        and this repo runs worktree agents routinely.
        """
        worktree_root = os.path.join(self._tmp.name, "worktree")
        subprocess.run(["git", "init", "-q", "-b", "main", self.root],
                       check=True, timeout=30)
        subprocess.run(["git", "-C", self.root, "config", "user.email", "test@example.com"],
                       check=True, timeout=30)
        subprocess.run(["git", "-C", self.root, "config", "user.name", "Test"],
                       check=True, timeout=30)
        subprocess.run(["git", "-C", self.root, "add", ".codearbiter/CONTEXT.md"],
                       check=True, timeout=30)
        subprocess.run(
            ["git", "-C", self.root, "-c", "core.hooksPath=",
             "-c", "commit.gpgSign=false", "commit", "-qm", "seed"],
            check=True, timeout=30)
        subprocess.run(
            ["git", "-C", self.root, "worktree", "add", "-q", "-b", "test-linked",
             worktree_root], check=True, timeout=30)
        # The mode marker itself lives at `self.cad` (the MAIN checkout,
        # matching marker_root's real escalation target).
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": worktree_root}
        buf = io.StringIO()
        # No CLAUDE_PROJECT_DIR: forces project_root(payload) through its
        # payload-cwd leg. Git names the linked checkout as project_root;
        # marker_root must then escalate to the main checkout.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            with mock.patch.object(sys, "stderr", buf):
                pt.staleness_check(payload)
        self.assertIn("CONFIRM-09", buf.getvalue())

    def test_never_raises_when_hooklib_import_fails(self):
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        with mock.patch.dict(sys.modules, {"_hooklib": None}):
            try:
                pt.staleness_check(self.payload())
            except Exception as e:  # noqa: BLE001
                self.fail(f"staleness_check raised: {e!r}")


class TestHookModeNeverBlocks(_Fixture):
    """The UserPromptSubmit entry point (main(), hook-mode branch) must always
    return 0 — a stale-flow WARN is surfaced, never a gate."""

    def _run_main(self, payload):
        # Pin CLAUDE_PROJECT_DIR to the tmp fixture: _hooklib.warn()'s durable-
        # sink half resolves its OWN root independently of payload["cwd"] (see
        # test_stale_dangerous_mode_emits_a_warn_and_durable_record above) —
        # every production hook invocation pins this env var, and leaving it
        # unset here would let project_root()'s git-rev-parse fallback
        # resolve to whatever repo happens to contain the test run, not the
        # fixture.
        raw = __import__("json").dumps(payload)
        env_patch = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root})
        with env_patch, mock.patch.object(sys, "stdin", io.StringIO(raw)):
            return pt.main([])

    def test_stale_flow_present_still_returns_0(self):
        _write_mode_marker(self.cad, {"sess-x": "dangerous"}, age_seconds=3600)
        rc = self._run_main(self.payload())
        self.assertEqual(rc, 0)

    def test_no_transcript_path_still_returns_0(self):
        rc = self._run_main(self.payload())
        self.assertEqual(rc, 0)

    def test_staleness_check_exception_does_not_break_hook_mode(self):
        # staleness_check() catches broadly internally; prove the wiring
        # stays fail-open end-to-end by making the underlying detector raise.
        with mock.patch.object(_hooklib, "staleness_warning", side_effect=RuntimeError("boom")):
            rc = self._run_main(self.payload())
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
