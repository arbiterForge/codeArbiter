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
    from artifact_ci import read_regular, unique_object
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


def main() -> None:
    """Execute one complete shard and emit its membership and actual outcomes."""
    try:
        index = int(os.environ["AUTHORITY_SHARD"])
        count = int(os.environ.get("AUTHORITY_SHARD_COUNT", "2"))
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
        "plan_sha256": hashlib.sha256(json.dumps(plan, separators=(",", ":")).encode()).hexdigest(),
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
