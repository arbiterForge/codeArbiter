# Spec — Claude statusline accounting integrity

**Status:** APPROVED 2026-09-26 by the repository owner (explicit directive to plan against this spec and open the spec/plan PR)  
**Date:** 2026-09-26  
**Slug:** `claude-statusline-accounting-integrity`  
**Format:** Markdown authority for this externally authored review campaign; this PR creates no same-slug HTML shadow.

**Governs:** `core/pysrc/_ledgerlib.py`, `core/pysrc/statusline.py`, `core/pysrc/_subagentslib.py`, `core/pysrc/_segmentslib.py`, `core/pysrc/wire-statusline.py`, a shared usage-normalization/pricing helper if introduced under `core/pysrc/`, their synchronized plugin copies, statusline/ledger tests, and the public documentation that defines Claude statusline token/cost semantics.

**Origin:** Deep review of the Claude Code statusline accounting path on `main` at `c3d574a3d144578379526499b1fafe7109236923`, prompted by suspected latent spend-aggregation errors.

## Intent

Make the Claude Code statusline's token and dollar accounting trustworthy across long sessions, delegated execution, cache usage, transcript replay, calendar-day boundaries, malformed records, new model versions, and temporary host-data failures.

The statusline must answer two distinct questions without conflating them:

1. **What API-equivalent list-price cost can codeArbiter reconstruct from locally observable usage?**
2. **What cost estimate did Claude Code itself report for the parent session?**

The first is the primary codeArbiter accounting metric. The second is an independent reconciliation/fallback source, not authority over the first.

A displayed dollar value must never silently imply actual billing truth, all-source completeness, or exact pricing when codeArbiter does not possess enough evidence to support that claim.

## Problem

The current implementation mixes incompatible accounting sources and contains several independent correctness failures.

`_ledgerlib.py` reconstructs parent-session token usage from the transcript but normally replaces its calculated cost with `cost.total_cost_usd` from Claude Code. The code and comments currently describe that host value as authoritative and as including delegated execution. That assumption is not part of the current Claude Code status-line contract and is contradicted by known delegated-session behavior.

At the same time:

- delegated/subagent transcripts are discovered for presentation but are not first-class sources in the cost ledger;
- the 20,000-new-line processing limit can permanently skip every unread transcript line after the limit because the stored offset advances to EOF rather than to the last consumed line;
- the Today token bucket is event-timestamp based while Today cost sums whole-session `host_cost`, incorrectly moving pre-midnight spend into the current day;
- an absent or malformed host cost is coerced to zero and can replace previously valid host state;
- a lower host cost for the same session is accepted even though cumulative same-session cost should not normally regress;
- unknown models silently receive Sonnet pricing;
- family-level pricing cannot distinguish model generations whose prices differ;
- cache-write aggregate and TTL-specific fields are not reconciled robustly;
- malformed request identities can prevent forward progress;
- duplicate request records use last-write-wins even if a later replay contains less complete usage;
- observable separately metered server-tool activity is discarded;
- presentation-oriented subagent bounds would be unsuitable as accounting bounds;
- no periodic refresh is installed, so a parent waiting on background work can display stale accounting;
- documentation alternates between describing the dollar value as API-equivalent estimation and as an authoritative/real session cost.

This work corrects the accounting model rather than adding patches around individual totals.

## User-facing accounting contract

### Session tokens

The Session token counters represent all successfully reconstructed usage belonging to the current Claude session, including locally discoverable delegated child transcripts.

The existing display definition is retained:

- input = uncached input + cache-write tokens;
- cache-read tokens remain excluded from the visible input counter so repeatedly served context does not dominate the number;
- output = output tokens;
- cache reads remain part of cost accounting.

### Today tokens

Today uses the same token definition as Session but includes only usage events whose own timestamps fall on the current local calendar day.

A session crossing midnight is split by event timestamp. Activity before midnight must never reappear in the next day's totals merely because the session remains active.

### Primary dollar metric

The primary dollar value is **codeArbiter reconstructed API-equivalent cost at pinned public list rates**, not an invoice and not actual account spend.

The normal complete label is:

`api≈$N`

It means every locally discovered usage item contributing to the scope has been processed and every billable component represented by that item has a known pricing rule.

When codeArbiter can calculate only a known subset because some observable usage cannot be priced or because the incremental scanner is still catching up, the label is:

`api≥$N`

The amount is the known non-negative portion only. Unknown usage is never silently priced as another model or discarded while presenting the total as complete.

