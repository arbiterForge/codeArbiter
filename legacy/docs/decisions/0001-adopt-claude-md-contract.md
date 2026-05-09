# ADR 0001 — Adopt CLAUDE.md Contract for `fusion-core`

- **Date:** 2026-05-04
- **Status:** Accepted
- **Owners:** Arch lead + Sec lead
- **Supersedes:** Prior CLAUDE.md ("project initialization" version)

## Context

The original CLAUDE.md captured locked architectural decisions and domain
vocabulary but did not encode defense-grade requirements: FIPS-only crypto,
audit field minimums, secrets-out-of-`.env`, SBOM/sign provenance, trust-zone
egress, conflict-resolution hierarchy, or stage-gated promotion criteria. A
senior-staff review identified 12 Blockers that would let the agent generate
code failing a defense-environment review.

## Decision

Adopt the rewritten CLAUDE.md + `docs/` split as the agent contract for
`fusion-core`. Establishes:

- Stage trajectory (1 Prototype → 2 Internal MVP → 3 Hardened Pilot → 4 ATO-Ready Production) with promotion triggers.
- Conflict-resolution hierarchy: Security/Compliance > Correctness/Data Integrity > Maintainability > Performance > Velocity.
- FIPS-only crypto from Stage 1 (UBI9 FIPS base + system OpenSSL FIPS provider).
- Audit field minimum (`docs/audit-spec.md`) emitted via `audit.emit(...)`, never via app logger.
- Secrets in AWS Secrets Manager from Stage 1; `.env` for secrets prohibited at all stages.
- SBOM from Stage 1; signed artifacts from Stage 2; SLSA L2 from Stage 2, L3 by Stage 4.
- Worker abstraction is a Stage 2 exit criterion (mitigates R-01).
- 17-item agent prohibited-actions list (`docs/agent-policy.md`) with verification signals.
- Risk register seeded with R-01..R-05.

## Consequences

**Positive.** Agent has explicit, verifiable rules with control-family
mappings. Defense reviewers can trace each posture goal to its enforcement.
Stage gating lets prototype velocity continue without re-litigating posture at
promotion time.

**Negative.** Slower per-PR than the previous contract: signed commits, SBOM,
license scan, SAST, secrets scan, dependency scan run on every push. Some
items remain `[CONFIRM-NN]`-blocked for Stage 2 promotion.

**Trade-off level cited (per CLAUDE.md §0):** Level 1 (Security & compliance)
over Level 5 (Developer ergonomics & velocity).

## Verification

- `make ci` passes against the rewritten contract.
- `cat .fusion/stage` returns `1`.
- `tools/agent_policy/` linter exits 0 against the seeded repo.
