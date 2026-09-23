#!/usr/bin/env python3
"""codeArbiter — unit tests for the payload-version gate (issue #530).

The bug these exist for: the gate keyed "already published" on a GIT TAG, while
`claude plugin update` keys on the MANIFEST VERSION. In the window where a
version is on the default branch but untagged, the guard reported "allowed" for
payload changes that could never reach an installed user.

Every case runs against a REAL throwaway git repository rather than a mocked
`git`, because the defect was in what git was ASKED, not in how its answer was
handled — a mock would have happily reproduced the wrong question.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import payload_version_gate as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def git(args, cwd):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


class _Repo(unittest.TestCase):
    """A repo whose `main` carries a released version, then an UNTAGGED one.

    This shape is the whole point: `2.8.13` is tagged, `2.9.1` is not, and both
    are on the default branch with payload attached. The live 2026-07-27 state.
    """

    PLUGIN = "plugins/ca"
    MANIFEST = "plugins/ca/.claude-plugin/plugin.json"
    PAYLOAD = "plugins/ca/hooks/_hooklib.py"
    TAG_PREFIX = "v"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir(parents=True)
        git(["init", "-q", "-b", "main"], self.root)
        git(["config", "user.email", "h@example.com"], self.root)
        git(["config", "user.name", "harness"], self.root)

        # A dev-only file under tools/, so scope exclusions are exercised too.
        self.write(f"{self.PLUGIN}/tools/package-lock.json", "base\n")
        self.write(self.PAYLOAD, "AUDIT = ()\n")
        self.set_version("2.8.13")
        git(["add", "-A"], self.root)
        git(["commit", "-qm", "release 2.8.13"], self.root)
        git(["tag", f"{self.TAG_PREFIX}2.8.13"], self.root)

        # A PR bumped to 2.9.1 and shipped payload. It merged. It was never tagged.
        self.write(self.PAYLOAD, "AUDIT = ('overrides.log',)\n")
        self.set_version("2.9.1")
        git(["add", "-A"], self.root)
        git(["commit", "-qm", "feat: ship on 2.9.1"], self.root)
        self.base = git(["rev-parse", "HEAD"], self.root).stdout.strip()
        git(["checkout", "-q", "-b", "work"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def set_version(self, version):
        self.write(self.MANIFEST, '{\n  "name": "ca",\n  "version": "%s"\n}\n' % version)

    def commit(self, message="change"):
        git(["add", "-A"], self.root)
        git(["commit", "-qm", message], self.root)

    def run_gate(self):
        return gate.gate(self.base, self.PLUGIN, root=self.root)


class TestTheUntaggedButInstalledCase(_Repo):
    """AC-1 and AC-4: the exact case that produced #530."""

    def test_payload_change_on_an_untagged_shipped_version_fails(self):
        # No tag v2.9.1 exists anywhere. The OLD gate printed
        # "payload changed on unpublished version 2.9.1 - allowed" here.
        self.assertFalse(gate.tag_exists("v2.9.1", self.root))
        self.write(self.PAYLOAD, "AUDIT = ('overrides.log', 'decision-log.md')\n")
        self.commit("fix(hooks): reclassify the arbitration log")

        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("still 2.9.1", message)
        self.assertIn("base has 2.9.1", message)

    def test_the_failure_does_not_depend_on_the_tag_check(self):
        """The advance check must be what fails it — not the tag backstop.

        Without this, deleting the tag lookup entirely would leave every test
        above still green, and the gate would be resting on the wrong half.
        """
        self.write(self.PAYLOAD, "changed\n")
        self.commit()
        original = gate.tag_exists
        gate.tag_exists = lambda *a, **k: False  # neuter the backstop completely
        try:
            code, message = self.run_gate()
        finally:
            gate.tag_exists = original
        self.assertEqual(code, gate.FAIL, message)

    def test_a_shipped_tools_artifact_counts_as_payload(self):
        # farm.js lives inside the excluded tools/ dir but DOES ship, so it must
        # still demand an advance. Pins the payload_scope integration.
        self.write("plugins/ca/tools/farm.js", "rebuilt\n")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)


