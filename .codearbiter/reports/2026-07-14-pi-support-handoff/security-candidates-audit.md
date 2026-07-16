# Pi Batch 2 security-candidate re-audit

Date: 2026-07-15
Scope: the two deferred Batch 2 security candidates only

## Verdict summary

| Candidate | Verdict | Severity | Gate effect |
|---|---|---:|---|
| Doctor structured values bypass shared redaction | CONFIRMED | MEDIUM | Must remediate before the combined checkpoint |
| Enforcement survives a lifecycle-generation change | CONFIRMED | MEDIUM | Must remediate before the combined checkpoint |

Both findings are coverage/control gaps on security paths. Neither review found a currently embedded secret, a demonstrated arbitrary external secret source, or a completed cross-repository mutation, so neither is classified CRITICAL/HIGH. Their potential impact is model-visible secret disclosure and stale-cwd mutation, respectively, so they are not acceptable as defense-in-depth nits.

## Candidate A — doctor structured-value redaction

**Verdict:** CONFIRMED

**Severity:** MEDIUM

**File:** `plugins/ca-pi/tools/src/doctor.ts:286`

**Description:** `diagnosePi()` interpolates package name/version/root/scope, Pi and Node versions, bridge path, expansion versions, child path, and runtime CLI/module/package-root values into diagnosis messages. `formatPiDoctorReport()` at lines 411–419 emits every diagnosis id, message, and remediation verbatim. `renderPiDoctorReportBlock()` in `plugins/ca-pi/tools/src/extension.ts:160-163` performs JSON and markup/control escaping but does not call the shared redactor. `registerAliases()` in `plugins/ca-pi/tools/src/commands.ts:160-162` appends that block and sends it with `sendUserMessage()`, making the values model-visible.

The existing adversarial envelope test proves delimiter/control non-injection only. It does not inject any shared-corpus secret and currently expects the injected report text to survive encoding.

Ordinary absolute package/runtime paths are intentional doctor provenance evidence and are not independently forbidden by the project controls. The defect is that secret-shaped content or unsafe controls in any structured value can reach the model-visible sink without the shared-corpus scrub and a sink-level size bound.

**Control:** `.codearbiter/security-controls.md`, Pi adapter and child-process security, lines 284–290 (redaction stays active; bounded/redacted external diagnostics); security-reviewer charter, Secrets, lines 55–57.

**Remediation:** Put the shared `safeDiagnostic` normalization at the final doctor report boundary before `sendUserMessage()`, with an explicit report-size bound. Add an adversarial test that injects a shared-corpus secret, markup delimiters, controls, and oversized content and inspects the final model-visible envelope.

## Candidate B — stale enforcement across lifecycle generations

**Verdict:** CONFIRMED

**Severity:** MEDIUM

**File:** `plugins/ca-pi/tools/src/tool-guard.ts:91`

**Description:** a wrapper checks the live boolean predicates at lines 92–103, then awaits `bridge.call()` at lines 110–117 and executes the captured native definition for the captured installation cwd at line 122 without proving that it is still in the same lifecycle. `deactivate()` at lines 214–218 changes booleans and fallback identity but carries no generation token. If the process deactivates and reactivates while the bridge promise is pending, a later boolean check alone would also be insufficient because the new lifecycle can be active again. The old call can therefore resume with an approval and cwd captured from the previous lifecycle.

The same TOCTOU shape exists in `bridgeToolResults()` at lines 292–308: it checks activity before awaiting the bridge, then may notify or apply a result notice after shutdown/reactivation. Existing tests prove steady-state dormancy, partial-install dormancy, current-context native delegation, fallback rotation, and retry/idempotency; they do not hold a bridge promise across deactivate/reactivate and then release it.

This is a lifecycle-boundary coverage/control gap. Calls already inside native Pi execution cannot be retroactively stopped by the extension, but no bridge-approved mutation or model-visible result decoration should begin after its originating codeArbiter lifecycle has ended.

**Control:** `.codearbiter/security-controls.md`, Pi adapter and child-process security, lines 276–299 (final authority and explicit cwd/bounded adapter boundary).

**Remediation:** Capture an opaque lifecycle generation before each awaited bridge call and require the same active generation before starting native execution or applying post-result effects. On mismatch, fail closed for mutators and suppress stale advisory/result effects. Add deterministic deferred-bridge tests for deactivate-only and deactivate→reactivate transitions, including old-cwd non-execution and no stale notification/notice.

## Gate status

PASS with two MEDIUM findings that must be resolved before the combined Batch 2 checkpoint. No CRITICAL or HIGH findings were identified in this narrow audit.
