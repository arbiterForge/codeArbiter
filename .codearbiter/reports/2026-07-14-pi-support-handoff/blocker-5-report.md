# Blocker 5 report - native read normalization and model-visible context

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Source:** `blocker-5-brief.md` and the handoff HIGH "read-context parity test is false-green"

## Outcome

Pi's real native `read` path now reaches the shared pre-read core in its canonical
`{file_path: ...}` shape while the native Pi executor still receives its original `{path: ...}`
arguments. A non-empty shared `additionalContext` response is appended to the native read result
through the existing bounded, secret-redacted, identity-owned notice mechanism. Pi then places that
patched native result in the next provider turn as the actual `toolResult`.

The adapter no longer asks the Python bridge for a fabricated post-result READ route. The
post-result bridge remains registered for WRITE and EDIT only. Native read failures and bridge
failures retain the prior advisory/fail-open behavior; mutation enforcement is unchanged.

## RED evidence

Tests were written or corrected before production code.

### Integrated Python normalization

```powershell
python .github/scripts/test_pi_parity.py `
  PiParityFixtures.test_pi_bridge_native_read_matches_canonical_shared_context -v
```

Result: exit 1. A canonical `{file_path: <governed file>}` request returned `notice` with the exact
ADR context, while the real native `{path: <same governed file>}` request returned:

```json
{"version":1,"outcome":"allow","auditCode":"PI_CORE_ALLOW"}
```

The failure was the expected `allow != notice`, proving the bridge had not applied the already
defined Pi host normalization seam.

### TypeScript result propagation and fake-route removal

```powershell
npm test -- --run test/tool-guard.test.ts `
  -t "appends governed pre-read context|does not fabricate a post-result READ"
```

Result: exit 1 with 2/2 focused failures. The production read wrapper returned only native content,
with no owned context block. The result handler also emitted one `event: tool_result, tool: read`
bridge request where the corrected test required none.

### Real installed-Pi model-context proof

```powershell
python .github/scripts/test_pi_package.py `
  PiPackageTests.test_real_rpc_native_read_context_is_model_visible_once -v
