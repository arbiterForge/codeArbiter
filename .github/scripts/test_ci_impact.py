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
PI_PLATFORM_CONTRACT = REPO_ROOT / ".github" / "scripts" / "test_pi_platform_contract.py"
SANDBOX_LAYERS_TOOL = REPO_ROOT / ".github" / "scripts" / "check_sandbox_docker_layers.py"

# Issue #406: a ca-sandbox suite that spins REAL containers used to carry its
# own private `dockerAvailable()` probe and degrade to `describe.skip` when the
# probe failed - on the REQUIRED CI job too.  The only sanctioned spelling is
# now the shared `dockerGate("<layer>")` helper, which fails hard in required
# mode and records an execution sentinel.  These two shapes are what a
# re-introduced private self-skip looks like.
_PRIVATE_DOCKER_PROBE = re.compile(
    r"(?m)^\s*(?:(?:async\s+)?function\s+dockerAvailable\b"
    r"|const\s+\w+\s*=\s*(?:HAS_DOCKER|dockerAvailable\(\))\s*\?)"
)
# A `docker info` PROBE, as an executed shell command - not the word "docker
# info" inside a YAML comment, which is all the job used to contain.
_DOCKER_PREFLIGHT = re.compile(r"(?m)^\s+(?:if\s+!\s+)?docker info\b")

# `needs.<id>.result` and `needs['<id>'].result` are the two spellings GitHub
# accepts; the aggregate gate uses both depending on whether the job id has a
# hyphen in it.
_NEEDS_RESULT = re.compile(r"needs(?:\.([A-Za-z0-9_-]+)|\['([^']+)'\])\.result")
_JOB_TIMEOUT = re.compile(r"(?m)^    timeout-minutes: (\d+)$")
# GitHub-hosted runners hard-stop a job at 6 hours; a repository-defined bound
# is only meaningful well under that.
HOSTED_JOB_MAXIMUM_MINUTES = 360

# A Pi Vitest file is HOST-DEPENDENT when it compares the *live* process
# platform against a literal.  Two shapes matter and both make a lane on the
# wrong OS unable to attest the file:
#   test.skipIf(process.platform !== "win32")(...)   - the whole test never runs
#   process.platform === "win32" ? "junction" : "dir" - a different OS primitive
# Deliberately NOT matched: an *injected* platform (`buildChildEnv({ platform:
# "win32", ... })`) or one merely forwarded into a pure function
# (`platform: process.platform`).  Those exercise the same code on every host,
# which is exactly what makes them safe to run once on the canonical lane.
_LIVE_PLATFORM_SELECTOR = re.compile(r"(?:process|os)\.platform\s*(?:===|!==)")
# The three-OS fan-out that makes a job able to attest a host-dependent file.
_PLATFORM_MATRIX = "os: [ubuntu-latest, windows-latest, macos-latest]"
# Vitest declaration heads, with their modifier chain (`.skipIf`, `.each`, ...).
_TEST_DECLARATION = re.compile(
    r"(?m)^\s*(?P<kind>describe|test|it)(?P<modifier>(?:\.[A-Za-z]+)*)\s*(?=[(`])"
)
# Modifiers that disable tests unconditionally - at *static* time, with no host
# predicate to satisfy.  `.only` belongs here because it silently disables every
# sibling in the file.  A committed suite carrying any of these is "assigned" to
# a required job while contributing no verdict (issue #405, one level down).
# `.fails` is deliberately absent: it still executes the body and asserts it
# throws, so it is a real verdict.
_STATICALLY_DISABLED = frozenset({"skip", "todo", "only"})


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


def platform_sensitive_pi_test_files() -> set[str]:
    """Committed ca-pi Vitest files whose behaviour is selected by the live OS.

    File-granular assignment (``unassigned_pi_test_files`` above) proves every
    suite runs *somewhere*.  It cannot prove the suite runs where its own
    platform gate opens: a ``test.skipIf(process.platform !== "win32")`` case is
    reported as "assigned" by a Linux-only lane that skips it.  This is the
    second half of the #405 contract.
    """
    return {
        path.name
        for path in PI_TEST_DIR.glob("*.test.ts")
        if _LIVE_PLATFORM_SELECTOR.search(path.read_text(encoding="utf-8"))
    }


def platform_contract_vitest_files() -> set[str]:
    """Vitest files ``test_pi_platform_contract.py`` re-runs inside a matrix cell.

    Read out of the script rather than duplicated here, so moving a file between
    its fixture groups cannot silently desynchronise this contract.
    """
    source = PI_PLATFORM_CONTRACT.read_text(encoding="utf-8")
    return {
        name.rsplit("/", 1)[-1]
        for name in re.findall(r'"(test/[A-Za-z0-9._-]+\.test\.ts)"', source)
    }