When usage is known to exist but no defensible reconstructed dollar value exists:

`api≈?`

### Claude-reported fallback

`cost.total_cost_usd` is retained separately as Claude Code's reported **estimated session cost**.

It is not added to reconstructed child cost, used as `max(host, reconstructed)`, or otherwise algebraically combined with reconstructed API-equivalent cost.

If reconstructed Session cost is unavailable but a valid Claude-reported value exists, Session may display it explicitly as:

`host≈$N`

Today must not manufacture a day-specific value from a whole-session host value.

### Actual billing

No codeArbiter statusline value is called a bill, real billed cost, authoritative billing cost, or actual account spend.

Discounts, credits, subscription treatment, custom `modelPricing`, provider-specific rates, data-residency modifiers, fast-mode premiums, and other modifiers are incorporated only when the underlying usage record exposes enough information and the pricing registry explicitly models them. Otherwise they remain outside the reconstructed API-equivalent claim.

## Scope

This effort includes:

- correct incremental processing of the parent Claude transcript;
- durable accounting of all locally discoverable delegated transcripts belonging to that parent session;
- one shared normalization/deduplication contract for transcript usage;
- exact/version-aware model pricing;
- cache-write and cache-read accounting;
- separately metered server-tool charges when the transcript both exposes them and codeArbiter has an explicit pricing rule;
- event-based Session/Today aggregation;
- independent preservation and reconciliation of Claude's host-reported estimate;
- explicit completeness/partial-coverage state;
- ledger migration;
- periodic refresh for background activity;
- docs and deterministic regression coverage.

## Out of scope

This spec does not:

- query Anthropic billing, Console, organization usage, or any network API at statusline render time;
- claim to recover API activity Claude Code does not expose in any locally readable source;
- infer hidden side-query/classifier cost from unrelated telemetry;
- fabricate provider, discount, data-residency, batch, fast-mode, or other price modifiers;
- merge reconstructed and host-reported dollars to make disagreement disappear;
- redesign the overall statusline;
- change Pi's separate usage ledger or Pi footer accounting semantics;
- make the bounded recent-subagent panel an accounting source of truth;
- introduce third-party Python dependencies.

## Definitions

**Observable usage event:** a locally readable transcript record carrying billable usage counters or separately metered tool counters.

**Source:** one parent or delegated transcript belonging to the current Claude session.

**Reconstructed API-equivalent:** the sum of priceable observable usage using codeArbiter's pinned pricing registry.

**Host-reported estimate:** the current `cost.total_cost_usd` value received in Claude Code's status-line payload.

**Complete:** every discovered source is scanned through its current durable end and every billable field observed is understood and priceable.

**Catching up:** work remains only because a bounded per-render processing budget deferred some records or sources.

**Partial:** all currently processable data has been consumed, but at least one observed billable component cannot be priced safely.

**Unavailable:** no defensible reconstructed monetary total can currently be produced.

## Load-bearing design decisions

### D-1 — Reconstructed usage owns `api≈`

The primary monetary metric is reconstructed from usage records. `cost.total_cost_usd` does not override it.

This restores one stable semantic meaning to `api≈`: what codeArbiter can reconstruct at its pinned list-price model from observable usage.

### D-2 — Claude's cost is reconciliation evidence, not arithmetic input

Persist the host-reported estimate independently.

Track at minimum:

- latest valid value;
- maximum value observed for the same session;
- whether the latest value regressed;
- whether it disappeared after previously being present;
- comparison state when reconstructed cost is complete.

A missing, null, malformed, negative, NaN, or infinite host value does not overwrite a previously valid value with zero.

A same-session decrease is recorded as anomalous and does not redefine reconstructed spend.

A host/reconstructed difference is diagnostic evidence. It does not cause one number to replace or be added to the other.

### D-3 — Delegated transcripts are first-class accounting sources

Parent and delegated transcripts are accounted through the same usage-normalization rules.

The accounting scanner must discover the delegated transcript directory associated with the parent session and persist independent progress for every child transcript.

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

No limit may advance an offset over unread data.

Reading the entire remaining file into memory before applying a record limit does not satisfy the bound.

### D-5 — Source identity namespaces request identity

Request IDs are not assumed globally unique across parent and delegated transcripts.

The deduplication identity includes the source.

A valid scalar `requestId` is preferred, then a valid scalar message ID. Missing or structurally invalid IDs receive a deterministic source-local identity derived from the consumed record position.

