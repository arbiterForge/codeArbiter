# codeArbiter — commands

All user intent flows through these commands. A direct instruction outside a command channel gets a
redirect to the closest command (see the §6 redirect). {{IF:claude}}The plugin is named `ca`; every command is
namespaced — invoke `/ca:<name>`.{{ELSE}}Every command ships as a `ca-`-prefixed
skill — invoke `$ca-<name>`.{{END}}

This table is the surface scan. A command body ({{IF:claude}}`{{PLUGIN_ROOT}}/commands/<name>.md`{{ELSE}}`{{PLUGIN_ROOT}}/skills/ca-<name>/SKILL.md`{{END}}) loads
ONLY when that command is invoked — never bulk-read the directory.

## Implementation

| Command | Argument | Purpose |
|---|---|---|
| `{{CMD:feature}}` | `"description"` | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. The only path to implementation. |
| `{{CMD:sprint}}` | `["goal"] [--farm]` | Autonomous sprint: one interactive spec gate, then plan-to-PR execution; every auto-decision SMARTS-scored and logged with a confidence flag. Hard gates still stop. `--farm` is a Feature Forge `preview` (off by default, needs `FARM_API_KEY`; not yet validated). |
| `{{CMD:fix}}` | `"bug description"` | Fix a defect via `tdd`, regression-test-first. |
| `{{CMD:refactor}}` | `"surface and motivation"` | Behavior-preserving restructure behind a parity-coverage gate. |
| `{{CMD:debug}}` | `"symptom"` | Investigate-then-decide root-cause analysis; exits to `{{CMD:fix}}`, `{{CMD:adr}}`, or a no-action close. |
| `{{CMD:chore}}` | `<docs\|deps\|revert> …` | Non-behavioral lane: docs edits, dependency bumps, reverts — type-scaled gates, no TDD demanded of prose. |
| `{{CMD:spike}}` | `"question" [timebox]` | Throwaway exploration on a `spike/*` branch. Never merges; exits to a findings note or `{{CMD:feature}}`. |

## Commit & ship

| Command | Argument | Purpose |
|---|---|---|
| `{{CMD:commit}}` | _(none)_ | The only path to a commit; routes to `commit-gate` (nine gates). |
| `{{CMD:pr}}` | `["title"]` | Finish a branch: open-PR / merge-via-PR / discard. No direct-to-default. |
| `{{CMD:watch}}` | `<PR number\|url\|branch>` | Babysit a PR's CI server-side: diagnose on red, notify + offer the merge on green. Never auto-merges. Auto-attaches from `{{CMD:pr}}` when `CODEARBITER_BABYSIT` is on. |
| `{{CMD:review}}` | `[path or scope]` | Dispatch the reviewer fleet over the diff; BLOCK on CRITICAL/HIGH. |
| `{{CMD:checkpoint}}` | `[focus]` | Lean periodic reviewer sweep; surfaces a triaged report. |
| `{{CMD:tribunal}}` | `[scope-path] [--tag <label>]` | Deep, rarely-run whole-codebase audit across eleven specialist lenses; one file per finding plus append-only run/triage logs, resumable from disk; files GitHub issues on approval. Never a required gate. |
| `{{CMD:release}}` | `[--dry-run]` | Lean SemVer release: bump-from-commits + changelog + annotated tag. |
| `{{CMD:add-dep}}` | `"package"` | Vet a dependency (license, provenance, supply chain) before install. |

## Decisions

| Command | Argument | Purpose |
|---|---|---|
| `{{CMD:adr}}` | `"title"` | Author a numbered, user-attributed ADR. |
| `{{CMD:adr-status}}` | `[--adr N]` | List/inspect ADR status and supersede chains. |
| `{{CMD:reconcile}}` | `["scope"]` | Reconcile artifacts vs. scaffold; arbitrate via SMARTS, user-attributed. |
| `{{CMD:conflict}}` | `"description"` | Stop all work and surface a rule conflict. |
| `{{CMD:threat-model}}` | `"scope"` | Optional lightweight STRIDE pass for a sensitive feature. |

