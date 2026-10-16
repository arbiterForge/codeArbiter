# Assistive state engine — current implementation status

**PR:** [arbiterForge/codeArbiter #983](https://github.com/arbiterForge/codeArbiter/pull/983)
**Branch:** `overhaul/assistive-state-engine` — **draft, unmerged, unreleased**.
**Earlier implementation evidence commit:** `95e8e18c3d6c2f9fecb74bccc40416c7a684cce1`.
**Direction:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md).
**Scope:** [single-PR task contract](assistive-state-engine-overhaul.md).

## Target

The agent reads the agreed outcome and bounded task context, implements useful
work, records actual checks and progress, and continues without artifact-origin
permission questions. True user stops, host security, journal/CAS integrity,
commits and publication permissions are **not** bypassed.

## Context and project catch-up expansion (2026-10-16)

The user expanded this PR to refresh project context and reconcile the active
project guidance with the assistive engine. Ordinary context preview/apply now
uses the installed native writer under existing authorization, without artifact
approval codes or a mandatory scout-qualification exchange. Exact source and
document identities, explicit selection, bounds, locks, paired writes, retained
before-images and recovery remain mandatory data-integrity controls.

The initialized project has been refreshed across all five content documents.
The native writer adopted four missing records and the legacy code-map record;
an action-boundary assessment observed five current v2 document/source identities.
The provenance records retain `semantic_review: unreviewed`: the independent
bounded source review is evidence at its stated scope, not a manufactured native
semantic attestation. Frontmatter and initialized state are preserved.

The refresh keeps accepted license, host, release, coverage and audit decisions,
and separates current instructions from dated results. Related release/authority
documentation debts are repaired, and Pi's release declaration now includes both
shipped helper bundles. Only evidenced board items are closed; independent feature
requests, live-host obligations and unresolved user decisions remain visible.

Current local proof includes the full native tests/vet, 28 context-workflow tests,
17 bridge tests, provenance tests, source/surface parity, and actual ordinary
create/update/recovery/refusal in isolated source-overlay fixtures for all three
hosts. These overlays are not published packages or live model qualification.
The independent release-owner exercise passed its bounded scenarios, and the
complete expanded review batch passed triage and aggregation with no unresolved
implementation finding. Both guard matrices pass 434 checks, the related hook
suites pass 153 tests, and the artifact-package suite passes 38 cases with one
Unix-only skip on Windows. Fresh hosted CI and diagram source pins still belong
to this expanded head; earlier passes below do not cover later changes. The
[catch-up record](../reviews/2026-10-16-pr983-context-catchup.md) records the nine
evidenced task closures and the retained backlog and qualification boundaries.

## Task tracker

| Task | Source state | Remaining |
|---|---|---|
| T01 | Approved direction and owning-callers inventory | None for design approval |
| T02 | Advisory scheduling; receipt-free task and batch progress; affected resident/catalog/status callers converted | Final-head hosted confirmation after any later source change |
| T03 | Scoped factual prerequisites and real user-decision records; old unknown scope retained | No additional source gap demonstrated |
| T04 | Reported checks; selected/shared inputs and applicable constraint bodies bound; native signed and Windows DWORD exit codes retained | Transitive dependencies remain explicitly unassessed; reported results are not host attestation |
| T05 | Feature, sprint, TDD, planning, execution and status adapted for Claude, Codex and Pi; ordinary installed Claude model journey passed | Codex and Pi live model cells remain unverified |
| T06 | Complete selected criteria and applicable constraints; bounded readback and named omissions; measured native orientation | End-to-end model cost unmeasured |
| T07 | Captured replies survive cleanup and recover without recapture; safe replay; complete saved-store restore with old client; later edits retained | Unknown historical formats remain unsupported |
| T08 | Three regenerated host adapters and 51 source-bound atlas owners; current chapter maps and ordinary HTML labels corrected; explicit proof on demand | Actual deployment and release derivative readback |
| T09 | Native, reconciliation, browser and mixed-client checks pass; hosted candidate matrix and installed Claude model canary passed | Final-head CI/package confirmation; publication readback after authorized release |
| T10 | Assistive context writer, five-document refresh, evidenced project catch-up and completed independent review | Expanded-head hosted checks and source-pin confirmation; unrelated backlog and genuine user decisions remain separate |

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
- **Hosted candidate:** CI run `38829939794` passed all 71 jobs for
  `ab6ebd3a1d2b77e9b4048bde350d34d8f056a018`; Docs run `38829939798`
  passed. This includes six native platforms and all 18 cold package cells.
  Native statement coverage was 8,234 / 9,820 (83.8493%), above the 70% floor;
  lines and branches were unmeasured. Readback verified all three archive
  hashes and 892 file records. Later commits need their own hosted result;
  the PR description records the final exact-head runs.
