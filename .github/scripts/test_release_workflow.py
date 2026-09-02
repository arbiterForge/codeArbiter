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
  PublishExecutionTest      #380 — the shared publish action's own shell,
                                   executed against fake git/gh/node responses:
                                   fresh, tag-only resume, already published,
                                   tag at the wrong commit, and Release at the
                                   wrong commit
  LaneIsolationTest         #382 — four lanes, each with its own manifest,
                                   CHANGELOG and tag namespace, only ca taking
                                   the "Latest" badge, and every declared
                                   target having exactly one publisher
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
# The publish mechanics all four lanes share (#382). Every assertion that used
# to read a publisher job's shell now reads THIS file, and proves it for all
# four lanes at once rather than for two of four copies.
PUBLISH_ACTION = REPO_ROOT / ".github" / "actions" / "publish-release" / "action.yml"
PUBLISH_ACTION_REF = "./.github/actions/publish-release"

# What each lane must bring of its own. Issue #382's acceptance criteria name
# these paths; the tests below also assert every one of them EXISTS, because a
# typo here is otherwise discovered by a failed release rather than by CI.
LANES = {
    "release": {
        "target": "ca",
        "manifest": "plugins/ca/.claude-plugin/plugin.json",
        "changelog": "CHANGELOG.md",
        "tag-prefix": "v",
        "title-prefix": "codeArbiter",
        "mark-latest": '"true"',
    },
    "release-codex": {
        "target": "ca-codex",
        "manifest": "plugins/ca-codex/.codex-plugin/plugin.json",
        "changelog": "plugins/ca-codex/CHANGELOG.md",
        "tag-prefix": "ca-codex-v",
        "title-prefix": "ca-codex",
        "mark-latest": '"false"',
    },
    "release-sandbox": {
        "target": "ca-sandbox",
        "manifest": "plugins/ca-sandbox/.claude-plugin/plugin.json",
        "changelog": "plugins/ca-sandbox/CHANGELOG.md",
        "tag-prefix": "ca-sandbox-v",
        "title-prefix": "ca-sandbox",
        "mark-latest": '"false"',
    },
    "release-pi": {
        "target": "ca-pi",
        "manifest": "plugins/ca-pi/package.json",
        "companion-manifest": "package.json",
        "changelog": "plugins/ca-pi/CHANGELOG.md",
        "tag-prefix": "ca-pi-v",
        "title-prefix": "ca-pi",
        "mark-latest": '"false"',
    },
}

# The write-token publishers, and the read-only job that authorizes them.
PUBLISH_JOBS = tuple(LANES)
PREFLIGHT_JOB = "preflight"

# Auto-publish-on-merge: one push-triggered write-token job per target,
# mirroring LANES/PUBLISH_JOBS and creating the corresponding GitHub Release
# only after the existing eligibility preflight passes.
AUTO_LANES = {
    "auto-release": {"target": "ca"},
    "auto-release-codex": {"target": "ca-codex"},
    "auto-release-sandbox": {"target": "ca-sandbox"},
    "auto-release-pi": {"target": "ca-pi"},
}
AUTO_PUBLISH_JOBS = tuple(AUTO_LANES)
AUTO_PREFLIGHT_JOB = "auto-preflight"
MANUAL_CODEX_PROVENANCE_JOB = "codex-provenance"
AUTO_CODEX_PROVENANCE_JOB = "auto-codex-provenance"
AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB = "auto-command-route-release-audit"

# #654: two triggers share this one file, and every job belongs to exactly one
# of them. The manual lane reads dispatch inputs that do not exist on the
# auto-tag lane, so a job that can start on both is not a lane — it is a bug.
TRIGGERS = ("workflow_dispatch", "workflow_run")
JOB_TRIGGER = dict(
    [(PREFLIGHT_JOB, "workflow_dispatch")]
    + [(job, "workflow_dispatch") for job in PUBLISH_JOBS]
    + [(MANUAL_CODEX_PROVENANCE_JOB, "workflow_dispatch")]
    + [(AUTO_PREFLIGHT_JOB, "workflow_run")]
    + [(job, "workflow_run") for job in AUTO_PUBLISH_JOBS]
    + [(AUTO_CODEX_PROVENANCE_JOB, "workflow_run")]
    + [(AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB, "workflow_run")]
)

# A job-level `if:` that uses one of these status functions opts OUT of the
# implicit "all `needs` succeeded" gate — which would let a publisher run after
# its own preflight refused the dispatch.
_STATUS_ESCAPES = ("always", "cancelled", "failure")


def _release() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def _jobs() -> dict:
    return workflow_jobs(_release())


def _named_step(job: str, name: str) -> str:
    """Return one named workflow step without borrowing evidence from siblings."""
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - |\Z)",
        job,
    )
    if not match:
        raise AssertionError(f"missing workflow step: {name}")
    return match.group(0)


def _job_if(block: str) -> str:
    """The job-level `if:` expression (two-space indent), '' when absent."""
    match = re.search(r"(?m)^    if:[ ]*(.+)$", block)
    return match.group(1).strip() if match else ""


def _job_needs(block: str) -> tuple:
    """The job's `needs:` targets — scalar, inline-list, or block-list form.

    Every form is read rather than only the scalar one this file happens to
    use today, because a `needs:` this helper could not parse would read as
    "depends on nothing", and a job that depends on nothing is exactly what
    the trigger-isolation walk below treats as ungated.
    """
    scalar = re.search(r"(?m)^    needs:[ ]+([\w.-]+)[ ]*$", block)
    if scalar:
        return (scalar.group(1),)
    inline = re.search(r"(?m)^    needs:[ ]*\[(.+)\][ ]*$", block)
    if inline:
        return tuple(name.strip().strip("'\"") for name in inline.group(1).split(","))
    listed = re.search(r"(?m)^    needs:[ ]*\n((?:      - .+\n)+)", block)
    if listed:
        return tuple(re.findall(r"-[ ]+([\w.-]+)", listed.group(1)))
    if re.search(r"(?m)^    needs:", block):
        raise AssertionError("a `needs:` edge this suite cannot parse — "
                             "an unreadable dependency must not read as none")
    return ()


def _condition_triggers(condition: str, *, allow_status_escape: bool = False) -> set:
    """Return the workflow triggers permitted by one supported condition."""
    if not allow_status_escape and any(
        re.search(rf"(?<![\w.]){escape}\s*\(", condition, re.IGNORECASE)
        for escape in _STATUS_ESCAPES
    ):
        raise AssertionError("a status function bypasses the implicit needs gate")
    if "github.event_name" not in condition:
        return set(TRIGGERS)
    if "||" in condition:
        raise AssertionError("unsupported boolean event guard")
    named = re.findall(r"github\.event_name == '([\w_]+)'", condition)
    if len(named) != 1 or named[0] not in TRIGGERS:
        raise AssertionError("unsupported boolean event guard")
    return {named[0]}


def _gated_triggers(job: str, jobs: dict, chain: tuple = ()) -> set:
    """Every event name `job` can start on (#654).

    A job's own `if:` pins it when that expression names an event; otherwise
    it inherits from the jobs it `needs`, because GitHub skips a dependent
    whose dependency skipped — which is why the four manual publishers carry
    no event guard of their own and do not need one.

    A job that neither names an event nor reaches one through `needs` starts
    on every trigger the file declares. That is not a conservative reading:
    it is precisely what the shipped dispatch preflight did.

    Only the single-quoted `github.event_name == 'X'` form is recognised. A
    correct guard written some other way (double quotes, or gating on an
    input's presence) reads here as "names no event" and turns these tests
    red — fail-closed, and deliberately so, but it means a red from this
    helper against a guard you believe is right is a signal to WIDEN the
    pattern below, not to weaken the guard in release.yml.
    """
    if job in chain:
        raise AssertionError(f"cyclic `needs` chain through {job!r}")
    if job not in jobs:
        raise AssertionError(f"`needs` names undeclared job {job!r}")
    condition = _job_if(jobs[job])
    permitted = _condition_triggers(
        condition,
        allow_status_escape=job == AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB,
    )
    parents = _job_needs(jobs[job])
    if not parents:
        return permitted
    for parent in parents:
        permitted &= _gated_triggers(parent, jobs, (*chain, job))
    return permitted


