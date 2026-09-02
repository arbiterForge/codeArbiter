---
title: Glossary
description: "One-to-three-sentence definitions of codeArbiter's core terms, each linking to the page that explains it fully."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Use codeArbiter terms with their exact, non-overlapping meanings."
  prerequisites: []
  proof: "You can distinguish command, skill, agent, phase, stage, layer, gate, and severity."
---

Short definitions for terms used across these docs. Each entry links to the page that explains
the concept in full. This page is a lookup, not a tutorial.

## ADR

An Architecture Decision Record: a numbered, dated, user-attributed file under
`.codearbiter/decisions/` that records one architectural decision. Authored only via `/ca:adr`;
never invented by a routine finding. See [ADRs and the Decision Log](/concepts/adrs/).

## Advisory

A non-blocking reminder that surfaces right after a write (e.g. a crypto pattern or a CI file
change) so the blocking gate at commit time is not a surprise. Advisories never stop a tool call.
See [Enforcement & Security](/enforcement/#advisory-non-blocking-reminders).

## Agent

A focused author or reviewer role dispatched by a [skill](#skill). An agent is not a public
command and not a second orchestrator; it receives only the tools and context its role needs.
Claude Code dispatches packaged plugin agents. Published releases from 0.7.5 include the complete
packaged resource charter set for that release for Codex host-provided agent threads, with exact
static-package and route-closure checks at release. Until exact-release thread dispatch is durably
proven, workflows use the bounded inline fallback only where the canonical workflow explicitly
permits it and isolation is not mandatory. Pi uses hardened child dispatch. See the
[Agents reference](/reference/#agents).

## Arbiter (enabled flag)

The `arbiter: enabled` line in `.codearbiter/CONTEXT.md`'s frontmatter: the single activation
flag that turns on the orchestrator persona and every enforcement hook for a repository. A repo
without it loads nothing and blocks nothing. See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#contextmd).

## Blocking gate

A gate whose failure stops the tool call outright: the call never happens. Most blocks are resolved
by fixing the issue or, when the gate permits it, a logged `/ca:override`; H-18 activation
protection deliberately has no in-session override path. Contrast with an [advisory](#advisory).
See [Enforcement & Security](/enforcement/#blocking-commit-time-gates).

## Board

`.codearbiter/open-tasks.md`, the project's task list. Every task holds one of three states
(queued, in-progress, done); the only sanctioned writer is `/ca:task`. See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#open-tasksmd).

## Checkpoint

A periodic, read-only sweep of the whole codebase by the reviewer fleet, consolidated into a
dated report under `.codearbiter/checkpoints/`. Catches drift between feature work without
blocking any single change. See [Checkpoints](/concepts/checkpoints/).

## Command

A public entry point the user invokes for an outcome, using the current host's syntax:
`/ca:name` in Claude Code, `$ca-name` in Codex, or `/ca-name` in Pi. The orchestrator routes that
command to its owning skill. See the [Commands reference](/reference/#commands).

## CONFIRM-NN

The placeholder for an unresolved question only the user can answer, numbered and recorded in
`.codearbiter/open-questions.md`. It blocks stage promotion until resolved and is never guessed
at. See [The `.codearbiter/` Directory Reference](/codearbiter-directory/#open-questionsmd).

## Decision log

`.codearbiter/decisions/decision-log.md`, the append-only ledger mirroring every ADR file: one
entry per recorded decision, never edited after the fact. A superseding decision appends a new
entry rather than rewriting the old one. See [ADRs and the Decision Log](/concepts/adrs/).

## Feature Forge / Preview Features

The two-axis system that separates a payload's SemVer maturity from whether an individual
feature is still a preview. In reader-facing copy this is labeled "Preview Features"; "Feature
Forge" is the internal name. See [What Is the Feature Forge](/feature-forge/overview/).

## Gate

A phase exit condition (STOP or BLOCK) that a change must clear before it proceeds. Not a
"checkpoint" and not a "guardrail": those are different mechanisms. See
[The Gated-Lane Model](/concepts/gated-lanes/).

## Hook

A Claude Code hook: a script that runs at a tool-call boundary (`PreToolUse`, `PostToolUse`,
`SessionStart`, …) and can block, remind, or inject context. codeArbiter's hooks are Python,
stdlib-only, and fail loud. See [Hooks reference](/hooks/).

## Lane

A sanctioned path through the system, with gates scaled to the work's risk: implementation,
commit & ship, decisions, or project & meta. Not a "workflow" and not a "track." See
[The Gated-Lane Model](/concepts/gated-lanes/).

## Layer

A level in the greenfield decomposition interview. “Layer” describes how `/ca:decompose` structures
discovery; it is not a project maturity stage, skill phase, or enforcement gate. See the
[`decompose` skill reference](/reference/skills/decompose/).

## Marker

A small file under `.codearbiter/.markers/` that records a gate's pass state, for example
`security-gate-passed`, which a commit-time gate checks for freshness and content coverage
before allowing a commit through. See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#markers).

## NEEDS-TRIAGE

The placeholder for an out-of-scope finding set aside inline during review: recorded, never
acted on in place. It typically lands as a queued item on the [board](#board). See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#open-tasksmd).

## Orchestrator

The always-on persona injected at `SessionStart` in an [arbiter](#arbiter-enabled-flag)-enabled
repo. It routes every request to the skill or agent that owns it and holds the gates; it never
freelances. See [The Persona-Register Split](/concepts/persona-and-context/).

## Override

The sanctioned, logged bypass for a gate that allows bypass, invoked as `/ca:override "reason"`.
It appends one permanent line to `.codearbiter/overrides.log` before the immediate action proceeds.
H-18 is intentionally non-overridable from the governed session. Never call an override a
“workaround” or a “skip.” See [Override a Gate Safely](/guides/overriding-a-gate/).

## Persona

A named voice codeArbiter speaks with: the terse orchestrator, or a focused author/reviewer
agent, each scoped to its own job and context footprint. See
[The Persona-Register Split](/concepts/persona-and-context/).

## Phase

One named step inside a skill, with an entry purpose and often a gate at its exit. A phase is not a
project [stage](#stage) or a decomposition [layer](#layer). See
[The Gated-Lane Model](/concepts/gated-lanes/).

## Provenance

The per-doc evidence trail that backs a derived `.codearbiter/` document (which source lines
justified which claim), used to detect when that source has since drifted. See
[Provenance and Context Drift](/concepts/provenance-drift/).

## SMARTS

The named framework an autonomous `/ca:sprint` uses to decide "as the user" on non-hard-gate
points, scoring each auto-decision and logging it with a confidence flag. See
[SMARTS](/concepts/smarts/).

## Severity

A finding classification (CRITICAL, HIGH, MEDIUM, or LOW) that expresses impact. Severity does not
itself say whether a phase must STOP or BLOCK; gate action is a separate decision. See
[Checkpoints](/concepts/checkpoints/#the-funnel).

## Skill

An orchestrator routine with named phases. The orchestrator routes to a skill from a command, and
the skill may dispatch agents; users do not invoke internal skill files as an alternate command
surface. See the [Skills reference](/reference/#skills).

## Spike

A time-boxed exploration on a disposable `spike/*` branch that answers one named question. It
never merges and never becomes the implementation. Only its written findings survive. See the
[`/ca:spike` reference](/reference/commands/spike/).

## Sprint

An autonomous, multi-task run via `/ca:sprint`: one interactive spec gate, then execution to a
shipped PR with every auto-decision SMARTS-scored and logged to `sprint-log.md`. Hard gates
remain true stops even under autonomy. See
[Run an Autonomous Sprint](/guides/autonomous-sprints/).

## Stage

A single project-maturity number in `.codearbiter/CONTEXT.md`'s frontmatter. It records where the
project is in its maturity progression and is surfaced by `/ca:status` and the statusline; it is not
a skill phase, decomposition layer, gate action, or finding severity. See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#contextmd).

## Statusline

codeArbiter's Claude Code statusline: usage segments in every session, plus a project-state row
(stage, tasks, open questions, overrides) in an arbiter-enabled repo. See
[Set Up the Statusline](/guides/the-statusline/).

## Tribunal

The deep, rarely-convened whole-codebase audit (`/ca:tribunal`): eleven specialist lenses over a
resumable on-disk run, filing approved findings as GitHub issues. Never a required gate, and not
a synonym for the routine [checkpoint](#checkpoint) sweep. See [Checkpoints](/concepts/checkpoints/).
