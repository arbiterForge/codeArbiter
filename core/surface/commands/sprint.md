---
description: "Run an autonomous sprint from maintained specs and plans, with truthful verification and no duplicate artifact approval ceremonies."
argument-hint: "[goal] [--farm]"
---

# {{CMD:sprint}} — autonomous sprint

The user's requested sprint establishes its working scope. Use `brainstorming` to clarify genuinely missing outcomes, `writing-plans` to maintain a practical plan, and `subagent-driven-development` to execute through real task dependencies without per-batch permission questions. Record meaningful choices and honest evidence; do not invent approvals, clear user stops, or infer tests passed from progress labels.

For each independently actionable deliverable, select or create one work ID
through the installed `hooks/work.py` facade. Use an explicit ID or stable
source origin to resume; title and command invocation are not identity. A
single-outcome sprint may use one item. For several deliverables, set the same
optional cycle key on each item with `work.py set-cycle`, or pass `--cycle-id`
on creation. The cycle groups member work IDs; it does not copy their specs,
plans, task states or checks into a second ledger. `work.py cycle-view
<cycle-id>` is the derived group overview. Keep real spec/plan attachments on
their selected member work item and report local progress, checks, PR delivery
and provider effects independently. See `{{PLUGIN_ROOT}}/includes/helper-invocation.md` for
literal helper invocation and retry boundaries.

## Flow

Load and follow `{{PLUGIN_ROOT}}/SPRINT.md`:

1. **Specify and plan:** build or resume the exact spec/plan representation. Ask about consequential missing choices, not about arbitrary approval hashes.
2. **Execute:** work through task-scoped prerequisites and coherent batches, implement or delegate where useful, and check changed behavior. Retry affected failures without restarting a reviewer fleet.
3. **Report and deliver:** show actual results, pending checks, and open choices. Use the existing authorized `commit-gate` and PR handoff; opening a PR does not authorize merging or publishing.

Real host/tool permissions, explicit security policy, irreversible operation limits and user stops remain intact. Artifact `DONE` means implementation reported complete, not independently verified acceptance.

## Arguments

- **Goal:** intended sprint outcome and scope.
- **`--farm`:** separately requested legacy Markdown preview backend; obey its provider, budget and circuit-breaker boundaries. HTML farm is disabled, and failure does not authorize a silent backend switch.

## Routes to

`{{PLUGIN_ROOT}}/SPRINT.md` routes through `brainstorming`, `writing-plans`, `subagent-driven-development`, `commit-gate`, and `finishing-a-development-branch`.

For a single bounded feature, use `{{CMD:feature}}`. No repetitive initial spec approval interview is implied by either entry.
