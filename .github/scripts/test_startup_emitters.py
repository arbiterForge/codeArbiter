#!/usr/bin/env python3
"""Tests for Lane E's slice of #437 (mode-plane-deterministic-flip): T-41..
T-50 — persona injection removed from SessionStart, the mode-plane clearing/
migration contract (AC-4/AC-41/AC-42/AC-35), the startup-block decomposition
into per-mode composable emitters (AC-30/31/32), the NEEDS-TRIAGE root-
resolution split fix, and the AC-26 persona-pin propagation into the pruner.

Imports `core/pysrc/session-start.py` directly via importlib (it is not a
valid module name — hyphenated) and `_modelib`/`_prunelib`/`_prunepolicy`
straight from `core/pysrc`, mirroring `test_modelib.py`'s own documented
precedent: this suite never depends on the vendored `plugins/*/hooks/`
copies `sync-core.py` produces, so it is [LL].

Run: python .github/scripts/test_startup_emitters.py
Regenerate the golden startup fixtures (T-45's explicit, never-bare flag):
    python .github/scripts/test_startup_emitters.py --regen
"""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORE = os.path.join(REPO_ROOT, "core", "pysrc")
FIXTURES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")
HOOKS_TESTS = os.path.join(REPO_ROOT, "plugins", "ca", "hooks", "tests")

sys.path.insert(0, CORE)
sys.path.insert(0, HOOKS_TESTS)  # _helpers: user-state isolation, make_transcript

import _modelib  # noqa: E402
import _prunelib  # noqa: E402
import _prunepolicy as _policy  # noqa: E402
from _helpers import (  # noqa: E402
    durable_plugin_copy,
    isolate_user_state,
    make_transcript,
    release_user_state,
)

_spec = importlib.util.spec_from_file_location(
    "session_start_lane_e", os.path.join(CORE, "session-start.py")
)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def setUpModule():
    global _USER_STATE
    _USER_STATE = isolate_user_state()


def tearDownModule():
    release_user_state(_USER_STATE)


# ---------------------------------------------------------------------------
# Shared fixtures: a fake, spelling-distinct host (precedent: test_session_
# start.py's TestStartupInstructionsHostAware._FakeHost) — proves emitted
# text is produced via host.cmd_ref()/host.command_noun, never a hardcoded
# claude-shaped string that happens to look host-aware.
# ---------------------------------------------------------------------------
class _FakeHost(M.hostapi.Host):
    name = "fakehost"
    command_noun = "fake-command"

    def cmd_ref(self, name):
        return "$$fake-" + name


