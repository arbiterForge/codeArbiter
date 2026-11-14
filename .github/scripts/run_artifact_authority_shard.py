#!/usr/bin/env python3
"""Run exhaustive duration-balanced authority shards, keeping class fixtures intact.

The timing file is a scheduling hint, never a test-selection allowlist. Discovery
owns membership, including newly added tests and imported regression classes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import unittest
from collections import defaultdict
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
TIMINGS = HERE.parent / "fixtures/artifact-authority-timings.json"


def flatten(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    """Yield every discovered case, including cases inside imported suites."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def discover() -> list[unittest.TestCase]:
    """Load the real authority module and fail on any incomplete discovery."""
    path = HERE / "test_artifact_authority_adapter.py"
    name = path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("authority suite cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    loader = unittest.TestLoader()
    cases = list(flatten(loader.loadTestsFromModule(module)))
    if loader.errors:
        raise ValueError("authority suite discovery failed: " + "\n".join(loader.errors))
    if not cases:
        raise ValueError("authority suite discovered zero tests")
    return sorted(cases, key=lambda case: case.id())


def class_id(case: unittest.TestCase) -> str:
    """Name the indivisible fixture owner rather than splitting it by test count."""
    cls = type(case)
    return cls.__module__ + "." + cls.__qualname__


def load_weights(path: Path = TIMINGS) -> dict[str, dict[str, float | int]]:
    """Read finite measured hints; stale or missing names cannot suppress tests."""
    from ci20_native_binding import read_regular, unique_object
    document = json.loads(read_regular(path, 1024 * 1024), object_pairs_hook=unique_object)
    if (not isinstance(document, dict)
            or document.get("format") != "codearbiter.authority-timing-hints/1"
            or not isinstance(document.get("classes"), dict)):
        raise ValueError("invalid authority timing hint file")
    weights = document["classes"]
    for name, entry in weights.items():
        if (not isinstance(name, str) or not name
                or not isinstance(entry, dict) or set(entry) != {"seconds", "tests"}
                or type(entry["tests"]) is not int or entry["tests"] < 1
                or type(entry["seconds"]) not in (int, float)
                or not math.isfinite(entry["seconds"]) or entry["seconds"] <= 0):
            raise ValueError("invalid class timing hint")
    return weights


def partition(cases: list[unittest.TestCase], count: int,
              weights: dict[str, dict[str, float | int]]) -> tuple[list[list[unittest.TestCase]], list[float]]:
    """Greedily balance measured fixture groups and prove complete disjoint membership."""
    if type(count) is not int or not 1 <= count <= 32:
        raise ValueError("shard count must be an integer from 1 through 32")
    ids = [case.id() for case in cases]
    if not cases or len(set(ids)) != len(ids):
        raise ValueError("discovery must contain unique nonempty test IDs")
    groups: dict[str, list[unittest.TestCase]] = defaultdict(list)
    for case in cases:
        groups[class_id(case)].append(case)
    if len(groups) < count:
        raise ValueError("not enough fixture groups for nonempty authority shards")
    def cost(name: str) -> float:
        hint = weights.get(name)
        per_test = float(hint["seconds"]) / int(hint["tests"]) if hint else 1.0
        return max(0.001, per_test) * len(groups[name])
    shards: list[list[unittest.TestCase]] = [[] for _ in range(count)]
    totals = [0.0] * count
    for name in sorted(groups, key=lambda name: (-cost(name), name)):
        target = min(range(count), key=lambda index: (totals[index], index))
        shards[target].extend(sorted(groups[name], key=lambda case: case.id()))
        totals[target] += cost(name)
    for shard in shards:
        shard.sort(key=lambda case: (class_id(case), case.id()))
    actual = [case.id() for shard in shards for case in shard]
    if len(actual) != len(set(actual)) or set(actual) != set(ids) or any(not shard for shard in shards):
        raise ValueError("authority partition lost, repeated, or emptied required coverage")
    return shards, totals


class TimedResult(unittest.TextTestResult):
    """Retain actual case durations and outcomes for future balancing."""
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.observations: list[dict[str, Any]] = []
        self.started: dict[str, float] = {}
        self.outcomes: dict[str, str] = {}

    def startTest(self, test: unittest.TestCase) -> None:
        self.started[test.id()] = time.perf_counter()
        self.outcomes[test.id()] = "pass"
        super().startTest(test)

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        self.outcomes[test.id()] = "failure"
        super().addFailure(test, err)

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        self.outcomes[test.id()] = "error"
        super().addError(test, err)

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        self.outcomes[test.id()] = "skip"
        super().addSkip(test, reason)

    def addExpectedFailure(self, test: unittest.TestCase, err: Any) -> None:
        self.outcomes[test.id()] = "expected_failure"
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        self.outcomes[test.id()] = "unexpected_success"
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test: unittest.TestCase, subtest: unittest.TestCase, err: Any) -> None:
        if err is not None:
            self.outcomes[test.id()] = "failure"
        super().addSubTest(test, subtest, err)

    def stopTest(self, test: unittest.TestCase) -> None:
        self.observations.append({
            "id": test.id(), "class": class_id(test),
            "seconds": round(time.perf_counter() - self.started[test.id()], 6),
            "outcome": self.outcomes[test.id()],
        })
        super().stopTest(test)


