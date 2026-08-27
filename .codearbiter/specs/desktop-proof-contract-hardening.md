# Spec — protected Codex desktop-proof boundary hardening

**Date:** 2026-08-26
**Route:** prerequisite maintenance PR for PR #711
**Approval:** approved by the repository user on 2026-08-26. This spec transcribes the reviewed architecture correction without expanding its authority.

## Problem

PR #711's trusted workflow correctly treats the event-selected candidate checkout as inert data, but the external desktop boundary is not yet strong enough to produce release-gating evidence. The workflow executes an unpinned host script, conflates the GitHub runner with the interactive desktop identity, requires profile destruction before the actor inside that profile can complete it, assumes a non-versioned plugin path that Codex does not install, and accepts a static candidate manifest as if it proved runtime routing.

Those defects are evidence defects, not permission to relax the desktop proof. The corrected lane must prove the exact trusted automation bytes, the exact Microsoft evaluation image, the actual versioned marketplace-selected `ca-codex` root, and a bounded sequence of observable desktop routing events. It must not create a billable or credential-copying substitute.

## Architecture

The protected workflow owns a tracked boundary manifest plus three tracked PowerShell programs:

- an **outer broker** runs as the GitHub runner identity, verifies all content bindings, applies Windows directly from the verified evaluation ISO into a new per-run VHDX, controls the resulting Hyper-V guest, and owns final teardown;
- a **desktop driver** runs in the distinct disposable interactive session, launches the exact Store/MSIX package, submits one fixed non-secret `$ca-review` task through the real desktop window, and observes the resulting canonical app-server thread and reviewer-dispatch items without retaining raw prompt or response content;
- a privileged **guest probe** prepares bounded Windows audit policy and correlates the driver observation with exact Store/package process creation plus ordered file reads from the versioned marketplace root. It emits only bounded canonical events over the credential-authenticated PowerShell Direct session carried locally over Hyper-V VMBus. The channel requires no guest network or remote-management listener.

The trusted default-branch checkout is the only verifier source. The host acquires and copies the Store/MSIX package before guest setup. Inside the guest, contract, broker-selected driver/probe, and those Store resources are copied into an inheritance-disabled SYSTEM/Administrators-owned root that grants the disposable desktop identity read/execute only. After its default-deny policy is active, the guest registers those copied package bytes and installs the local plugin without Microsoft network access; its pre-auth HTTPS policy permits only the four OpenAI endpoints in the tracked boundary contract. Candidate/run data and the writable observation exchange use separate roots. Privileged code rehashes every trusted guest input immediately before each execution, freezes the completed observation back into the trusted root before collection, and gives the HMAC key only to the freshly rehashed privileged probe. The event-selected PR archive is mounted or copied as inert candidate data and is never searched for or used as verifier code.

The approved image is **Windows 11 Enterprise Evaluation, version 25H2, x64, EN-US**, SHA-256 `A61ADEAB895EF5A4DB436E0A7011C92A2FF17BB0357F58B13BBC4062E535E7B9`, as published in Microsoft's Windows 11 Enterprise hash document. Every proof applies the selected Enterprise Evaluation image from that verified ISO into a fresh VHDX; no mutable template or unbound base VHD is trusted. Local provisioning may download the official evaluation image and use Hyper-V with the necessary local disk/network access. Elevation must be visible to the repository user; no hidden or programmatic UAC consent is allowed.

The route corpus is deliberately bounded. The trusted driver submits a fixed `$ca-review` request through the desktop window. The desktop's canonical thread state must contain the exact hashed user request and a completed `collabAgentToolCall` dispatch for `coverage-auditor`; Windows process/audit evidence must independently show the exact launched Store runtime reading `skills/ca-review/SKILL.md`, its linked `routines/dispatching-parallel-agents/SKILL.md`, and `agents/coverage-auditor.md` in order during that run window. The selected root comes from the first observed file-read path, not from an expected cache location. The receipt records only canonical event fields and domain-separated hashes of the observed thread, dispatch, process, file-audit, authentication, isolation, and teardown evidence. It never retains raw prompts, responses, command output, UI logs, screenshots, device codes, callbacks, cookies, tokens, or auth files. A complete candidate resource manifest remains a package-integrity preflight only and is never accepted as runtime proof.

