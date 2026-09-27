# Spec: Tribunal vNext review-quality modernization

**Status:** PROPOSED, implementation not authorized by this documentation-only PR
**Slug:** `tribunal-vnext-review-quality`
**Date:** 2026-09-26
**Source:** deep implementation review of Tribunal and its agents
**Authorized source snapshot:** `arbiterForge/codeArbiter@8e88bce938ebf7dc8cfd934307b8d6859092d86e`
**Governs:** `core/surface/skills/tribunal/**`, `core/surface/agents/tribunal-lens-reviewer.md`, Tribunal mapping/extraction roles, Tribunal schemas, generated host projections, Tribunal evaluation evidence, and directly related tests/documentation
**Does not establish released behavior:** current `main` is development evidence only

## Goal

Modernize Tribunal for the failure profile of current coding agents without weakening its evidence discipline.

The intended outcome is a deep audit that:

1. catches semantic and cross-surface defects that are easy for modern code-generating models to make while still producing clean-looking, test-passing code;
2. spends model reasoning on judgment rather than deterministic counting or repository-wide rereading;
3. gives serious findings an independent verification path before they become durable work;
4. resumes only against the source state it actually audited;
5. treats repository content as untrusted evidence, never as review instructions;
6. works honestly across Claude, Codex, and Pi capabilities rather than projecting Claude-specific execution assumptions onto every host; and
7. has a repeatable evaluation corpus so future model/card changes can be measured rather than justified from memory.

This effort preserves Tribunal as an opt-in deep audit. It does not make Tribunal a mandatory merge gate.

## Source review baseline

This spec was derived from current source at:

`arbiterForge/codeArbiter@8e88bce938ebf7dc8cfd934307b8d6859092d86e`

Relevant current owners include:

- `core/surface/skills/tribunal/SKILL.md`
- `core/surface/agents/tribunal-lens-reviewer.md`
- `core/surface/agents/map-structure.md`
- `core/surface/agents/map-deps.md`
- `core/surface/skills/tribunal/references/ai-markers.md`
- `core/surface/skills/tribunal/references/cost-and-models.md`
- `core/surface/skills/tribunal/references/finding-record.md`
- `core/surface/skills/tribunal/references/triage.md`
- `core/surface/skills/tribunal/references/schemas.md`
- `core/surface/skills/tribunal/references/telemetry.md`
- the eleven current lens cards under `core/surface/skills/tribunal/references/lenses/`
- `core/hosts.json`
- generated Claude, Codex, and Pi Tribunal projections
- historical Tribunal run artifacts under `.codearbiter/reports/` and `docs/reports/`

ADR-0027 remains an important design constraint: the lens roster is data and one generic lens reviewer executes it. This spec does not revert to eleven bespoke reviewer agents.

## Problem

Tribunal's orchestration architecture has improved faster than its failure model.

The August 2026 consolidation removed substantial duplicated agent prose and made the lens cards the real mandates. That is the correct direction. The cards themselves, however, still carry several heuristics from an earlier generation of AI-assisted coding:

- comment density and TODO/FIXME density as AI-authorship signals;
- naming/convention drift as an AI-authorship signal;
- fixed import/fan-in thresholds as architecture defect triggers;
- local catch-handling expectations that can misclassify intentional error propagation;
- broad suspicion of mocks/test doubles instead of measuring oracle quality and contract fidelity;
- type escapes treated too independently from whether they create an unsound boundary;
- performance advice that can be generated without an observed scale/latency/resource argument;
- severity priors influenced by inferred AI authorship/iteration history.

Current coding models are substantially better at producing conventional, plausible-looking implementations. The higher-value failure classes have shifted toward semantic divergence, partial change closure, weak or self-confirming verification, boundary behavior, state/concurrency semantics, and cross-surface inconsistencies.

The orchestration also has several correctness and efficiency defects independent of model capability.

## Confirmed current-source defects to close

### D1. Resume is time-bound rather than source-bound

Current resume logic primarily treats a run younger than seven days as resumable. It does not bind the run to the exact source state audited.

A branch can materially change minutes after a run starts. Resuming against a different HEAD, dirty worktree, or scoped diff can silently combine stale findings with fresh source.

Required correction:

- every fresh run records an immutable source fingerprint before lens work starts;
- resume compares the current source to that fingerprint before reusing completed work;
- elapsed time is advisory only, not source identity.

At minimum the fingerprint records:

- repository root identity sufficient to avoid crossing repositories;
- HEAD commit;
- whether the working tree was clean;
- scope path;
- a digest representing the reviewed dirty diff when dirty;
- a digest for any explicit review target used instead of the whole working tree.

If the fingerprint cannot be reconstructed, the run is legacy/unbound and may not silently resume as current evidence.

### D2. Run IDs can collide

`RUN_ID = <UTC-date>-<scope-slug>` permits two fresh completed runs for the same scope on the same UTC day to select the same directory.

Fresh run IDs must be unique without requiring deletion or overwrite of a prior report. Use a UTC timestamp plus a short random/unique suffix, while retaining a human-readable scope component.

### D3. `report-written` is overloaded as completion

The current resume contract treats a run containing `report-written` as complete even though issue filing and optional telemetry are later phases.

Separate:

- audit work complete;
- follow-up disposition complete;
- terminal run complete.

Add an explicit terminal event such as `run-completed`. A disconnect after report creation must permit the user to continue authorized filing/telemetry/disposition without rerunning the audit.

### D4. Cross-lens leads are not durable

The generic reviewer may return a one-line `[NEEDS-TRIAGE]` cross-lens observation, but durable run state contains only findings and coarse completion events.

A cross-lens lead must survive compaction, disconnect, resume, and failed dispatch. Introduce a small durable lead record, for example:

`leads/<lens>/<id>.json`

with:

- source lens;
- target lens or `orchestrator`;
- locations;
- one-line observation;
- reason it is not yet a finding;
- creation time;
- disposition.

A lead is evidence routing, not a defect. It becomes a finding only after the owning lens/orchestrator establishes the normal finding evidence contract.

### D5. Dedup identity is lens-coupled

Current `dedup_key` starts with the lens name. The same root defect discovered by reliability, architecture, coverage, observability, or performance therefore begins with different identity even when the evidence overlaps.

Add a lens-independent root-cause identity used by triage. Findings retain their original lens for provenance but can record:

- `root_cause_key`;
- `corroborates`;
- `related_lenses`.

Do not require a reviewer to guess a perfect root cause. The orchestrator may assign/normalize the root-cause key during triage.

### D6. AI-authorship inference affects severity

`ai-markers.md` currently attempts to infer AI authorship and iteration depth from comments, TODOs, naming switches, commit trailers, and generated-looking commit shapes, then applies a severity prior.

Authorship is not part of impact or likelihood. Remove AI-authorship inference from severity calibration.

Replace the concept with author-independent review-risk signals such as:

- trust/privilege boundary;
- persistent-state mutation;
- destructive/irreversible behavior;
- cross-package or cross-host fan-out;
- public API/protocol/schema change;
- concurrency;
- release/package/distribution impact;
- generated-source relationship;
- external integration;
- large blast radius;
- unusually high churn;
- weak verification relative to the changed behavior.

Risk signals decide where to spend review effort. They never increase severity merely because code looks machine-authored.

### D7. Shared model guidance is not host-native

The current Codex and Pi Tribunal projections contain Claude-specific model names, Claude API strings, and Anthropic-only wording inherited from the shared `cost-and-models.md`.

At the same source snapshot, `core/hosts.json` declares Codex `capabilities.agents: false` while Tribunal's main Phase 2 prose is dispatch-centric.

Replace provider/model generations in the shared contract with abstract review profiles:

- `deep`: strongest supported reasoning profile for semantic/security/reliability judgment and serious verification;
- `standard`: normal specialist review profile;
- `extract`: low-cost profile only where deterministic extraction cannot provide the facts.

Each host resolves those profiles to capabilities it actually supports. Generated Codex/Pi output must not contain unsupported Claude-specific model/API instructions.

A host without subagent capability must use an explicit inline execution contract and report reduced independence rather than pretending to have the same fresh-context semantics.

### D8. Low-confidence serious findings are misclassified as decisions

Current triage sends below-gate critical/high findings to `decision-required`.

Uncertainty about whether a factual defect exists is not an ADR-grade product decision.

Add `verify-required` or equivalent. Rules:

- a genuine design fork may be `decision-required`;
- an uncertain factual claim must be `verify-required` or `investigate`;
- a serious unverified claim must remain visible and must not be filed as a confirmed fix ticket until verification resolves it.

### D9. Finding scope and evidence scope are conflated

