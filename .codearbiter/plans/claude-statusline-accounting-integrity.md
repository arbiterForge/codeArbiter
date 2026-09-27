# Plan — Claude statusline accounting integrity

**Status:** APPROVED 2026-09-27 by the repository owner (in-session, together with the amended spec)  
**Date:** 2026-09-26 (revised 2026-09-27)  
**Slug:** `claude-statusline-accounting-integrity`  
**Source spec:** `.codearbiter/specs/claude-statusline-accounting-integrity.md`. Amended and APPROVED 2026-09-27.  
**Branch for planning artifacts:** `spec/claude-statusline-accounting-integrity`

## Revision note (2026-09-27)

The original 49-task plan is replaced, not patched. It reconciles `.codearbiter/review.md` and the spec's *Observed transcript semantics*. What changed structurally:

- **One parser.** The original T-10 kept a second, bounded child parser in `_subagentslib`. That is dropped: presentation now reads ledger summaries (spec D-7, AC-50).
- **Session-scoped identity.** The original T-17 proved source-scoped IDs. That is reversed, because fork replays duplicate parent requests into child transcripts (spec D-5, AC-08).
- **Benchmark first.** The base-commit performance benchmark lands immediately after the gates and before any implementation code (spec D-20, AC-39).
- **No periodic refresh.** The original T-38/T-39 (`refreshInterval: 2`) are removed. The installer is proven unchanged instead (spec D-13, AC-28).
- **New work items:**
  - incremental derived totals with partitioned evidence (D-21, AC-40);
  - UI try-lock with snapshot reuse (D-17, AC-41);
  - advisor iterations (D-26, AC-44);
  - modifiers (D-27, AC-45);
  - source lifecycle (D-22, AC-47);
  - discovery bound (D-25, AC-48);
  - oversized records (AC-49);
  - characterized fixtures (AC-51).
- **Four checkpoints.** The runtime work is grouped under the review's four checkpoints (CP-1..CP-4). The red/green task pairs are kept.

## Planning gate

This plan was derived against:

- the amended spec;
- `.codearbiter/review.md`;
- `.codearbiter/CONTEXT.md` (stage 2), `tech-stack.md` and `coding-standards.md`;
- the live canonical code on `main`. The governed files are unchanged from `c3d574a3` through `8e88bce9`.

**T-01 was executed locally on 2026-09-27** against the amended spec bytes: `python core/pysrc/_intentlib.py uncovered-intent .codearbiter/specs/claude-statusline-accounting-integrity.md` returned empty (exit 0). The backstop reads list-item criteria only, which is why the ACs are formatted as list items. T-01 must be re-run on the final approved spec bytes before T-03 begins.

**T-01 was re-run 2026-09-27 on the spec bytes carrying the AC-39 and AC-01 owner amendments.** `uncovered-intent` returned empty (exit 0).

Negative-judgment question: **if every AC below passed and nothing else changed, what could still be broken?**

- **Actual Anthropic billing can still differ.** Some billable activity is unobservable. For example, hidden side queries appear only in host `cost-state` aggregates. Some modifiers may also be unobservable. That is excluded from the product claim, and AC-01/02/14/16/21/29/31 force honest labeling.
- **Future host transcript shape drift.** New iteration types, new server-tool counters or new modifier values are caught *as partial coverage*, not silently. That is covered by AC-44/45/16 and AC-38.

No additional in-scope criterion was identified.

## Architecture

**`core/pysrc/_usagelib.py`** (new, pure, stdlib) holds small functions over immutable tables:

- `classify_identity(record)` → `rid:`/`mid:`/unproven;
- `normalize(record)` → a normalized usage fact: components per (charge class, model), cache total + classification, server-tool counters, modifiers, event timestamp, plus malformed/oversized reasons;
- `merge(evidence, fact)` → commutative/associative reconciliation. It takes the component maximum, refines the cache classification, takes the minimum event time, and detects model conflicts;
- `price(evidence)` → (dollars, unpriceable reasons), using the exact registry, alias table, modifier rules and charge registry.

It has no classes beyond plain data and no filesystem access.

**`core/pysrc/_ledgerlib.py`** remains the persistence owner. It gains:

- a bounded, line-streaming, multi-source scanner (parent + `<session>/subagents/*.jsonl`) with:
  - per-render byte, record and source budgets;
  - a per-record byte ceiling with skip-until-newline;
  - a persisted round-robin cursor;
  - stat-gated head/tail fingerprints;
  - a discovery bound;
