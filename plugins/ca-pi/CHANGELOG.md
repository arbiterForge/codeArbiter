# Changelog

All notable changes to `ca-pi` are documented in this file.

## [Unreleased]

## [0.2.2] - 2026-08-04

### Fixed

- `post-merge-cleanup` (issue #586): the Phase 1 gate no longer STOPs on every squash-merged branch. SHA-ancestry is now one of two accepted containment proofs — the second is the merged PR record (`headRefOid` == HEAD), reported alongside the ancestry check's negative result rather than treated as a failure. Phase 4 now fast-forwards the local default ref before checking it out, so a stale local default can no longer be misattributed to a correctly-kept Phase 3 artifact. Phase 5 documents why `-d` can accept a squash merge via its upstream, and sanctions `-D` only when this run's Phase 1 proof was the PR-record squash proof and `-d` refused.
- `standup` (issue #596): stale worktrees can now be confirmed as one explicitly enumerated group naming every member, instead of one confirmation per worktree; declining the group falls back to per-item confirmation. Branch pruning documents the same squash-merge `-D` exception as `post-merge-cleanup`.

## [0.2.0] - 2026-08-01

### Added

- Protected-state registry (hook `H-22`): `.codearbiter/` files can be enrolled as `marker-gated`, `helper-only`, or `append-only`, enforced across the Write, Edit, and shell flanks. `release-targets.md`, `open-tasks.md`, and `done-tasks.md` are enrolled, one per policy.
- `taskwrite archive` moves a long-done task to `done-tasks.md`, writing the permanent record before removing from the board so an interrupted run cannot lose it.

### Fixed

- `_releaselib.py` spawned git as a bare `git`, bypassing the trusted-path seam every Pi-reachable module must use.
- The shell flank's interpreter leg missed `py` and PowerShell, and matched on the interpreter token alone — which blocked the sanctioned helper's own invocation whenever a task description named an enrolled file. It now requires an inline-code switch.
- Archiving moved only a task's top line, orphaning its `Desc`/`Boundaries` sub-bullets onto the following task, and removed every line matching the target, collapsing two identical done entries into one.
- An unreadable `done-tasks.md` was treated as empty, so a transient read failure rewrote the append-only archive from scratch and discarded every record.

## [0.1.43] - 2026-07-30

### Changed

- **`_hooklib` sheds activation, completing the #321 partition (slice 4 of 4).**
  The hook core finishes at **557 lines, from 1,263** - a 56% reduction across
  four slices. `_activationlib` now owns which Host the process runs under, where
  the project root is, and whether the arbiter is switched on, together with the
  two process-lifetime caches those answers share.

  `_HOST` is deliberately **not** re-exported: importing a mutable global binds
  its *value*, so a later `set_host()` would rebind it in the owning module and
  leave a stale copy behind forever. The accessors are re-exported instead, and
  a test proves both modules share one cache in both directions.

  `_hooklib` re-exports every name with a consumer, so the public surface is
  unchanged and parity rests on 1,185 pre-existing hook tests that did not move.

  No behaviour change.

## [0.1.42] - 2026-07-30

### Changed

- **`_hooklib` sheds its path-scope detection (#321, slice 3 of 4).** The hook
  core drops from 880 to 663 lines - **1,263 before the partition began**, so
  three slices have taken nearly half off the god module. `_scopelib` now owns
  which repo paths are database migrations (H-14), CI/CD workflow files (H-15),
  and deployment / IaC manifests (H-16), plus the security-controls.md reader and
  glob compiler they share.

  The cleanest seam of the four: this cluster referenced NOTHING from the rest of
  `_hooklib`, and nothing referenced it. Its only dependency was `norm_path`,
  already on the `_pathnorm` floor.

  `_hooklib` re-exports every moved name - including the private ones, which have
  real consumers - so the public surface is unchanged and parity rests on 1,185
  pre-existing hook tests that did not move.

  No behaviour change.

## [0.1.41] - 2026-07-30

### Changed

- **`_hooklib` sheds its protected-path classifiers (#321, slice 2 of 4).** The
  hook core drops from 1,050 to 880 lines - 1,263 before the partition began.
  `_protectedlib` now owns which repo paths are append-only audit logs (H-05),
  ADR decision files (H-11), the activation manifest, and the gate-marker
  directory. `repo_rel` joined `norm_path` on the `_pathnorm` floor, because it
  references no module symbol and the remaining slices need it too.

  Measured the same way slice 1 was: one outward reference, zero inward.
  `_hooklib` re-exports every moved name, so all consumers are untouched and
  parity rests on 1,185 pre-existing hook tests that did not move. The public
  surface is preserved exactly - nothing lost, nothing gained.

  No behaviour change.

## [0.1.40] - 2026-07-30

### Changed

- **`_hooklib` sheds its H-09b/H-10b sensitive-scan concern (#321, slice 1 of 4).**
  The 1,263-line hook core drops to 1,051. `_sensitivelib` now owns the crypto and
  secret detectors, the pinned security diff argv, the path-aware diff walk, and
  the digests that bind a recorded gate pass to the lines it reviewed;
  `_pathnorm` holds `norm_path` as the dependency floor beneath every path
  classifier.

  The seam was measured rather than guessed: the cluster referenced exactly ONE
  symbol from the rest of `_hooklib`, and nothing in the rest of `_hooklib`
  referenced the cluster. `_hooklib` re-exports every moved name, so all 59
  consuming files are untouched and behavioural parity rests on 1,185
  pre-existing hook tests that did not move.

  No behaviour change.

## [0.1.39] - 2026-07-28

### Changed

- Projection of the shared surface change in ca 2.10.2: coverage figures are the
  union across a tree's supported hosts, and `tdd` Phase 5 requires the
  measuring host to be named (#521). `plugins/ca-pi/tools` is platform-forked
  and therefore in scope for the rule; its union job is tracked in #537. No
  Pi-specific behaviour changed.

## [0.1.38] - 2026-07-27

### Fixed

- Two holes in the #528 arbitration-log reclassification, both found by
  adversarial review before merge, both leaving the append-only log destructible
  from the shell.

  The H-11 carve-out was case-insensitive while H-05 - the guard taking over for
  that file - is case-sensitive on both flanks, so a case-varied spelling of the
  path was stripped from one guard's view and invisible to the other. On
  Windows/NTFS and default macOS/APFS that spelling resolves to the real file,
  so a delete under it removed the log with no gate firing.

  And `New-Item -Force`, which truncates an existing file, was covered by H-11
  but not by H-05, so the log lost that verb on reclassification - a gap the flat
  audit logs shared, now closed for all of them.

  The carve-out also lacked a right-edge anchor, so the log's path shielded any
  token beginning with it, letting the shell create files under `decisions/`
  that the Write/Edit guard still treats as immutable ADR history.

## [0.1.37] - 2026-07-27

### Fixed

- The projected `decision-variance` routine could not record a decision. Its
  Phase 4 is required to append every SMARTS arbitration to
  `.codearbiter/decisions/decision-log.md` "immediately, never batched" - and
  H-11 refused every write, because its path rule matched any `.md` under
  `decisions/` and so governed the arbitration log as immutable ADR history
  requiring the `/adr` authoring marker. Only `decision-lifecycle` arms that
  marker, so any arbitration outside an `/adr` session made a decision it could
  not write down (#528).

  The log is not an ADR - its own format doc states H-05's rule verbatim
  ("strictly append-only ... to supersede, append a new entry") - so it is now
  governed by H-05: append freely, never rewrite. ADR files beside it keep the
  marker gate unchanged, and the carve-out is exactly one path wide.

## [0.1.36] - 2026-07-27

### Fixed

- The coverage gate's no-tooling exemption required no evidence. The projected
  `tdd` Phase 5 and `refactor` Phase 2/6 are BLOCK gates that may be passed when
  a surface has no coverage tooling, but the trigger was a bare self-assertion
  by the agent running the phase - and "I could not find the command" is
  indistinguishable, from the inside, from "this surface has none". The two
  demand opposite responses: the first is a STOP under the routines' own hard
  rule, the second is the exemption. An agent that merely failed to locate the
  command could therefore pass a BLOCK gate by describing its own failure as a
  property of the repo, which is the same shape as #507 - a gate that reads as
  satisfied without ever executing.

  The exemption now requires the record to quote the `tech-stack.md` Coverage
  section it read and name the surface it found no command for. No citation, no
  exemption: the phase STOPs instead. The conditions live in
  `includes/maturity-coverage.md` alone, with `tdd`, `refactor` and the
  `coverage-auditor` agent deferring to it rather than each restating them.

## [0.1.35] - 2026-07-26

### Fixed

- The projected `tdd` and `refactor` routines can actually run their coverage
  gate. Both instructed "run the coverage command from `tech-stack.md`" and both
  forbid guessing one - and no such command existed for any tree, so every run
  reached the phase, found nothing to run, and passed through on a gap. A BLOCK
  gate that cannot execute reads as satisfied in every lane, which is worse than
  no gate at all (#507).
- The maturity threshold now names its metric: lines and branches, both binding.
  Previously it said only "minimum coverage", and a report gives four numbers
  that disagree - so the same tree was compliant or not depending on which
  column the reader picked.
- The projected `coverage-auditor` no longer carries its own copy of the
  threshold table. The copies drifted the moment the canonical one gained a
  metric rule, leaving the dispatched auditor applying a one-number test the
  dispatching routine had stopped using. It reads the shared table instead.

## [0.1.34] - 2026-07-26

### Fixed

- A background job that could not start its shell now says why. `launch` refuses
  with `undefined` on five paths; four are policy decisions the caller can
  predict, and the fifth is an environment failure it cannot - a spawn that
  threw. That error was discarded by a bare `catch {}`, so a Git Bash launch
  that failed on CI surfaced only as `expected undefined to be defined`, and the
  runtime's designed, fail-closed refusal was indistinguishable from a real
  fault. The spawn path now reports a per-launch diagnostic, and the background
  bash tool surfaces it instead of the generic block message (#504).
- The refusal detail is drawn from a closed vocabulary - a recognized Windows
  containment reason or an errno shape - never from `error.message`, which
  embeds the resolved shell path and working directory. Following the same
  bounded-reason-code convention already used for the child-process diagnostic
  channel (#428) keeps one convention across both layers rather than widening a
  second channel to free text.

## [0.1.33] - 2026-07-26

### Fixed

- The projected release routine names the latest-badge trap: a sibling must pass
  `--latest=false` explicitly, because omitting the flag is not declining it -
  GitHub defaults `make_latest` to true for any non-prerelease. This is the
  correction to `ca-pi-v0.1.32`, which took the repository's "Latest" badge on
  publication and displaced `ca`'s release from it.

## [0.1.32] - 2026-07-26

### Added

- The projected review routine accepts an inbound pull request as its argument
  (`#123`, a bare number, or a PR URL) and reviews it through the same fleet and
  the same triage funnel as a local diff. Shipped as an ARGUMENT rather than a
  second command, so the Pi command catalog and skill count are unchanged - a
  `review-pr` skill would have been a new public surface whose only difference
  is where the diff came from (#80).

## [0.1.31] - 2026-07-26

### Added

- The projected release routine can target `ca-pi`. It documented `ca` only, so
  the one sanctioned path to a version tag could not read ca-pi's manifest, its
  changelog, or its `ca-pi-v*` namespace - and, notably, could not resolve a
  baseline in a series that had no tag at all. It now reads a Targets row per
  plugin, and ca-pi's row carries the two traps specific to it: Pi installs the
  repository ROOT as the package, so the generated root `package.json` is a
  second manifest that must agree with the plugin's before tagging, and
  `plugins/ca-pi/tools/` is outside the shipped payload while the built bundles
  under `extensions/` are inside it (#382).

## [0.1.30] - 2026-07-26

### Fixed

- The shared guard and anti-slop libraries pick up two enforcement papercuts.
  `git commit-graph` is no longer gated as a commit - the H-09b/H-10b matcher
  took every `commit-*` verb, so object-database maintenance was told to run the
  crypto-compliance gate and the only escapes were a pass certifying nothing or
  an override covering a coverage hole (#485). And the prose-separator-dash
  detector now reads a paragraph at a time, so a separator at a soft-wrap
  boundary is reported instead of scoring zero in both directions (#484).
## [0.1.29] - 2026-07-26

### Added

- ca-pi has a sanctioned release lane, and therefore a way to produce the
  `ca-pi-v*` tag the install instructions have always told users to pin. It had
  none: the hosted release workflow published `ca` and `ca-codex` only, CI
  enforced an independent `ca-pi-v*` version guard the whole time, and no tag in
  the series had ever been cut - so the documented install could not be
  satisfied by anything, and the only way to produce one was to hand-cut a tag
  outside the changelog, tag-state, and read-back guarantees. The lane also
  treats the repository-root `package.json` as a companion manifest that must
  already agree with the plugin's, because Pi installs the ROOT as the package:
  a root disagreeing with the tag would install a version the tag does not name
  (#382).

### Changed

- The projected release routine named two independently-versioned plugins
  instead of four, and routes a sibling release to its hosted lane (#382).
## [0.1.28] - 2026-07-26

### Added

- `$ca-add-dep` gains a bounded **Ephemeral tool run** section: a pinned
  developer tool run once against the repository, adopting nothing, is not a
  project dependency and no longer takes dependency review. The distinguishing
  test is the dependency GRAPH, not the download. Version pinning and the
  approved registry still apply at full strength; a manifest or lockfile change
  is prohibited and verified after the run rather than trusted, because a tool
  that writes one has adopted itself (issue #346, ADR-0023).

## [0.1.27] - 2026-07-26

### Fixed

- The extension bundles are rebuilt against the widened outbound redactor. The
  bundles EMBED the shared farm redactor, so #487's widening (GitLab PATs,
  OpenAI project keys, basic auth in a clone URL, bearer tokens) reached
  `farm.js` but not `codearbiter.js` or `codearbiter-child.js` - a Pi install
  would have kept redacting on the narrower pattern set. The parent's baked
  child fingerprint is regenerated with them.

## [0.1.26] - 2026-07-25

### Fixed

- The anti-slop dash detector no longer flags a definition-list dash
  (`- **term** - meaning`). The rule it enforces is about SENTENCE separators,
  and the style guides are themselves written in that form, so the detector was
  contradicting the guides it exists to serve. A real separator later on the
  same line is still reported: only the definition dash is dropped, never the
  term before it (issue #338).

### Changed

- The detector's document scope now covers authored site prose, and recognises
  `.mdx` as prose rather than keying on `.md` alone.

## [0.1.25] - 2026-07-25

### Fixed

- The ca-pi test suite no longer reads the operator's real
  `~/.pi/agent/auth.json`. `security-controls.md` states that tests use
  disposable Pi homes and dummy credentials and never inspect the real auth
  store; the request fixtures spread `process.env`, so roughly 25 tests that did
  not set their own overrides resolved the actual store. The suite now loads a
  setup file that repoints every home variable Node consults - including the
  Windows `HOMEDRIVE`/`HOMEPATH` pair - plus `PI_CODING_AGENT_DIR` at a
  disposable root seeded with an obvious dummy, so the control is true by
  construction rather than per test file (issue #464).
- The Pi security contract now runs the ca-pi suites FROM the package rather
  than from the repository root. `npm --prefix` moves npm, not vitest, so those
  runs never loaded `plugins/ca-pi/tools/vitest.config.ts` - they executed
  without the package's build-time globals and, latterly, without its setup
  file, which is how a green security row could be reported for a suite running
  against the real home.

## [0.1.24] - 2026-07-25

### Fixed

- `/ca-doctor` no longer redacts its own diagnostics because of where the
  repository happens to live. The outbound redactor matches secret-shaped
  content by trigger word, and nearly every doctor line embeds a filesystem
  path - so a repository or worktree named `...-secret-...` had its `package`,
  `core` and `child` lines each replaced by a redaction notice. A path the
  process already knows is a structural field to compare against, not a value to
  guess at, so the project cwd and the ca-pi package root are now exempt from
  value-shaped matching in this one report. The exemption is exact-literal and
  nonce-keyed: a real credential on the same line still redacts that line whole,
  and a hostile report cannot forge the internal placeholder (issue #449).

## [0.1.23] - 2026-07-25

### Fixed

- A session started inside a linked worktree no longer repoints the MAIN
  repository's git-level enforcement at a path that dies with that worktree.
  The shared enforcer entry lives in the git common dir, so every worktree
  writes the main repo's copy; the SessionStart self-heal happily pinned it to
  the worktree's own plugin root, and pruning the worktree - which is what
  worktrees are for - left the repo silently ungated. An ephemeral enforcer is
  now refused in both the producer and the caller, leaving the previously
  registered install in place. A stale but durable path is still refreshed, so
  the guard is not a kill-switch (issue #441).

## [0.1.22] - 2026-07-25

### Added

- `$ca-cleanup` (`post-merge-cleanup`): the already-merged branch transition,
  which no command owned. It fetches, proves `HEAD` is an ancestor of the
  *fetched* default branch, classifies every dirty and untracked artifact as
  unique, redundant, or superseded, resolves each under its own confirmation,
  fast-forwards with `--ff-only`, and deletes the merged local branch with
  `branch -d`. Anything not provably redundant or superseded counts as unique
  and is never discarded unbidden; the remote branch is never touched
  (issue #308).

### Changed

- ORCHESTRATOR §6 routes on understood intent instead of asking the user to
  retype a command it has already named. Unambiguous and non-destructive intent
  routes directly; probable intent asks once, naming the command; genuinely
  unclear intent gets the chooser. Clarity and risk are separate axes, so an
  irreversible or gate-bypassing command still asks even when the intent is
  obvious. The invariant §6 protects is unchanged: the orchestrator routes the
  command and never improvises the operation, and a missing owner is a routing
  gap to surface rather than a reason to reach for `$ca-override` (ADR-0022).

## [0.1.21] - 2026-07-25

### Changed

- The bundled `release` routine now documents published-tag immutability: a bad
  release is corrected by publishing a new version, never by moving, retargeting,
  or deleting an existing tag, and every newly published tag records where it
  pointed so repository CI can prove it never moved (issue #386). Payload-only
  change to the generated surface; no adapter behavior changes.

## [0.1.20] - 2026-07-25

### Fixed

- A hook payload that is valid JSON but not an object (`[]`, `3`, `"str"`,
  `true`, `null`) is normalized to an empty payload at `read_input()` instead of
  being handed to the guards as a non-dict, where the truthy ones raised
  `AttributeError` out of the guard and the falsy ones were only accidentally
  safe. The envelope is host-produced, not model-produced, so an unreadable
  shape is the same compatibility event as unreadable syntax and takes the same
  documented warn-and-proceed path (ADR-0020).

## [0.1.18] - 2026-07-25

### Added

- `/ca-doctor` now reports whether MCP servers are configured for the active
  host, and that file writes performed through an MCP tool
  (`mcp__<server>__<tool>`) are outside codeArbiter's write gate. The Pi host
  claims no MCP configuration sources, so the line degrades to silence on Pi
  rather than reporting another host's configuration as this install's.

## [0.1.17] - 2026-07-25

### Fixed

- A governed-file notice now names the ADR by its filename stem
  (`ADR-0014-githook-shim-dropin-fail-closed`) instead of its bare number.
  Two ADRs share the number 0014, so the previous notice named two documents
  at once and the reader could tell neither apart.
- The `governs` cache carries a schema key, so a payload upgrade rebuilds it
  instead of serving the old numeric identifiers until a decision file changes.

## [0.1.16] - 2026-07-25

### Changed

- **Breaking (isolation contract):** the isolated Pi child no longer receives
  the operator's provider credential in any form. The parent binds a per-child
  loopback broker on `127.0.0.1:0` and projects a provider configuration whose
  `baseUrl` names that listener and whose `apiKey` references a per-child
  ephemeral token. The child's Pi makes ordinary provider calls to loopback;
  the parent authenticates the token, attaches the real credential, forwards
  upstream, and streams the response back incrementally. `cat`-ing the child's
  projected configuration now yields a token that dies with the child and is
  worthless off-host, which retires the whole encoding-transform exfiltration
  class rather than one instance of it.
- The `auth.json` projection is deleted outright, not merely unused, and the
  provider credential environment variables are no longer copied into the
  child. The parent still reads the operator store, for its own upstream call.
- Providers a bearer-substituting broker cannot serve fail the launch closed
  with the new `isolation-broker` stage identifier: `amazon-bedrock` and
  `google-vertex` (SDK request signing), `github-copilot` and `openai-codex`
  (OAuth refresh inside the child), any `oauth` provider record, and any
  provider with neither an operator `baseUrl` nor a pinned built-in endpoint.
- **Breaking (broker interface):** the broker's upstream authority now requires
  the parent's sensitive-value predicate. Without it the broker cannot tell
  whether a response is handing the operator's own material back to the child,
  so it refuses the authority rather than guessing.
- Headers the child sends are now an allow list of what a provider call actually
  needs, not a deny list of hop-by-hop names. Previously every unrecognised
  child header rode verbatim onto a request carrying the operator's real
  credential, and the credential could be substituted under any header name the
  child chose. The destination origin is fixed, but the operator's `baseUrl` is
  frequently a routing gateway, and gateways route on request headers.
- The upstream response is filtered with the same predicate that already
  suppressed a child echoing operator material through its final message. A
  reflected credential in a response header fails closed; a reflected value in
  the body resets the stream. Clean bytes still stream frame by frame, a
  bounded overlap window catches a value split across two writes, and a
  compressed body is refused rather than relayed unread.

### Fixed

- A model-level `baseUrl` in the operator's provider record skipped endpoint
  acceptance entirely whenever a provider-level endpoint had already been
  captured, so a credential-bearing model endpoint could cross unvalidated.
- Operator-configured provider headers could be duplicated, rather than
  overwritten, by a child sending the same header under a different case.
- A request target carrying an encoded path separator (`/v1/..%2fadmin`) passed
  the route-prefix test and reached the upstream with its encoding intact:
  WHATWG URL normalises encoded dots but not encoded slashes. Encoded
  separators are now refused outright.

## [0.1.15] - 2026-07-25

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

## [0.1.14] - 2026-07-25

### Fixed

- The Pi security contract asserted the exact CodeQL action SHA, so dependabot
  could never land a codeql-action bump on its own - it cannot edit a test, and
  every upgrade failed there until a human hand-edited the literal. The
  assertion now checks the property that matters: both refs are 40-hex commit
  SHAs, and init and analyze pin the same commit, so a split pair cannot
  silently analyse with a different CodeQL than it initialised.

## [0.1.13] - 2026-07-25

### Fixed

- Every Pi audit sink is hardened against link and race redirection. The bridge
  failure audit, the child-dispatch audit, and the confirmed-compaction audit
  each resolved the project's `.codearbiter` governance log from a
  caller-supplied cwd and appended to it directly, which follows file symlinks,
  directory junctions, and hardlinks - so a trusted project could redirect those
  records onto another same-user file and leave the real log without them. All
  five producers now share one primitive that canonicalizes the state directory,
  refuses a linked or escaping one, opens the target no-follow and
  create-exclusive, and re-verifies the opened handle's identity on both sides
  of the append. A failed or hostile sink returns false rather than throwing, so
  no producer's enforcement outcome or fail direction changes.
- Pi native compaction events are validated before they are narrowed. Both host
  records were laundered through a type assertion, and the before-compact
  handler read `event.signal.aborted` and `event.preparation.tokensBefore`
  before its fail-safe block opened, so a malformed or drifted native record
  rejected the host callback with a raw `TypeError` instead of the fixed
  `Pi native compaction failed safely; run /ca-doctor.` diagnostic. Both events
  are now parsed from `unknown` through exact bounded validators covering the
  abort signal, preparation, entry array, reason enum, booleans, and optional
  strings.

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
