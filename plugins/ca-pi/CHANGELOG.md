# Changelog

All notable changes to `ca-pi` are documented in this file.

## [0.1.13] - 2026-07-25

### Changed

- The shared statusline/footer ledger no longer rewrites itself on every render.
  `ledger_update()` used to load the compatibility snapshot plus every live
  session shard, write the session shard, load the snapshot and every shard a
  second time, then atomically rewrite the whole snapshot - on every refresh,
  whether or not anything had changed. Each write is now gated on the record (or
  the snapshot) actually differing from what is on disk, the duplicate load is
  gone, and the pure-liveness `last_ts` stamp is throttled to one refresh per
  five minutes so a quiet render forces no write at all. The 36-hour session TTL
  contract and the on-disk format are unchanged.
- `parse_iso()` now has one owner. `_ledgerlib` carried a byte-identical second
  copy of `_fmtlib`'s implementation and re-exports it instead.

## [0.1.12] - 2026-07-25

### Changed

- Pi path containment now has a single owner. Nine Pi modules each carried a
  private copy of the same containment predicate and `bridge.ts` carried a tenth
  platform-parameterised variant, so a containment or platform correction had to
  be applied consistently to every trust-boundary module and a partial update
  could make doctor report a path healthy while runtime enforcement rejected it.
  `path-boundary.ts` now owns the semantics as two explicitly named operations -
  lexical (text only) and canonical (both operands resolved through the
  filesystem) - with an injectable win32/posix flavor so both platforms are
  testable from either host. Every caller keeps the exact semantics it had.
- The 1,033-line Pi command module is split along its three lifecycle seams.
  Generated alias expansion with package-ownership validation, the background-job
  tool and `/ca-jobs` controller, and the `/ca-plan` controller are now separate
  modules with an acyclic import graph, so a change to one no longer forces
  review and re-verification of the other two. No behaviour changed: every moved
  line is byte-identical and every pre-existing suite passes unmodified.

## [0.1.11] - 2026-07-25

### Added

- The final-argument authority promotion STOP named by ADR-0014/ADR-0016 is
  now proven against the INSTALLED Pi candidate rather than an in-memory host
  double. A new live fixture loads codeArbiter plus a deliberately later
  trusted extension through Pi's own loader, runner, and tool wrapper, and
  proves the later extension's argument rewrite is re-judged and blocked
  before the governed mutator runs, that it cannot take ownership of that
  mutator, and that real ownership drift fails closed. It runs in every
  blocking supported-version platform cell.

## [0.1.10] - 2026-07-25

### Changed

- The farm plan handoff docs shipped with this host now describe the runtime
  plan contract (`parsePlan`, authoritative over `plan.schema.json`) and the
  split setup phases: `setup` runs once per worktree, `setupEachAttempt` reruns
  per attempt, and `setupInputs` invalidates the once-per-worktree cache.

## [0.1.9] - 2026-07-25

### Fixed

- The three live-Pi spawns in the package contract test now carry an explicit
  budget. Each `execFileSync`s a real Node process that imports the installed Pi
  host, and each inherited Vitest's bare 5000 ms default against cold hosted
  Windows process creation - the same flat-wall-clock defect as the Job Object
  admission window, in a file that fix did not reach. Measured 5497 ms and
  failing on `windows-latest`. Test-only.

## [0.1.8] - 2026-07-25

### Fixed

- Windows Job Object admission is no longer bounded by one flat 15-second
  wall-clock window. Cold admission pays two independent costs - starting the
  PowerShell host, then the one-time Add-Type compilation of the constant C#
  helper - and covering both with a single window made a loaded hosted runner
  indistinguishable from a hung helper, refusing containment twice in one day
  on `windows-latest`. The budget is now a no-progress budget per observable
  phase (the helper announces its host start before the compile) plus a hard
  30-second ceiling, so a slow-but-advancing helper is admitted while a silent
  one still fails closed. The refusal now names the phase it stalled in and
  how long it waited, while keeping its machine-readable `ready-timeout`
  reason token intact.

## [0.1.7] - 2026-07-25

### Fixed

- An abandoned maintainer session's synthetic `DEV: exit` is now durable: the
  owed audit line is staged on disk before the append is attempted and cleared
  only once both the append and the marker removal are confirmed, so a locked
  or failing `overrides.log` no longer erases the close and leaves an unmatched
  `DEV: enter`. The retry record is bounded, and an overflow that has to discard
  an owed close is itself written to the trail rather than dropped silently.
- The subagent transcript reader honours one result shape on every path, so a
  subagent-directory race no longer raises out of the statusline, and a
  syntactically valid non-object JSONL record is skipped instead of blanking
  every subagent row.
