#!/usr/bin/env python3
"""Unit tests for core/pysrc/prompt-submit.py — the mode-plane prompt-seam
interceptor (#437, mode-plane-deterministic-flip, Lane B, T-27..T-39).

Loads the CANONICAL core/pysrc copy directly (never a vendored plugins/*
copy — sync-core.py has not necessarily run when this suite executes; the
vendored copies are Lane Z's concern, GR-2/GR-3). A tiny synthetic plugin
root (arbiter.md / includes/safety-core.md / includes/dangerous-mode.md)
is used for injection tests so they stay independent of Lane D's exact
persona prose — only the composition MECHANISM is under test here.

Stdlib + unittest only. `python .github/scripts/test_prompt_submit.py`.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CORE_PYSRC = os.path.join(REPO, "core", "pysrc")

sys.path.insert(0, CORE_PYSRC)
import hostapi  # noqa: E402
import _hooklib  # noqa: E402
import _modelib  # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load(os.path.join(CORE_PYSRC, "prompt-submit.py"), "prompt_submit_under_test")


class _CodexHost(hostapi.Host):
    """Minimal Codex-shaped host for these tests — only `.name` matters here;
    the real translation logic (apply_patch etc.) is Codex-adapter territory,
    not this module's."""
    name = "codex"


# --------------------------------------------------------------------- fixtures

SAFETY_CORE_TEXT = "# Safety core\n\nSAFETY-CORE-MARK: residual invariants.\n"
ARBITER_BODY_TEXT = "# codeArbiter\n\nARBITER-MODE-MARK: orchestrated work.\n"
DANGEROUS_BODY_TEXT = "# dangerous\n\nDANGEROUS-MODE-MARK: gates-off posture.\n"


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.name
        ca_dir = os.path.join(self.root, ".codearbiter")
        os.makedirs(ca_dir)
        with open(os.path.join(ca_dir, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n")

        self.plugin_root = os.path.join(self.root, "_plugin")
        os.makedirs(os.path.join(self.plugin_root, "includes"))
        with open(os.path.join(self.plugin_root, "arbiter.md"), "w", encoding="utf-8") as f:
            f.write(ARBITER_BODY_TEXT)
        with open(os.path.join(self.plugin_root, "includes", "safety-core.md"),
                  "w", encoding="utf-8") as f:
            f.write(SAFETY_CORE_TEXT)
        with open(os.path.join(self.plugin_root, "includes", "dangerous-mode.md"),
                  "w", encoding="utf-8") as f:
            f.write(DANGEROUS_BODY_TEXT)

        self._env_patch = {
            "CLAUDE_PROJECT_DIR": self.root,
            "CLAUDE_PLUGIN_ROOT": self.plugin_root,
        }
        self._saved_env = {k: os.environ.get(k) for k in self._env_patch}
        os.environ.update(self._env_patch)
        _hooklib.reset_host()
        _hooklib._reset_root_cache()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _hooklib.reset_host()
        _hooklib._reset_root_cache()
        self._td.cleanup()

    def invoke(self, payload, host=None):
        """Run prompt-submit.py's run(host) against `payload` on stdin.
        Returns (rc, stdout, stderr)."""
        host = host if host is not None else hostapi.Host()
        old_stdin = sys.stdin
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(payload))
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = ps.run(host)
        finally:
            sys.stdin = old_stdin
        return rc, out.getvalue(), err.getvalue()

    def overrides_log(self):
        path = os.path.join(self.root, ".codearbiter", "overrides.log")
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as f:
            return f.read()

    def mode_marker_bytes(self):
        path = _modelib.mode_marker_path(root=self.root)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()


def _ups(prompt, session_id="s1", transcript_path=None):
    return {"hook_event_name": "UserPromptSubmit", "prompt": prompt,
            "session_id": session_id, "cwd": None,
            "transcript_path": transcript_path or ""}


def _precompact(session_id="s1"):
    return {"hook_event_name": "PreCompact", "session_id": session_id}


# --------------------------------------------------------------------- T-27/28/29

class TestClaudeFlipAndReport(_Fixture):
    def test_exact_token_flips_exit2_named_stderr_mode_written(self):
        rc, out, err = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc, 2)
        self.assertIn("dangerous", err)
        self.assertEqual(out, "")
        mode, diag = _modelib.current_mode("s1", root=self.root)
        self.assertEqual(mode, "dangerous")
        self.assertIsNone(diag)
        self.assertIn("MODE: dangerous enter", self.overrides_log())

    def test_substring_does_not_flip_reaches_model_mode_unchanged(self):
        before = self.mode_marker_bytes()
        rc, out, err = self.invoke(_ups("please run mode --dangerous now"))
        self.assertEqual(rc, 0)
        after = self.mode_marker_bytes()
        self.assertEqual(before, after)  # byte-unchanged (both None here)
        mode, _ = _modelib.current_mode("s1", root=self.root)
        self.assertEqual(mode, "arbiter")
        # Positive control on the SAME fixture: the exact token DOES flip —
        # proves the substring assertion above isn't vacuous.
        rc_second, _out2, _err2 = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc_second, 2)
        mode2, _ = _modelib.current_mode("s1", root=self.root)
        self.assertEqual(mode2, "dangerous")

    def test_bare_mode_reports_current_and_all_legal_values_writes_nothing(self):
        before = self.mode_marker_bytes()
        rc, out, err = self.invoke(_ups("mode"))
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("arbiter", err)
        for m in _modelib.MODES:
            self.assertIn(m, err)
        self.assertEqual(self.mode_marker_bytes(), before)
        self.assertEqual(self.overrides_log(), "")

    def test_flip_to_already_active_mode_is_noop_still_blocks(self):
        self.invoke(_ups("mode --dangerous"))
        log_after_first = self.overrides_log()
        rc, out, err = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc, 2)
        self.assertIn("already", err)
        self.assertEqual(self.overrides_log(), log_after_first)  # no new row


