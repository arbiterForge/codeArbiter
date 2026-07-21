# Task 7 process-tree author report

Date: 2026-07-16
Branch: `feat/pi-support`
Scope: cross-platform containment, production runner integration, generated helper/build/package coverage, and live descendant cleanup. Dispatch semantics are documented separately in `task-7-dispatch-author-report.md`.

## Accepted boundary

- POSIX launches Pi in a detached process group, tries group `SIGTERM`, then group `SIGKILL`, and verifies native absence within bounded windows.
- Windows launches only a canonical inert Node supervisor before containment. A canonical System32 Windows PowerShell holder assigns that supervisor to a `KILL_ON_JOB_CLOSE` Job before the supervisor may launch Pi.
- Launch metadata, `START`, `STARTED <pid>`, native exit status, parent leash, capability fd3, and raw stdio use separate bounded channels. Task text is sent only on raw stdin after containment readiness and the child handshake.
- The Windows holder opens real handles for the Pi root and plugin parent, acknowledges `WATCHING` before readiness, and uses `WaitForMultipleObjects` plus `GetExitCodeProcess`. A dedicated stdin reader signals a native stop event, so intentional cleanup and parent EOF close the Job without waiting for a forced helper kill.
- Natural Windows exit bounded-drains facade stdout/stderr while the fd7 supervisor leash remains open, closes the Job, drains remaining buffered output, then publishes the real exit code and emits `close`. This prevents both output truncation and runner settlement before containment finalization.
- Cleanup is idempotent and first-reason-wins for timeout, cancellation, protocol error/overflow, startup failure, and parent shutdown. Windows tries `taskkill /PID <actual-pi-pid> /T` without `/F`, then closes the Job as the force boundary and verifies both Pi and supervisor roots are absent.
- Launch/control pipe writes are independently time-bounded; a wedged supervisor pipe is destroyed and the Job is closed before the runner can wait indefinitely. The supervisor never directly kills Pi: fail-closed termination converges on the Job boundary.

## TDD record

Initial focused RED produced eight expected failures: containment readiness was missing, runner failure paths did not converge on cleanup, and the old Windows fixture still expected `/F`. A second supervisor RED produced three expected failures: the helper lacked `ATTACHED`, the inert supervisor launch plan was absent, and readiness was not enforced before protocol bytes.

Additional regressions were captured before fixes for:

- cancellation during async validation, spawn, and containment readiness;
- split UTF-8 JSONL across stdout chunks;
- native Windows real exit-code propagation;
- 60 KB final-output drain before descendant cleanup;
- native holder stop-event wakeup;
- bounded wedged launch/control writes and post-attach holder failure;
- generated helper inclusion, strict UTF-8/LF text, release scanning, and CI stale-artifact scope.

The production runner now installs cancellation before capability/handshake work, sends zero protocol bytes before containment readiness, uses one cleanup promise, decodes streaming UTF-8 with `StringDecoder`, settles failure without waiting forever for a child `close`, and requires verified parent-shutdown cleanup for success.

## SMARTS decisions

| Decision | Alternatives considered | Choice and rationale | Strength | Confidence |
|---|---|---|---|---|
| Windows pre-launch containment | direct Pi spawn; `taskkill` only; inert supervisor plus Job holder | Inert supervisor plus Job holder. It proves Job attachment before Pi exists and gives parent-death cleanup a kernel boundary. | Strong | High |
| Protocol separation | argv/env task transport; one multiplexed pipe; dedicated bounded pipes | Dedicated launch/control/status/leash/capability pipes plus raw stdio. Secrets and task material do not enter argv or helper control. | Strong | High |
| Windows exit truth | Node event only; PID liveness inference; native process handle | Native handle wait plus `GetExitCodeProcess`. Liveness cannot recover a real nonzero code and Node/libuv exit observation hung in the Job/extra-pipe topology. | Strong | High |
| Forced cleanup | `taskkill /F`; graceful taskkill only; graceful taskkill then Job close | Graceful tree request followed by Job close and native absence verification. This preserves a grace window while guaranteeing descendant containment. | Strong | High |
| Output versus cleanup ordering | close Job immediately; unbounded stream wait; bounded pre-drain then Job close | Bounded pre-drain with leash held open, Job close, bounded post-drain. This preserves final output without allowing descendant-held pipes to hang completion. | Strong | High |
| Cancellation replay | per-listener kills; raw `child.kill`; one memoized cleanup | One memoized cleanup promise with the first reason retained. Every failure path receives the same verified result. | Strong | High |

