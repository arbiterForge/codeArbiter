---
entity: skills/context-creation
related: [commands/create-context, decompose]
gates:
  - gate: repository selection
    when: before population
    effect: existing source uses brownfield inspection; initialized context uses selected refresh; a new project uses decompose
  - gate: safe context write
    when: applying a selected preview
    effect: current source and target identities must match, and unowned human content must remain unchanged
  - gate: initialization completion
    when: at the end
    effect: required documents and provenance pairs must be valid before the writer records the marker
---

## What it does

Build source-backed project context from an existing repository through direct bounded
inspection or optional scoped agents. It keeps actual host permissions and project-owned
constraints in force without requiring a special scout profile or per-document approval receipt.
A role label, matching source hash or successful write does not certify semantics or containment.

## Phases

1. Confirm the intended uninitialized repository and meaningful source. Initialized repositories
   use selected refresh instead of repeating population.
2. Inspect six logical categories: stack, infrastructure, architecture, security, tests and data.
   Six categories do not require six agents. Record inspected scope, citations, digests and gaps.
3. Draft five content documents: `CONTEXT.md`, `tech-stack.md`, `coding-standards.md`,
   `security-controls.md` and `code-map.md`. Separate observations, inferences and actual decisions.
4. Ask only material user-owned questions that evidence and existing authorization cannot settle.
   Unknowns stay visible; unrelated uncertainty does not stop independent work.
5. Inspect the safe writer's proposed document/provenance changes and apply selected previews.
   Preserve existing human content, task/question boards, audit history and real user stops.
6. Read back the valid output pairs and complete the native initialization transaction.

## Exits

Report the coverage, changes, unknowns and actual checks. Initialization records populated
context, not verified tests or a certified host. No artifact approval ceremony is required for
already-authorized work. A real host denial or unsupported writer shape still stops that action.

Use [the operator guide](/guides/understand-an-existing-project/) and
[Compare workflow routes](/concepts/workflow-routes/) for the full route.
