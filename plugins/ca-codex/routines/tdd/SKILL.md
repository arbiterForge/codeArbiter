---
name: tdd
description: The test-first gate. Routed to by /feature (after the spec is approved), /fix, and /refactor before any implementation code is written. Six gated phases — obligation scan, red, green, obligation verify, coverage, lint. No feature code exists before Phase 1 clears; nothing reaches commit-gate until all six are green.
disable-model-invocation: true
---

# tdd

## Authoritative format boundary

For an HTML spec/plan pair, load [includes/artifacts.md](../../includes/artifacts.md) and use
the installed structured-artifact engine for artifact I/O. Verify the plan's
binding to the approved spec, use typed `index`, `outline`, and symbol-scoped `read`,
and follow contextual pages for the selected task. The workflow must not parse rendered HTML
for criteria, status, evidence, or authority. Missing or
invalid HTML capability is a STOP, not a fallback to Markdown. Existing
authoritative Markdown pairs continue through the legacy path. HTML `--farm`
dispatch remains blocked.


Test-first, or it does not ship. Routed to by `/feature` (after spec approval), `/fix`, and `/refactor`.

For a feature author, including a confirmed small-lane feature, the owning
coordinator selects task paths and obtains the current bounded map, provenance,
scoped command records and collector observations, applicable constraint
references, and host-effective instructions in native precedence order. Before
the author mutates or executes a discovered command, compose the fresh child
input with `_artifactpromptlib.compose_feature_actor_input` and send its
returned `input` to that child. Bind the actual approved spec and plan IDs
for full-lane work. For a confirmed small-lane feature, pass its mini-spec
text as `confirmed_mini_spec` and leave both artifact IDs absent; do not invent
a plan or bypass its existing gate. The packet
is an orientation aid with `requires_actor_check`, not admission. Recheck
worktree/source identity and resolve applicable critical constraints before a
material action. Missing optional map detail permits bounded read-only source
inspection, with full schema or document body read only when needed.
Apply `_contextselectlib.prepare_actor_delivery` to that selected packet for
the actual child, task, worktree and current source/host epochs. Send its
`delivery_text` when requested and count the attempt before the material
action; an unknown receipt or surviving session marker never proves delivery.
Re-select on resume, compaction, scope or worktree change, and report a blocked
delivery gap rather than assuming the child retained prior context.

For a fix or targeted test-only change, use the caller that already owns the
task. Before the author mutates or executes a discovered command, call
`_contextselectlib.compose_fix_or_test_actor_input` with the current scoped
sources, exact command cwd and collector evidence, then send its returned
`input` to that actor. Use `route='fix'`, `caller='fix'`, and the confirmed
bug-origin evidence and named regression for a fix. Use `route='test_change'`
with the existing `fix`, `feature`, or `refactor` caller for a test-only change;
do not create a feature spec pair merely to deliver context. The selected
caller retains its own approval and TDD gates. Reuse an actual bug-origin RED
when it already proves the named regression; for a targeted test change,
validate the test against the real defect or an honest fault fixture. Never
change production behavior merely to manufacture a failing test. If this
conflicts with a required TDD gate, surface the conflict to that gate's owner;
context delivery does not waive it. The packet remains reported evidence, not
task admission.

## Pre-flight

Read these, or STOP and surface the gap — never guess a command or a threshold:

- `<project-root>/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `<project-root>/.codearbiter/tech-stack.md` — test, coverage, and lint invocations; file layout; mock patterns.
- [includes/verification-boundary.md](../../includes/verification-boundary.md) — the required split between focused local proof and exhaustive exact-head hosted CI.
- `<project-root>/.codearbiter/coding-standards.md` — style, structure, naming. Required for Phase 3.
- For `/feature`, the authoritative approved spec. For HTML, read its typed
  criterion records through the installed engine and confirm the paired plan's
  exact binding; for legacy Markdown, read
  `<project-root>/.codearbiter/specs/<slug>.md`. It is the feature obligation
  source.
- For `/fix`, the bug-origin evidence: observed and expected behavior, the
  current expectation and its citations, supported cause, and the regression
  oracle with its cited evidence. If a validated debug handoff supplies these,
  recheck its source binding and freshness in the actual worktree and the
  original caller authority through the fix owner. A packet or its intent field
  does not authorize repair. Do not create a feature artifact to enter TDD.
- For `/refactor` backfill, the user-approved surface table and pre-existing
  parity evidence owned by `/refactor`. It does not require a feature spec.
- `<project-root>/.codearbiter/security-controls.md` — only when the change touches a security boundary (auth, crypto, secrets, a trust boundary). Optional; absent on most changes.
- `<project-root>/.codearbiter/code-map.md` — if present, a coarse concern→path→role map to orient before writing tests and code. Absent is fine — it is read-on-demand, populated by context-creation or commit-gate heal.

## Phase 1 — Obligation scan · gate: BLOCK

An **obligation** is one verifiable claim about the change: (a) a unique ID, (b) a source citation,
(c) a status. Status moves `OPEN → MAPPED → COVERED`; an obligation Phase 4 cannot tie to a passing
test is `MISSING`. "We should test X" is not an obligation.

Derive every obligation before any code is written, and record each as `ID · source · OPEN`:

- **Spec (`/feature`)** — one obligation per acceptance criterion in the approved spec. For
  HTML, cite the exact artifact ID and criterion ID returned by the engine;
  caller-supplied labels cannot manufacture obligations or widen the approved
  criterion set.
- **Bug-origin regression (`/fix`)** — one obligation for each scoped wrong
  behavior to repair. Cite the current expectation, observed defect and supported
  cause, regression oracle and evidence, and relevant source binding. A validated
  debug handoff supplies cited facts, not authority; derive these rows in the
  existing ledger. Do not invent a feature artifact such as a spec, plan, or
  mini-spec. The target regression must go red for the right reason before the
  minimum implementation. If the expectation is unresolved or the proposed
  behavior is new, stop and use the feature or decision owner.
- **Refactor parity (`/refactor` backfill)** — cite the approved surface table
  and the uncovered symbol or seam with its pre-existing behavior and parity
  evidence. Do not turn a refactor into a feature or a bug fix.
- **Contract** — API and input-validation invariants, error responses, boundary conditions.
- **Security** — only when `security-controls.md` applies: the assertion that the security-relevant boundary holds.

Gate: the obligation list is complete. For `/feature`, **auto-pass** when every obligation maps
one-to-one onto the acceptance criteria of an already-approved spec (full-lane spec or small-lane
mini-spec) — the user approved that list once; do not re-ask. **User review is required** only for
obligations derived BEYOND that spec (Contract and Security rows): surface just those additions.
For `/fix`, the scoped bug-origin regression follows the original caller's repair authority and
current evidence; the absence of a feature spec is not a block or permission to expand scope.
Review any proposed obligation beyond that supported correction under its actual owner. An ADR
remains a user-attributed decision through `/adr`; neither a handoff nor this ledger creates one.
For `/refactor`, retain its user-approved surface table and parity gates; backfill only the named
uncovered behavior or seam. The TDD checklist does not amend that table.
Under `/sprint`, spec-derived obligations auto-pass the same way and beyond-spec additions are
SMARTS-decided and logged like any other auto-decision. A partial list never passes either way.

## Phase 2 — Red · gate: BLOCK

Bind a failing test ID to each obligation and move that obligation `OPEN → MAPPED`.
Run the test command from `tech-stack.md`. For `/fix`, first assess an existing failing
test against target red: compare its assertion and regression oracle with the current
target failure and evidence. Name the existing test ID in the obligation ledger and
reuse that named existing target-red test when its oracle is adequate and it fails for
the target reason. Do not duplicate a test solely because of its age or because it
predates repair. Add tests only for uncovered obligations. Do not make a named target
failure green before observing and recording its red result.

- Every newly written test MUST fail, and fail **for the right reason** — the assertion, not an import error or a typo. A new test that passes with no implementation is wrong; fix it before continuing.
- Record unrelated existing failures in the baseline and report them; an unrelated failure is not target red. An import or setup error is not target red. Preserve each failure's identity and output. A newly broken pre-existing test is a conflict — stop and surface it.
- Required commit gates remain blocked while required checks fail. Do not skip tests, suppress failures, or waive gates to proceed.

Observe the target regression red on the broken source before repair or implementation. If a material fixture or setup change occurs after that observation, the earlier red no longer qualifies: repeat target red on the broken implementation with the changed fixture or setup before the minimum repair. For an intermittent or timing defect, prefer a faithful deterministic seam. If only repeated trials can exercise the mechanism, predeclare a finite trial bound and failure oracle; record the stochastic sample limit. Do not claim deterministic proof from a passing sample or retry until green. A failing trial must match the target mechanism, not merely fail intermittently.

Reject the standard traps: asserting on a mock instead of behavior; a test that can never fail; a
snapshot so broad it asserts nothing; coupling to an implementation detail instead of observable
behavior; asserting on the framework's behavior rather than your own.

The reasons to skip red are known. Hearing one is the tell that this gate is about to be waived —
never the license to waive it:

| excuse | reality |
|---|---|
| "Too simple to fail first." | Simple changes have the cheapest red tests — and "too simple to test" and "too simple to break" have never been the same claim. |
| "I'll write the test right after." | A test written after green has never been seen red: it is authored against the implementation it was meant to constrain, and its power to catch the bug is never demonstrated. |
| "The test would just restate the implementation." | Then it is aimed at the wrong seam — assert the observable behavior, not the wiring. A change with no observable behavior to assert is a design finding, not an exemption. |
| "The existing suite already covers this." | Then the failing test is impossible to write — try it. If it genuinely cannot go red, the obligation is already COVERED and Phase 4 records exactly that; if it goes red, the claim was wrong and you are holding the proof. |

Gate: the runner confirms each newly written test red for the right reason, or an
adequate named existing target-red test red for that reason, with every obligation
`MAPPED` to a failing test. Record unrelated existing failures separately; they
cannot count as target red or clear later required checks. No implementation code
is written until this gate clears.

## Phase 3 — Green · gate: BLOCK

Write the **minimum** implementation that satisfies the Phase 2 tests — no speculative logic, no
gold-plating — to the conventions in `coding-standards.md`. Run the impact-bounded local tests from
`verification-boundary.md`: the new regression plus affected pre-existing contracts. A broken
pre-existing test is a regression: fix it. Exhaustive and cross-platform suites run on exact-head
hosted CI before merge.

Gate: rerun the same named target test for fresh green on the repaired source, then rerun fresh affected-contract tests on that source. Record these results with the applicable coverage, lint, and type-check results; an old-head green is not repair proof. The applicable local suite is green, reached by satisfying the Phase 2 tests — not by weakening them. A test's
assertions MUST be unchanged between red and green; only fixtures and setup may move, and a material change to either requires renewed target red on the broken implementation before this green. A relaxed
assertion is a gate violation.

## Phase 4 — Obligation verify · gate: BLOCK

Walk the Phase 1 list item by item. Each `MAPPED` obligation moves to `COVERED` (a real passing test
that exercises the claim) or `MISSING` (no test truly covers it). For security-relevant or
contract-critical logic, dispatch the `coverage-auditor` agent
([agents/coverage-auditor.md](../../agents/coverage-auditor.md)) to confirm the tests exercise the claim.

A `MISSING` obligation returns the workflow to Phase 2 — author a correct failing test, then re-run
Phase 3 — and loops until it is `COVERED`.

**Stakes:** when you block on a `MISSING` obligation, state what the untested seam leaves exposed, not
just that it is `MISSING` — one line naming the consequence: "this error path is untested; a 500 here
would reach users silently." The block is the rule; the stakes are why it is worth the friction.

Gate: every obligation `COVERED`, each backed by a passing test. Any `MISSING` blocks Phase 5.

## Phase 5 — Coverage · gate: BLOCK

Coverage scales with the maturity value (`stage:` in `CONTEXT.md`) — a rigor knob, not a promotion
gate. The threshold table is the shared [includes/maturity-coverage.md](../../includes/maturity-coverage.md) (the
single source of truth, also used by `refactor` Phase 2).

Resolve the surface's **declared coverage profile** from `tech-stack.md` against
[includes/maturity-coverage.md](../../includes/maturity-coverage.md), then run its coverage command.
Every required metric must clear the maturity threshold. Apply the shared
profile-selection, report-validity and critical-path evidence requirements;
do not substitute metrics or treat an unmeasured metric as passed. Below the
floor on any required metric → add meaningful tests until it is met.

**Name the host you measured on**, and for a tree `tech-stack.md` marks as platform-forked, the
figure is the UNION across its supported hosts — a single-host report scores the other platform's
arm as permanently uncovered (issue #521, conditions in [includes/maturity-coverage.md](../../includes/maturity-coverage.md)).
Where only one host is available, say so and name what is missing rather than quoting it as the
whole.

Where the surface has no coverage tooling at all, take the no-tooling exemption in
[includes/maturity-coverage.md](../../includes/maturity-coverage.md) — which requires QUOTING the `tech-stack.md`
Coverage section that omits a command for this surface — and pass the phase on the Phase 4
obligation verify alone. Without that citation the phase STOPs: "I could not find the command" and
"this surface has none" look identical from here and demand opposite responses. Do NOT invent a
command, and do NOT silently skip the phase as though it had been run — a gate that cannot execute
still reads as satisfied, which is worse than an absent one.

**Stakes:** when coverage blocks below threshold, name the class of code left dark — the paths a later
regression could rot unnoticed — not just "below threshold." The number is the rule; the untested paths
are why it matters.

Gate: threshold met on every required metric in the declared coverage profile
for the current maturity value, with the shared critical-path evidence, or the no-tooling
exemption taken WITH its citation and Phase 4 proof. A test added only to move the percentage fails this gate in
spirit — it converts an honest red into a green that asserts nothing.

## Phase 6 — Lint · gate: BLOCK

Run lint, and the type-check if the project is statically typed, from `tech-stack.md`. Resolve every
error.

Gate: clean lint and type-check, zero errors — this is what clears the path to `commit-gate`.
"Mostly passes" is not passing.

## Hard rules

- MUST NOT skip, suppress, or comment out a test to clear any gate.
- MUST NOT mark an obligation `COVERED` without a passing test that exercises the claim.
- MUST NOT lower a coverage threshold without a decision recorded in `CONTEXT.md`.
- MUST NOT inline-suppress a lint rule without a written reason, and never to bypass a security-relevant rule.
- MUST NOT guess the test, coverage, or lint command — read `tech-stack.md` or STOP.
- MUST, at exit, run the follow-up harvest ([includes/harvest.md](../../includes/harvest.md)) over any `[NEEDS-TRIAGE]` raised this run — batch-confirm promoting work to `open-tasks.md` and decisions to `open-questions.md` so nothing languishes; nothing auto-promotes interactively.
