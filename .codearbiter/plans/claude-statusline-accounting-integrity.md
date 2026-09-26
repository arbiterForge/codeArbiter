# Plan — Claude statusline accounting integrity

**Status:** DRAFT — awaiting plan approval; no implementation authority  
**Date:** 2026-09-26  
**Slug:** `claude-statusline-accounting-integrity`  
**Source spec:** `.codearbiter/specs/claude-statusline-accounting-integrity.md` — APPROVED 2026-09-26  
**Branch for planning artifacts:** `spec/claude-statusline-accounting-integrity`

## Planning gate

This plan was derived against the approved Markdown spec, `.codearbiter/CONTEXT.md` (stage 2), `.codearbiter/tech-stack.md`, `.codearbiter/coding-standards.md`, the live canonical accounting code on `main`, and the repository's `writing-plans` contract.

The GitHub connector used to author this PR cannot execute the repository-local `_intentlib.py uncovered-intent` command. Therefore **T-01 is a mandatory pre-implementation gate**, not optional bookkeeping: implementation does not begin unless the executable backstop returns empty against the exact spec bytes in this PR. The manual Phase-1 review found no uncovered in-scope intent.

Negative-judgment question: **if every AC below passed and nothing else changed, what could still be broken?** Actual Anthropic billing could still differ because some billable activity or modifiers may be unobservable locally. That is explicitly outside the product claim and is covered by AC-01/02/14/16/21/29/31: the statusline must label reconstructed/list-price and host-reported estimates honestly rather than claim invoice equivalence. No additional in-scope criterion was identified.

## Architecture

Use one new pure stdlib helper, `core/pysrc/_usagelib.py`, as the single owner of transcript usage normalization, request identity/reconciliation, pricing lookup, cache reconciliation, separately metered charge extraction, and per-event cost calculation.

Keep `core/pysrc/_ledgerlib.py` as the filesystem/persistence owner. Replace the current one-parent `reqs + tx_off` shape with a versioned per-source session record:

- parent transcript = one source;
- every discovered `<session>/subagents/*.jsonl` transcript = one source;
- each source owns path/generation, byte offset, normalized request map, backlog state, and source-local anomaly/coverage facts;
- session/day totals are derived from normalized requests rather than persisted as an independent source of truth;
- Claude's `cost.total_cost_usd` is persisted under a separate host-estimate structure.

`_subagentslib.py` keeps its bounded presentation scan but calls the shared normalizer/reconciler instead of maintaining a second usage definition.

The primary renderer remains a thin consumer of structured ledger totals and coverage state. It does not discover pricing or decide completeness itself.

## Pricing baseline for implementation

At implementation time, revalidate the shipped registry against Anthropic's official pricing pages before accepting T-03. The review that produced the spec observed these 2026-09-26 examples:

- Claude Opus 5.5: $4 input / $20 output / $5 5m cache write / $8 1h cache write / $0.20 cache read per MTok.
- Claude Sonnet 5: $2 / $10 / $2.50 / $4 / $0.20.
- Claude Fable 5.1: $10 / $50 / $12.50 / $20 / $0.25.
- Claude Haiku 4.5: $1 / $5 / $1.25 / $2 / $0.10.
- Web search: $10 per 1,000 successful searches in addition to token charges.

These values are **plan context, not permanent authority**. The implementation registry must record its own capture date/source and tests must pin the exact values accepted in the candidate.

## Acceptance-criteria ledger