class TestTheGateStillAllowsWhatItShould(_Repo):
    """AC-2: the ordinary flow must be unaffected."""

    def test_advancing_the_version_passes(self):
        self.write(self.PAYLOAD, "changed\n")
        self.set_version("2.9.2")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.PASS, message)
        self.assertIn("2.9.1 -> 2.9.2", message)

    def test_no_payload_change_passes_without_a_bump(self):
        self.write(f"{self.PLUGIN}/tools/package-lock.json", "dependabot bumped\n")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.PASS, message)
        self.assertIn("no shipped payload change", message)

    def test_a_first_introduction_passes(self):
        """A plugin absent from the base is not published anywhere. AC-2.

        The plugin must EXIST on the work branch and be absent on base — a
        plugin absent from both is a no-payload-change pass and proves nothing
        about the first-introduction arm."""
        self.write(
            "plugins/ca-sandbox/.claude-plugin/plugin.json",
            '{\n  "name": "ca-sandbox",\n  "version": "0.1.0"\n}\n',
        )
        self.write("plugins/ca-sandbox/commands/sandbox.md", "new plugin\n")
        self.commit("feat: introduce ca-sandbox")
        code, message = gate.gate(self.base, "plugins/ca-sandbox", root=self.root)
        self.assertEqual(code, gate.PASS, message)
        self.assertIn("first introduction", message)

    def test_a_prerelease_advancing_to_its_release_passes(self):
        # ca-codex shipped 0.2.4-beta.1 before 0.2.4; SemVer 11 ranks the
        # pre-release BELOW the release, so this is a genuine advance.
        self.set_version("2.9.1-beta.1")
        self.commit("beta")
        self.base = git(["rev-parse", "HEAD"], self.root).stdout.strip()
        self.write(self.PAYLOAD, "promoted\n")
        self.set_version("2.9.1")
        self.commit("promote")
        code, message = self.run_gate()
        self.assertEqual(code, gate.PASS, message)


class TestTheGateRefusesTheOtherDirections(_Repo):
    """The failure modes an `!=` comparison would have let through."""

    def test_a_version_that_goes_BACKWARDS_fails(self):
        # `!=` would call this a bump. It is a downgrade onto an already-released
        # version, which is worse than standing still.
        self.write(self.PAYLOAD, "changed\n")
        self.set_version("2.8.13")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)

    def test_regressing_to_a_prerelease_of_the_same_version_fails(self):
        self.write(self.PAYLOAD, "changed\n")
        self.set_version("2.9.1-beta.2")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)

    def test_an_advance_onto_an_ALREADY_TAGGED_version_fails(self):
        """The backstop: advanced from base, but that version is released."""
        git(["tag", "v2.9.5"], self.root)
        self.write(self.PAYLOAD, "changed\n")
        self.set_version("2.9.5")
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("already released", message)

    def test_an_unresolvable_base_fails_rather_than_passing(self):
        self.write(self.PAYLOAD, "changed\n")
        self.commit()
        code, message = gate.gate("origin/does-not-exist", self.PLUGIN, root=self.root)
        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("does not resolve", message)

    def test_an_unparseable_manifest_version_fails_and_SAYS_SO(self):
        """The diagnosis must name the real problem.

        `semver_greater` degrades to False on malformed input — the right gate
        answer with the wrong explanation, since "the version is still
        <garbage>" sends the reader hunting for a bump they already made."""
        self.write(self.PAYLOAD, "changed\n")
        self.write(self.MANIFEST, '{"name": "ca", "version": "not-a-version"}\n')
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("not valid SemVer", message)
        self.assertNotIn("still", message)

    def test_a_manifest_without_a_version_key_fails(self):
        self.write(self.PAYLOAD, "changed\n")
        self.write(self.MANIFEST, '{"name": "ca"}\n')
        self.commit()
        code, message = self.run_gate()
        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("no usable version string", message)