- per-session storage split in two:
  - a **compact summary**, read every render: offsets, fingerprints, lifecycle, derived totals, per-day totals, per-scope coverage, presentation summaries, host estimate, burn, schema and registry versions;
  - **partitioned request evidence**, deserialized only for the identities new records touch;
- derived totals maintained by subtract-old/add-new;
- a render-path try-lock (≤ 20 ms) that falls back to the last committed summary, flagged stale;
- migration from the legacy `reqs`/`tx_off` shape.

**`core/pysrc/_subagentslib.py`** no longer opens child JSONL. It renders rows from ledger presentation summaries plus `listdir`/`stat` liveness and optional `*.meta.json` labels.

**`core/pysrc/statusline.py` / `_segmentslib.py`** render `api≈` / `api≥` / `api≈?` / `host≈`, stale and unavailable, from structured per-scope coverage.

**`wire-statusline.py`** is unchanged.

**`tools/statusline-bench.py`** (new) is a deterministic generated-fixture benchmark. It produces structural I/O counters and warm-render timings for a given checkout. Its base report is committed before implementation.

## Pricing baseline for implementation

The official pricing page (`platform.claude.com/docs/en/about-claude/pricing`) was captured on 2026-09-27. Rates are per MTok, in the order input / output / 5m write / 1h write / cache read:

| Model | Rates |
|---|---|
| Claude Fable 5.1 | $10 / $50 / $12.50 / $20 / $0.25 |
| Claude Opus 5.5 | $4 / $20 / $5 / $8 / $0.20 |
| Claude Opus 5 (historical, AC-13) | $5 / $25 / $6.25 / $10 / $0.50 |
| Claude Sonnet 5 | $2 / $10 / $2.50 / $4 / $0.20 |
| Claude Haiku 4.5 | $1 / $5 / $1.25 / $2 / $0.10 |

Modifiers and extra charges:

- **Fast mode:** Opus 5.5 is $8 in / $40 out, and Opus 5 / 4.8 are $10 / $50. Cache multipliers stack on top.
- **Data residency:** `inference_geo: "us"` is 1.1× on 4.6+ models.
- **Long context:** 1M context is billed at standard rates on 4.6+ models.
- **Web search:** $10 per 1,000 searches. Web fetch has no additional charge. Code execution is billed by container time and is not observable from the transcript.

These values are **plan context, not permanent authority**. T-05 re-captures them. The registry records its own capture date and source, and the tests pin the exact values accepted in the candidate.

## Acceptance-criteria ledger

| AC | Criterion (short) |
|---|---|
| AC-01 | Reconstructed owns dollars; `api≈` / `api≥` / never-precise-when-unpriceable |
| AC-02 | Session-only `host≈` fallback (`max_seen`); never Today |
| AC-03 | Parent + delegated sums equal independent totals |
| AC-04 | Presentation limits do not limit accounting |
| AC-05 | Budget boundary defers, never skips |
| AC-06 | Real byte bounds; no whole-tail read |
| AC-07 | Partial trailing line |
| AC-08 | Session-scoped identity; fork replay counted once; owner rule |
| AC-09 | Malformed identity never wedges; classified unproven |
| AC-10 | Monotone duplicates |
| AC-11 | Model conflict → partial |
| AC-12 | Current-model exact pricing |
| AC-13 | `claude-opus-5` historical pricing |
| AC-14 | Unknown model → tokens yes, price no, partial |
| AC-15 | Cache cases incl. stale multi-iteration split |
| AC-16 | web_search priced, web_fetch known-zero, unknown counters partial |
| AC-17 | Cross-midnight parent |
| AC-18 | Cross-midnight delegated |
| AC-19 | Host disappearance non-destructive |
| AC-20 | Host regression anomaly; `max_seen` kept |
| AC-21 | Host disagreement non-destructive |
| AC-22 | Starvation-free catch-up |
| AC-23 | Replacement (truncate / same-size / larger / rotate) isolated |
| AC-24 | Parent-only burn from normalized usage |
| AC-25 | Legacy migration |
| AC-26 | Corrupt legacy fails soft |
| AC-27 | Concurrency preserves all state |
| AC-28 | No periodic refresh; installer unchanged; limitation documented |
| AC-29 | No render-time network |
| AC-30 | Fail-soft rendering with coverage reasons |
| AC-31 | Public vocabulary |
| AC-32 | Canonical-source parity |
| AC-33 | Unrelated statusline behavior unchanged |
| AC-34 | Full verification against exact candidate |
| AC-35 | Identity classes and domain separation |
| AC-36 | Order independence |
| AC-37 | Cache refinement never double-counts |
| AC-38 | Malformed-record coverage |
| AC-39 | Performance contract + base/head benchmark |
| AC-40 | History scaling 1k/10k/100k |
| AC-41 | Non-blocking lock; no false zeros |
| AC-42 | Unknown event time → Session only, Today partial |
| AC-43 | Cross-midnight replay deterministic + flagged |
| AC-44 | Advisor iterations priced at own model |
| AC-45 | Price modifiers |
| AC-46 | `<synthetic>` and alias models |
| AC-47 | Source lifecycle |
| AC-48 | Discovery bound |
| AC-49 | Oversized record progress |
| AC-50 | Presentation from summaries; no child JSONL opened |
| AC-51 | Characterized sanitized fixtures |
| AC-52 | `host≈` uses `max_seen` |

