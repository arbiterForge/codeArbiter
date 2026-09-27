# Spec — Claude statusline accounting integrity

**Status:** APPROVED 2026-09-27 by the repository owner. The amended spec was approved in-session on the condition that current Opus is priced at Opus 5.5 rates, which it is: `claude-opus-5-5` is priced at $4/$20/$5/$8/$0.20, and the Opus 5 rates apply only to records whose model is `claude-opus-5`. The original version was approved 2026-09-26. See *Amendment log*.  
**Date:** 2026-09-26 (amended 2026-09-27)  
**Slug:** `claude-statusline-accounting-integrity`  
**Format:** Markdown authority for this externally authored review campaign; this PR creates no same-slug HTML shadow.

**Governs:** `core/pysrc/_ledgerlib.py`, `core/pysrc/statusline.py`, `core/pysrc/_subagentslib.py`, `core/pysrc/_segmentslib.py`, `core/pysrc/wire-statusline.py`, a shared usage-normalization/pricing helper if introduced under `core/pysrc/`, their synchronized plugin copies, statusline/ledger tests, a statusline benchmark harness under `tools/` or the test tree, and the public documentation that defines Claude statusline token/cost semantics.

**Origin:** Deep review of the Claude Code statusline accounting path on `main` at `c3d574a3d144578379526499b1fafe7109236923`, prompted by suspected latent spend-aggregation errors. None of the governed files changed between that commit and `main@8e88bce9` (checked 2026-09-27).

## Amendment log

**2026-09-27 — review reconciliation + transcript characterization.**

- **Review blockers 1–5 reconciled:**
  - identity classes (D-5);
  - cache remainder model (D-9);
  - malformed-record coverage (D-24);
  - timestamp uncertainty (D-11);
  - performance contract (D-20).
- **Review findings 6–16 reconciled:**
  - periodic refresh removed from the accounting contract (D-13);
  - one parser (D-7);
  - incremental derived totals (D-21);
  - UI try-lock (D-17);
  - known-zero charges (D-10);
  - source lifecycle (D-22);
  - replacement identity (D-15);
  - per-record byte ceiling (D-14);
  - discovery bound (D-25);
  - cross-source duplication (D-5, from evidence);
  - host fallback by `max_seen` (D-2).
- **New from characterization** (see *Observed transcript semantics*):
  - Fork replays cross sources. D-5 is reversed from source-scoped to session-scoped identity, and AC-08 is rewritten.
  - Advisor iterations are billable usage that the top-level counters exclude (D-26).
  - The top-level cache TTL split is stale on multi-iteration records (D-9).
  - `<synthetic>` records are non-billable (D-8).
  - Price modifiers are present in the records (D-27).
- **2026-09-27 (at implementation start):** the usage-bearing test now requires both `"usage":` and `"type":"assistant"`, because attachment task-notifications carry a `usage` summary (observation 10). v2 state uses new file names alongside legacy shards, so that older statusline processes still running cannot ping-pong the schema.
- AC-01..AC-34 keep their numbers. AC-08, AC-09, AC-15, AC-16, AC-22, AC-23, AC-28 and AC-30 are rewritten in place. AC-35..AC-52 are new.

**2026-09-27 — implementation note: cold-partition membership filter (D-21 layout).**

- The evidence layout is implementation-owned under D-21. Benchmarking showed that an incremental render looked up each brand-new identity in its cold partition, even though new identities are almost always absent. At 64 children that cost about 256 KB of partition reads per render, above the base ledger bytes.
- Each cold partition now carries a membership filter (Bloom, 10 bits per key, 7 probes). It lives in the hot evidence file, which ingesting renders already read and write, and never in the compact summary, which no-change renders read. A filter is rebuilt only when its partition's key set grows (eviction, split, or a new key written into it). It adds no file and no replacement.
- A filter may only prove absence. A missing, malformed or undersized filter means "maybe present" and falls back to reading the partition. A false "absent" would double-count a fork replay of an evicted request, so it is never assumed. Tests pin eviction-then-replay, malformed filters, split membership and later eviction into a filtered partition, and each is killed by a mutant.

**2026-09-27 — AC-39 incremental count gate and AC-01 compact labels (owner decisions).**

- **AC-39.** The owner chose to gate incremental renders on bytes and wall-clock, and to bound file counts by formula (see AC-39). Evidence came from a quiet back-to-back 40-render benchmark with one hot-to-cold eviction in the window:
  - every timing and byte gate passed;
  - median incremental time was 150–165 ms against 187–277 ms at base;
  - ledger bytes read fell 50–94%;
  - replacements were 96 against 80 at 1k requests and 181 against 80 at 10k. The excess is one eviction batch rewriting about 16 or about 100 partitions.
- **Trade-off accepted:** an evicting render (about 1 in 64–128) is write-bursty and holds the lock longer. On a slow or synced home directory that render costs more, and a concurrent render can show a stale `*` once. The alternative was a time-routed cold store touching about one file per eviction. It was rejected because its dedupe lookup would rest on an unproven timestamp-routing assumption for fork replays.
- **AC-01 labels.** The owner accepted two renderings:
  - In a box too narrow for the full label, the word drops and the provenance symbol stays (`≈$N`, `≥$N`, `h≈$N`), so a figure is never clipped mid-number.
  - When usage exists but no defensible dollar figure does (unavailable with no host estimate, or everything unpriceable), the cell reads `api≈?`, distinct from `$0`.

## Intent

Make the Claude Code statusline's token and dollar accounting trustworthy in all of these conditions:

- long sessions;
- delegated and forked execution;
- advisor calls;
- cache usage;
- transcript replay;
- calendar-day boundaries;
- malformed records;
- new model versions;
- temporary host-data failures.

It must do this **without increasing steady-state statusline cost**. The target is correct accounting at equal or lower steady-state statusline latency and I/O than `main`.

The statusline must answer two distinct questions without conflating them:

1. **What API-equivalent list-price cost can codeArbiter reconstruct from locally observable usage?**
2. **What cost estimate did Claude Code itself report for the parent session?**

The first is the primary codeArbiter accounting metric. The second is an independent reconciliation/fallback source, not authority over the first.

A displayed dollar value must never silently imply any of these without the evidence to support it:

- actual billing truth;
- that every source is included;
- exact pricing.

## Problem

The current implementation mixes incompatible accounting sources and contains several independent correctness failures.

`_ledgerlib.py` reconstructs parent-session token usage from the transcript, but normally replaces its calculated cost with `cost.total_cost_usd` from Claude Code. The code and comments describe that host value as authoritative and as including delegated execution. The current Claude Code status-line contract does not promise that, and known delegated-session behavior contradicts it.

At the same time:

- delegated/subagent transcripts are discovered for presentation but are not first-class sources in the cost ledger;
- the 20,000-new-line processing limit can permanently skip every unread transcript line after the limit. The stored offset advances to EOF instead of to the last consumed line;
- the Today token bucket uses event timestamps, but Today cost sums whole-session `host_cost`, which moves pre-midnight spend into the current day;
- an unusable timestamp is attributed to Today (`_msg_date` falls back to `now`);
- an absent or malformed host cost is coerced to zero and can replace previously valid host state;
- a lower host cost for the same session is accepted, although cumulative same-session cost should not normally regress;
- unknown models silently receive Sonnet pricing;
- family-level pricing cannot distinguish model generations whose prices differ. For example, the current `"fable"` family entry prices Fable 5.1 cache reads at $1.00/MTok; the published rate is $0.25;
- cache-write aggregate and TTL-specific fields are not reconciled robustly;
- malformed request identities can prevent forward progress;
- duplicate request records use last-write-wins even when a later replay contains less complete usage;
- observable separately metered server-tool activity is discarded;
- billable advisor iterations nested in `usage.iterations` are discarded;
- presentation-oriented subagent bounds would be unsuitable as accounting bounds;
- the presentation path parses up to 12 child transcripts × ~2,500 lines on every render;
- ledger lock contention waits up to 200 ms and then renders fabricated zero totals;
- documentation alternates between calling the dollar value an API-equivalent estimate and an authoritative/real session cost.