```

Result: exit 1. The deterministic local provider drove Pi's actual native `read` dispatcher and,
on the following provider turn, captured the matching model-context `toolResult`. The governed
capture contained exactly one block - the native file content - instead of native content plus the
required owned context block. This was an assertion failure, not a fixture or transport error.

## Implementation

### Canonical Python payload

`plugins/ca-pi/hooks/pi-bridge.py` now canonicalizes only a READ `tool_call` through
`PiHost.normalize_tool_input()` before constructing the shared-core hook payload. The original
request object is not mutated and never returns to Pi's native executor. `_host.py` makes the read
normalizer idempotent so an already canonical `{file_path: ...}` input remains canonical.

No governance, matching, ADR, budget, deduplication, or H-rule logic was copied into the adapter.
Shared `pre-read.py` and `_readinjectlib.py` remain the only context-selection implementation.

### Actual native result propagation

The installed read wrapper retains the pre-execution bridge response, executes the original Pi read
with the canonical frozen snapshot of the original native arguments, and applies
`applyToolResultNotice()` to the returned native result. Only the returned `content` field is patched;
native `details`, `isError`, and every other result field are spread through unchanged.

`bridgeToolResults()` now routes only WRITE and EDIT. This removes the false post-result READ seam
without changing the existing write/edit notice behavior.

## Real-Pi fixture authenticity

The package test installs the current repository through Pi's normal package command into an
isolated Pi home and starts the already-installed Pi 0.80.6 CLI in RPC mode with its real builtin
tools. A test-only local provider emits two native `read` tool calls:

- `ca-read-context-governed` for `src/governed.txt`;
- `ca-read-context-ungoverned` for `src/ungoverned.txt`.

On the subsequent model turn, the provider filters its actual `context.messages` for those exact
`toolCallId` values and base64-encodes only the two observed `toolResult` objects into its final
assistant text. The Python assertion independently supplies the canonical fixture ADR text; it does
not call the bridge, a hook handler, or a test response seam to create the expected value. The test
also requires matching real RPC `tool_execution_start` and `tool_execution_end` events for both IDs,
`toolName: read`, and `isError: false`.

Sanitized model-visible captured shape after the fix:

```json
{
  "governed": {
    "role": "toolResult",
    "toolCallId": "ca-read-context-governed",
    "toolName": "read",
    "content": [
      {"type": "text", "text": "governed native body\n"},
      {
        "type": "text",
        "text": "<!-- codearbiter:pi-tool-result:<sha256> -->\nADR-0015 (Model-visible read contract) governs this file - do not contradict it; route changes via /ca:reconcile or /ca:adr.",
        "codearbiter": {"kind": "codearbiter-notice", "version": 1, "id": "<sha256>"}
      }
    ],
    "isError": false
  },
  "ungoverned": {
    "role": "toolResult",
    "toolCallId": "ca-read-context-ungoverned",
    "toolName": "read",
    "content": [{"type": "text", "text": "ungoverned native body\n"}],
    "isError": false
  }
}
```

The report uses `-` in place of the source's Unicode em dash in this sanitized rendering only. The
test asserts the exact Unicode shared context and requires it exactly once.

The same package test is part of `.github/scripts/test_pi_package.py`, which the supported CI matrix
runs on Windows, macOS, and Linux for both Pi 0.80.5 and 0.80.6. Local source inspection found
identical result semantics in installed 0.80.6 and the integrity-addressed cached 0.80.5 tarball:
native executor output is passed to `emitToolResult`; handler content patches are chained; the
resulting content becomes the next-turn `toolResult`. The cached 0.80.5 tarball's verified SHA-512 is
`18F605B87C3504DFB79B91B3C351C61F8D567450F36E994B6AE4B4CD849FD593A480A15DEB0B4401C8DC841FEF9B3F58B5319B40EC0409BB158FA1B1671BA780`.

## Security bounds

- Context crosses `BridgeClient` response validation and its 16,000-character safe diagnostic cap
  before insertion.
- `applyToolResultNotice()` applies the shared secret corpus redactor, normalizes newlines, replaces
  control bytes, enforces a 16,000-byte final block cap, and hashes the normalized identity for exact
  de-duplication.
- The adapter appends one owned text block and cannot replace native content, details, error state,
  or convert an executor exception into success.
- A READ bridge failure remains `warn`: the native read executes, and only the existing fixed,
  redacted `/ca-doctor` warning can be appended.
- Dormant and bootstrap READ paths still delegate natively before any bridge call. Shared self-read,
  ungoverned, and deduplicated outcomes return no context and therefore no notice.
- WRITE and EDIT pre-execution enforcement and post-result notices are unchanged; unknown tools
  remain potentially mutating and fail closed.
- The test adds no production switch, environment variable, dependency, manifest, lockfile,
  provider credential access, endpoint, network call, or package-runtime copy.

## Files changed

- `plugins/ca-pi/hooks/_host.py`
- `plugins/ca-pi/hooks/pi-bridge.py`
- `plugins/ca-pi/tools/src/tool-guard.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `.github/scripts/test_pi_parity.py`
- `.github/scripts/test_pi_package.py`
- `plugins/ca-pi/extensions/codearbiter.js` - deterministically regenerated parent bundle
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-5-report.md`

The child bundle and reviewed lockfile remain byte-identical. No shared governance file was changed
for this blocker.

## GREEN verification

### Focused

```powershell
python .github/scripts/test_pi_parity.py `
  PiParityFixtures.test_pi_read_and_edit_payload_normalization `
  PiParityFixtures.test_pi_bridge_native_read_matches_canonical_shared_context -v
npm test -- --run test/tool-guard.test.ts `
  -t "appends governed pre-read context|does not fabricate a post-result READ|read bridge warnings"
python .github/scripts/test_pi_package.py `
  PiPackageTests.test_real_rpc_native_read_context_is_model_visible_once -v
```

Results: integrated Python 2/2; wrapper/fake-route/advisory 3/3; real installed Pi 1/1.

### Full TypeScript, package, RPC, parity, doctor, and backstops

```powershell
npm run typecheck
npm test
npm test -- test/package.test.ts
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
python .github/scripts/test_host_descriptors.py
```

Results:

- typecheck: exit 0;
- full Pi: 8 files, 110/110 tests;
- TypeScript package: 14/14;
- release/package/RPC-process: 17/17;
- isolated real-Pi command/alias RPC: 1/1;
- parity: 19/19;
- doctor/backstop: 5/5;
- shared activation/hooklib: 69/69;
- host descriptors: 13/13.

### Generation and repository checks

```powershell
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Results: 42 shared core files x 3 plugins are byte-identical; Claude/Codex/Pi generated surfaces are
in sync; root/Pi package metadata matches the descriptor; diff check exits 0.