All test paths are under `plugins/ca/hooks/tests/`, where the tests are plugin-only. Canonical Python lives in `core/pysrc/`, and generated copies are refreshed by `tools/sync-core.py` before tests import them (T-41, plus a local sync before each focused green run).

## Ordered tasks

### CP-0 — Gates, characterization, baseline

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-01 | Run the intent backstop on the exact approved spec bytes; stop on any output. | spec | `python core/pysrc/_intentlib.py uncovered-intent .codearbiter/specs/claude-statusline-accounting-integrity.md` empty | Preflight | AC-34 | — | ACCEPTED (empty on approved bytes 2026-09-27) |
| T-02 | Capture sanitized structural fixtures from real local transcripts. Shapes: fork-context-ref + replay, 3-iteration advisor record, stale top-level cache split, streaming snapshot group, `<synthetic>`, modifier fields, a `cost-state` record. Replace IDs/UUIDs and strip all content. Confirm where `spawnDepth>1` children are written. Record provenance (Claude Code version, capture date) in a fixture README. | `tests/fixtures/statusline_accounting/` (new) | A fixture-lint test (this is a public repo) rejects content fields, real IDs/UUIDs, absolute paths, `cwd`, `gitBranch`, usernames, hostnames and emails, and asserts each named shape is present. The README records the `inference_geo:not_available` assumption (spec D-27) | Characterization | AC-51, AC-08, AC-44 | T-01 | ACCEPTED |
| T-03 | Add `tools/statusline-bench.py`. It generates deterministic fixtures (long parent; 0/1/12/13/64 children; 1k/10k/100k-request ledgers), runs warm no-change, host-only-change and incremental renders as **one subprocess per render** through the statusline entry point (JSON payload on stdin; `HOME`/ledger/transcript roots redirected by env), with a child-side wrapper installing `sys.audit` + read/write counters, and emits a JSON report. The same harness must run unchanged on base and head. **Run it on the base commit and commit the base report before any `core/pysrc` change.** | `tools/statusline-bench.py`, `.codearbiter/benchmarks/statusline-accounting-base.json`, `tools/README.md` | The base report exists in a commit whose tree has unchanged `core/pysrc` accounting files; the script is deterministic across two runs (structural counters identical) | Performance baseline | AC-39, AC-40 | T-01 | ACCEPTED |

