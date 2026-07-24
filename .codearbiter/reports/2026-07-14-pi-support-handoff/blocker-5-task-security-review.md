# Blocker 5 independent task and security review

**Recorded:** 2026-07-15
**Scope:** native read normalization and model-visible context only
**Review mode:** read-only source, focused tests, installed/cached Pi runtime source, and generated-bundle inspection

## Spec compliance

- **Verdict: NO — one binding context-delivery contract is incomplete.** Native `{path}` is converted to canonical `{file_path}` only for the Python pre-read payload (`plugins/ca-pi/hooks/_host.py:46`, `plugins/ca-pi/hooks/pi-bridge.py:158`), while the wrapper sends the unchanged frozen native shape to Pi's executor (`plugins/ca-pi/tools/src/tool-guard.ts:84`, `plugins/ca-pi/tools/src/tool-guard.ts:101`). The READ post-result bridge route is gone and WRITE/EDIT remain the only post-result routes (`plugins/ca-pi/hooks/pi-bridge.py:27`, `plugins/ca-pi/tools/src/tool-guard.ts:243`). Native result fields, including `details` and `isError`, are retained by spreading only the `content` patch over the native result (`plugins/ca-pi/tools/src/tool-guard.ts:104`).
- **Important — Pi drops the session identity required by the shared pre-read de-duplication contract.** `BridgeRequest` already provides `sessionId` (`plugins/ca-pi/tools/src/contracts.ts:5`), and the Python adapter passes it to shared core as `session_id` (`plugins/ca-pi/hooks/pi-bridge.py:163`); however, the real wrapper's READ request omits it (`plugins/ca-pi/tools/src/tool-guard.ts:90`). Shared core hashes `(session_id, rel)` and suppresses an already-injected pair (`core/pysrc/_readinjectlib.py:786`, `core/pysrc/_readinjectlib.py:1017`). Consequently every Pi read currently uses the same empty session identity: after one Pi session reads a governed file, later sessions in that checkout silently lose the context. This is not the shared per-session "exactly once" behavior. The real-Pi proof starts only one RPC session and therefore cannot catch the cross-session suppression (`.github/scripts/test_pi_package.py:1234`). **Remediation:** extend the tool execution context port with Pi's read-only session manager, capture `context.sessionManager.getSessionId()` into the READ bridge request, reject/handle an unavailable or malformed identifier explicitly, and add a real-Pi regression that runs two distinct sessions against the same governed file and observes the exact context once in each while a second read within one session remains silent.

## Strengths

- The normalization seam is narrow and idempotent: canonical `{file_path}` survives unchanged and no H-rule or governance lookup was copied into adapter code (`plugins/ca-pi/hooks/_host.py:46`, `.github/scripts/test_pi_parity.py:250`).
- The production result path appends one identity-owned block without replacing native content, and the ownership marker cannot be forged by plain native text (`plugins/ca-pi/tools/src/notices.ts:37`, `plugins/ca-pi/tools/src/notices.ts:62`). Redaction, control-byte replacement, UTF-8 byte capping, and exact identity de-duplication are all applied before insertion (`plugins/ca-pi/tools/src/notices.ts:25`, `plugins/ca-pi/tools/src/notices.ts:48`).
- The real-Pi fixture is authentic and non-tautological. It installs this repository through Pi's package command, leaves built-ins enabled, registers only a deterministic local provider, asks Pi for actual `read` tool calls with fixed IDs, and copies the next provider turn's actual `role=toolResult` objects (`.github/scripts/test_pi_package.py:156`, `.github/scripts/test_pi_package.py:452`, `.github/scripts/test_pi_package.py:287`). The assertion independently supplies the expected Unicode ADR text and requires matching real `tool_execution_start`/`tool_execution_end` IDs plus an ungoverned no-notice control (`.github/scripts/test_pi_package.py:1197`, `.github/scripts/test_pi_package.py:1253`, `.github/scripts/test_pi_package.py:1281`). No fake handler output can supply the expected ADR string.
- The six supported-version/OS cells execute the complete package/RPC script: Windows, macOS, and Linux on Pi 0.80.5 and 0.80.6 (`.github/workflows/ci.yml:205`, `.github/workflows/ci.yml:257`). Installed Pi 0.80.6 and the integrity-addressed cached Pi 0.80.5 source both chain tool-result content patches and preserve `details`/`isError`; the cached tarball integrity is the report's SHA-512 `18F605...A780`.
- The current parent bundle contains the same notice implementation, READ wrapper patch, and WRITE/EDIT-only post-result predicate as the TypeScript source (`plugins/ca-pi/extensions/codearbiter.js:655`, `plugins/ca-pi/extensions/codearbiter.js:735`, `plugins/ca-pi/extensions/codearbiter.js:880`). Its SHA-256 is `3DF243166F00834AA935B085CAD182BECB370BBF48E6E92BE1B347DADE22E6C3`; the child bundle and lock remain the recorded `E04A1CF...B328` and `9D3FE61...1CC2`.

