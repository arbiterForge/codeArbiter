---
status: accepted
date: 2026-09-02
title: Bind accepted ADRs to sealed obligations and current verification evidence
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .codearbiter/decisions/**, core/surface/skills/decision-lifecycle/**, core/surface/includes/smarts/**, core/surface/includes/routing-table.md, core/surface/arbiter.md, .github/scripts/check_adr_*.py, .github/scripts/test_adr_*.py, .github/scripts/test_routing_and_cleanup_surface.py, .github/workflows/ci.yml
---

# ADR-0033 — Bind accepted ADRs to sealed obligations and current verification evidence

## Status
Accepted — explicitly approved for authoring and acceptance by
SUaDtL@users.noreply.github.com on 2026-09-02.

## Context

An accepted ADR records governance approval, not delivery. The current lifecycle exposes accepted
alongside proposed, superseded, and rejected, but has no distinct implementation or verification
evidence. That gap is observable: accepted ADR-0026 requires an authoritative destructive-operation
registry and parity checker that do not yet exist. Accepted ADR bodies also have no immutable
acceptance binding, so a later in-place body edit cannot be rejected mechanically.

The repository already has an append-only SMARTS decision log, but that log records arbitration. Its
historical entries are heterogeneous and frequently have no cited artifact hash. Reinterpreting it as
a complete delivery ledger would invent evidence and couple two distinct lifecycles.

## Decision

The stored ADR governance states remain `proposed`, `accepted`, `superseded`, and `rejected`.
`accepted` is displayed as **Accepted/Planned**: it never implies implementation or verification.
Implemented and Verified are derived delivery states, not mutable ADR frontmatter values.

A separate append-only `.codearbiter/decisions/adr-lifecycle.jsonl` is the machine-readable delivery
ledger. Future acceptance appends exactly one immutable acceptance binding for the ADR's canonical
full filename stem. That binding records the acceptance commit, the SHA-256 of the exact committed
Git blob, a separately specified SHA-256 over the immutable decision body, and the digest of a sealed
authoritative obligation set. A second acceptance binding for the same stem is invalid.

Each normative obligation has a stable stem-scoped identifier and an exact ADR section/content
binding. An ADR is Implemented only when every obligation in its sealed set has append-only,
input-bound implementation evidence. It is Verified only when every sealed obligation has fresh,
input-bound verification evidence produced under an explicit proof contract. Evidence records bind
the source commit, relevant input digests, producer, command or workflow identity, observation time,
and freshness rule. Changed inputs invalidate the derived state; they do not rewrite history.

Public and machine-readable reports expose only obligations that are currently Verified at the input
digests being reported. Unsealed, stale, incomplete, or mismatched obligations fail closed with a
diagnostic. A repository proof establishes only the narrow repository claim it actually measures; it
does not imply live-host, publication, support, legal, or other external truth without that boundary's
own approved proof contract.

Legacy accepted ADRs receive explicit migration `baseline` bindings, never fabricated
acceptance-time records. Their obligation sets are mapped incrementally and remain unsealed and
Accepted/Planned until independently reviewed. Age, an old pull request, or a matching digest alone
never promotes a legacy ADR to Implemented or Verified.

The canonical ADR identifier remains the full filename stem. Bare-number compatibility remains only
while a number resolves uniquely. The two historical `0014` files retain their distinct full-stem
identities; neither is renamed or deleted and ambiguous bare-number resolution is never restored.

ADR-0026's already-approved implementation uses ADR-0030's current four-item destructive set:
logged bypass (`/override`), merge to the default branch, branch or worktree deletion, and release and
tag publication. The routing-table registry is authoritative, the arbiter keeps the required resident
projection, and CI proves item-for-item parity with a seeded mismatch.

## Alternatives considered

- **Extend `decision-log.md`** — rejected because it mixes SMARTS arbitration with delivery evidence,
  inherits heterogeneous historical entries, and makes sealed and fresh machine validation fragile.
- **Store delivery fields in ADR frontmatter** — rejected because it rewrites accepted records and
  recreates the acceptance-equals-delivery conflation this decision removes.
- **Treat existing accepted ADRs as implemented or verified** — rejected because repository history
  and matching content do not prove complete obligations or current behavior.

## Consequences

ADR acceptance remains a user-owned governance act while implementation and verification become
mechanically distinct, append-only, and invalidated by stale inputs. Future accepted bodies are
content-bound once, legacy records are migrated truthfully, and public output cannot silently promote
plans into guarantees. Tooling must validate ledger shape, append-only history, unique bindings,
sealed obligation completeness, digest integrity, evidence freshness, and verified-only exports.

## Risks

Manual obligation mapping can omit a normative clause; sealing therefore requires independent review
and a digest over the complete set. A proof contract can be too broad or too weak; exports must retain
its exact claim and input boundary. Git checkout transformations can confuse byte hashing; exact Git
blob bytes and immutable-body canonicalization must be specified separately and tested across line
endings. Legacy migration may remain incomplete for a long time, which is preferable to fabricating
closure. Proven wrong if an accepted body can change without CI failure, an unsealed or stale
obligation appears as Verified, or a repository-only receipt is presented as an external guarantee.
