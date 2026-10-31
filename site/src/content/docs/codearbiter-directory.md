---
title: "The .codearbiter/ Directory Reference"
description: "What the .codearbiter/ project-state store holds, its two context formats, and a one-table map of every stock path, its writer and its reader."
journey:
  level: "Power user"
  time: "4 minutes"
  outcome: "Locate the authoritative project-state artifact for a task, decision, audit, or recovery."
  prerequisites:
    - "An initialized repository"
  proof: "You can answer where a spec, plan, decision, gate event, checkpoint, and audit packet live."
---

`.codearbiter/` is codeArbiter's project-state store: a root-level directory, outside `.claude/`,
so it survives even if the plugin itself is uninstalled. It holds the project's own record (its
spec, task board, decisions, and audit trail), separate from the plugin code that reads and
writes it. `/ca:init` scaffolds it; `/ca:create-context` (existing codebase) or `/ca:decompose`
(greenfield) populates it. Its presence and content is the plugin's actual contract with your
repo: if you want to know what codeArbiter knows about your project, or what it will do next,
this directory is where to look.

Enforcement itself is gated on one file in here: `CONTEXT.md`. Everything else described below
only matters once that file carries `arbiter: enabled`.

The table below maps every stock path the scaffold or a governed lane produces or reads. Some appear
when the owning workflow first needs them (`plans/decomposition/`,
`.markers/`, `.provenance/`, `spikes/`, `reports/`). The [state file reference](/codearbiter-directory/files/)
covers each path in detail: its format, its lifecycle, and what happens if it is deleted.

## Two context formats

