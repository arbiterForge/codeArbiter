# writing-plans — `--farm` plan.json extension

Loaded by `writing-plans` Phase 4 only when `--farm` was requested. The base plan (Phases 1–4) is
unchanged; this leaf adds the machine artifact the farm dispatcher needs.

Apply the shared [includes/verification-boundary.md](../../../includes/verification-boundary.md): the slice's narrow RED test and
affected contracts run locally, while exhaustive repository/cross-platform proof remains an
exact-head hosted-CI requirement.

**Rollout gate:** HTML-backed farm use remains disabled until the repository's fresh model-era
qualification matrix, native payload packaging, and real authority adapters are complete. The
projection contract below is implemented so qualification can exercise the real boundary; it is not
permission to use HTML farm dispatch in ordinary work.

After the bijective coverage gate passes and the canonical plan is written, produce the farm artifact —
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

For a legacy Markdown plan, retain the existing schema-driven path below unchanged. For an HTML plan,
do **not** hand-write the projection. Construct the minimal candidate in memory and submit it through
the on-demand artifact protocol's `farm-project` operation. That operation atomically writes
`<project-root>/.codearbiter/plans/<slug>.plan.json` and an immutable content-addressed base binding
only after the approved source pair, current input snapshot, selected scope/slice, deterministic ID
mapping, projection bytes, and fresh RED result for every task all agree.

The HTML projection is the current slice's tasks only and is a strict subset of the unchanged farm
runtime schema:

- `meta.name` ← slug
- `meta.model` and `meta.apiBaseUrl` — **leave unset**. These are written by
  `subagent-driven-development`'s model research step at dispatch time. Writing them here would bake in
  a potentially stale selection.
- Per task: `id` ← T-NN (normalized to kebab-case), `description` ← task description,
  `filesInScope` ← path(s) from the task table, `test.path` ← the failing test written above,
  `gate.commands` ← the canonical task verification argv joined without shell reinterpretation;
  `deps` ← dependency ids inside the selected slice (empty array if none). Do not add `repo`,
  `context`, setup, retry, or task-model fields to an HTML projection. A canonical argv token that
  cannot be represented without shell quoting makes the slice unsupported and BLOCKS projection.
- **`gate.commands[0]` MUST be the task's narrow behavioral test** (the command that runs just
  `test.path`), with affected contract tests and lint/typecheck following. The farm's mutation guard re-runs
  `gate.commands[0]` per mutant; if the first command were an exhaustive suite, mutation testing would be
  prohibitively slow.

For the legacy path, validate the JSON against the schema before writing (load the schema from
`tools/plan.schema.json` and check). A schema-invalid plan BLOCKS.

`plan.schema.json` is the **authoring** contract. The dispatcher enforces its own **runtime** contract
(`PLAN_SHAPE` / `parsePlan()` in `farm.ts`) on the parsed JSON before it touches a single field, and
that one is authoritative: a plan that fails it exits before any worktree, branch, report, or network
call. The two are kept identical key-for-key and type-for-type by a parity test, so a plan that
satisfies the schema is accepted at runtime — with one deliberate exception, the kebab-case `id`
pattern, which is stricter here than the runtime path-safety rule. Both objects are closed: an
undeclared property is an error, not an ignored extra.

For the HTML path, the existing user/SMARTS workflow must capture a `farm_authorization` receipt whose
payload binds the current spec/plan/input hashes, scope, base projection hash, and each task's source
ID, farm ID, test path, verification-definition hash, command, failing exit, stdout hash and stderr
hash. A digest is correspondence, not approval authentication. Call `farm-project` with that receipt;
do not create a binding file directly.

Gate: all failing tests written and freshly observed failing; the legacy JSON is schema-valid or the
HTML projection and immutable binding were committed together. Both artifacts exist before handoff.
