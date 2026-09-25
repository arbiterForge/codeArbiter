# Debug correctness: reviewed specification

Document: CA-DEBUG-CORRECTNESS-01, D1 review revision 3  
Date: 2026-09-25  
Status: Proposed specification input, not an approved or engine-authored artifact  
Repository: arbiterForge/codeArbiter  
Inspected main: 4187f1e22dc7da3cf755a2654bbf7ec268236126  
Integration candidate rechecked for D1: PR #854 at 578065076e2e11a4e63f33256cb386a5cba1d7d2 (open and draft; debug owner/declaration byte-identical to the earlier inspected candidate)

## D1 preparation status

T01-T04 source preparation is complete; T05 native adoption and T06 actual approval are blocked, not waived. [D1.md](D1.md) records exact evidence and the remaining gate. D1-PROFILE.md resolves the finite profile choices and D1-CASES.json freezes evaluator-side controls. All product scenarios remain unrun. The D1 request authorizes this preparation on the same PR, not D2/D3, package updates, an approval receipt, merge or release.

## Authority and use

This source-only proposal is accompanied by [CONTRACT.md](CONTRACT.md), [SCENARIOS.md](SCENARIOS.md), [PLAN.md](PLAN.md), and [REVIEW.md](REVIEW.md). Together they are the self-contained reviewed planning input. They do not change installed behavior, create a canonical specification/plan, approve implementation, or establish release qualification.

The supplied revision-1 package was reviewed, not treated as an implemented contract. Its archive SHA-256 is `78329cd6a9abf2810eb4853b8068f0385837db9ec9d1cb2611662a04c9cf15b3`; its SPEC.md SHA-256 is `f1c7da4e8376e00ab5e93a6d39d98c4caf6762e9362172782f3ff56212d4eab3`. This revision preserves G1-G8, R01-R15, AC-01 through AC-28, SEM-01 through SEM-15, and V01-V35; the review identifies the clarifications and added negative cases. It is a reviewed restatement, not a byte-identical copy of revision 1 or a claim that its old validation report proves this revision.

Before execution, adopt this input through the qualified installed artifact engine under the current feature workflow, or its explicitly supported initial sprint-pair preparation. Allocate actual native criterion IDs and retain an external-ID correspondence. Preserve exact spec/plan binding and actual host-observed approval. Do not put these Markdown files in `.codearbiter/specs/` or `.codearbiter/plans/`, hand-author a lookalike HTML authority, invent receipts, or use a source-built binary as an installed-authority substitute. Missing capability blocks canonical authoring and execution, not publication of this explicitly unapproved review proposal.

The request for a WIP PR authorizes this documentation publication, not an implementation, merge, release, provider purchase, or approval event.

## Problem and outcome

Debug's investigation-first boundary is valuable. Its current procedure nevertheless requires reproduction before some investigations can start, forces unresolved evidence toward the wrong disposition, confuses an experiment requirement with confirmation, writes an open task for a no-action result, and underspecifies the bug-origin handoff to fix/TDD. A generated helper command also depends on a root token not guaranteed in ordinary Codex tool calls. These are source-bound contract findings, not a measured historical failure rate.

The intended outcome is a truthful diagnosis or actionable unresolved result, followed by an evidence-preserving repair handoff when actually authorized. The maintainer expects unfamiliar forks, primarily Claude Code and potentially Codex. More documentation, extra agents, a faster wrong answer, or a schema-valid unsupported cause does not establish success.

Retain investigation before repair, cited observations, alternative explanations, user-attributed decisions, regression failure for the right reason before implementation, minimum repair, fresh verification, existing security/branch/commit/release gates, sanctioned state writers, and one canonical source with generated host projections.

## Scope

| ID | Required outcome |
|---|---|
| G1 | Admit identifiable problems without invented reproductions; use current repository context. |
| G2 | Gather discriminating, source-bound evidence within an explicit action and disclosure boundary. |
| G3 | Return truthful code-defect, non-code, design, no-action, or unresolved results. |
| G4 | Produce and actually consume a bounded, transient, validated handoff with freshness checks. |
| G5 | Give fix/TDD an explicit bug origin and support an adequate existing failing regression. |
| G6 | Resolve affected installed helpers, interpreters, and literal arguments correctly. |
| G7 | Preserve source ownership, caller authority, existing state, host generation, and documentation parity. |
| G8 | Separate deterministic, installed-package, and model-behavior qualification. |

