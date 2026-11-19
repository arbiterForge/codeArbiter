# Machine and transition accountability

Every one of the 287 audited families and 1,748 baseline rows remains in the corpus. The original table is unchanged under audit/. The JSON transition coverage file copies each full baseline row and attaches planned ownership, work and evidence fields. None is marked newly tested.

Source intersection is an impact-review hint. It does not assert that every transition in a large file changes. Preserve unmodified edges and record each deliberate changed edge. Pure parsers and model-guided workflows can use proportionate conformance review; runtime claims require meaningful runtime evidence.

| Machine | Name | Kind | Rows | Owner | Work / closure tasks |
|---|---|---|---:|---|---|
| WF-01 | Outcome routing and retained user authority | model-guided | 4 | hooks-workflows | HW-27 |
| WF-02 | Conflict escalation | model-guided | 2 | hooks-workflows | HW-06, HW-13, HW-27 |
| WF-03 | Feature triage and resume | model-guided | 7 | hooks-workflows | HW-13, HW-27 |
| WF-04 | Design choice and SMARTS rationale | model-guided | 4 | hooks-workflows | HW-13, HW-27 |
| WF-05 | Plan construction, execution and revision | model-guided | 6 | hooks-workflows | HW-06, HW-13, HW-27 |
| WF-06 | TDD obligations and proof | model-guided | 6 | hooks-workflows | HW-13, HW-27 |
| WF-07 | Diagnosis and debug packet handoff | model-guided | 7 | hooks-workflows | HW-07, HW-27 |
| WF-08 | Fix, chore, refactor and spike ownership | model-guided | 4 | hooks-workflows | HW-27 |
| WF-09 | Parallel units and review verdict | model-guided | 6 | hooks-workflows | HW-08, HW-09, HW-20, HW-27 |
| WF-10 | Checkpoint and audit report persistence | model-guided | 4 | hooks-workflows | HW-13, HW-27 |
| WF-11 | Commit preparation and commit aftermath | model-guided | 7 | hooks-workflows | HW-10, HW-12, HW-13, HW-17, HW-27 |
| WF-12 | Finish, PR and merge selection | model-guided | 6 | hooks-workflows | HW-06, HW-13, HW-18, HW-27 |
| WF-13 | PR checks watcher | model-guided | 3 | hooks-workflows | HW-18, HW-27 |
| WF-14 | Terminal finding harvest | model-guided | 4 | hooks-workflows | HW-10, HW-12, HW-13, HW-14, HW-27 |
| WF-15 | ADR authoring, acceptance and evidence status | model-guided | 5 | hooks-workflows | HW-27 |
| WF-16 | Decision variance and arbitration | model-guided | 5 | hooks-workflows | HW-27 |
| WF-17 | Scaffold, activation and initial context population | model-guided | 8 | hooks-workflows | HW-10, HW-16, HW-27 |
| WF-18 | Greenfield decomposition interview and candidate promotion | model-guided | 6 | hooks-workflows | HW-27 |
| WF-19 | Context refresh, provenance and format ownership | model-guided | 6 | hooks-workflows | HW-06, HW-10, HW-27 |
| WF-20 | Selected work interface and status reads | model-guided | 4 | hooks-workflows | HW-14, HW-27 |
| WF-21 | Worktree creation, integration and cleanup | model-guided | 5 | hooks-workflows | HW-27 |
| WF-22 | Standup synchronization and old-work archival | model-guided | 4 | hooks-workflows | HW-14, HW-27 |
| WF-23 | Tribunal source-bound audit coordination | model-guided | 8 | hooks-workflows | HW-19, HW-27 |
| WF-24 | Overrides and candidate-bound safety records | model-guided | 4 | hooks-workflows | HW-17, HW-27 |
| WF-25 | Dependency adoption versus ephemeral tooling | model-guided | 4 | hooks-workflows | HW-09, HW-20, HW-27 |
| WF-26 | Secret, crypto and threat-model assessment | model-guided | 4 | hooks-workflows | HW-17, HW-27 |
| WF-27 | Release target selection and declaration backfill | model-guided | 5 | hooks-workflows | HW-27 |
| WF-28 | Release preparation and dry-run | model-guided | 8 | hooks-workflows | HW-27 |
| WF-29 | Hosted release candidate, publication and provenance | model-guided | 10 | hooks-workflows | HW-27 |
| WF-30 | Release incident recovery and immutable published identity | model-guided | 4 | hooks-workflows | HW-27 |
| WF-31 | Farm workflow qualification, selection and consumption | model-guided | 7 | hooks-workflows | FARM-R01, HW-27 |
| WF-32 | Private helper selection and invocation | model-guided | 3 | hooks-workflows | PI-D06, HW-27 |
| WF-33 | Posture, actual enforcement and host policy | model-guided | 4 | hooks-workflows | PI-D06, HW-27 |
| WF-34 | Diagnostics, prune settings and statusline configuration | model-guided | 5 | hooks-workflows | HW-14, HW-27 |
| WF-35 | Command compatibility clock and intentional retirement | model-guided | 4 | hooks-workflows | HW-21, HW-27 |
| RT-01 | Statusline render, theme transaction and degraded output | implemented | 6 | hooks-workflows | HW-27 |
| RT-02 | Usage identity normalization, merge and pricing | implemented | 4 | hooks-workflows | HW-27 |
| CC-01 | Codex fixture and durable characterization evidence | implemented | 5 | hooks-workflows | HW-27 |
| CC-02 | Isolated live resource probe and receipt classification | implemented | 9 | hooks-workflows | HW-27 |
| CC-03 | App-server JSONL protocol and shutdown | implemented | 7 | hooks-workflows | HW-27 |
| CC-04 | Candidate package snapshot and resource closure | implemented | 6 | hooks-workflows | HW-27 |
| CC-05 | Constrained Markdown link parser context | implemented | 6 | hooks-workflows | HW-27 |
| N01 | Operation admission, lock ownership and store availability | implemented | 7 | native | NT-03, NT-06, NT-08, NT-10, NT-12 |
| N02 | Journaled transaction and operation identity | implemented | 8 | native | NT-10, NT-12 |
| N03 | Recovery and recovery conflicts | implemented | 5 | native | NT-10, NT-12 |
| N04 | Artifact representation, version and canonical identity | implemented | 4 | native | NT-05, NT-09, NT-12 |
| N05 | Artifact governance and semantic revision | implemented | 4 | native | NT-09, NT-11, NT-12 |
| N06 | Stable symbol lifecycle | implemented | 4 | native | NT-05, NT-12 |
| N07 | Readiness, open decisions and criterion coverage | implemented | 4 | native | NT-09, NT-05, NT-12 |
| N08 | Plan–spec binding currency | implemented | 3 | native | NT-09, NT-11, NT-12 |
| N09 | Ordinary task progress | implemented | 5 | native | NT-05, NT-09, NT-12 |
| N10 | Strict receipted task review, reconciliation and acceptance | implemented | 5 | native | NT-09, NT-11, NT-12 |
| N11 | Dependency invalidation and advisory scheduling | implemented | 4 | native | NT-09, NT-12 |
| N12 | Prerequisite observation versus historical certification | implemented | 4 | native | NT-05, NT-09, NT-12 |
| N13 | Caller reported check history and applicability | implemented | 4 | native | NT-05, NT-06, NT-09, NT-12 |
| N14 | Check-conflict reconciliation | implemented | 5 | native | NT-09, NT-06, NT-12 |
| N15 | Immutable observation, source, event and receipt chain | implemented | 4 | native | NT-04, NT-11, NT-12 |
| N16 | Verification-input snapshot and output recognition | implemented | 4 | native | NT-02, NT-12 |
| N17 | Completion review selection and workspace closure | implemented | 5 | native | NT-02, NT-04, NT-11, NT-12 |
| N18 | Atomic initial sprint pair approval | implemented | 2 | native | NT-12 |
| N19 | Delegated SMARTS method change and reset closure | implemented | 2 | native | NT-12 |
| N20 | Bounded retrieval, continuation and completed-delivery ticket | implemented | 4 | native | NT-06, NT-09, NT-12 |
| N21 | Context ownership, inert preview and ordinary apply | implemented | 6 | native | NT-02, NT-12 |
| N22 | Context initialization finalization | implemented | 3 | native | NT-12 |
| N23 | Knowledge HTML ownership and migration cutover | implemented | 3 | native | NT-12 |
| N24 | Knowledge three-way merge | implemented | 3 | native | NT-12 |
| N25 | Knowledge/decomposition claim, question, run and promotion states | implemented | 5 | native | NT-12 |
| N26 | Paired legacy spec/plan migration and conservative rollback | implemented | 3 | native | NT-05, NT-12 |
| N27 | Rendered view repair and export | implemented | 3 | native | NT-03, NT-06, NT-10, NT-12 |
| N28 | Project/work ownership, origin deduplication and legacy adoption | implemented | 4 | native | NT-07, NT-12 |
| N29 | Local work lifecycle and independent delivery observation | implemented | 7 | native | NT-07, NT-12 |
| N30 | Provider, Project and transition-map generations | implemented | 4 | native | NT-12 |
| N31 | GitHub issue effect intent and delivery uncertainty | implemented | 6 | native | NT-12 |
| N32 | GitHub Project item and field effect | implemented | 5 | native | NT-12 |
| N33 | Mapped local-to-remote coordination | implemented | 11 | native | NT-12 |
| N34 | Typed farm projection, seal and dispatch validation | implemented | 5 | native | NT-12 |
| N35 | Derived project/cycle/work views and membership pagination | implemented | 3 | native | NT-07, NT-12 |
| N36 | Operation-scoped evidence memo | implemented | 3 | native | NT-06, NT-12 |
| N37 | CLI execution versus response acknowledgement | implemented | 4 | native | NT-03, NT-10, NT-12 |
| N38 | Typed context claim, command evidence and provenance freshness | implemented | 5 | native | NT-02, NT-12 |
| N39 | Delegated qualitative decision admission | implemented | 3 | native | NT-12 |
| hooks:activation | Project activation, initialization and scaffold recovery | implemented | 8 | hooks-workflows | HW-27 |
| hooks:host | Host selection, authenticated package identity and worktree roots | implemented | 6 | hooks-workflows | HW-03, HW-27 |
| hooks:mode | Session mode intent, backed effective mode and exact control tokens | implemented | 7 | hooks-workflows | HW-01, HW-02, HW-14, HW-16, HW-27 |
| hooks:mode-audit | Owed mode/dev audit rows and legacy session cleanup | implemented | 8 | hooks-workflows | HW-01, HW-02, HOST-D01, HW-14, HW-16, HW-27 |
| hooks:persona | Persona delivery, deduplication and compaction generation | implemented | 6 | hooks-workflows | HW-01, HW-02, HW-14, HW-16, HW-27 |
| hooks:startup | Active-session startup, stage briefing and daily standup delivery | implemented | 7 | hooks-workflows | HW-10, HW-11, HW-14, HW-15, HW-16, HOST-D01, HW-27 |
| hooks:read-context | Scoped read context injection, catalog generations and content authority | implemented | 6 | hooks-workflows | HW-27 |
| hooks:hook-admission | Native tool guards, activation, opaque operations and block side effects | implemented | 5 | hooks-workflows | HW-11, HW-27 |
| hooks:protected-state | Protected project paths, helper ownership and expiring authorizations | implemented | 7 | hooks-workflows | HW-17, HW-23, HW-27 |
| hooks:shell-parser | Shell mutation and Git intent classification | implemented | 5 | hooks-workflows | HW-17, HW-23, HW-27 |
| hooks:commit-gates | Commit candidate staging, sensitive-content binding and migration proof | implemented | 8 | hooks-workflows | HW-17, HW-23, HW-27 |
| hooks:security-producers | Security/migration marker production and attributed binary override | mixed | 4 | hooks-workflows | HW-17, HW-27 |
| hooks:push | Protected-ref and fast-forward Git push backstop | implemented | 5 | hooks-workflows | HW-17, HW-23, HW-27 |
| hooks:approval-single | Single-artifact approval arm, observed reply and cancellation | implemented | 6 | hooks-workflows | HW-27 |
| hooks:approval-pair | Paired spec/plan approval with durable submission recovery | implemented | 8 | hooks-workflows | HW-27 |
| hooks:prerequisite | User prerequisite arm, confirmation, capture and supersession | implemented | 7 | hooks-workflows | HW-27 |
| hooks:reconciliation | Frozen reconciliation prompt and recoverable native mutation | implemented | 8 | hooks-workflows | HW-11, HW-27 |
| hooks:reply-routing | Human reply normalization, code routing and AskUserQuestion observation | implemented | 7 | hooks-workflows | HW-27 |
| hooks:authority-request | Review/verifier request spool, terminal states and recovery | implemented | 7 | hooks-workflows | HW-08, HW-04, HW-11, HW-27 |
| hooks:verifier | Qualified command launch, output collection and host corroboration | implemented | 7 | hooks-workflows | HW-04, HW-08, HW-11, HW-27 |
| hooks:codex-review | Codex authority child launch, activity join, steering rejection and first final | implemented | 6 | hooks-workflows | HW-08, HW-04, HW-11, HW-27 |
| hooks:claude-review | Claude authority child pairing and independent review result | implemented | 6 | hooks-workflows | HW-08, HW-04, HW-11, HW-27 |
| hooks:debug-handoff | Stateless bounded debug packet validation | implemented | 4 | hooks-workflows | HW-07, HW-27 |
| hooks:native-client | Pinned native capability, bounded request execution and mutation recovery | implemented | 7 | hooks-workflows | HW-11, HW-25, DIST-M01, HW-27 |
| hooks:authoring-route | Inline/legacy/native authoring selection and current acceptance reads | implemented | 6 | hooks-workflows | DIST-M01, HW-25, HW-27 |
| hooks:context-writer | Assistive context preview, adoption, update and finalization | implemented | 6 | hooks-workflows | DIST-M01, HW-25, HW-27 |
| hooks:context-provenance | Context coverage, source identity, baseline drift and heal eligibility | implemented | 8 | hooks-workflows | HW-27 |
| hooks:context-snapshot | Bounded evidence membership, stable snapshots and dependency comparison | implemented | 6 | hooks-workflows | HW-27 |
| hooks:context-scout | Scout attempt admission, transport completion, subdivision and deterministic join | implemented | 6 | hooks-workflows | HW-27 |
| hooks:command-evidence | Declared command guidance, current execution binding and verification outcome | implemented | 6 | hooks-workflows | HW-27 |
| hooks:context-delivery | Task context selection, actor delivery receipts and bounded delivery retry | implemented | 6 | hooks-workflows | HW-27 |
| hooks:knowledge | Knowledge ownership, CAS edits, Markdown conversion and decomposition promotion | implemented | 10 | hooks-workflows | HW-10, HW-12, HW-13, HW-27 |
| hooks:work-owner | Work owner selection, durable identity and bounded context projection | implemented | 10 | hooks-workflows | HW-10, HW-12, HW-13, HW-15, HW-27 |
| hooks:taskwrite | Locked legacy task transition and archive-first recovery | implemented | 8 | hooks-workflows | HW-12, HW-15, HW-27 |
| hooks:work-adoption | Legacy board inventory preview and native work adoption | implemented | 3 | hooks-workflows | HW-27 |
| hooks:legacy-advisories | Board drift, lexical intent coverage and post-write review reminders | implemented | 7 | hooks-workflows | HW-27 |
| hooks:plan-file | Exact-byte legacy spec/plan compare-and-swap and truthful commit-point result | implemented | 5 | hooks-workflows | HW-11, HW-27 |
| hooks:append-conflict | Attributed append-only Git conflict union and rollback | implemented | 5 | hooks-workflows | HW-06, HW-27 |
| hooks:legacy-context-recovery | Fixed legacy code-map conflict inspection, selected side recovery and claim refresh | implemented | 5 | hooks-workflows | HW-27 |
| hooks:adr-lifecycle | ADR accepted obligations, implementation evidence and verified export eligibility | implemented | 8 | hooks-workflows | HW-27 |
| hooks:cleanup-eligibility | Branch/worktree delivery proof, authorized scope and unique-loss classification | implemented | 6 | hooks-workflows | HW-27 |
| hooks:cleanup-journal | Write-ahead deletion intent, guarded mutation and outcome reconciliation | implemented | 6 | hooks-workflows | HW-15, HW-27 |
| hooks:prune-plan | Transcript/Pi pruning policy, protected context and dry-run accounting | implemented | 6 | hooks-workflows | HW-22, HW-27 |
| hooks:prune-execute | Settled transcript admission, in-place write, backup restoration and cold-context nudge | implemented | 8 | hooks-workflows | HW-22, HW-27 |
| hooks:claude-accounting | Incremental usage evidence ingestion, replay, repricing and bounded catch-up | implemented | 8 | hooks-workflows | HW-27 |
| hooks:session-accounting | Session start/retention and observational child display lifecycle | implemented | 5 | hooks-workflows | HW-27 |
| hooks:pi-accounting | Pi ordered usage chunk acceptance and shard-first durable aggregation | implemented | 5 | hooks-workflows | HW-27 |
| hooks:git-install | Shared Git shim installation, owned registry and rollback | implemented | 6 | hooks-workflows | HW-16, HOST-D01, HW-27 |
| hooks:git-dispatch | Cross-host enforcer election and trusted executable negotiation | implemented | 7 | hooks-workflows | HOST-D01, HW-16, HW-27 |
| hooks:task-lock-exclusion | Local task-lock exclusion transaction and ownership-safe cleanup | implemented | 5 | hooks-workflows | HW-16, HOST-D01, HW-27 |
| hooks:advisory-runtime | Gate event logging, time-based stale-flow notice and babysit configuration | implemented | 5 | hooks-workflows | HW-11, HW-27 |
| hooks:update-notice | Per-host update cache, daily reservation and monotonic version merge | implemented | 6 | hooks-workflows | HW-27 |
| hooks:statusline-wiring | Owned statusLine install, refresh, backup restoration and spinner side effects | implemented | 7 | hooks-workflows | HW-05, HW-27 |
| hooks:doctor | Health check aggregation and declared-versus-live capability observation | implemented | 5 | hooks-workflows | HW-03, HW-27 |
| hooks:release-confirmation | Release build-command digest and confirmation freshness | mixed | 3 | hooks-workflows | HW-27 |
| hooks:tribunal-inventory | Read-only tribunal facts, host dispatch profile and unmeasured cost estimate | implemented | 3 | hooks-workflows | HW-27 |
| hooks:tribunal-run | Immutable source binding, append-only cursor, resumability and follow-up completion | implemented | 8 | hooks-workflows | HW-27 |
| hooks:tribunal-lock-leads | Tribunal stale-lock recovery, immutable leads and evidence-gated triage | implemented | 6 | hooks-workflows | HW-27 |
| hooks:tribunal-usage | Host-specific observed usage extraction and partial aggregation | implemented | 4 | hooks-workflows | HW-27 |
| hooks:pi-python-bridge | Closed Pi bridge routing, bounded hook execution and response translation | implemented | 7 | hooks-workflows | HW-14, HW-27 |
| hooks:pi-approval | Pi native-input approval handshake and exact pending-byte identity | implemented | 3 | hooks-workflows | HW-27 |
| hooks:codex-pretool | Codex hook payload admission and patch-file operation parsing | implemented | 6 | hooks-workflows | HW-14, HW-27 |
| hooks:display-git-probes | Non-authoritative branch and dirty-state display fallback | implemented | 3 | hooks-workflows | HW-27 |
| S01 | Pi session activation, ownership and degradation | implemented | 10 | pi | HW-14, PI-D02, PI-D04, PI-D05, PI-D06, PI-L01, PI-D07 |
| S02 | Pi final tool enforcement and permission transaction | implemented | 14 | pi | PI-D01, PI-D02, PI-D04, PI-D05, PI-D07 |
| S03 | Pi plan mode and revision-controlled file editing | implemented | 9 | pi | PI-D02, PI-D07 |
| S04 | Pi background job manager | implemented | 8 | pi | PI-D03, PI-D05, PI-D07 |
| S05 | Pi managed background containment, audit and health | implemented | 9 | pi | PI-D03, PI-D05, PI-D07 |
| S06 | Pi activity projection | implemented | 5 | pi | PI-D07 |
| S07 | Pi subagent dispatch and aggregate outcome | implemented | 8 | pi | PI-D01, PI-D02, PI-D04, PI-D05, PI-D06, PI-D07 |
| S08 | Pi private artifact approval process | implemented | 7 | pi | PI-C01, PI-D07 |
| S09 | Pi child RPC admission and runner protocol | implemented | 11 | pi | PI-D01, PI-D03, PI-D04, PI-D05, PI-D07 |
| S10 | Pi child environment and credential lifetime | implemented | 7 | pi | PI-D03, PI-D07 |
| S11 | Pi inference broker authorization and stream forwarding | implemented | 7 | pi | PI-D03, PI-D07 |
| S12 | Pi runtime identity and import admission | implemented | 5 | pi | HW-14, PI-C01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-D07, PI-L01 |
| S13 | Pi managed process trees and platform admission | implemented | 9 | pi | PI-D03, PI-D05, PI-D07 |
| S14 | Pi Python bridge process request lifecycle | implemented | 7 | pi | HW-14, PI-D07 |
| S15 | Pi usage extraction cursor and delivery acknowledgment | implemented | 6 | pi | HW-14, PI-D07 |
| S16 | Pi local audit append durability and approval dependency | implemented | 6 | pi | PI-D04, PI-D07 |
| S17 | Pi compaction proposal and host confirmation | implemented | 7 | pi | PI-D07 |
| S18 | Pi footer installation and serialized refresh | implemented | 7 | pi | PI-D06, PI-L01, PI-L02, PI-D07 |
| S19 | Pi sidebar manager and compositor ownership | implemented | 8 | pi | PI-L02, PI-D07 |
| S20 | Pi command ownership, notices and diagnostics | implemented | 6 | pi | PI-D06, PI-D07 |
| S21 | Pi source-checkout farm adapter | implemented | 4 | farm | Q-01 |
| S22 | Farm typed artifact admission and pinned engine execution | implemented | 7 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S23 | Farm run scheduler, dependency state and circuit breaker | implemented | 12 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S24 | Farm per-task author/gate/retry lifecycle | implemented | 14 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S25 | Farm best-of-N sample selection and cleanup | implemented | 8 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S26 | Farm commit, merge and moving-base retry | implemented | 9 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S27 | Farm HTTP worker transport and retry budget | implemented | 9 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S28 | Farm anti-gaming and mutation evidence | implemented | 12 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S29 | Farm subprocess timeout and containment result | implemented | 6 | farm | FARM-R02, Q-01 |
| S30 | Farm worktree and branch cleanup | implemented | 6 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S31 | Farm receipt publication and durable-output recovery boundary | implemented | 6 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S32 | Farm canary provider qualification | implemented | 7 | farm | DIST-M01, FARM-R01, FARM-R02, FARM-R03, HW-25, Q-01 |
| S33 | Farm safe file materialization | implemented | 5 | farm | Q-01 |
| S34 | GitHub work issue creation and issue-state delivery | implemented | 7 | hooks-workflows | HW-27 |
| S35 | GitHub issue adoption and reconciliation | implemented | 5 | hooks-workflows | HW-27 |
| S36 | GitHub project item membership delivery | implemented | 7 | hooks-workflows | HW-27 |
| S37 | GitHub project single-select field staging, CAS and recovery | implemented | 9 | hooks-workflows | HW-27 |
| S38 | GitHub mapped multi-target synchronization and PR observation | implemented | 6 | hooks-workflows | HW-27 |
| S39 | Legacy task board transitions and identity-preserving edits | implemented | 10 | hooks-workflows | HW-12, HW-27 |
| S40 | Legacy board archive and interrupted-copy recovery | implemented | 5 | hooks-workflows | HW-12, HW-27 |
| S41 | Legacy task harvest, triage and advisory diff classification | implemented | 7 | hooks-workflows | HW-12, HW-27 |
| S42 | Release target declaration, selection and first-adoption backfill | implemented | 7 | release-and-tooling | Q-01 |
| S43 | Release baseline, change-window and version derivation gates | implemented | 9 | release-and-tooling | Q-01 |
| S44 | Release publish classifier and exact-HEAD merge readiness | implemented | 9 | release-and-tooling | Q-01 |
| S45 | Release notes, assets and committed-source identity | implemented | 5 | release-and-tooling | Q-01 |
| S46 | Release pre-tag command runner and tree cleanliness | implemented | 9 | release-and-tooling | Q-01 |
| S47 | Sandbox Docker client request lifecycle | implemented | 7 | sandbox | SBX-C02, SBX-C03, Q-01 |
| S48 | Sandbox create and compensation sequence | implemented | 8 | sandbox | SBX-C01, SBX-C03, SBX-D03, Q-01 |
| S49 | Sandbox dependency-image cache and build fallback | implemented | 9 | sandbox | SBX-C01, SBX-C03, SBX-D01, SBX-D03, Q-01 |
| S50 | Sandbox network policy planning and enforcement | implemented | 6 | sandbox | SBX-D03, Q-01 |
| S51 | Sandbox Claude-inside admission, network firewall and teardown | implemented | 6 | sandbox | SBX-C03, SBX-D04, Q-01 |
| S52 | Sandbox exec and copy side effects | implemented | 6 | sandbox | SBX-C02, Q-01 |
| S53 | Sandbox resource discovery, destroy and prune verification | implemented | 7 | sandbox | SBX-C03, SBX-D02, Q-01 |
| S54 | Sandbox CLI cancellation and command outcome mapping | implemented | 6 | sandbox | SBX-D04, Q-01 |
| S55 | Site search loading, query generations and result expansion | implemented | 11 | site | SITE-U01, Q-01 |
| S56 | Academy local bookmark and cross-tab state | implemented | 8 | site | Q-01 |
| S57 | Academy command preferences and copy interaction | implemented | 7 | site | Q-01 |
| S58 | Site guide-directory filter | implemented | 3 | site | Q-01 |
| S59 | Site evidence/context/example selection and Academy disclosure | implemented | 5 | site | Q-01 |
| S60 | Site execution-map fragment navigation | implemented | 5 | site | Q-01 |
| S61 | Site workflow atlas view, route, node, zoom, print and export | implemented | 13 | site | Q-01 |
| S62 | Site splash documentation drawer | implemented | 5 | site | SITE-U02, Q-01 |
| S63 | Site table-of-contents tracking and forced theme | implemented | 5 | site | Q-01 |
| S64 | Site reference-generation pipeline and partial output | implemented | 5 | site | BUILD-G01, Q-01 |
| S65 | Site Pagefind index build and staged replacement | implemented | 8 | site | BUILD-G01, Q-01 |
| S66 | Site evidence capture, cleanup and freshness gate | implemented | 8 | site | Q-01 |
| S67 | Academy source admission and generated-course replacement | implemented | 7 | site | BUILD-G01, Q-01 |
| S68 | Native artifact candidate build and protected qualification | implemented | 7 | packaging | Q-01 |
| S69 | Cross-platform qualification promotion into host payload overlay | implemented | 6 | packaging | DIST-M01, PI-C01, PI-D07, Q-01 |
| S70 | Native payload verification and create-only installation | implemented | 8 | packaging | DIST-M01, Q-01 |
| S71 | Qualified release package cohort construction and verification | implemented | 7 | packaging | DIST-M01, PI-C01, PI-D07, Q-01 |
| S72 | Cold installed-host package execution and evidence | implemented | 7 | packaging | DIST-M01, PI-C01, PI-D07, Q-01 |
| S73 | Claude immutable distribution tag and marketplace channel promotion | implemented | 11 | packaging | DIST-M02, Q-01 |
| S74 | Codex immutable distribution, optional npm identity and channel promotion | implemented | 10 | packaging | DIST-M02, Q-01 |
| S75 | Generated host surface projection and drift gate | implemented | 8 | packaging | BUILD-G01, BUILD-G02, HW-19, HW-20, HW-21, HW-27, Q-01 |
| S76 | Canonical Python and package-notice synchronization | implemented | 7 | packaging | BUILD-G01, Q-01 |
| S77 | Pi package metadata projection and release-advance guard | implemented | 9 | packaging | DIST-M01, PI-C01, PI-D03, PI-D07, Q-01 |
| C01 | CI admission, impact selection and cancellation | implemented | 5 | release-and-tooling | NT-12, R-03, R-04, Q-01 |
| C02 | Required CI aggregate and advisory lanes | implemented | 4 | release-and-tooling | NT-12, R-03, R-04, Q-01 |
| C03 | Native candidate identity stamp and consumer binding | implemented | 4 | release-and-tooling | Q-01 |
| C04 | Native qualification DAG, package assembly and cold-install matrix | implemented | 7 | release-and-tooling | DIST-M01, NT-12, R-03, R-04, Q-01 |
| C05 | Concurrent Python suite execution and observed result | implemented | 5 | release-and-tooling | Q-01 |
| C06 | Authority suite discovery, partition, deadline and exact-coverage join | implemented | 4 | release-and-tooling | Q-01 |
| C07 | Context verification evidence and installed invocation admission | implemented | 4 | release-and-tooling | DIST-M01, Q-01 |
| C08 | Create-only context fixture and evaluator/solver boundary | implemented | 3 | release-and-tooling | Q-01 |
| C09 | Coverage input binding, post-test receipt and multi-host union | implemented | 6 | release-and-tooling | Q-01 |
| C10 | Docker integration test-layer observation | implemented | 3 | release-and-tooling | Q-01 |
| C11 | Real Codex installation, read-back and disposable-host lifecycle | implemented | 8 | release-and-tooling | R-06, R-07, Q-01 |
| C12 | Trusted static Codex candidate verification and exact-commit provenance | implemented | 5 | release-and-tooling | Q-01 |
| C13 | Upstream runtime canaries and advisory evidence | implemented | 4 | release-and-tooling | NT-12, R-03, R-04, Q-01 |
| C14 | Shipped payload scope and version-spending gate | implemented | 5 | release-and-tooling | R-06, Q-01 |
| C15 | Automatic release candidate intent and pre-tag enforcement | implemented | 5 | release-and-tooling | R-01, R-02, R-03, R-04, Q-01 |
| C16 | Release source selection, per-target eligibility and concurrency recheck | implemented | 6 | release-and-tooling | R-01, R-02, R-03, R-04, Q-01 |
| C17 | Per-target publication saga and incomplete public-release recovery | implemented | 11 | release-and-tooling | DIST-M02, R-01, R-04, R-08, Q-01 |
| C18 | npm registry identity, trusted publication and bounded read-back | implemented | 9 | release-and-tooling | DIST-M01, DIST-M02, R-01, R-04, R-08, Q-01 |
| C19 | Published tag observation receipt and exclusive local capture | implemented | 3 | release-and-tooling | Q-01 |
| C20 | Offline original-tag receipt reconciliation | implemented | 4 | release-and-tooling | Q-01 |
| C21 | Recorded tag immutability and evidence availability | implemented | 5 | release-and-tooling | R-06, Q-01 |
| C22 | Read-only branch protection and merge-queue posture audit | implemented | 4 | release-and-tooling | R-06, Q-01 |
| C23 | Codex distribution identity, credential minting and advisory ruleset audit | implemented | 4 | release-and-tooling | DIST-M02, R-01, R-04, R-08, Q-01 |
| C24 | Inert Pi candidate dependency capture and pending-review state | implemented | 5 | release-and-tooling | Q-01 |
| C25 | Pi dependency review, expiring advisory exceptions and isolated installation | implemented | 6 | release-and-tooling | Q-01 |
| C26 | Pi support promotion, failure receipts and draft-PR publication | implemented | 7 | release-and-tooling | Q-01 |
| C27 | Pi support evidence assembly, pre-closure and final qualification | implemented | 5 | release-and-tooling | Q-01 |
| C28 | Academy preview candidate binding and promotion proposal | implemented | 5 | release-and-tooling | Q-01 |
| C29 | Documentation site validation, evidence retention and Pages deployment | implemented | 5 | release-and-tooling | R-05, Q-01 |
| C30 | Local ADR acceptance packet creation, validity window and clearing | implemented | 4 | release-and-tooling | Q-01 |
| C31 | ADR two-commit local acceptance allowance versus committed governance validation | implemented | 5 | release-and-tooling | Q-01 |
| C32 | Command-route compatibility release clock and optional remote observation | implemented | 7 | release-and-tooling | HW-21, HW-27, NT-12, R-03, R-04, Q-01 |
| C33 | Release-skill proof freshness and exercised host boundary | implemented | 3 | release-and-tooling | Q-01 |
| C34 | Release-target provenance generation and scope-only freshness check | implemented | 3 | release-and-tooling | Q-01 |
| C35 | npm vulnerability exception lifecycle and gate decision | implemented | 4 | release-and-tooling | Q-01 |
| C36 | Adapter benchmark readiness, sample completion and optional real-spawn measurement | implemented | 6 | release-and-tooling | R-07, Q-01 |
| SX01 | Direct hook proof capture and media settlement | implemented | 7 | site-and-release | Q-01 |
| SX02 | Documentation examples: capture, pin, validate and render | implemented | 8 | site-and-release | Q-01 |
| SX03 | Documentation release and proof applicability derivation | implemented | 6 | site-and-release | R-08, Q-01 |
| SX04 | Version-fact extraction, process cache and token resolution | implemented | 4 | site-and-release | Q-01 |
| SX05 | Historical atlas source binding and generated projection | implemented | 6 | site-and-release | Q-01 |
| SX06 | Site metadata, graph and link build gates | implemented | 7 | site-and-release | Q-01 |
| SX07 | Captured terminal style decoder | implemented | 3 | site-and-release | Q-01 |
| T01 | Shadow CI impact prediction and broad fallback | implemented | 5 | release-and-tooling | Q-01 |
| T02 | Native statement coverage collection, publication and union verdict | implemented | 9 | release-and-tooling | Q-01 |
| T03 | Go test population discovery, chunk execution and exact-result accounting | implemented | 6 | release-and-tooling | NT-12, Q-01 |
| T04 | CI20 historical run baseline, graph replay and source inventory | implemented | 6 | release-and-tooling | T-01, Q-01 |
| T05 | Codex/Claude parity fixture construction and manual handoff | implemented | 3 | release-and-tooling | Q-01 |
| T06 | Native draft artifact example generation | implemented | 4 | release-and-tooling | Q-01 |
| T07 | Schema-derived Go view generation and drift check | implemented | 3 | release-and-tooling | NT-12, Q-01 |
| T08 | Manual live SMARTS exercise and weak output oracle | implemented | 5 | release-and-tooling | T-01, Q-01 |
| T09 | Knowledge retrieval measurement fixture and cold/warm comparison | implemented | 4 | release-and-tooling | Q-01 |
| T10 | Statusline benchmark phase progression and comparison verdict | implemented | 8 | release-and-tooling | T-01, Q-01 |
| T11 | Statusline screenshot generation and partial cleanup | implemented | 4 | release-and-tooling | T-01, Q-01 |
| T12 | Tribunal captured evidence, independent adjudication and critical-regression gate | implemented | 9 | release-and-tooling | Q-01 |
| generator:markdown | Source normalization, frontmatter and fenced Markdown scanner | implemented | 6 | hooks-workflows | HW-27 |
| generator:discovery | Plugin source discovery, names, slugs and host availability projection | implemented | 6 | hooks-workflows | HW-24, HW-19, HW-27 |
| generator:catalog-graph | Command discovery validation, command-skill pairing and legacy URL routing | implemented | 7 | hooks-workflows | HW-19, HW-21, HW-24, HW-27 |
| generator:curated-validation | Curated framing shape, gate-row parser and command/flag drift attribution | implemented | 8 | hooks-workflows | HW-27 |
| generator:hook-extractor | Bounded Python call-site extraction and hook-reference event attribution | implemented | 7 | hooks-workflows | HW-23, HW-27 |
| generator:public-catalog | Manual preview/configuration facts and generated public-source identity | implemented | 4 | hooks-workflows | HW-19, HW-20, HW-22, HW-27 |
| generator:rendering | Pure reference rendering, reader token safety and source embeds | implemented | 6 | hooks-workflows | HW-19, HW-20, HW-23, HW-27 |
| SW01 | Sandbox command routing and five-phase operator workflow | model-guided | 24 | sandbox | SBX-C01, SBX-D01, SBX-D02, SBX-D03, Q-01 |
| SW02 | Claude-inside credential workflow and five BLOCK phases | model-guided | 14 | sandbox | SBX-D04, Q-01 |
| pi-qualification:runtime-discovery | Test-only installed Pi runtime and CLI discovery | implemented | 4 | hooks-workflows | HW-26, HW-27 |
| pi-qualification:disposable-home | Test-only disposable home setup and process-exit cleanup | implemented | 4 | hooks-workflows | HW-26, HW-15, HW-27 |
