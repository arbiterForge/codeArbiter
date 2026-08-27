# Threat model — protected Codex desktop-proof boundary

**Date:** 2026-08-26
**Scope:** prerequisite maintenance architecture for PR #711
**Method:** bounded STRIDE review of the GitHub runner/broker → Hyper-V guest/probe → Codex desktop → receipt/attestation path.

## Assets and trust boundaries

- Trusted default-branch verifier, broker, probe, and boundary manifest.
- Event-selected `ca-codex` candidate archive, always inert data.
- Host runner identity and its GitHub job context.
- Disposable guest identity/profile and actual Codex marketplace cache.
- User-controlled ChatGPT device-consent boundary.
- Canonical route events and the finalized non-secret receipt.

Trust crossings are: GitHub event data into the trusted workflow; trusted host broker into a fresh ISO-applied Hyper-V guest through credential-authenticated PowerShell Direct over local VMBus; the pinned interactive driver into the actual Store desktop; canonical app-server/thread plus Windows process/file-audit observations into the bounded evidence response; and finalized receipt bytes into hosted attestation.

## Threats and controls

| STRIDE | Threat | Required control | Residual |
|---|---|---|---|
| Spoofing | Candidate or host replaces a boundary program; a lookalike process reads expected files; same identity is reused for runner and desktop. | Trusted manifest pins broker, driver, and probe; workflow verifies tracked/installed bytes; route records require exact Store package/signature, launched PID ancestry, disposable SID, app-server thread/dispatch correlation, and distinct identities. | A compromised host administrator can subvert Hyper-V and local identities; suspected compromise blocks proof. |
| Tampering | PR-selected code replaces a guest verifier or writable observation and forges a PASS with the HMAC key; route events, security digests, sequence state, or teardown request are changed/reordered; approved image or mutable template is substituted. | Execute only trusted-main programs; keep verifier bytes in an inheritance-disabled SYSTEM/Administrators-owned guest root, run/candidate data and the observation exchange in separate roots, rehash every guest verifier immediately before execution, freeze the observation before collection, and expose the HMAC key only to the rehashed privileged probe; recompute and HMAC-bind selected root, dispatch/thread identity, complete route events, security-record digest, sequence/timing state, and teardown request before receipt use; apply the exact verified Microsoft ISO into a new VHD every run. | A compromised guest administrator or host can still subvert the boundary; suspected compromise blocks proof. |
| Repudiation | Probe claims semantic routing or teardown from generic reads/static data. | Desktop submission and canonical thread/collab-dispatch items are correlated with exact process/file-audit records; only the outer broker finalizes after independently observed account/profile/VM teardown. | Desktop/app-server schemas can drift; unsupported drift fails closed and returns for review. |
| Information disclosure | Device code, cookies, tokens, prompts, UI logs, screenshots, crash dumps, or host credentials enter artifacts; candidate hooks, MCP/server/app declarations, or tools recover post-login state. | Device-auth pause before consent; exact digest-bound candidate hook path inventory and complete `hooks.json` bytes, treated as inert executable payload with hooks disabled; credential, filesystem, network-mapping, and doctor acquisition errors fail closed; file-only CLI storage requires exactly one `auth.json`, no matching Credential Manager target, and every required named all-OK doctor check; the packaged Codex runtime proves filesystem/network restrictions through its real sandbox consumer before consent; process auditing requires exactly one trusted driver, one measured app-server reader, one route runtime, and one pre-request canonical canary process, each bound by PID, parent, digest, time, and command digest where applicable; route observation rejects command-execution items; filesystem auditing rejects reusable-state reads. | The runtime must load authentication before the protected activation window; any later audited auth-path read or unexpected process fails the proof. The visible authorization UI is intentionally seen by the repository user but never persisted by the lane. |
| Denial of service | Guest floods/stalls the channel or leaves a profile/VM behind. | Message/count/size bounds, monotonic sequence, timeouts, fail-closed teardown, and no attestation on incomplete cleanup. | Manual host cleanup may be required after an infrastructure failure; that is not PASS evidence. |
| Elevation of privilege | Hidden UAC consent, overbroad runner permissions, guest-to-host mounts, or network use escapes the proof scope. | Visible local UAC only; least-privilege GitHub permissions; no host profile/shared folders; Hyper-V isolation; deny-by-default egress allowlist; no API keys/tokens. | Hyper-V and full-trust desktop rely on the host OS security boundary; zero-spend does not imply zero local resource risk. |

## Security verdict

The architecture is acceptable to implement only with every control above enforced mechanically and mutation-tested. Static package inspection, screenshots, backend/container behavior, or a probe-authored teardown claim cannot satisfy the desktop proof. Device authorization remains an explicit user-consent STOP after the prerequisite lands and is integrated into PR #711.
