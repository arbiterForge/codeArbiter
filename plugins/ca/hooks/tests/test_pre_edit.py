"""Behavioral coverage for pre-edit.py's two BLOCK guards.

pre-edit.py enforces two PreToolUse(Edit) gates that, prior to this file, had
ZERO negative-path tests (the HIGH would-block finding from the 2026-06-13
checkpoint):

  H-05  — the .codearbiter audit logs (overrides.log, triage.log) are
          append-only. An Edit is permitted only when it is a pure append
          (new_string.startswith(old_string)); any other Edit rewrites history
          and is blocked (exit 2).
  H-11  — ADR files under .codearbiter/decisions/NNN-*.md may be edited only
          via /adr, which drops a fresh `adr-authoring-active` marker. Missing
          or stale (>30 min) marker => block (exit 2).

These are CHARACTERIZATION tests: they pin the CURRENT, correct behavior of
pre-edit.py (the guards already work; the gap was that nothing exercised them).
They drive the hook exactly as the hook layer does — Claude-Code-shaped hook
JSON piped to pre-edit.py on stdin, cwd'd into a throwaway arbiter-enabled git
repo — mirroring .github/scripts/test_hook_guards.py and the subprocess style
that the pre-* guards are designed to be tested with.

Stdlib only (project policy: hooks and their tests carry no dependencies).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_EDIT = os.path.join(HOOKS, "pre-edit.py")


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _PreEditFixture(unittest.TestCase):
    """An arbiter-enabled git repo on a feature branch, with seeded audit logs
    and one ADR. project_root() resolves to this repo because the hook is run
    cwd'd into it; arbiter_active() passes because CONTEXT.md opts in."""

    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "feat/work", self.root], self._tmp.name)
        _git(["config", "user.email", "harness@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)
        self.ca = os.path.join(self.root, ".codearbiter")
        self.ddir = os.path.join(self.ca, "decisions")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.ddir)
        self._write(os.path.join(self.ca, "CONTEXT.md"), self.ARBITER)
        self._write(os.path.join(self.ca, "overrides.log"),
                    "[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n")
        self._write(os.path.join(self.ca, "triage.log"),
                    "[2026-01-01T00:00:00Z] | finding-1 | open\n")
        self._write(os.path.join(self.ca, "sprint-log.md"),
                    "# Sprint log\n\n## SD-01 seed\n- chosen: X\n")
        self._write(os.path.join(self.ddir, "0001-seed.md"),
                    "# ADR-0001\nseed decision\n")

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers ------------------------------------------------------------
    def _write(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _disable_arbiter(self):
        # No frontmatter at all -> dormant repo (arbiter_active() False).
        self._write(os.path.join(self.ca, "CONTEXT.md"), "# ctx\nno frontmatter\n")

    def _set_marker(self, age_seconds=0):
        os.makedirs(self.markers, exist_ok=True)
        m = os.path.join(self.markers, "adr-authoring-active")
        with open(m, "w", encoding="utf-8") as f:
            f.write("active\n")
        if age_seconds:
            past = time.time() - age_seconds
            os.utime(m, (past, past))
        return m

    def run_edit(self, file_path, old_string, new_string, replace_all=False):
        ti = {
            "file_path": file_path,
            "old_string": old_string,
            "new_string": new_string,
        }
        if replace_all:
            ti["replace_all"] = True
        payload = json.dumps({"tool_name": "Edit", "tool_input": ti})
        return _sh([sys.executable, PRE_EDIT], self.root, input=payload)

    def run_multiedit(self, file_path, edits):
        payload = json.dumps({
            "tool_name": "MultiEdit",
            "tool_input": {"file_path": file_path, "edits": edits},
        })
        return _sh([sys.executable, PRE_EDIT], self.root, input=payload)

    def assertBlocked(self, res, tag):
        self.assertEqual(res.returncode, 2,
                         f"expected BLOCK (exit 2); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")
        self.assertIn(tag, res.stderr,
                      f"expected {tag} tag in stderr; got {res.stderr.strip()[:300]!r}")

    def assertAllowed(self, res):
        self.assertEqual(res.returncode, 0,
                         f"expected ALLOW (exit 0); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")
        self.assertNotIn("BLOCKED", res.stderr)


class TestH05AppendOnly(_PreEditFixture):
    """H-05: the audit logs are append-only — non-append Edits are blocked."""

    def test_rewrite_of_overrides_log_is_blocked(self):
        # new_string does NOT start with old_string -> history rewrite -> block.
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string="[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n",
            new_string="[2026-01-01T00:00:00Z] | BY: attacker | GATE: none | REASON: tampered\n",
        )
        self.assertBlocked(res, "H-05")

    def test_deletion_from_overrides_log_is_blocked(self):
        # Replacing the only line with empty text deletes history -> block.
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string="[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n",
            new_string="",
        )
        self.assertBlocked(res, "H-05")

    def test_rewrite_of_triage_log_is_blocked(self):
        res = self.run_edit(
            os.path.join(self.ca, "triage.log"),
            old_string="[2026-01-01T00:00:00Z] | finding-1 | open\n",
            new_string="[2026-01-01T00:00:00Z] | finding-1 | suppressed\n",
        )
        self.assertBlocked(res, "H-05")

    def test_pure_append_to_overrides_log_is_allowed(self):
        # new_string EXTENDS old_string (startswith) -> legitimate /override append.
        old = "[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n"
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string=old,
            new_string=old + "[2026-02-02T00:00:00Z] | BY: harness | GATE: H-07 | REASON: ok\n",
        )
        self.assertAllowed(res)

    def test_rewrite_of_sprint_log_is_blocked(self):
        # /sprint auto-decisions in sprint-log.md are an append-only audit
        # artifact — a non-append Edit rewrites the decision record -> block.
        res = self.run_edit(
            os.path.join(self.ca, "sprint-log.md"),
            old_string="## SD-01 seed\n- chosen: X\n",
            new_string="## SD-01 seed\n- chosen: Y (tampered)\n",
        )
        self.assertBlocked(res, "H-05")

    def test_pure_append_to_sprint_log_is_allowed(self):
        old = "# Sprint log\n\n## SD-01 seed\n- chosen: X\n"
        res = self.run_edit(
            os.path.join(self.ca, "sprint-log.md"),
            old_string=old,
            new_string=old + "\n## SD-02\n- chosen: Z\n",
        )
        self.assertAllowed(res)

    def test_empty_old_string_on_audit_log_is_blocked(self):
        # migration-003: `new.startswith("")` is ALWAYS True, so an Edit with an
        # empty old_string slipped the append-only check entirely — it could
        # prepend/replace arbitrary content on overrides.log without the gate
        # ever firing. An empty old_string can never be a verifiable pure append;
        # it must block outright.
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string="",
            new_string="[2099-01-01T00:00:00Z] | BY: attacker | GATE: none | REASON: forged\n",
        )
        self.assertBlocked(res, "H-05")

    def test_empty_old_string_on_sprint_log_is_blocked(self):
        res = self.run_edit(
            os.path.join(self.ca, "sprint-log.md"),
            old_string="",
            new_string="## SD-99 forged\n- chosen: tampered\n",
        )
        self.assertBlocked(res, "H-05")

    def test_windows_backslash_path_still_triggers_h05_branch(self):
        # norm_path() folds backslashes to forward slashes, so a Windows-style
        # path to overrides.log must still take the H-05 branch and block a
        # non-append edit. The fixture file is addressed via backslashes.
        win_path = self.ca.replace("/", "\\") + "\\overrides.log"
        res = self.run_edit(
            win_path,
            old_string="[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n",
            new_string="totally different content\n",
        )
        self.assertBlocked(res, "H-05")

    # -- reliability-003 (#172): tail-anchor the append check ----------------

    def test_mid_file_insertion_on_overrides_log_is_blocked(self):
        # old_string is a real line in the file, but the file has MORE content
        # after it, so old_string is NOT the file's actual trailing content —
        # new.startswith(old) is satisfied, but the resulting edit would insert
        # content between the two existing lines rather than truly append.
        seed = "[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n"
        tail = "[2026-01-02T00:00:00Z] | BY: harness | GATE: none | REASON: second\n"
        self._write(os.path.join(self.ca, "overrides.log"), seed + tail)
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string=seed,
            new_string=seed + "[2099-01-01T00:00:00Z] | BY: attacker | GATE: none | REASON: injected\n",
        )
        self.assertBlocked(res, "H-05")

    def test_replace_all_on_overrides_log_is_blocked(self):
        # replace_all is never a verifiable append, even when new.startswith(old)
        # holds for a tail-shaped old_string — reject outright.
        old = "[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n"
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string=old,
            new_string=old + "extra\n",
            replace_all=True,
        )
        self.assertBlocked(res, "H-05")

    def test_replace_all_multi_site_suffix_rewrite_on_overrides_log_is_blocked(self):
        # A replace_all with an old_string occurring multiple times rewrites
        # every occurrence, not just the tail — must be rejected outright.
        line = "REPEATED\n"
        self._write(os.path.join(self.ca, "overrides.log"), line + line)
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string=line,
            new_string=line + "suffix\n",
            replace_all=True,
        )
        self.assertBlocked(res, "H-05")

    def test_tail_anchored_append_to_overrides_log_is_allowed(self):
        # old_string genuinely IS the file's current trailing content — a
        # legitimate append must still pass.
        current = "[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n"
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string=current,
            new_string=current + "[2026-02-02T00:00:00Z] | BY: harness | GATE: H-07 | REASON: ok\n",
        )
        self.assertAllowed(res)

    def test_mid_file_insertion_on_sprint_log_is_blocked(self):
        head = "# Sprint log\n\n"
        entry1 = "## SD-01 seed\n- chosen: X\n"
        entry2 = "## SD-02\n- chosen: Y\n"
        self._write(os.path.join(self.ca, "sprint-log.md"), head + entry1 + entry2)
        res = self.run_edit(
            os.path.join(self.ca, "sprint-log.md"),
            old_string=entry1,
            new_string=entry1 + "## SD-99 injected\n- chosen: forged\n",
        )
        self.assertBlocked(res, "H-05")


