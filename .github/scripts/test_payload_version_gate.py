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
from _releaselib import RELEASE_TAG_PREFIXES  # noqa: E402

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


class TestTheGatedSetMatchesTheRepository(unittest.TestCase):
    """AC-3: every plugin is gated exactly once, under one shared rule."""

    def test_every_gated_manifest_exists(self):
        for plugin, manifest in gate.GATED_MANIFESTS.items():
            with self.subTest(plugin=plugin):
                self.assertTrue((REPO_ROOT / manifest).is_file(), f"{manifest} is missing")

    def test_every_gated_plugin_has_a_release_tag_namespace(self):
        for plugin in gate.GATED_MANIFESTS:
            with self.subTest(plugin=plugin):
                self.assertIn(Path(plugin).name, RELEASE_TAG_PREFIXES)

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
