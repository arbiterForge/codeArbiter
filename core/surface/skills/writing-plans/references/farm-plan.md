# writing-plans — `--farm` plan.json extension

Loaded by `writing-plans` Phase 4 only when `--farm` was requested. The base plan (Phases 1–4) is
unchanged; this leaf adds the machine artifact the farm dispatcher needs.

After the bijective coverage gate passes and the `.md` plan is written, produce the farm artifact —
**one MVP slice at a time, not the whole plan up front.** Front-loading every failing test for the
entire plan would be the waterfall this skill otherwise rejects (Phase 3), and it maximizes the cost
of a mid-flight spec change. So the farm artifact is scoped to the **current slice** (the MVP slice on
the first pass; the next contiguous group on later passes). For each task in the current slice, in
dependency order:

1. Route through `tdd` Phase 1 (derive obligations) + Phase 2 (write the failing test). The test file
   must exist on disk and fail before continuing. Record the test file path for this task.
2. Confirm the test is actually failing (run the gate command from `tech-stack.md`; it must exit
   non-zero). A test that passes before implementation means the obligation is wrong — STOP and revisit
   Phase 2.

Then write `{{PROJECT_DIR}}/.codearbiter/plans/<slug>.plan.json` (the current slice's tasks only)
conforming to `{{PLUGIN_ROOT}}/tools/plan.schema.json`:

- `meta.name` ← slug
- `meta.repo` ← project name from CONTEXT.md
- `meta.model` and `meta.apiBaseUrl` — **leave unset**. These are written by
  `subagent-driven-development`'s model research step at dispatch time. Writing them here would bake in
  a potentially stale selection.
- Per task: `id` ← T-NN (normalized to kebab-case), `description` ← task description,
  `filesInScope` ← path(s) from the task table, `test.path` ← the failing test written above,
  `gate.commands` ← verification command from task table plus full-suite and lint/typecheck from
  `tech-stack.md`, `deps` ← dependency ids (empty array if none), `context` ← a minimal slice of
  relevant types/interfaces (omit if the test file plus task description is self-contained),
  `maxRetries` ← omit to use the farm default.
- **`gate.commands[0]` MUST be the task's narrow behavioral test** (the command that runs just
  `test.path`), with the full suite and lint/typecheck following. The farm's mutation guard re-runs
  `gate.commands[0]` per mutant; if the first command were the full suite, mutation testing would be
  prohibitively slow.

Validate the JSON against the schema before writing (load the schema from
`{{PLUGIN_ROOT}}/tools/plan.schema.json` and check). A schema-invalid plan BLOCKS.

Gate: all failing tests written and confirmed failing; `plan.json` written and schema-valid. Both
artifacts exist before handing off to `subagent-driven-development`.