def _repo(tmp, initialized=True, mode=None, session_id=None):
    """A minimal `.codearbiter` repo under `tmp`. `mode`/`session_id`, when
    given, seed the mode marker directly (bypassing flip()/prompt-submit.py,
    which is Lane B's surface)."""
    cad = os.path.join(tmp, ".codearbiter")
    os.makedirs(cad, exist_ok=True)
    body = "<!--INITIALIZED-->\nstage: 2\n" if initialized else "_stub_\n"
    with open(os.path.join(cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
        f.write(f"---\narbiter: enabled\n---\n\n{body}")
    if mode is not None and session_id is not None:
        _modelib.write_mode(session_id, mode, root=tmp)
    return tmp


def _overrides_log(root):
    return os.path.join(root, ".codearbiter", "overrides.log")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# T-41 / AC-27 — SessionStart injects NO persona and still emits the
# startup-state block. Exercised end-to-end through run(fake_host) so this is
# not a source-grep: a persona-injection block reintroduced anywhere in
# main() would make this RED.
# ---------------------------------------------------------------------------
class TestPersonaRemovedFromSessionStart(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        _repo(self.repo, initialized=True)
        self._env = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.repo})
        self._env.start()
        self._stdin = mock.patch.object(sys.stdin, "isatty", return_value=True)
        self._stdin.start()

    def tearDown(self):
        self._stdin.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _run(self):
        host = _FakeHost()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch("sys.exit"), \
                mock.patch.object(M, "spawn_background_fetch"), \
                mock.patch.object(M, "spawn_background_update_refresh"), \
                mock.patch.object(M, "heal_statusline_wiring", return_value=False):
            M.run(host)
        return out.getvalue()

    def test_no_persona_text_but_startup_state_present(self):
        text = self._run()
        # A real persona body would name ORCHESTRATOR/arbiter section markers
        # (§0/§1 headers) or the sentinel this feature introduces (T-16) — none
        # of that belongs on SessionStart's stdout any more.
        self.assertNotIn("§0", text)
        self.assertNotIn(_modelib.PERSONA_SENTINEL, text)
        self.assertNotIn("ORCHESTRATOR", text)
        self.assertIn("=== codeArbiter startup state ===", text)
        self.assertIn("host: fakehost", text)
        self.assertIn("stage: 2", text)


# ---------------------------------------------------------------------------
# T-42 / AC-4 — the mode file is cleared at SessionStart. clear_mode_marker
# clears THIS session's own entry unless it is recognised as the resuming
# owner; a session with no entry, or one this hook has never seen, is a
# no-op. Direct unit tests of the function (not the whole hook), per GR-4.
# ---------------------------------------------------------------------------
class TestClearModeMarker(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".codearbiter"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_live_dangerous_entry_is_removed_next_read_resolves_arbiter(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")

    def test_clearing_a_non_arbiter_entry_appends_a_mode_exit_row(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        log = _read(_overrides_log(self.root))
        self.assertEqual(log.count("MODE: dangerous exit"), 1)

    def test_clearing_an_already_arbiter_session_appends_nothing(self):
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-new", now=1000.0)
        self.assertEqual(_read(_overrides_log(self.root)), "")

    def test_no_session_id_is_a_pure_noop(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id=None, now=1000.0)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous", "no identity to clear against -- must not touch state")

    def test_the_recognised_owner_resuming_does_not_clear_its_own_entry(self):
        # First invocation: session_id has no entry yet -> records itself as
        # the owner. A flip (Lane B's surface) then sets it to dangerous
        # directly, mirroring how prompt-submit.py would.
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        # Second invocation, SAME session_id (a resume/compaction re-fire of
        # SessionStart) -- must be recognised as the owner and leave mode
        # untouched (AC-25's compaction-survival precondition).
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1500.0)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous",
                         "the owner's own resume/compaction must not clear its own mode")
        self.assertEqual(_read(_overrides_log(self.root)), "",
                         "no exit row for a session that never actually left dangerous")

    def test_a_different_unrecognised_session_id_does_not_touch_a_first_sessions_entry(self):
        _modelib.write_mode("sess-A", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-A", now=1000.0)
        # A later, genuinely different session starts.
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-B", now=2000.0)
        mode_b, _ = _modelib.current_mode("sess-B", root=self.root)
        self.assertEqual(mode_b, "arbiter", "a fresh session_id must resolve arbiter")
        # sess-A's entry is a residual (documented, not force-closed by a
        # different session) -- still recorded, unaffected by B's clear.
        mode_a, _ = _modelib.current_mode("sess-A", root=self.root)
        self.assertEqual(mode_a, "arbiter",
                         "sess-A's OWN clear already reset it before B ever ran")


# ---------------------------------------------------------------------------
# T-43 / AC-35 — no emitted overrides.log line ever names a deleted command.
# Asserted ON THE EMITTED LINE, never by a source grep (a grep would miss
# the hardcoded `except` fallback the old code carried at session-
# start.py:~906 — this drives BOTH arms: a working host and a host whose
# cmd_ref/name resolution itself fails).
# ---------------------------------------------------------------------------
class TestNoDeletedCommandNameStampedIntoOverridesLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".codearbiter"))

    def tearDown(self):
        self._tmp.cleanup()

    def _emitted_close_lines(self):
        log = _read(_overrides_log(self.root))
        return [ln for ln in log.splitlines() if "MODE:" in ln and "exit" in ln]

    def test_working_host_resolution_names_no_deleted_command(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        lines = self._emitted_close_lines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn("/ca:arbiter", lines[0])
        self.assertNotIn("arbiter", lines[0].lower().split("mode:")[0] + "")

    def test_host_name_resolution_failure_still_names_no_deleted_command(self):
        # host_name=None forces the get_host() resolution arm inside
        # clear_mode_marker; simulate that resolution itself failing (the
        # exact arm a source grep of the OLD `except: arbiter_ref =
        # "/ca:arbiter"` literal would miss).
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        with mock.patch.object(M, "get_host", side_effect=RuntimeError("no host")):
            M.clear_mode_marker(self.root, host_name=None, session_id="sess-1", now=1000.0)
        lines = self._emitted_close_lines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn("/ca:arbiter", lines[0])
        self.assertIn("HOST: unknown", lines[0])

    def test_no_deleted_command_name_appears_anywhere_in_any_emitted_line(self):
        # Broader net: sweep every plausible deleted-command spelling across
        # BOTH close paths this file can mint (clear_mode_marker; migration
        # mints none by design, asserted separately below).
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        log = _read(_overrides_log(self.root))
        for dead in ("/ca:arbiter", "/ca:dev", "{{CMD:arbiter}}", "{{CMD:dev}}"):
            self.assertNotIn(dead, log)


# ---------------------------------------------------------------------------
# T-44 / AC-30 — each startup emitter is individually callable and its
# output is a pure function of its own inputs (captured via stdout redirect,
# consistent with this file's pre-existing print-directly convention).
# ---------------------------------------------------------------------------
class TestEmittersIndividuallyCallable(unittest.TestCase):
    def _lines(self, fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*a, **kw)
        return buf.getvalue().splitlines()

    def test_emit_banner_is_host_and_mode_only(self):
        self.assertEqual(
            self._lines(M.emit_banner, "claude", "arbiter"),
            ["host: claude", "mode: arbiter"],
        )
        self.assertEqual(
            self._lines(M.emit_banner, "codex", "dangerous"),
            ["host: codex", "mode: dangerous"],
        )

    def test_emit_stage_reads_only_ctx_text(self):
        self.assertEqual(self._lines(M.emit_stage, "stage: 7\n"), ["stage: 7"])
        self.assertEqual(self._lines(M.emit_stage, "no stage here\n"), ["stage: —"])

    def test_emit_confirm_nn_none_vs_zero_vs_blocking(self):
        self.assertEqual(self._lines(M.emit_confirm_nn, None), [])
        self.assertEqual(self._lines(M.emit_confirm_nn, "nothing here\n"), ["open questions: 0"])
        lines = self._lines(M.emit_confirm_nn, "- CONFIRM-01: pick one\n")
        self.assertEqual(lines[0], "BLOCKING questions (CONFIRM-NN): 1 — must resolve before "
                                    "dependent work proceeds:")
        self.assertIn("CONFIRM-01", lines[1])

    def test_emit_task_summary_is_pure_given_an_injected_today(self):
        ot = "- [ ] 2026-08-01 a task\n"
        first = self._lines(M.emit_task_summary, ot, today=datetime.date(2026, 8, 12))
        second = self._lines(M.emit_task_summary, ot, today=datetime.date(2026, 8, 12))
        self.assertEqual(first, second, "same inputs must yield identical output")
        self.assertEqual(self._lines(M.emit_task_summary, None), [])

    def test_emit_provenance_and_update_notices_are_single_line_passthroughs(self):
        self.assertEqual(self._lines(M.emit_provenance_drift, ""), [])
        self.assertEqual(self._lines(M.emit_provenance_drift, "drift!"), ["drift!"])
        self.assertEqual(self._lines(M.emit_update_notice, ""), [])
        self.assertEqual(self._lines(M.emit_update_notice, "update!"), ["update!"])

    def test_emit_trailer_is_host_driven_not_hardcoded(self):
        lines = self._lines(M.emit_trailer, _FakeHost())
        self.assertEqual(len(lines), 1)
        self.assertIn("fake-command", lines[0])
        self.assertIn("$$fake-commands", lines[0])

    def test_emit_not_initialized_is_mode_aware_arbiter_names_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self._lines(M.emit_not_initialized, tmp, _FakeHost(), "arbiter")
        self.assertTrue(any("$$fake-decompose" in ln or "$$fake-create-context" in ln for ln in lines))
        self.assertTrue(any("$$fake-commands" in ln for ln in lines))

    def test_emit_not_initialized_non_arbiter_names_no_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self._lines(M.emit_not_initialized, tmp, _FakeHost(), "dangerous")
        joined = "\n".join(lines)
        self.assertNotIn("$$fake-", joined, "a mode with no commands must name none")
        self.assertIn("NOT INITIALIZED", joined)


# ---------------------------------------------------------------------------
# T-45 / AC-31 — golden fixture parity for the arbiter emitter set. Bare run
# REFUSES on a mismatch (never silently regenerates); --regen requires the
# explicit flag.
# ---------------------------------------------------------------------------
def _driver(fixture, host):
    """Reproduce main()'s arbiter/non-arbiter startup-state emitter sequence
    (banner .. trailer), EXCLUDING the daily briefing (git-dependent, already
    covered by the pre-existing standup-briefing test suite this lane does
    not own). Returns the captured stdout lines."""
    buf = io.StringIO()
    mode = fixture["mode"]
    with contextlib.redirect_stdout(buf):
        print("=== codeArbiter startup state ===")
        M.emit_banner(fixture["host_name"], mode)
        if not M.INITIALIZED_RE.search(fixture["ctx_text"]):
            M.emit_not_initialized(fixture.get("root", "."), host, mode)
            return buf.getvalue().splitlines()
        M.emit_stage(fixture["ctx_text"])
        M.emit_confirm_nn(fixture.get("oq_text"))
        today = datetime.date.fromisoformat(fixture["today"]) if fixture.get("today") else None
        M.emit_task_summary(fixture.get("ot_text"), today=today)
        M.emit_provenance_drift(fixture.get("drift_line") or "")
        M.emit_update_notice(fixture.get("update_line") or "")
        if mode == _modelib.MODES[0]:
            M.emit_trailer(host)
    return buf.getvalue().splitlines()


def _check_or_regen_fixture(path, regen=False):
    """(ok, message). In compare mode (regen=False), NEVER writes: a mismatch
    is reported and the file is left byte-unchanged (T-45's "bare run
    refuses"). In regen mode, recomputes `expected_lines` from the driver's
    actual output and overwrites the file."""
    with open(path, encoding="utf-8") as f:
        fixture = json.load(f)
    actual = _driver(fixture, _FakeHost())
    if regen:
        fixture["expected_lines"] = actual
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fixture, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return True, "regenerated"
    expected = fixture.get("expected_lines")
    if actual != expected:
        return False, (
            f"fixture mismatch at {path}\n  expected: {expected!r}\n  actual:   {actual!r}"
        )
    return True, "match"


class TestStartupFixtureGolden(unittest.TestCase):
    def test_arbiter_fixture_matches_pinned_lines(self):
        path = os.path.join(FIXTURES_DIR, "startup-arbiter.json")
        ok, msg = _check_or_regen_fixture(path, regen=False)
        self.assertTrue(ok, msg)

    def test_dangerous_fixture_matches_pinned_lines(self):
        path = os.path.join(FIXTURES_DIR, "startup-dangerous.json")
        ok, msg = _check_or_regen_fixture(path, regen=False)
        self.assertTrue(ok, msg)

    def test_bare_run_refuses_on_a_mismatched_fixture_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "startup-wrong.json")
            with open(os.path.join(FIXTURES_DIR, "startup-arbiter.json"), encoding="utf-8") as f:
                fixture = json.load(f)
            fixture["expected_lines"] = ["this is deliberately wrong"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fixture, f)
            before = _read(path)

            ok, _msg = _check_or_regen_fixture(path, regen=False)
            self.assertFalse(ok, "a mismatched fixture must be reported, not silently accepted")
            after = _read(path)
            self.assertEqual(before, after, "AC-31: a bare run must NEVER overwrite the fixture")

    def test_regen_flag_repairs_the_same_mismatched_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "startup-wrong.json")
            with open(os.path.join(FIXTURES_DIR, "startup-arbiter.json"), encoding="utf-8") as f:
                fixture = json.load(f)
            fixture["expected_lines"] = ["this is deliberately wrong"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fixture, f)

            ok, _msg = _check_or_regen_fixture(path, regen=True)
            self.assertTrue(ok)
            ok2, msg2 = _check_or_regen_fixture(path, regen=False)
            self.assertTrue(ok2, msg2)