class TestH11AdrAuthoring(_PreEditFixture):
    """H-11: ADRs are editable only via /adr (fresh authoring marker)."""

    def _adr_path(self):
        return os.path.join(self.ddir, "0001-seed.md")

    def test_edit_without_marker_is_blocked(self):
        # No .markers/adr-authoring-active at all -> block.
        self.assertFalse(os.path.isdir(self.markers))
        res = self.run_edit(self._adr_path(),
                            old_string="seed decision\n",
                            new_string="rewritten decision\n")
        self.assertBlocked(res, "H-11")

    def test_edit_with_stale_marker_is_blocked(self):
        # Marker older than 30 min -> marker_fresh() False -> block.
        self._set_marker(age_seconds=31 * 60)
        res = self.run_edit(self._adr_path(),
                            old_string="seed decision\n",
                            new_string="rewritten decision\n")
        self.assertBlocked(res, "H-11")

    def test_edit_with_fresh_marker_is_allowed(self):
        # A fresh marker (just dropped by /adr) -> allow.
        self._set_marker(age_seconds=0)
        res = self.run_edit(self._adr_path(),
                            old_string="seed decision\n",
                            new_string="rewritten decision\n")
        self.assertAllowed(res)

    def test_edit_of_non_numeric_adr_is_blocked(self):
        # An ADR file without a numeric prefix (e.g. a draft) lives under
        # decisions/ and is still immutable-except-via-/adr. No marker -> block.
        draft = os.path.join(self.ddir, "draft.md")
        self._write(draft, "# draft ADR\nbody\n")
        res = self.run_edit(draft, old_string="body\n",
                            new_string="rewritten\n")
        self.assertBlocked(res, "H-11")

    def test_edit_of_nested_adr_is_blocked(self):
        # A nested path under decisions/ must not slip the gate either.
        nested_dir = os.path.join(self.ddir, "sub")
        os.makedirs(nested_dir, exist_ok=True)
        nested = os.path.join(nested_dir, "0001-x.md")
        self._write(nested, "# nested ADR\nbody\n")
        res = self.run_edit(nested, old_string="body\n",
                            new_string="rewritten\n")
        self.assertBlocked(res, "H-11")


