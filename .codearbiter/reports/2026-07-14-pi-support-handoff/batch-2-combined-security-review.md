# Pi support Batch 2 cumulative security review

Date: 2026-07-15
Branch: `feat/pi-support`
Reviewer: security reviewer
Scope: cumulative Tasks 3-5 / Batch 2 workspace
Verdict: **BLOCK**

## Executive verdict

The cumulative Batch 2 implementation is not ready to pass the security gate. The review found one critical poisoned-working-directory execution path, one medium lifecycle/settings control gap, and one low final-sink size-bound gap.

| Severity | Count |
|---|---:|
| CRITICAL | 1 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 1 |

The controller's green suites and deterministic-build evidence remain valid for the behaviors they cover. They do not exercise the critical Windows executable-search path, the stale native-tool settings lifecycle, or the worst-case post-encoding doctor envelope.

## Findings

### CRITICAL — Project-controlled `git.exe` can execute from the bridge working directory

**Control:** `.codearbiter/security-controls.md:287-290` requires subprocesses to use absolute executables and explicit cwd. `.codearbiter/specs/pi-support.md:118-122` repeats the absolute-executable, minimal-environment, bounded-process contract. The combined checkpoint additionally requires that poisoned project cwd not become an execution trust source.

**Evidence:**

- `plugins/ca-pi/tools/src/bridge.ts:173-180` correctly launches an absolute Python interpreter and bridge script, but sets the Python process cwd to attacker-controlled `request.cwd`.
- `plugins/ca-pi/tools/src/bridge.ts:38-42` copies ambient `PATH`, `PATHEXT`, and Windows process-search variables into the child environment.
- Shared Python reached by an enabled `session_start` launches Git by bare name at `plugins/ca-pi/hooks/session-start.py:145-154` and `plugins/ca-pi/hooks/_githooks.py:116-121`.
- A harmless Windows proof copied the trusted `where.exe` binary to a temporary project directory as `git.exe`, then invoked the same Python `subprocess.run(["git", ...])` shape. From a clean cwd, real Git ran and returned its normal non-repository error. From the poisoned cwd, the copied executable ran instead. No repository file was changed.

This allows repository content to select an arbitrary executable during enabled bridge activation. The bridge's absolute Python path does not protect subprocesses launched later by Python. Because execution of attacker-controlled code is possible, severity is CRITICAL.

**Required remediation:**

1. Resolve and validate a trusted absolute Git executable outside project-controlled search locations, then pass/use that absolute path for every shared Python Git invocation. Do not rely on `PATH` ordering alone.
2. Keep the governed repository path in the canonical payload and explicit Git `-C`/`cwd` argument, but run the bridge process itself from a validated trusted package directory.
3. Sanitize process-search inputs to absolute, non-relative trusted paths. Treat empty/relative `PATH` elements and project-local executable resolution as invalid.
4. Add a live Windows canary that places a sentinel `git.exe` in the project root, reaches the enabled `session_start` bridge path, and proves that the sentinel never executes. Cover every Python helper that shells out to Git.

**Triage note:** `[NEEDS-TRIAGE]` The same shared bare-Git helpers may present an analogous search-path risk for existing Claude/Codex hook launchers. That broader question does not reduce or defer the Pi finding: the Pi adapter explicitly creates the unsafe project-cwd process boundary.

### MEDIUM — Native-tool factories capture session settings without a proven lifecycle invalidation boundary

**Control:** The combined checkpoint requires bootstrap, dormant, shutdown, partial-install, retry, and lifecycle-generation behavior to remain fail closed. Native execution must use the current authoritative execution context, including after shutdown/reactivation.

**Evidence:**

- `plugins/ca-pi/tools/src/extension.ts:295-300` creates one cwd- and trust-bound `SettingsManager` during `installEnforcement`.
- `plugins/ca-pi/tools/src/extension.ts:301-311` closes the native bash/read factories over that settings object. Shell prefix, shell path, and image-resize policy are therefore snapshots, not properties resolved from the current execution context.
- `plugins/ca-pi/tools/src/extension.ts:149-157` deactivates readiness on shutdown but does not explicitly invalidate the registered native wrappers or their captured factories.
- `plugins/ca-pi/tools/src/extension.ts:80-102` requests installation again on a later enabled `session_start`, but the adapter has no direct, tested invariant proving that every supported host lifecycle replaces same-cwd wrappers and makes dormant cross-cwd handles unreachable before native execution.

