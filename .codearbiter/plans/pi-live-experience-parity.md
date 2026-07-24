# Pi Live-Experience Parity Implementation Plan

**Status:** APPROVED for autonomous sprint execution

**Spec:** `.codearbiter/specs/pi-live-experience-parity.md`

**Goal:** Close actionable live-test issues #340, #341, #343, #344, and #345 while
recreating the rich codeArbiter footer for every interactive Pi repository.

**Architecture:** Add focused, typed capability modules beneath the existing ca-pi parent
adapter and keep `extension.ts` as the single lifecycle composition root. Pure renderers and
state machines own footer, policy, planning, and job behavior; existing final wrappers, the
Python bridge, trust gates, and process-tree machinery remain the enforcement boundaries.

**Tech stack:** Node.js 22.19+, strict TypeScript, Vitest, esbuild, Python 3 standard library,
Pi 0.80.5 and 0.80.10 structural contracts. No new dependency.

## Global constraints

- Preserve ADR-0011 and ADR-0013: host UI/process/session code stays in ca-pi; shared
  governance facts remain descriptor- or bridge-owned.
- Preserve final-wrapper ownership, canonical frozen arguments, H-rule precedence, trust
  boundaries, secret redaction, bounded crossings, and whole-process-tree cleanup.
- Install the custom footer globally in parent interactive Pi. Gate only governance-specific
  repository reads and rows on affirmative trust plus `arbiter: enabled`.
- Plan mode is read-only except for its current canonical spec, plan, and plan-ledger files.
- Background jobs and all their metadata are session-only and must not survive Pi shutdown.
- Do not expose parent UI, planning, or background capabilities in child, print, RPC, or other
  non-interactive modes.
- No persistent permission grant, provider-rate fabrication, web-fetch work for #342, release,
  tag, merge, or publish is in scope.
- Regenerate checked-in bundles and host surfaces. Do not commit this plan directly;
  implementation commits route through `$ca-commit`.

## File structure

| Path | Responsibility |
|---|---|
| `plugins/ca-pi/tools/src/footer.ts` | Pure status model normalization, responsive box rendering, and segment failure isolation. |
| `plugins/ca-pi/tools/src/footer-state.ts` | Pi session/footer inputs and bounded snapshots supplied by usage, governance, and activity ports. |
| `plugins/ca-pi/tools/src/policy.ts` | Typed `plan | execute` and `allow | ask | deny` policy tables. |
| `plugins/ca-pi/tools/src/plan-mode.ts` | Plan session state, canonical path authorization, ledger reconciliation, and native command behavior. |
| `plugins/ca-pi/tools/src/background-jobs.ts` | Session job state machine, bounded ring buffers, notifications, cleanup, and native job commands. |
| `plugins/ca-pi/tools/src/activity.ts` | Bounded live/recent activity registry shared by dispatch, jobs, and footer. |
| `plugins/ca-pi/tools/src/extension.ts` | Parent-only lifecycle composition and registration. |
| `plugins/ca-pi/hooks/pi-bridge.py` | Bounded structured governance snapshot using existing shared state readers. |
| `core/hosts.json` | Descriptor-owned Pi catalog path, native capabilities, and tool classifications. |
| `.github/scripts/test_pi_platform_contract.py` | Cold prerequisite preflight and supported-version aggregate. |
| `plugins/ca-pi/SKILLS.md` | Generated Pi skill catalog outside Pi's loader-scanned skill directory. |

## Acceptance-criteria ledger

