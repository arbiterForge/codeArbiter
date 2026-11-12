# Program charter and completion contract

## Authority and currentness

Repository: `arbiterForge/codeArbiter`. Audit baseline: `fd7eb34b2da439551443d09526ab48fd1d1bb9bf` on `main`. The full audit identifies 287 machine families, 1,748 transition rows and 70 finding/boundary records. Those are analytical counts, not advertised product feature counts or proof of every possible interleaving.

The current handoff rechecked live main and found the same commit. Source-derived findings remain bound to that exact source; prior bounded probe results were retained, not misrepresented as a new installed-host campaign. Current Release/tag observations are in `evidence/live-github-observations.json` and `evidence/release-tag-bindings.json`. Exact distributed bytes remain unqualified by this handoff.

The attached Project portfolio remains bound to `60bd988faae481a26d51ee812d4659eb6baef7ce`; the later claim registry includes `9496cff6332fe0b97195b7ebe67b73f62f30e5b3` and October 7 migration/approval expectations. These are historical context. The accepted assistive direction and current implementation take precedence for current behavior; preserve the historical records and append the new decision/evidence delta rather than silently treating old claims as current.

## Scope

Implement and close all findings in this corpus that require correction; preserve the explicitly identified healthy boundaries through meaningful conformance checks. Account for every baseline machine/transition without forcing simple parsers or model-guided workflows into a new runtime statechart framework. Added or materially changed behavior must receive new rows and tests.

Only this repository is the implementation target. Other authorized ArbiterForge products may receive separately scoped compatibility/claim updates after exact-source inspection. Out-of-scope downstream context is excluded. No external product behavior is inferred here.

## Architectural decision

Use one explicit transition/effect contract per existing subsystem owner and one shared vocabulary for truthful outcomes. Keep progress, evidence applicability, authority, delivery/observation, execution/containment and identity/generation separate. Generate repeated capability lists, output recognition, identity expectations, accepted bounds and diagnostic/catalog projections from their owners.

Preserve the existing file/CAS/journal kernel, stable IDs, wire compatibility, replay and before-images. Add contracts alongside handlers first. A global machine, database, daemon or general statechart DSL is not required by the evidence. Avoid a schema migration when a decoder/registry or result projection correction suffices.

Cancellation invalidates ordinary execution authority and stale UI updates. Explicitly owned cleanup and outcome reconciliation remain permitted until settlement. A process exit is not proof of containment; an absent response is not proof that no side effect happened.

## Explicit user changes

- Semantic conflict stops are dependent-only. Shared-store integrity barriers remain because every operation using that unsafe store depends on recovery.
- Corrected debug/reviewer submissions are allowed with proper attempt identity and current evidence. Rejected immutable records remain rejected.
- Progress/evidence semantics are selected through the included SMARTS discussion. No preferred option is preapproved.
- Pi delegated authorship must actually write/edit and run permitted verification under a scoped parent grant in supported hosts.
- Terminal harvest gets durable interruption recovery with bounded, idempotent reconciliation and no new universal ordinary-work blocker.
- The program stays on the integration branch until complete and tested, then produces a new major product release.

## Observable acceptance across UX, DX and AX

| Experience | Required outcome | Evidence |
|---|---|---|
| UX | Independent authorized work continues through unrelated semantic conflicts; status is truthful; recovery does not repeat completed work; uninstall preserves later user choices. | End-to-end success/refusal/interruption/resume scenarios and a comparison of prompts/steps before and after. |
| DX | One owner for every changed contract; generated derivatives stay synchronized; change impact and recovery ownership are obvious. | Registry/handler/consumer conformance, generated-output equality and task-to-source/test mapping. |
| AX | Current state, admissible events, authority scope, outcome and next recovery action are discoverable. | An agent completes scenarios from structured results without guessing from prose, exit code or stale labels. |

Do not invent numeric performance budgets. Measure the existing and candidate paths on the same workload/hardware, preserve current supported thresholds, and agree any new latency/concurrency objective from evidence. The test matrix must detect material regressions and state the sample population.

## Completion and branch promotion

Before promotion, every accepted implementation, migration and documentation task is complete, every finding has its source/candidate verification disposition, and every baseline row has meaningful test/review coverage mapping. Final publication and public readback are subsequent delivery obligations, not prerequisites that require a release to exist before it can be published. Required platform/runtime cells pass; unknown is not passed. N/A requires an actual unsupported/inapplicable contract and evidence, not a failed test relabeled to unblock release. No advertised required feature is deferred by an agent.

The source-to-bundle/package and installed qualification records name exact identities. Migration/backward readability and rollback boundaries are tested. ADR successors and canonical/derived documentation agree. The final candidate is frozen and tested before the single promotion PR. The exact final-main artifacts are verified before publication; if they differ, readiness remains pending until that requalification completes.

Do not claim an unconditional zero-regression guarantee. Demonstrate compatibility invariants, named intended changes, discriminating sequence tests and exact-artifact evidence.

## Program states and delivery evidence

| State | Entry event and guard | Side effects and remaining obligations |
|---|---|---|
| IMPLEMENTING | Branch/baseline recorded; task slices proceed under current authority. | Keep changes on the integration branch; unresolved decisions hold only dependent tasks. |
| INTEGRATION_QUALIFIED | All required implementation, migration, documentation, decision and candidate test obligations are complete on the frozen branch candidate. | Prepare the single promotion PR. No incomplete feature or unavailable required test is deferred to main. |
| PREPUBLICATION_READY | The exact eligible final source/build/artifact identities and required installed qualification are verified by the trusted producer. | Admit the first publication effect. Q-03 public effects/readback remain pending; they are deliberately outside this precondition. |
| DISTRIBUTION_SETTLING | One or more target publication effects have started. | Read back each target independently, retain partial outcomes, and perform only observed missing effects. |
| DISTRIBUTION_SETTLED | All required exact tags, packages/channels and final receipts/public readbacks agree. | Q-03 is complete; record the major release and migration guidance with its actual qualification scope. |

These are proposed program coordination states, not new native wire enums. A defect after promotion returns correction work to the held integration branch and its tests. Missing final-byte evidence holds publication; it does not license implementation of unfinished features directly on main. The prepublication predicate excludes the actual publication/readback task so that readiness is not circular.
