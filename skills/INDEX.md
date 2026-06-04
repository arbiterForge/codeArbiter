# skills — catalog (surface scan)

Skill bodies load on routing only. This index is the surface scan; never bulk-read
`skills/*/SKILL.md`. Each skill is an orchestrator routine with gated phases — routed to, never
"triggered."

| Skill | Routed to by | Owns |
|---|---|---|
| [tdd](tdd/SKILL.md) | `/feature` (after spec approval), `/fix`, `/refactor` | The test-first gate: six phases — obligation scan → red → green → obligation verify → coverage → lint. No implementation before Phase 1; no path to `commit-gate` until all six gates are green. |
| [commit-gate](commit-gate/SKILL.md) | `/commit` | The commit gate: eight phases — permission, branch, classification, verification, diff review, selective stage, message, commit. No commit while the suite is red or secrets/cruft are present. |
| [decision-variance](decision-variance/SKILL.md) | `/decision-variance` | SMARTS 6-lens arbitration of project/ADR conflicts; append-only, user-attributed decision log + audit trail. Never decides alone — every choice carries user attribution. |
| [debug](debug/SKILL.md) | `/debug` | Investigate-then-decide root-cause analysis: five phases. Investigation only, no code change here; forces one named exit — `/fix`, `/adr`, or a no-action close. |
| [refactor](refactor/SKILL.md) | `/refactor` | Behavior-preserving change behind a parity-coverage proof gate; routes to `tdd` Phase 1 only when new test seams are needed. |
| [context-creation](context-creation/SKILL.md) | `/create-context` (brownfield) | Back-fills `.codearbiter/` from existing source via parallel scouts; writes `CONTEXT.md` (`arbiter: enabled` + `stage:`) and locks it `<!--INITIALIZED-->`. |
| [decompose](decompose/SKILL.md) | greenfield startup, `/decompose` | Six-layer senior-architect interview, compaction-resilient via per-layer disk drafts + DRAFT ADRs; populates `.codearbiter/` and locks it initialized. |