This work corrects the accounting model rather than adding patches around individual totals.

## Observed transcript semantics (2026-09-27 characterization)

The local corpus scanned was 23 parent transcripts, 92 delegated transcripts and 18,427 assistant usage records. It was produced by Claude Code on this machine between 2026-09 and 2026-09-27. These are observations, not a host contract. The implementation re-verifies them against sanitized fixtures (plan T-02), and fixtures encode each shape.

1. **Fork replays cross sources.**
   - A forked child transcript starts with a `{"type":"fork-context-ref", "parentSessionId", "parentLastUuid", ...}` record. It is followed by a copy of the parent's spawning assistant message, which has:
     - the same `requestId` and `message.id`;
     - `isSidechain: true`;
     - a different `uuid`;
     - sometimes an earlier *partial streaming snapshot* of the usage (e.g. `output_tokens` 2 vs 7151) with an earlier timestamp.
   - 8 parent↔child overlaps and 15 sibling↔sibling overlaps were observed. All were this replay.
   - No `requestId` repeated across distinct top-level session files.
   - **Source-scoped identity would double-count every fork.**
2. **Advisor iterations are billable and excluded from the top-level counters.**
   - 177 records carry `usage.iterations` with 3 entries: `type:"message"`, `type:"advisor_message"` (with its own `model`, e.g. `claude-opus-5`, `claude-opus-5-5`), and `type:"message"`.
   - In every case the top-level `input/output/cache_*` counters equal the sum of the `message` iterations only.
   - The host's own `cost-state` record bills the advisor model separately. For example, the host's `claude-opus-5` output tokens equal the transcript's advisor-iteration output tokens exactly in several sessions.
3. **The top-level cache TTL split is stale on multi-iteration records.**
   - In all 177 records where `cache_creation.ephemeral_5m + ephemeral_1h ≠ cache_creation_input_tokens`, the top-level split reflects only the first iteration. The per-iteration splits sum exactly to the aggregate.
   - In all other 18,250 records the split equals the aggregate.
4. **Streaming snapshots are monotone.** 6,981 same-source duplicate groups exist. Every differing component grows across snapshots: output always, and input/cache when later iterations are added.
5. **`<synthetic>` records** (15) have `model:"<synthetic>"` and all-zero usage. One of them carried no `requestId`, and it was the only record lacking one.
6. **Modifier fields are present in the usage records:**
   - `speed` (`standard`; absent on 3,924 older records);
   - `service_tier` (`standard`);
   - `inference_geo` (`not_available`).
   - No `fast`, `us`, batch or priority values were observed.
7. **Server-tool counters are present** (`server_tool_use.web_search_requests`, `web_fetch_requests`). All were zero in this corpus, so non-zero fixtures are synthetic and are labeled as such.
8. **Other record types** that carry no billable usage, and which are ignored as non-usage:
   - `mode`, `permission-mode`, `bridge-session`, `attachment`, `atis-latch`, `last-prompt`;
   - `ai-title`, `queue-operation`, `file-history-*`, `pr-link`, `worktree-state`;
   - `relocated`, `agent-name`, `custom-title`, `system`, `user`, `fork-context-ref`.
   - `cost-state` records hold the host's own cumulative per-model usage, including hidden side-query models such as Haiku title generation, which appear in no transcript usage record, and host model labels like `claude-opus-5[1m]`. They are host evidence, not reconstructed usage.
9. **Child metadata:** `<session>/subagents/agent-*.meta.json` carries `agentType`, `description` and `spawnDepth`. Accounting discovery must glob `*.jsonl` only.
10. **Line sizes:**
    - The largest line in the corpus is 279 KB (a `user` record). Assistant lines reach at most 118 KB, and no line exceeds 1 MiB.
    - In assistant lines, `"type":"assistant"` is *not* near the start of the line (p50 offset 1.6 KB, max 118 KB), so a cheap prefix check cannot classify a line.
    - The `"usage":` key always sits within 49 KB of the line's end (p99 13.5 KB).
    - Escaped occurrences inside content (`\"usage\"`) do not contain the byte sequence `"usage":`.
    - `"type":"assistant"` sits within 1.6 KB of the end of every assistant line.
    - 11 `attachment` records (`task-notification`) carry `"usage":{"totalTokens",...}`, which summarizes a child's usage. They are **never** billable usage: counting them would double-count the child transcript.

## User-facing accounting contract

### Session tokens

The Session token counters represent all successfully reconstructed usage belonging to the current Claude session, including locally discoverable delegated child transcripts and advisor iterations.

The existing display definition is retained:

- input = uncached input + cache-write tokens;
- cache-read tokens remain excluded from the visible input counter, so repeatedly served context does not dominate the number;
- output = output tokens;
- cache reads remain part of cost accounting.

### Today tokens

Today uses the same token definition as Session, but includes only usage events whose own event time falls on the current local calendar day.

A session crossing midnight is split by event time. Activity before midnight must never reappear in the next day's totals merely because the session remains active. Usage with no trustworthy event time is counted in Session, never in Today, and makes Today coverage partial.

### Primary dollar metric

The primary dollar value is **codeArbiter reconstructed API-equivalent cost at pinned public list rates**. It is not an invoice and not actual account spend.

The normal complete label is:

`api≈$N`

It means three things:

- every locally discovered usage item in scope has been processed;
- every billable component represented by that item has a known pricing rule;
- every counted request has a proven identity.

When codeArbiter can calculate only a known subset, the label is:

`api≥$N`

That happens when some observable usage cannot be priced, cannot be uniquely identified, or has no trustworthy time for the Today scope, or when the incremental scanner is still catching up.

The amount must be a true lower bound. It includes only non-negative amounts from requests whose identity is proven unique, priced by known rules. Unknown usage is never silently priced as another model or discarded while presenting the total as complete.

When usage is known to exist but no defensible reconstructed dollar value exists:

`api≈?`

### Claude-reported fallback

`cost.total_cost_usd` is retained separately as Claude Code's reported **estimated session cost**.

It is never:

- added to reconstructed child cost;
- combined through `max(host, reconstructed)`;
- combined algebraically with reconstructed API-equivalent cost in any other way.

If reconstructed Session cost is unavailable but a valid Claude-reported value exists, Session may display it explicitly as:

`host≈$N`

Today must not manufacture a day-specific value from a whole-session host value.

### Actual billing

No codeArbiter statusline value is called a bill, real billed cost, authoritative billing cost, or actual account spend.

These are incorporated only when the usage record exposes enough information *and* the pricing registry explicitly models them (D-27):

- discounts, credits and subscription treatment;
- custom `modelPricing`;
- provider-specific rates;
- data-residency modifiers;
- fast-mode premiums;
- other modifiers.

Otherwise they remain outside the reconstructed API-equivalent claim.

## Scope

This effort includes:

- correct, bounded, incremental processing of the parent Claude transcript;
- durable accounting of all locally discoverable delegated transcripts belonging to that parent session, within a declared discovery bound;
- one shared parser, normalization and deduplication contract for transcript usage, consumed by both accounting and presentation;
- exact/version-aware model pricing and explicitly modeled price modifiers;
- cache-write and cache-read accounting;
- advisor-iteration accounting;
- separately metered server-tool charges, when the transcript exposes them and codeArbiter has an explicit pricing rule;
- event-based Session/Today aggregation;
- independent preservation and reconciliation of Claude's host-reported estimate;
- explicit, per-scope coverage state;
- incrementally maintained derived totals;
- non-blocking statusline ledger access;
- ledger migration;
- a base/head latency and I/O benchmark;
- docs and deterministic regression coverage.

