# ca-pi reboot-safe handoff

**Originally recorded:** 2026-07-14

**Reopened:** 2026-07-17 after PR-head Windows/Pi 0.80.5 launch-admission failure

**Branch:** `feat/pi-support`

**Pull request:** [#313](https://github.com/arbiterForge/codeArbiter/pull/313)

**Prior attested implementation:** `54080beadc8ff1fe6c8a5e0da81ad699c3ad0920` (superseded by the recovery patch)

**Promotion state:** Tasks 1-12 accepted; Tasks 13-14 in progress; hosted promotion pending

## Final resume boundary

The blocked Batch 2 handoff that originally occupied this file is superseded. Its interpreter,
activation, enforcement-installation, version-boundary, read-context, doctor, security, packaging,
cross-platform, and Windows process-containment findings were recovered and resolved test-first.
Do not resume implementation from the former Task 6 boundary.

PR-head run [29551679372](https://github.com/arbiterForge/codeArbiter/actions/runs/29551679372)
reopened the sprint when Windows/Pi 0.80.5 job
[87795375675](https://github.com/arbiterForge/codeArbiter/actions/runs/29551679372/job/87795375675)
missed the five-second canonical PowerShell Job-helper admission ceiling. The same implementation had
passed the same runner image previously, and the paired Windows/Pi 0.80.6 cell passed. Recovery raises
only the bounded cold admission budget to fifteen seconds, expands the live harness ceiling, and adds
fixed non-sensitive admission-stage diagnostics. Local live process-tree proof is 8/8; independent
security and SMARTS reviews are CLEAN. Commit, hosted matrix, and final evidence rebinding remain.

## Prior hosted promotion evidence (superseded)

Workflow run [29550379456](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456)
completed successfully on the prior attested implementation SHA. These results explain the recovered
race but do not promote the new implementation; a fresh matrix is required.

| Required check | Result | Evidence |
|---|---|---|
| Windows, Pi 0.80.5 | success | [job 87791467011](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791467011) |
| Windows, Pi 0.80.6 | success | [job 87791467010](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791467010) |
| Linux, Pi 0.80.5 | success | [job 87791467013](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791467013) |
| Linux, Pi 0.80.6 | success | [job 87791466989](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791466989) |
| macOS arm64, Pi 0.80.5 | success | [job 87791467006](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791467006) |
| macOS arm64, Pi 0.80.6 | success | [job 87791467051](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791467051) |
| Scoped CodeQL | success | [job 87791466968](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87791466968) |
| Repository aggregate | success | [job 87792299157](https://github.com/arbiterForge/codeArbiter/actions/runs/29550379456/job/87792299157) |

The npm-latest canary remained visibly red and nonblocking as designed. It exercised unsupported Pi
0.80.10 and did not expand the supported set beyond 0.80.5 and 0.80.6.

## Prior final verification (superseded)

- The local preclosure verifier passed all 46 canonical gates before the attested push.
- The Windows live process-tree proof passed all 8 variants on the stock PowerShell fallback.
- Canonical PowerShell 7 selection passed on hosted Windows; both supported Windows cells completed.
- Security review cleared executable identity, fail-closed launch ordering, bounded helper-subtree
  cleanup, stale-PID avoidance, minimal environment, and generated-bundle parity.
- `promotion.json` and `promotion.md` contain only the verifier's bounded sanitized fields and bind
  the six-cell matrix plus CodeQL to the attested implementation SHA.

## Preserved unrelated state

The user-owned `stash@{0}` containing unrelated `.codearbiter/open-tasks.md` review tasks was not
applied, dropped, or rewritten. No release, tag, merge, direct default-branch write, or publication
was performed.

## Resume command

If this session is interrupted, resume by checking PR #313 and running:

```powershell
git status --short
python .github/scripts/verify_pi_support.py --mode final
gh pr checks 313
```

Expected state: the final verifier is green, the PR remains open, and only an explicitly authorized
merge or later release workflow remains outside this sprint.
