#!/usr/bin/env python3
"""Issue #435 — what counts as a SHIPPED payload change for the version gate.

The per-plugin version gates path-scoped to `plugins/<name>` WHOLESALE, so a
dev-only `plugins/<name>/tools/package-lock.json` bump demanded a manifest
version advance and a CHANGELOG heading for a change no installed user can
observe. The tax is not the annoyance; it is the second-order effect. A version
bump is supposed to mean "installed users need this", and training contributors
to bump one to silence a gate is precisely the habit the gate exists to prevent.

`plugins/<name>/tools/` is a BUILD directory: TypeScript sources, a vitest
config, a lockfile, and node_modules. Nothing there runs on an installed
machine - except the committed esbuild artifacts, which absolutely do, and which
therefore must keep triggering the gate.

These tests run against a REAL throwaway git repository, because the thing under
test is a `git diff` pathspec and a hand-checked pathspec is exactly the kind of
thing that looks right and matches nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import payload_scope  # noqa: E402


def git(args, cwd):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


class _Repo(unittest.TestCase):
    """A throwaway repo with a `base` commit and a working branch on top."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        git(["init", "-q", "-b", "main"], self.root)
        git(["config", "user.email", "h@example.com"], self.root)
        git(["config", "user.name", "harness"], self.root)
        for rel in (
            "plugins/ca/commands/fix.md",
            "plugins/ca/hooks/pre-bash.py",
            "plugins/ca/tools/farm.ts",
            "plugins/ca/tools/farm.js",
            "plugins/ca/tools/package-lock.json",
            "plugins/ca/tools/package.json",
            "plugins/ca/tools/farm.unit.test.ts",
            "plugins/ca-sandbox/tools/sandbox.ts",
            "plugins/ca-sandbox/tools/sandbox.js",
            "plugins/ca-sandbox/tools/package-lock.json",
            "plugins/ca-pi/extensions/codearbiter.js",
            "plugins/ca-pi/tools/package-lock.json",
        ):
            self.write(rel, "base\n")
        git(["add", "-A"], self.root)
        git(["commit", "-qm", "base"], self.root)
        self.base = git(["rev-parse", "HEAD"], self.root).stdout.strip()
        git(["checkout", "-q", "-b", "work"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, rel, text, message="change"):
        self.write(rel, text)
        git(["add", rel], self.root)
        git(["commit", "-qm", message], self.root)

    def changed(self, plugin):
        return payload_scope.payload_changed(self.base, plugin, root=self.root)


class TestDevOnlyChangesDoNotDemandAVersionBump(_Repo):
    """AC-1: a dev-only change under `plugins/*/tools/` is not a payload change."""

    def test_lockfile_bump_alone(self):
        # The literal case from #435: dependabot bumps a dev dependency.
        self.commit("plugins/ca-sandbox/tools/package-lock.json", "bumped\n")
        self.assertFalse(self.changed("plugins/ca-sandbox"))

    def test_the_same_shape_on_ca(self):
        # The issue's scope note: the ca gate has the identical shape.
        self.commit("plugins/ca/tools/package-lock.json", "bumped\n")
        self.assertFalse(self.changed("plugins/ca"))

    def test_the_same_shape_on_ca_pi(self):
        self.commit("plugins/ca-pi/tools/package-lock.json", "bumped\n")
        self.assertFalse(self.changed("plugins/ca-pi"))

    def test_build_sources_manifests_and_tests(self):
        # A source edit that does NOT change the built artifact ships nothing:
        # the artifact is what runs on an installed machine. A source edit that
        # DOES change it is covered by the artifact rule below.
        for rel in (
            "plugins/ca/tools/farm.ts",
            "plugins/ca/tools/package.json",
            "plugins/ca/tools/farm.unit.test.ts",
        ):
            with self.subTest(rel=rel):
                git(["checkout", "-q", "-B", "work", self.base], self.root)
                self.commit(rel, "edited\n")
                self.assertFalse(self.changed("plugins/ca"))

    def test_a_brand_new_dev_file_is_also_excluded(self):
        # The exclusion is directory-shaped, not a denylist of known filenames,
        # so a dev file nobody has thought of yet does not reintroduce the tax.
        self.commit("plugins/ca/tools/vitest.config.ts", "new\n")
        self.assertFalse(self.changed("plugins/ca"))


class TestShippedChangesStillDemandAVersionBump(_Repo):
    """AC-2: the committed build artifacts, and everything outside `tools/`,
    still count. This is the half that must not weaken."""

    def test_the_committed_esbuild_artifact_counts(self):
        for plugin, artifact in (
            ("plugins/ca", "plugins/ca/tools/farm.js"),
            ("plugins/ca-sandbox", "plugins/ca-sandbox/tools/sandbox.js"),
        ):
            with self.subTest(plugin=plugin):
                git(["checkout", "-q", "-B", "work", self.base], self.root)
                self.commit(artifact, "rebuilt\n")
                self.assertTrue(self.changed(plugin))

    def test_ordinary_payload_outside_tools_counts(self):
        for rel in ("plugins/ca/commands/fix.md", "plugins/ca/hooks/pre-bash.py"):
            with self.subTest(rel=rel):
                git(["checkout", "-q", "-B", "work", self.base], self.root)
                self.commit(rel, "edited\n")
                self.assertTrue(self.changed("plugins/ca"))

    def test_pi_extension_bundles_count(self):
        # ca-pi's artifacts live in extensions/, OUTSIDE tools/ - so they were
        # never in the excluded scope. Pinned so a later reorganisation that
        # moves them under tools/ cannot silently drop them.
        self.commit("plugins/ca-pi/extensions/codearbiter.js", "rebuilt\n")
        self.assertTrue(self.changed("plugins/ca-pi"))

    def test_a_shipped_change_riding_alongside_a_dev_change_still_counts(self):
        # The mixed commit is the one an over-eager exclusion would swallow.
        self.commit("plugins/ca/tools/package-lock.json", "bumped\n")
        self.commit("plugins/ca/tools/farm.js", "rebuilt\n")
        self.assertTrue(self.changed("plugins/ca"))

    def test_no_change_at_all_is_not_a_payload_change(self):
        self.assertFalse(self.changed("plugins/ca"))


class TestTheExclusionCannotSilentlyWiden(unittest.TestCase):
    """AC-3: the exclusion is declared once, and its shape is pinned."""

    def test_only_the_tools_build_directory_is_excluded(self):
        for plugin in ("plugins/ca", "plugins/ca-sandbox", "plugins/ca-pi", "plugins/ca-codex"):
            with self.subTest(plugin=plugin):
                spec = payload_scope.pathspec(plugin)
                self.assertEqual(spec[0], plugin)
                excludes = [entry for entry in spec if entry.startswith(":(exclude)")]
                self.assertEqual(
                    excludes,
                    [f":(exclude){plugin}/tools"],
                    "the version gate must exclude the tools BUILD directory and nothing else",
                )

    def test_every_declared_artifact_lives_inside_the_excluded_directory(self):
        # An artifact declared outside `tools/` would be double-counted: already
        # in scope, and re-checked. Harmless but a sign the map has drifted.
        for plugin, artifacts in payload_scope.SHIPPED_TOOLS_ARTIFACTS.items():
            for artifact in artifacts:
                with self.subTest(artifact=artifact):
                    self.assertTrue(artifact.startswith(f"{plugin}/tools/"))

    def test_every_declared_artifact_exists_in_this_repository(self):
        # The whole exclusion rests on this list being real. A renamed or
        # relocated artifact silently stops being gated, which is the exact
        # failure mode the gate exists to prevent.
        repo = Path(__file__).resolve().parents[2]
        for plugin, artifacts in payload_scope.SHIPPED_TOOLS_ARTIFACTS.items():
            for artifact in artifacts:
                with self.subTest(artifact=artifact):
                    self.assertTrue((repo / artifact).is_file(), f"missing {artifact}")

    def test_every_committed_js_artifact_under_tools_is_declared(self):
        # The other direction: a NEW committed build artifact under tools/ must
        # be added to the map, or the exclusion silently stops gating it.
        repo = Path(__file__).resolve().parents[2]
        for plugin, artifacts in payload_scope.SHIPPED_TOOLS_ARTIFACTS.items():
            tools = repo / plugin / "tools"
            if not tools.is_dir():
                continue
            found = sorted(
                f"{plugin}/tools/{path.name}"
                for path in tools.glob("*.js")
                if path.is_file() and not path.name.endswith(".config.js")
            )
            with self.subTest(plugin=plugin):
                self.assertEqual(found, sorted(artifacts))


if __name__ == "__main__":
    unittest.main()