The selected plugin root must be derived from the actual first audited skill-read path and then validate as the Codex marketplace cache entry under the disposable profile:

`<profile>\.codex\plugins\cache\<marketplace>\ca-codex\<version>`

The receipt binds the marketplace name, plugin name, exact version, normalized root, package digest, route corpus identifier, desktop thread/request hash, completed reviewer-dispatch hash, exact package/runtime process chain, and observable file-event sequence. Cache enumeration, glob selection, or semantic relabeling of generic reads is prohibited. A route event passes only when the desktop thread observation, dispatch item, process chain, and audit record agree.

Only the outer broker may finalize a PASS receipt. It does so after the guest probe exits, the disposable account is disabled/deleted, its profile is removed, the guest is destroyed or reverted to the approved clean state, and those outcomes are independently observed. The guest probe can report `teardown_requested`; it cannot attest its own destruction.

## Security invariants

- ChatGPT device authorization is the only allowed authentication mode. The lane pauses before consent and never uses API keys, access tokens, copied sessions, billable API access, or unrelated credentials. Before consent, the packaged Codex runtime must parse the strict configuration with zero startup warnings and execute allow/deny filesystem plus network probes through `codex sandbox -P desktop-proof`; a handwritten policy evaluator is not evidence. Candidate hooks are disabled. The candidate hook paths and complete `hooks.json` bytes are exact digest-bound inert executable inventories; MCP/server/app/script/executable additions and any behavioral declaration change are rejected. Windows process auditing requires exactly one trusted driver, measured app-server reader, route runtime, and pre-request canonical canary, bound by exact PID, parent, digest, start time, and command digest where applicable. The canonical route rejects every command-execution item. Credential, file, mapping, and doctor acquisition errors fail closed. CLI authentication is forced to file-only storage; after login the production driver inventory requires a zero-exit doctor result with all required named checks present and `ok`, proves exactly one `auth.json`, no matching Credential Manager target, a shell-denied canary, and zero successful reads of reusable-auth paths during the protected activation window. The guest response HMAC covers a recomputed digest of every route/security/sequence/teardown field trusted by the outer receipt.
- The VM has no host-profile mounts, clipboard/session import, shared host folders, unrelated secrets, or inherited host credentials. All pre-existing outbound allow rules are disabled; the disposable run receives only the exact reviewed DNS and HTTPS rules needed by the pinned Microsoft/OpenAI endpoints, and the effective rules are compared field-for-field before authentication.
- The runner/broker SID and disposable desktop SID are distinct and recorded as non-secret hashes or normalized identifiers.
- The broker/probe channel uses PowerShell Direct over local Hyper-V VMBus, whose endpoint is authenticated by the exact VM identity plus an explicit per-run guest credential. A fresh broker secret keys an HMAC-SHA-256 challenge over the VM, bootstrap SID, disposable SID, run window, and canonical response. The contract does not claim an independently inspected peer ACL or mutual authentication that PowerShell Direct does not expose. Query count, audit-record count, response count, UTF-8 byte size, schema, sequence, duplicate, replay, and timeout bounds are enforced mechanically.
- Candidate bytes are data only. Privileged workflow steps execute scripts solely from the trusted default-branch checkout.
- No receipt or artifact is finalized or uploaded until teardown succeeds. Failure leaves a non-PASS diagnostic with no secret-bearing material and blocks the proof gate.
- Tests may use clearly marked fixtures to exercise validation, but they must never emit, attest, or commit synthetic desktop PASS evidence.

## Acceptance criteria

