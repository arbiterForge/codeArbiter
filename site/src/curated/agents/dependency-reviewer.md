---
entity: agents/dependency-reviewer
related: [commands/add-dep, skills/subagent-driven-development]
---

## Role

Read-only reviewer of third-party dependencies and container base images: checks license, provenance,
maintenance signal, known CVEs, and supply-chain posture before any install runs. It never installs
anything itself. `/ca:add-dep` dispatches it as the sole gate before a new dependency is added;
`subagent-driven-development` dispatches it when an author agent's diff touches a manifest or lock
file.

## Why this model tier

Ships `model: sonnet`. Judging license compatibility, provenance, and supply-chain risk from an
external registry (it holds `WebFetch`) is closer to research-grade reasoning than a fixed-pattern
scan, which is why it sits above the haiku-tier checks.

## What it emits

A per-check verdict (license, provenance, maintenance signal, CVEs, supply-chain posture, each
PASS/BLOCK/FLAG) plus CRITICAL–LOW findings with the package name and remediation. Blocks the install
on a denied license, an unapproved source, or a known CRITICAL CVE with no documented justification.
