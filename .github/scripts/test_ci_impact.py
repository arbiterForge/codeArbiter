#!/usr/bin/env python3
"""Unit tests for the fail-safe CI impact planner.

Run: python .github/scripts/test_ci_impact.py

The planner is intentionally stdlib-only.  These tests keep its classification
contract deterministic and, most importantly, prove that an unrecognised file
selects the broad validation lane instead of silently predicting a skip.
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "ci-impact.py"
_DESCRIPTORS_TOOL = REPO_ROOT / "tools" / "host_descriptors.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PI_PROMOTION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pi-promotion.yml"
PI_TEST_DIR = REPO_ROOT / "plugins" / "ca-pi" / "tools" / "test"

# `needs.<id>.result` and `needs['<id>'].result` are the two spellings GitHub
# accepts; the aggregate gate uses both depending on whether the job id has a
# hyphen in it.
_NEEDS_RESULT = re.compile(r"needs(?:\.([A-Za-z0-9_-]+)|\['([^']+)'\])\.result")
_JOB_TIMEOUT = re.compile(r"(?m)^    timeout-minutes: (\d+)$")
# GitHub-hosted runners hard-stop a job at 6 hours; a repository-defined bound
# is only meaningful well under that.
HOSTED_JOB_MAXIMUM_MINUTES = 360


def workflow_jobs(text: str) -> dict[str, str]:
    """Split a workflow's top-level `jobs:` mapping into {job id: raw block}.

    Deliberately textual, like the rest of this repo's workflow contracts - the
    scripts stay stdlib-only, so there is no YAML parser to lean on.
    """
    lines = text.splitlines(keepends=True)
    try:
        start = next(index for index, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:
        return {}
    jobs: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in lines[start + 1:]:
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if header is not None:
            if current is not None:
                jobs[current] = "".join(body)
            current, body = header.group(1), [line]
        elif current is not None:
            body.append(line)
    if current is not None:
        jobs[current] = "".join(body)
    return jobs


def aggregate_needs(ci: str) -> list[str]:
    """Job ids listed in ci-passed's `needs:` block."""
    aggregate = workflow_jobs(ci).get("ci-passed", "")
    match = re.search(r"(?ms)^    needs:\s*\n(?P<body>(?:      - [A-Za-z0-9_-]+\n)+)", aggregate)
    if match is None:
        return []
    return [line.strip()[2:].strip() for line in match.group("body").splitlines()]


def aggregate_required_results(ci: str) -> list[str]:
    """Job ids whose result the ci-passed gate actually enforces."""
    aggregate = workflow_jobs(ci).get("ci-passed", "")
    match = re.search(r'(?m)^\s+required_results="(?P<body>[^"\n]*)"\s*$', aggregate)
    if match is None:
        return []
    return [first or second for first, second in _NEEDS_RESULT.findall(match.group("body"))]


def unassigned_pi_test_files(ci: str, committed: set[str]) -> set[str]:
    """Committed ca-pi Vitest files no *required* merge-gate job executes.

    A bare `npm test` in a required Pi job covers the whole suite; a filtered
    `npm test -- test/a.test.ts ...` covers only the files it names.  Anything
    left over is a file that can regress with every required check green
    (issue #405).
    """
    jobs = workflow_jobs(ci)
    covered: set[str] = set()
    for job_id in aggregate_required_results(ci):
        if not job_id.startswith("ca-pi"):
            continue
        for match in re.finditer(r"(?m)^\s+run: npm test(?P<rest>[^\n]*)$", jobs.get(job_id, "")):
            rest = match.group("rest").strip()
            if not rest:
                covered |= set(committed)
                continue
            covered |= {
                token.rsplit("/", 1)[-1] for token in rest.split() if token.endswith(".test.ts")
            }
    return set(committed) - covered

_spec = importlib.util.spec_from_file_location("ci_impact", _TOOL)
module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = module
_spec.loader.exec_module(module)


