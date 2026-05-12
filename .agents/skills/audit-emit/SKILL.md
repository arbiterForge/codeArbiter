# Skill: audit-emit

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill whenever code emits, should emit, or modifies the emission of
an auditable event. This skill MUST complete before any audit-related code is
committed.

Triggers:
- Code introduces a new action that falls within the auditable event set defined
  in `projectContext/audit-spec.md`
- An existing emit call is modified or removed
- A new API endpoint, data write path, or authentication step is added (all are
  presumptive audit obligations until Phase 1 rules otherwise)
- The `audit-emit` skill is referenced in the routing table

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `.agents/projectContext/audit-spec.md` is readable — stop if missing. This
   file is the authoritative source for action categories, required fields, sink
   routing, and fail-closed policy.
2. `.agents/projectContext/tech-stack.md` is readable — stop if missing.
3. Current stage is known — read `cat .agents/projectContext/stage`.

If any file is missing, surface the gap and stop. Do not guess at field names,
emit signatures, or routing targets.

---

## Phase 1: Action Classification

**Goal:** Identify the auditable action category for the code change and confirm
it is registered in the project's auditable event set.

**Inputs:**
- Description of the code change
- `.agents/projectContext/audit-spec.md` — authoritative auditable event set,
  action naming conventions, and category definitions

**Actions:**

1. Read `.agents/projectContext/audit-spec.md` in full.
2. Identify which action category from the auditable event set applies to the
   code change.
3. Confirm the action string follows the naming convention defined in
   `projectContext/audit-spec.md`. If the file specifies a `verb.noun` pattern
   (or another convention), enforce that pattern for all new action strings.
4. If the action is not present in the registered auditable event set, add it
   to the registry before using it. Do not emit an unregistered action name.
5. If the code change involves multiple distinct auditable actions, identify and
   register each one separately.

**Output:** Confirmed action classification with action string and registration
status (existing or newly added to registry).

**Gate:** BLOCK. No Phase 2 begins until every auditable action produced by the
change is classified and registered. Emitting an unregistered action name is a
policy violation.

---

## Phase 2: Emit Construction

**Goal:** Build a correct emit call with all required fields populated.

**Inputs:**
- Action classification from Phase 1
- `.agents/projectContext/audit-spec.md` — required always-present fields,
  action-conditional fields, and the emit function or module to call

**Actions:**

1. Read the emit function or module defined in `projectContext/audit-spec.md`.
   Use that function exclusively — do not construct a bare HTTP call, write
   directly to a logger, or invent an alternative emit path.
2. Populate all always-present fields defined in `projectContext/audit-spec.md`.
   These fields must appear on every audit event regardless of action type.
3. Populate all action-conditional fields applicable to the classified action.
   These are fields required only for specific action categories, as defined in
   `projectContext/audit-spec.md`.
4. Do not hard-code project-specific metadata values (such as a product name or
   environment identifier) unless `projectContext/audit-spec.md` specifies them
   as required constants. Use runtime-resolved values where the spec calls for
   dynamic fields.
5. Do not include fields that are not defined in `projectContext/audit-spec.md`.
   Undeclared fields create schema drift and complicate downstream consumers.

**Output:** Emit call constructed with all required fields, sourced from
`projectContext/audit-spec.md`.

**Gate:** BLOCK if any required always-present field is missing. BLOCK if any
required action-conditional field for the classified action is missing.

---

## Phase 3: Sink Routing

**Goal:** Confirm the emit call routes through the canonical audit module and
does not bypass it.

**Inputs:**
- Emit call from Phase 2
- `.agents/projectContext/audit-spec.md` — sink definition and routing rules
- `.agents/projectContext/trust-zones.md` — zone topology and crossing rules
  (if the project defines trust zones)

**Actions:**

1. Confirm the emit call invokes only the canonical audit module or function
   defined in `projectContext/audit-spec.md`.
2. MUST NOT route an audit event through a general-purpose logger, a bare HTTP
   client, a message queue client, or any path not designated as the canonical
   audit sink.
3. If the project defines trust zones in `projectContext/trust-zones.md`, confirm
   the emit call originates from a permitted zone and targets the audit sink's
   declared zone. Flag any undeclared zone crossing as a blocking finding.
4. If the code change involves multiple emit points, verify each one routes
   through the canonical sink.

**Output:** Confirmed that all emit calls route through the canonical audit
module defined in `projectContext/audit-spec.md`.

**Gate:** BLOCK if any emit bypasses the canonical sink. BLOCK if any undeclared
trust zone crossing is introduced.

---

## Phase 4: Fail-Closed Check

**Goal:** Confirm the emit failure behavior matches the policy for the current
project stage.

**Inputs:**
- `.agents/projectContext/stage` — current stage value
- `.agents/projectContext/audit-spec.md` — fail-closed policy section