Non-goals: no new public command, top-level skill, mandatory agent role, model/provider dependency, daemon, database, telemetry, global memory, automatic issue filing, consumer-repository instruction files, persistent case directory, new artifact kind, board migration, automatic historical-note cleanup, or required HTML diagnostic report. No instrumentation or remediation inside debug, general-purpose executor, permission-mode change, unrelated helper sweep, Academy change, product-maturity change, or HTML-farm enablement.

Brownfield owns context generation. Debug consumes the existing optional code map and context; it must work without the other workstream's proposed output. PR #854 owns its broader consolidation, retirement, and farm changes. This effort neither imports that whole branch nor reverses its named retirement.

## Integration with PR #854

At the inspected candidate, `core/surface/commands/debug.md` contains only `{{SKILL_ENTRY:debug}}`; the skill owns its description, argument hint, entry boundaries, phases, and exit effects. The generator emits the complete procedure at each existing host entry. The candidate keeps the Claude owner discoverable, marks only the generated Claude command `disable-model-invocation: true`, and retains discoverable Codex/Pi public entries. Preserve that ownership and discovery behavior; do not add a second procedural wrapper or another schema-loaded entry.

The candidate's moved entry boundary still prohibits re-entry from an active fix, and its phases still require the old reproduction/count/three-exit/queued-close behavior. Those are not repaired merely by consolidation. Revise them in the owning skill. Replace the blanket re-entry prohibition with a bounded internal diagnostic prerequisite that returns to the current fix caller; never recursively invoke the public fix/debug commands.

The candidate removes `new-skill`, `skill-author`, and its template. Use the source-only authoring conventions in `core/surface/README.md` after integration. Do not resurrect the retired entry, workflow, alias, template, or discovery registration. Preserve historical decisions and unrelated compatibility exceptions.

This planning PR is based on main. Before the shared workflow edit, require the owner consolidation to be integrated, or obtain explicit approval for a separately bounded prerequisite extraction. Do not cherry-pick or merge #854 automatically. Re-read its status/head and current main; the recorded head is evidence, not a permanent dependency pin or permission to overwrite later changes.

## Selected approach and limits

Revise the existing five phases rather than introducing a new workflow. Keep one coordinator. Add a finite standard-library Python decoder/validator behind existing execution tools, plus on-demand reference material and actual consumer integration. A packet is data, not a truth engine or authorization token.

| Parameter | Proposed choice |
|---|---|
| Public entry identities | Existing debug and fix host-native names, unchanged. |
| Phases | Capture, hypothesize, gather, decide, hand off; early unresolved return is permitted. |
| Hypothesis breadth | Meaningful alternatives or a genuine discriminator/falsification attempt, not a fixed count. |
| Outcomes | `confirmed_code_defect`, `confirmed_noncode_cause`, `design_question`, `no_action`, `unresolved`. |
| Protocol | Proposed `codearbiter.debug-handoff/1.0.0`, not a shipped version. |
| Storage | Active session/tool input only; no new product-state file. |
| Packet ceiling | 65,536 UTF-8 bytes; 4 snapshots, 32 evidence records, 16 hypotheses, 24 checks, 8 blockers; container depth 16. |
| Summary | At most 400 words excluding short locators; result, uncertainty, next action, and authority first. |
| Default roles | Existing coordinator; no mandatory fleet. |
| Runtime | Shared standard-library Python, no new dependency or native executable. |
| Qualification | Claude required; Codex separately qualified; Pi keeps applicable generated/contract parity without inherited runtime claims. |

Limits are ceilings, not content targets. A prototype must not turn a two-observation case into a maximum-size packet. Numeric speedup or universal reliability is not promised.

## Lifecycle

| Phase | Work and valid exit |
|---|---|
| Capture | Establish symptom, scope, actual caller intent, available expectation/evidence, reproduction state, and observable source/runtime identity. Start safe orientation without inventing missing facts. |
| Hypothesize | Read enough to form useful mechanisms; identify discriminating checks. Zero candidates is allowed only for an unresolved result explaining the missing input. |
| Gather | Inspect existing evidence or execute an authorized bounded diagnostic. Record predicted and actual observations. Continue only when a new feasible check can improve the decision. |
| Decide | Apply the specific outcome's evidence requirements. Multiple contributing mechanisms are allowed. Independent defects remain separately scoped. |
| Hand off | Validate and return the compact result. The caller independently checks scope, authority, freshness, and downstream prerequisites before continuing. |

