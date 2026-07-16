# Tasks 13-14 hosted-evidence sequencing decision

Date: 2026-07-16
Branch: `feat/pi-support`
Attributed user: `SUaDtL@users.noreply.github.com`
User direction: continue the autonomous sprint through a PR and resolve non-hard-gate concerns with SMARTS.

## Conflict found

The approved outcomes are compatible, but the written sequence is circular:

1. Task 13 requires committed Windows, macOS, and Linux evidence for Pi 0.80.5 and 0.80.6.
2. Task 14 says not to commit, push, or open the PR until Tasks 1-14 are already accepted.
3. Task 14's verifier also requires Task 14 to be `ACCEPTED`, although its own green run is the evidence that earns that status.

No local command can honestly manufacture hosted runner or CodeQL evidence for an uncommitted tree.

## SMARTS decision T13-D01

**Verdict: use one sanctioned evidence PR checkpoint, then finish the same PR after hosted evidence; make the aggregate verifier explicitly preclosure-aware. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) Require Task 13/14 acceptance before any commit or PR | Hosted evidence can never be produced. | Preserves circular prose rather than the intended gate. | Unavailable. | Forces a false claim or permanent deadlock. | The required matrix cannot run. | No security benefit; encourages fabricated evidence. | Rejected |
| (b) Sanctioned checkpoint commit/PR after local preclosure, then hosted matrix and final status commit on the same branch | One sequence works for every future hosted-only gate. | Keeps implementation, evidence, and final closure in one reviewable PR. | Uses the repository's existing governed commit/PR and CI paths. | Every promotion claim binds to an immutable commit and real hosted result. | Preclosure and final verifier modes are deterministic and self-tested. | No gate is weakened; hosted security and CodeQL become real prerequisites to final closure. | Strong |
| (c) Treat local Windows or mocked platform cells as the full matrix | Easy to repeat but not representative. | Adds a second, misleading evidence meaning. | Available locally. | Cannot detect runner- or OS-specific failures. | Tests the harness, not the hosted contract. | Omits required platform security evidence. | Rejected |

## Required sequence

1. Complete Tasks 6-12 and all local Task 13 harness/evidence-schema work.
2. Run Task 14 in **preclosure** mode. It must require Tasks 1-12 accepted, Task 13/14 in progress, obligations PI-AC-01 through PI-AC-34 covered, the remaining obligations explicitly open, all local canonical suites green, sanitized provisional evidence, clean generation, and no partial-release artifacts.
3. Run the normal governed review and `$ca-commit`, then `$ca-pr` to create the evidence PR. This is not a partial release, merge, tag, or publication.
4. Require the same committed SHA to pass the six supported hosted cells, security/CodeQL, and the nonblocking latest canary. Generate only sanitized result-code evidence.
5. Accept Task 13 and PI-AC-35 after independent evidence review.
6. Run the preclosure verifier with Tasks 1-13 accepted and Task 14 in progress; that green result earns Task 14 / PI-AC-37 / PI-AC-38 acceptance. Update statuses, then rerun the verifier in **final** mode so it requires all Tasks 1-14 accepted and all 38 obligations covered.
7. Land the status/evidence update through `$ca-commit` on the same PR, rerun affected CI, and keep working until the PR is green and review-clean. Do not merge, tag, or publish.

The sprint-log append remains unavailable through `apply_patch` under H-05. This report is the durable decision record; no bypass is used.
