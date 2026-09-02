# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

This log tracks the primary `plugins/ca/` release and repository-wide changes.
The independently versioned `ca-codex`, `ca-pi`, and `ca-sandbox` siblings keep
their release details in their own changelogs. Project state under a consumer's
`.codearbiter/` is consumer-owned and out of scope. Entries below `2.0.0`
predate the plugin rewrite and are grouped by date.

---

## [Unreleased]

## [2.15.9] - 2026-09-02

### Fixed

- Release-note reconstruction now accepts only exact changelog headings,
  rejects ambiguous `Unreleased` and duplicate sections, and reads the
  regular-file blob from the exact tag and repository root without inherited
  Git repository overrides or replacement objects.

## [2.15.8] - 2026-09-01

### Added

- Review and generic parallel batches now terminate at a read-only verdict
  aggregator, while checkpoint persistence remains a separate non-overwriting
  writer invoked only by the explicit checkpoint workflow.

## [2.15.7] - 2026-09-01

### Fixed

- Update notices now select only the Claude `v*` release series, keep cache
  freshness and latest-version state separate from Codex and Pi, and retain
  the Claude marketplace update command.

## [2.15.6] - 2026-08-26

### Changed

- Plugin-root discovery now treats the executing module location as authoritative, validates the internal normalized root separately from Claude's native root, and fails closed on mismatch, traversal, symlink escape, or an invalid package anchor.
- Shared status-line and hook wiring now preserve host-native root semantics while consuming the same deterministically generated internal kernel across adapters.

## [2.15.5] - 2026-08-24

### Fixed

- Linked-worktree commits now read content-bound security and migration gate markers from the shared main-checkout marker root while keeping branch, diff, and migration-file reads anchored to the operation worktree.

## [2.15.4] - 2026-08-23

### Fixed

- Lock-contention regression tests now use deterministic retry clocks and real-lock event handshakes instead of scheduler-sensitive elapsed-time ceilings and timed holds. This removes intermittent CI failures while preserving the production 0.2-second fail-soft lock budget unchanged.

## [2.15.3] - 2026-08-21

### Fixed

- Codex desktop wrapped execution now preserves its explicit worktree directory through the shared H-01 guard. A valid feature-worktree commit is no longer evaluated as an unrelated session checkout on `main`; direct protected-branch commits remain blocked.

## [2.15.2] — 2026-08-13

### Fixed

- The orchestration mode is now stored one file per session under `.codearbiter/.markers/mode.d/`, replacing the single shared map. Two sessions in one checkout could previously overwrite each other's posture: a session that left `dangerous` for `arbiter` could have `dangerous` silently reinstated by a concurrent write, still authorized by its own earlier audit row. Each session now writes only its own entry, so no flip can revert or drop another's.
- The mode-plane staleness warning reads each session's own entry, so an unrelated session starting up no longer resets the clock on a session that has sat in `dangerous`.

## [2.15.1] — 2026-08-13

### Changed

- `$ca-spike` now carries only its committed findings file back to the parent before deleting the disposable spike branch. Exploratory code and spike commits remain outside implementation history.

## [2.15.0] — 2026-08-12

### Added

- Orchestration **mode plane** (ADR-0030): `arbiter`, `dangerous`, and `ops`. The injected persona is
  now `safety-core.md` plus the active mode's body, composed per turn, and the mode is flipped by a
  whole-prompt-anchored control token intercepted at the prompt seam with no model turn.
- `ops` mode: an advisory carve-out permitting in-channel work that starts, observes, or exercises a
  running system, keyed on the durable artifact produced. Anything mutating tracked files, the index,
  git history, or published state stays routed and refused.

### Changed

- `ORCHESTRATOR.md` is renamed `arbiter.md` and reframed as the arbiter mode's body rather than an
  always-on kernel. Its header records the former name so historical citations stay resolvable.
- Persona injection moved off `SessionStart` to the per-turn prompt seam; a once-per-session event
  cannot express a mid-session posture change. The startup block is now per-mode composable emitters.
- `dev` mode becomes `dangerous`: a general gates-off posture for any repository, with no
  maintainer-only env gate. No enforcement hook reads the mode, so every gate fires in all modes.

### Removed

- The `dev` and `arbiter` mode-entry commands. The mode bodies are the surface. The shared source
  catalog under `core/surface/commands/` drops from 40 to 38, and `ca`'s own visible catalog from
  39 to 38 — each host excludes entries it cannot serve, so a source count is never a host count.

### Fixed

- A compaction could silently clear a live mode, because the mode plane borrowed the legacy marker's
  owner record to decide whether it had seen a session before. It now keeps its own anchor.
- Mode and marker state resolved through two different roots in three places; in a linked worktree a
  transition pair could split across two audit logs, or a stale session go undetected.
## [2.14.1] — 2026-08-12

### Fixed

- Shared bash guard refresh. `_bashguardlib` is re-vendored here from `core/pysrc/`, so `ca` carries
  the same guard as its siblings. The behavior it corrects is Codex execution-workdir handling: an
  explicit workdir is honored, so H-01's branch check reads the repository the command actually runs
  in rather than the process's own directory. Nothing changes for a Claude session — this host never
  sets that workdir — but the payload did, so the version advances with it.

## [2.14.0] — 2026-08-08

### Changed

- The nine chain-internal skills (`brainstorming`, `writing-plans`, `executing-plans`,
  `subagent-driven-development`, `tdd`, `using-git-worktrees`, `dispatching-parallel-agents`,
  `secret-handling`, `crypto-compliance`) carry `disable-model-invocation: true` — their
  descriptions no longer load into every session's registry (ADR-0028). Every route to them is
  now an explicit `{{PLUGIN_ROOT}}/skills/<name>/SKILL.md` path load (routing-table preamble +
  per-site citations), so chains never depended on the hidden entries.
- Frontmatter scalars that start with `[`/`{` or contain `": "` or `" | "` are JSON-quoted
  across commands and skills (the `_yaml_safe_scalar` predicate, now also a skill-author house
  rule) — portability hygiene for hosts that parse frontmatter strictly.

### Fixed

- Documented harness behavior: `feature`, `fix`, and `new-skill` are reserved names suppressed
  from the model-facing registry by the host (typed invocation unaffected; intent routing runs
  through ORCHESTRATOR.md). Recorded in docs/investigations/token-efficiency.md.

## [2.13.0] — 2026-08-08

### Changed

- Tribunal roster consolidated (ADR-0027): the eleven `tribunal-<lens>-reviewer` agents are
  replaced by one generic `tribunal-lens-reviewer` dispatched once per active lens with a
  title-first lens assignment. The lens cards under `skills/tribunal/references/lenses/` are
  now the roster and carry each lens's scope emphasis and required reading; agent count
  28 → 18.
- Gate reviewers share `includes/reviewer-contract.md` (findings format, review output
  template, out-of-scope rule) and the backend/frontend authors share
  `includes/author-tdd-workflow.md` instead of restating those blocks per agent.
- Docs site: the eleven per-lens agent pages are replaced by a generated
  `/reference/tribunal-lenses/<lens>/` collection sourced from the lens cards, with
  redirects from the old agent URLs.

## [2.12.1] — 2026-08-07

### Fixed

- `/ca:release`'s `--dry-run` no longer executes a declared `rebuild`/`generate`
  command — it previously ran the row's rebuild unconditionally, overwriting a
  committed build artifact despite promising not to write anything. Found and
  fixed by a required pre-tag blind agent-judgment exercise.
- Phase 3's `resume_publish` path can now reconstruct release notes from the
  committed CHANGELOG via a new `changelog-section` CLI subcommand, instead of
  depending on a scratch file that does not survive a session boundary.

## [2.12.0] — 2026-08-07

### Added

- Recorded intent now precedes autonomous scoring and spec shaping (ADR-0025).
  SMARTS gains a scoped Step 0 recorded-intent check: it applies to `/ca:sprint`
  scoring and `brainstorming`, while `decision-variance`, the `grader`, and the
  `decision-challenger` are exempt by name, so arbitration keeps ranking the
  record via the Phase 4 authority order instead of conforming to it. The check
  ranks an "answered" outcome by that same order (a user steer outranks the log,
  the log outranks an accepted ADR, an ADR outranks the plans artifacts) and
  never conforms downward silently.
- `/ca:sprint` reads the decision record before Phase 1 spec approval and
  surfaces plausibly-touched ADRs and deferrals at the interactive gate. An
  auto-decision that would contradict an accepted ADR or a recorded deferral is
  a hard gate, with a stale-record valve: gate-time pre-rulings carry, a
  deferral whose recorded re-evaluation trigger has occurred is reopened rather
  than treated as a contradiction, and each record stops a sprint at most once.
  Sprint-log entries carry an `intent:` field pinned after the `confidence:`
  token, keeping harvested board titles clean (fixture-proven).
- `brainstorming` checks feature framings against recorded deferrals and
  backlog items (a resurrection is a fork to ask) and candidate approaches
  against accepted ADRs (a contradiction surfaces with its citation and pairs
  with a supersession fork; it is never silently dropped or recommended bare).
  All new reads are index-first and fail-soft: a repository with no
  decomposition record proceeds untouched, and brownfield repos gain no new
  block.
- The contract is pinned across every host projection by
  `test_recorded_intent_surface.py` (24 deletion mutants killed; ca-codex
  carries no `agents/` surface and is exempted explicitly), wired into CI as
  an explicit step. ADR-0026 (destructive operations declared in the routing
  table, amending ADR-0022) is ratified in this release; its implementation
  ships with the follow-up kernel restructure.

## [2.11.17] — 2026-08-06

### Fixed

- Corrected the 2.11.0 changelog entry's protected-state-registry description
  to name its three enrolled consumers (`release-targets.md`,
  `open-tasks.md`, `done-tasks.md`) instead of claiming it ships empty; the
  same stale "ships empty" claim in `_protectedstatelib.py` and
  `_bashguardlib.py` is corrected to match.
- The release skill's Phase 3 release-notes command used bracket notation
  (`--latest[=false]`), which is prose shorthand and not shell `gh` accepts;
  split into the two runnable commands the surrounding prose already
  describes.
- Pre-flight's clean-tree requirement and the later rebuild step read as
  contradictory in isolation; added a one-sentence note distinguishing the
  entry condition from the later, deliberately-reconciled exception.
- `medium-documents` was cited by bare name in the release skill's changelog
  step while every sibling include in the same sentence carries a full path;
  pathed it to match.
- Fixed a markdownlint MD018 trip in `security-controls.md` (a line began
  with `#175`, which reads as an unspaced ATX heading marker).
- `load_targets()` folded every `OSError` reading a declared release-targets
  file into `AbsentBlockError`, so a file that exists but cannot be read
  (permissions, a directory at that path, a transient I/O error) was
  misreported as "no release-targets block" instead of "could not read it."
  Added `UnreadableTargetsFileError`, a sibling of `AbsentBlockError`, so the
  two failure modes are distinguishable and the CLI exits 4 (not 3) for the
  unreadable case.
- `check_skill_proof_fresh.py` raised `AttributeError` instead of a clean
  error list when a proof artifact's top-level JSON value was an array or
  `null` rather than an object.
- `test_release_trace.py` pinned `PRE_CHANGE_SHA` with an 8-character
  abbreviation instead of the full 40-character SHA.
- `test_consumer_smoke.py` migrated `shutil.rmtree`'s cleanup callback from
  the deprecated `onerror=` (3-arg, exc_info tuple) spelling to `onexc=`
  (3-arg, exception instance).
- The context-creation skill's single-target `release-targets.md` template
  omitted `latest-eligible: true`, disagreeing with the release skill's own
  back-fill detector (`detect_candidate_target`), which emits it for the
  identical shape.
- Added a real-registry regression case for a stale H-22 protected-state
  marker (previously only exercised against a synthetic injected registry).
- `row_assertions()` reported a blank `rebuild: ""` string as a declared
  command instead of "not declared", inconsistent with the sibling
  `provenance_manifest` field two lines below it in the same function,
  which already strips blanks.
- `select_release_target_by_name()` returned the bare string `""` — outside
  its own documented `<target>|none|multiple|unknown` vocabulary — for a
  pair with a blank NAME (e.g. `"=1.2.3"`); it is now ignored like a pair
  with no `=` at all.
- The docs site's `.codearbiter/` directory reference listed `done-tasks.md`
  as written only by `/ca:task archive`, omitting `/ca:standup`'s per-item
  archival sweep, which the very next paragraph already describes archiving
  into the same file through the same helper.
- `release.yml`'s preflight step carried a leftover comment describing the
  OLD positional `select_release_target` call's `arity` contract, directly
  above the correct explanation of the NAME-KEYED `select-target-named`
  call that actually runs there today.

### Documentation

