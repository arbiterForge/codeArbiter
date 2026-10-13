# Brownfield implementation evidence

## T-003 path actions and source baseline

The approved T-003 record marks these paths as `create` and cites `PLAN-BASE`,
the inspected source at [4187f1e22dc7da3cf755a2654bbf7ec268236126](https://github.com/arbiterForge/codeArbiter/tree/4187f1e22dc7da3cf755a2654bbf7ec268236126):

- `.github/fixtures/context-onboarding/observation.schema.json`
- `.github/scripts/test_context_evaluation.py`

The 2026-10-02 Git inspection found neither path in that baseline tree.
The working-tree comparison against the same commit reports `A` for both paths,
with `create mode 100644` for each. Both files exist at the inspected campaign
HEAD `ffc6cfb90dbfc2da76945a704f1daa1899df1ab1`. The creation delta is measured
from the declared baseline; the later checkout contains the implementation.
T-003's approved final step expressly calls for rerunning and reviewing the
existing PR #873 tests against the integrated execution root.

These results can be checked with `git ls-tree --name-only <baseline> -- <paths>`
and `git diff --name-status <baseline> -- <paths>`, using the commit and paths
above. The inspection's native source snapshot was
`f2ef4d3f5878787797be720093c1ac06743387accf9e23b7689d99dc33bb91f3`.
It is a dated inspection reference; the installed engine supplies the source
snapshot for each later verification or review.

This note records the existing baseline and expected additions. The approved
path actions and rollback obligation remain in the canonical plan. Native
review request `e97ed3782459b0553170db7d9b3c051ab7663f8ad1f4f53fcb06b54f81ff521a`
remains rejected with `TASK_PATH_ACTION_MISMATCH`; the note is corrective
provenance, and a fresh passing native review remains required.

## How to read this historical record

Interpretation clarified on 2026-10-02. The source inspections and execution
records below are preserved verbatim. Each commit, PR status, package identity,
plan revision, model hash, context ticket, task state and test result belongs to
its recorded checkpoint. Within those records, words such as "current" refer to
that checkpoint, not the latest checkout or native workflow state. In particular,
the revision-7 and revision-15 bindings below are historical captures.

Read the canonical [specification](https://github.com/arbiterForge/codeArbiter/blob/ffc6cfb90dbfc2da76945a704f1daa1899df1ab1/.codearbiter/specs/exercise-ready-brownfield.html)
and [plan](https://github.com/arbiterForge/codeArbiter/blob/ffc6cfb90dbfc2da76945a704f1daa1899df1ab1/.codearbiter/plans/exercise-ready-brownfield.html) through the selected
installed engine for current identities, approved gates, source snapshot and task
eligibility. Obtain a new complete context for each dispatch and use only evidence
that the engine validates for that operation. Normal task transitions change the
plan revision and model hash without rewriting these earlier records. No printed
revision or context ticket in this history is a reusable current binding.

The original evidence and its authority limits follow unchanged. The native
artifacts remain the only requirements, task-state and acceptance owners.

This record contains source inspection and ordinary execution evidence. The
canonical specification and plan own requirements, task state and acceptance.
No result below grants trial, install, merge, publication or completed-plan
commit authority.

## T-001 obligation mapping

The author read all eight contextual pages (88 records) for
`PLAN-EXERCISE-BROWNFIELD#T-001`, revision 7, model SHA-256
`dae081725e77ed1a1315bf11bd253fe458a914534ad65845dc2d1331e4a5d98c`.
The final engine context ticket was
`62e529b82e53c4a994a138e7e9907591cb4e83076f43f83868d8b25df3a97fb8`.
The selected installed engine reported verified specification and plan authority
and an `approved_source` binding to specification normative SHA-256
`addf0bf9bea697f1edd485e56d41b29810ced5d374d59ccf6d60197f9bda0d7a`.

| Criterion | T-001 proof obligation and mapped control |
| --- | --- |
| `SPEC-EXERCISE-BROWNFIELD#AC-030` | Preserve existing source ownership, test bodies, docstrings, CLI selectors, and errors. Inspect the complete prerequisite diff; run the original fixture suite and `test_named_output_preserves_real_docstring_case_execution`. |
| `SPEC-EXERCISE-BROWNFIELD#AC-032` | Distinguish ordinary success from named collection and native acceptance. Retain the existing docstring-output rejection; run `test_named_output_keeps_failure_error_and_skip_outcomes` and `test_named_output_rejects_missing_duplicate_and_zero_selected_results` against actual runner output and result objects. |
| `SPEC-EXERCISE-BROWNFIELD#AC-039` | Record the current bounded preparation profile and pending live cells; preserve the all-live-task commit rule and unselected P1 state. Review this evidence against the actual source and workflow identities. |

These are mappings of the three approved criterion references, not additional
criteria or a second task-state ledger. The three named compatibility tests
precede the local fixture-class adaptation. Native verification and independent
review remain the orchestrator's separate evidence boundary.

## Source reconciliation before the native-v1 exercise

GitHub and local Git were checked again on 2026-09-26 after the native review
repair and its trusted-base prerequisite. The four campaign/prerequisite PRs
remain open. The current comparison main is
`1501cc4ef6ba6a5187db0ded486445af2cae3283`, which includes merged #884.
Its post-merge CI run 36275242710 and normal release-workflow run 36276272106
completed successfully. These runs do not qualify #854's newer package.

#854 is at `00f2598e60446f015506530a3396c87728d2eada`. Its current hosted
run is 36275349074; package and native-review qualification remain pending at
this inspection. The six native statement profiles from that run match Go
source identity `0ae1a1e41c5cb857e99994bb99b4dc2bcec3221345a9b1f399141837bb162fb4`
and summarize to 4458/5518 statements (80.7901%), with every platform and
executable integration profile present. This satisfies the approved stage-2
statement floor without claiming Go line or branch coverage or completed CI.

#873's published head remains `4e2a02f19f2ec23c0b50c221a24cf518fec9f573`,
stacked on #854. Its clean local integration is
`4896472b1b854cc6650e614bf6fca2ef9c0806c4`, retaining the reviewed brownfield
helpers alongside current #854. That local integration is not yet pushed.
#871 remains `0759ca2bf3d6740141fa3b0e0bf219232633fbb5`; #872 and this
execution checkout remain `08a0e1f484d096ca158ecd0fa2ef6903ed8bdf8a` plus
the bounded working-tree changes described below. No complete sibling branch
was imported into this execution checkout.

The context-check skill, its compatibility command, the status command, and
the debug skill are byte-identical between the earlier #854 source below and
current #854. Those four paths are also unchanged between the earlier main
and current main. Their previously inspected ownership consequences still
hold. The source/output adaptation and its exact allowed paths are unchanged.
A fresh installed-engine identity and approval read still validates spec
revision 8 and plan revision 7 at the hashes above. This factual refresh does
not change their definitions, accept T-001, or qualify any future live cell.

## Source and owner inspection before the transport repair

GitHub and local Git were read on 2026-09-26. All four PRs remained open.

| Source | Observed full commit | Ownership consequence |
| --- | --- | --- |
| Main | `a5a3d79cb5633cae3982552d6a7cf724de83aa49` | Current comparison base; historical campaign source references remain historical. |
| #854 | `721e59929e93939108e758db6900fb8862499757` | `core/surface/skills/context-check/SKILL.md` owns the audit; the compatibility command is `{{SKILL_ENTRY:context-check}}`, and `status drift` targets the skill directly. Preserve this composition before any later overlapping runtime work. |
| #871 | `0759ca2bf3d6740141fa3b0e0bf219232633fbb5` | Its current diff contains the native debug pair and `docs/proposals/debug-correctness/` evidence. Debug diagnosis and regression handoff remain independently owned. |
| #872 / execution HEAD | `08a0e1f484d096ca158ecd0fa2ef6903ed8bdf8a` | Planning checkout `codex/pr872-stack-completion`; genuine approved artifacts and the in-progress implementation are dirty working-tree state. |
| #873 | `4e2a02f19f2ec23c0b50c221a24cf518fec9f573` | Stacked on #854 at `721e59929e93939108e758db6900fb8862499757`; partial source units exist, but are not native acceptance. |

The complete #854 context-check/status diff was inspected. T-001 neither imports
those runtime owners nor changes them. #873 additionally owns report, observation,
intent and provenance changes; none is required by the fixture runner and none
is imported as a T-001 prerequisite.

#854 also composes `core/surface/commands/debug.md` through
`{{SKILL_ENTRY:debug}}` and retains the diagnosis-only entry boundaries in its
owning skill. That skill's blob is
`9ccacb1c8499690645661e1f8599091aacea80e4`; current main and #871 still carry
`0e0995202a00c7e11751b3e7c159de0205a90391`. The #871 handoff contract separates
diagnostic evidence, reported intent and regression reuse from actual repair
authority. Future context/fix delivery must reconcile both owners; this fixture
integration changes neither and does not treat #871's design as shipped runtime.

## Bounded prerequisite integration

The parent integrated only this existing #873 fixture closure into the execution
checkout, preserving the prior fixture source before output adaptation:

- `.github/scripts/test_context_fixtures.py`
- `.github/scripts/_context_fixturelib.py`
- `.github/fixtures/context-onboarding/cases.json`
- `.github/workflows/ci.yml`: the fixture push-path entry, hooks filter and one
  fixture runner step.
- `.github/scripts/test_hook_ci_partition.py`: the exact resulting reviewed
  command inventory, preserving every prior command and order.

The fixture library imports only the standard library. The suite reads its
catalog and this checkout's workflow and imports the existing CI guard functions.
It does not point `ROOT` into the sibling checkout. The source's whole workflow
was not copied: its report and evaluation runners would require other task units.

Before wiring, the original integrated 20-test suite exited 1 with three failures
and one error for the missing filter/runner. After the bounded wiring, all 20
tests passed. The inventory retained 59 existing commands and added one fixture
command: 60 commands, contracts 58, digest
`e90e50d6ec3437a0783ea89a09598615e7d0cd1b31b945284eaec5b2acd3322f`.
The guard's 18 mutation tests and actual workflow inventory passed. These are
prerequisite source-integration facts, not accepted T-002 or T-043 outcomes.

After the compatibility controls passed, the parent registered
`python .github/scripts/test_context_named_output.py` immediately after the
fixture runner under the same mandatory hooks/contracts predicate. This final
inventory preserves all original 59 commands in order and adds exactly two:
61 commands, contracts 59, functional 1, isolation 1, guard 1, setup 2. Its
digest is `49d1041b41de8bfd408f6e66a6a373e322cb3a4611d10db257487388a824452c`.
Fresh guard tests (18) and compatibility tests (3) passed with that inventory.
The full 20-test fixture discovery also passed again against the final inventory,
with all five required names collected once by the selected installed collector.
The final registration keeps the new regression active in hosted CI; it is
not an import of #873's other runners.

## Installed transport qualification before native review

The complete #854 CI run 36275349074 passed at head
`00f2598e60446f015506530a3396c87728d2eada`. Its package source is the
tested merge `2e51a5a71d0adf2c48e2fe38b17b37e4a4886dd7`, tree
`8ec980e1868f86f18479c1ddb2a13233d1820fec`. Downloaded artifact ZIP
digests and the complete package cohort were verified before a real Codex
marketplace installation into a new isolated home. The cohort SHA-256 is
`f489bab2a4abde210a0f9bc736e7ef176bc1d29abb947d94d3b4f8fafcce6ccd`;
the Codex archive SHA-256 is
`69cb4fcc9860646497f76a3c2923295f6ec284fb8a80837c4fea2a2f591cbd22`.
All 237 installed ca-codex 0.14.3 package files match their declared bytes.
The existing qualified 0.13.11 installation was not changed.

A fresh Codex CLI 0.145.0 process using gpt-5.6-sol at low effort reported the
actual codex/arbiter/stage-2 startup and a doctor result of 14 OK, zero warnings
and zero failures. The prescribed staging dry-run was denied by H-03 before
execution. Its index and source stayed unchanged apart from the retained
automatic audit append and read-lock metadata. Doctor event SHA-256:
`a5b1286c599ddb56d5d46a918aabeba4cf9e2e9eb36cf99d935f7e3a23a445ff`.

A separate fresh process using gpt-5.6-luna at high effort, with the native-v2
feature disabled and the catalog advertising v1, executed one real child
launch and wait. The native event stream records child UUID
`01a0dfe4-0d05-7322-8f72-1191c5b6632d` completing with the exact harmless
probe response. No shell command, artifact operation or task transition ran
in that probe. Event SHA-256:
`518d78125dad63e453a5e7f4dc43949f3228996c62d9571afe3e386d1e00b701`.
The event projection proves the actual launch, UUID and response; it does not
independently attest every launch argument. Request-bound native verification
and review must establish their own complete authority evidence.

These are bounded compatibility checks for the authorized transport repair,
not an E0 provider experiment or proof of useful contribution. The next
coordinator uses this exact installed package and runtime for only T-001's
declared local verification and one native-v1 spec review. It must use the
supported terminal recovery for the obsolete unlaunched v2 request, preserve
all historical evidence, and stop at REVIEW. No source editing, scope
acceptance, next-task start, publication or consumer deployment is included.

## Source-preparation execution profile and pending qualification

The earlier source/output preparation used Windows AMD64, PowerShell
7.6.5, CPython 3.14.6, and Git for Windows 2.55.0.windows.3 in one linked worktree.
The selected installed authoring package is qualified `ca-codex` 0.13.11.
Its verified Windows AMD64 engine is version 0.1.0, protocol
`codearbiter.artifact-api/0.1.0`, schema 0.3.1, SHA-256
`d4bd06cd3460e0817a15b90f8d9979bbd682e801eba22ac92f59a6ac5be11162`.
A fresh installed `capabilities` call reported repository operations and host
default authoring enabled, with runtime downloads disabled. The release manifest
and observed binary hash agree; this is the authoring cell actually used here.
The plan's E0-E2 direction remains map-first; this run qualifies only the bounded
source/output behavior assigned to T-001. P1 remains unselected and default off.

Actual provider/model/settings, live contribution usefulness, cross-host loading,
consumer writes, cold installation, Go/cold-install verification bridges and
future context-kind qualification remain pending in their owning tasks. No
provider trial, spending, package installation or consumer deployment was run
during that source/output preparation. The subsequent bounded transport
qualification is recorded separately above.
The existing `all_accepted_and_current` rule still requires every live selected
plan task to be accepted/current before completed-plan commit.

## Historical local verification of the named-output adaptation

Both declared commands ran from the actual execution checkout using CPython
3.14.6. The source-tree regression module uses only stdlib and the repository's
unchanged named collector. A separate ordinary check passed the complete real
stdout/stderr bytes to the selected installed 0.13.11 collector. No installed
collector, runtime, authority source or native task state was modified.

```text
python -m unittest discover -s .github/scripts -p test_context_fixtures.py -v
python -m unittest discover -s .github/scripts -p test_context_named_output.py -v
```

| Run | Real unittest outcome | Selected installed collector |
| --- | --- | --- |
| Original integrated fixture suite, before output adaptation | 20 tests, exit 0 | `MISSING_TEST_RESULT` for the first required campaign method because its docstring occupies the result line. |
| New compatibility regressions, before output adaptation | 3 tests, exit 1; six subtest errors | Each required method failed at `MISSING_TEST_RESULT` for the real passing nested case, once per participating class; no import/setup failure. |
| Same regressions after adaptation | 3 tests, exit 0 | All three required names collected exactly once. |
| Full fixture suite after adaptation | 20 tests, exit 0 | All five required campaign names collected exactly once. |

The original named-output adaptation added local `shortDescription()` methods
returning `None` in `TestCampaignSelection` and `TestFixtureInventory`. That
historical step changed no test body, assertion, docstring, selector or
result-handling path. Reconstructing it from the merged #873 source reproduces
the recorded SHA-256 values: before
`a4c3338a1953fbba19e97ecd766405acd7c14ab9741e9c0b540bf06d2d692b40`;
after `b5594f5df404b194444bddc64c29c59663ff610bdd3d2eac9d309e58d6801ee1`.
Those values identify the earlier adaptation, before the subsequent fixture
inventory, placement-boundary and successful-fix controls were integrated.
The named-output regression module remains identical to its red and green
source: `29a9356c09ab17e54407fadc5db0f5f5117d0a31fc9b12de19bb386683ee1778`.

The integrated `.github/scripts/test_context_fixtures.py` inspected on
2026-10-01 has SHA-256
`1633a8cbfb4090a5ef8cee94cd8d9bcf4710895eb5ec0140923e183e04c9d7f4`.
It includes the later `TestSolvableFixFixture` control, its own
`shortDescription()` adapter, and the `Path(temp).resolve() / 'case'` argument
used to materialize that control in an absolute temporary directory. These
later additions include test-body changes; the earlier unchanged-body statement
applies only to the original two-adapter step. The original dirty-recipe test
already used `parent = Path(temp).resolve()` in #873. Historical run captures
below retain their original source bindings and do not qualify later bytes.
Fresh installed verification and native review must bind the integrated input
before task acceptance.

The controls retain each full raw stream and actual `TextTestResult` object
while checking execution, setup/teardown events and outcomes. A separate
capture retained all 12 nested runner transcripts, 21 executed inner cases,
their unmodified docstrings and actual failure/error/skip counts. Plain
docstring-bearing cases establish rejection; adapted cases establish success.
Real assertion failures, runtime errors and skips remain nonpassing. Repeated
real cases produce `DUPLICATE_TEST_RESULT`; absent names and an empty successful
suite produce `MISSING_TEST_RESULT`. These same raw transcripts also passed
the expected positive/negative checks with the selected installed collector.

Direct CLI selection of the two participating classes ran seven tests and
exited 0. The unknown selector still exits 2 with `unknown test selector`.
Selecting the same class twice preserves the original CLI behavior (ten tests,
exit 0), while named collection rejects the duplicate results. Successful
process exit alone is not treated as qualification.

Complete ordinary outputs and result metadata remain in the task's local
scratch capture, without personal absolute paths in this document. These
filenames identify ordinary evidence, not workflow receipts:

| Capture | SHA-256 of complete raw stderr or transcript |
| --- | --- |
| `brownfield-t001-fixtures-before-output-adapter.stderr` | `4a4edbc59fb9ebc464e2a2761186f2eaab9d23e46ac77f4caf3394bbc07c9054` |
| `brownfield-t001-named-output-red.stderr` | `b6304b95dd15d0fa5f269fe53e6413f17b94eda6ded2f0e3c4be4f0be9dc0990` |
| `brownfield-t001-named-output-green.stderr` | `be4bd26d6d731aec409fe8ed3d368ad7092237507869665fcc3024338cabd215` |
| `brownfield-t001-fixtures-after-output-adapter.stderr` | `0e82e95d4914c07652e54262705daa4e0b0738bea2c0f8bc735e95a8e68abf03` |
| `brownfield-t001-final-integrated-fixtures.stderr` | `75bd0907cd248f5d13949166bfef4eda5c1ddf10677f520f216b746deb085975` |
| `brownfield-t001-nested-outcome-transcripts.json` | `e1a70345680f79a1f665a0fb1d0fd7c75657982046b0abce5c26c8496b773ad5` |

The installed collector source SHA-256 was
`83a82b71d73bff8052536a3c5b5499904b9632fc3dc822f554111a099f69f2f4`.
All standard discovery captures had empty stdout; real unittest output
was retained on stderr. The reported durations are run observations and are
not performance thresholds.

`python -m py_compile .github/scripts/test_context_fixtures.py
.github/scripts/test_context_named_output.py` passed. No TypeScript surface
changed. For TDD phase 5, `.codearbiter/tech-stack.md` explicitly states:
"There is **no coverage tooling for the Python hooks** (`plugins/*/hooks/*.py`,
`.github/scripts/*.py`). No numeric floor exists for those surfaces"; the
documented no-tooling exemption applies, with the behavioral obligations above
checked directly. Native verification and independent review remain pending;
these local runs do not change task acceptance or authorize staging/commit.

## CP-01 source implementation — 2026-09-27

The user directed continued implementation without repeating reviews of unchanged
prerequisites. The recorded `T-VERIFY-HARNESS-PREAUTHOR`,
`CP-01-IMPLEMENTATION-PREAUTHOR` and `CP-02-IMPLEMENTATION-PREAUTHOR` overrides
permit source progress while preserving actual native task states and failed
review history. They supply no task acceptance, policy approval, installed
capability, live-trial result or hosted-CI result.

The test-owned verification bridge executes the finite named Go cases, retains
bounded raw outcomes and binds the actual executable and whole module before
and after execution. Its eight tests include a failing sibling selector, real
source drift and a multi-package invocation. The latter exposed and corrected
an overly broad rejection of package-level Go skips for packages without tests;
skipped named tests and a skipped selected package still reject. The candidate
installed-invocation builder remains a
preflight helper; no installed exercise is claimed.

The CP-01 libraries now provide the reused closed report decoder, inert bounded
raw SHA-256 reads, finite filesystem membership, source/target/effect snapshots,
conservative provenance v2 dual reading, and command/constraint record codecs.
Semantic approval remains separate from identity matching. Unsupported existing
provenance bytes survive both the v2 and legacy write routes.

Parent verification on the corrected source passed all 43 report/snapshot tests
and all 127 provenance tests. The single combined coverage/security review found
concrete defects in byte-drift detection, directory membership composition,
command input binding and legacy record preservation; retained failing controls
were corrected and the final tests passed. Command state now binds literal argv,
cwd and declared prerequisites separately from external environment/runtime
identities. A literal executable path containing spaces remains one argument.
Four old stub-test fixtures now remove only their own empty temporary placeholder
before testing absent-file creation; every existing assertion is retained.

| Final source | SHA-256, identical in canonical and three generated copies |
| --- | --- |
| `_contextsnapshotlib.py` | `9505377a2495a858b7d6b7625f1d7ba67b435c79e7c5cc200e9a216f414aeb11` |
| `_contextreportlib.py` | `ba83e7112c22d723413fb92c7e1bf54b7062a5ad4b3ebffa309d7d563dccc2ed` |
| `_provenancelib.py` | `e3c2d8a413e35bcd36031be2837ccf989a7bcb4d49d964c13bf6f3f8e8ec2bf2` |

These results establish the bounded source contracts. The native document
implementation, workflow integration, package qualification, useful live
exercise and exact-head hosted checks remain later delivery obligations.

## Native representation boundary — T-011

The native catalog now selects a closed codec by registered kind, isolates
inactive optional-kind parsing, and rejects unavailable representations. The
only registered kinds remain spec and plan; no context writer is enrolled.
Global transaction recovery still precedes catalog access.

The parent ran the declared Python wrapper, which executed the actual anchored
`TestContextRepresentationBoundary` Go selector and observed all four subcases:
HTML identity, unknown representation rejection, inactive optional-content
isolation with strict active parsing, and legacy format collision rejection.
The wrapper passed once. A scratch mutation that skipped active optional kinds
failed the corresponding behavior assertion. The initial pre-change Go compile
failure demonstrated the missing API, not a behavioral assertion failure.

Affected Go packages and vet passed. Package-local statement samples are not
the required whole-module integration report or six-platform hosted union;
that coverage remains a delivery requirement under the merged language-specific
policy. These source results do not alter the native plan state.

## Typed context, Markdown parsing and preview — T-012 through T-014

The native context contract now validates the five closed document types and
finite identity, fact, command, relationship, map and constraint-reference
entries. Raw caller input cannot supply arbitrary Markdown, unknown sections or
new normative rules. Historical command results retain their complete input
binding and do not become current authority by being stored.

The parser recognizes bounded legacy fields and generated field markers while
preserving unrelated bytes and line endings. Markers describe syntax only.
Preview rendering reparses the full source, selects structural anchors and
returns exact old/new spans without writing. Missing-file creation remains
distinct from an existing empty file. Code maps render a readable concern,
repository path and role index bounded to 50 entries and 20 KiB.

The parent ran the declared real-Go bridges after integration: six typed-contract
subcases, 19 parser subcases and seven renderer subcases passed. Concrete failing
controls led to fixes for long Markdown fences, mixed legacy/managed duplicate
identity fields, unreadable generated maps and silently discarded duplicate
identity inputs. Independent fact claims remain allowed. Existing human text,
line endings and fixed field prefixes survive supported updates.

These are source and preview results. No field adoption, live file write,
native task acceptance or installed capability is established by a preview;
the following mutation and authority tasks own that boundary.

## Native mutation, authority and disabled enrollment — T-015 through T-018

The native writer applies a document and its v2 provenance together under the
existing repository lock and transaction journal. Create, adopt and update bind
the exact document and provenance preimages. A committed retry with the same
operation identity and preview binding returns the durable historical result
without overwriting later human edits; conflicting input under that identity
rejects. Unsupported provenance survives unchanged. Content and directory
membership evidence are recomputed from bounded real reads. The current
membership implementation explicitly refuses non-ASCII paths rather than
guessing an incompatible Unicode normalization policy.

Recovery controls exercise complete and rollback recovery at eight transaction
fault points, lost responses, duplicate operation identities, human edits,
pending conflicts, aliases and unsupported journals. A reproduced Windows case
collision could previously fail after the first write. Case-equivalent targets
now reject before staging or journal creation, and journal validation checks
the same condition.

The production authority path creates a native context preview, obtains the
separate host-observed context approval and reconstructs the approved mutation
from that receipt before applying it. Caller labels, generated markers and
generic spec/plan approvals do not authorize context writes. Exact-source drift
refuses before mutation. The context kind is registered but remains disabled in
installed workflow capabilities pending qualification. Generic HTML routes
remain limited to their supported kinds. The existing six package qualification
suite labels are unchanged; fixture outcomes do not become package claims.

Main commit `8e88bce938ebf7dc8cfd934307b8d6859092d86e` was integrated into the
working source with author changes preserved and overlapping tests combined.
The integration is not yet committed. A final 51-path source manifest and one
combined source audit were retained as
`brownfield-cp02-integrated-source-freeze-final.json` and
`brownfield-cp02-final-source-audit.md`. The audit found no remaining source
findings. Its result applies to those frozen bytes, not to later source edits
or future installed qualification.

Fresh parent checks on that integrated source passed:

| Check | Observed result |
| --- | --- |
| Whole native module | `go test ./... -count=1` and `go vet ./...` passed |
| Context native bridge | All six declared tests passed, observing the real named Go cases |
| Existing native recovery bridge | All 16 required named outcomes passed |
| Authority adapter | 159 tests passed, with one expected POSIX-only Windows skip |
| Package suite | 38 tests passed, with one expected Unix-descriptor Windows skip |
| CI hook partition | 18 tests passed; 63 command registrations retained |
| Provenance | 142 tests passed after combining main and author coverage |
| Context contracts | 43 tests passed |
| Intent library | 40 tests passed |
| Instrumented CLI integration | Five tests passed and emitted actual coverage |

The first native bridge run exposed one stale wrapper selector after the
enrollment test was renamed to `canonical_schema_and_disabled_kind`. The
wrapper was corrected to the actual Go subcase and the complete six-test run
passed. The initial failure remains in the local evidence.

The Windows/amd64 statement measurement, including the real CLI integration
profile, covered 4,373 of 6,557 statements (66.6921%) for source digest
`92b6e873d73af5d5606ce6728456d6da8a6fcbe47773558326629e2d378a3390`
using Go 1.27.1. This is a single-platform diagnostic, not the required
six-platform result. Existing engine, migration, sprint-authority and several
regression suites carry Linux build constraints and do not run in this local
measurement. No coverage threshold, source denominator or platform requirement
was changed in response. The current source still requires the complete
GitHub-hosted platform union and its 70% statement floor. The successful older
PR #886 union does not qualify these newer bytes.

Native task acceptance, actual read-only host containment, installed package
qualification, a useful authorized live exercise and current-head hosted CI
remain separate delivery obligations. No unchanged native review was retried.

## Initialization reads and passive inspection — T-019 and T-020

Initialization readers now share one body-marker parser. A marker embedded in
frontmatter, a fenced example or another comment does not initialize the
project. Startup, status, initializer and doctor use the same result and retain
malformed-state diagnostics. Doctor was included as a necessary adjacent
consumer after the reader inventory found its old literal-marker check.

The initializer has an explicit `--check --passive --root PATH` route intended
for a trusted external process before host activation. It reads the bounded
context state and reports the known activation effects with capability and
authorization still unverified. It does not invoke Git, install hooks, alter
exclusions, fetch, refresh updates or send source to a model. Active startup
behavior remains available. A skill invoked after SessionStart cannot undo
effects that already happened; the command documents that boundary.

The parent freshly executed all four named T-019/T-020 controls after the final
passive-inventory refinement; all passed. Existing author runs also passed the
affected initializer, startup, hook, doctor and activation suites. Generated
Python and command surfaces were regenerated from their canonical owners.

## Context scout profile source preparation — T-024

The context workflow now distinguishes the shared Bash-enabled scout from an
actually restricted context scout. Existing decision-variance behavior is
preserved. The generated workflow refuses context dispatch when the host does
not expose an enforced restriction and observed read, report and denied-write
behavior. No unused host descriptor flag or synthetic receipt validator was
added.

The parent ran both named source-contract tests and observed two passes.
Generated surface checks, descriptor tests and the applicable build tests
passed in the author run. These checks establish instructions and generated
closure only. The current collaboration API cannot configure read-only child
permissions, so no unrestricted child was presented as an isolation test.
T-024's live containment and report-delivery obligations remain unqualified;
its native task remains unaccepted. A later real supported profile must close
that gap before the context scout workflow can be shipped as available.

## Initializer writer bridge and durable protection — T-021

The initializer accepts a closed internal request naming either one finite
context preview or one receipt-only apply. It validates the request and checks
the shipped writer before calling the existing authority/native routes.
Caller approval flags, arbitrary content and unrelated targets reject before
content effects. The original scaffold, passive inspection and repair routes
remain available.

Context protection is resolved only for a relevant context path. Hook imports
do not launch the native engine. A committed native document/provenance
transaction retains protection if the installed writer later fails. Empty
journal directories and validated unrelated historical transactions do not
enroll context accidentally. Ambiguous evidence preserves protection while
leaving unrelated ordinary paths alone. The existing shell guard needed a
small adjacent change because its static registry snapshot would otherwise
miss these lazy policies.

Tests reproduced and corrected import-time probing, missing shell protection,
an unsupported bridge import and mistaken enrollment from unrelated historical
journals. The parent reran both named writer controls after those corrections;
both passed. The complete workflow suite had also passed all eight T-019,
T-020, T-021 and T-025 controls at that integration point. Author checks passed
407 guard assertions and the affected protection, initializer and bridge
suites; canonical/generated copies matched at handoff. Later finalization work
legitimately changes shared bridge files and requires its own integrated check.

Positive writer tests use explicit fixture clients. Installed context mutation
remains unavailable until actual package and host qualification; none of these
tests supplies user approval or native task acceptance.

## Bounded report admission and joins — T-025

The existing report codec now admits attempts against one retained run ledger
and joins complete leaf reports. Full onboarding requires six logical domains;
a scoped refresh reports only its affected coverage. Failed transports remain
failures, while complete reports with uncertain findings retain explicit gaps.
Subdivision retains parent identities and coverage, and does not reset the
24-attempt ceiling, depth-three/fanout-four limits, one retry or run deadline.
Missing budgets, unexplained overlap and contradictory observations refuse
synthesis without dropping reports.

Boundary tests exposed two older decoder inconsistencies with the campaign's
initial parameters. The per-report bound is now 64 KiB, independently of the
48 KiB normalized join bound. Evidence is limited to 128 entries across the
whole report, including multiple categories; the old per-category 64-entry
check was not an aggregate ceiling. The separate command/constraint reference
limit remains 64. Controls admit a valid report between 48 and 64 KiB while
rejecting its oversized join, admit 65 evidence entries in one category and
128 across categories, and reject 129 aggregate entries.

The parent reran both named join controls after the corrections; both passed.
The author reran all 43 report contracts successfully. Canonical codec and its
three generated copies share SHA-256
`944eca80c2dee480846612a47d32c463bc1fe1ddc9b6d8dd21406f7a54eb785d`.
The complete workflow and generated checks will run again when concurrent
finalization/synthesis edits settle. These pure helpers do not perform host
dispatch or establish containment, spending authority or live qualification.

## Evidence-led synthesis and relevant questions — T-026

The synthesis workflow now distinguishes observed facts, inferences, proposals
and approved decisions. It preserves effective local instructions and source
citations, retains conflicting observations for targeted reinspection, and asks
only for missing decisions the user owns. A repository with evidence of no
storage does not trigger an unrelated database interview. Scoped absence
remains scoped, declared commands do not become claimed successful runs, and
observations do not create tasks or architectural decisions by themselves.

The author observed the two new instruction-contract controls fail before the
source changes, then pass with the existing workflow controls. The parent
subsequently ran all 12 workflow tests successfully, including both named
T-026 controls. Generated surface checks and the affected author-side suites
passed. These checks establish the instruction contracts and generated copies;
they do not establish live model compliance. The complete task context was
read in four pages containing 125 records. Native task eligibility and
acceptance remain separate from this source evidence.

## Finalization and current authority integration — T-022

Initialization now has a separate, bounded preview that binds all thirteen
required document, provenance, task-board, question-board and audit identities.
Its approved receipt authorizes only that finalization. Apply reconstructs the
approved request, validates current evidence, and commits the initialization
marker and the matching CONTEXT provenance digest together. Independently
owned outputs are checked and preserved, including valid empty boards and
historical task/audit formats. An old content approval cannot authorize this
new mutation.

An injected edit after validation demonstrated why the transaction must retain
the validated preimage. The corrected operation refuses the conflict and
preserves the human edit. The parent ran the two native finalization controls
and the receipt-only operation test successfully after this correction. The
author also ran the complete Go suite successfully. The Python bridge's Go
wrapper now requires the exact named passing test, so selecting zero Go tests
cannot count as successful verification.

The parent reran the full authority-adapter suite against the integrated
Python bridge: 159 tests completed successfully with one expected POSIX-only
skip on Windows. This confirms the new bridge retains the existing authority
contracts. Installed repository-context mutation is still disabled pending
actual package qualification; these results are not a production approval or
native campaign acceptance.

## Interrupted scaffold recovery — T-023

The initializer inventories surviving state before recovering an incomplete
scaffold. It creates only absent files with exclusive creation and preserves
all existing regular-file bytes. An initialized or malformed context,
conflicting requested stage, unknown surviving history format, unsafe path, or
missing CONTEXT amid other project state stops the write for inspection. Stage
examples in the document body do not change frontmatter validation.

Recovery tests cover every scaffold prefix, an injected failure after a file
creation, retained human task/audit bytes, and ambiguous provenance-only state.
Real native recovery cases cover a lost response followed by replay and a
divergent human edit with its pending transaction preserved. The parent ran
the complete workflow suite after the final corrections: all 14 tests passed,
including both exact T-023 methods. The existing 17-test initializer suite and
canonical/generated parity checks passed in the author run.

Scaffold recovery never repeats a content or finalization write. Those cases
remain with the native journal, exact receipt and recovery operation; the
workflow now states how to inspect that prior outcome before continuing.

## Initialized refresh and human preservation — T-027/T-028

The existing status/context-check route now supports an explicitly selected
scoped or full refresh after initialization. It preserves the initialized
marker and independently owned task, question and audit history. Unsupported
human Markdown remains available for safe advisory reads; replacing normative
content requires its actual owner and approval. There is no raw-write fallback.

A production-path regression exposed rejection of a legitimate provenance
refresh when the rendered document text did not change. The native preview now
accepts changed, validated provenance for a selected owned field. A new receipt
is still required. Missing selections, timestamp-only changes, true no-ops,
changes to unselected claims, stale sources/preimages and reuse of an earlier
approval refuse. The operation test exercises preview, fixture-observed
receipt capture, receipt-only apply and replay, while checking byte-identical
human document and history. Fixture authority is not a live host approval.

A separate Windows regression demonstrated that a directory junction at
`.codearbiter` let scaffold recovery create files in the linked temporary human
directory. The initializer now checks reparse points before those writes. The
negative test proves refusal with the linked directory unchanged.

The parent ran the complete workflow oracle after both fixes: all 18 tests
passed, including the exact T-027 and T-028 pairs. The authors ran the native
contextdocument/operations packages, ten route-compatibility tests and generated
parity checks successfully. Native campaign acceptance and installed-package
qualification remain pending.

## Document-scoped healing and incomplete evidence — T-029/T-030

Commit-gate healing now maps a selected changed source to every affected stale
document. It intersects document drift with the staged worklist, reinspects
each affected document and updates only its selected evidence. One fresh
document cannot hide another stale dependent, and an unmapped selected path
does not silently become healed.

The v2 assessor retains valid neighboring records when one provenance record is
missing, corrupt, unsupported or unreadable. Available documents keep their
own current/stale/unchecked identity assessment; incomplete coverage remains
visible and never certifies semantic freshness. Startup reports presence
without broadly hashing sources. The actual startup path also reports partial
legacy hash acquisition as unknown.

The new store reader stops directory enumeration at 256 entries, bounds each
file and the aggregate input to 8 MiB, and rejects duplicate JSON keys. Small
sentinel fixtures prove those limits without constructing large payloads.
The parent reran the complete provenance oracle after the bounded-reader
correction: all 145 tests passed. Author runs also passed the 202 read-injection
and 80 session-start tests and generated parity checks. These are source and
consumer-contract results, not live model compliance or native acceptance.

## Bounded maps and scoped command evidence — T-031/T-032

The coarse map retains the 50-entry/20 KiB limits and now diagnoses malformed
roles, unsafe paths and missing targets on demand. Old map targets with
`drift_trigger=false` still report deletion, without falsely reporting an
existing ordinary source as missing. The native writer checks the bounded
proposed targets before approval/apply. Existing human maps are not truncated
or rewritten by advisory inspection.

Command selection now preserves source, cwd, prerequisites and the complete
execution binding. Equal command text in different packages remains distinct.
Historical stored success alone does not establish a current result. Named
test observations must match the declared collector and named-test oracle,
with each required test passing exactly once. An exit-only observation can
report success for an explicitly declared non-test oracle; it cannot stand in
for missing test outcomes. Shell declarations remain inert references.

The resolver calls these supplied observations `reported_current_state`.
It validates their scope and consistency but cannot authenticate their
provenance. The owning execution collector must supply the actual observation
and current binding; later task delivery and installed-host exercises remain
separate obligations.

Fresh parent verification passed all 147 provenance tests, both exact T-032
consumer methods, the full Go module and `go vet`. The native bridge's strict
mutation inventory was extended for the actual new T-027 negative case. The
parent reran that bridge successfully against all sixteen expected native
subtests; the author also ran all six bridge methods successfully. The
collector still refuses missing, unexpected or skipped named outcomes.

## Relevant dependency invalidation — T-033

Context assessment now rechecks each document's declared content and membership
dependencies, with its own target preimage. A manifest or nested instruction
change marks only affected documents stale. Unrelated leaf edits or HEAD
advancement and the workflow's own provenance/marker effects do not require a
broad re-scout. The assessment remains bound to the physical worktree and Git
directories; a copied record in a sibling worktree does not become current.

This scoped identity assessment is separate from the existing strict snapshot
check before a write. It supplies neither semantic approval nor mutation
authority. The parent ran the complete declared context-contract oracle after
the source froze: all 45 tests passed, including the two exact T-033 methods.
The author's provenance oracle passed all 147 tests. Direct script execution
now includes the formerly omitted command-record TestCase and runs the same
45 tests as discovery. Generated copies matched in the author check.

## Task context selection and first manifest — T-034/T-040

Task selection now joins the applicable package scopes without collapsing equal
commands with different cwd or constraint owners. The packet carries bounded
map entries, source identity, command observations, constraint references and
the supplied host instruction order. Oversize maps do not produce a misleading
partial map; oversize instruction text keeps references and an explicit gap.
The parent ran all four consumer tests after T-034 source release successfully.

An empty interview-derived tech-stack record now identifies the first real
manifest as a selected refresh candidate. This works both when the file appears
during a session and when a new session starts after it exists. The advisory
check preserves interview history, performs no context write and grants no
approval. The parent ran the complete workflow oracle after the ordinary-session
regression was corrected: all 20 tests passed with no skips.

The combined CP-03/CP-04 audit checked a frozen 107-path source manifest and
reported no actionable findings. T-034 and T-040 were outside that freeze.
Source tests and this audit do not substitute for actual child delivery,
native lifecycle acceptance or exact installed-candidate qualification.

## Feature, fix, test and review inputs — T-035/T-036/T-037

Feature authors and independent reviewers receive a freshly composed scoped
packet tied to the existing approved artifact IDs or confirmed small-lane
mini-spec. Fix and test-change inputs retain the existing caller, command cwd
and observed execution state. Fix inputs preserve the cited causal evidence and
named bug-origin regression; an already useful regression can be reused without
changing production behavior to manufacture RED.

Review context now distinguishes bounded read-only orientation from admission
to a substantive verdict. Missing critical references and applicable unresolved
constraints block that verdict. An optional missing map or legacy provenance
warning does not force onboarding or forbid useful source inspection. The
selector and input composers are inert; actual child delivery remains a later
host exercise.

The parent ran all ten consumer tests after T-036 source release successfully.
T-035 also exposed an import regression in four installed approval cases:
loading its selector from the unrelated approval path cached a development
host adapter. A fresh-process regression reproduced this before the selector
was made lazy. All four affected installed-host cases passed after that repair.
The failed broad run remains retained; it was not repeatedly rerun. Generated
Python and command surfaces passed the authors' parity checks. The strict
context-check body digest was reconciled with its approved refresh changes,
and its targeted preservation guard passed with the cleanup digest unchanged.

## Resume and actor delivery accounting — T-038

Delivery planning binds the actual actor instance, task paths, source identity,
worktree, instruction epoch and observable host epoch. An author role or surviving
session marker cannot suppress a new child's context. Unobserved delivery permits
bounded, counted redelivery and leaves an explicit gap after its limit. Dispatch
instructions use this helper for authors and reviewers.

Claude compaction separately invalidates advisory read-context markers. Epoch
state is bounded and stored per session, so concurrent sessions cannot overwrite
each other's generation. Corrupt or oversized state remains byte-identical and
causes bounded pointer redelivery without accumulating new markers. Self-reads
still return before epoch I/O. The helper resolves worktree paths but does not
read source content, maintain a persistent context index or grant authority.

The parent ran both required T-038 methods successfully. The author's complete
host suite passed 4/4, prompt tests 32/32, read-injection tests 202/202 and consumer
tests 10/10, with generated parity. Codex/Pi compaction events and actual actor
receipts are not inferred from this source proof; their unobserved cells remain
unqualified.

## Loader observations, costs and package closure — T-039/T-041/T-042

The native-loading fixture prepares ten isolated instruction cells and retains
bounded raw loader events. Its assessment binds staged file and observation
digests, distinguishes complete supplied input from path-only events, and never
promotes synthetic or supplied captures to host qualification. The parent ran
the complete six-test host suite successfully. Actual native loading remains
unobserved; a missing event is not evidence that an instruction was excluded.

Whole-run accounting preserves failed attempts, retries, changed-snapshot
re-scouts, joins and supplied transient/native write events. File-effect capture
separately measures bytes and timestamps in a real temporary repository, so
same-byte timestamp churn is visible. The parent ran all 27 evaluation tests
successfully. A supplied ledger is not authenticated host activity, and two
file snapshots cannot prove that no transient write happened between them.

Package closure now requires the context selector and its transitive helpers,
protected writer and actual feature/fix/review/TDD/SDD consumer resources. Removing
the selector cannot suppress these checks while its consumers remain. Older
packages without those consumers retain their earlier classification. The
protected-state reader is explicitly accounted for in the consumer inventory.
The parent ran the complete 18-test consumer suite successfully; the author
also verified canonical/generated parity for all three governance hosts.
These source results do not establish cold installed execution or contribution
readiness. Those remain separate tests of the exact assembled candidate.

## Successful-fix trial preparation

The original eleven-case catalog has a fix-lane conflict that should stop for a
decision, but no successful fix. The separate `solvable-fix.json` supplement adds
`falsy-override-fix` without changing any existing case or oracle identity. It
contains a deliberate false-value selection bug and the ordinary named
`test_false_override` regression. Fixture preparation observed exactly one
failure among three baseline tests, then verified a reference repair against
those tests and false/zero/empty/None, fallback and mapping-preservation checks.
The full fixture preparation suite passed 24/24 after this addition.

That reference repair is a control in a disposable synthetic repository, not a
model contribution. The evaluator must remain inaccessible to a future solving
actor, including commands executing its edited code. A file-tool restriction
alone does not establish isolation for separately launched application tests.
The live A/B run and its provider/data/resource decision remain pending.

## Integrated candidate and remaining live proof — 2026-09-27

The installed-context source now connects actual named native test observations
to the existing qualification receipts and exact assembled package metadata.
The client requires the matching platform, source and binary binding plus its
installed resources. Ordinary source builds omit that qualification and refuse
context writes. Cold Claude/Codex cells exercise the public installed writer's
create, update, read and recovery paths with explicitly synthetic fixture
authority. Pi retains its unsupported-workflow refusal. These are candidate
checks; they do not grant or claim live host authority.

The author passed the six-case native runner, package receipt rejection controls,
installed missing/nonisolated controls, the existing all-host cold fixture,
94 CI-impact tests and 18 hook-partition tests. The parent independently passed
the current Go suite and `go vet`, plus all 22 context workflow tests including
both T-059 upgrade/rollback controls. Exact six-platform coverage and the cold
installed positive require the committed candidate's hosted run and are pending.
The Python audit guard's denial of development-checkout reads is not an operating
system sandbox for its native child.

T-039 and T-045 now exercise the exact generated hook command in their local
controls, including valid capture and invalid-event refusal. T-045 retains
separate baseline and candidate delivery; controlled candidate delivery loads
the digest-bound installed selector outside the development checkout. Its
source suite passed 29 tests, then T-046's scoped-readiness controls brought the
same suite to 31 passing tests. Supplied evidence remains unverified; it cannot
claim E0-E2/G1 readiness, enable P1 or grant commit/release authority.

No real model trial, scout containment qualification, native instruction-loading
claim or measured contribution benefit has been produced by these source checks.
The live tasks and conditional guidance decision remain in the same native plan.
The logged candidate-commit override permits source delivery for hosted testing
while preserving actual task states and all security and exact-head merge checks.

## Current owner integration and candidate boundary: 2026-09-28

At the 17:02–17:04 UTC source check, main was
`158daa0016eb7f7127221fac6deefb59991804ad` (tree
`0f0b65a3d6f31fb9c1e4e8bd4275bd0a0e01cc33`). PR #854 was merged at
`00f2598e60446f015506530a3396c87728d2eada` (merge
`6320eb51ec4cccee27ac1da1be326824d7e51a57`), and #873 was merged at
`a09b49d191b52c0615b81cc00705bb8b58a6d6bc` (merge
`6afd0172714697e88e37b854f2df0cd323504299`). Both merged heads and
current main are ancestors of the #872 execution head
`ffc6cfb90dbfc2da76945a704f1daa1899df1ab1`. Its integration commit is
`4319325135a83fc48de810252700a60869d1b13a`. PR #871 remains open at
`0759ca2bf3d6740141fa3b0e0bf219232633fbb5`; its separate debug
correctness work is not represented as merged or accepted here.

T-001's exact declared implementation paths are
`docs/campaigns/exercise-ready-brownfield/README.md`,
`docs/campaigns/exercise-ready-brownfield/implementation-evidence.md`,
`.github/scripts/test_context_fixtures.py`, and
`.github/scripts/test_context_named_output.py`. This dated source correction
touches only the first two; it does not change the native task definition or
the original two named verification commands. The complete revision-15 T-001
context was read in four typed pages (88 records; final ticket
`6f6ffe5a86049a90158798b24fffb7068db0877e987823944eb08e96d00eadc8`).
The approved specification is revision 8 at normative SHA-256
`addf0bf9bea697f1edd485e56d41b29810ced5d374d59ccf6d60197f9bda0d7a`;
the bound plan is revision 15 at model SHA-256
`a26ee71d7f132840470d10aa1160730d5172f37814096f75715cb5840c1bf3c4`
and normative SHA-256
`34784632f0bd08c361e54b4b40b27c4b7af1656e9026ffb49c19538fd31ae61a`.
T-001 is still `REVIEW`, and `all_accepted_and_current` is false. These
context reads confer neither a verification outcome nor acceptance.

The exact overlapping owner bodies were checked at the current execution head.
`core/surface/commands/context-check.md` is still the one-line
`{{SKILL_ENTRY:context-check}}` wrapper (blob
`c23b4a82f094d962f513c5c2fee5558518d28f61`), and
`core/surface/commands/debug.md` is still `{{SKILL_ENTRY:debug}}` (blob
`b206f9c45616068bf7ce74f4e3be762f702b739a`). The debug skill retains
#854's blob `9ccacb1c8499690645661e1f8599091aacea80e4`; the candidate does
not import #871's independent diagnostic work. Relative to current main, the
brownfield source changes only the context-check skill (main blob
`2b04866d43ad597bb8076d5adb9cabec5c30bab6`, candidate blob
`eb55f65163c1f9edd988ec08ef93cfb4bf0ca76d`) and the status command
(main blob `ccb0f5b810487a0385f18999e85673d1b7eb0158`, candidate blob
`0216eab207dbb61d7b05700de5e5e209e75a67af`) among those five owner
paths. The former defines bounded v2 assessment and selected initialized
refresh; the latter keeps status and drift reads from authorizing a write.
Debug diagnosis and regression handoff remain with their separate owner.

The selected native *authoring* host is the separately qualified Codex CLI
0.145.0/native-v1 installation of ca-codex 0.14.6, with 238 verified package
members and cohort SHA-256
`8a44b787b25adf839cc87589c8a99f8bc13cf17ed900b9ba026d120658f453af`.
This is the selected workflow authority for the pending native T-001 run. It
is separate from the #872 candidate's cold-package cohort. The latter is
bound by the retained qualification metadata to source
`8e7e1c38da4078b12deb2618fba1cb5ae0a61c8b`, head
`ffc6cfb90dbfc2da76945a704f1daa1899df1ab1`, ca package 2.24.0,
ca-codex package 0.15.0 and ca-pi package 0.16.0. GitHub run
36398483740, attempt 1, completed successfully at that committed head:
71 jobs succeeded, including 18 cold package cells and merge readiness.
This CI result covers committed `ffc6cfb9` only; the ensuing documentation
and native-lifecycle working-tree changes need their own applicable verification.
The local qualification metadata says `installed: false`; a prepared
distribution is not an installed live host.

The E0–E2 preparation profile remains selected and P1 remains unselected and
off. Real native instruction loading, scout containment, an authorized first
contribution and measured model benefit remain unproven. Eight historical
Claude probes are exhausted; another provider trial requires the concrete
provider, data and resource decision. Codex/Pi unsupported or unobserved live
cells must be stated for the exact profile, without broadening the support
claim. The coordinator must run T-001's two declared unittest commands and
collect their required named outcomes through the selected installed verifier,
then obtain its actual independent review and task disposition. Ordinary
source results and this document do not replace those receipts. The existing
all-live-task `all_accepted_and_current` gate still blocks a completed-plan
commit while any live selected-plan task is pending or in review; a P1 no-go
requires the same plan's normal amendment and approval path.
