# Plan — protected Codex desktop-proof boundary hardening

Spec: `.codearbiter/specs/desktop-proof-contract-hardening.md` (approved 2026-08-26). Stage 2. Security-sensitive maintenance prerequisite for PR #711.

## Obligation ledger

All obligations below are one-to-one transcriptions of the approved acceptance criteria, so TDD Phase 1 auto-passes without a second approval.

| ID | Source | Status | Failing-first proof |
|---|---|---|---|
| O-01 | AC-01 | IN REMEDIATION | First review found the desktop driver absent; manifest must bind all three programs and installed copies |
| O-02 | AC-02 | IN REMEDIATION | ISO digest was checked but an unrelated template VHD was executed; direct per-run ISO application required |
| O-03 | AC-03 | IMPLEMENTED | Workflow trust-separation regression green |
| O-04 | AC-04 | IN REMEDIATION | Receipt mutation test exists; runtime identity observation and behavior harness required |
| O-05 | AC-05 | IN REMEDIATION | Static teardown-order test was vacuous; observable lifecycle trace and injected failures required |
| O-06 | AC-06 | IN REMEDIATION | Expected cache root was synthesized; root must derive from the first exact audited skill read |
| O-07 | AC-07 | IN REMEDIATION | Generic 4663 reads were assigned semantic labels; desktop thread + dispatch + process correlation required |
| O-08 | AC-08 | IN REMEDIATION | Nonce/ACL values were echoes and bounds unenforced; honest PowerShell Direct/HMAC binding and executable bounds required |
| O-09 | AC-09 | IN REMEDIATION | Device mode was declared, not observed from prompt-ready, login completion, and account state |
| O-10 | AC-10 | IN REMEDIATION | Durable-field validator exists; bounded output inventory and post-teardown observation required |
| O-11 | AC-11 | IN REMEDIATION | Isolation values were hardcoded and firewall checks accepted arbitrary allow rules |
| O-12 | AC-12 | IN REMEDIATION | Direct ISO-to-fresh-VHD provisioning and exact effective egress policy required before local execution |
| O-13 | AC-13 | IN REMEDIATION | Structural workflow check exists; executable teardown trace must gate receipt finalization |
| O-14 | AC-14 | BLOCKED BY REVIEW | First ca-review normalized 15 findings into T1 Critical, T2-T10 High, and two Medium follow-ups |

## Files and implementation tasks

