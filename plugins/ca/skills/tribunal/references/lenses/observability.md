# observability — lens mandate

Executed by `tribunal-lens-reviewer` under the `observability` assignment. Write contract + evidence discipline: `finding-record.md`.

## Scope emphasis
The assigned path slice, weighted to critical paths and boundaries.

## Required reading
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — logging/tracing/metrics stack; `inventory.md` in the run dir — the boundary map.

## Checklist
- Missing or inconsistent structured logging on critical paths.
- Absent tracing / correlation IDs across service or async boundaries.
- No metrics on critical paths; audit-trail gaps for security-relevant events.
- Sensitive-data-in-logs is flagged once, by the secrets lens — do not double-report it here.

## Exposure
Count of boundary crossings / critical paths inspected (`inventory.md` boundary map).

## Out of scope
Whether the logged operation is itself correct (reliability).
