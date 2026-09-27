# Tribunal and agent deep review: effectiveness, efficiency, and modern AI-code failure modes

**Review date:** 2026-09-26
**Current-source authority inspected:** `arbiterForge/codeArbiter@8e88bce938ebf7dc8cfd934307b8d6859092d86e` on `main`
**Review type:** development-architecture and review-quality assessment
**Not a release audit:** current `main` is development evidence, not proof of released behavior
**Historical comparison:** the 2026-08-26 re-audit was bound to `cf323b9e2c30ad0bdac3f086552fd3860b4ca72a`; current inspected `main` is 484 commits ahead of that historical audit point

## Executive finding

Tribunal's architecture is considerably better than its current failure model.

The August consolidation to one generic `tribunal-lens-reviewer` plus data-driven lens cards was a sound efficiency improvement and should remain. The principal modernization need is not to recreate specialist agent bodies. It is to update:

- what the lens cards consider high-yield failure modes;
- how scopes and evidence packets are selected;
- how serious findings are independently verified;
- how run state binds to the source that was actually audited;
- how repository content is treated as untrusted evidence;
- how host capability differences are represented; and
- how Tribunal measures its own detection quality over time.

The current cards visibly retain heuristics from an earlier generation of AI-written code research. Current coding models are substantially better at producing clean, conventional, plausible code. Review value has shifted toward semantic divergence, incomplete propagation, verification weakness, boundary/state behavior, and cross-surface closure.

## Scope inspected

Primary current-source files:

- `core/surface/skills/tribunal/SKILL.md`
- `core/surface/agents/tribunal-lens-reviewer.md`
- `core/surface/agents/map-structure.md`
- `core/surface/agents/map-deps.md`
- `core/surface/skills/tribunal/references/ai-markers.md`
- `core/surface/skills/tribunal/references/cost-and-models.md`
- `core/surface/skills/tribunal/references/finding-record.md`
- `core/surface/skills/tribunal/references/triage.md`
- `core/surface/skills/tribunal/references/schemas.md`
- `core/surface/skills/tribunal/references/report.md`
- `core/surface/skills/tribunal/references/issue-filing.md`
- `core/surface/skills/tribunal/references/telemetry.md`
- all eleven lens cards under `core/surface/skills/tribunal/references/lenses/`
- `core/hosts.json`
- generated Tribunal surfaces for Claude, Codex, and Pi
- historical Tribunal runs committed under `.codearbiter/reports/` and `docs/reports/`
- ADR-0027, which establishes the generic-lens-reviewer architecture

No repository changes were made during the review itself.

## What is strong and should be preserved

### Generic reviewer plus lens cards

ADR-0027 correctly identified that the prior eleven Tribunal agent bodies were mostly duplicated mechanics around small lens-specific mandates. One generic reviewer:

- reduces always-loaded agent registry context;
- removes eleven-way contract drift;
- keeps model tiering/routing at dispatch time;
- makes adding/updating a lens primarily a data/mandate change.

The modernization should strengthen the cards and orchestration, not reverse this consolidation.

### Durable finding writes

Writing one file per finding at discovery time is a good crash/compaction design. It avoids a single shared mutable finding stream and limits loss to the in-flight finding.

### Evidence-or-drop discipline

Requiring concrete source evidence and refusing truncated-window absence claims materially improves review quality compared with generic "code smell" commentary.

The rule needs to be expanded from "whole file/unit" to boundary/search-universe evidence for some absence classes, but the principle is correct.

### Central triage

Lens severity/confidence being provisional and centrally recalibrated is correct. The orchestrator should remain responsible for dedup, root-cause grouping, severity, confidence, and filing eligibility.

### Explicit outward-action authorization

Issue filing and telemetry remain separately authorized. Tribunal can identify blocking-severity defects without itself becoming a mandatory workflow gate.

### Historical runs provide useful empirical data

Committed run artifacts make it possible to inspect actual lens yield and spend rather than reviewing prompt prose only.

## High-priority correctness findings

### R1. Resume can silently cross source states

