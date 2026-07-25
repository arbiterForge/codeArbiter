# Changelog

All notable changes to `ca-pi` are documented in this file.

## [0.1.4] - 2026-07-25

### Fixed

- An abandoned maintainer session's synthetic `DEV: exit` is now durable: the
  owed audit line is staged on disk before the append is attempted and cleared
  only once both the append and the marker removal are confirmed, so a locked
  or failing `overrides.log` no longer erases the close and leaves an unmatched
  `DEV: enter`.
- The subagent transcript reader honours one result shape on every path, so a
  subagent-directory race no longer raises out of the statusline, and a
  syntactically valid non-object JSONL record is skipped instead of blanking
  every subagent row.
- Provenance records are validated before admission and each file is loaded
  inside its own error boundary, so one schema-invalid record no longer aborts
  the directory scan and silently drops every later valid record.


## [0.1.3] - 2026-07-24

### Security

- Governed mutators now re-read live Pi project trust at final execution. Trust
  that is withdrawn, absent, or throwing retires the ready lifecycle: bash,
  write, edit, and custom mutators fail closed, pending approvals become stale,
  and reads fall back to the untrusted native path until a new affirmatively
  trusted session starts.

### Fixed

- Pi bridge failures during a governed tool call now record the same hashed
  correlation as that call's permission-audit row, so a failure joins the tool
  call, permission decision, and result event. Lifecycle and doctor requests
  keep a locally minted correlation. Only a SHA-256 digest is accepted on the
  wire; the raw Pi tool-call id never reaches the request JSON or the audit log.


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
