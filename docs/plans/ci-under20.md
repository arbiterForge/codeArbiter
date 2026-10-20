# codeArbiter: complete CI under 20 minutes

**Status:** PROPOSED IMPLEMENTATION PLAN; performance target not achieved.
**Scope:** `arbiterForge/codeArbiter` only. This delivery changes documentation only.
**Owner:** repository maintainer; execution may be delegated to a CLI implementation agent.
**Planning date:** October 19, 2026, America/New_York.
**Plan-only PR base:** `849a3cf6fa6f4fdf3256cd3095c92499e9c4ec77`.
**Historical implementation reference:** [PR #993](https://github.com/arbiterForge/codeArbiter/pull/993), head `16983f5017b39e35de2f90994e30fcd60730e82c`.
**Evidence:** [frozen timing and dependency-model summary](ci-under20-evidence.json), assessed October 19, 2026.

This is the durable handoff for a subsequent implementation, not an implemented workflow,
a qualified release, an accepted ADR, or permission to relax verification. Merging this
plan does not implement CI changes or approve account settings, spending, or a public
performance claim. All execution tasks below start unchecked.

## 1. Outcome and operating envelope

Make the complete full-workload CI path finish successfully in **less than 1,200 seconds**
from the original trigger through the last required result. Include scheduling,
provisioning, all selected tests, downstream packages, and the final merge-readiness gate.
Include applicable independent required analysis workflows in the same endpoint; do not
stop the clock at one green workflow while another required result is pending.

Qualify both a solo run and **two overlapping full runs**, including their waiting time.
This is a finite operating envelope, not a promise about unlimited simultaneous submissions.
Target approximately **16–17 minutes of execution/dependencies**, leaving **2–3 minutes**
of scheduling headroom. Runner hours are a capacity input, not a cost-minimization objective.

**Recommendation:** build the CI test binary early, verify independent configurations and
candidate consumers in parallel, qualify only after complete evidence, and obtain enough
concurrent runner capacity. Do not spend the next implementation merely changing shard
counts, increasing deadlines, or moving required checks to nightly runs.

## 2. Frozen evidence, not current implementation proof

The companion JSON is preserved from the preceding read-only assessment. Its historical
`repository_changes: false` and `inspected_main` describe that assessment, not publication
of this plan. It is a calculated summary, not a raw job-API archive or an executable model.
Its simulations must be reproduced before implementation acceptance.

| Source and result | Observed elapsed | Queue-free dependency replay |
|---|---:|---:|
| #993 run `39088746696`, head `16983f50`; 113 successful jobs | 59m43s | 21m11s |
| Earlier #993 run `39069528962`; 125 successful jobs | 23m59s | 21m04s |
| Earlier #993 run `39071349661`; 125 successful jobs | 28m44s | 21m31s |
| Assessment-main run `39310829347`, head `05395634`; 77 successful jobs and six legitimate skips | 56m16s | 46m43s |

Queue-free replay preserves each measured job duration, including setup and cleanup, but
assumes immediately available capacity. It does not simulate changed contention or prove
that the same timings apply to another source tree.

For run `39088746696`, the actual determining chain contained **15m51s of execution**,
**43m51s of ready-to-start delay**, and one second of workflow settlement. That delay
includes scheduling/provisioning; it is not all proven to be an account-quota effect.
One Intel macOS conformance job waited 18m59s. A final native qualification job waited
9m56s for 65 seconds of execution. Removing waiting still leaves a different limiting
chain longer than twenty minutes: native candidate verification followed by authority
verification, qualification, assembly, and cold-package checks.

The plan-only branch starts at `849a3cf6fa6f4fdf3256cd3095c92499e9c4ec77`, newer than both
the benchmark PR and assessment main `0539563484b2b487be77a3370d2952acb579fd2c`.
No timing from the older trees qualifies this base. CI20-01 must re-read the then-current
main and carry forward every newer obligation. Project portfolio/claim snapshots from
September 1 and October 7 are historical context, not current CI authority.

### Modeled route and assumptions

| Proposed scenario | Modeled no-queue path | Assumptions, not measured gains |
|---|---:|---|
| Existing benchmark PR graph | 21m11s | Actual dependencies and measured job durations retained. |
| Early CI-only build; full verification on independent branches | 18m04s | Early build job takes 90–180s; all original builder work remains required; other job durations unchanged. |
| Above plus lightweight final qualification | 16m27s | Early build takes 120s; final qualification takes 15s without fresh native provisioning. |

The 16m27s chain is impact 10s, longest native configuration group 787s, coverage union
52s, qualification 15s, assembly 51s, cold package 68s, and final gate 4s. Hook checks
remain on their independent required branches. Consumers that truly need a qualified
installation must stay after qualification, potentially changing this model.

## 3. Non-negotiable constraints

- Retain all current native platforms and required configurations: default, CGO-disabled,
  instrumented, context/storage, authority/conformance, and Linux race obligations.
  Discover the current test population; historical case counts are not an allowlist.
- Preserve coverage denominators, complete profile unions, current floors, installed-host
  behavior, exact package/cold-install verification, and legitimate platform exceptions.
- Never set `native_tested: true` for a compile-only input, introduce a production-wide
  permissive environment switch, or let failed source tests become a qualified package.
- Keep the protected merge context and both dependency/result registrations complete.
  Reject missing, failed, cancelled, skipped-required, stale, duplicate, cross-run, or
  changed-byte evidence. Do not weaken ordinary installation or publication admission.
- Preserve failed-run diagnostics, source/run/attempt identity, private worker isolation,
  cleanup failure behavior, and no-test-retry semantics. Reusing compiler work is distinct
  from using cached successful test results as fresh proof.
- Do not cancel an unrelated current PR, subtract queueing, benchmark only quiet warm runs,
  or shrink full-workload selection to claim success. Preserve existing superseded-commit
  cancellation policy; it is not a license to hide failed acceptance attempts.

## 4. Architecture to implement

### 4.1 Build first; qualify last

Current shape:

```text
setup -> complete native tests/vet -> build tested candidate
      -> authority / conformance / bridge checks
      -> global qualification -> package assembly -> cold checks -> merge gate
```

Proposed shape (all verification branches remain required):

```text
trigger -> impact / preflight
           |-> native CI-only build -> eligible candidate consumers --|
           |-> complete source/configuration verification ------------|-> strict qualification
           |-> hook and other required checks ------------------------|       -> exact packages
                                                                             -> cold checks
                                                        all required results -> merge gate
```

Introduce an explicit **CI-only unqualified test-input contract**. Bind source commit,
native OS/architecture, build flags, pinned Go executable/module identity, and candidate
bytes. Test-fixture admission is not ordinary installed-product admission. Classify every
consumer before moving it: binary tests may start early; installation/qualification tests
that require a qualified candidate cannot be silently reclassified.

Retain complete native verification as independent required work. Capture evidence for
the same immutable source and candidate cohort. If a verification path rebuilds the
candidate, compare the intended byte identity and document any permitted non-byte-equivalent
configuration; do not assert that a different executable was the tested candidate.

Only the final approved qualification owner may transition the candidate to qualified.
Ordinary installs must reject provisional inputs. Preserve the current normal builder's
behavior unless the new mode explicitly and safely separates CI construction from its
ordinary tested-output contract. `--skip-tests` plus a forged flag is not this design.

### 4.2 Capture native observations where tests execute

Native jobs record their real observations and candidate bindings while they already have
the correct host/tool environment. A lightweight final aggregation step validates the
complete evidence and authorizes assembly; it must not allocate six fresh native runners
solely to reinstall tools and issue receipts, or keep scarce runners idle until other
platforms finish.

This changes receipt ownership. Define and review that contract before altering the
protected emitter or its downstream consumers. An unkeyed JSON digest detects substitution;
it is not a signature or an independent execution attestation. Enumerate the same-run
artifact and trusted-job boundary, the exact fields checked, replay rules, missing-job
handling, and the decision about reused successful producer attempts. Reject forged PASS
records and transport/source confusion. Native proof still comes from actual native jobs.

Keep downstream package names/formats and verifier expectations compatible, or change
all required producers/readers coherently with migration and rollback tests. Archive and
cold-install verification still happen after genuine qualification. The 15-second join is
a measurement hypothesis, not permission to discard checks.

### 4.3 Capacity is part of the design

The benchmark consumes **288.03 runner-minutes**, including **76.98 macOS runner-minutes**.
For two identical simultaneous runs, a workload-only lower bound at 20 total slots is
28.80 minutes; at five macOS slots, the macOS-only bound is 30.79 minutes. Meeting twenty
minutes requires averages above 28.8 total and 7.7 macOS slots, before dependency bursts
and other workloads. Runner labels, not platform-looking job names, classify these totals.

The effective organization entitlement/override is **UNKNOWN**. Do not infer it from peak
observed jobs or public plan defaults. CI20-05 must verify it and current official limits.
The provisional sizing request is approximately **60 total and 15 macOS concurrent standard
jobs**, recalculated for the implemented graph. It is not an approved quota or guaranteed
provisioning. A numerically feasible average is not sufficient scheduling headroom.

Public standard-runner minutes and concurrency are separate concepts. Verify billing
before any alternative capacity choice. Support requests, quota/account changes, dedicated
infrastructure, and paid capacity require separate maintainer approval. Use only authorized
personal ArbiterForge infrastructure, ephemeral isolation and minimal tokens if a fallback
is approved; do not expose release secrets to untrusted PR code.

## 5. Execution tasks and dependency order

All tasks are pending. Implementation ownership below is a role, not an assertion that
work has been assigned or completed. Prefer one coherent implementation PR with reviewable
internal commits; this plan-only PR must not acquire code or workflow changes.

| ID | Task | Owner | Depends on | Exit evidence |
|---|---|---|---|---|
| CI20-01 | Freeze current source, obligations and benchmark | Implementer | None | Inventory and baseline on exact current main; all required workflows included. |
| CI20-02 | Specify CI-input admission and qualification ownership | Implementer + maintainer review | CI20-01 | Proposed ADR/contract, consumer classification, evidence/state-transition matrix and failing negative controls. |
| CI20-03 | Implement early build and independent complete verification | Implementer | CI20-02 | Bound candidate reused; original tests/configurations retained; strict installed-input refusal. |
| CI20-04 | Replace late native reprovisioning with strict aggregation | Implementer | CI20-03 | Native records validated once; complete qualification/assembly/rollback tests; measured shorter tail. |
| CI20-05 | Verify and secure concurrent headroom | Maintainer; implementer supplies data | Starts with CI20-01, recalculated after CI20-04 | Effective limits, approval record if needed, and measured two-run scheduling capacity. |
| CI20-06 | Optimize the remaining measured bottleneck, only if necessary | Implementer | CI20-04 and first full measurements | Same-workload before/after evidence; no verification loss. |
| CI20-07 | Qualify full end-to-end latency and finalize documentation | Implementer + maintainer acceptance | CI20-04, CI20-05, and CI20-06 if used | Five solo runs and two overlapping pairs, all under 1,200s, including cold-cache coverage. |

### CI20-01: reconcile without carrying forward stale implementation

- [ ] Pin then-current main, benchmark/prototype heads, exact merge revision, relevant
  workflows, package/qualification consumers, and current required check identities.
- [ ] Inventory commands, configurations, native platforms, selectors, skips, thresholds,
  artifact owners and current timeout decisions. Preserve newer SMARTS/ship-set tests,
  Windows fixes and other current-main requirements; do not restore older assumptions.
- [ ] Use #993 as a commit-bound reference. Review reusable improvements such as
  duration-balanced fixture isolation, conformance overlap, pagination, diagnostic naming
  and bounded cleanup. Do not cherry-pick its complete obsolete workflow or resolve a
  conflict with wholesale older files.
- [ ] Reproduce the dependency replay from all job pages, preserving setup and cleanup.
  Validate job identity, completeness and timestamps. Record assumptions explicitly.
  Keep raw metadata and reproducible calculation tooling with subsequent benchmark receipts.

**Exit:** a current-source checklist and source-to-job map that make every missing
obligation visible, plus a reproducible benchmark. Do not describe plan publication as
this task's completion.

### CI20-02 through CI20-04: candidate and evidence contracts

- [ ] Specify provisional, verified and qualified states; who may emit each; which
  consumers accept them; and how each state is tied to actual source and executable bytes.
- [ ] Add negative tests first for ordinary-install refusal, failed native verification
  alongside successful adapters, wrong source/platform/tool/flags, mutated binaries,
  missing configurations, partial coverage, empty or all-skipped workers, duplicate
  records, cross-run/attempt confusion, and altered transport/artifact identities.
- [ ] Build early without claiming qualification. Start only eligible consumers; keep all
  current verification work as independent required jobs. Track the same immutable input.
- [ ] Capture native observations in executing jobs and implement a single auditable
  aggregate. Preserve native-only assertions; prevent an aggregator from inventing them.
- [ ] Update every affected producer/consumer and exact-check contract together. Keep
  impact selection and both merge-gate registrations closed over all new subjects.
- [ ] Test retries, failed child cleanup, response loss, incomplete artifact upload,
  superseded source and rollback. Preserve logs without private worker directories.

**Likely owners, to verify against the implementation base:**
`tools/build-artifacts.py`, `tools/artifact-coverage.py`, ordinary admission in
`core/pysrc/_artifactlib.py`, the CI candidate/qualification helpers, workflow producers
and consumers, test-fixture adapters, impact maps, and their regression tests. Some helper
paths and `.github/workflows/ci-native-platform.yml` exist only in the #993 reference;
create or adapt deliberately rather than assuming they are already on main. Do not edit
ordinary product admission merely to make CI easier.

### CI20-05: scheduling headroom

- [ ] Record effective standard and macOS limits, observed queue delay, competing workflow
  demand, cold provisioning and any existing per-workflow/group concurrency constraints.
- [ ] Recompute workload minima and peak demand with the new graph. Seek maintainer approval
  before contacting Support, changing account quotas/settings or using paid/dedicated capacity.
- [ ] Exercise two current full runs concurrently without cancelling unrelated current work,
  moving admission outside the timer, or assuming larger machines lift macOS limits.

**Exit:** an approved and measured operating envelope, or an explicit unresolved capacity
blocker. A denied quota request does not authorize weaker coverage or a changed stopwatch.

### CI20-06: only optimize newly measured limiting suites

Profile before editing. Assessment-main instrumented `internal/operations` took 494.584s
on Windows x64 and 454.268s on ARM64. The Windows hermeticity job was roughly 14–15 minutes.
These are historical leads, not evidence that the same files limit the new candidate.

- [ ] Obtain per-test JSON timings and distinguish compilation, setup, filesystem work
  and tests. Preserve all discovered native cases and complete coverage accounting.
- [ ] Use bounded process isolation for fixtures that mutate process-global environment
  (`t.Setenv` is present in the historical completion fixture); do not blindly add
  `t.Parallel` or multiply full native configurations on a small Windows runner.
- [ ] Retain seeded-home byte comparisons, warning/handle/process-leak detection,
  environment variants, and negative tests proving the hermeticity guard can fail.
- [ ] Run alternating-order same-workload comparisons where useful; qualify the hosted
  outcome separately. Mark this task not needed only with a recorded timing justification.

## 6. Acceptance and evidence schema

CI20-07 is complete only when all of the following are checked:

- [ ] Five complete solo runs and two pairs of overlapping complete runs: **nine runs
  total**, on the same reconciled implementation head, including at least one cold
  compiler-cache case. Retain any failed attempts rather than replacing their history.
- [ ] Every accepted run succeeds in less than 1,200 seconds from the recorded trigger
  to the final required completion. Document the timestamp source; do not substitute
  a later job start or retry start. Include applicable required analysis workflows.
- [ ] Every current native platform, configuration, test population, qualification
  boundary and exact package/cold-install obligation is accounted for. Legitimate
  platform skips are named; required omissions cannot pass.
- [ ] Evidence matches the exact source/run/attempt and candidate hashes. All negative
  controls remain effective. Qualification does not precede complete required success.
- [ ] Actual overlapping-run capacity and queue-delay budgets are demonstrated. A quiet
  warm-only result or one fast run is insufficient. This initial sample is not a p95/p99
  estimate and does not create a universal performance guarantee.

For each acceptance attempt retain: source head and synthetic merge SHA; run/attempt;
trigger and final timestamps; complete required-workflow set; all paginated job/step
records; runner labels and observed entitlement; configuration/test membership and
outcomes; candidate/tool/module/profile identities; artifact digests; execution,
dependency-wait and ready-to-start components; concurrent-run cohort; cache/provisioning
conditions; and computed totals. Bind future measurement scripts and their inputs by
commit/digest. Preserve failed/cancelled results as failed/cancelled, not speedups.

If execution remains over budget, inspect the current critical path before editing
another shard count. If external scheduling prevents the target, record that blocker and
obtain approval for a capacity alternative. Do not redefine start-to-finish.

## 7. Propagation, approvals and rollback

**Propagation order:** establish current-source inventory and reviewed contract; add
negative tests; update construction/fixture consumers; update native record producers
and qualification/package readers; update orchestration, impact/merge gates and tests;
refresh affected provenance through the native writer; run hosted acceptance; only then
update implementation docs with measured results and qualified scope.

Use the existing architectural-decision process for the new admission/receipt ownership.
This plan is not that accepted decision. Do not change product branding, versions,
licensing, maturity or public compatibility claims as part of CI optimization. Any real
shipped-contract change discovered during implementation needs its own correct scope,
review and release handling, not a blanket exemption because the goal is CI speed.

No Project canon or claim-registry edit is part of this documentation delivery. Timings
remain commit-bound observations; model rows stay labeled unexecuted. Capacity and
spending decisions remain separately approval-gated. No account changes are authorized
by merging this plan.

**Implementation rollback:** revert the coherent execution/receipt-ownership change with
its matching workflow contracts and provenance. Test the previous qualified path before
removing it; preserve historical artifacts and failed-run evidence. Do not strand an
intermediate candidate format in ordinary publication. No user project-state migration
is intended; any incompatible producer/reader transition must be explicitly designed.

**Plan-only rollback:** revert these two documentation files. This PR neither merges
#993's implementation nor touches CI, tests, production source, manifests, generated
surfaces, provenance, account settings or releases. Existing workflow policies may run
checks on the PR normally; no run cancellation or manual dispatch is requested here.

## 8. Source and document continuity

This plan supersedes #993 as the implementation handoff. The older PR's head, review
history and run evidence remain reference material, not merge-ready implementation or
proof of this plan. A subsequent implementer starts from current main and follows
CI20-01 instead of depending on a mutable old branch name.

Frozen assessment sources (historical, not live implementation assertions):

- `arbiterForge/codeArbiter@16983f5017b39e35de2f90994e30fcd60730e82c:.github/workflows/ci.yml`
- `arbiterForge/codeArbiter@16983f5017b39e35de2f90994e30fcd60730e82c:.github/workflows/ci-native-platform.yml`
- `arbiterForge/codeArbiter@16983f5017b39e35de2f90994e30fcd60730e82c:.github/scripts/artifact_ci.py`
- `arbiterForge/codeArbiter@0539563484b2b487be77a3370d2952acb579fd2c:tools/build-artifacts.py`
- `arbiterForge/codeArbiter@0539563484b2b487be77a3370d2952acb579fd2c:core/pysrc/_artifactlib.py`
- `arbiterForge/codeArbiter@0539563484b2b487be77a3370d2952acb579fd2c:.github/scripts/test_suite_hermeticity.py`

The evidence JSON retains the original run IDs, artifact hashes, capacity calculations,
method limitations and official reference URLs. It is frozen historical input: add new
exact-head evidence separately rather than silently replacing its historical observations.
The assessment's earlier `05395634` main identity is not relabeled as the plan PR base.

**Next execution step:** CI20-01, followed by reviewed CI-only input and qualification
contracts; begin capacity discovery in parallel, but obtain separate approval before
external requests, account changes or spending. No implementation task is completed by
opening or merging this plan.
