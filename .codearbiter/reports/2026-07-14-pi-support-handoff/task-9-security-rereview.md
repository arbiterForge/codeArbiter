# Task 9 independent security and integration rereview

Date: 2026-07-16
Reviewer: Task 10 security owner (independent of Task 9 authorship)
Scope: Pi farm preview production route, lifecycle/trust authorization, descriptor ownership, backend and plan containment, farm-only environment, bounded output, process-tree cleanup, and shared-backend parity

## Verdict

PASS after remediation. One HIGH lifecycle finding was confirmed, regression-tested, fixed, and rereviewed. No unresolved HIGH or CRITICAL Task 9 finding remains in the local evidence set.

## Confirmed finding

**Severity:** HIGH
**Surface:** `plugins/ca-pi/tools/src/extension.ts`, `plugins/ca-pi/tools/src/farm.ts`

Farm authorization originally used a mutable readiness boolean and then awaited the enabled-marker read. A prior session's tool call could resume after shutdown and reactivation, observe the new lifecycle as ready, and start the shared mutating farm backend in the stale context. The root cause was broader: an obsolete `session_start` could also resume after awaited activation steps and mint readiness or replace state for a newer session.

## Remediation and proof

- `installParent` now creates a distinct opaque lease for every session start, invalidates the prior lease on reset/shutdown, and checks identity after awaited enabled, bridge-preparation, enforcement, persona, startup-bridge, and prompt-refresh work.
- Readiness consumers receive the current ready lease, not a boolean. Dispatch and compaction capture and recheck it around awaited work.
- Farm authorization captures the lease only after enabled/trust authorization, rechecks it after the enabled-marker await, and carries it into the runner.
- `runFarmPreview` rechecks the identical lease after backend/plan/environment/Node-path awaits and immediately before spawn. It also rechecks cancellation before spawn.
- Deterministic regressions prove stale shutdown-to-reactivation work cannot mint readiness, authorize farm, spawn, egress, or overwrite the current bridge state.

## Other reviewed boundaries

- The production call site registers only `codearbiter_farm_preview`, classified `EXEC` by the generated Pi descriptor and `_host.py` surface.
- Unknown and foreign-owned replacements remain blocked by the final owner/source guard.
- Backend resolution canonicalizes the checkout, requires the one shared `plugins/ca/tools/farm.js`, and rejects missing/outside/stale artifacts.
- Plan resolution canonicalizes and requires a regular file inside the active project; the shared backend remains the only plan parser/executor.
- The child environment admits only `FARM_*` plus reviewed runtime variables; provider keys, Claude OAuth, child recursion state, and real-home values are excluded.
- Output is aggregate byte-bounded and never returned raw. Cancellation, overflow, nonzero exit, unverifiable cleanup, and root-first normal exit all terminate/verify the process tree and cannot promote incorrectly.
- Pi adds no farm implementation or independent shared-store mechanism; it invokes the existing built backend under the same ADR-0012 state behavior and keeps the `preview` label.

## Evidence

- `npm --prefix plugins/ca-pi/tools run typecheck` - PASS
- `npm --prefix plugins/ca-pi/tools exec vitest run test/farm.test.ts` - 11 passed
- Focused activation/dispatch/compaction/farm/security run - 81 passed
- Full Pi tools suite - 253 passed, 1 skipped
