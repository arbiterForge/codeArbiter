# typesafety — lens mandate

Executed by `tribunal-lens-reviewer` under the `typesafety` assignment.

## Purpose / failure family
Find unsound type/schema boundaries that permit states the consuming contract
cannot safely handle.

## Applicability
The language or boundary has a static type, schema or public interface contract
whose soundness matters to assigned behavior.

## Skip conditions
No relevant type/schema contract exists. Do not demand static types from an
untyped language; route independently proved validation failures to appsec or
reliability.

## Scope emphasis
External-data decoding, public signatures, narrowing and variant handling,
nullability, identifier/unit distinctions and invariant-bypassing escape hatches.

## Required reading
- Finding record ([routines/tribunal/references/finding-record.md](../finding-record.md)) and review risk ([routines/tribunal/references/review-risk.md](../review-risk.md)).
- `<project-root>/.codearbiter/coding-standards.md` — type conventions;
  `<project-root>/.codearbiter/tech-stack.md` — type/schema tooling and validation
  boundaries; actual producer and public consumer contracts.

## Deterministic probes
Inspect schema/signature differences, narrowing sites, exhaustive variant
handling, nullability and existing checker results. Locate casts, suppression
comments and untyped ingress as candidates, then trace validated construction.

## Review questions
- Can unvalidated external data be asserted into a trusted internal type?
- Can schema/type drift, unchecked narrowing or nullability violate a consumer invariant?
- Are variants exhaustive, including supported future/unknown wire values?
- Can interchangeable identifiers or units produce a concrete wrong operation?
- Does an escape hatch bypass a required invariant rather than encode an already
  established fact the checker cannot express?

## False-positive guards / non-findings
A cast justified by validated construction is valid. Compiler limitations,
deliberate opaque boundaries and negative type tests can justify suppressions.
Naming/style drift and generic error-message quality are not type defects.

## Evidence requirements
Show the unsound boundary/contract, a reachable invalid value, its route past
validation and the consuming invariant it violates. For absent validation, name
the search universe and trace producer, decoder and callers before blaming the
local cast. Checker diagnostics alone do not prove runtime impact.

## Exposure metric
Count of public or data/type boundaries traced through validation and use;
count repeated escape-hatch syntax only once per underlying invariant.

## Escalation / cross-lens handoff
Test-fidelity owns test-double type drift; appsec owns exploitable validation
bypasses and reliability owns runtime state corruption. Corroborate the shared
mechanism rather than file it under every lens.

## Out of scope
Type-style preferences, general error-message advice and test fixture fidelity.
