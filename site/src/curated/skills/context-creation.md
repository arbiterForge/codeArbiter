---
entity: skills/context-creation
related: [commands/create-context, decompose]
use_when: "A repository has meaningful existing source but no project context yet, and you want it populated from what the code shows."
avoid_when: "A new project with no source, which is `/ca:decompose`, or a repository that is already initialized, which takes a scoped or full refresh through `/ca:status drift`."
asks: "Only the material decisions that the code and your existing instructions cannot settle. Everything else is recorded with its source or marked unknown."
produces: "Five source-backed context documents (project context, tech stack, coding standards, security controls and code map) with provenance, and an initialization result that lists the remaining unknowns."
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

In a new HTML-format repository the result is records in five knowledge documents, each with its
basis, cited sources and the paths it governs; a Markdown-format repository gets five content
documents and their source provenance. A package script is a declared command, not a passing
test, and an observed convention is not a newly approved policy.

## Usage

```text
/ca:create-context
```

Prefer `/ca:init --brownfield` for initial population; this compatibility route remains
available. If context is already initialized, request a scoped or full refresh through the
context-check owner instead, and do not erase the initialization marker or rerun the scaffolder.

## Example

```text
Illustrative output shape, not a captured run:
Existing source detected. Inspecting six logical categories within the selected repository.
Five source-backed content documents prepared. One material deployment choice remains unresolved.
Applying the selected supported previews; preserving task, question and audit history.
Initialization result and remaining evidence limits reported from the committed state.
```

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