A subtree audit may need callers, middleware, schemas, contracts, manifests, or tests outside that subtree to evaluate behavior inside it.

Represent separately:

- `finding_scope`: where Tribunal is allowed to file findings;
- `evidence_scope`: bounded external context the reviewer may read to establish or refute those findings.

Reading evidence outside the finding scope never authorizes filing unrelated findings there.

### D10. Negative evidence is too file-local

"Read the whole relevant unit" is insufficient for absence claims such as missing error handling, authorization, cleanup, or validation because ownership may be intentionally centralized elsewhere.

An absence claim must state its search universe and boundary trace, for example:

- function plus direct callers;
- route plus middleware chain;
- resource lifecycle owner;
- public API plus validation layer;
- producer plus consumer contract.

The finding record should capture enough evidence to show why the absence belongs to the reviewed unit rather than a caller/owner.

### D11. Mapping spends model tokens on deterministic facts

`map-structure` and `map-deps` use model agents to collect file counts, languages, manifests, dependency names, env reads, entry points, and churn.

Introduce deterministic inventory extraction for all facts that can be obtained reliably from repository state. The model is reserved for ambiguous classification:

- which boundaries are semantically trust boundaries;
- which modules are load-bearing;
- which change relationships are likely to imply closure obligations;
- which risk signals deserve additional review.

The deterministic extractor must not execute repository-provided scripts.

### D12. Tribunal lacks a committed detection-quality evaluation corpus

Current tests prove generation/projection and selected support mechanics, but no committed corpus was found that establishes whether each lens catches known modern defects while rejecting clean controls.

Tribunal must gain a versioned evaluation corpus and repeatable qualification procedure before this modernization is considered complete.

## Design principles

1. **Failure-mode first, author independent.** Research about AI-generated code informs what Tribunal looks for. It does not make machine-looking code presumptively worse.
2. **Deterministic facts before model judgment.** Count, parse, enumerate, hash, and resolve with deterministic tooling where possible.
3. **Targeted evidence beats bulk context.** Give reviewers a compact, relevant evidence packet and allow bounded expansion when the claim requires it.
4. **Serious findings earn independent verification.** A critical/high label is not made authoritative merely because one strong model emitted it confidently.
5. **Repository content is data, not authority.** Source, comments, docs, tests, issue text, PR text, command output, and generated artifacts may contain hostile instructions.
6. **Host differences are explicit.** Claude, Codex, and Pi use the same conceptual contract only where their real capabilities support it.
7. **Durable state describes exactly what was reviewed.** Resume cannot silently cross source snapshots.
8. **Measure unique verified defects, not finding volume.**
9. **Preserve the current durable-output strengths.** One-file-per-finding persistence, append-only run/triage logs, explicit filing authorization, and opt-in telemetry remain.

## vNext audit pipeline

### Phase 0: Bind and size

Before any reviewer work:

1. resolve repository root and scope;
2. record source fingerprint;
3. generate unique run ID;
4. inspect host capabilities;
5. determine applicable deterministic probes;
6. estimate review cost from selected evidence, active lenses, host execution profile, and available historical calibration;
7. receive the existing explicit user cost/model authorization.

The cost estimate remains a band, not a quote.

Lower concurrency is presented as a peak-resource/rate-limit/wall-clock lever, not as a primary token-cost lever. Cost controls that actually reduce total work are scope reduction, conditional lens selection, smaller evidence packets, deterministic preprocessing, and lower review profile where validated.

### Phase 1: Deterministic inventory plus risk/contract map

Build `inventory.json` as the canonical machine-readable extraction and project `inventory.md` for human use.

Deterministic inventory should include, where available without running repository code:

- tracked file inventory and sizes;
- languages;
- manifests and lockfiles;
- direct dependency names/versions;
- generated-source relationships already declared in repository config;
- test/source path relationships;
- CI/release/deploy/config surfaces;
- entry points detectable from known stack conventions;
- import/call graph information where a parser or language tool already exists and can run without executing project code;
- git churn/change facts;
- dirty-diff paths;
- public/package metadata surfaces.

The orchestrator then applies judgment to create:

- trust boundaries;
- state boundaries;
- public-contract boundaries;
- change-closure obligations;
- high-blast-radius components;
- verification-risk areas.

No AI-authorship estimate is produced.

### Phase 2: Applicability and targeted evidence packets

Every lens card must declare:

