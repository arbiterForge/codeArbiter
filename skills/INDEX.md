# skills — catalog (surface scan)

Skill bodies load on routing only. This index is the surface scan; never bulk-read
`skills/*/SKILL.md`. Each skill is an orchestrator routine with gated phases — routed to, never
"triggered."

| Skill | Routed to by | Owns |
|---|---|---|
| [tdd](tdd/SKILL.md) | `/feature` (after spec approval), `/fix`, `/refactor` | The test-first gate: six phases — obligation scan → red → green → obligation verify → coverage → lint. No implementation before Phase 1; no path to `commit-gate` until all six gates are green. |
