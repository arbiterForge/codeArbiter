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

    def run_edit(self, file_path, old_string, new_string):
        payload = json.dumps({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
            },
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
