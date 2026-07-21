# Pi live-experience parity runtime

**Status:** APPROVED for autonomous sprint execution

**Design approved:** 2026-07-18 by the repository owner during the `$ca-sprint` specification gate

**Written spec and plan approved:** 2026-07-18 by the repository owner

## Purpose

Close the actionable gaps found during the first live ca-pi release test and make Pi feel materially
closer to the Claude Code host. The sprint fixes the two observed release-verification defects, ports
the rich codeArbiter statusline to Pi, adds a reusable permission-confirmation seam, adds a real
read-only plan mode with a governed task ledger, and adds session-scoped background shell jobs.

The result is one modular capability platform inside the existing ca-pi parent adapter. It is not a
collection of unrelated example extensions and it does not create a second governance kernel.

## Issue scope

- Fix #340: cold `test_pi_platform_contract.py --fixtures-only` prerequisite diagnosis.
- Fix #341: Pi must not load the generated skill catalog as a malformed skill.
- Leave #342 as the informational Pi parity tracker.
- Implement #343: a reusable `allow | ask | deny` host permission decision.
- Implement #344: background shell execution with completion watchers and session cleanup.
- Implement #345: a Pi-native plan mode and task-tracking layer integrated with codeArbiter plans.
- Add the live-test gap discovered during specification: recreate the rich codeArbiter statusline in
  Pi through its custom-footer API.

## Project constraints

- Repository artifacts live under the established `.codearbiter/`, `plugins/`, `core/`, `.github/`,
  and public-documentation paths. No alternate planning tree or foreign workflow terminology enters
  the repository.
- `ca-pi` remains a thin host adapter over the shared governance core under ADR-0011 and ADR-0013.
  Host UI, process, and session behavior stays in `plugins/ca-pi/tools/src/`; shared governance rules
  remain in `core/` and the existing Python bridge.
- No new runtime or development dependency is added. The external Pi runtime remains an install and
  test input, not a checked-in dependency.
- Pi 0.80.5 and 0.80.10 remain the exact supported versions for this sprint.
- Existing H-rules, trust boundaries, final-wrapper ownership, secret redaction, bounded crossings,
  and process-tree guarantees remain non-negotiable.
- Parent-only capabilities do not appear in hardened child Pi processes.
- All new behavior is test-first and all checked-in extension/helper bundles are regenerated.

## Architecture decision

Use a modular capability platform inside the existing ca-pi parent adapter. Focused modules expose
typed ports and pure state machines while `extension.ts` remains the lifecycle composition root.

The capability modules are:

1. A footer renderer and state adapter.
2. A mode and permission-policy engine.
3. A planning controller and plan-ledger writer.
4. A session-scoped background-job manager.
5. A small activity registry consumed by the footer.

The final tool path is:

```text
final governed tool request
  -> shared H-rule verdict
  -> active-mode policy verdict
  -> optional Pi confirmation
  -> foreground or background execution
```

A shared-core hard block always wins. `ask` is a host policy result, never a bypass of a hard rule.
The request is canonicalized once inside the final wrapper; confirmation and execution use that same
frozen value under the same lifecycle generation.

## Rich Pi footer

### Global activation

When ca-pi is installed in an interactive Pi session, it installs a custom footer regardless of
whether the current directory is a codeArbiter project. Installation is the opt-in. There is no
second per-repository enable command.

The universal footer uses Pi-owned session and footer data for:

- current folder and session name;
- Git branch exposed by Pi, plus trusted dirty-state enrichment when available;
- model, provider, and thinking level;
- session input, output, cache-read, cache-write, cache-hit rate, and cost;
- current context use and context-window size;
- session age and daily token/cost totals;
- update availability;
- active or recently completed background jobs and dispatched children.

The presentation preserves the current codeArbiter box, palette intent, threshold colors, compact
formatting, responsive width, and fail-soft behavior. Pi does not expose Claude Code rate-window
telemetry, so the Pi footer omits that segment instead of inventing a value.

### Governance row

The stage, task, question, override, sprint, dev, and prune fields appear only when the repository is
both `arbiter: enabled` and affirmatively trusted. The snapshot comes through a bounded structured
bridge response that reuses the existing shared state readers. The universal footer does not read
`.codearbiter/open-tasks.md`, `.codearbiter/open-questions.md`, or other project-state files in a
dormant or untrusted repository.

### Failure behavior

Every footer segment degrades independently. A render failure produces a minimal safe line. A fatal
footer initialization failure restores Pi's native footer and publishes a bounded `/ca-doctor`
diagnostic. Unload and shutdown dispose subscriptions and restore the native footer.

## Permission policy and modes

### Decision model

The host decision is exactly `allow`, `ask`, or `deny`.

- `deny`: return a block without showing a confirmation.
- `ask`: show `ctx.ui.confirm()` with the operation class, working directory, and bounded consequence
  text; approval continues and cancellation denies.
- `allow`: continue without UI.

Missing UI, a stale lifecycle, malformed parameters, a confirmation exception, or a changed final
tool owner denies. Version one stores no persistent "always allow" choice.