1. **AC-01 — exact automation binding.** The trusted workflow verifies the tracked broker and guest-probe SHA-256 values against the trusted boundary manifest and verifies the installed execution copies match before either runs.
2. **AC-02 — exact image binding.** Provisioning and receipt validation require the approved Windows 11 Enterprise 25H2 x64 EN-US SHA-256 above; a wrong, missing, or unapproved image digest fails closed.
3. **AC-03 — trusted-code-only execution.** A regression contract proves privileged workflow steps execute verifier/broker/probe code only from the trusted default-branch checkout and treat the event-selected archive solely as inert data.
4. **AC-04 — separated identities.** The receipt distinguishes the GitHub runner/broker identity from the disposable interactive desktop identity and rejects equality, omission, or reuse.
5. **AC-05 — outer teardown finalization.** The guest probe cannot finalize PASS. The broker finalizes only after independently observing account disable/delete, profile removal, and guest destroy/revert.
6. **AC-06 — actual marketplace root.** Runtime validation derives the root from the exact first audited desktop skill read, accepts only the versioned Codex marketplace root under the disposable profile, binds marketplace/plugin/version/package digest, and rejects legacy, expected-path-only, or glob-selected roots.
7. **AC-07 — observable route corpus.** PASS requires one fixed request submitted through the real desktop window, its hashed canonical thread item, a completed coverage-auditor `collabAgentToolCall`, and exact Store-runtime process/audit evidence for the approved skill→routine→charter corpus. Static manifest equality or generic ordered reads alone cannot satisfy the criterion.
8. **AC-08 — authenticated bounded channel.** The PowerShell Direct exchange binds the exact VM and guest credential identity to a per-run HMAC challenge and enforces schema, audit/query/message count, UTF-8 byte size, monotonic sequence, duplicate/replay, and timeout limits. Unsupported peer-ACL or mutual-authentication claims are prohibited.
9. **AC-09 — device authorization and reusable-state isolation.** The broker permits only `chatgpt-device`, pauses before user consent, rejects API-key, access-token, copied-session, keyring, or silent-login modes, requires the real packaged Codex permission consumer to prove the strict hook-disabled profile before consent, requires the digest-bound inert hook inventory and parsed declarations, rejects every nonallowlisted activation process and route command execution, executes the production-used post-auth inventory plus required named all-OK doctor gate, verifies one file-only auth artifact and no matching Credential Manager target after login, and rejects any reusable-auth-path read during the protected activation window.
10. **AC-10 — non-secret evidence.** Durable outputs exclude device codes, callbacks, cookies, tokens, auth files, raw prompts/UI logs, screenshots, crash dumps, and opaque credential-shaped strings.
11. **AC-11 — VM isolation.** Provisioning establishes no host-profile mounts/shared folders/unrelated credentials, uses a disposable guest identity, and records only non-secret isolation outcomes.
12. **AC-12 — zero-spend local provisioning boundary.** The local Hyper-V path uses only the hash-verified official Microsoft evaluation image, requests elevation visibly, and introduces no cloud purchase or billable API use.
13. **AC-13 — attestation ordering.** Upload and attestation consume only a teardown-finalized receipt; incomplete or probe-authored receipts are rejected.
14. **AC-14 — governed delivery.** Failing-first tests, this approved spec, an implementation plan, and a bounded threat-model record ship with the prerequisite maintenance PR; all applicable repository tests and static checks pass.

## Explicit non-goals and authority limits

- No merge, tag, release, publication, deployment, or PR #711 integration before maintainer landing.
- No security override or weakening of the underlying security review.
- No device authorization consent in this prerequisite PR. After landing and PR #711 integration, dispatch may proceed only far enough to show the authorization URL and code and then pause for explicit consent.
- No proof claim from package manifests, backend-only tests, container tests, screenshots, or synthetic receipts.

## Open questions

None blocking. Host-specific availability discovered during provisioning is an execution blocker, not permission to change these acceptance criteria.