Source inspection is consistent with supported Pi normally disposing the old extension runner during session replacement and constructing a new cwd-bound runtime. Same-cwd activation also calls `installEnforcement` again. Those host behaviors reduce practical exposure, but the adapter-owned control is not self-contained or dynamically proven. In particular, same-cwd reloads can retain changed trust/config snapshots if a wrapper is reused, and a surviving dormant handle can retain old-cwd shell/read settings until the host disposes it. This is a security-path lifecycle/coverage gap, not a demonstrated current code-execution exploit, so severity is MEDIUM.

**Required remediation:**

1. Do not close native factories over a session-scoped `SettingsManager`. Resolve settings from the current authoritative cwd/trust context at execution time, or generation-bind each factory and reject it after deactivation.
2. Explicitly invalidate/unregister built-in wrappers on shutdown and before reactivation, then rebuild them on every enabled activation, including same-cwd reloads and changed trust/config.
3. Add supported-runtime tests for: same-cwd reactivation after shell/read settings change; trust-state change; cross-cwd session replacement; invocation through a retained pre-shutdown tool handle; and partial/rejected/cancelled installation. The stale handle must block or use only current settings, never the captured prior-session settings.

### LOW — Doctor's 16,000-character cap is applied before JSON escaping, so the final envelope can expand to about 96 KiB

**Control:** The combined checkpoint brief at `.codearbiter/reports/2026-07-14-pi-support-handoff/batch-2-combined-checkpoint-brief.md:18` requires an explicit bound at the final model-visible sink.

**Evidence:**

- `plugins/ca-pi/tools/src/extension.ts:161-167` applies `safeDiagnostic(..., 16_000)` before `JSON.stringify` and then expands each `<`, `>`, `&`, and C1 character to a six-character `\uXXXX` sequence.
- `plugins/ca-pi/tools/test/activation.test.ts:127-149` uses only a small number of escapable characters before a long ASCII tail, then asserts a final block length below 16,200. It does not cover an all-escaping adversarial input.
- The integration reviewer confirmed that 40,000 `<`, `>`, or `&` characters produce a decoded report of 16,001 characters but a final block of 96,104 characters / 96,106 UTF-8 bytes. A plain-ASCII input produces a 16,104-character block.

The output remains redacted, JSON-encoded, delimiter-safe, and globally finite; there is no demonstrated secret leak or injection. The flaw is bounded output amplification and inaccurate final-sink enforcement, so severity is LOW.

**Required remediation:**

1. Enforce the declared limit on the fully encoded, model-visible UTF-8 envelope, or reserve the maximum escape-expansion budget before encoding.
2. Preserve valid JSON and the single fixed delimiter; do not truncate encoded JSON mid-string.
3. Add adversarial all-escape and multibyte fixtures that assert the byte length of the complete final block, not only decoded report characters.

## Boundary analysis

### Pre-trust activation and Python discovery

The earlier poisoned-Python-candidate issue is fixed: bridge preparation occurs only after canonical enabled activation, Python discovery uses the trusted package-root cwd, and the resolved interpreter is absolute. Dormant doctor inspection does not prepare the bridge or execute Python. This boundary is clean except for the later bare-Git subprocess finding above.

### Exact runtime identity and API ordering

Runtime identity is anchored to the absolute launched Pi entrypoint and canonical package metadata. Only exact Pi `0.80.5` and `0.80.6` identities are accepted. Compatibility and before/after identity checks occur before importing/evaluating the runtime API, closing the earlier wrong-runtime and time-of-check/time-of-use paths.

### Package and provenance

The shipped Pi adapter remains private and dependency-free; build/test tools are exactly locked with registry, integrity, and license evidence. Install/provenance tests use isolated package installation and scripts are disabled in CI. No Pi runtime is bundled. The controller recorded deterministic hashes:

- Parent bundle: `4DF7A73C7E681E463B3C64B4A75E81B2F0075E6C7DE7D3ECD1210C847799F535`
- Child placeholder: `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`
- Dependency lock: `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`

### Trust and project-local state

The adapter does not grant trust. It passes Pi's current `isProjectTrusted` result into `SettingsManager`, and doctor reports untrusted project-local state honestly. The trust handoff is clean, subject to the stale captured-settings finding.

### Unknown/mutating tools, bootstrap, and final arguments

The bootstrap guard is installed before parent enforcement setup and blocks potentially mutating tools until readiness. Unknown tools fail closed. Ready wrappers bridge and then execute the identical canonical final-argument snapshot. Dormant state is inactive. Opaque lifecycle generations suppress stale results and prevent stale mutators across resolved, rejected, and cancelled bridge work; same-generation failures remain visible. No additional bypass was found.

### Native READ context

Native READ remains native. Only the canonical `path` to `file_path` normalization is applied; native arguments are otherwise unchanged. Authoritative session identity, rotating fallback identity, deduplication, redaction, and the 16 KiB governed-context cap prevent cross-session replay and duplicate model-visible context. This boundary is clean.

### Bridge schema, IPC, process cleanup, and logging

Request and response schemas reject extra/duplicate keys, non-finite JSON, over-depth structures, oversized containers, and stream overflow. Cancellation/timeout terminate the process tree. Audit/log output uses fixed reason codes and byte counts rather than raw stderr, request bodies, prompts, auth material, or provider secrets. The bridge is clean except for the critical bare-Git executable resolution.

### Doctor truthfulness

Doctor distinguishes the stored-wrapper self-test from unsupported active-dispatch live fire and reports exact runtime/package/trust/core/command/bridge status. Redaction and delimiter safety are effective. The only additional issue is the low final-envelope bound finding.

### CI and release canaries

CI actions are SHA-pinned, install scripts are disabled, exact supported Pi versions run on all three operating systems, and latest-Pi compatibility is nonblocking. Static-analysis Task 10 remains planned; it is not evidence for this Batch 2 checkpoint and must complete before promotion.

## Accepted and pending boundaries

- `active-dispatch` remains honestly `DEGRADED`: supported Pi `0.80.5`/`0.80.6` public APIs expose no deterministic active-dispatch submission method. PI-AC-28 and Task 5 remain blocked pending Task 13 real-host/promotion evidence. This accepted limitation is still a promotion STOP.
- The generated child is intentionally still an empty placeholder and Task 6 child-process/env hardening is pending. No child runner exists yet to review. This is out of Batch 2 scope, but child/env security cannot be marked complete or promoted.
- Static analysis in PI-AC-30 / Task 10 is pending and cannot be inferred from unit/integration green status.

## Gate

**BLOCK.** Remediate the CRITICAL, MEDIUM, and LOW findings, add the specified adversarial/lifecycle fixtures, rerun the cumulative controller matrix on the resulting source and generated parent bundle, and obtain a fresh security rereview. The accepted `active-dispatch` limitation and pending child/env work remain independent promotion stops even after these findings close.

---

## Security rereview — 2026-07-15

Fix report: `batch-2-combined-fix-report.md`
Verified SHA-256: `9A23386EC363CFFB8579D322D8105FB8A67956430FD1B126EE596A60C3C7A9F7`
Rereview verdict: **BLOCK**

### Rereview severity summary

| Severity | Open | Disposition |
|---|---:|---|
| CRITICAL | 0 | Original CRITICAL closed |
| HIGH | 1 | New residual trust-boundary finding |
| MEDIUM | 0 | Original MEDIUM closed |
| LOW | 0 | Original LOW closed |

### Original finding dispositions

#### Original CRITICAL — project-cwd executable search: CLOSED

The implemented boundary meets the executable-identity portion of the fix brief:

- `plugins/ca-pi/tools/src/bridge.ts:38-58` constructs a reduced child environment from the two validated executable directories and Windows System32, carries explicit Git/Python identities, and does not copy ambient `PATH`, `PATHEXT`, `ComSpec`, provider variables, or project-relative search entries.
- `plugins/ca-pi/tools/src/bridge.ts:65-111` considers only absolute PATH entries, canonicalizes candidates, and excludes candidates inside the governed project. Empty, relative, missing, and project-contained candidates are ignored.
- `plugins/ca-pi/tools/src/bridge.ts:119-150` resolves Windows process-tree termination to an absolute canonical System32 executable and never performs a bare helper lookup in production.
- `plugins/ca-pi/tools/src/bridge.ts:179-198` canonicalizes the supplied Git, Python, package, and bridge paths; `plugins/ca-pi/tools/src/bridge.ts:253-276` rechecks Git/Python against each request project and starts Python from the canonical package root with `shell: false`.
- `core/pysrc/_gitexec.py:12-37` validates the carried absolute Git identity. Source inspection and an AST inventory confirmed that every shared-core Git `subprocess.run`/`Popen` path now calls `git_executable()`; the only other Pi-reachable process spawn uses absolute `sys.executable` for a package-owned script.
- `core/pysrc/_githooks.py:117-121` uses that identity for hook discovery, while `core/pysrc/_githooks.py:150-181` embeds and re-exports the validated Git/Python identities and directly executes the absolute Python path. The legacy Claude/Codex shim remains the fallback only when the identity channel is absent.
- The authentic checked-in Windows installed-package canary passed and exercised enabled real RPC startup plus the installed managed hook with project PATH poisoning while confirming the project-local executable was not selected.

The current deterministic identities also match the fix report:

- Parent bundle: `51C3861E74DC79F143D8CDE22DC7E11E78F06B27859833AEAA77555121C7B0E8`
- Child placeholder: `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`
- Canonical/generated `_gitexec.py`: `1350E81C95D7168504D0187096CC75E818BDFAEFD20385AC2EDAC3FDF82E0C85`

The alternate Git-config execution boundary described below is distinct: it occurs after the correct absolute Git binary has started.

#### Original MEDIUM — captured native settings and lifecycle overlap: CLOSED

- `plugins/ca-pi/tools/src/extension.ts:341-365` creates settings inside each native factory for the execution root. Active factories use only the current activation's trust result; dormant/bootstrap/stale factories force `projectTrusted: false`.
- `plugins/ca-pi/tools/src/tool-guard.ts:91-159` binds each wrapper to an opaque lifecycle generation. A stale or bootstrap mutator blocks while a stale read resolves a fresh native factory from the current execution cwd with no stale bridge decoration.
- `plugins/ca-pi/tools/src/tool-guard.ts:212-252` creates distinct activation/bootstrap generations and refreshes wrapper definitions for the new generation, including same-cwd reactivation.
- `plugins/ca-pi/tools/src/extension.ts:94-114` invalidates the prior generation and enters activation-check blocking synchronously before awaiting activation detection. Failed/partial installation remains in a blocked generation until shutdown or retry.
- The checked-in tests cover current-cwd dormant reads, same-cwd trust/settings refresh, retained old handles, the activation-check overlap, stale resolved/rejected/cancelled work, partial installation, retries, and unchanged same-generation error propagation.

#### Original LOW — final doctor envelope: CLOSED

- `plugins/ca-pi/tools/src/extension.ts:167-204` redacts first, encodes the complete JSON/delimiter envelope, measures UTF-8 bytes, and selects a Unicode-safe prefix with a visible in-JSON truncation marker. The returned block is valid JSON with exactly one fixed boundary and is at most 16,000 UTF-8 bytes.
- `plugins/ca-pi/tools/test/activation.test.ts:127-167` covers secret/control redaction, markup, quotes, backslashes, C1 characters, and multibyte input against the complete final block.

#### Failed-start status cleanup: CLOSED

- `plugins/ca-pi/tools/src/extension.ts:67-93` tracks keyed status ownership independently of `enabled` and resets all parent session fields.
- `plugins/ca-pi/tools/src/extension.ts:94-100` clears a previously published status before a reused session begins; `plugins/ca-pi/tools/src/extension.ts:163-166` clears any owned status on shutdown even after failed activation.
- `plugins/ca-pi/tools/test/status.test.ts:168-214` proves a never-published dormant lifecycle is silent and failed-start status clears on both a later dormant start and shutdown.