def _extract_run(text: str, name_fragment: str, step_indent: int, where: str) -> str:
    """The dedented body of a named step's `run: |` block, verbatim from the
    shipped YAML. The execution tests below run exactly this text — no
    transcription of the logic into the test, which would only assert that a
    copy behaves, not that the shipped file does.

    `step_indent` is the column of the step's `- name:`; the body sits four
    columns further in (`- name:` -> keys at +2 -> block scalar at +4). A
    workflow job nests one level deeper than a composite action's steps, which
    is the only difference between the two callers below."""
    key_indent = step_indent + 2
    body_indent = step_indent + 4
    lines = text.splitlines(keepends=True)
    marker = " " * step_indent + "- name:"
    starts = [i for i, line in enumerate(lines)
              if line.startswith(marker) and name_fragment in line]
    if len(starts) != 1:
        raise AssertionError(
            f"{where}: {len(starts)} steps match {name_fragment!r}, expected exactly 1")
    index = starts[0] + 1
    while index < len(lines) and lines[index].strip() != "run: |":
        if lines[index].startswith(" " * step_indent + "- "):
            raise AssertionError(f"{where}/{name_fragment}: step has no `run: |` block")
        index += 1
    body = []
    for line in lines[index + 1:]:
        if line.strip() and not line.startswith(" " * body_indent):
            break
        body.append(line[body_indent:] if len(line) > body_indent else "\n")
    del key_indent
    return "".join(body)


def _step_run(job: str, name_fragment: str) -> str:
    """A named step's shell, from a job in release.yml (steps at column 6)."""
    return _extract_run(_jobs()[job], name_fragment, 6, job)


def _action_step(name_fragment: str) -> str:
    """A named step's shell, from the shared publish action (steps at column 4).

    #382: the four lanes run this one text, so an assertion here is an assertion
    about every lane — strictly stronger than the previous suite, which proved
    the guards for `release` and `release-codex` and would have said nothing
    about a hand-copied third and fourth.
    """
    return _extract_run(PUBLISH_ACTION.read_text(encoding="utf-8"),
                        name_fragment, 4, "publish-release action")


