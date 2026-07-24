# Pi support Batch 2 cumulative integration review

Date: 2026-07-15
Branch: `feat/pi-support`
Review mode: fresh read-only review of the current combined Tasks 3-5 workspace, all seven remediation blocks, generated artifacts, tests, durable plan state, and controller evidence

## Verdict

- **Spec compliance: NO**
- **Task verdict: CHANGES REQUIRED**
- **Findings: 0 Critical / 2 Important / 0 Minor**
- **Checkpoint recommendation: DO NOT CLOSE**

The cumulative enforcement, version, activation, read-context, doctor-truthfulness, lifecycle-generation, generation, and packaging work is otherwise coherent. Two cross-path gaps remain: an enforcement-install failure leaves the keyed status active after shutdown, and the doctor report's pre-encoding character cap does not bound the final model-visible envelope. Both contradict explicit Batch 2 checkpoint properties and require fixes plus rereview before Tasks 6-9 can start.

## Strengths

- Python discovery remains behind successful enabled activation, uses the installed package root as the discovery cwd, validates an absolute Python 3 executable, and leaves the dormant doctor transport unprepared (`plugins/ca-pi/tools/src/extension.ts:80-90`, `plugins/ca-pi/tools/src/extension.ts:218-250`, `plugins/ca-pi/tools/src/bridge.ts:268-290`).
- TypeScript activation is pinned to the shared fixture contract and mirrors the canonical Python whitespace, BOM, duplicate-marker, malformed-frontmatter, and Python `re.I` behavior, including U+0130/U+0131 (`plugins/ca-pi/tools/src/activation.ts:4-22`, `core/activation-contract.json`, `.github/scripts/test_hooklib.py`).
- Bootstrap/final enforcement is layered and lifecycle-aware. Opaque object generations protect resolved, rejected, and cancellation-shaped bridge completions; stale mutation cannot execute, stale READ delegates from the current execution context, and stale result effects are suppressed (`plugins/ca-pi/tools/src/tool-guard.ts:90-165`, `plugins/ca-pi/tools/src/tool-guard.ts:205-280`, `plugins/ca-pi/tools/src/tool-guard.ts:322-353`).
- Exact Pi admission is the real default boundary. Canonical package identity and manifest version are authenticated before runtime module evaluation, and only exact `0.80.5`/`0.80.6` proceeds to API loading (`plugins/ca-pi/tools/src/extension.ts:192-202`, `plugins/ca-pi/tools/src/compatibility.ts:9-33`, `plugins/ca-pi/tools/src/runtime-resolver.ts:105-199`).
- Native READ input is normalized only for shared pre-read judgment; Pi's native executor receives its native argument contract, and governed context is appended once per authoritative session without a fabricated READ result bridge (`plugins/ca-pi/hooks/pi-bridge.py:155-167`, `plugins/ca-pi/tools/src/tool-guard.ts:127-163`, `plugins/ca-pi/tools/src/tool-guard.ts:322-353`).
- Doctor wording is truthful: the stored wrapper self-test is distinct from unavailable active-dispatch evidence, `active-dispatch` is always degraded, and Task 5/PI-AC-28 remain blocked (`plugins/ca-pi/tools/src/doctor.ts:354-408`, `.codearbiter/plans/pi-support.md:123`, `.codearbiter/plans/pi-support.md:704-715`).
- The current generated parent contains the same reviewed logic as source and matches the controller's deterministic SHA-256 `4DF7A73C7E681E463B3C64B4A75E81B2F0075E6C7DE7D3ECD1210C847799F535`; the child placeholder and lock also match the controller's recorded hashes.

## Findings

### Critical

None.

### Important

#### 1. Enforcement-install failure leaves the `codearbiter` status active after `session_shutdown`