| Criterion | Planned proof | Owning tasks |
|---|---|---|
| AC-01 | Cold aggregate fixture asserts fixed failure code/remediation before subprocess fixtures. | T01 |
| AC-02 | Canonical tech-stack prerequisite assertion. | T01 |
| AC-03 | Generated Pi catalog location and absence of loose loader-scanned catalog. | T02 |
| AC-04 | Descriptor, generator, orphan, and reference regressions across all hosts. | T02 |
| AC-05 | Parent interactive activation test in dormant and enabled repositories. | T06 |
| AC-06 | Deterministic universal footer snapshots from Pi-owned inputs and the shared usage ledger. | T03, T04, T05 |
| AC-07 | Renderer/API tests prove absent rate-window data is omitted. | T03 |
| AC-08 | Trusted enabled structured bridge snapshot test. | T05, T06 |
| AC-09 | Dormant/untrusted bridge-call and project-read absence test. | T05, T06 |
| AC-10 | Width, control, color, fail-soft, native-restore, and disposal tests. | T03, T06 |
| AC-11 | Exhaustive typed policy matrix. | T07 |
| AC-12 | Wrapper-order and unknown-tool denial regressions. | T08 |
| AC-13 | Frozen-argument, lifecycle, missing-UI, cancel, and UI-error regressions. | T08 |
| AC-14 | Execute-mode read/mutation/external matrix with no durable grant. | T07, T08 |
| AC-15 | Plan-mode read/source/config/external/unknown matrix. | T07, T09 |
| AC-16 | Canonical plan-path traversal, symlink, and repository-escape tests. | T09 |
| AC-17 | `/ca-plan` enter/report/approve/cancel adapter tests. | T10 |
| AC-18 | Bounded custom-entry restore and on-disk reconciliation tests. | T09, T10 |
| AC-19 | Stable plan IDs/status ledger and separate backlog regression. | T09 |
| AC-20 | Governed background launch returns a session-local ID. | T11, T13 |
| AC-21 | Bounded `/ca-jobs list|tail|cancel` command tests. | T13 |
| AC-22 | Four-job, 65,536-byte, label, and timeout limits. | T11 |
| AC-23 | Explicit-argv Pi shell launch reusing process-tree machinery. | T12 |
| AC-24 | One completion notification and one footer activity transition. | T13, T14 |
| AC-25 | Cancel/timeout/switch/shutdown/unload/fatal descendant-cleanup fixtures. | T12, T13 |
| AC-26 | Unverified cleanup latches unhealthy and directs to `/ca-doctor`. | T12, T15 |
| AC-27 | Redacted bounded append-only permission/job audit tests. | T08, T13 |
| AC-28 | Parent-only package inventory and hardened-child absence tests. | T06, T10, T13 |
| AC-29 | Public documentation and parity fact assertions. | T15 |
| AC-30 | Fresh focused, supported-version, generated, security, full-gate, and live-run receipts. | T16 |

## MVP slice

Tasks T01 through T08 are the contiguous minimum releasable slice. They fix the two observed
release defects, install the rich footer globally with trusted-only governance enrichment, and
add the reusable permission decision inside the final wrapper. T09 through T15 extend that same
policy/lifecycle foundation with plan mode, session jobs, activity, diagnostics, and docs.

## Task status ledger

| Task | Status |
|---|---|
| T01 | ACCEPTED |
| T02 | ACCEPTED |
| T03 | ACCEPTED |
| T04 | ACCEPTED |
| T05 | ACCEPTED |
| T06 | ACCEPTED |
| T07 | ACCEPTED |
| T08 | ACCEPTED |
| T09 | ACCEPTED |
| T10 | ACCEPTED |
| T11 | ACCEPTED |
| T12 | ACCEPTED |
| T13 | ACCEPTED |
| T14 | ACCEPTED |
| T15 | ACCEPTED |
| T16 | PENDING |

## T01 — Make the Pi platform aggregate cold-start explicit

**Status:** ACCEPTED

**Depends on:** none

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-01, AC-02

**Files:**

- Modify `.github/scripts/test_pi_platform_contract.py`
- Modify `.codearbiter/tech-stack.md`

**Steps:**

1. Add a fixture that removes/omits the platform-specific resolved Vitest launcher and proves
   no fixture subprocess runs, the result code is `missing_prerequisite`, and the remediation is
   exactly `npm --prefix plugins/ca-pi/tools ci --ignore-scripts`.
2. Add the smallest preflight before the aggregate command loop; do not auto-install.
3. State the install as an aggregate prerequisite in the canonical tech-stack document.

**Verification:**

```powershell
python .github/scripts/test_pi_platform_contract.py --fixtures-only
```

## T02 — Move the generated Pi catalog outside the loader directory

**Status:** ACCEPTED

**Depends on:** none

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-03, AC-04

**Files:**

- Modify `core/hosts.json`
- Modify `tools/build-surface.py`
- Modify `.github/scripts/test_host_descriptors.py`
- Modify `.github/scripts/test_build_surface.py`
- Modify `.github/scripts/check-plugin-refs.py`
- Modify `core/surface/skills/skill-author/SKILL.md`
- Modify `core/surface/README.md`
- Generate `plugins/ca-pi/SKILLS.md`
- Remove generated `plugins/ca-pi/skills/INDEX.md`

**Steps:**

1. Add failing descriptor/generator/reference tests for host-specific catalog paths and orphan
   cleanup, retaining the current Codex behavior.
