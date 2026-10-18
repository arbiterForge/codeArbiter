# Coding standards — codeArbiter

Conventions for source in this repository. Build/test commands belong to
`tech-stack.md`; accepted security controls belong to `security-controls.md`.
Shared instruction authoring belongs to `core/surface/README.md`.

## Source ownership

- Shared Python is authored in `core/pysrc/`, then copied by
  `tools/sync-core.py` into governance-host hooks. Do not edit those copies.
- Shared instructions are authored in `core/surface/`, then rendered by
  `tools/build-surface.py` using `core/hosts.json`.
- The native Go engine is `core/artifacts/`. Public and embedded schemas and
  generated model types must agree through their existing generator/checks.
- Farm TypeScript lives in `plugins/ca/tools/`; the infrastructure sibling
  lives in `plugins/ca-sandbox/tools/`.
- Pi host TypeScript lives in `plugins/ca-pi/tools/src/`; the adapter consumes
  the shared kernel rather than reimplementing it.
- Site generators/tests live in `site/scripts/` and `site/test/`; curated
  prose and generated content have distinct owners.

## Python hooks and bridge

Use Python's standard library only in shipped hooks. No third-party runtime
imports; a package used by a separately locked reference-conformance test is
not a hook dependency.

Keep entry hooks thin and shared logic in leading-underscore libraries.
Use `snake_case` functions/variables, `UPPER_SNAKE` constants, and
`CapWords` classes. Imports must not perform filesystem, Git or process work.
Separate pure decisions from bounded filesystem/process access so tests can
exercise malformed, absent, stale and unsafe input independently.

Preserve the existing hook header convention: Python shebang, concise
codeArbiter purpose, design invariants and public API notes. Existing legacy
header differences are not a reason for unrelated sweeping edits.

Malformed input must not crash SessionStart. Entry points follow their owning
documented fail-open/fail-closed policy and surface bounded diagnostics.
Libraries may return or raise their documented typed failures; callers must
not turn a refused or uncertain write into success. Missing and unreadable state
are different conditions.

Keep enforcement IDs stable and covered by the corresponding tests. Use explicit
argument arrays for subprocess boundaries and retain path/size/schema bounds.
The syntax floor is `python -m py_compile` on changed canonical Python files;
behavioral tests cover the affected outcomes.

## Native Go engine

Use the module's pinned Go toolchain and existing package boundaries. Keep Go
source formatted with `gofmt`. The module remains dependency-free; do not add a
datastore, service or general permission/rules layer to implement ordinary state
updates.

Preserve closed schemas and typed operation boundaries. Treat format, schema,
renderer, protocol, artifact revision and product release as separate identities.
Generate derived types with the existing tool; do not independently patch
generated definitions.

Retain bounded input/output, explicit omitted context, stable references,
safe rendering, compare-and-swap, locks, journals and exact replay/recovery.
A reported result is not an attestation. Progress, verification, review and
publication remain distinct under ADR-0043. Unknown applicability remains
unknown; neither stale history nor a later failing check may be hidden.

Tests should discriminate changed behavior, including negative results and
recovery paths. Historical HTML, transaction before-images, and fixture digests
must retain their original meaning and bytes. Fix the producer/view contract
before changing a pinned expected value.

## TypeScript tools and host adapter

`strict: true` remains mandatory. Use `camelCase` values/functions,
`CapWords` types/interfaces and the tree's established explicit local import
extensions. Keep concise codeArbiter purpose headers. Runtime and development
dependency scopes are not interchangeable; use pinned lockfiles.

The farm and sandbox ship their built JavaScript. Rebuild affected bundles from
source and keep source/output synchronized. The Pi build owns both parent/child
extensions, `helpers/windows-supervisor.js` and `helpers/approval-dialog.js`;
do not hand-edit those outputs.

Pi uses Node 22.19+ and Python 3. The external Pi runtime is a reviewed
test/install input, not a shipped runtime dependency. Keep host API declarations
at the existing adapter boundary. Require affirmative project trust before
repository-aware activation. Preserve final tool-argument enforcement,
bounded/redacted host crossings, isolated child environments, the existing
inference broker and whole-process-tree cleanup. Do not add a second runner.

`plugins/ca-pi/package.json` owns its independent version. Generate the root
Git/npm manifest through `tools/build-host-packages.py`. Publication follows
the protected hosted release path, never an ad-hoc local npm publish.

## Shared instructions

Use the existing command-backed owner rather than adding duplicate public
procedures. Descriptions should identify intent and the side-effect boundary.
Host-specific tool names and unsupported capabilities belong in the host
descriptor/conditional notes. Generate all host copies and check resource
closure. Instructions must not recreate artifact permission codes or compulsory
per-task reviewer chains removed by ADR-0043.

## License and exact bytes

The repository license is AGPL-3.0-only and the recorded copyright holder is
SUaDtL (ADR-0009). No new per-file copyright or SPDX headers; the root LICENSE
governs.

New tracked text uses UTF-8 without BOM and LF. Follow the actual scoped
`.gitattributes` rules, including the native module, generated surfaces,
workflows and plugin/site source. Do not normalize retained HTML, immutable
artifact evidence, migration before-images or frozen fixtures: their `-text`
or explicit byte contract takes precedence. Never create a whole-file newline
rewrite as an incidental edit.
