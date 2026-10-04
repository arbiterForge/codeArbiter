# codeArbiter: exercise-ready brownfield onboarding
## Supporting assessment and implementation proposal

**Assessment date:** September 25, 2026. **Repository:** arbiterForge/codeArbiter. **Inspected main:** `d171126e71e48b78d242c3d95b218236fdd8f61d`, rechecked at the end. **Source tree:** `a9569692369f5b53e2edf8ae78e0c4e67e93c3c3`.

This is an assessment, not an approved specification, migration, implementation, authority receipt, or release qualification. The accompanying `evidence-ledger.json` records executed checks and their limits. No production repository, consumer instruction file, global setting, installation, or pull request was changed. Synthetic fixtures were created only inside an isolated temporary audit directory and removed afterward.

## Maintainer decision

**Ship a trustworthy onboarding and task-context path before adding automatic instruction generation.** Complete the existing installation-channel correction, repair initialization and refresh contradictions, and improve consumption of the existing map/provenance records. Do not make AGENTS.md or CLAUDE.md generation a default brownfield output for the exercise.

A small, opt-in scoped-guidance pilot is justified only after the map-only alternative is evaluated. It should use the existing internal artifact engine, a separately approved non-HTML kind, one canonical record, and deterministic native Markdown projections. It must permit a zero-new-files result. Native instruction files are a distribution mechanism, not an authority mechanism or an automatic cost saving.

### Current work to reuse

| Work | Evidence state | Consequence |
|---|---|---|
| PR #870, head `6434bf3b610dd2a3d17fb2d14d22eb20883b05c0` | Open; actual one-file catalog patch inspected. Author reports isolated installation of ca 2.21.16 with six native binaries. That installation was not repeated in this assessment. | Do not implement a second channel fix. Qualify the actual merged/released installation path before the exercise. |
| PR #854, head `35a3cd18a327fe5aa306ba452cc21ae096a24b02` | Open draft. Its current account distinguishes remaining context-creation/context-check consolidation from completed retirement work. | Coordinate shared command/skill changes. Compatibility aliases alone do not establish one procedural owner. Do not include farm enablement in this review's implementation scope. |
| Published ca 2.21.16 and ca-codex 0.13.17 | Non-draft releases and archive/publication assets confirmed through GitHub. | Published metadata is not proof that a particular installed host has those bytes or can execute the complete workflow. |
| Connected machine's ca 2.21.12 | Installed payload found at `helpers/artifacts`; its trusted bridge successfully queried native Windows AMD64 capabilities. | This particular install is not missing its engine. It is older than inspected source, and the capability response does not qualify current installed workflow resources or host authority. |

PR references: `https://github.com/arbiterForge/codeArbiter/pull/870` and `https://github.com/arbiterForge/codeArbiter/pull/854`. Release metadata references: `https://github.com/arbiterForge/codeArbiter/releases/tag/v2.21.16` and `https://github.com/arbiterForge/codeArbiter/releases/tag/ca-codex-v0.13.17`.

## 1. Source, installation, and authority ownership

`core/surface/` owns the host-facing command, skill, agent, and include templates. `tools/build-surface.py` renders their host-specific surfaces. `core/hosts.json` owns host descriptors; shared Python implementation lives in `core/pysrc/`. Package metadata and qualification use `tools/build-host-packages.py`; native artifact candidates are built through `tools/build-artifacts.py`. The Go module under `core/artifacts/` implements the internal artifact engine. See S13–S23 in the source index.

Generated managed subtrees under `plugins/ca/`, `plugins/ca-codex/`, and `plugins/ca-pi/` are not independent sources of truth. This does not mean every file under plugins is generated: host-specific seams, such as the Codex pre-tool adapter, need their actual ownership checked. Change canonical templates/shared code and regenerate the managed outputs; do not patch a rendered copy to repair the workflow.

The executed generator check reports all three host surfaces synchronized. That establishes source/rendered parity, not binary distribution, native instruction loading, live hook enforcement, provider support, or task correctness.

ADR-0037 explicitly accepts an extensible internal engine while withholding automatic rollout or migration approval. Its per-kind obligations include canonical/generated ownership, authority mapping, compatibility, recovery, native-platform evidence, cold installation, and release qualification. Implemented kind contracts currently list spec and plan. The repository catalog still scans HTML, parses through the HTML renderer, and constructs `.html` canonical paths. A new Markdown-oriented kind therefore requires more than a new enum or schema file. See S20–S23.

## 2. Current onboarding-to-contribution path