2. Change Pi's descriptor catalog to `SKILLS.md`; make all consumers resolve the descriptor value
   instead of assuming `skills/INDEX.md`.
3. Regenerate surfaces twice and prove idempotence and absence of loose Markdown directly beneath
   `plugins/ca-pi/skills/`.

**Verification:**

```powershell
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_build_surface.py
python tools/build-surface.py --check
python .github/scripts/check-plugin-refs.py ca-pi
```

## T03 — Port the rich footer renderer as a pure module

**Status:** ACCEPTED

**Depends on:** none

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-06, AC-07, AC-10

**Files:**

- Create `plugins/ca-pi/tools/src/footer.ts`
- Create `plugins/ca-pi/tools/test/footer.test.ts`

**Steps:**

1. Write fixed-width snapshots for compact/wide layouts, palette thresholds, formatters, missing
   segments, control characters, `NO_COLOR`, and absent rate-window telemetry.
2. Port the established box/palette/segment behavior into a pure TypeScript renderer whose input
   contains only normalized, bounded values.
3. Refactor duplicated formatting helpers only after the snapshots pass.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/footer.test.ts
```

## T04 — Adapt Pi-owned session data and define the daily-usage port

**Status:** ACCEPTED

**Depends on:** T03

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-06

**Files:**

- Create `plugins/ca-pi/tools/src/footer-state.ts`
- Modify `plugins/ca-pi/tools/src/contracts.ts`
- Modify `plugins/ca-pi/tools/src/pi-api.d.ts`
- Extend `plugins/ca-pi/tools/test/footer.test.ts`

**Steps:**

1. Add failing adapters for folder/session, Pi-exposed branch, model/thinking, token/cache/cost,
   context, age, update, and bounded daily totals.
2. Extend only the local structural Pi boundary needed by 0.80.5 and 0.80.10.
3. Define a bounded daily-usage snapshot port supplied by the shared bridge in T05; keep the
   TypeScript adapter free of user-global and project filesystem reads.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/footer.test.ts
npm --prefix plugins/ca-pi/tools run typecheck
```

## T05 — Add structured governance and global usage snapshots

**Status:** ACCEPTED

**Depends on:** T04

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-08, AC-09

**Files:**

- Modify `plugins/ca-pi/hooks/pi-bridge.py`
- Modify `core/pysrc/_ledgerlib.py`
- Regenerate `plugins/ca-pi/hooks/_ledgerlib.py`
- Modify `plugins/ca-pi/tools/src/bridge.ts`
- Modify `plugins/ca-pi/tools/src/contracts.ts`
- Modify `plugins/ca-pi/tools/test/bridge.test.ts`
- Modify `.github/scripts/test_pi_security.py`

**Steps:**

1. Add failing bridge tests for a bounded structured status snapshot, zero governance invocation
   before affirmative trust and enablement, and a project-independent usage-ledger event.
2. Reuse the existing shared state readers for stage/tasks/questions/overrides/sprint/dev/prune, and
   extend the existing OS-locked per-session ledger to accept bounded Pi usage facts keyed by
   canonical session-entry position.
3. Return only validated fixed fields; prove malformed/oversized responses fail soft, global usage
   reads no project state, and governance cannot broaden the trust boundary.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/bridge.test.ts
python .github/scripts/test_pi_security.py
```

## T06 — Install and own the global interactive footer lifecycle

**Status:** ACCEPTED

**Depends on:** T03, T04, T05

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-05, AC-08, AC-09, AC-10, AC-28

**Files:**

- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/src/roles.ts`
- Modify `plugins/ca-pi/tools/build.mjs`
- Modify `plugins/ca-pi/tools/src/activation.ts`
- Modify `plugins/ca-pi/tools/src/status.ts`
- Modify `plugins/ca-pi/tools/test/activation.test.ts`
- Modify `plugins/ca-pi/tools/test/status.test.ts`
- Modify `plugins/ca-pi/tools/test/package.test.ts`

**Steps:**

1. Add activation tests for plain, dormant, untrusted, trusted-enabled, child, and non-interactive
   sessions plus fatal initialization and unload.
2. Install `setFooter` for every parent interactive repository, enrich only after trust, isolate
   segment failures, and restore Pi's native footer on fatal setup or disposal.