Lists, dictionaries, and other unhashable IDs never raise and never wedge the source at the same offset forever.

### D-6 — Duplicate usage converges monotonically

Repeated transcript representations of the same API request are reconciled rather than blindly summed or last-write-wins overwritten.

For cumulative non-negative usage counters, a later partial/replayed record must not reduce a previously observed value.

The normalizer therefore preserves the greatest defensible cumulative value per component unless host evidence establishes a different schema.

Conflicting model identities for one deduplicated request are not silently resolved by whichever line appeared last. They make that request's pricing identity ambiguous until the implementation can prove which identity is billable.

### D-7 — One usage normalizer owns parent and child semantics

The repository must have one pure normalization contract for:

- token coercion and validation;
- model identity;
- cache fields;
- server-tool counters;
- timestamps;
- request identity;
- duplicate reconciliation.

`_ledgerlib` and `_subagentslib` must not maintain divergent independent definitions of a usage record.

The implementation may extract a new stdlib-only helper module or make the existing ledger module the owner, but normalization rules exist in one place.

Presentation remains independently bounded.

### D-8 — Pricing is version-aware; unknown does not mean Sonnet

Remove the unknown-model-to-Sonnet pricing fallback.

Pricing lookup uses the most specific recognized model/version identity first. Family aliases are allowed only when the aliased models are explicitly known to share the same price tuple.

The pricing registry records enough metadata to audit its values, including a source/update date in code comments or structured metadata.

At implementation time it must cover at minimum the currently active Claude model IDs used by Claude Code plus still-supported historical model IDs reasonably present in resumable transcripts.

Tests explicitly cover current Opus, Sonnet, Fable, and Haiku versions and at least one historical model whose price differs from the current generation.

An unknown future/custom model contributes tokens but marks reconstructed monetary coverage partial rather than borrowing another model's rate.

### D-9 — Cache accounting reconciles aggregate and TTL-specific fields

The normalizer retains:

- uncached input;
- output;
- cache reads;
- 5-minute cache writes;
- 1-hour cache writes;
- cache-write amount whose TTL cannot be determined, when applicable.

When both `cache_creation_input_tokens` and the nested TTL-specific split are present, they are reconciled and checked for consistency.

A missing or partial TTL split does not silently discard the aggregate remainder.

An unknown cache-write TTL is not assigned a cheaper or more expensive TTL merely to obtain a number. It makes the unknown portion unpriceable unless the host contract for that exact record form proves the TTL.

### D-10 — Observable separately metered tools participate in cost

When a usage record exposes a separately metered server-tool counter and the pricing registry has an explicit rule for it, that charge contributes to reconstructed API-equivalent cost.

Unknown server-tool counters are retained as coverage evidence and make the result partial rather than being silently ignored.

The pricing engine remains extensible by charge class; it must not assume forever that all API-equivalent spend is `tokens × model price`.

### D-11 — Calendar-day cost is event-derived

Every reconstructed monetary component carries or inherits the timestamp of its usage event.

Session cost is the sum across the current session's accepted events.

Today cost is the sum only across events assigned to the current local calendar day.

A session crossing midnight, including a delegated child crossing midnight, is split consistently for both tokens and reconstructed cost.

Whole-session host cost is never assigned wholesale to Today.

### D-12 — Coverage is durable state, not a rendering guess

The ledger returns enough structured information for rendering to distinguish at least:

- complete;
- catching up;
- partial;
- unavailable.

The renderer does not infer completeness merely because it received a numeric float.

A newly discovered unscanned child source immediately prevents a complete claim until consumed.

### D-13 — Background activity gets a periodic refresh

The owned Claude status-line configuration sets `refreshInterval: 2`.

Event-driven refresh remains active. The periodic interval exists specifically so background/delegated activity can advance the local ledger while the parent conversation is idle.

Install, refresh/self-heal, ownership recognition, backup, and uninstall tests must preserve this field correctly without destroying a user's prior status-line configuration.

The renderer itself performs no network access.

### D-14 — Incremental accounting stays bounded and eventually complete

Accounting may use per-render source/record/byte budgets, but scheduling must be starvation-free.

If more work is pending than one render can process, repeated renders with unchanged files eventually consume every source through EOF.

A continuously active large parent transcript must not permanently starve older child transcripts, and many child transcripts must not permanently starve the parent.

While backlog exists, the monetary result is visibly not complete.

### D-15 — Transcript replacement/truncation self-heals without cross-source loss