- **Files:** `plugins/ca-pi/tools/src/extension.ts:93-98`, `plugins/ca-pi/tools/src/extension.ts:149-157`; generated equivalent at `plugins/ca-pi/extensions/codearbiter.js:1299-1304` and `plugins/ca-pi/extensions/codearbiter.js:1353-1361`.
- **Problem:** the install-failure path sets an unhealthy keyed status and then sets `enabled = false`. The shutdown handler clears the status only when `enabled` is true or an alias invocation degradation exists. The retained `bridgeDegraded` enforcement failure is not part of that condition, so shutdown deactivates enforcement but leaves stale UI state in a reused Pi process.
- **Why it matters:** Task 3 requires status to clear on `session_shutdown` (`.codearbiter/plans/pi-support.md:551-555`), and cumulative property 3 requires shutdown to be genuinely inactive (`batch-2-combined-checkpoint-brief.md:14`). A stale unhealthy status incorrectly represents an ended lifecycle and can bleed into the next dormant session.
- **Focused evidence:** invoking the current generated parent with an injected enforcement-install failure and then `session_shutdown` produced only:

  ```json
  [["codearbiter","codeArbiter host: pi starting"],["codearbiter","codeArbiter host: pi unhealthy - enforcement installation failed; run /ca-doctor"]]
  ```

  There was no final `setStatus("codearbiter", undefined)` call. The existing failure/retry test invokes shutdown but asserts only readiness transitions (`plugins/ca-pi/tools/test/activation.test.ts:353-381`); normal and ownership-degraded status tests do not cover the failed-install state (`plugins/ca-pi/tools/test/status.test.ts:151-194`).
- **Remediation:** clear the extension-owned keyed status unconditionally on `session_shutdown`, or track whether this extension has published any status independently of `enabled`. Keep `enabled = false` on the failure path. Add a regression that fails installation, observes the unhealthy status, shuts down, requires a final undefined status, then proves a retry/new lifecycle still works.

#### 2. The doctor limit is applied before escaping, so final model-visible output can exceed the declared bound by about 6x

- **Files:** `plugins/ca-pi/tools/src/extension.ts:161-167`; generated equivalent at `plugins/ca-pi/extensions/codearbiter.js:1364-1369`; incomplete regression at `plugins/ca-pi/tools/test/activation.test.ts:127-149`.
- **Problem:** `safeDiagnostic(report, 16_000)` bounds the decoded report first. `JSON.stringify()` and the subsequent `<`, `>`, `&`, and C1-control escaping then expand retained characters after that bound. The value passed to `sendUserMessage()` therefore has no final-sink size cap.
- **Why it matters:** cumulative property 7 explicitly requires an output bound at the final model-visible sink (`batch-2-combined-checkpoint-brief.md:18`). The present finite pre-encoding cap prevents unbounded growth, but it does not enforce the claimed final boundary and permits avoidable model-context amplification.
- **Focused evidence against the current generated parent:** 40,000-character reports produced these lengths:

  | Input character | Decoded report length | Final model-visible block length |
  |---|---:|---:|
  | `<` | 16,001 | 96,104 |
  | U+0080 | 16,001 | 96,104 |
  | `"` | 16,001 | 32,104 |
  | `\\` | 16,001 | 32,104 |

  The existing adversarial test places only a small amount of markup/control text before ordinary `x` padding, so its `<16,200` assertion does not exercise expansion-heavy retained input.
- **Remediation:** enforce a named maximum on the fully encoded payload/envelope, or truncate the normalized report according to its escaped/JSON-encoded size while preserving valid JSON and one fixed owned boundary. Add expansion-heavy cases for markup, C1 controls, quotes, and backslashes and assert the complete string passed to `sendUserMessage()` stays within the final limit.

### Minor

None.

## Cumulative acceptance matrix

