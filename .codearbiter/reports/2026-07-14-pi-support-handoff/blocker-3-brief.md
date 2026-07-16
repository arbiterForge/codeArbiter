# Batch 2 remediation 3 — fail-closed enforcement bootstrap in real Pi

## Context

This is the third remediation task for the approved `pi-support` feature on `feat/pi-support`.
Remediations 1-2 are accepted. Tasks 6-9 remain gated.

## Confirmed root-cause evidence

- `installParent()` throws when `installEnforcement()` fails during enabled `session_start`.
- Pi's real lifecycle runner catches ordinary extension-handler failures, emits `extension_error`,
  and continues the host session.
- The current focused fake-host test observes the throw, but it does not prove real Pi remains
  fail-closed after Pi swallows that error.

Trace the real lifecycle dispatcher, current `EnforcementInstaller`, guard registration order, and
package/RPC fixture before proposing the implementation.

## Test-first obligations

1. Add a real installed-Pi RPC/JSON fault-injection regression that forces enforcement installation
   to fail during enabled session startup, observes Pi continue after `extension_error`, then attempts
   a mutating tool call through the real dispatcher.
2. Run it RED and record proof that the host continued and the mutation was not reliably blocked by
   an installed bootstrap boundary.
3. Add an always-installed bootstrap guard, or use an explicit supported host shutdown mechanism,
   so every potentially mutating call is blocked from the moment enabled activation begins until the
   complete final-execution enforcement boundary is installed.
4. The block must be structured, non-executing, name `/ca-doctor`, and remain effective when Pi
   catches the original lifecycle error. Do not rely on a thrown handler as enforcement.
5. Dormant repositories remain silent and ungoverned; read/advisory behavior keeps the approved
   failure direction. Unknown/opaque tools remain potentially mutating.
6. Partial installation cannot mark the boundary ready. A later successful retry may transition to
   normal wrapped execution only after the entire installation completes.
7. Run focused GREEN, existing installation retry/final-argument/unknown-tool tests, the full Pi
   suite, typecheck, deterministic builds, real package/RPC checks, parity, and doctor/backstop tests.
   Report exact commands and results.

## Binding global constraints

- The adapter must be the final authority over governed tool arguments; same-process trusted
  extensions remain the declared cooperative residual, not permission to run unguarded during
  bootstrap.
- Unknown Pi tools are potentially mutating and block by default.
- Python remains stdlib-only; no new process, dependency, manifest, lockfile, public command,
  endpoint, or configuration surface.
- No raw secret may enter code, fixtures, RPC output, logs, audits, reports, or failure text.
- Preserve remediation 1 interpreter safety and remediation 2 activation parity.
- Preserve UTF-8/LF and deterministic bundle generation.
- Preserve all unrelated/user-owned dirt.

## Scope and handoff

Modify only files required for the bootstrap state/guard, real-Pi fault-injection regression,
focused tests, and deterministic parent bundle. Do not fix later blockers or start Tasks 6-9.

Do not stage, commit, publish, switch branches, stash, reset, clean, or install dependencies.

Write the full implementation report to
`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-report.md`, including root cause,
fault-injection design, RED/GREEN evidence, files changed, verification, self-review, and concerns.
