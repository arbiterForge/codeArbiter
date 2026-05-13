<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: observability-spec.md
-->

<!--PLACEHOLDER-->
<!-- Populated by decompose / context-creation skill, or backfilled when
     observability obligations first land. Template source:
     ${FRAMEWORK_ROOT}/.agents/skills/observability-emit/templates/observability-spec.md.tmpl -->

# Observability Specification

## Signal Categories

_The signal types this project emits. Common: metrics, traces (spans),
structured logs, alert rules, SLOs. Each category has its own
registration, naming, and label rules below._

| Category | Used? | Notes |
|---|---|---|
| metrics | _yes / no_ | |
| traces  | _yes / no_ | |
| logs    | _yes / no_ | |
| alerts  | _yes / no_ | |
| SLOs    | _yes / no_ | |

## Naming Conventions

_Per-category naming rules (prefix, separator, allowed characters)._

| Category | Convention | Example |
|---|---|---|
| _metric_ | _e.g. `<service>.<subsystem>.<event>`_ | |
| _span_   | _e.g. `<service>/<operation>`_ | |
| _log_    | _e.g. `<service>.<level>`_ | |

## Required Labels

_Labels / attributes every signal in each category MUST carry._

| Category | Required labels | Notes |
|---|---|---|
| metric | _e.g. `service`, `env`, `version`_ | |
| span   | _e.g. `service.name`, `trace_id`, `span_id`_ | |
| log    | _e.g. `service`, `level`, `trace_id`_ | |

## Cardinality Budgets

_Maximum allowed unique values per label, per category. Unbounded
labels (user_id, request_id) MUST NOT be used as metric labels._

| Label | Max cardinality | Notes |
|---|---|---|

## Canonical Emit Module / Function Paths

_Where the canonical emit functions live. observability-emit skill
Phase 2 requires emits go through these paths._

| Category | Module / Function | Notes |
|---|---|---|
| metric | _e.g. `obs.metrics.counter(name, labels)`_ | |
| span   | _e.g. `obs.tracer.start(name, attrs)`_ | |
| log    | _e.g. `obs.log.info(event, fields)`_ | |
| alert  | _alert rule storage location_ | |

## Alert Rule Storage Location

_Where alert rule definitions live (Prometheus rules file, Datadog
monitors-as-code, etc.). observability-emit Phase 4 verifies signal
has a paired alert when alerting-relevant._

## SLO Definitions

_Service-level objectives this project commits to. Each SLO names
the signal(s) it depends on so observability-emit Phase 4 can confirm
the wiring exists._

| SLO | Signal(s) | Target | Window |
|---|---|---|---|

## Fail-Closed Policy

_What happens when an observability emit fails (fire-and-forget vs.
fail the request). For audit events this is mandated by audit-spec.md;
for observability, choose per signal category._

## Test Obligation

_How observability emit must be tested per the observability-emit
skill Phase 5._