| # | Required property | Result | Evidence / assessment |
|---:|---|---|---|
| 1 | No pre-activation Python discovery, bridge execution, or project-cwd interpreter trust | PASS | Deferred resolver in `extension.ts:218-260`; safe discovery cwd and absolute result in `bridge.ts:268-290`; dormant/poisoned-cwd coverage is present in `activation.test.ts` and `package.test.ts`. |
| 2 | One canonical TypeScript/Python activation contract, including Unicode case behavior | PASS | Shared `core/activation-contract.json`; TypeScript parser at `activation.ts:4-22`; Python and TypeScript consumers cover Python-specific whitespace and the exact U+0049/U+0069/U+0130/U+0131 set. |
| 3 | Fail-closed bootstrap; dormant/shutdown inactivity; safe partial installs/retries | **FAIL** | Enforcement itself is fail closed and lifecycle-aware, but finding 1 leaves extension-owned status state active after shutdown on the install-failure path. |
| 4 | Exact Pi `0.80.5`/`0.80.6` admission before module/API access; authentic provenance/canary | PASS | Exact set at `compatibility.ts:9-25`; two-phase identity/load at `runtime-resolver.ts:105-199`; default ordering at `extension.ts:192-202`; supported matrix and latest canary are structurally validated. |
| 5 | Canonical tool/read contract; native execution; bounded/redacted context once per authoritative session | PASS | READ-only normalization at `pi-bridge.py:155-167`; native execution/result patch at `tool-guard.ts:127-163`; authoritative/fallback session handling at `tool-guard.ts:65-80` and `217-253`; two-session real-Pi proof recorded by controller. |
| 6 | Truthful doctor evidence; wrapper self-test distinct; PI-AC-28/Task 5 blocked | PASS | Permanent degraded row at `doctor.ts:360-365`; exact wrapper test at `doctor.ts:374-408`; plan ledger remains blocked at `pi-support.md:123` and Task 5 at `:704-715`. |
| 7 | Shared doctor redaction/control handling and explicit final-sink bound | **FAIL** | Shared redaction and control escaping are present, but finding 2 proves the complete model-visible envelope exceeds the intended limit after encoding. |
| 8 | Opaque lifecycle generations across resolved/rejected/cancelled work | PASS | Object identity minted/cleared at `tool-guard.ts:238-253`; wrapper and result completion checks at `:127-163` and `:334-352`; focused tests cover resolution, rejection, AbortError-shaped cancellation, and same-generation propagation. |
| 9 | Deterministic/generated parity and internally consistent metadata/artifacts | PASS | Controller's full generation checks passed; current parent/child/lock hashes match the recorded deterministic hashes; root/nested metadata agree at version `0.1.0` with no runtime Pi dependency. |
| 10 | Preserve user dirt; no staging or prohibited git/release action | PASS | Current branch is `feat/pi-support`; cached diff is empty; the pre-existing modified governance files, scratch artifact, and four named temp directories remain present. Current state and controller ledger support the no-stage/no-switch/no-clean claim. |

## Task and durable-plan assessment

- **Task 3:** cumulative approval is reopened by finding 1. Activation, persona, aliases, ownership, and normal status behavior otherwise match the accepted task.
- **Task 4:** remains task-compliant in the combined state. Canonical mapping, final-execution authority, bridge failure direction, bootstrap protection, and lifecycle-generation remediation integrate coherently.
- **Task 5:** PI-AC-15 and PI-AC-16 remain supported; Task 5 and PI-AC-28 correctly remain **BLOCKED** for the accepted active-dispatch limitation. Finding 2 additionally blocks the combined checkpoint's doctor-output requirement.
- **Tasks 6-9:** have not started. Their plan cells remain `PENDING` (`.codearbiter/plans/pi-support.md:803-1063`), and the planned `child-env.ts`, `runner.ts`, `roles.ts`, `compaction.ts`, and corresponding test files are absent. The existing four-line `child-extension.ts` is the previously declared placeholder, not Task 6 implementation.

## Test-evidence assessment

The controller's current cumulative matrix is broad and internally consistent: Pi 123/123, typecheck, real package/RPC 17/17, command RPC 1/1, parity 19/19, doctor/backstop 7/7, hooklib 69/69, descriptors 13/13, sync-core 13 with one expected skip, and surface 34/34. The real-Pi fault injection, unsupported-runtime module-evaluation sentinel, two-session READ capture, parsed doctor envelope, source-drift checks, and lifecycle deferred-bridge tests are materially authentic rather than prose-only assertions.

The matrix nevertheless has two precise blind spots:

1. The enforcement-failure lifecycle test checks deactivation/retry but not the keyed status after shutdown.
2. The doctor-envelope test checks one mixed adversarial input whose retained 16,000-character tail is ordinary text; it does not test worst-case JSON/markup expansion.

No broad suite was rerun during this review because the controller had just run it on the same cumulative bytes. Two focused read-only probes against the current generated parent reproduced the findings above.

## Known honest limitation

Supported Pi 0.80.5/0.80.6 public extension APIs expose no deterministic command-side active tool-dispatch method. The stored wrapper self-test therefore does not prove active-dispatch behavior. The current `active-dispatch` diagnosis must remain `DEGRADED`, PI-AC-28 and Task 5 must remain blocked, and Task 13 must supply supported-version real-host/promotion evidence. This limitation is represented truthfully and is not itself a new finding.

