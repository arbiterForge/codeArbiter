# Review — Claude statusline accounting integrity

**Reviewed PR:** #883  
**Reviewed branch:** `spec/claude-statusline-accounting-integrity`  
**Reviewed base:** `main@c3d574a3d144578379526499b1fafe7109236923`  
**Review date:** 2026-09-26  
**Scope:** Validate the spec and plan against the current implementation for correctness, missed failure modes, silent failure, resource waste, over-engineering, and statusline latency risk.

## Guiding requirements

1. Correct accounting is the primary requirement.
2. The change must not increase statusline latency. Prefer reducing it.
3. Any incomplete or ambiguous accounting state must fail visibly/explicitly rather than render a confidently wrong precise total.
4. Bounded work may defer accounting but must not discard it.
5. Avoid duplicated parsing, repeated historical aggregation, unnecessary writes, and periodic work that is not demonstrably needed.

## Overall verdict

The spec has the right overall accounting direction and correctly identifies the major defects in the current implementation:

- the `TX_MAX_NEW_LINES` offset/EOF skip;
- host cost overriding reconstructed cost;
- delegated/subagent usage not participating as durable first-class accounting sources;
- whole-session host cost being assigned to Today;
- family-level and unknown-model pricing problems;
- weak cache-write reconciliation;
- malformed request identity and last-write-wins replay behavior;
- omitted separately metered observable server-tool usage;
- presentation bounds being unsuitable as accounting bounds;
- misleading documentation around `cost.total_cost_usd`.

However, the current plan should **not be implemented unchanged**.

There are remaining correctness gaps capable of producing a confidently wrong `api≈` or `api≥`, and the proposed runtime architecture can materially increase work on the statusline hot path. The plan currently has no measurable latency/I/O acceptance criterion, despite latency being one of the primary product constraints.

## Blocking findings

### 1. Position-derived fallback identities break the meaning of `api≥`

D-5 currently says missing or structurally invalid IDs receive a deterministic source-local identity derived from the consumed record position.

That guarantees forward progress, but it does not guarantee deduplication.

If two transcript records are different representations of the same API request and both lack a trustworthy `requestId` or message ID, record-position identities make them two requests. Both can be counted.

That means a displayed value such as:

```text
api≥$4.20
```

may not actually be a lower bound. The defensible known amount could be lower.

#### Required correction

Request identity needs at least three states:

- trustworthy request ID;
- trustworthy message ID;
- ambiguous/unproven identity.

An ambiguous record should:

- advance the source scanner;
- be retained as coverage evidence;
- make monetary coverage partial;
- not be included in a quantity labeled as a lower bound unless uniqueness can actually be established.

Identity classes should also be domain-separated so a real request ID cannot collide with a generated fallback identity. Persist an identity equivalent to:

```text
rid:<encoded-id>
mid:<encoded-id>
pos:<generation>:<byte-offset>
```

rather than one raw key namespace.

#### Add tests for

- repeated missing IDs;
- numeric IDs;
- empty IDs;
- booleans;
- arrays/objects;
- actual IDs resembling fallback IDs;
- duplicate ambiguous records.

---

### 2. Cache aggregate-to-TTL refinement can double-count

D-6 requires monotonic duplicate reconciliation. D-9 requires cache aggregate and TTL-specific reconciliation.

Those two requirements can interact incorrectly if implemented as a component-wise maximum.

Example for one request:

```text
Record A:
cache_creation_input_tokens = 100
no TTL split
```

A normalizer may reasonably represent this as:

```text
unknown_write = 100
```

A later replay may contain:

```text
Record B:
cache_creation_input_tokens = 100
ephemeral_5m_input_tokens = 100
```

If reconciliation independently keeps the maximum observed value of each component, the accepted state can become:

```text
unknown_write = 100
5m_write = 100
```

That prices 200 tokens of cache writes from an actual 100-token write.

#### Required correction

Unknown TTL is not an independent cumulative counter. It is a classification remainder.