**Actions:**

1. Read the current stage: `cat .agents/projectContext/stage`.
2. Read the fail-closed policy from `projectContext/audit-spec.md`. If the file
   defines a project-specific policy, enforce that. If the file is silent, apply
   the stage-based defaults below:

   | Stage | Minimum Fail Behavior                                             |
   |-------|-------------------------------------------------------------------|
   | 1     | Fire-and-forget acceptable; failed emit may be logged and dropped |
   | 2     | Fire-and-forget acceptable; failed emit must be logged            |
   | 3     | Failed emit MUST fail the originating request; no silent drop     |
   | 4     | Failed emit MUST fail the originating request; no silent drop     |

3. Inspect the code path surrounding each emit call. Confirm the error handling
   matches the required behavior for the current stage.
4. MUST NOT silently swallow an emit error at any stage. Even at Stage 1-2 where
   fire-and-forget is acceptable, the failure must be observable (logged or
   surfaced to a monitoring path).

**Output:** Confirmed that emit failure handling matches stage policy.

**Gate:** BLOCK if a failed emit is silently swallowed with no error path.
BLOCK at Stage 3+ if a failed emit does not fail the originating request.

---

## Phase 5: Test Obligation

**Goal:** Confirm every auditable action introduced or modified by the change
has a corresponding test.

**Inputs:**
- Action classification from Phase 1
- Emit construction from Phase 2
- `.agents/projectContext/tech-stack.md` — test runner and mock/stub conventions
- `.agents/projectContext/audit-spec.md` — test obligation section

**Actions:**

1. For each auditable action classified in Phase 1, verify that at least one
   test exists that:
   - Confirms the emit function is called when the action occurs
   - Confirms all required fields from Phase 2 are present in the emitted event
   - Confirms the emit is not called when the action does not occur
2. Use the test framework and mock/stub patterns specified in
   `projectContext/tech-stack.md`. Do not hard-code library-specific imports
   unless that library is named in `projectContext/tech-stack.md`.
3. For complex emit logic or multi-step action sequences, invoke the
   `audit-emitter` agent to review emit correctness before marking the
   obligation complete.
4. Run the test command specified in `projectContext/tech-stack.md` and confirm
   all audit-related tests are green.
5. Run the lint command specified in `projectContext/tech-stack.md` and confirm
   zero errors.

**Output:** Passing tests covering every auditable action, confirmed by the
test runner.

**Gate:** BLOCK if any auditable action lacks a test for emit call presence and
required field coverage. BLOCK if the test runner or lint command reports any
error.

---

## Decision Gates Summary

| Gate         | Condition                                                      | Action if blocked                    |
|--------------|----------------------------------------------------------------|--------------------------------------|
| Phase 1 exit | Unregistered action name used                                  | Register action before proceeding    |
| Phase 2 exit | Required always-present or action-conditional field missing    | Add missing field; re-read audit-spec |
| Phase 3 exit | Emit bypasses canonical sink or undeclared zone crossing       | Reroute through canonical sink       |
| Phase 4 exit | Emit failure silently swallowed, or Stage 3+ not fail-closed   | Fix error handling before continuing |
| Phase 5 exit | Auditable action lacks a test, or test/lint fails              | Write missing test; fix lint errors  |

---

## Hard Rules

- MUST read `projectContext/audit-spec.md` before Phase 1. Do not guess field
  names, action strings, or the emit function path.
- MUST NOT emit to any path other than the canonical audit module defined in
  `projectContext/audit-spec.md`.
- MUST NOT emit an unregistered action name. Add it to the registry first.
- MUST NOT silently swallow an emit error at any stage.
- MUST NOT hard-code project-specific metadata constants unless
  `projectContext/audit-spec.md` explicitly specifies them as required constants.
- MUST NOT bypass the `audit-emitter` agent review for complex audit logic.
- MUST NOT guess test runner or lint commands — always read
  `projectContext/tech-stack.md`.
- MUST NOT proceed to the commit-gate skill until all five phases are complete.

---

## Failure Modes

| Failure                                               | Response                                                              |
|-------------------------------------------------------|-----------------------------------------------------------------------|
| `audit-spec.md` missing or unreadable                 | Stop; surface gap to user; do not guess fields or emit path           |
| `tech-stack.md` missing or unreadable                 | Stop; surface gap; do not guess test or lint commands                 |
| Action not in auditable event set                     | Add action to registry before emitting; do not use unregistered name  |
| Required field missing from emit call                 | Add field; re-read `audit-spec.md` for correct value source           |
| Emit routes through logger or bare HTTP               | Reroute through canonical sink; flag as policy violation              |
| Emit error silently swallowed                         | Add error handling; Stage 3+ must fail the originating request        |
| No test for an auditable action                       | Write test before proceeding; do not mark obligation COVERED without evidence |