class TestBasenameCollisionRefusal(unittest.TestCase):
    """AC-07 / #626 finding 2a: two declared payload rows that reduce to the
    same basename must be refused before the map silently loses one of them —
    whether the two rows agree or disagree on prefix."""

    def _write_targets(self, tmp, sections):
        path = Path(tmp) / "release-targets.md"
        lines = ["<!-- release-targets -->"]
        for i, (name, prefix, payload) in enumerate(sections):
            if i:
                lines.append("")
            lines.extend([
                f"[{name}]",
                f"prefix: {prefix}",
                "changelog: CHANGELOG.md",
                f"payload: {payload}",
            ])
        lines.append("<!-- /release-targets -->")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_equal_prefix_basename_collision_is_refused(self):
        # Two rows, SAME prefix, same resulting basename. Even though the
        # overwrite would today have produced an identical value, the
        # collision itself — not its value — is the defect.
        with tempfile.TemporaryDirectory() as tmp:
            declared = self._write_targets(tmp, [
                ("foo", "foo-v", "plugins/foo/"),
                ("foo-tool", "foo-v", "tools/foo/"),
            ])
            with self.assertRaises(gate.BasenameCollisionError) as ctx:
                gate.tag_prefixes(declared)
        message = str(ctx.exception)
        self.assertIn("foo", message)
        self.assertIn("plugins/foo", message)
        self.assertIn("tools/foo", message)

    def test_different_prefix_basename_collision_is_refused_before_overwrite(self):
        # Two rows, DIFFERENT prefixes, same resulting basename — the shape
        # that would gate the wrong plugin under the wrong tag namespace.
        #
        # The pairing in the message is what proves "before any overwrite":
        # the diagnostic must attribute 'foo-v' to 'plugins/foo' and 'baz-v'
        # to 'tools/foo' — the FIRST row's prefix against the FIRST row's
        # payload. If the raise fired AFTER `prefixes[basename]` was
        # reassigned to the second row's value, this exact pairing would
        # break (both entries would read 'baz-v') even though an exception
        # still got raised — merely asserting "raised" or "both strings
        # appear somewhere" cannot tell the two orderings apart.
        with tempfile.TemporaryDirectory() as tmp:
            declared = self._write_targets(tmp, [
                ("foo", "foo-v", "plugins/foo/"),
                ("baz", "baz-v", "tools/foo/"),
            ])
            with self.assertRaises(gate.BasenameCollisionError) as ctx:
                gate.tag_prefixes(declared)
        message = str(ctx.exception)
        self.assertIn("'plugins/foo' (prefix 'foo-v')", message)
        self.assertIn("'tools/foo' (prefix 'baz-v')", message)

    def test_a_later_valid_row_does_not_mask_an_earlier_collision(self):
        # A third, later, non-colliding row proves the function stops at the
        # collision rather than continuing past it to build a partial map
        # that happens to look complete.
        with tempfile.TemporaryDirectory() as tmp:
            declared = self._write_targets(tmp, [
                ("foo", "foo-v", "plugins/foo/"),
                ("baz", "baz-v", "tools/foo/"),
                ("quux", "quux-v", "plugins/quux/"),
            ])
            with self.assertRaises(gate.BasenameCollisionError):
                gate.tag_prefixes(declared)

    def test_gate_surfaces_the_collision_as_a_clean_failure_not_a_traceback(self):
        """The refusal must actually reach the operator through `gate()`."""
        original = gate.tag_prefixes

        def _colliding(*_a, **_k):
            raise gate.BasenameCollisionError(
                "two declared release-target payload directories share the basename "
                "'foo': 'plugins/foo' (prefix 'foo-v') and 'tools/foo' (prefix 'baz-v')."
            )

        gate.tag_prefixes = _colliding
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                root.mkdir()
                git(["init", "-q", "-b", "main"], root)
                git(["config", "user.email", "h@example.com"], root)
                git(["config", "user.name", "harness"], root)
                manifest = root / _Repo.MANIFEST
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(
                    '{\n  "name": "ca",\n  "version": "2.8.13"\n}\n', encoding="utf-8")
                payload = root / _Repo.PAYLOAD
                payload.parent.mkdir(parents=True, exist_ok=True)
                payload.write_text("AUDIT = ()\n", encoding="utf-8")
                git(["add", "-A"], root)
                git(["commit", "-qm", "release 2.8.13"], root)
                git(["tag", "v2.8.13"], root)
                base = git(["rev-parse", "HEAD"], root).stdout.strip()
                payload.write_text("AUDIT = ('overrides.log',)\n", encoding="utf-8")
                manifest.write_text(
                    '{\n  "name": "ca",\n  "version": "2.9.1"\n}\n', encoding="utf-8")
                git(["add", "-A"], root)
                git(["commit", "-qm", "feat: ship on 2.9.1"], root)

                code, message = gate.gate(base, "plugins/ca", root=root)
        finally:
            gate.tag_prefixes = original

        self.assertEqual(code, gate.FAIL, message)
        self.assertIn("foo", message)
        self.assertIn("plugins/foo", message)
        self.assertIn("tools/foo", message)

    def test_todays_real_declared_targets_still_resolve_correctly(self):
        """Existing non-colliding mapping is completely unaffected.

        Against the REAL, current `.codearbiter/release-targets.md` — not a
        synthetic fixture — every gated plugin must still resolve to a tag
        namespace with no collision raised."""
        namespaces = gate.tag_prefixes()
        for plugin in gate.GATED_MANIFESTS:
            with self.subTest(plugin=plugin):
                self.assertIn(Path(plugin).name, namespaces)


