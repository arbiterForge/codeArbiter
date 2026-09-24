---
entity: commands/new-skill
related: [skills/skill-author, feature]
gates:
  - gate: gap evidence
    when: before any skill content is written
    effect: the gap must be proven uncovered by an existing skill or agent — nothing is authored speculatively
  - gate: spec approval
    when: before authoring begins
    effect: the user must sign off on the skill's spec first
---

## What it does

The explicit entry for assessing and authoring a new codeArbiter skill. Its complete
procedure is generated from the `skill-author` owner, so invocation does not require
loading a second wrapper. The owner drives the job through five gated stages: proving the gap, scoping it,
authoring the content, a self-review pass, and finally wiring in the routing entry — the
`INDEX.md` line that actually makes the new skill reachable. Nothing gets written before an
existing skill or agent is shown not to already handle the need, and nothing is considered done
until the result has its own gates, hard rules, and a route pointing to it.

Name the skill in verb-noun form (`"dependency-review"`), not as a loose description
(`"the thing that checks packages"`) — that shape is what the authoring phase expects.

The owning skill remains available to natural-language routing on Claude. The generated
command stays explicitly usable without a duplicate model-facing description. Codex and
Pi expose their generated entry skill and keep the owner as a path-loaded routine.

## Usage

```
/ca:new-skill <verb-noun skill name>
```

The name argument seeds the gap-evidence phase; the spec that phase produces is what gets
approved before any file is written.

## Example

```text
> /ca:new-skill "release-notes-linter"

Phase 1 (gap evidence): checked existing skills/agents — no coverage found for
release-notes format linting.
Phase 2 (scope): drafting spec for approval...

Spec: release-notes-linter
  Routes from: /ca:release (post-changelog-render)
  Gates: 2 (format check, broken-link check)
Approve this spec? y
```

## When to reach for it

A one-time action belongs in `/ca:feature` or a plain command definition, not a new skill; if an
existing skill nearly covers the need, extend it via `/ca:feature` instead. "Do we even need a
skill here?" is an ordinary informational question, not permission to create a skill.
