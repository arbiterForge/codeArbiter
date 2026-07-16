# Pi support Batch 2 trust/config residual fix brief

Date: 2026-07-15
Branch: `feat/pi-support`
Source: `batch-2-combined-security-review.md`, security rereview HIGH finding
User direction: resolve review concerns with SMARTS, recover from classifier interruptions, continue autonomously through Tasks 6-14, and land as a PR.

## Decision

Require an affirmative current Pi project-trust result before any repository-aware codeArbiter bridge or Git startup. Global extension loading is discovery, not authorization.

### SMARTS

| Lens | Affirmative trust gate | Config-neutral pre-trust Git |
|---|---|---|
| Scalable | Strong. One activation invariant covers every later repository-aware operation. | Weak. Each new Git operation expands the helper/config audit surface. |
| Maintainable | Strong. One host guard precedes existing bridge preparation. | Weak. Bespoke Git restrictions duplicate behavior across commands and platforms. |
| Available | Adequate. Governance waits for one explicit Pi trust decision. | Strong. Startup remains automatic before trust. |
| Reliable | Strong. No asynchronous repository work starts in an untrusted generation. | Weak. Git delegation behavior varies by command, configuration, and version. |
| Testable | Strong. Negative-trust tests assert zero bridge, Git, hook, and fetch activity. | Weak. Exhaustive non-delegation proof requires a growing Git-version matrix. |
| Securable | Strong. Default-deny matches the documented parent-extension trust boundary. | Weak. Repository configuration remains inside an automatic process-execution boundary. |

Recommendation: affirmative trust gate. Strength: **strong**. Confidence: **high**. Availability is the only tradeoff and remains acceptable because Pi already exposes an explicit trust workflow.

Conflict resolution: preserve `.codearbiter/security-controls.md`'s intended trust invariant; clarify the Pi spec and plan that a globally installed extension loading before trust does not authorize codeArbiter activation. The user explicitly authorized SMARTS resolution and autonomous continuation on 2026-07-15.

## Required behavior

1. On every `session_start`, invalidate the prior lifecycle and enter the activation-check blocked generation before asynchronous work.
2. Check canonical `.codearbiter/CONTEXT.md` activation without running Python or Git.
3. If dormant, fully deactivate and remain status-silent as today.
4. If enabled but `context.isProjectTrusted?.() !== true`:
   - do not resolve Python or Git;
   - do not construct or call the concrete bridge;
   - do not load persona/startup state through shared Python;
   - do not discover/install managed Git hooks, read repository Git state, or start background fetch;
   - retain the activation-check fail-closed generation so mutating tools block while native reads use current untrusted settings;
   - publish one fixed, redacted status/notification directing the operator to Pi's trust workflow and a new session;
   - let doctor truthfully diagnose enabled-but-untrusted state without bridge preparation or wrapper live fire.
5. Only after affirmative trust may bridge preparation, enforcement installation, persona loading, shared `session_start`, hook discovery, Git reads, or fetch begin.
6. Shutdown and retry must clear status and lifecycle state exactly once; same-process false-to-true trust reactivation must refresh definitions and identities.
7. Project-local installs remain governed by Pi's own load-time trust gate; the adapter still verifies affirmative trust before repository-aware work.

## Test-first evidence required

- Unit RED/GREEN for enabled untrusted startup: zero bridge calls, zero bridge preparation, zero enforcement installation, zero persona load, fixed waiting-for-trust status, fail-closed mutation, and native untrusted READ behavior.
- Unit RED/GREEN for missing `isProjectTrusted`, explicit false, true, false-to-true same-process retry, shutdown, and dormant repositories.
- Doctor RED/GREEN: enabled-untrusted remains truthful and side-effect-free; no stored-wrapper self-test or bridge probe runs.
- Real supported-Pi/package regression using the existing harness: an enabled untrusted global-extension session performs no repository-aware bridge/Git/hook/fetch activity before affirmative trust. Use only inert sentinels and existing defensive test infrastructure.
- Preserve the existing trusted Windows executable-identity and managed-hook canary after trust.
- Update `.codearbiter/specs/pi-support.md`, `.codearbiter/specs/pi-support-review.md`, `.codearbiter/plans/pi-support.md`, and `.codearbiter/security-controls.md` so host load timing and adapter authorization are no longer contradictory.
- Rebuild deterministically and rerun the full Batch 2 controller matrix.

## Scope guard

This fix closes the current Batch 2 security HIGH only. Do not start Tasks 6-14 inside this author pass. Do not stage, commit, push, publish, switch branches, stash, reset, clean, or modify unrelated user-owned dirt.

After clean integration and security rereviews, the controller proceeds directly into Tasks 6-14 under the user's autonomous-to-PR instruction.
