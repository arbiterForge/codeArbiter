---
status: accepted
date: 2026-06-16
title: Split the persona register into terse gates and conversational thinking
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/ORCHESTRATOR.md, plugins/ca/skills/brainstorming/SKILL.md, plugins/ca/skills/debug/SKILL.md, plugins/ca/skills/decision-variance/SKILL.md
---

# ADR-0005 — Split the persona register

## Status
Accepted — ratified 2026-06-16 by SUaDtL@users.noreply.github.com

## Context
The 2026-06 multi-agent market-readiness evaluation (issue #70) found that daily use
"feels flat," and attributed it to the persona being terse everywhere by design. A uniformly
mechanical voice caps the back-and-forth that makes an assistant feel alive, which suppresses
adoption without strengthening the product. The opposing risk: softening the gates dilutes
their authority, because a gate that chats is a gate a user argues with.

## Decision
The persona runs two registers, scoped by surface. Gates and enforcement (commit-gate, the
reviewer fleet, hard STOPs, BLOCK findings) stay terse, mechanical, and non-negotiable. The
thinking surfaces (`brainstorming`, `debug`, and decision-variance/SMARTS) run a
conversational register: they explore, ask, and reason with the user. Warmth lives where it
helps the user think; it never reaches the surfaces whose job is to refuse.

## Alternatives considered
- **A1 pure enforcement (status quo)** — terse everywhere. Reliable-strong on gate authority,
  but it is the documented cause of flat daily feel: adoption cost with no enforcement gain.
- **A2 pure engagement** — conversational throughout, gates included. Highest adoption-feel
  upside, but Reliable-weak: a chatty gate dilutes the stop signal that is the product's core.

## Consequences
Easier: the exploratory surfaces can build rapport and surface intent, which is where adoption
friction actually lives. The enforcement moat is untouched. This decision sets the direction
for issues #82, #83, and #84 (BLOCK stakes, persona warmth at the close, the `/feature`
receipt). Harder: two registers to maintain and keep from leaking into each other; the
boundary between "thinking" and "gating" surfaces must stay legible to skill authors.

## Risks
Register leak: warmth creeping into gates, or terseness flattening the thinking surfaces.
Mitigated by scoping the conversational register to named skill bodies and keeping
`ORCHESTRATOR.md` terse. Proven wrong if conversational thinking surfaces measurably slow the
gated lanes, or if users still report flat daily feel after the split ships.
