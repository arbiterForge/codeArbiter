# Task 7 dispatch author report

Date: 2026-07-16
Branch: `feat/pi-support`
Scope: orchestration/registration only; the Task 7 process-tree recovery lane owns containment, build inputs, generated bundles, and live process tests.

## Implemented contract

- Added `plugins/ca-pi/tools/src/dispatch.ts` with the exact closed mode set `single | chain | parallel` and exact closed terminal set from the approved plan.
- Added one frozen `DISPATCH_POLICY` for role count, concurrency, depth, task, child-output, aggregate-output, and timeout ceilings. Request limits may only reduce those ceilings and must be positive safe integers.
- Validates the full role list before any child spawn, including unknown/duplicate roles, multiple authors, single-mode cardinality, depth, and limits.
- Single mode runs one role. Chain mode is sequential. Parallel mode is a FIFO bounded worker queue whose output stays in requested-role order.
- Parent cancellation aborts every active child controller and marks queued siblings cancelled without starting them.
- Child output is an exact `{ "state", "summary" }` JSON object. The state is limited to `accepted | changes_requested | blocked`; malformed output, thrown runners, degraded runners, deadlines, cancellation, and size violations map to deterministic operational terminals without unhandled rejection.
- Every child receives a bounded `codearbiter-dispatch-v1` stdin task envelope. It preserves the role charter's Markdown report contract by requiring the complete report inside the JSON `summary` string. Chain mode forwards only the parsed prior `{ role, state, summary }`, never PID, correlation id, provider, launch path, raw JSONL, or environment data.
- Aggregate output accounting is applied in requested order, so parallel completion timing cannot change which child crosses the cap.

## Registration and authorization

- Registered `codearbiter_dispatch` from the parent extension only. Public parameters expose task, mode, roles, depth, and bounded limits; trusted Node/Pi/package/child-extension paths stay in the extension closure.
- Dispatch authorization fails closed before runtime, path, catalog, or child resolution unless all three conditions are current: the canonical marker is enabled, Pi reports affirmative project trust, and `installParent`'s successful enforcement lifecycle generation remains ready.
- Session start resets readiness. Dormant/untrusted/throwing-trust/enforcement-failure contexts never become ready. Session shutdown invalidates the captured readiness closure, preventing stale trusted-context reuse.
- Verified the installed supported Pi 0.80.6 type surface: tool `execute` receives `ExtensionContext`, whose public interface includes `isProjectTrusted(): boolean`. The local `ToolExecutionContextPort` now models that optional capability for fail-closed structural use.
- Classified `codearbiter_dispatch` as Pi-only `EXEC` in both `core/hosts.json` and the live Pi `TOOL_MAP`. The active guard permits it only when Pi reports the canonical parent extension as the active source and blocks a foreign replacement as source drift. Existing final-wrapper expectations remain unchanged for `bash`, `write`, and `edit`.

## TDD evidence

Expected RED was observed before each production slice:

1. `npm test -- --run test/dispatch.test.ts`
   - failed because `../src/dispatch.ts` did not exist.
2. `npm test -- --run test/dispatch.test.ts -t "chain forwards"`
   - failed because the first raw Markdown task was not the required JSON transport envelope.
3. `npm test -- --run test/tool-guard.test.ts -t "parent-extension-owned Pi dispatch"`
   - failed because the generated Pi descriptor did not yet classify `codearbiter_dispatch`.
4. `npm test -- --run test/dispatch.test.ts -t "production registration|owns dispatch readiness"`
   - failed because production registration/readiness integration did not yet exist.

Focused GREEN:

- `npm test -- --run test/dispatch.test.ts` -> 27/27 passed.
- `npm test -- --run test/dispatch.test.ts test/tool-guard.test.ts test/activation.test.ts test/status.test.ts` -> 89/89 passed.
- `python .github/scripts/test_pi_parity.py` -> 19/19 passed.
- `npm run typecheck` -> passed immediately after the dispatch integration. A later shared-tree run was temporarily blocked by the independent containment lane's in-progress `windows-supervisor.ts` `WritableStream.destroy` type error; no dispatch diagnostic was reported.

Additional descriptor-suite note: `python .github/scripts/test_host_descriptors.py` passed the descriptor schema/immutability/generation cases relevant to the host-map edit, but the whole script remains red on pre-existing sprint-in-progress Task 6/7 generator allowlist and charter-regeneration expectations. Those failures enumerate the broader unaccepted Pi source set and are not attributable to `codearbiter_dispatch` classification.

## Files in this slice

- `plugins/ca-pi/tools/src/dispatch.ts`
- `plugins/ca-pi/tools/test/dispatch.test.ts`
- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/src/contracts.ts`
- `core/hosts.json`
- `plugins/ca-pi/hooks/_host.py`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`

## Remaining acceptance dependencies

- The containment lane must finish runner/process-tree/supervisor integration, restore full typecheck, add the build input, rebuild once, and pass the live descendant-cleanup matrix.
- Generated parent bundle evidence must confirm the registered tool and updated Pi descriptor after that rebuild.
- Independent spec-compliance and security review remain required before Task 7 acceptance.