| AC | Criterion |
|---|---|
| AC-01 | Reconstructed API-equivalent owns Session/Today dollars; complete = `api≈`, partial/catching-up = `api≥`, known-unpriceable never becomes a precise total. |
| AC-02 | Host estimate is an explicit Session-only fallback (`host≈`); never fabricated into Today. |
| AC-03 | Parent + delegated transcripts sum exactly to independent fixture totals. |
| AC-04 | Accounting is not constrained by recent-subagent presentation limits. |
| AC-05 | Work beyond `TX_MAX_NEW_LINES` is deferred, never skipped; repeated scans converge exactly once. |
| AC-06 | The scan bound is real and does not `read()` the unbounded remainder before limiting work. |
| AC-07 | Partial trailing lines do not advance past incomplete bytes and are consumed once when complete. |
| AC-08 | Request identities are source-scoped. |
| AC-09 | Malformed/unhashable/missing identities cannot raise or wedge progress. |
| AC-10 | Duplicate cumulative usage is monotonic: smaller/equal replay cannot reduce totals; larger replay can extend them once. |
| AC-11 | Conflicting request model identity becomes ambiguous/partial, not last-write-wins pricing. |
| AC-12 | Current Opus/Sonnet/Fable/Haiku exact pricing is tested. |
| AC-13 | Historical model pricing that differs from current family pricing is tested. |
| AC-14 | Unknown/custom models contribute tokens but never borrow arbitrary pricing; monetary coverage becomes partial. |
| AC-15 | Cache read/write aggregate and TTL split cases reconcile without token loss or invented TTL. |
| AC-16 | Recognized separately metered server tools add exact charges; unknown non-zero counters make coverage partial. |
| AC-17 | Parent usage crossing local midnight splits both tokens and reconstructed cost correctly. |
| AC-18 | Delegated usage crossing midnight follows the same event-time split. |
| AC-19 | Missing/null/malformed later host estimate does not erase prior valid host state or reconstructed cost. |
| AC-20 | Same-session host regression is recorded without erasing max or reconstructed spend; a new session may start from zero. |
| AC-21 | Host/reconstructed disagreement preserves both independently; no `max`, addition, or replacement. |
| AC-22 | Bounded source scheduling is starvation-free and eventually reaches every unchanged source EOF. |
| AC-23 | Truncation/replacement rebuilds only the affected source. |
| AC-24 | Burn samples use accepted normalized usage; this plan deliberately retains **parent-only burn** and documents/tests that scope. |
| AC-25 | Production-shaped legacy ledger migrates without deletion and never reinterprets old `host_cost` as reconstructed cost. |
| AC-26 | Corrupt legacy state fails soft without contaminating healthy records. |
| AC-27 | Same/distinct-session concurrency preserves source state, offsets, requests, totals, and session-start data. |
| AC-28 | Owned statusline writes `refreshInterval: 2` and backup/refresh/uninstall remain exact. |
| AC-29 | No render-time network or live pricing/billing fetch. |
| AC-30 | I/O races, malformed input, unknown models, and lock contention degrade locally and never traceback/blank the bar. |
| AC-31 | All public/source vocabulary distinguishes `api≈`, `api≥`, `host≈`, and actual billing honestly. |
| AC-32 | Canonical Python changes originate in `core/pysrc/` and generated copies are byte-synchronized. |
| AC-33 | Existing unrelated statusline/ledger behavior remains green. |
| AC-34 | Focused tests, full hooks, generated checks, docs/site, and exact-head CI all pass. |