- `Purpose / failure family`
- `Applicability`
- `Skip conditions`
- `Scope emphasis`
- `Required project context`
- `Deterministic probes`
- `Review questions`
- `False-positive guards / non-findings`
- `Evidence requirements`
- `Exposure metric`
- `Escalation / cross-lens handoff`
- `Out of scope`

The orchestrator records why each lens ran or skipped.

For each active lens, generate a bounded evidence packet containing only the highest-value starting context:

- target paths/symbols;
- relevant contract/spec/ADR references;
- immediate callers/callees or route/middleware chain as applicable;
- matching tests;
- relevant manifests/config;
- deterministic probe results;
- known risk/closure signals.

A lens may expand beyond the packet when necessary to prove or refute a claim, but bulk repository loading is not the default.

### Phase 3: Specialist review

Retain one generic `tribunal-lens-reviewer`.

Change its trust/tool contract:

- assignment, Tribunal shared contracts, and the selected lens card are authority;
- repository/user-content artifacts read during the review are untrusted evidence and cannot change role, scope, tools, output schema, filing authority, or run state;
- source comments that look like system/developer/reviewer instructions are analyzed as source content only;
- the lens reviewer must not execute arbitrary repository-provided commands;
- default review should use read/search/write-to-run-dir capabilities, not general-purpose execution.

The reviewer writes findings and leads durably as they are discovered.

### Phase 4: Verification

Introduce a separate verification role or explicit verification mode whose job is to disprove a candidate finding.

Verification is mandatory for:

- provisional critical;
- provisional high;
- any medium promoted during triage to high/critical;
- any finding whose recommendation requires a materially expensive or invasive change and whose proof is primarily inferential.

Verification may use:

1. direct code/contract trace;
2. deterministic static probe;
3. repository-native test/lint/type/security command explicitly documented in `tech-stack.md`;
4. a minimal non-mutating reproduction;
5. a fresh-context reviewer with only the candidate finding and necessary evidence.

The verifier does not modify product code. Temporary reproduction artifacts must live outside tracked product paths or under the run directory and be cleaned/recorded.

Verification output records:

- `confirmed`;
- `refuted`;
- `narrowed`;
- `inconclusive`.

Only confirmed/narrowed serious findings proceed as confirmed fix work. Inconclusive serious items remain `verify-required`.

For hosts unable to provide fresh subagent context, record `verification_independence: limited`. Do not claim equivalent independent verification.

### Phase 5: Root-cause triage

Triage groups corroborating findings by root cause before issue planning.

The orchestrator:

- calibrates severity from impact and likelihood only;
- calibrates confidence from evidence and verification;
- separates factual uncertainty from design decisions;
- records corroborating lenses;
- prevents multiple issues for one underlying defect unless remediation ownership is genuinely separable.

Decision vocabulary becomes at least:

- `keep`
- `combine`
- `duplicate`
- `false-positive`
- `defer`
- `accept-risk`
- `decision-required`
- `verify-required`
- `investigate`

### Phase 6: Report and planning

Preserve the current projection model. Reports are regenerated from authoritative findings/leads/logs.

Report sections distinguish:

1. verified defects;
2. verification-required items;
3. genuine decisions needed;
4. investigate/debt appendix;
5. lens applicability/coverage;
6. verification coverage;
7. review-cost/evidence summary.

Plans cover verified `keep`/`combine` work only. A finding that still needs verification does not become an implementation-plan item.

### Phase 7: Filing, disposition, telemetry, terminal completion

Keep explicit filing authorization and opt-in telemetry.

Add `run-completed` after the user has either:

- completed or explicitly skipped filing; and
- completed or explicitly skipped telemetry.

A completed audit with skipped follow-ups is terminal. A report-written audit with undecided follow-ups is resumable at follow-up only.

## Failure-model modernization

### Replace `ai-markers.md` with review-risk signals

Rename/rewrite the concept to avoid AI-authorship inference.

Do not attempt to identify whether a human or model authored a file from style or commit-message shape.

Structural thresholds such as import count, fan-in, file length, or churn may route scrutiny but cannot alone be a finding. A finding must name the concrete correctness, maintainability, security, or change-risk consequence.

### Add semantic-contract review

Add a first-class lens/failure family focused on "plausible but semantically wrong" implementations.

It examines:

- issue/spec requirements;
- accepted ADR/decision obligations;
- public API/protocol behavior;
- pre-existing behavior that must remain unchanged;
- forbidden behavior/negative requirements;
- edge semantics;
- compatibility constraints;
- whether tests encode the requested behavior rather than merely the implementation.