## Out of scope

This spec does not:

- query Anthropic billing, Console, organization usage, or any network API at statusline render time;
- claim to recover API activity Claude Code does not expose in any locally readable usage record. That includes hidden side queries visible only in host `cost-state` aggregates;
- infer hidden side-query/classifier cost from unrelated telemetry;
- fabricate provider, discount, data-residency, batch, fast-mode, or other price modifiers;
- merge reconstructed and host-reported dollars to make disagreement disappear;
- introduce a periodic `refreshInterval` (a separately measured follow-up; see D-13);
- redesign the overall statusline;
- change Pi's separate usage ledger or Pi footer accounting semantics;
- introduce third-party Python dependencies.

## Definitions

**Observable usage event:** a locally readable transcript record carrying billable usage counters, advisor iterations, or separately metered tool counters.

**Source:** one parent or delegated transcript belonging to the current Claude session.

**Request identity:** the dedup key of one API request. It is one of `rid:<requestId>`, `mid:<message id>`, or *unproven* (D-5).

**Reconstructed API-equivalent:** the sum of priceable, identity-proven observable usage, using codeArbiter's pinned pricing registry.

**Host-reported estimate:** the current `cost.total_cost_usd` value received in Claude Code's status-line payload.

**Coverage** is computed separately for the Session scope and the Today scope:

- **Complete:** every discovered source is scanned through its current durable end. Every observed billable component is understood and priceable, every counted request has a proven identity, and (for Today) every in-scope event has a trustworthy time.
- **Catching up:** work remains only because a bounded per-render budget deferred records or sources.
- **Partial:** all currently processable data has been consumed, but at least one observed component or record cannot be counted safely. Coverage carries a reason set such as:
  - `unknown_model`, `unpriced_modifier`, `unknown_charge`, `unknown_iteration`;
  - `unknown_cache_ttl`, `unproven_identity`, `malformed_record`, `oversized_record`;
  - `unknown_event_time`, `conflicting_event_day`, `model_conflict`;
  - `source_vanished_with_backlog`, `discovery_bound`.
- **Unavailable:** no defensible reconstructed monetary total can currently be produced.
- **Stale** is orthogonal to the other states. The rendered values come from the last committed snapshot because this render could not acquire the ledger lock (D-17).

## Load-bearing design decisions

### D-1 — Reconstructed usage owns `api≈`

The primary monetary metric is reconstructed from usage records. `cost.total_cost_usd` does not override it.

### D-2 — Claude's cost is reconciliation evidence, not arithmetic input

Persist the host-reported estimate independently. Track at minimum:

- the latest valid value;
- the maximum value observed for the same session (`max_seen`);
- whether the latest value regressed;
- whether it disappeared after previously being present;
- comparison state when reconstructed cost is complete.

A missing, null, malformed, boolean, negative, NaN, or infinite host value does not overwrite a previously valid value with zero.

A same-session decrease is recorded as anomalous and does not redefine reconstructed spend.

When `host≈` is the displayed fallback, the value shown is the same-session `max_seen`, not the latest-by-completion-order observation. Overlapping renders can deliver stale payloads out of order. The literal latest observation is retained for diagnostics. A new session ID starts from zero.

A host/reconstructed difference is diagnostic evidence. It does not cause one number to replace or be added to the other.

### D-3 — Delegated transcripts are first-class accounting sources

Parent and delegated transcripts are accounted through the same parser and normalization rules.

The accounting scanner discovers `<session>/subagents/*.jsonl` for the parent session and persists independent progress for every child transcript, within the discovery bound of D-25. Non-JSONL siblings (e.g. `*.meta.json`) are not sources. Plan T-02 confirms where nested (`spawnDepth > 1`) children are written. If a class of child cannot be associated with the parent without guessing, it is reported as unobservable rather than found by broadening directory walks.

The recent-subagent presentation limits (`SHOW_WINDOW`, `MAX_SUB_FILES`, `MAX_SUB_LINES`, visible-row count) do not constrain accounting.

A child that finished hours ago remains represented in Session and Today accounting while its session ledger remains live.

More than 12 delegated transcripts must be handled correctly.

### D-4 — Bounded work may defer records; it may never discard them

A processing ceiling exists to bound render latency, not to truncate history.

When a scan stops because it reaches its per-render record/byte/source budget:

- the persisted offset is the byte immediately after the last complete record actually consumed;
- unconsumed bytes remain pending;
- the next render resumes exactly there;
- coverage is `catching_up` until every discovered source reaches its current end.

No limit may advance an offset over unread data. Reading the entire remaining file into memory before applying a record limit does not satisfy the bound.

### D-5 — Request identity: classified, domain-separated, session-scoped

Every usage record's identity is classified as follows:

1. **`rid:<requestId>`** — `requestId` is a non-empty `str` of at most 256 characters with no control characters.
2. **`mid:<message.id>`** — no trustworthy `requestId`, and `message.id` meets the same test.
3. **Unproven** — neither exists or passes the test. This includes missing, empty, numeric, boolean, list and object values.

Identity keys are domain-separated by their prefix, so a real ID that textually resembles a key of another class cannot collide with it.

**Scope is the session, not the source.** Request IDs are server-issued per API call. Fork replays (observation 1) copy the parent's request into child transcripts, so an identical `rid`/`mid` in parent and child — or in two children — is **one** request and is reconciled once under D-6. Evidence retains every source that observed the request, for diagnostics and for source-local presentation (D-7).

A record carrying both IDs registers a `mid→rid` alias. A later or earlier record carrying only the message ID merges into that request, whatever the arrival order: reconciliation is order-independent.

An **unproven** record:

- still advances the scanner;
- is retained as coverage evidence, with source and byte position;
- contributes to neither tokens nor dollars in any scope;
- makes that scope's coverage `partial` (`unproven_identity`), unless the record is non-billable (all usage counters zero, e.g. `<synthetic>`, observation 5). Zero-usage records never affect coverage, whatever their identity or model.

Lists, dictionaries and other unhashable values never raise, and never wedge a source at the same offset.

### D-6 — Duplicate usage converges monotonically and order-independently

Repeated representations of one request are reconciled, never blindly summed or overwritten last-write-wins.

For each cumulative component of a request (per charge class and model, D-26), the accepted value is the maximum observed across all representations. Cache writes follow D-9's classification model, not an independent per-field maximum.

Reconciliation is commutative and associative. The accepted state after any permutation of the same record set is identical. This is required because round-robin scanning (D-14) and fork replays make arrival order across sources arbitrary.

Conflicting model identities for one request are not resolved by whichever line appeared last. They make that request's pricing identity ambiguous (`model_conflict`, partial) unless an explicit normalization rule proves the IDs equivalent. Model-alias normalization, such as a stripped `[1m]` context label, is one such rule.

### D-7 — One parser and one normalizer; presentation reads summaries

The repository has **one** transcript parser and **one** pure normalization contract for:

- record decoding and validation;
- token coercion and validation;
- model identity and modifiers;
- cache fields;
- iterations;
- server-tool counters;
- timestamps;
- request identity;
- duplicate reconciliation.

The accounting scanner is the only code that decodes transcript JSONL on the render path.

For each source it maintains a compact **presentation summary**:

- label;
- observed model(s);
- display input/output;
- last observed mtime/size;
- source accounting subtotal.