A gate controls dependent action, not the ability to report known facts. An early unresolved result need not fabricate later-phase content. With no identifiable symptom at all, ask one focused question and return the missing-input explanation without inventing a case.

## Requirements

### R01: admission and orientation

Accept a user report, failed job, trace, timestamped error, or identifiable anomaly. Label user reports as reports, not independently reproduced facts. Establish expected behavior from applicable contracts, approved specs, tests, authoritative documentation, or stated user intent. Preserve conflicts; without an expectation, inspect mechanics but do not assert a contract violation.

Read scoped instructions and required codeArbiter context. Use `code-map.md` when present as a search pointer, then verify current sources. Inspect relevant manifests, test configuration, and source before asking for facts already available. Avoid bulk repository/governance reads.

Preserve activation and initialization authority. Missing context does not authorize scaffolding, marker writes, guessed commands, or disabled gates. Safe orientation can report a precise prerequisite gap; dependent execution stops when its required command, context, or safety boundary is unavailable. This is not a zero-onboarding mode. Do not assume an OS, provider, network policy, branch, installed version, or clean worktree.

### R02: reproduction

Represent reproduced, intermittent, not-yet-reproduced, unsafe-to-replay, and unavailable explicitly. Retain attempted actions, inputs, cwd, preconditions, observed failure, and limits where known. A failed replay only describes its tested conditions; it does not disprove the defect or justify no action.

Sufficient current source/contract evidence may establish a code defect before replay. Such a handoff must name a concrete regression obligation derived from the causal trace. Fix still observes a valid target failure before repair. Without an honest testable obligation, return unresolved. Do not force failures or alter oracles to fit a route.

### R03: hypotheses and efficiency

Distinguish observations from mechanisms. Inspect before ranking. Include ordinary configuration/environment/dependency explanations when relevant, not as mandatory padding. One well-supported mechanism plus a real discriminator is acceptable; consider more than three when warranted. One check may discriminate several hypotheses.

Choose checks by discriminating value, safety, cost, and availability. Recency and familiarity are search hints, not proof. Do not repeat unchanged checks without a reason. Stop on sufficient outcome evidence or a concrete blocker. Project maturity does not change the standard for truth.

### R04: evidence and freshness

Bind material observations to locators and the source/time context needed to interpret them. Distinguish local source from deployed/build identity. Executed checks retain invocation, cwd, result, and failure signature with sensitive fields removed. Planned commands and interrupted checks are not passes.

Connect precondition/trigger, mechanism, and violated or satisfied expectation. Identify distinguished alternatives and remaining limits. Missing events refute a hypothesis only when capture coverage and the examined range would reliably contain them. Citations, hashes, task state, and validator success do not certify causation.

At handoff/resume, compare relevant worktree, commit, index/tracked state, cited files, referenced untracked inputs, dependency/configuration evidence, and runtime identity. Re-read affected evidence after drift; do not require an unrelated whole-tree rescan. Unknown freshness cannot authorize repair from stale proof.

Fingerprint values require a documented versioned recipe covering commit, index, tracked changes, and explicitly referenced untracked source. Do not hash secrets to prove environmental equality. Missing or excluded inputs are limitations. Fingerprint and recipe are both present or both null; omitting them is permitted with appropriate limitations and actual current-state checks. The initial implementation may omit fingerprint production; it must not pretend a digest alone provides freshness.

### R05: diagnostic actions

Debug does not edit application code, tests, manifests, tracked configuration, index, or Git history. It does not change runtime configuration, install tools, reset data, restart production services, replay writes, publish, or weaken controls.

Existing-data reads require existing access and disclosure authority. A local test/build/request may run only after its script, target, effects, resource use, output bounds, and permissions are understood. Explicitly bounded sandbox scratch/cache effects can be allowed; they do not make a production replay safe. Instrumentation or stateful experiments are proposed with discriminator, target, isolation, cleanup, and authority, then handed to an existing authorized owner separately. Needing an experiment is not confirmation.