Which one? `{{CMD:conflict}}` when two *rules* contradict (persona vs. docs vs. code) and work cannot
safely continue — it halts everything. `{{CMD:reconcile}}` when *artifacts* have drifted (ADRs, scaffold,
context docs disagree about the architecture) and you want each variance arbitrated — work continues.

## Project & meta

| Command | Argument | Purpose |
|---|---|---|
| `{{CMD:decompose}}` | _(none)_ | Greenfield: layered interview to populate `.codearbiter/`. |
| `{{CMD:create-context}}` | _(none)_ | Brownfield: back-fill `.codearbiter/` from existing source. |
| `{{CMD:init}}` | `[--stage N \| --check]` | Scaffold the root-level `.codearbiter/` state store, or `--check` to report detection state without writing. |
| `{{CMD:status}}` | _(none)_ | Show maturity, open tasks, unresolved `CONFIRM-NN`, overrides since checkpoint. |
| `{{CMD:task}}` | `add "<desc>" \| start <id\|"title"> \| done <id\|"title">` | The sanctioned task-board writer: add a queued task, start one (flips to in-progress + stamps the date, minting a dotted ID on pick-up), or mark one done. The only blessed write to `open-tasks.md`. |
| `{{CMD:audit}}` | `[range]` | Assemble the governance packet for a window — commits, overrides, ADRs, sprint decisions, open items — into `.codearbiter/audits/`. Read-only. |
| `{{CMD:metrics}}` | `[--window N]` | Read-only governance trend glance: override rate, small-lane rate, sprint low-confidence ratio, each with a direction arrow vs. the prior 20-commit window. Not a second `{{CMD:audit}}` packet. |
{{IF:claude}}
| `{{CMD:statusline}}` | `install \| uninstall \| status` | Install/wire the codeArbiter statusline, remove it, or report its state. |
| `{{CMD:prune}}` | `status \| dry \| run <path> \| audit <path> \| on \| off` | Trim transcript clutter to extend session lifetime. Dry-run by default; gains land on resume/compaction, not the live turn. |
{{END}}
| `{{CMD:doctor}}` | _(none)_ | Verify the install is enforcing: interpreter, payload, cache staleness, repo state, live-fire hook probe. |
| `{{CMD:preview}}` | _(none)_ | Zero-onboarding read-only dry-run of the reviewer fleet on the current diff: predicts reviewers by path, runs the state-free secret scan, writes nothing. |
| `{{CMD:context-check}}` | _(none)_ | Optional manual drift audit: report stale provenance-tracked docs, then per stale doc offer re-scout, re-baseline, or defer. Not the daily loop — commit-gate auto-heal owns routine maintenance. |
| `{{CMD:standup}}` | _(none)_ | Daily hygiene: review repo state, then ff-only pull / prune merged branches / remove stale worktrees / surface stashes — each under per-action confirmation. |
| `{{CMD:new-skill}}` | `"gap"` | Author a new skill after the gap is proven uncovered. |
| `{{CMD:btw}}` | `"question"` | Lightweight Q&A; no state change. |
| `{{CMD:override}}` | `"reason"` | Sanctioned, logged single-identity gate bypass. |
| `{{CMD:commands}}` | _(none)_ | Show this catalog. |

## Maintainer

| Command | Argument | Purpose |
|---|---|---|
| `{{CMD:dev}}` | `["note"]` | Suspend orchestration to edit codeArbiter itself. Requires `CODEARBITER_DEV=1`; entry/exit logged to `overrides.log`. |
| `{{CMD:arbiter}}` | _(none)_ | Exit dev mode: restore orchestration, log the exit. |

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
- **ADR** — an Architecture Decision Record under `.codearbiter/decisions/`, authored only via `{{CMD:adr}}`.
