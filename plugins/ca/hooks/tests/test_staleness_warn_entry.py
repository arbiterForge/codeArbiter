"""CONFIRM-09: prune-transcript.py's UserPromptSubmit entry point wires
_hooklib.staleness_warning into a real WARN — via _hooklib.warn(), which is
non-blocking and also writes the durable gate-events.log record
(observability-001, #186), so the two features are proven together here.

WARN-only contract: the hook-mode entry point (staleness_check / main())
must NEVER raise and must NEVER change prune-transcript.py's hook-mode exit
code (always 0), regardless of whether a flow is stale.
"""
import importlib.util
import io
import os
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


def _touch(path, age_seconds=0):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")
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
    def test_stale_dev_flow_emits_a_warn_and_durable_record(self):
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
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

    def test_fresh_dev_flow_emits_nothing(self):
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=5)
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
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
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
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": subdir}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}):
            with mock.patch.object(sys, "stderr", buf):
                pt.staleness_check(payload)
        self.assertIn("codeArbiter hook:", buf.getvalue())
        self.assertIn("CONFIRM-09", buf.getvalue())

    def test_never_raises_when_hooklib_import_fails(self):
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
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
        # test_stale_dev_flow_emits_a_warn_and_durable_record above) — every
        # production hook invocation pins this env var, and leaving it unset
        # here would let project_root()'s git-rev-parse fallback resolve to
        # whatever repo happens to contain the test run, not the fixture.
        raw = __import__("json").dumps(payload)
        env_patch = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root})
        with env_patch, mock.patch.object(sys, "stdin", io.StringIO(raw)):
            return pt.main([])

    def test_stale_flow_present_still_returns_0(self):
        _touch(os.path.join(self.cad, ".markers", "dev-active"), age_seconds=3600)
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
