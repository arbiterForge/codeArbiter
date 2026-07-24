# Pi Batch 2 security-candidate remediation

Date: 2026-07-15
Branch: `feat/pi-support`
Result: GREEN - both confirmed MEDIUM findings remediated

## Candidate A - final doctor-envelope normalization

`renderPiDoctorReportBlock()` is the final boundary between structured doctor data and the
model-visible `/ca-doctor` follow-up. It now passes the complete formatted report through the shared
`safeDiagnostic()` control before JSON encoding, with an explicit 16,000-character report bound.
This preserves intentional ordinary provenance paths while applying the shared secret corpus,
newline/control normalization, and truncation once at the sink. JSON encoding and the existing
markup-character escape then retain the single fixed `<codearbiter-doctor-report>` boundary.

### RED evidence

The test first injected all of the following into the final report envelope:

- `OPENAI_API_KEY=synthetic-shared-corpus-secret`, a value recognized by the shared corpus;
- a closing report tag and attacker tag;
- NUL and bell controls;
- 40,000 ordinary characters.

Before the production edit, `activation.test.ts` failed because the encoded payload still contained
the raw synthetic secret and the complete oversized input. The received payload also retained raw
escaped control values rather than the normalized diagnostic form.

### GREEN contract

The final model-visible envelope now proves:

- exactly one opening and one closing owned report boundary;
- no raw shared-corpus secret or key label;
- no raw markup/control character in the encoded JSON line;
- decoded controls use the replacement character;
- decoded report length is at most 16,001 UTF-16 code units (16,000 plus the truncation ellipsis);
- complete envelope length remains below 16,200 characters for the adversarial fixture.

## Candidate B - lifecycle generation across awaited enforcement work

`EnforcementInstaller` now owns an opaque object generation. Every `beginBootstrap()` creates a new
identity and `deactivate()` removes it. Installed wrappers and result handlers read that identity
immediately before bridge work and require the identical still-active identity after the bridge
await. Wrappers also check it after native execution before applying advisory decoration.

Behavior on a generation mismatch is deliberately category-specific:

- potentially mutating tools fail closed before native execution, so an approval from an ended
  lifecycle cannot execute against its captured cwd;
- a stale READ whose native execution has not started delegates once to the native factory selected
  from the current execution-context cwd and ignores the stale bridge response;
- if native execution already started, its result is returned without stale bridge decoration;
- stale WRITE/EDIT result-handler responses return no patch and emit no notification;
- new-lifecycle wrappers and result handling continue normally after reactivation.

### RED evidence

Four deterministic deferred tests were added before their corresponding production behavior:

1. An old WRITE approval resolved after deactivate-to-reactivate and executed at
   `C:/old-enabled` instead of rejecting.
2. A READ bridge response resolved after deactivate and executed the captured old-cwd native
   definition instead of the current execution-context definition; its stale notice remained
   eligible for decoration.
3. A WRITE result bridge response resolved after deactivate-to-reactivate, notified, and returned
   an owned notice instead of being suppressed.
4. With the post-native check intentionally absent, a READ deactivated while its native executor
   was pending returned the stale bridge notice after native completion.

All failures were assertion failures at the intended TOCTOU boundary, not fixture or type errors.

### GREEN contract

The focused lifecycle suite now proves deactivate-only and deactivate-to-reactivate transitions,
old-cwd non-execution for mutation, current-context native READ delegation, no stale READ/result
notice, no stale notification, post-native suppression, and successful operation of the new
lifecycle.

## Files changed

- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/src/tool-guard.ts`
- `plugins/ca-pi/tools/test/activation.test.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `plugins/ca-pi/extensions/codearbiter.js` (deterministically rebuilt parent bundle)
- `.codearbiter/reports/2026-07-14-pi-support-handoff/security-candidates-fix-report.md`

No dependency, manifest, lockfile, child bundle, network route, credential access, staging state, or
shared governance rule changed in this remediation.

## Verification

Focused RED-to-GREEN:

- final doctor-envelope regression: failed on raw secret before implementation, then passed;
- three bridge-await lifecycle regressions: 3/3 failed at the expected stale effects before
  implementation, then passed;
- post-native lifecycle regression: failed on stale notice before the post-native generation check,
  then passed;
- combined focused suite: 40/40;
- TypeScript typecheck: PASS.

Full verification after rebuilding the shipped parent:

- full Pi TypeScript suite: 8 files, 119/119;
- TypeScript package/install suite: 14/14;
- release/package/RPC-process suite: 17/17;
- isolated real-Pi command/alias RPC rerun: 1/1;
- Pi parity: 19/19;
- Pi doctor/backstop: 7/7;
- shared activation/hooklib: 69/69;
- host descriptors: 13/13;
- surface generator unit suite: 34/34;
- shared-core generator unit suite: 13 tests with 1 expected platform skip;
- `sync-core.py --check`: PASS (42 core files x 3 hosts);
- `build-surface.py --check`: PASS;
- `build-host-packages.py --check`: PASS;
- `git diff --check`: PASS.

Three observed builds (the implementation build and two final rebuilds) were byte-identical:

| Artifact | SHA-256 |
|---|---|
| Parent bundle | `EECE5726344FA2F5AA4FA9CDBF8484DF1AF665D027967A14AD69A8848101F21F` |
| Child bundle | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| Dependency lock | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child and dependency lock remain identical to the pre-remediation values. No known local
finding remains in either of the two security candidates.

---

## Review-fix addendum - rejected and cancelled bridge completions

**Recorded:** 2026-07-15
**Review source:** `security-candidates-task-security-review.md`
**Result:** GREEN - the single MEDIUM lifecycle rejection gap is closed

### Review finding

The first generation check covered only bridge promises that resolved. A bridge rejection or
cancellation completed the `await` abruptly, bypassing the generation comparison. Old-lifecycle
mutation remained non-executing but exposed the raw rejection instead of the fixed lifecycle block;
stale READ could not take the safe current-cwd native path; and stale result-handler failures could
escape into a dormant or replacement lifecycle.

### RED evidence

A rejecting deferred bridge was added before production changes. Three tests failed at the intended
boundary:

- a WRITE rejection released after deactivate-to-reactivate returned
  `raw old-lifecycle bridge detail` instead of the fixed `lifecycle changed` `/ca-doctor` block;
- an `AbortError`-shaped stale READ rejection propagated instead of delegating through the current
  execution-context cwd;
- a stale WRITE result rejection propagated instead of resolving `undefined` without effects.

The same-generation wrapper/result rejection assertions passed in RED, establishing the behavior
that had to remain unchanged rather than giving the implementation permission to swallow live
bridge faults.

### Implementation

Both lifecycle-sensitive `bridge.call()` awaits now have a narrow `try`/`catch`:

- when the captured generation is still current, the original rejection object is rethrown;
- when the generation changed, a mutator receives the same fixed, secret-independent lifecycle
  block used by the resolved path;
- a stale READ delegates once through the current execution-context native factory with its original
  signal, arguments, update callback, and context, and no stale bridge detail or decoration;
- a stale WRITE/EDIT result rejection returns `undefined`, with no patch and no notification.

The resolved completion policy, post-native generation check, steady-state semantics, and dormant
behavior are otherwise unchanged.

### Expanded GREEN coverage

The focused tests cover:

- old WRITE rejection across deactivate-to-reactivate, no old-cwd execution, fixed sanitized block,
  and a successful new-lifecycle WRITE;
- stale READ `AbortError` after deactivate and deactivate-to-reactivate, exactly one current-cwd
  native delegation, original signal identity preserved, no raw rejection/decoration, and successful
  new-lifecycle READ;
- stale WRITE and EDIT result rejections after deactivate and deactivate-to-reactivate, no patch or
  notification, plus normal new-lifecycle result handling;
- same-generation wrapper and result-handler rejection object identity propagated unchanged.

Verification after the review fix:

- focused tool-guard suite: 34/34;
- full Pi TypeScript suite: 8 files, 123/123;
- TypeScript typecheck: PASS;
- release/package/RPC-process suite: 17/17;
- isolated real-Pi command/alias RPC rerun: 1/1;
- Pi parity: 19/19;
- Pi doctor/backstop: 7/7;
- `sync-core.py --check`: PASS (42 core files x 3 hosts);
- `build-surface.py --check`: PASS;
- `build-host-packages.py --check`: PASS;
- `git diff --check`: PASS.

Three observed review-fix builds were byte-identical:

| Artifact | SHA-256 |
|---|---|
| Parent bundle | `4DF7A73C7E681E463B3C64B4A75E81B2F0075E6C7DE7D3ECD1210C847799F535` |
| Child bundle | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| Dependency lock | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

Review-fix files changed:

- `plugins/ca-pi/tools/src/tool-guard.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `plugins/ca-pi/extensions/codearbiter.js`
- `.codearbiter/reports/2026-07-14-pi-support-handoff/security-candidates-fix-report.md`

No dependency, manifest, lockfile, child bundle, network route, staging state, or user-owned dirty
artifact changed. The review rejection has no remaining local finding.
