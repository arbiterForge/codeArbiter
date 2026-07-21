# Pi Batch 2 security-candidate re-audit brief

Date: 2026-07-15
Branch: `feat/pi-support`
Mode: read-only audit first; implementation is authorized only for confirmed findings.

## Candidate A — doctor structured-value redaction

Determine whether any structured value collected for Pi doctor diagnostics can reach the model-visible `/ca-doctor` expansion without passing through the shared secret-redaction corpus and bounded diagnostic normalization.

Audit the full path from `collectPiDoctorInput()` and `diagnosePi()` through `formatPiDoctorReport()`, `renderPiDoctorReportBlock()`, and `sendUserMessage()`. Include adversarial values in package metadata, extension/module/CLI/package-root paths, runtime identity, command ownership, child/package fingerprints, wrapper-self-test responses, and any remediation/message field that can contain runtime data.

Required verdict: `CONFIRMED`, `CLOSED`, or `UNPROVEN`, with severity, exact source/test evidence, and a minimal remediation if confirmed. Tests must prove the final model-visible envelope does not contain injected shared-corpus secret values or unsafe controls.

## Candidate B — stale enforcement after shutdown or process reuse

Determine whether installed Pi guard handlers, result handlers, wrappers, cached cwd/session identity, or bootstrap state can continue governing or leaking prior-session state after `session_shutdown`, a dormant `session_start`, a partial installation failure, or extension reuse for another repository.

Audit enabled-ready to shutdown, enabled to dormant repository, partial failure to dormant, and dormant to re-enabled transitions. Include unknown-tool source-drift handling, native delegation cwd selection, duplicate registration behavior, lifecycle fallback rotation, and bridge-call suppression while inactive. Use real Pi semantics where the supported public API permits deterministic evidence; otherwise identify the exact coverage boundary.

Required verdict: `CONFIRMED`, `CLOSED`, or `UNPROVEN`, with severity, exact source/test evidence, and a minimal remediation if confirmed.

## Constraints

- Preserve existing user-owned dirty files and unrelated artifacts.
- Do not stage, commit, push, publish, switch branches, stash, reset, or clean.
- Do not start Tasks 6–9.
- Write the audit result to `security-candidates-audit.md` in this report directory.