### CP-1 — Contract and normalization (`_usagelib.py`)

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-04 | Red pricing tests: exact current models, `claude-opus-5`, unknown model, `<synthetic>` zero/non-zero, `[1m]` + dated aliases, non-alias suffix, fast/geo/tier modifiers. | `test_usagelib.py` (new) | Red before implementation | TDD pricing | AC-12, AC-13, AC-14, AC-45, AC-46 | T-02 | ACCEPTED |
| T-05 | Implement the registry (capture date/source recorded; re-captured from the official page at implementation time), alias table, modifier rules and `price()`. No unknown→Sonnet fallback. | `core/pysrc/_usagelib.py` | T-04 green; `py_compile` | TDD pricing | AC-12, AC-13, AC-14, AC-29, AC-45, AC-46 | T-04 | ACCEPTED |
| T-06 | Red normalization tests: counter coercion (non-finite, negative, boolean, fractional, over-ceiling → malformed reasons); cache classification (every AC-15 case + the stale multi-iteration split); advisor iterations, incl. two same-model advisor calls in one turn (sum within representation) + unknown iteration type; server-tool classes (priced / known-zero / unknown, synthetic non-zero fixtures). | `test_usagelib.py` | Red | TDD normalization | AC-15, AC-16, AC-38, AC-44 | T-05 | ACCEPTED |
| T-07 | Implement `normalize()` and the charge registry. Cache = total + classification (D-9); iterations per D-26; server tools per D-10. | `core/pysrc/_usagelib.py` | T-06 green; malformed input never raises | TDD normalization | AC-15, AC-16, AC-30, AC-38, AC-44 | T-06 | ACCEPTED |
| T-08 | Red identity/reconciliation tests: every D-5 class incl. look-alike keys; `mid`-only before/after `rid`+`mid`; larger/equal/smaller replays; model conflict + alias equivalence; every AC-37 cache sequence; min event time, untrustworthy timestamps, cross-midnight representations; **permutation property test** over merge order. | `test_usagelib.py` | Red | TDD reconciliation | AC-09, AC-10, AC-11, AC-35, AC-36, AC-37, AC-42, AC-43 | T-07 | ACCEPTED |
| T-09 | Implement `classify_identity()` and the commutative `merge()`. | `core/pysrc/_usagelib.py` | T-08 green incl. permutation property | TDD reconciliation | AC-09, AC-10, AC-11, AC-35, AC-36, AC-37, AC-43 | T-08 | ACCEPTED |

### CP-2 — One bounded multi-source scanner

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-10 | Red parent-scanner tests: budget −1/exact/+1/multi-chunk; offset = after the last consumed record; partial trailing line; oversized usage-bearing and non-usage lines (within and beyond the byte budget; 64 KiB tail `"usage":` check); I/O counters prove bytes read ≤ budget. | `test_ledgerlib.py` | Red on current `f.read()` / EOF-advance behavior | TDD bounded streaming | AC-05, AC-06, AC-07, AC-49 | T-09 | ACCEPTED |
| T-11 | Implement the bounded binary line-streaming scanner (byte/record budgets, per-record ceiling, skip-until-newline) feeding `_usagelib`. | `core/pysrc/_ledgerlib.py` | T-10 green | TDD bounded streaming | AC-05, AC-06, AC-07, AC-49 | T-10 | ACCEPTED |
| T-12 | Red scanner-level malformed/coverage tests: every AC-38 case through the scanner; the observation-8 non-usage types leave coverage complete; poison lines never wedge. | `test_ledgerlib.py` | Red | TDD coverage-aware fail-soft | AC-30, AC-38 | T-11 | ACCEPTED |
| T-13 | Route scanner outcomes into source coverage reasons. | `core/pysrc/_ledgerlib.py` | T-12 green | TDD coverage-aware fail-soft | AC-30, AC-38 | T-12 | ACCEPTED |
| T-14 | Red migration tests: a production-shaped legacy ledger (`reqs`, `tx_off`, `tx_path`, `host_cost`, `today`, `sess_start`) + a corrupt sibling shard. | `test_ledgerlib.py` | Red; old `host_cost` never becomes reconstructed cost | TDD migration | AC-25, AC-26 | T-13 | ACCEPTED |
| T-15 | Introduce the versioned schema (compact summary + partitioned evidence, D-21 layout) and migrate. Legacy `host_cost` seeds only the host record; transcript-derived state replays, reporting `catching_up`. | `core/pysrc/_ledgerlib.py` | T-14 green; no user deletion required | TDD migration | AC-25, AC-26 | T-14 | ACCEPTED |
| T-16 | Red multi-source tests: 0/1/12/13/64 children + children older than `SHOW_WINDOW`; fork-replay fixture from T-02 (parent↔child and sibling↔sibling) counted once, with the owner rule for per-source subtotals; every source-order permutation yields identical state; directory entries above the discovery bound; `*.meta.json` ignored as a source. | `test_ledgerlib.py` | Red | TDD delegated sources | AC-03, AC-04, AC-08, AC-36, AC-48 | T-15 | ACCEPTED |
| T-17 | Implement ledger-owned discovery (bounded listing, `*.jsonl` only), per-child source state, session-scoped reconciliation through evidence partitions, and the D-7 owner rule. | `core/pysrc/_ledgerlib.py` | T-16 green | TDD delegated sources | AC-03, AC-04, AC-08, AC-36, AC-48 | T-16 | ACCEPTED |
| T-18 | Red starvation test: a growing large parent + children exceeding every budget; assert completion within a deterministic render count. | `test_ledgerlib.py` | Red | TDD eventual completeness | AC-22 | T-17 | ACCEPTED |
| T-19 | Implement the persisted round-robin scheduler cursor. | `core/pysrc/_ledgerlib.py` | T-18 green; each render within budgets | TDD eventual completeness | AC-05, AC-22 | T-18 | ACCEPTED |
| T-20 | Red replacement/lifecycle tests: truncate; same-size 4→4 MiB; larger 4→6 MiB; rotate; vanish after EOF; vanish with backlog; vanish before scan; reappear; listing failure; co-observed fork request recomputed from the remaining observers. | `test_ledgerlib.py` | Red | TDD source isolation/lifecycle | AC-23, AC-47 | T-19 | ACCEPTED |
| T-21 | Implement stat-gated head/tail fingerprints, generation rebuild, and lifecycle states. | `core/pysrc/_ledgerlib.py` | T-20 green; no-change render performs no fingerprint read | TDD source isolation/lifecycle | AC-23, AC-30, AC-47 | T-20 | ACCEPTED |