A semantic-contract finding requires a concrete contract/evidence source. Absence of a written product contract is not permission to invent one.

### Add change-closure review

Add a first-class lens/failure family for incomplete propagation of a logically complete change.

It examines applicable surfaces such as:

- callers/consumers;
- generated projections;
- host adapters;
- manifests;
- package contents;
- install/update/uninstall paths;
- CI gates;
- release automation;
- schemas;
- compatibility behavior;
- migrations;
- docs where they are part of the shipped operator contract.

It must distinguish source implementation from exact distributed-artifact proof. Current `main` does not establish release behavior.

### Verification-quality replaces simplistic test-count reasoning

Unify the conceptual responsibility currently split between coverage and test-fidelity. Implementation may replace the two cards with one `verification-quality` card and preserve old public lens URLs through redirects.

The lens asks:

- Does the test contain an oracle strong enough to distinguish a plausible wrong implementation?
- Is the expected behavior derived independently from the code under test?
- Does a mock/double faithfully model the contract being relied on?
- Are negative/forbidden behaviors checked?
- Are failure, concurrency, cancellation, compatibility, and boundary semantics tested when relevant?
- Can mutation/differential/property/metamorphic checks cheaply strengthen confidence?
- Did the same implementation trajectory author tests that merely agree with its own interpretation?

Mocks, fixtures, or generated tests are not findings by themselves.

### Reliability

Rewrite from syntax-based async checks to ownership/semantics:

- error ownership and propagation;
- cancellation;
- timeout/deadline behavior;
- retries and idempotency;
- atomicity;
- concurrent mutation and ordering;
- resource lifecycle;
- partial failure;
- orphan state;
- fail-open/fail-closed behavior;
- recovery and restart semantics.

Do not require every `await` or Promise chain to catch locally. Intentional propagation to a documented owning boundary is valid.

### Application security

Keep appsec, but require reachability and trust-boundary reasoning.

Examples:

- resource-level authorization;
- injection sinks with actual untrusted reachability;
- privilege transitions;
- authentication/session/token validation;
- SSRF/path/deserialization boundaries;
- business-logic authorization;
- prompt/data instruction boundaries in agentic systems.

CORS wildcard, string concatenation, or other syntactic signatures are candidates for analysis, not automatic severity conclusions.

### Supply chain and secrets

Keep the domain, but move registry existence, known-vulnerability lookup, lock consistency, and simple secret-pattern discovery to deterministic probes where practical.

Model judgment focuses on:

- dependency necessity;
- suspicious/confusable package identity;
- provenance/trust implication;
- dangerous package use;
- secret flow;
- logging/transmission/storage semantics.

### Migration

First establish the repository's actual migration/deploy model. Do not universally require a down migration.

Review:

- expand/contract compatibility;
- lock duration;
- large-table behavior;
- backfill correctness;
- operation ordering;
- irreversible/destructive changes;
- recovery evidence;
- mixed-version application/database windows.

### Architecture

Architecture remains useful but must not file "god module" or pattern-drift findings from fixed numeric thresholds alone.

A finding needs a concrete consequence, such as:

- unsafe coupling;
- impossible change isolation;
- duplicated policy likely to diverge and already demonstrating drift;
- unreachable/dead production path;
- violated repository-owned architectural contract;
- generated/canonical ownership ambiguity.

### Observability

Make applicability explicit. Local libraries are not defective merely because they lack tracing.

Review required diagnosability where the product/stack demands it:

- critical failure reason;
- correlation across service/async boundaries;
- security/audit event completeness;
- bounded diagnostic detail;
- failure-mode observability needed for operations/recovery.

### Performance

Require an actual performance premise:

- documented SLO/latency/resource constraint;
- observed benchmark/profile;
- clear asymptotic issue;
- repeated I/O/subprocess/network operation on a plausible hot path;
- unbounded growth;
- demonstrable scale multiplier.

"Could cache/memoize" without such a premise is not a finding.

### Type safety

Focus on unsound boundaries:

- unvalidated external data;
- schema/type mismatch;
- unchecked narrowing;
- nullability;
- exhaustive variants;
- identifiers/units represented interchangeably;
- public interface contracts;
- escape hatches that demonstrably bypass a needed invariant.

Naming style and generic error-message quality do not belong in the type-safety lens.