## Task-quality issues

### Critical

None.

### Important

1. **Cross-session context suppression** — `plugins/ca-pi/tools/src/tool-guard.ts:90`; remediation above. This makes the task's main behavior reliable only for the first process/session to read a given governed path.
2. **The model-visible READ failure diagnostic can disclose raw absolute host paths.** `BridgeClient.validatePaths()` passes `realpath()` errors containing the interpreter/script/package path into `failed()` (`plugins/ca-pi/tools/src/bridge.ts:84`, `plugins/ca-pi/tools/src/bridge.ts:144`). `failure()` embeds that detail in the warning (`plugins/ca-pi/tools/src/bridge.ts:100`), and the READ wrapper appends it to the native result consumed by the model (`plugins/ca-pi/tools/src/tool-guard.ts:102`). `safeDiagnostic()` redacts secret patterns and controls but does not redact generic absolute paths/usernames (`plugins/ca-pi/tools/src/redaction.ts:7`). This contradicts the review's no-raw-path diagnostic boundary. **Remediation:** map path-validation and process-start failures to fixed public classes such as `path validation failed` / `bridge launch failed`, keep detailed paths out of response text, and add a READ-path regression whose missing interpreter/package paths contain a sentinel username/path that must not reach the patched tool result.

### Minor

None.

## Task assessment

**Task quality: Needs fixes.** The actual native result route and test fixture are well constructed, but the missing session identity makes shared pre-read de-duplication globally sticky across Pi sessions, and the newly reviewed model-visible warning boundary still exposes raw absolute path details.

## Security review — 2026-07-15

### CRITICAL findings (0)

None.

### HIGH findings (0)

None.

### MEDIUM findings (2)

1. **Severity:** MEDIUM
   **File:** `plugins/ca-pi/tools/src/tool-guard.ts:90`
   **Description:** Omitting `sessionId` turns shared per-session injection de-duplication into cross-session suppression, so governance and security pointers can fail open after an earlier Pi session read the same file.
   **Control:** Pi adapter and child-process security; shared pre-read per-session interface.
   **Remediation:** propagate the authenticated Pi session manager's `getSessionId()` value and prove two-session delivery plus same-session de-duplication through real Pi.

2. **Severity:** MEDIUM
   **File:** `plugins/ca-pi/tools/src/bridge.ts:144`
   **Description:** Absolute interpreter/package/script paths from `realpath()` errors can be copied into a READ warning and then into model context. Secret-pattern redaction does not remove a generic local username/path.
   **Control:** Pi adapter and child-process security — bounded/redacted child diagnostics; review binding forbidding raw secret/path diagnostic leaks.
   **Remediation:** expose fixed failure classes only and add a sentinel-path non-disclosure regression at the actual patched read result.

### LOW findings (0)

None.

### Gate status

**PASS (0 CRITICAL, 0 HIGH).** Both MEDIUM findings must remain in the checkpoint report; the first is independently an Important task-compliance defect, so blocker 5 is not task-approved yet.

## Bounded check record

- Read the blocker brief/report and authoritative handoff finding; inspected the current Python adapter, shared pre-read contract, TypeScript bridge/contracts/result wrapper/notices, all focused parity/wrapper/real-Pi tests, CI matrix, security controls, coding standards, reviewer charter, and task-review template.
- Inspected installed Pi 0.80.6 result chaining and the integrity-addressed cached Pi 0.80.5 tarball's equivalent `agent-session.js`/`extensions/runner.js` semantics. No network or install was used.
- Inspected the generated parent bundle directly and calculated the three recorded hashes. No tests were rerun because the implementer supplied complete GREEN evidence and the two findings are source-proven; no working-tree/index/HEAD/branch mutation was performed other than this required review artifact.