def hosts():
    spec = importlib.util.spec_from_file_location("host_descriptors_ci_impact", _DESCRIPTORS_TOOL)
    descriptors = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = descriptors
    spec.loader.exec_module(descriptors)
    return descriptors.load_host_descriptors(str(REPO_ROOT))


def map_document():
    return {
        "schema": 1,
        "checks": [
            {
                "id": "broad-lane",
                "lane": "CHECK",
                "scope": "REPO",
                "contract": "Broad validation",
            },
            {
                "id": "pi-adapter",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Adapter contract",
            },
            {
                "id": "pi-latest",
                "lane": "WATCH",
                "scope": "PI",
                "contract": "Upstream compatibility",
            },
            {
                "id": "ca-surface",
                "lane": "CHECK",
                "scope": "CA",
                "contract": "Generated surface",
            },
            {
                "id": "codex-surface",
                "lane": "CHECK",
                "scope": "CDX",
                "contract": "Generated surface",
            },
            {
                "id": "pi-surface",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Generated surface",
            },
        ],
        "edges": [
            {"glob": "plugins/ca-pi/**", "checks": ["pi-adapter", "pi-latest"]},
            {"glob": "core/pysrc/**", "checks": ["broad-lane"]},
            {
                "kind": "descriptor_surface",
                "source_prefix": "core/surface/",
                "checks": {
                    "claude": "ca-surface",
                    "codex": "codex-surface",
                    "pi": "pi-surface",
                },
            },
        ],
    }


def valid_map():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "impact-map.json"
        path.write_text(json.dumps(map_document()), encoding="utf-8")
        return module.load_map(path)


class CheckNameTest(unittest.TestCase):
    def test_render_check_name_uses_the_fixed_tag_grammar(self):
        check = module.Check(
            id="pi-adapter",
            lane="CHECK",
            scope="PI",
            contract="Adapter contract",
            dimensions=("os: Windows", "runtime: Pi 0.80.5"),
        )
        self.assertEqual(
            module.render_check_name(check),
            "[CHECK] | [PI  ] | Adapter contract  <os: Windows · runtime: Pi 0.80.5>",
        )


class EvaluationTest(unittest.TestCase):
    def test_unknown_path_expands_to_the_broad_lane(self):
        result = module.evaluate(
            valid_map(), ["unclassified/new-file.txt"], hosts=()
        )
        self.assertTrue(result.fallback)
        self.assertEqual(result.reason, "unmapped path: unclassified/new-file.txt")
        self.assertEqual([check.id for check in result.selected], ["broad-lane"])

    def test_pi_plugin_change_selects_adapter_and_advisory_contracts(self):
        result = module.evaluate(
            valid_map(), ["plugins/ca-pi/tools/src/index.ts"], hosts=()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )

    def test_multiple_paths_have_a_deterministic_deduplicated_selection(self):
        result = module.evaluate(
            valid_map(),
            ["plugins/ca-pi/tools/src/index.ts", "plugins/ca-pi/extensions/a.ts"],
            hosts=(),
        )
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )


class MapValidationTest(unittest.TestCase):
    def load(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "impact-map.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return module.load_map(path)

    def test_rejects_duplicate_check_ids(self):
        document = map_document()
        document["checks"].append(document["checks"][0].copy())
        with self.assertRaisesRegex(module.ImpactMapError, "duplicate check id"):
            self.load(document)

    def test_rejects_unknown_edge_target(self):
        document = map_document()
        document["edges"][0]["checks"] = ["missing"]
        with self.assertRaisesRegex(module.ImpactMapError, "unknown check"):
            self.load(document)

    def test_rejects_missing_broad_lane(self):
        document = map_document()
        document["checks"] = document["checks"][1:]
        with self.assertRaisesRegex(module.ImpactMapError, "broad-lane"):
            self.load(document)


class DescriptorSurfaceTest(unittest.TestCase):
    def test_codex_host_note_selects_only_codex_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/includes/codex-host-notes.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual([check.id for check in result.selected], ["codex-surface"])

    def test_shared_surface_template_selects_every_host_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/ORCHESTRATOR.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            {check.scope for check in result.selected}, {"CA", "CDX", "PI"}
        )