### CP-3 — Incremental summaries, host estimate, locking, rendering

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-22 | Red principal independent-total fixture: parent + several children with mixed models, fork replay, advisor iterations, cache variants, web search, and a fast/geo modifier. Expected tokens and dollars are hard-coded from fixture facts. | `test_ledgerlib.py` | Red | TDD all-source totals | AC-03, AC-12, AC-15, AC-16, AC-44, AC-45 | T-21 | ACCEPTED |
| T-23 | Implement incremental derived indices (per-source, per-source-per-day, session, compact summary) via subtract-old/add-new, with a rebuild only on schema, registry, generation change, or checksum mismatch. Remove the host-cost override. | `core/pysrc/_ledgerlib.py` | T-22 green; derived == from-scratch recomputation; host variations leave reconstructed values identical | TDD reconstructed source of truth | AC-01, AC-03, AC-21, AC-40 | T-22 | ACCEPTED |
| T-24 | Red calendar tests: parent and child cross-midnight; unknown event time; cross-midnight replay in both arrival orders. | `test_ledgerlib.py` | Red on current whole-session Today cost and `_msg_date`→now fallback | TDD calendar | AC-17, AC-18, AC-42, AC-43 | T-23 | ACCEPTED |
| T-25 | Implement per-day attribution by minimum event time, Session-only unknown-time accounting, and `conflicting_event_day`; delete whole-session host attribution from Today and cross-session Today aggregation over compact summaries. | `core/pysrc/_ledgerlib.py` | T-24 green | TDD calendar | AC-02, AC-17, AC-18, AC-42, AC-43 | T-24 | ACCEPTED |
| T-26 | Red history-scaling tests at 1k/10k/100k accepted requests: a no-change render deserializes no evidence; a *k*-new-record render deserializes ≤ *k* partitions, each ≤ the fixed maximum size; an overgrown partition splits. | `test_ledgerlib.py` | Red if evidence loading is O(history) | TDD history scaling | AC-40 | T-25 | ACCEPTED |
| T-27 | Tune evidence partitioning and summary reads until T-26 holds; Today across prior sessions reads summaries only. | `core/pysrc/_ledgerlib.py` | T-26 green | TDD history scaling | AC-40 | T-26 | ACCEPTED |
| T-28 | Red per-scope coverage tests: complete; catching-up; each partial reason; unavailable; a newly discovered unscanned child; Session-complete while Today-partial. | `test_ledgerlib.py` | Red | TDD coverage | AC-01, AC-14, AC-22 | T-25 | ACCEPTED |
| T-29 | Return structured per-scope coverage (state + reasons + stale flag) from the ledger API. | `core/pysrc/_ledgerlib.py` | T-28 green | TDD coverage | AC-01, AC-14, AC-22 | T-28 | ACCEPTED |
| T-30 | Red host-estimate tests: valid→absent/null/malformed/boolean; increase; decrease; out-of-order; new session; above/below reconstructed. | `test_ledgerlib.py` | Red on current zero-coercion/override | TDD host reconciliation | AC-19, AC-20, AC-21, AC-52 | T-23 | ACCEPTED |
| T-31 | Persist the host estimate separately (`latest`, `max_seen`, presence/regression, delta when complete); fallback uses `max_seen`. | `core/pysrc/_ledgerlib.py` | T-30 green | TDD host reconciliation | AC-02, AC-19, AC-20, AC-21, AC-52 | T-30 | ACCEPTED |
| T-32 | Parent-only burn derived from accepted parent-owned requests; child usage and fork replays leave burn unchanged. | `core/pysrc/_ledgerlib.py`, `test_ledgerlib.py` | Burn tests green | TDD burn | AC-24, AC-33 | T-23 | ACCEPTED |
| T-33 | Red concurrency + lock tests: same/distinct-session competing scans; session-start write during accounting; interrupted atomic replace; **lock held by another process** → render returns within the try-lock bound with a stale snapshot; no snapshot → unavailable, never zero. | `test_ledgerlib.py` | Red | TDD persistence + non-blocking | AC-27, AC-41 | T-21, T-29, T-31 | ACCEPTED |
| T-34 | Implement the render-path try-lock (≤ 20 ms) with last-committed-summary fallback; reconcile multi-source writes under the existing lock/shard model; preserve the `sess_start` overlay. | `core/pysrc/_ledgerlib.py` | T-33 green; existing concurrency tests green | TDD persistence + non-blocking | AC-27, AC-30, AC-41 | T-33 | ACCEPTED |
| T-35 | Red presentation tests: `_subagentslib` renders from summaries + `listdir`/`stat`/`*.meta.json`; an instrumented `open` proves no child JSONL is opened; rows, labels and liveness match pre-change output on equivalent fixtures (golden captured from `main` first). | `test_statusline.py` | Red | TDD one parser | AC-33, AC-50 | T-29 | ACCEPTED |
| T-36 | Rewrite `_subagentslib` to consume ledger presentation summaries; delete its JSONL parsing. | `core/pysrc/_subagentslib.py`, `core/pysrc/statusline.py` | T-35 green | TDD one parser | AC-04, AC-33, AC-50 | T-35 | ACCEPTED |
| T-37 | Red renderer tests: `api≈`, `api≥`, `api≈?`, Session `host≈` (`max_seen`), Today no-host, stale marker, unavailable ≠ `$0`; width and `NO_COLOR` included. | `test_statusline.py` | Red | TDD user-facing semantics | AC-01, AC-02, AC-33, AC-41 | T-29, T-31, T-34 | ACCEPTED |
| T-38 | Update the ledger→renderer contract and usage-row rendering; preserve box layout and width safety. | `core/pysrc/statusline.py`, `core/pysrc/_segmentslib.py` | T-37 green; `py_compile` | TDD user-facing semantics | AC-01, AC-02, AC-30, AC-33, AC-41 | T-37 | ACCEPTED |
| T-39 | Prove the installer unchanged: existing `test_wire_statusline.py` green; add an assertion that `owned_statusline()` introduces no `refreshInterval`, and that a user's pre-existing `statusLine` (including any refresh field) round-trips through install/uninstall. | `test_wire_statusline.py` | Green without any `wire-statusline.py` change | Regression guard | AC-28 | T-01 | ACCEPTED |
| T-40 | Fail-soft matrix through `render()`: vanished dirs/files, permission errors, malformed/oversized records, unknown model/tool/iteration/modifier, held lock; each yields no traceback, no blank bar, and the specified reason. Assert no network (socket guard). | `test_statusline.py`, `test_ledgerlib.py` | Green | TDD robustness | AC-29, AC-30, AC-33 | T-34, T-38 | ACCEPTED |

