# Batch 2 remediation 2 — canonical activation parsing report

**Status:** COMPLETE
**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Commits:** none

## Scope

This remediation fixes only confirmed Batch 2 blocker 2: Pi's TypeScript activation parser had
drifted from the canonical Python parser. Remediation 1, later blockers, Tasks 6-9, dependencies,
manifests, public commands, endpoints, configuration surfaces, audit logs, and unrelated/user-owned
dirt were not changed.

## Root cause

The two hosts independently encoded different activation grammars:

- `core/pysrc/_hooklib.py::frontmatter_enabled_text` is canonical. It splits on LF, strips leading
  UTF-8 BOM characters only from line 1, accepts surrounding Python whitespace on delimiters and
  markers, matches `arbiter: enabled` case-insensitively with optional whitespace after the colon,
  treats any number of enabled markers as enabled, stops at the first closing delimiter, and
  reports an opened-but-unclosed block as `(False, True)`.
- `plugins/ca-pi/tools/src/activation.ts` normalized newlines, required an exact column-zero
  `---\n` opening, filtered only lowercase column-zero `arbiter` keys, required whitespace after the
  colon, and required exactly one enabled marker.
- Neither implementation was pinned to a shared cross-host fixture contract, so Pi's narrower
  handwritten grammar could pass its local tests while disagreeing with the shared core.

The confirmed review probe `---\n  ArBiTeR:enabled\n---\n` therefore returned active in Python and
inactive in TypeScript.

During self-review, a second language-runtime differential was traced: Python `\s` and
`str.strip()` include U+001C-U+001F and U+0085, JavaScript `\s` does not, and JavaScript uniquely
includes U+FEFF. The final adapter uses Python's explicit whitespace set and handles U+FEFF only via
the canonical leading-BOM rule.

## Contract design

`core/activation-contract.json` is the single versioned cross-host fixture source. Its 18 fixtures
record the canonical Python `(enabled, malformed)` results for:

- canonical lowercase;
- mixed case;
- indentation;
- surrounding ASCII and Python-specific Unicode whitespace;
- whitespace and no whitespace after the colon;
- leading UTF-8 BOM;
- duplicate enabled markers;
- CRLF;
- closing delimiter at EOF;
- disabled and wrong values;
- a marker outside frontmatter;
- missing frontmatter;
- unclosed and bare-opening malformed frontmatter.

The fixture file is a test contract, not another runtime parser. Python remains authoritative:

- `.github/scripts/test_hooklib.py` evaluates every fixture with the generated, byte-identical
  shared `_hooklib.frontmatter_enabled_text` and asserts both `enabled` and `malformed`.
- `plugins/ca-pi/tools/test/activation.test.ts` consumes the same fixture objects and requires
  `isEnabled` to equal the recorded Python `enabled` result for every case.
- `python tools/sync-core.py --check` proves the tested Claude `_hooklib.py` is byte-identical to
  `core/pysrc/_hooklib.py` and the Codex/Pi vendored copies.

Calling Python from the activation adapter was not selected: activation runs before bridge
preparation and must remain dormant and side-effect-free in repositories that have not opted in.
The minimum safe runtime change is therefore a small TypeScript codec pinned to the shared contract.

## RED evidence

The shared fixture and both consumers were added before the TypeScript implementation changed.

### Primary parser-drift RED

Command:

```powershell
cd plugins/ca-pi/tools
npm test -- test/activation.test.ts -t "matches the canonical shared activation contract"
```

Result: exit 1; 1 failed, 9 skipped.

```text
AssertionError: mixed-case: expected false to be true
- Expected: true
+ Received: false
```

Before implementation, the Python oracle was also run:

```powershell
python .github/scripts/test_hooklib.py
```

Result: exit 0; 69 tests passed, including
`test_frontmatter_enabled_text_matches_shared_activation_contract`. This proved the RED was Pi
parser drift rather than an incorrect fixture expectation.

### Python/JavaScript whitespace differential RED

After the primary GREEN, source-level semantic comparison found Python-specific whitespace missing
from JavaScript's shorthand. The shared fixture was extended before changing implementation.

Command:

```powershell
cd plugins/ca-pi/tools
npm test -- test/activation.test.ts -t "matches the canonical shared activation contract"
```

Result: exit 1; 1 failed, 9 skipped.

```text
AssertionError: python-specific-unicode-whitespace: expected false to be true
- Expected: true
+ Received: false
```

The Python hooklib suite remained 69/69 green with that fixture, confirming the differential.

## Implementation

`plugins/ca-pi/tools/src/activation.ts` now mirrors the canonical decision sequence:

1. Read `.codearbiter/CONTEXT.md` as UTF-8; unreadable or missing remains inactive.
2. Split only on LF, allowing CRLF through Python-compatible whitespace handling.
3. Remove one or more leading U+FEFF characters only from line 1.
4. Require a Python-whitespace-tolerant opening delimiter.
5. Scan through the leading block, accumulating any case-insensitive enabled marker.
6. Return the accumulated result at the first closing delimiter.
7. Return inactive if the block never closes.

Duplicate enabled markers now remain enabled. Disabled/wrong values, markers after the closing
delimiter, missing frontmatter, unreadable files, and malformed/unclosed frontmatter remain inactive.
The canonical Python source was not modified.

The existing local activation test was renamed from "only exact" to "canonical" and its duplicate
expectation was corrected from false to true. The parent bundle was regenerated; the child bundle
remained byte-identical.

## Files changed

- `core/activation-contract.json` — new shared, versioned fixture contract.
- `.github/scripts/test_hooklib.py` — Python consumer asserting canonical `enabled` and `malformed`.
- `plugins/ca-pi/tools/test/activation.test.ts` — TypeScript consumer and corrected duplicate case.
- `plugins/ca-pi/tools/src/activation.ts` — minimal canonical parser adapter.
- `plugins/ca-pi/extensions/codearbiter.js` — regenerated deterministic parent bundle.
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-2-report.md` — this report.

No dependency, manifest, lockfile, shared Python source, generated child bundle, audit log, or later
blocker file was changed by this remediation.

## GREEN and verification evidence

### Focused GREEN

```powershell
cd plugins/ca-pi/tools
npm test -- test/activation.test.ts -t "matches the canonical shared activation contract"
```

Result: exit 0; 1 passed, 9 skipped.

```powershell
npm test -- test/activation.test.ts
```

Result: exit 0; 10/10 passed.

```powershell
python .github/scripts/test_hooklib.py
```

Result: exit 0; 69/69 passed, including the shared-contract test and all malformed semantics.

### Pi adapter

```powershell
cd plugins/ca-pi/tools
npm run typecheck
npm test
```

Results: typecheck exit 0; 8 files and 96/96 tests passed.

### Deterministic bundle

`npm run build` was run twice from `plugins/ca-pi/tools`. Both runs exited 0 and emitted the same
hashes:

| Artifact | First build SHA-256 | Second build SHA-256 |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `12BE6DDFE05F027EF21679A87D32767A2BDEB97E9EFB2112F6C23E407E7702B5` | `12BE6DDFE05F027EF21679A87D32767A2BDEB97E9EFB2112F6C23E407E7702B5` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

The child hash equals the preserved handoff hash; the parent hash changed only because it contains
the corrected activation adapter.

### Generation, package, and parity

```powershell
python tools/sync-core.py --check
```

Result: exit 0; 42 core files x 3 plugins byte-identical.

```powershell
python tools/build-surface.py --check
python tools/build-host-packages.py --check
```

Results: exit 0; Claude/Codex/Pi surfaces in sync; root and Pi package metadata match the descriptor.

```powershell
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_sync_core.py
python .github/scripts/test_build_surface.py
```

Results: 13/13 passed; 13 passed with 1 platform skip; 34/34 passed. The build-surface suite's
intentional mutation diagnostics were followed by a final green `--check`.

```powershell
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
```

Results: parity 18/18; doctor/backstop 5/5; package 15/15; isolated real-Pi RPC 1/1.

```powershell
git diff --check
```

Result: exit 0. A byte-level check of all remediation source, fixture, test, and bundle files found
UTF-8 without BOM, LF only, a final LF, and no lone carriage returns.

## Self-review

- The fixture source is shared and versioned; Python and TypeScript do not maintain separate fixture
  lists.
- Python's canonical implementation and all generated Python copies remain byte-identical and
  unchanged.
- The TypeScript adapter matches Python's BOM boundary instead of relying on JavaScript `trim()`,
  which would incorrectly treat U+FEFF as general whitespace.
- Python's exact whitespace code-point set is explicit in the TypeScript codec, closing the
  JavaScript `\s` differential discovered during review.
- The parser stops at the first closing delimiter, so body markers cannot activate a repository.
- Opened-but-unclosed frontmatter remains inactive in TypeScript and `(False, True)` in Python.
- Missing/unreadable files remain fail-silent and dormant; no bridge or Python resolution is added
  to the pre-activation path.
- No later blocker was modified or opportunistically fixed.
- Remediation 1 and all preserved unrelated/user-owned dirt remain in place.

## Concerns

None for blocker 2. The combined Batch 2 checkpoint remains blocked on the later recorded blockers;
this report does not claim Tasks 6-9 are unblocked.

## [NEEDS-TRIAGE]

None observed within this remediation.

## Reviewer fix loop — exact Python `re.I` case-fold parity

**Finding:** Important/HIGH, confirmed after the initial implementation report.
**Status:** RESOLVED test-first.
**Commits:** none.

### Root cause

Python `re.I` gives the literal `i` in `arbiter` four matching code points: ASCII U+0049/U+0069,
Latin capital I with dot U+0130, and dotless i U+0131. JavaScript `/iu` matches only ASCII
U+0049/U+0069 for that literal. The initial TypeScript codec therefore remained narrower than the
canonical parser even though ordinary mixed-case fixtures were green.

The source-independent focused probe returned:

```text
Python: [true, true, true]  # ASCII i, U+0131, U+0130
Node:   [true, false, false]
```

### Contract-first RED

Two fixtures were added to `core/activation-contract.json` before production code changed:

- `python-re-i-latin-capital-i-with-dot` — `arb\u0130ter: enabled` -> `(true, false)`;
- `python-re-i-dotless-i` — `arb\u0131ter: enabled` -> `(true, false)`.

The TypeScript contract loop was changed to `expect.soft` so one run reports every drift rather than
stopping at the first fixture.

Command:

```powershell
cd plugins/ca-pi/tools
npm test -- test/activation.test.ts -t "matches the canonical shared activation contract"
```

Result: exit 1; 1 contract test failed, 9 skipped, with two soft-assertion failures:

```text
python-re-i-latin-capital-i-with-dot: expected false to be true
python-re-i-dotless-i: expected false to be true
```

The canonical side was then confirmed without changing Python:

```powershell
python .github/scripts/test_hooklib.py
```

Result: exit 0; 69/69 passed, including both new shared-contract fixtures.

### Minimal implementation

Only the `i` position in the TypeScript enabled-marker expression changed:

```text
arbiter -> arb[i\u0130\u0131]ter
```

The existing JavaScript `iu` flags continue to supply ASCII `i/I`. U+0130 and U+0131 are admitted
explicitly at that position only. Whitespace, BOM, delimiter, duplicate, malformed, wrong-value,
body-marker, and read-failure semantics are unchanged.

### GREEN and complete verification rerun

```powershell
cd plugins/ca-pi/tools
npm test -- test/activation.test.ts -t "matches the canonical shared activation contract"
npm test -- test/activation.test.ts
npm test
npm run typecheck
```

Results: focused contract 1 passed with 9 skipped; activation 10/10; Pi 96/96 across 8 files;
typecheck exit 0.

```powershell
python .github/scripts/test_hooklib.py
```

Result: 69/69 passed.

`npm run build` was run twice. Both builds exited 0 and emitted identical hashes:

| Artifact | First build SHA-256 | Second build SHA-256 |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `5D4FFE50FB65FA4C7ADCAE323F50B182E0AD873B738D76287F03CDE9B42E235B` | `5D4FFE50FB65FA4C7ADCAE323F50B182E0AD873B738D76287F03CDE9B42E235B` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

The child bundle remains byte-identical to the handoff. The parent hash supersedes the initial
remediation hash because it contains the exact case-fold adapter.

The same directly affected gates from the initial report were rerun:

```powershell
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_sync_core.py
python .github/scripts/test_build_surface.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
```

Results: host descriptors 13/13; sync-core 13 with 1 platform skip; build-surface 34/34;
42 shared files x 3 plugins byte-identical; all three surfaces and package metadata in sync; parity
18/18; doctor/backstop 5/5; package 15/15; isolated real-Pi RPC 1/1.

### Files changed in this reviewer loop

- `core/activation-contract.json` — two canonical Python `re.I` fixtures.
- `plugins/ca-pi/tools/test/activation.test.ts` — soft assertions report all fixture drift.
- `plugins/ca-pi/tools/src/activation.ts` — exact `i`-position character class.
- `plugins/ca-pi/extensions/codearbiter.js` — regenerated parent bundle.
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-2-report.md` — appended evidence.

### Self-review and concerns

An exhaustive U+0000-U+10FFFF probe at the `i` position produced the identical accepted set for
Python and the final JavaScript expression:

```text
[U+0049, U+0069, U+0130, U+0131]
```

This proves the explicit additions do not over-activate another character. `git diff --check`
remained clean. No blocker-2 concern remains; later Batch 2 blockers remain out of scope and still
gate Tasks 6-9.
