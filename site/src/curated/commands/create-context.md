---
entity: commands/create-context
related: [decompose, init, skills/context-creation]
gates:
  - gate: brownfield check
    when: before inspection
    effect: meaningful source must exist; initialized projects use selected refresh instead
  - gate: safe population
    when: writing context
    effect: selected previews preserve current source bindings and existing human content
---

## What it does

Populate project context from existing code through direct bounded inspection and optional
scoped agents. Cover stack, infrastructure, architecture, security, tests and data; record what
was inspected and what remains unknown. This creates five content documents and their source
provenance. It does not require six child agents, a qualified scout profile or approval receipts.

Only material user-owned decisions need questions. A package script is a declared command,
not a passing test, and an observed convention is not a newly approved policy. Preserve actual
host permissions, secret boundaries and user-owned content throughout.

## Usage

```
/ca:create-context
```

Prefer `/ca:init --brownfield` for initial population. The compatibility route remains available.
If context is already initialized, request a scoped or full refresh through the context-check
owner; do not erase the initialization marker or rerun the scaffolder.

## Example

```text
Illustrative output shape, not a captured run:
Existing source detected. Inspecting six logical categories within the selected repository.
Five source-backed content documents prepared. One material deployment choice remains unresolved.
Applying the selected supported previews; preserving task, question and audit history.
Initialization result and remaining evidence limits reported from the committed state.
```

Use [the operator guide](/guides/understand-an-existing-project/) and
[Compare workflow routes](/concepts/workflow-routes/) for the complete route.
