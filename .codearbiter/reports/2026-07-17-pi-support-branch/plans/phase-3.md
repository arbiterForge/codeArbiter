# Phase plan — wave 3 (coverage / infra / observability / performance / typesafety)

## Group: pi-child-audit (observability-001 + observability-002) — one issue
Give the Pi child dispatch path the same gate-events.log audit parity as bridge.ts /
compaction.ts (task, role, model, exit, duration, bounded redacted stderr), and make
windows-supervisor / job-object failures carry a reason code instead of bare REFUSED/false.
Effort M. Highest-priority keep of the run.

## Singles (ordered)
1. infra-001 — add ca-pi-codeql to ci-passed needs/required_results (with the same
   skipped-is-ok handling as other conditional jobs). Effort S. Do before merge of any
   Pi-touching PR.
2. typesafety-001 — replace the empty ExtensionAPI stub + 'as never' casts with structural
   port interfaces at the Pi boundary. Effort M.
3. coverage-001 — unit-test windows-supervisor protocol logic (parseLaunch, boundedRead,
   fail-closed wiring). Effort M. 4. coverage-002 — exercise runtime-resolver's real
   fail-closed branches (un-mock in a dedicated suite). Effort S-M.
5. coverage-003 — direct unit test for _gitexec._trusted_environment_path. Effort S.
6. coverage-004 — test ci-impact.py main() fail-safe except branch. Effort S.
7. performance-002 — benchmark the real BridgeClient spawn path, not a stub port. Effort S.
8. typesafety-002 — add Public API headers + type contracts to _gitexec/_prunepolicy. Effort S.

## Decision-required
- performance-001 — persistent bridge worker vs per-call spawn: ADR-candidate — resolve via /ca:adr. Files as a discussion issue, not a fix ticket.
