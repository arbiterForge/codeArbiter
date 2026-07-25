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
  PreflightExecutionTest    #378/#385 — the preflight's own shell, executed
                                   against fake GitHub responses
  PublishExecutionTest      #380 — the publisher's own shell, executed against
                                   fake git/gh responses: fresh, tag-only
                                   resume, already published, tag at the wrong
                                   commit, and Release at the wrong commit
  RegistrationTest                 a release.yml-only edit must start the CI
                                   job that runs this file

Stdlib only; the workflow is parsed textually, like every other workflow
contract in this directory. The two execution classes need a POSIX shell and
so are skipped on Windows — the structural classes above run everywhere, and
the hooks job's ubuntu/macos cells run all of it.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def _step_run(job: str, name_fragment: str) -> str:
    """The dedented body of a named step's `run: |` block, verbatim from the
    shipped workflow. The execution tests below run exactly this text — no
    transcription of the logic into the test, which would only assert that a
    copy behaves, not that the workflow does."""
    lines = _jobs()[job].splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines)
              if line.startswith("      - name:") and name_fragment in line]
    if len(starts) != 1:
        raise AssertionError(
            f"{job}: {len(starts)} steps match {name_fragment!r}, expected exactly 1")
    index = starts[0] + 1
    while index < len(lines) and lines[index].strip() != "run: |":
        if lines[index].startswith("      - "):
            raise AssertionError(f"{job}/{name_fragment}: step has no `run: |` block")
        index += 1
    body = []
    for line in lines[index + 1:]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line[10:] if len(line) > 10 else "\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# Hermetic execution harness: the real step text, fake `git`/`gh`/`python3`, a
# temp cwd holding only a copy of _releaselib.py. Nothing touches the network,
# the repo, or a real tag.
#
# The fakes are shell FUNCTIONS rather than scripts on PATH: a function wins
# over any PATH lookup in every bash, whereas Git Bash re-prepends /usr/bin to
# an inherited PATH and would silently run the real `git`.
# --------------------------------------------------------------------------- #

_STUB_PRELUDE = """
git() {
  echo "git $*" >> "$STUB_LOG"
  if [ "$1" = "ls-remote" ]; then cat "$STUB_LS_REMOTE"; fi
  return 0
}
gh() {
  echo "gh $*" >> "$STUB_LOG"
  if [ "$1" = "api" ]; then
    for arg in "$@"; do
      if [ "$arg" = ".check_runs" ]; then
        "$STUB_PYTHON" -c 'import json,os;print(json.dumps(json.load(open(os.environ["STUB_CHECKS"]))["check_runs"]))'
        return 0
      fi
    done
    cat "$STUB_CHECKS"
    return 0
  fi
  if [ "$1" = "release" ] && [ "$2" = "view" ]; then
    if [ "$STUB_RELEASE" = "none" ]; then return 1; fi
    if [ "$STUB_RELEASE" = "published" ]; then DRAFT=false; else DRAFT=true; fi
    for arg in "$@"; do
      if [ "$arg" = ".isDraft" ]; then echo "$DRAFT"; return 0; fi
      if [ "$arg" = ".tagName" ]; then echo "$STUB_TAGNAME"; return 0; fi
    done
    echo "{\\"isDraft\\": $DRAFT, \\"tagName\\": \\"$STUB_TAGNAME\\"}"
    return 0
  fi
  return 0
}
python3() { "$STUB_PYTHON" "$@"; }
"""


def _bash():
    """A POSIX shell able to run the step bodies. On Windows `bash` on PATH is
    usually the WSL launcher, whose filesystem view is not the one subprocess
    hands it, so only Git Bash is accepted there."""
    if sys.platform != "win32":
        return shutil.which("bash")
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.isfile(candidate):
            return candidate
    return None


BASH = _bash()
POSIX_ONLY = unittest.skipIf(BASH is None, "no POSIX shell available")