- **Installed bootstrap correction:** an actual model attempt exposed missing
  runnable bridge guidance. Commit `7623d82085ec1c398d4213904535224863c35312`
  supplies the correct helper installation and bounded request fields through
  stdin, with optional operation-schema discovery. The executable regression
  failed before the correction and passed afterward; all 51 authoring tests,
  16 surface tests and 151 generator tests passed (one Windows symlink skip).
  Independent review found no actionable issue.

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

## Actual installed model attempts

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

That first refusal came from the isolated Codex home omitting its Windows
sandbox implementation. A second invocation selected the existing restricted
token implementation, retained `workspace-write` and approvals `never`, and
correctly reported workspace-write. Its PowerShell reads stalled; the model
stopped without changing repository state. The owned stalled CLI was terminated.
Neither attempt qualifies Codex, and no full-access fallback was used.

Claude Code 2.1.296 then loaded the actual CI ca 3.0.0 archive through its
session-only plugin directory, using existing `auto` permissions. The first
attempt guessed the undocumented bridge initialization and request fields;
it also created an out-of-scope temporary helper. It was stopped after task
start and failing regressions, before implementation completion. This failed
attempt motivated the bootstrap correction above; it is not qualification.

The corrected local candidate reused that verified archive and native binary,
with only generated `includes/artifacts.md` replaced. Claude Code 2.1.296 /
`claude-opus-5-5` completed a fresh disposable configuration task in 81.516
seconds with normal `auto` permissions: bounded context, actual failing tests
(exit 1), implementation, the exact planned test command passing (exit 0),
reported checks and `DONE`. Fresh native readback returned plan revision 5,
current binding, `checks_are_verified: false` and `evidence_assessed: false`.
An independent rerun passed all three tests. No attestation was fabricated.

The successful run made 15 native operations (six identity, two task-context,
three operation-schema, one start, two check and one accept-scope), nine shell
calls and two source/test writes. It asked zero artifact permission questions,
launched zero reviewers and made zero explicit snapshot calls. Eleven tool
permission decisions were accepted by the host's existing configuration;
observed file changes stayed within the disposable repository. This is one
Claude model/session, not an all-host or all-model qualification claim.

Base archive SHA-256:
`38b6f755f637bc5285d706a032d0dfa1fe6fc9ecc63e1528512a60ef6641ddd5`.
Replacement guide SHA-256:
`219d3179edcd564a119982ed36768394c9af367f66a6482ab4d86f9977e98cbf`.
The local evidence directory beside the managed checkout retains the original
and corrected attempts, `claude-canary-v2-verification.json`, fresh readback,
independent test output and `context-benchmark.json`. These are local evidence,
not published receipts; final packaged-byte confirmation is recorded on the PR.

## Next executable work

1. Complete exact-head CI and correct proven failures without replacing source
   checks with looser assertions or adding new approval machinery.
2. Confirm the final candidate package against the successful installed model
   exercise, rerunning from final bytes when they differ. Retain all failed
   attempts and keep unexercised live-host cells unverified.
3. After authorized merge/publication, verify exact distributed package,
   marketplace, website and derivative bytes. Publication is not performed by
   this implementation task; no published tag is moved.

The Git repository retains earlier slice evidence and prior versions of this
status file. The active instructions and this tracker intentionally contain
only current operational facts.
