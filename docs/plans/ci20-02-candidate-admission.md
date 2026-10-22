# CI20-02 — CI-only native test-input admission and qualification contract

**Status:** provisional producer/verifier and six-platform direct-test CI lane implemented; NOT an accepted ADR, installed-product feature, qualified release pipeline, or evidence that the twenty-minute goal is achieved.

**Owning source:** `arbiterForge/codeArbiter@0badb588dc1179b06e13db1ca5322590962b586a` (development baseline).
**Plan:** [CI under twenty minutes](https://github.com/arbiterForge/codeArbiter/pull/1011) in plan-only PR #1011.
**Current execution PR:** #1013 (single PR for incremental implementation).
**Historical comparison:** closed/unmerged #993 at `16983f5017b39e35de2f90994e30fcd60730e82c`. It is not a current implementation.

The objective is to allow certain **test harnesses** to start against exact native
binary bytes without claiming that the source has passed verification. The source
of truth for ordinary installed admission is `core/pysrc/_artifactlib.py`;
the separate native receipt issuer is `tools/build-artifacts.py`. Neither is
changed in this batch. The ordinary product must never acquire a permissive CI
environment switch.

## States and sole owners

| State | Producer and allowed consumers | What it establishes | What it cannot establish |
|---|---|---|---|
| **P — provisional CI test input** | Future CI job `artifact-ci-build` executes `.github/scripts/ci20_candidate.py build`; only `artifact-ci-direct-tests` may verify/directly exercise it | Native binary exists; repository, run, attempt, toolchain, module bytes, build flags and binary bytes are bound | Module tests, host admission, native qualification, installed capabilities, release packaging, publish eligibility, PASS |
| **V — independently verified native inputs** | **NOT YET IMPLEMENTED.** Required native configuration jobs will execute the complete tests/vet/coverage/context/race matrix; their exact artifact and source records must be checked by the strict join | Complete verified observations against the same bound executable cohort | Ordinary installed eligibility until the required aggregate is complete |
| **Q — qualified installation/package** | **EXISTING, UNCHANGED.** `artifact-engine` protects `tools/build-artifacts.py --qualify-existing`, after all named gates and actual native evidence | Eligible real native-tested installation manifest/receipt and exact installed-host packages | Automatic or self-issued qualification from P/V records alone |

There is **no implemented P → V or V → Q transition** in this slice. In
particular, `native_tested: true` is never written or inferred by the new
helper. Its provisional format has **no `release.json`**, no `native_tested`
field, and no `qualification` or `tests_passed` field. A direct producer
cannot invoke or be mistaken for the existing qualification job.

## Provisional producer format and protection

The helper produces `codearbiter.ci-test-input/1` with
`state: unqualified` and one binary; it never creates a release manifest.
The exact record binds:

- `GITHUB_REPOSITORY`, `GITHUB_ACTIONS`, `GITHUB_WORKFLOW_REF`, the checkout `HEAD`,
  `GITHUB_SHA`, run ID and positive run attempt;
- the currently pinned native `go1.27.1`, its executable SHA-256,
  `GOOS/GOARCH == GOHOSTOS/GOHOSTARCH`, `CGO_ENABLED=0`, and the bounded
  hash of **all** Go module bytes (including sources, tests and embedded inputs);
- the fixed offline `go build -trimpath -buildvcs=false -ldflags=-s -w`
  configuration, binary file name/size/SHA-256 and the exact supported OS/arch;
- explicit normal Go environment isolation: local toolchain, no workspace,
  no `GOFLAGS`, no network module proxy or checksum fetch.

Only `artifact-ci-build` may execute `build` under the intended GitHub
workflow; no other CI job can create a record through that CLI. Output must be
a **new** direct child of `RUNNER_TEMP`, and it is atomically named only
after a successful native compiler exit and complete record creation. The
consumer verifies only an exact two-file directory, with bounded, regular,
non-linked inputs, strict unique JSON keys, complete schema, identical run,
checkout/module/tool identity, and matching binary bytes. An earlier successful
producer attempt in the **same run** may be reused by a later consumer attempt,
but future attempt records, a new run or a changed source/tool/binary are
refused. All supported regular runner filesystems are subject to these checks.

This is a **fail-closed substitution/mistake detector, not a signed attestation**.
It does not establish a trustworthy GitHub check result on its own; the
workflow's trusted same-run transport and required-result registration must be
reviewed in CI20-03/04. Do not accept a user-controlled `passed: true` field as
native evidence, or upload/check out a provisional input from another run.

## Consumer classification at the frozen current source

| Existing suite / caller | Current behavior | Admission before full native tests? |
|---|---|---|
| Direct binary CLI/protocol harnesses and future direct tests | Can invoke exact binary bytes without an installed `ArtifactClient` | **Potentially yes** — only after conversion to the explicit `artifact-ci-direct-tests` owner and regression proof |
| `.github/scripts/test_artifact_bridge.py` | Real installed `ArtifactClient` checks `release.json` and `native_tested` | **No**, until independent purpose-built test admission is designed and reviewed |
| `.github/scripts/test_artifact_conformance.py` | Real installed protocol through `ArtifactClient` | **No**, retain after genuine qualification |
| `.github/scripts/test_artifact_authority_adapter.py` (`ClaudeEndToEndTest`) | Copies tested install and invokes installed host bridge | **No**, retain after genuine qualification |
| `.github/scripts/test_greenfield_context.py` | Builds/copies a qualified installation for installed writer | **No**, retain after qualification |
| `.github/scripts/test_artifact_package.py`, installed-host and cold-package suites | Assert ordinary install, package identities and host capabilities | **No**, retain after genuine qualification |
| `core/pysrc/_artifactlib.py`, shipped hook consumers | Strict ordinary installed admission | **Never** admit P; no shipped code or environment switch added |

The only allowlisted provisional consumer job identifier is
`artifact-ci-direct-tests`. Its direct capabilities smoke executes the verified
binary without the installed bridge. **No existing installed-host suite is
moved earlier in CI** and no speedup is claimed.

## Mandatory negative controls

`.github/scripts/test_ci20_candidate.py` exercises:

- native-only and exact-workflow producer/consumer role checks; wrong repository,
  source, run, attempt, Go target/tool/flags rejected;
- a real ordinary `ArtifactClient` refusing the provisional input, even when
  its JSON is copied into a fake `release.json`;
- the ordinary native receipt issuer refusing a provisional input, even under
  the previous authorized `artifact-engine` job identity;
- byte tampering, changed manifest, false `native_tested`, injected PASS fields,
  unexpected/missing/duplicate keys, non-finite JSON, file/directory/symlink
  substitutions, future attempt and output overwrite;
- failed compiler never publishing a partial candidate; earlier-attempt reuse
  remaining within the same run;
- no permissive CLI `qualify` or production-wide test-mode option.

These are **unit/contract tests**, not fake evidence for successful actual Go
verification. A separate actual local Go build smoke of the unqualified test
input is useful validation, but is not equivalent to a complete hosted matrix.

## Validated development evidence (not hosted qualification)

The local Windows x64 test-harness producer successfully compiled a
**6,118,400-byte** native binary with SHA-256
`c9246accfa753c0aad42df2d22b1652c5bf63bcf2325d8c59e3c08b571ad5aab`.
Its record had the provisional format/state, bound source/tool/module data and
**no** `release.json` or `native_tested` claim. The isolated CLI round-trip
also accepted only the designated direct consumer and rejected a different run;
the environment was deliberately simulated locally, **not** a hosted CI run.

Focused local checks passed: 19 candidate/negative-control tests, 108 CI impact
tests, 11 provenance checks, 15 coverage tests, 16 artifact-surface tests and
33 release-workflow tests. Actionlint passed the changed CI workflow with
external ShellCheck/Pyflakes disabled. Only the workflow's impact/artifact
selectors, its early admission test step, the impact map, this design and the
native-written tech-stack/security-controls evidence digests changed.
`tools/build-artifacts.py`, installed-client admission and native runtime
sources were not modified. The current main's full native CI matrix and
performance objective are **not** qualified by those local checks.

## Further work before changing the CI dependency graph

**CI20-03:** The six-platform direct-input producer and consumer are now
scheduled and required by the merge gate. Expand eligible direct test coverage
only after individual tests are classified. Leave all installed-host and
release-verification suites behind real qualification. Run native Go tests
and coverage independently; keep both Go compile settings and test-result
freshness. Design a candidate-byte correspondence proof—do not assume a
separately rebuilt binary is byte-identical without comparing actual hashes.
Keep all six native hosts and all required coverage.

**CI20-04:** Define actual verification observations and a final aggregator that
uses trusted job completion and exact candidate/source/platform identities, not
arbitrary self-declared JSON. The currently protected merge gate and
`artifact-engine` receipt semantics must be preserved or changed coherently,
including package readers, negative tests and rollback. Ordinary installed
admission must continue refusing provisional inputs.

**CI20-05:** Verify the actual organization's runner/concurrency limits; obtain
approval before external requests or paid capacity.

**CI20-07:** Only complete green hosted end-to-end runs, including queueing and
overlapping-run demand, can establish a measured under-twenty-minute result.
The prior 16m27s replay remains a **model**, not an implemented result.

## Propagation, approval and rollback

Affected in this slice: the separate CI-only helper, its negative tests, the
impact/test reachability wiring, this proposed contract and native source
provenance if `ci.yml` is modified. Product runtime, adapter admission, release
payload and exact package formats remain untouched.

This design does **not** approve an ADR, network/account changes, billing or
anything resembling a second permissions plane. The maintainer must approve any
future architecture change to the qualification issuer/receipt.

Rollback this new helper, its tests and routing/documentation together; retain
historical observations. No installed consumer migration is introduced by the
provisional test-input format.

## CI20-03 — First hosted integration batch (pending exact-head verification)

The workflow now schedules `artifact-ci-build` on all six native platforms,
uploads same-run unqualified binaries, and schedules `artifact-ci-direct-tests`
on the corresponding six hosts after the complete producer matrix succeeds.
The consumer verifies exact source/run/tool/byte identity and invokes the
native executable's read-only capabilities endpoint directly. Both job groups
are registered in the protected `ci-passed` dependency list **and** the
required-result expression. The new helper is also in the impact/artifact
filters and impact map.

This is an **integration/transport proof**, not yet the parallelization
of the expensive installed-host and module suites. The original
`artifact-engine`, native authority shards, coverage, qualification receipts,
package assembly, and cold-package tests remain unchanged and required.
This first integration can temporarily increase runner demand. Any timing
regression is measured rather than described as a speedup.

**Verification still required:** exact-head hosted checks for six producers,
six consumers, complete native suite, coverage, package gate and current
review. Failure of any producer/consumer must fail the protected aggregate.
The next optimization slice should overlap actual eligible direct work with
independent native verification, while retaining byte correspondence and
strict qualification.

## CI20-04 exact-byte correspondence (implementation batch)

The package assembly job now waits for both six-platform provisional producer and direct-test groups, downloads same-run unqualified binaries, and refuses packaging unless the six provisional binary bytes exactly match the six existing native-tested candidate bytes. The read-only CI20 correspondence checker requires exact source, run, workflow, platform, build flags, module/tool identities, release manifests, native-tested receipts, and context observations; it explicitly records that this check is not qualification. Existing artifact-engine qualification and the full release package/cold-test gates remain authoritative. Eleven correspondence negative controls and 108 impact tests passed locally. A replay using all twelve actual hosted archives from run 39542204174 passed six-of-six byte correspondence; the GitHub Actions checkout source was the PR merge commit 20fa81a5, not the PR branch head. This is exact-byte evidence, not a completed successful CI run or a demonstrated under-20-minute latency.