Current source decides whether an incomplete run is resumable primarily by run age and the last triaged wave.

It does not bind a run to exact HEAD, dirty diff, explicit review target, or a digest of the source state that produced the findings.

Impact:

- a branch can change substantially while a run remains less than seven days old;
- completed lens results may be reused against different bytes;
- the resulting report can appear durable and precise even though its findings span source states.

Recommendation:

record and validate an immutable source fingerprint. Time should be a staleness hint, never the source identity.

### R2. Same-day run directory collision

A fresh run ID is currently `<UTC-date>-<scope-slug>`.

Two completed audits of the same scope on the same day can select the same directory. Fresh runs need a timestamp/unique suffix and must never overwrite/reuse a completed run implicitly.

### R3. `report-written` is treated as terminal too early

Report creation occurs before issue filing and telemetry, but resume logic treats the presence of `report-written` as complete.

A disconnect after the report but before an authorized filing step should resume the follow-up, not force a new audit.

Recommendation:

separate audit completion, follow-up disposition, and terminal `run-completed`.

### R4. Cross-lens leads are ephemeral

The generic reviewer says a cross-lens observation must be returned as one-line `[NEEDS-TRIAGE]` and never dropped. No corresponding durable lead schema exists.

That means a lead can disappear when:

- the returned summary is compacted;
- a dispatch dies;
- the run resumes from disk without reloading prior summaries.

Recommendation:

persist lead/handoff records separately from findings.

### R5. Dedup is structurally lens-biased

Current dedup identity contains the lens name. A single root defect corroborated by architecture, reliability, performance, observability, and coverage starts with different keys.

Historical runs show the same root cause being discovered through multiple lenses and then manually combined or marked duplicate.

Recommendation:

retain lens provenance, but add a lens-independent root-cause identity during triage.

### R6. Factual uncertainty is conflated with product decisions

Below-confidence critical/high findings currently become `decision-required`.

A low-confidence claim that a race, vulnerability, or corruption path exists is not an ADR decision. It is an unverified factual claim.

Recommendation:

add `verify-required` and reserve `decision-required` for genuine design/product choices.

### R7. Finding scope and evidence scope need separation

A scoped audit of one subtree may need to inspect callers, middleware, schemas, contracts, manifests, generated surfaces, or tests elsewhere to judge the subtree correctly.

Current language treats the assigned path slice as the review scope without explicitly separating evidence expansion from filing scope.

Recommendation:

define `finding_scope` and `evidence_scope`.

### R8. Negative evidence is too local

"Read the whole relevant unit" is necessary but not sufficient for many absence claims.

Examples:

- error propagation may intentionally terminate at a central handler;
- authorization may live in route middleware;
- lifecycle cleanup may be owned by a parent;
- validation may be centralized before a typed internal boundary.

Recommendation:

absence findings state the boundary/search universe used to establish ownership of the missing behavior.

## Failure-model findings

### R9. AI-authorship markers have aged poorly

Current `ai-markers.md` uses:

- excessive trivial comments;
- stale TODO/FIXME;
- near-duplicate functions;
- convention switches;
- naming drift;
- AI commit trailers;
- generated-looking conventional commit shapes;

to raise scrutiny and then apply a small severity prior.

There are two problems.

First, these signals are weaker as authorship indicators now that coding models better match repository style.

Second, authorship should not change severity at all. Severity belongs to impact and likelihood.

Recommendation:

replace AI-authorship inference with author-independent review-risk signals. Churn, blast radius, trust boundaries, state mutation, public contracts, concurrency, release/package fan-out, generated-source relationships, and weak verification can route scrutiny. They do not independently raise severity.

### R10. Architecture thresholds should route, not convict

Current architecture guidance treats fixed import/fan-in thresholds as "likely god module" / critical shared-dependency signals.

These may be useful prioritization hints. They are not sufficient findings.

A high fan-in module can be a deliberate stable primitive. A large module can be cohesive. A one-implementation interface can enforce an important boundary.

Recommendation:

require a concrete consequence before filing architecture debt: unsafe coupling, demonstrated drift, impossible isolation, dead path, ownership ambiguity, or a violated repository-owned architecture contract.

### R11. Reliability's async heuristic is too syntactic

Current reliability guidance asks for every `await`/Promise/then chain to have local catch handling.

Intentional propagation is often correct. Catching locally can be worse if it converts a typed failure into a weak fallback or duplicate logging.

Recommendation:

trace error ownership end to end and emphasize:

- propagation semantics;
- cancellation;
- timeouts/deadlines;
- retries/idempotency;
- atomicity;
- race/order behavior;
- lifecycle;
- partial failure;
- fail-open/fail-closed;
- recovery.

### R12. Test-fidelity and coverage should become verification-quality

The important modern question is not "did the agent use a mock" or even "is there a test file."

It is whether the verification can distinguish a plausible wrong implementation from the required behavior.

Current test-fidelity correctly worries about tests validating fiction but can over-penalize doubles. Current coverage includes implementation-detail assertions but remains relatively conventional.

Recommendation:

one verification-quality owner should assess:

- oracle strength;
- oracle independence from implementation;
- contract fidelity of doubles;
- forbidden/negative behavior;
- failure/concurrency/compatibility semantics;
- useful property/metamorphic/differential checks;
- same-trajectory patch/test agreement risk.

A mock is not a finding. An unfaithful mock that lets a real defect pass is.

### R13. Semantic-contract correctness is missing as a first-class concern

Modern agents can produce code that is locally coherent, clean, and test-passing but does the wrong thing at one semantic edge or changes more behavior than requested.

Add a semantic-contract lens/failure family that checks implementation against:

- issue/spec requirements;
- accepted decisions;
- public API/protocol behavior;
- compatibility;
- required unchanged behavior;
- forbidden behavior.

It may not invent an unwritten product requirement.

### R14. Change closure is missing as a first-class concern

Historical codeArbiter Tribunal runs repeatedly found incomplete propagation:

- missing CI/release routes;
- host parity gaps;
- source/package divergence;
- generated-surface omissions;
- tests that exercised flags rather than the real behavior.

Add a change-closure lens/failure family for logically incomplete propagation across callers, generated surfaces, adapters, manifests, packages, CI, release, schema, docs-as-contract, and compatibility paths.

### R15. Appsec should reason about reachability, not signatures alone

Current appsec contains useful high-yield classes such as IDOR/resource-level authorization.

Some checklist wording is too absolute:

- concatenation does not establish exploitable injection without a real sink and untrusted reachability;
- CORS wildcard is context-dependent;
- validation requirements depend on whether the boundary is still untrusted.

Recommendation:

use deterministic probes to locate candidate sinks, then model reasoning for trust, reachability, authorization, exploitability, and business logic.

### R16. Supply-chain checks should become partly deterministic

Package hallucination/slopsquatting remains a real concern, but a language model should not visually guess whether a dependency exists.

Registry existence, lock consistency, known-vulnerability checks, and simple secret patterns are better deterministic probes.

The model should reason about package necessity, confusable identity, provenance, dangerous use, and secret flow.

### R17. Migration should respect the repository's migration model

A universal rollback/down-path expectation is not valid for all production migration strategies.

Review expand/contract safety, locks, large backfills, mixed-version windows, destructive steps, operation ordering, and recovery according to the project's declared deployment model.

### R18. Observability applicability is under-specified

A local library is not defective for lacking tracing or business metrics.

Run the lens where the product/tech stack declares operational/audit requirements. Focus on diagnosability of critical failures, correlation, bounded failure detail, and required audit/security events.

### R19. Performance is vulnerable to speculative findings

"Could memoize/cache/hoist" is not enough for an expensive deep-audit finding.

Require a scale premise:

- SLO/resource contract;
- profile/benchmark;
- asymptotic issue;
- repeated external I/O/subprocess on a plausible hot path;
- unbounded growth.

### R20. Type safety includes concerns that do not belong there

Type escapes matter when they create an unsound boundary. Naming drift and generic error-message quality do not belong in a type-safety lens.

