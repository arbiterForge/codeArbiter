# /adr-status [--adr N]

## Purpose

Report the health of Architecture Decision Records. Invokes the `decision-lifecycle` skill health scan mode. Identifies aged decisions, unchallenged ADRs, supersession candidates, and unresolved `[CONFIRM-NN]` placeholders. Read-only — no files are modified.

## Usage

```
/adr-status            # scans all ADRs in ${PROJECT_ROOT}/.agents/projectContext/decisions/
/adr-status --adr 4    # focuses the scan on ADR-0004 specifically
```

## Routes To

`decision-lifecycle` skill (`${FRAMEWORK_ROOT}/.agents/skills/decision-lifecycle/SKILL.md`) — health scan mode.

## What Happens Step by Step

1. `decision-lifecycle` skill reads `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` for the full ADR index
2. For each ADR (or the targeted ADR if `--adr N` supplied):
   - **Age check** — flag if last status change or authoring date is older than 12 weeks without an accepted status
   - **Challenge check** — flag if status is `proposed` but the ADR has never been through a `/checkpoint` challenge
   - **Supersession check** — flag if a newer ADR or code pattern contradicts the decision in this ADR
   - **CONFIRM-NN check** — flag any `[CONFIRM-NN]` placeholders that remain unresolved
3. Results aggregated into a structured report
4. Report presented to user — no state is changed

## Output Structure

```
## ADR Health Report — YYYY-MM-DD

### Aged (> 12 weeks without status change)
- ADR-NNNN — <title> — last updated <date>

### Unchallenged (proposed but never through a checkpoint)
- ADR-NNNN — <title> — authored <date>

### Supersession candidates (code or newer ADR contradicts this decision)
- ADR-NNNN — <title> — evidence: <brief description>

### Unresolved CONFIRM-NN placeholders
- ADR-NNNN — [CONFIRM-NN]: <placeholder text>

### Clean
- ADR-NNNN — <title> — accepted, challenged, no open placeholders
```

## Hard Gates

- MUST NOT resolve any `[CONFIRM-NN]` placeholder found during the scan — surface it, stop
- Read-only — no file is modified
- If a supersession candidate is identified and it contradicts an accepted ADR: flag for `/surface-conflict`

## When NOT to Use

- To create a new ADR: use `/adr`
- To challenge a specific ADR in depth: use `/checkpoint` (invokes `decision-challenger`)
- To ask what a specific ADR says: use `/btw`