## Ordered tasks

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-01 | Run the mandatory intent-completeness backstop on the exact approved spec before implementation. Stop on any output; repair the spec rather than adding an ungoverned task. | `.codearbiter/specs/claude-statusline-accounting-integrity.md` | `python core/pysrc/_intentlib.py uncovered-intent .codearbiter/specs/claude-statusline-accounting-integrity.md` returns empty | TDD preflight: acceptance ledger completeness | AC-34 | — | PENDING |
| T-02 | Add a dedicated shared-usage test module with current/historical price fixtures and prove the existing family fallback cannot satisfy them. | `plugins/ca/hooks/tests/test_usagelib.py` (new) | `python -m unittest discover -s plugins/ca/hooks/tests -p "test_usagelib.py" -v` is red for exact current/historical pricing and unknown-model behavior before implementation | TDD pricing obligations | AC-12, AC-13, AC-14 | T-01 | PENDING |
| T-03 | Introduce the version-aware pricing registry and exact model matcher; remove any unknown→Sonnet semantic from the new pricing path. Record capture date/source next to the registry. | `core/pysrc/_usagelib.py` (new) | T-02 pricing cases green; `python -m py_compile core/pysrc/_usagelib.py` | TDD exact/unknown pricing | AC-12, AC-13, AC-14, AC-29 | T-02 | PENDING |
| T-04 | Add red cache normalization fixtures: no cache, cache read, 5m, 1h, aggregate-only, matching aggregate+split, partial split, inconsistent split. | `plugins/ca/hooks/tests/test_usagelib.py` | Focused unittest is red on aggregate remainder/unknown-TTL cases before code change | TDD cache normalization | AC-15 | T-03 | PENDING |
| T-05 | Implement pure normalized usage records with finite/non-negative numeric validation and lossless cache reconciliation, retaining unpriced cache-write remainder separately. | `core/pysrc/_usagelib.py` | T-04 green; malformed/string/negative/non-finite fixtures return bounded normalized results, never raise | TDD cache + malformed input | AC-09, AC-15, AC-30 | T-04 | PENDING |
| T-06 | Add red server-tool charge fixtures for recognized web-search counters and unknown non-zero server-tool counters. | `plugins/ca/hooks/tests/test_usagelib.py` | Focused unittest red before implementation; independent expected dollars hard-coded from fixture facts | TDD charge classes | AC-16 | T-05 | PENDING |
| T-07 | Implement extensible charge-class extraction/pricing, initially including web-search requests; unknown non-zero charge classes mark pricing partial. | `core/pysrc/_usagelib.py` | T-06 green; recognized charge counted once, unknown retained as an unpriceable reason | TDD non-token charges | AC-16, AC-29 | T-06 | PENDING |
| T-08 | Add red request-identity/replay cases: same source duplicate larger/equal/smaller, unhashable IDs, missing IDs, and conflicting models. | `plugins/ca/hooks/tests/test_usagelib.py` | Focused unittest red before reconciliation implementation | TDD request reconciliation | AC-09, AC-10, AC-11 | T-05 | PENDING |
| T-09 | Implement source-local deterministic identity and monotonic request reconciliation; conflicting non-equivalent model identities make pricing ambiguous rather than choosing the last line. | `core/pysrc/_usagelib.py` | T-08 green; independent aggregate of accepted normalized records matches fixtures | TDD request reconciliation | AC-08, AC-09, AC-10, AC-11 | T-08 | PENDING |
| T-10 | Refactor bounded subagent presentation parsing to consume the shared normalizer/reconciler without changing recent-file, row-count, label, or liveness bounds. | `core/pysrc/_subagentslib.py`, `plugins/ca/hooks/tests/test_statusline.py` | existing subagent tests + new duplicate/cache cases green; visible row counts unchanged | TDD one-normalizer presentation parity | AC-24, AC-30, AC-33 | T-09 | PENDING |
| T-11 | Add red parent streaming tests at `TX_MAX_NEW_LINES-1`, exact, +1, and multiple chunks; assert first-call offset equals last consumed record, not EOF. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test is red on current implementation's +1 case | TDD bounded streaming | AC-05, AC-06 | T-09 | PENDING |
| T-12 | Replace whole-tail `f.read()` accounting with bounded binary line streaming; persist the offset after the last consumed complete record. | `core/pysrc/_ledgerlib.py` | T-11 green and the test spies/fixture proves no unbounded whole-tail read occurs | TDD bounded streaming | AC-05, AC-06 | T-11 | PENDING |
| T-13 | Add red partial-line, malformed JSON, valid non-object JSON, and malformed identity progress tests; poison records must not wedge the same byte forever. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused tests red where current offset/identity behavior is unsafe | TDD forward progress | AC-07, AC-09, AC-30 | T-12 | PENDING |
| T-14 | Make source scanning advance only across complete consumed lines, degrade malformed records locally, and retry an incomplete trailing line after it is completed. | `core/pysrc/_ledgerlib.py` | T-13 green; appended completion is consumed exactly once | TDD forward progress | AC-07, AC-09, AC-30 | T-13 | PENDING |
| T-15 | Add a production-shaped legacy-ledger migration fixture covering `reqs`, `tx_off`, `tx_path`, `host_cost`, `today`, `sess_start`, and a corrupt sibling shard. | `plugins/ca/hooks/tests/test_ledgerlib.py` | new migration test is red before schema migration; fixture never treats old `host_cost` as reconstructed cost | TDD migration | AC-25, AC-26 | T-14 | PENDING |
| T-16 | Introduce a versioned `sources` representation and migrate the current parent transcript state into a parent source; preserve valid session metadata and force safe replay where old cached semantics cannot be trusted. | `core/pysrc/_ledgerlib.py` | T-15 green; no user deletion required; reconstructed total comes only from replayed normalized usage | TDD migration | AC-25, AC-26 | T-15 | PENDING |
| T-17 | Add source-scoping tests proving identical request IDs in parent and child source maps remain independent. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test red before multi-source aggregation | TDD source namespace | AC-08 | T-16 | PENDING |
| T-18 | Add delegated-source discovery fixtures for 0/1/12/13/many child transcripts, including children older than `SHOW_WINDOW`. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused tests red before accounting discovery; UI presentation assertions remain bounded | TDD delegated discovery | AC-03, AC-04 | T-16 | PENDING |
| T-19 | Implement ledger-owned discovery of the current parent's delegated transcript directory and durable per-child source state, independent of `_subagentslib` presentation windows. | `core/pysrc/_ledgerlib.py` | T-17/T-18 green; 13th and old child both contribute to accounting | TDD delegated source persistence | AC-03, AC-04, AC-08 | T-17, T-18 | PENDING |
| T-20 | Add a red independent-total fixture with mixed models/cache/tool charges across parent and multiple children. Expected tokens/cost are calculated in test constants, not via production aggregators. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test red before multi-source aggregation | TDD all-source totals | AC-03, AC-12, AC-15, AC-16 | T-19 | PENDING |
| T-21 | Aggregate Session tokens and reconstructed cost across normalized per-source requests; remove host-cost override from the reconstructed Session result. | `core/pysrc/_ledgerlib.py` | T-20 green; setting host cost above/below expected reconstructed value does not change reconstructed result | TDD reconstructed source of truth | AC-01, AC-03, AC-21 | T-20 | PENDING |
| T-22 | Add parent cross-midnight fixtures with events priced differently on yesterday/today and assert Session=sum(all), Today=sum(today only) for both tokens and cost. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test red on current whole-session Today cost logic | TDD calendar attribution | AC-17 | T-21 | PENDING |
| T-23 | Derive per-day reconstructed totals from normalized event timestamps; delete whole-session `host_cost` attribution from Today. | `core/pysrc/_ledgerlib.py` | T-22 green; Today no longer changes when only yesterday's event cost changes | TDD calendar attribution | AC-17, AC-02 | T-22 | PENDING |
| T-24 | Add delegated cross-midnight fixture, including a child started yesterday and completed today. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test passes only when child event timestamps split identically to parent | TDD delegated calendar attribution | AC-18 | T-23 | PENDING |
| T-25 | Add source truncation/replacement fixtures proving one child rebuild does not erase parent/sibling requests. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused test red before per-source generation reset | TDD source replacement isolation | AC-23 | T-19 | PENDING |
| T-26 | Add source generation/fingerprint handling and isolated reset/replay on truncation/replacement. | `core/pysrc/_ledgerlib.py` | T-25 green; unaffected sources byte/logical-state equal before/after | TDD source replacement isolation | AC-23, AC-30 | T-25 | PENDING |
| T-27 | Add red backlog/coverage fixtures for complete, catching-up, partial-unknown-model, partial-unknown-tool, and unavailable reconstruction. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused tests red before structured coverage is returned | TDD coverage semantics | AC-01, AC-12, AC-14, AC-16, AC-22 | T-21 | PENDING |
| T-28 | Return structured reconstruction coverage + reason set from the ledger; a numeric subtotal alone can no longer imply completeness. | `core/pysrc/_ledgerlib.py` | T-27 green; newly discovered unscanned child reports catching-up immediately | TDD coverage semantics | AC-01, AC-14, AC-16, AC-22 | T-27 | PENDING |
| T-29 | Add starvation fixture: large continuously-growing parent plus enough children to exceed one render budget; repeated unchanged-budget calls must eventually touch every source and converge. | `plugins/ca/hooks/tests/test_ledgerlib.py` | test red before fair scheduling; deterministic finite number of calls reaches complete | TDD eventual completeness | AC-22 | T-28 | PENDING |
| T-30 | Implement deterministic fair/round-robin source scheduling with a persisted cursor or equivalent stable mechanism; bounded work cannot starve parent or children. | `core/pysrc/_ledgerlib.py` | T-29 green; each call remains within declared source/record budget | TDD eventual completeness | AC-05, AC-06, AC-22 | T-29 | PENDING |
| T-31 | Add host-estimate tests: valid→absent/null/malformed, increase, same-session decrease, new-session reset, host above/below reconstructed. | `plugins/ca/hooks/tests/test_ledgerlib.py` | focused tests red on current zero-coercion/override behavior | TDD host reconciliation | AC-19, AC-20, AC-21 | T-21 | PENDING |
| T-32 | Persist host estimate separately (`latest`, `max_seen`, presence/regression state, optional delta when reconstruction complete); never substitute it into reconstructed totals. | `core/pysrc/_ledgerlib.py` | T-31 green; reconstructed totals byte/value-identical across host-estimate variations | TDD host reconciliation | AC-19, AC-20, AC-21 | T-31 | PENDING |
| T-33 | Retain the burn sparkline as **parent-only** but derive it from accepted normalized parent requests; add explicit scope tests so child spend cannot accidentally alter the existing burn UX. | `core/pysrc/_ledgerlib.py`, `plugins/ca/hooks/tests/test_ledgerlib.py` | burn replay/dedupe tests green; adding child-only usage leaves parent burn samples unchanged | TDD burn semantics | AC-24, AC-33 | T-10, T-21 | PENDING |
| T-34 | Extend concurrency fixtures to the new multi-source schema: same-session competing scans, distinct sessions, session-start metadata write during accounting, and interrupted atomic replace. | `plugins/ca/hooks/tests/test_ledgerlib.py` | concurrency suite red on any source/offset/request regression; existing serialization harness retained | TDD persistence integrity | AC-27 | T-26, T-30, T-32 | PENDING |
| T-35 | Reconcile multi-source writes under the existing lock/shard model so concurrent renders cannot regress offsets or accepted requests; preserve targeted `sess_start` overlay behavior. | `core/pysrc/_ledgerlib.py` | T-34 green; existing concurrency tests remain green | TDD persistence integrity | AC-27, AC-30 | T-34 | PENDING |
| T-36 | Add renderer tests for complete `api≈`, catching-up/partial `api≥`, unpriceable `api≈?`, Session `host≈` fallback, and Today no-host fallback. | `plugins/ca/hooks/tests/test_statusline.py`, `plugins/ca/hooks/tests/test_ledgerlib.py` | focused tests red before rendering contract update; width/NO_COLOR assertions included | TDD user-facing semantics | AC-01, AC-02, AC-30, AC-33 | T-28, T-32 | PENDING |
| T-37 | Update the ledger→renderer contract and usage-row rendering so statusline labels reflect structured coverage; preserve existing box layout/width safety. | `core/pysrc/statusline.py`, `core/pysrc/_segmentslib.py` | T-36 green; `python -m py_compile core/pysrc/statusline.py core/pysrc/_segmentslib.py` | TDD user-facing semantics | AC-01, AC-02, AC-30, AC-33 | T-36 | PENDING |
| T-38 | Add wire/install tests for `refreshInterval: 2`, exact prior-statusline backup/restore, self-heal refresh, and third-party statusline preservation. | `plugins/ca/hooks/tests/test_wire_statusline.py` | focused test red because owned statusline currently lacks refresh interval | TDD background refresh | AC-28 | T-01 | PENDING |
| T-39 | Add `refreshInterval: 2` to codeArbiter-owned statusline settings without changing ownership recognition or backup semantics. | `core/pysrc/wire-statusline.py` | `python plugins/ca/hooks/tests/test_wire_statusline.py -v` green after sync; fresh install/refresh/uninstall fixtures exact | TDD background refresh | AC-28 | T-38 | PENDING |
| T-40 | Add/extend fail-soft regression matrix for vanished child dirs/files, permission errors, malformed source records, unknown model/tool, and ledger lock contention through `render()`. | `plugins/ca/hooks/tests/test_statusline.py`, `plugins/ca/hooks/tests/test_ledgerlib.py` | focused statusline + ledger tests green with no traceback/blank render | TDD robustness | AC-29, AC-30, AC-33 | T-35, T-37 | PENDING |
| T-41 | Synchronize canonical Python to all generated host copies and prove byte parity before running tests that import vendored hooks. | `tools/sync-core.py`, generated `plugins/ca/hooks/*`, `plugins/ca-codex/hooks/*`, `plugins/ca-pi/hooks/*` | `python tools/sync-core.py` then `python tools/sync-core.py --check` and `python .github/scripts/test_sync_core.py` | Generated-source parity | AC-32 | T-03, T-05, T-07, T-09, T-10, T-12, T-14, T-16, T-19, T-21, T-23, T-26, T-28, T-30, T-32, T-33, T-35, T-37, T-39 | PENDING |
| T-42 | Run the focused Python accounting/statusline/wire suite on synchronized bytes; fix only spec-governed failures before broader tests. | `plugins/ca/hooks/tests/test_usagelib.py`, `test_ledgerlib.py`, `test_statusline.py`, `test_wire_statusline.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p "test_usagelib.py" -v` plus direct/focused ledger/statusline/wire tests all green | Focused verification | AC-03–AC-30, AC-32, AC-33 | T-41 | PENDING |
| T-43 | Correct source comments and command documentation so the renderer no longer claims host cost is real/authoritative/bill-equivalent; document parent-only burn and all three monetary labels. | `core/pysrc/statusline.py`, `core/pysrc/_ledgerlib.py`, `core/pysrc/_segmentslib.py`, `core/surface/commands/statusline.md` | grep/structural assertions added or updated; generated command docs regenerated and contain `api≈`/`api≥`/`host≈` with no prohibited authoritative-billing claim | Documentation contract | AC-24, AC-31 | T-37 | PENDING |
| T-44 | Update the public statusline guide and fixture/screenshot commentary to the reconstructed-vs-host contract; explain partial coverage and background refresh without promising actual billing. | `site/src/content/docs/guides/the-statusline.md`, `tools/statusline-screenshot.py`, relevant `site/test/**` assertions | `npm --prefix site test` green; documentation tests assert the new vocabulary and reject the old claim | Documentation contract | AC-28, AC-31, AC-33 | T-43 | PENDING |
| T-45 | Regenerate shared surface copies after command-doc changes and prove both source generators are clean. | `core/surface/commands/statusline.md`, generated command surfaces | `python tools/build-surface.py` then `python tools/build-surface.py --check`; `python tools/sync-core.py --check` | Generated docs parity | AC-31, AC-32 | T-43 | PENDING |
| T-46 | Run the spec's full adversarial accounting matrix as deterministic unittests and close any combination gaps not already exercised by focused tasks. | `plugins/ca/hooks/tests/test_usagelib.py`, `plugins/ca/hooks/tests/test_ledgerlib.py`, `plugins/ca/hooks/tests/test_statusline.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` green; matrix includes 0/1/12/13/many children, limit boundaries, replay variants, midnight, host disagreement, migration, and narrow/wide render | Adversarial acceptance proof | AC-03–AC-30, AC-33 | T-42, T-44, T-45 | PENDING |
| T-47 | Advance affected package versions/changelogs according to current release invariants because sync changes shipped files under all governance adapters; regenerate the root Pi package manifest where required. | `plugins/ca/.claude-plugin/plugin.json`, `CHANGELOG.md`, README version badge if required, `plugins/ca-codex/.codex-plugin/plugin.json`, `plugins/ca-codex/CHANGELOG.md`, `plugins/ca-pi/package.json`, `plugins/ca-pi/CHANGELOG.md`, root `package.json` | current version-guard tests green; `python tools/build-host-packages.py` then `--check`; no unchanged tagged plugin version carries modified shipped bytes | Release/package consistency | AC-32, AC-34 | T-46 | PENDING |
| T-48 | Run full repository verification relevant to the touched surfaces: compile, hooks, sync/build checks, site, refs, host packages, and the repository's CI-impact-selected local gates. | touched Python, generated hosts, site/docs, package manifests | `python -m py_compile core/pysrc/_usagelib.py core/pysrc/_ledgerlib.py core/pysrc/_subagentslib.py core/pysrc/_segmentslib.py core/pysrc/statusline.py core/pysrc/wire-statusline.py`; `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"`; `python tools/sync-core.py --check`; `python tools/build-surface.py --check`; `python tools/build-host-packages.py --check`; `python .github/scripts/check-plugin-refs.py`; `npm --prefix site test` | Full local verification | AC-29, AC-30, AC-31, AC-32, AC-33, AC-34 | T-47 | PENDING |
| T-49 | Open/update the implementation PR only after the exact candidate passes local gates; require hosted exact-head CI before any completion/merge claim. Retain the independent fixture arithmetic and pricing-capture evidence in the PR body. | implementation PR metadata; no product source path | GitHub exact-head checks green; PR body answers all ten Completion Evidence questions from the spec | Final acceptance/review evidence | AC-12, AC-13, AC-16, AC-25, AC-27, AC-34 | T-48 | PENDING |

