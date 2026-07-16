---
status: accepted
date: 2026-07-13
title: Treat Pi host authentication as opaque runtime state and fail closed on unknown tools
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .codearbiter/security-controls.md, plugins/ca-pi/**, core/pysrc/**, core/surface/**, tools/build-surface.py, .github/workflows/**
---

# ADR-0014 — Treat Pi host authentication as opaque runtime state and fail closed on unknown tools

## Status
Accepted — approved 2026-07-13 by SUaDtL@users.noreply.github.com (Option A: opaque Pi host
authentication boundary, enforcement-only children, and fail-closed unknown tools).

## Context
Full Pi subagent parity requires fresh Pi processes to use the operator's selected provider and model.
Pi may resolve provider authentication from its host-managed auth store, environment variables, or
user-owned credential commands. codeArbiter's existing security controls describe only secrets it
manages directly, so they did not define whether `ca-pi` could inspect, copy, or forward Pi's wider
credential state. The approved full-parity spec also classified unknown extension tools as `OTHER`,
which is unsafe when an unknown tool may mutate the repository without reaching a write or exec gate.

This ambiguity created a same-level conflict between the approved Pi subagent design and the existing
secret boundary. The maintainer selected the full-parity option that preserves Pi's native provider
support while keeping credential resolution owned by Pi and making the adapter fail closed where a
tool's effect is unknown.

## Decision
Treat Pi's host-managed provider authentication — including its auth store, provider environment
resolution, and user-owned credential commands — as opaque external trusted runtime state. `ca-pi`
must never read, parse, copy, snapshot, log, or implement resolution for that state. Parent and child
launches name an exact provider and model and never silently fall back to another provider or model.

Build each Pi child environment from a minimal operating-system/runtime baseline rather than cloning
the parent environment. Remove codeArbiter's unrelated `FARM_API_KEY` and
`CLAUDE_CODE_OAUTH_TOKEN`; admit only the runtime variables and explicitly selected provider
configuration needed for the chosen child. Task text travels on stdin, never in argv, environment, or
temporary files. JSONL, stderr, results, and audit output are schema-validated, bounded, and redacted.

Start each child with Pi discovery, approval, context, and session loading disabled, then load only
the trusted `ca-pi` enforcement adapter plus explicit generated skill and charter paths. The
`CODEARBITER_SUBAGENT=1` marker disables recursive dispatch only; it never disables enforcement. An
ambient or user-supplied marker outside the runner's validated child contract produces a visible,
fail-closed diagnosis. Child processes remain cooperative process isolation, not an operating-system
sandbox.

Treat every unknown Pi tool as potentially mutating and block it unless the generated host descriptor
explicitly classifies it as read-only or maps it to a governed canonical operation. `ca-pi` never
grants project trust. Same-process extensions the operator has already trusted retain arbitrary
same-user code execution under ADR-0010's cooperative-agent boundary, but promotion requires a live
test proving no later extension can mutate final governed arguments after `ca-pi` approves them. If
Pi cannot provide that ordering guarantee, implementation stops and ADR-0013 must be revisited.

## Alternatives considered
- **API-key-only Pi children** — declined. It would break subscription and host-native authentication
  parity while still making codeArbiter responsible for credential transport.
- **Remove isolated Pi subagents** — declined. It would knowingly reduce the approved full-parity
  target when a bounded host-native design remains testable.
- **Pass through the parent environment and classify unknown tools as `OTHER`** — declined. It would
  expose unrelated secrets to children and allow new mutating tools to bypass governance by default.

## Consequences
Pi keeps its native provider/authentication capabilities without turning `ca-pi` into a third secret
manager. Child launches and tool classification gain explicit, testable security contracts shared by
the generated host descriptor. Adding a provider or tool requires a deliberate allowlist or mapping
change plus fixtures; ambient host state cannot silently expand a child or tool's authority.

The adapter and doctor become more complex: they must construct cross-platform minimal environments,
validate exact provider/model selection, detect marker misuse, bound and redact process output, and
fail visibly on collisions or unclassified tools. Some Pi configurations that depend on broad ambient
environment inheritance will require explicit provider configuration instead.

## Risks
Pi may resolve authentication through behavior that cannot be invoked without exposing more ambient
state than this contract permits. A later extension may run after `ca-pi` and rewrite approved tool
arguments. Process isolation does not protect the host from a malicious model, tool, or trusted
extension. Provider additions may accidentally widen the environment allowlist, and redaction cannot
make unbounded secret-bearing output safe after the fact.

This decision is proven wrong if live tests cannot enforce final governed arguments, if a child needs
codeArbiter to copy or interpret Pi credential material, or if an unknown mutating tool can execute
before classification. Any of those outcomes is a promotion STOP and reopens ADR-0013 rather than
authorizing a host-specific governance fork.