Focus on schema/runtime mismatch, nullability, exhaustive variants, identifiers/units, unchecked external data, public contracts, and escapes that bypass a real invariant.

## Efficiency findings

### E1. Full specialist scans are not consistently cost-effective

Historical codeArbiter evidence shows strong variation in yield.

#### July 9 Codex-support run

Observed reviewer spend:

- appsec: 105,860 tokens, 2 findings
- architecture: 109,901, 10 findings
- reliability: 141,387, 9 findings
- secrets-supply: 84,644, 0 findings
- test-fidelity: 63,454, 0 findings
- coverage: 76,012, 4 findings
- infra: 65,826, 3 findings
- observability: 71,020, 4 findings
- performance: 64,676, 3 findings
- typesafety: 67,894, 1 finding

Secrets-supply plus test-fidelity consumed about 148k reviewer tokens for zero findings in that run.

#### July 17 Pi-support run

Observed reviewer spend included:

- reliability: 163,147 tokens
- appsec: 147,462, 0 findings
- architecture: 54,222
- secrets-supply: 93,331, 0 findings
- test-fidelity: 93,804, one low finding that triaged to investigate
- infra: 62,177
- coverage: 54,993
- observability: 123,347
- typesafety: 80,288
- performance: 92,163

Appsec, secrets-supply, and test-fidelity consumed roughly 335k reviewer tokens for only one low-confidence item in that particular run.

This does not justify deleting those domains. Public telemetry contains other runs where security/supply/test lenses found material issues. It does show that "all applicable concerns get a full expensive specialist pass over broad scope" is not cost-optimal.

Recommendation:

use deterministic reconnaissance and applicability signals before expensive model review.

### E2. Mapping agents perform many deterministic tasks

`map-structure` and `map-deps` currently spend model context on file tree shape, language counts, manifests, dependency names, env-variable reads, and git churn.

These are largely extractable without reasoning.

Recommendation:

produce a deterministic machine-readable inventory, then ask a model only to classify ambiguous boundaries/load-bearing relationships.

### E3. More context is not automatically better review

Tribunal's architecture is still oriented toward large lens reads. Recent review benchmarking indicates that extra broad context can reduce issue detection through attention dilution.

Recommendation:

start reviewers with concise evidence packets and permit targeted expansion, rather than feeding every lens a large fraction of the repository.

### E4. Lower concurrency is mislabeled as a cost-control lever

Lower concurrency can help rate limits, peak resources, and wall-clock contention. Running the same review work sequentially generally does not eliminate token work.

Primary cost controls should be:

- narrower scope;
- lens applicability;
- deterministic extraction;
- smaller evidence packets;
- validated lower model tier/profile where appropriate;
- fewer redundant/corroborating passes.

### E5. The estimator is intentionally crude but now has enough evidence to improve

The current formula assumes each lens processes roughly half the repository with a fixed multiplier.

A July 2 telemetry run estimated 4.5M tokens and observed about 853k. Other runs have incomplete actuals.

Recommendation:

estimate from selected evidence size and active lenses, then calibrate by host/profile/lens using compatible observed history where available.

## Host-specific defect

Current generated:

`plugins/ca-codex/routines/tribunal/references/cost-and-models.md`

contains Claude-specific model guidance such as Opus/Sonnet/Haiku API strings and Anthropic-only proprietary-code wording.

At the same commit:

`core/hosts.json`

declares Codex `capabilities.agents: false`.

The Codex Tribunal skill later contains a fallback note for inline execution, but the primary shared Phase 2 contract still describes dispatching one lens-reviewer per active lens.

Recommendation:

make the shared contract provider-neutral and resolve `deep`/`standard`/`extract` profiles per host. Hosts without subagent isolation must record that limitation explicitly.

## Reviewer prompt-injection gap

The generic Tribunal lens reviewer has Read, Grep, Glob, Bash, and Write and consumes arbitrary repository content.

Its current body does not contain a broad rule that source comments, docs, tests, PR/issue text, command output, and instruction-shaped strings are untrusted evidence rather than authority.