If one source truncates, rotates, or changes identity, only that source's derived records are rebuilt.

A child transcript reset cannot erase parent or sibling accounting.

The implementation must not retain records beyond the durable end of a source after detecting a genuine replacement.

### D-16 — Existing ledger state migrates deliberately

Current ledger files are expected in the field.

A new schema must:

- recognize the current parent-only `reqs`/`tx_off` representation;
- preserve session-start metadata where valid;
- never reinterpret old `host_cost` as reconstructed cost;
- rebuild transcript-derived accounting when required rather than pretending incompatible cached values are exact;
- use atomic replacement and the existing lock discipline;
- fail soft if old state is malformed.

Migration must not require the user to delete `~/.codearbiter/ledger.json`.

### D-17 — Concurrency and atomicity remain hard requirements

The existing independent session shards, lock, atomic replacement, and same-session race protections remain.

Adding multiple transcript sources must not reopen lost-update behavior.

A concurrent session-start metadata write cannot erase accounting progress, and simultaneous renders cannot regress a source offset or accepted usage.

### D-18 — Generated-source discipline remains unchanged

`core/pysrc/` remains canonical.

Do not independently patch:

- `plugins/ca/hooks/`
- `plugins/ca-pi/hooks/`
- `plugins/ca-codex/hooks/`

Canonical changes are synchronized through the existing repository generation path, and sync checks must remain byte-clean.

### D-19 — Documentation has one cost vocabulary

Public docs, command docs, source comments, and screenshots/fixtures must consistently distinguish:

- reconstructed `api≈`;
- partial/lower-bound `api≥`;
- Claude-reported `host≈`;
- actual billing, which codeArbiter does not claim.

Remove statements that `cost.total_cost_usd` is authoritative, "real", guaranteed to include subagents, or exactly equal to the user's bill.

## Logical ledger model

The exact serialized field names are implementation-owned, but the durable model must be equivalent to:

```text
session
  identity
  first/last timestamps
  resolved session start

  sources
    parent-source
      kind
      stable identity
      transcript locator
      consumed byte position
      source generation/fingerprint
      normalized requests

    delegated-source-N
      same fields

  reconstructed
    session totals
    per-local-day totals
    coverage state
    unpriceable reasons

  host estimate
    latest valid
    max seen
    last seen
    regression/missing state
    optional reconciliation delta

  burn samples
```

Request records must retain enough information to recompute pricing when the pricing registry changes without rereading already-pruned source text during the same live-ledger lifetime.

At minimum that means preserving normalized model identity and usage components rather than persisting only a precomputed dollar subtotal.

## Reconciliation behavior

When both reconstructed and host-reported values exist, codeArbiter may calculate a diagnostic difference.

That comparison is informational because legitimate divergence can result from:

- delegated sessions not represented in the parent host estimate;
- host `modelPricing`;
- custom/provider pricing;
- unobservable internal calls;
- list-price changes;
- modifiers not represented in transcripts;
- host defects;
- codeArbiter pricing defects.

No fixed discrepancy direction proves which source is correct.

The statusline is not required to add another reconciliation segment. The diagnostic state must, however, be represented in testable ledger/accounting output so future `/doctor` or troubleshooting work can inspect it without reverse-engineering raw files.

## Acceptance criteria

**AC-01 — Primary semantic contract.** Session and Today dollar values are reconstructed API-equivalent values when reconstruction is available; `cost.total_cost_usd` does not override or get added to them. Complete values render `api≈`, partial/catching-up values render `api≥`, and an unpriceable known-usage state does not render a precise dollar total.

**AC-02 — Host fallback is explicit.** When Session reconstruction is unavailable and a valid Claude-reported estimate exists, the renderer may display `host≈$N`; Today never derives a fabricated daily value from that whole-session figure.

**AC-03 — Parent plus delegated accounting.** A fixture containing one parent and multiple delegated transcripts produces Session tokens and reconstructed cost equal to the independently calculated sum of all accepted usage records.

**AC-04 — Presentation limits do not limit accounting.** A fixture with more than `MAX_SUB_FILES` delegated transcripts, including completed children older than `SHOW_WINDOW`, still includes every child in Session/Today accounting while the visible subagent panel remains bounded exactly as intended.

**AC-05 — 20k-boundary loss is impossible.** With more than `TX_MAX_NEW_LINES` unread complete records, the first update stops at the last processed record rather than EOF and reports catching-up coverage; subsequent updates consume the remainder exactly once and converge on the full independent total.