def os_matrix_pi_test_files(ci: str, committed: set[str]) -> set[str]:
    """Vitest files a required Pi job executes on *every* supported OS.

    Only a job that fans out over ``_PLATFORM_MATRIX`` counts: a job pinned to
    one runner can never execute the other hosts' gated cases.
    """
    jobs = workflow_jobs(ci)
    covered: set[str] = set()
    for job_id in aggregate_required_results(ci):
        block = jobs.get(job_id, "")
        if not job_id.startswith("ca-pi") or _PLATFORM_MATRIX not in block:
            continue
        for match in re.finditer(r"(?m)^\s+run: npm test(?P<rest>[^\n]*)$", block):
            rest = match.group("rest").strip()
            if not rest:
                covered |= set(committed)
                continue
            covered |= {
                token.rsplit("/", 1)[-1] for token in rest.split() if token.endswith(".test.ts")
            }
        if "test_pi_platform_contract.py" in block:
            covered |= platform_contract_vitest_files()
    return covered


def statically_disabled_pi_tests() -> dict[str, list[str]]:
    """{file: [disabled declarations]} for `.skip` / `.todo` / `.only`.

    These disable a case with no host predicate to satisfy, so the file stays
    "assigned" to a required job while contributing nothing.  A genuine platform
    gate must use ``.skipIf`` / ``.runIf``, which the OS-matrix contract above
    then holds to running somewhere the gate opens.
    """
    disabled: dict[str, list[str]] = {}
    for path in sorted(PI_TEST_DIR.glob("*.test.ts")):
        found = [
            f"{match.group('kind')}{match.group('modifier')}"
            for match in _TEST_DECLARATION.finditer(path.read_text(encoding="utf-8"))
            if _STATICALLY_DISABLED & set(match.group("modifier").split(".")[1:])
        ]
        if found:
            disabled[path.name] = found
    return disabled


_spec = importlib.util.spec_from_file_location("ci_impact", _TOOL)
module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = module
_spec.loader.exec_module(module)


