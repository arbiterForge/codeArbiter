---
name: decision-lifecycle
description: Author and track Architecture Decision Records. Routed to when the user invokes /adr to record a new decision or /adr-status to list ADR health. Authors numbered, dated, user-attributed ADRs under .codearbiter/decisions/, maintains supersede chains, and reports status read-only. Never authors an ADR as its own judgment — every ADR carries explicit user attribution.
---

# decision-lifecycle

Author and track ADRs. Routed to when the user invokes `/adr "<title>"` (author a new ADR) or `/adr-status [--adr N]` (list ADR health, read-only). Every ADR is user-attributed — this skill never records a decision the user did not explicitly make.

The append-only decision-log format (entry fields, supersession protocol) lives in `${CLAUDE_PLUGIN_ROOT}/skills/decision-variance/references/smarts.md`. Read it before writing a log line; do not restate it here.

## Pre-flight

Read these, or STOP and surface the gap — never guess a path:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/` — the ADR directory and existing records. Create it on first `/adr` if absent.
- For `/adr`: confirm the user explicitly authorized this decision and supplied (or confirmed) its content. An ADR is never authored as the disposition of a routine finding.

## Phase 1 — Index · gate: BLOCK

Scan `${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/` for existing `NNNN-*.md` ADR files. Record each by number, title, and status. Determine the next sequential number (no gaps) for `/adr`; for `/adr-status` this is the working set.

Gate: the existing ADRs are indexed and, for `/adr`, the next number is fixed.

## Phase 2 — Author (/adr) · gate: STOP

Confirm the decision content with the user — context, the decision itself, alternatives, consequences. MUST NOT fill these from inference. Surface any unknown as an inline `[CONFIRM-NN]` placeholder; do not resolve it by guessing.

**Drop the authoring marker first.** The `pre-write`/`pre-edit` hooks block any write to `.codearbiter/decisions/NNNN-*.md` unless a fresh authoring marker is present — that block is the mechanism enforcing "ADRs only via `/adr`" (ORCHESTRATOR §3), so the sanctioned path must arm it itself. Immediately before writing, create the marker at the path the hooks check (project root = git top level):

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.codearbiter/.markers"
touch "$(git rev-parse --show-toplevel)/.codearbiter/.markers/adr-authoring-active"
```

The marker is honored for 30 minutes. Then write `${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/NNNN-<slug>.md` using the template below. If this decision supersedes an existing one, set `supersedes:` to that ADR's number; leave the prior ADR's file untouched (forward-only chain — do not edit it to add a back-reference).

```markdown
---
status: proposed
date: YYYY-MM-DD
title: <title>
decided-by: <user identifier>
supersedes: NNNN | none
---

# ADR-NNNN — <title>

## Status
Proposed

## Context
<What situation, constraint, or requirement prompted this decision?>

## Decision
<What was decided. One clear statement.>

## Alternatives considered
- **<Option A>** — <why not chosen>
- **<Option B>** — <why not chosen>

## Consequences
<What becomes easier or harder as a result.>

## Risks
<What could go wrong; what would prove this decision wrong.>
```

After writing the ADR, append a corresponding entry to the decision log per the format in `${CLAUDE_PLUGIN_ROOT}/skills/decision-variance/references/smarts.md` — `Decided by:` names the user. Status transitions (`proposed → accepted → superseded | rejected`) require explicit user instruction; never advance status on this skill's own judgment.

Once the ADR file and its log entry are written (and any user-instructed status edit is applied), remove the marker — it exists only for one authoring pass:

```bash
rm -f "$(git rev-parse --show-toplevel)/.codearbiter/.markers/adr-authoring-active"
```

Gate: the ADR file is written with a real `decided-by` user attribution, numbered without a gap, and its log entry is appended. An ADR with no user attribution, or authored as the disposition of a finding, does not pass — STOP.

## Phase 3 — Status (/adr-status) · gate: BLOCK

Read-only. For each ADR (or the `--adr N` target), report: number, title, status, date, and supersession state — found by scanning forward for any later ADR whose `supersedes:` names it. Surface every unresolved `[CONFIRM-NN]` placeholder found in any ADR; MUST NOT resolve it.

If a supersession candidate contradicts an `accepted` ADR with no clear direction, do not pick one — flag it for `/surface-conflict`.

```
## ADR Status — YYYY-MM-DD

### Active
- ADR-NNNN — <title> — <status> (<date>)

### Superseded
- ADR-NNNN — <title> — superseded by ADR-MMMM

### Unresolved CONFIRM-NN
- ADR-NNNN — [CONFIRM-NN]: <text>
```

An empty section is marked "None" — not omitted. MAY dispatch `decision-challenger` (`${CLAUDE_PLUGIN_ROOT}/agents/decision-challenger.md`) to stress-test an ADR; optional, never forced.

Gate: every indexed ADR appears with its current status and supersession state; no `[CONFIRM-NN]` resolved; no file modified.

## Hard rules

- MUST author an ADR only via `/adr` with explicit user attribution. MUST NOT author an ADR as the disposition of a routine finding — an out-of-scope finding gets an inline `[NEEDS-TRIAGE]` marker instead.
- MUST NOT record a decision the user did not explicitly make. "Use your best judgment," "I trust you" are declined.
- MUST NOT resolve a `[CONFIRM-NN]` placeholder by guessing. Surface it and stop.
- MUST NOT advance an ADR's status without explicit user instruction.
- MUST NOT edit a prior ADR or a prior decision-log entry to add a back-reference — supersession is a forward-only chain; append a new record whose `supersedes:` names the prior one.
- MUST NOT number an ADR with a gap.
- MUST NOT modify any file under `/adr-status` — it is read-only.
- MUST NOT force the `decision-challenger` agent — its dispatch is MAY only.
