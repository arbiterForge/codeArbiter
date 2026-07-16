# ca-pi reboot-safe handoff

**Recorded:** 2026-07-14
**Branch:** `feat/pi-support`
**Git common directory:** `.git`
**Promotion state:** Batch 2 combined checkpoint (Tasks 3-5) is **BLOCKED**

## Resume boundary

Batch 1 was accepted. Tasks 3-5 were individually accepted after their focused author/reviewer
loops, but the subsequent combined integration and security review found cross-task failures. Treat
the combined Batch 2 verdict as authoritative: do not start Tasks 6-9 until all confirmed blockers
are fixed test-first and fresh combined reviews are clean.

This handoff intentionally does not commit, stash, reset, clean, switch branches, publish, install an
npm release, or begin Tasks 6-9. A reboot does not require a commit; the working tree is the durable
feature state.

## Confirmed combined-review blockers

### 1. CRITICAL - pre-trust/dormancy Python resolution

- `plugins/ca-pi/tools/src/extension.ts` resolves Python during extension load, before activation and
  trust are established.
- `plugins/ca-pi/tools/src/bridge.ts` tries bare `py`, `python`, and `python3` candidates without a
  safe working-directory boundary.
- The security review proved that a poisoned working-directory `py.exe` can execute.
- Required proof: defer resolution until activation/trust, eliminate project-cwd executable search,
  validate an absolute interpreter, and add a poisoned-cwd live regression test.

### 2. HIGH - activation parser drift

- `plugins/ca-pi/tools/src/activation.ts` requires an exact lowercase, column-zero marker and exactly
  one match.
- `core/pysrc/_hooklib.py` is case-insensitive, whitespace/BOM tolerant, and permits duplicates.
- Review probe: `---\n  ArBiTeR:enabled\n---\n` was inactive in TypeScript and active in Python.
- Required proof: one generated or shared parser contract with cross-host fixtures.

### 3. HIGH - real Pi can swallow enforcement installation failure

- The parent extension throws when enforcement installation fails.
- Pi's lifecycle runner catches ordinary handler failures, emits `extension_error`, and continues.
- Required proof: an always-installed bootstrap guard that blocks mutators until enforcement is
  complete, or an explicit host shutdown, verified through real-Pi RPC fault injection.

### 4. HIGH - supported-version split

- `plugins/ca-pi/tools/src/compatibility.ts` accepts every version `>=0.80.5`.
- The approved spec, descriptor, and doctor contract support exactly 0.80.5 and 0.80.6.
- Required proof: reject 0.80.7, prereleases, and 1.x before tool registration; exercise installed
  runtime compatibility in the latest-version canary.

### 5. HIGH - read-context parity test is false-green

- `plugins/ca-pi/hooks/_host.py` defines `{path}` to `{file_path}` normalization.
- `plugins/ca-pi/hooks/pi-bridge.py` does not apply that normalization before `pre-read.py`.
- The adapter drops response context, and the current fake `tool_result` test targets a route that
  does not establish real Pi model-visible parity.
- An isolated probe allowed native `{path: src/app.py}` while the shared `{file_path: ...}` input
  produced an ADR-context notice.
- Required proof: normalize the integrated payload, preserve context through the actual native
  result route, and assert exact model-visible output.

### 6. MEDIUM - doctor live-fire overstates active-host coverage

- The doctor invokes its stored enforcement wrapper directly instead of Pi's active dispatcher.
- This proves the wrapper/shared core, not that the host is dispatching through it.
- Required proof: test active dispatch, or relabel the check as a wrapper self-test and keep PI-AC-28
  open until a live-host test exists.

## Security candidates requiring re-audit

The security review did not complete a final adjudication of these two candidates. Do not report
them as confirmed defects without a fresh source-backed review:

- Structured doctor report values may not pass through the shared-corpus redaction path.
- Installed enforcement wrappers may persist after shutdown/deactivation in a reused Pi process.

## Green evidence that is necessary but insufficient

These checks passed before the combined review found the blockers above. They are useful baselines,
not promotion evidence:

- Pi tests: 92/92.
- Package/RPC tests: 15/15.
- Descriptor/oracle tests: 13/13.
- Pi doctor/backstop tests: 5/5.
- Parity tests: 18/18; the read-context finding proves this suite currently permits a false green.
- Shared Python suite: 931/931.
- Cold-install verification: 218 assertions.
- Hook guards: 106.
- Surface generator: 34/34.
- `sync-core`: 13 tests with one skip; `--check` reported all three host copies byte-identical.
- Package check, typecheck, deterministic builds, and diff check passed.

Recorded SHA-256 hashes:

| Artifact | SHA-256 |
|---|---|
| `plugins/ca-pi/tools/package-lock.json` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |
| `plugins/ca-pi/extensions/codearbiter.js` | `CC9B98CE62184A11EDDFC2FCFF131FADD624C986EF59C83FCB172F31BB09118F` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

## Preserved user-owned dirt

Do not alter, stage, stash, reset, clean, or attribute these to the ca-pi work:

- `.codearbiter/gate-events.log`
- `.codearbiter/open-tasks.md`
- The untracked scratch file whose displayed name resembles
  `C:Users...scratchpadtest_output.txt` and contains a private-use separator glyph.
- Pre-existing July 13 temporary directories:
  `ca-pi-child-32732-ok`, `ca-pi-child-32732-cancel`, `ca-pi-child-94260-ok`, and
  `ca-pi-child-94260-cancel`.

Preserve any additional untracked caches or temporary artifacts until their ownership is proven.

## Required next sequence

1. Confirm branch and working-tree identity; do not clean or normalize the tree.
2. Fix the poisoned-cwd/pre-trust interpreter path test-first.
3. Fix canonical activation parsing with cross-host fixtures.
4. Add fail-closed bootstrap enforcement and real-Pi installation-failure coverage.
5. Enforce the exact supported-version set and strengthen the canary.
6. Fix native read normalization and exact model-visible context propagation.
7. Correct or relabel doctor live-fire coverage.
8. Re-audit both unresolved security candidates.
9. Run the focused tests, full suites, deterministic generation checks, and a fresh combined
   integration/security review.
10. Only after a clean combined checkpoint may Tasks 6-9 begin.

## Fresh-context resume prompt

Use `$ca-feature` to resume the approved feature on `feat/pi-support` from this report. Treat the
Batch 2 combined checkpoint as blocked, fix the recorded blockers test-first in order with fresh
author/reviewer loops, and re-audit the two unresolved security candidates. Do not start Tasks 6-9,
commit, publish, switch branches, stash, reset, or clean user-owned dirt until the combined
checkpoint is independently clean.

First read-only checks after reboot:

```powershell
git rev-parse --abbrev-ref HEAD
git status --short
git diff --check
Get-FileHash -Algorithm SHA256 plugins/ca-pi/tools/package-lock.json
Get-FileHash -Algorithm SHA256 plugins/ca-pi/extensions/codearbiter.js
Get-FileHash -Algorithm SHA256 plugins/ca-pi/extensions/codearbiter-child.js
```
