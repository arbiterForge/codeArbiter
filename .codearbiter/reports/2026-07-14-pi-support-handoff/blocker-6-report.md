# Blocker 6 report â€” truthful Pi doctor dispatcher coverage

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Result:** GREEN â€” relabeled to wrapper self-test; PI-AC-28 remains BLOCKED

## Public API conclusion

No supported Pi 0.80.5 or 0.80.6 public extension API can submit a deterministic tool call through
Pi's active dispatcher from an extension command.

- Pi 0.80.6 was inspected from the operator-installed package at
  `%APPDATA%/npm/node_modules/@earendil-works/pi-coding-agent`, version-confirmed by its
  `package.json`, and from `dist/core/extensions/types.d.ts`.
- Pi 0.80.5 was inspected without network access or installation from the existing npm cache tarball
  with integrity
  `sha512-GPYFuHw1BN+3m5Gzw1HGH41WdFDzbplLauS0zYSf1ZOkgKFd6wtEAcjchB/vmz9YtTGbQOwECbsVj6GxZxungA==`.
- Both authoritative `ExtensionAPI` declarations expose event registration, custom tool/command
  registration, message injection, shell `exec`, and tool introspection/activation. Neither exposes a
  dispatch/execute/call/run/submit-tool method. `sendUserMessage` starts an LLM turn and therefore
  cannot deterministically submit the exact H-03 probe.
- Normalized declaration evidence: 0.80.5 ExtensionAPI SHA-256
  `986c076b6071490d8d316b9f884d27389e4ef0e42c907f832d6684d1e7f8f86c`; 0.80.6
  `dd80258bb74604322310701034d61afa3110682e647322db061b56a348c538e4`; zero matching public
  dispatch method names in either declaration.

The handoff's truthful relabel path was therefore used. No private handler map, undocumented host
internal, fake dispatch seam, dependency, configuration switch, network access, or install was added.

## Root cause and RED proof

The old path was:

`/ca-doctor` -> stored `EnforcementInstaller` bash definition -> wrapper `execute()`

That path proves the stored wrapper, canonical bridge, and H-03 rule cooperate. It never asks Pi's
active dispatcher to select or invoke the wrapper.

RED was observed before production edits:

1. `doctor.test.ts`: four failures â€” missing `active-dispatch`, missing
   `runPiWrapperSelfTest`, and absent exact/dormant wrapper-self-test semantics.
2. `test_pi_doctor.py`: generated Pi skill/catalog still advertised live-fire; Task 5 still said
   ACCEPTED and claimed an active wrapped executor.
3. Real installed-Pi RPC: `/ca-doctor` emitted `HEALTHY  live-fire` and no `active-dispatch` or
   `wrapper-self-test` row.
4. The standalone generated Pi mechanical doctor still said its command proved hooks actually fire;
   a focused RED failed on that exact public claim.

## Implemented behavior

- Renamed internal/public Pi concepts to `wrapper-self-test`:
  `runPiWrapperSelfTest`, `runDoctorWrapperSelfTest`, and
  `codearbiter-doctor-wrapper-self-test`.
- The self-test calls only the stored governed bash wrapper with
  `git add --all --dry-run`.
- Only an error beginning with exact `BLOCKED [H-03]` is healthy. Execution, another H-ID, or text
  that merely mentions `[H-03]` is unhealthy. Dormant repositories skip the call and degrade.
- `diagnosePi()` always emits this explicit row:

  `DEGRADED  active-dispatch: Supported Pi 0.80.5/0.80.6 public extension APIs cannot submit this deterministic self-test through the active dispatcher; the wrapper self-test does not exercise active dispatch.`

  Its remediation is:

  `Require passing supported-version real-host promotion/CI evidence before closing PI-AC-28.`
- The wrapper success row is exact:

  `HEALTHY  wrapper-self-test: The stored governed Pi bash wrapper returned the exact shared-core H-03 block for git add --all --dry-run; no staging occurred.`