## Final checkpoint recommendation

Do not close Batch 2 and do not start Tasks 6-9. Fix both Important findings test-first, deterministically rebuild the parent bundle, rerun the affected status/activation tests plus the controller's relevant backstops, and return this same cumulative integration reviewer to the current workspace for rereview. The checkpoint can advance to user acknowledgement only after this review and the parallel cumulative security review are both clean.

---

## Rereview — 2026-07-15

### Verdict

- **Reviewed remediation report SHA-256:** `9A23386EC363CFFB8579D322D8105FB8A67956430FD1B126EE596A60C3C7A9F7`
- **Spec compliance: YES**
- **Task verdict: APPROVED**
- **New or remaining findings: 0 Critical / 0 Important / 0 Minor**
- **Checkpoint recommendation: ADVANCE TO USER ACKNOWLEDGEMENT**

The author remediation closes both original Important findings and the controller-added activation/settings and executable-identity boundaries. No replacement defect was found in the affected paths. The known active-dispatch limitation remains represented honestly as `DEGRADED`; PI-AC-28 and the Task 5 promotion cell remain `BLOCKED` exactly as the approved plan requires. This accepted limitation is not a Batch 2 remediation failure and must not be relabeled as active-dispatch proof.

### Remediation verification

| Boundary | Rereview result | Independent evidence |
|---|---|---|
| Failed-start status cleanup | **CLOSED** | Status ownership is tracked independently of `enabled`; a new start clears previously published state before activation, and shutdown clears any extension-published keyed status (`plugins/ca-pi/tools/src/extension.ts:71-83`, `:94-104`, `:111-116`, `:167-171`). The regression exercises failed activation, dormant reuse, a second failure, and shutdown (`plugins/ca-pi/tools/test/status.test.ts:185-219`). |
| Complete doctor-envelope bound | **CLOSED** | Redaction precedes sizing, JSON/markup escaping is included in the measured value, truncation is surrogate-safe, the marker remains inside valid JSON, and the complete fixed-delimiter block is capped at 16,000 UTF-8 bytes (`plugins/ca-pi/tools/src/extension.ts:174-204`). Expansion-heavy markup, quotes, backslashes, C1 controls, and multibyte payloads are covered against the final block (`plugins/ca-pi/tools/test/activation.test.ts:153-168`). |
| Activation overlap and stale settings | **CLOSED** | `beginActivation()` creates a blocked generation before the asynchronous activation check; retained mutators fail closed, retained reads recreate a native definition from the current execution cwd with untrusted settings, and every enabled generation receives newly constructed trusted factories (`plugins/ca-pi/tools/src/tool-guard.ts:92-169`, `:186-217`, `:220-303`; `plugins/ca-pi/tools/src/extension.ts:340-369`). The retained-handle/current-settings regression covers activation-await, same-cwd reactivation, stale reads, stale writes, and absence of stale bridge use (`plugins/ca-pi/tools/test/tool-guard.test.ts:279-338`). |
| Bridge executable boundary | **CLOSED** | Git and Python discovery accept only absolute canonical executable identities outside the governed project; the bridge revalidates them per request, runs absolute Python from the trusted package root, passes an absolute-only PATH plus explicit identities, and resolves the Windows tree-kill helper absolutely (`plugins/ca-pi/tools/src/bridge.ts:40-123`, `:179-199`, `:245-279`, `:367-403`). Shared Python consumes `_gitexec.git_executable()` and managed hooks carry the absolute Git/Python identities (`core/pysrc/_gitexec.py:16-37`, `core/pysrc/_githooks.py:117-124`, `:150-173`). The real Windows package canary proved a project-local `git.exe` was not selected or executed and that the managed hook ran with the embedded identities. |
| Deterministic generation and host parity | **CLOSED** | `sync-core --check` reports 43 canonical files byte-identical across all three plugins; surface and descriptor checks pass. Two independent `npm run build` executions retained parent SHA-256 `51C3861E74DC79F143D8CDE22DC7E11E78F06B27859833AEAA77555121C7B0E8`, child SHA-256 `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`, and lock SHA-256 `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`. |

