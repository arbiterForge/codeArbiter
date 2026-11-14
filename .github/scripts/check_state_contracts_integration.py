#!/usr/bin/env python3
"""P-02 partial-program integrity, independent of all-current publication readiness.

Read committed Git objects. Recorded statuses are not changed when current
inputs differ. Existing hosted-proof authentication stays with its bounded,
authenticated readiness owner. This check adds no remote mutation, acquisition,
publication or approval.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import sys

import major_readiness as readiness

CORPUS = readiness.CORPUS
# Immutable accepted105-file intake from bootstrap13b0943fa7075c2272c2038a8642bf6ea589e311.
# A self-consistent rewritten manifest is not an approved rebaseline.
FROZEN_MANIFEST_SHA256 = "86be15f1b12dc7f9e052268a1c627f47af99713020449593a2c57b4cb3fc58f4"
ADVANCED = {"TESTED", "INSTALLED_QUALIFIED", "RELEASED", "PRESERVED", "NOT_APPLICABLE"}


def safe_path(value):
    path = PurePosixPath(value) if isinstance(value, str) else PurePosixPath("..")
    readiness.require(not path.is_absolute() and ".." not in path.parts and ":" not in str(path)
                      and "\\" not in str(path) and str(path) not in (".", ""), "unsafe program reference")
    return str(path)


def validate(repo, source, load=None):
    readiness.require(readiness.SHA.fullmatch(source or ""), "exact integration source required")
    cache = {}
    def original(commit, path):
        safe_path(path)
        key = (commit, path)
        if key not in cache:
            cache[key] = readiness.blob(repo, commit, path) if load is None else load(commit, path)
        return cache[key]
    def read(path):
        return json.loads(original(source, CORPUS + path))

    manifest_bytes = original(source, CORPUS + "MANIFEST.json")
    readiness.require(readiness.digest(manifest_bytes) == FROZEN_MANIFEST_SHA256,
                      "accepted frozen intake manifest identity differs")
    manifest = json.loads(manifest_bytes)
    readiness.require(manifest.get("schema") == "codearbiter-handoff-manifest/1", "frozen manifest schema differs")
    entries = manifest.get("files")
    readiness.require(isinstance(entries, list) and len(entries) == 105, "frozen intake must contain105files")
    seen = set()
    for entry in entries:
        readiness.require(isinstance(entry, dict), "malformed frozen entry")
        path = safe_path(entry.get("path"))
        readiness.require(path not in seen and not path.startswith("execution/") and path != "MANIFEST.json",
                          "duplicate or live path in frozen intake")
        seen.add(path)
        content = original(source, CORPUS + path)
        readiness.require(type(entry.get("bytes")) is int and len(content) == entry["bytes"]
                          and readiness.digest(content) == entry.get("sha256"), "frozen intake identity differs: " + path)

    # Reuse the maintained accounting vocabulary and row checks. Their source is
    # read from the selected commit, never from a mismatched external checkout.
    module_path = CORPUS + "execution/tools/coverage_ledger.py"
    module = type(sys)("integration_coverage_ledger")
    module.__file__ = str(repo / module_path)
    exec(compile(original(source, module_path), module.__file__, "exec"), module.__dict__)
    ledger = read("execution/coverage-ledger.json")
    progress = read("execution/progress.json")
    tasks = read("contracts/tasks.json")["tasks"]
    readiness.require(isinstance(tasks, list) and all(isinstance(t, dict) for t in tasks), "malformed tasks")
    task_ids = {t["id"] for t in tasks}
    readiness.require(len(task_ids) == len(tasks), "duplicate task identity")
    owners = {t["owner"] for t in tasks}
    added = progress.get("new_required_work", [])
    readiness.require(isinstance(added, list) and all(isinstance(t, dict) and t.get("id") for t in added), "malformed added tasks")
    task_ids.update(t["id"] for t in added)
    definitions = {
        "findings": ("contracts/finding-dispositions.json", "records", "finding_id"),
        "machines": ("contracts/machine-coverage.json", "machines", "machine_id"),
        "transitions": ("contracts/transition-coverage.json", "transitions", "transition_id"),
    }
    contracts = {}
    for group, (path, field, identity) in definitions.items():
        records = read(path)[field]
        readiness.require(isinstance(records, list) and all(isinstance(row, dict) for row in records), "malformed " + group)
        contracts[group] = {row[identity]: row for row in records}
        readiness.require(len(contracts[group]) == len(records), "duplicate " + group + " identity")
    new_rows = progress.get("new_transition_rows", [])
    readiness.require(isinstance(new_rows, list) and all(isinstance(row, dict) and row.get("transition_id") for row in new_rows), "malformed added transitions")
    contracts["added_transitions"] = {row["transition_id"]: row for row in new_rows}
    readiness.require(len(contracts["added_transitions"]) == len(new_rows), "duplicate added transition")
    owners.update(row["owner"] for row in contracts["machines"].values())
    readiness.require(set(ledger) == {"schema", "derived_from", "status_vocabulary", *contracts}, "ledger top-level shape differs")
    readiness.require(ledger["schema"] == module.SCHEMA and isinstance(ledger["status_vocabulary"], list)
                      and len(ledger["status_vocabulary"]) == len(module.STATUSES)
                      and set(ledger["status_vocabulary"]) == module.STATUSES, "ledger vocabulary differs")
    authenticated, counts, applicability = {}, {}, {}
    for group, rows in contracts.items():
        readiness.require(isinstance(ledger[group], dict) and set(ledger[group]) == set(rows), "disposition population differs: " + group)
        counts[group] = dict(Counter(row.get("status") for row in ledger[group].values() if isinstance(row, dict)))
        for identity, contract in rows.items():
            row = ledger[group][identity]
            readiness.require(isinstance(row, dict) and isinstance(row.get("task_ids"), list)
                              and row["task_ids"] and len(set(row["task_ids"])) == len(row["task_ids"])
                              and isinstance(row.get("evidence"), list)
                              and all(isinstance(item, dict) for item in row["evidence"]), "malformed disposition row: " + identity)
            problems = module._problems_for(group, identity, row, task_ids, owners)
            readiness.require(not problems, "; ".join(problems))
            readiness.require(row.get("treatment") == contract.get("treatment"), "disposition treatment differs: " + identity)
            # Findings may coordinate several known task owners. Existing
            # family/transition ownership stays explicit; this is not a new
            # ordinary-work assignment or publication-completion gate.
            if group in ("machines", "transitions"):
                readiness.require((row.get("owner") or contract.get("owner")) in owners,
                                  "disposition owner missing: " + identity)
            for item in row["evidence"]:
                readiness.require(item.get("kind") in module.EVIDENCE_KINDS and readiness.SHA.fullmatch(item.get("commit", ""))
                                  and isinstance(item.get("ref"), str), "malformed evidence reference: " + identity)
                safe_path(item["ref"].split("#", 1)[0])
            if row["status"] not in ADVANCED:
                # PLANNED makes no observation claim. IMPLEMENTED may cite a
                # committed source trace rather than a passed proof record.
                for item in row["evidence"]:
                    content = original(item["commit"], item["ref"].split("#", 1)[0])
                    if item.get("sha256"):
                        readiness.require(readiness.digest(content) == item["sha256"], "implemented reference bytes differ")
                continue
            paths = readiness.evidence_paths(contract)
            readiness.require(paths, "disposition has no owning source: " + identity)
            cell = "disposition:" + group + ":" + identity
            # Historical authenticity is mandatory even when current inputs
            # are stale. This function never substitutes current bytes for old.
            readiness.authenticate_recorded_disposition(repo, source, cell, row, paths, original, authenticated)
            changed, unavailable = set(), set()
            for item in row["evidence"]:
                record = authenticated[("proof", item.get("ref_commit", source), item["ref"], item["sha256"])]
                different, unknown = readiness.disposition_input_applicability(
                    repo, source, record, original, authenticated)
                changed.update(different)
                unavailable.update(unknown)
            applicability[cell] = {"status": "UNKNOWN" if unavailable else "STALE" if changed else "APPLICABLE",
                                   "changed_inputs": sorted(changed), "unavailable_inputs": sorted(unavailable)}
    return {"schema": "codearbiter-integration-integrity/1", "source_commit": source,
            "result": "PASSED", "frozen_files": len(entries), "counts": counts,
            "current_applicability": applicability, "recorded_statuses_changed": False,
            "product_qualification": False, "publication_readiness": "NOT_ASSESSED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source", default="HEAD")
    args = parser.parse_args(argv)
    try:
        source = readiness.command(["git", "rev-parse", "--verify", args.source + "^{commit}"], args.repo).decode().strip()
        report = validate(args.repo, source)
        print(json.dumps(report, indent=2))
        return 0
    except (readiness.ReadinessError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(json.dumps({"schema": "codearbiter-integration-integrity/1", "result": "FAILED", "error": str(error),
                          "product_qualification": False, "publication_readiness": "NOT_ASSESSED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
