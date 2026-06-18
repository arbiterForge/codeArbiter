#!/usr/bin/env python3
"""reviewer-yield.py — per-reviewer dispatch-to-finding yield from checkpoint docs.

Part of the token-efficiency investigation (Step 4 of the plan). Answers: when a
reviewer IS dispatched, how often does it actually return a finding? A reviewer that
is dispatched a lot but almost never finds anything on the changes it sees is the
candidate for (a) a tighter dispatch trigger and (b) a safer model downgrade (Step 2).

Source of truth: the "## Finding summary" table inside each
`.codearbiter/checkpoints/YYYY-MM-DD*.md` document (written by checkpoint-aggregator).
Each row is a reviewer that ran in that checkpoint, with its CRITICAL/HIGH/MEDIUM/LOW
counts. A row whose cells say "Not run" is excluded from the dispatch denominator;
a row that PASSed with zero findings counts as a dispatch that produced nothing.

LIMITATIONS (read before trusting):
- Coverage is whatever checkpoint docs exist on disk. The `/sprint` Phase-4 quality
  review does not always persist a checkpoint document, so sprint-only review activity
  may be undercounted. This measures the persisted record, not every dispatch ever.
- "Finding produced" means an enforced C/H/M/L severity. Bare [NEEDS-TRIAGE] notes are
  not counted as findings.

Usage:
  reviewer-yield.py [CHECKPOINT_DIR ...]
      Default dir: ./.codearbiter/checkpoints
  reviewer-yield.py --json        Emit machine-readable JSON instead of a table.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

SEVERITIES = ("critical", "high", "medium", "low")
_LEADING_INT = re.compile(r"-?\d+")


def _cell_count(raw: str) -> int:
    """Leading integer of a summary cell; 0 for '—', 'PASS', 'Not run', prose, etc."""
    m = _LEADING_INT.search(raw.strip())
    return int(m.group()) if m and raw.strip()[:1].isdigit() else 0


def _norm(name: str) -> str:
    return name.strip().strip("*` ").strip()


def parse_finding_summary(text: str):
    """Yield (reviewer, [c,h,m,l], not_run) for each data row of the first
    '## Finding summary' table in a checkpoint document."""
    lines = text.splitlines()
    in_section = False
    seen_table = False
    for line in lines:
        if line.lstrip().lower().startswith("## finding summary"):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("---"):
                break  # left the section
            if not stripped.startswith("|"):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 2:
                continue
            reviewer = _norm(cells[0])
            low = reviewer.lower()
            if not seen_table:
                # First table row is the header (| Reviewer | CRITICAL | ... |)
                seen_table = True
                continue
            if set(reviewer) <= {"-", " "} or low.startswith(":--") or "--" in reviewer:
                continue  # separator row
            if not reviewer or low.startswith("total") or low.startswith("**total"):
                continue
            sev_cells = cells[1:5]
            not_run = any("not run" in c.lower() for c in sev_cells)
            counts = [_cell_count(c) for c in sev_cells] + [0, 0, 0, 0]
            yield reviewer, counts[:4], not_run


def collect(dirs):
    files = []
    for d in dirs:
        files.extend(sorted(glob.glob(os.path.join(d, "*.md"))))
    stats = {}  # reviewer -> dict
    for fp in files:
        try:
            text = open(fp, encoding="utf-8").read()
        except OSError as e:
            print(f"warn: cannot read {fp}: {e}", file=sys.stderr)
            continue
        for reviewer, counts, not_run in parse_finding_summary(text):
            s = stats.setdefault(
                reviewer,
                {"dispatched": 0, "with_findings": 0, "not_run": 0,
                 "total_findings": 0, "by_sev": [0, 0, 0, 0], "checkpoints": []},
            )
            if not_run:
                s["not_run"] += 1
                continue
            s["dispatched"] += 1
            total = sum(counts)
            if total > 0:
                s["with_findings"] += 1
            s["total_findings"] += total
            for i in range(4):
                s["by_sev"][i] += counts[i]
            s["checkpoints"].append(os.path.basename(fp))
    return files, stats


def main(argv):
    json_out = "--json" in argv
    dirs = [a for a in argv if not a.startswith("--")] or [
        os.path.join(".codearbiter", "checkpoints")
    ]
    files, stats = collect(dirs)

    if not files:
        print(f"No checkpoint documents found under: {', '.join(dirs)}", file=sys.stderr)
        return 1

    rows = []
    for reviewer, s in stats.items():
        disp = s["dispatched"]
        yield_pct = (s["with_findings"] / disp * 100) if disp else 0.0
        rows.append((reviewer, s, yield_pct))
    # Lowest yield first — best downgrade/tighten candidates at the top.
    rows.sort(key=lambda r: (r[2], r[1]["total_findings"]))

    if json_out:
        out = {
            "checkpoints_scanned": [os.path.basename(f) for f in files],
            "reviewers": [
                {
                    "reviewer": rv,
                    "dispatched": s["dispatched"],
                    "with_findings": s["with_findings"],
                    "not_run": s["not_run"],
                    "yield_pct": round(yp, 1),
                    "total_findings": s["total_findings"],
                    "by_severity": dict(zip([x.upper() for x in SEVERITIES], s["by_sev"])),
                }
                for rv, s, yp in rows
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"Reviewer dispatch-to-finding yield  ({len(files)} checkpoint(s) scanned)")
    print("Lowest yield first = best candidate for a tighter trigger (Step 4) / model downgrade (Step 2).\n")
    hdr = f"{'reviewer':<30} {'disp':>4} {'found':>5} {'yield':>6} {'tot':>4}  {'C/H/M/L'}"
    print(hdr)
    print("-" * len(hdr))
    for rv, s, yp in rows:
        chml = "/".join(str(x) for x in s["by_sev"])
        nr = f"  (not-run x{s['not_run']})" if s["not_run"] else ""
        print(f"{rv:<30} {s['dispatched']:>4} {s['with_findings']:>5} {yp:>5.0f}% {s['total_findings']:>4}  {chml}{nr}")
    print("\nNote: coverage is persisted checkpoint docs only; sprint Phase-4 reviews may")
    print("not write a checkpoint and can be undercounted. Treat as a pointer, not a census.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
