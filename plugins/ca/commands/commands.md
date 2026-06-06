---
description: Show the codeArbiter command catalog — the public command list and what each routes to.
argument-hint: (none)
---

# /ca:commands — command catalog

Present the public command list. Read-only, no state change.

## Flow

1. Read the quick-reference table from `${CLAUDE_PLUGIN_ROOT}/COMMANDS.md`.
2. Output the table only — command, one-line description, route. No prose walkthrough.

## Catalog

| Command | Does | Routes to |
|---|---|---|
| `/ca:feature "<what>"` | Spec-driven feature — the only entry to implementation | `brainstorming` → `tdd` pipeline |
| `/ca:fix "<bug>"` | Fix a confirmed defect, regression test first | `tdd` skill |
| `/ca:refactor "<what>"` | Behavior-preserving restructure | `tdd` skill |
| `/ca:debug "<symptom>"` | Investigate-then-decide root-cause analysis | `debug` skill |
| `/ca:commit` | Run the full commit gate | `commit-gate` skill |
| `/ca:pr` | Open a PR after BLOCK reviews clear | `finishing-a-development-branch` |
| `/ca:review [path]` | Review the current diff with the reviewer fleet | `dispatching-parallel-agents` |
| `/ca:checkpoint` | Periodic multi-reviewer codebase sweep | `dispatching-parallel-agents` |
| `/ca:threat-model` | Pre-implementation STRIDE analysis | `security-architecture` skill |
| `/ca:adr "<title>"` | Author an Architecture Decision Record | `decision-lifecycle` skill |
| `/ca:adr-status` | Report ADR health | `decision-lifecycle` skill |
| `/ca:decision-variance` | Reconcile artifacts vs. scaffold via SMARTS | `decision-variance` skill |
| `/ca:add-dep "<pkg>"` | Vet and add a dependency | `dependency-reviewer` |
| `/ca:release` | SemVer bump + changelog + annotated tag | `release` skill |
| `/ca:init` | Scaffold `.codearbiter/` state store | (scaffolder) |
| `/ca:statusline` | Install/wire the codeArbiter statusline | (installer) |
| `/ca:create-context` | Populate context for an existing codebase | `context-creation` skill |
| `/ca:decompose` | Greenfield layered interview | `decompose` skill |
| `/ca:status` | Formatted project status report | (none) |
| `/ca:btw "<question>"` | Lightweight Q&A — no routing | (none) |
| `/ca:surface-conflict` | Halt all work and surface a contradiction | (none) |
| `/ca:override "<reason>"` | Logged bypass of a gate | (none) |
| `/ca:new-skill "<name>"` | Author a new skill | `skill-author` skill |
| `/ca:commands` | Show this catalog | (none) |

## Hard gate

Read-only. MUST NOT modify a file or route to a skill. Output the catalog only.