def _lane_inputs(job: str) -> dict:
    """The `with:` mapping a publisher job hands the shared publish action."""
    block = _jobs()[job]
    tail = block.split(f"- uses: {PUBLISH_ACTION_REF}", 1)
    if len(tail) != 2:
        raise AssertionError(f"{job} does not use {PUBLISH_ACTION_REF}")
    found = {}
    for line in tail[1].splitlines()[1:]:
        if not line.strip() or line.strip() == "with:":
            continue
        # The `with:` keys sit two columns inside `with:` itself; anything
        # shallower ends this step and must not be read as one of its inputs.
        if not line.startswith(" " * 10):
            break
        match = re.match(r"\s*([a-z-]+):\s*(.+?)\s*$", line)
        if match:
            found[match.group(1)] = match.group(2)
    if not found:
        raise AssertionError(f"{job} passes no inputs to {PUBLISH_ACTION_REF}")
    return found


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
    case " $* " in
      *"/releases?per_page=100"*)
        case "$STUB_RELEASE" in
          unavailable)
            echo "simulated Release API failure" >&2
            return 1
            ;;
          none)
            printf '[[]]\n'
            return 0
            ;;
          published) DRAFT=false ;;
          *) DRAFT=true ;;
        esac
        printf '[[{"draft":%s,"tag_name":"%s"}]]\n' "$DRAFT" "$STUB_TAGNAME"
        return 0
        ;;
      *"/releases/tags/"*)
        case "$STUB_RELEASE" in
          none|draft)
            printf 'HTTP/2.0 404 Not Found\ncontent-type: application/json\n\n{}\n'
            return 1
            ;;
          unavailable)
            echo "simulated Release API failure" >&2
            return 1
            ;;
          published) DRAFT=false ;;
          *) DRAFT=true ;;
        esac
        printf 'HTTP/2.0 200 OK\ncontent-type: application/json\n\n'
        printf '{"draft":%s,"tag_name":"%s"}\n' "$DRAFT" "$STUB_TAGNAME"
        return 0
        ;;
    esac
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
node() {
  echo "node $*" >> "$STUB_LOG"
  # `node -p "require('./<path>').version"`. The ROOT package.json is ca-pi's
  # companion manifest, so it must answer separately from the plugin manifest -
  # otherwise the disagreement guard could never be observed to fire.
  case "$*" in
    *"require('./package.json')"*) echo "$STUB_ROOT_VERSION" ;;
    *) echo "$STUB_MANIFEST_VERSION" ;;
  esac
}
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
        shutil.copy(
            HERE / "check_command_route_release_state.py",
            scripts / "check_command_route_release_state.py")
        # The shim (copied above) resolves `core/pysrc/_releaselib.py` at
        # import time via its own __file__ -> parents[2] -- i.e. TWO levels
        # above `.github/scripts/`, exactly like this synthetic tree's
        # `.github/scripts/` is two levels below `root`. Without the mechanism
        # module also present here, every subprocess invocation of the copied
        # shim raises FileNotFoundError before it does anything else. This is
        # NOT a fallback for a genuinely absent mechanism (the spec forbids
        # that) -- it is reproducing the real on-disk shape the shim already
        # requires, the same way the shim itself is copied above.
        core_pysrc = root / "core" / "pysrc"
        core_pysrc.mkdir(parents=True)
        shutil.copy(HERE.parent.parent / "core" / "pysrc" / "_releaselib.py",
                    core_pysrc / "_releaselib.py")
        # The DECLARED file, for the same reason the mechanism module is
        # copied above: reproduce the real on-disk shape, do not stub it.
        # Since A-4.4 the shim reads its target register from here rather
        # than from a literal, so `select-target-named` resolves nothing
        # without it -- and CI, which checks out the whole repo, always has
        # it. Copying the REAL file (never a synthetic one) is also what
        # makes these execution tests exercise this repository's actual
        # declared targets rather than a fixture that could drift from them.
        declared = root / ".codearbiter"
        declared.mkdir(parents=True)
        shutil.copy(
            HERE.parent.parent / ".codearbiter" / "release-targets.md",
            declared / "release-targets.md")
        return root

    def _run(self, script, *, env=None, ls_remote="", checks="[]",
             release="none", tagname="", notes="## [9.9.9] - 2026-07-24\n",
             manifest_version="9.9.9", root_version=None):
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
            "STUB_MANIFEST_VERSION": manifest_version,
            "STUB_ROOT_VERSION": (manifest_version if root_version is None
                                  else root_version),
            "STUB_PYTHON": sys.executable.replace("\\", "/"),
            "GITHUB_SHA": self.HEAD,
            "GITHUB_REPOSITORY": "arbiterForge/codeArbiter",
            "GITHUB_OUTPUT": str(root / "gh-output.txt"),
            # Nothing authenticating is set here: the fake `gh` never signs in
            # and never reaches the network.
            # Mirrors action.yml's own `create-release` default ("true") so
            # every existing call site that never mentions it keeps exercising
            # the manual-dispatch behavior unchanged; a test can still override
            # via `env={"CREATE_RELEASE": "false"}`.
            "CREATE_RELEASE": "true",
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
        cls.maxDiff = None
        cls.readiness_step = _step_run("preflight", "Require green merge readiness")

    def _check_run(self, conclusion="success", status="completed", head=None):
        head = self.HEAD if head is None else head
        return ('{"check_runs": [{"name": "[GATE ] | [REPO] | Merge readiness", '
                f'"status": "{status}", "conclusion": '
                + ("null" if conclusion is None else f'"{conclusion}"')
                + f', "head_sha": "{head}"}}]}}')

    # -- #378 / #382: the dispatch truth table, over all four inputs -----------
    #
    # The inputs are positional in _releaselib.RELEASE_TARGETS order, and the
    # workflow passes them in that order. A lane wired to the wrong input would
    # resolve the wrong plugin and publish an irreversible tag for it, so every
    # single-input case is asserted rather than sampled.
    DISPATCH_INPUTS = ("CONFIRM", "CODEX_CONFIRM", "SANDBOX_CONFIRM", "PI_CONFIRM")

    def _select(self, **supplied):
        """Run the preflight's resolver with every input set — blank unless
        named. All four must be present: the step runs under `set -u`, exactly
        as it does on the runner, where the job's `env:` always defines them."""
        env = {name: "" for name in self.DISPATCH_INPUTS}
        env.update(supplied)
        return self._run(self.target_step, env=env)

    def test_each_input_alone_selects_its_own_plugin(self):
        cases = {
            "CONFIRM": ("2.6.1", "ca"),
            "CODEX_CONFIRM": ("0.2.4", "ca-codex"),
            "SANDBOX_CONFIRM": ("0.1.5", "ca-sandbox"),
            "PI_CONFIRM": ("0.1.28", "ca-pi"),
        }
        self.assertEqual(tuple(cases), self.DISPATCH_INPUTS)
        self.assertEqual(tuple(t for _, t in cases.values()),
                         _releaselib.RELEASE_TARGETS,
                         "the dispatch inputs must stay in RELEASE_TARGETS order")
        for name, (version, target) in cases.items():
            with self.subTest(input=name):
                proc, _, out = self._select(**{name: version})
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(f"target={target}\n", out)

    def test_no_input_refuses(self):
        proc, _, out = self._select()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(out, "", "a refused dispatch must publish no target")

    def test_any_two_inputs_refuse_before_any_publisher_is_eligible(self):
        versions = dict(zip(self.DISPATCH_INPUTS,
                            ("2.6.1", "0.2.4", "0.1.5", "0.1.28")))
        pairs = [(a, b) for i, a in enumerate(self.DISPATCH_INPUTS)
                 for b in self.DISPATCH_INPUTS[i + 1:]]
        self.assertEqual(len(pairs), 6, "all six pairs must be covered")
        for first, second in pairs:
            with self.subTest(inputs=(first, second)):
                proc, _, out = self._select(**{first: versions[first],
                                               second: versions[second]})
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
    """#380, executed: fresh, resume, published, and both wrong-commit states.

    #382 moved this shell out of the two publisher jobs and into the action all
    four lanes use, so each case below now covers every lane. The cases that
    depend on the tag NAMESPACE are run once per lane's prefix, because
    `TAG_VERSION="${TAG##*v}"` has to strip `ca-sandbox-v` and `ca-pi-v` just as
    correctly as a bare `v`, and a namespace it mis-parsed would reach the
    classifier as a version mismatch and abort a legitimate release."""

    STEP_NAME = "Create the tag and GitHub Release"
    VERIFY_NAME = "Verify the published Release"
    VERSION_NAME = "Resolve and verify version"

    # (lane, tag) for a 9.9.9 release in each namespace.
    NAMESPACES = tuple((job, LANES[job]["tag-prefix"] + "9.9.9") for job in LANES)

    def _publish(self, tag, version="9.9.9", *, tag_at=None, release="none",
                 mark_latest="false", summary="", title_prefix="codeArbiter",
                 create_release="true"):
        ls_remote = ""
        if tag_at:
            ls_remote = (f"9{'0' * 39}\trefs/tags/{tag}\n"
                         f"{tag_at}\trefs/tags/{tag}^{{}}\n")
        return self._run(_action_step(self.STEP_NAME),
                         env={"TAG": tag, "VER": version, "SUMMARY": summary,
                              "TITLE_PREFIX": title_prefix,
                              "MARK_LATEST": mark_latest,
                              "CREATE_RELEASE": create_release},
                         ls_remote=ls_remote, release=release, tagname=tag)

    def test_fresh_publish_tags_and_releases(self):
        proc, log, _ = self._publish("v9.9.9")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: publish_fresh", proc.stdout)
        self.assertIn("git tag -a v9.9.9", log)
        self.assertIn("git push origin refs/tags/v9.9.9", log)
        self.assertIn("gh release create v9.9.9", log)

    def test_every_namespace_publishes_fresh(self):
        # Proves the namespace parsing, which is the one thing the four lanes do
        # not share: each supplies its own tag prefix.
        for job, tag in self.NAMESPACES:
            with self.subTest(lane=job, tag=tag):
                proc, log, _ = self._publish(tag)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("publish state: publish_fresh", proc.stdout)
                self.assertIn(f"git tag -a {tag}", log)
                self.assertIn(f"gh release create {tag}", log)

    def test_tag_only_resume_creates_the_release_without_retagging(self):
        proc, log, _ = self._publish("v9.9.9", tag_at=self.HEAD)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: resume_publish", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertIn("gh release create v9.9.9", log)

    def test_release_api_unavailability_aborts_before_any_tag_mutation(self):
        proc, log, _ = self._publish("v9.9.9", release="unavailable")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("api-unavailable", proc.stdout + proc.stderr)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("git push origin refs/tags/v9.9.9", log)
        self.assertNotIn("gh release create", log)

    def test_existing_draft_aborts_before_any_tag_mutation(self):
        proc, log, _ = self._publish("v9.9.9", release="draft")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("draft", proc.stdout + proc.stderr)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("git push origin refs/tags/v9.9.9", log)
        self.assertNotIn("gh release create", log)

    # -- Explicit tag-only action behavior --------------------------------------
    def test_create_release_false_tags_and_pushes_but_never_calls_release_create(self):
        proc, log, _ = self._publish("v9.9.9", create_release="false")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: publish_fresh", proc.stdout)
        self.assertIn("git tag -a v9.9.9", log)
        self.assertIn("git push origin refs/tags/v9.9.9", log)
        self.assertNotIn("gh release create", log)

    def test_create_release_false_on_an_already_tagged_commit_is_a_no_op(self):
        # A tag-only caller can revisit an existing tag without creating a
        # Release. `resume_publish` must not retry anything in that mode.
        proc, log, _ = self._publish("v9.9.9", tag_at=self.HEAD,
                                     create_release="false")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: resume_publish", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("gh release create", log)

    def test_create_release_false_still_aborts_on_a_tag_at_the_wrong_commit(self):
        # The #380 tag-integrity guard applies regardless of create-release.
        # A tag-only caller must never silently move an existing tag either.
        proc, log, _ = self._publish("v9.9.9", tag_at=self.OTHER,
                                     create_release="false")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("abort_mismatch", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("gh release create", log)

    def test_create_release_true_is_the_default_and_matches_prior_behavior(self):
        # No `env` override at all — the default the harness sets mirrors
        # action.yml's own default, so this is what every EXISTING manual
        # dispatch caller (with no opinion on the input) already gets.
        proc, log, _ = self._run(_action_step(self.STEP_NAME),
                                 env={"TAG": "v9.9.9", "VER": "9.9.9",
                                      "SUMMARY": "", "TITLE_PREFIX": "codeArbiter",
                                      "MARK_LATEST": "false"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gh release create v9.9.9", log)

    def test_create_release_false_skips_the_release_readback_but_still_verifies_the_tag(self):
        script = _action_step(self.VERIFY_NAME)
        # No Release exists at all ("none") — a create_release=true run would
        # fail here (test_read_back_rejects_a_tag_that_moved... covers that
        # arm); create_release=false must not even look.
        proc, _, _ = self._run(script, env={"TAG": "v9.9.9",
                                            "CREATE_RELEASE": "false"},
                               release="none",
                               ls_remote=f"{self.HEAD}\trefs/tags/v9.9.9\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_create_release_false_verify_still_rejects_a_tag_at_the_wrong_commit(self):
        script = _action_step(self.VERIFY_NAME)
        proc, _, _ = self._run(script, env={"TAG": "v9.9.9",
                                            "CREATE_RELEASE": "false"},
                               release="none",
                               ls_remote=f"{self.OTHER}\trefs/tags/v9.9.9\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not the dispatched commit", proc.stdout + proc.stderr)

    # -- empty requested-version trusts the manifest (auto-tag has no dispatch input)
    def test_empty_requested_version_trusts_the_manifest(self):
        proc, _, out = self._resolve(manifest="plugins/ca/.claude-plugin/plugin.json",
                                     requested="", tag_prefix="v")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("version=9.9.9\n", out)
        self.assertIn("tag=v9.9.9\n", out)

    def test_a_nonempty_requested_version_still_must_equal_the_manifest(self):
        # The empty-string carve-out must not weaken the manual dispatch
        # guard for every caller that DOES supply a version.
        bad, _, out = self._resolve(manifest="plugins/ca/.claude-plugin/plugin.json",
                                    requested="9.9.8", tag_prefix="v")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("bump/align first", bad.stdout + bad.stderr)
        self.assertEqual(out, "")

    def test_already_published_is_a_no_op(self):
        proc, log, _ = self._publish("v9.9.9", tag_at=self.HEAD, release="published")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("publish state: already_published", proc.stdout)
        self.assertNotIn("git tag -a", log)
        self.assertNotIn("gh release create", log)

    def test_a_tag_at_another_commit_aborts_before_publishing(self):
        for job, tag in self.NAMESPACES:
            with self.subTest(lane=job, tag=tag):
                proc, log, _ = self._publish(tag, tag_at=self.OTHER)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("publish state: abort_mismatch", proc.stdout)
                self.assertNotIn("gh release create", log)
                self.assertNotIn("git tag -a", log)

    def test_a_published_release_on_a_tag_at_another_commit_aborts(self):
        # The regression #380 names: a non-draft Release used to short-circuit
        # the comparison, so a wrong-commit tag reported a clean rerun.
        for job, tag in self.NAMESPACES:
            with self.subTest(lane=job, tag=tag):
                proc, log, _ = self._publish(tag, tag_at=self.OTHER,
                                             release="published")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("abort_mismatch", proc.stdout)
                self.assertNotIn("gh release create", log)

    # -- the "Latest" badge is opt-in, and only ca opts in --------------------- #
    def test_a_sibling_release_explicitly_declines_the_latest_badge(self):
        # The bug this exists to prevent, and the test that FAILED to prevent it:
        # asserting `--latest` is ABSENT is not the same as asserting the badge
        # is declined. GitHub defaults `make_latest` to true for any
        # non-prerelease, so omitting the flag hands the badge over. The first
        # real ca-pi release displaced ca v2.8.13 from the position every
        # visitor sees, while this assertion was green.
        off, log_off, _ = self._publish("ca-pi-v9.9.9", mark_latest="false")
        self.assertEqual(off.returncode, 0, off.stderr)
        self.assertIn("gh release create ca-pi-v9.9.9", log_off)
        self.assertIn("--latest=false", log_off,
                      "a sibling must DECLINE the badge explicitly; omitting "
                      "the flag lets GitHub default it to latest")

    def test_the_primary_release_claims_the_badge(self):
        on, log_on, _ = self._publish("v9.9.9", mark_latest="true")
        self.assertEqual(on.returncode, 0, on.stderr)
        self.assertIn("--latest", log_on)
        self.assertNotIn("--latest=false", log_on)

    def test_an_unrecognised_mark_latest_value_still_declines_the_badge(self):
        # Fail-closed on the badge: anything that is not exactly "true" must
        # DECLINE, not fall through to GitHub's default of claiming it.
        for value in ("", "false", "no", "TRUE", "1"):
            with self.subTest(mark_latest=value):
                proc, log, _ = self._publish("ca-sandbox-v9.9.9", mark_latest=value)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("--latest=false", log)
        self.assertIn("gh release create ca-sandbox-v9.9.9 --title ca-sandbox 9.9.9",
                      log.replace("codeArbiter", "ca-sandbox"))

    # -- version/manifest agreement, including ca-pi's companion root --------- #
    def _resolve(self, *, manifest, requested, tag_prefix, companion="",
                 manifest_version="9.9.9", root_version=None):
        return self._run(_action_step(self.VERSION_NAME),
                         env={"CONFIRM": requested, "MANIFEST": manifest,
                              "COMPANION": companion, "TAG_PREFIX": tag_prefix},
                         manifest_version=manifest_version,
                         root_version=root_version)

    def test_a_requested_version_must_equal_the_manifest(self):
        ok, _, out = self._resolve(manifest="plugins/ca/.claude-plugin/plugin.json",
                                   requested="9.9.9", tag_prefix="v")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("version=9.9.9\n", out)
        self.assertIn("tag=v9.9.9\n", out)
        bad, _, out = self._resolve(manifest="plugins/ca/.claude-plugin/plugin.json",
                                    requested="9.9.8", tag_prefix="v")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("bump/align first", bad.stdout + bad.stderr)
        self.assertEqual(out, "")

    def test_the_tag_is_built_from_the_lane_prefix(self):
        for job, params in LANES.items():
            with self.subTest(lane=job):
                proc, _, out = self._resolve(manifest=params["manifest"],
                                             requested="9.9.9",
                                             tag_prefix=params["tag-prefix"])
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(f"tag={params['tag-prefix']}9.9.9\n", out)

    def test_a_companion_manifest_that_disagrees_refuses_to_publish(self):
        # ca-pi: the root package.json is what Pi installs. A root that
        # disagrees with the plugin manifest would install a package claiming a
        # version the tag does not name.
        agree, _, out = self._resolve(manifest="plugins/ca-pi/package.json",
                                      companion="package.json",
                                      requested="9.9.9", tag_prefix="ca-pi-v",
                                      root_version="9.9.9")
        self.assertEqual(agree.returncode, 0, agree.stderr)
        self.assertIn("tag=ca-pi-v9.9.9\n", out)
        drift, _, out = self._resolve(manifest="plugins/ca-pi/package.json",
                                      companion="package.json",
                                      requested="9.9.9", tag_prefix="ca-pi-v",
                                      root_version="9.9.8")
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn("would not match the tag", drift.stdout + drift.stderr)
        self.assertEqual(out, "", "a refused lane must emit no tag")

    def test_lanes_without_a_companion_skip_the_check(self):
        proc, log, _ = self._resolve(manifest="plugins/ca/.claude-plugin/plugin.json",
                                     requested="9.9.9", tag_prefix="v",
                                     root_version="0.0.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("require('./package.json')", log)

    def test_read_back_rejects_a_tag_that_moved_off_the_dispatched_commit(self):
        script = _action_step(self.VERIFY_NAME)
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
        script = _action_step(self.VERIFY_NAME)
        proc, _, _ = self._run(script, env={"TAG": "v9.9.9"}, release="published",
                               tagname="v9.9.8",
                               ls_remote=f"{self.HEAD}\trefs/tags/v9.9.9\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("names tag", proc.stdout + proc.stderr)

    def test_read_back_rejects_a_draft(self):
        script = _action_step(self.VERIFY_NAME)
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
        self.assertEqual(writers, sorted(PUBLISH_JOBS + AUTO_PUBLISH_JOBS),
                         "exactly the declared publishers (manual + auto-tag) "
                         "may declare `contents: write`")

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
                self.assertIn(
                    PREFLIGHT_JOB, _job_needs(jobs[job]),
                    f"{job} must not start without the preflight's authorization")

    def test_publish_jobs_gate_on_the_single_resolved_target(self):
        jobs = _jobs()
        expected = {job: f"'{params['target']}'" for job, params in LANES.items()}
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
        self.assertNotIn("merge-readiness",
                         PUBLISH_ACTION.read_text(encoding="utf-8"),
                         "#385: the shared publish action must not gate itself")


class ExistingTagIntegrityTest(unittest.TestCase):
    """#380: never resume onto a tag that names another commit.

    #382 moved these guards into the shared publish action, so each assertion
    below now holds for all four lanes at once. `LaneIsolationTest` is what
    keeps that true — it proves every publisher actually routes through this
    action, so a lane cannot opt out of the guards by hand-rolling its own
    shell."""

    @staticmethod
    def _action() -> str:
        return PUBLISH_ACTION.read_text(encoding="utf-8")

    def test_the_publisher_peels_the_remote_tag(self):
        action = self._action()
        self.assertIn('"refs/tags/$TAG^{}"', action,
                      "an annotated tag must be peeled to its commit")
        self.assertIn("_releaselib.py peel-tag", action,
                      "peeling must route through the tested helper")

    def test_the_publisher_classifies_before_tagging(self):
        action = self._action()
        self.assertIn("_releaselib.py classify", action,
                      "#380: the shared publish-state classifier must decide")
        self.assertIn('"$GITHUB_SHA"', action)

    def test_the_publisher_distinguishes_release_absence_from_api_failure_before_tagging(self):
        action = self._action()
        lookup = action.index("check_command_route_release_state.py api-lookup")
        mutation = action.index('git tag -a "$TAG"')
        self.assertLess(lookup, mutation)
        self.assertIn(
            'gh api --paginate --slurp "repos/$GITHUB_REPOSITORY/releases?per_page=100"',
            action,
        )
        self.assertNotIn(
            'gh api --include "repos/$GITHUB_REPOSITORY/releases/tags/$TAG"',
            action,
            "the tag endpoint hides drafts behind 404 and is unsafe before tag mutation",
        )

    def test_the_bare_tag_exists_skip_is_gone(self):
        # The exact defect: any remote hit was treated as resumable and tag
        # creation was skipped without comparing the tag to GITHUB_SHA.
        for text in (_release(), self._action()):
            self.assertNotIn('if git ls-remote --exit-code --tags origin "$TAG"', text)
            self.assertNotIn("already on remote — skipping tag creation", text)

    def test_a_mismatch_fails_before_gh_release_create(self):
        case_body = self._action().split("STATE=", 1)[1]
        mismatch = case_body.split("*)", 1)[1].split("esac", 1)[0]
        self.assertNotIn("gh release create", mismatch,
                         "the fail-closed arm must not publish")
        self.assertIn("exit 1", mismatch)

    def test_verification_checks_the_tag_and_its_commit_not_only_isdraft(self):
        verify = self._action().split("Verify the published Release", 1)
        self.assertEqual(len(verify), 2, "the publish action has no read-back step")
        body = verify[1]
        self.assertIn(".tagName", body, "the read-back must compare tagName")
        self.assertIn("FINAL_SHA", body,
                      "the read-back must re-peel the tag to its commit")
        self.assertIn('[ "$FINAL_SHA" = "$GITHUB_SHA" ]', body)
        self.assertIn(".isDraft", body)


class LaneIsolationTest(unittest.TestCase):
    """#382: four independent streams, and no lane outside the shared guards.

    The acceptance criteria ask for version/tag/changelog isolation across all
    four streams. Isolation here means two things, and both are asserted: no two
    lanes share a manifest, a CHANGELOG, or a tag namespace, and every lane
    routes its publish through the one action that carries the #380 guards."""

    def test_every_declared_target_has_exactly_one_publisher(self):
        # The register in _releaselib and the jobs in release.yml must agree. A
        # target the selector can resolve with no job to run it would report a
        # successful dispatch that published nothing at all.
        self.assertEqual([LANES[job]["target"] for job in PUBLISH_JOBS],
                         list(_releaselib.RELEASE_TARGETS),
                         "RELEASE_TARGETS and the publisher lanes have diverged")
        jobs = _jobs()
        for job in PUBLISH_JOBS:
            self.assertIn(job, jobs, f"{job} is declared but not in release.yml")

    def test_the_preflight_accepts_exactly_the_declared_targets(self):
        block = _jobs()[PREFLIGHT_JOB]
        arm = "|".join(_releaselib.RELEASE_TARGETS) + ")"
        self.assertIn(arm, block,
                      "the preflight's accepting arm must list exactly RELEASE_TARGETS")

    def test_every_lane_publishes_through_the_shared_action(self):
        for job in PUBLISH_JOBS:
            with self.subTest(lane=job):
                self.assertIn(f"- uses: {PUBLISH_ACTION_REF}", _jobs()[job],
                              "a lane must not hand-roll its own publish shell")

    def test_no_lane_carries_its_own_publish_shell(self):
        # The duplication #382 removed: a lane with its own `run:` block is a
        # fifth copy of the tag classifier waiting to drift out of step.
        for job in PUBLISH_JOBS:
            with self.subTest(lane=job):
                self.assertNotIn("gh release create", _jobs()[job])
                self.assertNotIn("git tag -a", _jobs()[job])

    def test_each_lane_declares_the_paths_the_issue_specifies(self):
        for job, params in LANES.items():
            with self.subTest(lane=job):
                wired = _lane_inputs(job)
                for key, value in params.items():
                    self.assertEqual(wired.get(key), value,
                                     f"{job} must pass {key}: {value}")

    def test_every_lane_tag_prefix_comes_from_the_shared_register(self):
        # #382: the hosted lane and the /ca:release command must not disagree
        # about a namespace. `_releaselib.release_tag_prefixes()` is the one source
        # of truth; a lane that drifts from it would publish into a series the
        # command cannot resolve a baseline for.
        for job, params in LANES.items():
            with self.subTest(lane=job):
                self.assertEqual(
                    _lane_inputs(job)["tag-prefix"],
                    _releaselib.release_tag_prefixes()[params["target"]],
                    f"{job}'s tag namespace differs from the shared register")

    def test_manifests_changelogs_and_namespaces_do_not_overlap(self):
        for key in ("manifest", "changelog", "tag-prefix", "target"):
            values = [_lane_inputs(job)[key] for job in PUBLISH_JOBS]
            with self.subTest(field=key):
                self.assertEqual(len(set(values)), len(values),
                                 f"two lanes share a {key}: {values}")

    def test_every_declared_manifest_and_changelog_exists(self):
        # A typo in one of these paths is otherwise found by a failed release.
        for job in PUBLISH_JOBS:
            wired = _lane_inputs(job)
            for key in ("manifest", "companion-manifest", "changelog"):
                path = wired.get(key)
                if not path:
                    continue
                with self.subTest(lane=job, field=key):
                    self.assertTrue((REPO_ROOT / path).is_file(),
                                    f"{job}'s {key} '{path}' does not exist")

    def test_only_the_primary_release_claims_the_latest_badge(self):
        claiming = [job for job in PUBLISH_JOBS
                    if _lane_inputs(job)["mark-latest"].strip('"') == "true"]
        self.assertEqual(claiming, ["release"],
                         "only ca may take the repository's \"Latest\" badge")

    def test_the_action_declines_the_badge_rather_than_omitting_the_flag(self):
        # Structural backstop for the execution test above: omitting `--latest`
        # is NOT declining it, because GitHub defaults a non-prerelease to
        # latest. The shipped action must spell the refusal out.
        action = PUBLISH_ACTION.read_text(encoding="utf-8")
        self.assertIn("--latest=false", action,
                      "a sibling lane must pass --latest=false explicitly")

    def test_each_lane_reads_its_own_dispatch_input(self):
        # Wiring a lane to another lane's input would publish the wrong plugin
        # at a version the operator typed for something else.
        seen = set()
        for job in PUBLISH_JOBS:
            wired = _lane_inputs(job)
            with self.subTest(lane=job):
                requested = wired["requested-version"]
                self.assertRegex(requested,
                                 r"^\$\{\{ github\.event\.inputs\.\w+ \}\}$")
                self.assertNotIn(requested, seen,
                                 f"{job} reuses another lane's version input")
                seen.add(requested)

    def test_the_dispatch_declares_a_version_input_per_lane(self):
        header = _release().split("jobs:", 1)[0]
        declared = set(re.findall(r"(?m)^      (\w+):$", header))
        for job in PUBLISH_JOBS:
            wired = _lane_inputs(job)
            for key in ("requested-version", "summary"):
                name = re.search(r"inputs\.(\w+)", wired[key]).group(1)
                with self.subTest(lane=job, field=key):
                    self.assertIn(name, declared,
                                  f"{job} reads undeclared dispatch input {name!r}")

    def test_the_publish_action_never_resolves_its_own_authorization(self):
        # Staleness and merge readiness are the preflight's job (#385). An
        # action that re-decided either would be a second policy to keep in
        # agreement with ci.yml, and the publish path is the copy nobody
        # notices is wrong.
        action = PUBLISH_ACTION.read_text(encoding="utf-8")
        self.assertNotIn("merge-readiness", action)
        self.assertNotIn("select-target", action)


class AutoTagLaneTest(unittest.TestCase):
    """Every eligible manifest advance publishes its tag and GitHub Release
    through a `workflow_run`-triggered mirror of the manual dispatch lanes."""

    def test_the_trigger_is_workflow_run_on_ci_completion_not_a_bare_push(self):
        # A bare `push` trigger here would race ci.yml's OWN concurrent
        # re-run for the same commit (#385's reasoning, restated for the
        # push-triggered case): querying check-runs for GITHUB_SHA from a job
        # that started at the same instant as the run computing them could
        # read "pending" or "missing" for its own commit.
        text = _release()
        self.assertIn('workflows: ["ci"]', text)
        self.assertIn("types: [completed]", text)
        header = text.split("jobs:", 1)[0]
        self.assertNotRegex(header, r"(?m)^  push:\n    branches: \[main\]$",
                            "a bare push trigger races ci.yml's own re-run")

    def test_auto_preflight_holds_no_write_permission(self):
        block = _jobs()[AUTO_PREFLIGHT_JOB]
        self.assertRegex(block, r"(?m)^      contents: read$",
                         "the auto-tag preflight must pin `contents: read`")
        self.assertNotIn("contents: write", block)

    def test_auto_preflight_gates_on_a_successful_ci_run_on_main(self):
        condition = _job_if(_jobs()[AUTO_PREFLIGHT_JOB])
        self.assertIn("github.event.workflow_run.conclusion == 'success'", condition)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", condition)
        self.assertIn("github.event_name == 'workflow_run'", condition)

    def test_every_auto_lane_depends_on_the_auto_preflight(self):
        jobs = _jobs()
        for job in AUTO_PUBLISH_JOBS:
            with self.subTest(job=job):
                self.assertIn(
                    AUTO_PREFLIGHT_JOB, _job_needs(jobs[job]),
                    f"{job} must not start without the auto-preflight's eligibility check")

    def test_every_auto_lane_gates_on_its_own_resolved_eligibility(self):
        jobs = _jobs()
        for job, params in AUTO_LANES.items():
            with self.subTest(job=job):
                condition = _job_if(jobs[job])
                target = params["target"]
                self.assertIn(f"needs.auto-preflight.outputs.{target} == 'true'",
                              condition,
                              f"{job} must run only when {target} is eligible")

    def test_every_auto_lane_creates_a_release_after_eligibility_preflight(self):
        jobs = _jobs()
        for job in AUTO_PUBLISH_JOBS:
            with self.subTest(job=job):
                inputs = _lane_inputs(job)
                self.assertEqual(inputs.get("create-release"), '"true"',
                                 f"{job} must create a GitHub Release after auto-tagging")

    def test_every_auto_lane_trusts_the_manifest_rather_than_a_dispatch_input(self):
        jobs = _jobs()
        for job in AUTO_PUBLISH_JOBS:
            with self.subTest(job=job):
                inputs = _lane_inputs(job)
                self.assertEqual(inputs.get("requested-version"), '""',
                                 f"{job} has no dispatch input to compare "
                                 "against — it must trust the manifest")

    def test_every_auto_lane_matches_its_manual_siblings_manifest_and_namespace(self):
        # The auto lanes are a MIRROR of the manual ones — same manifest,
        # changelog, tag-prefix, mark-latest per target — never a second,
        # independently-drifting declaration of the same facts.
        jobs = _jobs()
        manual_by_target = {p["target"]: (job, p) for job, p in LANES.items()}
        for auto_job, auto_params in AUTO_LANES.items():
            with self.subTest(job=auto_job):
                target = auto_params["target"]
                manual_job, manual_params = manual_by_target[target]
                auto_inputs = _lane_inputs(auto_job)
                manual_inputs = _lane_inputs(manual_job)
                for key in ("manifest", "changelog", "tag-prefix",
                           "title-prefix", "mark-latest"):
                    self.assertEqual(
                        auto_inputs.get(key), manual_inputs.get(key),
                        f"{auto_job}'s {key!r} must match {manual_job}'s")

    def test_only_the_primary_auto_lane_claims_the_latest_badge(self):
        jobs = _jobs()
        for job, params in AUTO_LANES.items():
            with self.subTest(job=job):
                inputs = _lane_inputs(job)
                expected = '"true"' if params["target"] == "ca" else '"false"'
                self.assertEqual(inputs.get("mark-latest"), expected)

    def test_every_auto_lane_checks_out_the_upstream_run_commit_explicitly(self):
        # workflow_run does not reliably default GITHUB_SHA / the checkout ref
        # to the completed run's own commit — every auto lane must pin it
        # explicitly rather than trust an ambient default.
        jobs = _jobs()
        for job in AUTO_PUBLISH_JOBS:
            with self.subTest(job=job):
                self.assertIn("github.event.workflow_run.head_sha", jobs[job])

    def test_auto_eligible_first_introduction_and_advance_are_true(self):
        # The CLI subcommand the preflight's own shell calls, executed
        # directly: a series with no tag yet, or a manifest strictly ahead
        # of its last tag, is eligible; equal or behind is not.
        proc = subprocess.run(
            [sys.executable, str(HERE / "_releaselib.py"),
             "auto-eligible", "2.12.1", "v"],
            input="v2.12.0\nv2.11.0\n", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "true")

        proc = subprocess.run(
            [sys.executable, str(HERE / "_releaselib.py"),
             "auto-eligible", "2.12.0", "v"],
            input="v2.12.0\nv2.11.0\n", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "false",
                         "a manifest equal to the last tag has nothing new to publish")

        proc = subprocess.run(
            [sys.executable, str(HERE / "_releaselib.py"),
             "auto-eligible", "1.0.0", "zzz-v"],
            input="", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "true",
                         "a series with no tag yet is a first introduction")

    def test_final_command_route_audit_waits_for_every_ra11_publisher(self):
        block = _jobs()[AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB]
        self.assertEqual(
            set(_job_needs(block)),
            {AUTO_PREFLIGHT_JOB, "auto-release", "auto-release-codex", "auto-release-pi"},
        )
        condition = _job_if(block)
        self.assertIn("always()", condition)
        self.assertIn("github.event_name == 'workflow_run'", condition)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", condition)
        self.assertIn("needs.auto-preflight.result == 'success'", condition)

    def test_final_command_route_audit_is_read_only_and_pins_the_candidate(self):
        block = _jobs()[AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB]
        self.assertIn("contents: read", block)
        self.assertNotIn("contents: write", block)
        self.assertIn("github.event.workflow_run.head_sha", block)
        self.assertIn("fetch-tags: true", block)

    def test_final_command_route_audit_collects_api_evidence_then_runs_hermetic_checker(self):
        block = _jobs()[AUTO_COMMAND_ROUTE_RELEASE_AUDIT_JOB]
        self.assertIn("gh api --include", block)
        self.assertIn("check_command_route_release_state.py observe", block)
        self.assertIn("--evidence-dir", block)


class CodexCandidateProvenanceTest(unittest.TestCase):
    """A ca-codex tag is authorized only for trusted static candidate bytes."""

    def test_manual_and_auto_codex_publishers_need_hosted_static_provenance(self):
        jobs = _jobs()
        expected = {
            "release-codex": MANUAL_CODEX_PROVENANCE_JOB,
            "auto-release-codex": AUTO_CODEX_PROVENANCE_JOB,
        }
        for publisher, provenance in expected.items():
            with self.subTest(publisher=publisher):
                self.assertIn(provenance, jobs)
                self.assertIn(provenance, _job_needs(jobs[publisher]))
                block = jobs[provenance]
                self.assertIn("contents: read", block)
                self.assertNotIn("contents: write", block)
                self.assertNotIn("actions: read", block)
                self.assertNotIn("gh run download", block)
                self.assertNotIn("codex-desktop-candidate", block)
                self.assertNotIn("candidate-resolution.json", block)
                self.assertNotIn("--receipt", block)
                self.assertNotIn("--candidate-archive", block)
                self.assertIn("verify_codex_candidate_provenance.py", block)
                self.assertIn("--final-ref", block)

    def test_manual_and_auto_provenance_pin_the_exact_final_main_commit(self):
        jobs = _jobs()
        manual = jobs[MANUAL_CODEX_PROVENANCE_JOB]
        automatic = jobs[AUTO_CODEX_PROVENANCE_JOB]
        self.assertIn("ref: ${{ github.sha }}", manual)
        self.assertIn("--final-ref ${{ github.sha }}", manual)
        self.assertIn(
            "CANDIDATE_SHA: ${{ github.event.workflow_run.head_sha }}", automatic
        )
        self.assertIn('--final-ref "$CANDIDATE_SHA"', automatic)

    def test_auto_provenance_executes_only_trusted_default_branch_code(self):
        automatic = _jobs()[AUTO_CODEX_PROVENANCE_JOB]
        trusted_checkout = _named_step(
            automatic, "Check out the trusted default-branch verifier"
        )
        candidate_materialization = _named_step(
            automatic, "Materialize the exact completed-run candidate as inert data"
        )
        verifier = _named_step(automatic, "Verify the exact static Codex candidate")

        self.assertIn("ref: ${{ github.sha }}", trusted_checkout)
        self.assertIn("path: trusted", trusted_checkout)
        self.assertNotIn("github.event.workflow_run.head_sha", trusted_checkout)
        self.assertEqual(
            automatic.count("uses: actions/checkout@"), 1,
            "the privileged provenance job may use actions/checkout only for "
            "trusted default-branch code",
        )
        self.assertNotIn(
            "ref: ${{ github.event.workflow_run.head_sha }}", automatic,
            "event-selected content must never enter this privileged job via "
            "actions/checkout",
        )
        self.assertIn(
            "CANDIDATE_SHA: ${{ github.event.workflow_run.head_sha }}",
            candidate_materialization,
        )
        required_materialization_controls = (
            'case "$CANDIDATE_SHA" in',
            '""|*[!0-9a-f]*)',
            '[ "${#CANDIDATE_SHA}" -ne 40 ]',
            'git -C trusted cat-file -e "$CANDIDATE_SHA^{commit}"',
            'git -C trusted merge-base --is-ancestor "$CANDIDATE_SHA" '
            '"${{ github.sha }}"',
            'git -C trusted worktree add --detach ../candidate "$CANDIDATE_SHA"',
        )
        for control in required_materialization_controls:
            with self.subTest(control=control):
                self.assertIn(control, candidate_materialization)
        self.assertNotIn("|| true", candidate_materialization)
        self.assertIn(
            "python3 trusted/.github/scripts/verify_codex_candidate_provenance.py",
            verifier,
        )
        self.assertIn("--repo candidate", verifier)
        self.assertIn('--final-ref "$CANDIDATE_SHA"', verifier)
        self.assertNotIn("--receipt", verifier)
        self.assertNotIn("gh run download", verifier)
        self.assertNotIn(
            "python3 candidate/.github/scripts/verify_codex_candidate_provenance.py",
            automatic,
        )
        self.assertNotIn(
            "python3 .github/scripts/verify_codex_candidate_provenance.py",
            automatic,
        )


class TriggerIsolationTest(unittest.TestCase):
    """#654: two triggers share this file — a job written for one must never
    wake up on the other.

    `workflow_dispatch` supplies the four confirmation inputs the manual
    preflight resolves its single target from. `workflow_run` supplies none
    of them. The dispatch preflight shipped with no `if:` at all, so every
    merge to main also woke it on the auto-tag path, where it read four
    empty inputs, resolved `none`, and exited 1 — twelve consecutive
    `release` runs concluded `failure` while the auto-tag lanes beside them
    tagged correctly.

    Nothing was mis-published: the preflight failed CLOSED, and the manual
    publishers skipped with it. What it cost is the signal. At the run list
    a permanently-red `release` is indistinguishable from a genuine
    auto-tag failure — a tag never created, so npm-publish never fires —
    which is the one alarm this workflow exists to raise.
    """

    def test_the_dispatch_preflight_runs_only_on_a_dispatch(self):
        self.assertEqual(
            _gated_triggers(PREFLIGHT_JOB, _jobs()), {"workflow_dispatch"},
            "#654: the preflight reads dispatch inputs that exist on no other "
            "trigger — it must be gated to the trigger that supplies them")

    def test_every_job_is_bound_to_exactly_one_trigger(self):
        jobs = _jobs()
        for job in jobs:
            with self.subTest(job=job):
                self.assertEqual(
                    len(_gated_triggers(job, jobs)), 1,
                    f"{job} can start on more than one of this file's "
                    "triggers; each lane must belong to exactly one")

    def test_every_job_is_bound_to_the_trigger_its_own_lane_declares(self):
        # Exactly-one is not enough on its own: a guard inverted to
        # `!= 'workflow_run'` binds the preflight to one trigger — the wrong
        # one. Pin which lane each job belongs to.
        jobs = _jobs()
        self.assertEqual(sorted(jobs), sorted(JOB_TRIGGER),
                         "release.yml declares a job no lane accounts for")
        for job, trigger in JOB_TRIGGER.items():
            with self.subTest(job=job):
                self.assertEqual(_gated_triggers(job, jobs), {trigger},
                                 f"{job} belongs to the {trigger} lane")

    def test_the_walk_reports_an_ungated_job_as_reachable_from_both(self):
        # The assertions above earn their keep only if the walk actually
        # discriminates. Proven against synthetic text, not by mutating the
        # shipped workflow. This first case is #654 itself: no `if:` at all.
        jobs = {"preflight": "    name: x\n",
                "release": "    needs: preflight\n"
                           "    if: needs.preflight.outputs.target == 'ca'\n"}
        self.assertEqual(_gated_triggers("preflight", jobs), set(TRIGGERS))
        self.assertEqual(_gated_triggers("release", jobs), set(TRIGGERS),
                         "a publisher inherits its preflight's reach")

    def test_the_walk_rejects_an_or_widened_event_guard(self):
        jobs = {"preflight": "    if: github.event_name == 'workflow_dispatch'"
                             " || github.event_name == 'workflow_run'\n"}
        with self.assertRaisesRegex(AssertionError, "unsupported boolean"):
            _gated_triggers("preflight", jobs)

    def test_the_walk_inherits_a_parents_trigger_through_needs(self):
        jobs = {"preflight": "    if: github.event_name == 'workflow_dispatch'\n",
                "release": "    needs: preflight\n"}
        self.assertEqual(_gated_triggers("release", jobs), {"workflow_dispatch"})

    def test_the_walk_intersects_its_guard_with_every_parents_lane(self):
        jobs = {
            "auto-preflight": "    if: github.event_name == 'workflow_run'\n",
            "release": "    needs: auto-preflight\n"
                       "    if: github.event_name == 'workflow_dispatch'\n",
        }
        self.assertEqual(_gated_triggers("release", jobs), set())

    def test_the_walk_intersects_multiple_parents_rather_than_unions_them(self):
        jobs = {
            "dispatch-preflight": "    if: github.event_name == 'workflow_dispatch'\n",
            "auto-preflight": "    if: github.event_name == 'workflow_run'\n",
            "release": "    needs: [dispatch-preflight, auto-preflight]\n",
        }
        self.assertEqual(_gated_triggers("release", jobs), set())

    def test_the_walk_rejects_a_status_function_that_bypasses_needs(self):
        for condition in (
            "always() || github.event_name == 'workflow_dispatch'",
            "always () && github.event_name == 'workflow_dispatch'",
            "Always() && github.event_name == 'workflow_dispatch'",
        ):
            with self.subTest(condition=condition):
                jobs = {
                    "release": "    needs: preflight\n" f"    if: {condition}\n",
                    "preflight": "    if: github.event_name == 'workflow_dispatch'\n",
                }
                with self.assertRaisesRegex(AssertionError, "status function"):
                    _gated_triggers("release", jobs)

    def test_the_walk_raises_rather_than_reading_an_unresolvable_needs(self):
        # never-fold-unreadable-into-absent: a `needs:` this suite cannot
        # parse, or one naming a job that does not exist, must stop the test
        # rather than resolve to "depends on nothing".
        for block, why in (("    needs: {a: b}\n", "unparseable form"),
                           ("    needs: ghost\n", "undeclared dependency")):
            with self.subTest(case=why):
                with self.assertRaises(AssertionError):
                    _gated_triggers("a", {"a": block})
        with self.assertRaises(AssertionError):
            _gated_triggers("a", {"a": "    needs: b\n", "b": "    needs: a\n"})


class RegistrationTest(unittest.TestCase):
    """A release.yml-only edit must start the CI job that runs this file."""

    def test_release_workflow_is_in_the_hooks_filter(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/release.yml", paths_filter(ci, "hooks"),
                      "the hooks filter must flag a release.yml-only change")

    def test_the_publish_action_is_in_the_hooks_filter(self):
        # #382: the publish mechanics moved OUT of release.yml. Without this the
        # only file that can weaken the #380 guards would be the one file no
        # filter watched.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/actions/**", paths_filter(ci, "hooks"),
                      "the hooks filter must flag a publish-action-only change")

    def test_release_workflow_starts_a_push_run(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/release.yml", push_trigger_paths(ci),
                      "a push touching only release.yml must still start CI")

    def test_the_publish_action_starts_a_push_run(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".github/actions/**", push_trigger_paths(ci),
                      "a push touching only the publish action must still start CI")

    def test_ci_invokes_this_suite(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python .github/scripts/test_release_workflow.py", ci,
                      "this contract suite must run in CI")


class NameKeyedTargetSelectionTest(unittest.TestCase):
    """A-4.2/T-44b: the workflow passes NAME-KEYED confirmations.

    The previous form passed four bare values whose meaning came from
    their POSITION, aligned by index against the declared row order.
    Nothing enforced that the two orders agreed. A row inserted at the
    front of `.codearbiter/release-targets.md` shifted every confirmation
    by one, so a dispatch meaning to publish the second target published
    the first -- while holding `contents: write`, and with every
    downstream check passing, because the wrong release is internally
    consistent.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    def test_name_keyed_selection_is_what_the_workflow_calls(self):
        self.assertIn("select-target-named", self.text)

    def test_name_keyed_replaced_the_positional_call(self):
        # The positional subcommand still EXISTS in the shim (its own
        # tests cover it, and T-46 owns its retirement), but the workflow
        # must no longer reach for it -- two call paths would let the
        # order hazard back in through the one that matters.
        positional = re.search(
            r"_releaselib\.py select-target(?!-named)", self.text)
        self.assertIsNone(
            positional,
            "release.yml still calls the positional select-target; the "
            "order hazard is only closed if the workflow uses the "
            "name-keyed form")

    def test_name_keyed_every_declared_target_is_passed_with_its_name(self):
        # Derived from the DECLARED file, not a hand-list: a target added
        # to the declaration but not plumbed here would otherwise be
        # unreleasable, and a name typo would resolve to `unknown` only at
        # dispatch time.
        rows = _releaselib.load_targets(
            str(REPO_ROOT / ".codearbiter" / "release-targets.md"))
        for row in rows:
            name = row["target"]
            with self.subTest(target=name):
                self.assertRegex(
                    self.text, rf'"{re.escape(name)}=\$[A-Z_]+"',
                    f"release.yml does not pass a name-keyed input for the "
                    f"declared target {name!r}")

    @staticmethod
    def _workflow_keyed_names(text):
        """The target names release.yml actually passes, read out of the
        `select-target-named` invocation itself rather than a hand-list —
        so this test cannot drift from the command it describes."""
        call = re.search(
            r"select-target-named(.*?)\)\n", text, re.S)
        if call is None:
            return set()
        return set(re.findall(r'"([A-Za-z0-9._-]+)=\$', call.group(1)))

    def test_name_agreement_declared_set_equals_workflow_inputs(self):
        """A-4.3. The declared target set and the workflow's inputs must
        agree BY NAME, in both directions.

        One direction is the obvious one: a target declared in
        `.codearbiter/release-targets.md` with no workflow input is
        unreleasable, and nobody finds out until someone tries to release
        it.

        The other direction is the quiet one: a workflow input naming a
        target the declaration no longer carries. That input stays on the
        dispatch form, an operator fills it in, and the resolver answers
        `unknown` at dispatch time — a fail-closed refusal, but only after
        somebody believed they were cutting a release. Worse, if the name
        were later re-declared for a DIFFERENT component, the stale input
        would silently start selecting it.

        Set equality, not containment, so neither direction can rot.
        """
        declared = {row["target"] for row in _releaselib.load_targets(
            str(REPO_ROOT / ".codearbiter" / "release-targets.md"))}
        wired = self._workflow_keyed_names(self.text)
        self.assertTrue(wired, "no name-keyed inputs found in release.yml")
        self.assertEqual(
            wired, declared,
            "release.yml's name-keyed inputs and the declared target set "
            f"disagree. Declared-but-unwired: {sorted(declared - wired)}. "
            f"Wired-but-undeclared: {sorted(wired - declared)}. Reconcile "
            "both files; adding a name to one alone is what this asserts "
            "against.")

    def test_name_agreement_detects_a_declared_target_with_no_input(self):
        # The assertion's own discriminating power, against synthetic text
        # rather than by mutating the real workflow.
        text = ('TARGET=$(python3 x select-target-named \\\n'
                '  "ca=$CONFIRM" "ca-codex=$CODEX_CONFIRM")\n')
        self.assertEqual(self._workflow_keyed_names(text), {"ca", "ca-codex"})

    def test_name_agreement_extraction_reads_the_real_invocation(self):
        # If the extraction silently returned an empty set, the equality
        # test above would fail loudly rather than pass vacuously -- but
        # pin the non-empty read anyway, since a vacuous PASS is the
        # failure mode this repo has already hit twice.
        self.assertGreaterEqual(len(self._workflow_keyed_names(self.text)), 4)

    def test_name_keyed_unknown_label_has_its_own_diagnosis(self):
        # `unknown` means the workflow's inputs and the declared file
        # disagree, which is a different problem from "no input" -- the
        # catch-all arm would fail closed but say nothing useful.
        self.assertIn("unknown)", self.text)
        self.assertIn("does not declare", self.text)

    def test_name_keyed_labels_are_all_handled_by_the_case(self):
        # Every label the selector can return must have an arm, or a
        # fail-closed catch-all. Asserted against the mechanism's own
        # vocabulary rather than a copy of it.
        for label in ("multiple", "none", "unknown"):
            with self.subTest(label=label):
                self.assertIn(f"{label})", self.text)
        self.assertIn("*)", self.text)


if __name__ == "__main__":
    unittest.main()