### Cumulative acceptance matrix after remediation

| # | Required property | Result | Rereview note |
|---:|---|---|---|
| 1 | No pre-activation Python discovery, bridge execution, or project-cwd interpreter trust | PASS | Preserved; the strengthened Git/Python resolver and package-root bridge cwd close the project-executable path as well. |
| 2 | One canonical TypeScript/Python activation contract, including Unicode case behavior | PASS | Preserved; parity and full Pi tests remain green. |
| 3 | Fail-closed bootstrap; dormant/shutdown inactivity; safe partial installs/retries | PASS | The original stale-status failure is closed, and activation-await mutation is now blocked before `isEnabled()` settles. |
| 4 | Exact Pi `0.80.5`/`0.80.6` admission before module/API access; authentic provenance/canary | PASS | Preserved by the cumulative package and descriptor tests. |
| 5 | Canonical tool/read contract; native execution; bounded/redacted context once per authoritative session | PASS | Preserved; refreshed factories do not change the native execution contract. |
| 6 | Truthful doctor evidence; wrapper self-test distinct; PI-AC-28/Task 5 blocked | PASS | Doctor/backstop tests remain green; no active-dispatch claim was introduced. |
| 7 | Shared doctor redaction/control handling and explicit final-sink bound | PASS | The full encoded model-visible block is now `<= 16,000` UTF-8 bytes for every adversarial fixture. |
| 8 | Opaque lifecycle generations across resolved/rejected/cancelled work | PASS | Preserved and extended through the activation-check interval and retained settings handles. |
| 9 | Deterministic/generated parity and internally consistent metadata/artifacts | PASS | Rebuilt twice with unchanged parent, child, and lock hashes; sync/surface/descriptor gates pass. |
| 10 | Preserve user dirt; no staging or prohibited git/release action | PASS | Branch remains `feat/pi-support`; cached diff count is zero; no branch, commit, clean, reset, push, tag, or release action occurred during rereview. |

### Independent verification run