- The generated Pi doctor description, skill, index, catalog, command catalog, and preview wording now
  distinguish wrapper wiring from active-dispatch evidence. Claude/Codex doctor, preview, and catalog
  rendered bytes stayed unchanged.
- The shared mechanical doctor is host-aware: Pi reports static checks plus the wrapper-self-test /
  active-dispatch gap; Claude/Codex retain their existing runtime live-fire verdict text.
- Task 5 now records PI-AC-15/16 as accepted but has `Status: BLOCKED` for PI-AC-28. Task 13 owns the
  supported-version real-host/CI evidence needed to close it.

## Structural and real-host proof

- Unit tests capture the exact wrapper input and reject execute, wrong-H-ID, H-03-bait, and dormant
  false greens.
- Generated-surface tests parse the Pi skill frontmatter, JSON catalog entry, and index row rather
  than accepting an unrelated matching phrase. They also pin Claude/Codex live-fire surfaces.
- Plan tests isolate Task 5 and the PI-AC-28 ledger row, so a phrase elsewhere cannot satisfy them.
- The installed real-Pi RPC test parses the `<codearbiter-doctor-report>` JSON envelope, requires one
  exact diagnosis row per ID, checks the exact wrapper and active-dispatch messages/remediation,
  rejects `live-fire`, requires overall `doctor: DEGRADED`, and compares staged paths before/after.
  The staged state was unchanged.

## Files changed for this blocker

- Runtime: `plugins/ca-pi/tools/src/doctor.ts`, `extension.ts`, `tool-guard.ts`
- Unit/integration: `plugins/ca-pi/tools/test/doctor.test.ts`,
  `.github/scripts/test_pi_doctor.py`, `.github/scripts/test_pi_package.py`
- Canonical generated surface: `core/surface/commands/doctor.md`,
  `core/surface/commands/preview.md`, `core/surface/COMMANDS.md`
- Generated Pi surface: `plugins/ca-pi/skills/ca-doctor/SKILL.md`,
  `plugins/ca-pi/skills/ca-preview/SKILL.md`, `plugins/ca-pi/skills/INDEX.md`,
  `plugins/ca-pi/generated/command-catalog.json`, `plugins/ca-pi/COMMANDS.md`
- Shared mechanical doctor: `core/pysrc/doctor.py` and the three byte-identical generated host copies
- Durable plan: `.codearbiter/plans/pi-support.md`
- Built parent: `plugins/ca-pi/extensions/codearbiter.js`

## GREEN verification

- Focused doctor unit: 19/19
- Full Pi TypeScript: 115/115
- TypeScript typecheck: PASS
- Pi package/RPC suite: 17/17
- Installed RPC command-only rerun: 1/1
- Three-host parity: 19/19
- Pi doctor/backstop: 7/7
- Shared hooklib: 69/69
- Host descriptors: 13/13
- Surface generator: 34/34
- Sync-core: 13 tests, 1 expected skip
- `build-host-packages.py --check`: PASS
- `build-surface.py --check`: PASS; subsequent write changed 0 files
- `sync-core.py --check`: PASS; subsequent write changed 0 files
- `git diff --check`: PASS
- Two consecutive builds: byte-identical

Final artifact SHA-256:

| Artifact | SHA-256 |
|---|---|
| Parent bundle | `700E81D51769FEB7A52AE77BE21F1AB7AAF7B283E695D04470AAEDFFDAE682AF` |
| Child bundle | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| Dependency lock | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child bundle and reviewed dependency lock are unchanged.

## Residual

`active-dispatch` intentionally remains degraded and PI-AC-28 remains BLOCKED. It can be promoted only
by supported-version real-host promotion/CI evidence that exercises an actual model-issued tool call
through Pi's dispatcher. The known child placeholder remains a separate pre-existing Task 6 degraded
row.
