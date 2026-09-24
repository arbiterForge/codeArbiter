# PR #852: original-publication receipt reconciliation

Date: 2026-09-24 (America/New_York)
Inspected PR head: `831e22bc11ea93eab07098a509ba9ec68f77e073`
Integrated origin: `cf90ce4d79c5d87cb88f163535c1035da2315815`

## Failure and bounded correction

Normal CI run `35960703378`, job `107508442465`, rejected three published
`.12` tags missing from the disjoint publication ledgers. This was a missing
record, not evidence of a tag move. Append only their original annotated-tag
identities to `.github/published-tags.json`. Preserve all 163 existing records,
ledger metadata, and all 44 legacy baselines. No release tag, release asset,
publisher, package version, or security check changes in this correction.

## Claim-specific source evidence

The original successful publisher was run `35957243864`, attempt 1, executing
`.github/workflows/release.yml` at
`cf90ce4d79c5d87cb88f163535c1035da2315815`. All three tags dereference to that
commit. Authenticated artifact metadata, downloaded receipt bytes, original job
logs, current remote refs, and peeled tag objects were checked independently.
Current remote refs alone were not used as original-publication evidence.

| Tag | Receipt artifact | Original job | Annotated tag object |
|---|---|---|---|
| `v2.21.12` | `10790504318` | `107498192151` | `ef157eab229c8f143c0d13444a45e62b6c571499` |
| `ca-codex-v0.13.12` | `10791186306` | `107498414352` | `67dff985d712eaae5a5bc829821244ea7f29867d` |
| `ca-pi-v0.14.12` | `10790577928` | `107498693023` | `ca1605b16e745bc7a19d76912c499f48d6b61156` |

Receipt ZIP SHA-256 values, in table order:

```text
79cea7db741fac072c4f859f0631f0564084273d5713dadce96b41c2b4e5a962
1d5f0dc30344e4f50eb136339293da144bdd9c228e1e990f9453edb5afc20986
e4a50f2366794e7c63ecb20528c5ddcd0e60e6209782aac1fd56f60cd28089b1
```

Each original job records both a successful `[new tag]` push and the
`marker_durable_tag_created` outcome before receipt capture. The observations
occurred at 04:50:03Z, 04:51:13Z, and 04:52:29Z respectively on September 24.
The existing `reconcile_tag_receipt.py` validated each candidate against the
expected repository, tag, commit, run, attempt, workflow, and both input-ledger
hashes. Only the three new objects' JSON member order was normalized for
repeatable byte identity; their validated values and all prior records are unchanged.

## Fresh verification

Run `35962136443`, attempt 1, preparation commit
`19c9bbc9c8681861bf31362c2174edc6d181dfa5`, passed receipt authentication,
74 tag-immutability tests, 16 publication-receipt tests, 20 reconciliation tests,
and the live `--require-recorded` audit. The audit reported 166 original receipts
and 44 legacy baselines resolving to their recorded identities.

Artifact `10792806187` retains the receipts, exact original-log observations,
commands, test logs, live audit, and final ledger. Its ZIP SHA-256 is
`ac2d54f542fd7d9e84101752b12287e4e74ef756bc018a756aa801303f66a2d6`.
Downloaded ledger bytes exactly match the locally reviewed candidate:

- SHA-256: `d43bcac76e40ccc2ed85c0fe5bb487ab98d907e645c7e0b1605028c8d44d6792`
- Git blob: `e44f749f8e068e5df6e78bc69d26ffb3e57d700e`

The preparation verifier held read-only repository permissions. A separate
write-permission job stored only the hash-checked ledger blob and advanced no
reference. Preparation-only files are not part of the product change.

## Separate macOS Pi diagnostic

The same PR CI run's macOS Pi job `107508472867` failed during the unchanged
`npm audit signatures` step before adapter tests. A controlled repeat in job
`107510890958`, run `35961511872`, used the same PR source, Node 22.19.0,
locked Pi 0.84.1 graph, scripts-disabled installation, and unchanged signature
audit; it passed. Artifact `10792098999` records the actual result, ZIP SHA-256
`1acbd17f94a8018862cbfd3a53b5db22dceb6aada62e82bd6afa07aa94039404`.
This does not establish the original failure's root cause or substitute for the
normal adapter job. No dependency, retry policy, or signature requirement was
changed merely to obtain a green result.

## Remaining boundary

The changed release skill still needs its actual independent bounded exercise.
Its historical proof record was not relabeled. Deterministic archive tests and
this receipt repair do not confer that authority. Normal CI must assess the
final committed PR head; this report does not claim that aggregate passed.
Codex live-model proof follows publication under upstream PR #853; pre-release
static, cold-execution, provenance, and other applicable gates remain intact.

No merge, publication, issue closure, tag mutation, or legacy-baseline rewrite
was performed. Rollback is a reviewed follow-up on the PR, never deletion or
retargeting of the published tags this ledger records.