| Task | Files | Action | Covers | Depends on |
|---|---|---|---|---|
| T-01 | `.github/desktop-proof-boundary.json` (new) | Bind the exact broker/probe/desktop-driver bytes, direct ISO image application, Store/runtime provenance, fixed `$ca-review` route, exact egress rules, honest PowerShell Direct/HMAC channel, and prohibited evidence/auth modes. | O-01,O-02,O-06,O-07,O-08,O-09,O-10,O-11,O-12 | — |
| T-02 | `.github/scripts/test_codex_desktop_boundary.py` (new) | Execute shared broker/probe/driver state machines through fixture adapters; cover success plus every provision, auth, route, isolation, teardown, flood, spoof, and cleanup failure without emitting proof receipts. | O-01,O-02,O-04,O-05,O-06,O-07,O-08,O-09,O-10,O-11,O-12 | T-01 contract shape |
| T-03 | `.github/scripts/test_ci_impact.py`, `.github/scripts/test_codex_skill_resources.py` | Add failing-first workflow/receipt regressions: trusted-code-only execution, digest verification before launch, teardown before upload/attestation, versioned marketplace root, and route events rather than manifest equality. | O-03,O-04,O-05,O-06,O-07,O-13 | — |
| T-04 | `.github/scripts/check_codex_skill_resources.py` | Upgrade desktop receipt validation to the corrected schema: separated identities, broker-finalized teardown, exact boundary/image bindings, versioned selected root, bounded canonical event sequence, and non-secret output. Retain the candidate manifest only as integrity preflight. | O-01,O-02,O-04,O-05,O-06,O-07,O-08,O-09,O-10,O-11,O-13 | T-02,T-03 red |
| T-05 | `.github/scripts/Invoke-CodeArbiterDesktopCandidate.ps1` (new) | Implement the outer state machine: split immutable guest verifier/run/exchange roots with exact ACLs and immediate rehashes, direct ISO-to-fresh-VHD application, exact firewall/isolation setup, exact digest-bound inert hook path and complete `hooks.json` byte inventories with hooks disabled, real pre-consent Codex sandbox probes, fail-closed credential/file acquisition plus production-used file-only inventory and required named all-OK doctor checks, hook-disabled exact activation-process allowlisting, a response-complete HMAC channel, explicit device-consent handoff, measured teardown, and receipt finalization from a frozen observation only. | O-01,O-02,O-04,O-05,O-08,O-09,O-10,O-11,O-12 | T-02 red |
| T-06 | `.github/scripts/Invoke-CodeArbiterDesktopRouteProbe.ps1` (new) | Implement privileged audit preparation/collection: exact Store process ancestry, app-server/driver correlation, audited-root derivation, bounded 4688/4663 records, zero reusable-auth-path reads during the candidate window, HMAC response, and no semantic inference from path order alone. | O-01,O-05,O-06,O-07,O-08,O-09,O-10 | T-02 red |
| T-06a | `.github/scripts/Invoke-CodeArbiterDesktopUiDriver.ps1` (new) | In the disposable interactive session, drive the actual desktop window with a fixed non-secret request, observe account mode and canonical thread/collab-dispatch items through the measured bundled app-server, reject every route command-execution item, and emit only bounded hashes and exact process identifiers. | O-01,O-04,O-06,O-07,O-09,O-10 | T-02 red |
| T-07 | `.github/workflows/codex-desktop-candidate.yml` | From trusted main, validate the boundary manifest, script bytes, installed copies, and image digest before launch; pass the candidate only as data; upload only the broker-finalized post-teardown receipt; keep actions/permissions pinned and narrow. | O-01,O-02,O-03,O-05,O-09,O-13 | T-03 red,T-04,T-05,T-06 |
| T-08 | `.github/workflows/ci.yml`, `.codearbiter/tech-stack.md` | Register the new tests and preserve CI/tech-stack parity. | O-14 | T-02,T-03 |
| T-09 | `.codearbiter/reports/2026-08-26-desktop-proof-boundary-threat-model.md`, spec, plan | Record trust boundaries, STRIDE threats, mitigations, residual risks, approval, and proof limits. | O-14 | — |
| T-10 | local Hyper-V state outside the repository | Download the official image, verify exact SHA-256 before use, request visible elevation, provision the isolated guest without host-profile mounts or unrelated credentials, and verify the broker's pre-auth stop. Do not persist credentials or synthetic proof. | O-02,O-08,O-09,O-11,O-12 | T-04,T-05,T-06 green and review |
| T-11 | governed commit and PR metadata | Run applicable full tests/static checks, independent security/review gates, sanctioned staging/commit, push, and open the separate maintenance PR. Stop at maintainer landing. | O-14 | T-01..T-10 |

## TDD order

1. Add T-02/T-03 assertions and run them against current main. Every new assertion must fail for the named missing behavior while the existing suites remain green.
2. Implement T-01 and T-04..T-07 minimally until the unchanged red assertions pass.
3. Perform the mutation walk: wrong script hash, wrong image hash, same identities, probe-authored PASS, incomplete teardown, legacy root, glob-selected root, missing/reordered/extra route event, nonce mismatch, unauthorized peer, oversize event, non-device auth, keyring or extra auth state, subprocess/runtime/desktop auth-path reads during the route, contradictory plugin/profile permissions, secret-bearing field, host mount, and upload-before-teardown must each fail at least one test.
4. Wire T-08, run the applicable repository suite, and take the Python no-coverage-tooling exemption exactly as documented in `.codearbiter/tech-stack.md` after obligation verification.
5. Re-run T-09 independent security/auth/coverage/architecture review and require zero Critical/High findings; preserve the two Medium findings as explicit follow-up work unless resolved in this branch.
6. Only after code review is green, perform T-10 local provisioning. Stop before device consent.
7. Run `ca-commit` and `ca-pr` for T-11. The PR is the terminal output of this prerequisite branch; landing remains maintainer-only.

## Verification commands

Focused red/green:

```powershell
python .github/scripts/test_codex_desktop_boundary.py
python .github/scripts/test_codex_skill_resources.py
python .github/scripts/test_ci_impact.py
python .github/scripts/test_release_workflow.py
```

Static and workflow checks:

```powershell
python .github/scripts/check_codex_skill_resources.py --candidate-contract-only --candidate-package plugins/ca-codex --json
python .github/scripts/check-plugin-refs.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

The commit gate determines the complete impacted suite from the final staged paths; these focused commands do not replace it.

## Stopping points

- Any missing official image hash match, Hyper-V prerequisite, trustworthy desktop event source, or supported device-auth handoff blocks proof; it does not authorize a substitute.
- The prerequisite PR may be pushed and opened but not merged by this campaign controller.
- After maintainer landing, PR #711 integration and the approved CodeQL #23 correction resume. Dispatch stops after displaying the device-authorization URL and code; user consent is a separate gate.