- Marked `specs/release-portable-fixture.md` implemented (was "awaiting
  approval") now that #576 shipped it, and repaired three markdown-table
  breaks and a stale coverage-proof cross-reference (A-6.7/A-6.8) in
  `plans/portable-release-and-protected-state.md`.

## [2.11.16] — 2026-08-06

### Fixed

- `run-pre-tag` now resolves a POSIX-compatible shell (Git for Windows'
  own `bash.exe`) to dispatch a target's declared `pre-tag` commands,
  instead of always dispatching through `cmd.exe` on Windows — so a row
  spelled `"$PY" <script>` (the #601 convention) now runs correctly on
  every platform, not just POSIX. A Windows host with no POSIX shell
  reachable at all now reports a distinct "could not run" diagnosis
  (exit 9) rather than misreading the absence as drift. This repository's
  own `.codearbiter/release-targets.md` `pre-tag` rows are rewritten from
  hardcoded `python3` to `"$PY"` now that the fix makes it portable
  (#602).

## [2.11.15] — 2026-08-05

### Added

- INDEX.md / routing-table.md consistency is now a CI-checked invariant
  instead of an authoring discipline: `check_routing_index_parity.py`
  fails the build when a skill/routine/agent is missing its INDEX row,
  an INDEX row points at nothing, or `includes/routing-table.md` routes
  to a name that does not exist — across all four generated surfaces
  (`core/surface`, `ca`, `ca-codex`, `ca-pi`). `skill-author`'s routing-
  integration phase now cites the check instead of re-stating the
  hand-verification it replaces (#592).

## [2.11.14] — 2026-08-05

### Added

- `/ca:release --dry-run` is now real: it runs Pre-flight and Phase 1's
  read-only version derivation, then reports the target, the derived
  version and rationale, the per-commit classification, and the resolved
  declared row, without writing a changelog entry, bumping a manifest,
  committing, or tagging (#565).
- A new `uncovered_intent` helper (`_intentlib.py`) backstops
  `writing-plans`' bijective plan/criteria check with a citation check
  against the spec's own scope bullets and a linked issue's acceptance
  checkboxes, catching a criterion that both a plan and its own spec
  quietly missed (#566).

### Fixed

- `writing-plans`' Phase 4 gate is reframed to state only what bijection
  actually proves — that a plan and its `AC-NN` ledger agree with each
  other, never that the ledger itself is complete — and both
  `brainstorming` and `writing-plans` now ask an explicit negative-judgment
  question ("if every criterion passed, what would still be broken?")
  that a bijective check cannot mechanize (#566).

## [2.11.13] — 2026-08-05

### Fixed

- Six `.github/scripts/test_release_lib.py` governance rules that pin
  load-bearing sentences in the release skill — the footer BLOCK /
  never-auto-fill rule, the publish read-back rule, the immutable-tag hard
  rule, the pre-tag BLOCK-on-nonzero rule, and two re-run HIGH rules
  (`tag_sha` peeling, back-fill's `latest-eligible` declaration) — had every
  anchor token also occurring elsewhere in the skill, so the sentence each
  one names could be deleted while the rule stayed green. Each is now
  re-anchored on a span unique to its own guarded sentence, verified against
  the source and all three rendered payloads (`ca`, `ca-codex`, `ca-pi`),
  with a pinned RED/GREEN mutation proof against the real skill text (#571).

## [2.11.12] — 2026-08-05

### Fixed

- The git-level hook backstop (#161) could run from an arbitrarily stale
  host plugin cache — a Codex install that predated the #279 sensitive-scan
  exemption resurrected that exact false positive, blocking a commit whose
  only "sensitive" lines were the crypto/secret gate's own machine-written
  audit rows, with no in-session exit but an override. Each live host's
  session now records a content-addressed freshness heartbeat
  (`.git/codearbiter-hooksd/<plugin>.seen`) alongside its registered
  enforcer entry; the generated shim skips a registered entry whose
  heartbeat is missing or stale relative to a fresher registered sibling,
  deferring the verdict to whichever entry a live session most recently
  confirmed, rather than letting an unrefreshed cache author a block.
  `/ca:doctor` now surfaces a stale drop-in entry before it can produce a
  false block (#556).

## [2.11.11] — 2026-08-05

### Fixed

- The H-11 authoring-marker freshness window is now a single declaration
  (`_hooklib.MARKER_FRESHNESS_MINUTES`), imported by every enforcement flank
  that used to hardcode its own copy of the literal (`pre-write.py`,
  `pre-edit.py`, `_bashguardlib.py`, `git-enforce.py`,
  `_protectedstatelib.py`) — a change to the window now moves every flank
  together instead of silently desyncing them (#567).
- `_releaselib.py`'s unreachable `_PRERELEASE_MARKERS` dead code — proven
  unreachable behind the anchored release-tag regex — is removed rather than
  left as unexplained dead code shipped to every consumer (#568).

## [2.11.10] — 2026-08-05

### Fixed

- Linked-worktree sessions could record a security/migration gate pass that
  the H-09b/H-10b/H-14 commit guards would never see: `security-pass.py` and
  `migration-pass.py`, run bare via a Bash tool call (no `CLAUDE_PROJECT_DIR`
  in that shell), wrote their marker under the worktree's own (gitignored)
  `.codearbiter/.markers/`, while the guards read it from the main checkout.
  A new `marker_root()` seam (`hostapi.Host`) gives both sides the same
  main-checkout answer without moving the diff/migration SCAN root, which
  must stay bound to the tree actually being committed (#604).
- `test_colorlib.py`'s palette-compatibility tests read the real project's
  `.codearbiter/` state when rendered via subprocess with no explicit `cwd`,
  so a maintainer's own accumulated audit-log rows could make a required
  custom-palette color intermittently disappear from the assertion window.
  Isolated to a synthetic, in-fixture `.codearbiter/` (or none at all), plus
  a new test that appends adversarial override/gate-event/task rows and
  proves the palette-completeness check still holds (#552).
- Ten `test_git_hooks.py`/`test_repo_resolution.py` tests failed whenever the
  suite itself ran from inside a linked git worktree (subagents do this
  routinely): `_githooks`'s own `__file__` resolved to an ephemeral path,
  which the existing `is_ephemeral_path` safety check (#441/ADR-0014)
  correctly refused to register into a fixture's shared drop-in dir. Fixtures
  now resolve `_githooks`'s enforcer path from a durable temp-dir copy of the
  hooks payload (`durable_plugin_copy`, the #442 fix's existing pattern).

## [2.11.9] — 2026-08-05

### Fixed

- H-05/H-11/H-18 (the `.codearbiter` audit logs, ADRs under `decisions/`, and
  `CONTEXT.md`) gain the interpreter leg H-22/H-19 already carried — an
  inline-code one-liner (`python3 -c "open('overrides.log','w')..."`, `py
  -c`, `pwsh -Command`) no longer walks past all three shell flanks (#574).
- H-22's git-restore leg now also covers restoring the ENCLOSING DIRECTORY
  of a registered file (`git checkout HEAD -- .codearbiter/`), not only the
  bare basename, and a package manager's `install` SUBCOMMAND (`pip
  install`, `npm install`, `cargo install`, …) no longer false-blocks
  against coreutils' `install` verb (#575).
- The Codex host notes' hook-safe audit-log append recipe no longer directs
  Windows PowerShell 5.1 users to bare `>>`, which can write a UTF-16LE tail
  onto an existing UTF-8 log; the recipe now uses an explicit UTF-8-no-BOM
  `[System.IO.File]::AppendAllText` append with a documented verification
  step (#594).

## [2.11.8] — 2026-08-05

### Fixed

- Every command/skill surface that spelled the interpreter fallback as
  `python3 X || python X` now resolves the interpreter once, by presence,
  before invoking a helper (#577). The `||` fold branches on the helper's
  EXIT CODE, so any helper answer that carries information as a nonzero code
  (e.g. `taskwrite.py archive`'s "archive could not be read") got silently
  re-run under `python` and had its verdict replaced by the second run's.
  `plugins/*/hooks/hooks.json` is deliberately unchanged — its pass/fail
  hooks carry no exit-code vocabulary to lose.

## [2.11.7] — 2026-08-05

### Changed

- `tdd` Phase 2 gains a rationalization guard: the four known excuses for
  skipping the red test ("too simple to fail first", test-after equivalence,
  "would restate the implementation", "already covered") paired with their
  rebuttals — the already-covered rebuttal carrying its own falsifying
  instrument. A/B-validated against the prior skill before shipping (7/7 hard
  requirements both arms, zero over-blocking, sharper domain grounding).
- `skill-author` Phase 4 adopts the evidence-lens checklist (issue #612):
  rationalization guards at tempting gates, instruments over self-report,
  recommendation with counter-case, mechanize-don't-accrete, and
  letter-vs-spirit — plus A/B validation for behavior-changing gate revisions.

## [2.11.6] — 2026-08-05

### Changed

- The orchestrator persona is restructured on measured A/B evidence (#609):
  hard rules move to the head of the document, a rationalization guard and a
  letter-vs-spirit rule intercept gate-skipping, every user-facing ask leads
  with a recommendation and its strongest counter-case, a suspicious gate is
  diagnosed before any bypass, and the startup-presentation instructions move
  out of the always-on persona and into the SessionStart briefing itself —
  roughly 20% shorter always-on persona with no observed behavioral
  regression across the tested scenario suite.

## [2.11.5] — 2026-08-04

### Changed

- Modernized the `brainstorming` skill for capable models: bundled ideas split
  before refinement, candidate approaches shaped with one recommendation,
  parameter-level choices decided and recorded while genuine forks are asked in
  full, a breaker stops non-converging refinement loops, and the spec is
  mechanically self-reviewed and adversarially challenged before approval.

## [2.11.4] — 2026-08-04

### Fixed

- The orchestrator no longer asks "did you mean" when it has already resolved
  the exact command and its complete argument. `ORCHESTRATOR.md` §6 now draws
  the tier-1/tier-2 boundary (ADR-0022) by what is already resolved rather than
  by temperament: an exact command with a complete argument and no competing
  candidate is unambiguous by definition and routes directly. Tier 2 is
  reserved for a genuinely incomplete reading — an argument you'd have to
  invent, or a second plausible command — and the destructive set.

## [2.11.3] — 2026-08-04

### Fixed

- `post-merge-cleanup` (#586): Phase 1's containment proof no longer relies on
  SHA-ancestry alone, which fails for every ordinary squash merge in this
  repo's default merge mode. A squash merge is now proven by the merged PR
  record (`headRefOid` == HEAD), reported alongside the ancestry check's
  negative result as a fact rather than a failure. Phase 3's blocked-checkout
  STOP now distinguishes a genuinely conflicting kept artifact from a stale
  local default ref. Phase 4 fast-forwards the local default ref before
  checking it out, so a stale ref can no longer be misattributed to a kept
  artifact. Phase 5 documents why `git branch -d` can already accept a
  squash-merged branch via its upstream, and sanctions `git branch -D` only
  when this run's Phase 1 proof was the PR-record squash proof and `-d`
  refused.
- `standup` (#596): stale worktrees can now be confirmed for removal as one
  explicitly enumerated group naming every member, instead of forcing one
  confirmation per worktree; declining the group falls back to per-item
  confirmation. Branch pruning documents the matching squash-merge `-D`
  exception.

## [2.11.2] — 2026-08-04

### Fixed

- Gave the release lane's internal tree-state probe the same audit-scratch
  exemption the skill already requires everywhere else, so a mid-window
  `gate-events.log` append is no longer misdiagnosed as a mutating pre-tag
  command.
- Split `run-pre-tag`'s failure diagnosis into four distinct exit codes: a
  declared command that ran and reported drift, one that mutated the tree,
  one whose interpreter or program could not be located at all, and a
  tree-state probe failure — each with its own remedy, so "could not run"
  is never reported as "ran and disagreed".
- Exported the resolved interpreter to every declared release-lane command
  via a `PY` environment variable, so a declared row can portably spell
  `"$PY"` instead of a hardcoded interpreter.
- Mechanized the release lane's version-bump arithmetic behind a new
  `apply-bump` subcommand, closing the one step still left to hand
  derivation.
- Floored the release lane's first-release footer check on the earliest
  addition of either `CONTEXT.md` or `release-targets.md`, so a Back-fill
  consumer's own first release can clear Phase 1 step 3.

## [2.11.1] — 2026-08-03

### Fixed

- Restored fresh-clone release-trace verification by pinning its historical
  reference to the reachable pre-migration commit with the same release-library
  bytes.
- Stabilized repeated statusline-render tests by isolating their unrelated
  repository-dirty probes.
- Kept the landing page's guarantee cards aligned by resetting inherited
  sibling-flow spacing at the card boundary.

## [2.11.0] — 2026-07-31

### Added

- **A protected-state registry, enforced as hook class `H-22`.** Project-state
  files under `.codearbiter/` can now be guarded, each registry entry carrying
  its own policy rather than one uniform rule: `marker-gated` admits a write
  only under a fresh authoring marker, `helper-only` hard-blocks every tool
  path so a sanctioned helper's own file I/O is the only route, and
  `append-only` admits mutation solely through an append verb.

  `open-tasks.md` is deliberately not marker-gated. `taskwrite.py` is already
  its only blessed writer, and because it writes with Python file I/O whose
  argv never names the file, it is invisible to every flank by construction. A
  marker would therefore add nothing for the helper while *admitting* an agent
  that hand-composes board markdown under it, which is the inversion of the
  goal.

  The class registers on all three flanks. A one-flank implementation passes a
  Write-door test while `echo … >> file` still lands, so `pre-write`,
  `pre-edit`, and the shell guard each carry it. Two non-regressions are
  pinned because they are load-bearing rather than convenient: `git add
  open-tasks.md` must pass, since `commit-gate` runs exactly that on every
  retained board flip and a git verb in the list would make commit-gate block
  itself; and a filename appearing in a helper's argv as description text must
  pass.

  The shipped registry enrolls three consumers: `.codearbiter/release-targets.md`
  (`marker-gated`), `.codearbiter/open-tasks.md` (`helper-only`), and
  `.codearbiter/done-tasks.md` (`append-only`). It stays code constants rather
  than disk-loaded state, which would otherwise let a repo un-protect its own
  board by editing a file. Recorded as ADR-0024.

- **The release mechanism is now portable.** `_releaselib` splits into a
  host-neutral mechanism under `core/pysrc/`, generated byte-identically into
  all three governance plugins, and repo-specific data that moves into a
  declared `.codearbiter/release-targets.md`. Repo facts that were defaults
  become required parameters, since a default is how a repo assumption survives
  a portability refactor unnoticed.

  This closes a defect that made `/ca:release` unrunnable anywhere but here:
  its first pre-flight step called a helper that was never in the plugin
  payload.

### Fixed

- **A consumer whose tag prefix contained `-beta`, `-rc`, or `-alpha` lost every
  release in that series.** The pre-release filter substring-tested the whole
  tag including the prefix, so a project tagging `web-beta-v1.2.0` received the
  never-released sentinel and would have been offered a first-release baseline
  despite having releases. The test now applies to the version portion only.
  Invisible in this repository, live in a consumer's.

- **The release skill cited a CI path that only exists in this repository.** A
  parenthetical pointed at `.github/actions/publish-release/action.yml` to
  explain where the tag-peeling helper came from. That file ships in no
  payload, so every consumer read a pointer to nothing - the exact
  this-repo contamination the portable-fixture work exists to remove. The
  explanation stands without the path.

- **The tag was written before the check that says whether writing it was
  safe.** Phase 2 named `git tag -a` first and classified the publish state
  afterwards, so an agent following the step in written order created the ref
  and only then asked whether it should have. `git tag` now appears once, in
  the `publish_fresh` branch, after classification.

- **Three of `classify`'s six arguments had no stated source, and a fourth had
  no local one.** `head_sha`, `tag_version`, and `manifest_version` were named
  but never sourced, so each was supplied from whatever the reader inferred;
  `release_nondraft`'s only origin, `gh release view`, reports "no remote" and
  "no such release" through the same non-zero exit. All four now carry an
  explicit derivation, and the ambiguous `gh` failure STOPs instead of passing
  a guess into the one branch that decides whether a published release is
  republished.

- **`<summary>` in the Release title convention was never defined.** It
  appeared exactly once in the skill - in the convention itself - so the title
  of every published Release was improvised. It is now derived from the
  changelog section the release already composed.

- **Every Markdown heading was silently deleted from composed tag messages.**
  `git tag`'s default cleanup mode is `strip`, which treats `#`-prefixed lines
  as comments and removes them. A Keep-a-Changelog section is entirely
  `#`-prefixed, so the version heading and every group heading vanished,
  leaving an undifferentiated bullet list that no longer says which version it
  describes. This already happened to this repository's published `v2.8.13`,
  and a published tag is immutable, so it can only be superseded. The lane now
  passes `--cleanup=verbatim` and then re-reads what git actually stored to
  confirm the heading survived - neither of the two guards the skill already
  named could see this, because both read the section file rather than the tag.

- **The publish classifier was fed a stale version and an un-negated flag.**
  Two arguments added one commit earlier were sourced wrongly.
  `manifest_version` said to read the manifest "as Pre-flight read it" - but
  Pre-flight reads it before the version bump, and the stale value makes the
  classifier return `abort_mismatch`, a terminal stop, on a release where
  nothing is wrong. `release_nondraft` was sourced from `gh release view --json
  isDraft`, which emits a JSON object rather than a bare boolean and carries
  the opposite polarity, so `already_published` was unreachable. Both now carry
  an exact command and, for the second, an explicit inversion.

- **A check the skill required could not be run.** Both phases named
  `release_dates_consistent` and Phase 2 called it mandatory, but no CLI
  subcommand exposed it, so it was reachable only by importing the module -
  something the skill never instructs. Added as `dates-match`.

- **The first release of every back-filled project died on a sentinel.** With
  no tag yet in a series, the tag helper returns the literal string `<none>`,
  and the skill spelled the commit window `LAST_TAG..HEAD` - so the command it
  handed the operator was `git log <none>..HEAD`, which exits 128 with `fatal:
  bad revision`. The prose called that state "normal, not an error" while
  giving a command that cannot survive it, and it lands on exactly the
  consumers the back-fill lane exists to serve. The window is now derived into
  `$WINDOW` (`HEAD` when there is no tag, `<tag>..HEAD` otherwise) before any
  command uses it.

- **Version derivation now has one base instead of two floors.** The bump
  applies to `$BASE_VERSION` - the maximum of the last tag's version and the
  highest version any declared manifest carries - and the strictly-greater
  assertion runs once against it. The two-floor form this replaces hard-blocked
  a legitimate release: a project holding a `v1.2.0` tag and a `1.4.2` manifest
  derived `1.3.0` from the tag, then failed its own manifest floor, and the
  step said only "must exit 0" with no remedy. It also demanded a comparison
  against the last tag, which on a first release is the string `<none>` - not a
  version, so that comparison was unrunnable on exactly the path back-fill
  exists to serve. One base removes both.

- **The manifest reader now follows the file's format.** Only the JSON form was
  named, so a declared `pyproject.toml` raised `JSONDecodeError`. The
  `<manifest_version>` argument also reads the *first* declared manifest while
  the base reads the *maximum* across all of them - deliberate, but safe only
  because the bump touches every declared path, so that coupling is now stated
  rather than left to be discovered when a partial bump turns a healthy release
  into a terminal stop with a misleading reason.

- **A project that had shipped without tagging was released backward.** With
  no tag in its series the lane took `0.0.0` as the base, so a package whose
  manifest already read `1.4.2` derived `0.1.0` - and the manifest bump then
  wrote that over it, moving the project's own version backward. Every gate
  passed, the manifest-equality assertion included, because the bump had just
  made it equal. The base is now the highest version any declared manifest
  carries, taken across all of them rather than the first, and the
  strictly-greater assertion runs against that floor as well as against the
  last tag - through a new `semver-greater` command, since the arithmetic the
  hard rules say must never be guessed had no tool behind it.

- **Three smaller wiring defects on the ordinary path.** The possibly-empty
  tag sha was passed unquoted, and on the fresh-publish path - the common case
  - an empty unquoted argument does not become an empty positional, it
  vanishes, so the classifier received five arguments and exited 2. Reading
  the manifest version named no command where every neighbouring argument
  named one. And the tag round-trip check read `git tag -l --format=%(contents)`,
  a reconstruction that appends a newline and so cannot detect a byte
  difference even in principle; it now reads the raw object.

## [2.10.8] — 2026-07-30

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

## [2.10.7] — 2026-07-30

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

## [2.10.6] — 2026-07-30

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

## [2.10.5] — 2026-07-30

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

## [2.10.4] — 2026-07-29

### Fixed

- **The symlink-safe worktree writer accepts an absolute destination spelled
  through a link (#541).** `writeWorktreeFile` canonicalized the worktree ROOT
  but resolved the caller's absolute path as-is, then compared the two — so a
  caller building a destination from the root it had itself passed in was
  refused for writing inside its own worktree. Same root cause as #539, one
  module down, and it never reproduced on a host whose paths are already
  canonical.

  Only the ANCESTOR chain is canonicalized; the final component stays literal,
  so a symlinked destination is still refused rather than written through. Like
  #539 this tightens the guard: a path whose ancestors traverse a link out of
  the root is now caught by containment instead of relying on a later check.

- **A timed-out farm test no longer abandons a live subprocess (#542).** Every
  launch in `farm.test.ts` is a real child process and none were tracked, so a
  vitest timeout left one running with the temp directory as its cwd and the
  teardown then failed `EBUSY` — reporting the cleanup instead of the timeout
  that caused it. Children are now reaped before the directory is removed, and
  the removal tolerates Windows' asynchronous handle release.

  The heaviest case (12 tasks at `FARM_CONCURRENCY` 6) also gets a budget drawn
  from measurement rather than a nudge: 3553 ms isolated on a developer box
  against a 5000 ms default, 5331 ms under load on a CI runner. It is now 30 s —
  bounded, so a genuine hang still fails. The case itself is unchanged;
  concurrency stays at 6 and every assertion stands.

## [2.10.3] — 2026-07-28

### Fixed

- **The farm worktree containment check canonicalizes both paths before
  comparing them (#539).** It was lexical, and `path.resolve` neither expands a
  Windows 8.3 short name nor follows a link — so two spellings of one directory
  compared as different paths and a worktree root genuinely inside the repo was
  refused, with a message telling the operator to point it inside the repo where
  it already was. The only escape was `FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1`,
  which disables the guard outright to work around a false positive in it.

  Surfaced by #521's coverage-union job the first time this tree ran on Windows
  CI: 15 failures, all downstream of one refusal, because the runner's tmpdir is
  `C:\Users\RUNNER~1\...` while git reports `C:/Users/runneradmin/...`. It does
  not reproduce on a developer box whose profile path is already 8.3-clean.

  The change **tightens** the guard: resolving links means a junction inside the
  repo whose target is outside is now refused, where the lexical check accepted
  it. That was never exploitable — `fs.rm` removes the link rather than
  recursing through it, measured — but accepting it was still wrong. A missing
  root is normal and is canonicalized by walking up to the deepest existing
  ancestor; any realpath failure that is not absence refuses, per #163.

## [2.10.2] — 2026-07-28

### Changed

- **A quoted coverage figure is now the union across a tree's supported hosts,
  per tree (#521).** The command is identical on every platform; the report is
  not. Code behind a platform fork cannot execute off its own platform, so a
  single-host report scores the other platform's arm as uncovered no matter how
  well tested it is — measured here, `exec.ts` reads 87.50% branches on Windows
  against 76.38% on Linux, an 11-point gap that is entirely `awaitTaskkill` plus
  the win32 `treeKill` arm on one side and the POSIX arm on the other.

  That matters beyond arithmetic: `treeKill` is a process-containment path, so
  under a single-host rule a genuine gap in it is indistinguishable from the
  platform artifact.

  `includes/maturity-coverage.md` gains the rule and `tdd` Phase 5 now requires
  the measuring host to be named. Trees with no platform fork stay single-host —
  a union of identical reports is the same report.

## [2.10.1] — 2026-07-28

### Fixed

- **The farm dispatcher serializes access to git's worktree registry (#515).**
  `.git/worktrees/` is a shared registry that git mutates non-atomically:
  `git worktree add` scans the existing entries while creating its own, so a
  second concurrent add could read a sibling's directory after it existed but
  before its `commondir` was written. The dispatcher ran up to
  `FARM_CONCURRENCY` prepare sequences at once with no lock, so one task would
  intermittently escalate at `attempts: 0` with
  `worktree add failed: … failed to read .git/worktrees/<other>/commondir`,
  flipping an otherwise green run's exit code from 0 to 2.

  Measured directly against real git: six concurrent prepare sequences over 40
  rounds produced two failures with that signature, and zero when serialized.

  Worktree creation, removal and prune now run under a dedicated lock, separate
  from the existing merge lock so that short registry calls never queue behind a
  long merge. Concurrency is unchanged — the worker API call, the gate and the
  tests all still run in parallel; only the brief registry mutations are
  serialized, and the retry backoff deliberately runs outside the lock so one
  worker's retry schedule cannot stall the others.

## [2.10.0] — 2026-07-27

A MINOR bump, not a patch: this window adds `ca-pi` as a fourth sibling plugin,
`/ca:cleanup`, inbound-PR review, multi-plugin release lanes, and the §6 routing
model — nine `feat` commits since the 2.9.1 section, no breaking changes.

Cut so the fixes below actually reach installed users. They had been merged onto
an untagged `2.9.1`, and `claude plugin update` is a no-op while the manifest
version string is unchanged — so a populated `2.9.1` plugin cache stayed frozen
at the pre-fix payload. The maintainer's own session was still being blocked by
the pre-fix copy of a hook guard whose fix had already merged. The gate that is
supposed to catch this keys on the git tag rather than the manifest, and `v2.9.1`
was never tagged; that gap is #530.

### Fixed

- `decision-variance` could not record a decision. Its Phase 4 is required to
  append every SMARTS arbitration to `.codearbiter/decisions/decision-log.md`
  "immediately, never batched" — and H-11 refused every write to it, because
  H-11's path rule matched any `.md` under `decisions/` and therefore governed
  the arbitration log as immutable ADR history requiring the `/adr` authoring
  marker. Only `decision-lifecycle` arms that marker, so any arbitration outside
  an `/adr` session made a decision it could not write down (#528).

  The log is not an ADR. It is an append-only audit artifact — its own format
  doc states H-05's rule verbatim ("strictly append-only … to supersede, append
  a new entry") — so it is now governed by H-05 instead: append freely, never
  rewrite. ADR files beside it keep the marker gate unchanged, and the carve-out
  is exactly one path wide: `old-decision-log.md` and a nested
  `sub/decision-log.md` are still ADRs. (`decision-log.md.bak` is in neither
  guard set — it does not end in `.md`, so it was never an ADR path either.)

  Adversarial review caught two holes in the first cut of this, both of which
  left the append-only log destructible from the shell. The carve-out was
  case-insensitive while H-05 — the guard taking over for that file — is
  case-sensitive on both flanks, so a case-varied spelling was stripped from one
  guard's view and invisible to the other; on Windows/NTFS and default
  macOS/APFS that spelling resolves to the real file. And `New-Item -Force`,
  which truncates, was covered by H-11 but not H-05, so the log lost that verb
  on reclassification — a gap the flat audit logs shared, now closed for all of
  them. The carve-out also lacked a right-edge anchor, so the log's path
  shielded any token beginning with it.

  Consequence of the deadlock, for the record: blocked from writing DECISION-0029
  during this session, the assistant cited it in `farm.ts` anyway — a dangling
  governance pointer that would have shipped inside `farm.js`. Caught in review
  and retracted (#526).

- The coverage gate's no-tooling exemption required no evidence. `tdd` Phase 5
  and `refactor` Phase 2/6 are BLOCK gates that may be passed when a surface has
  no coverage tooling, but the trigger was a bare self-assertion by the agent
  running the phase — and "I could not find the command" is indistinguishable,
  from the inside, from "this surface has none". The two demand opposite
  responses: the first is a STOP under the skills' own hard rule, the second is
  the exemption. So an agent that merely failed to locate the command could walk
  through a BLOCK gate by describing its own failure as a property of the repo,
  which is the shape of issue #507 — a gate that reads as satisfied without ever
  executing.

  The exemption now requires the record to name the surface and quote, from
  `tech-stack.md`, either the whole Coverage section or the passage stating the
  absence for that surface by name. A partial quote that stops before the
  commands does not count, and a section that merely never mentions the surface
  must be quoted in full so the silence is visible and judged rather than
  asserted. No citation, no exemption: the phase STOPs. The record travels into
  the PR description, so the claim is still falsifiable when a human reviews and
  not only while the lane is live.

  **This repo takes the exemption.** `site/` and the Python hooks have no
  coverage command, and `tech-stack.md` had a local copy of the old, laxer rule
  for exactly those surfaces — naming only `refactor` Phase 2, telling an agent
  to "say so" rather than cite. That copy is now a pointer, which is the whole
  point: the conditions live in `includes/maturity-coverage.md` and nowhere else.

- The farm's mutation-escalation note stated survivor counts it had invented.
  It interpolated the number of mutants *evaluated* under a "survived" label, so
  a task whose test caught 1 of 10 was rejected with "mutation score 0.10 (10
  mutants survived)" — a claim the score in the same sentence disproves. This
  note is the entire operator-facing explanation for a hard-escalated task and
  is fed back into the next worker's prompt, so a wrong count both misled a
  human and misinformed a retry (#525).

  The root cause was the `MutationResult` type, not the format string. A
  pluggable `FARM_MUTATION_CMD` is only required to print a trailing JSON line
  with a numeric `score`; `total` and `survived` are optional. But the type
  declared all three fields as always present, so the parser had to invent the
  missing ones — an empty survivor list and a `99` denominator — and once
  invented, nothing downstream could tell a fabricated count from a measured
  one. `evaluated` and `survivors` are now optional, absent when the producer
  did not report them, and the note states a survivor count only when there is
  one to state.

  **If you use a pluggable `FARM_MUTATION_CMD`,** a hook that reports only a
  score now yields `gaming: mutation score 0.05 — …` with no survivor clause,
  where it previously claimed `(99 mutants survived)`. A hook that reports
  survivors but no total yields `(9 survived)` rather than inventing a
  denominator. A hook whose survivor ids are not strings keeps its true count;
  an earlier cut of this fix filtered them out and reported `(0/10 survived)`
  while escalating the task for its survivors.

  **Behaviour change to the escalation gate, for hook users only.** The
  `evaluated >= 5` floor exists to refuse hard-rejecting a task on thin
  evidence. It previously substituted `99` for an unreported mutant count, so a
  hook that never said how many mutants it ran cleared the floor and could get a
  task rejected on no evidence at all. It now requires a count the hook actually
  reported.

  Measured across 27 hook shapes, exactly four change, all in the same
  direction (escalate → warn) and all under the same rule — *the producer
  stated no usable count*: `{"score":0.05}` (absent), `"total":null`,
  `"total":[10]`, and `"total":1e400` (Infinity). Nothing changes for the
  built-in mutator, which always reports a count, nor for any hook that reports
  a real one, and nothing newly escalates.

  A count is read as reported when it is a number or a numeric string, so
  `"total":"10"` from a shell hook that quotes its numbers still clears the
  floor exactly as before. An intermediate version of this fix rejected quoted
  numbers, which silently disabled the anti-gaming gate for such hooks at every
  count.

- `tdd` Phase 5 and `refactor` Phase 2/6 can actually run. Both instructed
  "run the coverage command from `tech-stack.md`" and both forbid guessing one -
  and no coverage command existed, in any tree, for any of the four plugins. So
  every run reached the phase, found nothing to run, and passed through on a
  gap. A BLOCK gate that cannot execute is worse than an absent one: it reads as
  satisfied in every lane, which is the same defect class as issue #501's five
  suites that ran on nothing (#507).

  `refactor` was the worse casualty. Phase 2 is "Behavioral parity coverage
  proof" - the gate that justifies the lane by showing the tests can detect a
  behavior change BEFORE production code is touched - and it rested entirely on
  a command that did not exist.

- The threshold table never said WHICH metric, and the omission was
  load-bearing rather than cosmetic: a report gives four numbers that disagree,
  so "≥ 70%" with no column named is not something anyone can be held to. It is
  now **lines and branches, both binding**. Lines catches code no test reaches
  (issue #504 was exactly that - a `catch` with zero executions inside a
  750-test suite); branches catches the untaken half of a condition a test does
  reach, which lines alone reports as covered.

- A contract test now asserts that any command a gate reads from
  `tech-stack.md` is actually defined there, so the next gate cannot ship
  pointing at nothing. It goes further than the text check that shape usually
  gets, because adversarial review broke three weaker versions of it in
  succession:

  - it **runs for the files it guards** — the gate prose and `tech-stack.md`
    are registered in the `impact` filter and the push trigger, so a PR that
    only deletes the coverage section no longer skips the one job that checks
    it (the same omission as #384, #403/#404 and #416);
  - it **resolves the command**, asserting the named `npm run <script>` exists
    in the named manifest rather than trusting that the prose is
    self-consistent;
  - it is **complete by construction**, deriving the expected set from the
    `plugins/*/tools` manifests, so a new tree cannot be added undocumented;
  - it is **checked in both directions**, so an entry guarding nothing fails
    loudly instead of looking like protection. Running that check for the first
    time surfaced a third command reader nobody had noticed —
    `dependency-reviewer` reads an `audit` command from the same file.

  Every branch above is mutation-verified: six mutations, each confirmed to
  fire, against a control that passes.

### Added

- `/ca:review` can review an inbound GitHub pull request, not only the diff you
  just wrote: `/ca:review #123` fetches that PR's diff and runs the same fleet,
  the same path matrix, and the same `finding-triage` -> `checkpoint-aggregator`
  funnel. A gate that only reviews its own author's change is a linter, not a
  team gate, and reviewing code you did NOT write is where it earns its keep
  (issue #80).

  Deliberately an ARGUMENT rather than a `/ca:review-pr` command. The scope
  resolver already took one, the fleet is scope-agnostic, and every phase
  downstream operates on a diff regardless of where it came from - so a second
  command would be a whole public surface (the catalog, three host projections,
  the README counts, the site sidebar) whose only distinguishing feature is
  where the diff was fetched from. The command count is unchanged.

  Three guards ride with it. A missing or unauthenticated `gh` STOPs rather than
  falling back to the working diff, which would report a verdict on the wrong
  change under the PR's name. The diff is resolved ONCE, because the fleet runs
  in parallel and a PR updated mid-review would otherwise have reviewers reading
  different code. And posting the verdict is a separate, confirmed step that
  never uses `--approve` or `--request-changes`: a comment on someone else's PR
  is public the moment it lands, and those two flags carry merge authority this
  command does not have.

- `/ca:release` releases any of the four plugins, as one command taking the
  target as its argument (default `ca`, so a bare `/ca:release` is unchanged).
  It could only ever target `ca` before, because `LAST_TAG` resolution matched
  `^vMAJOR.MINOR.PATCH` and nothing else - so the three siblings had version
  guards in CI, a changelog, and a tag namespace, but no sanctioned command that
  could read any of them. Every phase is now written once against a Targets
  table rather than four times: one row per plugin giving its tag namespace,
  manifest, changelog, payload scope, shipped bundles, and whether it may claim
  the repo-wide "Latest" badge (only `ca` may). No new command was added - four
  commands would be four public surfaces to govern and carry for one operation
  whose only difference is which row it reads (#382).
- `_releaselib.last_tag_select` takes the tag namespace as a parameter, and
  `RELEASE_TAG_PREFIXES` is now the single source of truth for it - the same
  register the hosted release lanes' `tag-prefix` inputs are asserted against, so
  the command and the workflow cannot disagree about a namespace. Series
  isolation is a property of the ANCHORED match rather than an exclusion list to
  maintain: `^v` cannot match `ca-pi-v0.1.30`, so a fifth plugin cannot leak into
  an existing series by being forgotten somewhere (#382).

- `/ca:add-dep` gains a bounded **Ephemeral tool run** section. The command
  applied to any download-and-execute, so a one-time analysis tool was pushed
  through project-dependency review — and with no command owning that action,
  the routing loop reached for `/ca:override` for an operation that adds no risk
  at all. The distinguishing test is now the dependency *graph*, not the
  download: anything entering a manifest, a lockfile, or a base image takes the
  existing review unchanged. The carve-out keeps the part of supply-chain review
  that still applies — an exact pinned version and the approved registry — and
  requires one confirmation rather than a review, because the operator has
  already decided not to adopt. A manifest or lockfile change is prohibited and
  *verified* with `git status --porcelain` after the run rather than trusted: a
  tool that writes one has adopted itself, and that stops and takes the full
  review. It is a section rather than a command because a new command would add
  a public surface across three hosts to govern an action whose whole definition
  is that it changes nothing (issue #346, ADR-0023).
- Added `/ca:cleanup` and its `post-merge-cleanup` skill: the already-merged
  branch transition, which no command owned. It fetches, proves `HEAD` is an
  ancestor of the *fetched* default branch, classifies every dirty and untracked
  artifact as unique, redundant, or superseded, resolves each under its own
  confirmation, fast-forwards with `--ff-only`, and deletes the merged local
  branch with `branch -d`. Anything not provably redundant or superseded counts
  as unique and is never discarded unbidden; stashes are report-and-route only;
  the remote branch is never touched. Branch deletion keys off proven ancestry
  rather than `: gone]` upstream state, so a squash-merged branch whose remote
  still exists is recognised as landed (issue #308).
- Added `ca-pi`, the fourth sibling plugin and third governance host, generated
  from the same Python and markdown core as Claude Code and Codex CLI.
- Added a dependency-free, Git-installed Pi package with `/ca-*` aliases,
  `/skill:ca-*` fallbacks, project-trust-gated activation, final tool wrappers,
  native compaction, bounded child dispatch, farm preview routing, diagnostics,
  and cross-platform contract tests for Pi 0.80.5 and Pi 0.80.6.
- Added the reproducible Pi install/live-test runbook and converted the host
  parity ledger to source-visible Claude Code/Codex CLI/Pi evidence.

### Changed

- The release skill named two independently-versioned plugins; the repository
  has four. It now names every series (`v*`, `ca-codex-v*`, `ca-sandbox-v*`,
  `ca-pi-v*`) and routes a sibling release to the hosted dispatch lane instead
  of leaving it undefined. `/ca:release` still owns `ca` itself. The stale count
  was load-bearing in one place: the guidance for resolving `LAST_TAG` and for
  setting `--latest` reasoned about "both plugins", which understated by two the
  set of tags that can shadow ca's baseline or take the "Latest" badge (#382).

- ORCHESTRATOR §6 now routes on understood intent instead of naming a command
  and then asking the user to retype it. Unambiguous, non-destructive intent
  routes directly into the command with every gate intact; probable intent asks
  once, naming the command; genuinely unclear intent gets the chooser. Clarity
  and risk are separate axes, so anything irreversible or gate-bypassing —
  `/ca:override`, merge to the default branch, branch or worktree deletion,
  release and tag publication, `/ca:dev` entry — still asks even when the intent
  is obvious. The invariant §6 protects is preserved by construction: the
  orchestrator routes the command and never improvises the operation, and a
  missing owner is a routing gap to surface, never a reason to reach for
  `/ca:override` (ADR-0022, issue #308).
- Marked the complete `ca-pi` adapter as a Feature Forge `preview`. It is
  available and welcomed for real use, with automated and hosted promotion
  evidence complete, while broader real-world testing continues before any
  claim of 100% validation or stable status.

### Security

- Pi child work now crosses a minimal provider-specific environment, strict
  bounded RPC/JSONL schemas, an enforcement-only child extension, attested
  startup, and whole-process-tree cleanup on cancel, timeout, and failure.
- Pi repository-aware activation requires both the existing opt-in marker and
  affirmative host project trust; unknown or foreign tool replacements fail
  closed.

### Fixed

- A sibling release now DECLINES the repo-wide "Latest" badge explicitly
  instead of omitting the flag. Omitting `--latest` is not neutral: GitHub
  defaults `make_latest` to true for any non-prerelease, so every namespaced
  sibling silently claimed it. Caught by publishing - `ca-pi-v0.1.32`, the first
  sanctioned ca-pi release, displaced `ca v2.8.13` from the position every
  visitor sees. The badge was restored with `gh release edit --latest`, a
  metadata change that moves no ref; the ca-pi release stays exactly where it
  was published.

  The test that should have caught it asserted `--latest` was ABSENT from the
  command log, which is the defect restated as an assertion - absence of the
  flag WAS the bug, so a test demanding absence could only ever agree with it.
  It now asserts the refusal is present, with a fail-closed case for any value
  other than `"true"`.

- `git commit-graph` is no longer gated as though it were `git commit` (#485).
  A word boundary sits between `commit` and `-`, so the H-09b/H-10b matcher took
  every `commit-*` verb. The cost was not the annoyance: the gate told the
  operator to run the crypto-compliance gate for a command that writes no
  objects and creates no commit, leaving only a pass that certifies nothing or
  an `/ca:override` invented to cover a coverage hole. It bit at the worst
  moment too, since a stale commit-graph is exactly what a batch of
  `--delete-branch` merges leaves behind. `commit-tree` stays in scope
  deliberately: it creates a commit object, and a crafted commit plus
  `update-ref` is a real path around H-01. Anything else in the `commit-*` space
  is still gated, so an unfamiliar verb fails closed rather than open.
- The prose-separator-dash detector reads a paragraph at a time instead of a
  line at a time (#484). It required word characters on both sides of the dash
  ON THE SAME LINE, so a separator that landed at a soft-wrap boundary scored
  zero in both directions - the right-hand span on the next line, or the
  left-hand span on the previous one. Three real violations in the site's own
  pages had to be found by hand for that reason. Joining stops at every block
  boundary (blank line, list item, heading, table row, thematic break, fence),
  and each finding still carries the line of its own dash.

- A secret in a farm plan no longer persists in the run's permanent receipt.
  `plan.meta` was serialized verbatim into `.farm/runs/<runId>/farm-report.json`
  and its Markdown sibling, and the run-scoped change made that permanent: the
  old `.farm/farm-report.json` was clobbered by the next run, while
  `.farm/runs/` accumulates with no prune path. `meta.setup`,
  `setupEachAttempt` and `setupInputs` are raw shell-command arrays and
  `apiBaseUrl` is a URL, so a token in a setup command was a perfectly legal
  plan that landed on disk forever. Every free-text `meta` field is now redacted
  at the sink, once, for both receipts. Note this is redaction and not an
  allowlist: `checkPlanObject` is already a closed-object check that rejects
  unknown `meta` keys at parse, so the allowlist the issue proposed would have
  duplicated an existing control and caught nothing — the *allowed* fields were
  the exposed ones (issue #439).
- The artifacts block and the diff-evidence reasons now pass through the file's
  own redaction chokepoint, so raw `git` stderr and filesystem error text cannot
  reach either receipt un-redacted.
- The outbound redactor recognises four credential shapes an adversarial run
  proved were reaching a receipt intact: GitLab PATs (`glpat-`), OpenAI project
  keys (`sk-proj-`), basic auth embedded in a clone URL, and bearer tokens. A
  `curl -u user:pass` rule is deliberately *not* added — that shape collides
  with `docker run -u 1000:1000`, and the gap is recorded rather than papered
  over.
- `atomicWriteFile` preserves an existing destination's permission bits instead
  of resetting them to the umask default, opens its temp file `O_EXCL`, and
  cleans up when the *write* fails rather than only when the rename does. The
  test that claimed to cover that path only exercised the rename.
- The shipped `farm.js` bundle is now executed by the test suite, not merely
  regenerated and byte-compared. `includes/farm.md` tells operators to run
  `node <plugin>/tools/farm.js`, but the integration launcher ran `farm.ts`
  through the tsx loader and the unit suite imported `farm.ts` — so the merge
  gate proved source behaviour and deterministic generation, and never that the
  ESM bundle starts, parses argv, resolves its bundled modules, or preserves
  exit semantics under plain Node. A byte-identical artifact is not a working
  one. A focused shard now covers plan validation, a missing credential, the
  loopback API's success and failure paths, and report emission against the
  rebuilt bundle; a parity test runs one fixture through both entry points and
  compares exit code, tally, and report; and a negative control proves a
  syntactically valid but behaviourally altered bundle fails the shard while
  every `farm.ts` test stays green. CI rebuilds before testing so the shard runs
  against a fresh artifact (issue #407).
- The test suites no longer write outside their own temp directories. Running
  the hook suite rewrote the developer's real `~/.claude/settings.json` — both
  the statusline command and its owner key repointed at whatever plugin root the
  test process resolved — and littered `~/.codearbiter/` with a ledger, its
  lock, five session shards and an update cache. Four modules did it, none using
  the `redirect_home` helper that already sat beside them, and CI never noticed
  because a fresh runner has no settings to clobber. All four now take a
  module-level isolation fixture, which covers every test class added later
  rather than relying on one more remembered `setUp` (issue #442).
- The hook suite no longer leaks file handles or child processes. Unclosed
  `settings.json` / `CONTEXT.md` reads, five never-reaped subprocesses, and an
  implicitly reclaimed `HTTPError` produced `ResourceWarning`s — and on Windows
  an open handle blocks `TemporaryDirectory` cleanup while a live child holds a
  temp path, so teardown *raised* instead of the assertion failing. That is why
  the same unchanged tree went `FAILED (errors=2)` on one run and `OK` on the
  next three. Handles are closed, subprocesses are reaped through `addCleanup`
  regardless of assertion outcome, and the two detached background spawns
  `session-start.py` fires are stubbed in the harness rather than launched for
  real (issue #462).
- A new CI gate keeps both closed: each suite runs under a pristine redirected
  home seeded with a stale-but-real `settings.json`, and must leave it
  byte-identical while emitting no `ResourceWarning`. The guard proves its own
  detector can fail, so a green result means something.
- The per-plugin payload-version gates no longer fire on a dev-only change under
  `plugins/*/tools/`. That directory is a build tree — TypeScript sources, a
  vitest config, a lockfile — and none of it runs on an installed machine, so a
  dependabot lockfile bump used to demand a manifest advance and a CHANGELOG
  heading describing a change no user can observe. The cost was not the noise:
  a version bump is supposed to mean "installed users need this", and a gate
  that fires on nothing trains contributors to bump a version to silence it. The
  committed esbuild artifacts inside that directory (`farm.js`, `sandbox.js`) do
  ship and still trigger the gate, as does everything outside it — including
  ca-pi's `extensions/` bundles, which were never in the excluded scope
  (issue #435).
- A session started inside a linked worktree no longer repoints the **main**
  repository's git-level enforcement at a path that dies with that worktree.
  The shared `<plugin>.path` enforcer entry lives in the git *common* dir, so
  every linked worktree writes the main repo's copy — and the SessionStart
  self-heal pinned it to whatever plugin root the session happened to load,
  which inside a worktree is the worktree's own. Pruning the worktree then left
  H-01, H-03, H-05, H-09b, H-10b, H-11 and H-19 pointing at nothing, with no
  announcement: the repo keeps looking governed. An ephemeral enforcer is now
  refused in both the producer (`_githooks._write_path_entry`) and the caller
  (`session-start.py`), leaving the previously registered install in place — a
  stale-but-durable enforcer still enforces, an absent one does not. A stale but
  durable path is still refreshed, so the guard cannot become a kill-switch
  (issue #441; same bug class as #438's statusline pin, sharing its
  `_durabilitylib.is_ephemeral_path` predicate).
- `FARM_RUN_ID` no longer accepts a Windows reserved device name. `NUL`, `CON`,
  `AUX`, `PRN`, `COM1`-`COM9` and `LPT1`-`LPT9` match the run id's character
  class perfectly, and Windows resolves them ahead of any extension, so `NUL`,
  `nul` and `com1.log.1` all name a device rather than a directory. Since the
  run id became a directory name under `.farm/runs/`, that made `mkdir` throw
  outside the run's cleanup scope and took the run's receipts - its recovery
  record - with it. Refused at startup on every platform, because an
  orchestrator's `FARM_RUN_ID` travels between machines. Matched on the stem
  only, so `console`, `nulls`, `COM0` and `COM10` remain valid (issue #440).
- A hook payload that is valid JSON but not an object (`[]`, `3`, `"str"`,
  `true`, `null`) is normalized to an empty payload at `read_input()` rather
  than handed to the guards as a non-dict. Downstream, `tool_input()` evaluates
  `(data or {}).get(...)`, so the falsy shapes were only accidentally safe and
  the truthy ones raised `AttributeError` out of the guard. The hook envelope is
  host-produced, not model-produced, so an unreadable shape is the same
  compatibility event as unreadable syntax and now takes the same documented
  warn-and-proceed path (ADR-0020). The ca-codex adapter still fails closed on
  the same payload: it is a router, not a guard, and that asymmetry is now
  recorded in both the ADR and the adapter.
- Prune dry-run records, audit logs, CLI, footer, and cold-cache metrics now separate
  model-visible context savings from file-only sidecar cleanup; sidecar bytes
  no longer inflate the context-benefit decision or arm the cold-cache nudge.
- Prune hooks now ignore and repair malformed per-session state instead of
  allowing invalid legacy values to escape fail-open handling.
- Farm runs now own their receipts. Every run publishes its stream, per-task
  diffs, and JSON/Markdown report under `.farm/runs/<run-id>/`, so two farm
  processes against one repository can no longer erase each other's artifacts;
  the familiar top-level `.farm/` paths remain as a latest pointer. Every report
  write is atomic (same-directory temp file, rename), so a crash mid-publication
  leaves the previous complete artifact instead of truncated JSON. `FARM_RUN_ID`
  pins a run's id and artifact directory, and minted run ids widened to 64 bits
  now that the id names a directory rather than only a log field. Concurrent
  runs still share git state; the farm docs now name the exact settings
  (`FARM_INTEGRATION_BRANCH`, `FARM_WORKTREE_ROOT`, non-overlapping task ids)
  that a second simultaneous run needs.
- A farm run that cannot publish its authoritative, run-scoped report now fails
  with a dedicated exit code 3 and suppresses the success `Report:` breadcrumb,
  instead of exiting 0 and pointing operators at a file that was never written.
  A failure to refresh the non-authoritative top-level latest pointer is
  reported as a warning and does not fail the run. Streaming-rail and per-task
  diff write failures are no longer swallowed: the published report records the
  rail as incomplete and names the tasks whose diff evidence is unavailable,
  with a true total alongside the bounded list.

## [2.9.1] — 2026-07-20

### Fixed
- Tribunal runs recover exact per-reviewer token usage from Claude Code
  subagent transcripts, retaining fresh input, cache creation, cache reads,
  output, and explicit unavailable reasons.

## [2.9.0] — 2026-07-12

Statusline customization and correctness hardening across concurrent sessions.

### Added
- Five opt-in statusline palettes (`violet`, `blue`, `green`, `amber`, and
  `mono`) plus a bounded, partial custom JSON palette. Violet remains the
  byte-identical default; invalid configuration fails softly, and `NO_COLOR`
  remains authoritative.
- Recent subagent rows now show the recorded model, `model:mixed`, or
  `model:?`, captured during the existing bounded transcript scan.

### Fixed
- Farm API calls now reject credential-bearing base URLs, revalidate at each
  network boundary, refuse automatic redirects, and keep provider-controlled
  response bodies out of logs and retry/report diagnostics.
- Concurrent statusline renders no longer lose ledger updates, session-start
  metadata, or aggregate token/cost totals.
- Linked Git worktrees report their branch correctly, third-party statusline
  commands are no longer mistaken for codeArbiter-owned settings, and the
  display-only dirty check has a 100 ms latency budget.
- Windows audit events survive same-process and dual-host process bursts while
  retaining bounded, fail-open lock behavior.
- Prune warm-reset coverage no longer depends on wall-clock scheduling, and
  docs-site hook snapshots no longer pin exact source line numbers.

## [2.8.13] — 2026-07-12

Host-aware runtime vocabulary, plus dual-host audit-trail hardening.

### Fixed
- Audit-log lines in `gate-events.log` now record the writing host
  (`host=claude` / `host=codex`), restoring per-writer attribution now that two
  hosts can share one `.codearbiter/` store (ADR-0012).
- `gate-events.log` appends are now protected by a Windows byte-range lock and
  the file is created `0o600`, so concurrent sessions cannot interleave or
  truncate audit lines.

### Changed
- Every runtime-emitted command reference (startup briefing, NOT-INITIALIZED
  pointers, H-12/H-18 gate messages, doctor lines, the init scaffold's stub
  text) now flows through the host seam (`Host.cmd_ref`), so the same vendored
  core names `/ca:<cmd>` under Claude Code and `$ca-<cmd>` under Codex
  (ADR-0011 M3). Claude output is string-identical to 2.8.12.
- The markdown surface (`commands/`, `skills/`, `includes/`, `COMMANDS.md`,
  `SPRINT.md`, `ORCHESTRATOR.md`) is now rendered from `core/surface/`
  templates by `tools/build-surface.py` — byte-identical to the previous
  hand-maintained tree, with CI (`--check`) holding it there.

## [2.8.12] — 2026-07-09

Internal host-abstraction seam; no behavior change under Claude Code.

### Changed
- **Per-op guard loop (ADR-0011, M2).** `pre-write.py` guards canonical per-file ops from `Host.iter_file_ops` (a Claude Write maps to exactly one op with the pre-seam fields, so its verdict path is byte-identical), with new fail-closed branches for patch-style edit/delete/opaque kinds that only a write-batching host (Codex `apply_patch`) can produce. `pre-bash.py`/`pre-edit.py` route `tool_input` through the host seam (pass-through on Claude). Proven by the unmodified 794-test suite plus the new cross-host verdict-parity suite.
- **Shared-core extraction (ADR-0011, M1).** All 42 host-neutral hook files are now canonical in `core/pysrc/` and vendored byte-identically into `plugins/ca/hooks/` by `tools/sync-core.py` (`--check` gates drift in CI). A new `hostapi.py` seam carries host specifics (project-root resolution, tool-name normalization, capability flags); `plugins/ca/hooks/_host.py` pins the Claude Code host. Entry scripts are now importable `run(host)` functions with identical CLI, exit-code, and fail-open contracts — proven by the unmodified 794-test suite. Groundwork for the `ca-codex` sibling plugin.

## [2.8.11] — 2026-07-02

Durable sink for mechanical gate decisions, plus an audit staleness warning.

### Added
- **Durable gate-events sink (#186).** `block()`/`remind()`/`warn()` — the three primitives every one of the 16 entry hooks funnels every gate decision through — now best-effort append a structured line (`[ISO-8601Z] KIND [tag] hook=<script> | msg`) to `.codearbiter/gate-events.log`, so BLOCK/REMIND/WARN events are durable and greppable instead of visible only in the live transcript. The write is fail-open: a locked, missing, or unwritable log never changes a hook's exit code nor suppresses a BLOCK. The log is append-only (added to the `AUDIT_LOG_BASENAMES` single source that `AUDIT_LOG_NAMES` and all three H-05 flanks derive from, so the protected set cannot drift).
- **Audit staleness-warn (CONFIRM-09).** A `UserPromptSubmit` check warns (non-blocking) when an active `/sprint` or `/dev` flow has not appended its expected audit-log line within a bounded window, resolving the audit-completeness half of the log-write-compulsion question. It is a warn, never a hard gate; the H-05 integrity guards remain the sole true STOP.

## [2.8.10] — 2026-07-02

Lower SessionStart latency on the linchpin hook.

### Changed
- **Cut SessionStart blocking work (#194).** The hooks-install re-probe now skips its git spawns when a cheap, spawn-free on-disk check proves the shims are current — fail-safe by construction (a grammar-free `hookspath` scan of `.git/config`; any doubt, including a later `core.hooksPath` change, falls through to a real install, so the git-enforce backstop can never be silently left unwired). The five independent `assemble_summary` git reads now run concurrently, and the first-of-day briefing threads its already-read `CONTEXT.md`/`open-tasks.md`/`open-questions.md` text through instead of re-reading. Injected startup state is byte-identical.

## [2.8.9] — 2026-07-02

The mechanical guards now judge the repository the git operation actually fires in.

### Fixed
- **Hook repo-resolution (#190).** The `.git/hooks` git-enforce backstop resolves its target via `git rev-parse --show-toplevel` from its own working directory (not `CLAUDE_PROJECT_DIR`), so a `git -C <other> commit` is gated against `<other>`. `pre-bash.py`'s `git_cwd` now finds `-C` past global options and composes a repeated `-C` run the way git itself does (fold-left), closing a fail-open on crafted spellings; a `-C` target that is not a real directory fails closed. `session-start.py` and `taskwrite.py` drop divergent local `project_root()` copies for the shared, `CLAUDE_PROJECT_DIR`-first `_hooklib.project_root`.

## [2.8.8] — 2026-07-02

### Changed
- **Thin entry points for the babysit/metrics/preview command helpers (#179).** Three command surfaces that ran a lib as a script or embedded multi-statement `python -c` blocks now call dedicated thin entry hooks, so the logic is import-covered by `py_compile` and tests. Output is byte-identical.

## [2.8.7] — 2026-07-02

### Fixed
- **Atomic state writes and a single-parse prune (#191, #188).** The prune-state, git-hook shim, and statusline-settings writers route through a unique-temp + `os.replace` atomic write, so a torn write leaves the prior file intact (a partial shim can no longer silently disable the #161 backstop, and concurrent sessions no longer collide on a fixed `.tmp`). The prune hook now reads and parses the transcript once per prompt instead of twice.

## [2.8.6] — 2026-07-02

### Changed
- **Statusline thin-entry refactor (#178).** `statusline.py` drops from 1186 to 642 lines, with its concern-groups extracted into focused libs behind a thin entry point. Behavior is proven unchanged by the existing suite with assertions unmodified.

## [2.8.5] — 2026-07-02

### Security
- **Tail-anchored audit-log append and a literal `--no-verify` block (#172, #175).** The H-05 append check now admits an audit-log Edit only as a strict tail append and rejects a `replace_all` on an audit-log path outright, closing a hole where a mid-file insertion or multi-site suffix rewrite passed as an "append". A new H-20 guard blocks a literal `--no-verify`/`-n` on `git commit` (including bundled and attached-value short-flag clusters, mirroring git's own parsing) and on `git push`, because that flag skips the `.git/hooks` git-enforce backstop.

## [2.8.4] — 2026-07-02

### Added
- **Update-available notifier (#209).** A best-effort, once-daily, fail-silent check compares the installed plugin version against the latest GitHub Release and surfaces a one-line `update available X → Y` notice at SessionStart and in the statusline. The network refresh is off the SessionStart hot path (a detached child; the hooks only read the cache), HTTPS-only per ADR-0003, unauthenticated, sends no repo or user data. The README documents native marketplace auto-update as the official mechanism.

## [2.8.3] — 2026-07-02

### Fixed
- **Farm dispatcher hardening (#192, #187, #183).** The cost-arbitrage farm now bounds response-body reads, completes its abort accounting, validates numeric environment overrides, surfaces mutation-hook failures instead of swallowing them, and covers the entitlement probe.

## [2.8.2] — 2026-07-02

### Security
- **Guards fail closed on a crash or an unreadable git state (#189, #193).** A crash inside a `pre-bash`/`pre-edit`/`pre-write` guard, or a git-read error while resolving branch/diff state, now blocks (H-00) rather than allowing the operation through, and the git-enforce backstops gained coverage. A guard that cannot determine whether an operation is safe treats it as unsafe.

## [2.8.1] — 2026-07-02

Opening of the tribunal remediation campaign: supply-chain hardening plus the quick-kill fixes.

### Security
- **Pin GitHub Actions to commit SHAs and add dependabot (#202).** Every workflow action is pinned to a full commit SHA (not a moving tag), dependabot is configured for actions and npm, and the `cat-file`/env-bind surfaces in CI are hardened.

### Fixed
- **Tribunal quick-kills (#197).** Atomic provenance/state writes, typed spawn options, and fail-closed CI scripts, closing the first wave of tribunal findings (#174, #176, #177, #182, #184, #185, #195).

---

## [2.8.0] — 2026-07-01

The tribunal release: a deep, resumable, whole-codebase audit lane, hardened by a full post-landing review and an eleventh lens, plus a fix for the false fail-closed commit-gate block that work surfaced.

### Added
- **`/ca:tribunal` — the deep resumable codebase-audit lane (#157, #168, #170).** Convenes eleven bespoke `tribunal-*-reviewer` specialist lenses (appsec, architecture, coverage, infra, migration, observability, performance, reliability, secrets-supply, test-fidelity, typesafety) over the whole codebase in recorded priority waves. Each finding persists as its own crash-durable file under `.codearbiter/reports/<run-id>/` alongside append-only triage/run logs, so an interrupted run resumes from disk across sessions and days; a triage pass recalibrates severity and confidence against a defined, severity-tiered confidence gate; approved findings file as deduped GitHub issues, only on explicit authorization. Rare and opt-in by design: never a required gate, never blocks a merge or commit. The infra lens covers CI/CD workflow security, container posture, IaC, and deploy manifests.

### Fixed
- **The commit gate no longer fails closed on commit messages containing `;`, `|`, `&`, or a `git -C` mention (#169).** The H-09b/H-10b/H-14 pre-commit scan truncated its argument parse at the first separator character inside a quoted or heredoc commit-message body; the leftover fragment leaked message words into a pathspec query whose failure blocked the commit as an unreadable diff. Heredoc bodies are now stripped before parsing, with the raw command retained as a fallback matcher so nothing scans less than before; the argument capture is quote-aware; and a fail-closed block message now carries the underlying git error, so the next read failure is diagnosable at a glance.

## [2.6.1] — 2026-07-01

A security-hardening release. Five P1 reports (thanks to @tg12) showed the enforcement layer being enforced against a forgeable or lexical surface (a writable activation file, writable gate markers, raw path strings, a literal command string, an env-controlled delete root) rather than the real underlying operation. Each is closed, and the rest of the repo was swept for the same class in every case. Also fixes a task-id parsing gap and finishes two stale AGPLv3 relicense surfaces.

### Security
- **The activation switch can no longer be flipped off from inside the repo it governs (#159).** Every enforcement hook stays dormant unless `.codearbiter/CONTEXT.md` frontmatter reads `arbiter: enabled`, yet nothing protected that file, so writing `arbiter: disabled` (or corrupting the frontmatter) silenced every gate. The Write/Edit guards (H-18) now block a CONTEXT.md change whose resulting content drops `arbiter: enabled` or breaks the frontmatter, and the Bash pre-hook blocks the shell flank. A legitimate `stage:` change that keeps the flag enabled still passes.
- **Gate-pass markers can no longer be forged by a direct write (#160).** The `.codearbiter/.markers/` tokens that turn a hard BLOCK into an allow were ordinary writable repo files, so a hand-written marker forged a security, migration, or ADR gate pass. The Write/Edit guards (H-19) now block tool writes to any marker, and the Bash pre-hook blocks shell redirects and file verbs naming `security-gate-passed` or `migration-gate-passed`. The sanctioned recorder scripts and the `/ca:adr` authoring marker still work.
- **Symlink aliases no longer bypass the audit-log and ADR guards (#162).** The Write and Edit guards classified the raw `file_path`, so a symlink whose visible path lacked `.codearbiter/` slipped a write onto an append-only audit log or an immutable ADR. Every protected-path check now resolves the real path (the approach the Read and post-write hooks already used) and matches both the raw and resolved forms. `NotebookEdit`, previously wired to no hook, is now covered too.
- **Git mutations are enforced below the command spelling (#161).** The Bash pre-hook gates `git commit`, `push`, and `add` by matching the literal command string, so shell indirection such as `g=git; c=commit; $g $c` built a real commit the hook never saw, with no enforcement beneath it. codeArbiter now installs repo-level `pre-commit` and `pre-push` hooks that enforce the protected-branch, force-push, and crypto/secret/migration gates at the git operation itself, where spelling no longer matters. They reuse the same detection primitives as the Bash hook so the two cannot drift, never overwrite a pre-existing hook, and install idempotently at init and on session start.
- **Farm worktree deletes are contained to the repo-scoped farm root (#163).** The dispatcher resolved a worktree path from the env-controlled `FARM_WORKTREE_ROOT` plus a plan-controlled task id and recursively force-deleted it before git validated it, so a broad or misconfigured root plus a plausible id could delete an unrelated directory. The resolved root must now live inside the repository unless `FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1` is set, every worktree path is asserted strictly inside that root before deletion, and the reserved ids `.` and `..` are rejected.

### Fixed
- **A mistyped multi-part `--id` no longer strands a task (#158).** `/ca:task add --id` accepted a value with more than two dot-separated parts and minted an un-targetable four-segment id that start/done could not reach and the board linter could not see. The id is now validated as a single `GROUP.TYPE` pair and rejected with a clear message otherwise, and the board reader recognizes an over-segmented id so it can be surfaced and repaired.
- **Release-skill changelog heading and license declarations aligned (#151).** The `/ca:release` skill now documents the Keep-a-Changelog `## [X.Y.Z]` heading the repo and its release guards use, replacing the last reference to the bare `## vX.Y.Z` form. The plugin manifest now declares `AGPL-3.0-only` (correcting a stale `MIT`), and the README license notice no longer implies a commercial license is currently on offer, completing the AGPLv3 relicense across those surfaces.

---

## [2.6.0] — 2026-06-27

codeArbiter 2.6.0 spans several tracks. The headline additions are context-drift provenance (passive drift detection, a coarse code map, and commit-gate auto-heal) and file-scoped just-in-time context injection, which surfaces the governing decision, control, or spec at the moment an agent reads a file. The `--farm` preview gains best-of-N sampling and iterative retries for first-time-go accuracy, and commit-gate now lands task-board transitions atomically with the work (ADR-0008). This release also relicenses the project from MIT to AGPLv3 with a proprietary dual-licensing path; see the License note under Changed.

### Added
- **Best-of-N sampling against the gate (`FARM_SAMPLES`, default 1).** Because the gate is a deterministic pass/fail oracle and each task runs in an isolated worktree, N candidates are drawn in parallel and the first to pass the gate is accepted. Each sample runs in its own scratch worktree cut from the integration HEAD; the winner's files are taken into the task worktree and merged, the losers discarded. Total in-flight worker calls never exceed `FARM_CONCURRENCY` — a shared limiter, so sampling shares the budget rather than multiplying it. `FARM_SAMPLES=1` is byte-for-byte today's single-candidate path (pinned by a regression test). (report F1)
- **Sampling parameters on the worker call (`FARM_TEMPERATURE`, `FARM_MAX_TOKENS`).** The chat body now carries `temperature` (default 0; auto-bumped to 0.7 when `FARM_SAMPLES>1` so samples diversify) and an optional `max_tokens` cap (default unset = provider default, today's behavior). (report F4)
- **Best-of-N cost transparency.** `farm-report.json` records both the summed sample-token spend and the accepted candidate's own tokens (`acceptedPromptTokens`/`acceptedCompletionTokens`), so the N×-tokens trade-off is visible rather than hidden. (report F1)
- **Task-board transitions land atomically with the work (ADR-0008, #142).** commit-gate is now the single board-sync chokepoint. A done-flip `[~]`→`[x]`, start-flip `[ ]`→`[~]`, or a single queued add to `open-tasks.md` is recognized by a new `_taskboardlib.classify_board_diff` classifier, retained by commit-gate Phase 6 (not flagged as scope creep), and staged by Phase 7 into the same commit as the work — so the flip is invisible on `main` until merge, then lands atomically, and an abandoned PR abandons the flip with it. No more lagging `chore(board)` PR or cross-session board drift. A new `/ca:standup` advisory drift sweep (`hooks/boardsync.py reconcile`, read-only and best-effort) surfaces any merged-but-not-flipped task; the fix still routes through `/ca:task`.
- **Context-drift detection, a code map, and commit-gate auto-heal (#145).** codeArbiter records which source files back each derived `.codearbiter/` doc. When a tracked source changes, a single SessionStart line flags the drift, `.codearbiter/code-map.md` gives a coarse orientation map, commit-gate auto-heal re-baselines the provenance or proposes a doc update with the work commit, and `/ca:context-check` runs the audit on demand. A drifted claim is suppressed rather than surfaced as if it were fresh.
- **File-scoped just-in-time context injection (#146).** A `PreToolUse:Read` hook injects a budgeted (≤150-token), freshness-gated pointer to the security control, accepted ADR, approved spec, or fresh provenance claim that governs the file being read, in that priority order, then always allows the Read. A non-governed Read injects nothing and makes no git call. A spec opts in with an optional `**Governs:**` header line.

### Changed
- **Retries are now iterative.** On a retry — a failed gate, or a sampling round with no green — the worker is shown its own previous in-scope output, not just the gate-failure tail, so it refines rather than restarts blind. The prior output rides the same `FARM_ENRICH_MAX_BYTES` byte-cap and secret-redaction chokepoint as all injected context; out-of-scope drift is never carried forward. (report F2)
- **The follow-up harvest runs pre-commit.** commit-gate's raise-new harvest moved from after-the-commit to Phase 7 before staging, so a discovered follow-up task rides the work commit as a contingent default; a follow-up that must survive PR abandonment is filed as a GitHub issue instead of the board. (ADR-0008, #142)
- **Relicensed from MIT to AGPLv3 with proprietary dual-licensing (#147, ADR-0009).** The open-source distribution moves to the GNU AGPLv3, whose network-use clause closes the hosted-fork loophole that MIT leaves open. Copyright is held solely by the owner, who reserves a proprietary dual-licensing path for a planned closed-source SaaS; future contributions require a CLA (see `CLA.md`). The change is forward-only, so code already published under MIT stays available under MIT. This supersedes ADR-0006's broad-adoption posture. See `LICENSE` and the README for the full terms.

### Fixed
- **Mutation-hook least privilege (#143).** The pluggable mutation hook (`FARM_MUTATION_CMD`) no longer inherits the dispatcher's API key or OAuth token, giving it least-privilege parity with every other child command.
- **Heredoc commit messages (#139).** The commit gate no longer false-blocks a multi-line `git commit -F - <<EOF` commit message (H-09b).
- **`/ca:release` hardening (#138).** The release skill resolves the baseline tag, the notes heading, release-date consistency, and half-finished-publish recovery through tested helpers, and rebuilds `farm.js` unconditionally on every release.

---

## [2.5.2] — 2026-06-25

Deep-review (`docs/reports/2026-06-24-root/`) remediation, in two parts. The quick-kill batch is mechanical robustness, diagnosability, and hot-path hardening with no enforcement-behavior change (guard matrix, cold-install, and statusline render verified unchanged or byte-identical). The HARD-GATE batch closes real gaps in the crypto/secret commit gate and the append-only audit guards; each enforcement change shipped test-first (a RED test proving the gap, then the fix), with the full guard matrix, cold-install, migration backstop, and hook unit suites green.

### Security
- **Commit-time gates can no longer be bypassed by `git commit <pathspec>`.** A `git commit <path>` records the *worktree* content of the named paths (bypassing the index), but the H-09b/H-10b crypto-secret gate and the H-14 migration gate scanned only the staged (`--cached`) diff — so an unstaged crypto/secret/migration change named as a pathspec committed with no recorded review. Both gates now union the worktree diff **scoped to the named pathspecs** (an unrelated worktree change elsewhere is not dragged in). The crypto/secret scan and the H-14 file-list read now also **fail closed** when `git diff` cannot be read (timeout/error) instead of silently passing. (appsec-001/002, reliability-003)
- **Farm child commands no longer inherit dispatcher secrets.** `run()` scrubs `FARM_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from the environment passed to every child (git, operator gate/setup/test, mutation) — the API key is used only by the in-process `fetch`. Least-privilege defense-in-depth; shrinks the blast radius of the operator-authored gate-command shell boundary (CodeQL `js/shell-command-injection-from-environment` #5, traced non-exploitable and dismissed).
- **Two detection blind spots in the crypto/secret commit gate are closed.** `CRYPTO_RE` did not match RC2 or Blowfish (both forbidden by `security-controls.md`), so a commit adding either passed the H-09b gate with no crypto-compliance review. `SECRET_RE`'s leading word-boundary never fired when a secret keyword was the trailing segment of a compound identifier, so a hardcoded `FARM_API_KEY = "..."` committed clean past H-10b. Both now match. The outbound farm redactor and the commit-gate secret pattern are also pinned to a shared, CI-checked corpus (`secret-detection-corpus.json`) asserted against both, so they can no longer silently drift apart. (secrets-001/002, architecture-001, #132)
- **The H-05 append-only audit-log guard no longer accepts an empty-`old_string` Edit.** Because `new.startswith("")` is always true, an Edit with an empty `old_string` on `overrides.log` / `triage.log` / `sprint-log.md` slipped the append-only check entirely; it now blocks outright. The variable-indirection residual risk and the known truncation-spelling gaps (`exec N>`, `>>>`, process substitution) are now documented in `security-controls.md` so the policy matches the enforced scope. (migration-003, appsec-003, observability-005, #132)
- **A session-boundary `/ca:dev` exit now closes the audit pair.** When SessionStart clears a live dev marker (a prior session entered `/ca:dev` and ended without `/ca:arbiter`), it appends a synthetic `DEV: exit` line to `overrides.log` before removing the marker, so the audit trail no longer keeps an orphaned `DEV: enter` with no matching close. (observability-001, #133)

### Fixed
- **The task board can't be lost to a crashed write.** `taskwrite.py` writes `open-tasks.md` atomically (temp file in the board's own directory + `os.replace`), so an interrupted write leaves the prior board intact. (migration-001)
- **Farm dispatcher robustness + diagnosability.** A per-command wall-clock timeout (`FARM_GATE_TIMEOUT_MS`, default 5m; git stays unbounded) kills a hung gate/setup/mutation child so a stuck command can no longer wedge a run and stall the final report; the worktree-cleanup `finally` is guarded against an early failure; plan validation emits named field errors instead of an opaque crash; a run-id correlates `farm-results.jsonl` lines and the report header. Response/parse shape guards turn malformed API or mutation-hook output into actionable errors instead of silent empties. (reliability-001/004, migration-004, observability-003, dx-001/002/003)
- **ca-sandbox surfaces real failure causes.** `docker create`/`cp` exit codes are checked and the failed-clone path captures a bounded slice of git stderr into the thrown error, so a failed sandbox build/clone no longer reports only a bare exit code. (reliability-002, observability-004)
- **Task-board lib input guards.** `_taskboardlib.set_state`/`promote` no longer raise or silently mutate state on an unexpected value; valid value sets are documented. (dx-004/005)
- **Gate-pass markers are written atomically.** `migration-pass.py` and `security-pass.py` write their pass markers through a temp file plus `os.replace` (shared `_hooklib.write_text_atomic`), so a crash mid-write can no longer leave a half-written marker that the backstop reads as an unrecognized digest and spuriously re-blocks the next commit. Fail-closed behavior is unchanged. (migration-002, #133)

### Changed
- **Hook hot-path and statusline render cost reduced (behavior-preserving).** `_hooklib` caches the controls read (mtime-keyed, per ephemeral hook process) and precompiles its default path-globs at import; the statusline caches per-render state reads and its cost-ledger subsystem moved into a dedicated `_ledgerlib.py`. Verified: guard matrix 79/0, cold-install 134/0, and the statusline render byte-identical. (performance-001..005, architecture-005/007)
- Public-API header blocks added to `_hooklib.py` and `_sloplib.py` per the coding standard. (dx-007)
- **Audit-guard path sets centralized in `_hooklib` (behavior-preserving).** The append-only-log and ADR-decisions path patterns, previously triplicated inline across `pre-write` / `pre-edit` / `pre-bash`, now have a single definition (`is_audit_log` / `AUDIT_LOG_NAMES`, `is_decisions_path` / `DECISIONS_DIR_RE`), so adding an audit artifact touches one file instead of three. The detached-HEAD protected-tip check also resolves in one `git show-ref` spawn instead of three sequential `git rev-parse` calls, with the same block/allow decisions. (architecture-004, performance-006, #132, #133)

### Tests
- Added integration/coverage for existing behavior with no source change: custom CI/deploy scope grammar, the H-12 governed-path reminder (incl. superseded-ADR), and `validateRepoUrl` scp double-colon rejection; plus a `_ledgerlib` suite. (coverage-003/004/005)

### Documentation
- **Full pre-release docs pass.** Tightened the always-loaded orchestrator core (collapsed the duplicated non-negotiables, trimmed the register, made the lazy-load routers state one deterministic trigger-to-route surface) and reconciled the governance docs to the now-merged enforcement (the forbidden-crypto list, the secret-sweep pattern, and the audit-trail section that now names the automated `session-cleanup` `DEV: exit` write). Corrected stale references (`/ca:arbiter` no longer instructs a manual dev-exit line the hook already writes; `auth-crypto-reviewer` and the post-write reminder now list rc2/blowfish). The docs site gains an **Enforcement & Security** page and a complete **Hooks reference** documenting every hook (event, location, controls, and fail posture).

## [2.5.1] — 2026-06-23

### Fixed
- **Scope-touch reminders now fire on macOS and Windows** (`H-12`/`H-15`/`H-16`/`H-13`).
  `post-write-edit.py` derived its repo-relative path with a lexical `os.path.relpath`. When
  the hook payload's `file_path` and `git rev-parse --show-toplevel` named the same repo via
  divergent forms (a symlinked `/var` vs `/private/var` on macOS, an 8.3 short name on
  Windows), the path came out `..`-prefixed and every path-scoped reminder was silently
  dropped. A new `_hooklib.repo_rel()` canonicalizes both sides with `realpath` first. (#125)
- **`/ca:release` is now scoped to the `ca` plugin** (ADR-0007). The skill assumed a
  single-plugin repo: `LAST_TAG` resolved via bare `git describe` (returning a `ca-sandbox`
  tag), the bump and commit window spanned the whole repo, the derived version was never
  asserted against `plugin.json`, and the README/catalog surfaces had no sync step. All are
  now scoped to `plugins/ca/` and enforced, including a read-back of the published Release. (#125)

## [2.5.0] — 2026-06-22

### Added
- **Advisory scope-touch detection for CI, deploy/IaC, and auth** (`H-15`/`H-16`/`H-17`). After a
  write/edit, `post-write-edit.py` now reminds when a CI/CD workflow (`H-15`), a deployment/IaC
  manifest (`H-16`), or narrow high-signal auth logic (`H-17`) is touched, pointing at
  `security-reviewer`. These are **advisory only — no commit block**: a workflow runs only once merged
  and IaC bites only on apply, so a hard per-commit gate would impede iterative infra work while the PR
  review still catches the change (the irreversible-once-committed harms — secret/migration/crypto —
  keep their blocking gates). commit-gate now dispatches `security-reviewer` on a staged CI/deploy touch
  even on bare `/commit` / the small lane, closing the same lane-skip gap `H-14` closed for migrations.
  CI and deploy paths are detected by default glob sets, extendable/narrowable via `ci-paths` /
  `deploy-paths` blocks in `security-controls.md` (same grammar as `migration-paths`); the migration,
  CI, and deploy detectors now share one `path_in_globs` matcher in `_hooklib.py`. Resolves the
  scope-touch half of #73. (#73)
- **`/ca:metrics` — governance trend glance** (issue #79). Read-only command computing override rate,
  small-lane rate, and sprint low-confidence ratio over 20-commit windows, each with a direction arrow
  (↑/↓/→) vs. the prior window. Optional `--window N` to adjust the window size. Bare numbers only —
  not a second `/ca:audit` packet; writes nothing.
- **Task-board lifecycle + `/ca:task` writer and follow-up harvest** (#118). `open-tasks.md` gains a
  kanban-style lifecycle (`[ ]` queued, `[~]` in-progress, `[x]` done) with content-bearing IDs, so
  the in-flight count and stale-task nudge read real state instead of counting every bullet. The board
  now surfaces malformed or undated entries at SessionStart rather than letting work silently drop off.
  New `/ca:task add|start|done` is the sanctioned board mutator, and each gated workflow's terminal
  step harvests its un-actioned residue (NEEDS-TRIAGE markers, the checkpoint DEFERRABLE table,
  low-confidence sprint decisions) into the durable backlog.

### Fixed
- **`--farm` setup-doc error messages now point at the file that actually ships** (#119). The no-model
  and no-API-key guards cited a never-scaffolded `.codearbiter/farm.md`; they now point at
  `${CLAUDE_PLUGIN_ROOT}/includes/farm.md`, which is part of the plugin payload.
- **The crypto and secret commit gates now catch the Node/TS forms** (#120). `CRYPTO_RE` detects the
  TypeScript TLS-verification-disable patterns (the `rejectUnauthorized` bypass and the Node TLS-reject
  env override), not only the Python form; and `SECRET_RE` matches object-literal secrets
  (`"api_key": "…"`) plus high-entropy key prefixes (`AKIA`, `ghp_`, `sk-ant-`), not only `=`-style
  assignments. The `farm.ts` outbound redactor is aligned so the gate and the redactor never disagree.

## [2.4.6] — 2026-06-19

### Changed
- **Trimmed the always-on `ORCHESTRATOR.md` kernel.** The verbose `/dev` maintainer-override body
  moved to a new on-demand `includes/dev-mode.md` (loaded only on `/ca:dev` or `/ca:arbiter`), and the
  `--farm` summary compressed to a one-line pointer at `SPRINT.md` / `includes/farm.md`. The kernel
  retains the `/dev` security invariant (env-gated on `CODEARBITER_DEV=1`, entry/exit logged
  append-only, load the detail before suspending any gate) as a stub; the `§0.1` terminology lock and
  `§7` Override stay in-kernel, and `§3`/`§5`/`§6`/`§7` heading numbers are unchanged so hook citations
  stay accurate. Behavior-preserving — reduces the per-session SessionStart injection by ~21 lines. (#75)

### Security
- **Cleared 17 Dependabot alerts and hardened the farm test harness.** Bumped the vulnerable
  dev-dependency pins under `plugins/ca/tools/` (`package.json` / `package-lock.json`) and tightened
  process spawning in `farm.test.ts` so the test harness no longer shells out unsafely. Dev/test-only —
  no change to runtime plugin behavior. (#106)

## [2.4.5] — 2026-06-19

### Added
- **Migration commit-time backstop** (`H-14`): a `git commit` that stages a database migration is
  blocked until a migration-review pass is recorded for that file. commit-gate dispatches the
  `migration-reviewer` agent on a staged migration and, on PASS, records a content-digest marker
  (`.codearbiter/.markers/migration-gate-passed`) via the new `hooks/migration-pass.py`; `pre-bash.py`
  H-14 then admits the commit only when every staged migration is covered. Binding is by file-content
  digest with no freshness window — an edit to a reviewed migration re-blocks (closing TOCTOU and
  enforcing migration immutability at commit time). Migration paths are detected by a default glob set,
  extendable/narrowable via a `migration-paths` block in `security-controls.md`. Closes the bare-`/commit`
  / `/feature` small-lane gap where no lane dispatched the reviewer and no hook fired. (#77)

## [2.4.4] — 2026-06-18

### Added
- **Cold-miss nudge** [Feature Forge — `preview`]: an opt-in `UserPromptSubmit` speed bump that
  blocks once, with an advisory on stderr, when a large banked prune delta is about to re-cache on
  bloated in-memory context (idle ≥ 240 s, freed tokens ≥ 80k, `CODEARBITER_PRUNE_NUDGE=on`).
  Returns exit code 2 once; a resubmit proceeds. The once-per-cold-window `cold_nudged` marker is
  persisted in `prune-state.json` and reset on any warm submit. Strictly fail-open: any internal
  error returns 0 and never blocks the session. This is the first non-zero exit path in `hook_run`.
  Advisory content is derived from state numbers only (no transcript text). (#69)

## [2.4.2] — 2026-06-16

### Fixed
- **Closed six confirmed hook-enforcement bypasses** surfaced by the 2026-06-15 repo review, each
  with a red→green test: `git push --all`/`--mirror` could publish protected refs from any branch
  (H-01); `>|` force-clobber slipped the log-truncation and ADR-redirect guards (H-05/H-11); the
  Write/Edit ADR gate matched only numeric-prefixed names, so drafts and nested `decisions/*.md`
  slipped (H-11); `sprint-log.md` was not in the append-only set (H-05); `hooks.json` matched only
  `Edit`, letting `MultiEdit` sidestep the audit-log/ADR guards; and a detached-HEAD / case-sensitive
  branch check let a commit onto `main`'s tip slip. Adds direct tests for `pre-write.py` and
  `security-pass.py` plus a self-heal characterization test. (#68)

### Changed
- **Deduped skill overlap and unified the ADR format** (behavior-preserving skill-prose cleanups from
  the 2026-06-15 review). ADRs now share one `references/adr-template.md`, and `decompose` emits
  parseable `status:` frontmatter so `/ca:adr-status` reads every ADR uniformly. Five duplications
  were extracted to shared leaves (`--farm` plan extension, fresh-run verification, maturity→coverage
  table, crypto/secret on-pass block, cut-doc list). The `finishing-a-development-branch` open-PR path
  now executes the `/ca:pr` steps inline instead of re-routing (which looped under `/sprint`), and the
  stale inline command catalog was removed in favor of rendering from `COMMANDS.md`. (#68)

## [2.4.1] — 2026-06-14

### Fixed
- **Anti-slop copy pass now runs on the `/ca:chore` docs lane.** User-facing docs authored through the
  docs lane previously got no copy-law pass, so the core §3.A em/en dash prose-separator tell (the
  highest-signal AI text marker) could ship unflagged. The docs lane now applies the
  `anti-slop-design` pass before `commit-gate`, and a new advisory `H-13` PostToolUse reminder surfaces
  separator dashes in user-facing docs (repo-root community docs and `docs/**`) as you write, exempting
  code, URLs, numeric/date ranges, and lone table-cell dashes. (#60)

### Added
- **`PRIVACY.md`.** Records the no-data-by-default posture (no telemetry, no network calls in default
  operation, all state local to the repo) and the two opt-in flows that touch data: the `--farm`
  provider calls and the prune dry-mode local metrics. Supplies the Privacy Policy URL for the
  Claude Community Marketplace listing. (#63)

### Changed
- **Clarified that `/ca:dev` is the gates-off escape hatch**, not the required lane for editing
  codeArbiter's own command, hook, or persona bodies. Normal development of those files flows through
  the ordinary gated lanes and ships via PR + release. (#64)

## [2.4.0] — 2026-06-14

### Changed
- **Reframed `farm` as a pluggable execution backend (cheap / premium / agentic).** The dispatcher now
  runs every task through a `Worker` interface seam rather than calling the HTTP chat endpoint directly;
  the HTTP-chat author is one implementation. The worker owns the apply step, and a task-level
  containment sweep runs post-apply for any worker type, so path-traversal and read-only-test guards
  hold regardless of backend. Behavior-preserving for the existing flow. The name `farm` and its
  `preview` (Feature Forge) status are unchanged.

### Added
- **Prompt enrichment for workers.** Outgoing requests now include the read-only source of the task's
  failing test and the current contents of existing in-scope files, so a worker sees the contract it
  must satisfy. The injected context is byte-capped (configurable, mindful of `FARM_REQUEST_TIMEOUT_MS`)
  with a visible truncation marker, and is run through a redaction pass over the `security-controls.md`
  secret-pattern set — planted secrets, including multi-line PEM keys, are never transmitted.
- **Optional per-task `model`.** `task.model` is accepted in the plan schema (`additionalProperties:false`
  honored) and resolves as `task.model ?? meta.model`, enabling design-for cross-model execution.
- **Scope-aware scheduling.** A task overlapping an unfinished sibling's `filesInScope` is removed from
  readiness (not merely merge-serialized) until that sibling is green and merged; ordering is derived
  and id-tiebroken.
- **Regenerate-on-conflict.** A merge conflict now resets to the new integration HEAD and re-runs the
  worker once (the post-loop merge moved into the attempt loop) before escalating, instead of escalating
  instantly.
- **Streaming results rail.** Each settled task is appended to `.farm/farm-results.jsonl` in completion
  order as it settles, alongside the final `farm-report.json`.

---

## [2.3.1] — 2026-06-14

### Changed
- **Moved the `--farm` (OpenCode Zen) cost-arbitrage backend under Feature Forge.** It is labeled
  `preview` in the command catalog and the sprint body, documented in both READMEs' Feature Forge
  section, and carries a preview banner in its setup doc. `CONFIRM-05` records the promotion bar (the
  evidence that moves the farm from preview to stable). No behavior change to the farm itself.

---

## [2.3.0] — 2026-06-14

### Added
- **`/ca:release` now publishes the GitHub Release.** A new Phase 3 creates the GitHub Release via
  `gh release create` under the same explicit authorization that pushes the tag, reusing the changelog
  section composed in Phase 1 as the release notes. Closes the gap where the skill cut and pushed a tag
  but left the Releases page empty until someone ran `gh` by hand.

---

## [2.2.0] — 2026-06-14

### Added
- **`anti-slop-design` reference and `design-quality-reviewer` agent.** A lazy-loaded include bundle
  (`includes/anti-slop-design/`: an INDEX router, an always-loaded core, craft leaves, and per-medium
  leaves for documents, dataviz, slides, web, CLI, and diagrams) that keeps generated user-facing
  output from defaulting to generic AI-slop. A read-only `design-quality-reviewer` enforces it,
  dispatched by `frontend-author` on UI changes; `/ca:pr` and `release` apply the reference inline to
  PR-body and CHANGELOG prose. Governs generated artifacts only, not the framework's own docs.
- **`docs/patterns/lazy-load-bundles.md`** documenting the lazy-load reference-bundle pattern.

### Fixed
- **Statusline subagent rows** show a wider, more useful label: it fills the available row width
  instead of a fixed 22 columns, and is derived from a title-like first line with reminder and
  role-assignment preambles stripped.
- **Statusline honors the `NO_COLOR` environment variable**, and an expired rate-limit reset now reads
  `--` instead of a bare dash.

### Changed
- Unified the five blocking reviewer agents (security, auth-crypto, migration, dependency, coverage)
  onto one output grammar: `CRITICAL`/`HIGH`/`MEDIUM`/`LOW` buckets plus a single gate-status line.
- Tightened public-facing copy: purged em-dash prose separators from the README, plugin README, and
  demo-script, and corrected the agent count to 15.

---

## [2.1.1] — 2026-06-13

### Changed
- **Project moved to the `arbiterForge` GitHub organization.** Canonical home is now
  `github.com/arbiterForge/codeArbiter`. Plugin metadata (`homepage`, `repository`, `author`),
  the self-hosted marketplace `owner`, install instructions, and all doc links point at the new
  org. The old `SUaDtL/codeArbiter` URLs continue to redirect. No behavior, gate, or payload logic
  changed — metadata and documentation only.

---

## [2.1.0] — 2026-06-13

First stable minor since the 2.0 plugin rewrite. Consolidates the `2.1.0-beta.1`…`beta.6`
pre-releases into one release. Everything here ships **stable and dormant-by-default** (inert in a
repo without `arbiter: enabled`). Per-feature maturity is governed by the **Feature Forge**, not by
the version string: the session-transcript pruner is the lone **`preview`** feature — opt-in via
`CODEARBITER_PRUNE`, promoted by real-world data, never on by default. See *Feature Forge* in the
README. The per-beta history remains in the git tag log.

### Added
- **`/ca:standup` + SessionStart morning briefing** — read-only hygiene briefing on the first session
  of each local day (a one-line offer thereafter): branch divergence, merged-but-unpruned branches,
  stale worktrees, stashes/dirty state. The hook only reports; `/ca:standup` performs cleanups under
  per-action confirmation (ff-only pull on a clean tree, prune of merged branches — never current or
  default, stale-worktree removal, report-only stashes). Remote `git fetch` is detached and
  non-blocking. New `hooks/_standuplib.py` with full `unittest` coverage.
- **`/ca:watch <PR>` — PR CI babysitter** — watches a PR's checks to completion via server-side
  `gh pr checks --watch` (zero model tokens while CI runs). On red it diagnoses
  (`CODEARBITER_BABYSIT_ONRED`: `propose` default | `branch`); on green it notifies and offers the
  merge — **never** auto-merges, and a default-branch merge still routes through the hard gate. Global
  `CODEARBITER_BABYSIT` (default off) auto-attaches a watcher when `/ca:pr` opens a PR; never set on
  the user's behalf. New `hooks/_babysitlib.py` with `unittest` coverage.
- **Session-transcript pruner** (`/ca:prune`) — *Feature Forge preview, ships off.* Trims clutter from
  Claude Code JSONL transcripts at safe quiescence boundaries. Ten strategies across `gentle` /
  `standard` / `aggressive` tiers; protected tail keeps the K most recent tool turns verbatim; unknown
  line types pass through byte-identical; 7-check validation battery with rollback; live-race-safe
  write protocol. After-each-turn service mode (`UserPromptSubmit` / `PreCompact`, gains land at
  resume/compaction, off by default), a `✂ N% · Xs ago` statusline segment, and a `/ca:doctor` payload
  check. Dry mode (`CODEARBITER_PRUNE=dry`) records every would-be prune to an append-only JSONL log
  (`~/.codearbiter/metrics/prune-dry.jsonl`) — sizes/savings/verdicts only, **no transcript content** —
  the evidence base for the `dry → on` go/no-go. Backed by `hooks/_prunelib.py`; 40+ unit tests.
- **Feature Forge** (README) — a section with its own hero (`docs/feature-forge.svg`) framing preview
  features as opt-in, dormant, and promoted by real-world data; plus a `Feature Forge: prune data`
  issue form and chooser config so returning a `dry` log is drag-attach-submit. Demo shot list
  (`docs/demo-script.md`) and a README placeholder for an in-motion GIF.
- **Spinner verbs** wired during plugin install/uninstall.
- **`pre-edit.py` hook test suite** (`tests/test_pre_edit.py`) — H-05 append-only guard and H-11
  ADR-marker paths, including stale-marker and Windows-path variants.
- **CVE gate in CI** — `npm audit --omit=dev --audit-level=critical` in the `tools` job.
- **Architecture decision records** — `.codearbiter/decisions/` with ADR-0001..0004 and a decision log.

### Changed
- **Plugin storefront** (`plugins/ca/README.md`) and the README **configuration table** split so
  preview opt-ins (prune) sit under Feature Forge, not beside blessed flags. A collapsible README
  worked-example now *shows* a real `/ca:fix → commit → pr` flow.
- **Catalog & routing** — `COMMANDS.md`, `README.md` (counts 32→34), and the routing table gain
  `/ca:standup` and `/ca:watch`.
- **security-controls.md** — TLS section rewritten around resolved-URL validation; boundary-crossings
  table gains plan.json/`FARM_MUTATION_CMD` shell-exec and the loopback `http://` exception rows.
- **Babysitter flag resolution is executed, not eyeballed** — `_babysitlib.py` gains a fail-safe CLI;
  `/ca:pr` and `/ca:watch` invoke it instead of restating spellings in prose.
- **SH-6 ff-pull gate wired into the live briefing** — `assemble_summary` computes `ff_pull_eligible`
  via the pure helper rather than re-deriving the condition.

### Fixed
- **Statusline self-heals across plugin updates** — the SessionStart hook refreshes a
  codeArbiter-owned pin to the current renderer path each session, persisting only on a real change,
  leaving third-party statuslines untouched, and degrading silently on any error. New `refresh` action
  on `wire-statusline.py` and `heal_statusline_wiring()` in `session-start.py`, both `unittest`-covered.
- **Cold-install hook test no longer clobbers the developer's global statusline** — `scenario_env` now
  sandboxes `HOME`/`USERPROFILE` so a hook's `~/.claude/settings.json` write cannot escape into real
  user state.
- **Pruner robustness** — startup self-heal for the write/truncate crash window; rollback no longer
  eats a concurrent append; `CODEARBITER_PRUNE_KEEP_RECENT` counts turns as documented.
- **Audit remediation (pre-tag sweep)** — catalog drift in `COMMANDS.md`/`init.md`, the §6
  repeat-redirect command list completed, `prune.md` Windows interpreter fallback, `/sprint`→`/ca:sprint`
  normalization; `session-start.py` briefing comment/upstream-line/base-branch-namespace fixes; a
  textual `[DEV]` statusline badge for where color is stripped.

### Security
- **Validate the resolved API base URL before every fetch** — `farm.ts` now checks the resolved base
  URL (env → plan.meta → default) via `assertSecureBaseUrl` (HTTPS-only, documented loopback `http://`
  exception, WHATWG `URL` parsing), closing a path where a `FARM_API_BASE_URL` override could send the
  `Authorization: Bearer` header over cleartext. Error messages never include the key.

---

## [2.0.1] — 2026-06-10

### Added
- **Fable pricing in the statusline** — `API_PRICES` gains the Fable family ($10/$50 per MTok, standard 1.25×/2×/0.1× cache multipliers) so the `api≈` cost estimate prices Fable-model tokens correctly instead of falling back to Sonnet rates.
- **Fable model pill** — the statusline model pill recognizes the Fable family and renders it gold, the tier above Opus violet; previously an unrecognized Fable model fell through to the grey unknown-model pill.

---

## [2.0.0] — 2026-06-10 — Native Claude Code plugin

The big one. codeArbiter is rebuilt from a ~13,600-line `.agents/` + vendoring framework into a **native Claude Code plugin**. The soul is intact — orchestration, gates, SMARTS, the audit trail — re-grounded on Claude Code's plugin primitives and made leaner and more autonomous. Install with `/plugin marketplace add arbiterForge/codeArbiter` then `/plugin install ca@codearbiter`; commands are namespaced `/ca:<name>`. Pre-release, the whole plugin went through an eight-persona adversarial marketplace-readiness review; everything it surfaced is folded in below.

### Added
- **Native plugin packaging** — `.claude-plugin/marketplace.json` + the plugin under `plugins/ca/`. No clone-into-your-repo, no symlinks, no shims.
- **Per-repo activation** — a `SessionStart` hook injects the orchestrator persona only in a repo whose `.codearbiter/CONTEXT.md` sets `arbiter: enabled`, and exits silently everywhere else. This single mechanism replaces the entire `CLAUDE.md → AGENTS.md → _includes` chain **and** the monolith-vs-vendored dual mode.
- **Root-level `.codearbiter/` project state** — stage, specs, plans, ADRs, decision log, and the overrides audit trail live at the repo root so they commit with your code and survive uninstalling the plugin. The sole footprint codeArbiter adds to a consumer repo.
- **Spec-driven `/ca:feature`** — brainstorm a spec → plan → test-first build → commit → finish. The only path to implementation.
- **Dynamic-workflow skill layer** — `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `finishing-a-development-branch`, `using-git-worktrees`.
- **`/ca:sprint`** — the flagship autonomy mode: brainstorm a spec (the one interactive gate), then execute the plan deciding "as the user" via SMARTS on every non-hard-gate point, logging each call with a confidence flag to `.codearbiter/sprint-log.md`. Hard gates — security, crypto/secrets, irreversible ops, merge-to-default — remain true stops.
- **`/ca:dev` / `/ca:arbiter`** — maintainer override for editing codeArbiter itself, env-gated behind `CODEARBITER_DEV=1` with entry/exit logged to `overrides.log`. Fully documented; nothing in the plugin is hidden from its operator.
- **`/ca:chore` and `/ca:spike`** — sanctioned lanes for non-behavioral work (docs edits, dependency bumps, reverts — type-scaled gates) and for throwaway exploration (a `spike/*` branch that can never merge; exits to a findings note or `/ca:feature`).
- **`/ca:feature` small lane** — a logged change-class triage (Step 0): small changes meeting four mechanical criteria skip the brainstorm/plan ceremony and go straight to `tdd` after a one-reply mini-spec confirmation. Every classification is appended to `.codearbiter/triage.log`, which the hooks guard append-only like `overrides.log`.
- **`/ca:audit`** — the promotion packet: assembles commits, overrides (verbatim), triage classifications, ADRs with attribution, sprint auto-decisions, open `CONFIRM-NN`s, and open checkpoint findings for a window into `.codearbiter/audits/<date>.md`. Read-only; never overwrites a packet.
- **Live ADRs** — an optional `governs:` path-glob field on ADRs; the post-write hook surfaces "this file is governed by ADR-NNNN" on any matching Write/Edit, so accepted decisions push back at edit time instead of waiting for a checkpoint sweep.
- **SMARTS precedent row** — each variance table cites the 1–3 most-similar prior decisions from the project's own decision log and the observed lens pattern ("Precedent: none on record" on thin history).
- **Mechanical hook hardening** — every enforcement hook is gated on `arbiter: enabled` (the dormancy promise is now mechanically true); hooks match the PowerShell tool as well as Bash; a `python3`→`python` fallback chain keeps gates alive on stock Windows; UTF-8 stdout guards; Windows backslash-path normalization; git guards tolerate global flags and catch `commit -a`, `--force-with-lease`, forcing refspecs, and `git add --all`; the audit logs are protected against truncation, deletion, and non-append edits.
- **Enforcement layer red-teamed pre-release** — six verified bypasses closed: directory/glob/pathspec-magic staging (`git add src/`, `git add *`, `-u`); audit-log rewrites via `truncate`/`tee`/`cp`/`dd`/`sed -i`; shell-authored ADRs (`echo > .codearbiter/decisions/…`); pushes whose refspec lands on `main` (`git push origin HEAD:main`); a fail-open UTF-8 decode in the security diff scan; and the 30-minute TOCTOU window in the crypto/secret commit gate — the gate-pass marker is now **diff-bound** (`hooks/security-pass.py` records a digest of every sensitive line the gate approved; a pass for one diff cannot launder a different one). Proven by a 62-assertion guard-logic CI matrix on 3 OSes, alongside the 110-assertion cold-install interpreter matrix.
- **`/ca:doctor`** — install health, proven not assumed: interpreter resolution (including the Microsoft Store `python3` stub), payload integrity, stale plugin-cache siblings, repo activation state, git identity, statusline wiring — then a live-fire probe (`git add --all --dry-run` must come back `BLOCKED [H-03]`) that catches the silent-dormancy failure the static checks can't.
- **Pipeline resume** — plans carry a per-task `status` column; acceptance is recorded to the plan file, not just conversation context; an interrupted `/ca:feature` or `/ca:sprint` re-enters at the first unaccepted task (never re-brainstorms an approved spec); `/ca:status` lists every pipeline with its progress.
- **Version-bump CI guard** — a PR changing the plugin payload on an already-published version fails CI, because `claude plugin update` no-ops on an unchanged version string and installed users would silently keep the old payload.
- **commit-gate behavioral-proof phase** (verification before completion) and a closed reproduce→fix→verify loop in `debug`.
- **Plugin statusline** — token/context/cost segment renders everywhere; the four arbiter segments (stage, open tasks, open questions, overrides-since-checkpoint) render only when `arbiter: enabled`. Wire it with `/ca:statusline`.

### Changed
- **`AGENTS.md` → `ORCHESTRATOR.md`** — terser, high-authority voice, single-source rules, `${CLAUDE_PLUGIN_ROOT}` paths. Persona is hook-injected, not `@import`-loaded.
- **Path model collapsed** — `${FRAMEWORK_ROOT}` → `${CLAUDE_PLUGIN_ROOT}`; `${PROJECT_ROOT}/.agents/projectContext/` → `.codearbiter/`.
- **SMARTS retained and trimmed** — 6 lenses + ADR/decision-log + audit trail kept; the 12-week aging clock and forced challenger dropped.
- **Maturity is a single `stage` value** — a rigor knob, not the old 4-stage promotion machinery.
- **Every skill/command/agent body re-grounded** — ~35–40% prose shrink per skill, every hard gate preserved.
- **Tone pass on the user-facing surfaces** — the off-channel redirect now leads with routing help and a pre-filled command instead of a refusal ("Strike 1/2" is gone); the persona holds the gates without being adversarial toward the operator; a user-facing glossary (stage, gate, phase, `CONFIRM-NN`, SMARTS, …) ships in `COMMANDS.md`.
- **Review-stop economics** — `tdd` Phase 1 auto-passes obligations that map one-to-one onto the already-approved spec (user reviews only beyond-spec additions); `executing-plans` drops the redundant breakdown acknowledgment; quality review runs once per batch over the combined diff. Roughly 7 interactive stops → 4 for a small feature, with no gate weakened.
- **Crypto gate tuned** — benign `crypto.randomUUID`/`getRandomValues` no longer trip the commit gate; signing, key-derivation, `randomBytes`, `subtle`, and password-hashing changes still do.

### Removed
- **All portability/vendoring machinery** — `.agents/`↔`.claude/` symlinks, per-file `@import` shims, `/init-vendor`, the `${FRAMEWORK_ROOT}`/`${PROJECT_ROOT}` dual-root scheme, the `AGENTS-CODEARBITER-ROOT` sentinel, `_paths.md`, and `SELF-EDIT-MODE`.
- **Enterprise ceremony** — app-level audit/observability signal emission, the trust-zones doc (folded into `security-controls.md`), the 4-stage promotion model, and the commands `/hotfix`, `/rotate`, `/ticket`, `/stage`, `/onboard`. Two reviewer agents cut (`standards-compliance`, `scaffold-completeness`).
- **The legacy v1 tree** moved to `legacy/` for reference.

---

## [2026-05-13] — token efficiency pass, added missing slash commands, added local context caching to decompose 

Meta-review of the framework: a four-workstream pass on the decompose skill, skill↔command coupling, AGENTS.md preamble weight, and a sanctioned self-edit mode. Plus follow-up commits addressing an independent consistency review and a vendor-pollution cleanup.

### Added
- **`/decision-variance` command** — entry point to the previously orphan `decision-variance` skill. Dispatches `decision-challenger`; requires explicit user attribution for every arbitration choice.
- **`${FRAMEWORK_ROOT}/.agents/skills/INDEX.md`** — skills surface scan with invocation-class annotations (user-invoked / condition-triggered / internal), matching the existing `.agents/agents/INDEX.md` pattern.
- **`${FRAMEWORK_ROOT}/.agents/SELF-EDIT-MODE`** sentinel + AGENTS.md §1 Phase 0 detection — a per-developer toggle (gitignored) that suppresses the H-08 bootstrap nag when the framework is being edited as source rather than consumed. `session-start.sh` Phase 0 detection requires SELF-EDIT-MODE + AGENTS-CODEARBITER-ROOT + monolith layout.
- **`decompose` skill compaction resilience** — new Phase 2.5 init/resume + per-layer disk drafts (`${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-N-*.md`) + Layer 4 immediate `Status: DRAFT` ADR writes + Phase 4 disk-rehydrate clause + Phase 6 draft-directory cleanup gate. The interview now survives auto-compaction with no data loss for completed layers.
- **AGENTS.md §1 Phase 0 — Monolith Self-Edit Detection** documenting the suppression clause.

### Changed
- **AGENTS.md preamble slimmed** by ~75 lines. §0.1.1 Path Resolution, §4 Reference Map, and §5 Routing Table extracted to on-demand bodies (`.agents/commands/_paths.md`, `_reference-map.md`, `_routing-table.md`) following the existing `_redirect.md` pattern. Stubs remain in AGENTS.md with bolded "Loaded when:" callouts.
- **§5 row for `schema-validator`** strengthened to `[OPTIONAL PLUGIN]` — agent body is consumer-supplied, not framework core.
- **§5 condition-only skills** annotated `(condition-triggered, no command)` to disambiguate from user-invoked routes.
- **`decompose` Phase 1** reduced from a "re-do Pre-Flight checks" duplicate to a lightweight "Pre-Flight passed → announce + log entry" step. Pre-Flight section retained (framework structural standard per `skill-author`).
- **`decompose` Phase 5** clarified — DRAFT ADRs written in Layer 4 are now promoted in place to `Status: Accepted` rather than rewritten. Phase 5 source-to-destination mapping notes which files are already on disk from earlier phases.

### Fixed
- **HIGH consistency findings from independent review** — Phase 2 of decompose was asking the Layer 1 question both in Phase 2 AND Phase 2.5 (now Phase 2.5 only); AGENTS.md §4 stub said "twelve rows" but the body has thirteen (corrected); overrides.log entry from this work cycle contained two factual errors — corrected via an append-only audit-fix entry.
- **MEDIUM consistency findings** — three places in `decompose/SKILL.md` misattributed `.decompose-draft/` detection to Pre-Flight; corrected to Phase 2.5 only. Phase 2 Gate language updated from "No gate; this phase is declarative" to describe the actual gate.
- **LOW consistency findings** — Phase 5 ADR template split into two separate code blocks (DRAFT state, Accepted state) to avoid copy-paste hazard; `skills/INDEX.md` tdd row consolidated to `user → /feature, /fix`; "Workstream N" self-references in permanent docs replaced with stable language.

### Removed
- **`.agents/projectContext/decisions/001-ticketing-design.md`** — a real ADR about codeArbiter's own ticketing design was inadvertently shipping in the framework's projectContext, polluting any vendor consumer's submodule clone. Removed from `HEAD` (still present in git history; vendor consumers don't see it in their working tree unless they check out an old commit).
- **Two framework-edit `/override` entries** from `.agents/projectContext/overrides.log`. Log reset to header-only state with a new `FRAMEWORK-SOURCE INTENT` block declaring the framework's published log is intentionally empty.

---

## [2026-05-13] — copyright standards, /decompose, H-08 hook fix

### Added
- `/decompose` command file and registration ([#11](../../pull/11)) — closes a gap where the greenfield-interview skill had no slash-command entry point.
- Copyright header enforcement via checkpoint reviewer ([#9](../../pull/9)) — new files must carry the standard `<!-- Copyright ... -->` header; checkpoint blocks if missing.

### Changed
- Retrofit copyright headers onto all existing framework files ([#10](../../pull/10)).
- Shim file ordering — copyright block moved below the `@path` import line in every `.claude/commands/*.md` shim.

### Fixed
- H-08 source-code check now excludes the vendor tree and framework artifacts ([#13](../../pull/13)) — previously falsed-positive in vendored installs.

---

## [2026-05-12] — ticketing, statusline, perf, expansion

### Added
- **Ticketing skill** ([#3](../../pull/3)) — optional scope-overflow inbox with two variants: lightweight in-repo (`${PROJECT_ROOT}/.agents/projectContext/tickets/`) and Plane MCP integration (on-prem only, API-key auth via env vars). Ships disabled (`enabled: false`); consumers opt in by editing `ticketing-config.md`.
- **Custom Claude Code statusline** ([#4](../../pull/4)) — token-aware status bar surfacing stage / tasks / open questions / git branch / overrides count.
- **Project README and MIT LICENSE** ([#4](../../pull/4)) — first user-facing documentation surface.
- **5 new skills + 4 new commands** ([#6](../../pull/6)) — including `decision-variance`, `doc-review-gate`, `observability-emit`, and others, with a framework-wide terminology lock (§0.1 invariants on `skill` / `agent` / `phase` / `stage` / `layer` / `gate` / `severity` and the `invoke` / `route` / `dispatch` verb triple).
- **`/create-context` command** ([#7](../../pull/7)) — brownfield bootstrap for existing codebases (alongside `/decompose` for greenfield).

### Changed
- **Modular path conventions** ([#7](../../pull/7)) — formal `${FRAMEWORK_ROOT}` vs `${PROJECT_ROOT}` split; framework source uses the former, populated project state uses the latter. Vendored-vs-monolith modes documented in AGENTS.md §0.1.1 (later extracted to `_paths.md`).
- **Install docs added** ([#7](../../pull/7)) — `/init-vendor` command and submodule install instructions.
- **~250 lines cut from AGENTS.md / commands / agents** ([#5](../../pull/5)) — token-efficiency pass; surface-scan INDEX files introduced so routing decisions don't bulk-load `.agents/agents/*.md` or `.agents/commands/*.md`.

---

## [2026-05-10] — foundation

### Added
- **codeArbiter v2 foundation** — initial commit of `AGENTS.md`, `${PROJECT_ROOT}/.agents/projectContext/` scaffold (templates for CONTEXT, tech-stack, security-controls, audit-spec, coding-standards, secrets-policy, dependency-policy, observability-spec, trust-zones, open-questions, open-tasks, stage, decisions/, decomposition/, tickets/, plugins/, checkpoints/), abstract skills, and the `.claude/` shim layer.
- **FUSION `.claude/` system** — routing-table-driven orchestration: every user intent flows through a slash command that fans out to skills and reviewer agents.
- **18 reviewer / author agent definitions** — `auth-crypto-reviewer`, `backend-author`, `frontend-author`, `infra-author`, `migration-reviewer`, `dependency-reviewer`, `security-reviewer`, `trust-zone-reviewer`, `architecture-drift-reviewer`, `coverage-auditor`, `standards-compliance-reviewer`, `scaffold-completeness-reviewer`, `audit-emitter`, `decision-challenger`, `checkpoint-aggregator`, `finding-triage`, `scout`, `grader`.
- **Command catalog** — `/feature`, `/fix`, `/refactor`, `/debug`, `/commit`, `/pr`, `/review`, `/threat-model`, `/adr`, `/adr-status`, `/checkpoint`, `/stage`, `/release`, `/add-dep`, `/rotate`, `/surface-conflict`, `/ticket`, `/btw`, `/status`, `/init`, `/override`, `/hotfix`, `/onboard`, `/new-skill`, `/commands`.
- **`skill-author` skill** — meta-skill enforcing the Skill Structure Standard (Trigger, Pre-Flight, Phases with gates, Failure Modes, Subagents Invoked) for any new skill authored via `/new-skill`.
- **Claude Code hook scripts and `settings.json`** ([#2](../../pull/2)) — `pre-bash.sh`, `pre-edit.sh`, `pre-write.sh`, `post-write-edit.sh`, `session-start.sh`, `statusline.sh`, `statusline-tokens.py`.

### Removed
- `CODEARBITER_PLAN.md` and `CODEARBITER_PROGRESS.md` — superseded by `AGENTS.md` and the projectContext scaffold once v2 was complete.

---

## Maintenance notes

- This changelog is updated by the maintainer (or via `/release` once that workflow is in regular use), not auto-generated. Each entry should describe an outcome a user might notice, not every commit on the way there.
- `[2.0.0]` froze when `v2.0.0` was tagged (2026-06-10). New work accumulates in a fresh section above it; any change to the shipped payload (`plugins/ca/**`) must ride a version bump — CI enforces this against published versions.
