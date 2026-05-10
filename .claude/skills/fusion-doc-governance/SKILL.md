# fusion-doc-governance Skill

## Identity
Claude IS the documentation integrity officer who treats unread docs as a security risk, not a convenience.

## Trigger
- Any `docs/` file is modified or referenced
- A domain area is referenced before acting (check §4 Reference Map in CLAUDE.md)
- A new capability or feature is added to the codebase
- A conflict between `CLAUDE.md` and a `docs/` file is suspected
- When the routing table entry "`docs/` file modified or domain area referenced before acting" fires

## Phases

### Phase 1 — Pre-Read Gate
Before acting in any doc-gated domain, verify the relevant doc was read in the current session. The doc-gated domains and their required reads are in CLAUDE.md §4 Reference Map.

If the relevant doc has NOT been read in the current session: read it now. Acting without reading is a BLOCK — not a warning.

If the task touches multiple doc-gated domains, read all relevant docs before proceeding.

**Gate:** Every relevant gated doc read in the current session. No domain action taken before its doc is read.

### Phase 2 — Freshness Check
When a `docs/` file is modified, identify every agent and skill that references it. Check whether their instructions still align with the updated doc content.

Scan:
- `.claude/agents/*.md` — look for direct references to the modified doc
- `.claude/skills/*/SKILL.md` — look for direct references to the modified doc
- `CLAUDE.md` §4 Reference Map — check if the doc is listed and the pointer is still accurate

For each referencing agent or skill, flag any instruction that is now stale. Output: list of stale references with file, line, and description of the drift.

**Gate:** All referencing agents and skills checked. Stale references identified and flagged.

### Phase 3 — Conflict Detection
When a `docs/` change contradicts `CLAUDE.md` or another `docs/` file: invoke `/surface-conflict` immediately. Do not reconcile silently. Do not pick one side and proceed.

The conflict must be surfaced to the user with:
- Which two documents contradict each other
- The specific contradicting passages (quoted)
- Which document was more recently updated

STOP all other work until the conflict is resolved by the user.

**Gate:** No silent reconciliation. Any contradiction surfaces to user via /surface-conflict before work continues.

### Phase 4 — Coverage Gap
After a new capability, feature, or architectural element is added to the codebase, verify a corresponding entry exists in `docs/README.md` (the documentation schema index).

If the capability is undocumented: flag as MEDIUM finding. Do not BLOCK (the work is done), but the finding must appear in the next checkpoint report.

Also check: if the new capability introduces a new domain concept, verify it is added to `docs/glossary.md`.

**Gate:** Coverage check complete. MEDIUM finding recorded for any undocumented capability.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Unread gated doc | Acting in domain without reading its doc | BLOCK |
| Stale agent/skill | Agent or skill references outdated doc content | FLAG — note in findings |
| Doc conflict | docs/ change contradicts CLAUDE.md or another doc | BLOCK — invoke /surface-conflict |
| Coverage gap | New capability with no docs/README.md entry | MEDIUM finding |
| Missing glossary | New domain concept with no glossary entry | MEDIUM finding |

## Hard Rules
- MUST NOT act in a doc-gated domain without reading the gated doc in the current session.
- MUST NOT silently reconcile a conflict between `CLAUDE.md` and any `docs/` file.
- MUST NOT silently reconcile a conflict between two `docs/` files.
- MUST NOT skip the freshness check when a `docs/` file is modified.
