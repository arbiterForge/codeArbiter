# observability — lens mandate

Executed by `tribunal-observability-reviewer`. Write contract + evidence discipline: `finding-record.md`.

## Checklist
- Missing or inconsistent structured logging on critical paths.
- Absent tracing / correlation IDs across service or async boundaries.
- No metrics on critical paths; audit-trail gaps for security-relevant events.
- Sensitive-data-in-logs is flagged once, by the secrets lens — do not double-report it here.

## Exposure
Count of boundary crossings / critical paths inspected (`inventory.md` boundary map).

## Out of scope
Whether the logged operation is itself correct (reliability).
