# ca-pi reboot-safe handoff

**Originally recorded:** 2026-07-14

**Reopened:** 2026-07-17 after evidence-head Windows/Pi 0.80.5 test timeout

**Branch:** `feat/pi-support`

**Pull request:** [#313](https://github.com/arbiterForge/codeArbiter/pull/313)

**Prior attested implementation:** `3a1046d4254c44baf49a547b251589111af1fd88` (superseded by the test-harness recovery)

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
security and SMARTS reviews are CLEAN. Recovery run
[29552647068](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068) passed the complete
supported matrix and aggregate gate on the attested implementation. The feature is again at its
governed terminal state, but evidence-head run
[29553244197](https://github.com/arbiterForge/codeArbiter/actions/runs/29553244197) reopened it when the
real duplicate-host/package isolation proof hit its own fifteen-second Vitest timeout on Windows/Pi
0.80.5. No product assertion failed, and the paired 0.80.6 cell passed. Recovery raises only that
real-host integration-test ceiling to forty-five seconds. Commit, fresh hosted matrix, and final
evidence rebinding remain.

## Prior hosted promotion evidence (superseded)

Workflow run [29552647068](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068)
completed successfully on the prior attested implementation SHA. A fresh matrix is required for the
test-harness recovery commit.

| Required check | Result | Evidence |
|---|---|---|
| Windows, Pi 0.80.5 | success | [job 87798366352](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366352) |
| Windows, Pi 0.80.6 | success | [job 87798366366](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366366) |
| Linux, Pi 0.80.5 | success | [job 87798366376](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366376) |
| Linux, Pi 0.80.6 | success | [job 87798366364](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366364) |
| macOS arm64, Pi 0.80.5 | success | [job 87798366387](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366387) |
| macOS arm64, Pi 0.80.6 | success | [job 87798366358](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366358) |
| Scoped CodeQL | success | [job 87798366321](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87798366321) |
| Repository aggregate | success | [job 87799295412](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068/job/87799295412) |

The npm-latest canary remained visibly red and nonblocking as designed. It exercised unsupported Pi
0.80.10 and did not expand the supported set beyond 0.80.5 and 0.80.6.

## Prior final verification (superseded)

- The local preclosure verifier passed all 46 canonical gates before the attested push.
- The Windows live process-tree proof passed all 8 variants on the stock PowerShell fallback.
- Canonical PowerShell 7 selection and bounded cold admission passed on hosted Windows; both supported
  Windows cells completed.
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