Canonical cache-write state should be equivalent to:

```text
total_cache_write
known_5m
known_1h
unknown = total_cache_write - defensibly_classified
```

A replay may make classification more specific without increasing total cache-write tokens.

#### Add tests for

- aggregate-only → complete 5m split;
- aggregate-only → complete 1h split;
- partial split → complete split;
- complete split → less-complete replay;
- split sum greater than aggregate;
- aggregate increase while classification remains partial;
- conflicting 5m/1h classifications.

This needs its own explicit AC rather than being left implicit between AC-10 and AC-15.

---

### 3. Malformed records can still become silent undercount

The existing implementation skips malformed JSON and keeps advancing. Fail-soft rendering is correct, but fail-soft rendering and trustworthy accounting are separate requirements.

A malformed record may have represented billable usage. If the scanner advances past it and the ledger later declares coverage `complete`, `api≈` becomes a silent undercount.

#### Required correction

Any consumed record whose shape prevents codeArbiter from determining whether observable billable usage was represented must affect source monetary coverage.

Examples:

- malformed JSON;
- structurally invalid assistant usage;
- non-finite counters;
- negative counters;
- booleans accepted as numeric values;
- fractional token/request counters where the source contract requires integers;
- oversized records intentionally skipped for latency protection.

Unknown ordinary non-usage event types may still be ignored.

AC-30 should not only say these inputs do not crash/blank the statusline. It should also say when they force `partial` coverage.

---

### 4. Missing or conflicting timestamps have no safe day-attribution contract

The current `_msg_date()` behavior effectively maps an unusable timestamp to Today.

That is unsafe for the new accounting contract.

#### Required correction

For usage without a trustworthy event timestamp:

- include defensibly reconstructed usage in Session;
- do not manufacture Today attribution;
- Today coverage becomes partial with a reason such as `unknown_event_time`.

Duplicate representations of one request may also contain conflicting timestamps, including timestamps on opposite sides of midnight. The spec must define how timestamp reconciliation works so a replay cannot silently move spend between days.

Add a same-request/cross-midnight replay fixture.

---

### 5. The spec lacks a measurable latency/I/O acceptance contract

The current plan can satisfy all existing ACs while making the statusline slower.

That is unacceptable for this feature.

The repository already treats statusline latency as a first-class concern:

- `_ledgerlib.py` avoids unconditional rewrites and has tests proving an unchanged render performs zero replacements;
- `git_dirty()` has a 100 ms ceiling;
- prior statusline performance work removed repeated state scans/writes.

This effort needs an explicit performance contract before implementation.

#### Required performance criteria

At minimum:

- **No-change render:** no transcript content is reread and no ledger file is rewritten.
- **Incremental render:** transcript bytes read are bounded by an explicit accounting byte budget.
- **No duplicate child parse:** one JSONL record is decoded by at most one accounting/presentation pipeline.
- **History scaling:** a no-change render does not become slower merely because the session has 1k, 10k, or 100k already-accounted requests.
- **Lock contention:** statusline accounting must not wait the current full 200 ms ledger-lock budget.
- **Base/head benchmark:** on identical generated fixtures, warm-render median and p95 must not regress versus the base commit.
- Test 0, 1, 12, 13, and many children plus a long parent transcript.
- Record file reads/writes, parsed bytes, and elapsed time so noisy CI timing cannot conceal a structural regression.

---

## High-priority architecture/resource findings

### 6. Remove fixed `refreshInterval: 2` from the hard accounting contract

D-13 and AC-28 currently mandate a two-second refresh.

That is too aggressive to encode as a correctness requirement.

A statusline render already performs work including:

- ledger locking;
- ledger/session-shard reads;
- transcript scanning;
- status/arbiter reads;
- subagent directory/file operations;
- a Git dirty probe;
- formatting/rendering.

A two-second global timer multiplies all of this even while the user is idle and can create self-contention if one render overlaps the next.

It may also spend resources without guaranteeing that the host visibly repaints every intermediate invocation.

