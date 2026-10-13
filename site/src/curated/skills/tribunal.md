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

## What it does

This is the deepest, most expensive review the project offers: convened rarely, on demand,
invoked through the tribunal command, and never required as a gate on ordinary work. One generic
reviewer agent serves thirteen lens cards. Applicable lenses review bounded evidence, and each
finding or cross-lens lead is saved as it is found. A deterministic inventory supplies mechanical
facts without running project code; model reasoning focuses on contracts, risks, and consequences.

## The lenses

Every dispatch is the same [`tribunal-lens-reviewer`](/reference/agents/tribunal-lens-reviewer/)
agent handed a per-lens assignment; the thirteen lens cards it executes are published under
[tribunal lenses](/reference/#tribunal-lenses), and the [tribunal command
page](/reference/commands/tribunal/) carries the full roster and each lens's concern. At most
five run concurrently; a lens whose concern doesn't exist in scope is skipped rather than run
for nothing. The roster includes [semantic-contract](/reference/tribunal-lenses/semantic-contract/)
for plausible but incorrect behavior and [change-closure](/reference/tribunal-lenses/change-closure/)
for incomplete propagation to consumers and shipped surfaces. Coverage and test-fidelity retain
their existing names and share verification-quality guidance.

## On disk

A run lives under `.codearbiter/reports/<run-id>/`. A fresh run receives a unique UTC
timestamp, scope label, and random suffix; it never overwrites an earlier run.

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

Resume depends on matching the reviewed source, scope, and evidence set. The binding covers HEAD,
staged and unstaged content, and selected untracked inputs; only the active run's own output is
excluded. Changed inputs require a fresh run. A run without a binding remains readable as history
but cannot resume as current evidence. Age alone neither authorizes nor prevents resume.

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

On hosts without fresh reviewer contexts, the report states limited verification independence.
Unverified serious claims remain visible and cannot be filed as confirmed fix work. Repository
content and tool output cannot grant execution or change the review's authority.

## Exits

The run leaves a regenerated report and, only on your explicit approval, a set of filed tracked
issues. Nothing is filed on silence. Approved findings land as GitHub issues, never as entries
on `open-tasks.md`, so a periodic-review finding survives a PR getting abandoned. It never edits,
refactors, or commits project code itself, and it never blocks a commit or a merge; a critical
finding here is a recommendation to fix, not a pipeline stop.