### Execute mode

Version one matches the Claude Code permission posture:

- explicitly classified read-only actions allow silently;
- writes, edits, mutating shell commands, dependency installation, network or external side effects,
  background launches, pushes, releases, and other governed mutations ask;
- an existing H-rule violation denies without an approval option;
- unknown tools remain fail-closed until explicitly classified.

The policy table is data-driven so later profiles can choose different `allow | ask | deny` mappings
without rewriting wrapper control flow. This sprint ships only `plan` and `execute` session modes.

### Plan mode

Plan mode is read-only for source, configuration, external side effects, and operational state.
Explicitly classified reads and non-mutating inspection commands are allowed. Unknown shell commands
deny.

The narrow write exception is the current planning session's canonical files beneath
`.codearbiter/specs/` and `.codearbiter/plans/`. Path traversal, repository escape, symlink escape,
and writes to unrelated `.codearbiter/` files deny. `/ca-task` remains the project-backlog writer;
plan tasks do not rewrite `open-tasks.md`.

The active plan state is persisted as bounded Pi custom session entries. Resuming the same Pi session
restores plan or execution state and reconciles it with the on-disk plan ledger. Entering execution
requires an explicit confirmation. Cancelling preserves the draft and returns to execute mode without
marking the plan approved.

The plan's status column is the task source of truth. Planning and execution UI report the same task
identifiers and states that exist in `.codearbiter/plans/<slug>.md`.

## Background shell jobs

The parent registers a governed background-shell tool and native `/ca-jobs list|tail|cancel` command.
Launches use Pi's configured shell identity and prefix as explicit argv with `shell: false`, reuse the
existing process-tree implementation, and clear the normal final-wrapper and permission path before
spawning.

Version-one limits are:

- at most four active jobs;
- a session-local monotonic job ID;
- the last 65,536 UTF-8 bytes retained per job;
- an optional caller timeout, with no short default timeout;
- bounded labels and status text;
- no command or environment text in the durable audit record.

The footer shows active jobs and recent terminal states. Completion sends a Pi notification. List,
tail, and cancel remain available only while the owning session is active.

Every cancel, timeout, session switch, session shutdown, extension unload, or fatal manager error
terminates and verifies the entire process tree. Jobs never survive Pi shutdown and are never restored
from session entries. If cleanup cannot be proven, the manager becomes unhealthy, blocks new jobs,
and directs the user to `/ca-doctor`.

## Live-test fixes

### Cold platform prerequisite (#340)

The platform aggregate checks for the Pi tools workspace's resolved Vitest binary before running any
fixture command. If it is absent, the runner exits with a fixed `missing_prerequisite` result and the
exact remediation:

```text
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
```

The runner does not install dependencies itself. `.codearbiter/tech-stack.md` states that this command
is a prerequisite of the platform aggregate, not merely an adjacent command.

### Generated catalog warning (#341)

The Pi host descriptor generates its human-readable skill catalog at `plugins/ca-pi/SKILLS.md`,
outside the `pi.skills` loader directory. The generated command catalog remains under `generated/`.
Host-conditional references and repository checks resolve the descriptor-owned catalog path rather
than assuming every host uses `skills/INDEX.md`.

This is an implementation of ADR-0011 and ADR-0013's generated thin-adapter model, not a conflicting
architecture decision and not a new ADR.

## Security and audit

- Confirmation is performed inside the active final wrapper after the shared bridge returns no hard
  block and before the frozen request executes.
- Approval is single-use because no reusable token is issued; it applies only to the current wrapper
  invocation and lifecycle generation.
- A later extension replacement is caught by the existing final-owner guard and cannot reuse prior UI
  approval.
- Plan path checks use canonical existing parents, reject symlinks and traversal, and never broaden the
  allowed `.codearbiter/` surface.
- Planning-file transactions serialize codeArbiter-owned writers and use content hashes to reject
  stale codeArbiter state. An unrelated local process that already has direct repository write
  authority is outside portable cross-platform CAS isolation; if it changes the file during or after
  publication, the bridge reports the observed disk bytes and never substitutes the requested bytes.
  Held canonical parent handles still prevent that race from redirecting publication outside the
  active spec or plan path.
- Job audit records contain fixed event code, host, correlation/job ID, lifecycle ID, duration, exit
  class, and byte counts. They exclude commands, prompts, environment values, and raw output.
- Output and labels are control-sanitized before display. Secret detection and existing redaction stay
  active on every governed request.
- Non-interactive, RPC, print, and child modes do not expose confirmation-dependent mutations,
  background jobs, planning UI, or the custom footer.

## Acceptance criteria

- **AC-01:** A cold platform aggregate exits before fixture execution with `missing_prerequisite` and
  the exact `npm --prefix plugins/ca-pi/tools ci --ignore-scripts` remediation.
- **AC-02:** The canonical tech-stack document states the Pi tools install as an explicit aggregate
  prerequisite.