# --------------------------------------------------------------------- dormancy

class TestDormancy(_Fixture):
    def setUp(self):
        super().setUp()
        # Overwrite CONTEXT.md to a DORMANT (non-opted-in) repo.
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"),
                  "w", encoding="utf-8") as f:
            f.write("dormant fixture, no frontmatter\n")

    def test_dormant_repo_flip_token_never_flips_never_blocks(self):
        rc, out, err = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIsNone(self.mode_marker_bytes())

    def test_dormant_repo_ordinary_prompt_injects_nothing(self):
        rc, out, err = self.invoke(_ups("hello"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


# --------------------------------------------------------------------- T-31/32/33/35

class TestInjection(_Fixture):
    def test_composed_persona_is_safety_core_plus_current_mode_previous_absent(self):
        self.invoke(_ups("mode --dangerous"))  # flip turn: no injection
        rc, out, err = self.invoke(_ups("do something"))
        self.assertEqual(rc, 0)
        self.assertIn("SAFETY-CORE-MARK", out)
        self.assertIn("DANGEROUS-MODE-MARK", out)
        self.assertNotIn("ARBITER-MODE-MARK", out)
        self.assertIn(_modelib.PERSONA_SENTINEL, out)

    def test_second_turn_same_session_mode_gen_injects_nothing_new_session_does(self):
        rc1, out1, _ = self.invoke(_ups("first"))
        self.assertIn("SAFETY-CORE-MARK", out1)
        rc_second, out2, _ = self.invoke(_ups("second"))
        self.assertEqual(rc_second, 0)
        self.assertEqual(out2, "")
        rc3, out3, _ = self.invoke(_ups("first in a new session", session_id="s2"))
        self.assertIn("SAFETY-CORE-MARK", out3)

    def test_after_flip_next_turn_injects_the_new_body(self):
        rc0, out0, _ = self.invoke(_ups("warm up"))
        self.assertIn("ARBITER-MODE-MARK", out0)
        self.invoke(_ups("mode --dangerous"))
        rc, out, _ = self.invoke(_ups("after flip"))
        self.assertIn("DANGEROUS-MODE-MARK", out)
        self.assertNotIn("ARBITER-MODE-MARK", out)

    def test_unbacked_mode_falls_back_to_arbiter_with_diagnostic(self):
        # Write "dangerous" DIRECTLY to the mode marker, bypassing flip() —
        # so overrides.log carries NO matching "MODE: dangerous enter" row
        # (AC-11: the injector must refuse to compose it).
        _modelib.write_mode("s1", "dangerous", root=self.root)
        mode, _ = _modelib.current_mode("s1", root=self.root)
        self.assertEqual(mode, "dangerous")  # precondition: marker really says dangerous
        rc, out, err = self.invoke(_ups("go"))
        self.assertEqual(rc, 0)
        self.assertIn("ARBITER-MODE-MARK", out)
        self.assertNotIn("DANGEROUS-MODE-MARK", out)
        self.assertIn("not-ledger-backed", err)


# --------------------------------------------------------------------- T-34 (compaction)

class TestCompactionGeneration(_Fixture):
    def test_precompact_bump_forces_reinjection(self):
        rc1, out1, _ = self.invoke(_ups("first"))
        self.assertIn("SAFETY-CORE-MARK", out1)
        rc_second, out2, _ = self.invoke(_ups("second"))
        self.assertEqual(out2, "")  # deduped, as TestInjection also proves

        rc_pc, out_pc, err_pc = self.invoke(_precompact())
        self.assertEqual(rc_pc, 0)
        self.assertEqual(out_pc, "")  # PreCompact never blocks, never prints

        rc3, out3, _ = self.invoke(_ups("after compaction"))
        self.assertIn("SAFETY-CORE-MARK", out3)  # re-injected

    def test_precompact_on_dormant_repo_does_not_bump(self):
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"),
                  "w", encoding="utf-8") as f:
            f.write("dormant\n")
        gen_before = ps._read_compaction_generation(self.root, "s1")
        self.invoke(_precompact())
        gen_after = ps._read_compaction_generation(self.root, "s1")
        self.assertEqual(gen_before, gen_after)

    def test_hooks_json_registers_prompt_submit_on_precompact(self):
        # Pins the registration itself (advisor finding): without this, the
        # bump path above is dead code no host ever calls, and the compaction
        # hole reopens silently behind a passing unit test.
        path = os.path.join(REPO, "plugins", "ca", "hooks", "hooks.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        groups = cfg["hooks"].get("PreCompact", [])
        cmds = [h["command"] for g in groups for h in g["hooks"]]
        self.assertTrue(any("prompt-submit.py" in c for c in cmds),
                         "prompt-submit.py must be registered on PreCompact "
                         "(Claude) so the compaction generation ever advances")


# --------------------------------------------------------------------- T-36

class TestClaudeHooksJsonRegistration(unittest.TestCase):
    def setUp(self):
        path = os.path.join(REPO, "plugins", "ca", "hooks", "hooks.json")
        with open(path, encoding="utf-8") as f:
            self.cfg = json.load(f)

    def test_user_prompt_submit_two_entry_pair_present(self):
        groups = self.cfg["hooks"]["UserPromptSubmit"]
        matches = [g for g in groups
                   if any("prompt-submit.py" in h["command"] for h in g["hooks"])]
        self.assertEqual(len(matches), 1)
        cmds = [h["command"] for h in matches[0]["hooks"]]
        self.assertEqual(len(cmds), 2)
        fallback = [c for c in cmds if "||" in c]
        primary = [c for c in cmds if c not in fallback]
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(fallback), 1)
        self.assertIn("python3", fallback[0])


class TestFallbackPairIdempotent(_Fixture):
    def test_both_slot_occupants_exit_2_on_the_same_turn(self):
        # Simulates the two hooks.json entries both actually running against
        # the same session/prompt (AC-7's idempotency clause) — the SECOND
        # occupant must still block (exit 2), even though the flip already
        # landed on the first.
        rc1, _out1, err1 = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc1, 2)
        self.assertIn("flipped", err1)
        rc_second, _out2, err2 = self.invoke(_ups("mode --dangerous"))
        self.assertEqual(rc_second, 2)
        self.assertIn("already", err2)