# ---------------------------------------------------------------------------
# T-46 / AC-32 — a non-arbiter startup omits the trailer, the catalog
# reference, and the standup reference, and still emits host/stage/mode; the
# SAME fixture (mode flipped) in arbiter emits all three omitted lines.
# ---------------------------------------------------------------------------
class TestNonArbiterOmitsTrailerCatalogAndStandup(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(FIXTURES_DIR, "startup-arbiter.json"), encoding="utf-8") as f:
            self.base = json.load(f)

    def test_arbiter_emits_trailer_catalog_and_standup_reference(self):
        lines = _driver(self.base, _FakeHost())
        joined = "\n".join(lines)
        self.assertIn("Present this state, then await a", joined, "trailer")
        self.assertIn("$$fake-commands", joined, "catalog reference")
        self.assertIn("host: claude", joined)
        self.assertIn("stage: 3", joined)
        self.assertIn("mode: arbiter", joined)

    def test_dangerous_omits_trailer_and_catalog_reference_keeps_host_stage_mode(self):
        fixture = dict(self.base, mode="dangerous")
        lines = _driver(fixture, _FakeHost())
        joined = "\n".join(lines)
        self.assertNotIn("Present this state, then await a", joined, "trailer must be omitted")
        self.assertNotIn("$$fake-commands", joined, "catalog reference must be omitted")
        self.assertIn("host: claude", joined)
        self.assertIn("stage: 3", joined)
        self.assertIn("mode: dangerous", joined)

    def test_confirm_nn_stays_pinned_on_in_dangerous_mode_too(self):
        fixture = dict(self.base, mode="dangerous")
        lines = _driver(fixture, _FakeHost())
        joined = "\n".join(lines)
        self.assertIn("BLOCKING questions (CONFIRM-NN)", joined)

    def test_standup_reference_never_appears_outside_arbiter_via_main(self):
        # The daily-briefing emitter (the ONLY place {standup} is referenced)
        # is gated on `mode == arbiter` in main() itself -- proven directly
        # against main()'s own gate rather than the excerpted driver above.
        #
        # clear_mode_marker only PRESERVES a non-arbiter entry for a session
        # it recognises as the returning owner (see TestClearModeMarker), so
        # the realistic sequence is: first SessionStart registers ownership
        # (mode is still arbiter at that point); the flip to dangerous then
        # happens mid-session via prompt-submit.py (Lane B's surface, not
        # touched here); a SECOND SessionStart (e.g. after compaction) is
        # what this test actually exercises against main()'s own gate.
        with tempfile.TemporaryDirectory() as tmp:
            _repo(tmp, initialized=True)
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmp}):
                M.clear_mode_marker(tmp, host_name="claude", session_id="sess-1", now=1000.0)
                _modelib.write_mode("sess-1", "dangerous", root=tmp)

                out = io.StringIO()
                fake_stdin = io.StringIO(json.dumps({"session_id": "sess-1"}))
                with contextlib.redirect_stdout(out), \
                        mock.patch.object(sys, "stdin", fake_stdin), \
                        mock.patch("sys.exit"), \
                        mock.patch.object(M, "spawn_background_fetch"), \
                        mock.patch.object(M, "spawn_background_update_refresh"), \
                        mock.patch.object(M, "heal_statusline_wiring", return_value=False):
                    M.run(_FakeHost())
        self.assertIn("mode: dangerous", out.getvalue(), "the flip must have survived the resume")
        self.assertNotIn("$$fake-standup", out.getvalue())
        self.assertNotIn("daily briefing", out.getvalue())