3. Prove no footer/UI code reaches the hardened child bundle.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/activation.test.ts test/status.test.ts test/package.test.ts
```

## T07 — Define the extensible mode and permission policy

**Status:** ACCEPTED

**Depends on:** none

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-11, AC-14, AC-15

**Files:**

- Create `plugins/ca-pi/tools/src/policy.ts`
- Create `plugins/ca-pi/tools/test/policy.test.ts`
- Modify `plugins/ca-pi/tools/build.mjs`
- Modify `plugins/ca-pi/tools/src/pi-api.d.ts`
- Modify `core/hosts.json`
- Modify `tools/host_descriptors.py`
- Modify `.github/scripts/test_host_descriptors.py`

**Steps:**

1. Write an exhaustive table for `plan | execute`, known action classes, and
   `allow | ask | deny`; prove unknown tools and unknown actions deny.
2. Add descriptor-owned classifications for the new planning/background tool surfaces.
3. Implement the pure policy evaluator and bounded confirmation consequence model without a
   persistent grant type.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/policy.test.ts
python .github/scripts/test_host_descriptors.py
```

## T08 — Enforce `ask` inside the final wrapper

**Status:** ACCEPTED

**Depends on:** T07

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-12, AC-13, AC-14, AC-27

**Files:**

- Modify `plugins/ca-pi/tools/src/tool-guard.ts`
- Modify `plugins/ca-pi/tools/src/contracts.ts`
- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/test/tool-guard.test.ts`
- Modify `plugins/ca-pi/tools/test/security.test.ts`
- Modify `plugins/ca-pi/tools/test/final-arguments.test.ts`

**Steps:**

1. Add failing tests proving hard/unknown denies precede UI and missing UI, cancellation, UI error,
   lifecycle change, owner change, or argument change executes nothing.
2. Evaluate mode policy after a non-blocking shared bridge verdict, ask once with bounded text, then
   execute the same frozen arguments under the same lifecycle generation.
3. Append bounded audit facts only; exclude prompts, commands, environment, parameters, and output.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/tool-guard.test.ts test/security.test.ts test/final-arguments.test.ts
```

## T09 — Build the read-only plan state and canonical ledger

**Status:** ACCEPTED

**Depends on:** T07, T08

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-15, AC-16, AC-18, AC-19

**Files:**

- Create `plugins/ca-pi/tools/src/plan-mode.ts`
- Create `plugins/ca-pi/tools/test/plan-mode.test.ts`
- Create `core/pysrc/_planfilelib.py` and generated host copies
- Create `.github/scripts/test_planfilelib.py`
- Modify `plugins/ca-pi/hooks/pi-bridge.py`
- Modify `plugins/ca-pi/tools/src/bridge.ts`
- Modify `plugins/ca-pi/tools/test/bridge.test.ts`
- Modify `plugins/ca-pi/tools/src/contracts.ts`
- Modify `plugins/ca-pi/tools/src/pi-api.d.ts`

**Steps:**

1. Add state-machine and adversarial path tests for stable task IDs, status transitions, custom
   session-entry bounds, traversal, symlink escape, repository escape, and unrelated state writes.
2. Implement `plan | execute` session state and reconcile bounded Pi entries with the canonical
   `.codearbiter/plans/<slug>.md` status column.
3. Route canonical planning-file reads and atomic replacements through the existing hardened Pi
   bridge using OS-owned locking and handle-relative publication; a pathname-only TypeScript
   authorization is insufficient for adversarial target or ancestor swaps.
4. Permit only the active spec/plan/plan-ledger paths and prove `open-tasks.md` is never mutated.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/plan-mode.test.ts
python .github/scripts/test_planfilelib.py
python tools/sync-core.py --check
```

## T10 — Register the native `/ca-plan` lifecycle

**Status:** ACCEPTED

**Depends on:** T09

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-17, AC-18, AC-28

**Files:**

- Modify `plugins/ca-pi/tools/src/commands.ts`
- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/test/commands.test.ts`
- Modify `plugins/ca-pi/tools/test/activation.test.ts`
- Modify `core/hosts.json`
- Modify `.github/scripts/test_host_descriptors.py`

**Steps:**

1. Add a descriptor-backed native-command registry so `/ca-plan` is not emitted as a model-routed
   skill alias.
2. Test enter/report/approve/cancel/resume, including confirmation before execute and preserved
   unapproved drafts after cancel.
