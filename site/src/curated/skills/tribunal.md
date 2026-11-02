---
entity: skills/tribunal
related: [commands/tribunal]
gates:
  - gate: cost acknowledgment
    when: before anything is dispatched
    effect: you must acknowledge the estimated token cost and confirm the model before the run proceeds; an unacknowledged run does not start
  - gate: approval and filing
    when: after the report is presented
    effect: findings become tracked issues only on your explicit selection; silence or a vague "looks good" files nothing
---

## On disk

A run lives under `.codearbiter/reports/<run-id>/`.

- `source.json`: the exact source binding checked before review and resume.
- `findings/<lens>/<finding-id>.json`: one file per finding, written the instant it's found.
- `pending-leads/` and `leads/`: saved cross-lens observations and their imported records.
- `lead-dispositions.jsonl`: why each lead was promoted, dismissed, or deferred.
- `verification/`: separate attempts to confirm, narrow, refute, or leave a claim inconclusive.
- `run.jsonl` and `triage.jsonl`: append-only logs; nothing here is ever hand-edited.
- `inventory.json` and `inventory.md`: deterministic facts and their readable projection.
- `risk-map.json`: review priorities, applicable lenses, and bounded evidence packets.
- `plans/phase-<n>.md`: one plan file per wave's kept work.
- `report.md` and `manifest.yaml`: regenerated from the durable records.
- `issue-commands.sh`: the default hand-off, a ready command set executed only on explicit approval.

The source binding covers HEAD, staged and unstaged content, and selected untracked inputs; only
the active run's own output is excluded.

## Phases

1. Check any prior source binding, collect deterministic facts, estimate the selected work, and
   obtain your cost acknowledgment and supported model settings before reviewers start.
2. Save the source binding, inventory, review priorities, and evidence packet for each active lens.
   Record why each remaining lens was skipped.
3. Review in bounded waves, saving findings and leads as they appear. Evidence may include declared
   callers or contracts outside a subtree without widening the finding scope.
4. Give every critical/high claim and expensive inferential recommendation a separate verification
   attempt, then group related findings by root cause and calibrate impact and confidence.
5. Regenerate the report with verified defects, verification-required items, design decisions,
   investigations, coverage, and limitations. Only eligible kept work enters fix plans.
6. Complete or explicitly skip issue filing, then complete or explicitly skip optional telemetry.
   Each action keeps its own consent; producing a report authorizes neither.
7. Record `run-completed` only after both follow-ups have a disposition. A disconnect after
   `report-written` resumes pending follow-ups after the source check, without repeating the audit.

Unverified serious claims cannot be filed as confirmed fix work.

## Exits

Approved findings land as GitHub issues, never as entries on `open-tasks.md`, so a
periodic-review finding survives a PR getting abandoned. The run never edits, refactors, or commits
project code itself.