This matters especially for a deep repository audit, whose purpose requires reading large quantities of potentially attacker-controlled text.

Recommendation:

- add an explicit untrusted-evidence contract;
- remove arbitrary Bash from normal lens review if not required;
- put execution into a bounded verifier stage;
- add hostile repository-content cases to the Tribunal eval corpus.

## Verification architecture

Keep multi-reviewer specialization, but change the unit of work.

Current shape:

`repository -> many lenses -> broad rereads -> orchestrator dedup`

Recommended shape:

`repository -> deterministic inventory -> risk/contract slices -> targeted specialist evidence -> independent verification -> root-cause aggregation`

Independent verification is particularly important for critical/high findings. A strong first reviewer can still be confidently wrong; verification should try to disprove the claim rather than simply restate it.

## Tribunal quality evaluation is the largest process gap

The repository tests that Tribunal cards project correctly across hosts and tests selected mechanics such as usage accounting.

The telemetry documentation itself notes that exposure counts cannot prove detector sensitivity and says seeded-vulnerability canaries or scanner cross-checks would be needed.

No committed Tribunal defect/clean-control corpus was found in this review.

Without one, the project cannot answer:

- did a lens rewrite improve recall or just produce fewer findings?
- did a stronger/newer model make an old heuristic obsolete?
- can a cheaper model now run a lens without quality loss?
- did a prompt cleanup increase false positives?
- does host inline execution materially reduce detection?
- does a security lens's zero finding mean clean source or a blind detector?

Recommendation:

build a small frozen evaluation corpus from real historical failures plus clean controls, then compare incumbent/candidate prompts/models on the same tasks.

Primary metrics should be:

- known-defect recall;
- false-positive rate on clean controls;
- serious-finding verification survival;
- unique verified root causes;
- duplicate/corroboration rate;
- prompt-injection resistance;
- tokens/evidence size per verified root cause.

Raw finding count is not quality.

## Public Tribunal telemetry observation

Four public run-metrics payloads located in codeArbiter issues #200, #246, #309, and #310 contain 212 raw findings in aggregate.

Across those payloads:

- 26 decisions were explicitly duplicates;
- 79 decisions were combine records;
- 13 were investigate records;
- same-run false-positive count was zero.

The zero false-positive field should not be interpreted as proven detector precision. It records triage decisions during the run, not downstream ground truth about whether filed defects were later refuted.

The high combine/duplicate volume reinforces the value of root-cause-first aggregation.

## Research basis

The review used current repository evidence as the authority for codeArbiter facts. The following outside research was used only to reassess likely modern coding-agent failure modes.

### Plausible patches can still be semantically wrong

You Wang, Michael Pradel, Zhongxin Liu, "Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study", arXiv:2503.15223 / ICSE 2026.

Reported results include:

- 7.8% of evaluated patches counted as correct by the benchmark while failing developer-written tests;
- 29.6% of plausible patches showing behavioral differences from developer ground-truth patches;
- similar-but-divergent implementations and overly broad behavior adaptation as common discrepancy causes.

Reference: https://arxiv.org/abs/2503.15223

### Agent-authored tests often provide weak behavioral oracles

"All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code", IEEE AITest 2026, DOI 10.1109/AITest70988.2026.00038.

The study analyzes 86,156 test-file patches from 33,596 agent-authored PRs across 2,807 repositories and reports 80.2% with weak or no explicit oracle signals.

Reference: https://doi.org/10.1109/AITest70988.2026.00038

### Patch and test errors can agree when produced in one trajectory

Leitian Tao et al., "ExecCritic: Learn to Test, Test to Improve for Coding Agents", arXiv:2609.09133.

The paper explicitly motivates separating test construction from source repair because a shared trajectory can encode the same mistaken behavioral interpretation in both patch and test.

Reference: https://arxiv.org/abs/2609.09133

### Broad context can degrade code-review performance

Deepak Kumar, "SWE-PRBench: Benchmarking AI Code Review Quality Against Pull Request Feedback", arXiv:2603.26130.

