#!/usr/bin/env python3
"""Attest the SMARTS design-quality decision-engine validator rules by exact
Go test name, following the go-test-json-by-name pattern of
test_artifact_native.py.

This module is deliberately table-driven so later tasks can add more
Go-test-to-method mappings without a second module:

- TestSMARTSProfileLegacyAccepted and TestSMARTSProfileLegacyRejectsUnknown
  (package internal/observation) attest that the observation contract
  routes 0.1.0 and 0.2.0 records to their own schema and validator.
- TestSMARTSRefusesDecisionCriticalUnknownSelection and
  TestSMARTSRecordsProfile020 (package internal/operations) attest that
  smarts-apply records 0.2.0 decisions and refuses a decision-critical
  Unknown.
- test_engine_module_passes runs the whole core/artifacts module and fails
  on any fail event or nonzero exit; on a non-Linux host it also runs every
  Linux-only package in full through the WSL path below.

Each row of CASES is (unittest method name, Go package under core/artifacts,
exact Go test name). Each unittest method passes ONLY when its Go test
emitted an Action=="pass" event for its exact Test name; a skip, a missing
event (crash, build failure, no match), or a fail all leave the method
failing.

The internal/operations test harness is `//go:build linux`. On a non-Linux
host such a package is cross-compiled (GOOS=linux) into a test binary
outside the repository and run under WSL (default distribution, or
CA_WSL_DISTRO); `go tool test2json` turns its output into the same events.
A host without WSL emits no pass events, so those methods fail closed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PACKAGE_OBSERVATION = "./internal/observation"
PACKAGE_OPERATIONS = "./internal/operations"

# (unittest method name, Go package, exact Go test name)
CASES: list[tuple[str, str, str]] = [
    ("test_unknown_requires_fields", PACKAGE_OBSERVATION, "TestSMARTSDecisionUnknownRequiresFields"),
    ("test_unknown_fields_forbidden_elsewhere", PACKAGE_OBSERVATION, "TestSMARTSDecisionUnknownFieldsForbiddenElsewhere"),
    ("test_indifferent_is_uniform", PACKAGE_OBSERVATION, "TestSMARTSDecisionIndifferentIsUniform"),
    ("test_critical_unknown_blocks_selection", PACKAGE_OBSERVATION, "TestSMARTSDecisionCriticalUnknownBlocksSelection"),
    ("test_strong_refused_with_critical_unknown", PACKAGE_OBSERVATION, "TestSMARTSDecisionStrongRefusedWithCriticalUnknown"),
    ("test_unknown_cannot_shield_dominated_choice", PACKAGE_OBSERVATION, "TestSMARTSDecisionUnknownCannotShieldDominatedChoice"),
    ("test_v2_keeps_retained_rejections", PACKAGE_OBSERVATION, "TestSMARTSDecisionV2KeepsRetainedRejections"),
    ("test_legacy_profile_accepted", PACKAGE_OBSERVATION, "TestSMARTSProfileLegacyAccepted"),
    ("test_legacy_profile_rejects_unknown", PACKAGE_OBSERVATION, "TestSMARTSProfileLegacyRejectsUnknown"),
    ("test_smarts_apply_refuses_critical_unknown_selection", PACKAGE_OPERATIONS, "TestSMARTSRefusesDecisionCriticalUnknownSelection"),
    ("test_smarts_apply_records_profile_020", PACKAGE_OPERATIONS, "TestSMARTSRecordsProfile020"),
]


def _linux_only(package: str) -> bool:
    """True when any test file in the package is gated by `//go:build linux`.

    One gated file is enough: on a non-Linux host those tests would silently not
    compile, so the whole package must also run on Linux to cover them.
    """
    tests = sorted((REPO / "core/artifacts" / package).glob("*_test.go"))
    return bool(tests) and any(
        f.read_text(encoding="utf-8").splitlines()[:1] == ["//go:build linux"] for f in tests
    )


def _wsl_path(path: Path) -> str:
    drive, rest = os.path.splitdrive(str(path.resolve()))
    return "/mnt/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def _run_via_wsl(package: str, pattern: str) -> subprocess.CompletedProcess:
    """Cross-compile a Linux test binary and run it under WSL, emitting
    `go test -json` events through `go tool test2json`."""
    module = REPO / "core/artifacts"
    with tempfile.TemporaryDirectory(prefix="smarts-go-") as tmp:
        binary = Path(tmp) / "package.test"
        env = dict(os.environ, GOOS="linux", GOARCH="amd64", CGO_ENABLED="0")
        build = subprocess.run(
            ["go", "test", "-c", "-buildvcs=false", "-o", str(binary), package],
            cwd=module, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        if build.returncode != 0:
            return build
        wsl = ["wsl.exe"] + (["-d", os.environ["CA_WSL_DISTRO"]] if os.environ.get("CA_WSL_DISTRO") else [])
        run = subprocess.run(
            wsl + ["--cd", _wsl_path(module / package), "--exec", _wsl_path(binary),
                   "-test.v=test2json", "-test.count=1", "-test.run", pattern],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return subprocess.run(
            ["go", "tool", "test2json", "-p", package], cwd=module, input=run.stdout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) if run.stdout else subprocess.CompletedProcess(run.args, run.returncode, b"", run.stderr)


def _run_go_tests(package: str, names: list[str]) -> tuple[dict[str, bool], str, str]:
    """Run exactly the named Go tests in one package via `go test -json` and
    report pass/fail by exact Test field. A skip, a missing event (crash,
    build failure, no match), or a fail all read as not-passed; this
    function never raises on a non-zero go exit so callers fail their own
    assertions instead of erroring in setUpClass."""
    pattern = "^(" + "|".join(sorted(names)) + ")$"
    if sys.platform != "linux" and _linux_only(package):
        result = _run_via_wsl(package, pattern)
        stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", "replace")
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
    else:
        command = ["go", "test", "-json", "-buildvcs=false", "-count=1", package, "-run", pattern]
        result = subprocess.run(
            command, cwd=REPO / "core/artifacts",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        stdout, stderr = result.stdout, result.stderr
    outcomes: dict[str, bool] = {name: False for name in names}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("Test")
        if name in outcomes and event.get("Action") == "pass":
            outcomes[name] = True
    return outcomes, stdout, stderr


def _module_failures() -> list[str]:
    """Run every test in the engine module; return what failed. `go test
    ./...` builds Linux-only packages without their tests on other hosts,
    so those packages also run in full under WSL there."""
    module = REPO / "core/artifacts"
    failures: list[str] = []
    result = subprocess.run(
        ["go", "test", "-json", "-buildvcs=false", "-count=1", "./..."], cwd=module,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    runs = [("./...", result.returncode, result.stdout, result.stderr, False)]
    if sys.platform != "linux":
        for package in sorted(p for p in module.glob("internal/*") if p.is_dir()):
            rel = "./" + package.relative_to(module).as_posix()
            if _linux_only(rel):
                wsl = _run_via_wsl(rel, ".*")
                out = wsl.stdout if isinstance(wsl.stdout, str) else wsl.stdout.decode("utf-8", "replace")
                err = wsl.stderr if isinstance(wsl.stderr, str) else wsl.stderr.decode("utf-8", "replace")
                runs.append((rel, wsl.returncode, out, err, True))
    for label, code, stdout, stderr, needs_pass in runs:
        passed = False
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("Action") == "fail":
                failures.append(f"{label}: {event.get('Package')} {event.get('Test') or ''}".strip())
            if event.get("Action") == "pass" and not event.get("Test"):
                passed = True
        if code != 0 or (needs_pass and not passed):
            failures.append(f"{label}: exit {code}, package pass={passed}\n{stderr[-2000:]}")
    return failures


def _run_all(cases: list[tuple[str, str, str]]) -> dict[str, bool]:
    """Group cases by Go package and run go test once per package."""
    by_package: dict[str, list[str]] = {}
    for _, package, go_test_name in cases:
        by_package.setdefault(package, []).append(go_test_name)
    outcomes: dict[str, bool] = {}
    for package, names in by_package.items():
        package_outcomes, stdout, stderr = _run_go_tests(package, names)
        outcomes.update(package_outcomes)
        missing = [n for n, ok in package_outcomes.items() if not ok]
        if missing:
            sys.stderr.write(
                f"[test_smarts_engine_contract] {package}: no pass event for {sorted(missing)}\n"
            )
            sys.stderr.write(stdout)
            sys.stderr.write(stderr)
    return outcomes


class SMARTSEngineContract(unittest.TestCase):
    """One method per required Go test; each is independently assertable."""

    results: dict[str, bool] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = _run_all(CASES)

    def _assert_go_test_passed(self, go_test_name: str) -> None:
        self.assertTrue(
            self.results.get(go_test_name, False),
            f"{go_test_name} did not emit a go test -json pass event",
        )

    def test_unknown_requires_fields(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionUnknownRequiresFields")

    def test_unknown_fields_forbidden_elsewhere(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionUnknownFieldsForbiddenElsewhere")

    def test_indifferent_is_uniform(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionIndifferentIsUniform")

    def test_critical_unknown_blocks_selection(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionCriticalUnknownBlocksSelection")

    def test_strong_refused_with_critical_unknown(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionStrongRefusedWithCriticalUnknown")

    def test_unknown_cannot_shield_dominated_choice(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionUnknownCannotShieldDominatedChoice")

    def test_v2_keeps_retained_rejections(self) -> None:
        self._assert_go_test_passed("TestSMARTSDecisionV2KeepsRetainedRejections")

    def test_legacy_profile_accepted(self) -> None:
        self._assert_go_test_passed("TestSMARTSProfileLegacyAccepted")

    def test_legacy_profile_rejects_unknown(self) -> None:
        self._assert_go_test_passed("TestSMARTSProfileLegacyRejectsUnknown")

    def test_smarts_apply_refuses_critical_unknown_selection(self) -> None:
        self._assert_go_test_passed("TestSMARTSRefusesDecisionCriticalUnknownSelection")

    def test_smarts_apply_records_profile_020(self) -> None:
        self._assert_go_test_passed("TestSMARTSRecordsProfile020")

    def test_engine_module_passes(self) -> None:
        failures = _module_failures()
        self.assertEqual(failures, [], "engine module regression:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