## MVP slice

**MVP = T-01 through T-49.**

There is no honest smaller shippable slice. The failures are coupled by the meaning of the displayed dollar value: landing only streaming fixes, only child aggregation, only pricing, or only renderer labels would leave the same number carrying mutually incompatible semantics. The implementation can be committed/reviewed in checkpoints, but no intermediate checkpoint is a release candidate.

Recommended internal checkpoints:

1. **CP-1 — Normalization/pricing:** T-01..T-10.
2. **CP-2 — Durable multi-source scanner/migration:** T-11..T-19.
3. **CP-3 — Aggregation/calendar/coverage/reconciliation:** T-20..T-35.
4. **CP-4 — Renderer/background refresh/fail-soft:** T-36..T-40.
5. **CP-5 — Generation/docs/adversarial proof:** T-41..T-46.
6. **CP-6 — Packaging/exact-head release proof:** T-47..T-49.

## Dependency notes

- T-16 migration intentionally precedes delegated aggregation. Old `host_cost` cannot be allowed to masquerade as reconstructed state for even one intermediate implementation.
- T-21 reconstructed aggregation precedes host reconciliation. Otherwise tests can accidentally continue treating the host estimate as the monetary source of truth.
- T-28 coverage state precedes renderer changes. The renderer must consume a typed/structured fact rather than infer partiality from a number.
- T-41 sync occurs only after canonical Python behavior is coherent enough to test through the vendored test imports.
- T-47 versioning is deliberately late: version numbers describe the final shipped byte set, not an intermediate checkpoint.