**AC-06 — Processing bounds are real.** The incremental parser does not read the unbounded remainder of a transcript into memory before applying its processing ceiling.

**AC-07 — Partial trailing line.** A writer-flushed partial JSONL line does not advance the durable offset over the partial bytes; once completed, the record is consumed exactly once.

**AC-08 — Request identities are source-scoped.** Identical request IDs appearing in parent and child transcripts are both counted once; they do not overwrite one another.

**AC-09 — Malformed identity cannot wedge accounting.** Array/object/missing request IDs and message IDs neither raise nor prevent the durable offset from advancing past a successfully handled record.

**AC-10 — Duplicate usage is monotonic.** A duplicate request whose later replay contains lower/partial counters cannot reduce previously reconstructed token or cost totals. A later genuinely more complete record increases the corresponding components without double-counting.

**AC-11 — Model conflict is honest.** Conflicting model identities for one deduplicated request do not silently price the request using last-write-wins; the affected monetary coverage becomes partial unless an explicit normalization rule proves equivalence.

**AC-12 — Exact model pricing.** Pricing tests cover the implementation-time current Opus, Sonnet, Fable, and Haiku model IDs and verify their exact input/output/cache prices against the pinned registry.

**AC-13 — Historical pricing.** At least one historical resumable model whose rate differs from its current family successor is priced by its historical exact rule rather than the current family rule.

**AC-14 — Unknown model behavior.** An unknown/custom/future model contributes its observed tokens but never receives Sonnet or another arbitrary price; reconstructed monetary coverage is partial.

**AC-15 — Cache accounting.** Fixtures cover no-cache, cache-read, 5-minute write, 1-hour write, aggregate-only write, matching aggregate+split, and incomplete/inconsistent aggregate+split cases without losing tokens or silently inventing TTL.

**AC-16 — Server-tool charges.** A fixture containing a recognized separately metered server-tool usage field contributes the configured charge exactly once. An unknown non-zero separately metered field makes coverage partial rather than disappearing.

**AC-17 — Cross-midnight parent.** Parent events on opposite sides of local midnight contribute to one Session total but separate calendar-day token and cost buckets.

**AC-18 — Cross-midnight delegated activity.** The same split is proven for child/delegated transcript usage; a child started yesterday but completed today does not move yesterday's spend into Today.

**AC-19 — Host disappearance.** A valid host estimate followed by a payload where the field is absent/null/malformed does not replace persisted valid host state with zero and does not alter reconstructed cost.

**AC-20 — Host regression.** A same-session host value that decreases is retained as latest observation only with an anomaly state; it cannot regress reconstructed spend or erase the previous maximum. A new session ID remains free to begin at zero.

**AC-21 — Host disagreement is non-destructive.** Fixtures where host cost is above and below reconstructed cost preserve both values independently and produce deterministic reconciliation state without `max()`, addition, or replacement.

**AC-22 — Source catch-up is starvation-free.** With a large parent plus enough children to exceed one update's work budget, repeated updates eventually reach every unchanged source's EOF and transition coverage from catching-up to complete.

**AC-23 — Source truncation is isolated.** Replacing/truncating one child causes only that source to be rebuilt; parent and sibling totals survive unchanged.

**AC-24 — Burn semantics share normalized usage.** Burn samples are derived from the same accepted/deduplicated usage events rather than an independent parser. If delegated activity is included in the Session burn metric, it is chronological and deduplicated; if the product deliberately retains parent-only burn, that scope is explicit in code and docs and tested.

**AC-25 — Ledger migration.** A current production-shaped ledger migrates without manual deletion, preserves valid session-start metadata, does not mistake historical `host_cost` for reconstructed cost, and converges to correct totals after transcript replay.

**AC-26 — Corrupt migration fails soft.** Malformed legacy ledger/session shards cannot break the statusline or contaminate healthy session/source records.

**AC-27 — Concurrency.** Distinct-session and same-session concurrent updates preserve every accepted source, source offset, request, reconstructed total, and session-start value under the existing serialization/atomic-write contract.

**AC-28 — Background refresh.** `owned_statusline()` writes `refreshInterval: 2`; install/refresh preserves ownership semantics, uninstall restores the exact prior user statusline, and background transcript growth becomes visible without requiring another parent assistant message.

**AC-29 — No render-time network.** The complete feature works offline from local status payloads, transcripts, pricing data shipped with codeArbiter, and the local ledger. No pricing or billing request is performed by the renderer.

