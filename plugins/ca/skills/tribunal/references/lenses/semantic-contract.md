# semantic-contract — lens mandate

Executed by `tribunal-lens-reviewer` under the `semantic-contract` assignment.

## Purpose / failure family
Catch plausible implementations that diverge from requested semantics, including
over-broad changes that pass tests while altering protected behavior.

## Applicability
A current issue/spec, accepted ADR, public contract, or supported pre-existing
behavior establishes an expectation for the assigned code.

## Skip conditions
No affected behavior or usable contract basis. Record missing or conflicting
expectations as a bounded question; absence of a spec is not a product defect.

## Scope emphasis
Trace requirements through entry points, decisions, outputs and consumers.
Compare the changed behavior with both positive and negative obligations.

## Required reading
- Finding record (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/finding-record.md`) and review risk (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/review-risk.md`).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — product scope and vocabulary.
- Applicable issue/spec, accepted ADR obligations, API/protocol contracts,
  compatibility promises and pre-existing behavior evidence in the packet.

## Deterministic probes
Inspect changed symbols and direct consumers, contract/schema differences, and
existing regression expectations. Map each claimed behavior to its cited source;
do not derive the expected answer by copying the implementation.

## Review questions
- Does the implementation satisfy the actual requirement, including forbidden
  behavior, edge values, ordering, units and compatibility?
- Does a broad filter, fallback or default change unrelated pre-existing behavior?
- Do tests agree with the intended semantics, or share the same wrong interpretation?
- Are accepted decision obligations implemented at the boundary they govern?

## False-positive guards / non-findings
Never invent an unwritten requirement or treat a stylistic preference as a
contract. Conflicting or ambiguous requirements need clarification, not a guessed
defect. An intentional, authorized behavior change is not a regression merely
because historical code behaved differently.

## Evidence requirements
Cite the current expectation and its applicability, a concrete distinguishing
input/state, the implementation path, and the wrong observable result. For
missing behavior, name the search universe and trace callers/consumers to its
owner; checking one branch alone cannot establish absence.

## Exposure metric
Count of distinct behavioral obligations traced to implementation and consumers;
report unresolved expectations separately.

## Escalation / cross-lens handoff
Send inadequate-oracle leads to coverage, stale-double leads to test-fidelity,
and incomplete propagation to change-closure. Corroborate a shared root cause
instead of filing a second defect.

## Out of scope
Inventing product decisions, general test completeness, and distribution closure
without a semantic mismatch in the assigned finding scope.
