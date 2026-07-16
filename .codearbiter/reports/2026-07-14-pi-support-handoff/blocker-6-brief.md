# Blocker 6 brief — truthful Pi doctor dispatcher coverage

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Source finding:** handoff MEDIUM "doctor live-fire overstates active-host coverage"

## Decision

Use the handoff's truthful relabel path unless authoritative Pi 0.80.5/0.80.6 public extension APIs
provide a supported way for an extension command to submit a tool call through Pi's active dispatcher.
Do not reach through private handler maps or call undocumented host internals merely to preserve the
`live-fire` label.

The current probe calls codeArbiter's stored wrapped bash definition directly. It proves the wrapper,
canonical bridge, and shared H-03 rule cooperate, but it does not prove Pi's active dispatcher selected
that wrapper for a model-issued tool call. Relabel it as a wrapper self-test and keep `PI-AC-28` open.

## Binding behavior

- Rename production/test/report concepts from `live-fire` to `wrapper-self-test`; remove public Pi
  claims that the in-command probe exercises the active dispatcher or proves hooks/tools actually fire.
- The wrapper self-test still submits only `git add --all --dry-run` to the stored governed bash
  wrapper. Exact `[H-03]` is healthy; execution or another block is unhealthy; dormant skips it.
- Add an explicit structured `active-dispatch` diagnosis in Pi's doctor report. It must remain
  `degraded`, state that the in-command self-test cannot invoke Pi's active dispatcher, and point to
  the supported-version real-host promotion/CI evidence required to close the gap. Do not call a
  missing capability healthy.
- Keep `PI-AC-28 doctor coverage` `BLOCKED` in the durable plan and correct Task 5's stale ACCEPTED/
  active-executor wording so it cannot contradict the coverage ledger.
- Render Pi-specific doctor description/skill/catalog wording from shared `core/surface` conditionals;
  Claude and Codex live-fire wording/behavior must remain byte-equivalent unless their canonical text
  objectively needs no-op regeneration.
- The installed real-Pi `/ca-doctor` RPC fixture must assert the new exact diagnosis IDs/messages,
  absence of a `live-fire` row/claim, wrapper self-test H-03 result, degraded active-dispatch row, no
  staging mutation, and overall honest verdict.
- No private Pi dispatcher APIs, fake active-dispatch seam, dependency, lock/manifest change,
  production test switch, network/install, or auth access.
- Regenerate shared surfaces and parent bundle deterministically; child and reviewed lock unchanged.

## Required RED/GREEN proof

1. Unit RED demonstrates current `runPiLiveFire`/`live-fire` result calls the stored executor yet claims
   active coverage and has no `active-dispatch` degraded row.
2. Generated-surface RED proves Pi doctor prose/catalog still says `live-fire`/active wrapped executor.
3. Real installed-Pi RPC RED invokes `/ca-doctor` and finds the misleading row/claim.
4. GREEN covers wrapper exact command/H-03/execute/wrong-block/dormant cases, explicit active-dispatch
   degradation, Pi-only generated wording, plan ledger consistency, and real RPC report/no staging.
5. Full Pi/package/RPC/parity/doctor/hooklib/descriptor/surface/sync/typecheck and deterministic bundle
   checks remain green.

## Review focus

- No identifier, message, catalog, skill, report, test, or plan text can imply the direct wrapper call
  traverses Pi's active dispatcher.
- The self-test remains useful and non-mutating; the honest degraded row is not accidentally promoted
  to healthy by formatter/summary logic.
- Existing independent real-Pi tool-dispatch regressions remain development evidence, but are not
  misrepresented as a runtime `/ca-doctor` active-dispatch check.
