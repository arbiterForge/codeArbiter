---
name: ca-sprint
description: "Run an autonomous sprint from maintained specs and plans, with truthful verification and no duplicate artifact approval ceremonies."
argument-hint: "[goal] [--farm]"
---

# /ca-sprint — autonomous sprint

The user's requested sprint establishes its working scope. Use `brainstorming` to clarify genuinely missing outcomes, `writing-plans` to maintain a practical plan, and `subagent-driven-development` to execute through real task dependencies without per-batch permission questions. Record meaningful choices and honest evidence; do not invent approvals, clear user stops, or infer tests passed from progress labels.

## Flow

Load and follow `<plugin-root>/SPRINT.md`:

1. **Specify and plan:** build or resume the exact spec/plan representation. Ask about consequential missing choices, not about arbitrary approval hashes.
2. **Execute:** work through task-scoped prerequisites and coherent batches, implement or delegate where useful, and check changed behavior. Retry affected failures without restarting a reviewer fleet.
3. **Report and deliver:** show actual results, pending checks, and open choices. Use the existing authorized `commit-gate` and PR handoff; opening a PR does not authorize merging or publishing.

Real host/tool permissions, explicit security policy, irreversible operation limits and user stops remain intact. Artifact `DONE` means implementation reported complete, not independently verified acceptance.

## Arguments

- **Goal:** intended sprint outcome and scope.
- **`--farm`:** separately requested legacy Markdown preview backend; obey its provider, budget and circuit-breaker boundaries. HTML farm is disabled, and failure does not authorize a silent backend switch.

## Routes to

`<plugin-root>/SPRINT.md` routes through `brainstorming`, `writing-plans`, `subagent-driven-development`, `commit-gate`, and `finishing-a-development-branch`.

For a single bounded feature, use `/ca-feature`. No repetitive initial spec approval interview is implied by either entry.
