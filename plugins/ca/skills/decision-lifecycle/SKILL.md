---
name: decision-lifecycle
description: Author and track Architecture Decision Records. Routed to when the user invokes /adr to record a new decision or /adr-status to list ADR health. Authors numbered, dated, user-attributed ADRs under .codearbiter/decisions/, maintains supersede chains, and reports status read-only. Never authors an ADR as its own judgment — every ADR carries explicit user attribution.
---

# decision-lifecycle

Author and track ADRs. Routed to when the user invokes `/adr "<title>"` (author a new ADR) or `/adr-status [--adr N]` (list ADR health, read-only).

The append-only decision-log format (entry fields, supersession protocol) lives in `${CLAUDE_PLUGIN_ROOT}/includes/smarts/decision-log-format.md`. Read it before writing a log line; do not restate it here.

**Boundary with `decision-variance`.** A decision that needs *making* — competing options, variance detection, SMARTS scoring, the decision log itself — routes to `decision-variance`; recording a decision already made, and reporting ADR health, is this skill. The two share the canonical SMARTS reference under `${CLAUDE_PLUGIN_ROOT}/includes/smarts/` and one ADR template (`references/adr-template.md`).

## Pre-flight

Read these, or STOP and surface the gap — never guess a path:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/` — the ADR directory and existing records. Create it on first `/adr` if absent.
- For `/adr`: confirm the user explicitly authorized this decision and supplied (or confirmed) its content.

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

The marker is honored for 30 minutes. Then write `${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/NNNN-<slug>.md` using the canonical ADR template — `${CLAUDE_PLUGIN_ROOT}/skills/decision-lifecycle/references/adr-template.md` (the single source of truth for the ADR shape, shared with `decompose`). Author it with `status: proposed`. If this decision supersedes an existing one, set `supersedes:` to that ADR's number; leave the prior ADR's file untouched (forward-only chain — do not edit it to add a back-reference).

After writing the ADR, append a corresponding entry to the decision log per the format in `${CLAUDE_PLUGIN_ROOT}/includes/smarts/decision-log-format.md` — `Decided by:` names the user. Status transitions (`proposed → accepted → superseded | rejected`) require explicit user instruction; never advance status on this skill's own judgment.

**`governs:` makes the decision live.** When an ADR names path globs in `governs:`, the post-write
hook surfaces a one-line notice on any Write/Edit touching a matching file — "this file is governed
by ADR-NNNN" — so a recorded decision pushes back at edit time instead of waiting for a checkpoint
sweep. Offer the field whenever a decision constrains identifiable files; omit it for decisions
without a file footprint. Globs are fnmatch-style against repo-relative forward-slash paths.

Once the ADR file and its log entry are written (and any user-instructed status edit is applied), remove the marker — it exists only for one authoring pass:

```bash
rm -f "$(git rev-parse --show-toplevel)/.codearbiter/.markers/adr-authoring-active"
```

Gate: the ADR file is written with a real `decided-by` user attribution, numbered without a gap, and its log entry is appended. An ADR with no user attribution, or authored as the disposition of a finding, does not pass — STOP.

## Phase 3 — Status (/adr-status) · gate: BLOCK

Read-only. For each ADR (or the `--adr N` target), report: number, title, status, date, and supersession state — found by scanning forward for any later ADR whose `supersedes:` names it. Surface every unresolved `[CONFIRM-NN]` placeholder found in any ADR; MUST NOT resolve it.

If a supersession candidate contradicts an `accepted` ADR with no clear direction, do not pick one — flag it for `/conflict`.

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

- MUST clear every phase gate; a skipped phase is a hard-rule violation.
- MUST NOT record a decision the user did not explicitly make — "use your best judgment," "I trust you" are declined; an out-of-scope finding gets an inline `[NEEDS-TRIAGE]` marker, never an ADR of its own.
- MUST NOT edit a prior ADR or a prior decision-log entry to add a back-reference — supersession is a forward-only chain; append a new record whose `supersedes:` names the prior one.