### HIGH finding (1)

**Severity:** HIGH
**File:** `plugins/ca-pi/tools/src/extension.ts:94-120`; `core/pysrc/session-start.py:147-155`; `core/pysrc/session-start.py:185-214`; `core/pysrc/session-start.py:595-604`; `core/pysrc/session-start.py:697-704`; `core/pysrc/_gitlib.py:104`; `core/pysrc/_githooks.py:134-142`
**Description:** An enabled global extension does not require an affirmative Pi project-trust result before it prepares the bridge and executes the shared `session_start` entry. `context.isProjectTrusted()` is consulted only later for native `SettingsManager` construction at `plugins/ca-pi/tools/src/extension.ts:360`. The shared startup then runs several absolute Git commands, including status/config discovery and a detached fetch. Selecting a canonical external `git.exe` closes current-directory executable search, but Git still reads repository-local configuration and may delegate to configured external programs. Therefore an enabled but untrusted repository can still cross from project-controlled Git configuration into host process execution during automatic global-extension startup. The detached fetch makes the crossing asynchronous and outside the bridge response lifetime.
**Control:** The accepted remediation brief requires executable discovery only after enabled/trusted activation (`batch-2-combined-fix-brief.md:12`). `.codearbiter/security-controls.md:276-290` says `ca-pi` never grants project trust and constrains subprocess crossings; `.codearbiter/specs/pi-support.md:201-206` includes untrusted project-local resources and subprocess argv/env in the threat model. Absolute initial executable identity is necessary but does not neutralize execution delegated by Git configuration.
**Remediation:** Require an affirmative current `context.isProjectTrusted() === true` before Python/Git discovery, bridge `session_start`, managed-hook discovery/installation, Git status reads, or background fetch. Treat absent/false trust as untrusted, keep mutation enforcement fail closed, permit native reads only through fresh untrusted settings, and report the trust state truthfully in doctor/status without running repository-aware Git. If any Git inspection must remain available before trust, replace the general shared startup path with a narrowly designed config-neutral read path and independently prove that repository-local config cannot select hooks, monitors, transports, credential commands, filters, or other helpers. Add an existing-runtime negative-trust regression that asserts no bridge/Git/helper/hook activity occurs before affirmative trust.

This is HIGH rather than CRITICAL because repository-local Git configuration is not normally transferred as tracked clone content, so the precondition is narrower than the original project-root executable search. It is still an undeclared arbitrary-process boundary on automatic untrusted startup and therefore blocks the gate.

### Independent rereview commands

All commands were run against the current working tree without implementation edits, staging, or commits.

| Command | Result |
|---|---|
| `npm test -- --run test/activation.test.ts test/status.test.ts test/bridge.test.ts test/tool-guard.test.ts` in `plugins/ca-pi/tools` | GREEN, 76/76 |
| `npm run typecheck` in `plugins/ca-pi/tools` | GREEN |
| `python plugins/ca/hooks/tests/test_git_hooks.py -v` | GREEN, 34/34 |
| `python tools/sync-core.py --check` | GREEN, 43 canonical files x 3 plugins byte-identical |
| `python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enabled_start_never_executes_project_git_and_installs_absolute_hook_identities -v` | GREEN, 1/1 authentic Windows installed-package canary |
| `git diff --cached --name-only` | Empty; nothing staged |

### Pending boundaries

- Active dispatch remains honestly `DEGRADED`; PI-AC-28/Task 5 and the promotion gate remain blocked pending Task 13 real-host evidence.
- Tasks 6-9, the generated child runner/env boundary, and later static-analysis work were not started or reviewed here. They remain outside this Batch 2 remediation rereview and cannot be inferred complete.

### Rereview gate

