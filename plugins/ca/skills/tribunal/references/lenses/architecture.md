# architecture — lens mandate

Executed by `tribunal-lens-reviewer` under the `architecture` assignment.

## Purpose / failure family
Find structural choices with concrete consequences: unsafe coupling, failed
change isolation, divergent policy ownership and unreachable production paths.

## Applicability
Assigned modules participate in an architectural boundary, shared policy,
extension seam or canonical/generated ownership relationship.

## Skip conditions
No relevant relationship or consequence can be established. A preferred pattern
or module-size threshold alone is not a reason to run a speculative redesign.

## Scope emphasis
Module boundaries, real callers, policy owners and canonical-to-generated edges.
Use the inventory map as a starting point, including dynamic entry points.

## Required reading
- Finding record (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/finding-record.md`) and review risk (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/review-risk.md`).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/coding-standards.md` — repository conventions;
  applicable accepted architectural contracts and inventory import/caller map.

## Deterministic probes
Inspect imports, exports, runtime registration, declared entry points and
duplicated policy paths. Fan-in and module size route inspection only; static
zero-caller results require checking plugin/reflection/configuration consumers.

## Review questions
- Does coupling force unsafe changes across a boundary that should isolate them?
- Do duplicate policy owners already disagree, or permit a concrete invariant bypass?
- Does an abstraction conceal complexity or expose internals callers must coordinate?
- Is supposedly live code unreachable in the production registration/deploy path?
- Is canonical/generated ownership ambiguous enough to ship inconsistent behavior?

## False-positive guards / non-findings
Numeric thresholds, import counts and naming/pattern differences are not findings.
A one-implementation interface can provide useful isolation, an external boundary
or a testing seam. Static unreferenced code may be a public API or dynamic entry
point. Intentional variation under an accepted contract is not architecture drift.

## Evidence requirements
Show the relationship and concrete correctness, maintenance or change-isolation
consequence; cite any violated repository-owned architectural contract. For dead
code or missing ownership, state the search universe across direct callers,
dynamic registration, public exports and generation/deployment consumers.

## Exposure metric
Count of module/policy ownership relationships traced, recording unresolved
dynamic consumers separately.

## Escalation / cross-lens handoff
Route stale propagated surfaces to change-closure and wrong behavioral obligations
to semantic-contract. Corroborate existing architecture-drift-reviewer evidence
under one root cause; do not re-file the same accepted-ADR violation.

## Out of scope
Style-only redesign, numeric god-module findings, speculation about lost author
context, and duplicate ADR compliance findings without a distinct consequence.
