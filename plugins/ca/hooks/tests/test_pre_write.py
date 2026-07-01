"""Behavioral coverage for pre-write.py's two BLOCK guards.

pre-write.py enforces two PreToolUse(Write) gates that, prior to this file, had
ZERO direct tests (test_write.py covers the pruner engine, not this hook):

  H-05 — the .codearbiter audit logs (overrides.log, triage.log) and the
         /sprint decision record (sprint-log.md) are append-only. A Write is a
         full overwrite -> blocked (exit 2).
  H-11 — ADR files anywhere under .codearbiter/decisions/ may be authored only
         via /adr, which drops a fresh `adr-authoring-active` marker. Missing or
         stale marker -> block (exit 2).

Same subprocess style as test_pre_edit.py: Claude-Code-shaped hook JSON piped to
pre-write.py on stdin, cwd'd into a throwaway arbiter-enabled repo. Stdlib only.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_WRITE = os.path.join(HOOKS, "pre-write.py")


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


class _PreWriteFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        self.ca = os.path.join(self.root, ".codearbiter")
        self.ddir = os.path.join(self.ca, "decisions")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.ddir)
        self._write(os.path.join(self.ca, "CONTEXT.md"), self.ARBITER)
        self._write(os.path.join(self.ca, "overrides.log"), "seed\n")
        self._write(os.path.join(self.ca, "sprint-log.md"), "# Sprint log\n")
        self._write(os.path.join(self.ddir, "0001-seed.md"), "# ADR-0001\nseed\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _disable_arbiter(self):
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

    def run_write(self, file_path, content="x\n"):
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
        })
        return _sh([sys.executable, PRE_WRITE], self.root, input=payload)

    def assertBlocked(self, res, tag):
        self.assertEqual(res.returncode, 2,
                         f"expected BLOCK (exit 2); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")
        self.assertIn(tag, res.stderr)

    def assertAllowed(self, res):
        self.assertEqual(res.returncode, 0,
                         f"expected ALLOW (exit 0); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")


class TestH05Write(_PreWriteFixture):
    def test_write_to_overrides_log_is_blocked(self):
        self.assertBlocked(self.run_write(os.path.join(self.ca, "overrides.log")), "H-05")

    def test_write_to_sprint_log_is_blocked(self):
        # sprint-log.md is the /sprint audit record — a Write overwrites it.
        self.assertBlocked(self.run_write(os.path.join(self.ca, "sprint-log.md")), "H-05")


class TestH11Write(_PreWriteFixture):
    def test_write_to_numbered_adr_without_marker_is_blocked(self):
        self.assertBlocked(
            self.run_write(os.path.join(self.ddir, "0002-new.md")), "H-11")

    def test_write_to_non_numeric_adr_without_marker_is_blocked(self):
        # A draft ADR (no numeric prefix) under decisions/ must still block.
        self.assertBlocked(self.run_write(os.path.join(self.ddir, "draft.md")), "H-11")

    def test_write_to_nested_adr_without_marker_is_blocked(self):
        self.assertBlocked(
            self.run_write(os.path.join(self.ddir, "sub", "0003-x.md")), "H-11")

    def test_write_to_adr_with_fresh_marker_is_allowed(self):
        self._set_marker(age_seconds=0)
        self.assertAllowed(self.run_write(os.path.join(self.ddir, "0002-new.md")))

    def test_write_to_adr_with_stale_marker_is_blocked(self):
        self._set_marker(age_seconds=31 * 60)
        self.assertBlocked(self.run_write(os.path.join(self.ddir, "0002-new.md")), "H-11")


class TestH18ContextMd(_PreWriteFixture):
    """#159: CONTEXT.md is the activation switch; a Write may not drop
    `arbiter: enabled` or corrupt the frontmatter."""
    CTX = None

    def setUp(self):
        super().setUp()
        self.CTX = os.path.join(self.ca, "CONTEXT.md")

    def test_disable_arbiter_is_blocked(self):
        self.assertBlocked(self.run_write(self.CTX, content="---\narbiter: disabled\n---\n"), "H-18")

    def test_strip_frontmatter_is_blocked(self):
        self.assertBlocked(self.run_write(self.CTX, content="# ctx\nno frontmatter\n"), "H-18")

    def test_unclosed_frontmatter_is_blocked(self):
        # opens '---' but never closes -> malformed -> not enabled.
        self.assertBlocked(self.run_write(self.CTX, content="---\narbiter: enabled\n"), "H-18")

    def test_keep_enabled_stage_bump_is_allowed(self):
        self.assertAllowed(self.run_write(
            self.CTX, content="---\narbiter: enabled\nstage: 3\n---\n<!--INITIALIZED-->\nx\n"))


class TestH19Markers(_PreWriteFixture):
    """#160: gate-pass markers are not writable via the Write tool."""
    def test_write_security_gate_marker_is_blocked(self):
        self.assertBlocked(
            self.run_write(os.path.join(self.markers, "security-gate-passed"), content="d\n"), "H-19")

    def test_write_migration_gate_marker_is_blocked(self):
        self.assertBlocked(
            self.run_write(os.path.join(self.markers, "migration-gate-passed"), content="d\n"), "H-19")

    def test_write_adr_marker_is_blocked(self):
        self.assertBlocked(
            self.run_write(os.path.join(self.markers, "adr-authoring-active"), content="x\n"), "H-19")