3. Register only in parent interactive mode and dispose state subscriptions on session change/unload.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/commands.test.ts test/activation.test.ts
```

## T11 — Build the bounded session job state machine

**Status:** ACCEPTED

**Depends on:** T07, T08

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-20, AC-22

**Files:**

- Create `plugins/ca-pi/tools/src/background-jobs.ts`
- Create `plugins/ca-pi/tools/test/background-jobs.test.ts`

**Steps:**

1. Write transition tests for monotonic session IDs, four active jobs, optional timeouts, bounded
   labels, terminal states, and a last-65,536-UTF-8-byte ring buffer.
2. Implement the pure manager state and output retention before wiring any process spawn.
3. Prove no restorable session entry or durable command/environment metadata is produced.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/background-jobs.test.ts
```

## T12 — Reuse the process-tree boundary for job launch and cleanup

**Status:** ACCEPTED

**Depends on:** T11

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-23, AC-25, AC-26

**Files:**

- Modify `plugins/ca-pi/tools/src/background-jobs.ts`
- Modify `plugins/ca-pi/tools/src/process-tree.ts`
- Modify `plugins/ca-pi/tools/test/background-jobs.test.ts`
- Modify `plugins/ca-pi/tools/test/process-tree.test.ts`
- Modify `.github/scripts/test_pi_process_tree.py`

**Steps:**

1. Add Windows/POSIX fixtures for explicit Pi shell argv, `shell: false`, descendant completion,
   cancellation, timeout, switch, shutdown, unload, and cleanup failure.
2. Expose the smallest reusable spawn/terminate handle from existing process-tree code and connect
   it to the job manager after the governed permission path clears.
3. Verify cleanup before terminal disposal; latch unhealthy and reject later launches if verification
   fails.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/background-jobs.test.ts test/process-tree.test.ts
python .github/scripts/test_pi_process_tree.py --fixture-only
```

## T13 — Register the background tool and `/ca-jobs`

**Status:** ACCEPTED

**Depends on:** T10, T12

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-20, AC-21, AC-24, AC-25, AC-27, AC-28

**Files:**

- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/src/commands.ts`
- Modify `plugins/ca-pi/tools/src/contracts.ts`
- Modify `plugins/ca-pi/tools/src/tool-guard.ts`
- Modify `plugins/ca-pi/tools/test/commands.test.ts`
- Modify `plugins/ca-pi/tools/test/activation.test.ts`
- Modify `plugins/ca-pi/tools/test/package.test.ts`
- Modify `plugins/ca-pi/tools/test/tool-guard.test.ts`
- Modify `.github/scripts/test_host_descriptors.py`
- Modify `core/hosts.json`

**Steps:**

1. Add failing registration/command tests for `codearbiter_background_bash` and
   `/ca-jobs list|tail|cancel`, plus child/non-interactive absence.
2. Route launch through hard rules and `ask`; expose only bounded labels/status/output and notify
   once per completion.
3. Wire every session lifecycle exit to verified `terminateAll` before manager disposal and append
   only bounded redacted job audit facts.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/commands.test.ts test/activation.test.ts test/package.test.ts test/background-jobs.test.ts test/tool-guard.test.ts
```

## T14 — Feed dispatch and job activity into the footer

**Status:** ACCEPTED

**Depends on:** T06, T13

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-24

**Files:**

- Create `plugins/ca-pi/tools/src/activity.ts`
- Create `plugins/ca-pi/tools/test/activity.test.ts`
- Modify `plugins/ca-pi/tools/src/dispatch.ts`
- Modify `plugins/ca-pi/tools/src/background-jobs.ts`
- Modify `plugins/ca-pi/tools/src/bridge.ts`
- Modify `plugins/ca-pi/tools/src/footer-state.ts`
- Modify `plugins/ca-pi/tools/src/status.ts`
- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/test/dispatch.test.ts`
- Modify `plugins/ca-pi/tools/test/background-jobs.test.ts`
- Modify `plugins/ca-pi/tools/test/bridge.test.ts`
- Modify `plugins/ca-pi/tools/test/footer.test.ts`
- Modify `plugins/ca-pi/tools/test/package.test.ts`
- Modify `plugins/ca-pi/tools/test/status.test.ts`
- Modify `plugins/ca-pi/tools/test/activation.test.ts`
- Modify `.github/scripts/test_host_descriptors.py`

**Steps:**

1. Test bounded active/recent projections, stale-event eviction, completion transitions, and
   control sanitization.
2. Publish dispatch and job lifecycle events to one session activity registry consumed by the
   footer; keep the registry non-durable.
