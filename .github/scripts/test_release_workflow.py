#!/usr/bin/env python3
"""codeArbiter — contract tests for the hosted release workflow.

Run: python .github/scripts/test_release_workflow.py

`.github/workflows/release.yml` holds `contents: write` and publishes tags and
GitHub Releases — externally visible writes that no later job can roll back.
`test_release_lib.py` proves the pure helpers; these assertions parse the
SHIPPED workflow, so removing or weakening a guard turns this suite red even
while every `_releaselib` unit test stays green.

  DispatchExclusivityTest   #378 — exactly one plugin per dispatch, decided by
                                   one read-only preflight both publishers need
  MergeReadinessGateTest    #385 — the exact commit being tagged must carry a
                                   green `[GATE ] | [REPO] | Merge readiness`
  ExistingTagIntegrityTest  #380 — an existing tag is peeled and compared to
                                   GITHUB_SHA through the shared classifier
  RegistrationTest                 a release.yml-only edit must start the CI
                                   job that runs this file

Stdlib only; the workflow is parsed textually, like every other workflow
contract in this directory.
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import _releaselib  # noqa: E402 — needs the sys.path mutation above
from test_ci_impact import paths_filter, push_trigger_paths, workflow_jobs  # noqa: E402

RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The two write-token publishers, and the read-only job that authorizes them.
PUBLISH_JOBS = ("release", "release-codex")
PREFLIGHT_JOB = "preflight"

# A job-level `if:` that uses one of these status functions opts OUT of the
# implicit "all `needs` succeeded" gate — which would let a publisher run after
# its own preflight refused the dispatch.
_STATUS_ESCAPES = ("always()", "!cancelled()", "cancelled()", "failure()")


def _release() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def _jobs() -> dict:
    return workflow_jobs(_release())


def _job_if(block: str) -> str:
    """The job-level `if:` expression (two-space indent), '' when absent."""
    match = re.search(r"(?m)^    if:[ ]*(.+)$", block)
    return match.group(1).strip() if match else ""


class DispatchExclusivityTest(unittest.TestCase):
    """#378: one dispatch releases exactly one plugin — enforced, not documented."""

    def test_a_read_only_preflight_job_exists(self):
        self.assertIn(PREFLIGHT_JOB, _jobs(),
                      "release.yml has no preflight job to arbitrate the dispatch")

    def test_top_level_permissions_are_read_only(self):
        # Least privilege: the write token is granted at the publishing jobs,
        # so the preflight that authorizes them can never hold one.
        text = _release()
        header = text.split("jobs:", 1)[0]
        self.assertRegex(header, r"(?m)^permissions:\n  contents: read$",
                         "top-level permissions must be `contents: read`")

    def test_only_the_publish_jobs_carry_a_write_token(self):
        writers = sorted(job for job, block in _jobs().items()
                         if re.search(r"(?m)^      contents: write$", block))
        self.assertEqual(writers, sorted(PUBLISH_JOBS),
                         "exactly the two publishers may declare `contents: write`")

    def test_preflight_holds_no_write_permission(self):
        block = _jobs()[PREFLIGHT_JOB]
        self.assertRegex(block, r"(?m)^      contents: read$",
                         "the preflight job must pin `contents: read`")
        self.assertNotIn("contents: write", block,
                         "#385: the preflight job must never receive a write token")

    def test_preflight_resolves_the_target_through_the_shared_helper(self):
        block = _jobs()[PREFLIGHT_JOB]
        self.assertIn("_releaselib.py select-target", block,
                      "#378: the preflight must resolve the target via _releaselib")
        self.assertIn("target=$TARGET", block,
                      "the resolved target must be published as a job output")

    def test_every_publish_job_depends_on_the_preflight(self):
        jobs = _jobs()
        for job in PUBLISH_JOBS:
            with self.subTest(job=job):
                self.assertRegex(
                    jobs[job], r"(?m)^    needs: preflight$",
                    f"{job} must not start without the preflight's authorization")

    def test_publish_jobs_gate_on_the_single_resolved_target(self):
        jobs = _jobs()
        expected = {"release": "'ca'", "release-codex": "'ca-codex'"}
        for job, literal in expected.items():
            with self.subTest(job=job):
                condition = _job_if(jobs[job])
                self.assertIn(f"needs.preflight.outputs.target == {literal}", condition,
                              f"{job} must run only for the resolved target {literal}")
                # The independent per-input gates are exactly the #378 defect:
                # each tested only its OWN confirmation, so supplying both
                # started both write-token publishers.
                self.assertNotIn("inputs.confirm != ''", condition)
                self.assertNotIn("inputs.codex_confirm != ''", condition)

    def test_publish_jobs_keep_the_default_branch_guard(self):
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                self.assertIn("github.ref == 'refs/heads/main'", _job_if(block))

    def test_no_publish_job_escapes_the_needs_success_gate(self):
        # A status-check function in a job `if:` overrides the implicit
        # "all needs succeeded" rule, which would run the publisher anyway.
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            condition = _job_if(block)
            for escape in _STATUS_ESCAPES:
                with self.subTest(job=job, escape=escape):
                    self.assertNotIn(escape, condition)

    def test_the_preflight_refuses_a_dispatch_off_the_default_branch(self):
        self.assertIn("refs/heads/main", _jobs()[PREFLIGHT_JOB],
                      "the preflight must refuse a dispatch off the default branch")