class TestDeclarationErrorReporting(unittest.TestCase):
    """AC-08 / #626 finding 2b: `tag_prefixes()`'s `load_targets()` call can
    raise any `ReleaseTargetsError` subclass (`AbsentBlockError`,
    `FileExistsNoBlockError`, `UnreadableTargetsFileError`,
    `MalformedBlockError`, ...) for a missing, malformed, or unreadable
    `.codearbiter/release-targets.md`. Before this fix, `gate()` caught only
    `BasenameCollisionError` around this exact call, so every one of those
    cases propagated as an uncaught Python traceback with the interpreter's
    default exit code instead of the gate's normal `(FAIL, message)` shape
    every other failure path here produces."""

    def test_absent_declaration_file_raises_a_declared_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "release-targets.md"
            with self.assertRaises(gate.ReleaseTargetsError):
                gate.tag_prefixes(missing)

    def test_malformed_declaration_file_with_no_block_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            malformed = Path(tmp) / "release-targets.md"
            malformed.write_text("not a declaration at all\n", encoding="utf-8")
            with self.assertRaises(gate.ReleaseTargetsError):
                gate.tag_prefixes(malformed)

    def test_empty_declaration_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "release-targets.md"
            empty.write_text("", encoding="utf-8")
            with self.assertRaises(gate.ReleaseTargetsError):
                gate.tag_prefixes(empty)

    def test_unreadable_declaration_file_raises(self):
        # Opening a DIRECTORY at the declared path is a portable way to
        # exercise "present but unreadable" on every OS this repo supports:
        # Windows raises PermissionError, POSIX raises IsADirectoryError —
        # both are OSErrors whose errno is not ENOENT, which
        # core/pysrc/_releaselib.py's load_targets() documents as exactly
        # the UnreadableTargetsFileError case (never AbsentBlockError, per
        # [[never-fold-unreadable-into-absent]]). No chmod fixture needed,
        # so this is exercised for real rather than only via a mock.
        with tempfile.TemporaryDirectory() as tmp:
            unreadable = Path(tmp) / "release-targets.md"
            unreadable.mkdir()
            with self.assertRaises(gate.ReleaseTargetsError):
                gate.tag_prefixes(unreadable)

    def _committed_repo(self, tmp):
        root = Path(tmp) / "repo"
        root.mkdir()
        git(["init", "-q", "-b", "main"], root)
        git(["config", "user.email", "h@example.com"], root)
        git(["config", "user.name", "harness"], root)
        manifest = root / _Repo.MANIFEST
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('{\n  "name": "ca",\n  "version": "2.8.13"\n}\n', encoding="utf-8")
        payload = root / _Repo.PAYLOAD
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_text("AUDIT = ()\n", encoding="utf-8")
        git(["add", "-A"], root)
        git(["commit", "-qm", "release 2.8.13"], root)
        git(["tag", "v2.8.13"], root)
        base = git(["rev-parse", "HEAD"], root).stdout.strip()
        payload.write_text("AUDIT = ('overrides.log',)\n", encoding="utf-8")
        manifest.write_text('{\n  "name": "ca",\n  "version": "2.9.1"\n}\n', encoding="utf-8")
        git(["add", "-A"], root)
        git(["commit", "-qm", "feat: ship on 2.9.1"], root)
        return root, base

    def test_gate_reports_a_declaration_error_as_a_clean_FAIL_not_a_traceback(self):
        """The refusal must reach `gate()` as (FAIL, message) with a
        path-identifying, cause-naming diagnostic — never propagate as an
        uncaught exception, and never a silently substituted empty map that
        would let the gate fall through to 'no declared namespace'."""
        original = gate.tag_prefixes

        def _raise_absent(*_a, **_k):
            raise gate.ReleaseTargetsError(
                "could not read release-targets file "
                f"{str(gate.DECLARED_TARGETS)!r}: [Errno 2] No such file or directory"
            )

        gate.tag_prefixes = _raise_absent
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root, base = self._committed_repo(tmp)
                code, message = gate.gate(base, "plugins/ca", root=root)
        finally:
            gate.tag_prefixes = original

        self.assertEqual(code, gate.FAIL, message)
        self.assertIn(str(gate.DECLARED_TARGETS), message)
        self.assertIn("ReleaseTargetsError", message)
        self.assertIn("No such file or directory", message)

    def test_gate_does_not_confuse_a_declaration_error_with_no_declared_namespace(self):
        """Before this fix, an uncaught exception here crashed the process —
        it did NOT fall through to the existing 'declares no release target'
        message. Pin that the new branch produces its OWN diagnostic, not
        that unrelated one, so a future change cannot silently swap a crash
        for a misleading pass-shaped message instead of a real fix."""
        original = gate.tag_prefixes
        gate.tag_prefixes = lambda *_a, **_k: (_ for _ in ()).throw(
            gate.ReleaseTargetsError("synthetic malformed-block failure"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root, base = self._committed_repo(tmp)
                code, message = gate.gate(base, "plugins/ca", root=root)
        finally:
            gate.tag_prefixes = original

        self.assertEqual(code, gate.FAIL, message)
        self.assertNotIn("declares no release target", message)
        self.assertIn("synthetic malformed-block failure", message)

    def test_todays_real_declared_targets_file_never_trips_the_new_branch(self):
        """No mock — the CURRENT declared file always resolves cleanly, so
        this pins that the new `except ReleaseTargetsError` branch is
        additive and never fires against a healthy repo."""
        namespaces = gate.tag_prefixes()
        self.assertIn("ca", namespaces)


class TestTheGatedSetMatchesTheRepository(unittest.TestCase):
    """AC-3: every plugin is gated exactly once, under one shared rule."""

    def test_every_gated_manifest_exists(self):
        for plugin, manifest in gate.GATED_MANIFESTS.items():
            with self.subTest(plugin=plugin):
                self.assertTrue((REPO_ROOT / manifest).is_file(), f"{manifest} is missing")

    def test_every_gated_plugin_has_a_release_tag_namespace(self):
        # Now asserted against the DERIVED map, not the retired constant.
        namespaces = gate.tag_prefixes()
        for plugin in gate.GATED_MANIFESTS:
            with self.subTest(plugin=plugin):
                self.assertIn(Path(plugin).name, namespaces)

    def test_no_prefix_literal_remains_in_the_gate(self):
        """A-4.1: the gate derives every tag namespace from the declared
        file, so no namespace string may be written into its source.

        A literal here is not a style nit. It is a SECOND source of truth
        for the same fact: a target declared in
        `.codearbiter/release-targets.md` under one prefix, and gated here
        under another, would be checked in one namespace and released in
        the other with nothing comparing them.

        Scanned as source text rather than by importing, because a literal
        can hide in a default argument or a fallback branch that no test
        input reaches."""
        source = (REPO_ROOT / ".github" / "scripts"
                  / "payload_version_gate.py").read_text(encoding="utf-8")
        code = os.linesep.join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#"))
        for prefix in gate.tag_prefixes().values():
            if prefix == "v":
                # A bare "v" appears in ordinary prose and identifiers; the
                # namespaced siblings are the discriminating case.
                continue
            with self.subTest(prefix=prefix):
                self.assertNotIn(
                    f'"{prefix}"', code,
                    f"tag prefix {prefix!r} is written literally in the gate's "
                    "source; it must come from the declared file")
                self.assertNotIn(f"'{prefix}'", code)
        # Scoped to IMPORT and USE, not to any mention. The gate's own
        # docstring names the retired constant to explain what replaced it
        # and why, which is documentation worth keeping -- an assertion
        # that banned the string outright would force deleting the
        # rationale to satisfy the test.
        self.assertNotIn(
            "import RELEASE_TAG_PREFIXES", code,
            "the gate must not import the retired constant")
        self.assertNotIn(
            "RELEASE_TAG_PREFIXES[", code,
            "the gate must not read the retired constant")
        self.assertNotIn(
            "RELEASE_TAG_PREFIXES,", code,
            "the gate must not import the retired constant in a list")

    def test_the_derived_map_agrees_with_the_declared_file(self):
        # The derivation itself, against an independent read of the same
        # file -- so a bug that returns an empty or partial map is caught
        # rather than passing vacuously through the membership test above.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_core_rl_for_gate_test", REPO_ROOT / "core" / "pysrc" / "_releaselib.py")
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        rows = core.load_targets(
            str(REPO_ROOT / ".codearbiter" / "release-targets.md"))
        expected = {
            (r["payload"] or "").strip("/").rsplit("/", 1)[-1]: r["prefix"]
            for r in rows
            if (r["payload"] or "").strip("/") not in ("", ".")
        }
        self.assertEqual(gate.tag_prefixes(), expected)
        self.assertGreaterEqual(len(expected), len(gate.GATED_MANIFESTS))

    def test_an_undeclared_gated_payload_fails_with_a_named_reason(self):
        # Previously a KeyError against the hardcoded map. A gate that
        # tracebacks tells an operator nothing about what to do.
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "release-targets.md"
            empty.write_text("\n".join([
                "<!-- release-targets -->",
                "[other]",
                "prefix: other-v",
                "changelog: CHANGELOG.md",
                "payload: plugins/other/",
                "<!-- /release-targets -->",
                "",
            ]), encoding="utf-8")
            namespaces = gate.tag_prefixes(empty)
        self.assertNotIn("ca", namespaces)
        self.assertEqual(namespaces, {"other": "other-v"})

    def test_ca_pi_is_gated_elsewhere_and_not_here(self):
        """Double-gating ca-pi would apply two rules to one plugin."""
        self.assertNotIn("plugins/ca-pi", gate.GATED_MANIFESTS)
        guard = (REPO_ROOT / "tools" / "build-host-packages.py").read_text(encoding="utf-8")
        self.assertIn("def pi_release_guard", guard)
        # ...and it must share this gate's definition of "advance" (#530 AC-3),
        # not carry a private copy that can drift.
        self.assertIn("from _releaselib import", guard)

    def test_every_payload_scoped_plugin_is_gated_somewhere(self):
        """A new plugin cannot be added to payload_scope and left ungated."""
        import payload_scope
        for plugin in payload_scope.SHIPPED_TOOLS_ARTIFACTS:
            with self.subTest(plugin=plugin):
                self.assertTrue(
                    plugin in gate.GATED_MANIFESTS or plugin == "plugins/ca-pi",
                    f"{plugin} is payload-scoped but no version gate claims it",
                )

    def test_unknown_plugin_is_a_usage_error(self):
        self.assertEqual(gate.main(["--plugin", "plugins/nope", "--base", "main"]), gate.USAGE)

    def test_the_exit_codes_are_distinguishable_to_a_SHELL(self):
        """CI reads the process exit code, not the constant's name.

        Every other assertion in this file compares `code` against `gate.PASS`
        or `gate.FAIL`, so setting both to 0 would leave all of them green while
        the gate silently stopped failing anything. This repo has shipped that
        exact defect before, so the values are pinned against literals here.
        """
        self.assertEqual(gate.PASS, 0)
        self.assertNotEqual(gate.FAIL, 0)
        self.assertNotEqual(gate.USAGE, 0)
        self.assertNotEqual(gate.FAIL, gate.USAGE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
