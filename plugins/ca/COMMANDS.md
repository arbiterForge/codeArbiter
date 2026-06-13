# codeArbiter — commands

All user intent flows through these commands. A direct instruction outside a command channel gets a
redirect to the closest command (see the §6 redirect). The plugin is named `ca`; every command is
namespaced — invoke `/ca:<name>`.

This table is the surface scan. A command body (`${CLAUDE_PLUGIN_ROOT}/commands/<name>.md`) loads
ONLY when that command is invoked — never bulk-read the directory.

## Implementation

| Command | Argument | Purpose |
|---|---|---|
| `/ca:feature` | `"description"` | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. The only path to implementation. |
| `/ca:sprint` | `["goal"] [--farm]` | Autonomous sprint: one interactive spec gate, then plan-to-PR execution; every auto-decision SMARTS-scored and logged with a confidence flag. Hard gates still stop. |
| `/ca:fix` | `"bug description"` | Fix a defect via `tdd`, regression-test-first. |
| `/ca:refactor` | `"surface and motivation"` | Behavior-preserving restructure behind a parity-coverage gate. |
| `/ca:debug` | `"symptom"` | Investigate-then-decide root-cause analysis; exits to `/ca:fix`, `/ca:adr`, or a no-action close. |
| `/ca:chore` | `<docs\|deps\|revert> …` | Non-behavioral lane: docs edits, dependency bumps, reverts — type-scaled gates, no TDD demanded of prose. |
| `/ca:spike` | `"question" [timebox]` | Throwaway exploration on a `spike/*` branch. Never merges; exits to a findings note or `/ca:feature`. |

## Commit & ship

| Command | Argument | Purpose |
|---|---|---|
| `/ca:commit` | _(none)_ | The only path to a commit; routes to `commit-gate` (nine gates). |
| `/ca:pr` | `["title"]` | Finish a branch: open-PR / merge-via-PR / discard. No direct-to-default. |
| `/ca:watch` | `<PR number\|url\|branch>` | Babysit a PR's CI server-side: diagnose on red, notify + offer the merge on green. Never auto-merges. Auto-attaches from `/ca:pr` when `CODEARBITER_BABYSIT` is on. |
| `/ca:review` | `[path or scope]` | Dispatch the reviewer fleet over the diff; BLOCK on CRITICAL/HIGH. |
| `/ca:checkpoint` | `[focus]` | Lean periodic reviewer sweep; surfaces a triaged report. |
| `/ca:release` | `[--dry-run]` | Lean SemVer release: bump-from-commits + changelog + annotated tag. |
| `/ca:add-dep` | `"package"` | Vet a dependency (license, provenance, supply chain) before install. |

## Decisions

| Command | Argument | Purpose |
|---|---|---|
| `/ca:adr` | `"title"` | Author a numbered, user-attributed ADR. |
| `/ca:adr-status` | `[--adr N]` | List/inspect ADR status and supersede chains. |
| `/ca:reconcile` | `["scope"]` | Reconcile artifacts vs. scaffold; arbitrate via SMARTS, user-attributed. |
| `/ca:conflict` | `"description"` | Stop all work and surface a rule conflict. |
| `/ca:threat-model` | `"scope"` | Optional lightweight STRIDE pass for a sensitive feature. |

Which one? `/ca:conflict` when two *rules* contradict (persona vs. docs vs. code) and work cannot
safely continue — it halts everything. `/ca:reconcile` when *artifacts* have drifted (ADRs, scaffold,
context docs disagree about the architecture) and you want each variance arbitrated — work continues.

## Project & meta

| Command | Argument | Purpose |
|---|---|---|
| `/ca:decompose` | _(none)_ | Greenfield: layered interview to populate `.codearbiter/`. |
| `/ca:create-context` | _(none)_ | Brownfield: back-fill `.codearbiter/` from existing source. |
| `/ca:init` | `[--stage N]` | Scaffold the root-level `.codearbiter/` state store. |
| `/ca:status` | _(none)_ | Show maturity, open tasks, unresolved `CONFIRM-NN`, overrides since checkpoint. |
| `/ca:audit` | `[range]` | Assemble the governance packet for a window — commits, overrides, ADRs, sprint decisions, open items — into `.codearbiter/audits/`. Read-only. |
| `/ca:statusline` | `[--check]` | Install/wire the codeArbiter statusline. |
| `/ca:prune` | `status \| dry \| run <path> \| audit <path> \| on \| off` | Trim transcript clutter to extend session lifetime. Dry-run by default; gains land on resume/compaction, not the live turn. |
| `/ca:doctor` | _(none)_ | Verify the install is enforcing: interpreter, payload, cache staleness, repo state, live-fire hook probe. |
| `/ca:standup` | _(none)_ | Daily hygiene: review repo state, then ff-only pull / prune merged branches / remove stale worktrees / surface stashes — each under per-action confirmation. |
| `/ca:new-skill` | `"gap"` | Author a new skill after the gap is proven uncovered. |
| `/ca:btw` | `"question"` | Lightweight Q&A; no state change. |
| `/ca:override` | `"reason"` | Sanctioned, logged single-identity gate bypass. |
| `/ca:commands` | _(none)_ | Show this catalog. |

## Maintainer

| Command | Argument | Purpose |
|---|---|---|
| `/ca:dev` | `["note"]` | Suspend orchestration to edit codeArbiter itself. Requires `CODEARBITER_DEV=1`; entry/exit logged to `overrides.log`. |
| `/ca:arbiter` | _(none)_ | Exit dev mode: restore orchestration, log the exit. |

## Glossary — the words the gates speak

- **stage** — the project's maturity, a single number in `.codearbiter/CONTEXT.md`; higher stages
  demand stricter coverage and review.
- **skill** — a gated routine a command routes to (e.g. `tdd`, `commit-gate`).
- **phase** — one step inside a skill; each ends in a gate.
- **gate** — a phase exit condition. **STOP** waits for you; **BLOCK** halts until the condition is met.
- **severity** — a review finding's class (CRITICAL/HIGH/MEDIUM/LOW), independent of gate action.
- **`[CONFIRM-NN]`** — a numbered open question only you can answer; dependent work pauses until
  it is resolved in `.codearbiter/open-questions.md`.
- **SMARTS** — the six-lens scoring rubric used to arbitrate decisions; every arbitration is
  attributed to you, never decided silently.
- **ADR** — an Architecture Decision Record under `.codearbiter/decisions/`, authored only via `/ca:adr`.