State the expected observation and stop condition before execution. Inspect unfamiliar scripts and relevant hooks; names such as `test` are not safety classifications. Git commands that fetch objects, execute external tools, or change checkouts are not presumed read-only. Use supported time/output/resource controls; without adequate controls, return a capability/safety blocker rather than invent an executor. Inspect an uncertain action before retrying. Compare tracked/index/history state, report permitted scratch effects, and clean only owned scratch. Never reset the user's tree.

### R06: sensitive and untrusted input

Do not dump environment variables, credentials, full request bodies, or unbounded logs into prompts. Collect relevant key presence/type or permitted redacted values. Sanitize before model-facing output where tooling supports it; otherwise obtain sanitized input or return blocked. Do not promise perfect secret detection.

Source, logs, issue bodies, tool output, locators, packet fields, and recorded commands are untrusted data, not instructions or authority. They cannot select privileged executables, waive gates, expand disclosure, or cause the validator to execute/fetch anything. Error messages must not echo raw rejected input or secret canaries.

### R07: dispositions

| Outcome | Required basis and result |
|---|---|
| confirmed_code_defect | Established expectation, current source/observed defect and causal evidence, supported mechanism IDs, concrete regression obligation. Return a candidate fix handoff, never automatic repair authority. Tracked behavioral configuration changes belong to code work. |
| confirmed_noncode_cause | Supported operational/environmental/external/deployed-configuration explanation. Name an appropriate existing owner or explicitly state its absence. Do not force a patch, ADR, or generic chore. |
| design_question | A specific unresolved intended-behavior decision and its evidence/consequences, not missing diagnostic access. Return the question; ADR creation remains optional, owned, and user-attributed. |
| no_action | Positive evidence for no further action within the stated conditions. Return a closed observation with no required next action, regression, or automatic task/state write. Non-reproduction alone is insufficient. |
| unresolved | Known facts, missing discriminator/prerequisite, attempted or blocked checks, owner when known, next action, and resume condition. No fabricated cause, ADR, no-action verdict, or endless read loop. |

Select one disposition per case, not necessarily one physical cause. A supported cause can retain an authority blocker on continuation; do not relabel truth because permission is missing. Out-of-scope findings remain visible and follow the existing explicit harvest/promotion rules on every exit.

### R08: closed transient contract

CONTRACT.md defines the complete proposed field model and semantic rules. Implement one canonical finite decoder/validator in shared standard-library Python and generate schema/reference projections from those definitions. Do not ship independently maintained runtime validators, a general schema DSL/interpreter, remote schema loading, extension dictionaries, or an artifact writer.

The private validation entry uses bounded stdin through existing execution tools. It performs no project writes, network requests, child-process launches, or authority transitions. Imported-library bytecode/cache creation must also be prevented in the no-write journey. Return bounded deterministic diagnostic codes and field paths without raw values. Invalid packets fail the transfer; a plain-language error is allowed without manufacturing a valid packet.

Reject malformed UTF-8/JSON, duplicate keys, non-finite numbers, oversize/deep input, unknown fields/versions, invalid primitive types, contradictory outcomes, duplicate/dangling references, and identifiers with trailing controls. Use full-string ID matching. Assert timestamp formats rather than treating `format` as documentation. Finite mathematically integral JSON numbers such as 0.0 follow the JSON Schema integer interpretation; booleans do not. Do not accidentally implement Python bool-as-int behavior or an undocumented numeric-lexeme restriction.

Validation proves only the declared structural/semantic invariants. It cannot establish causation, permissions, host enforcement, or the truth of evidence.

### R09: consumer

Debug emits a validated packet. Fix invokes the same validator, consumes its actual fields, and independently checks the active request's scope/repair authority and relevant current evidence. Do not discard valid evidence and re-ask already answered symptom/expectation/reproduction questions. Gather genuinely missing facts or reconcile drift.

Evidence from another session, worktree, or build is historical until applicability is established. Normalize legacy summaries in memory from available citations; missing facts stay unknown, not automatically confirmed. No existing record is rewritten. A malformed retained packet is an input error, not permission to repair from an unvalidated fallback.

### R10: bug-origin TDD and call/return

