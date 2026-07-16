# Pi support Batch 2 cumulative review fix brief

Date: 2026-07-15
Source reviews: `batch-2-combined-integration-review.md` and `batch-2-combined-security-review.md`

## Finding 1 - CRITICAL: project-cwd Git executable search

The Pi bridge runs trusted Python from the governed project cwd and shared Python invokes bare `git`. On Windows a project-local `git.exe` can execute during enabled activation.

Required outcome:

- Resolve and validate a trusted absolute Git executable only after enabled/trusted activation, using a search that ignores empty/relative/project-controlled locations.
- Pass the absolute executable through the Pi bridge boundary and ensure every Git subprocess reachable through Pi executes that absolute path, including managed git-enforce hook invocations.
- Run the bridge Python process from a validated trusted package directory, not the governed repository. Keep the repository only in the validated request payload and explicit subprocess cwd/`-C` arguments.
- Sanitize process-search environment entries; no project-relative search leg may remain. Audit other bridge helper executables such as Windows process-tree termination.
- Add an authentic Windows canary with a project-local `git.exe` control and prove the enabled session-start path never executes/selects it while real Git behavior and hook installation continue.

## Finding 2 - MEDIUM: stale native-tool settings

Native bash/read factories close over one session's SettingsManager. Dormant cross-cwd calls and same-cwd reactivation can retain old shell path/prefix, image policy, or trust state.

Required outcome:

- Active wrappers must be refreshed or generation-bound on every activation, including same-cwd reactivation.
- Dormant/bootstrap/stale READ/native delegation must use settings resolved for the current execution cwd with project trust forced false, never the prior active session's SettingsManager.
- Preserve current user-level settings where Pi's untrusted SettingsManager contract permits them, but do not inherit prior project-local settings or trust.
- Add tests for cross-cwd dormancy, same-cwd reactivation after settings/trust change, retained old handles, and partial/rejected/cancelled lifecycles.

## Finding 3 - MEDIUM/LOW: final doctor-envelope bound

The decoded report is capped before JSON/markup escaping, allowing a final model-visible block near 96 KiB.

Required outcome:

- Bound the complete encoded model-visible envelope (prefer UTF-8 bytes) without truncating JSON mid-token.
- Preserve shared secret/control redaction, one fixed delimiter, valid JSON, ordinary provenance usefulness, and a visible truncation marker.
- Test all-escape, quote/backslash, C1/control, and multibyte adversarial payloads against the full final block.

## Finding 4 - MEDIUM: unhealthy status survives failed-start shutdown

An enforcement-install failure sets `enabled=false`, so the shutdown condition skips clearing the keyed unhealthy status.

Required outcome:

- Clear codeArbiter's keyed status on shutdown regardless of the final enabled flag.
- Clear stale session status/state when a reused process starts a dormant repository.
- Test failed enabled start -> shutdown -> dormant/new session and normal retry behavior.

## Gates and constraints

- Test first for every finding and preserve same-generation/live failure behavior.
- Update generated shared files and rebuilt parent deterministically where required.
- Keep active-dispatch honestly DEGRADED; PI-AC-28/Task 5 remain BLOCKED.
- Do not start Tasks 6-9.
- Preserve user-owned dirty files; no stage, commit, push, publish, branch switch, stash, reset, or clean.
- Write implementation evidence to `batch-2-combined-fix-report.md`.