New scaffolds record narrative context as native HTML knowledge: `context/project.html`,
`context/tech-stack.html`, `context/coding-standards.html`, `context/security-controls.html` and
`context/code-map.html`, plus greenfield `decomposition/project.html`. `CONTEXT.md` frontmatter
carries `context-format: html` for them. Repositories scaffolded earlier keep the Markdown
documents and [`.provenance/` records](/codearbiter-directory/files/#provenance) until their owner converts them explicitly
with `knowledge.py convert`, agent-recorded content, a mapping from every returned section to saved records or notes, and `convert --finish <token> --coverage @checklist.json`. In both formats `CONTEXT.md` owns activation and stage, and the scope
blocks in `security-controls.md` stay the operative migration, CI and deploy configuration.

## Project plans are not feature execution plans

In an HTML-knowledge repository, greenfield decomposition is one native document,
`decomposition/project.html`, whose capability, component, phase and work-item records hold the
intended architecture, phased plan and backlog; reconcile reads them by stable record ID.
In a Markdown-format repository, greenfield decomposition creates three named Markdown documents:
`plans/01-architecture-breakdown.md`, `plans/02-phased-build-plan.md` and
`plans/03-task-backlog.md`. They own project architecture, phased delivery and the project backlog.
Reconcile consumes their exact filenames. They are not legacy feature pairs to convert to HTML.
Brownfield context creation does not manufacture this set.

Feature/sprint specifications and execution plans are a different layer. New full-lane work uses
a same-slug typed HTML pair when the installed package has its qualified native capability;
existing Markdown pairs remain on their exact legacy path; small-lane work remains inline with
its triage record. [Review specifications and plans](/guides/review-artifacts/) explains the
review, progress and recovery boundaries.

## At a glance

| Path | Written by | Read by | Editable by hand? |
|---|---|---|---|
| `CONTEXT.md` | `/ca:init`; context workflows through the native writer | every enforcement hook (`arbiter_active()`), the orchestrator | No: use the context writer; preserve activation frontmatter |
| `code-map.md` | Context workflows through the native writer | feature/task orientation, context checks | No: refresh selected claims through `/ca:context-check` |
| `context/*.html` | HTML-format context workflows through `knowledge.py` and the native engine | `knowledge.py relevant`, `task-context`, reviewers | No: change records with `knowledge.py`; a Git conflict uses `knowledge.py merge-conflict` |
| `decomposition/project.html` | HTML-format `/ca:decompose` | Interview resume, `reconcile`, `knowledge.py promote` | No: change records with `knowledge.py` |
| `.gitattributes` | `/ca:init` (HTML format) and `knowledge.py convert --finish` | Git | Keep it: it stops line-ending conversion of native HTML artifacts |
| `open-tasks.md` (legacy owner) | `/ca:task` through `taskwrite.py` | selected work facade, statusline, `SessionStart` | No: guarded to the legacy writer (hook `H-22`) |
| `done-tasks.md` (legacy owner) | `/ca:standup`'s selected archival sweep | legacy history, read on demand | No: guarded (hook `H-22`, append-only) |
| `work/project.json`, `work/*.html` (native owner) | `work.py` through the native engine | selected work calls and derived views | No: use stable Work IDs and native operations |
| `work/provider.json` | `work.py provider-configure` | explicit GitHub sync | No: finite provider binding; no credential value is stored |
| `work/project-provider.json` | `work.py project-configure` | optional GitHub Projects item and single-select effects | No: binds to the issue provider; no credential value is stored |
| `legacy/open-tasks.md`, `legacy/done-tasks.md` | selected journaled work adoption | historical byte-exact snapshots | No: retained originals, not writable boards |
| `open-questions.md` | the orchestrator, when a `[CONFIRM-NN]` is raised | `/ca:status`, `SessionStart`, the statusline | Yes |
| `decisions/*.md`, `decision-log.md` | `/ca:adr` only | `/ca:adr-status`, `/ca:reconcile`, `post-write-edit.py` (H-12) | No: guarded to `/ca:adr` |
| `specs/*.md` | Legacy feature/sprint workflows already owned by Markdown | `writing-plans`, `/ca:status` | Yes |
| `plans/01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md` | Greenfield `decompose` | Human project review, `reconcile` | Review through the owning project-planning procedure; preserve exact filenames |
| Other legacy `plans/*.md` | `writing-plans` for an existing Markdown spec | `executing-plans`, `subagent-driven-development`, `/ca:status` | Preserve the selected format, agreed scope and execution state |
| `specs/*.html`, `plans/*.html` | New full-lane feature/sprint workflows through the internal typed-artifact engine (default) | The same workflow readers through validated, scoped reads | No: use typed engine operations |
| `plans/decomposition/` | `/ca:decompose` | Interview resume and context provenance | Preserve the recorded answers and decisions through the owning workflow |
| `checkpoints/*.md` | `checkpoint-aggregator` agent (`/ca:checkpoint`) | `/ca:audit`, `/ca:status`-adjacent reads | Yes |
| `audits/*.md` | `/ca:audit` | humans (report only) | Yes |
| `reports/` | `/ca:tribunal` and named handoff/evidence workflows | the owning workflow on resume, humans | Yes, but not while an owning run is in flight |
| `sprint-log.md` | `/ca:sprint` | `/ca:status`, `/ca:audit` | No: append-only, guarded (H-05) |
| `overrides.log` | `/ca:override`, the mode-plane flip (`mode --dangerous`/`--ops`/`--arbiter`, `MODE: <name> enter/exit`) | statusline, `/ca:status`, `/ca:audit`, staleness-warn | No: append-only, guarded (H-05) |
| `triage.log` | `/ca:feature` small-lane triage | `/ca:audit` | No: append-only, guarded (H-05) |
| `gate-events.log` | every `block()`/`remind()`/`warn()` call in the hooks | (durable sink; no reader ships yet) | No: append-only, guarded (H-05) |
| `.markers/` | `security-pass.py`, `migration-pass.py`, `prompt-submit.py` (mode marker), `/ca:adr` | the commit-gate hooks (`pre-bash.py`, `pre-write.py`, `pre-edit.py`) | No: guarded, and hand-writing one is friction and an audit trail, not a proof (see [`.markers/`](/codearbiter-directory/files/#markers)) |
| `.provenance/*.json` | `context-creation`, `decompose`, `context-check` (re-scout/re-baseline) | `SessionStart` (drift line), `commit-gate` (auto-heal) | Not by hand: regenerate via `/ca:context-check` |
| `security-controls.md`, `tech-stack.md`, `coding-standards.md` | Context workflows through the native writer | reviewer agents, the crypto/secret gates | No: update selected content with its paired provenance |
| `last-checkpoint` | `/ca:checkpoint` after its report is written | `/ca:status`, the statusline (overrides-since-checkpoint) | Not normally: it's a counter, not a note |
| `spikes/*.md` | `/ca:spike` | humans, `/ca:feature` (seeds `brainstorming`) | Yes |

## Per-path reference

The [state file reference](/codearbiter-directory/files/) documents each path in the table: its
format, who may change it, and what happens if it is deleted or goes stale.