TDD distinguishes approved-feature criteria, confirmed-bug obligations, and existing refactor parity. A bug fix does not invent a feature spec or plan. Carry observed/expected behavior, expectation source, source binding, defect evidence, and regression obligation while retaining applicable contract/security, implementation, commit, and release gates.

Direct fix remains supported. It may call the debug owner as one bounded diagnostic prerequisite and receive the result into its current invocation; the user must not reissue public commands. Do not recursively route debug-to-fix-to-debug or create a new persistent call-state store. Unresolved results stop repair. A diagnosis-only request ends after diagnosis even when repair is obvious. The packet's `repair_requested` label is not authorization.

### R11: target red and repair proof

Reuse an adequate existing test that freshly fails for this exact defect; record identity and the red observation. `reuse_existing: true` requires a named test. Add tests only for uncovered obligations. With no adequate test, write a regression and see it fail for the correct reason before implementation.

Unrelated baseline failures and new import/setup failures are neither target red nor green. Keep them visible; do not skip, weaken, lower thresholds, or waive required commit/merge checks. Candidate regressions that pass against the alleged broken state require corrected evidence/oracle or an unresolved result, not speculative repair.

Assert behavior, not a forced failure or mock-only detail. For intermittent defects, use a faithful controlled seam or bounded repeated-trial oracle and report stochastic limits. Keep assertions unchanged between red and green. Material fixture/setup changes require renewed baseline red. After minimum repair, freshly run target and affected-contract tests plus applicable coverage, lint/type-check, and specialized gates. Exhaustive supported-platform proof remains exact-head hosted CI's responsibility. No known-red required check is authorized for commit.

### R12: portable helpers

Resolve absolute helper paths from the loaded trusted installed resource and host-owned package identity. Codex must not try an empty root environment variable first. No `/hooks`, consumer-checkout, source-clone, recursive cache search, or project-selected executable fallback. Preserve current supported installation conventions.

Select and validate a working Python 3 interpreter before invoking the helper. Distinguish missing/stub/incompatible interpreters from a helper's refusal. Never use `python3 helper ... || python helper ...`; a failed operation must not be repeated or its error concealed.

Prefer argv arrays. Otherwise use supported literal host quoting; spaces, non-ASCII text, quotes, leading hyphens, and shell metacharacters remain data. Put options before `--` separating user text; give option values beginning with hyphens an unambiguous supported form. Do not interpolate source/log text into executable syntax.

Limit common guidance to the validator and genuinely authorized task-follow-up path; repair the task owner's relevant examples when necessary. Preserve writer validation, locking, atomicity, and error behavior. Removing the default no-action writer does not qualify the remaining follow-up route.

### R13: output and lifetime

Return a short summary projected from the validated case, with facts, uncertainty, next action, locators, and authority/access needs. A recommended route is not an executed handoff. Do not automatically display the whole JSON, copy raw logs, create root instructions, or inject packets each turn.

Pass the session-local packet at handoff. If limits are exceeded, compact explicitly to decision-relevant cited evidence or report capacity; never silently drop evidence needed by a conclusion. Resume reuses actually retained identity and checks freshness. Lost context is stated and reconstructed from accessible evidence, not claimed as durable memory.

No default note/state write for no-action or unresolved. Explicitly authorized real follow-ups use the existing task/harvest owner and include executable action, provenance, and completion evidence. No historical `debug.note` cleanup or fake task transitions. Persistence/export as a runtime feature remains separate scope.

### R14: ownership and parity

Edit canonical sources and regenerate Claude/Codex/Pi. Preserve #854's single owning skill and discovery distinctions. Change operative entries, routing, consumers, tests, and docs together; remove conflicting old hard rules rather than append competing instructions. Historical records remain historical. Do not derive fixed catalog counts from the old baseline.

Keep existing roles and their authority. Role labels or frontmatter do not establish read-only enforcement. New enforcement claims require effective-tool/effect tests. Claude is required for readiness; Codex needs separate installed proof. Pi needs applicable generated and contract checks and retains its existing limitations. Debug portability does not establish native artifact-authoring support on Pi.

### R15: compatibility and coordination

