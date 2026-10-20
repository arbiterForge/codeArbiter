---
name: refactor
description: "Restructure code without changing observable behavior: rename, extract, inline, move, deduplicate, or replace an internal implementation with an equivalent one. Prove parity through unchanged pre-existing tests. Not for new behavior, bug fixes, explanation-only questions, or committing finished work."
argument-hint: "<surface and motivation>"
---

# refactor

Select this owning procedure for a behavior-preserving restructure, whether requested
in plain language or through `/refactor`. Entry syntax is not an additional gate;
the authorized scope, parity, and verification requirements below still apply.
Externally observable behavior before equals after, proven rather than assumed.

## Entry boundaries

- Identify both the surface and the motivation. Phase 1 owns the precise surface
  table under existing authorization. Ask only about a missing consequential scope decision.
- New behavior, including a new error path, side effect, or public method beyond
  a Phase 3 seam, belongs to `/feature`. Incorrect existing behavior belongs to `/fix`.
- An explanation-only question stays in the non-mutating question-answer path,
  not this editing procedure and not a required help-command detour.
- Persisting an already-completed refactor belongs to the existing commit owner at
  `<plugin-root>/routines/commit-gate/SKILL.md`, with its actual authorization and gates.
  No commit, push, or PR is implied merely by entering this refactor procedure.

## Pre-flight

Read these, or STOP and surface the gap — never guess a command or a threshold:

- `<project-root>/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `<project-root>/.codearbiter/tech-stack.md` — the test, coverage, lint, and type-check invocations; file layout.
- `<plugin-root>/includes/verification-boundary.md` — the required split between focused local parity proof and exhaustive exact-head hosted CI.
- `<project-root>/.codearbiter/coding-standards.md` — style, structure, naming. Required for Phase 4.

The working tree MUST be clean over the named surface before Phase 1. A dirty surface conflates the refactor diff with unrelated edits and breaks parity verification — STOP and surface it.

## Phase 1 — Surface identification · gate: BLOCK

Inspect the requested refactor and record its precise surface before restructuring.
Present the table and continue when the existing request covers it; no second
signoff is required. Ask only about a genuinely unresolved scope or outcome:

- Files (repo-relative paths).
- Top-level symbols touched — function, class, and exported member names.
- Public method signatures within those symbols.
- External consumers — call sites in other modules.

Reject vague surfaces. "the auth module", "the user service", "some helpers in utils" are categories, not surfaces. A surface is acceptable only when a reader could grep the repo for the listed symbols and arrive at the same file set. The table is the parity contract for Phases 2–6.

Gate: a precise, complete surface table covered by existing user authorization.
Resolve category-level requests through source inspection where their outcome is
clear. Ask only when inspection exposes a consequential missing choice. Include
necessary consumer updates within the requested restructure and record their scope.

## Phase 2 — Behavioral parity coverage proof · gate: BLOCK

Prove pre-existing tests already exercise the named surface well enough to detect a behavior change, before any production code is touched. Locate every test that exercises a symbol in the surface table. Run the coverage command from `tech-stack.md` scoped to the surface files; record each metric required by the declared coverage profile and the per-symbol test evidence.

Coverage scales with the maturity value (`stage:` in `CONTEXT.md`) — the same knob as `tdd` Phase 5,
using the shared threshold table `<plugin-root>/includes/maturity-coverage.md`.

Every public method in the surface table MUST have at least one direct test — transitive coverage through a higher-level integration test does not count. A public method with zero direct tests is uncovered for this gate.

Resolve the **declared coverage profile** from `tech-stack.md` against the shared
`maturity-coverage.md` rule. Every required metric must clear the threshold, and
the shared report-validity and critical-path evidence requirements must hold.
Keep the same profile, scope and required metrics before and after the refactor.
Where the surface has no coverage tooling, take the no-tooling exemption in
`<plugin-root>/includes/maturity-coverage.md` — it requires QUOTING the `tech-stack.md` Coverage
section that omits a command for this surface — and the per-symbol direct-test proof stands alone.
Without that citation the phase STOPs rather than passing on an unverifiable claim.

If surface coverage is below the maturity threshold on any required metric, or a public method has no direct test, use the characterization/backfill approach in `<plugin-root>/routines/tdd/SKILL.md`. Add tests for the existing behavior and run them before restructuring; initially passing tests establish the baseline. Use a meaningful isolated negative control where needed to check the oracle. Record the passing post-backfill baseline, including test identities and assertions. Resume with that measured coverage and preserve the baseline assertions through implementation.

Gate: surface coverage at or above the maturity threshold on every required metric in the declared coverage profile, the shared critical-path evidence present, AND every public method backed by a direct test. Otherwise backfill via `tdd` Phase 1 before retrying.

## Phase 3 — Red parity tests (conditional) · gate: BLOCK

Pin any new test seam the refactor exposes before implementation. A new seam is one of: a newly exported symbol that did not exist; a new public method signature on an existing class; a previously private function promoted to module-public.

If the refactor exposes no new seam, record "No new seams" and skip to Phase 4. Otherwise, for each seam write one or more tests that pin its contract. These tests MUST be red before implementation, and every pre-existing test MUST stay green. A seam test is scoped strictly to the restructure — it MUST NOT require behavior beyond what the original code already produced. A seam test that needs new behavior to pass means the work is a feature: route it to `tdd` and abort.

Gate: either "No new seams", or failing seam tests with all pre-existing tests still green. BLOCK if a proposed seam test requires new behavior, or if any pre-existing test breaks as a side effect of writing the seam tests.

## Phase 4 — Implementation · gate: BLOCK

**Strategy choice (conditional).** Only when materially distinct restructuring strategies exist (for
example, extract-and-delegate versus move-and-rename), and only after the Phase 1 surface table and
the Phase 2 parity proof are settled, run a SMARTS comparison per
`<plugin-root>/includes/smarts/core.md` inline to choose between them. The choice never widens the
surface table or relaxes a parity or coverage gate. One evident strategy gets no SMARTS table.

Apply the restructure with zero behavior change, to the conventions in `coding-standards.md`. Confine every edit to the surface table. Acceptable edits: rename symbols (with consumer updates); extract or inline functions and methods; move symbols between files; replace an internal implementation with an equivalent one; collapse or split modules where the public interface is preserved.

Unacceptable inside a refactor: adding a behavior, branch, error path, or side effect; changing the value any public method returns for any pre-existing input; adding a public method beyond a Phase 3 seam; changing observable order of operations (event emission, logging, IO). Classify the resulting staged diff against `commit-gate` classification criteria — a diff that classifies as `feat` is not a refactor; halt and route to `tdd`.

Gate: the refactor remains within the authorized outcome, with any Phase 3 seam
tests now green. Maintain the surface table for discovered consumer updates within
that scope. BLOCK if the diff classifies as `feat` or requires a scope expansion
without the actual owner's authorization.

## Phase 5 — Parity verification · gate: BLOCK

Run the impact-bounded parity tests recorded in the post-backfill Phase 2 baseline,
following `verification-boundary.md`. Compare test changes made during implementation
against that baseline, including characterization cases added to existing test files.
Preserve their assertions. Necessary import or symbol-reference updates must retain
the same behavioral oracle. If implementation requires changing an expected result,
resolve the behavior change through the feature or fix owner. Phase 3 seam tests
must also pass. Record current results and any permitted mechanical test changes.

Gate: baseline parity and new seam checks pass with preserved behavioral assertions.
The exhaustive pre-existing suite remains an exact-head hosted-CI merge requirement.

## Phase 6 — Lint and coverage · gate: BLOCK

Run lint, the type-check if the project is statically typed, and coverage, all from `tech-stack.md`. Resolve every lint and type error. Confirm surface coverage remains at or above the maturity threshold on every required metric in the same declared coverage profile. A refactor MUST NOT reduce coverage of the surface it touched on any required metric or drop its critical-path evidence.

Where the surface has no coverage tooling, the same clause as Phase 2 applies — the no-tooling exemption in `<plugin-root>/includes/maturity-coverage.md`, citation included — and parity is verified through Phase 5's post-backfill baseline and preserved behavioral assertions. Phase 2 and Phase 6 MUST NOT give different answers about the same surface, which is why both defer to the one shared clause rather than restating its conditions.

Gate: clean lint and type-check, zero errors, and no coverage regression on the named surface. "Mostly passes" is not passing — this is what clears the path to `commit-gate`.

## Hard rules

- MUST identify the precise surface and existing authorization before Phase 2; do not request duplicate signoff.
- MUST NOT proceed past Phase 2 if surface coverage is below the maturity threshold or any public method has zero direct tests — route to `tdd` Phase 1 to backfill.
- MUST NOT introduce new behavior in Phase 4. A diff that classifies as `feat` under `commit-gate` is not a refactor.
- MUST NOT weaken a baseline assertion to make the refactor pass. Mechanical test-reference changes must preserve the behavioral oracle.
- MUST NOT reduce coverage of the named surface during the refactor.
- MUST keep the surface table current and obtain authorization for a material scope expansion or changed outcome.
- MUST NOT inline-suppress a lint rule to clear Phase 6, and never to bypass a security-relevant rule.
- MUST NOT guess the test, coverage, lint, or type-check command — read `tech-stack.md` or STOP.
