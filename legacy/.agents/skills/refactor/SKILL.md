---
name: refactor
description: Restructure existing code without changing behavior. Six-phase gated workflow that proves behavioral parity through pre-existing test coverage, blocks any change classifiable as `feat`, and refuses to accept modified tests as evidence of correctness.
---

<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: SKILL.md
-->


# Skill: refactor

## Purpose

The `refactor` skill governs any change whose stated intent is to restructure code
without altering behavior — renaming, extracting, inlining, splitting modules,
collapsing duplication, or replacing internal implementations behind unchanged
interfaces. It enforces a single invariant: the externally observable behavior of
the named surface before the refactor is identical to the externally observable
behavior after. Every gate in this skill exists to verify that invariant by
mechanical means rather than by inspection. A refactor that cannot demonstrate
parity through unmodified pre-existing tests is not a refactor — it is a feature
change in disguise and MUST be routed back through the `tdd` skill.

---

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

- User invokes `/refactor` (when wired) or otherwise requests a behavior-preserving
  restructure (rename, extract function/class, inline, move, deduplicate, replace
  internal implementation)
- The routing table in `AGENTS.md` §5 lists "refactor" as the primary route for
  the cue
- A `tdd` Phase 1 obligation scan determines that the planned change introduces
  no new obligations and the user confirms intent is restructure-only
- A `commit-gate` Phase 3 classification of a staged change set returns `refactor`
  and there is no prior gated workflow for that change set

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` is readable — stop if missing.
2. `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` is readable — stop if missing.
3. `${PROJECT_ROOT}/.agents/projectContext/stage` exists and the current stage is known —
   `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.
4. A test runner, lint command, and coverage command are documented in
   `tech-stack.md`. If any of the three is undocumented, stop and surface the gap.
5. The working tree is clean (no unstaged changes overlapping the named surface).
   A dirty surface conflates the refactor diff with unrelated edits and breaks
   parity verification.

If any pre-flight check fails, stop and surface the gap. Do not guess thresholds
or commands.

---

## Phase 1: Surface Identification

**Goal:** Enumerate the exact files, functions, classes, and public method
signatures that fall within the refactor's blast radius before any other work
begins.

**Inputs:**
- The user's description of the planned restructure
- The current working tree

**Actions:**

1. Restate the planned refactor in one sentence and confirm it back to the user.
2. List the exact surface as a structured table:
   - Files (absolute or repo-relative paths)
   - Top-level symbols touched (function names, class names, exported members)
   - Public method signatures within those symbols
   - External consumers of any public symbol (call sites in other modules)
3. Reject vague surfaces. Examples of unacceptable surface descriptions:
   - "the auth module"
   - "the user service"
   - "some helpers in utils"
   A surface is acceptable only when a reader could grep the repo for the exact
   listed symbols and arrive at the same file set.
4. Record the surface table. It becomes the parity contract for Phases 2–5.

**Output:** A surface table with files, symbols, public signatures, and external
consumers, signed off by the user.

**Gate:** BLOCK if the surface is vague, incomplete, or describes a category
rather than a list. "The auth module" is not a surface — "the functions
`signToken`, `verifyToken`, and `rotateKey` in `src/auth/tokens.ts`" is.

---

## Phase 2: Behavioral Parity Coverage Proof

**Goal:** Prove that pre-existing tests already exercise the named surface
sufficiently to detect a behavior change, before any production code is touched.

**Inputs:**
- The surface table from Phase 1
- The test runner and coverage command from `tech-stack.md`
- The stage value from Pre-Flight

**Actions:**

1. Locate every test file that exercises any symbol in the surface table.
2. Run the coverage command scoped to the surface files. Record line, branch,
   and per-symbol coverage.
3. Look up the stage's minimum coverage threshold (same table as `tdd` Phase 5):

   | Stage | Minimum Coverage |
   |-------|------------------|
   | 1     | >= 60%           |
   | 2     | >= 70%           |
   | 3     | >= 85%           |
   | 4     | >= 90%           |

4. For each public method listed in the surface table, confirm it has at least
   one direct test (not merely transitive coverage through a higher-level
   integration test). A public method with zero direct tests is uncovered for
   the purposes of this gate.
5. If coverage of the named surface is below the stage threshold, OR any public
   method has zero direct tests, halt and route to the `tdd` skill Phase 1 to
   backfill obligations and tests. Resume Phase 2 only after the backfill is
   green.