#### Required correction

Periodic background refresh should be a separately benchmarked product choice, not part of accounting correctness.

Preferred approach for this PR:

- do not introduce a new periodic refresh by default;
- rely on normal event-driven renders for accounting correctness;
- if idle background-agent freshness is considered essential, add a configurable interval only after measuring the candidate execution envelope with adequate headroom;
- do not hard-code `2` into the accounting ACs.

If a default periodic interval is retained, begin conservatively (for example around 10 seconds), and only after base/head measurements on supported platforms.

---

### 7. Do not keep two child-transcript parsing pipelines

Current `_subagentslib.py` already performs a bounded presentation scan:

- lists the subagent directory;
- stats JSONL candidates;
- sorts them;
- opens up to 12 files;
- parses up to roughly 2,500 lines per selected file.

The plan then adds a second durable accounting scanner over all child transcripts while T-10 keeps the presentation scanner and only makes it call the shared normalizer.

That removes duplicated semantics, but not duplicated parsing cost.

#### Required correction

Use one transcript parser.

The accounting scanner should retain compact presentation metadata per source, equivalent to:

```text
label
observed model(s)
display input/output
last observed mtime
accounting totals
```

Then `_subagentslib` should consume those ledger/source summaries and only perform the cheap filesystem metadata work needed for active/recent liveness presentation.

The desired end state is:

- one JSONL parsing path;
- one normalization/reconciliation contract;
- presentation reads already-derived summaries.

This is the clearest opportunity for this change to **reduce** statusline latency relative to main.

---

### 8. Avoid O(total historical requests) aggregation on each repaint

The current `_agg_reqs()` model walks request history to derive totals.

The plan says totals are derived from normalized requests, which is logically correct, but a literal implementation will become increasingly expensive once every parent and child request is retained.

#### Required correction

Keep normalized request records as authoritative evidence, but maintain incrementally updated derived indices:

```text
source totals
source totals by relevant local day
session totals
compact session/day summary
```

When a request changes:

```text
subtract(old contribution)
add(new contribution)
```

Rebuild derived state only for cases such as:

- schema migration;
- pricing-registry version change;
- source generation replacement;
- detected derived-state corruption.

Steady-state work must not be proportional to accepted historical request count.

Likewise, Today aggregation across prior live sessions should use compact session summaries rather than walking every historical request map.

Add an explicit AC forbidding steady-state O(history) work.

---

### 9. Ledger lock contention should not create latency or false zeros

Current `ledger_update()` may wait up to `LOCK_WAIT = 0.2` seconds and then return blank zero totals if the lock cannot be acquired.

With more per-render ledger work and any periodic refresh, that becomes more likely.

This creates two bad behaviors:

- visible latency;
- a temporary false-zero display that looks like valid accounting.

#### Required correction

For the statusline path, prefer an effectively non-blocking/very-short try-lock.

On contention:

- read/use the last committed safe snapshot if available;
- preserve its existing coverage/age metadata;
- mark accounting stale/catching-up if needed;
- never replace valid visible totals with fabricated zeros merely because this render lost a lock race.

The stronger blocking lock semantics can remain for writers that actually require serialized mutation, but the UI should not spend 200 ms waiting.

---

## Additional silent-failure cases

### 10. Known-zero server-tool counters need an explicit classification

The charge registry should distinguish:

1. recognized separately priced counters;
2. recognized zero-incremental-price counters;
3. unknown/unpriceable counters.

For example, observable web-search requests have an explicit separately metered price, while web-fetch request counters may be observable without an additional per-request charge.

A known-zero counter must not unnecessarily make otherwise complete accounting partial.

---

### 11. Source disappearance lifecycle is incomplete

Once a child source has contributed usage, absence from the next directory listing must not erase its accepted accounting state.

Define explicit behavior for:

- source disappears after observed EOF → preserve accepted accounting;
- source disappears with pending backlog → preserve accepted subtotal, mark partial;
- source discovered but disappears before scanning → partial;
- source reappears as a new generation → isolated source rebuild.