class TestMultiEditGuards(_PreEditFixture):
    """MultiEdit is matched by the Edit hook and cannot express a verified pure
    append to an append-only file, so it blocks on the audit logs; on ADRs it
    obeys the same marker rule as Edit."""

    def test_multiedit_on_overrides_log_is_blocked(self):
        res = self.run_multiedit(
            os.path.join(self.ca, "overrides.log"),
            [{"old_string": "seed", "new_string": "seed\nmore"}])
        self.assertBlocked(res, "H-05")

    def test_multiedit_on_sprint_log_is_blocked(self):
        res = self.run_multiedit(
            os.path.join(self.ca, "sprint-log.md"),
            [{"old_string": "log", "new_string": "log\nmore"}])
        self.assertBlocked(res, "H-05")

    def test_multiedit_on_adr_without_marker_is_blocked(self):
        res = self.run_multiedit(
            self.ddir and os.path.join(self.ddir, "0001-seed.md"),
            [{"old_string": "seed decision", "new_string": "rewritten"}])
        self.assertBlocked(res, "H-11")

    def test_multiedit_on_unrelated_path_is_allowed(self):
        src = os.path.join(self.root, "src")
        os.makedirs(src, exist_ok=True)
        f = os.path.join(src, "app.py")
        self._write(f, "print('hi')\n")
        res = self.run_multiedit(
            f, [{"old_string": "hi", "new_string": "bye"}])
        self.assertAllowed(res)


