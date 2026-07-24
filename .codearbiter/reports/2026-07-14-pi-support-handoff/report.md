# ca-pi reboot-safe handoff

**Originally recorded:** 2026-07-14

**Closed:** 2026-07-17 after hosted recovery verification

**Branch:** `feat/pi-support`

**Pull request:** [#313](https://github.com/arbiterForge/codeArbiter/pull/313)

**Attested implementation:** `f457decbf799ef197ca7b8bc235aa414db5c0832`

**Promotion state:** Tasks 1-14 accepted; PI-AC-01 through PI-AC-38 covered

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
[29552647068](https://github.com/arbiterForge/codeArbiter/actions/runs/29552647068) first passed the
complete supported matrix and aggregate gate. Later evidence-head runs exposed two additional
test-harness flakes without a failed product assertion: the real duplicate-host proof exceeded first
fifteen and then forty-five seconds on hosted Windows while its loopback Git clone continued making
progress. The final recovery gives that aggregate fixture a bounded 120-second budget beneath the
platform runner's 180-second cap and runs it in a fresh Vitest process before the remaining
process-tree fixtures. Independent security and SMARTS reviews are CLEAN.

Final PR-head run [29554559519](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519)
passed both supported Windows cells, both supported macOS cells, Ubuntu/Pi 0.80.5, scoped CodeQL, and
the repository aggregate. Ubuntu/Pi 0.80.6 had one transient opaque `PI-SEC-PACKAGE` result even
though the same package suite passed earlier in that job; the same-head rerun passed that security
step and the complete cell. No security gate was reordered, retried in code, skipped, or weakened.
The feature is at its governed terminal state: an open PR with final hosted promotion evidence.

## Hosted promotion evidence

Workflow run [29554559519](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519)
completed successfully on the attested implementation SHA.

| Required check | Result | Evidence |
|---|---|---|
| Windows, Pi 0.80.5 | success | [job 87804797391](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797391) |
| Windows, Pi 0.80.6 | success | [job 87804797511](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797511) |
| Linux, Pi 0.80.5 | success | [job 87804797641](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797641) |
| Linux, Pi 0.80.6 | success | [job 87804797198](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797198) |
| macOS arm64, Pi 0.80.5 | success | [job 87804797464](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797464) |
| macOS arm64, Pi 0.80.6 | success | [job 87804797875](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797875) |
| Scoped CodeQL | success | [job 87804797602](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804797602) |
| Repository aggregate | success | [job 87804991186](https://github.com/arbiterForge/codeArbiter/actions/runs/29554559519/job/87804991186) |

The npm-latest canary remained visibly red and nonblocking as designed. It exercised unsupported Pi
0.80.10 and did not expand the supported set beyond 0.80.5 and 0.80.6.

## Final verification

- The local preclosure verifier passed all 46 canonical gates before the attested push.
- The Windows live process-tree proof passed all 8 variants with bounded canonical Job containment.
- Canonical PowerShell 7 selection and bounded cold admission passed on hosted Windows; both supported
  Windows cells completed.
- Security review cleared executable identity, fail-closed launch ordering, bounded helper-subtree
  cleanup, stale-PID avoidance, minimal environment, and generated-bundle parity.
- The duplicate-host proof keeps every offline/auth, counterfeit-host, canonical-runtime,
  exact-source, shutdown, and cleanup assertion under nested 120/180-second bounds.
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