def sandbox_layers_module():
    """The ca-sandbox docker-layer sentinel verifier, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "check_sandbox_docker_layers_ci_impact", SANDBOX_LAYERS_TOOL
    )
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def privately_gated_sandbox_suites() -> dict[str, list[str]]:
    """ca-sandbox test files that still hand-roll their own docker self-skip."""
    layers = sandbox_layers_module()
    offenders: dict[str, list[str]] = {}
    for path in layers.sandbox_test_files(REPO_ROOT):
        found = [
            match.group(0).strip()
            for match in _PRIVATE_DOCKER_PROBE.finditer(path.read_text(encoding="utf-8"))
        ]
        if found:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = found
    return offenders


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

    def test_the_required_sandbox_job_fails_when_docker_is_unavailable(self):
        # Issue #406 AC-1/AC-2.  ca-sandbox is the driver that clones UNTRUSTED
        # repositories, and every real-container suite used to convert a failed
        # `docker info` probe into `describe.skip` - on the required merge-gate
        # job too.  A runner Docker outage therefore removed the ONLY isolation,
        # mount, network, lifecycle and teardown evidence while the board went
        # green off pure argv-builder tests.  The required job must now (a)
        # preflight the daemon BEFORE the suite and exit non-zero without it,
        # and (b) run the suite in docker-REQUIRED mode so a daemon that dies
        # mid-run fails the file instead of skipping it.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ca-sandbox-tools", aggregate_required_results(ci))
        job = workflow_jobs(ci)["ca-sandbox-tools"]
        suite = job.find("run: npm test")
        self.assertNotEqual(suite, -1, "the sandbox job no longer runs `npm test`")
        probe = _DOCKER_PREFLIGHT.search(job)
        self.assertIsNotNone(probe, "the sandbox job runs no `docker info` preflight command")
        self.assertLess(
            probe.start(), suite, "the docker preflight must run BEFORE the sandbox suite"
        )
        self.assertIn(
            "exit 1",
            job[probe.start():suite],
            "the docker preflight does not fail the job when the daemon is unavailable",
        )
        self.assertIn(
            'CA_SANDBOX_REQUIRE_DOCKER: "1"',
            job,
            "the required sandbox suite does not run in docker-REQUIRED mode",
        )

    def test_the_required_sandbox_job_asserts_a_real_container_execution_sentinel(self):
        # Issue #406 AC-3.  A preflight only proves the daemon answered once.
        # The required job must additionally prove that every docker-gated
        # layer actually EXECUTED, so a suite that silently stops registering
        # (a bad filter, a renamed file, a gate left inert) cannot pass.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = workflow_jobs(ci)["ca-sandbox-tools"]
        suite = job.find("run: npm test")
        self.assertIn(
            "CA_SANDBOX_DOCKER_SENTINEL",
            job,
            "the sandbox suite records no machine-checkable execution sentinel",
        )
        verifier = job.find("check_sandbox_docker_layers.py")
        self.assertNotEqual(verifier, -1, "the sandbox job never asserts the layer sentinel")
        self.assertGreater(
            verifier, suite, "the layer sentinel must be asserted AFTER the suite runs"
        )

    def test_every_real_container_sandbox_suite_routes_through_the_shared_docker_gate(self):
        # The contract above is only worth as much as the gate's reach: a suite
        # keeping its own `dockerAvailable()` + `describe.skip` pair opts itself
        # back out of required mode AND contributes no sentinel line, which is
        # exactly the #406 hole one file at a time.
        self.assertEqual(
            privately_gated_sandbox_suites(),
            {},
            "ca-sandbox suites still self-skipping outside the shared docker gate",
        )
        layers = sandbox_layers_module().declared_layers(REPO_ROOT)
        self.assertTrue(layers, "no dockerGate() layers found - the scan is wrong")
        # The containment guarantees the sandbox actually advertises. Each is a
        # real-container suite, so each must be a sentinel-bearing layer.
        for required in ("isolation", "lifecycle", "network", "run"):
            self.assertIn(
                required,
                layers,
                f"the {required!r} real-container layer is not behind the shared docker gate",
            )

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

    def test_every_platform_gated_pi_test_file_runs_on_every_supported_os(self):
        # Issue #405, second half / issue #390 AC-2.  File-granular assignment
        # is blind to a test's own platform gate: a Linux-only lane reports
        # activation.test.ts as "assigned" while
        # `test.skipIf(process.platform !== "win32")` at line 388 silently skips
        # the only case that reads the fixed user-global update cache.  Any file
        # that branches on the LIVE platform must therefore run in a job that
        # fans out over all three operating systems, or its Windows/macOS branch
        # is attested by nothing.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        sensitive = platform_sensitive_pi_test_files()
        self.assertTrue(sensitive, "no platform-gated Pi test files found - the scan is wrong")
        self.assertLessEqual(
            sensitive,
            committed,
            "the platform scan drifted off the committed Vitest set",
        )
        self.assertEqual(
            sorted(sensitive - os_matrix_pi_test_files(ci, committed)),
            [],
            "Pi test files that branch on the live platform but run on one OS only",
        )

    def test_the_platform_gate_contract_binds_to_the_three_os_fan_out(self):
        # The contract above must BITE on each way it can be broken.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        covered = os_matrix_pi_test_files(ci, committed)
        self.assertTrue(covered, "no required Pi job fans out over the OS matrix")
        # (a) A host-INDEPENDENT suite is not credited with OS coverage, so a
        #     future win32-gated test added to one would be caught.
        self.assertNotIn("policy.test.ts", covered)
        self.assertNotIn("policy.test.ts", platform_sensitive_pi_test_files())
        # (b) Collapsing the fan-out to a single runner uncovers everything.
        collapsed = ci.replace(_PLATFORM_MATRIX, "os: [ubuntu-latest]", 1)
        self.assertEqual(os_matrix_pi_test_files(collapsed, committed), set())
        # (c) Dropping one file from the matrix step uncovers exactly that file.
        without = ci.replace(" test/activation.test.ts", "", 1)
        self.assertEqual(
            covered - os_matrix_pi_test_files(without, committed), {"activation.test.ts"}
        )

    def test_no_committed_pi_test_is_disabled_by_a_static_skip_todo_or_only(self):
        # Issue #405, the "assigned but inert" hole: `npm test` makes every file
        # a required gate, but a `test.skip` / `test.todo` inside one - or a
        # single `test.only`, which mutes every sibling - keeps the board green
        # with no verdict behind it.  A platform gate must be expressed as
        # `.skipIf` / `.runIf` so the OS-matrix contract above can hold it.
        self.assertEqual(
            statically_disabled_pi_tests(),
            {},
            "ca-pi Vitest declarations disabled with no host predicate to satisfy",
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
                # `pi-checks` is the canonical host-independent job added by
                # issue #390.  A Pi payload edit now predicts all three Pi
                # contracts; omitting it made the receipt under-report the
                # required jobs a reviewer must wait on.
                ["pi-adapter", "pi-checks", "pi-latest"],
            )
            self.assertEqual(
                receipt["predicted_not_selected"],
                ["ca-surface", "codex-surface", "pi-surface"],
            )
            self.assertEqual(
                receipt["selected"][0]["reproduce"],
                "python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.10",
            )
            self.assertEqual(
                receipt["selected"][1]["reproduce"],
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