3. Prove activity failure cannot fail dispatch/job cleanup or the rest of footer rendering.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/activity.test.ts test/dispatch.test.ts test/footer.test.ts
```

## T15 — Update diagnostics, public behavior contracts, and parity

**Status:** ACCEPTED

**Depends on:** T01 through T14

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-26, AC-29

**Files:**

- Modify `plugins/ca-pi/tools/src/doctor.ts`
- Modify `plugins/ca-pi/tools/src/extension.ts`
- Modify `plugins/ca-pi/tools/src/status.ts`
- Modify `plugins/ca-pi/tools/test/doctor.test.ts`
- Modify `plugins/ca-pi/tools/test/activation.test.ts`
- Modify `plugins/ca-pi/tools/test/status.test.ts`
- Modify `plugins/ca-pi/tools/test/tool-guard.test.ts`
- Modify `core/surface/includes/pi-host-notes.md`
- Modify `README.md`
- Modify `docs/pi-parity-testing.md`
- Modify `docs/parity.md`
- Modify `site/src/content/docs/getting-started/compatibility.md`
- Modify `site/src/content/docs/hooks.md`
- Modify `.github/scripts/test_pi_doctor.py`
- Modify `.github/scripts/test_public_pi_docs.py`
- Modify `.github/scripts/test_pi_parity.py`

**Steps:**

1. Add failing fact assertions for catalog path, cold prerequisite, global footer/trusted row,
   permission asks, read-only plan mode, session-only jobs, cleanup health, and omitted rate windows.
2. Add bounded doctor probes for footer initialization and background-manager health without
   exposing commands or environment.
3. Update canonical/public docs and parity classifications to exactly match shipped behavior.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/doctor.test.ts test/status.test.ts test/activation.test.ts
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_public_pi_docs.py
python .github/scripts/test_pi_parity.py
```

## T16 — Regenerate, verify fresh, and capture the live receipt

**Status:** PENDING

**Depends on:** T15

**Maps to:** regression, implementation, refactor, green
**Covers:** AC-30

**Files:**

- Modify `plugins/ca-pi/tools/build.mjs` only if a new entry point is required
- Modify `plugins/ca-pi/tools/test/benchmark-boundary.ts` if the full benchmark exposes live-wrapper drift
- Modify `plugins/ca-pi/tools/src/tool-guard.ts`, `plugins/ca-pi/tools/src/extension.ts`, and
  `plugins/ca-pi/tools/test/tool-guard.test.ts` if live installed-runtime verification exposes
  extension-native preflight drift
- Modify `plugins/ca-pi/tools/src/process-tree.ts` and
  `plugins/ca-pi/tools/test/background-jobs.test.ts` if a real non-Node background shell exposes
  Windows supervisor-host drift
- Regenerate `plugins/ca-pi/extensions/codearbiter.js`
- Regenerate `plugins/ca-pi/extensions/codearbiter-child.js`
- Regenerate `plugins/ca-pi/helpers/windows-supervisor.js`
- Regenerate descriptor-owned host surfaces
- Record sprint verification and decision receipts in the established codeArbiter artifacts

**Steps:**

1. Run focused tests from fresh Vitest/Python processes, typecheck, build, and regenerate every
   checked-in artifact; inspect the child bundle for parent-only capability absence.
2. Run generator, package, parity, public-doc, security, platform fixtures, and both exact Pi-version
   contracts from fresh processes.
3. Run the full repository gate, then live-test installed Pi 0.80.10 in a plain repository and a
   trusted enabled repository: footer, ask/deny, plan lifecycle, job completion/cancel, and shutdown
   cleanup. Preserve a bounded receipt without prompts, commands, environment, or raw output.

**Verification:**

```powershell
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test
npm --prefix plugins/ca-pi/tools run build
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/check-plugin-refs.py ca-pi
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_parity.py
python .github/scripts/test_public_pi_docs.py
python .github/scripts/test_pi_security.py
python .github/scripts/test_pi_platform_contract.py --fixtures-only
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.5
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.10
python .github/scripts/verify_pi_support.py --mode final
git diff --check
```

## Execution order and acceptance

Execute T01 through T16 in dependency order. Each task begins with its named failing regression,
implements the smallest behavior that passes it, refactors only while green, runs its focused
verification from a fresh process, and then receives the sprint task review before its status changes
from `PENDING` to `ACCEPTED`. After T16, route the complete diff through `$ca-commit` and `$ca-pr`;
open the PR and stop without merging.