## Criterion-to-task bijection

| Criterion | Tasks |
|---|---|
| AC-01 | T-21, T-27, T-28, T-36, T-37 |
| AC-02 | T-23, T-36, T-37 |
| AC-03 | T-18, T-19, T-20, T-21, T-46 |
| AC-04 | T-18, T-19, T-46 |
| AC-05 | T-11, T-12, T-30, T-46 |
| AC-06 | T-11, T-12, T-30, T-46 |
| AC-07 | T-13, T-14, T-46 |
| AC-08 | T-09, T-17, T-19, T-46 |
| AC-09 | T-05, T-08, T-09, T-13, T-14, T-46 |
| AC-10 | T-08, T-09, T-46 |
| AC-11 | T-08, T-09, T-46 |
| AC-12 | T-02, T-03, T-20, T-27, T-49 |
| AC-13 | T-02, T-03, T-49 |
| AC-14 | T-02, T-03, T-27, T-28, T-46 |
| AC-15 | T-04, T-05, T-20, T-46 |
| AC-16 | T-06, T-07, T-20, T-27, T-28, T-49 |
| AC-17 | T-22, T-23, T-46 |
| AC-18 | T-24, T-46 |
| AC-19 | T-31, T-32, T-46 |
| AC-20 | T-31, T-32, T-46 |
| AC-21 | T-21, T-31, T-32, T-46 |
| AC-22 | T-27, T-28, T-29, T-30, T-46 |
| AC-23 | T-25, T-26, T-46 |
| AC-24 | T-10, T-33, T-43 |
| AC-25 | T-15, T-16, T-49 |
| AC-26 | T-15, T-16, T-46 |
| AC-27 | T-34, T-35, T-49 |
| AC-28 | T-38, T-39, T-44 |
| AC-29 | T-03, T-07, T-40, T-48 |
| AC-30 | T-05, T-10, T-13, T-14, T-26, T-35, T-36, T-37, T-40, T-48 |
| AC-31 | T-43, T-44, T-45, T-48 |
| AC-32 | T-41, T-45, T-47, T-48 |
| AC-33 | T-10, T-33, T-36, T-37, T-40, T-44, T-46, T-48 |
| AC-34 | T-01, T-47, T-48, T-49 |