One initial `npm run typecheck` was accidentally invoked from the repository root and returned the
expected `Missing script: typecheck`; it made no changes. The canonical tools-directory invocation
above then passed.

## Deterministic bundle evidence

Two consecutive final `npm run build` executions produced identical SHA-256 hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `3DF243166F00834AA935B085CAD182BECB370BBF48E6E92BE1B347DADE22E6C3` | `3DF243166F00834AA935B085CAD182BECB370BBF48E6E92BE1B347DADE22E6C3` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| `plugins/ca-pi/tools/package-lock.json` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

## Residual concerns

The real runtime execution is local Pi 0.80.6; Pi 0.80.5 is covered by the six-cell CI matrix and by
integrity-verified source evidence for the same result-patching path, not by a second local runtime
installation. The model-context fixture intentionally relies on the supported Pi provider/message
schema and should remain a promotion canary whenever the exact supported Pi set changes.

No unresolved local blocker remains for remediation 5.

---

## Independent security-review remediation addendum

**Recorded:** 2026-07-15
**Review source:** `blocker-5-task-security-review.md`

The independent task review found two additional Important/MEDIUM defects after the first blocker-5
implementation. Both are now fixed and covered by focused and real-host regressions. This addendum
supersedes the earlier two-read fixture description, 110-test TypeScript count, and parent-bundle
hash where they differ below.

### Finding 1 - cross-session read-context suppression

The wrapper omitted `BridgeRequest.sessionId`, so every native Pi read reached shared
`_readinjectlib.py` with the same empty session identity. Shared context was correctly deduplicated
within that identity, but the empty value accidentally made the marker global across later Pi
sessions in the same checkout.

Authoritative Pi evidence was checked before implementation:

- installed Pi 0.80.6 declares `ExtensionContext.sessionManager` and
  `ReadonlySessionManager.getSessionId(): string`;
- Pi's registered-tool wrapper supplies its execution context from `runner.createContext()`, so the
  final native `execute()` override receives that supported context;
- the integrity-addressed cached Pi 0.80.5 package exposes the same declarations and wrapper path.
  Its already-recorded SHA-512 remains
  `18F605B87C3504DFB79B91B3C351C61F8D567450F36E994B6AE4B4CD849FD593A480A15DEB0B4401C8DC841FEF9B3F58B5319B40EC0409BB158FA1B1671BA780`.

`ToolExecutionContextPort` now includes the read-only session-manager seam. A READ wrapper validates
the native value as a non-blank string no longer than the bridge protocol's 1,024-character limit,
then sends it as `sessionId`. If Pi omits the manager, returns a malformed value, or throws, the
wrapper uses a private random UUID that is stable only for the current enforcement lifecycle.
`beginBootstrap()` rotates it and `deactivate()` clears it. Dormant/bootstrap READ execution returns
to the native tool before consulting either the session manager or the bridge. The identifier is
never placed in model text, diagnostics, notices, or audit records.

RED proof, captured before the production edit:

- `appends governed pre-read context to the native result without changing native execution`
  expected `sessionId: pi-session-123`; the request omitted the field;
- `uses a stable private fallback for malformed Pi session identities and rotates it with the
  lifecycle` expected a bounded string; the request field was `undefined`;
- the upgraded real-Pi test started two sequential RPC processes against the same governed repo.
  The later session's first governed read contained one native block instead of native plus context,
  proving cross-session suppression rather than a concurrent-fixture race.

The real provider now emits three native reads per session: governed-first, governed-second for the
same path, then ungoverned. It runs in two sequential, isolated Pi RPC processes sharing the same
governed checkout. Each session's first governed result contains native content plus the exact owned
context once; its second contains native content only; the ungoverned result remains native-only.
Real `get_state` responses are also required to expose non-empty, bounded, distinct session IDs. The
test asserts only those predicates and this report intentionally records no raw session values.