The benchmark evaluates 350 human-reviewed pull requests. Eight frontier models detect only 15-31% of human-flagged issues in the diff-only configuration, and all eight degrade as the supplied context expands.

Reference: https://arxiv.org/abs/2603.26130

### Indirect prompt injection remains relevant to coding agents

"How Vulnerable Are AI Agents to Indirect Prompt Injections? Insights from a Large-Scale Public Competition", arXiv:2603.15714.

The competition included coding-agent scenarios and recorded successful indirect-injection attacks across every model tested.

Reference: https://arxiv.org/abs/2603.15714

### Package hallucination risk has narrowed but not disappeared

Aleksandr Churilov, "The Range Shrinks, the Threat Remains: Re-evaluating LLM Package Hallucinations on the 2026 Frontier-Model Cohort", arXiv:2605.17062.

Across the reported frontier-model cohort, overall hallucination rates ranged from about 4.62% to 6.10%, supporting deterministic package existence/provenance validation rather than assuming modern models have eliminated the class.

Reference: https://arxiv.org/abs/2605.17062

## Recommended vNext pipeline

1. **Bind:** exact source fingerprint, unique run ID, host capabilities.
2. **Extract:** deterministic inventory and mechanical probes.
3. **Route:** applicability-based lens selection and compact evidence packets.
4. **Review:** generic specialist reviewer under an explicit untrusted-evidence contract.
5. **Verify:** fresh-context/deterministic attempt to disprove serious findings.
6. **Consolidate:** lens-independent root-cause grouping and corroboration.
7. **Report:** verified defects, verification-required items, design decisions, and investigate/debt separated.
8. **Follow up:** explicit issue/telemetry disposition and terminal completion.

## Prioritized implementation sequence

### T1: Correctness floor

- source fingerprint/resume;
- unique run IDs;
- terminal run state;
- durable cross-lens leads;
- lens-independent root cause;
- verification-required state.

### T2: Reviewer trust boundary

- repository-content-is-data rule;
- reduced normal reviewer tool authority;
- bounded verifier execution;
- prompt-injection fixtures.

### T3: Failure-model rewrite

- eliminate AI-authorship severity prior;
- semantic-contract review;
- change-closure review;
- verification-quality ownership;
- modernize all remaining lens heuristics and false-positive guards.

### T4: Adaptive orchestration

- deterministic inventory;
- applicability rules;
- targeted evidence packets;
- host-native model profiles;
- improved estimator.

### T5: Verification

- independent verifier;
- serious-finding verification gate;
- host-independence status.

### T6: Evaluation/calibration

- historical/seeded defects;
- clean controls;
- frozen corpus;
- incumbent versus candidate evidence;
- quality/cost metrics.

### T7: Documentation/telemetry

- document the research rationale so it does not disappear again;
- record revalidation date;
- update aggregate telemetry for verification/root-cause data without weakening privacy;
- regenerate and verify all host projections.

## Product-system note

The Project Source snapshot dated 2026-09-01 recorded Tribunal telemetry/privacy wording as contradicted. Current source has moved.

At the time of this review:

- current `PRIVACY.md` explicitly documents optional per-run Tribunal KPI feedback;
- current `arbiterforge-site` source at `34a6068aac291a084177df22e23a12428868b2d4:index.html` says optional Tribunal feedback requires per-run consent.

Therefore the old project-level telemetry contradiction should be revalidated rather than carried forward automatically. This observation does not prove exact released/package behavior or live deployed-site bytes and is not an implementation requirement of this codeArbiter PR.

## Conclusion

The part of Tribunal most worth preserving is its current structural direction: one generic lens executor, durable per-finding artifacts, central calibration, and explicit outward-action consent.

The part most in need of modernization is the doctrine.

Modern coding-agent review should spend less effort identifying whether code "looks AI-written" and more effort establishing whether apparently good code is semantically correct, completely propagated, independently verified, safe at boundaries, and consistent across the surfaces that make the behavior real.

The companion spec in this PR turns these findings into an implementation contract.