Every AC has at least one task and every task advances at least one AC. This is the plan/spec bijection only; semantic completeness remains gated by T-01 and the negative-judgment review above.

## Parallelization after the gates

After T-01, these can proceed concurrently until their dependency joins:

- **Pricing/normalization:** T-02..T-09.
- **Background-refresh installer:** T-38..T-39.
- **Documentation test preparation:** tests for T-44 may be authored red in parallel, but the final wording waits on T-37/T-43.
- **Migration fixture design:** T-15 can be prepared once the intended source schema from T-16 is sketched, but T-16 cannot land before the bounded scanner T-14.
- **Renderer tests:** T-36 fixture scaffolding can begin after the coverage-result shape in T-27 is fixed, while T-31/T-32 host reconciliation finishes.

Do **not** parallel-edit generated `plugins/*/hooks` copies. One integration owner runs `sync-core.py` and `build-surface.py` at T-41/T-45.

## Rollback and compatibility

The implementation must be rollback-safe at the repository level:

- no network migrations;
- no destructive rewrite outside the existing user-local ledger;
- legacy ledger replay is deterministic and fail-soft;
- a failed new-schema write leaves the prior valid target intact through atomic replacement;
- uninstall restores the exact prior Claude `statusLine` object, including any pre-existing refresh setting.

If implementation discovers that current Claude transcript layout cannot durably associate a class of child session with the parent without guessing, stop and surface that source as unobservable/partial. Do not broaden directory walks across unrelated sessions to make totals look complete.

## Completion condition

The implementation is complete only when T-49 is accepted and every task is `ACCEPTED`. A locally green focused suite is not completion; hosted exact-head CI and the spec's ten Completion Evidence answers are required.
