---
status: accepted
date: 2026-09-08
title: Use reviewed host locks and two-phase Pi promotion
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .github/fixtures/pi-hosts/**, .github/scripts/pi_host_locks.py, .github/workflows/ci.yml, .github/workflows/pi-promotion.yml, .github/pi-promotion-targets.json, plugins/ca-pi/**, core/hosts.json, docs/pi-parity-testing.md, .codearbiter/specs/pi-support.md
---

# ADR-0035 — Use reviewed host locks and two-phase Pi promotion

## Status
Accepted — ratified by SUaDtL@users.noreply.github.com on 2026-09-08.

## Context

The supported Pi CI and promotion paths installed host packages from the network without a
repository-owned dependency graph. Pi 0.80.5's published shrinkwrap resolved four HIGH advisories,
while exact Pi 0.84.1's graph passed the dependency review needed for the current support baseline.
That checkpoint-specific baseline is operational state, not a permanent version decision. A global
install also allowed ambient npm configuration, cache state, lifecycle hooks, and later registry
resolution to influence the executable graph used as compatibility evidence.

Promotion creates a second trust boundary. A newly captured candidate graph has not yet passed
dependency review. Disabling lifecycle scripts does not make explicitly running the candidate's
binary safe, so pre-review automation cannot execute that package while still describing the graph
as inert data.

## Decision

This ADR governs how Pi versions enter supported execution; it does not permanently pin Pi 0.84.1
or make a single supported version an architectural invariant. Exact Pi 0.84.1 is the current
checkpoint baseline after retiring 0.80.5. Supported Pi is expected to advance through the promotion
process as Pi releases advance. The current implementation maintains one rolling exact version, but
the supported-version set remains operational policy and may evolve without a new ADR as long as the
review, installation, and promotion boundaries recorded here remain intact.

Supported CI obtains each supported Pi version only from a committed lockfile-v3 graph whose
registry URLs and SHA-512 integrities are complete and whose exact bytes are bound to a strict
structured dependency-review receipt. Admission requires a literal `PASS` and complete evidence for
source identity, reviewer identity, licenses, zero production and complete-graph audit findings,
disabled lifecycle scripts, signatures, and provenance. Missing, unknown, malformed, contradictory,
pending, or digest-mismatched evidence fails closed.

Supported installation uses `npm ci` in a clean prefix outside the repository. Every npm subprocess
disables lifecycle scripts, isolates cache and log state, replaces ambient user and global npm
configuration with empty disposable files, removes ambient npm configuration and auth-token
variables, and pins both the general and `@earendil-works` registries at command-line precedence.
The installed graph is not exposed until production and complete audits, npm signature verification,
and an exact-version installed-tree check pass.

Promotion is deliberately two-phase. Trusted default-branch automation may resolve an exact stable
candidate, capture its dependency graph and source metadata as `PENDING_REVIEW`, apply the declared
prospective text and generated-surface changes, and open a draft PR. That phase treats candidate
bytes as data and never installs or executes them. The draft cannot pass supported-host CI until a
sanctioned dependency review replaces the pending record with a complete reviewed `PASS` receipt.
Only then may reviewed-PR CI install the locked candidate and run the live Linux, Windows, and macOS
host-contract matrix. Static pre-review checks and live post-review proof remain distinct and are
never represented as substitutes for each other.

## Alternatives considered

- **Permanently pin Pi 0.84.1 or mandate a single supported version in architecture** — rejected
  because Pi support must advance with upstream releases; exact versions and the size of the current
  support set are operational policy governed by evidence, not immutable architecture.
- **Keep Pi 0.80.5 and override its published shrinkwrap** — rejected because npm honors the
  package shrinkwrap and a downstream override or hand-edited lock would bypass rather than resolve
  the reviewed dependency failure.
- **Continue ad-hoc global installs** — rejected because the resolved graph and ambient npm state
  are not durable, reviewable evidence and can drift independently across runners.
- **Execute candidates before review with lifecycle scripts disabled** — rejected because explicit
  package binary execution remains arbitrary code execution.
- **Require dependency review before generating any promotion PR** — rejected because the inert
  draft is the durable review artifact that binds the candidate lock, source, and complete proposed
  support delta without granting execution authority.

## Consequences

Supported-host evidence is reproducible from repository-owned bytes and a review record, and a
candidate cannot cross the executable boundary by merely being captured. Promotion now requires an
explicit review handoff: automated drafts are expected to remain red at supported-install gates
until the receipt is accepted, after which the ordinary required CI matrix supplies live proof.

Lock and receipt maintenance add repository weight and review ceremony. Promotion recipes must stage
every declared target atomically and prove no unstaged prospective delta remains. Each supported
version update requires a new exact graph and receipt rather than a version-string-only edit, but it
does not require a new architecture decision when these boundaries remain unchanged.

## Risks

A forged or incomplete receipt, unpinned registry command, ambient npm configuration, or accidental
pre-review binary invocation could reopen the supply-chain boundary. A draft could also be mistaken
for validated runtime support if its static checks are described imprecisely, or omit a declared
generated/current projection if staging drifts from the promotion plan.

This decision is proven wrong if supported Pi execution can occur without the exact reviewed graph,
if a pending candidate executes before review, if reviewed-PR CI does not supply live supported-host
proof, if the process prevents routine advancement to reviewed upstream Pi releases, or if promotion
can commit only a subset of its declared atomic target set.
