# 02: Phased build plan

Illustrative, unapproved greenfield roadmap. This is a project-level document,
not an executable typed feature plan or a promise about delivered functionality.

## MVP: preserve useful searches

Goal: a person can save and retrieve a named search. Include the list and query
model, basic validation and an explicit empty state. Resolve CONFIRM-01 before
choosing persistence. Defer cross-user sharing because it introduces ownership
and access-control decisions. Done means a created search can be retrieved in
its defined order through the selected application interface.

## v1: move saved searches

Goal: a person can export their own saved searches. Include ordered name/query
CSV rows, special-character round-trip and no export for an empty collection.
Defer import because conflict handling and validation are separate decisions.
The pure serializer is demonstrated in the product tour, but the full UI,
authorization and download delivery are not implemented by that fixture.

## v2: consider collaboration

Goal: decide whether sharing belongs in the product. Investigate access control,
revocation and expected collaboration journeys before scheduling implementation.
Do not call this phase complete based on the CSV tests. Done means the proposed
scope, risks and measurable acceptance conditions have been reviewed.

## Review

Check that MVP has standalone value, dependencies are explicit, and deferred
work has a reason rather than disappearing from the project record.
