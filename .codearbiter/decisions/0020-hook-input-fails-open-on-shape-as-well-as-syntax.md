---
status: accepted
date: 2026-07-25
title: Hook input fails open on malformed shape as well as malformed syntax
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/pysrc/_hooklib.py, core/pysrc/pre-bash.py, core/pysrc/pre-write.py, core/pysrc/pre-edit.py, core/pysrc/pre-read.py, core/pysrc/post-write-edit.py
---

# ADR-0020 — Hook input fails open on malformed shape as well as malformed syntax

## Status
Accepted — explicitly decided by SUaDtL@users.noreply.github.com on 2026-07-25.

## Context
`_hooklib.read_input()` already carries a documented, deliberate exception to the fail-loud
principle: a malformed stdin payload must NOT brick the session by blocking every subsequent tool
call, so a parse error warns and returns `{}`.

That exception covers malformed **syntax** only. A payload that is valid JSON but not an object —
`[]`, `3`, `"str"`, `true`, `null` — parses cleanly and is returned as a non-dict. Downstream,
`tool_input(data)` evaluates `(data or {}).get(...)`, so *falsy* non-dicts (`[]`, `null`) are
accidentally safe via the `or {}`, while *truthy* ones (`3`, `"str"`, `true`) raise AttributeError
out of the guard.

The decisive fact is that **the hook envelope is host-produced, not model-produced.** It arrives on
stdin from Claude Code, Codex, or Pi. A model can place hostile content *inside* `tool_input`
fields, but cannot make the top-level object a list. A non-dict envelope therefore means host
misbehaviour or version drift — a compatibility event, not an attack.

## Decision
Treat a malformed **shape** exactly as the existing exception treats malformed **syntax**: normalize
any non-dict payload to `{}` at the single `read_input()` chokepoint, and widen the docstring to say
so. Unreadable input is unreadable, whether the failure is syntactic or structural.

The distinction between the two carries no security content here. Both mean *the guard cannot read
this call*, which is the exact situation the documented exception already ruled on.

## Alternatives considered
- **Fail closed on a non-dict envelope** — rejected. It buys no protection against a threat that
  cannot reach this surface (the envelope is not model-controlled), while creating precisely the
  failure the existing exception exists to prevent: a host payload change would brick every tool
  call until codeArbiter shipped a fix.
- **Split the rule by position — router fails closed, guard fails open** — considered and not taken
  as doctrine. It is more precise, but it makes every future hook author decide which side their
  code is on, and the asymmetry is better recorded as a note than as a rule (see below).

## Consequences
One rule, stated once, at one chokepoint: unreadable input yields `{}` and a warning. Every host —
including future ones — inherits it without a per-host decision.

**A deliberate asymmetry is recorded rather than removed.** The ca-codex *adapter*
(`plugins/ca-codex/hooks/pre-tool-adapter.py`) fails CLOSED on a non-object payload, and that stays.
The adapter is a **router**: it decides which guard to dispatch to, so a payload it cannot route is
one it cannot prove safe. A guard that cannot parse its own input is a different case. That
difference is intentional, not drift, and this ADR is the place it is written down. The adapter's
refusal is additionally dormancy-aware — in a repository that never opted into codeArbiter it passes
through untouched — so failing closed there cannot break unrelated projects.

## Risks
Normalizing a non-dict envelope to `{}` means a guard proceeds with no `tool_input` rather than
refusing, so a host that silently changed its envelope shape would degrade to unenforced calls with
only a warning to show for it. That is the accepted cost of the existing exception, now applied
consistently.

This decision is proven wrong if a host is found where the envelope shape is model-influenceable, or
if the warning proves too quiet to surface a real host drift — in which case the remedy is to make
the degradation louder, not to fail closed and brick the session.