### CP-4 — Performance, docs, generation, release proof

| ID | Work | Path(s) | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-41 | Synchronize canonical Python to all generated host copies. | `tools/sync-core.py`, generated `plugins/*/hooks/*` | `python tools/sync-core.py`; `--check`; `python .github/scripts/test_sync_core.py` | Generated parity | AC-32 | T-05, T-07, T-09, T-11, T-13, T-15, T-17, T-19, T-21, T-23, T-25, T-27, T-29, T-31, T-32, T-34, T-36, T-38 | ACCEPTED |
| T-42 | Focused suite on synchronized bytes: `test_usagelib`, `test_ledgerlib`, `test_statusline`, `test_wire_statusline`. Run with `NO_COLOR` unset. | tests | All green | Focused verification | AC-32, AC-33, AC-34 | T-41 | ACCEPTED |
| T-43 | Structural I/O acceptance: add CI-gated tests asserting the D-20 no-change / host-only / heartbeat-at-most-once / incremental / single-decode counters; run `tools/statusline-bench.py` on head vs the committed base report; attach the comparison to the PR; stop if structural counters regress, or if the warm median/p95 exceed base × 1.05. | `test_ledgerlib.py`, `tools/statusline-bench.py`, `.codearbiter/benchmarks/statusline-accounting-head.json` | Counters ≤ base; timing within tolerance | Performance acceptance | AC-39, AC-40 | T-42 | ACCEPTED |
| T-44 | Correct source comments and command docs: the three monetary labels, stale/unavailable, parent-only burn, idle-freshness limitation; remove authoritative-host claims. | `core/pysrc/*.py` comments, `core/surface/commands/statusline.md` | Structural doc assertions; no prohibited claim | Documentation | AC-24, AC-28, AC-31 | T-38 | ACCEPTED |
| T-45 | Update the public statusline guide and screenshot/fixture commentary to the reconstructed-vs-host contract. | `site/src/content/docs/guides/the-statusline.md`, `tools/statusline-screenshot.py`, `site/test/**` | `npm --prefix site test` (plus typecheck/link audit per site conventions) | Documentation | AC-28, AC-31, AC-33 | T-44 | ACCEPTED |
| T-46 | Regenerate shared surfaces after the command-doc change. | generated command surfaces | `python tools/build-surface.py` then `--check`; `sync-core.py --check` | Generated docs parity | AC-31, AC-32 | T-44 | ACCEPTED |
| T-47 | Close adversarial-matrix combination gaps not already exercised. | tests | `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` green | Adversarial proof | AC-03, AC-04, AC-05, AC-06, AC-07, AC-08, AC-09, AC-10, AC-11, AC-15, AC-17, AC-18, AC-19, AC-20, AC-23, AC-26, AC-33, AC-35, AC-37, AC-46, AC-47, AC-48, AC-49, AC-50, AC-51, AC-52 | T-43, T-45, T-46 | ACCEPTED |
| T-48 | Advance affected package versions/changelogs per current release invariants (all adapters that ship synced hooks; root Pi manifest). | plugin manifests, CHANGELOGs, README badge, root `package.json` | Version-guard tests; `python tools/build-host-packages.py --check` | Release consistency | AC-32, AC-34 | T-47 | ACCEPTED |
| T-49 | Full local verification, then the implementation PR, with hosted exact-head CI green before any completion claim. The PR body answers all eleven Completion Evidence questions and includes the base/head benchmark report. | all touched surfaces; PR metadata | `py_compile`; full unittest discovery; `sync-core --check`; `build-surface --check`; `build-host-packages --check`; `check-plugin-refs.py`; site tests; `gh pr checks` green | Final acceptance | AC-12, AC-13, AC-16, AC-25, AC-27, AC-29, AC-34, AC-39 | T-48 | PENDING |

