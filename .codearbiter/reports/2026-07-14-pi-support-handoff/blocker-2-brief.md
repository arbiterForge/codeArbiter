# Batch 2 remediation 2 — canonical activation parsing

## Context

This is the second remediation task for the approved `pi-support` feature on `feat/pi-support`.
Remediation 1 is accepted. Tasks 6-9 remain gated.

## Confirmed root-cause evidence

- `plugins/ca-pi/tools/src/activation.ts` currently accepts only an exact lowercase, column-zero
  `arbiter: enabled` marker and requires exactly one match.
- Canonical `core/pysrc/_hooklib.py::frontmatter_enabled_text` tolerates a leading BOM, surrounding
  whitespace, case differences, no whitespace after the colon, and duplicate enabled markers.
- The combined review proved `---\n  ArBiTeR:enabled\n---\n` inactive in TypeScript and active in
  Python.

Read and trace both implementations and their current tests before proposing the implementation.
The Python shared-core behavior is the canonical existing contract; do not silently redefine it.

## Test-first obligations

1. Establish one shared or generated activation contract that prevents the Pi TypeScript parser and
   canonical Python parser from drifting independently.
2. Add cross-host fixtures covering at least: canonical lowercase, mixed case, indentation,
   whitespace/no-whitespace after the colon, leading UTF-8 BOM, duplicate enabled markers, CRLF,
   closing delimiter at EOF, disabled/wrong value, marker outside frontmatter, missing frontmatter,
   and unclosed/malformed frontmatter.
3. Make both Python and TypeScript tests consume the same contract/fixture source. The TypeScript
   result must equal Python's `enabled` result for every fixture; preserve Python's existing
   `malformed` semantics wherever the fixture records them.
4. Run the smallest TypeScript cross-host/contract test RED and record the exact parser-drift
   failure before changing implementation.
5. Implement the minimum TypeScript/generated/shared-contract change to match canonical behavior.
   Do not create a second handwritten policy source.
6. Run the focused test GREEN, then affected Python hooklib tests, Pi tests, typecheck, deterministic
   build/checks, and package/parity checks. Report exact commands and results.

## Binding global constraints

- `core/pysrc/` and `core/surface/` remain authoritative. Pi may add codecs/adapters, never a
  separate governance rule or command body.
- Python remains stdlib-only.
- Dormant repositories stay silent: no persona, enforcement, audit mutation, or scaffold unless the
  canonical contract reports enabled.
- Preserve UTF-8/LF. A leading BOM is test input only, not a source-file encoding change.
- If generation or shared Python output changes, regenerate/check all declared host targets and
  prove a second run produces no diff.
- Do not add or change a dependency, manifest, lockfile, public command, endpoint, or configuration
  surface.
- Preserve all user-owned/unrelated dirt and the accepted remediation-1 behavior.

## Scope and handoff

Modify only files required for the canonical activation contract, its cross-host fixtures/tests,
generated outputs, and deterministic parent bundle. Do not fix later Batch 2 blockers or start Tasks
6-9. Record unrelated observations as `[NEEDS-TRIAGE]` in the report.

Do not stage, commit, publish, switch branches, stash, reset, or clean.

Write the full implementation report to
`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-2-report.md`, including source-backed root
cause, contract design, RED/GREEN evidence, exact files changed, verification, self-review, and
concerns.