def group_indexes(count: int, groups: int, group: int) -> list[int]:
    """The partition indexes one of `groups` jobs runs; together they cover every index once."""
    if not 1 <= groups <= count or not 0 <= group < groups:
        raise ValueError("authority group is out of range")
    return [index for index in range(count) if index % groups == group]


def plan_digest(shards: list[list[unittest.TestCase]]) -> str:
    plan = [[case.id() for case in shard] for shard in shards]
    return hashlib.sha256(json.dumps(plan, separators=(",", ":")).encode()).hexdigest()


def coverage_problems(codes: list[int], reports: list[dict[str, Any] | None],
                      expected: list[str], plan_sha256: str | None = None) -> list[str]:
    """Every reason concurrent shard results do not prove the expected population."""
    problems = [f"shard {i} exited {code}" for i, code in enumerate(codes) if code]
    problems += [f"shard {i} wrote no observation" for i, report in enumerate(reports) if report is None]
    present = [report for report in reports if report is not None]
    plans = {report["plan_sha256"] for report in present}
    if len(plans) > 1 or (plan_sha256 is not None and plans - {plan_sha256}):
        problems.append("shards disagree on the partition plan")
    selected = [test for report in present for test in report["selected_ids"]]
    if len(selected) != len(set(selected)) or sorted(selected) != sorted(expected):
        problems.append("shard selections do not cover the discovered population exactly once")
    if any(report.get("passed") is not True for report in present):
        problems.append("a shard did not pass")
    return problems