| Step | Current owner and inputs | Outputs, consumer, and permission boundary | Failure or review concern |
|---|---|---|---|
| Entry selection | `init.md`; brownfield/init compatibility entry; current context presence and chosen mode | Routes to scaffolding, brownfield, greenfield, or status. Explicit initialization is not discovery-only. | Existing aliases retain overlapping procedure text. Do not remove them outside the compatibility policy. |
| Scaffold | `init-codearbiter.py`; root/stage and host command spellings | CONTEXT stub, task/question/log/checkpoint files; local Git lock exclusion and best-effort enforcement-hook installation. Existing files are preserved. | Writes are sequential. A partial run that leaves CONTEXT can make a subsequent scaffold refuse. No interrupted-onboarding recovery was executed here. |
| Brownfield preflight | `context-creation` Phase 1; CONTEXT and root listing | Classifies meaningful existing code and rejects initialized context. | Not a complete fork/upstream/worktree, instruction-tree, command-authorization, or environmental inventory. |
| Exploration | Six independent scout assignments A–F, shared scout charter | Evidence reports with path/line/hash, bounded descriptions and confidence. Scouts do not author project records. | Required isolation must exist; failure is not permission for an inline substitute. Oversized scopes need an explicit split-and-join contract. |
| Synthesis | Orchestrator, report-only after preflight | Proposed overview, stack, standards, security guidance, questions, map, release candidates, and provenance | Contradictory reports must trigger targeted independent re-inspection, not an unreported raw-source read by the synthesizer. |
| Gap handling | User and orchestrator | Answers or explicit deferrals recorded in existing questions/tasks | Missing evidence is not automatic policy. Batch genuinely relevant questions; retain explicit approval for deferral under the existing contract. |
| Persist and initialize | Legacy record owners, task helper, protected-state policies, context-creation final phase | Project-state records and initialized marker | Marker currently precedes final non-empty checks. File-specific validation and publication order need correction. |
| Later fresh session | Session-start plus prompt-submit and existing records | Host/stage/task/question/drift summary; mode-specific context. Map is not universally injected. | Initialization does not prove current environment, verified commands, or first-task readiness. Active startup also has Git/network effects. |
| Feature/fix/test work | Feature/fix/TDD routes; existing context and optional map | Relevant exploration, properly authorized small or full lane, real tests, review and commit gates | Optional map consumption and host-dependent read hooks do not guarantee that every worker or reviewer receives relevant scope context. |
| Refresh | Commit-gate selective healing or manually selected context-check | Scoped re-scout, hash update, reviewed record update, or visible defer | Known-source-only invalidation misses additions; first-record hash selection can suppress healing; full rescan routes into initialization refusal. |

For a feature, keep the existing small/full-lane decision and typed artifact preflight. A fix still needs the fault's actual evidence rather than an invented architecture review. A test-only change needs the local test runner and boundary, not unrelated deployment verification. A reviewer should receive relevant source-of-truth pointers and constraints independently of the author's conclusions. The proposed task-time selector must serve all four consumers before their first material action, not just add more documentation to onboarding. See S01–S12 and S25–S29.

## 3. Prioritized findings and counterexamples

### F01. Installation route is an exercise prerequisite, not a context-design detail

On inspected main, `.claude-plugin/marketplace.json:7–10` selects `./plugins/ca`. PR #870 changes that to the binary-bearing distribution branch. The new release notes describe the desired channel, but the still-open catalog change is distinct evidence. Do not infer installation readiness from the release title. The connected machine's older install separately has a functioning engine; do not tell the user that all installations are broken. Required evidence is a fresh install through the intended channel and a real bounded workflow in the intended environment, not another source-tree test.

### F02. Initialization and refresh do not form a coherent lifecycle

`context-creation` rejects an initialized repository, while `context-check.md:30` directs full rescans to context creation. Add an explicitly authorized refresh mode under the existing init/status routes and one procedural owner. It must preserve the initialized marker and repair only affected records. Do not temporarily clear the marker.

The final context-creation phase adds the initialized marker before checking that required files are non-empty. Move the completion assertion after file-specific validation and make interrupted completion recoverable. Scaffold existence, valid records, completed initialization, verified commands, and task readiness are separate outcomes.

`init-codearbiter.py:188–203` writes the scaffold incrementally. Existing CONTEXT refusal at 176–179 means a crash after its creation can strand a partial scaffold. This is a source-derived recovery risk, not a fault-injected reproduction. Proposed recovery must inventory existing bytes and their owners, resume only missing approved work, and refuse conflicts rather than overwrite valid state.

### F03. File invariants are ambiguous; a uniform non-empty test is inadequate

The skill describes `overrides.log` as empty, but final validation asks for non-empty files. The helper already provides the intended interpretation: header-only with zero audit entries, at `init-codearbiter.py:90–95`. Preserve that header and every existing entry. This is a contract ambiguity, not a reproduced runtime failure.

Similarly, tasks may be valid header-only boards, a domain can be inapplicable, and done-tasks is a real scaffold output even when omitted from an abbreviated command description. Validation must recognize these distinct valid states rather than encourage fabricated content.

