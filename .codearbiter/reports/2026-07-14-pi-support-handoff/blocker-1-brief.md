# Batch 2 remediation 1 — pre-trust and poisoned-cwd Python resolution

## Context

This is the first remediation task for the approved `pi-support` feature on `feat/pi-support`.
Tasks 3-5 passed focused review, but the authoritative combined Batch 2 integration/security review
blocked promotion. Do not begin Tasks 6-9.

## Confirmed root-cause evidence

- `plugins/ca-pi/tools/src/extension.ts` resolves Python during extension load, before activation and
  project trust are established.
- `plugins/ca-pi/tools/src/bridge.ts` tries bare `py`, `python`, and `python3` candidates without a
  safe working-directory boundary.
- The prior security review proved that a poisoned working-directory `py.exe` can execute.

Reproduce and trace this source path before proposing the implementation. Treat the prior report as
evidence, not a substitute for reading the current code.

## Test-first obligations

1. Add the smallest live regression test that places a poisoned interpreter candidate in the
   project working directory and proves extension load/dormant operation cannot execute it.
2. Run the focused test RED and record the command, expected failure, and evidence that it failed for
   the poisoned-cwd/pre-trust reason.
3. Defer Python resolution until enabled activation and trust are established.
4. Eliminate project-working-directory executable search and validate the selected interpreter as
   an absolute executable path before use.
5. Preserve the approved failure direction: mutating governance fails closed when Python is
   unavailable; dormant repos receive no persona, enforcement, audit mutation, or scaffold.
6. Run the focused test GREEN, then the relevant Pi test suite, typecheck, deterministic build, and
   any directly affected Python packaging/parity checks. Report exact commands and results.

## Binding global constraints

- Python remains stdlib-only.
- Every bridge process uses an absolute interpreter and installed script, argv arrays, `shell: false`,
  bounded stdin/stdout/stderr, explicit cwd, and tree termination.
- `ca-pi` never grants project trust.
- No raw secret may enter code, logs, fixtures, reports, or failure output.
- Do not add or change a dependency, manifest, lockfile, public command, endpoint, or configuration
  surface.
- Keep UTF-8/LF and do not hand-edit generated extension bundles; use the deterministic build.
- Preserve `.codearbiter/gate-events.log`, `.codearbiter/open-tasks.md`, the untracked scratch file,
  all pre-existing temporary directories, and all unrelated dirt.

## Scope and handoff

Modify only files required for this blocker and its tests/build output. Do not fix later Batch 2
blockers opportunistically; record any such observation as `[NEEDS-TRIAGE]` in the report.

Do not commit, stage, publish, switch branches, stash, reset, or clean. The controller owns the
governed commit gate after the entire Batch 2 checkpoint is clean.

Write the full implementation report to
`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-1-report.md`, including source-backed root
cause, RED/GREEN evidence, exact files changed, test results, self-review, and concerns.