**AC-30 — Fail-soft rendering.** Missing transcript path, vanished child directory, concurrently removed file, permission error, malformed JSON, invalid usage type, unknown model, and ledger lock contention each degrade only the affected accounting state and never emit a traceback or blank the rest of the statusline.

**AC-31 — Public vocabulary.** Command docs, statusline guide, source comments, fixture comments, and any screenshots describe reconstructed `api≈`, partial `api≥`, and host fallback accurately and contain no remaining claim that `cost.total_cost_usd` is authoritative billing truth or guaranteed delegated-session aggregation.

**AC-32 — Canonical-source parity.** All Python implementation changes originate in `core/pysrc/`; generated plugin copies are synchronized and `tools/sync-core.py --check` passes.

**AC-33 — Regression suite.** Existing statusline/ledger behavior unrelated to corrected accounting remains green, including width safety, `NO_COLOR`, session age, theme behavior, git segments, arbitration segments, task state, and subagent presentation.

**AC-34 — Full verification.** Focused accounting tests, full hook `unittest` discovery, repository-generated-source checks, relevant site/docs tests, and all existing CI gates pass against the exact candidate commit.

## Required adversarial test matrix

The implementation is not complete if testing consists only of one happy-path arithmetic fixture.

The suite must include combinations of:

- parent-only, child-only-after-parent, and mixed parent/child activity;
- 0, 1, 12, 13, and many delegated transcripts;
- large parent and large child transcripts;
- multiple records with the same request ID inside one source;
- the same request ID across different sources;
- later duplicate records that are larger, equal, smaller, and model-conflicting;
- malformed JSON and valid non-object JSON;
- missing, string, negative, NaN-like, and extremely large usage values;
- partial last lines;
- truncation and replacement;
- 20k-limit boundary minus one, exact, plus one, and multiple chunks;
- model version changes during one session;
- cache reads and both cache-write TTLs;
- aggregate-only and inconsistent cache-write metadata;
- known and unknown server-tool counters;
- host cost valid, absent, malformed, increasing, decreasing, and disagreeing with reconstruction;
- midnight crossing in both parent and child activity;
- background growth while the parent transcript is unchanged;
- lock contention and interrupted atomic replacement;
- legacy-ledger migration;
- narrow and wide statusline rendering.

The independent expected total in the principal accounting fixtures must be calculated from fixture facts, not by calling the production aggregation function under test.

## Implementation constraints

- Python remains stdlib-only.
- No statusline render invokes network I/O.
- No accounting fix may weaken the existing "never traceback" contract.
- No unbounded directory/file parser is introduced onto the render path.
- Performance bounds control how much work happens **now**, never how much history is eventually counted.
- Pricing data is deterministic, reviewable, and shipped with the repository.
- Do not duplicate accounting logic between canonical and generated host copies.
- Do not alter Pi's separate usage-ledger contract as collateral work.
- Do not use the host estimate to conceal missing transcript coverage.
- Do not add a third independent transcript parser for tests or UI.

## Documentation correction

The public explanation should state, in substance:

> codeArbiter reconstructs the Claude statusline's `api≈` value from locally observable parent and delegated usage using a pinned API list-price table. It is an API-equivalent estimate, not your bill. `api≥` means some locally observed usage remains unpriced or is still being incrementally processed. If transcript reconstruction is unavailable, a Session row may show Claude Code's own estimated session cost as `host≈`; that value is kept separate because Claude Code does not define it as actual billing and its coverage can differ from codeArbiter's reconstructed sources.

The exact prose may vary, but those semantic boundaries may not.

## Completion evidence

The implementation PR must make it possible for a reviewer to answer, from retained deterministic evidence:

1. Which sources contribute to Session and Today?
2. How do we know an accounting bound deferred rather than dropped work?
3. How are child transcripts kept after they disappear from the recent-agent UI?
4. What happens for an unknown model or cache TTL?
5. How is each current model's price selected?
6. How are separately metered observable tool charges handled?
7. Why can a host-cost reset or regression no longer corrupt the primary number?
8. How does midnight attribution work?
9. How does an existing user's ledger migrate?
10. Which remaining classes of real-world billing cannot be observed and are therefore deliberately not claimed?

A green arithmetic unit test without answers to those questions does not satisfy this spec.

## Open questions

None required before planning.

The implementation may choose the exact internal schema, parser-helper module boundary, and processing-budget constants provided those choices satisfy the source coverage, eventual-completeness, migration, concurrency, and user-visible honesty criteria above.