class MergeReadinessGateTest(unittest.TestCase):
    """#385: publish only on green merge-readiness evidence for the exact SHA."""

    def test_the_gate_name_matches_the_shipped_ci_aggregate(self):
        # A rename in ci.yml that this constant does not follow would silently
        # turn the gate into "no evidence found" — which must stay fail-closed,
        # but should be caught here rather than at the next release.
        ci_gate = workflow_jobs(CI_WORKFLOW.read_text(encoding="utf-8"))["ci-passed"]
        declared = re.search(r'(?m)^    name: "(.+)"$', ci_gate).group(1)
        self.assertEqual(_releaselib.MERGE_READINESS_CHECK, declared)

    def test_the_preflight_queries_check_runs_for_the_dispatched_sha(self):
        block = _jobs()[PREFLIGHT_JOB]
        self.assertIn("commits/${GITHUB_SHA}/check-runs", block,
                      "#385: merge readiness must be resolved for GITHUB_SHA itself")
        self.assertIn("_releaselib.py merge-readiness", block,
                      "the verdict must come from the tested classifier")

    def test_only_a_green_verdict_proceeds(self):
        block = _jobs()[PREFLIGHT_JOB]
        # `green` is the one accepting arm; everything else, including an
        # unrecognised label from a crashed helper, must exit non-zero.
        self.assertRegex(block, r"(?m)^\s+green\)", "no accepting `green` arm")
        self.assertRegex(block, r"(?m)^\s+\*\)[\s\S]{0,400}?exit 1",
                         "the fail-closed default arm must exit 1")

    def test_the_gate_runs_before_any_write_token_job(self):
        # Structural restatement of the ordering the `needs` edge buys us: no
        # publisher may resolve merge readiness for itself.
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                self.assertNotIn("merge-readiness", block)


class ExistingTagIntegrityTest(unittest.TestCase):
    """#380: never resume onto a tag that names another commit."""

    def test_both_publishers_peel_the_remote_tag(self):
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                self.assertIn('"refs/tags/$TAG^{}"', block,
                              "an annotated tag must be peeled to its commit")
                self.assertIn("_releaselib.py peel-tag", block,
                              "peeling must route through the tested helper")

    def test_both_publishers_classify_before_tagging(self):
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                self.assertIn("_releaselib.py classify", block,
                              "#380: the shared publish-state classifier must decide")
                self.assertIn('"$GITHUB_SHA"', block)

    def test_the_bare_tag_exists_skip_is_gone(self):
        # The exact defect: any remote hit was treated as resumable and tag
        # creation was skipped without comparing the tag to GITHUB_SHA.
        text = _release()
        self.assertNotIn('if git ls-remote --exit-code --tags origin "$TAG"', text)
        self.assertNotIn("already on remote — skipping tag creation", text)

    def test_a_mismatch_fails_before_gh_release_create(self):
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                case_body = block.split("STATE=", 1)[1]
                mismatch = case_body.split("*)", 1)[1]
                self.assertNotIn("gh release create", mismatch.split("esac", 1)[0],
                                 "the fail-closed arm must not publish")
                self.assertIn("exit 1", mismatch.split("esac", 1)[0])

    def test_verification_checks_the_tag_and_its_commit_not_only_isdraft(self):
        for job, block in ((j, _jobs()[j]) for j in PUBLISH_JOBS):
            with self.subTest(job=job):
                verify = block.split("Verify the published Release", 1)
                self.assertEqual(len(verify), 2, f"{job} has no read-back step")
                body = verify[1]
                self.assertIn(".tagName", body, "the read-back must compare tagName")
                self.assertIn("FINAL_SHA", body,
                              "the read-back must re-peel the tag to its commit")
                self.assertIn('[ "$FINAL_SHA" = "$GITHUB_SHA" ]', body)
                self.assertIn(".isDraft", body)


class RegistrationTest(unittest.TestCase):
    """A release.yml-only edit must start the CI job that runs this file."""

    def test_release_workflow_is_in_the_hooks_filter(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/release.yml", paths_filter(ci, "hooks"),
                      "the hooks filter must flag a release.yml-only change")

    def test_release_workflow_starts_a_push_run(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/release.yml", push_trigger_paths(ci),
                      "a push touching only release.yml must still start CI")

    def test_ci_invokes_this_suite(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python .github/scripts/test_release_workflow.py", ci,
                      "this contract suite must run in CI")


if __name__ == "__main__":
    unittest.main()
