---
status: accepted
date: 2026-07-16
title: Require every live git enforcer and persist trusted executable identity
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0014
governs: core/pysrc/_githooks.py, core/pysrc/session-start.py, plugins/*/hooks/_githooks.py, plugins/*/hooks/session-start.py
---

# ADR-0015 - Require every live git enforcer and persist trusted executable identity

## Status
Accepted - explicitly approved 2026-07-16 by SUaDtL@users.noreply.github.com after review of Option A:
all live enforcers must allow, trusted executable identity is atomic and persistent, and malformed
identity state fails closed.

This decision supersedes only the git-hook selection and executable-identity portions of
`0014-githook-shim-dropin-fail-closed.md`. Its shared, host-neutral drop-in directory and fail-closed
posture remain in force. The separately authored Pi security ADR that also carries number 0014 is not
superseded.

## Context
ADR-0014 replaced a last-writer-wins absolute enforcer path with a shared drop-in registry. It directed
the shim to execute the first live enforcer it found. That rule is unsafe once independently versioned
host plugins coexist: an older first entry can allow an operation that a newer sibling would block.
Filename ordering is not a security authority, and the plugins' independent versions are not safely
comparable as one release sequence.

The Pi host also requires absolute, trusted Python and Git executable identities. A later legacy-host
SessionStart that lacks those identities must not erase them, and an incomplete first registration or
failed first persistence must not silently fall back to ambient `PATH`. The identity pair and its owner
form one security state and therefore cannot be updated safely as separate files.

Pre-push supplies its ref transaction on standard input. Running more than one enforcer therefore also
requires capturing that payload once and replaying the identical bytes to each live enforcer.

## Decision
The host-neutral registry uses stable, manifest-derived plugin names. Legacy registry entries whose
keys are version-directory names are ignored rather than treated as live authorities.

The shim runs every live registered enforcer in deterministic registry order. Every enforcer must
allow the operation; the first non-zero verdict stops evaluation and is returned. If no enforcer
resolves, the shim fails closed as ADR-0014 requires. For pre-push, the shim captures standard input
using shell built-ins and replays the same payload to each enforcer.

Trusted Python path, Git path, and owning plugin are persisted together in one atomically replaced
identity bundle inside the shared drop-in directory. A host that has no trusted identity preserves an
existing complete bundle. A first registration with an incomplete identity pair, or a failed first
write, raises and leaves the Pi integration unready. A refresh failure with an existing complete bundle
preserves that prior bundle. If a bundle exists but is incomplete or its executables are stale, the shim
fails closed; ambient `PATH` is available only to legacy installations for which no identity bundle has
ever been registered. Uninstall removes the bundle only when the uninstalling plugin owns it.

## Alternatives considered
- **Keep first-live selection.** Rejected because entry ordering permits an older sibling to downgrade
  a newer security decision.
- **Select the newest enforcer.** Rejected because independently versioned plugins have no common,
  authenticated ordering and registry metadata is not a release authority.
- **Copy one canonical enforcer into the shared directory.** Rejected because it creates a new shared
  executable lifecycle and ownership protocol without eliminating last-writer downgrade risk.
- **Run every live enforcer and persist one atomic identity bundle.** Selected because disagreement
  resolves in the secure direction and identity state cannot be partially observed.

## Consequences
- A block from any live host plugin blocks the git operation. Mixed-version installations cannot use
  registry ordering to bypass a stricter sibling.
- Multiple read-only checks and audit events can occur for one git operation. This is intentional; the
  checks are bounded by the number of installed host plugins.
- An older enforcer can produce a false-positive block. That availability cost is preferable to a
  silent security downgrade and is recoverable by updating or uninstalling the stale plugin.
- Pre-push input is held in a shell variable before replay. Git's ref-update payload is line-oriented
  and bounded by the pushed refs; tests prove identical replay to each enforcer.
- A stale or malformed trusted identity bundle blocks until the owning Pi plugin refreshes or removes
  it, making identity corruption visible rather than falling back to an untrusted executable.

## SMARTS assessment
- **Securable - Strong:** all live controls must allow, incomplete trusted identity fails closed, and
  ambient executable resolution cannot replace an attempted Pi identity.
- **Maintainable - Strong:** stable manifest names and one atomic bundle remove version-directory and
  partial-file repair rules.
- **Available - Adequate:** a stale enforcer or identity can block legitimate work until repaired.
- **Reliable - Strong:** mixed versions, uninstall ownership, failed refresh, and pre-push replay have
  deterministic behavior.
- **Testable - Strong:** the behavioral matrix covers version skew, stale registry keys, identity
  persistence failures, legacy preservation, PATH poisoning, and identical pre-push input.
- **Scalable - Indifferent:** the bounded plugin count makes sequential evaluation acceptable; this
  decision does not target large fleets of enforcers.

## Risks
- A future host could perform mutating work inside its enforcer, violating the assumption that repeated
  evaluation is safe. Enforcers remain restricted to validation and audit recording.
- Shell command substitution strips trailing newlines. Git pre-push parsing is line-based and the test
  contract compares the semantic ref records received by every enforcer.
- The duplicate historical ADR-0014 number remains visible. Renumbering either accepted record would
  rewrite history, so this ADR identifies the superseded artifact by its full slug.