## Security review corrections

Review caught and this lane corrected: cancellation races before readiness; a temporary fabricated exit-code fallback; `STARTED` before proxy readiness; split UTF-8 decoding; missing helper stale-build coverage; stdin EOF not waking the native holder; Job close occurring before bounded output drain; facade exit status becoming visible before final cleanup; unbounded control writes; a raw supervisor child kill; and uncorroborated Job-terminated supervisor code `0` being exposed as success.

The production-shaped supported-Pi live harness bundles the runner into a temporary path owned by the `ca-pi` package, retains the reviewed CLI identity, disables ambient discovery through Pi's exact `--no-*` flags, and leaves real/user auth state untouched. Strict JSONL validation now has a separate partial-message normalizer for the installed providers' transient streaming fields (`partialArgs`, `streamIndex`, `partialJson`, and `index`); these fields are bounded, exact-key checked, and removed before the unchanged strict final-message validator.

The package loader expectation was also updated to preserve intentional fail-closed child authentication: an ordinary auto-load of `codearbiter-child.js` now expects the exact missing-marker error, one successfully loaded parent extension, and no child registrations. No authentication check was relaxed.

## Verification evidence

- `npm --prefix plugins/ca-pi/tools run typecheck` -> passed.
- `npm --prefix plugins/ca-pi/tools exec vitest run test/process-tree.test.ts test/runner-isolation.test.ts test/child-env.test.ts` -> 49 passed, 1 skipped.
- Shared-tree `npm --prefix plugins/ca-pi/tools test` -> 221 passed, 1 skipped; the only three failures are Task 8's intentionally RED compaction seam tests, owned by the active Task 8 lane.
- `npm --prefix plugins/ca-pi/tools exec vitest run test/package.test.ts` -> 15 passed.
- `npm --prefix plugins/ca-pi/tools run build` -> passed; supervisor, child, and parent bundles generated.
- `python .github/scripts/test_pi_process_tree.py` -> 8/8 live variants passed on Windows, including root-first orphan cleanup, stubborn escalation, parent shutdown, post-attach holder crash, 60 KB final output, and real exit code 23.
- `python .github/scripts/test_pi_package.py` -> 21 passed.
- `python .github/scripts/test_pi_child_live.py` -> supported-version help plus two production-runner isolated children passed end to end; its 7 static fixtures also passed.

Generated SHA-256:

- `plugins/ca-pi/helpers/windows-supervisor.js`: `9C3462861F705479A27CAE57C0889D085027F4060EFEE7368BBCA9C68D78EC33`
- `plugins/ca-pi/extensions/codearbiter.js`: `B96952137BFF09FDF0297AF580401FE02D75250342490B6873C6B59B34B5F7EB`
- `plugins/ca-pi/extensions/codearbiter-child.js`: `B6DE9D09E61254EF4C351AE16080D0382ADFD6E5763822724555AAAD8CAF83CC`

## Files in this lane

- `plugins/ca-pi/tools/src/process-tree.ts`
- `plugins/ca-pi/tools/src/windows-supervisor.ts`
- `plugins/ca-pi/tools/src/runner.ts`
- `plugins/ca-pi/tools/test/process-tree.test.ts`
- `plugins/ca-pi/tools/test/runner-isolation.test.ts`
- `plugins/ca-pi/tools/test/package.test.ts`
- `plugins/ca-pi/tools/build.mjs`
- `plugins/ca-pi/helpers/windows-supervisor.js`
- `.github/scripts/test_pi_process_tree.py`
- `.github/scripts/test_pi_package.py`
- `.github/scripts/test_pi_child_live.py`
- `.github/workflows/ci.yml`

No files were staged, committed, pushed, or switched by this lane.