class _ShellHarness(unittest.TestCase):
    """Runs one step body with stubbed `git`/`gh` and reports rc + the call log."""

    HEAD = "1" * 40
    OTHER = "2" * 40

    def _sandbox(self):
        root = Path(tempfile.mkdtemp(prefix="ca-release-"))
        self.addCleanup(shutil.rmtree, root, True)
        scripts = root / ".github" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy(HERE / "_releaselib.py", scripts / "_releaselib.py")
        return root

    def _run(self, script, *, env=None, ls_remote="", checks="[]",
             release="none", tagname="", notes="## [9.9.9] - 2026-07-24\n"):
        root = self._sandbox()
        (root / "notes.md").write_text(notes, encoding="utf-8", newline="\n")
        (root / "ls-remote.txt").write_text(ls_remote, encoding="utf-8", newline="\n")
        # Deliberately NOT `checks.json`: the step redirects its own `gh api`
        # output there, and the redirection truncates before the fake reads.
        (root / "stub-checks.json").write_text(checks, encoding="utf-8", newline="\n")
        environ = dict(os.environ)
        environ.update({
            "STUB_LOG": str(root / "calls.log"),
            "STUB_LS_REMOTE": str(root / "ls-remote.txt"),
            "STUB_CHECKS": str(root / "stub-checks.json"),
            "STUB_RELEASE": release,
            "STUB_TAGNAME": tagname,
            "STUB_PYTHON": sys.executable.replace("\\", "/"),
            "GITHUB_SHA": self.HEAD,
            "GITHUB_REPOSITORY": "arbiterForge/codeArbiter",
            "GITHUB_OUTPUT": str(root / "gh-output.txt"),
            # Nothing authenticating is set here: the fake `gh` never signs in
            # and never reaches the network.
        })
        environ.update(env or {})
        proc = subprocess.run([BASH, "-c", _STUB_PRELUDE + "\n" + script],
                              cwd=str(root), env=environ,
                              capture_output=True, text=True)
        log_path = root / "calls.log"
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        output_path = root / "gh-output.txt"
        step_output = (output_path.read_text(encoding="utf-8")
                       if output_path.exists() else "")
        return proc, log, step_output