**BLOCK — 0 CRITICAL, 1 HIGH, 0 MEDIUM, 0 LOW open.** The three original security findings and the failed-start status cleanup are closed, but automatic repository-aware Git activity must not occur before affirmative project trust. Remediate the HIGH trust/config boundary, add the negative-trust regression, rerun the focused and authentic package suites, and obtain another security rereview. Independent promotion stops remain unchanged.

---

## Final security rereview — 2026-07-15

Fix report: `batch-2-trust-config-fix-report.md`
Verified SHA-256: `B919027A41DCCA51CEB4CACA3D6E21A073BBFEF81135704A12BB6B36436BBA88`
Final rereview verdict: **PASS**

### Final severity summary

| Severity | Open | Disposition |
|---|---:|---|
| CRITICAL | 0 | Original executable-search finding remains closed |
| HIGH | 0 | Trust/config boundary closed |
| MEDIUM | 0 | Original lifecycle/settings finding remains closed |
| LOW | 0 | Original doctor-envelope finding remains closed |

### HIGH trust/config finding: CLOSED

Global extension loading is now discovery only. The adapter has an affirmative, fail-closed authorization boundary before any repository-aware work:

- `plugins/ca-pi/tools/src/extension.ts:49-55` defines one fixed trust direction and treats missing, false, or throwing `isProjectTrusted` as non-affirmative. The status contains no repository-derived data.
- `plugins/ca-pi/tools/src/extension.ts:105-120` invalidates the prior lifecycle, enters the activation-check blocked generation, clears cached bridge/executable identities and old session state, then reads only the canonical activation marker. Dormant state fully deactivates. Enabled-but-untrusted state publishes the fixed direction and returns without entering bootstrap.
- `plugins/ca-pi/tools/src/extension.ts:121-138` makes affirmative trust the only route to `beginBootstrap`, command-ownership inspection, bridge preparation, enforcement installation, persona loading, and shared `session_start`. Consequently the shared Python/Git/hook/status/fetch paths reviewed in the prior HIGH are unreachable before trust.
- `plugins/ca-pi/tools/src/extension.ts:303-309` clears Python, Git, preparation, concrete-bridge, and unavailable-bridge caches on every session start before activation/trust I/O. The same-process false-to-true retry therefore constructs fresh identities rather than reviving a prior client.
- `plugins/ca-pi/tools/src/tool-guard.ts:91-159` and `plugins/ca-pi/tools/src/tool-guard.ts:212-252` keep the activation-check generation fail closed: retained or bootstrap mutators block; stale/retained reads use a newly created native factory at the current execution cwd with no bridge call or old decoration. `plugins/ca-pi/tools/src/extension.ts:369-397` supplies trusted factories only after authorization and separate fresh `projectTrusted: false` factories for native fallback.
- `plugins/ca-pi/tools/src/extension.ts:185-188` clears owned status/session state and deactivates enforcement on shutdown. A later session again clears all bridge/executable caches before checking the marker or trust.

Missing, false, and throwing trust therefore share the same source-proven direction: no Python/Git resolution, concrete bridge call, enforcement installation, persona/shared startup, managed-hook discovery/installation, repository Git read, or fetch. The bootstrap guard remains active specifically so absence of trust cannot turn into native mutation authority.

### Doctor and status boundary: CLOSED

- `plugins/ca-pi/tools/src/extension.ts:331-365` obtains a fail-closed trust result before constructing doctor input. Python is reported unavailable-to-check until trust, `bridgePrepared` is false, and the stored-wrapper self-test receives `projectTrusted: false`.
- `plugins/ca-pi/tools/src/doctor.ts:108-140` calls the bridge only when the caller proves it was prepared. `plugins/ca-pi/tools/src/doctor.ts:142-147` independently treats a missing or throwing trust signal as non-affirmative.
- `plugins/ca-pi/tools/src/doctor.ts:250-251`, `plugins/ca-pi/tools/src/doctor.ts:311-340`, and `plugins/ca-pi/tools/src/doctor.ts:376-380` report the trust row as unhealthy and Python/bridge/final-wrapper checks as intentionally withheld rather than healthy. `plugins/ca-pi/tools/src/doctor.ts:404-420` exits before wrapper execution while trust is absent.
- The existing encoded/redacted 16,000-byte final envelope remains unchanged, so the fixed trust report is single-boundary, secret-safe, and bounded.
- Shutdown, dormant, failed-start, and false-to-true status transitions retain the previously accepted keyed cleanup behavior.