def retention_directory(count: int, indexes: list[int]) -> Path | None:
    """Opt in to one exclusive, bounded runner-temp data directory."""
    value = os.environ.get("AUTHORITY_OBSERVATION_DIR")
    if value is None:
        return None
    root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    target = Path(value)
    info = root.lstat()
    if (count != 4 or indexes != list(range(4)) or not target.is_absolute()
            or target.parent.resolve(strict=True) != root or target.name in ("", ".", "..")
            or not stat.S_ISDIR(info.st_mode) or root.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("authority observations require four complete shards and a direct runner-temp child")
    # mkdir refuses existing files, directories and dangling links alike.
    target.mkdir()
    return target


def retention_context() -> dict[str, Any]:
    """Read the existing native-consumer binding, never create a new stamp."""
    import ci20_native_binding as binding
    import major_qualification_report as observer
    repo = HERE.parents[1]
    source = observer.source_identity(repo)
    metadata = Path(os.environ["RUNNER_TEMP"]) / "ci20-native-tested.json"
    raw = binding.read_regular(metadata, 65536)
    record = json.loads(raw, object_pairs_hook=binding.unique_object)
    candidate = Path(os.environ["ARTIFACT_TEST_INSTALLATION"])
    verified = binding.verify(candidate, metadata, record["platform"])
    if (not source["clean"] or source["source_commit"] != verified["source_commit"]
            or binding.read_regular(metadata, 65536) != raw):
        raise ValueError("authority source or original candidate metadata changed")
    return {"source": source, "run_id": int(verified["run_id"]),
            "execution_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "native_binding": verified,
            "candidate_identity": {k: verified[k] for k in ("manifest_sha256", "binary_sha256")},
            "native_metadata_path": str(metadata),
            "native_metadata_sha256": hashlib.sha256(raw).hexdigest()}


def observation_problems(reports: list[dict[str, Any] | None],
                         observations: list[dict[str, Any] | None],
                         before: dict[str, Any], after: dict[str, Any],
                         expected_argv: list[str]) -> list[str]:
    """Join actual original TestResult events to their original timing rows."""
    if before != after or not before["source"].get("clean"):
        return ["authority source or candidate changed across original shards"]
    problems = []
    outcomes = {"pass": "passed", "skip": "skipped", "failure": "failed", "error": "failed",
                "expected_failure": "expected-failure", "unexpected_success": "failed"}
    discovered = sum(len(r["selected_ids"]) for r in reports
                     if isinstance(r, dict) and isinstance(r.get("selected_ids"), list))
    for index, (report, observed) in enumerate(zip(reports, observations)):
        try:
            if (not isinstance(report, dict) or report.get("format") != "codearbiter.authority-shard-observation/1"
                    or type(report.get("shard")) is not int or report["shard"] != index
                    or type(report.get("shard_count")) is not int or report["shard_count"] != 4
                    or type(report.get("discovered_count")) is not int or report["discovered_count"] != discovered
                    or not isinstance(observed, dict)
                    or observed.get("format") != "codearbiter.major-test-observation/1"
                    or observed.get("producer") != "python-test-result-observer"
                    or observed.get("proof_kind") != "source-test"
                    or observed.get("source_commit") != before["source"]["source_commit"]
                    or observed.get("source_tree") != before["source"]["source_tree"]
                    or observed.get("clean") is not True or observed.get("source_stable") is not True
                    or type(observed.get("ci_run_id")) is not int or observed["ci_run_id"] != before["run_id"]
                    or type(observed.get("exit_code")) is not int or observed["exit_code"] != 0
                    or observed.get("argv") != expected_argv):
                raise ValueError
            selected, timings, tests = report["selected_ids"], report["observations"], observed["tests"]
            if (not isinstance(selected, list) or not isinstance(timings, list) or not isinstance(tests, list)
                    or not 0 < len(selected) <= 32768
                    or type(report["tests_run"]) is not int or report["tests_run"] != len(selected)
                    or len(timings) != len(selected) or len(tests) != len(selected)):
                raise ValueError
            actual = {}
            for row in timings:
                if (not isinstance(row, dict) or row["id"] in actual or row["outcome"] not in outcomes
                        or type(row["seconds"]) not in (int, float)
                        or not math.isfinite(row["seconds"]) or row["seconds"] < 0):
                    raise ValueError
                actual[row["id"]] = outcomes[row["outcome"]]
            if len(set(selected)) != len(selected) or set(actual) != set(selected):
                raise ValueError
            named = {}
            for row in tests:
                if not isinstance(row, dict) or set(row) != {"id", "result"} or row["id"] in named:
                    raise ValueError
                named[row["id"]] = row["result"]
            expected = {"python:.github/scripts/run_artifact_authority_shard.py:" + name: result
                        for name, result in actual.items()}
            if named != expected:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            problems.append("authority original named observation differs from its shard/source/candidate")
    if len(reports) != 4 or len(observations) != 4:
        problems.append("authority original observation population is not four shards")
    return problems


def retain_observations(target: Path, indexes: list[int], timing_raw: list[bytes],
                        observation_raw: list[bytes], context: dict[str, Any], plan: str) -> None:
    """Retain original JSON bytes; write the passing bundle descriptor last."""
    from ci20_native_binding import read_regular
    files = {}
    for index, timing, observed in zip(indexes, timing_raw, observation_raw):
        for kind, raw in (("timing", timing), ("observation", observed)):
            name = f"shard-{index}-{kind}.json"
            with (target / name).open("xb") as stream:
                stream.write(raw)
            files[name] = hashlib.sha256(raw).hexdigest()
    raw = read_regular(Path(context["native_metadata_path"]), 65536)
    if hashlib.sha256(raw).hexdigest() != context["native_metadata_sha256"]:
        raise ValueError("authority original candidate metadata changed before retention")
    with (target / "native-binding.json").open("xb") as stream:
        stream.write(raw)
    files["native-binding.json"] = hashlib.sha256(raw).hexdigest()
    with (target / "bundle.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"format": "codearbiter.authority-retained-observations/1",
                   "state": "VALIDATED_ORIGINAL_SHARDS", "context": context,
                   "partition_indexes": indexes, "plan_sha256": plan, "files": files},
                  stream, indent=2, sort_keys=True)
        stream.write("\n")


