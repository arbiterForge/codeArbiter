# Phase-3 plan — wave 3 (coverage, infra, observability, performance, typesafety) kept work

15 wave-3 findings → 8 kept, 4 combined into existing groups, 4 deduped into wave-1 anchors (typesafety-001, observability-002, observability-003, performance-002).

## Corroboration of wave-1 anchors (no new work — strengthens existing)
- **group-load-host-failopen (architecture-004, high):** now corroborated by FIVE lenses. typesafety-001 reproduced the guard bypass directly (base Host + Codex apply_patch → `file_path=''` → H-18/19/05/11 all skipped); observability-002 supplies the "no breadcrumb" half of the fix; coverage-003 is the test deliverable (below). The fix must fail CLOSED **and** emit a signal, and land with the coverage-003 test.
- **group-manifest-path (reliability-001/002):** observability-003 dedups in — same wrong `.claude-plugin/` path.
- **architecture-001 (dead run(host) param):** performance-002 dedups in — the perf cost (double `_host.py` exec-load per invocation) is a direct consequence; fixing the param fixes it.

## Combined into existing groups
- **group-parser-partial-op** (appsec-001 + coverage-001): coverage-001 is the missing fixture for the partial-recognized-envelope case; add it alongside the per-directive fail-closed code fix.
- **group-project-root-seam** (architecture-006 + reliability-005 + performance-001 + performance-003): the dead payload-cwd leg is not just a correctness/design issue — it forces a `git rev-parse` subprocess on EVERY Codex hook invocation (performance-001), re-resolved per gate-log because `project_root()` is unmemoized (performance-003). Resolve the root-signal design AND memoize at process level in one pass.
- **group-shared-store** (adds observability-001): the audit-trail attribution requirement — record `get_host().name` in every gate-events.log/overrides.log line — is the concrete, non-ADR half of the shared-store contract.

## New kept work (wave 3)
### Group G — ca-codex CI / release / packaging wiring (theme: group-ci-vendoring)
Distinct issues, one theme. Deepens architecture-002/003 with workflow specifics:
- infra-001 (high): `release.yml` has no ca-codex publish job — add a `ca-codex-v*` job mirroring the ca-sandbox pattern.
- infra-002 (high): extend `test_hooks_cold_install.py` to ca-codex's differently-shaped hooks.json (ties to reliability-008's dual-registration fix — same cold-install fail-open).
- infra-003 (medium): add `plugins/ca-codex/.codex-plugin/plugin.json` to `check_license_consistency.py`'s MANIFESTS.

### Group H — test-coverage for the new host surface
- coverage-003 (high): test the `load_host()` except/fallback path (rides the group-load-host-failopen code fix).
- coverage-004 (medium): end-to-end `main()` test of session-start's `has_statusline=False` skip under a Codex host.
- coverage-002 (low): fixture for CodexHost's non-patch-tool defensive fallback branch.

### Group I — Codex diagnosability
- observability-004 (medium): surface the resolved `host.name` in both `session-start.py`'s startup banner and `doctor.py`'s report, so a dormant Codex install is distinguishable from a healthy one.

## Acceptance (wave 3)
- CI: a ca-codex release job exists; the cold-install matrix exercises ca-codex; the license check covers its manifest.
- Every Codex hook invocation resolves root without a mandatory git subprocess (or the cost is memoized to once/process).
- The audit trail attributes each event to a host; startup/doctor output names the resolved host.
- The load_host fallback path and the has_statusline gate are tested.