| Command | Result |
|---|---|
| `npm test -- --run test/activation.test.ts test/status.test.ts test/bridge.test.ts test/tool-guard.test.ts` (`plugins/ca-pi/tools`) | GREEN, 76/76 |
| `npm run typecheck` (`plugins/ca-pi/tools`) | GREEN |
| `npm test -- --run` (`plugins/ca-pi/tools`) | GREEN, 134/134 |
| `python .github/scripts/test_pi_package.py -v` | GREEN, 19/19, including real isolated RPC, enforcement-failure, and Windows Git poison tests |
| `python .github/scripts/test_pi_parity.py -v` | GREEN, 19/19 |
| `python .github/scripts/test_pi_doctor.py -v` | GREEN, 7/7 |
| `python plugins/ca/hooks/tests/test_git_hooks.py -v` | GREEN, 34/34 |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` | GREEN, 932/932 |
| `python tools/sync-core.py --check` | GREEN, 43 files x 3 plugins byte-identical |
| `python tools/build-host-packages.py --check` | GREEN |
| `python tools/build-surface.py --check` | GREEN |
| `python .github/scripts/test_build_surface.py -v` | GREEN, 34/34 |
| `python .github/scripts/test_host_descriptors.py -v` | GREEN, 13/13 |
| `npm run build` twice with SHA-256 checks (`plugins/ca-pi/tools`) | GREEN, byte-deterministic with the hashes recorded above |

### Scope and durable-plan check

Tasks 6, 7, 8, and 9 remain `PENDING` in `.codearbiter/plans/pi-support.md:803-1068`. Every create/generated file listed by those four tasks is absent, including the child environment/runner/roles, dispatch/process-tree, prune/compaction, and farm/shared-store implementations and tests. The existing `child-extension.ts`, `extension.ts`, `bridge.ts`, and surface-generator changes remain attributable to the approved Tasks 2-5 work and this remediation; no Task 6-9 implementation seam has been started. The Git index is empty.

### Final rereview recommendation

Close the cumulative Batch 2 implementation/security remediation review and advance to the required user acknowledgement. Do not infer active-dispatch coverage from this approval: Task 5/PI-AC-28 retain their explicit blocked/degraded state until the later supported-version real-host promotion evidence exists. Tasks 6-9 may begin only after that acknowledgement gate.

---

## Final trust/config integration rereview — 2026-07-15

### Verdict

- **Reviewed trust/config fix report SHA-256:** `B919027A41DCCA51CEB4CACA3D6E21A073BBFEF81135704A12BB6B36436BBA88`
- **Spec compliance: YES**
- **Task verdict: APPROVED**
- **New or remaining integration findings: 0 Critical / 0 Important / 0 Minor**
- **Integration gate recommendation: ACCEPT**

The prior security HIGH is closed in the cumulative implementation without reopening either original integration finding or any previously accepted Batch 2 behavior. Global Pi extension loading is now discovery only: repository-aware authorization begins only after canonical activation and an affirmative current host trust result. The integration side is clean; the controller should still require the separately assigned final security rereview before treating the overall security checkpoint as closed.

### Trust/config boundary verification

| Required behavior | Result | Independent evidence |
|---|---|---|
| Dormant lifecycle is silent | **PASS** | Every start invalidates prior state, enters an activation-check generation, and clears cached bridge identities, but marker absence immediately deactivates without status, notification, bridge, persona, or repository work (`plugins/ca-pi/tools/src/extension.ts:105-115`). The dormant regression asserts zero preparation, bridge calls, user messages, and status calls (`plugins/ca-pi/tools/test/activation.test.ts:201-221`). |
| Enabled missing/false/failing trust stays before the repository boundary | **PASS** | `hasAffirmativeProjectTrust` accepts only the literal result `true` and converts missing or throwing signals to false (`plugins/ca-pi/tools/src/extension.ts:49-57`). The trust check occurs after filesystem-only `isEnabled` and before bootstrap, ownership inspection, bridge preparation, enforcement installation, persona loading, and shared startup (`plugins/ca-pi/tools/src/extension.ts:105-138`). Missing and false unit fixtures observe only the in-memory bridge reset and activation guard, with zero preparation/enforcement/persona/bridge calls (`plugins/ca-pi/tools/test/activation.test.ts:223-263`). |
| Mutations remain fail closed and reads remain fresh/untrusted/native | **PASS** | The activation-check generation remains active on the trust-wait return. Retained mutators reject before bridge/native execution; retained reads recreate the native definition at the execution cwd through `projectTrusted: false`, with no bridge decoration or stale settings (`plugins/ca-pi/tools/src/tool-guard.ts:92-169`, `:220-277`; `plugins/ca-pi/tools/src/extension.ts:369-400`). The retained-handle regression covers both directions and current settings (`plugins/ca-pi/tools/test/tool-guard.test.ts:279-338`). |
| Trust status and doctor are truthful and side-effect free | **PASS** | Enabled-untrusted startup publishes and notifies one fixed redacted `/trust` direction (`plugins/ca-pi/tools/src/extension.ts:49`, `:116-119`). Doctor recomputes affirmative trust, marks bridge unprepared, reports Python/bridge/final-wrapper checks as intentionally withheld, and skips the wrapper self-test (`plugins/ca-pi/tools/src/extension.ts:331-367`; `plugins/ca-pi/tools/src/doctor.ts:128-147`, `:244-395`, `:398-421`). Unit evidence records zero bridge/wrapper calls (`plugins/ca-pi/tools/test/doctor.test.ts:241-289`). |
| False-to-true and ordinary trusted starts refresh normally | **PASS** | Every start drops cached Python, Git, and bridge objects before trust evaluation; affirmative trust then creates a fresh bootstrap generation and fresh trusted/untrusted factories (`plugins/ca-pi/tools/src/extension.ts:105-125`, `:303-330`, `:369-400`). Same-process false-to-true coverage observes a status clear followed by exactly one fresh prepare/enforce/persona/shared-start sequence (`plugins/ca-pi/tools/test/activation.test.ts:265-318`). |
| Real untrusted and trusted Windows paths agree with the unit boundary | **PASS** | The installed-package untrusted RPC test observed no pre-commit/pre-push hook, hook-discovery cache, `FETCH_HEAD`, or shared startup marker, while returning exactly the fixed trust status and withheld doctor rows (`.github/scripts/test_pi_package.py:1254-1322`). The existing trusted Windows canary still proves project-local `git.exe` is not selected and the managed hook executes with absolute Git/Python identities (`.github/scripts/test_pi_package.py:1501`). Both passed inside the fresh 20/20 package run. |

The activation-check guard itself is deliberately active before trust so mutations cannot race the asynchronous marker/trust decision. That adapter-local fail-closed state is not repository-aware enforcement installation and performs no Python, Git, bridge, hook, persona, or shared-core work.

### Governance consistency

The four governing artifacts now state one compatible invariant:

- `.codearbiter/specs/pi-support.md:183-191`, `:207-221`, and `:261-265` distinguish global discovery from authorization, require literal affirmative trust, define dormant/untrusted behavior, and require a fresh false-to-true activation.
- `.codearbiter/specs/pi-support-review.md:35-41` adds a dated correction to the historical review: global load timing does not authorize repository activity, and doctor must remain pre-bridge/pre-wrapper while untrusted. The original M0 trust question remains part of the historical review record; the dated correction is the document's current resolution and does not contradict the other artifacts.
- `.codearbiter/plans/pi-support.md:176-184`, `:541-546`, and `:796-806` place the same trust gate before bridge/shared startup and preserve the side-effect-free doctor requirement.
- `.codearbiter/security-controls.md:276-289` defines the same default-deny control, including missing/false/failing trust, fresh untrusted reads, fixed redacted direction, and project-local load-time trust plus adapter authorization.

No document grants trust, treats global load as authorization, permits pre-trust Git inspection, or claims active-dispatch evidence.

### Independent verification run

| Command | Result |
|---|---|
| `npm test -- --run test/activation.test.ts test/doctor.test.ts test/status.test.ts test/tool-guard.test.ts` (`plugins/ca-pi/tools`) | GREEN, 81/81 |
| `npm run typecheck` (`plugins/ca-pi/tools`) | GREEN |
| `npm test -- --run` (`plugins/ca-pi/tools`) | GREEN, 138/138 |
| `python .github/scripts/test_pi_package.py -v` | GREEN, 20/20; includes authentic enabled-untrusted RPC and trusted Windows identity/hook canaries |
| `python .github/scripts/test_pi_parity.py -v` | GREEN, 19/19 |
| `python .github/scripts/test_pi_doctor.py -v` | GREEN, 7/7 |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` | GREEN, 932/932 |
| `python tools/sync-core.py --check` | GREEN, 43 canonical files x 3 plugins byte-identical |
| `python tools/build-host-packages.py --check` | GREEN |
| `python .github/scripts/test_host_descriptors.py -v` | GREEN, 13/13 |
| `python .github/scripts/test_build_surface.py -v` | GREEN, 34/34 |
| `npm run build` twice with SHA-256 checks (`plugins/ca-pi/tools`) | GREEN, byte-deterministic |
| `git diff --check` | GREEN |