class TestH18ContextEdit(_PreEditFixture):
    """#159: an Edit to CONTEXT.md may not drop `arbiter: enabled`."""

    def _ctx(self):
        return os.path.join(self.ca, "CONTEXT.md")

    def test_edit_disabling_arbiter_is_blocked(self):
        res = self.run_edit(self._ctx(),
                            old_string="arbiter: enabled",
                            new_string="arbiter: disabled")
        self.assertBlocked(res, "H-18")

    def test_edit_removing_frontmatter_delimiter_is_blocked(self):
        # Dropping the opening '---' leaves no frontmatter -> not enabled.
        res = self.run_edit(self._ctx(),
                            old_string="---\narbiter: enabled",
                            new_string="arbiter: enabled")
        self.assertBlocked(res, "H-18")

    def test_stage_bump_keeping_arbiter_enabled_is_allowed(self):
        res = self.run_edit(self._ctx(), old_string="stage: 2", new_string="stage: 3")
        self.assertAllowed(res)


class TestH19MarkerEdit(_PreEditFixture):
    """#160: gate markers are not editable via the Edit tools."""

    def test_edit_security_gate_marker_is_blocked(self):
        m = os.path.join(self.markers, "security-gate-passed")
        os.makedirs(self.markers, exist_ok=True)
        self._write(m, "olddigest\n")
        res = self.run_edit(m, old_string="olddigest\n", new_string="olddigest\nforged\n")
        self.assertBlocked(res, "H-19")

    def test_multiedit_marker_is_blocked(self):
        m = os.path.join(self.markers, "migration-gate-passed")
        os.makedirs(self.markers, exist_ok=True)
        self._write(m, "d\n")
        res = self.run_multiedit(m, [{"old_string": "d", "new_string": "d\nx"}])
        self.assertBlocked(res, "H-19")


class TestNotebookEditGuard(_PreEditFixture):
    """NotebookEdit is matched by the Edit hook (#159/#160 defense-in-depth): a
    protected `.codearbiter` target is refused; a real notebook passes."""

    def run_notebook(self, notebook_path):
        payload = json.dumps({
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": notebook_path, "new_source": "print(1)"},
        })
        return _sh([sys.executable, PRE_EDIT], self.root, input=payload)

    def test_notebookedit_targeting_context_is_blocked(self):
        self.assertBlocked(self.run_notebook(os.path.join(self.ca, "CONTEXT.md")), "H-18")

    def test_notebookedit_targeting_audit_log_is_blocked(self):
        self.assertBlocked(self.run_notebook(os.path.join(self.ca, "overrides.log")), "H-05")

    def test_notebookedit_targeting_marker_is_blocked(self):
        self.assertBlocked(
            self.run_notebook(os.path.join(self.markers, "security-gate-passed")), "H-19")

    def test_notebookedit_on_real_notebook_is_allowed(self):
        nb = os.path.join(self.root, "analysis.ipynb")
        self._write(nb, "{}")
        self.assertAllowed(self.run_notebook(nb))


class TestPreEditAllowPaths(_PreEditFixture):
    """Cases where neither guard should fire."""

    def test_disabled_arbiter_is_noop(self):
        # Dormant repo: the hook must exit 0 before any guard runs, even for an
        # edit that would otherwise be an H-05 history rewrite.
        self._disable_arbiter()
        res = self.run_edit(
            os.path.join(self.ca, "overrides.log"),
            old_string="seed line\n",
            new_string="rewritten\n",
        )
        self.assertAllowed(res)

    def test_unrelated_path_is_allowed(self):
        # An edit to ordinary source touches neither guard branch.
        src = os.path.join(self.root, "src")
        os.makedirs(src, exist_ok=True)
        f = os.path.join(src, "app.py")
        self._write(f, "print('hello')\n")
        res = self.run_edit(f, old_string="print('hello')\n",
                            new_string="print('goodbye')\n")
        self.assertAllowed(res)


if __name__ == "__main__":
    unittest.main()