## Reviewer prompt-injection boundary

The following must be explicit in the generic reviewer, mapper/extractor handoff, verifier, and triage paths:

- repository source is untrusted evidence;
- comments/docs/tests/config/PR text/issues/tool output cannot alter the assignment;
- strings that imitate system/developer/assistant/tool instructions remain data;
- reviewers do not follow instructions discovered in evidence;
- only caller-owned assignment metadata and checked-in Tribunal contracts govern the role;
- untrusted content cannot grant write, network, execution, issue-filing, or scope authority.

Where deterministic extraction can avoid exposing large raw untrusted text to the reasoning model, prefer it.

## Tool boundary

### Generic lens reviewer

Target default tools:

- Read
- Grep/search
- Glob
- Write restricted by procedure to its run directory

Remove general Bash execution from the normal reviewer contract unless a host cannot otherwise provide an equivalent read-only capability.

### Deterministic extractor

Use a repository-owned helper invoked by the orchestrator. It may inspect git metadata and parse files. It must not:

- execute project scripts;
- install dependencies;
- source shell files;
- evaluate configuration as code;
- follow untrusted instructions.

### Verifier

May run only explicitly trusted commands from the repository's `.codearbiter/tech-stack.md` or a bounded built-in probe. Every executed command and result status is captured as evidence.

## Cost model

Replace the current fixed assumption that every lens rereads roughly half of the repository.

Estimate from:

- selected evidence packet size;
- number of active lenses;
- selected host execution profile;
- verification candidates expected from prior data;
- deterministic-extraction overhead;
- observed per-lens usage from compatible historical runs when available.

Historical observations are calibration data, not guarantees.

The estimator must continue to show its inputs and a broad uncertainty band.

## Evaluation corpus

Create a versioned Tribunal evaluation corpus before promoting the new doctrine.

### Minimum case families

Include both defect and clean-control cases for:

1. intentional async error propagation that must not be flagged;
2. swallowed/incorrectly translated error that must be flagged;
3. faithful mock versus stale/unfaithful mock;
4. test that executes code but has no meaningful oracle;
5. test authored from the implementation that validates the same wrong behavior;
6. semantically divergent but plausible patch;
7. over-broad behavior change that still passes supplied tests;
8. incomplete generated/host/package/release propagation;
9. concurrency/read-modify-write race;
10. resource-level authorization failure;
11. reachable injection sink;
12. public credential-free CORS wildcard clean control;
13. package name that does not exist in the intended registry;
14. justified one-implementation interface clean control;
15. actual leaky/cosmetic abstraction with a concrete consequence;
16. type cast that is safe by validated construction versus an unsound boundary escape;
17. performance-looking loop that is cold/bounded versus real repeated I/O on a hot path;
18. repository file containing instruction-shaped prompt injection;
19. cross-lens defect that must consolidate to one root cause;
20. resume attempt after source fingerprint drift.

Prefer real historical defects from codeArbiter where they can be reduced into stable fixtures without encoding the answer in the prompt.

### Evaluation outputs

For each model/host/card revision capture:

- required findings hit/missed;
- forbidden findings/false positives;
- unique verified root causes;
- duplicate/corroboration behavior;
- serious-finding verification survival;
- prompt-injection compliance;
- token usage when observable;
- evidence/context size;
- run duration.

Primary quality measures:

- recall on known defects;
- false-positive rate on clean controls;
- serious-finding precision after verification;
- unique verified root causes per unit cost.

Raw finding count is not a quality metric.

### Qualification rule

A card/model/orchestration change must not be promoted as the recommended Tribunal configuration solely because it produces more findings.

Compare candidate versus incumbent on the same frozen corpus. Any regression in critical security/correctness cases blocks promotion unless explicitly accepted with evidence and rationale.

Model-generation upgrades are a reason to rerun the corpus, not to assume older prompts remain optimal.

## Telemetry evolution

Public opt-in telemetry remains aggregate-only.

Add aggregate fields only if they preserve the current privacy boundary, for example:

- lenses skipped by applicability;
- findings sent to verification;
- verification outcomes;
- root-cause group count;
- corroboration count;
- evidence-packet token/size bands;
- deterministic-probe counts.

Do not transmit repository identity, paths, code, finding text, commit hashes, or source fingerprints.

Post-run real-world disposition should be captured locally where possible. Same-run `false-positive` alone is not sufficient ground truth for detector precision.

