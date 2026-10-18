---
name: tdd
description: Verify authorized feature, fix, and refactor work with scoped obligations, regression-first fixes, behavioral checks, characterization baselines, coverage, and lint.
disable-model-invocation: true
---

# tdd

Select the verification approach before changing code. Keep the intended behavior,
observed results, and pending checks explicit throughout implementation.

## Pre-flight

Use the selected specification or inline criteria for a feature, the observed defect
and expected behavior for a fix, and the agreed surface plus existing behavior for a
refactor. Read applicable project instructions and the test, coverage, and lint
commands in `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md`. Follow
`${CLAUDE_PLUGIN_ROOT}/includes/verification-boundary.md` for local versus hosted checks.
Read security controls when the affected behavior crosses a security boundary.
Use `.codearbiter/code-map.md` on demand for source orientation when present.

For artifact I/O, load `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md`. Use the selected
spec/plan identities and typed criterion records for HTML. Direct implementation
reads the same relevant inputs; it does not require a child or delivery receipt.

For actual delegation, send bounded context to the named actor. Feature actors use
`_artifactpromptlib.compose_feature_actor_input`; fix and test-only actors use
`_contextselectlib.compose_fix_or_test_actor_input`. Bind the actual task paths,
commands and cwd, applicable constraints, and effective instructions. A small-lane
feature supplies `confirmed_mini_spec` with absent spec/plan IDs. A fix supplies
`route='fix'`, `caller='fix'`, bug-origin evidence and the named regression. Test-only
work uses `route='test_change'` under its existing feature, fix, or refactor caller.
Use `required_refs` for particular task-critical inputs. Missing optional map or
provenance information permits focused source inspection.

`_contextselectlib.prepare_actor_delivery` can prepare the actor's bounded input.
Send the returned delivery text when requested and retain observed delivery facts.
An advisory delivery result needs no further retry. Re-select after a material
source, scope or worktree change. Resolve actual critical missing or conflicting
inputs before the affected action, and preserve host permissions.

## Phase 1 — Obligations and verification approach

Record each required claim with an ID, its source, and its proving check. Include
applicable contract and security boundaries. Retain the existing feature criteria,
fix expectation, or refactor surface; ask only about a consequential missing choice.

| Work | Evidence required |
|---|---|
| Confirmed fix | Observe a named regression failing for the defect before repair, then passing after repair. Reuse an adequate current bug-origin RED. |
| Feature | Prefer test-first behavior checks. Existing implementation can be verified through current criterion-focused tests and meaningful negative controls where needed; report the observed sequence accurately. |
| Refactor or coverage backfill | Run characterization tests against existing behavior before restructuring. An initially passing test is a valid baseline. Preserve that baseline and its assertions through the refactor. |
| Documentation or non-executable change | Use the relevant reference, generation, schema, or rendering validation. Mark test and coverage phases inapplicable with the concrete reason. |

Each obligation moves `OPEN → MAPPED → COVERED`; a claim without adequate evidence
remains `MISSING`. Declare the approach and needed checks up front. Record only
observed results, including failures, skips, and unavailable checks.

## Phase 2 — Establish the baseline

Run the selected checks and read their output. For a confirmed fix, verify that the
named regression fails for the target assertion, not an import, setup, or unrelated
error. Reuse a suitable existing test rather than duplicating it. Add tests for
uncovered behavior. Keep unrelated baseline failures separately identified.

For test-first feature work, observe the intended missing behavior before adding
it. For characterization, observe the existing behavior passing. A negative control
or isolated fault fixture can establish that a test detects a relevant deviation;
do not alter correct production behavior merely to obtain a failure.

For timing defects, prefer a deterministic seam. When repeated trials are necessary,
state a finite trial bound and failure oracle before running them. Report sample
limits; a passing sample is not deterministic proof.

Proceed when the selected baseline supports the intended change. A confirmed fix
requires its genuine target RED. Missing characterization coverage requires useful
baseline tests before restructuring. Never weaken assertions or suppress failures.

## Phase 3 — Implement and check

Implement the scoped change using project conventions. Run the proving checks on
the resulting source, followed by affected pre-existing contracts. Repair regressions
and retain failed results until superseded by an actual rerun.

For a regression-first fix, run the same named test for fresh GREEN. Keep its
assertions unchanged between RED and GREEN. A material fixture or setup change
requires renewed target RED against the broken source before claiming that sequence.
For refactors, preserve the behavior and baseline test assertions.

## Phase 4 — Verify obligations

Match each obligation to evidence that exercises its claim. Mark it `COVERED` only
when the applicable check passed. An unexplained failure or untested requirement
remains `MISSING`; repair the affected work and rerun its checks. Reuse current
results when the relevant source and inputs are unchanged.

Review the combined change at the scope its risks warrant. Use `coverage-auditor`
(`${CLAUDE_PLUGIN_ROOT}/agents/coverage-auditor.md`) for an independently required review of security or contract-critical behavior.
State exactly what the evidence proves and what remains unknown.

## Phase 5 — Coverage

Apply `${CLAUDE_PLUGIN_ROOT}/includes/maturity-coverage.md` using the project's declared
coverage profile and maturity stage. Run the owning coverage command for the affected
surface; every required metric must meet its threshold and critical-path evidence
requirements. Keep production scope, exclusions, and metrics unchanged unless the
user has authorized a policy change.

Name the measurement host and retain the supported host union for platform-forked
trees. An unavailable host remains unmeasured. When the surface has no coverage
tooling, cite its `tech-stack.md` Coverage declaration and use the shared no-tooling
rule with the Phase 4 evidence. Never invent a command or treat unmeasured coverage
as passing.

## Phase 6 — Lint and handoff

Run applicable lint and type checks from the project command guide. Resolve errors.
Return the scoped obligations, selected verification approach, actual command/cwd
and outcomes, and any pending checks to the caller. The commit owner evaluates this
evidence for the selected staged changes; it does not require a different historical
test sequence from the one appropriate to the work.

Preserve failures and actual user stops. Do not skip tests, lower coverage thresholds,
or suppress security checks to obtain a pass. Use `${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`
for genuine out-of-scope findings. Completion reports must distinguish implementation,
verification, review, and release.