# ---------------------------------------------------------------------------
# T-47 / AC-41 — a pre-existing dev-active marker converts to dangerous
# exactly once and is removed; a second run after a flip to arbiter does not
# resurrect it.
# ---------------------------------------------------------------------------
class TestMigrateDevActiveMarker(unittest.TestCase):
    """`clear_mode_marker` (T-42/T-47 merged, see its module docstring) is
    the SessionStart-time settlement pass for both concerns. These tests
    drive its dev-active-migration half specifically.

    CONVERSION (the is_owner branch) requires session_id to already be the
    RECOGNISED owner -- realistic when an older build (still running /dev)
    already wrote the owner record for this session_id and the plugin is
    then upgraded mid-session (a resume/compaction re-fires SessionStart
    under the new code). A session_id seen for the FIRST time ever, even
    with a live marker, is NOT yet "the owner" -- see
    test_a_first_ever_encounter_force_closes_rather_than_converts."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.markers = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(self.markers)
        self.legacy = os.path.join(self.markers, "dev-active")

    def tearDown(self):
        self._tmp.cleanup()

    def _drop_legacy(self):
        with open(self.legacy, "w", encoding="utf-8") as f:
            f.write("active\n")

    def _register_owner_then_drop_marker(self, session_id, now=1000.0):
        # First SessionStart: no marker yet -> registers session_id as the
        # owner (mirrors an older build's own clear_dev_marker call).
        M.clear_mode_marker(self.root, host_name="claude", session_id=session_id, now=now)
        self._drop_legacy()

    def test_the_recognised_owner_resuming_converts_and_removes_the_legacy_file(self):
        self._register_owner_then_drop_marker("sess-1")
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1001.0)
        self.assertFalse(os.path.isfile(self.legacy))
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous")

    def test_no_audit_row_is_minted_for_the_conversion_itself(self):
        self._register_owner_then_drop_marker("sess-1")
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1001.0)
        self.assertEqual(_read(_overrides_log(self.root)), "",
                         "the historical DEV: enter row already backs this session")

    def test_second_run_after_a_flip_to_arbiter_does_not_resurrect(self):
        self._register_owner_then_drop_marker("sess-1")
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1001.0)
        _modelib.flip("sess-1", "arbiter", root=self.root)
        # Third invocation, SAME recognised owner: legacy file is already
        # gone, so the conversion arm is a pure no-op regardless.
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1002.0)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter", "must not resurrect dangerous")

    def test_a_first_ever_encounter_force_closes_rather_than_converts(self):
        # A live marker with NO recorded owner (the genuine first-ever
        # SessionStart, or a legacy marker from before this owner-tracking
        # file existed at all) has no confirmed identity to convert to --
        # falls back to the pre-#437 force-close contract instead.
        self._drop_legacy()
        M.clear_mode_marker(self.root, host_name="claude", session_id="sess-1", now=1000.0)
        self.assertFalse(os.path.isfile(self.legacy))
        log = _read(_overrides_log(self.root))
        self.assertEqual(log.count("DEV: exit"), 1)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter", "force-close does not attribute the marker to a "
                                          "session with no confirmed ownership")

    def test_no_session_id_falls_back_to_the_legacy_force_close_path(self):
        # No identity to key a mode entry to -- restores the pre-#437
        # `clear_dev_marker` contract instead of losing the signal: force-
        # close the LEGACY marker directly via the #396 write-ahead
        # mechanism ("a marker that can NEVER be cleared is a worse failure
        # mode than one cleared too eagerly").
        self._drop_legacy()
        M.clear_mode_marker(self.root, host_name="claude", session_id=None, now=1000.0)
        self.assertFalse(os.path.isfile(self.legacy))
        log = _read(_overrides_log(self.root))
        self.assertEqual(log.count("DEV: exit"), 1)


# ---------------------------------------------------------------------------
# T-48 / AC-42 — downgrading to a pre-mode build leaves no un-closed audit
# pair and no orphaned state; the mode file is inert to that build (never
# spuriously created when there is nothing mode-plane-related to act on).
# ---------------------------------------------------------------------------
class TestDowngradeParity(unittest.TestCase):
    def test_a_clean_pre_mode_plane_repo_stays_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".codearbiter"))
            log = _overrides_log(tmp)
            with open(log, "w", encoding="utf-8") as f:
                f.write("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n"
                        "[2026-01-01T01:00:00Z] | BY: session-cleanup | DEV: exit | NOTE: —\n")
            before = _read(log)

            M.clear_mode_marker(tmp, host_name="claude", session_id="sess-1", now=1000.0)

            self.assertEqual(_read(log), before, "no spurious rows on a clean pre-mode repo")
            mode_path = _modelib.mode_marker_path(root=tmp)
            self.assertFalse(os.path.isfile(mode_path),
                             "the mode file must not be spuriously created")

    def test_pre_existing_matched_dev_pair_is_not_reopened(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".codearbiter"))
            log = _overrides_log(tmp)
            with open(log, "w", encoding="utf-8") as f:
                f.write("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n"
                        "[2026-01-01T01:00:00Z] | BY: session-cleanup | DEV: exit | NOTE: —\n")
            M.clear_mode_marker(tmp, host_name="claude", session_id="sess-1", now=1000.0)
            log_text = _read(log)
            self.assertEqual(log_text.count("DEV: enter"), 1)
            self.assertEqual(log_text.count("DEV: exit"), 1)


# ---------------------------------------------------------------------------
# NEEDS-TRIAGE root-resolution split (#437, found by Lane A, closed here) —
# `main()`'s mode-plane calls must resolve through `marker_root`, not
# `project_root`, so an `enter` row (written via `_modelib.flip`, which
# already resolves through `marker_root`) and its matching `exit`/close row
# (written by THIS file) land in the SAME overrides.log even inside a linked
# worktree. The trap: a test that only patches `marker_root` and asserts a
# PATH proves nothing (T-10 already covers that shape for _modelib itself).
# This test makes `project_root` and `marker_root` resolve to TWO DIFFERENT
# directories and proves the enter/exit PAIR lands in ONE overrides.log —
# then mutates (points the close path back at project_root) and confirms
# the split reappears, so the test is proven to actually measure the seam.
# ---------------------------------------------------------------------------
class TestRootResolutionSplitFixed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # Two DISTINCT roots -- simulating a linked worktree (`worktree_root`,
        # what project_root() would resolve to from inside the worktree) and
        # the main checkout (`main_root`, what marker_root() escalates to).
        self.worktree_root = os.path.join(self._tmp.name, "worktree")
        self.main_root = os.path.join(self._tmp.name, "main-checkout")
        os.makedirs(os.path.join(self.worktree_root, ".codearbiter"))
        os.makedirs(os.path.join(self.main_root, ".codearbiter"))

    def tearDown(self):
        self._tmp.cleanup()

    def _run_enter_then_close(self, close_root_provider):
        """Simulate a flip's `enter` row landing via marker_root (exactly as
        `_modelib.flip` resolves it), then run session-start.py's close path
        against whatever root `close_root_provider()` supplies."""
        _modelib.flip("sess-1", "dangerous", root=self.main_root)
        close_root = close_root_provider()
        M.clear_mode_marker(close_root, host_name="claude", session_id="sess-1", now=2000.0)

    def test_enter_and_exit_land_in_the_same_overrides_log_via_marker_root(self):
        with mock.patch.object(M, "project_root", return_value=self.worktree_root), \
                mock.patch.object(M, "marker_root", return_value=self.main_root):
            # The fix: session-start.py's main() resolves the mode-plane root
            # via marker_root(), exactly as flip() does -- reproduced here by
            # calling marker_root() directly (main()'s own call site), not
            # project_root().
            self._run_enter_then_close(M.marker_root)

        main_log = _read(_overrides_log(self.main_root))
        worktree_log = _read(_overrides_log(self.worktree_root))
        self.assertIn("MODE: dangerous enter", main_log)
        self.assertIn("MODE: dangerous exit", main_log)
        self.assertEqual(worktree_log, "",
                         "the enter/exit pair must NOT be split across the two roots")

    def test_mutant_using_project_root_for_the_close_path_reintroduces_the_split(self):
        # Proves the test above actually measures the seam: routing the
        # close path through project_root (the pre-fix shape) reintroduces
        # the split -- and the failure is WORSE than "the exit row lands in
        # the wrong file". `clear_mode_marker` reads `current_mode` off
        # WHATEVER root it is given; read from worktree_root, "sess-1" has
        # NO entry at all (the flip wrote it to main_root via marker_root),
        # so current_mode resolves the SAFE DEFAULT ("arbiter") and the
        # mode-is-already-arbiter branch mints NO exit row anywhere. The
        # `MODE: dangerous enter` row in main_root's log is left permanently
        # unmatched -- silent, because nothing raised and the mode-clearing
        # call still "succeeded" (returned normally, exactly as documented).
        with mock.patch.object(M, "project_root", return_value=self.worktree_root), \
                mock.patch.object(M, "marker_root", return_value=self.main_root):
            self._run_enter_then_close(M.project_root)

        main_log = _read(_overrides_log(self.main_root))
        worktree_log = _read(_overrides_log(self.worktree_root))
        self.assertIn("MODE: dangerous enter", main_log)
        self.assertNotIn("MODE: dangerous exit", main_log,
                         "the mutant never even sees this row as needing a close")
        self.assertEqual(worktree_log, "",
                         "the mutant mints NO exit row anywhere -- current_mode read off "
                         "the wrong root resolves the safe default, so clear_mode_marker "
                         "thinks there is nothing to close")

    def test_mains_own_root_resolution_calls_marker_root_not_project_root_for_mode_state(self):
        # A closer-to-production check: run main() itself (via run()) inside
        # a repo where project_root and marker_root deliberately disagree,
        # and confirm the mode-plane calls land against marker_root's answer.
        _repo(self.main_root, initialized=True, mode="dangerous", session_id="sess-1")
        _modelib._append_override_line(
            self.main_root,
            _modelib._mode_audit_line("enter", "dangerous", host_name="claude", now=1000.0),
        )
        fake_stdin = io.StringIO(json.dumps({"session_id": "sess-1"}))
        with mock.patch.object(M, "project_root", return_value=self.worktree_root), \
                mock.patch.object(M, "marker_root", return_value=self.main_root), \
                mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.worktree_root}), \
                mock.patch.object(sys, "stdin", fake_stdin), \
                mock.patch("sys.exit"), \
                mock.patch.object(M, "spawn_background_fetch"), \
                mock.patch.object(M, "spawn_background_update_refresh"), \
                mock.patch.object(M, "heal_statusline_wiring", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()):
            M.run(_FakeHost())
        # main() clears sess-1 (not the recognised owner on its first
        # observed invocation) -- the exit row it mints must land in the
        # SAME log the enter row above was seeded into: main_root's.
        main_log = _read(_overrides_log(self.main_root))
        worktree_log = _read(_overrides_log(self.worktree_root))
        self.assertIn("MODE: dangerous exit", main_log)
        self.assertNotIn("MODE:", worktree_log)


# ---------------------------------------------------------------------------
# T-49/T-50 / AC-26 — the injected persona survives every prune strategy at
# every tier, including aggressive: `_prunelib.build_index` builds a pinned
# SemanticEntry for a line carrying `PERSONA_SENTINEL` (T-50), and
# `_prunepolicy.plan_prune` retains a pinned entry regardless of the
# recent-turn boundary (T-49).
# ---------------------------------------------------------------------------
class TestPersonaPinningInPrunePolicy(unittest.TestCase):
    def test_pinned_entry_is_protected_and_excluded_from_actions_at_every_tier(self):
        entries = [
            _policy.SemanticEntry("persona", 0, "user", "message", 500, pinned=True),
            _policy.SemanticEntry("u1", 1, "user", "message", 40),
            _policy.SemanticEntry("a1", 2, "assistant", "message", 60, tool_bearing=True),
            _policy.SemanticEntry("r1", 3, "tool", "tool-result", 5000),
            _policy.SemanticEntry("u2", 4, "user", "message", 40),
            _policy.SemanticEntry("a2", 5, "assistant", "message", 60, tool_bearing=True),
        ]
        for tier in ("gentle", "standard", "aggressive"):
            policy = _policy.PrunePolicy(tier=tier, keep_recent=1, max_bytes=64)
            plan = _policy.plan_prune(entries, policy)
            self.assertIn("persona", plan.protected_ids, f"tier={tier}")
            self.assertNotIn(
                "persona", [entry_id for entry_id, _action in plan.actions], f"tier={tier}",
            )

    def test_unpinned_entry_at_the_same_ordinal_position_is_not_protected(self):
        # Mutant-killer for a test that would pass even if `pinned` were
        # never read: swap `pinned=True` for `pinned=False` on the SAME
        # entry and confirm it now falls OUTSIDE protected_ids.
        entries = [
            _policy.SemanticEntry("persona", 0, "user", "message", 500, pinned=False),
            _policy.SemanticEntry("u1", 1, "user", "message", 40),
            _policy.SemanticEntry("a1", 2, "assistant", "message", 60, tool_bearing=True),
        ]
        plan = _policy.plan_prune(entries, _policy.PrunePolicy(tier="aggressive", keep_recent=1))
        self.assertNotIn("persona", plan.protected_ids)


class TestPersonaPinningSurvivesTheRealClaudeCodec(unittest.TestCase):
    """T-50: `_prunelib.build_index` marks a line carrying PERSONA_SENTINEL
    as pinned; every strategy's guard routes through `_protected`, which
    checks BOTH the recent-turn boundary and pinned_ordinals, so the pinned
    line survives even though it sits well before `protected_from` (the
    injected persona is near the START of the transcript, not the tail)."""

    def _transcript_with_pinned_first_turn(self):
        pinned_thinking = _modelib.PERSONA_SENTINEL + "\n" + ("safety-core body " * 40)
        first = _prunelib._dumps({
            "type": "assistant", "uuid": "a0", "parentUuid": "u0",
            "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": pinned_thinking, "signature": "sig"},
                {"type": "text", "text": "ack"},
            ]},
        })
        header = _prunelib._dumps({"type": "user", "uuid": "u0", "parentUuid": None,
                                   "message": {"role": "user", "content": "go"}})
        tail = make_transcript(n_pairs=8, result_bytes=2000).decode("utf-8")
        data = (header + "\n" + first + "\n" + tail).encode("utf-8")
        return data

    def _run_aggressive(self, data, protected_fn=None):
        lines = _prunelib.load_lines(data)
        cfg = _prunelib.Config(tier="aggressive", keep_recent=1, max_bytes=64)
        index = _prunelib.build_index(lines, cfg)
        if protected_fn is not None:
            with mock.patch.object(_prunelib, "_protected", side_effect=protected_fn):
                _prunelib.apply_strategies(lines, index, cfg)
        else:
            _prunelib.apply_strategies(lines, index, cfg)
        return lines[1]  # the pinned assistant thinking-block line

    def test_pinned_line_sits_before_the_protected_tail(self):
        # Sanity precondition: if the fixture accidentally put the pinned
        # line INSIDE the protected tail, the whole test would pass for the
        # wrong reason (pins a form that cannot occur in a real transcript).
        data = self._transcript_with_pinned_first_turn()
        lines = _prunelib.load_lines(data)
        cfg = _prunelib.Config(tier="aggressive", keep_recent=1, max_bytes=64)
        index = _prunelib.build_index(lines, cfg)
        self.assertLess(1, index.protected_from,
                        "fixture precondition: the pinned line (idx 1) must be OUTSIDE "
                        "the recent-turn tail, or this test proves nothing")
        self.assertIn(1, index.pinned_ordinals)

    def test_pinned_line_survives_aggressive_reasoning_fold(self):
        data = self._transcript_with_pinned_first_turn()
        before = data.split(b"\n")[1]
        after_line = self._run_aggressive(data)
        self.assertEqual(after_line.out_bytes(), before,
                         "AC-26: the pinned persona line must be byte-unchanged at aggressive")

    def test_mutant_without_the_pin_check_strips_the_persona_line(self):
        # Restore-after-mutate, executed as a real assertion rather than a
        # manual step: patch _protected back to its PRE-T-50 shape (boundary
        # only, no pinned_ordinals check) and confirm the SAME fixture now
        # loses its thinking block -- proving the guard above is load-bearing.
        data = self._transcript_with_pinned_first_turn()
        before = data.split(b"\n")[1]

        def boundary_only(ln, index):
            return ln.idx >= index.protected_from

        after_line = self._run_aggressive(data, protected_fn=boundary_only)
        self.assertNotEqual(after_line.out_bytes(), before,
                            "mutant: without the pin check, aggressive reasoning-fold "
                            "strips the persona's thinking block -- the guard was load-bearing")



class TestQuotingTheSentinelDoesNotPinTheQuote(unittest.TestCase):
    """A tool result that merely CONTAINS the sentinel is not the persona.

    The literal ships inside this repo's own sources - `_modelib.py`,
    `prompt-submit.py`, `extension.ts` and their tests - so a Read of any of
    them, or a Grep for the sentinel itself, produced a transcript line that
    pinned permanently at every tier. The transcript kept growing while the
    pruner reported it protected, and agents here read and grep those files
    routinely, so this was reachable rather than theoretical.

    AC-26 asks for the INJECTION to be pinned, not every copy of the string.
    The injection arrives as a message; a file's contents arrive as a tool
    result, which is the discriminator used here.
    """

    def _index_for(self, obj):
        blob = (_prunelib._dumps(obj) + chr(10)).encode("utf-8")
        lines = _prunelib.load_lines(blob)
        return _prunelib.build_index(lines, _prunelib.Config(tier="aggressive", keep_recent=0))

    def test_a_tool_result_quoting_the_sentinel_is_not_pinned(self):
        quoted = "core/pysrc/_modelib.py:44:PERSONA_SENTINEL = " + _modelib.PERSONA_SENTINEL
        index = self._index_for({
            "type": "user", "uuid": "r0", "parentUuid": "a0",
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": "t0", "content": quoted,
            }]},
        })
        self.assertEqual(index.pinned_ordinals, frozenset(),
                         "grepping for the sentinel pinned the grep output forever")

    def test_the_injected_persona_message_is_still_pinned(self):
        """The narrowing must not cost the property it protects."""
        composed = "safety core body" + chr(10) * 2 + _modelib.PERSONA_SENTINEL
        index = self._index_for({
            "type": "user", "uuid": "p0", "parentUuid": None,
            "message": {"role": "user", "content": composed},
        })
        self.assertEqual(len(index.pinned_ordinals), 1)


if __name__ == "__main__":
    if "--regen" in sys.argv:
        for name in ("startup-arbiter.json", "startup-dangerous.json"):
            ok, msg = _check_or_regen_fixture(os.path.join(FIXTURES_DIR, name), regen=True)
            print(f"{name}: {msg}")
        sys.exit(0)
    unittest.main()