### Checked-in defensive evidence

- `plugins/ca-pi/tools/test/activation.test.ts:223-294` covers missing/false trust, zero preparation/enforcement/persona/bridge work, fixed status/notification, shutdown, cache reset, and same-process false-to-true activation.
- `plugins/ca-pi/tools/test/tool-guard.test.ts:279-339` covers retained reads/mutators across the activation-check and reactivation generations with fresh untrusted native factories.
- `plugins/ca-pi/tools/test/doctor.test.ts:241-289` proves enabled-untrusted doctor performs no bridge probe or wrapper self-test and reports the withheld checks truthfully.
- `.github/scripts/test_pi_package.py:1254-1322` exercises the supported real-RPC enabled-untrusted global session and observes no managed hook, hook-discovery cache, fetch state, or shared startup marker while checking the fixed status and doctor report.
- The existing trusted Windows executable-identity/managed-hook canary remains green after the trust gate, proving the authorized path still carries the accepted absolute identities.

### Governing-document consistency

- `.codearbiter/security-controls.md:274-302` now states that global load is discovery, requires affirmative trust before repository-aware work, and defines the fail-closed untrusted behavior.
- `.codearbiter/specs/pi-support.md:183-191`, `.codearbiter/specs/pi-support.md:207-221`, and PI-AC-09/16 at `.codearbiter/specs/pi-support.md:259-265` and `.codearbiter/specs/pi-support.md:279-281` use the same invariant.
- `.codearbiter/specs/pi-support-review.md:31-41` distinguishes global load timing from adapter authorization.
- `.codearbiter/plans/pi-support.md:176-184` and `.codearbiter/plans/pi-support.md:541-549` record the same activation ordering, untrusted behavior, cache refresh, and side-effect-free doctor contract.

No contradictory current parent-activation rule was found.

### Independent final-rereview commands

All commands used existing checked-in suites and ran against the current working tree without implementation edits, staging, commits, or Tasks 6-14 work.

| Command | Result |
|---|---|
| `npm test -- --run test/activation.test.ts test/doctor.test.ts test/status.test.ts test/tool-guard.test.ts` in `plugins/ca-pi/tools` | GREEN, 81/81 |
| `npm test -- --run` in `plugins/ca-pi/tools` | GREEN, 138/138 |
| `npm run typecheck` in `plugins/ca-pi/tools` | GREEN |
| The two checked-in enabled-untrusted and trusted executable/hook `PiPackageTests` methods | GREEN, 2/2 |
| `python .github/scripts/test_pi_doctor.py -v` | GREEN, 7/7 |
| `python .github/scripts/test_host_descriptors.py -v` | GREEN, 13/13 |
| `python plugins/ca/hooks/tests/test_git_hooks.py -v` | GREEN, 34/34 from the preceding cumulative rereview |
| `python tools/sync-core.py --check` | GREEN, 43 canonical files x 3 plugins byte-identical |
| `python .github/scripts/test_build_surface.py -v` | GREEN, 34/34 |
| `git diff --cached --name-only` | Empty; nothing staged |

Current deterministic artifacts match the fix report:

- Parent bundle: `FE70C2B22E5925D4A5E6A7CC3026930E5E87EA36822F632C5BFBB611A31C9973`
- Child placeholder: `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`
- Dependency lock: `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`

### Remaining independent stops

- Active dispatch remains honestly `DEGRADED`; its later supported-version promotion evidence is not part of this trust/config fix.
- Tasks 6-14, including child execution/env isolation and later static-analysis/promotion work, were not started or reviewed in this pass. This PASS does not pre-accept them.

### Final gate

**PASS — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW open for cumulative Batch 2.** The trust/config HIGH is closed without reopening the executable, lifecycle/settings, doctor-envelope, or status findings. The controller may leave the Batch 2 security remediation loop and continue to the separately gated later tasks.