AC-30 currently guarantees only that a disappearance does not crash rendering. It should also protect accounting state.

---

### 12. Replacement detection must cover same-size and larger replacements

`size < offset` catches truncation. It does not detect all replacements.

Explicitly test:

```text
old file: 4 MiB
replacement: 4 MiB
```

and:

```text
old file: 4 MiB
replacement: 6 MiB
```

T-26 mentions generation/fingerprint handling, but these cases should be named acceptance fixtures so implementation cannot regress to path+size identity.

---

### 13. A giant single JSONL record can defeat a line-count bound

Replacing `f.read()` with line iteration is necessary, but an unlimited `readline()` can still consume an arbitrarily large single record.

Define a per-record byte ceiling.

If an oversized record is skipped or deferred to preserve latency:

- scanner progress must remain deterministic;
- accounting must become partial rather than silently complete.

---

### 14. Exhaustive discovery and bounded directory work need a defined boundary

The spec currently wants all three:

- every locally discoverable child;
- bounded directory/file work;
- eventual discovery of every child.

For an arbitrarily large flat directory in a fresh process, those guarantees do not coexist cleanly without an index or a supported discovery ceiling.

Define an explicit supported discovery bound.

If the bound is exceeded:

- do not walk unbounded directory state;
- retain known source accounting;
- report partial coverage with a discovery-bound reason.

Correct-but-partial is preferable to an unbounded statusline.

---

### 15. Validate whether request IDs can repeat across parent and child sources before locking in source-scoped counting

The plan assumes identical request IDs in parent and child transcripts represent two independent API calls and should both count.

That is consequential.

Before implementation, capture sanitized real parent/child transcript fixtures from current Claude behavior and characterize whether one billable API call can be represented in both parent and delegated files.

If cross-source duplication exists, source-scoping alone will double-count it.

This characterization should precede implementation of D-5/T-17 rather than being discovered after the schema is committed.

---

### 16. Host fallback should not depend on process completion order

The separate host estimate design is correct.

However, if multiple statusline executions can overlap or receive stale host payloads, `latest` by writer completion order is not necessarily the best Session fallback.

If reconstruction is unavailable and `host≈` must be shown, use the greatest valid cumulative same-session host observation as the fallback candidate while still retaining the literal latest observation for diagnostics/anomaly tracking.

A new session remains allowed to start from zero.

This makes the planned `max_seen` state operationally useful instead of merely diagnostic.

---

## Pricing review

The proposed current-model registry values should still be revalidated at implementation time, as the plan requires.

The current published rates observed during this review are consistent with the values recorded in the plan for:

- Claude Fable 5.1;
- Claude Opus 5.5;
- Claude Sonnet 5;
- Claude Haiku 4.5.

The spec is correct to call the reconstructed amount a pinned public-list-rate API-equivalent estimate rather than actual account spend.

Modifiers such as:

- discounts/credits;
- subscription treatment;
- custom `modelPricing`;
- provider-specific rates;
- data residency;
- fast mode;
- other host/account-specific pricing

must remain outside the precise reconstructed claim unless the locally observed usage contains enough explicit information to price the modifier defensibly.

---

## What should be preserved

The following design choices are sound and should survive the rework:

- a small pure stdlib `_usagelib.py` is justified;
- source-local durable accounting state;
- source-scoped request identity after the cross-source duplication behavior is characterized;
- starvation-free bounded incremental processing;
- explicit separation of host estimate and reconstructed cost;
- exact/version-aware pricing;
- explicit `complete / catching_up / partial / unavailable` coverage;
- parent-only burn as an explicit product choice;
- existing atomic replacement and cross-session persistence protections;
- canonical-source/generated-copy discipline.

Do **not** turn `_usagelib.py` into a generalized pricing framework with plugin classes or deep abstraction. A small set of pure normalization/reconciliation functions plus immutable pricing/charge tables is sufficient.

---

