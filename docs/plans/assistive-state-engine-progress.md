# Assistive state engine — current implementation status

**PR:** [arbiterForge/codeArbiter #983](https://github.com/arbiterForge/codeArbiter/pull/983)
**Branch:** `overhaul/assistive-state-engine` — **draft, unmerged, unreleased**.
**Implementation evidence commit:** `95e8e18c3d6c2f9fecb74bccc40416c7a684cce1`.
**Direction:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md).
**Scope:** [single-PR task contract](assistive-state-engine-overhaul.md).

## Target

The agent reads the agreed outcome and bounded task context, implements useful
work, records actual checks and progress, and continues without artifact-origin
permission questions. True user stops, host security, journal/CAS integrity,
commits and publication permissions are **not** bypassed.

## Task tracker

| Task | Source state | Remaining |
|---|---|---|
| T01 | Approved direction and owning-callers inventory | None for design approval |
| T02 | Advisory scheduling; receipt-free task and batch progress; affected resident/catalog/status callers converted | Exact-head integration checks |
| T03 | Scoped factual prerequisites and real user-decision records; old unknown scope retained | No additional source gap demonstrated |
| T04 | Reported checks; selected/shared inputs and applicable constraint bodies bound; native signed and Windows DWORD exit codes retained | Transitive dependencies remain explicitly unassessed; reported results are not host attestation |
| T05 | Feature, sprint, TDD, planning, execution and status adapted for Claude, Codex and Pi | Successful installed model exercise blocked by host policy |
| T06 | Complete selected criteria and applicable constraints; bounded readback and named omissions; measured native orientation | End-to-end model cost unmeasured |
| T07 | Captured replies survive cleanup and recover without recapture; safe replay; complete saved-store restore with old client; later edits retained | Unknown historical formats remain unsupported |
| T08 | Three regenerated host adapters and 37 source-bound atlas owners; ordinary HTML labels corrected; explicit proof on demand | Actual deployment and release derivative readback |
| T09 | Native, reconciliation, browser and mixed-client checks pass locally; actual candidate installed through Codex marketplace | Hosted exact-head matrix and successful model canary; publication readback after authorized release |

## Verified candidate checks

- **Native candidate:** Go 1.27.1 Windows/amd64, full `go test ./... -count=1`
  and `go vet ./...` passed through `tools/build-artifacts.py`. Binary SHA-256:
  `040d743097e0069f13f0c997be95dcb8bb06c5807a2a7b124544d1e92861334a`.
  Regression tests first reproduced constraint drift/context omissions,
  rejected native exit codes and the obsolete HTML banner.
- **Reconciliation:** 65 adapter tests pass using that candidate, including
  the crash between durable prompt capture and attempt persistence. The
  original immutable reply, operation ID and CAS are recovered; no new user
  event is created. Ambiguous or unsafe history is preserved for inspection.
- **Real two-binary T07 probe:** the engine built from base `045c0812`
  reads the complete restored 0.3.1 store with its original user stop. The
  old client refuses new-schema writes; the current engine preserves later
  edits during replay and exports newer work. All 16 probe outcomes pass.
  Restore occurs in a separate disposable repository.
- **Browser:** four tests pass in Chrome 154.0.8037.99 at desktop and compact
  widths, including keyboard, no-script/no-network, accessibility, print and
  enlarged text. Current rendered hashes are pinned in
  `docs/artifacts/browser-qualification.json`; historical HTML is unchanged.
- **Callers and integration:** cross-host projection regressions, 16 artifact
  surface, 43 debug, 18 consumer, eight provenance and 102 CI-impact tests pass.
  The final assistive/revalidation atlas suites pass all 20 tests. Shared core,
  host surfaces, generated types and embedded schemas match; site generation
  and the existing npm audit gate pass. Independent reviews found no remaining
  actionable implementation issue. Staged secret scanning found no leaks.
- **Public-doc integration:** both Codex farm cells and built-HTML assertions
  now report unavailability without an automatic provider/model switch. All
  1,072 site tests pass with two local workers and unchanged timeouts, followed
  by the Academy non-root-base and rendered-release checks. The unrestricted
  local worker count had exhausted timeout budgets; no test was skipped or
  relaxed to obtain the passing run.
- **Earlier offline installed fixtures:** ordinary progress and separate
  historical proof passed on all three adapters before this correction.
  Those results do not establish this candidate's hosted package matrix,
  model behavior, numerical coverage or release status.

## Bounded context measurement

The unchanged reference fixture `PLAN-ARTIFACTS-001#T-001` was read through
both native binaries on Windows. The baseline uses identity plus complete
paginated contextual reads; the candidate uses identity plus `task-context`.

| Measured value | Baseline | Candidate |
|---|---:|---:|
| Native calls | 10 | 2 |
| JSON response bytes | 107,378 | 13,212 |
| Task/criterion/constraint records | 103 | 8 |
| Median elapsed time, five sequential samples | 285.983 ms | 53.781 ms |

The smaller packet intentionally omits unrelated context and names omitted
references. This is native orientation, not identical payloads or an end-to-end
model/token benchmark. Neither measured path issues an explicit snapshot,
permission prompt or reviewer launch; internal file reads were not instrumented.

## Actual installed model attempt

The candidate was installed and enabled as ca-codex 0.18.0 through a real
isolated local marketplace. Installed source members and the native binary
matched the candidate bytes. Codex CLI 0.145.0 selected `gpt-5.6-sol` for the
bounded authorized configuration task in a disposable repository.

The request specified `workspace-write`, but the actual session enforced
`read-only`. It rejected the regression-test write, installed bridge execution
and required Python test command. No product or artifact state changed; no
check or `DONE` was recorded. CLI exit 0 represents conversational completion,
not qualification. The attempt took 92.056 seconds. Temporary authentication
was removed, and no sandbox, trust or approval policy was bypassed.

This establishes a real host refusal, **not a successful model canary**.
The local evidence directory beside the managed checkout retains
`canary-events.jsonl`, `canary-final.txt`, `canary-run.json` and
`context-benchmark.json`; these are local evidence, not published receipts.

## Next executable work

1. Complete exact-head CI and correct proven failures without replacing source
   checks with looser assertions or adding new approval machinery.
2. Complete the ordinary installed model workflow in a host that actually
   grants the required writes and test execution. Retain the refusal above;
   do not turn a fixture or host-policy bypass into qualification.
3. After authorized merge/publication, verify exact distributed package,
   marketplace, website and derivative bytes. Publication is not performed by
   this implementation task; no published tag is moved.

The Git repository retains earlier slice evidence and prior versions of this
status file. The active instructions and this tracker intentionally contain
only current operational facts.
