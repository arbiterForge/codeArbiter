#!/usr/bin/env python3
"""Tests for the integration-branch candidate-version rule (program task P-01).

Cases run against REAL throwaway git repositories, like test_payload_version_gate,
because the rule's correctness is about which commits git is asked to compare.
The key sequence: two successive child PRs into the integration branch both
change payload on the same untagged candidate. The strict immediate-base gate
refuses the second; the integration rule admits it, and only it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integration_candidate as ic  # noqa: E402
import payload_version_gate as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANCH = "major/state-contracts"


def _load_host_packages():
    spec = importlib.util.spec_from_file_location("build_host_packages", REPO_ROOT / "tools" / "build-host-packages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


class RecordParsing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "integration-candidate.json"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, **overrides):
        data = {
            "schema": ic.SCHEMA,
            "branch": BRANCH,
            "baseline_main_commit": "a" * 40,
            "candidates": {"ca": "4.0.0"},
        }
        data.update(overrides)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_integration_base_selects_the_record(self):
        self.write()
        record = ic.select(BRANCH, self.path)
        self.assertIsNotNone(record)
        self.assertEqual(record.versions, {"ca": "4.0.0"})

    def test_refs_heads_prefix_is_normalized(self):
        self.write()
        self.assertIsNotNone(ic.select(f"refs/heads/{BRANCH}", self.path))

    def test_main_and_merge_group_main_never_select(self):
        self.write()
        self.assertIsNone(ic.select("main", self.path))
        self.assertIsNone(ic.select("refs/heads/main", self.path))

    def test_other_branch_keeps_strict_rule(self):
        self.write()
        self.assertIsNone(ic.select("feat/codex-support-m0", self.path))

    def test_empty_base_keeps_strict_rule(self):
        self.write()
        self.assertIsNone(ic.select("", self.path))
        self.assertIsNone(ic.select(None, self.path))

    def test_absent_record_keeps_strict_rule(self):
        self.assertIsNone(ic.select(BRANCH, self.path))

    def test_record_cannot_enrol_main(self):
        self.write(branch="main")
        with self.assertRaises(ic.IntegrationRecordError):
            ic.select(BRANCH, self.path)

    def test_malformed_record_fails_closed(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ic.IntegrationRecordError):
            ic.select(BRANCH, self.path)

    def test_wrong_schema_fails_closed(self):
        self.write(schema="other/1")
        with self.assertRaises(ic.IntegrationRecordError):
            ic.select(BRANCH, self.path)

    def test_short_baseline_fails_closed(self):
        self.write(baseline_main_commit="abc123")
        with self.assertRaises(ic.IntegrationRecordError):
            ic.select(BRANCH, self.path)

    def test_prerelease_candidate_is_refused(self):
        self.write(candidates={"ca": "4.0.0-rc.1"})
        with self.assertRaises(ic.IntegrationRecordError):
            ic.select(BRANCH, self.path)

    def test_the_committed_record_parses(self):
        record = ic.load()
        self.assertEqual(record.branch, BRANCH)
        self.assertEqual(set(record.versions), {"ca", "ca-codex", "ca-pi", "ca-sandbox"})


class PayloadGateIntegration(unittest.TestCase):
    """main: v3.8.7 tagged. Integration branch from that baseline; children add payload."""

    PLUGIN = "plugins/ca"
    MANIFEST = "plugins/ca/.claude-plugin/plugin.json"
    PAYLOAD = "plugins/ca/hooks/_hooklib.py"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        git(["init", "-q", "-b", "main"], self.root)
        git(["config", "user.email", "h@example.com"], self.root)
        git(["config", "user.name", "harness"], self.root)
        self.write(self.PAYLOAD, "A = 1\n")
        self.set_version("3.8.7")
        self.commit("release 3.8.7")
        git(["tag", "v3.8.7"], self.root)
        self.baseline = git(["rev-parse", "HEAD"], self.root)
        git(["checkout", "-q", "-b", BRANCH], self.root)
        self.record = ic.Candidate(branch=BRANCH, baseline=self.baseline, versions={"ca": "4.0.0"})

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def set_version(self, version):
        self.write(self.MANIFEST, json.dumps({"name": "ca", "version": version}) + "\n")

    def commit(self, message):
        git(["add", "-A"], self.root)
        git(["commit", "-qm", message], self.root)
        return git(["rev-parse", "HEAD"], self.root)

    def integration(self):
        return gate.gate_integration(self.record, self.PLUGIN, "main", self.root)

    def child(self, name, payload, version="4.0.0"):
        """Open a child branch off the integration tip and change payload."""
        git(["checkout", "-q", BRANCH], self.root)
        base = git(["rev-parse", "HEAD"], self.root)
        git(["checkout", "-q", "-b", name], self.root)
        self.write(self.PAYLOAD, payload)
        self.set_version(version)
        self.commit(name)
        return base

    def merge_child(self, name):
        git(["checkout", "-q", BRANCH], self.root)
        git(["merge", "-q", "--no-ff", "-m", f"merge {name}", name], self.root)

    def test_two_successive_children_on_the_same_candidate_pass_only_under_the_rule(self):
        self.child("child-1", "A = 2\n")
        code, message = self.integration()
        self.assertEqual(code, gate.PASS, message)
        self.merge_child("child-1")

        immediate_base = self.child("child-2", "A = 3\n")
        strict_code, strict_message = gate.gate(immediate_base, self.PLUGIN, self.root)
        self.assertEqual(strict_code, gate.FAIL, "strict immediate-base rule must refuse the reused candidate")
        self.assertIn("still 4.0.0", strict_message)
        code, message = self.integration()
        self.assertEqual(code, gate.PASS, message)

    def test_no_payload_change_since_baseline_passes_without_candidate(self):
        self.write("docs/notes.md", "x\n")
        self.commit("docs only")
        code, message = self.integration()
        self.assertEqual(code, gate.PASS, message)
        self.assertIn("no shipped payload change", message)

    def test_payload_on_a_version_other_than_the_candidate_fails(self):
        self.child("child", "A = 2\n", version="4.0.1")
        code, message = self.integration()
        self.assertEqual(code, gate.FAIL)
        self.assertIn("declared integration candidate 4.0.0", message)

    def test_payload_on_the_unchanged_main_version_fails(self):
        self.child("child", "A = 2\n", version="3.8.7")
        code, _ = self.integration()
        self.assertEqual(code, gate.FAIL)

    def test_candidate_already_tagged_fails(self):
        self.child("child", "A = 2\n")
        git(["tag", "v4.0.0", self.baseline], self.root)
        code, message = self.integration()
        self.assertEqual(code, gate.FAIL)
        self.assertIn("already released", message)

    def test_main_reaching_the_candidate_fails(self):
        self.child("child", "A = 2\n")
        git(["checkout", "-q", "main"], self.root)
        self.write(self.PAYLOAD, "A = 9\n")
        self.set_version("4.0.0")
        self.commit("main shipped 4.0.0 first")
        git(["checkout", "-q", "child"], self.root)
        code, message = self.integration()
        self.assertEqual(code, gate.FAIL)
        self.assertIn("does not advance", message)

    def test_baseline_not_on_main_fails_closed(self):
        side = self.child("child", "A = 2\n")
        record = ic.Candidate(branch=BRANCH, baseline=git(["rev-parse", "HEAD"], self.root), versions={"ca": "4.0.0"})
        self.assertNotEqual(side, record.baseline)
        code, message = gate.gate_integration(record, self.PLUGIN, "main", self.root)
        self.assertEqual(code, gate.FAIL)
        self.assertIn("is not on main", message)

    def test_baseline_not_in_head_fails_closed(self):
        git(["checkout", "-q", "main"], self.root)
        self.write("other.txt", "x\n")
        later_main = self.commit("later main")
        git(["checkout", "-q", BRANCH], self.root)
        record = ic.Candidate(branch=BRANCH, baseline=later_main, versions={"ca": "4.0.0"})
        code, message = gate.gate_integration(record, self.PLUGIN, "main", self.root)
        self.assertEqual(code, gate.FAIL)
        self.assertIn("not contained in HEAD", message)

    def test_unresolvable_main_ref_fails_closed(self):
        self.child("child", "A = 2\n")
        code, message = gate.gate_integration(self.record, self.PLUGIN, "origin/main", self.root)
        self.assertEqual(code, gate.FAIL)
        self.assertIn("does not resolve", message)

    def test_strict_rule_is_unchanged_for_a_main_targeted_unchanged_version(self):
        self.child("child", "A = 2\n", version="3.8.7")
        code, _ = gate.gate("main", self.PLUGIN, self.root)
        self.assertEqual(code, gate.FAIL)


class PiIntegrationValidation(unittest.TestCase):
    hp = _load_host_packages()

    BASE_LOG = "# Changelog\n\n## [0.27.7] - 2026-11-12\n\n- prior\n"
    CAND_LOG = "# Changelog\n\n## [0.30.0]\n\n- program\n\n## [0.27.7] - 2026-11-12\n\n- prior\n"

    def check(self, **overrides):
        kwargs = dict(
            current_version="0.30.0",
            candidate_version="0.30.0",
            root_version="0.30.0",
            changelog=self.CAND_LOG,
            baseline_version="0.27.7",
            baseline_changelog=self.BASE_LOG,
            main_version="0.27.7",
            main_changelog=self.BASE_LOG,
            root_changed=True,
            changelog_changed=True,
            tagged=False,
        )
        kwargs.update(overrides)
        return self.hp.validate_pi_integration_candidate(**kwargs)

    def test_the_guard_can_load_the_shared_rule_module_in_a_fresh_process_state(self):
        # The CI path (main() with --release-guard-base) loads the rule via
        # importlib in a process that never imported it. A dataclass with
        # postponed annotations needs its module registered in sys.modules,
        # or loading crashes on EVERY Pi guard run. This file imports the
        # module at top, so remove it to reproduce the CI process state.
        saved = sys.modules.pop("integration_candidate", None)
        try:
            rules = self.hp._integration_candidate_module()
            record = rules.Candidate(branch=BRANCH, baseline="a" * 40, versions={"ca-pi": "0.30.0"})
            self.assertEqual(record.versions["ca-pi"], "0.30.0")
            self.assertIsNone(rules.select("main"))
        finally:
            if saved is not None:
                sys.modules["integration_candidate"] = saved

    def test_the_guard_cli_runs_end_to_end_without_crashing(self):
        # Exercise the real entry point in a subprocess on this checkout.
        import subprocess
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build-host-packages.py"), "--check",
             "--release-guard-base", "HEAD", "--integration-base-branch", "main"],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        self.assertNotIn("Traceback", result.stderr, result.stderr[-2000:])

    def test_second_child_passes_when_heading_already_on_integration_base(self):
        # The immediate integration base carries 0.30.0's heading; only the
        # baseline comparison makes this admissible.
        strict = self.hp.validate_pi_release_advance(
            current_version="0.30.0", base_version="0.30.0", root_version="0.30.0",
            changelog=self.CAND_LOG, base_changelog=self.CAND_LOG,
            root_changed=False, changelog_changed=True,
        )
        self.assertIsNotNone(strict)
        self.assertIsNone(self.check())

    def test_wrong_candidate_fails(self):
        self.assertIn("declared integration candidate", self.check(current_version="0.30.1", root_version="0.30.1"))

    def test_missing_candidate_fails(self):
        self.assertIn("no integration candidate", self.check(candidate_version=None))

    def test_stale_root_metadata_fails(self):
        self.assertIn("root Pi version", self.check(root_version="0.27.7"))

    def test_root_not_regenerated_since_baseline_fails(self):
        self.assertIn("regenerated root metadata", self.check(root_changed=False))

    def test_missing_changelog_heading_fails(self):
        self.assertIn("missing exact changelog heading", self.check(changelog=self.BASE_LOG))

    def test_heading_already_on_baseline_fails(self):
        self.assertIn("not newly introduced", self.check(baseline_changelog=self.CAND_LOG))

    def test_published_candidate_tag_fails(self):
        self.assertIn("already tagged", self.check(tagged=True))

    def test_main_reaching_candidate_fails(self):
        self.assertIn("does not advance live main", self.check(main_version="0.30.0"))

    def test_main_heading_collision_fails(self):
        self.assertIn("live main already carries", self.check(main_changelog=self.CAND_LOG))


class WorkflowAdmission(unittest.TestCase):
    """The integration branch gets real CI; publication and deploy stay main-only."""

    def read(self, name):
        return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")

    def test_ci_admits_integration_prs_and_pushes(self):
        ci = self.read("ci.yml")
        self.assertIn("branches: [main, feat/codex-support-m0, major/state-contracts]", ci)
        self.assertIn("branches: [main, major/state-contracts]", ci)
        self.assertIn('- "docs/state-contracts-major/**"', ci)

    def test_integration_push_selects_every_domain(self):
        ci = self.read("ci.yml")
        integ = "(github.event_name == 'push' && github.ref == 'refs/heads/major/state-contracts')"
        for key in ("ca", "ca-sandbox", "ca-codex", "ca-pi", "host-descriptors", "hooks", "impact",
                    "manifests", "codex-resources"):
            self.assertIn(f"      {key}: ${{{{ steps.filter.outputs.{key} == 'true' || {integ} }}}}", ci)
        self.assertIn(f"refs/heads/main') || {integ} }}}}", ci)

    def test_all_three_version_gates_and_pi_guard_pass_the_ci_base_branch(self):
        ci = self.read("ci.yml")
        for plugin in ("plugins/ca", "plugins/ca-sandbox", "plugins/ca-codex"):
            self.assertIn(
                f'payload_version_gate.py --plugin {plugin} --base "origin/$BASE" \\\n'
                f'            --integration-base-branch "$BASE" --main-ref origin/main', ci)
        self.assertIn('--integration-base-branch "${BASE_BRANCH#refs/heads/}" --main-ref origin/main', ci)

    def test_ci_and_codeql_grant_no_write_permission(self):
        for name in ("ci.yml", "codeql.yml"):
            text = self.read(name)
            for perm in ("contents: write", "pages: write", "id-token: write", "packages: write",
                         "pull-requests: write"):
                for line in text.splitlines():
                    if line.strip().startswith("#"):
                        continue
                    self.assertNotIn(perm, line, f"{name} grants {perm}")

    def test_release_admits_only_same_repo_main_push_or_main_dispatch(self):
        release = self.read("release.yml")
        self.assertIn("github.event.workflow_run.head_branch == 'main'", release)
        self.assertIn("github.event.workflow_run.event == 'push'", release)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", release)
        self.assertIn("(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')", release)
        self.assertNotIn("major/state-contracts", release)

    def test_docs_deploy_stays_main_only(self):
        docs = self.read("docs.yml")
        self.assertIn("branches: [main, major/state-contracts]", docs)
        self.assertIn(
            "if: contains(fromJSON('[\"push\",\"workflow_run\",\"workflow_dispatch\"]'), github.event_name) "
            "&& github.ref == 'refs/heads/main'", docs)
        workflow_run = docs.split("  workflow_run:", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertIn("branches: [main]", workflow_run)


if __name__ == "__main__":
    unittest.main()