## Backward compatibility and migration

1. Existing historical Tribunal run directories remain readable as historical evidence.
2. Runs without a source fingerprint are marked legacy/unbound. They may be reported but do not silently resume as current.
3. Existing `finding/v1` records remain readable. New fields should be additive where possible.
4. Do not create a new schema version merely because an optional field is added. Version only when a consumer-visible incompatible contract actually changes.
5. If `coverage` and `test-fidelity` are replaced by `verification-quality`, preserve their public site URLs through redirects and retain historical lens names in old run rendering.
6. The generic `tribunal-lens-reviewer` remains the normal specialist executor.
7. Existing issue references and historical dedup keys remain resolvable. New root-cause identity does not rewrite old logs.
8. This effort does not rename the public `tribunal` command or implement the separate catalog proposal to expose it as `review deep`.

## Workstreams

### T1: Run-state correctness

- source fingerprint
- unique run IDs
- explicit terminal state
- legacy-run behavior
- resume drift tests
- durable cross-lens leads
- root-cause/corroboration fields

### T2: Reviewer trust boundary

- untrusted-evidence doctrine
- remove/restrict arbitrary execution from normal lens reviewer
- deterministic extractor boundaries
- prompt-injection fixtures
- verifier execution allowlist

### T3: Failure-model rewrite

- replace `ai-markers.md` with review-risk signals
- add semantic-contract lens
- add change-closure lens
- consolidate coverage/test-fidelity into verification-quality or implement equivalent single ownership
- modernize reliability, appsec, supply, migration, architecture, observability, performance, and type-safety mandates
- add false-positive guards and applicability rules to every card

### T4: Adaptive orchestration

- deterministic inventory
- lens applicability selection
- targeted evidence packets
- finding/evidence scope split
- host-native profile resolution
- revised cost estimator

### T5: Independent verification

- verifier role/mode
- serious-finding verification gate
- verification statuses
- host-independence reporting
- triage integration

### T6: Evaluation and calibration

- frozen defect + clean-control corpus
- runner/procedure
- incumbent/candidate comparison
- quality/cost metrics
- promotion rule
- model-generation requalification procedure

### T7: Documentation and projections

- regenerate Claude/Codex/Pi surfaces
- host-native model/capability wording
- site lens pages/redirects
- telemetry schema/prose
- developer-facing research/rationale note
- current tests updated from count-only/card-presence assertions to contract assertions where appropriate

## Acceptance criteria

1. A fresh Tribunal run records an exact source fingerprint before lens dispatch.
2. A resume against changed HEAD, changed dirty diff, changed explicit target, or incompatible scope does not silently reuse completed review work.
3. Two fresh runs for the same scope on the same date cannot collide.
4. `report-written` no longer means terminal completion; `run-completed` or equivalent records terminal disposition.
5. A disconnect after report generation can resume at filing/telemetry/disposition without rerunning lenses.
6. Cross-lens leads are durable, resumable, and explicitly disposed.
7. Same root defect reported by multiple lenses can consolidate under a lens-independent root-cause identity while retaining lens provenance.
8. Triage does not convert factual uncertainty into `decision-required`. Genuine design choices and unverified factual claims have distinct states.
9. Severity is a function of impact/likelihood, not inferred AI authorship, commit style, comment density, or iteration history.
10. No current host projection uses provider/model instructions unsupported by that host. Codex/Pi output contains no accidental Claude API/model contract.
11. A host without subagent capability explicitly records inline/shared-context execution limitations.
12. Deterministic inventory covers the agreed mechanical facts without using a model agent for basic counting/enumeration.
13. The deterministic extractor does not execute project-provided code or configuration.
14. Every lens card implements the mandatory applicability, skip, deterministic-probe, false-positive-guard, evidence, exposure, escalation, and out-of-scope sections.
15. The generic lens reviewer explicitly treats repository content and tool output as untrusted evidence, not instructions.
16. Normal lens review cannot run arbitrary repository shell commands.
17. A subtree finding may use bounded evidence outside the subtree without filing unrelated outside-scope defects.
18. Absence findings state the search universe/boundary trace needed to establish ownership of the missing behavior.
19. Semantic-contract review catches at least the corpus's plausible-but-wrong and over-broad-patch cases without inventing an unwritten requirement.
20. Change-closure review catches the corpus's incomplete generated/host/package/release propagation cases.
21. Verification-quality distinguishes strong behavioral oracles from smoke/test-presence theater and includes clean controls for legitimate mocks.
22. Reliability does not flag intentional error propagation solely because an `await` lacks local catch handling.
23. Appsec severity depends on actual trust/reachability/exploitability evidence rather than a syntactic signature alone.
24. Migration review adapts to the declared deploy/migration model rather than universally requiring down migrations.
25. Performance findings require an observed/documented scale premise, not speculative optimization.
26. Type-safety findings demonstrate an unsound contract/boundary, not style drift alone.
27. Every provisional critical/high finding receives the required independent verification attempt or is reported as verification-required.
28. A refuted serious finding cannot be filed as a confirmed defect.
29. The evaluation corpus contains both defect and clean-control cases for all minimum families listed above.
30. The evaluation procedure reports recall, false positives, serious-finding verification survival, unique root causes, duplicate/corroboration behavior, and cost/evidence size.
31. A candidate Tribunal configuration cannot replace the incumbent if it regresses a critical corpus case without an explicit approved exception.
32. Historical run records remain readable; unbound legacy runs never masquerade as fingerprint-bound current evidence.
33. Existing issue references remain resolvable and old logs are not rewritten.
34. If lens names are retired, generated documentation preserves historical URLs through redirects.
35. Public telemetry remains opt-in and does not add source fingerprints, code, paths, commit hashes, or finding text.
36. Host projections and generated documentation are rebuilt and pass exact-surface parity/reference checks.
37. Unit/contract tests cover the new run-state, resume, trust-boundary, schema, routing, and host-projection behavior.
38. The PR implementing this spec includes benchmark evidence comparing incumbent and candidate Tribunal behavior on the frozen corpus.