def _symlinks_supported():
    """Windows CI runners often lack the privilege to create symlinks; skip the
    symlink cases there (ubuntu/macos exercise the #162 path fully)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            os.symlink(os.path.join(d, "t"), os.path.join(d, "l"))
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False


@unittest.skipUnless(_symlinks_supported(), "symlink creation not permitted here")
class TestSymlinkAlias(_PreWriteFixture):
    """#162: a symlink whose visible path lacks .codearbiter/ but resolves into
    it must still be classified as protected."""
    def _symlink(self, link, target):
        # target_is_directory matters on Windows: a dir symlink to a
        # (possibly not-yet-existing) directory must be created as a dir link,
        # or realpath won't resolve paths beneath it. POSIX ignores the flag.
        tgt_abs = os.path.join(self.root, target)
        os.symlink(target, os.path.join(self.root, link),
                   target_is_directory=os.path.isdir(tgt_abs))

    def test_symlinked_dir_to_codearbiter_blocks_audit_log(self):
        self._symlink("alias", ".codearbiter")
        self.assertBlocked(
            self.run_write(os.path.join(self.root, "alias", "overrides.log")), "H-05")

    def test_symlinked_dir_to_decisions_blocks_adr(self):
        self._symlink("dlink", os.path.join(".codearbiter", "decisions"))
        self.assertBlocked(
            self.run_write(os.path.join(self.root, "dlink", "0002-x.md")), "H-11")

    def test_symlinked_file_to_context_blocks_disable(self):
        self._symlink("ctxlink", os.path.join(".codearbiter", "CONTEXT.md"))
        self.assertBlocked(
            self.run_write(os.path.join(self.root, "ctxlink"),
                           content="---\narbiter: disabled\n---\n"), "H-18")

    def test_symlinked_marker_dir_blocks_write(self):
        os.makedirs(self.markers, exist_ok=True)  # target must exist for a Windows dir symlink
        self._symlink("mlink", os.path.join(".codearbiter", ".markers"))
        self.assertBlocked(
            self.run_write(os.path.join(self.root, "mlink", "security-gate-passed"),
                           content="d\n"), "H-19")


class TestPreWriteAllowPaths(_PreWriteFixture):
    def test_disabled_arbiter_is_noop(self):
        self._disable_arbiter()
        self.assertAllowed(self.run_write(os.path.join(self.ca, "overrides.log")))

    def test_unrelated_path_is_allowed(self):
        self.assertAllowed(self.run_write(os.path.join(self.root, "src", "app.py")))


if __name__ == "__main__":
    unittest.main()
