#!/usr/bin/env python3
"""Live accountability ledger for the program's findings, machine families and rows (P-02).

The intake contracts (contracts/*.json) are frozen history. This tool derives the
LIVE ledger at execution/coverage-ledger.json from them once (`init`), then
validates it (`check`) every time execution records change.

Status vocabulary keeps the distinctions PROGRAM.md requires:
  PLANNED -> IMPLEMENTED -> TESTED -> INSTALLED_QUALIFIED -> RELEASED
plus NOT_APPLICABLE (needs a cited unsupported/inapplicable contract) and
PRESERVED (an unchanged baseline edge with reviewed conformance evidence).

`check` refuses: a missing or extra intake ID; an unknown owner/task; any status
beyond PLANNED without evidence; evidence lacking a kind, a reference and an
exact commit; NOT_APPLICABLE without a contract citation; and TESTED-or-later
evidence whose kinds are only review/comment (a comment is not proof).
It never certifies product behavior; it only keeps the accounting honest.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2]
LEDGER = CORPUS / "execution" / "coverage-ledger.json"
PROGRESS = CORPUS / "execution" / "progress.json"
SCHEMA = "codearbiter-coverage-ledger/1"
ORDER = ["PLANNED", "IMPLEMENTED", "TESTED", "INSTALLED_QUALIFIED", "RELEASED"]
TERMINAL_OTHER = {"NOT_APPLICABLE", "PRESERVED"}
STATUSES = set(ORDER) | TERMINAL_OTHER
EVIDENCE_KINDS = {"test", "sequence-test", "installed-run", "hosted-run", "review", "conformance-check", "release-readback"}
EXECUTED_KINDS = EVIDENCE_KINDS - {"review"}
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def intake():
    tasks = _load(CORPUS / "contracts/tasks.json")["tasks"]
    findings = _load(CORPUS / "contracts/finding-dispositions.json")["records"]
    machines = _load(CORPUS / "contracts/machine-coverage.json")["machines"]
    rows = _load(CORPUS / "contracts/transition-coverage.json")["transitions"]
    return tasks, findings, machines, rows


def init(force: bool) -> int:
    if LEDGER.exists() and not force:
        print(f"{LEDGER} exists; refusing to overwrite live evidence (use --force only for a fresh, empty ledger)", file=sys.stderr)
        return 1
    tasks, findings, machines, rows = intake()

    def entry(owner, treatment, task_ids):
        return {"owner": owner, "treatment": treatment, "task_ids": list(task_ids), "status": "PLANNED", "evidence": []}

    ledger = {
        "schema": SCHEMA,
        "derived_from": "contracts/{finding-dispositions,machine-coverage,transition-coverage}.json (frozen intake)",
        "status_vocabulary": ORDER + sorted(TERMINAL_OTHER),
        "findings": {f["finding_id"]: entry(None, f["treatment"], f["task_ids"]) for f in findings},
        "machines": {m["machine_id"]: entry(m["owner"], m["treatment"], m["task_ids"]) for m in machines},
        "transitions": {r["transition_id"]: entry(r["owner"], r["treatment"], r["task_ids"]) for r in rows},
        "added_transitions": {},
    }
    LEDGER.write_text(json.dumps(ledger, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    print(f"initialized {LEDGER.name}:{len(findings)} findings, {len(machines)} machines, {len(rows)} rows")
    return 0


def _problems_for(kind: str, key: str, item: dict, task_ids: set[str], owners: set[str]) -> list[str]:
    out = []
    where = f"{kind}[{key}]"
    status = item.get("status")
    if status not in STATUSES:
        out.append(f"{where}: unknown status {status!r}")
        return out
    if item.get("owner") is not None and item["owner"] not in owners:
        out.append(f"{where}: unknown owner {item['owner']!r}")
    for tid in item.get("task_ids", []):
        if tid not in task_ids:
            out.append(f"{where}: unknown task {tid}")
    evidence = item.get("evidence", [])
    if status == "PLANNED":
        return out
    if not evidence:
        out.append(f"{where}: status {status} without evidence")
        return out
    for i, ev in enumerate(evidence):
        if ev.get("kind") not in EVIDENCE_KINDS:
            out.append(f"{where}.evidence[{i}]: kind must be one of {sorted(EVIDENCE_KINDS)}")
        if not ev.get("ref"):
            out.append(f"{where}.evidence[{i}]: missing ref (test id, run URL, review record)")
        if not _SHA.match(str(ev.get("commit", ""))):
            out.append(f"{where}.evidence[{i}]: missing exact 40-hex source commit")
    if status == "NOT_APPLICABLE" and not item.get("contract"):
        out.append(f"{where}: NOT_APPLICABLE requires a cited unsupported/inapplicable contract")
    if status in ORDER[2:] or status == "PRESERVED":
        if status != "PRESERVED" and not any(ev.get("kind") in EXECUTED_KINDS for ev in evidence):
            out.append(f"{where}: {status} needs executed evidence, not review alone")
    if status in ("INSTALLED_QUALIFIED", "RELEASED") and not any(ev.get("kind") in {"installed-run", "release-readback"} for ev in evidence):
        out.append(f"{where}: {status} needs installed-run or release-readback evidence")
    return out


def check(require_complete: bool) -> int:
    tasks, findings, machines, rows = intake()
    ledger = _load(LEDGER)
    problems: list[str] = []
    if ledger.get("schema") != SCHEMA:
        problems.append("ledger schema mismatch")
    progress = _load(PROGRESS) if PROGRESS.exists() else {}
    task_ids = {t["id"] for t in tasks} | {w.get("id") for w in progress.get("new_required_work", []) if w.get("id")}
    owners = {m["owner"] for m in machines} | {t["owner"] for t in tasks}
    expected = {
        "findings": {f["finding_id"] for f in findings},
        "machines": {m["machine_id"] for m in machines},
        "transitions": {r["transition_id"] for r in rows},
    }
    for kind, ids in expected.items():
        have = set(ledger.get(kind, {}))
        if have != ids:
            problems.append(f"{kind}: missing {sorted(ids - have)[:5]} extra {sorted(have - ids)[:5]}")
    counts: dict[str, Counter] = {}
    for kind in ("findings", "machines", "transitions", "added_transitions"):
        counts[kind] = Counter()
        for key, item in ledger.get(kind, {}).items():
            counts[kind][item.get("status")] += 1
            problems.extend(_problems_for(kind, key, item, task_ids, owners))
    if require_complete:
        for kind in ("findings", "machines", "transitions", "added_transitions"):
            pending = counts[kind]["PLANNED"] + counts[kind]["IMPLEMENTED"]
            if pending:
                problems.append(f"{kind}: {pending} entries not yet TESTED/PRESERVED/NOT_APPLICABLE")
    report = {
        "kind": "COVERAGE_LEDGER_ACCOUNTING_ONLY",
        "result": "FAILED" if problems else "PASSED",
        "counts": {k: dict(v) for k, v in counts.items()},
        "problems": problems[:50],
        "problem_count": len(problems),
        "product_qualification": False,
    }
    print(json.dumps(report, indent=2))
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--force", action="store_true")
    p_check = sub.add_parser("check")
    p_check.add_argument("--require-complete", action="store_true", help="promotion predicate: nothing PLANNED/IMPLEMENTED")
    args = parser.parse_args(argv)
    return init(args.force) if args.cmd == "init" else check(args.require_complete)


if __name__ == "__main__":
    raise SystemExit(main())