@POSIX_ONLY
class PreflightExecutionTest(_ShellHarness):
    """#378 + #385, executed: the preflight's own shell against fake inputs."""

    @classmethod
    def setUpClass(cls):
        cls.branch_step = _step_run("preflight", "Refuse a dispatch off")
        cls.target_step = _step_run("preflight", "Resolve exactly one release target")
        cls.readiness_step = _step_run("preflight", "Require green merge readiness")

    def _check_run(self, conclusion="success", status="completed", head=None):
        head = self.HEAD if head is None else head
        return ('{"check_runs": [{"name": "[GATE ] | [REPO] | Merge readiness", '
                f'"status": "{status}", "conclusion": '
                + ("null" if conclusion is None else f'"{conclusion}"')
                + f', "head_sha": "{head}"}}]}}')

    # -- #378: the four-cell dispatch truth table ------------------------------
    def test_ca_only_selects_ca(self):
        proc, _, out = self._run(self.target_step,
                                 env={"CONFIRM": "2.6.1", "CODEX_CONFIRM": ""})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("target=ca\n", out)

    def test_codex_only_selects_ca_codex(self):
        proc, _, out = self._run(self.target_step,
                                 env={"CONFIRM": "", "CODEX_CONFIRM": "0.2.4"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("target=ca-codex\n", out)

    def test_neither_input_refuses(self):
        proc, _, out = self._run(self.target_step,
                                 env={"CONFIRM": "", "CODEX_CONFIRM": ""})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(out, "", "a refused dispatch must publish no target")

    def test_both_inputs_refuse_before_any_publisher_is_eligible(self):
        proc, _, out = self._run(self.target_step,
                                 env={"CONFIRM": "2.6.1", "CODEX_CONFIRM": "0.2.4"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("more than one plugin", proc.stdout + proc.stderr)
        self.assertEqual(out, "")

    def test_a_dispatch_off_main_is_refused(self):
        ok, _, _ = self._run(self.branch_step, env={"GITHUB_REF": "refs/heads/main"})
        self.assertEqual(ok.returncode, 0, ok.stderr)
        bad, _, _ = self._run(self.branch_step, env={"GITHUB_REF": "refs/heads/feat/x"})
        self.assertNotEqual(bad.returncode, 0)

    # -- #385: merge-readiness evidence for the exact commit -------------------
    def test_green_evidence_for_this_commit_proceeds(self):
        proc, _, _ = self._run(self.readiness_step, checks=self._check_run())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_pending_and_failed_evidence_all_refuse(self):
        cases = {
            "missing": '{"check_runs": []}',
            "pending": self._check_run(conclusion=None, status="in_progress"),
            "failure": self._check_run(conclusion="failure"),
            "cancelled": self._check_run(conclusion="cancelled"),
            "skipped": self._check_run(conclusion="skipped"),
        }
        for label, payload in cases.items():
            with self.subTest(evidence=label):
                proc, _, _ = self._run(self.readiness_step, checks=payload)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("refusing to tag", proc.stdout + proc.stderr)

    def test_green_evidence_for_another_commit_is_refused(self):
        proc, _, _ = self._run(self.readiness_step,
                               checks=self._check_run(head=self.OTHER))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sha_mismatch", proc.stdout + proc.stderr)


@POSIX_ONLY
class PublishExecutionTest(_ShellHarness):
    """#380, executed: fresh, resume, published, and both wrong-commit states."""

    STEP_NAME = "Create the tag and GitHub Release"
    VERIFY_NAME = "Verify the published Release"

    def _publish(self, job, tag, version, *, tag_at=None, release="none"):
        ls_remote = ""
        if tag_at:
            ls_remote = (f"9{'0' * 39}\trefs/tags/{tag}\n"
                         f"{tag_at}\trefs/tags/{tag}^{{}}\n")
        return self._run(_step_run(job, self.STEP_NAME),
                         env={"TAG": tag, "VER": version, "SUMMARY": ""},
                         ls_remote=ls_remote, release=release, tagname=tag)

    def test_fresh_publish_tags_and_releases(self):
        proc, log, _ = self._publish("release", "v9.9.9", "9.9.9")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: publish_fresh", proc.stdout)
        self.assertIn("git tag -a v9.9.9", log)
        self.assertIn("git push origin refs/tags/v9.9.9", log)
        self.assertIn("gh release create v9.9.9", log)

    def test_tag_only_resume_creates_the_release_without_retagging(self):
        proc, log, _ = self._publish("release", "v9.9.9", "9.9.9", tag_at=self.HEAD)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: resume_publish", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertIn("gh release create v9.9.9", log)

    def test_already_published_is_a_no_op(self):
        proc, log, _ = self._publish("release", "v9.9.9", "9.9.9",
                                     tag_at=self.HEAD, release="published")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: already_published", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("gh release create", log)

    def test_a_tag_at_another_commit_aborts_before_publishing(self):
        for job, tag, version in (("release", "v9.9.9", "9.9.9"),
                                  ("release-codex", "ca-codex-v0.9.9", "0.9.9")):
            with self.subTest(job=job):
                proc, log, _ = self._publish(job, tag, version, tag_at=self.OTHER)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("publish state: abort_mismatch", proc.stdout)
                self.assertNotIn("gh release create", log)
                self.assertNotIn("git tag -a", log)

    def test_a_published_release_on_a_tag_at_another_commit_aborts(self):
        # The regression #380 names: a non-draft Release used to short-circuit
        # the comparison, so a wrong-commit tag reported a clean rerun.
        for job, tag, version in (("release", "v9.9.9", "9.9.9"),
                                  ("release-codex", "ca-codex-v0.9.9", "0.9.9")):
            with self.subTest(job=job):
                proc, log, _ = self._publish(job, tag, version, tag_at=self.OTHER,
                                             release="published")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("abort_mismatch", proc.stdout)
                self.assertNotIn("gh release create", log)

    def test_the_codex_publisher_never_claims_the_latest_badge(self):
        proc, log, _ = self._publish("release-codex", "ca-codex-v0.9.9", "0.9.9")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gh release create ca-codex-v0.9.9", log)
        self.assertNotIn("--latest", log)

    def test_read_back_rejects_a_tag_that_moved_off_the_dispatched_commit(self):
        script = _step_run("release", self.VERIFY_NAME)
        good, _, _ = self._run(script, env={"TAG": "v9.9.9"}, release="published",
                               tagname="v9.9.9",
                               ls_remote=f"{self.HEAD}\trefs/tags/v9.9.9\n")
        self.assertEqual(good.returncode, 0, good.stderr)
        moved, _, _ = self._run(script, env={"TAG": "v9.9.9"}, release="published",
                                tagname="v9.9.9",
                                ls_remote=f"{self.OTHER}\trefs/tags/v9.9.9\n")
        self.assertNotEqual(moved.returncode, 0)
        self.assertIn("not the dispatched commit", moved.stdout + moved.stderr)

    def test_read_back_rejects_a_release_naming_another_tag(self):
        script = _step_run("release", self.VERIFY_NAME)
        proc, _, _ = self._run(script, env={"TAG": "v9.9.9"}, release="published",
                               tagname="v9.9.8",
                               ls_remote=f"{self.HEAD}\trefs/tags/v9.9.9\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("names tag", proc.stdout + proc.stderr)

    def test_read_back_rejects_a_draft(self):
        script = _step_run("release", self.VERIFY_NAME)
        proc, _, _ = self._run(script, env={"TAG": "v9.9.9"}, release="draft",
                               tagname="v9.9.9",
                               ls_remote=f"{self.HEAD}\trefs/tags/v9.9.9\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("draft/unpublished", proc.stdout + proc.stderr)


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