# --------------------------------------------------------------------- T-38/39 (Codex)

class TestCodexEnvelope(_Fixture):
    def test_flip_emits_exactly_the_seven_schema_keys_no_permission_decision(self):
        rc, out, err = self.invoke(_ups("mode --dangerous"), host=_CodexHost())
        self.assertEqual(rc, 0)  # Codex signals block via the JSON body, not exit code
        env = json.loads(out)
        self.assertEqual(set(env.keys()), ps.CODEX_ENVELOPE_KEYS)
        self.assertNotIn("permissionDecision", env)
        self.assertEqual(env["decision"], "block")
        self.assertFalse(env["continue"])
        mode, _ = _modelib.current_mode("s1", root=self.root)
        self.assertEqual(mode, "dangerous")

    def test_bare_mode_report_also_uses_the_seven_key_block_shape(self):
        rc, out, err = self.invoke(_ups("mode"), host=_CodexHost())
        env = json.loads(out)
        self.assertEqual(set(env.keys()), ps.CODEX_ENVELOPE_KEYS)
        self.assertNotIn("permissionDecision", env)

    def test_injection_envelope_has_no_permission_decision_and_carries_context(self):
        rc, out, err = self.invoke(_ups("go"), host=_CodexHost())
        self.assertEqual(rc, 0)
        env = json.loads(out)
        self.assertNotIn("permissionDecision", env)
        self.assertTrue(env["continue"])
        ctx = env["hookSpecificOutput"]["additionalContext"]
        self.assertIn("SAFETY-CORE-MARK", ctx)
        self.assertIn("ARBITER-MODE-MARK", ctx)

    def test_codex_hooks_json_single_entry_with_command_windows_and_limit(self):
        path = os.path.join(REPO, "plugins", "ca-codex", "hooks", "hooks.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        groups = cfg["hooks"]["UserPromptSubmit"]
        matches = [g for g in groups
                   if any("prompt-submit.py" in h["command"] for h in g["hooks"])]
        self.assertEqual(len(matches), 1)
        hooks = matches[0]["hooks"]
        self.assertEqual(len(hooks), 1)  # R-2: Codex = single OS-native handler
        entry = hooks[0]
        self.assertIn("commandWindows", entry)
        self.assertIn("additionalContextLimit", entry)
        self.assertGreater(entry["additionalContextLimit"], 2500)  # explicit, not the default

    def test_codex_has_no_precompact_registration(self):
        path = os.path.join(REPO, "plugins", "ca-codex", "hooks", "hooks.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertNotIn("PreCompact", cfg["hooks"])


class TestCodexContextLimit(unittest.TestCase):
    """T-39 / AC-28 — pure _compose_persona() unit tests: no host, no fixture
    filesystem needed."""

    def test_each_real_mode_body_fits_the_explicit_limit(self):
        safety = SAFETY_CORE_TEXT * 5   # exercise real-ish sizes without depending on Lane D prose
        for body in (ARBITER_BODY_TEXT * 40, DANGEROUS_BODY_TEXT * 40):
            composed, truncated = ps._compose_persona(
                safety, body, limit_tokens=ps.CODEX_ADDITIONAL_CONTEXT_LIMIT)
            self.assertFalse(truncated)
            self.assertLessEqual(len(composed) // 4 + 1, ps.CODEX_ADDITIONAL_CONTEXT_LIMIT)

    def test_over_limit_truncates_body_never_safety_core(self):
        safety = SAFETY_CORE_TEXT
        body = "X" * 100000  # deliberately oversized
        composed, truncated = ps._compose_persona(safety, body, limit_tokens=50)
        self.assertTrue(truncated)
        self.assertIn("SAFETY-CORE-MARK", composed)      # safety-core survives whole
        self.assertIn(ps._ELLIPSIS, composed)              # visible, not a silent drop
        est = (len(composed) + 3) // 4
        self.assertLessEqual(est, 50 + 5)  # small proxy-rounding slack, still bounded

    def test_real_composed_arbiter_persona_measured_against_the_default_would_overflow(self):
        # Documents WHY R-4 requires an explicit limit rather than accepting
        # Codex's ~2500-token default, using the actually-shipped bodies
        # (when present) rather than the synthetic fixture text above.
        real_plugin_root = os.path.join(REPO, "plugins", "ca")
        safety_path = os.path.join(real_plugin_root, "includes", "safety-core.md")
        arbiter_path = os.path.join(real_plugin_root, "arbiter.md")
        if not (os.path.isfile(safety_path) and os.path.isfile(arbiter_path)):
            self.skipTest("generated safety-core.md/arbiter.md not present in this checkout")
        with open(safety_path, encoding="utf-8") as f:
            safety = f.read()
        with open(arbiter_path, encoding="utf-8") as f:
            body = f.read()
        composed, truncated = ps._compose_persona(safety, body)  # no limit — measure raw
        raw_tokens = (len(composed) + 3) // 4
        self.assertGreater(raw_tokens, 2500,
                            "if this ever drops under 2500 the R-4 rationale comment "
                            "in prompt-submit.py should be revisited")
        composed2, truncated2 = ps._compose_persona(
            safety, body, limit_tokens=ps.CODEX_ADDITIONAL_CONTEXT_LIMIT)
        self.assertFalse(truncated2, "the explicit limit must comfortably fit today's "
                                      "real arbiter persona")


# --------------------------------------------------------------------- T-37 (doctor.py)

class TestDoctorHookScripts(unittest.TestCase):
    def test_core_doctor_lists_prompt_submit(self):
        with open(os.path.join(CORE_PYSRC, "doctor.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('"prompt-submit.py"', text)


if __name__ == "__main__":
    unittest.main()
