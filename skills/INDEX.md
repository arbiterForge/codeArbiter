# skills — catalog (surface scan)

Skill bodies load on routing only. This index is the surface scan; never bulk-read
`skills/*/SKILL.md`. Each skill is an orchestrator routine with gated phases — routed to, never
"triggered."

| Skill | Routed to by | Owns |
|---|---|---|
| [tdd](tdd/SKILL.md) | `/feature` (after spec approval), `/fix`, `/refactor` | The test-first gate: six phases — obligation scan → red → green → obligation verify → coverage → lint. No implementation before Phase 1; no path to `commit-gate` until all six gates are green. |
| [commit-gate](commit-gate/SKILL.md) | `/commit` | The commit gate: nine phases — permission, branch, classification, verification, behavioral proof, diff review, selective stage, message, commit. No commit while the suite is red, the behavior unproven, or secrets/cruft present. |
| [decision-variance](decision-variance/SKILL.md) | `/decision-variance` | SMARTS 6-lens arbitration of project/ADR conflicts; append-only, user-attributed decision log + audit trail. Never decides alone — every choice carries user attribution. |
| [debug](debug/SKILL.md) | `/debug` | Investigate-then-decide root-cause analysis: five phases. Investigation only, no code change here; forces one named exit — `/fix`, `/adr`, or a no-action close. |
| [refactor](refactor/SKILL.md) | `/refactor` | Behavior-preserving change behind a parity-coverage proof gate; routes to `tdd` Phase 1 only when new test seams are needed. |
| [context-creation](context-creation/SKILL.md) | `/create-context` (brownfield) | Back-fills `.codearbiter/` from existing source via parallel scouts; writes `CONTEXT.md` (`arbiter: enabled` + `stage:`) and locks it `<!--INITIALIZED-->`. |
| [decompose](decompose/SKILL.md) | greenfield startup, `/decompose` | Six-layer senior-architect interview, compaction-resilient via per-layer disk drafts + DRAFT ADRs; populates `.codearbiter/` and locks it initialized. |
| [brainstorming](brainstorming/SKILL.md) | `/feature` (front), `/sprint` planning | Socratic idea→spec: one question at a time, challenge vagueness, force trade-offs; writes `specs/<slug>.md` whose acceptance criteria become `tdd` obligations. Hard-gate: no code until the spec is approved. |
| [writing-plans](writing-plans/SKILL.md) | `/feature`, `/sprint` (after the spec) | Decomposes an approved spec into small tasks, each with a path + a verification that maps to a `tdd` obligation; writes `plans/<slug>.md` with bijective criterion↔task coverage. |
| [executing-plans](executing-plans/SKILL.md) | `/feature` | Inline, checkpointed execution of a plan — each task through `tdd`, proven by a fresh run, with a human checkpoint between batches. The non-autonomous counterpart to `subagent-driven-development`. |
| [subagent-driven-development](subagent-driven-development/SKILL.md) | `/sprint` (engine), optionally `/feature` | Fresh subagent per task → spec-compliance then quality review → fresh-run verification; accepts only on proof. Hard-stops on `tdd` BLOCK, security CRITICAL, `[CONFIRM-NN]`. |
| [dispatching-parallel-agents](dispatching-parallel-agents/SKILL.md) | `subagent-driven-development`, `/sprint`, parallel `/review` | Reusable fan-out primitive: bound concurrency, collect, dedupe, funnel through `finding-triage`→`checkpoint-aggregator`. Results unused until the funnel runs. |
| [finishing-a-development-branch](finishing-a-development-branch/SKILL.md) | `/feature`, `/sprint` (terminal) | The terminal step after `commit-gate`: open-PR / merge-via-PR / discard. No direct-to-main, no force-push; `/sprint` auto-selects open-PR and never merges. |
| [using-git-worktrees](using-git-worktrees/SKILL.md) | `subagent-driven-development`, `dispatching-parallel-agents` (opt-in) | OPTIONAL per-unit filesystem isolation for parallel work; integrates accepted units back onto the caller's working branch for its single `commit-gate` + finish. Never the default path. |