### F04. Scout confidence and coverage are underspecified at the synthesis boundary

The scout vocabulary is strong/moderate/weak; synthesis uses HIGH/MEDIUM/LOW. No deterministic normalization was found in the inspected path. Choose one canonical vocabulary, with a closed legacy adapter if needed. Confidence is independent of coverage or applicability: high confidence in a narrow search is not proof of a repository-wide negative.

All six isolated reports are currently mandatory. Preserve that contract before changing dispatch. The charter's read-only intent coexists with Bash permission; a role label or a generic Codex agent type is not evidence of enforced write containment. No scout write escape was attempted here. Installed host containment remains a qualification requirement.

### F05. Drift checks cannot justify new instruction freshness

Executed on the pinned implementation:

| Counterexample | Actual result | Implication |
|---|---|---|
| A deleted architecture path has `drift_trigger=false` | `compute_drift` returns `{}` | Such moves/deletions are outside existing invalidation, even though an instruction about that path can now be wrong. |
| An empty interview-derived record meets a newly staged package manifest | `heal_worklist` returns `[]` | First implementation does not automatically populate empty provenance. |
| First document cites current package hash; second cites an older hash | `compute_drift` identifies the second as stale, while `heal_worklist` returns `[]` | First-occurrence hash selection loses per-document disagreement. |
| One code-map role is 100,000 characters on one line | `lint_code_map` returns `[]` | Count and wrapping rules do not bound content overhead. |

Relevant implementation: `_provenancelib.py:417–482`, `524–635`, and `890–940`. `rebaseline` updates hashes and retains claims. It does not check whether a claim is still true. Existing tolerant readers also skip malformed data and have incomplete-coverage conditions; a successful empty drift result must not be relabeled “all context fresh” without coverage status.

Correct healing should evaluate each `(document, cited source)` dependency, preserve disagreeing claims, and revalidate semantics before accepting a new baseline. Extend selective acquisition to relevant membership changes, including a newly added manifest or scope boundary. Do not make every source edit trigger every scout.

### F06. Existing map and just-in-time retrieval are valuable but not a complete handoff

The map is already used on demand by feature/fix/TDD. The Read hook emits bounded advisory pointers, and current HTML indexing preserves validated authority/identity without treating a digest as approval. Keep those mechanisms. The nominal 150-token injection budget is a character-based estimate, not actual measured host tokens.

Codex's descriptor does not supply the same pre-Read seam. Its packaged agent charters are resources passed to host-provided threads, not native registrations. Therefore the portable improvement is a bounded task-time reference selection carried explicitly into author/reviewer dispatch. Native loading can supplement it, but cannot be its only correctness mechanism.

The persona compaction-generation ledger is separate from file-read dedup. Whether read pointers must be reinjected after compaction is an unverified integration question, not an established live failure. Test it before relying on that seam for mandatory knowledge. See S09–S15.

### F07. Discovery needs evidence categories tied to useful work

Current preflight should explicitly capture: repository/fork/upstream identity, launch and worktree root, dirty/staged/untracked boundaries, existing instruction scopes, declared command working directories, generated/source ownership, prerequisites, and task-specific uncertainties. Avoid credentials in remote URLs or local environment values.

Current root-only release discovery is insufficient as a general multi-package strategy; this repository itself has distinct plugin manifests. Do not infer a publishing convention from one package file. Existing ADR summaries also need an explicit report producer for decision bodies; the current assignments do not clearly establish that evidence path. An upstream accepted decision is evidence of upstream policy, not an automatically approved new codeArbiter decision.

Initialization is not side-effect-free: the helper manages local exclusions/hooks, and active session-start can launch a remote-tracking fetch and update refresh (`session-start.py:214–227`, `1182–1205`, `1273–1277`). An event profile must establish permitted effects rather than silently assuming internet access or treating all startup behavior as passive reading. No arbitrary project install/test/deploy script should run during discovery.

## 4. Output inventory and maintenance obligations

The following are existing outputs or later consumers, not newly approved artifact kinds. “Legacy” means the current accepted Markdown/helper workflow remains authoritative for its own domain; it does not authorize arbitrary new writes or overwrite of human content.