Do not migrate consumer state, modify accepted ADRs, change exact-format existing spec/plan pairs, or silently accept unknown packet versions. Reconcile active work and current evidence before implementation, after dependency integration, and before final qualification. Coordinate debug, fix/TDD, helper, generator, and brownfield overlaps without copying unrelated changes.

## Acceptance ledger

All 28 original acceptance identities remain. Added review scenarios sharpen existing obligations rather than silently create a second criterion ledger. Native adoption allocates engine IDs and records the correspondence.

| ID | Scope | Observable acceptance | Scenarios |
|---|---|---|---|
| AC-01 | G1 | A cited failure with unknown trigger enters scoped investigation as not_yet_reproduced without invented cause/repro. | V01 |
| AC-02 | G1 | Available expectation is used without re-asking; genuine conflicts/missing intent stay explicit. | V02 |
| AC-03 | G1 | Missing context/capability produces a precise prerequisite result, no guessed command, onboarding, marker, or readiness fiction. | V03 |
| AC-04 | G2 | Diagnostics stay within assessed target/effects/resources/authority; unsafe replay and unknown scripts do not execute. | V04,V05 |
| AC-05 | G2 | Sensitive collection is bounded/sanitized or blocked; embedded instructions and rejected values do not escape their data boundary. | V06 |
| AC-06 | G2 | Narrow cases use real discriminators without padding; wide cases expand when evidence warrants; no pointless repeats. | V07,V08 |
| AC-07 | G2,G4 | Source/runtime identity and capture limits prevent stale evidence and absent partial logs from silently establishing causes. | V09,V10,V39 |
| AC-08 | G3 | Unavailable evidence terminates unresolved with discriminator/resume condition, no ADR/no-action fiction or loop. | V11 |
| AC-09 | G2,G3 | Instrumentation-needed hypotheses remain unconfirmed without independent support; no debug code edits. | V12 |
| AC-10 | G3 | All five outcomes meet distinct obligations, support multiple mechanisms, and retain continuation blockers honestly. | V13,V14,V37 |
| AC-11 | G3,G7 | Evidence-backed no-action leaves board/state unchanged; failed replay alone cannot justify it. | V15,V16 |
| AC-12 | G3,G7 | A real design question is surfaced without autonomous ADR; missing access is not a design decision. | V17 |
| AC-13 | G3,G7 | Non-code cause names an existing owner or its absence without unauthorized operations or gratuitous patch. | V18,V37 |
| AC-14 | G4 | Producer/consumer use the bounded protocol and pure validator without writes, execution, external loads, or authority events. | V19,V40 |
| AC-15 | G4 | Malformed/oversize/duplicate/wrong-version/dangling/contradictory inputs reject, diagnostics do not echo secrets, and scalar/identifier rules agree. | V20,V38,V39 |
| AC-16 | G4,G5 | Fix consumes validated expectations/regression, rechecks real authority/current evidence, and avoids duplicate questions. | V21,V22,V37 |
| AC-17 | G5 | Direct fix obtains a bounded diagnostic prerequisite and returns without fake feature artifacts or routing recursion. | V23,V36 |
| AC-18 | G5 | Adequate existing target-red regression is identified and reused; no duplicate just because it predates repair. | V24,V38 |
| AC-19 | G5 | Unrelated/new failures remain visible and cannot count as target red or waive required gates. | V25 |
| AC-20 | G5 | Target fails correctly before repair and passes after minimum repair with unchanged assertions, renewed red when fixtures materially change, and fresh affected proof. | V26,V27 |
| AC-21 | G6 | Literal installed-helper calls work without root tokens/source rescue across relevant cwd/path/worktree cells. | V28 |
| AC-22 | G6 | Interpreter selection precedes invocation, user text stays data, and helper error survives without repeated mutation. | V29 |
| AC-23 | G4,G7 | Resume preserves actually available identity, checks freshness, admits lost context, and does not migrate/store cases. | V30 |
| AC-24 | G7 | Diagnosis-only stops; authorized continuation keeps original scope/gates; real task promotion remains separately authorized. | V31,V36 |
| AC-25 | G7 | Canonical/generated/docs/entry/catalog contracts agree; preserve #854 ownership and retirement without new public surfaces. | V32,V36 |
| AC-26 | G5,G7 | Feature/refactor/ADR/writer/security/branch/release authority remains intact. | V33 |
| AC-27 | G8 | Qualification distinguishes proof layers and exact cells; missing, zero-selected, stale, or cancelled evidence is not green. | V34,V41 |
| AC-28 | G7,G8 | No required fleet/store; comparisons report aggregate costs/outcomes honestly and solvable cases cannot all escape unresolved. | V35,V41 |