def run_all(count: int, expected: list[str], indexes: list[int] | None = None,
            plan_sha256: str | None = None) -> bool:
    """Run every shard as a concurrent child on this host and prove complete coverage.

    One runner per platform uses its own cores instead of four queued runners
    repeating checkout, toolchain and candidate setup. Each child keeps process
    isolation; the parent accepts only identical plans whose selections cover
    the discovered population exactly once and whose every child passed.
    A platform may split the plan across jobs; each job then runs and proves
    only its own indexes against the same plan.
    """
    indexes = list(range(count)) if indexes is None else indexes
    retained = retention_directory(count, indexes)
    if retained is not None and (not isinstance(plan_sha256, str) or len(plan_sha256) != 64
                                 or set(plan_sha256) - set("0123456789abcdef")):
        raise ValueError("authority retention requires the exact discovered partition digest")
    context_before = retention_context() if retained is not None else None
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="authority-shards-") as raw:
        reports = [Path(raw) / f"shard-{index}.json" for index in indexes]
        observations = [Path(raw) / f"shard-{index}-observation.json" for index in indexes]
        logs = [Path(raw) / f"shard-{index}.log" for index in indexes]
        children = []
        for slot, index in enumerate(indexes):
            env = dict(os.environ, AUTHORITY_SHARD=str(index), AUTHORITY_SHARD_COUNT=str(count),
                       AUTHORITY_TIMING_OUTPUT=str(reports[slot]))
            with logs[slot].open("wb") as log:
                argv = [sys.executable, str(Path(__file__).resolve())]
                if retained is not None:
                    argv = [sys.executable, str(HERE / "major_qualification_report.py"), "observe-python",
                            "--repo", str(HERE.parents[1]), "--output", str(observations[slot]),
                            ".github/scripts/run_artifact_authority_shard.py"]
                children.append(subprocess.Popen(argv,
                                                 env=env, stdout=log, stderr=subprocess.STDOUT))
        # Bound each child below the job timeout so a hung shard still yields
        # every partition's log instead of the runner discarding them all.
        deadline = time.monotonic() + float(os.environ.get("AUTHORITY_CHILD_TIMEOUT_SECONDS", "2100"))
        codes = []
        for index, child in enumerate(children):
            try:
                codes.append(child.wait(timeout=max(0.0, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                with logs[index].open("ab") as log:
                    log.write(b"\nauthority shard timed out and was terminated\n")
                codes.append(-1)
        loaded: list[dict[str, Any] | None] = []
        observed_loaded: list[dict[str, Any] | None] = []
        timing_raw, observation_raw = [], []
        for slot, index in enumerate(indexes):
            print(f"::group::authority shard {index}/{count} (exit {codes[slot]})", flush=True)
            print(logs[slot].read_text(encoding="utf-8", errors="replace"), flush=True)
            print("::endgroup::", flush=True)
            try:
                if retained is not None:
                    from ci20_native_binding import read_regular, unique_object
                    timing = read_regular(reports[slot], 16 * 1024 * 1024)
                    observed = read_regular(observations[slot], 16 * 1024 * 1024)
                    timing_value = json.loads(timing, object_pairs_hook=unique_object)
                    observation_value = json.loads(observed, object_pairs_hook=unique_object)
                    loaded.append(timing_value)
                    observed_loaded.append(observation_value)
                    timing_raw.append(timing); observation_raw.append(observed)
                else:
                    loaded.append(json.loads(reports[slot].read_text(encoding="utf-8")))
            except (OSError, ValueError):
                loaded.append(None)
                observed_loaded.append(None)
    problems = coverage_problems(codes, loaded, expected, plan_sha256)
    if retained is not None:
        problems += observation_problems(loaded, observed_loaded, context_before, retention_context(),
                                         [sys.executable, str(Path(__file__).resolve())])
        if not problems:
            retain_observations(retained, indexes, timing_raw, observation_raw, context_before, plan_sha256)
    present = [report for report in loaded if report is not None]
    slowest = sorted((o for report in present for o in report["observations"]), key=lambda o: -o["seconds"])[:10]
    print("slowest authority cases: " + ", ".join(f"{o['id'].rsplit('.', 1)[-1]} {o['seconds']:.1f}s" for o in slowest),
          flush=True)
    for problem in problems:
        print(f"authority shards FAILED: {problem}", flush=True)
    return not problems


def main() -> None:
    """Execute one complete shard and emit its membership and actual outcomes."""
    if os.environ.get("AUTHORITY_SHARD") == "all":
        try:
            count = int(os.environ.get("AUTHORITY_SHARD_COUNT", "4"))
            groups = int(os.environ.get("AUTHORITY_GROUPS", "1"))
            group = int(os.environ.get("AUTHORITY_GROUP", "0"))
            indexes = group_indexes(count, groups, group)
            cases = discover()
            # Refuses an invalid count before any child starts.
            shards, _ = partition(cases, count, load_weights())
            expected = [case.id() for index in indexes for case in shards[index]]
        except (OSError, ValueError) as error:
            raise SystemExit(str(error)) from error
        print(f"authority group {group}/{groups}: partitions {indexes} of {count}", flush=True)
        if not run_all(count, expected, indexes, plan_digest(shards)):
            raise SystemExit(1)
        return
    try:
        index = int(os.environ["AUTHORITY_SHARD"])
        count = int(os.environ.get("AUTHORITY_SHARD_COUNT", "4"))
        cases = discover()
        shards, costs = partition(cases, count, load_weights())
        if not 0 <= index < count:
            raise ValueError("authority shard index is out of range")
    except (KeyError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    selected = shards[index]
    plan = [[case.id() for case in shard] for shard in shards]
    print(f"authority shard {index}/{count}: {len(selected)} of {len(cases)} tests; "
          f"estimated class weights {[round(value, 1) for value in costs]}", flush=True)
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(unittest.TestSuite(selected))
    passed = result.wasSuccessful() and result.testsRun == len(selected)
    # Native-only skips remain legitimate, but a wholly unexercised shard is not proof.
    passed = passed and result.testsRun > len(result.skipped) + len(result.expectedFailures)
    report = {
        "format": "codearbiter.authority-shard-observation/1",
        "shard": index, "shard_count": count,
        "discovered_count": len(cases), "selected_ids": plan[index],
        "plan_sha256": plan_digest(shards),
        "tests_run": result.testsRun, "skipped": len(result.skipped),
        "passed": bool(passed), "observations": result.observations,
    }
    destination = os.environ.get("AUTHORITY_TIMING_OUTPUT")
    if destination:
        with Path(destination).open("x", encoding="utf-8", newline="\n") as output:
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
