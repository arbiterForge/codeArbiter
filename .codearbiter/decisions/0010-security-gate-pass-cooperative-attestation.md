---
status: accepted
date: 2026-07-02
title: Security-gate pass is a cooperative-agent attestation, not a non-fabricable proof
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/hooks/security-pass.py, plugins/ca/hooks/pre-bash.py, .codearbiter/security-controls.md
---

# ADR-0010 — Security-gate pass is a cooperative-agent attestation, not a non-fabricable proof

## Status
Accepted — ratified 2026-07-02 by SUaDtL@users.noreply.github.com. Resolves tribunal finding
appsec-003 (issue #196).

## Context
`security-pass.py` mints the `.codearbiter/.markers/security-gate-passed` marker by hashing every
sensitive line (`CRYPTO_RE`/`SECRET_RE`) currently in the worktree and recording their digests, with
no evidence that a crypto/secret review actually occurred. `pre-bash.py` H-09b/H-10b (and
`git-enforce.py`) then admit the commit because every sensitive line is covered. The H-19 shell-forge
guard blocks writing the marker via `echo`/`cp`/`tee`, but invoking the sanctioned producer directly
(`python3 plugins/ca/hooks/security-pass.py`) is unguarded and yields the same marker — so
`python3 .../security-pass.py && git commit ...` clears the gate the crypto-compliance/secret-handling
skills exist to force, without the review itself happening. This is the same trust-model seam as
appsec-002 (issue #175, `--no-verify` indirection): the control raises friction and leaves an audit
trail but does not cryptographically bind to a real review event.

## Decision
codeArbiter's gate markers are cooperative-agent attestations, not tamper-proof proofs. Direct
invocation of `security-pass.py` is the intended attestation mechanism, and the trust boundary is
stated explicitly in `security-controls.md`. No code change to the producer. Rationale: codeArbiter
governs a cooperating orchestrator; a Bash-capable non-cooperating agent can defeat most controls
regardless (per appsec-002/#175), so binding the marker to a non-fabricable reviewer artifact adds
real complexity for a threat the product does not claim to stop. The gate's value is raising friction
and leaving an audit trail on the cooperative path, and that value is preserved.

## Alternatives considered
- **Bind the marker to a non-fabricable review artifact** (require the reviewer agent's signed verdict
  as input to `security-pass.py`) — declined. M-effort and brittle, and it defends against a
  non-cooperating Bash-capable agent that already bypasses the surrounding controls; the product's
  threat model is a cooperative orchestrator, so the binding buys little.
- **Narrower / soft measures** (invoke `security-pass.py` only as a subprocess of the reviewer skill;
  a soft warning without changing gate semantics) — declined. Hard to guarantee and brittle; a warning
  that changes nothing is noise.

## Consequences
Easier: no new machinery; the existing producer and gate stand. The trust boundary is now documented,
so the posture is a stated design choice rather than a latent gap a future audit re-files. Harder: a
non-cooperating agent with shell access can still self-mint a pass — accepted, and out of scope for the
product's threat model.

## Risks
The documented boundary must not be read as "the gate is unnecessary" — it still enforces the
cooperative path and the audit trail. This decision is proven wrong if codeArbiter's threat model
expands to untrusted/adversarial agents, at which point the self-mint path becomes a real
vulnerability and option 2 (non-fabricable binding) becomes the fix.