The per-child subtotal attributes a fork-replayed request to the source that owns it. The *owner* is the parent if the parent observed the request, otherwise the lexicographically smallest observing source; replayed copies are excluded. This keeps presentation deterministic and prevents a forked child from displaying the parent's spawning call as its own spend.

`_subagentslib` consumes those summaries, plus the cheap filesystem metadata (directory listing, `stat`, optional `*.meta.json` label) needed for active/recent liveness presentation. It no longer opens or parses child JSONL.

Presentation limits remain as they are for what is *shown*.

### D-8 — Pricing is version-aware; unknown does not mean Sonnet

Remove the unknown-model-to-Sonnet pricing fallback.

Pricing lookup uses exact recognized model IDs, after a small explicit alias-normalization table: dated snapshot suffixes and the `[1m]` context label. Family aliases are allowed only where the aliased models are explicitly known to share the same price tuple.

The registry records its capture date and source URL. At implementation time it covers:

- the current Claude Code models: Fable 5.1, Opus 5.5, Sonnet 5, Haiku 4.5;
- the still-supported historical IDs present in resumable transcripts, at minimum `claude-opus-5`, observed in 571 records plus advisor iterations;
- Opus/Sonnet 4.x where cheaply tabulated.

`claude-opus-5` is the required AC-13 historical case. Its price differs from Opus 5.5 on every component.

Long-context (`[1m]`) usage on 4.6-and-later models is billed at standard rates. The alias rule encodes that, not a guess.

An unknown future/custom model contributes tokens but marks monetary coverage partial (`unknown_model`). It never borrows another model's rate.

`<synthetic>` with all-zero usage is non-billable (no tokens, no cost, no coverage effect). `<synthetic>` with any non-zero counter is treated as an unknown model.

### D-9 — Cache writes are a total plus a classification, never independent counters

Per request, canonical cache-write state is:

```text
total_write       = max observed cache_creation_input_tokens across representations
known_5m, known_1h = the best-classified split observed, each ≤ total_write
unknown           = total_write − known_5m − known_1h   (≥ 0)
```

The split source, in priority order:

1. The sum of per-iteration `cache_creation` splits across `type:"message"` iterations, when present and summing to the aggregate (observation 3).
2. The top-level `cache_creation` split, when it sums to the aggregate.
3. Otherwise, the top-level split counts only as a *partial* classification (each component capped so the classified sum ≤ total) and the remainder stays `unknown`.

A split whose components sum to more than the aggregate is inconsistent. The aggregate stands, and the excess is not priced as extra writes.

A replay may make the classification more specific, i.e. reduce `unknown`. It never increases `total_write` beyond the maximum aggregate observed. A less-classified replay never undoes a more complete classification.

An `unknown` remainder is not assigned a cheaper or more expensive TTL to obtain a number. It makes monetary coverage partial (`unknown_cache_ttl`), and its tokens still count in the input display.

### D-10 — Separately metered server tools: priced, known-zero, or unknown

The charge registry classifies each `server_tool_use` counter as one of:

1. **Separately priced** — e.g. `web_search_requests` at $10 / 1,000.
2. **Known zero-incremental** — e.g. `web_fetch_requests`: no charge beyond tokens. A non-zero value never makes coverage partial.
3. **Unknown or unpriceable** — any other counter, including `code_execution_requests`, which is billed by container time the transcript does not expose. A non-zero value makes coverage partial (`unknown_charge`).

Charge counters reconcile per request by maximum (D-6).

The engine stays extensible by charge class and must not assume that all spend is `tokens × model price`. It stays a set of pure functions and immutable tables, not a plugin framework.

### D-11 — Calendar-day attribution is event-derived and replay-stable

Every reconstructed component inherits its request's **event time**. That is the minimum trustworthy timestamp across all representations of the request.

A trustworthy timestamp is a parseable ISO-8601 string whose year falls in a sane window. Anything else — missing, unparseable, or outside the window — is untrustworthy.

Minimum is commutative, so neither scan order nor replay arrival order can change the result (D-6). It also approximates request start for forked copies, which carry earlier snapshot timestamps.

- Session cost/tokens sum all accepted requests.
- Today cost/tokens sum only requests whose event time falls on the current local calendar day.
- A request with no trustworthy timestamp in any representation counts in Session only. Today coverage becomes partial (`unknown_event_time`). It is never attributed to Today by default.
- If a request's trustworthy representations fall on different local days, the minimum still decides, and the affected day scopes carry `conflicting_event_day`. The attribution is deterministic and visible, never silent.
- Whole-session host cost is never assigned wholesale to Today.

A session or delegated child crossing midnight splits consistently for both tokens and reconstructed cost.

### D-12 — Coverage is durable, structured, and per-scope

The ledger returns, separately for Session and for Today:

- the coverage state;
- the reason set;
- a staleness flag.

The renderer does not infer completeness from receiving a number. A newly discovered, unscanned child source immediately prevents a complete claim.

### D-13 — No periodic refresh in this effort

Accounting correctness relies on the host's normal event-driven renders. This effort adds **no** `refreshInterval`. The owned statusline configuration and the install/refresh/uninstall behavior of `wire-statusline.py` are unchanged.

While the parent is idle, background children's spend becomes visible on the next render. This is a documented freshness limitation, not an accounting error: work is deferred, never lost.

A periodic interval can be proposed later as a separate change. It needs its own base/head benchmark of the render envelope on supported platforms, with headroom and without self-overlap, and its own tests.

### D-14 — Incremental accounting is bounded and starvation-free

Each render has explicit budgets:

- **Accounting byte budget** — total transcript bytes read across sources.
- **Record budget** — records decoded.
- **Source budget** — sources opened.
- **Per-record byte ceiling** — 4 MiB, about 14× the largest line observed (observation 10). A single JSONL line longer than the ceiling is consumed without being decoded.

An oversized line is still consumed deterministically: the scanner advances past its terminating newline. If the line's terminator lies beyond the render's byte budget, the scanner persists a *skip-until-newline* position and continues next render.

While passing over the line, the scanner retains only its final 64 KiB. That window covers the observed usage position with more than 1.3× headroom.

- If that tail contains both `"usage":` and `"type":"assistant"`, the line is **usage-bearing**. It records `oversized_record` and makes coverage partial, never being silently skipped as though it held no usage.
- Otherwise it is a non-usage line, such as a large `user`/`attachment` tool result or image, and it is ignored without affecting coverage.

Reads are line-streamed from the stored offset. The remaining tail is never read whole.

Scheduling across sources is fair, using a persisted round-robin cursor or an equivalent. Repeated renders with unchanged files eventually consume every discovered source through EOF. Neither a continuously growing parent nor many children can permanently starve the other.

While backlog exists, coverage is `catching_up`.

### D-15 — Replacement detection covers truncation, same-size and larger replacement

Each source persists a generation fingerprint:

- the byte offset;
- a hash of the file's first ≤4 KiB, the head;
- a hash of the ≤4 KiB immediately preceding the stored offset, the tail of the consumed region.

The source is re-verified whenever its `stat` (size, mtime, and inode/file-id where available) differs from the stored value. Re-verification costs at most two bounded reads.

A size below the offset, or a head or tail mismatch, means **replacement**. The source's derived requests are discarded and it is rebuilt from byte 0 as a new generation. This applies to truncations and same-size replacements alike, and to larger replacements (e.g. 4 MiB → 6 MiB).

Rebuilding is isolated. Parent and sibling accounting is untouched, except where session-scoped reconciliation (D-5) must recompute a request that the replaced source also observed. That recompute uses the remaining observers' evidence.

A no-change render does not re-verify, because the `stat` is unchanged.

### D-16 — Existing ledger state migrates deliberately

Current ledger files are expected in the field. A new schema must:

- recognize the current parent-only `reqs`/`tx_off` representation;
- preserve session-start metadata where valid;
- never reinterpret old `host_cost` as reconstructed cost. It may seed the host-estimate record as a `max_seen` candidate;
- rebuild transcript-derived accounting from replay rather than pretend incompatible cached values are exact. During the rebuild, coverage is `catching_up`;
- use atomic replacement and the existing lock discipline;
- fail soft if old state is malformed.

Migration must not require the user to delete `~/.codearbiter/ledger.json`.

### D-17 — Concurrency, atomicity, and non-blocking UI access

The existing independent session shards, lock, atomic replacement and same-session race protections remain.

Adding multiple sources must not reopen lost-update behavior. A concurrent session-start metadata write cannot erase accounting progress, and simultaneous renders cannot regress a source offset or accepted usage.

**The statusline render path does not wait out the full lock budget.** It makes a short try-lock attempt, bounded by a constant of at most 20 ms. On contention it renders the **last committed snapshot** with its coverage preserved and the `stale` flag set. Scanning is deferred to a later render.

A render that loses the lock race never displays fabricated zero totals. When no committed snapshot exists yet, the monetary state is `unavailable` (rendered distinctly from `$0`), not zero.

Other writers that need serialized mutation keep the existing blocking budget.

### D-18 — Generated-source discipline remains unchanged

`core/pysrc/` remains canonical. Do not independently patch:

- `plugins/ca/hooks/`
- `plugins/ca-pi/hooks/`
- `plugins/ca-codex/hooks/`

Canonical changes are synchronized through the existing generation path, and sync checks must remain byte-clean.

### D-19 — Documentation has one cost vocabulary

Public docs, command docs, source comments, and screenshots/fixtures must consistently distinguish:

- reconstructed `api≈`;
- partial/lower-bound `api≥`;
- Claude-reported `host≈`;
- stale/unavailable states;
- actual billing, which codeArbiter does not claim.

Remove statements that `cost.total_cost_usd` is authoritative, "real", guaranteed to include subagents, or exactly equal to the user's bill.

### D-20 — Performance and I/O contract

Steady-state statusline cost must be equal to or lower than on `main`. Structural I/O is the gated measure, because CI timing is noisy. Wall-clock is compared as an acceptance artifact.

- **No-change render** means: no source's `stat` changed, no new source was discovered, the host estimate payload is unchanged, and the ledger heartbeat (`LEDGER_HEARTBEAT`, 300 s, which keeps a live session inside its TTL) is not due. Such a render has:
  - zero transcript content bytes read;
  - zero ledger files written;
  - zero request-evidence partitions deserialized.
- **Host-only change:** a changed host estimate rewrites the compact summary only, reading no transcript bytes and no evidence partitions.
- **Heartbeat:** the heartbeat write happens at most once per `LEDGER_HEARTBEAT` and touches only the compact summary. It is intentional, and it is tested so that it is neither removed nor multiplied.
- **Incremental render:** transcript bytes read ≤ the accounting byte budget, plus at most two bounded fingerprint windows per changed source.
- **Single decode:** each JSONL record is decoded at most once per render, by the accounting scanner only. Presentation decodes no JSONL.
- **History scaling:** the work of a no-change render, and of an incremental render with *k* new records, does not grow with the count of already-accepted requests. Fixtures at 1k, 10k and 100k accepted requests demonstrate this through counters of bytes deserialized and evidence partitions loaded (D-21).
- **Lock:** the render path's maximum lock wait is ≤ 20 ms (D-17).
- **Base/head benchmark:** a deterministic generated-fixture benchmark is committed **before** implementation code and recorded against the base commit. The scenarios are:
  - 0, 1, 12, 13 and 64 children;
  - a long parent;
  - warm no-change renders;
  - incremental renders.

  Production runs one fresh process per render, so the benchmark does the same. It drives the stable external entry point — the statusline script, with a JSON status payload on stdin and `HOME`/ledger/transcript roots redirected by environment variable — as **one subprocess per render**, so that import cost is measured. A small wrapper installs a `sys.audit` hook plus read/write accounting in that child process, so the identical harness runs unchanged against base and head. It counts file opens, bytes read, bytes decoded, ledger writes, and elapsed time. The candidate's structural counters for no-change and incremental renders are ≤ base. Warm-render median and p95 on identical fixtures and the same machine are ≤ base × 1.05, and the report is retained in the implementation PR.

### D-21 — Derived totals are maintained incrementally

Normalized request records remain the authoritative evidence. Renders read **derived indices**, maintained by subtract-old / add-new whenever a request's accepted state changes:

- per-source totals;
- per-source per-local-day totals;
- session totals;
- a compact per-session summary, consisting of Session + per-day totals, coverage, offsets, fingerprints, presentation summaries and the host estimate.

Request evidence is stored so that an incremental render deserializes only the partitions its new records touch, and the compact summary is stored separately from the evidence.

**Every evidence partition has a fixed maximum size**, a named constant. A partition that would exceed it splits, for example by extending its identity-hash prefix. A fixed bucket count that grows O(history/B) does not satisfy this rule. The layout is otherwise implementation-owned, provided D-20's history-scaling counters hold.

Full rebuild of the derived state occurs only in these cases:

- schema migration;
- a pricing-registry version change;
- source generation replacement;
- detected derived-state inconsistency, for example a summary checksum or version mismatch.

Today aggregation across prior live sessions reads their compact summaries, never their request evidence.

### D-22 — Source lifecycle

- **A source disappears after being scanned to EOF:** its accepted accounting is preserved. It is marked vanished and remains in totals while the session ledger is live.
- **A source disappears with unscanned backlog:** the accepted subtotal is preserved and coverage becomes partial (`source_vanished_with_backlog`).
- **A source is discovered but disappears before any scan:** coverage becomes partial (`source_vanished_with_backlog`).
- **A source reappears at the same path with a mismatched fingerprint:** it becomes a new generation (D-15).
- **Directory listing fails:** known sources keep their accounting, and coverage is `catching_up` until a listing succeeds.

### D-23 — Host fallback is order-robust

See D-2. `max_seen` is the displayed `host≈` value, which makes the tracked maximum operationally meaningful.

### D-24 — Malformed records affect coverage, not rendering

Rendering stays fail-soft. Accounting records its uncertainty. A consumed record is `malformed_record`, and coverage becomes partial, when its shape prevents determining whether it represented billable usage.

One rule applies to undecodable, non-object and oversized lines alike. A line is **usage-bearing** when its final 64 KiB contain both `"usage":` and `"type":"assistant"` (observation 10). This excludes the `attachment` task-notification usage summaries. Only usage-bearing lines can affect coverage. The cases are:

- a usage-bearing line that is undecodable JSON, or is valid JSON but not an object;
- an assistant record whose `usage` is present but not an object;
- non-finite, negative or boolean counters;
- fractional token counters;
- counters above a sanity ceiling.

These are ignored without affecting coverage:

- recognized non-usage record types (observation 8);
- unknown record types with no `message.usage`;
- non-usage-bearing undecodable or oversized lines.

### D-25 — Discovery is bounded

The child discovery bound is **4,096 JSONL entries per session**. The bound is a named constant, and the directory listing is capped at that many entries per render. Within the bound every child is discovered and accounted.

Beyond it, codeArbiter does not walk more directory state. Known sources keep their accounting, and coverage is partial (`discovery_bound`). Correct-but-partial is preferred over an unbounded statusline.

### D-26 — Advisor iterations are accounted

For a record with `usage.iterations`:

- The top-level counters represent the `type:"message"` iterations (observation 2). They are priced at the record's model.
- Each `type:"advisor_message"` iteration is a separate charge component. It is priced at *that iteration's* `model`, with its own input/output/cache counters, and attributed to the same request identity and event time.
- Iterations are aggregated in two stages:
  1. **Within one representation**, iterations of the same (type, model) are **summed**, because one turn can contain several advisor calls.
  2. **Across representations** of the request, those sums reconcile by **maximum** (D-6).

  Taking the maximum per individual iteration would undercount.
- An iteration of any other `type` with non-zero counters makes coverage partial (`unknown_iteration`).
- An advisor iteration without a model, or with an unknown one, counts its tokens and makes coverage partial (`unknown_model`).

Advisor tokens appear in Session/Today token totals.

### D-27 — Observed price modifiers are priced explicitly or make coverage partial

- `speed`: `standard` or absent is standard. `fast` is priced only for models with a published fast rate (Opus 5.5, Opus 5, Opus 4.8), using the registry's fast rates, with the cache multipliers applied on top as published. Otherwise `unpriced_modifier`.
- `inference_geo`: absent, `not_available` or `global` is standard. `us` applies the published 1.1× multiplier on models 4.6 and later. Any other value is `unpriced_modifier`.
- `service_tier`: `standard` or absent is standard. Any other value is `unpriced_modifier`.

**Documented default:** `speed`, `inference_geo` and `service_tier` are opt-in request parameters, and each defaults to standard pricing. That is why an absent field is treated as standard.

**Assumption:** treating `inference_geo: "not_available"` as standard is an *inference*, not documented host behavior. It is the only value observed across 18,412 records from a Claude Code install that never opted into data residency. The rule is isolated in the modifier table, so that a contrary observation changes one entry. T-02 records this assumption with the fixtures.

## Logical ledger model

The exact serialized layout is implementation-owned. The durable model must be equivalent to:

```text
session summary (read every render; compact)
  identity, first/last timestamps, resolved session start
  sources[]: kind, locator, offset, skip-until-newline flag, fingerprint (stat + head/tail hash),
             lifecycle state, presentation summary, per-source totals + per-day totals
  scheduler cursor
  derived: session totals, per-local-day totals, per-scope coverage + reasons
  host estimate: latest valid, max_seen, last seen, regression/missing state, optional delta
  burn samples (parent-only)
  schema version, pricing-registry version

request evidence (loaded only for touched identities; partitioned)
  identity key (rid:/mid:/…) → observing sources, event-time min, per-charge-class/model
  component maxima, cache total + classification, model(s), modifiers
  mid→rid aliases
  unproven-record evidence (source, byte position, reason)
```

Request evidence must retain enough information to recompute pricing when the registry changes. That means normalized model identity, modifiers and usage components, never only a precomputed dollar subtotal.

## Reconciliation behavior

When both reconstructed and host-reported values exist, codeArbiter may calculate a diagnostic difference.

That comparison is informational, because legitimate divergence can result from:

- delegated sessions not represented in the parent host estimate;
- hidden side queries present only in host `cost-state` aggregates (observation 8);
- host `modelPricing`;
- custom/provider pricing;
- list-price changes;
- modifiers not represented in transcripts;
- host defects;
- codeArbiter pricing defects.

No fixed discrepancy direction proves which source is correct.

The statusline is not required to add another reconciliation segment. The diagnostic state must, however, be represented in testable ledger output.

## Acceptance criteria

- **AC-01 — Primary semantic contract.** Session and Today dollar values are reconstructed API-equivalent values whenever reconstruction is available. `cost.total_cost_usd` never overrides them or gets added to them. Rendering is:

  - complete → `api≈`;
  - partial or catching-up → `api≥`;
  - known but unpriceable usage → never a precise dollar total.

- **AC-02 — Host fallback is explicit.** When Session reconstruction is unavailable and a valid Claude-reported estimate exists, the renderer may display `host≈$N` using `max_seen`. Today never derives a fabricated daily value from that whole-session figure.

- **AC-03 — Parent plus delegated accounting.** A fixture containing one parent and multiple delegated transcripts produces Session tokens and reconstructed cost equal to the independently calculated sum of all accepted, deduplicated usage.

- **AC-04 — Presentation limits do not limit accounting.** Take a fixture with more than `MAX_SUB_FILES` delegated transcripts, including completed children older than `SHOW_WINDOW`. Every child is still included in Session/Today accounting, while the visible subagent panel stays bounded exactly as intended.

- **AC-05 — 20k-boundary loss is impossible.** Give the scanner more unread complete records than one render's budget allows. The first update stops at the last processed record, not EOF, and reports catching-up coverage. Subsequent updates consume the remainder exactly once and converge on the full independent total.

- **AC-06 — Processing bounds are real.** The incremental parser never reads the unbounded remainder of a transcript into memory before applying its ceiling. An I/O-counting fixture shows bytes read per render ≤ the accounting byte budget + fingerprint windows.

- **AC-07 — Partial trailing line.** A writer-flushed partial JSONL line does not advance the durable offset over the partial bytes. Once completed, the record is consumed exactly once.

- **AC-08 — Request identity is session-scoped (fork replay counted once).** A fork-replay fixture follows the observed shape: `fork-context-ref`, then the parent's spawning assistant message copied into one or more children with the same `requestId`/`message.id`, `isSidechain:true`, and a smaller, earlier partial snapshot. Session tokens and cost count that request **once**, at its maximum components. Neither the parent nor any child's presentation subtotal double-counts it; the owner rule of D-7 applies. Result totals are identical under every scan order of the sources.

- **AC-09 — Malformed identity cannot wedge accounting.** Missing, empty, numeric, boolean, array and object `requestId`/`message.id` values neither raise nor stop the offset from advancing. Such records are classified unproven under D-5.

- **AC-10 — Duplicate usage is monotonic.** A duplicate request whose later replay contains lower or partial counters cannot reduce previously reconstructed token or cost totals. A later, genuinely more complete record increases the corresponding components without double-counting.

- **AC-11 — Model conflict is honest.** Conflicting model identities for one request do not price the request last-write-wins. Unless an explicit alias rule proves equivalence, the affected monetary coverage becomes partial (`model_conflict`).

- **AC-12 — Exact model pricing.** Pricing tests cover the implementation-time current Opus, Sonnet, Fable and Haiku model IDs. They verify each exact input/output/5m-write/1h-write/cache-read price against the pinned registry, including Fable 5.1's $0.25 and Opus 5.5's $0.20 cache-read rates.

- **AC-13 — Historical pricing.** `claude-opus-5` is priced by its own exact rule ($5 / $25 / $6.25 / $10 / $0.50 per MTok as captured), not Opus 5.5's.

- **AC-14 — Unknown model behavior.** An unknown/custom/future model contributes its observed tokens but never receives Sonnet or another arbitrary price. Reconstructed monetary coverage becomes partial.

- **AC-15 — Cache accounting.** Fixtures cover every one of these cases without losing tokens, inventing a TTL, or pricing more write tokens than the maximum aggregate:

  - no cache;
  - cache read;
  - 5m write;
  - 1h write;
  - aggregate-only;
  - matching aggregate + split;
  - incomplete split;
  - inconsistent split where the split exceeds the aggregate;
  - the multi-iteration stale top-level split, where the per-iteration split must be used.

- **AC-16 — Server-tool charges.** The following hold:

  - A fixture with non-zero `web_search_requests` contributes $10/1,000 exactly once per request, including across duplicate representations.
  - Non-zero `web_fetch_requests` adds no charge and keeps coverage complete.
  - A non-zero unknown counter (and `code_execution_requests`) makes coverage partial instead of disappearing.

  The fixtures are synthetic and are labeled as such.

- **AC-17 — Cross-midnight parent.** Parent events on opposite sides of local midnight contribute to one Session total but separate calendar-day token and cost buckets.