- **AC-03:** Pi's human-readable generated catalog is `plugins/ca-pi/SKILLS.md`; no loose Markdown
  catalog remains directly under `plugins/ca-pi/skills/`.
- **AC-04:** Surface generation, orphan cleanup, host-descriptor tests, and plugin-reference checks
  resolve the per-host catalog paths without weakening Claude or Codex checks.
- **AC-05:** Installing ca-pi installs the rich custom footer in every interactive Pi repository,
  including repositories without `.codearbiter/`.
- **AC-06:** The universal footer renders folder/session, Git, model/thinking, session usage/cache/cost,
  context, age/daily totals, update, and available activity data from Pi-owned sources.
- **AC-07:** Pi rate-window data is omitted and never fabricated.
- **AC-08:** The governance row renders only for an affirmatively trusted, enabled repository and uses
  the shared state readers.
- **AC-09:** Dormant and untrusted repositories perform no codeArbiter project-state reads for footer
  rendering.
- **AC-10:** Footer rendering is width-bounded, control-safe, `NO_COLOR` aware, segment-fail-soft, and
  able to restore Pi's native footer after fatal initialization or unload.
- **AC-11:** The permission engine exposes an extensible typed `allow | ask | deny` decision over mode
  and action class.
- **AC-12:** Existing H-rule blocks and unknown-tool blocks deny before confirmation and remain
  non-bypassable.
- **AC-13:** Confirmation uses the canonical frozen final arguments and current lifecycle; denial,
  missing UI, stale lifecycle, or UI failure executes nothing.
- **AC-14:** Execute mode silently allows classified reads and asks for governed mutation or external
  side effects without persisting an "always allow" choice.
- **AC-15:** Plan mode allows classified reads, denies source/config/external mutation, and denies
  unknown shell actions.
- **AC-16:** Plan mode allows writes only to the current canonical spec, plan, and plan-ledger paths;
  traversal, symlink escape, and unrelated `.codearbiter/` writes deny.
- **AC-17:** `/ca-plan` can enter, report, approve, and cancel plan mode; approving asks before entering
  execute mode and cancelling preserves the draft without approval.
- **AC-18:** Plan mode and task state resume from bounded Pi custom session entries and reconcile with
  the plan status ledger.
- **AC-19:** Plan tasks use stable IDs and the plan status column; `/ca-task` and `open-tasks.md` remain
  the separate project backlog.
- **AC-20:** The background-shell tool returns a session-local job ID after the hard-rule and permission
  path clears.
- **AC-21:** `/ca-jobs list|tail|cancel` reports bounded session state, retrieves retained output, and
  cancels a job without exposing raw command or environment data.
- **AC-22:** The manager enforces four active jobs, 65,536 retained bytes per job, bounded labels, and
  optional timeouts.
- **AC-23:** Background launches reuse Pi's configured shell and the existing process-tree machinery
  with explicit argv and `shell: false`.
- **AC-24:** Completion updates the footer and emits one bounded notification.
- **AC-25:** Cancel, timeout, switch, shutdown, unload, and fatal errors terminate and verify every
  descendant; no job or job metadata survives shutdown.
- **AC-26:** An unverified cleanup makes the manager unhealthy and blocks later launches with a
  `/ca-doctor` direction.
- **AC-27:** Permission and job audit rows are append-only, bounded, and exclude commands,
  environments, prompts, and raw output.
- **AC-28:** Footer, plan, permission UI, and background capabilities are parent-interactive only and
  cannot recurse into hardened children.
- **AC-29:** Public Pi docs and the parity ledger accurately describe the footer, permission, plan,
  background-job, catalog, and cold-prerequisite behavior without claiming unsupported telemetry.
- **AC-30:** Focused tests, Pi 0.80.5/0.80.10 contracts, generated checks, security checks, the full
  repository gate, and a live Pi 0.80.10 run all pass from fresh processes.

## Out of scope

- Persistent permission grants, user-configurable permission profiles, or additional modes beyond
  `plan` and `execute`.
- Background jobs that survive a Pi process or session boundary.
- A service daemon, OS scheduler, detached durable queue, or cross-session job database.
- Replacing `.codearbiter/open-tasks.md` with session todos.
- Fabricating provider rate-limit data or scraping private provider authentication state.
- Porting the new Pi-native UI mechanics to Claude Code or Codex in this sprint.
- Adding a web-fetch capability for #342.
- Releasing, tagging, publishing, or merging the resulting branch.

## Verification strategy

Pure unit tests cover policy matrices, plan-path authorization, state restoration, rendering at fixed
widths, ledger aggregation, job transitions, output bounds, and catalog generation. Adapter tests
exercise final-wrapper ordering, confirmation cancellation, lifecycle changes, native commands,
footer restoration, and process cleanup. Cross-platform fixtures exercise Windows and POSIX process
trees. Supported-version and package tests prove Pi 0.80.5/0.80.10 compatibility. The live runbook
closes the user-visible behaviors on installed Pi 0.80.10 before the normal commit and PR gates.
