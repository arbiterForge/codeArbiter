# Changelog

All notable changes to `ca-pi` are documented in this file.

## [0.1.1] - 2026-07-18

### Fixed

- Shared prune metrics now distinguish model-visible context savings from
  file-only sidecar cleanup, including explicit strategy scopes and corrected
  footer and cold-cache decisions.
- Shared prune hooks ignore and repair malformed per-session state rather than
  allowing invalid legacy values to escape fail-open handling.

### Changed

- Promote the verified Pi host window through exact Pi 0.80.10.


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
