# Task 9 author report — farm preview routing and shared-store attribution

Status: implementation and author verification complete; awaiting independent security review before
the plan status moves to `ACCEPTED`.

## Test-first evidence

- RED: `npm exec vitest run test/farm.test.ts` failed because `../src/farm.ts` did not exist.
- RED: the production registration test failed because `installPiFarmPreview` did not exist.
- RED: the descriptor/guard ownership test failed because `codearbiter_farm_preview` was absent from
  the canonical Pi tool map.
- RED after root review: normal root close did not call whole-tree cleanup, and `HOME`/`USERPROFILE`
  crossed the farm boundary.
- The new three-pair store test passed on its first executable run. Host attribution was already
  implemented in the shared core; Task 9 adds the missing Claude/Pi, Codex/Pi, and Pi/Pi concurrent
  acceptance proof without inventing a production change solely to manufacture a red result.

## Implementation

- Added `runFarmPreview`, which resolves only the sibling checked-in
  `plugins/ca/tools/farm.js` backend from the Git checkout by canonical absolute path. It validates
  checkout containment, the plan's active-project containment, the backend's regular-file identity,
  and direct TypeScript-source freshness. Missing, escaped, or stale state returns an explicit
  `preview` degradation; there is no second engine and no silent premium fallback.
- Added the trusted `codearbiter_farm_preview` Pi tool. It accepts only a project-relative plan path
  and optional canary flag. Registration requires the same enabled marker, current affirmative Pi
  trust, and lifecycle-ready enforcement closure as `codearbiter_dispatch`.
- Added canonical `EXEC` classification and parent-extension source ownership for the tool in both the
  host descriptor and the thin Pi host map.
- The farm subprocess receives only `FARM_*`, `PATH`/`PATHEXT`, Windows runtime roots, and temporary
  directory variables. Ordinary provider keys, Claude OAuth, the child marker, and operator-home
  paths are excluded. Ordinary Pi children continue to delete `FARM_API_KEY` in `child-env.ts`.
- The shared Task 7 process-tree boundary now covers the farm backend. Cancel, overflow, error, and
  natural root exit all await verified tree cleanup; natural exit preserves the real exit code and
  uses `parent_shutdown` so root-first detached descendants are terminated. Unverified cleanup
  degrades rather than reporting completion.
- Rendered Pi-native farm instructions now call the extension tool for canary and dispatch while
  Claude/Codex retain their existing paths. `[CONFIRM-05]` remains the stable-promotion bar, and the
  future embedded-worker idea is recorded only as a non-shipping spike.
- Added `test_pi_shared_store.py`: 48 concurrent append events per pair for Claude/Pi, Codex/Pi, and
  Pi/Pi, requiring exact parseable attribution and no lost or corrupt append beyond ADR-0012's
  existing append baseline.

## Fresh verification

All commands exited 0 on 2026-07-16:

- Pi typecheck and deterministic build.
- Focused farm/dispatch/compaction/guard/package suite: 97 tests passed.
- Pi shared-store proof: 3 tests passed.
- Shared farm backend suite: 192 tests passed; `farm.js` rebuilt successfully.
- Existing dual-host shared-store proof: 2 tests passed.
- Pi parity: 19 tests passed.
- Surface generation check, shared-core byte-identity check, and repository `git diff --check`.

Root independently reproduced farm/guard/activation/status (70 tests), shared store (3 tests), and Pi
parity (19 tests) before the independent security-review slot was opened.

## Files

- `plugins/ca-pi/tools/src/farm.ts`
- `plugins/ca-pi/tools/test/farm.test.ts`
- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `plugins/ca-pi/tools/test/package.test.ts`
- `.github/scripts/test_pi_shared_store.py`
- `core/hosts.json`, `plugins/ca-pi/hooks/_host.py`
- `core/surface/includes/farm.md`
- `core/surface/skills/writing-plans/SKILL.md`
- `core/surface/skills/subagent-driven-development/SKILL.md`
- `core/surface/skills/subagent-driven-development/references/farm-dispatch.md`
- generated host renders and `docs/parity.md`
