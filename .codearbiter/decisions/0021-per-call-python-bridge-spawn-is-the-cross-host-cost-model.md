---
status: accepted
date: 2026-07-25
title: Per-call Python bridge spawn is the cross-host cost model
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca-pi/tools/src/bridge.ts, plugins/ca-pi/hooks/pi-bridge.py
---

# ADR-0021 — Per-call Python bridge spawn is the cross-host cost model

## Status
Accepted — explicitly decided by SUaDtL@users.noreply.github.com on 2026-07-25.

## Context
Every gated Pi tool call spawns a fresh Python bridge process. Tribunal finding performance-001
raised whether that should become a persistent bridge worker, and downgraded itself from high on a
decisive observation: **Claude Code pays the same per-call hook-spawn cost.** The question is
therefore not whether spawning is free — it is whether Pi should diverge from the cost model every
other host already accepts.

`.github/scripts/pi_benchmark.py` measures the cost (`medianMs`, `p95Ms`) and is wired into CI path
filters, so the number is observable rather than anecdotal.

## Decision
Accept the per-call spawn as the cross-host standard cost model. Do not build a persistent bridge
worker.

The per-call process is **stateless by construction**: it holds no lifetime, carries nothing between
gate decisions, and dies with the decision it made. That property is the point, not a side effect.

## Alternatives considered
- **Persistent bridge worker (daemon)** — rejected. It places a long-lived process holding
  enforcement authority in front of every gated tool call, requiring its own authentication, health
  checking, restart, and staleness handling. A wedged worker degrades every subsequent gated call
  rather than one.
- **Reduce spawn cost instead** — not needed now, and explicitly the preferred remedy if latency
  ever becomes a real problem (see reopen condition).

## Consequences
One code path, no daemon lifecycle, and no state that can be poisoned between calls. Pi's cost
profile matches Claude Code's, so "is this slow?" is answered the same way on every host.

The cost is linear in gated tool calls and is paid on every one. That is accepted.

## Risks
The rejection rests on a judgement about where this codebase actually breaks. The 2026-07-25 sweep
produced three independent defects from long-lived or ambient state — a statusline pinned into a
worktree that was then pruned, a broker listener that could outlive its child, and a token bound to a
broker rather than to a process. A daemon in the enforcement path would add exactly that class of
surface.

This decision is proven wrong if the measured `p95Ms` becomes a real impediment to normal work. The
remedy in that case is to make the bridge **cheaper to start** — trimming imports, deferring work
off the hot path — not to keep one alive. Adopting a persistent worker would require superseding this
ADR and confronting the daemon-lifetime surface deliberately, rather than arriving at it by
increments.
