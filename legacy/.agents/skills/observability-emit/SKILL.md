---
name: observability-emit
---

<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: SKILL.md
-->


# Skill: observability-emit

## Purpose

Govern the emission of operational observability signals — metrics, traces (spans),
structured logs, alert rules, and SLO definitions — so that every signal is
registered in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`, named per project convention,
labeled within cardinality budget, free of secret-shaped values, and (when
alert-relevant) wired to a paired alert rule and SLO. This skill is the parallel of
`audit-emit`: where `audit-emit` governs the compliance event stream, this skill
governs the operational telemetry stream.

---

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Routing conditions:
- Code introduces, modifies, or removes the emission of a metric, span, structured
  log, alert rule, or SLO definition.
- A new code path that should be observable per `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`
  is added (presumptive observability obligation until Phase 1 rules otherwise).
- A label, attribute, or field on an existing observability signal is added,
  renamed, or removed.
- The `observability-emit` skill is referenced in the routing table.

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` is readable — stop if missing.
   This file is the authoritative source for signal categories, naming conventions,
   required labels, cardinality budgets, canonical emit paths, and alert/SLO
   storage locations.
2. `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` is readable — stop if missing.
3. Current stage is known — read `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.

If any file is missing, surface the gap and stop. Do not guess at signal names,
label sets, emit signatures, or storage paths.

---

## Phase 1: Signal Classification

**Goal:** Identify which observability signal category applies to the code change
and confirm the signal name is registered in
`${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` under the correct category.

**Inputs:**
- Description of the code change.
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — authoritative signal categories,
  naming conventions, and per-category registries.

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` in full.
2. Classify the signal into exactly one category per the spec:
   - **metric** — a counter, gauge, histogram, or summary.
   - **span** — a trace span (distributed tracing).
   - **log** — a structured operational log line (not an audit event; audit events
     route through `audit-emit`).
   - **alert** — an alert rule definition.
   - **SLO** — a service-level objective definition.
3. Confirm the signal name follows the naming convention defined in
   `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` for the chosen category. If the spec
   defines a `domain.subsystem.metric_name` pattern (or any other), enforce it.
4. If the signal name is not present in the registered set for its category, add
   it to the registry in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` before proceeding.
   Do not emit an unregistered signal.
5. If the code change introduces multiple distinct signals, classify and register
   each one separately.

**Output:** Confirmed signal category and signal name, with registration status
(existing or newly added).

**Gate:** BLOCK. No Phase 2 begins until every signal produced by the change is
classified and registered. Emitting an unregistered signal name is a policy
violation.

---

## Phase 2: Emit Construction

**Goal:** Build a correct emit call with all required labels, attributes, or
fields populated from `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`, and free of
secret-shaped values.

**Inputs:**
- Signal classification from Phase 1.
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — required labels/attributes per
  category, canonical emit module or function path.
- `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` — secret patterns to exclude
  (consulted via the `secret-handling` cross-route).

**Actions:**

1. Read the canonical emit module or function path defined in
   `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` for the signal's category. Use that
   path exclusively — do not write directly to a logger, bare HTTP client, or
   alternative telemetry shim.
2. Populate every required label, attribute, or field for the signal's category
   as defined in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`. Required label sets are
   declared per category; do not invent fields not declared in the spec.
3. Inspect every label, attribute, or field value for secret-shaped content
   (tokens, keys, credentials, raw PII per `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`).
   If any value could carry secret data, cross-route to the `secret-handling`
   skill Phase 3 before continuing.
4. Do not hard-code environment-specific or deployment-specific constants
   (region, cluster name) as label values unless
   `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` declares them required constants. Use
   runtime-resolved values where the spec calls for dynamic labels.
5. If the change touches multiple emit sites, verify each site populates the full
   required set for its category.

**Output:** Emit call constructed with all required labels/attributes/fields,
sourced from `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`, with no secret-shaped values.

**Gate:** BLOCK if any required label, attribute, or field is missing. BLOCK on
any value that could carry secret data — cross-route to `secret-handling` Phase 3
and do not return to Phase 3 of this skill until cleared.

---

## Phase 3: Cardinality Check

**Goal:** For metrics and spans, confirm that no label dimension is unbounded and
that the combined cardinality of the label set fits the per-signal budget defined
in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`.

**Inputs:**
- Emit call from Phase 2.
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — per-signal cardinality budgets
  and forbidden label patterns.

**Actions:**

1. Skip this phase only for `log`, `alert`, and `SLO` categories (cardinality
   applies primarily to metrics and spans). For `log`, still confirm that no
   structured field value is unbounded user input emitted at indexed-field scope.
2. For each label or span attribute, identify its value domain:
   - **Bounded enum** (e.g., HTTP method, status class) — acceptable.
   - **Bounded identifier set** (e.g., tenant_id with a known small N) —
     acceptable if within the budget declared in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`.
   - **Unbounded identifier** (e.g., raw user_id, request_id, email, URL path
     with embedded IDs, free-text input) — NOT acceptable as a label or indexed
     attribute. Such values belong in span events or log fields, not labels.
3. If `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` declares a numeric cardinality
   budget for the signal (e.g., "total combined label cardinality ≤ 10k"),
   estimate the combined cardinality and confirm it fits the budget.
4. If a label is borderline, surface the question to the user; do not silently
   approve.

**Output:** Confirmed that every label/attribute on metrics and spans has a
bounded value domain and fits the declared cardinality budget.

**Gate:** BLOCK if any label value domain is unbounded. BLOCK if the estimated
combined cardinality exceeds the per-signal budget declared in
`${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`.

---

## Phase 4: Alert / SLO Wiring

**Goal:** If the signal is alert-relevant per `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`,
confirm that a paired alert rule and SLO are defined together. No
signal-without-monitoring.

**Inputs:**
- Signal classification from Phase 1.
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — list of alert-relevant signals,
  alert rule storage location, SLO definition location.

**Actions:**

1. Consult `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` to determine whether the signal
   is in the alert-relevant set. Examples of alert-relevant signals: error-rate
   counters, latency histograms used in SLI calculation, saturation gauges.
2. If the signal is alert-relevant:
   - Confirm an alert rule exists at the alert rule storage location defined in
     `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`, referencing this signal.
   - Confirm a paired SLO is defined at the SLO definition location defined in
     `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`, expressing the objective that the
     alert protects.
   - If either is missing, author both before proceeding. Do not author only one.
3. If the signal is NOT alert-relevant per the spec, no alert/SLO wiring is
   required and this phase exits without action.
4. MUST NOT introduce an alert rule without a paired SLO. MUST NOT introduce an
   SLO without the underlying signal and alert rule.

**Output:** For alert-relevant signals, a paired alert rule and SLO both exist
and reference the signal. For non-alert-relevant signals, this is explicitly
noted.

**Gate:** BLOCK if the signal is alert-relevant per the spec but the paired
alert rule or SLO is missing.

---

## Phase 5: Test Obligation

**Goal:** Confirm every observability signal introduced or modified by the
change has a corresponding test that exercises emit-call presence and label
correctness.

**Inputs:**
- Signal classification from Phase 1.
- Emit construction from Phase 2.
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — test runner and mock/stub conventions.
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — test obligation section, if
  present.

**Actions:**

1. For each signal classified in Phase 1, verify that at least one test exists
   that:
   - Confirms the canonical emit function is called when the observed event
     occurs.
   - Confirms all required labels/attributes/fields from Phase 2 are present on
     the emitted signal.
   - For metrics and spans, confirms that no forbidden high-cardinality label
     (per Phase 3) appears.
   - Confirms the emit is not called when the observed event does not occur.
2. Use the test framework and mock/stub patterns specified in
   `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`. Do not hard-code library-specific imports
   unless that library is named in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
3. Run the test command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` and confirm
   all observability-related tests are green.
4. Run the lint command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` and confirm
   zero errors.

**Output:** Passing tests covering every observability signal introduced or
modified, confirmed by the test runner.

**Gate:** BLOCK if any signal lacks a test for emit-call presence and required
label coverage. BLOCK if the test runner or lint command reports any error.

---

## Hard Rules

- MUST read `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` before Phase 1. Do not guess
  signal names, label sets, cardinality budgets, or canonical emit paths.
- MUST NOT emit to any path other than the canonical emit module defined in
  `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` for the signal's category.
- MUST NOT emit an unregistered signal name. Add it to the registry first.
- MUST NOT include secret-shaped values in any label, attribute, or field;
  cross-route to `secret-handling` Phase 3 if in doubt.
- MUST NOT use unbounded identifiers (raw user IDs, request IDs, free-text user
  input, full URL paths with embedded IDs) as metric labels or indexed span
  attributes.
- MUST NOT introduce an alert rule without a paired SLO, or an SLO without the
  underlying signal and alert rule.
- MUST NOT hard-code environment- or deployment-specific constants as label
  values unless `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` declares them required
  constants.
- MUST NOT guess test runner or lint commands — always read
  `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
- MUST NOT proceed to the commit-gate skill until all five phases are complete.

---

## Decision Gates Summary

| Gate         | Condition                                                                | Action if blocked                                                                  |
|--------------|--------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| Phase 1 exit | Unregistered signal name or signal name violates naming convention       | Register signal in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` under correct category; rename if needed |
| Phase 2 exit | Required label/attribute/field missing, or value carries secret-shaped data | Add missing field; cross-route to `secret-handling` Phase 3 for any secret risk     |
| Phase 3 exit | Unbounded label value domain, or estimated cardinality exceeds budget    | Demote unbounded value to span event or log field; tighten label set                |
| Phase 4 exit | Alert-relevant signal lacks paired alert rule or SLO                     | Author the missing alert rule and SLO together before proceeding                    |
| Phase 5 exit | Signal lacks emit-presence/label test, or test/lint fails                | Write missing test; fix lint errors                                                 |

---

## Interactions with other skills

- **`audit-emit` (parallel skill).** `audit-emit` governs the compliance event
  stream — discrete, durable, auditor-facing records routed through the canonical
  audit sink. `observability-emit` governs the operational telemetry stream —
  metrics, spans, logs, alerts, SLOs for runtime visibility and on-call response.
  The two streams are independent: a compliance-relevant action that also has
  operational significance MUST route through both skills (audit-emit for the
  audit record, observability-emit for the operational signal). Do not collapse
  one into the other. If a signal's purpose is ambiguous, classify it under
  `audit-emit` if the consumer is an auditor or compliance review, and under
  `observability-emit` if the consumer is an on-call engineer or capacity
  planner.

- **`secret-handling` Phase 3 (cross-route on Phase 2).** When Phase 2 of this
  skill encounters a label, attribute, or field whose value could carry
  secret-shaped data, control transfers to `secret-handling` Phase 3 for
  redaction or rejection. Return to this skill only after `secret-handling`
  clears the value or the value is removed.

- **`tdd` skill.** Phase 5 of this skill (Test Obligation) is satisfied via the
  test obligations declared by the `tdd` skill. Tests for observability signals
  follow the same TDD discipline as feature code: a failing test for the
  required emit must exist before the emit is implemented.

---

## Failure Modes

| Failure                                                  | Response                                                                       |
|----------------------------------------------------------|--------------------------------------------------------------------------------|
| `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` missing or unreadable            | Stop; surface gap to user; do not guess signal names, labels, or emit paths    |
| `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` missing or unreadable                    | Stop; surface gap; do not guess test or lint commands                          |
| Signal name not in registered set for its category       | Add signal to registry in `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` before emitting              |
| Required label missing from emit                         | Add label; re-read `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` for correct value source            |
| Label value carries secret-shaped data                   | Cross-route to `secret-handling` Phase 3; do not return until cleared          |
| Unbounded identifier used as metric label                | Demote to span event or log field; tighten the label set                       |
| Alert-relevant signal lacks paired alert rule or SLO     | Author the missing alert rule and SLO together before proceeding               |
| Alert rule authored without paired SLO (or vice versa)   | Treat as policy violation; author the missing artifact before commit            |
| No test for an observability signal                      | Write test before proceeding; do not mark obligation complete without evidence |

---

## Subagents Invoked

None. This skill operates entirely within the orchestrator context. Cross-routes
to `secret-handling` (Phase 2 of this skill) and to `commit-gate` (post-Phase 5)
are skill handoffs, not subagent dispatches.