## MVP slice

**MVP = T-01 through T-49.** There is no honest smaller shippable slice. Every item determines the meaning, or the cost, of the same displayed dollar figure:

- streaming;
- identity;
- advisor accounting;
- pricing;
- coverage;
- labels;
- locking;
- migration.

Checkpoints are review units, not release candidates.

## Dependency notes

- **T-03 precedes every `core/pysrc` change.** The baseline cannot be reconstructed honestly after the fact.
- **T-02 fixtures feed T-04, T-06, T-08, T-16 and T-22.** Real shapes, not imagined ones, define the red tests.
- **T-09 (commutative merge) precedes all scanner work.** Order independence is a property of the reconciler, not of scan order.
- **T-15 (schema + migration) precedes multi-source work.** Legacy `host_cost` must never masquerade as reconstructed state, even for one intermediate commit.
- **T-23 precedes T-30/T-31.** Otherwise tests can keep treating the host estimate as the monetary source of truth.
- **T-29 precedes renderer and presentation work (T-35, T-37).** Renderers consume typed facts.
- **T-36 removes the second parser only after T-17 publishes summaries.** The panel never loses data mid-plan.
- **T-48 versioning is late.** Versions describe the final shipped byte set.

## Criterion-to-task bijection

| Criterion | Tasks |
|---|---|
| AC-01 | T-23, T-28, T-29, T-37, T-38 |
| AC-02 | T-25, T-31, T-37, T-38 |
| AC-03 | T-16, T-17, T-22, T-23, T-47 |
| AC-04 | T-16, T-17, T-36, T-47 |
| AC-05 | T-10, T-11, T-19, T-47 |
| AC-06 | T-10, T-11, T-47 |
| AC-07 | T-10, T-11, T-47 |
| AC-08 | T-02, T-16, T-17, T-47 |
| AC-09 | T-08, T-09, T-47 |
| AC-10 | T-08, T-09, T-47 |
| AC-11 | T-08, T-09, T-47 |
| AC-12 | T-04, T-05, T-22, T-49 |
| AC-13 | T-04, T-05, T-49 |
| AC-14 | T-04, T-05, T-28, T-29 |
| AC-15 | T-06, T-07, T-22, T-47 |
| AC-16 | T-06, T-07, T-22, T-49 |
| AC-17 | T-24, T-25, T-47 |
| AC-18 | T-24, T-25, T-47 |
| AC-19 | T-30, T-31, T-47 |
| AC-20 | T-30, T-31, T-47 |
| AC-21 | T-23, T-30, T-31 |
| AC-22 | T-18, T-19, T-28, T-29 |
| AC-23 | T-20, T-21, T-47 |
| AC-24 | T-32, T-44 |
| AC-25 | T-14, T-15, T-49 |
| AC-26 | T-14, T-15, T-47 |
| AC-27 | T-33, T-34, T-49 |
| AC-28 | T-39, T-44, T-45 |
| AC-29 | T-05, T-40, T-49 |
| AC-30 | T-07, T-12, T-13, T-21, T-34, T-38, T-40 |
| AC-31 | T-44, T-45, T-46 |
| AC-32 | T-41, T-42, T-46, T-48 |
| AC-33 | T-32, T-35, T-36, T-37, T-38, T-40, T-42, T-45, T-47 |
| AC-34 | T-01, T-42, T-48, T-49 |
| AC-35 | T-08, T-09, T-47 |
| AC-36 | T-08, T-09, T-16, T-17 |
| AC-37 | T-08, T-09, T-47 |
| AC-38 | T-06, T-07, T-12, T-13 |
| AC-39 | T-03, T-43, T-49 |
| AC-40 | T-03, T-23, T-26, T-27, T-43 |
| AC-41 | T-33, T-34, T-37, T-38 |
| AC-42 | T-08, T-24, T-25 |
| AC-43 | T-08, T-09, T-24, T-25 |
| AC-44 | T-02, T-06, T-07, T-22 |
| AC-45 | T-04, T-05, T-22 |
| AC-46 | T-04, T-05, T-47 |
| AC-47 | T-20, T-21, T-47 |
| AC-48 | T-16, T-17, T-47 |
| AC-49 | T-10, T-11, T-47 |
| AC-50 | T-35, T-36, T-47 |
| AC-51 | T-02, T-47 |
| AC-52 | T-30, T-31, T-47 |