- **AC-18 — Cross-midnight delegated activity.** The same split is proven for child transcript usage. A child that started yesterday and completed today does not move yesterday's spend into Today.

- **AC-19 — Host disappearance.** A valid host estimate, followed by a payload where the field is absent, null or malformed, does not replace the persisted valid host state with zero and does not alter reconstructed cost.

- **AC-20 — Host regression.** A same-session host value that decreases is retained as the latest observation, with an anomaly state. It cannot regress reconstructed spend, erase `max_seen`, or lower the displayed `host≈` fallback. A new session ID starts at zero.

- **AC-21 — Host disagreement is non-destructive.** Fixtures where the host cost is above, and below, the reconstructed cost preserve both values independently. They produce deterministic reconciliation state with no `max()`, addition or replacement.

- **AC-22 — Source catch-up is starvation-free.** Take a large, continuously growing parent plus enough children to exceed one update's budgets. Repeated updates eventually reach every unchanged source's EOF, and coverage transitions from catching-up to complete, within a deterministic, asserted number of renders.

- **AC-23 — Source replacement is isolated and complete.** Four replacements of one child — truncation, same-size replacement (4 MiB → 4 MiB, different content), larger replacement (4 MiB → 6 MiB) and rotation — each rebuild only that source's generation. Parent and sibling totals are unchanged, except for session-scoped requests the replaced source co-observed, which are recomputed from the remaining observers.

- **AC-24 — Burn semantics share normalized usage.** Burn samples are derived from the same accepted, deduplicated usage events. This effort retains **parent-only** burn, explicit in code and docs, and tested: child-only usage and fork replays leave parent burn unchanged.

- **AC-25 — Ledger migration.** A current production-shaped ledger migrates without manual deletion. It preserves valid session-start metadata, never mistakes historical `host_cost` for reconstructed cost, and converges to correct totals after transcript replay.

- **AC-26 — Corrupt migration fails soft.** Malformed legacy ledger/session shards cannot break the statusline or contaminate healthy session/source records.

- **AC-27 — Concurrency.** Distinct-session and same-session concurrent updates preserve all of these under the existing serialization/atomic-write contract:

  - every accepted source;
  - every source offset;
  - every request;
  - every derived total;
  - the session-start value.

- **AC-28 — No periodic refresh introduced.** `owned_statusline()` output and the install/refresh/uninstall behavior are unchanged; existing `test_wire_statusline.py` stays green unmodified in intent. Docs state the idle-freshness limitation, and that deferred work is never lost.

- **AC-29 — No render-time network.** The feature works offline from:

  - local status payloads;
  - transcripts;
  - pricing data shipped with codeArbiter;
  - the local ledger.

- **AC-30 — Fail-soft rendering, coverage-aware accounting.** Each of these degrades only the affected accounting state, never emits a traceback, and never blanks the rest of the statusline:

  - missing transcript path;
  - vanished child directory;
  - concurrently removed file;
  - permission error;
  - malformed JSON;
  - invalid usage type;
  - unknown model;
  - oversized record;
  - ledger lock contention.

  Each case that D-22, D-24 or D-14 classifies as affecting coverage produces the specified partial reason.

- **AC-31 — Public vocabulary.** These all describe `api≈`, `api≥`, `host≈` and stale/unavailable accurately:

  - command docs;
  - the statusline guide;
  - source comments;
  - fixture comments;
  - screenshots.

  None of them still claims that `cost.total_cost_usd` is authoritative billing truth or is guaranteed to aggregate delegated sessions.

- **AC-32 — Canonical-source parity.** All Python implementation changes originate in `core/pysrc/`. Generated plugin copies are synchronized, and `tools/sync-core.py --check` passes.

- **AC-33 — Regression suite.** Existing statusline/ledger behavior unrelated to corrected accounting remains green:

  - width safety;
  - `NO_COLOR`;
  - session age;
  - theme behavior;
  - git segments;
  - arbitration segments;
  - task state;
  - subagent presentation: the same rows, labels and liveness as before for equivalent fixtures.

- **AC-34 — Full verification.** All of these pass against the exact candidate commit:

  - focused accounting tests;
  - full hook `unittest` discovery;
  - repository-generated-source checks;
  - relevant site/docs tests;
  - the benchmark comparison (AC-39);
  - all existing CI gates.

- **AC-35 — Identity classes.** Tests cover:

  - repeated missing IDs;
  - numeric, empty, boolean, array and object IDs;
  - an actual ID textually resembling another class's key;
  - duplicate unproven records;
  - `mid`-only records merging with a later and with an earlier `rid`+`mid` record.

  Unproven non-zero records never enter any total and make coverage partial. Zero-usage unproven records (`<synthetic>`) do not affect coverage.

- **AC-36 — Order independence.** For the principal multi-source fixture, every permutation of source scan order, and a shuffled record order within duplicate groups, yields identical accepted request state, totals, per-day buckets and coverage.

- **AC-37 — Cache refinement cannot double-count.** For one request, each of these sequences yields `total_write` = the maximum aggregate, and never more:

  - aggregate-only → complete 5m split;
  - aggregate-only → complete 1h split;
  - partial split → complete split;
  - complete split → less-complete replay;
  - a split summing above the aggregate;
  - an aggregate increase while the classification stays partial;
  - conflicting 5m/1h classifications.

- **AC-38 — Malformed-record coverage.** Every D-24 case is covered:

  - undecodable or non-object JSON on a usage-bearing line;
  - non-object usage;
  - non-finite, negative, boolean and fractional counters;
  - counters above the ceiling;
  - an oversized usage-bearing record.

  Each advances the scanner and makes coverage partial with the right reason.

  These leave coverage complete:

  - unknown non-usage record types;
  - every observed non-usage type in observation 8;
  - an undecodable or oversized line that is not usage-bearing, e.g. a large `user` tool result;
  - `attachment` task-notification records carrying a `usage` summary, which are never counted as usage;
  - escaped `\"usage\"` text inside content.

- **AC-39 — Performance contract.** The D-20 benchmark exists in a commit preceding implementation code, and its base report is recorded. Structural I/O tests show:

  - a no-change render (as defined in D-20) reads zero transcript content bytes, writes zero ledger files and deserializes zero evidence partitions, with 0/1/12/13/64 children;
  - a host-only change writes only the compact summary;
  - the heartbeat writes at most once per `LEDGER_HEARTBEAT`;
  - an incremental render stays within budget;
  - presentation decodes no JSONL.

  The benchmark runs one subprocess per render through the statusline entry point, with counters taken by an in-child audit wrapper. Its warm median and p95 are ≤ base × 1.05 on identical fixtures and the same machine, with the report retained in the PR. The candidate's structural counters are ≤ base, with two exceptions:

  - **Transcript bytes** may exceed base by the D-20 allowance of two bounded fingerprint windows per changed source per render.
  - **Incremental file counts** (opens, replacements) are bounded by formula and reported against base, not held to it. Incremental renders still gate strictly on bytes read, decoded and written, and on wall-clock. The formula:
    - each render writes at most 2 files (summary and hot evidence);
    - at most ⌈new identities / (`HOT_MAX`/2)⌉ renders evict, and an evicting render adds at most one rewrite per live partition;
    - opens exceed base by at most two per such partition rewrite, plus one partition read per membership-filter false positive (bounded at 2% of new identities).

- **AC-40 — History scaling.** At 1k, 10k and 100k accepted requests, a no-change render deserializes no evidence. A *k*-new-record incremental render deserializes at most *k* partitions, each no larger than the fixed maximum partition size. A test grows one partition past that maximum and asserts that it splits. Derived totals equal a from-scratch recomputation.

