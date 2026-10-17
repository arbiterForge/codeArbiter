#!/usr/bin/env python3
"""Execute two complete authority shards concurrently in one native CI job.

The four existing fixture-preserving partitions remain the coverage owners.
Two runner jobs each execute two isolated child processes, avoiding four full
runner startups per platform. All child results must match fresh discovery.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from artifact_ci import read_regular, unique_object
from _artifactworkerlib import worker_directory
import run_artifact_authority_shard as shard

GROUPS = ((0, 2), (1, 3))
SHARD_COUNT = 4
HERE = Path(__file__).resolve().parent


def selected_group(raw: str) -> tuple[int, int]:
    """Admit only a declared nonempty group; never allow arbitrary selections."""
    if raw not in ("0", "1"):
        raise ValueError("AUTHORITY_GROUP must be 0 or 1")
    return GROUPS[int(raw)]


def validate_report(report: Any, *, index: int, plan: list[list[str]],
                    plan_sha256: str) -> None:
    """Require complete actual execution of exactly the freshly discovered shard."""
    if (not isinstance(report, dict)
            or report.get("format") != "codearbiter.authority-shard-observation/1"
            or type(report.get("shard")) is not int or report["shard"] != index
            or type(report.get("shard_count")) is not int or report["shard_count"] != SHARD_COUNT
            or type(report.get("discovered_count")) is not int or report["discovered_count"] != sum(map(len, plan))
            or report.get("selected_ids") != plan[index]
            or report.get("plan_sha256") != plan_sha256
            or report.get("passed") is not True
            or type(report.get("tests_run")) is not int or report["tests_run"] != len(plan[index])
            or type(report.get("skipped")) is not int
            or not 0 <= report["skipped"] < len(plan[index])):
        raise ValueError("authority child did not prove its exact discovered membership")
    observations = report.get("observations")
    if (not isinstance(observations, list)
            or len(observations) != len(plan[index])
            or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in observations)):
        raise ValueError("authority child lacks complete execution observations")
    if sorted(item.get("id", "") for item in observations) != sorted(plan[index]):
        raise ValueError("authority child observations are missing or duplicated")
    outcomes = [item.get("outcome") for item in observations]
    if (any(outcome not in ("pass", "skip", "expected_failure") for outcome in outcomes)
            or outcomes.count("skip") != report["skipped"] or "pass" not in outcomes):
        raise ValueError("authority child observations do not establish a real pass")


def run_child(index: int, root: Path, environment: dict[str, str]) -> dict[str, Any]:
    """Run an unchanged shard interpreter with its own home, temp and report files."""
    # Do not place native fixture roots below the report tree. The portable
    # filesystem checks repeatedly inspect path ancestry; needless depth makes
    # every operation slower. A fresh, flat host-temp root is still worker-owned.
    with worker_directory(prefix=f"ca-authority-{index}-") as temporary:
        owned = Path(temporary)
        for name in ("home", "config", "data", "cache"):
            (owned / name).mkdir()
        env = dict(environment, AUTHORITY_SHARD=str(index), AUTHORITY_SHARD_COUNT=str(SHARD_COUNT),
                   AUTHORITY_TIMING_OUTPUT=str(root / f"shard-{index}.json"),
                   HOME=str(owned / "home"), USERPROFILE=str(owned / "home"),
                   TMP=str(owned), TEMP=str(owned), TMPDIR=str(owned),
                   XDG_CONFIG_HOME=str(owned / "config"), XDG_DATA_HOME=str(owned / "data"),
                   XDG_CACHE_HOME=str(owned / "cache"), PYTHONUTF8="1")
        # Retain the existing job deadline and per-test subprocess bounds.
        # Do not retry failed tests or trade failure evidence for a shorter time.
        with (root / f"shard-{index}.log").open("xb") as log:
            completed = subprocess.run(
                [sys.executable, str(HERE / "run_artifact_authority_shard.py")],
                cwd=HERE.parents[1], env=env, stdout=log, stderr=subprocess.STDOUT, check=False,
            )
    print(f"authority shard {index}: exit {completed.returncode}", flush=True)
    return {"shard": index, "exit": completed.returncode}


def run_group(group: str, destination: Path) -> dict[str, Any]:
    """Join both required children without accepting missing or stale reports."""
    selected = selected_group(group)
    partitions, _ = shard.partition(shard.discover(), SHARD_COUNT, shard.load_weights())
    plan = [[case.id() for case in part] for part in partitions]
    plan_sha256 = hashlib.sha256(json.dumps(plan, separators=(",", ":")).encode()).hexdigest()
    destination = destination.absolute()
    destination.mkdir()  # Fresh per-job directory; refuse any pre-existing report tree.
    environment = dict(os.environ)
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {index: pool.submit(run_child, index, destination, environment) for index in selected}
        for index, future in futures.items():
            try:
                outcome = future.result()
                results.append(outcome)
                if outcome["exit"] != 0:
                    raise ValueError(f"authority shard {index} exited {outcome['exit']}")
                report = json.loads(read_regular(destination / f"shard-{index}.json", 2 * 1024 * 1024),
                                    object_pairs_hook=unique_object)
                validate_report(report, index=index, plan=plan, plan_sha256=plan_sha256)
            except (OSError, ValueError) as error:
                errors.append(f"shard {index}: {str(error)[:1000]}")
    report = {
        "format": "codearbiter.authority-group-observation/1", "group": int(group),
        "shards": list(selected), "plan_sha256": plan_sha256,
        "selected_ids": [name for index in selected for name in plan[index]],
        "children": results, "passed": not errors, "errors": errors,
    }
    with (destination / "group.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


def main() -> None:
    """Execute only the workflow-selected group, then fail closed on any child error."""
    try:
        result = run_group(os.environ["AUTHORITY_GROUP"], Path(os.environ["AUTHORITY_GROUP_OUTPUT"]))
        print(json.dumps(result, indent=2), flush=True)
    except (KeyError, OSError, ValueError) as error:
        raise SystemExit(f"authority group refused: {error}") from error
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
