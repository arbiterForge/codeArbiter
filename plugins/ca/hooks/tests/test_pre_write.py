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
import importlib.util as _ilu
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_WRITE = os.path.join(HOOKS, "pre-write.py")
sys.path.insert(0, HOOKS)


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

    def test_write_to_gate_events_log_is_blocked(self):
        # gate-events.log (observability-001, #186) is the durable
        # BLOCK/REMIND/WARN sink — an append-only audit artifact like the rest.
        self.assertBlocked(self.run_write(os.path.join(self.ca, "gate-events.log")), "H-05")


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


def _load_pre_write():
    """Load pre-write.py as an IN-PROCESS module (mirrors
    test_guard_crash_failclosed.py's `_load` pattern) rather than a
    subprocess. T-06's H-22 branch needs a SYNTHETIC protected-state
    registry — REGISTRY ships empty at this slice (T-33/T-65/T-66 enroll
    consumers later) — and `_protectedstatelib.lookup_policy`/
    `resolve_registered_path` read the module-level REGISTRY fresh on every
    call (unlike the shell flank's precompiled `_STATE_WRITE_RES`), so
    mutating `_protectedstatelib.REGISTRY` directly is visible to a call
    made from THIS SAME process — a call inside a pre-write.py SUBPROCESS
    would just re-import its own, separately-loaded, empty REGISTRY."""
    spec = _ilu.spec_from_file_location("pre_write_h22test", PRE_WRITE)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestH22ProtectedState(unittest.TestCase):
    """T-06 (#564): the generic "state" branch. marker-gated admits only
    under a fresh authoring marker; helper-only/append-only hard-block
    unconditionally, with NO marker path at all."""

    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n"

    def setUp(self):
        import _protectedstatelib
        self.mod = _load_pre_write()
        self._protectedstatelib = _protectedstatelib
        self._orig_registry = _protectedstatelib.REGISTRY
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        self.ca = os.path.join(self.root, ".codearbiter")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.ca)
        with open(os.path.join(self.ca, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write(self.ARBITER)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.root

    def tearDown(self):
        self._protectedstatelib.REGISTRY = self._orig_registry
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self._tmp.cleanup()

    def _set_registry(self, registry):
        self._protectedstatelib.REGISTRY = registry

    def _touch_marker(self, name, age_seconds=0):
        os.makedirs(self.markers, exist_ok=True)
        m = os.path.join(self.markers, name)
        with open(m, "w", encoding="utf-8") as f:
            f.write("active\n")
        if age_seconds:
            past = time.time() - age_seconds
            os.utime(m, (past, past))
        return m

    def run_write(self, file_path, content="x\n"):
        payload = {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}}
        old_stdin, old_stdout, old_stderr = sys.stdin, sys.stdout, sys.stderr
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as ctx:
                self.mod.main()
            return ctx.exception.code, sys.stderr.getvalue()
        finally:
            sys.stdin, sys.stdout, sys.stderr = old_stdin, old_stdout, old_stderr

    def assertBlockedH22(self, res):
        code, err = res
        self.assertEqual(code, 2, err)
        self.assertIn("H-22", err, err)

    def assertAllowed(self, res):
        code, err = res
        self.assertEqual(code, 0, err)

    def test_marker_gated_write_without_marker_is_blocked(self):
        self._set_registry({".codearbiter/release-targets.md":
                            self._protectedstatelib.ProtectedPolicy.MARKER_GATED})
        self.assertBlockedH22(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def test_marker_gated_write_with_fresh_marker_is_allowed(self):
        self._set_registry({".codearbiter/release-targets.md":
                            self._protectedstatelib.ProtectedPolicy.MARKER_GATED})
        self._touch_marker("release-targets-authoring")
        self.assertAllowed(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def _guard_delete(self, path):
        """Run ONE canonical `delete` op through the guard.

        Driven at `_guard_op` rather than through a payload, because a
        `delete` kind only ever arrives from a host whose write tool batches
        per-file operations (Codex's apply_patch, ADR-0011 M2) -- Claude's
        Write payload always maps to a single `write`.
        """
        import io
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.mod._guard_op(self.root, {"file_path": path, "kind": "delete"})
            return 0, sys.stderr.getvalue()
        except SystemExit as exc:
            return exc.code, sys.stderr.getvalue()
        finally:
            sys.stderr = old

    def test_a_fresh_marker_does_not_admit_deleting_marker_gated_state(self):
        # CodeRabbit MAJOR, confirmed. The marker-gated arm admitted any op
        # kind under a fresh marker, so a self-mintable, friction-grade
        # token (ADR-0024) became a DELETE capability over protected state.
        # An authoring lane writes rows; it never removes the file.
        self._set_registry({".codearbiter/release-targets.md":
                            self._protectedstatelib.ProtectedPolicy.MARKER_GATED})
        self._touch_marker("release-targets-authoring")
        self.assertBlockedH22(self._guard_delete(
            os.path.join(self.ca, "release-targets.md")))

    def test_delete_of_helper_only_state_stays_blocked(self):
        # The non-marker policies had no marker path to begin with; pinned
        # so the new delete arm cannot accidentally become the ONLY thing
        # blocking them.
        self._set_registry({".codearbiter/open-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.HELPER_ONLY})
        self.assertBlockedH22(self._guard_delete(
            os.path.join(self.ca, "open-tasks.md")))

    def test_marker_gated_write_with_stale_marker_is_blocked(self):
        self._set_registry({".codearbiter/release-targets.md":
                            self._protectedstatelib.ProtectedPolicy.MARKER_GATED})
        self._touch_marker("release-targets-authoring", age_seconds=31 * 60)
        self.assertBlockedH22(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def test_helper_only_write_is_blocked_unconditionally(self):
        self._set_registry({".codearbiter/open-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.HELPER_ONLY})
        self.assertBlockedH22(self.run_write(os.path.join(self.ca, "open-tasks.md")))

    def test_helper_only_write_is_blocked_even_with_a_marker_present(self):
        # helper-only has NO marker path at all — a marker present under
        # ANY name must not admit it.
        self._set_registry({".codearbiter/open-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.HELPER_ONLY})
        self._touch_marker("open-tasks-authoring")
        self.assertBlockedH22(self.run_write(os.path.join(self.ca, "open-tasks.md")))

    def test_append_only_write_is_blocked_unconditionally(self):
        self._set_registry({".codearbiter/done-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.APPEND_ONLY})
        self.assertBlockedH22(self.run_write(os.path.join(self.ca, "done-tasks.md")))

    def test_unregistered_path_is_unaffected(self):
        self._set_registry({".codearbiter/release-targets.md":
                            self._protectedstatelib.ProtectedPolicy.MARKER_GATED})
        self.assertAllowed(self.run_write(os.path.join(self.ca, "open-tasks.md")))

    def test_the_real_production_registry_protects_release_targets(self):
        # Was "the REAL production registry blocks nothing new -- empty at
        # this slice". T-33 enrols the first consumer, so the real registry
        # now BLOCKS this write. Deliberately uses the production registry
        # (no _set_registry call): every other test in this class injects a
        # synthetic one, so without this the enrolment itself -- the thing
        # T-33 actually ships -- would be untested on this flank.
        self.assertBlockedH22(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def test_the_real_registry_admits_the_write_under_a_fresh_marker(self):
        # Spec 2.7's fourth case, against the PRODUCTION registry: the
        # sanctioned authors (context-creation, the release skill's
        # back-fill lane and its row-edit path) all mint this marker, so a
        # block with no marker path would leave them no route at all.
        self._touch_marker("release-targets-authoring", age_seconds=0)
        self.assertAllowed(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def test_the_real_registry_still_blocks_under_a_STALE_marker(self):
        # Freshness is the control, not mere presence -- a marker left
        # behind by a lane that exited without cleanup must not keep the
        # file writable indefinitely.
        self._touch_marker("release-targets-authoring", age_seconds=60 * 60 * 3)
        self.assertBlockedH22(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    def test_the_marker_for_a_DIFFERENT_file_does_not_admit_this_one(self):
        # Marker names encode the path, so minting one consumer's marker
        # must not arm another's -- the exact failure the spec rejects
        # reusing `adr-authoring-active` for.
        self._touch_marker("adr-authoring-active", age_seconds=0)
        self.assertBlockedH22(self.run_write(
            os.path.join(self.ca, "release-targets.md")))

    @unittest.skipUnless(_symlinks_supported(), "symlink creation not permitted here")
    def test_symlinked_dir_alias_blocks_registered_state_file(self):
        # F10 (#564 follow-up): the #162 symlink property TestSymlinkAlias
        # (above) pins for the four legacy classes had no "state" case. A
        # symlinked DIRECTORY whose visible path lacks .codearbiter/ but
        # resolves into it must still hit "state" via the REALPATH leg.
        self._set_registry({".codearbiter/open-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.HELPER_ONLY})
        alias = os.path.join(self.root, "alias")
        os.symlink(self.ca, alias, target_is_directory=True)
        self.assertBlockedH22(self.run_write(os.path.join(alias, "open-tasks.md")))

    @unittest.skipUnless(_symlinks_supported(), "symlink creation not permitted here")
    def test_symlinked_protected_file_still_blocks_via_raw_spelling(self):
        # F10/F3 (#564 follow-up): the MIRROR-IMAGE case, and the one the
        # OLD "raw leg" (norm_path(fpath), inert for an equality-based
        # lookup) got backwards — when the PROTECTED PATH ITSELF is a
        # symlink, realpath resolves the only spelling a host actually
        # sends (the absolute path) straight through it to an unregistered
        # target. The raw (symlink-unresolved) repo-relative form is what
        # still recognizes the registered NAME.
        self._set_registry({".codearbiter/open-tasks.md":
                            self._protectedstatelib.ProtectedPolicy.HELPER_ONLY})
        decoy = os.path.join(self.root, "decoy.md")
        with open(decoy, "w", encoding="utf-8") as f:
            f.write("not protected\n")
        link = os.path.join(self.ca, "open-tasks.md")
        os.symlink(decoy, link)
        self.assertBlockedH22(self.run_write(link))


class TestPreWriteAllowPaths(_PreWriteFixture):
    def test_disabled_arbiter_is_noop(self):
        self._disable_arbiter()
        self.assertAllowed(self.run_write(os.path.join(self.ca, "overrides.log")))

    def test_unrelated_path_is_allowed(self):
        self.assertAllowed(self.run_write(os.path.join(self.root, "src", "app.py")))


if __name__ == "__main__":
    unittest.main()