class WorkflowContractTest(unittest.TestCase):
    def test_ci_runs_impact_planner_without_replacing_existing_job_conditions(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            ci,
        )
        self.assertIn("cancel-in-progress: true", ci)
        self.assertIn("id: impact", ci)
        self.assertIn("python tools/ci-impact.py", ci)
        self.assertIn("list-files: shell", ci)
        self.assertIn("impact: ${{ steps.filter.outputs.impact }}", ci)
        self.assertIn("needs.changes.outputs.impact == 'true'", ci)
        self.assertIn("needs.changes.outputs.ca-pi == 'true'", ci)

    def test_ci_uses_the_typed_check_name_schema_for_every_owned_job(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        expected = (
            "[CHECK] | [REPO] | Impact selection",
            "[CHECK] | [REPO] | Impact planner contract",
            "[CHECK] | [CORE] | Host descriptor contract",
            "[CHECK] | [CA  ] | Farm dispatcher contract",
            "[CHECK] | [SBX ] | Sandbox driver contract",
            "[CHECK] | [PI  ] | Host-independent adapter contract",
            "[CHECK] | [PI  ] | Adapter contract  <os: ${{ matrix.os }} · runtime: Pi ${{ matrix.pi-version }}>",
            "[WATCH] | [PI  ] | Upstream compatibility  <runtime: npm latest>",
            "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>",
            "[CHECK] | [CORE] | Hook contract  <os: ${{ matrix.os }}>",
            "[GATE ] | [CA  ] | Payload version",
            "[GATE ] | [SBX ] | Payload version",
            "[GATE ] | [CDX ] | Payload version",
            "[GATE ] | [PI  ] | Payload version",
            "[CHECK] | [CA  ] | Reference graph",
            "[CHECK] | [CA  ] | Documentation consistency",
            "[CHECK] | [SBX ] | Reference graph",
            "[CHECK] | [REPO] | Manifest contract",
            "[CHECK] | [REPO] | License consistency",
            "[CHECK] | [CORE] | Generated surface",
            "[CHECK] | [CDX ] | Reference graph",
            "[GATE ] | [REPO] | Merge readiness",
        )
        for name in expected:
            self.assertIn(f'name: "{name}"', ci)

    def test_every_committed_pi_test_file_runs_in_a_required_merge_gate_job(self):
        # Issue #405: the six-cell matrix named 6 of the 23 committed Vitest
        # files, so a PR could regress policy/plan-mode/dispatch/background-jobs/
        # windows-supervisor with every required check green.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        self.assertTrue(committed, "no ca-pi Vitest files found - the glob is wrong")
        self.assertEqual(
            sorted(unassigned_pi_test_files(ci, committed)),
            [],
            "committed ca-pi test files that no required merge-gate job executes",
        )

    def test_the_pi_suite_partition_contract_fails_when_the_full_suite_run_is_removed(self):
        # AC-2 of #405: the contract above must BITE, not merely pass because
        # one job happens to run everything.  Neutering the unfiltered run has
        # to leave test files unassigned.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        jobs = workflow_jobs(ci)
        mutated, neutered_jobs = ci, []
        for job_id in aggregate_required_results(ci):
            if not job_id.startswith("ca-pi"):
                continue
            block = jobs[job_id]
            neutered = re.sub(r"(?m)^(\s+)run: npm test$", r"\1run: echo npm test", block)
            if neutered != block:
                mutated = mutated.replace(block, neutered, 1)
                neutered_jobs.append(job_id)
        self.assertNotEqual(
            neutered_jobs, [], "no required ca-pi job runs the unfiltered `npm test` suite"
        )
        self.assertTrue(
            unassigned_pi_test_files(mutated, committed),
            "removing the full-suite run left every Pi test file still assigned",
        )

    def test_host_independent_pi_job_is_registered_in_both_needs_and_required_results(self):
        # Issue #390 CRITICAL: `ci-passed` enforces jobs through TWO
        # independent registrations - the `needs:` list (which makes it wait)
        # and the `required_results` string (which makes it care).  Adding a
        # job to one and not the other silently drops the verdict and nothing
        # else in CI notices.  This asserts both exist AND that they agree for
        # every job, with exactly one sanctioned exception: the advisory
        # ca-pi-latest canary is intentionally awaited but not enforced.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ca-pi-checks", sorted(workflow_jobs(ci)))
        needs = aggregate_needs(ci)
        required = aggregate_required_results(ci)
        self.assertIn("ca-pi-checks", needs, "ci-passed.needs is missing ca-pi-checks")
        self.assertIn(
            "ca-pi-checks", required, "ci-passed.required_results is missing ca-pi-checks"
        )
        self.assertEqual(
            sorted(set(needs) - set(required)),
            ["ca-pi-latest"],
            "awaited but unenforced jobs (only the advisory Pi canary may appear here)",
        )
        self.assertEqual(
            sorted(set(required) - set(needs)),
            [],
            "enforced jobs the aggregate never waits for",
        )

    def test_host_independent_pi_checks_run_once_outside_the_platform_matrix(self):
        # Issue #390: every one of these consumes neither matrix.os nor
        # matrix.pi-version, so six cells produced six identical verdicts.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        self.assertIn("ca-pi-checks", sorted(jobs))
        canonical, matrix = jobs["ca-pi-checks"], jobs["ca-pi-tools"]
        self.assertNotIn("strategy:", canonical, "the canonical Pi job must not fan out")
        self.assertIn("runs-on: ubuntu-latest", canonical)
        for token in (
            "run: python tools/build-host-packages.py --check",
            "run: npm run typecheck",
            "run: npm run build",
            "run: python .github/scripts/test_pi_security.py",
            "run: python .github/scripts/test_pi_parity.py",
            "run: python .github/scripts/pi_benchmark.py --samples 100",
        ):
            with self.subTest(token=token):
                self.assertIn(token, canonical, f"ca-pi-checks must own `{token}`")
                self.assertNotIn(token, matrix, f"ca-pi-tools still repeats `{token}` per cell")
        # Everything whose verdict genuinely depends on the installed Pi
        # version or the host OS stays in the six-cell matrix.
        for token in (
            "os: [ubuntu-latest, windows-latest, macos-latest]",
            "npm install --global @earendil-works/pi-coding-agent@${{ matrix.pi-version }}",
            "run: npm test -- test/package.test.ts",
            "run: python .github/scripts/test_pi_package.py --rpc-commands",
            "--pi-version ${{ matrix.pi-version }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, matrix, f"ca-pi-tools must keep `{token}`")

    def test_every_pi_ci_and_promotion_job_declares_a_bounded_timeout(self):
        # Issue #399: a wedged npm install or leaked process otherwise holds a
        # hosted runner until GitHub's platform maximum.
        missing: list[str] = []
        unbounded: list[str] = []
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        candidates = [
            (".github/workflows/ci.yml", job_id, block)
            for job_id, block in workflow_jobs(ci).items()
            if "[PI  ]" in block
        ]
        promotion = PI_PROMOTION_WORKFLOW.read_text(encoding="utf-8")
        candidates += [
            (".github/workflows/pi-promotion.yml", job_id, block)
            for job_id, block in workflow_jobs(promotion).items()
        ]
        self.assertGreaterEqual(len(candidates), 8, "the Pi job scan found too few jobs")
        for workflow, job_id, block in candidates:
            declared = _JOB_TIMEOUT.search(block)
            if declared is None:
                missing.append(f"{workflow}:{job_id}")
                continue
            if not 0 < int(declared.group(1)) < HOSTED_JOB_MAXIMUM_MINUTES:
                unbounded.append(f"{workflow}:{job_id}={declared.group(1)}")
        self.assertEqual(missing, [], "Pi jobs with no timeout-minutes")
        self.assertEqual(unbounded, [], "Pi job timeouts at or above the hosted maximum")

    def test_pi_upstream_canary_concludes_advisory_rather_than_failed(self):
        # Issue #381: the WATCH lane reports upstream incompatibility; that is
        # its signal, not its failure.  Expected incompatibility is absorbed at
        # STEP level so the check concludes green, while a break in the canary
        # HARNESS still turns it red - which is why there is no job-level
        # continue-on-error to swallow it.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        canary = workflow_jobs(ci)["ca-pi-latest"]
        self.assertIsNone(
            re.search(r"(?m)^    continue-on-error: true$", canary),
            "job-level continue-on-error hides canary harness failures",
        )
        for probe in ("id: admission", "id: platform-contract"):
            self.assertIn(probe, canary, f"the canary must address its probe step: {probe}")
        self.assertEqual(
            len(re.findall(r"(?m)^        continue-on-error: true$", canary)),
            2,
            "exactly the two upstream-compatibility probes absorb their own failure",
        )
        # The harness (toolchain + latest-Pi install) must NOT be absorbed.
        harness = re.search(
            r"(?ms)^      - name: Install reviewed toolchain and external latest Pi.*?(?=^      - name: )",
            canary,
        )
        self.assertIsNotNone(harness, "canary harness install step is missing")
        self.assertNotIn("continue-on-error", harness.group(0))
        self.assertIn("if: always()", canary, "the advisory receipt must always publish")
        self.assertIn("GITHUB_STEP_SUMMARY", canary, "the advisory verdict must be visible")
        # And the aggregate gate stays independent of the advisory result.
        self.assertNotIn("ca-pi-latest", aggregate_required_results(ci))

    def test_documentation_contract_is_always_required_by_merge_readiness(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("  documentation-contract:\n", ci)
        self.assertIn('name: "[CHECK] | [REPO] | Documentation contract"', ci)
        aggregate = ci.split("  ci-passed:\n", 1)[1]
        self.assertIn("      - documentation-contract\n", aggregate)
        self.assertIn("${{ needs['documentation-contract'].result }}", aggregate)


class ReceiptCommandTest(unittest.TestCase):
    def test_cli_writes_deterministic_json_and_a_markdown_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(REPO_ROOT / ".github/ci-impact-map.json"),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                ["pi-adapter", "pi-latest"],
            )
            self.assertEqual(
                receipt["predicted_not_selected"],
                ["ca-surface", "codex-surface", "pi-surface"],
            )
            self.assertEqual(
                receipt["selected"][0]["reproduce"],
                "npm --prefix plugins/ca-pi/tools test",
            )
            self.assertEqual(
                receipt["selected"][0]["reason"],
                "matched path: plugins/ca-pi/tools/src/extension.ts",
            )
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)
            self.assertIn("Predicted not selected", markdown)
            self.assertIn("advisory", markdown)

    def test_a_malformed_map_falls_back_to_broad_validation_without_failing(self):
        # main()'s documented fail-safe contract (tools/ci-impact.py ~422-448):
        # any planner error (ImpactMapError/OSError/ValueError) degrades to the
        # broad-lane receipt rather than propagating, and the exit code stays 0
        # so a planner bug can never fail-closed the merge gate itself.
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            malformed_map = temporary_path / "impact-map.json"
            malformed_map.write_text("not valid json", encoding="utf-8")
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(malformed_map),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                ["broad-lane"],
            )
            self.assertTrue(receipt["reason"].startswith("planner error:"))
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)


if __name__ == "__main__":
    unittest.main()