| Output | Purpose and current semantic/write owner | Actual consumer and load trigger | Validation, evidence and freshness | Recommendation and maintenance cost |
|---|---|---|---|---|
| CONTEXT.md | Helper owns activation scaffold; context workflow synthesizes body; initialized marker is lifecycle state | Startup/status and task preflight | Frontmatter/marker handling plus broad final checks; body facts come from reports, not marker existence | Keep. Validate activation separately from overview truth. Scope refresh; never clear initialization to rescan. Low routine cost, high lifecycle sensitivity. |
| tech-stack.md | Legacy declared technologies, prerequisites and commands | Task authors, TDD/debug and technology routing | Evidence from manifests/CI; declaration is not successful execution. Provenance covers only enrolled dependencies | Keep. State command cwd and declared/verified distinction at consumption. Revisit only changed command inputs. |
| coding-standards.md | Legacy project-specific conventions | Authors/reviewers/TDD and reference map | Patterns inferred from code require different status from approved constraints | Keep. Preserve repository conventions; prevent observations becoming “must” rules. Reconfirm only changed applicable conventions. |
| security-controls.md | Legacy security descriptions and approved constraints | Relevant security review, references and file-scoped injection | No secrets; approved policies and observed implementations must be separated | Keep thin. Task-relevant revalidation; no unrelated security encyclopedia. |
| code-map.md | Legacy coarse concern-to-path navigation synthesized from scout C | Feature/fix/TDD before exploration; not universal startup payload | Existing count/wrapping lint and per-document provenance; no full byte or membership coverage | Improve consumption and size/freshness diagnostics first. No duplicate inventory. Moderate refresh cost at actual boundary changes. |
| .provenance/*.json | Supporting evidence identity through `_provenancelib` | Drift check, commit healing and advisory read injection | Atomic writes and safe-path handling; loose record validation, cited-path-only invalidation, hash-only rebaseline | Retain store. Repair per-document healing and coverage diagnostics. New instruction consumers need stricter semantics, not blind reuse as approval. |
| open-questions.md | Unresolved questions and user-approved deferrals | Startup/status and planning | Explicit answers/deferrals; not a repository-fact substitute | Keep. Batch related questions; separate task blockers from unrelated deferred unknowns. |
| open-tasks.md | Canonical task board through taskwrite helper | Dispatch, status and commit/task workflow | Helper-only mutation and stable task identity | Preserve. No raw board rewrite during onboarding, no duplicate task store. Existing task maintenance cost. |
| done-tasks.md | Append-only completion history through archive helper | History/archive consumers | Initialized with a valid header; protected append-only behavior | Preserve even when empty. Not disposable generated context. |
| overrides.log | Append-only audit record under override workflow | Audit and statusline/checkpoint calculations | Header-only is valid; zero entries is distinct from an empty file | Preserve all prior bytes. Never truncate or re-create to satisfy onboarding checks. |
| last-checkpoint | Checkpoint boundary, scaffold starts at zero | Checkpoint and statusline consumers | Helper-owned value, not an onboarding approval | Preserve; do not reset during refresh. |
| release-targets.md | Release configuration with dedicated marker-gated authoring | Release workflow | Candidate detection must be separated from publishing authorization; protected state rules apply | Keep when applicable. Explicit unresolved configuration is better than an invented release policy. |
| decisions/ summaries | Decision-lifecycle owner, with upstream documents as evidence | ADR readers, planners and applicable governing pointers | Source/status/approval distinction essential; input coverage must be explicit | Preserve originals and authority. Do not manufacture newly accepted ADRs from summaries. |
| .markers/ and hook indexes | Internal transient state/receipts/dedup | Hooks/helpers | Identity/freshness scoped to their contracts, not human approval | Do not promote to user-facing canonical policy or eager instructions. |
| Later spec/plan pair | Engine-owned typed artifacts, or valid legacy pair under compatibility rules | Full contribution planning, implementation, review and verification | Closed schemas, bounded operations, real authority receipts and verification | Keep intact. No fallback Markdown for unavailable typed capability; no automatic migration. |
| Later small-lane triage | Existing bounded task lane | Small changes and commit review | Existing small-lane eligibility and authorization | Preserve; onboarding should not force every useful first task into a large project plan. |

PRODUCT, ARCHITECTURE and greenfield sprint-cut documents are not required brownfield outputs. Do not create them merely to fill a dashboard or achieve a larger file count. The pinned tracked repository contained no root/nested AGENTS.md or CLAUDE.md instruction files; that observation does not describe a future consumer fork or user/managed instructions.

## 5. Scout contract proposal

Before adaptive dispatch, keep six logical domains and make report validation executable. Each report needs an immutable assignment/attempt identity, snapshot binding, domain and path scope, explicit search coverage, excluded areas, outcome, evidence findings, contradictions and resource accounting. This is a bounded evidence envelope, not a new authority-bearing policy file.

Use distinct outcomes: `observed`, `not_applicable`, `not_found_in_scope`, `not_inspected`, `ambiguous`, `failed`, and `oversize`. A zero-result search does not establish not-applicable. A failed or uninspected assignment does not count as completed coverage. Require the reason and searched scope for negative outcomes; permit unknown confidence where no claim can be responsibly made.

The orchestrator can validate report shape and reconcile compatible evidence; it cannot resolve missing truth by inventing facts or secretly breaking report-only synthesis. Contradictions go back to an independent bounded scout. Only the synthesizer proposes reusable guidance, the maintainer decides normative/ownership questions, validators check closed structure and evidence identities, and sanctioned helpers write authorized records. Scouts never compete to write instruction files.

For small repositories, all six logical coverage outcomes can be brief, with a shared immutable inventory avoiding redundant listing and hashing. For large independent packages, subdivide by actual command/test/source boundaries; each child remains isolated and the join must account for the complete original assignment. A no-database repository gets a justified negative report, not a deleted scout or invented database policy.

Scheduling and model choice are separate from completeness. Bound concurrency and aggregate token/latency budgets across every attempt, including failed scouts and synthesis. Retain required fresh contexts. Use approved per-host model mappings; do not translate Claude's `haiku` label into an invented Codex tier. A host without the required isolation or containment remains blocked for this workflow.

## 6. Host-loading evidence and remaining qualification

The machine observed was Windows AMD64 with Claude Code 2.1.282 and Codex CLI 0.145.0. The eleven probes used isolated temporary configuration directories and a local synthetic provider. Actual client request bodies, not an agent's report of what it read, were inspected. Every run deliberately stopped with HTTP 400 before real inference. One scripted response requested Read of two harmless fixture files so the next request could demonstrate lazy loading.

| Probe | Observed outgoing context |
|---|---|
| Claude root or nested launch with only AGENTS.md | No synthetic AGENTS content; repeated with hooks not disabled and with a Git root. Cause not determined. |
| Claude root CLAUDE.md plus adjacent AGENTS.md | CLAUDE content once; AGENTS absent in that profile. |
| Claude explicit import | Imported AGENTS and root CLAUDE content both present once. |
| Claude nested launch | Root and applicable nested CLAUDE content present. |
| Claude root launch, then client reads two subtrees | Root initially; both respective nested CLAUDE contents present in the next request. |
| Codex root launch | Root AGENTS present; nested AGENTS absent. |
| Codex nested launch | Root and nested AGENTS present. |
| Codex nested override | Root plus override present; same-directory ordinary AGENTS absent. |

In one Claude fixture the instruction-containing text component grew from 809 to 1,004 UTF-8 bytes with the import. These figures include client wrappers; they are not tokenizer counts or a general savings estimate. Codex fixture components were 170 bytes at root, 202 for the nested chain, and 197 with the override. Comparing those numbers across clients would be misleading. The ledger retains per-request observations.

Codex warned that it would not create PATH helper aliases under the temporary CODEX_HOME. This limits tool-execution qualification, not the observed outgoing instruction contents. No real provider, subagent, or task result was qualified by these probes. Native Claude AGENTS availability remains unresolved in this isolated profile, not disproved universally.

**Official-documentation qualifications:** Current Claude documentation describes native AGENTS support from 2.1.277 with availability/settings caveats, and a default that prefers ancestor CLAUDE files over AGENTS. Imports expand content rather than making it lazy. Codex documents a launch-directory ancestor chain, per-directory override precedence, and a default 32 KiB project-instruction budget. Do not infer portable cross-subtree delivery from filename existence. Official sources: Claude memory documentation and Codex AGENTS guidance listed at the end.

The next qualification matrix must include restart/compaction, custom and built-in subagents, scoped-rule frontmatter failures, ignored/excluded instructions, unavailable native capabilities, imports and escapes, root/nested launch, cross-subtree tasks, override divergence, additional directories and the actual supported OS/path/provider cells. Use host loading receipts where available, captured effective input, and independent task tests as separate evidence layers. No global configuration change is required or authorized to make a candidate look portable.

## 7. Conditional placement policy and rejected alternatives

Start with no new file. A candidate must satisfy every test below: a real task-relevant semantic boundary; unique non-obvious guidance supported by evidence; inadequate existing instruction/map coverage; a defined recipient/load trigger; safe ownership; bounded effective context; and a plausible measured maintenance-adjusted benefit. Record why here, which tasks, unique content, source evidence, missing alternative coverage and avoided future exploration. Directory count or size cannot substitute for any test.

In this repository, `core/artifacts/` is a plausible candidate because it is a separate Go module with a particular command context. `core/surface/` is another because source edits generate multiple host distributions. These are candidates, not approved placements: the current map and source README may already supply sufficient guidance. Do not create one file per generated plugin copy, a policy for every test folder, or a database instruction file merely because a directory resembles one.

| Alternative | Decision |
|---|---|
| Improved existing map, provenance diagnostics and task-time selection | Preferred first implementation. Changes consumers and validation without inventing another persistent index. |
| Thin root pointers | Useful only for genuinely universal missing guidance. A pointer is not proof that the target was loaded. |
| A few scoped native files | Conditional pilot after placement, ownership, freshness and host qualification. |
| Claude path-scoped rules | Potentially useful for cross-cutting scopes; only as a qualified projection, not a portable universal canonical format. |
| Paired AGENTS and CLAUDE everywhere | Reject. Duplication and loading divergence can erase the intended advantage. |
| Native auto-memory or unconstrained host init as canonical project policy | Reject for governed reusable records; authority and deterministic mutation are insufficiently controlled for this purpose. |
| No new instructions | Correct when existing guidance plus retrieval is sufficient, particularly already-instructed or one-off small repositories. |

## 8. Proposed governed contract, not an existing schema

A scoped-guidance pilot would be a separately approved `repository-guidance` kind in the existing internal engine. Use one canonical JSON record per stable guidance identity, with host-readable Markdown as checked derived views. JSON is chosen for a small closed machine model, not as a container for arbitrary Markdown. This needs a representation-aware engine path; it is not an approved migration of existing context files.

| Field family | Requirement and reason |
|---|---|
| Version and stable ID | Required. Closed per-kind version dispatch; identity survives a scope move. |
| Scope and task kinds | Required, normalized repository-relative directory plus bounded task enum. |
| Snapshot and evidence references | Required structure; unknown values allowed in drafts. Reference existing provenance rather than maintaining a second hash database. |
| Entries | Required bounded list of typed command, source/edit-target relationship, read-before pointer, or approved-constraint reference. No arbitrary `instructions` string. |
| Confidence and verification | Required distinction per claim/command. Declared is not executed; verified requires a trusted execution receipt. |
| Ownership and host views | Required empty-or-explicit view list. Each target needs approved ownership and a qualified loader profile. |
| Lifecycle and approval reference | Engine-controlled. Draft can lack approval; publishing cannot. A caller cannot set an arbitrary `approved:true`. |
| Freshness dependencies | File identities plus selective membership dependencies for claims affected by additions/removals. Reuse/version existing provenance; unknown coverage blocks publication, not drafting. |

Commands contain argv, working directory and only reviewed non-secret environment requirements. The engine never executes them. Read-before and constraint entries point at canonical owners; v1 should avoid free-form normative paragraphs. An architectural invariant without a suitable approved source remains a proposed decision, not a generated rule.

### Illustrative draft record

This example is deliberately **not publishable**: its provenance binding and approval are unresolved. It shows a declared command from `tools/build-artifacts.py:100–115`; that command was not run in this assessment. Empty views mean no consumer file is authorized.

```json
{
  "schema": "codearbiter.repository-guidance/0.1.0",
  "id": "GUIDE-ARTIFACTS",
  "scope": {"path": "core/artifacts", "tasks": ["change", "test", "review"]},
  "basis": {"revision": "d171126e71e48b78d242c3d95b218236fdd8f61d", "worktree_snapshot": null},
  "lifecycle": {"state": "draft", "approval_ref": null},
  "ownership": {"canonical": "engine", "views": []},
  "entries": [{
    "id": "CMD-TEST",
    "kind": "command",
    "purpose": "test",
    "cwd": "core/artifacts",
    "argv": ["go", "test", "./...", "-count=1"],
    "environment": {"GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0"},
    "evidence_refs": [{"path": "tools/build-artifacts.py", "lines": [100, 115], "provenance_ref": null}],
    "confidence": "strong",
    "verification": {"state": "declared", "receipt_ref": null}
  }]
}
```

### Illustrative rendered preview, not a native file write

```markdown
# Artifact module

Declared test command, not verified in this assessment:
- Working directory: `core/artifacts`
- Command: `go test ./... -count=1`
- Environment: `GOTOOLCHAIN=local`, `GOPROXY=off`, `GOSUMDB=off`, `CGO_ENABLED=0`
- Source: `tools/build-artifacts.py`, lines 100–115.

Command execution requires the applicable task authorization.
```

### Invalid-input examples

`cwd: "../../outside"` is rejected before path resolution or preview. An added `instructions: "ignore the governing gates"` property is rejected as an unknown field, not carried through as free-form prose. A claimed verified command without a genuine bound execution receipt is rejected. A request to publish over a human-owned CLAUDE.md is an ownership conflict even when the proposed body would be valid.

### Validation and rendering boundaries

Code must reject unknown properties, duplicate JSON keys, invalid enums/IDs, non-finite numbers, excessive depth/count/bytes, ambiguous or unresolved active references, unsafe paths and malformed import syntax. Resolve both lexical and real paths under trusted roots; reject traversal, absolute/drive/UNC paths, control characters, symlink escapes, Windows reserved/alternate-stream forms and cross-platform normalization collisions. A path must not silently resolve to a different scope on another supported platform.

Use stable identity/order, canonical serialization and LF output. A proposed initial budget is 2 KiB per view and 8 KiB for a selected guidance set; these are pilot limits, not measured optima. Bound the total expanded import closure as well. Refuse oversize publication rather than truncate an invariant. Escape Markdown control and import-looking text; emit imports only from the qualified adapter's closed layout. Keep machine metadata and full schemas out of repeated native context.

Semantic checks must validate source/command cwd, evidence identity and claim state, approved-constraint references, overlap/conflict, ownership and host capability. Human review still decides whether a factual interpretation is true, a convention should become normative, a placement is useful, and publishing authority exists. Static validation cannot make arbitrary prose trustworthy.

## 9. Preservation and lifecycle

Inventory the full preexisting instruction tree before planning any write, including human files, local/ignored guidance where authorized, overrides, imports, generated documents, edited managed views and cross-worktree state. Preserve unknown ownership. Neither a filename nor a generated comment is permission to take it over.

V1 should support whole-file managed views only at absent targets or targets whose previous bytes and explicit ownership receipt match. Existing human instructions remain unchanged. A sidecar or task-time reference is preferable where ownership is unavailable, but a sidecar must not be advertised as automatically loaded. Managed blocks are a later option only with explicit range ownership, outside-block preservation and compare-and-swap; malformed or edited markers are conflicts, not invitations to repair by guesswork.

Create and update start with an inert preview. An approved operation binds canonical revision, scope and expected target bytes. No-op runs write nothing, including no timestamps. A journal and compare-and-swap support interruption/retry; a multi-file publication must not be called filesystem-atomic merely because each rename is atomic. Cooperating sessions need a consistency check before using a partially published set.

A human edit, concurrent branch update or unexpected target stops the write and preserves bytes. Rollback restores only matching engine-owned previous versions; it must not undo a subsequent human change. Removal deletes only unchanged owned views and explicitly owned import references, preserving unrelated files and canonical history.

On moves/deletions, retire or rebind stable guidance IDs after evidence review; never leave old scoped files active. On upstream merges, compare both cited-file identities and relevant scope membership. Bind validation to the worktree snapshot, not just a branch name or HEAD. A changed digest marks a dependency for review; re-baselining cannot itself restore semantic validity. Unknown or failed freshness checks produce an explicit incomplete state.

Initialization and refresh are separate operations. Completion writes the initialized marker last; refresh never resets it. Repair preserves valid state and only regenerates affected owned outputs. Schema changes require per-kind compatibility and upgrade approval; old clients must report unsupported capability rather than reinterpret a new model or overwrite it.

## 10. Bounded greenfield reuse

Reuse typed evidence and guidance only for decisions and structures that exist. Approved intended architecture can inform an initial root pointer while remaining distinguishable from implemented facts. An empty repository has no basis for speculative nested guidance.

The first real manifest, first implementation, or new command/test boundary should trigger selective acquisition through the existing work/refresh lifecycle. The executed empty-provenance counterexample shows why hash-only healing is insufficient for this transition. Add bootstrap acquisition, not a new greenfield framework. Deeper placement still passes the same policy and may yield zero files.

## 11. Evaluation designed to reject scoped guidance

Compare A, current onboarding; B, corrected onboarding with better existing-map/task-time retrieval; and C, B plus opt-in scoped guidance. Hold snapshots and tasks constant. Attribute shared correctness repairs to B rather than crediting C for unrelated fixes. Use already-instructed, tiny, multi-package and infrastructure-only/no-database repositories, and include a case where repeated use is too limited to amortize generation.

Run first use, repeated fresh sessions and changed-repository use. Isolate memory and fixture configuration; record model/provider/version, actual effective settings, cache state and run order. Counterbalance task/arm order and retain independently judged task outcomes. Do not grade success by asking the model whether it read a file.

| Measurement | Required evidence |
|---|---|
| Cold onboarding | Wall/critical-path latency plus every scout's input/output/cache tokens, retries and synthesis costs |
| Human friction | Questions, deferrals, approvals and avoidable interruptions, separated by task relevance |
| Effective context | Actual startup and scoped injected content, duplication and true tokenizer/provider usage where available |
| Subsequent exploration | Searches, files/bytes reread, rediscovered commands and source-boundary mistakes |
| Task correctness | Passing relevant tests, independent review, missed constraints, escaped defects and inappropriate scope expansion |
| Maintenance | Stale claims, needed refresh work, human edits/conflicts, instruction churn and added tracked bytes |
| Amortization | Onboarding + repeated task costs + repository-change maintenance for the same number of useful contributions |
| Money | Separate accounting using actual model identifiers, usage/cache evidence and dated pricing; no invented savings |

Required deterministic fixtures: already-instructed repository; tiny project; multiple independent packages; infrastructure-only/no database; conflicting evidence; not-applicable versus not-found; partially failed scout; oversize scope; malformed closed model; zero-change repeated runs; human edits; interrupted/concurrent writes; stale/moved/deleted paths; newly added boundary inputs; unsafe paths/imports; branch/worktree differences; supported schema upgrade and unsupported downgrade. Host fixtures additionally cover root/nested starts, cross-subtree reads and tasks, restart/compaction, subagents, existing mixed instruction trees, overrides, disabled features, imports, rule parse failures and supported platform/path cells.

Keep four result classes separate: static validation, deterministic renderer/storage tests, actual host-loading integration, and real task behavior. The current 335 passing focused tests/checks plus surface parity do not substitute for a complete onboarding or live task run. No amortized token or dollar savings were measured here.

## 12. Implementation slices and stop conditions

| Slice | Change, reason and dependency | Completion evidence | Rollback boundary |
|---|---|---|---|
| E0: installed exercise capability | Finish the existing #870 channel work, then establish the exact supported Claude environment; qualify Codex separately. This precedes new full-lane contribution reliance. | Exact installed bytes; native capability; required resources/hooks/trust; real isolated scout dispatch; one authorized bounded contribution through verification/review/commit preflight. | Revert only the channel change or install a separately approved qualified version. Never bypass typed-artifact gates or enable fallback artifacts. |
| E1: truthful lifecycle | One current procedure owner; file-specific invariants; marker last; partial repair and initialized refresh; confidence normalization; preserve all required isolated reports. Coordinate route edits with #854. | Regressions fail before and pass after; header-only logs/boards, partial initialization, initialized refresh, preserved human edits, all-host generated parity. | Revert this bounded lifecycle change without deleting valid context or clearing the initialized marker. |
| E2: reuse existing context | Per-document conflict healing, incomplete-coverage reporting, selective membership acquisition, size diagnostics and explicit task-time reference selection. No new native instruction file by default. | Counterexamples corrected, no unrelated rescout, author/reviewer packets observed, no-op/diff bounds, map-only task evaluation. | Disable new advisory selector/diagnostics without removing canonical project records or weakening work gates. |
| P1: optional governed pilot | Approved per-kind feature for non-HTML guidance, closed model and bounded render/write lifecycle; qualify loader profiles. Depends on E0–E2 baseline and separate authority approval. | Static/semantic/host/negative/recovery evidence, untouched existing files, successful no-op behavior, independently correct tasks, demonstrable benefit over B. | Keep kind disabled by default; remove only unchanged owned projections through reviewed rollback; preserve existing canon. |
| G1: greenfield reuse | Reuse approved machinery only after actual boundaries exist. | Intended versus implemented distinction and first-manifest acquisition fixture; legitimate zero-file empty repository. | Stop generation without undoing approved project decisions or actual implementation. |

E0 install qualification, E1 lifecycle regression design and E2 baseline measurement can proceed in parallel where they do not edit the same owners. Coordinate shared context-creation/status/init edits before merge. Host-loading fixture development and placement evaluation can also proceed independently; publication and new-kind rollout cannot skip their dependencies.

## Do not change

Preserve scout isolation/report-only synthesis and existing required coverage until a replacement contract is separately qualified. Preserve human approval, small/full-lane eligibility, TDD, independent review, verification, commit/branch/release gates and fail-closed typed capability behavior. Preserve task-helper and append-only owners, valid legacy artifacts and accepted ADR authority. Preserve canonical source-to-generated ownership. Preserve repository-specific instructions and conventions. Do not introduce an always-loaded schema, second context database, new public command, dynamic renderer service, automatic instruction-file takeover, farm enablement, or global settings requirement.

## Exit decision

Before the exercise, require a qualified installation plus truthful, resumable initialization/refresh and a bounded first contribution that consumes the existing context. Keep automatic scoped instruction generation off. Proceed with a guidance pilot only when it preserves current authority and human files, has observable loading on declared host profiles, handles stale/concurrent/interrupted state, and produces better maintenance-adjusted task outcomes than the improved map-only baseline. A pilot that produces no advantage should be rejected rather than expanded.

## Source index

The machine-readable source index in `evidence-ledger.json` identifies S01–S35 with pinned URLs. Source paths and line references throughout this report refer to the exact inspected revision, not a moving branch.

Official host documentation revalidated September 25, 2026:
- Claude project instructions: `https://code.claude.com/docs/en/memory`
- Claude subagents: `https://code.claude.com/docs/en/sub-agents`
- Claude hook observations: `https://code.claude.com/docs/en/hooks`
- Codex AGENTS guidance: `https://learn.chatgpt.com/docs/agent-configuration/agents-md`

These documents describe supported behavior; the ledger separately records what was actually observed in the restricted local probes. Full native host behavior, task correctness, unknown exercise settings and measured cost benefit remain unqualified where explicitly listed.