The two fresh builds retained the fix report's exact artifacts:

- parent: `FE70C2B22E5925D4A5E6A7CC3026930E5E87EA36822F632C5BFBB611A31C9973`
- child: `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`
- lock: `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`

The generated parent contains the same fixed trust direction and literal `isProjectTrusted?.() === true` gate as the reviewed TypeScript source.

### Scope and workspace integrity

Tasks 6 through 14 remain `PENDING` at `.codearbiter/plans/pi-support.md:820-1455`. Every create/generated file assigned to those tasks is absent, including child isolation, dispatch/process-tree, compaction/prune, farm/store, security/static-analysis, benchmark/platform, public-doc, promotion-evidence, and final-verifier artifacts. The trust/config pass did not start a later implementation seam.

The branch remains `feat/pi-support`, the Git index is empty, and `git diff --check` passes. This rereview made no implementation edit, stage, commit, branch switch, reset, clean, stash, push, tag, publish, or release action; the only write is this required durable rereview section.

### Final integration recommendation

Accept the final Batch 2 integration rereview. The trust/config HIGH is integrated cleanly, all cumulative Batch 2 acceptance properties remain satisfied, deterministic artifacts match, and Tasks 6-14 remain untouched. Preserve the honest `active-dispatch: DEGRADED` diagnosis and Task 5/PI-AC-28 promotion stop, obtain the parallel final security acceptance, and only then advance through the controller's acknowledgement gate into later tasks.