- **AC-41 — Non-blocking lock, no false zeros.** Hold the ledger lock in another process. A render returns within the try-lock bound plus render time, shows the last committed snapshot flagged stale with its coverage preserved, and never shows `$0`/zero tokens that the snapshot does not contain. With no snapshot, it shows unavailable rather than zero.

- **AC-42 — Unknown event time.** A request with no trustworthy timestamp counts in Session, never in Today, and Today coverage is partial (`unknown_event_time`).

- **AC-43 — Cross-midnight replay.** Two representations of one request fall on opposite sides of midnight, in parent and child and in both arrival orders. The request is attributed by minimum event time, deterministically, and the affected day scopes carry `conflicting_event_day`. No arrival order moves the spend.

- **AC-44 — Advisor iterations.** A fixture follows the observed 3-iteration shape: `message`, `advisor_message` on another model, `message`. It prices the top-level counters at the record's model and the advisor iteration at its own model, each exactly once across streaming snapshots, and advisor tokens appear in token totals. A turn with **two** advisor calls on the same model sums both within the representation before reconciling by maximum across representations. An unknown iteration type with non-zero counters makes coverage partial.

- **AC-45 — Price modifiers.** Coverage behaves as follows:

  - absent or `standard` `speed`/`service_tier` and absent, `not_available` or `global` `inference_geo` price at standard rates, with coverage complete;
  - `speed:"fast"` on Opus 5.5 prices at the registry fast rate;
  - `inference_geo:"us"` on a 4.6+ model applies 1.1×;
  - any other value makes coverage partial (`unpriced_modifier`).

- **AC-46 — Synthetic and alias models.** `<synthetic>` records with all-zero usage add nothing and leave coverage complete. `claude-opus-5[1m]` and dated snapshot IDs resolve through the explicit alias table. Non-alias unknown suffixes are unknown models.

- **AC-47 — Source lifecycle.** All four D-22 cases, plus a failed directory listing, preserve the accepted accounting and produce the specified coverage.

- **AC-48 — Discovery bound.** A session directory with more JSONL entries than the discovery bound does not trigger an unbounded walk. Known sources are retained and coverage is partial (`discovery_bound`). Within the bound, every child is accounted.

- **AC-49 — Oversized record progress.** A single JSONL line larger than the per-record ceiling, including one larger than a render's byte budget, is passed deterministically across renders, with no wedge and no unbounded read. A usage-bearing oversized line (both markers in its final 64 KiB) marks `oversized_record`. A non-usage oversized line leaves coverage unchanged. In both cases the following records are consumed exactly once.

- **AC-50 — Presentation from summaries.** The subagent panel renders from ledger presentation summaries and filesystem metadata alone. An instrumented test proves that `_subagentslib` opens no child JSONL, and that its rows, labels and liveness match the pre-change output for equivalent fixtures.

- **AC-51 — Characterized fixtures.** Sanitized structural fixtures exist for every observed shape and are exercised by the principal accounting tests. They carry type, replaced IDs, model, usage, timestamp, `isSidechain`, `agentId` and `fork-context-ref`, and no conversation content. The shapes are:

  - fork replay;
  - advisor iterations;
  - the stale top-level cache split;
  - streaming snapshots;
  - `<synthetic>`;
  - modifier fields;
  - `cost-state`.

- **AC-52 — Host fallback uses `max_seen`.** Out-of-order host observations (higher, then lower, same session) display `host≈` at the higher value and record the lower value as the latest/anomalous one.

## Required adversarial test matrix

The implementation is not complete if testing consists only of one happy-path arithmetic fixture. The suite must include combinations of:

- parent-only, child-only-after-parent, and mixed parent/child activity;
- 0, 1, 12, 13 and many delegated transcripts, and more than the discovery bound;
- large parent and large child transcripts;
- fork replays across parent/child and sibling/sibling;
- all permutations of source scan order;
- multiple records with the same request ID inside one source, and across sources;
- later duplicate records that are larger, equal, smaller, model-conflicting, and `mid`-only;
- all identity classes of D-5;
- malformed JSON, valid non-object JSON, and oversized lines;
- missing, string, negative, NaN-like, boolean, fractional and extremely large usage values;
- partial last lines;
- truncation, same-size replacement, larger replacement, and vanish/reappear;
- per-render budget boundaries: minus one, exact, plus one, and multiple chunks;
- model version changes during one session, aliases, and `<synthetic>`;
- advisor iterations and unknown iteration types;
- cache reads, both cache-write TTLs, aggregate-only, inconsistent, and stale-top-level-split metadata;
- known-priced, known-zero and unknown server-tool counters;
- speed/geo/tier modifiers;
- host cost valid, absent, malformed, increasing, decreasing, out-of-order, and disagreeing with reconstruction;
- midnight crossing in parent and child activity, cross-midnight replay, and unknown timestamps;
- background growth while the parent transcript is unchanged;
- lock contention (held lock), no-snapshot contention, and interrupted atomic replacement;
- legacy-ledger migration;
- 1k/10k/100k accepted-request history;
- narrow and wide statusline rendering.

The independent expected total in the principal accounting fixtures must be calculated from fixture facts, not by calling the production aggregation function under test.

## Implementation constraints

- Python remains stdlib-only.
- No statusline render invokes network I/O.
- No accounting fix may weaken the existing "never traceback" contract.
- No unbounded directory, file or record parser is introduced onto the render path.
- Performance bounds control how much work happens **now**, never how much history is eventually counted.
- Pricing data is deterministic, reviewable, and shipped with the repository.
- `_usagelib.py` stays a small set of pure functions plus immutable tables. It has no plugin classes and no deep abstraction.
- Do not duplicate accounting logic between canonical and generated host copies.
- Do not alter Pi's separate usage-ledger contract as collateral work.
- Do not use the host estimate to conceal missing transcript coverage.
- There is exactly one transcript JSONL parser. Tests may build fixtures, but they may not re-implement the parser to derive expected totals.

## Documentation correction

The public explanation should state, in substance:

> codeArbiter reconstructs the Claude statusline's `api≈` value from locally observable parent, delegated and advisor usage using a pinned API list-price table. It is an API-equivalent estimate, not your bill. `api≥` means some locally observed usage is unpriced, unidentifiable, or still being incrementally processed. If transcript reconstruction is unavailable, a Session row may show Claude Code's own estimated session cost as `host≈`. That value is kept separate because Claude Code does not define it as actual billing, and its coverage can differ from codeArbiter's reconstructed sources. Background agents' spend appears on the next statusline render.

The exact prose may vary, but those semantic boundaries may not.

## Completion evidence

The implementation PR must make it possible for a reviewer to answer the following from retained deterministic evidence:

1. Which sources contribute to Session and Today, and how are fork replays counted once?
2. How do we know an accounting bound deferred rather than dropped work?
3. How are child transcripts kept after they disappear from the recent-agent UI?
4. What happens for an unknown model, cache TTL, iteration type, modifier, or identity?
5. How is each current model's price selected?
6. How are separately metered observable tool charges and advisor iterations handled?
7. Why can a host-cost reset, regression or out-of-order observation no longer corrupt the primary number?
8. How does midnight attribution work, including for replays and unknown timestamps?
9. How does an existing user's ledger migrate?
10. Which remaining classes of real-world billing cannot be observed, and are therefore deliberately not claimed?
11. What do the base/head benchmark and structural I/O counters show?

A green arithmetic unit test without answers to those questions does not satisfy this spec.

## Open questions

None required before planning.

The implementation may choose the exact internal schema, evidence-partition layout, parser-helper module boundary and processing-budget constants. Those choices must satisfy the coverage, eventual-completeness, performance, migration, concurrency and user-visible honesty criteria above.