Every AC has at least one task, and every task advances at least one AC. This is the plan/spec bijection only. Semantic completeness remains gated by T-01 and the negative-judgment review above.

## Parallelization after the gates

- T-02 and T-03 can run concurrently. T-39 is independent of everything after T-01.
- CP-1 (T-04..T-09) is strictly sequential, because it is one module growing test-first.
- CP-2 and CP-3 each touch `_ledgerlib.py` and are sequential. The only exception is T-35 golden capture (pre-change subagent output from `main`), which can be prepared early.
- Doc test preparation for T-45 can be authored red in parallel once T-38's labels are fixed.

Do **not** parallel-edit generated `plugins/*/hooks` copies. One integration owner runs `sync-core.py` and `build-surface.py`. Concurrent authors, if any, use separate worktrees.

## Rollback and compatibility

- There are no network migrations and no destructive rewrite outside the user-local ledger.
- Legacy ledger replay is deterministic and fail-soft.
- A failed new-schema write leaves the prior valid target intact through atomic replacement.
- The installer is unchanged, so uninstall semantics are unchanged.
- If a class of child transcript cannot be associated with its parent without guessing (see T-02's nested-child check), stop and surface it as unobservable/partial. Do not broaden directory walks.

## Completion condition

The implementation is complete only when T-49 is accepted and every task is `ACCEPTED`. None of these is completion on its own:

- a locally green suite;
- a green suite without the benchmark comparison;
- a benchmark without hosted exact-head CI.
