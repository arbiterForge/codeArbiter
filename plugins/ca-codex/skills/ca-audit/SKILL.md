---
name: ca-audit
description: Assemble the governance record for a range — commits, overrides, ADRs, sprint auto-decisions, open questions, checkpoint findings — into one dated audit packet. Read-only.
argument-hint: "[<from-ref> <to-ref> | --since-checkpoint | --since <date>]"
---

# $ca-audit — promotion packet

Everything codeArbiter logs, it logs append-only and scattered: `overrides.log`, `triage.log`,
`decisions/`, `sprint-log.md`, `checkpoints/`. This command assembles them into the one document a
team lead, compliance reviewer, or auditor actually asks for: *what happened in this window, who
authorized it, and what is still open.* Read-only over every source; its only write is the packet.

## Window

- `<from-ref> <to-ref>` — two tags/SHAs (e.g. `v1.2.0 v1.3.0`).
- `--since-checkpoint` — use `source_commit` and `recorded_at` from the latest checkpoint report under `.codearbiter/checkpoints/` as the commit and UTC time anchors.
- `--since <date>` — ISO date to HEAD.
- No argument → from the most recent tag to HEAD (no tags → last checkpoint; neither → BLOCK and
  ask for an explicit window).

## Flow

1. Resolve the window to a commit range and a time range; both appear in the packet header. For a checkpoint window, select the report with the latest valid `recorded_at`, verify its `source_commit` resolves to a commit and is an ancestor of HEAD, and cite the report. Include its `worktree_dirty` value as a review-scope limitation. Missing or invalid anchors require an explicit ref/date window; never infer one from the report filename or the integer override counter in `last-checkpoint`.
2. Gather, citing each source file:
   - **Commits** — `git log` over the range, grouped by Conventional-Commit type; merge commits
     listed with their PR reference.
   - **Overrides** — every `overrides.log` line in the time range, verbatim (including
     `SECURITY-OVERRIDE` and `DEV:` entries), each with its `BY:` identity.
   - **Triage** — every small-lane classification in `triage.log` in range.
   - **Decisions** — ADRs created or superseded in range (from `decisions/` file dates and the
     supersede chains), each with its Decided-by attribution.
   - **Sprint auto-decisions** — entries from `sprint-log.md` in range; list every `low`-confidence
     entry verbatim, count the `high` ones.
   - **Open questions** — all currently-unresolved `[CONFIRM-NN]` items.
   - **Checkpoint findings** — from the most recent `checkpoints/*.md`: findings still open.
3. Write the packet to `<project-root>/.codearbiter/audits/<YYYY-MM-DD>.md` (second run the
   same day appends `-2`, `-3`, … — an existing packet is never overwritten). Surface the path and
   a three-line summary: commits, overrides, open items.

## Hard gate

Read-only over every source — MUST NOT modify any log, decision, or checkpoint while assembling.
MUST NOT overwrite an existing packet. MUST quote override and low-confidence sprint entries
verbatim — never paraphrase an audit line. An empty section is stated as empty, never omitted —
"no overrides in window" is itself the finding.

## When NOT to use

- Live project state right now → `$ca-status`.
- Triggering reviews → `$ca-checkpoint` (this command only reports what reviews already found).
