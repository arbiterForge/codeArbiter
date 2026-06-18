#!/usr/bin/env python3
"""farm-first-pass.py — first-pass-through-gate & escalation rate from a farm report.

Part of the token-efficiency investigation. Serves two plan steps at once:
  - Step 6 kill-criterion: is `--farm` actually buying juice, or are escalations
    sending the work back to the premium (Max-pool) path?
  - Step 2c baseline (farm path): the first-pass-through-gate rate for worker-authored
    tasks. A cheap author that needs multiple attempts to go green can cost MORE than a
    stronger model passing first try; this measures it instead of guessing.

Source of truth: `.farm/farm-report.json`, written by tools/farm.ts:
  { plan, aborted, tokens:{prompt,completion},
    results:[ {id, status:"green"|"escalate", attempts, promptTokens?, completionTokens?,
               mutationScore?, warning?, note?, filesWritten?} ],
    blocked:[ {id, reason} ], ts }

Definitions:
  - settled task         = appears in results[] (green or escalate)
  - first-pass green      = status=="green" AND attempts==1
  - first-pass rate       = first-pass green / settled
  - escalation rate       = escalate / settled   (compare to FARM_ABORT_ESCALATION_RATE)
  - A high escalation rate (or aborted=true) means re-dispatches land back on the Max
    pool — the farm's "extra juice" erodes. That is the revert signal.

Usage:
  farm-first-pass.py [PATH]      Default: .farm/farm-report.json
  farm-first-pass.py --json [PATH]
"""
from __future__ import annotations

import json
import os
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def analyze(report):
    results = report.get("results", []) or []
    blocked = report.get("blocked", []) or []
    settled = len(results)
    green = [r for r in results if r.get("status") == "green"]
    escalated = [r for r in results if r.get("status") == "escalate"]
    first_pass = [r for r in green if int(r.get("attempts", 0)) == 1]
    multi_pass = [r for r in green if int(r.get("attempts", 0)) > 1]

    def rate(n):
        return (n / settled * 100) if settled else 0.0

    total_attempts = sum(int(r.get("attempts", 0)) for r in results)
    warned = [r for r in results if r.get("warning")]

    return {
        "aborted": bool(report.get("aborted")),
        "settled": settled,
        "blocked": len(blocked),
        "green": len(green),
        "escalated": len(escalated),
        "first_pass_green": len(first_pass),
        "multi_pass_green": len(multi_pass),
        "first_pass_rate_pct": round(rate(len(first_pass)), 1),
        "escalation_rate_pct": round(rate(len(escalated)), 1),
        "avg_attempts_per_settled": round(total_attempts / settled, 2) if settled else 0.0,
        "gaming_warnings": len(warned),
        "tokens": report.get("tokens", {}),
        "model": (report.get("plan") or {}).get("model"),
        "ts": report.get("ts"),
        "_results": results,
        "_blocked": blocked,
    }


def main(argv):
    json_out = "--json" in argv
    pos = [a for a in argv if not a.startswith("--")]
    path = pos[0] if pos else os.path.join(".farm", "farm-report.json")
    if not os.path.exists(path):
        print(f"No farm report at {path}. Run `/ca:sprint --farm` first, or pass a path.",
              file=sys.stderr)
        return 1

    a = analyze(load(path))

    if json_out:
        out = {k: v for k, v in a.items() if not k.startswith("_")}
        print(json.dumps(out, indent=2))
        return 0

    print(f"Farm first-pass / escalation report  ({path})")
    if a["model"]:
        print(f"Model: {a['model']}    written: {a['ts']}")
    if a["aborted"]:
        print("\n  ** ABORTED by circuit breaker — escalation exceeded threshold. **")
        print("  ** Re-dispatches go to the premium Max pool: net-negative this run. **")
    print()
    print(f"  settled tasks      : {a['settled']}  (blocked: {a['blocked']})")
    print(f"  green              : {a['green']}  (first-pass: {a['first_pass_green']}, "
          f"multi-pass: {a['multi_pass_green']})")
    print(f"  escalated          : {a['escalated']}")
    print(f"  FIRST-PASS RATE    : {a['first_pass_rate_pct']}%   <- Step 2c baseline / kill-criterion")
    print(f"  escalation rate    : {a['escalation_rate_pct']}%   (compare to FARM_ABORT_ESCALATION_RATE, default 50%)")
    print(f"  avg attempts/task  : {a['avg_attempts_per_settled']}")
    print(f"  gaming warnings    : {a['gaming_warnings']}")
    tok = a["tokens"] or {}
    if tok:
        print(f"  worker tokens      : prompt={tok.get('prompt','?')} completion={tok.get('completion','?')} "
              f"(off-pool; the point of the farm)")

    if a["escalated"]:
        print("\n  Escalated tasks (each one's labor reverts to the premium path):")
        for r in a["_results"]:
            if r.get("status") == "escalate":
                note = (r.get("note") or "").split("\n")[0]
                print(f"    - {r.get('id')}: attempts={r.get('attempts')}  {note}")
    print("\nVerdict heuristic: low first-pass rate + nonzero escalation = the cheap worker")
    print("is offloading less than it looks; weigh against a premium-only run of the same slice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
