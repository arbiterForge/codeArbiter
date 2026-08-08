---
status: proposed
date: 2026-08-08
title: Chain-internal skills are path-routed and registry-hidden
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/includes/routing-table.md, core/surface/skills/*/SKILL.md, core/surface/commands/*.md, core/surface/SPRINT.md, plugins/*/skills/*/SKILL.md, plugins/*/routines/*/SKILL.md
---

# ADR-0028 — Chain-internal skills are path-routed and registry-hidden

## Status
Proposed — decision content approved by SUaDtL@users.noreply.github.com on 2026-08-08 (plan
"tranquil-crunching-fog" v2 approved post-adversarial-review; rulings: dual-fronted skills stay
registry-visible; harness-reserved names documented, not renamed). Awaiting explicit ratification.

## Context

Claude Code auto-exposes every plugin skill as a slash command and loads its description into
every session's model-facing registry. Nine of codeArbiter's skills are strictly chain-internal —
never user-typed, reached only mid-chain — yet their descriptions cost ~1K tokens per session.
Adversarial review killed the naive fix (frontmatter alone): the nine were reached by BARE NAME
in routing prose, and the registry entry was plausibly their only resolution path — hiding them
without a written fallback severs every chain. A five-round scratch-plugin spike (verbatim
transcription probes, never a model's own inventory report) then established the live facts:
`disable-model-invocation: true` removes name and description while the body stays path-loadable;
`feature`/`fix`/`new-skill` are HARNESS-RESERVED names suppressed from the model-facing listing
regardless of plugin or frontmatter; unquoted `": "` does not drop entries on current builds
(falsifying the earlier scanner-drop theory); and `dispatching-parallel-agents`' absence was
registry-budget pressure, not content.

## Decision

- **Routing is path-defined, registry-independent.** The routing-table preamble states the rule:
  routing to a skill means loading `{{PLUGIN_ROOT}}/skills/<name>/SKILL.md`; every chain-internal
  route site additionally cites the explicit path at first mention (feature/checkpoint/review/
  spike commands, SPRINT.md, subagent-driven-development, dispatching-parallel-agents,
  commit-gate's security-gate routing).
- **The nine chain-internal skills ship `disable-model-invocation: true`**: brainstorming,
  writing-plans, executing-plans, subagent-driven-development, tdd, using-git-worktrees,
  dispatching-parallel-agents, secret-handling, crypto-compliance. The key is inert on the codex
  and pi hosts (routines are path-loaded prose there).
- **The dual-fronted skills stay registry-visible** (commit-gate via /commit, and
  finishing-a-development-branch via /pr): their plain-words auto-route phrasing is plausibly
  load-bearing (user ruling).
- **Frontmatter scalar quoting is a house rule**: any scalar starting with `[`/`{` or containing
  `": "` or `" | "` is JSON-quoted at the source — the `_yaml_safe_scalar` predicate the
  generator already applies to codex/pi wrappers, now applied to the claude surface and encoded
  in skill-author Phase 4 + the skill template. Hygiene and cross-host portability, not a bug
  fix on current builds.
- **Harness-reserved names are documented, not renamed** (user ruling): /ca:feature, /ca:fix,
  /ca:new-skill keep their names; the suppression affects only the model-facing listing, typed
  invocation and ORCHESTRATOR-routed intent are unaffected. Recorded in
  docs/investigations/token-efficiency.md.

## Alternatives considered

- **Frontmatter hides without the path rewrite** — rejected: adversarially shown to leave the
  nine skills with no written resolution path.
- **`user-invocable: false` (instead or additionally)** — rejected: no token gain (description
  still loads) and the combined state is the least-documented harness behavior.
- **`skillOverrides` settings map** — rejected: user-settings-only, not plugin-shippable.
- **Renaming feature/fix/new-skill to dodge the reservation** — rejected (user ruling): breaks
  muscle memory, docs, catalogs, and cross-references for a model-listing-only gain the
  ORCHESTRATOR routing layer already compensates for.
- **Hiding the dual-fronted skills too** — rejected (user ruling): plain-words auto-routing on
  commit/PR intents plausibly reads their descriptions.

## Consequences

- ~1K tokens of chain-internal descriptions leave every Claude-host session's registry; the
  registry-budget pressure that silently dropped the longest entry also clears.
- Chain routing is deterministic from prose alone — a fresh model with no registry can follow
  every lane by path.
- New chain-internal skills must carry the key AND a path-cited route site (skill-author Phase 4
  enforces; the routing-table preamble states the convention once).
- The reserved-name suppression is a harness behavior codeArbiter does not control; if a future
  build widens the reserved set, the same document-and-route-through-ORCHESTRATOR posture applies.

## Risks

- A future harness change could make `disable-model-invocation` also block user-typed invocation
  or path loads — the spike instrument (scratch plugin + verbatim transcription) is the re-test.
- Path citations can rot if a skill directory is renamed; check-plugin-refs.py resolves every
  `{{PLUGIN_ROOT}}` citation in CI, so rot fails the build rather than the chain.
- Hidden skills are invisible to model-initiated discovery by design; a genuinely new intent that
  should route to one depends on ORCHESTRATOR.md and the routing table staying authoritative.