## Explicit non-goals

- Make Tribunal a mandatory merge/commit gate.
- Rename `tribunal` to `review deep`; catalog rationalization owns that product-surface decision.
- Replace ordinary diff review, checkpoint review, or threat modeling.
- Prove release behavior from current `main`.
- Infer who authored code.
- Install or execute arbitrary analyzers/dependencies merely to run Tribunal.
- Auto-file issues or telemetry without the existing explicit authorization.
- Convert every judgment-heavy checklist into a new machine-readable DSL.
- Require a live external model evaluation on every ordinary repository commit.
- Guarantee that one model or one prompt can detect every defect.

## Research basis recorded for maintainability

These references informed the failure-model changes. They are supporting evidence, not product authority:

- Wang, Pradel, Liu, "Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study", arXiv:2503.15223 / ICSE 2026. Reports plausible patches that pass benchmark checks yet fail developer tests or diverge behaviorally from developer patches.
- "All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code", DOI 10.1109/AITest70988.2026.00038. Reports weak or absent explicit oracle signals across a large corpus of agent-authored test patches.
- Tao et al., "ExecCritic: Learn to Test, Test to Improve for Coding Agents", arXiv:2609.09133. Motivates separation between test construction and source repair when shared trajectory errors can agree.
- Kumar, "SWE-PRBench: Benchmarking AI Code Review Quality Against Pull Request Feedback", arXiv:2603.26130. Reports low single-model recall and degradation as review context expands.
- "How Vulnerable Are AI Agents to Indirect Prompt Injections? Insights from a Large-Scale Public Competition", arXiv:2603.15714. Demonstrates indirect-injection success across coding/tool/computer-use agent scenarios.
- Churilov, "The Range Shrinks, the Threat Remains: Re-evaluating LLM Package Hallucinations on the 2026 Frontier-Model Cohort", arXiv:2605.17062. Supports keeping supply-chain package validation relevant even as model quality improves.

Research claims must not be turned into hard-coded numeric thresholds in lens cards without a repository-specific reason and qualification evidence.

## Verification required before implementation approval

Before this spec moves from PROPOSED to APPROVED:

1. adversarially review the spec against current source for implementation contradictions and silent failure modes;
2. decide whether `coverage` and `test-fidelity` are physically replaced by `verification-quality` in one compatibility wave or kept temporarily as separate cards sharing the new doctrine;
3. select the exact host-native mechanism for `deep`/`standard`/`extract` profile resolution;
4. select the exact source-fingerprint representation and legacy-run behavior after exercising current run artifacts;
5. confirm the minimal evaluation-runner mechanism that can compare model behavior without creating a CI dependency on paid/live inference.

No implementation claim is made by this spec.