**Output:** A parity coverage report citing the stage threshold, measured
coverage of the named surface, and a per-public-method test inventory. All
entries marked COVERED.

**Gate:** BLOCK if coverage of the named surface is below the stage threshold
OR if any public method in the surface table has zero direct tests. Backfill
via `tdd` Phase 1 before retrying.

---

## Phase 3: Red Parity Tests (conditional)

**Goal:** When the refactor exposes a new test seam — for example, extracting an
internal helper into a new exported function with its own public signature —
write failing tests for that seam before implementation.

**Inputs:**
- The surface table from Phase 1
- The parity coverage report from Phase 2

**Actions:**

1. Inspect the planned refactor against the surface table. If the refactor will
   produce any of the following, treat each as a new test seam:
   - A newly exported symbol that did not exist before
   - A new public method signature on an existing class
   - A previously private function being promoted to module-public
2. If no new test seams are exposed, skip the remaining actions and record
   "No new seams" as the Phase 3 output.
3. For each new seam, write one or more failing tests that pin the seam's
   contract. These tests MUST fail before implementation begins.
4. Run the test suite. The new seam tests MUST be red. All pre-existing tests
   MUST remain green.
5. New seam tests are scoped strictly to surface restructure — not to introduce
   behavior beyond what the original code already produced. If a proposed seam
   test would require new behavior to pass, the change is not a refactor —
   route it to `tdd` and abort.

**Output:** Either "No new seams" or a set of failing seam tests with
pre-existing tests still green.

**Gate:** BLOCK if a proposed seam test would require new behavior to pass.
BLOCK if any pre-existing test fails as a side effect of writing the new seam
tests. A new-behavior seam test is a feature, not a refactor.

---

## Phase 4: Implementation

**Goal:** Apply the restructure with zero behavior change.

**Inputs:**
- The surface table from Phase 1
- The parity coverage report from Phase 2
- Any seam tests from Phase 3
- `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md`

**Actions:**

1. Read `coding-standards.md` before editing.
2. Apply the refactor mechanically within the surface table. Acceptable edits:
   - Rename symbols (with consumer updates)
   - Extract functions or methods
   - Inline functions or methods
   - Move symbols between files
   - Replace internal implementation with an equivalent one
   - Collapse or split modules where the public interface is preserved
3. Unacceptable edits inside a refactor:
   - Adding a new behavior, branch, error path, or side effect
   - Changing the value returned by any public method for any pre-existing input
   - Adding a new public method beyond a Phase 3 seam
   - Changing observable order of operations (event emission, logging, IO)
4. Mentally classify the resulting staged diff using `commit-gate` Phase 3
   criteria. If the diff would classify as `feat`, the change is not a refactor
   — halt and route to `tdd`.

**Output:** Applied refactor confined to the surface table, with Phase 3 seam
tests (if any) now green.

**Gate:** BLOCK if the diff would classify as `feat` under `commit-gate` Phase 3.
BLOCK if any edit falls outside the surface table from Phase 1 without an
explicit user-approved surface amendment.

---

## Phase 5: Parity Verification

**Goal:** Demonstrate that the pre-existing test suite — without modification —
still passes after the refactor.

**Inputs:**
- The full project test suite
- The parity coverage report from Phase 2 (list of pre-existing tests)
- The git diff of staged changes

**Actions:**

1. Run the full project test suite using the command from `tech-stack.md`.
2. Every pre-existing test identified in Phase 2 MUST pass with NO modification
   to its source. Inspect the diff and confirm zero edits to any pre-existing
   test file.
3. A modified pre-existing test is, by definition, evidence that the surface's
   observable behavior changed. A modified test MUST be reverted; if the test
   cannot pass after revert, the refactor introduced a behavior change and
   MUST be routed to `tdd` as a feature or fix.
4. New seam tests written in Phase 3 (if any) MUST pass.
5. Record the pass/fail tally and any modified-test detection in the parity
   verification report.

**Output:** Full test suite green with zero pre-existing tests modified.

**Gate:** BLOCK if any pre-existing test was modified to pass. A modified test
is a behavior change, not a refactor. BLOCK if any test in the suite fails.

---

## Phase 6: Lint/Coverage Gate

