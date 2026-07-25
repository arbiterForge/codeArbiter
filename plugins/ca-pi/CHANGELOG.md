# Changelog

All notable changes to `ca-pi` are documented in this file.

## [0.1.3] - 2026-07-24

### Security

- Isolated Pi children now receive a bounded, selected-provider credential
  projection into a fresh private ephemeral root instead of inheriting the
  operator's Pi home. Only the exact provider record a child needs crosses the
  boundary; no other provider record, session, or package state does.
  Credential material never appears in argv, prompts, results, logs,
  telemetry, or `.codearbiter/`, and is scrubbed on every path including
  failure. Ratified as ADR-0016, superseding the opaque-auth clause of
  ADR-0014. Addresses #372.
- Isolated Pi children also receive a **credential-blind** projection of the
  selected provider's `models.json` record, so a private agent directory no
  longer strips the operator's endpoint, protocol, and model configuration and
  silently sends their key to Pi's built-in endpoint. Only the exactly-selected
  provider record crosses, and within it only structural/protocol configuration;
  `apiKey` and `headers` cross only as whole-value `$NAME`/`${NAME}` environment
  references, which hold no secret and resolve from the already-allowlisted
  child environment, and a `baseUrl` crosses as an endpoint only. A literal
  `apiKey` or header value, a `!command` value, a `baseUrl` embedding URL
  userinfo, and any key outside the reviewed Pi provider schema all fail the
  launch closed.
  Ratified as ADR-0017, which amends only ADR-0016's "no Pi configuration"
  clause — it permits **configuration** projection and still forbids
  **credential** projection.

### Fixed

- The isolated child no longer rebinds `PI_PACKAGE_DIR` beneath its private
  root. That variable names Pi's own read-only shipped-asset directory, not
  operator state, so pointing it at an empty private root made Pi's startup
  theme load fail before its RPC loop existed and killed every isolated child
  at exit 1 with zero provider turns.

### Changed

- A credential-isolation or config-projection failure now names its stage
  (`isolation-setup`, `isolation-cleanup`, or `isolation-config`) in the
  degraded diagnostic. All three are fixed identifiers chosen by the runner and
  are never derived from child output, error text, paths, configuration values,
  or credential values.

## [0.1.2] - 2026-07-24

### Fixed

- The canonical plan-file bridge tests no longer hardcode a Windows-absolute
  repository root, so they exercise `operatePlanFile` on Linux and macOS instead
  of silently asserting the rejected path. Test-only; `plan-mode.ts` is
  unchanged.

## [0.1.1] - 2026-07-18

### Fixed

- Shared prune metrics now distinguish model-visible context savings from
  file-only sidecar cleanup, including explicit strategy scopes and corrected
  footer and cold-cache decisions.
- Shared prune hooks ignore and repair malformed per-session state rather than
  allowing invalid legacy values to escape fail-open handling.

### Changed

- Promote the verified Pi host window through exact Pi 0.80.10.
- Mark the complete adapter as a Feature Forge `preview`: available and welcomed
  for real use, with broader testing still required before stable status or any
  claim of 100% validation.


## [0.1.0] - 2026-07-14

### Added

- Initial private, dependency-free Git package metadata and an isolated Node
  22.19+ TypeScript build/test boundary. The nested and root package versions
  are synchronized for `ca-pi-v*` tags; there is no npm release.
- Descriptor-generated command skills, routines, role charters, catalogs, and
  byte-identical stdlib-only Python governance core. The public surface provides
  38 `/ca-*` aliases with `/skill:ca-*` fallbacks.
- Dormant parent activation gated by the repository marker and affirmative Pi
  project trust, plus package/command ownership checks and compact status.
- Final built-in tool wrappers, bounded Python bridge, read/write notices, Git
  backstop, and `/ca-doctor` diagnostics for package origin, trust, collisions,
  supported expansion fingerprints, child integrity, and wrapper health.
- Enforcement-only child execution with minimal provider-specific environments,
  bounded RPC/JSONL, attested startup, exact generated roles, cancellation,
  timeouts, output limits, and Windows/POSIX process-tree containment.
- Single, chain, and parallel role dispatch; Pi-native compaction over the
  shared prune policy; and Feature Forge `--farm` preview routing to the one
  checked-in shared backend.
- Cross-platform fixtures, relative performance measurements, shared-store
  attribution tests, and a reproducible Pi 0.80.5/0.80.6 promotion runbook.

### Deferred

- npm packaging is a future spike. A Pi-native embedded farm worker is a future
  spike that must retain the shared farm contract; neither is a current
  dependency or release path.