- Provenance records are validated before admission and each file is loaded
  inside its own error boundary, so one schema-invalid record no longer aborts
  the directory scan and silently drops every later valid record.

## [0.1.6] - 2026-07-25

### Fixed

- The SessionStart statusline self-heal no longer pins a NON-DURABLE plugin
  root into the user's global `~/.claude/settings.json`. A session started
  inside a git worktree resolved the plugin root to that worktree and rewrote
  the global pin there; once the worktree was pruned the statusline rendered
  nothing. A non-durable root is now inert - the existing pin is left exactly
  as it is - while a genuinely stale pin from a real plugin-cache update still
  heals. Explicit `wire-statusline.py install` from such a root refuses loudly
  instead of writing a doomed path.

## [0.1.5] - 2026-07-25

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
  `apiKey` or header value, a `!command` value, a credential-bearing `baseUrl`,
  and any key or value shape outside the reviewed Pi provider schema all fail
  the launch closed.
  Ratified as ADR-0017, which amends only ADR-0016's "no Pi configuration"
  clause — it permits **configuration** projection and still forbids
  **credential** projection.
- A projected `baseUrl` is now accepted **positively** instead of being screened
  only for URL userinfo. Screening userinfo alone closed the rare
  credential-in-endpoint shape and left the common one open: a secret in a query
  string (`?api-key=` on Azure, `?key=` on Google), a fragment, or a path
  segment crossed into the child verbatim. Blocklisting parameter names is an
  unbounded list, so a `baseUrl` now crosses only when it is a parseable
  absolute `http`/`https` URL with no userinfo, **no query and no fragment at
  all**, and a bounded route of short unencoded segments. A provider
  endpoint needs neither query nor fragment — Pi's own Azure provider takes
  `api-version` from `AZURE_OPENAI_API_VERSION` — and an endpoint that does not
  meet the rule fails the launch closed rather than projecting material that
  cannot be shown credential-free. Route segments are case-insensitive: an
  operator's Azure deployment or Cloudflare gateway name routinely carries
  capitals, and refusing them bought nothing — a lowercase-only rule admitted
  `sk-querysecret999` while refusing `GPT4-Prod`. The bound that actually
  refuses key material is the per-segment byte limit.
- Every endpoint the projection accepts is now also registered in the child's
  sensitive-value set and the projected `models.json` is retained behind a scrub
  handle. A bounded route is not *provably* credential-free, and the two controls
  that assumed otherwise were blind to it: an endpoint echoed back by the child
  was not suppressed in the final assistant message, and on the removal-failure
  cleanup path `auth.json` was truncated while the projected `models.json` was
  left intact on disk. Both now behave identically for both files.
- Projected value SHAPES, not only key names, are pinned to Pi 0.80.10's
  provider schema (`oauth` only `"radius"`, `authHeader` only a boolean, and so
  on). A record that passed the name allowlist but not the declared type used to
  project and then die mutely inside Pi's own validator instead of producing the
  intended fail-closed refusal.
- A reserved object key (`__proto__`, `constructor`, `prototype`) is now rejected
  as a projected header name, the one place in the projection that skipped the
  module's own reserved-key rule.
- The isolated child's private root — which holds the operator's real credential
  in cleartext — is now removed from a `try`/`finally` around the whole launch
  rather than threaded manually through every return. An unexpected throw after a
  successful environment prepare previously escaped the runner and stranded that
  root on disk permanently. No such throw was reachable against Pi 0.80.10; the
  change makes the class unreachable by construction rather than by audit of
  every return path.

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
- **Operator-visible audit-record format change.** `ChildResult` no longer
  carries `stderrHead`, and the dispatch audit line written to
  `.codearbiter/gate-events.log` no longer carries a `STDERR_HEAD:` field.
  Child stderr is now counted, never sampled, so no child-controlled text
  reaches the audit record; `STDERR_BYTES:` remains. Anything parsing
  `STDERR_HEAD:` out of the audit line must be updated.

## [0.1.4] - 2026-07-24

### Changed

- Refreshed the bundled farm surface (`includes/farm.md`, the
  `subagent-driven-development` farm-dispatch reference) for run-scoped farm
  receipts: the run's artifact directory is the authoritative receipt, the
  top-level `.farm/` paths are a non-authoritative latest pointer, exit 3 is
  reserved for a failure of the run-scoped report, and the concurrency caveat
  (`FARM_INTEGRATION_BRANCH`, `FARM_WORKTREE_ROOT`, non-overlapping task ids)
  is now stated where operators read it. Prose-only; no Pi adapter code changed.

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