**Goal:** Confirm style, type-check, and coverage all clear — mirroring the
exit conditions of `tdd` Phase 5 and Phase 6.

**Inputs:**
- `tech-stack.md` — lint, type-check, and coverage commands
- `${PROJECT_ROOT}/.agents/projectContext/stage` — for the coverage threshold

**Actions:**

1. Run the lint command from `tech-stack.md`. Zero errors permitted. Warnings
   that escalate to errors under the project's configuration must be resolved.
2. Run the type-check command (if the project uses static typing). Zero errors
   permitted.
3. Run the coverage command. Confirm coverage of the named surface remains at or
   above the stage threshold. A refactor MUST NOT reduce coverage of the surface
   it touches.
4. MUST NOT inline-suppress a lint rule to clear this gate. If a genuine
   suppression is required, it requires a comment justifying it and must not
   bypass a security-relevant rule.

**Output:** Lint, type-check, and coverage outputs all clean. Surface coverage
unchanged or improved relative to Phase 2 baseline.

**Gate:** BLOCK on any lint error, type error, or coverage regression on the
named surface. Coverage MUST NOT decrease as a side effect of restructure.

---

## Hard Rules

- MUST NOT begin Phase 2 without a precise surface table from Phase 1.
- MUST NOT proceed past Phase 2 if any public method in the surface table has
  zero direct tests.
- MUST NOT proceed past Phase 2 if surface coverage is below the stage threshold;
  route to `tdd` Phase 1 to backfill.
- MUST NOT introduce new behavior in Phase 4. A change whose `commit-gate`
  Phase 3 classification would be `feat` is not a refactor.
- MUST NOT modify any pre-existing test to make it pass. A modified test is a
  behavior change.
- MUST NOT reduce coverage of the named surface during the refactor.
- MUST NOT extend the refactor's surface mid-flight without an explicit
  user-approved amendment to the Phase 1 surface table.
- MUST NOT inline-suppress lint rules to clear Phase 6.
- MUST NOT guess test runner, lint, or coverage commands — always read
  `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.

---

## Decision Gates Summary

| Gate         | Condition                                                                       | Action if blocked                                       |
|--------------|---------------------------------------------------------------------------------|---------------------------------------------------------|
| Phase 1 exit | Surface vague, incomplete, or describes a category rather than named symbols    | Stop; require user to name files and symbols precisely  |
| Phase 2 exit | Surface coverage below stage threshold, or any public method has zero direct tests | Halt; route to `tdd` Phase 1 to backfill obligations |
| Phase 3 exit | Proposed seam test requires new behavior, or pre-existing tests broke           | Stop; route to `tdd` — change is a feature              |
| Phase 4 exit | Diff would classify as `feat` under `commit-gate` Phase 3                       | Stop; route to `tdd` — change is a feature              |
| Phase 5 exit | Any pre-existing test modified, or any test fails                               | Stop; revert test edits; if tests cannot pass, route to `tdd` |
| Phase 6 exit | Lint error, type error, or coverage regression on named surface                 | Stop; fix without inline suppression                    |

---

## Interactions with other skills

**`tdd` skill (Phase 1 backfill).** When Phase 2 of `refactor` finds that the
named surface lacks sufficient coverage — either total coverage below the stage
threshold or any public method with zero direct tests — `refactor` halts and
routes to `tdd` Phase 1 to write obligations and red tests for the uncovered
surface. Only after `tdd` returns with green tests does `refactor` resume at
Phase 2 to re-verify parity coverage. The handoff also applies in Phase 3 when
a proposed seam test would require new behavior, and in Phase 4/5 whenever a
detected behavior change reveals the work is a feature, not a restructure.

**`commit-gate` skill (classification).** `refactor` Phase 4 explicitly mirrors
`commit-gate` Phase 3 classification criteria. The implementation gate uses the
`commit-gate` rubric to verify the staged diff would classify as `refactor`
rather than `feat`. When all six `refactor` phases pass, the resulting commit
is routed through `commit-gate` like any other change; `commit-gate` Phase 3
must classify the diff as `refactor`, and `commit-gate` Phase 4 verification
gates (test, lint, secrets) run against the already-green state produced here.
A divergence — for example, `commit-gate` classifying as `feat` after
`refactor` produced a green Phase 4 — is a hard contradiction and MUST be
surfaced via `/surface-conflict`.