## Recommended implementation order

The current 49-task plan has strong verification depth, but it is too procedural around a runtime architecture that still needs correction.

Reframe the execution around the following order:

1. **Characterize real transcript semantics first.**
   - Capture sanitized current parent+child fixtures.
   - Establish cross-source duplication behavior.
   - Establish real cache and server-tool record shapes.

2. **Repair the spec before implementation.**
   - ambiguous identity;
   - cache refinement semantics;
   - malformed-record coverage;
   - timestamp uncertainty;
   - disappearing sources;
   - replacement identity;
   - discovery bounds;
   - latency/I/O acceptance.

3. **Add the base-commit performance benchmark before implementation.**
   - It must exist before candidate code so the baseline cannot be reconstructed after the fact.

4. **Build a small pure `_usagelib.py`.**
   - normalization;
   - identity classification;
   - replay reconciliation;
   - exact pricing lookup;
   - cache classification;
   - separately metered charge classification.

5. **Correct the parent incremental scanner.**
   - bounded bytes/records;
   - no EOF skipping;
   - incomplete trailing lines;
   - oversized-record behavior;
   - fail-soft but coverage-aware malformed handling.

6. **Extend that same scanner to delegated sources.**
   - independent durable offsets/generations;
   - fair source scheduling;
   - bounded discovery.

7. **Make the scanner publish presentation summaries.**
   - Remove child JSONL parsing from the presentation hot path.

8. **Add incrementally maintained derived totals.**
   - avoid O(history) steady-state aggregation.

9. **Change UI lock behavior.**
   - effectively try-lock;
   - reuse last committed snapshot on contention;
   - no 200 ms UI wait;
   - no false-zero accounting.

10. **Reassess periodic refresh separately.**
    - Do not make a two-second timer part of accounting correctness.
    - Enable only if measured and justified.

11. **Run adversarial accounting and performance acceptance together.**
    - A functionally correct candidate that regresses hot-path latency does not pass.

---

## Suggested plan simplification

Retain the existing test depth, packaging checks, generated-source checks, docs correction, and exact-head CI requirements.

Collapse the runtime work conceptually into four implementation checkpoints:

### CP-1 — Contract and normalization

- real transcript characterization;
- corrected identity/cache/timestamp semantics;
- pricing/charge registry;
- pure normalization/reconciliation tests.

### CP-2 — One bounded multi-source scanner

- parent + child sources;
- correct offsets;
- partial-line handling;
- bounded record bytes;
- fair scheduling;
- replacement/disappearance behavior;
- bounded discovery;
- migration.

### CP-3 — Incremental summaries and rendering

- source/session/day derived summaries;
- structured coverage;
- separate host estimate;
- parent-only burn;
- presentation consumes ledger summaries;
- no second child parser;
- non-blocking contention behavior.

### CP-4 — Performance, docs, generation, release proof

- base/head latency and I/O comparison;
- full adversarial matrix;
- generated parity;
- docs/vocabulary;
- packaging/versioning;
- exact-head CI.

The number of test cases/tasks may still be large. The important simplification is one parser, one normalizer, incremental derived summaries, and one compact coverage model.

---

## Acceptance direction for the CLI agent

Do not treat the existing spec/plan as ready for implementation until the blockers in this review are reconciled.

The revised spec/plan should make it impossible to pass while:

- overcounting duplicate ambiguous records;
- double-counting cache aggregate + refined TTL splits;
- skipping malformed potential usage and still claiming `complete`;
- assigning unknown-time usage to Today;
- repeatedly reparsing child transcripts for presentation;
- walking all historical requests on every render;
- waiting 200 ms on the ledger lock;
- returning false zeros on lock contention;
- performing unbounded directory/record work;
- adding an unconditional two-second refresh without a measured latency budget;
- producing a candidate whose warm statusline latency or hot-path I/O regresses against the base commit.

The target is not merely “correcter accounting.” The target is **correct accounting with equal or lower steady-state statusline cost**.
