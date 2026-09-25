#!/usr/bin/env python3
"""Contracts for the release-on-merge workflow (ADR-0040).

release.yml publishes each plugin independently when `ci` succeeds on a main
push, and .github/actions/publish-target is the one re-runnable publish path.
These tests parse the SHIPPED files so that re-coupling the plugins, dropping
a consumer-safety gate, or turning an advisory check back into a blocker turns
CI red.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ci_impact import workflow_jobs  # noqa: E402

RELEASE = REPO / ".github/workflows/release.yml"
ACTION = REPO / ".github/actions/publish-target/action.yml"
RELEASE_JOBS = {"release-ca": "ca", "release-codex": "ca-codex",
                "release-pi": "ca-pi", "release-sandbox": "ca-sandbox"}


def release_text() -> str:
    return RELEASE.read_text(encoding="utf-8")


def action_text() -> str:
    return ACTION.read_text(encoding="utf-8")


def jobs() -> dict[str, str]:
    return workflow_jobs(release_text())


def action_step(name_fragment: str) -> str:
    steps = re.split(r"(?m)^    - ", action_text().split("\n  steps:\n", 1)[1])
    matches = [step for step in steps if re.match(rf"name: [^\n]*{re.escape(name_fragment)}", step)]
    if len(matches) != 1:
        raise AssertionError(f"expected one action step named like {name_fragment!r}, got {len(matches)}")
    return matches[0]


def step_index(name_fragment: str) -> int:
    text = action_text()
    index = text.find(f"name: {name_fragment}")
    if index < 0:
        raise AssertionError(f"missing action step {name_fragment!r}")
    return index


class TriggerTest(unittest.TestCase):
    def test_releases_follow_successful_main_ci_and_manual_retry(self):
        text = release_text()
        self.assertIn('workflows: ["ci"]', text)
        self.assertIn("branches: [main]", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("options: [ca, ca-codex, ca-pi, ca-sandbox]", text)

    def test_preflight_requires_a_successful_same_repo_main_push(self):
        condition = jobs()["preflight"]
        for clause in ("github.event.workflow_run.conclusion == 'success'",
                       "github.event.workflow_run.event == 'push'",
                       "github.event.workflow_run.head_branch == 'main'",
                       "github.event.workflow_run.head_repository.full_name == github.repository"):
            self.assertIn(clause, condition)

    def test_dispatch_is_refused_off_the_default_branch(self):
        self.assertIn("(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')",
                      jobs()["preflight"])

    def test_each_run_releases_its_own_commit_from_its_own_manifests(self):
        preflight = jobs()["preflight"]
        # Never skip because main moved on: a later merge may start no CI run.
        self.assertNotIn('SOURCE=""', preflight)
        self.assertIn('SOURCE="$RUN_SHA"; CI_RUN_ID="$RUN_ID"', preflight)
        self.assertIn('git merge-base --is-ancestor "$SOURCE" HEAD', preflight)
        self.assertIn('git checkout --quiet --detach "$SOURCE"', preflight)

    def test_dispatch_uses_the_newest_main_commit_with_successful_ci(self):
        self.assertIn("branch=main&event=push&status=success&per_page=1", jobs()["preflight"])

    def test_each_release_job_rechecks_before_publishing(self):
        found = jobs()
        for job in RELEASE_JOBS:
            block = found[job]
            self.assertIn("id: recheck", block, job)
            self.assertIn("release_target.py eligible", block, job)
            self.assertRegex(block, r"uses: \./\.github/actions/publish-target\n\s+if: steps\.recheck\.outputs\.go == 'true'", job)

    def test_dispatch_requires_a_successful_ci_run_for_the_commit(self):
        preflight = jobs()["preflight"]
        self.assertIn("status=success", preflight)
        self.assertIn("no successful push CI run", preflight)


class IndependenceTest(unittest.TestCase):
    def test_every_release_job_depends_only_on_the_preflight(self):
        found = jobs()
        for job in RELEASE_JOBS:
            self.assertRegex(found[job], r"(?m)^    needs: preflight$", job)

    def test_each_release_job_gates_only_on_its_own_eligibility(self):
        found = jobs()
        for job, target in RELEASE_JOBS.items():
            condition = re.search(r"(?m)^    if: (.+)$", found[job]).group(1)
            self.assertEqual(condition, f"needs.preflight.outputs.{target} == 'true'", job)

    def test_one_targets_planning_error_does_not_block_the_others(self):
        found = jobs()
        preflight = found["preflight"]
        self.assertIn('ELIGIBLE=false; FAILED="$FAILED $TARGET"', preflight)
        self.assertIn('echo "failed=${FAILED# }" >> "$GITHUB_OUTPUT"', preflight)
        errors = found["eligibility-errors"]
        self.assertIn("if: needs.preflight.outputs.failed != ''", errors)
        self.assertIn("exit 1", errors)
        for job in RELEASE_JOBS:
            self.assertNotIn("eligibility-errors", found[job], job)

    def test_no_cohort_machinery_remains(self):
        for text in (release_text(), action_text()):
            self.assertNotIn("cohort-reconciliation", text)
            self.assertNotIn("continuation", text)
            self.assertNotIn("cohort-marker", text)

    def test_each_release_job_serializes_only_with_itself(self):
        found = jobs()
        for job, target in RELEASE_JOBS.items():
            self.assertIn(f"group: release-{target},", found[job])
        self.assertNotRegex(release_text(), r"(?m)^concurrency:")

    def test_release_jobs_check_out_the_exact_planned_commit(self):
        found = jobs()
        for job in RELEASE_JOBS:
            self.assertIn("ref: ${{ needs.preflight.outputs.source }}", found[job])
            self.assertIn("persist-credentials: false", found[job])
            self.assertIn("uses: ./.github/actions/publish-target", found[job])


class PermissionTest(unittest.TestCase):
    def test_workflow_default_is_read_only(self):
        self.assertRegex(release_text(), r"(?m)^permissions:\n  contents: read$")

    def test_only_ca_is_marked_latest(self):
        found = jobs()
        self.assertIn('mark-latest: "true"', found["release-ca"])
        for job in ("release-codex", "release-pi", "release-sandbox"):
            self.assertNotIn('mark-latest: "true"', found[job])

    def test_codex_publishes_with_the_dedicated_distribution_app(self):
        codex = jobs()["release-codex"]
        self.assertIn("environment: codex-distribution", codex)
        self.assertIn("github-token: ${{ steps.codex-publisher.outputs.token }}", codex)
        self.assertIn("contents: read", codex)

    def test_pi_can_sign_npm_provenance(self):
        self.assertIn("id-token: write", jobs()["release-pi"])


class ConsumerSafetyGateTest(unittest.TestCase):
    def test_package_cohort_is_verified_before_anything_is_published(self):
        verify = action_step("Verify the CI package cohort")
        self.assertIn("verify-cohort", verify)
        self.assertIn('--workflow-sha "$SOURCE_COMMIT"', verify)
        self.assertLess(step_index("Verify the CI package cohort"),
                        step_index("Create and push the annotated tag"))

    def test_companion_manifest_must_agree(self):
        self.assertIn('[ "$COMPANION_VERSION" = "$VERSION" ]', action_step("Resolve version"))

    def test_changelog_section_is_required(self):
        notes = action_step("Extract the CHANGELOG section")
        self.assertIn("changelog-section", notes)
        self.assertIn("notes-match", notes)

    def test_tag_is_created_only_when_the_plan_says_so(self):
        self.assertIn("if: ${{ steps.plan.outputs.tag == 'create' }}",
                      action_step("Create and push the annotated tag"))

    def test_tag_is_read_back_against_the_release_commit(self):
        readback = action_step("Read back the tag")
        self.assertIn('[ "$TAG_SHA" = "$SOURCE_COMMIT" ]', readback)
        self.assertNotIn("if:", readback.split("run:")[0])

    def test_attached_package_reads_back_byte_identical(self):
        upload = action_step("Upload and read back the package asset")
        self.assertIn("sha256sum --check --strict", upload)

    def test_npm_readback_requires_the_ci_built_integrity(self):
        readback = action_step("Read back the npm publication")
        self.assertIn('state.startswith("present")', readback)
        self.assertIn("classify_registry_lookup", readback)
        # Integrity is the gate; attestation shape is advisory (ADR-0040).
        self.assertIn("require_attestation=False", readback)
        self.assertIn("require_attestation=False", action_step("Select the exact Pi npm tarball"))

    def test_release_goes_public_only_after_every_channel(self):
        publish = step_index("Publish the Release")
        for earlier in ("Upload and read back the package asset",
                        "Publish the Claude marketplace channel",
                        "Publish the Codex marketplace channel",
                        "Read back the npm publication"):
            self.assertLess(step_index(earlier), publish, earlier)
        self.assertIn('[ "$DRAFT" = false ] && [ "$NAMED" = "$TAG" ]', action_step("Publish the Release"))

    def test_receipt_is_written_after_the_release_is_public(self):
        self.assertLess(step_index("Publish the Release"),
                        step_index("Attach the publication receipt"))
        self.assertNotIn('"published-and-read-back"', action_text())


class AdvisoryCheckTest(unittest.TestCase):
    def test_codex_ruleset_audit_warns_instead_of_blocking(self):
        audit = action_step("Audit Codex distribution rulesets")
        self.assertIn("continue-on-error: true", audit)
        self.assertIn("::warning::", audit)

    def test_npm_provenance_is_advisory(self):
        self.assertIn("::warning::npm provenance", action_step("Read back the npm publication"))

    def test_pre_tag_checks_are_advisory(self):
        self.assertIn("run-pre-tag", jobs()["preflight"])
        self.assertIn("(not blocking)", jobs()["preflight"])


class ChannelTest(unittest.TestCase):
    def test_codex_channel_uses_the_git_dist_tag_until_npm_resumes(self):
        channel = action_step("Publish the Codex marketplace channel")
        self.assertIn("--catalog-mode git", channel)
        self.assertNotIn("npm publish", action_text().replace("ca-pi to npm", ""))

    def test_claude_channel_is_published(self):
        self.assertIn("tools/promote-claude-marketplace.py",
                      action_step("Publish the Claude marketplace channel"))

    def test_pushing_steps_carry_the_publisher_token(self):
        for name in ("Create and push the annotated tag",
                     "Publish the Claude marketplace channel",
                     "Publish the Codex marketplace channel"):
            self.assertIn("GH_TOKEN: ${{ inputs.github-token }}", action_step(name), name)


if __name__ == "__main__":
    unittest.main()