## Delivery, qualification, and rollback

PLAN.md decomposes the work, dependencies, file ownership, verification, and acceptance mappings. SCENARIOS.md defines all original 35 scenarios and six additional review scenarios V36-V41. Each scenario is unrun product work in this proposal. Tests must exercise real production mechanics where deterministic logic exists; a toy state machine or answer-shaped fixture cannot qualify behavior.

Use separate layers: canonical/generated contracts; real decoder/semantic/consumer and helper tests; cold exact-package host journeys; model-driven trials. Validate boundaries, including exact byte/count/depth limits, malformed input, no-effect execution, and mutants for removed gates. Resource tests must use actual generated public and private paths, not manually repaired commands or access to source directories.

Retain the original minimum paired comparison set: V01,V07,V08,V11,V12,V15,V17,V18,V21,V23,V24,V25,V26,V31; three fresh repetitions for baseline and candidate per declared host/model configuration. Also run candidate authority/disclosure/staleness cases V05,V06,V22 with three fresh repetitions, plus each remaining scenario in its declared proof layer. Use hidden fixed ground truth, synthetic nonfunctional canaries, authorized tools/providers/budget, exact model/settings/host/package/environment identities, and individual retained results. Record total tool/subagent/model cost and tokens when available; unknown is not zero. Do not combine unlike configurations or report best runs only. Failures are retained and affected trials rerun after correction.

Safety/authority invariants are hard requirements. Solvable cases must reach their supported diagnosis/handoff; unresolved can pass only cases whose evidence is actually unavailable. An unexplained material cost/time regression must be investigated and explicitly accepted, not hidden. A finite sample is not universal reliability proof.

Deterministic source completion, merge eligibility, named-host readiness, and published-artifact qualification are separate. Required CI/review gates still apply. Source work with disclosed pending external cells is not exercise-qualified. Before the exercise, install the selected exact qualified artifact and run a harmless local debug-to-fix smoke in the actual environment. No artifact version, OS, provider, or spending authority is chosen by this proposal.

No consumer-state migration is necessary. Roll back coupled producer/validator/consumer/generation/docs coherently and retain user records and previous evidence. Partial installs fail explicitly. Do not remove #854's owner consolidation or restore its retired authoring surface when rolling back this feature. Do not leave a new packet interpreted by an incompatible old consumer. Host failures narrow/block the affected action rather than weaken controls or inherit another host's result.

## Evidence references

Main source facts are bound to `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:` and the following paths: `core/surface/skills/debug/SKILL.md`, `core/surface/commands/debug.md`, `core/surface/commands/fix.md`, `core/surface/skills/tdd/SKILL.md`, `core/surface/includes/routing-table.md`, `core/surface/includes/safety-core.md`, `core/surface/includes/codex-host-notes.md`, `core/surface/commands/task.md`, `core/pysrc/taskwrite.py`, `core/surface/includes/verification-boundary.md`, `core/surface/includes/artifacts.md`, `core/surface/skills/writing-plans/SKILL.md`, `.codearbiter/coding-standards.md`, `.codearbiter/decisions/0037-extensible-structured-artifact-engine.md`, and `.github/scripts/test_board_sync.py`.

The prior reviewed source was `d171126e71e48b78d242c3d95b218236fdd8f61d`. The inspected comparison to current main changes only `.claude-plugin/marketplace.json`; these debug-related source findings are therefore not inferred from a changed implementation. The current marketplace source is not an installed-payload qualification.

PR #854 candidate facts are separately bound to `arbiterForge/codeArbiter@35a3cd18a327fe5aa306ba452cc21ae096a24b02:core/surface/commands/debug.md`, `core/surface/skills/debug/SKILL.md`, and `core/surface/README.md`, with the PR's changed-file list, patches, and discussion. Candidate facts are not merged/released behavior. The Project's September 1 bootstrap and August audit remain historical; no canon or cross-product claim registry is changed by this proposal.