### Finding 2 - model-visible bridge diagnostics exposed absolute paths

Bridge path validation, spawn errors, and non-zero-process stderr previously flowed through
`BridgeResponse.message`. Because READ is advisory, `applyToolResultNotice()` then appended those raw
diagnostics to the actual native result consumed by the model. Shared secret redaction did not and
was not intended to erase arbitrary usernames or absolute paths.

All locally generated bridge failure branches were audited and now use bounded public classes:

| Failure branch | Model-visible class |
|---|---|
| interpreter/script/package realpath, absolute-path, or containment validation | `path validation failed` |
| synchronous spawn failure or child `error` event | `bridge launch failed` |
| non-zero bridge exit, regardless of stderr | `bridge process failed` |
| request serialization/size | `request serialization failed` / `request overflow` |
| cancellation/timeout/stream limit | `cancelled` / `timed out` / `protocol overflow` |
| invalid stdout JSON or response schema | `returned malformed protocol` |

Stderr remains bounded and counted for the audit record but its text is discarded. Audit lines keep
only the host, rule, audit class, correlation UUID, and request/stdout/stderr byte counts. The
existing fail direction remains unchanged: a READ/tool-result failure is an advisory `warn`, a
mutation `tool_call` is a `block`, and every public message retains `/ca-doctor` guidance.

RED proof, captured through the actual wrapped native READ result before the production edit:

- missing interpreter, missing script, and missing package paths emitted raw realpath errors
  containing a sentinel username/path;
- a launch failure emitted `spawn <sentinel absolute path> ENOENT`;
- a non-zero subprocess emitted its sentinel stderr path.

The same tests now require the native read body, the exact fixed public class, and `/ca-doctor`,
while rejecting the sentinel and every configured interpreter/script/package path from the complete
serialized patched result. The validation-path audit is independently required to contain three
`PI_BRIDGE_WARN` records and no sentinel.

### Final GREEN verification

Focused and real-host results after rebuilding the shipped parent extension:

- tool-guard/session regressions: 26/26;
- bridge/subprocess regressions: 15/15;
- TypeScript typecheck: exit 0;
- upgraded real installed-Pi two-session read-context test: 1/1.

Full regression results:

- full Pi TypeScript suite: 8 files, 114/114;
- TypeScript package/install suite: 14/14;
- release/package/RPC-process suite: 17/17;
- isolated real-Pi command/alias RPC: 1/1;
- Pi parity: 19/19;
- Pi doctor/backstop: 5/5;
- shared activation/hooklib: 69/69;
- host descriptors: 13/13;
- surface generator unit suite: 34/34;
- shared-core generator unit suite: 12/12 with one platform-conditional skip.

Generation checks remain green: 42 shared core files across three plugins are byte-identical;
Claude/Codex/Pi surfaces are in sync; package metadata matches the descriptor; `git diff --check`
exits 0.

Two consecutive final builds produced identical SHA-256 hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `D698E7F6F660AF680F5A11B4FAD8B00C8FEBCC53144F80243054DA93DE24A2F7` | `D698E7F6F660AF680F5A11B4FAD8B00C8FEBCC53144F80243054DA93DE24A2F7` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| `plugins/ca-pi/tools/package-lock.json` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child bundle and lockfile remain byte-identical to the pre-review values. The parent hash changed
only because it contains the reviewed runtime fixes. One verification attempt invoked the package
build script from the repository root and received the expected `Missing script: build`; it made no
changes. The package-directory build then succeeded before the real-Pi GREEN run.

### Additional files changed by this review loop

- `plugins/ca-pi/tools/src/contracts.ts`
- `plugins/ca-pi/tools/src/tool-guard.ts`
- `plugins/ca-pi/tools/src/bridge.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `plugins/ca-pi/tools/test/bridge.test.ts`
- `.github/scripts/test_pi_package.py`
- `plugins/ca-pi/extensions/codearbiter.js` - deterministically regenerated parent bundle
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-5-report.md`

No dependency, lockfile, production switch, credential access, network route, provider endpoint,
shared governance rule, or child bundle changed. No unresolved local blocker remains for blocker 5
after the independent-review remediation.
