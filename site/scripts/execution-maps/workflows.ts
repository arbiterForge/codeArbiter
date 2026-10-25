/** C04 source-bound teaching maps, not an orchestration DSL or runtime authority. */
import type { ExecutionMap } from './model';
export interface WorkflowDefinition {
  id: string; title: string; summary: string; endpoint: string; guide: string; asset: string;
  map: ExecutionMap; notes: Array<{ title: string; detail: string; source: string }>;
}
export const workflows: readonly WorkflowDefinition[] = [
  {
    "id": "sprint",
    "title": "An authorized sprint reaches a PR",
    "summary": "Agree the outcome → implement within scope → report and hand off",
    "endpoint": "An honest implementation report and authorized PR; merge remains separate.",
    "guide": "/guides/autonomous-sprints/",
    "asset": "lane-sprint.svg",
    "map": {
      "id": "sprint",
      "title": "An authorized sprint reaches a PR",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Current assistive source flow with retained historical citations. The user's request authorizes the agreed work; ordinary drafts, task progress and in-scope methods require no second artifact approval, context ticket or receipt-driven reviewer chain. Actual user stops, host/security controls and commit/publication permissions remain. This source explanation is not a captured live host run.",
      "outcome": "An implementation report and authorized open PR with actual checks, meaningful decisions and remaining work. Reported DONE does not certify verification or release; the sprint never merges or discards work without separate authority.",
      "sources": {
        "autonomy": {
          "path": "core/surface/SPRINT.md",
          "quote": "WITHOUT per-batch\nhuman checkpoints",
          "currentQuote": "no artificial per-batch human pause"
        },
        "finish": {
          "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
          "quote": "**execute those steps here; do not re-invoke `{{CMD:pr}}`**",
          "currentQuote": "execute the **Open-PR procedure** below in this owner. Do not load or re-invoke the PR command wrapper."
        },
        "pair": {
          "path": "core/surface/SPRINT.md",
          "quote": "commits approval plus plan binding in one recoverable native transaction.",
          "currentQuote": "A `draft_preview` binding identifies the current source"
        },
        "pr": {
          "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
          "quote": "`commit-gate` MUST have cleared on the current HEAD.",
          "currentQuote": "Establish applicable verification for the current HEAD."
        },
        "sprint": {
          "path": "core/surface/SPRINT.md",
          "quote": "## Phase 1 — Sprint spec · gate: STOP",
          "currentQuote": "## Phase 1 - Establish a useful working agreement"
        },
        "sprintExit": {
          "path": "core/surface/SPRINT.md",
          "quote": "AUTO-SELECTS open-PR and surfaces the merge decision to the user.",
          "currentQuote": "`/sprint` may open a PR under the existing authorized workflow"
        },
        "sprintRecovery": {
          "path": "core/surface/SPRINT.md",
          "quote": "A failed TDD, coverage, lint, or fresh-verification result blocks acceptance, not authorized repair.",
          "currentQuote": "A failing unit test, lint error, mismatched criterion"
        },
        "task": {
          "path": "core/surface/skills/subagent-driven-development/SKILL.md",
          "quote": "The subagent works test-first by routing through the `tdd` skill",
          "currentQuote": "Work directly when a focused change is clearer and cheaper."
        },
        "taskReview": {
          "path": "core/surface/skills/subagent-driven-development/SKILL.md",
          "quote": "Runs ONCE per scope — after every task in the current scope has cleared Phase 3 and Phase 5",
          "currentQuote": "## 3. Verify truthfully and assess only relevant risks"
        },
        "tdd": {
          "path": "core/surface/skills/tdd/SKILL.md",
          "quote": "A `MISSING` obligation returns the workflow to Phase 2",
          "currentQuote": "Select the verification approach before changing code."
        }
      },
      "chapters": [
        {
          "id": "review-pair",
          "title": "Establish the working agreement",
          "question": "What outcome and constraints define the work?",
          "output": "A maintained spec and plan for the authorized outcome. Material unresolved product choices go to the actual owner; ordinary planning does not wait for an artifact approval receipt.",
          "nodes": [
            {
              "id": "sprint-entry",
              "role": "command",
              "label": [
                "/ca:sprint"
              ],
              "title": "/ca:sprint: select the work",
              "href": "/reference/commands/sprint/",
              "source": "sprint",
              "detail": "Resolve an existing exact-format pair before starting new work. This map follows a new HTML pair; existing Markdown retains its own contract.",
              "output": "One selected format, scope and backend."
            },
            {
              "id": "sprint-spec",
              "role": "skill",
              "label": [
                "brainstorming"
              ],
              "title": "brainstorming: sprint definition",
              "href": "/reference/skills/brainstorming/",
              "source": "sprint",
              "detail": "Capture the outcome, exclusions, priorities and real constraints. Read relevant recorded intent and existing decisions; ask only consequential unresolved owner questions.",
              "output": "A ready draft specification and surfaced decisions."
            },
            {
              "id": "sprint-plan",
              "role": "skill",
              "label": [
                "writing-plans"
              ],
              "title": "writing-plans: linked draft",
              "href": "/reference/skills/writing-plans/",
              "source": "pair",
              "detail": "Maintain a same-format spec/plan pair with useful criteria, tasks, dependencies and checks. A draft_preview binding identifies current source; ordinary in-scope plan maintenance needs no separate artifact permission.",
              "output": "A structurally valid linked draft for the agreed outcome."
            },
            {
              "id": "sprint-approve",
              "role": "skill",
              "label": [
                "Working",
                "agreement"
              ],
              "title": "/ca:sprint: maintain the agreement",
              "href": "/reference/commands/sprint/",
              "source": "pair",
              "detail": "Continue under the user's existing authorization with the maintained spec and plan. Do not arm pair approval or delegate-methods for ordinary work. Explicit requested checkpoints and material outcome changes still belong to their actual owner.",
              "output": "A bounded working agreement, without invented approval or new permission receipts."
            }
          ],
          "edges": [
            {
              "to": "sprint-spec",
              "kind": "sequence",
              "label": "define scope",
              "source": "sprint",
              "detail": "The selected new sprint enters the definition phase.",
              "from": "sprint-entry"
            },
            {
              "to": "sprint-plan",
              "kind": "sequence",
              "label": "draft pair",
              "source": "pair",
              "detail": "Derive useful tasks and checks from the current agreed specification.",
              "from": "sprint-spec"
            },
            {
              "to": "sprint-approve",
              "kind": "return",
              "label": "agreed scope",
              "source": "pair",
              "detail": "Keep the linked plan aligned with the authorized outcome; no artifact approval ceremony is required.",
              "from": "sprint-plan"
            }
          ]
        },
        {
          "id": "execute-tasks",
          "title": "Build and verify each task",
          "question": "What replaces the attended batch coordinator?",
          "output": "Useful implementation and actual check results. Reported progress remains separate from independent review, passing verification and release readiness.",
          "nodes": [
            {
              "id": "sprint-engine",
              "role": "skill",
              "label": [
                "Task engine"
              ],
              "title": "subagent-driven-development: select",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "autonomy",
              "detail": "Read compact task-context or exact symbols and inspect the full dependency ancestry. Unresolved ancestors remain visible with their IDs and reasons; independent work can proceed. Inspect existing IN_PROGRESS work before redispatch and preserve independently blocked tasks.",
              "output": "One coherent task inside the agreed scope with relevant current facts."
            },
            {
              "id": "sprint-author",
              "role": "skill",
              "label": [
                "Implement",
                "or delegate"
              ],
              "title": "Task engine: implement or delegate",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "task",
              "detail": "Work directly for a focused change or delegate a coherent unit when useful. Supply relevant criteria, paths, constraints and checks within actual host permissions. Bounded context delivery ends after two attempts with an advisory unknown observation; missing critical inputs and actual conflicts still stop dependent work.",
              "output": "Implementation work with bounded relevant context."
            },
            {
              "id": "sprint-tdd",
              "role": "skill",
              "label": [
                "tdd"
              ],
              "title": "tdd inside authoring",
              "href": "/concepts/test-first/",
              "source": "tdd",
              "detail": "Select proportional verification: genuine regression RED/GREEN for fixes, criterion-focused checks for features, and passing characterization baselines for refactors. Preserve behavioral assertions, meaningful negative controls where needed, coverage and lint.",
              "output": "Evidence returned to the caller, not permission to commit.",
              "conditional": true
            },
            {
              "id": "sprint-proof",
              "role": "skill",
              "label": [
                "Actual checks",
                "+ findings"
              ],
              "title": "Task engine: verify truthfully",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "taskReview",
              "detail": "Compare work with the agreed criteria and run relevant checks through the host-governed tool. Record actual command outcomes and limitations with task-check; caller-reported results do not certify an independent review or passing named-test proof.",
              "output": "Actual checks, failures and unrun obligations, with no fabricated evidence."
            }
          ],
          "edges": [
            {
              "to": "sprint-author",
              "kind": "sequence",
              "label": "useful unit",
              "source": "task",
              "detail": "Implement directly or delegate when useful within actual host permissions.",
              "from": "sprint-engine"
            },
            {
              "to": "sprint-tdd",
              "kind": "sequence",
              "label": "behavioral task",
              "source": "task",
              "detail": "Use the verification approach appropriate to the change; documentation or non-runnable work uses concrete relevant validation.",
              "from": "sprint-author"
            },
            {
              "to": "sprint-proof",
              "kind": "return",
              "label": "actual results",
              "source": "taskReview",
              "detail": "Record checks actually run and inspect the result against the agreed criteria.",
              "from": "sprint-tdd"
            }
          ]
        },
        {
          "id": "accept-scope",
          "title": "Assess risks and report progress",
          "question": "What prevents a green task from becoming a false completion claim?",
          "output": "Relevant findings, actual check outcomes and honest implementation state. A failing or unrun check remains visible; an actual user stop remains blocked.",
          "nodes": [
            {
              "id": "sprint-quality",
              "role": "agent",
              "label": [
                "Applicable",
                "reviewers"
              ],
              "title": "Combined quality reviewers",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "taskReview",
              "detail": "Review the relevant diff when risk or change size warrants it. Select specialist review for actual security, dependency or migration concerns or an applicable policy; a receipt change alone does not require another reviewer.",
              "output": "Applicable quality findings against the whole scope.",
              "conditional": true
            },
            {
              "id": "sprint-triage",
              "role": "agent",
              "label": [
                "finding-triage"
              ],
              "title": "finding-triage",
              "href": "/reference/agents/finding-triage/",
              "source": "taskReview",
              "detail": "Classify actual findings and preserve out-of-scope follow-ups. Correct affected work and revisit only conclusions changed by relevant source, requirements or evidence.",
              "output": "A disposition for the current findings.",
              "conditional": true
            },
            {
              "id": "sprint-accepted",
              "role": "skill",
              "label": [
                "Report",
                "progress"
              ],
              "title": "Task engine: honest implementation progress",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "sprintRecovery",
              "detail": "Use receipt-free task-review and accept-scope to record implementation readiness or DONE with a real reason. These labels do not certify tests, independent review or release. Preserve blocked members, real user stops and outstanding checks.",
              "output": "Reported implementation progress with evidence and remaining work kept distinct."
            }
          ],
          "edges": [
            {
              "to": "sprint-triage",
              "kind": "sequence",
              "label": "classify",
              "source": "taskReview",
              "detail": "The active caller retains responsibility for severity and scope.",
              "from": "sprint-quality"
            },
            {
              "to": "sprint-accepted",
              "kind": "return",
              "label": "honest progress",
              "source": "sprintRecovery",
              "detail": "Record actual implementation progress without claiming that pending verification passed.",
              "from": "sprint-triage"
            }
          ]
        },
        {
          "id": "handoff",
          "title": "Commit and hand off the PR",
          "question": "Where does autonomous authority end?",
          "output": "Inspect the actual PR head, observed checks, meaningful decisions and unresolved findings. Commit and PR actions use existing authorization; merge and publication remain separate.",
          "nodes": [
            {
              "id": "sprint-commit",
              "role": "skill",
              "label": [
                "commit-gate"
              ],
              "title": "commit-gate",
              "href": "/reference/skills/commit-gate/",
              "source": "sprintExit",
              "detail": "When a commit is authorized, retain staged-diff inspection, secrets checks and applicable tests through commit-gate. Artifact progress does not create commit, merge or publication authority.",
              "output": "The gated commit and its actual evidence."
            },
            {
              "id": "sprint-finish",
              "role": "skill",
              "label": [
                "Finish branch"
              ],
              "title": "finishing-a-development-branch",
              "href": "/reference/skills/finishing-a-development-branch/",
              "source": "sprintExit",
              "detail": "Sprint mode selects Open a PR instead of asking for attended terminal choices. Merge and discard are excluded.",
              "output": "A PR handoff, not authority to land on main."
            },
            {
              "id": "sprint-pr",
              "role": "command",
              "label": [
                "/ca:pr",
                "procedure"
              ],
              "title": "/ca:pr procedure reused in place",
              "href": "/reference/commands/pr/",
              "source": "finish",
              "detail": "The finisher executes the PR procedure here; the command is not re-invoked. Existing caller ownership prevents a routing loop.",
              "output": "Required PR preparation and path-selected review."
            },
            {
              "id": "sprint-pr-review",
              "role": "agent",
              "label": [
                "PR reviewers",
                "+ verdict"
              ],
              "title": "PR reviewers and verdict funnel",
              "href": "/reference/commands/pr/",
              "source": "pr",
              "detail": "Complete the applicable review and resolve blockers before opening. The sprint summary includes logged decisions, low-confidence calls and follow-ups.",
              "output": "An open PR with an honest sprint report and unresolved obligations."
            }
          ],
          "edges": [
            {
              "to": "sprint-finish",
              "kind": "sequence",
              "label": "current commit",
              "source": "sprintExit",
              "detail": "The normal completion path reaches finalization.",
              "from": "sprint-commit"
            },
            {
              "to": "sprint-pr",
              "kind": "reuse",
              "label": "reuse procedure",
              "source": "finish",
              "detail": "Run the existing procedure without invoking its entry again.",
              "from": "sprint-finish"
            },
            {
              "to": "sprint-pr-review",
              "kind": "dispatch",
              "label": "review before PR",
              "source": "pr",
              "detail": "Only the actual reviewer results support the final verdict.",
              "from": "sprint-pr"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "sprint-engine",
          "kind": "sequence",
          "label": "authorized work",
          "source": "autonomy",
          "detail": "The maintained plan reaches implementation without artificial batch pauses or pair approval.",
          "from": "sprint-approve"
        },
        {
          "to": "sprint-proof",
          "kind": "return",
          "label": "concrete validation",
          "source": "task",
          "detail": "Documentation-only or other work without a runnable test uses concrete relevant validation and records the actual result.",
          "from": "sprint-author"
        },
        {
          "to": "sprint-engine",
          "kind": "repeat",
          "label": "More eligible tasks",
          "source": "taskReview",
          "detail": "Continue independent dependency-clean work while preserving real blockers and outstanding checks.",
          "from": "sprint-proof"
        },
        {
          "to": "sprint-quality",
          "kind": "dispatch",
          "label": "review warranted",
          "source": "taskReview",
          "detail": "Obtain useful independent or policy-required review for the actual risk and scope.",
          "from": "sprint-proof"
        },
        {
          "to": "sprint-accepted",
          "kind": "sequence",
          "label": "no extra review needed",
          "source": "taskReview",
          "detail": "When no additional review is warranted or required, report implementation progress with actual checks and limitations.",
          "from": "sprint-proof"
        },
        {
          "to": "sprint-author",
          "kind": "return",
          "label": "Correction inside scope",
          "source": "sprintRecovery",
          "detail": "Repair affected work and rerun relevant checks; preserve explicit user stops and actual security or host denials.",
          "from": "sprint-triage"
        },
        {
          "to": "sprint-commit",
          "kind": "sequence",
          "label": "authorized handoff",
          "source": "sprintExit",
          "detail": "Return the honest report to sprint, which owns any authorized commit and PR action. DONE is not release readiness.",
          "from": "sprint-accepted"
        }
      ]
    },
    "notes": [
      {
        "title": "Existing authorization covers ordinary progress",
        "detail": "Maintain the agreed spec and plan under the existing authorization. Ask only about consequential unresolved choices. Task progress, actual checks and independent review remain distinct.",
        "source": "pair"
      },
      {
        "title": "Autonomy is bounded",
        "detail": "Choose reversible in-scope methods from the user's intent; use SMARTS for a difficult tradeoff when useful and record material decisions. Changed outcomes, spending, credentials, irreversible actions, merge and publication retain their actual authority boundaries.",
        "source": "sprint"
      },
      {
        "title": "Failure is not an endless retry",
        "detail": "After two unchanged corrective attempts without new evidence, stop that strategy. Preserve blocked state and its dependents; continue only independently eligible work.",
        "source": "sprintRecovery"
      },
      {
        "title": "HTML farm remains disabled",
        "detail": "HTML --farm remains disabled. A separately requested legacy Markdown farm uses real provider configuration, budget and circuit-breaker controls; unavailable backends are reported without silent provider/model switches.",
        "source": "sprint"
      }
    ]
  },
  {
    "id": "dependency",
    "title": "Review before adopting a dependency",
    "summary": "Select the package → review → confirm → inspect the change",
    "endpoint": "Reviewed adoption; deliver manifest and lockfile together.",
    "guide": "/guides/adding-a-dependency/",
    "asset": "lane-add-dep.svg",
    "map": {
      "id": "dependency",
      "title": "Review before adopting a dependency",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "The adoption path is shown here. A one-time named inspection tool is a separate bounded branch inside the same command. The reviewer does not install the package.",
      "outcome": "A reviewed and explicitly confirmed dependency change. Inspect the manifest and lockfile, then deliver them together through the owning change and commit/PR procedure.",
      "sources": {
        "dep": {
          "path": "core/surface/commands/add-dep.md",
          "quote": "After the agent clears it, the orchestrator surfaces the install command for confirmation."
        },
        "depOne": {
          "path": "core/surface/commands/add-dep.md",
          "quote": "## Ephemeral tool run — one invocation, nothing adopted"
        },
        "depReview": {
          "path": "core/surface/agents/dependency-reviewer.md",
          "quote": "Produce findings. Do not modify files. Do not run install commands."
        }
      },
      "chapters": [
        {
          "id": "adopt",
          "title": "Review, confirm, then adopt",
          "question": "Who checks the package, and who is allowed to run the install?",
          "output": "The reviewer verdict and install confirmation are separate. A denied license or unresolved provenance concern blocks adoption.",
          "nodes": [
            {
              "id": "dep-entry",
              "role": "command",
              "label": [
                "/ca:add-dep"
              ],
              "title": "/ca:add-dep: identify the package",
              "href": "/reference/commands/add-dep/",
              "source": "dep",
              "detail": "Name the package and exact version. Read the project policy and stack requirements; an omitted version must be resolved before treating a review as specific.",
              "output": "A concrete package and the policy it will be judged against."
            },
            {
              "id": "dep-reviewer",
              "role": "agent",
              "label": [
                "Dependency",
                "reviewer"
              ],
              "title": "dependency-reviewer",
              "href": "/reference/agents/dependency-reviewer/",
              "source": "depReview",
              "detail": "Inspect license, registry, provenance, maintenance, audit findings and install-script posture. Return findings; do not install or modify files.",
              "output": "A package-specific review result with unresolved concerns visible."
            },
            {
              "id": "dep-confirm",
              "role": "command",
              "label": [
                "Confirm",
                "install"
              ],
              "title": "/ca:add-dep: installation confirmation",
              "href": "/reference/commands/add-dep/",
              "source": "dep",
              "detail": "After the reviewer clears the package, the orchestrator presents the exact install command for your confirmation. A review pass is not that instruction.",
              "output": "Explicit permission for the named installation."
            },
            {
              "id": "dep-change",
              "role": "command",
              "label": [
                "Inspect paired",
                "changes"
              ],
              "title": "/ca:add-dep: inspect the adoption",
              "href": "/guides/adding-a-dependency/",
              "source": "dep",
              "detail": "Check the actual manifest and lockfile changes. The command requires them to be committed together, never one without the other; use the existing delivery procedure.",
              "output": "The paired dependency change and its delivery obligation."
            }
          ],
          "edges": [
            {
              "to": "dep-reviewer",
              "kind": "dispatch",
              "label": "review first",
              "source": "dep",
              "detail": "The command dispatches its dependency reviewer before any install.",
              "from": "dep-entry"
            },
            {
              "to": "dep-confirm",
              "kind": "return",
              "label": "cleared package",
              "source": "dep",
              "detail": "Return a verdict before asking for the install action.",
              "from": "dep-reviewer"
            },
            {
              "to": "dep-change",
              "kind": "sequence",
              "label": "confirmed command",
              "source": "dep",
              "detail": "Run only the confirmed adoption and inspect its resulting files.",
              "from": "dep-confirm"
            }
          ]
        }
      ],
      "alternatives": []
    },
    "notes": [
      {
        "title": "No extra skill is invented",
        "detail": "This command directly dispatches an agent and receives its result. The empty Skills row is intentional, not an omitted phase.",
        "source": "dep"
      },
      {
        "title": "One-time inspection is not adoption",
        "detail": "The operator must request the named tool for one inspection run, with an exact version, approved source and explicit command confirmation. It cannot change manifests, lockfiles or committed artifacts.",
        "source": "depOne"
      },
      {
        "title": "The gate has a specific enforcement boundary",
        "detail": "The dependency-review rule is orchestrator-enforced. The source does not claim a hook intercepts every bare install typed outside this command.",
        "source": "dep"
      }
    ]
  },
  {
    "id": "adr",
    "title": "Record a decision and bind its acceptance",
    "summary": "Attributed decision → proposed record → accepted/planned binding",
    "endpoint": "Accepted/Planned record; delivery proof remains separate.",
    "guide": "/guides/recording-adrs/",
    "asset": "lane-adr.svg",
    "map": {
      "id": "adr",
      "title": "Record a decision and bind its acceptance",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "This path follows an explicitly attributed decision through user-authorized acceptance. Remaining Proposed is valid. A status query and optional challenge are separate operations, not automatic authoring steps.",
      "outcome": "The decision, decision-log append and exact acceptance binding are retained. Accepted/Planned does not prove implementation, verification or a merged PR.",
      "sources": {
        "adr": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "currentPath": "core/surface/skills/decision-lifecycle/references/authoring.md",
          "quote": "Status transitions (`proposed → accepted → superseded | rejected`) require explicit user instruction"
        },
        "adrAccept": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "currentPath": "core/surface/skills/decision-lifecycle/references/authoring.md",
          "quote": "### Accepted/Planned binding"
        },
        "adrCommit": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "currentPath": "core/surface/skills/decision-lifecycle/references/authoring.md",
          "quote": "its `source_commit` cannot truthfully name a commit that does\n   not exist yet."
        },
        "adrWrite": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "currentPath": "core/surface/skills/decision-lifecycle/references/authoring.md",
          "quote": "Author it with `status: proposed`."
        }
      },
      "chapters": [
        {
          "id": "author-decision",
          "title": "Record the user’s choice",
          "question": "What did the human decide, and what is actually being recorded?",
          "output": "A numbered Proposed ADR and corresponding log entry. Acceptance waits for an explicit user instruction.",
          "nodes": [
            {
              "id": "adr-entry",
              "role": "command",
              "label": [
                "/ca:adr"
              ],
              "title": "/ca:adr: attributed decision",
              "href": "/reference/commands/adr/",
              "source": "adr",
              "detail": "Name the decision and the person making it. A routine finding or an unresolved CONFIRM item cannot be converted into an invented architectural choice.",
              "output": "A named decision to record, not model-owned authority."
            },
            {
              "id": "adr-index",
              "role": "skill",
              "label": [
                "Index + author"
              ],
              "title": "decision-lifecycle: index and author",
              "href": "/reference/skills/decision-lifecycle/",
              "source": "adrWrite",
              "detail": "Use the next unused number and full filename stem, gather rationale and governed paths, and write the current template with status proposed.",
              "output": "A dated, attributed Proposed record."
            },
            {
              "id": "adr-log",
              "role": "skill",
              "label": [
                "Append the log"
              ],
              "title": "decision-lifecycle: decision log",
              "href": "/reference/skills/decision-lifecycle/",
              "source": "adrWrite",
              "detail": "Append the matching user-attributed decision-log entry. A replacement names the full predecessor stem; it does not rewrite the earlier decision.",
              "output": "The decision and its append-only log entry."
            },
            {
              "id": "adr-accept",
              "role": "skill",
              "label": [
                "Explicit",
                "acceptance"
              ],
              "title": "decision-lifecycle: accept on instruction",
              "href": "/reference/skills/decision-lifecycle/",
              "source": "adrAccept",
              "detail": "Only explicit user acceptance advances status. Derive stable obligations and independently review the completeness of the sealed set before recording the binding.",
              "output": "Accepted/Planned content and reviewed obligations."
            }
          ],
          "edges": [
            {
              "to": "adr-index",
              "kind": "sequence",
              "label": "authoring owner",
              "source": "adr",
              "detail": "The command routes to decision-lifecycle for numbering, attribution and writing.",
              "from": "adr-entry"
            },
            {
              "to": "adr-log",
              "kind": "sequence",
              "label": "record the choice",
              "source": "adrWrite",
              "detail": "The log entry accompanies the newly written ADR.",
              "from": "adr-index"
            },
            {
              "to": "adr-accept",
              "kind": "sequence",
              "label": "only on instruction",
              "source": "adrAccept",
              "detail": "Stop at Proposed unless the user explicitly authorizes acceptance.",
              "from": "adr-log"
            }
          ]
        },
        {
          "id": "bind-record",
          "title": "Bind a commit that exists",
          "question": "Why are acceptance content and its binding not one invented commit?",
          "output": "A committed acceptance event points to the real prior source commit. Later implementation and verification require their own current evidence.",
          "nodes": [
            {
              "id": "adr-source-commit",
              "role": "skill",
              "label": [
                "commit-gate"
              ],
              "title": "commit-gate: accepted record",
              "href": "/reference/skills/commit-gate/",
              "source": "adrCommit",
              "detail": "Commit the accepted ADR and decision-log append through the normal gate. The acceptance binding is deliberately not added to this commit.",
              "output": "An existing source commit whose bytes can now be hashed."
            },
            {
              "id": "adr-binding",
              "role": "skill",
              "label": [
                "Bind accepted",
                "content"
              ],
              "title": "decision-lifecycle: append acceptance",
              "href": "/reference/skills/decision-lifecycle/",
              "source": "adrAccept",
              "detail": "From the exact source commit, bind the blob, immutable record and sealed obligations in the append-only lifecycle ledger. A second binding for the same stem is invalid.",
              "output": "An acceptance event with a real source identity."
            },
            {
              "id": "adr-binding-commit",
              "role": "skill",
              "label": [
                "Persist the",
                "binding"
              ],
              "title": "decision-lifecycle: subsequent commit",
              "href": "/reference/skills/decision-lifecycle/",
              "source": "adrAccept",
              "detail": "Persist the binding in a subsequent commit. Later PR delivery must preserve the required source ancestry; an unqualified squash cannot stand in for it.",
              "output": "The retained record and acceptance binding, not implementation evidence."
            }
          ],
          "edges": [
            {
              "to": "adr-binding",
              "kind": "return",
              "label": "hash exact source",
              "source": "adrCommit",
              "detail": "The source commit must exist before the binding can truthfully identify it.",
              "from": "adr-source-commit"
            },
            {
              "to": "adr-binding-commit",
              "kind": "sequence",
              "label": "append then persist",
              "source": "adrAccept",
              "detail": "Persist the event without rewriting earlier history.",
              "from": "adr-binding"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "adr-source-commit",
          "kind": "sequence",
          "label": "accepted content",
          "source": "adrAccept",
          "detail": "The user-directed acceptance path commits its content before binding that commit.",
          "from": "adr-accept"
        }
      ]
    },
    "notes": [
      {
        "title": "Status is a separate read",
        "detail": "/ca:adr-status reads the decision and lifecycle evidence. It may optionally dispatch decision-challenger; that is not a required authoring agent or an automatic status transition.",
        "source": "adrAccept"
      },
      {
        "title": "A replacement points forward",
        "detail": "Use the full predecessor stem. Partial supersession can legitimately fork; the scope belongs in the new decision’s prose.",
        "source": "adrWrite"
      },
      {
        "title": "Accepted is not delivered",
        "detail": "A sealed set with current implementation and verification inputs is required to derive Implemented or Verified. Legacy unsealed records retain their narrower evidence boundary.",
        "source": "adrAccept"
      }
    ]
  },
  {
    "id": "release",
    "title": "Prepare a release through a reviewed PR",
    "summary": "Declare → derive → merge the release PR → publish",
    "endpoint": "Published identity; declared receipt closeout is a separate PR.",
    "guide": "/guides/releasing-a-version/",
    "asset": "lane-release.svg",
    "map": {
      "id": "release",
      "title": "Prepare a release through a reviewed PR",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Real release path, not --dry-run. Preparation stops at a release PR. Tag composition belongs to a qualified hosted publisher after merge and exact-head CI, never the interactive checkout.",
      "outcome": "An exact published tag and declared asset inventory after authorization and read-back. When provenance is declared, retain the original receipt and merge its separate closeout PR; publication alone does not finish that record.",
      "sources": {
        "pr": {
          "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
          "quote": "`commit-gate` MUST have cleared on the current HEAD.",
          "currentQuote": "Establish applicable verification for the current HEAD."
        },
        "release": {
          "path": "core/surface/commands/release.md",
          "currentPath": "core/surface/skills/release/SKILL.md",
          "quote": "## Dry run"
        },
        "releaseAssets": {
          "path": "core/surface/commands/release.md",
          "currentPath": "core/surface/skills/release/SKILL.md",
          "quote": "declared assets are qualified in the protected publisher before any tag push",
          "currentQuote": "The qualifying hosted publisher MUST declare and enforce one reviewed asset path before the release PR merges"
        },
        "releaseAuth": {
          "path": "core/surface/skills/release/SKILL.md",
          "quote": "CI success alone never creates authorization"
        },
        "releaseHosted": {
          "path": "core/surface/skills/release/SKILL.md",
          "quote": "Phase 2 is a contract for the qualifying hosted publisher, not a local fallback."
        },
        "releasePR": {
          "path": "core/surface/skills/release/SKILL.md",
          "quote": "The release commit must merge through a pull request before any tag is composed."
        },
        "releaseReceipt": {
          "path": "core/surface/skills/release/SKILL.md",
          "quote": "provenance closeout remains pending until that PR merges."
        },
        "releaseSkill": {
          "path": "core/surface/skills/release/SKILL.md",
          "quote": "# release"
        },
        "releaseVersion": {
          "path": "core/surface/commands/release.md",
          "currentPath": "core/surface/skills/release/SKILL.md",
          "quote": "The base accounts for both the last compatible tag and every declared manifest.",
          "currentQuote": "**`$BASE_VERSION`"
        }
      },
      "chapters": [
        {
          "id": "resolve-release",
          "title": "Resolve and derive",
          "question": "Which target and version are actually eligible?",
          "output": "A resolved target, target-scoped history and a derived identity. Missing declarations or required notes are explicit stops or governed back-fill.",
          "nodes": [
            {
              "id": "release-entry",
              "role": "command",
              "label": [
                "/ca:release"
              ],
              "title": "/ca:release: select the declared target",
              "href": "/reference/commands/release/",
              "source": "release",
              "detail": "Use the sole declared target or name the intended one. An unknown or ambiguous selection stops rather than choosing a familiar plugin or version.",
              "output": "One explicit target and the real versus dry-run mode."
            },
            {
              "id": "release-preflight",
              "role": "skill",
              "label": [
                "Release",
                "pre-flight"
              ],
              "title": "release: pre-flight and target resolution",
              "href": "/reference/skills/release/",
              "source": "releaseSkill",
              "detail": "Resolve project and shell context, the declared row, clean non-default branch, current verification and relevant questions. A missing declaration uses confirmed back-fill, not a guessed row.",
              "output": "A target with its preconditions and verification scope."
            },
            {
              "id": "release-version",
              "role": "skill",
              "label": [
                "Derive version"
              ],
              "title": "release: version derivation",
              "href": "/reference/skills/release/",
              "source": "releaseVersion",
              "detail": "Classify only the target’s payload window. Derive through its declared policy using compatible tags and manifests; required changelog notes come from actual commit evidence.",
              "output": "The derived version, rationale and target-scoped notes."
            }
          ],
          "edges": [
            {
              "to": "release-preflight",
              "kind": "sequence",
              "label": "declared owner",
              "source": "release",
              "detail": "The command routes to the reusable release skill.",
              "from": "release-entry"
            },
            {
              "to": "release-version",
              "kind": "sequence",
              "label": "target scoped",
              "source": "releaseVersion",
              "detail": "Sibling target history must not bump this target.",
              "from": "release-preflight"
            }
          ]
        },
        {
          "id": "prepare-release",
          "title": "Prepare the release PR",
          "question": "What is reviewed before a tag can exist?",
          "output": "The release PR describes committed surfaces, exact declared asset names and their reviewed hosted qualification path. Stop this invocation: no tag composition before merge.",
          "nodes": [
            {
              "id": "release-surfaces",
              "role": "skill",
              "label": [
                "Update",
                "surfaces"
              ],
              "title": "release: declared manifests and changelog",
              "href": "/reference/skills/release/",
              "source": "release",
              "detail": "Update only declared surfaces and run the post-bump pre-tag checks. Report exact asset names and the hosted qualification path without executing release-build locally.",
              "output": "The intended diff and declaration, not a local publication payload."
            },
            {
              "id": "release-commit",
              "role": "skill",
              "label": [
                "commit-gate"
              ],
              "title": "commit-gate: release changes",
              "href": "/reference/skills/commit-gate/",
              "source": "releasePR",
              "detail": "Commit the release edits through the existing permission, selected-file and evidence gate. A tag names a commit, never outstanding working-tree changes.",
              "output": "Committed release changes and current gate results."
            },
            {
              "id": "release-pr",
              "role": "command",
              "label": [
                "/ca:pr",
                "procedure"
              ],
              "title": "Ordinary PR procedure",
              "href": "/reference/commands/pr/",
              "source": "releasePR",
              "detail": "Route the committed branch through the ordinary PR path. The release skill stops here instead of composing a tag on this branch.",
              "output": "A reviewable release request with the publisher and intended cohort disclosed."
            },
            {
              "id": "release-review",
              "role": "agent",
              "label": [
                "PR reviewers",
                "+ verdict"
              ],
              "title": "Applicable PR review and owner decision",
              "href": "/reference/commands/pr/",
              "source": "pr",
              "detail": "Run the path-selected review and current-head checks. The owner decides whether to merge. The PR’s own head is not the later hosted publication identity.",
              "output": "A reviewed release PR; merge remains explicit."
            }
          ],
          "edges": [
            {
              "to": "release-commit",
              "kind": "dispatch",
              "label": "gated persistence",
              "source": "releasePR",
              "detail": "Commit release edits through the existing gate.",
              "from": "release-surfaces"
            },
            {
              "to": "release-pr",
              "kind": "sequence",
              "label": "mandatory PR",
              "source": "releasePR",
              "detail": "The release branch must use the PR route and stop this invocation.",
              "from": "release-commit"
            },
            {
              "to": "release-review",
              "kind": "dispatch",
              "label": "review before merge",
              "source": "pr",
              "detail": "Apply the ordinary PR reviewer and merge requirements.",
              "from": "release-pr"
            }
          ]
        },
        {
          "id": "hosted-release",
          "title": "Qualify the merged candidate",
          "question": "Which environment can compose the tag?",
          "output": "A qualified hosted publisher identifies the exact fetched default-branch commit and green evidence. Missing capability, stale surfaces or asset mismatch stops publication.",
          "nodes": [
            {
              "id": "release-hosted",
              "role": "skill",
              "label": [
                "Hosted",
                "candidate"
              ],
              "title": "release: bind the hosted candidate",
              "href": "/reference/skills/release/",
              "source": "releaseHosted",
              "detail": "After the release PR merges, a fresh hosted checkout must equal the fetched default branch and satisfy exact-head checks. Bind the current release section and every declared manifest.",
              "output": "The merged candidate identity, not the earlier PR head."
            },
            {
              "id": "release-qualify",
              "role": "skill",
              "label": [
                "Qualify assets"
              ],
              "title": "release: exact hosted inventory",
              "href": "/reference/skills/release/",
              "source": "releaseAssets",
              "detail": "The reviewed publisher either builds the declared assets or verifies a retained exact-head CI cohort. Local scratch files do not cross the PR boundary as publication input.",
              "output": "The declared inventory and candidate-bound evidence, when assets are declared."
            },
            {
              "id": "release-tag",
              "role": "skill",
              "label": [
                "Compose tag"
              ],
              "title": "release: hosted annotated tag",
              "href": "/reference/skills/release/",
              "source": "releaseHosted",
              "detail": "Classify the observed tag/release state, compose only when appropriate, and verify the stored tag message. An already-published identity is not replaced.",
              "output": "An annotated tag in the isolated hosted checkout and a report; nothing yet pushed."
            }
          ],
          "edges": [
            {
              "to": "release-qualify",
              "kind": "sequence",
              "label": "qualified cohort",
              "source": "releaseAssets",
              "detail": "The exact merged candidate owns the package evidence.",
              "from": "release-hosted"
            },
            {
              "to": "release-tag",
              "kind": "sequence",
              "label": "before publication",
              "source": "releaseHosted",
              "detail": "The qualifying hosted publisher owns tag composition; the interactive agent does not run it locally.",
              "from": "release-qualify"
            }
          ]
        },
        {
          "id": "publish-release",
          "title": "Authorize, publish and retain proof",
          "question": "What is public, and what still needs a record?",
          "output": "Read back exact publication before cleanup. When a provenance manifest is declared, close its receipt through a separate PR rather than editing the hosted default branch.",
          "nodes": [
            {
              "id": "release-publish",
              "role": "skill",
              "label": [
                "Authorized",
                "publication"
              ],
              "title": "release: consume explicit authorization",
              "href": "/reference/skills/release/",
              "source": "releaseAuth",
              "detail": "Only the declared publisher consumes the applicable one-cohort permission. An explicit merge instruction after the release-PR report can supply it for that protected publisher; CI success alone cannot.",
              "output": "An authorized push and release creation for the identified cohort."
            },
            {
              "id": "release-readback",
              "role": "skill",
              "label": [
                "Read back",
                "publication"
              ],
              "title": "release: inspect remote identities and assets",
              "href": "/reference/skills/release/",
              "source": "releaseReceipt",
              "detail": "Read back the annotated tag, dereferenced commit, non-draft release and exact asset names. Preserve partial failure evidence instead of recreating published identities.",
              "output": "The observed publication result, not merely an upload attempt."
            },
            {
              "id": "release-receipt",
              "role": "skill",
              "label": [
                "Receipt",
                "closeout"
              ],
              "title": "release: retain the original receipt",
              "href": "/reference/skills/release/",
              "source": "releaseReceipt",
              "detail": "If declared, capture the original remote provenance and hand off a non-default-branch receipt PR. Closeout remains pending until that PR merges. With no declared manifest, say explicitly that this step is skipped.",
              "output": "Published release plus an explicit completed or pending provenance boundary."
            }
          ],
          "edges": [
            {
              "to": "release-readback",
              "kind": "sequence",
              "label": "verify the remote",
              "source": "releaseReceipt",
              "detail": "A successful command alone is not proof of the remote inventory.",
              "from": "release-publish"
            },
            {
              "to": "release-receipt",
              "kind": "sequence",
              "label": "retain original evidence",
              "source": "releaseReceipt",
              "detail": "Capture the original publication identity before disposing of positively identified scratch state.",
              "from": "release-readback"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "release-surfaces",
          "kind": "sequence",
          "label": "real run only",
          "source": "release",
          "detail": "Dry run stops before modifying surfaces.",
          "from": "release-version"
        },
        {
          "to": "release-hosted",
          "kind": "sequence",
          "label": "after owner merge",
          "source": "releaseHosted",
          "detail": "Only the actual merged, green default-branch candidate may enter the qualifying hosted publisher.",
          "from": "release-review"
        },
        {
          "to": "release-publish",
          "kind": "sequence",
          "label": "one-cohort authority",
          "source": "releaseAuth",
          "detail": "Consume explicit publisher authorization, including the narrowly defined prior release-PR merge instruction where applicable.",
          "from": "release-tag"
        }
      ]
    },
    "notes": [
      {
        "title": "Dry run stops before writes",
        "detail": "It reads current local refs and derives the target/version window. It does not fetch, run commit-gate or declared tests/builds, create assets, compose tags or publish. A green preview does not qualify a release.",
        "source": "release"
      },
      {
        "title": "Hosted publication is a prerequisite",
        "detail": "No qualifying hosted publisher means a stop before tag composition. Add and review that capability separately, not a local fallback or an ignored build failure.",
        "source": "releaseHosted"
      },
      {
        "title": "Do not ask twice for the same authorized cohort",
        "detail": "A declared protected automatic post-CI publisher can consume the explicit merge instruction given after the release-PR report and before merge. That does not authorize a later cohort or rebuilt candidate.",
        "source": "releaseAuth"
      },
      {
        "title": "Publication and provenance closure differ",
        "detail": "Report the release as live only after read-back. A branch-only provenance append is not closeout; its receipt must reach the declared default-branch record through a PR.",
        "source": "releaseReceipt"
      }
    ]
  },
  {
    "id": "greenfield",
    "title": "Initialize a new project from intent",
    "summary": "Scaffold → resumable interview → confirm records → populate → initialize",
    "endpoint": "Populated project context; implementation has not started.",
    "guide": "/guides/plan-a-new-project/",
    "asset": "lane-init-greenfield.svg",
    "map": {
      "id": "greenfield",
      "title": "Initialize a new project from intent",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Choose this route only when meaningful source does not yet exist. A decomposition persona is not an extra agent dispatch. Existing source selects the separate brownfield route.",
      "outcome": "Five HTML knowledge documents, decomposition records holding the answered interview and confirmed intended architecture, promoted work on the task board, and native initialization. Unknowns stay recorded as unknown. Continue already-authorized work; population alone does not prove implementation or verification.",
      "sources": {
        "decompose": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 2 — Draft persistence (or resume) · gate: BLOCK",
          "currentQuote": "## 1. Inspect and resume"
        },
        "greenLock": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 6 — Initialization lock & cleanup · gate: BLOCK",
          "currentQuote": "## 5. Initialize and return to work"
        },
        "init": {
          "path": "core/surface/commands/init.md",
          "quote": "The populator is **mandatory, not optional**"
        },
        "interview": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "Gate: all six layers complete",
          "currentQuote": "Record each question as a decomposition `question` record when you ask it"
        },
        "populate": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 5 — project-state population · gate: BLOCK",
          "currentQuote": "## 4. Populate context"
        },
        "threeDocs": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "Gate: all three artifact files on disk AND the user explicitly approves all three",
          "currentQuote": "Show the user the synthesized records."
        }
      },
      "chapters": [
        {
          "id": "begin-greenfield",
          "title": "Choose the new-project route",
          "question": "Why is an activation flag not enough?",
          "output": "A writable project-state scaffold and a valid new-project interview or explicit resume choice. An initialized project is not reinitialized.",
          "nodes": [
            {
              "id": "green-init",
              "role": "command",
              "label": [
                "/ca:init"
              ],
              "title": "/ca:init: scaffold once",
              "href": "/reference/commands/init/",
              "source": "init",
              "detail": "The scaffolder writes activation and empty state but no initialization sentinel. It refuses to overwrite existing state; an uninitialized stub enters its selected populator directly.",
              "output": "An enabled stub that is not ready for normal work."
            },
            {
              "id": "green-entry",
              "role": "command",
              "label": [
                "/ca:decompose"
              ],
              "title": "/ca:decompose: selected strategy",
              "href": "/reference/commands/decompose/",
              "source": "init",
              "detail": "Automatic detection or --greenfield chooses the decomposition workflow. Source-shape mismatches remain stops rather than forced population.",
              "output": "The explicitly selected greenfield route."
            },
            {
              "id": "green-resume",
              "role": "skill",
              "label": [
                "decompose"
              ],
              "title": "decompose: establish or resume drafts",
              "href": "/reference/skills/decompose/",
              "source": "decompose",
              "detail": "Create any missing knowledge documents and read the decomposition records. Answered questions stay settled; resume with the open question that matters most for the next step, not a fixed first-unfinished phase.",
              "output": "Durable interview records and the next relevant open question."
            }
          ],
          "edges": [
            {
              "to": "green-entry",
              "kind": "sequence",
              "label": "no meaningful source",
              "source": "init",
              "detail": "The stub must pass through its greenfield populator.",
              "from": "green-init"
            },
            {
              "to": "green-resume",
              "kind": "sequence",
              "label": "interview owner",
              "source": "decompose",
              "detail": "The selected skill prepares persistence before questioning.",
              "from": "green-entry"
            }
          ]
        },
        {
          "id": "design-project",
          "title": "Confirm the intended project",
          "question": "What did the interview produce that the user must inspect?",
          "output": "Capability, component, phase and work-item records the user confirmed. They describe intended architecture, not a typed feature execution plan or existing code.",
          "nodes": [
            {
              "id": "green-layers",
              "role": "skill",
              "label": [
                "Resumable",
                "interview"
              ],
              "title": "decompose: record questions and answers",
              "href": "/reference/skills/decompose/",
              "source": "interview",
              "detail": "Explore problem, users, capabilities, technical shape, integrations and risks in the order the conversation makes natural. Each question is saved when asked and each actual answer as soon as it is given. ADR attribution uses the decision-lifecycle owner; unresolved facts remain open questions.",
              "output": "Answered and open question records, with linked draft decisions."
            },
            {
              "id": "green-docs",
              "role": "skill",
              "label": [
                "Intended",
                "architecture"
              ],
              "title": "decompose: synthesize records",
              "href": "/guides/plan-a-new-project/",
              "source": "threeDocs",
              "detail": "From the answered questions and linked ADRs, add capability, component, phase and work-item decomposition records, each linked to the answers it rests on.",
              "output": "Intended architecture, phased delivery and proposed work as records."
            },
            {
              "id": "green-approve",
              "role": "skill",
              "label": [
                "Confirm",
                "records"
              ],
              "title": "decompose: confirm the project definition",
              "href": "/guides/plan-a-new-project/",
              "source": "threeDocs",
              "detail": "Show the synthesized records, apply corrections with record updates and save the user's actual confirmation as an answered question. A wording or method refinement needs no fresh confirmation; remaining gaps stay open questions.",
              "output": "The confirmed project definition before population."
            }
          ],
          "edges": [
            {
              "to": "green-docs",
              "kind": "sequence",
              "label": "complete durable input",
              "source": "threeDocs",
              "detail": "Synthesis rereads the saved answers and linked decisions rather than trusting conversation memory.",
              "from": "green-layers"
            },
            {
              "to": "green-approve",
              "kind": "return",
              "label": "user review",
              "source": "threeDocs",
              "detail": "No population until the user confirms the records match their choices.",
              "from": "green-docs"
            }
          ]
        },
        {
          "id": "lock-greenfield",
          "title": "Populate and initialize",
          "question": "What exists when control returns to normal operation?",
          "output": "Five HTML knowledge documents, promoted work on the task board, the question board, audit header and native initialization. Decomposition holds intended design; the code map records only what code exists.",
          "nodes": [
            {
              "id": "green-populate",
              "role": "skill",
              "label": [
                "Populate",
                "state"
              ],
              "title": "decompose: populate project context",
              "href": "/reference/skills/decompose/",
              "source": "populate",
              "detail": "Add knowledge records for what is known, each with its basis; planned commands stay proposed and unrun, and unknowns stay unknown. Promote each approved work item once with knowledge.py promote; decision-lifecycle owns actual ADR choices.",
              "output": "Populated knowledge documents and promoted tasks, with open questions and intended roadmap retained."
            },
            {
              "id": "green-lock",
              "role": "skill",
              "label": [
                "Initialize"
              ],
              "title": "decompose: native initialization",
              "href": "/reference/skills/decompose/",
              "source": "greenLock",
              "detail": "knowledge.py initialize checks that the five knowledge documents exist and parse and the task board is well formed, then commits the initialization marker. Open questions do not prevent it; a refusal names the document to repair.",
              "output": "Initialized project state; no implied feature, commit or PR completion."
            }
          ],
          "edges": [
            {
              "to": "green-lock",
              "kind": "sequence",
              "label": "then initialize",
              "source": "greenLock",
              "detail": "Initialization records structural availability only; it does not require every question answered or any command run.",
              "from": "green-populate"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "green-layers",
          "kind": "sequence",
          "label": "fresh or resumed interview",
          "source": "decompose",
          "detail": "Continue from the saved answers; nothing settled is asked again.",
          "from": "green-resume"
        },
        {
          "to": "green-populate",
          "kind": "sequence",
          "label": "records confirmed",
          "source": "populate",
          "detail": "Population consumes the confirmed records, not a guessed summary.",
          "from": "green-approve"
        },
        {
          "to": "green-docs",
          "kind": "repeat",
          "label": "Requested corrections",
          "source": "threeDocs",
          "detail": "Update the records and show them again; preserve the recorded intent.",
          "from": "green-approve"
        }
      ]
    },
    "notes": [
      {
        "title": "Release intent is not a declared target",
        "detail": "The interview records tag-prefix and changelog preferences. With no manifest or tag to substantiate a declaration, it must not invent release-targets.md.",
        "source": "populate"
      },
      {
        "title": "Intent and implementation stay distinct",
        "detail": "Decomposition records hold intended architecture and the code map holds observed structure. Planned commands remain proposed and unrun; refresh context against real sources and manifests when they arrive.",
        "source": "populate"
      },
      {
        "title": "Initialization is not the first feature",
        "detail": "The endpoint is populated project context and observed initialization. Continue already-authorized work through its owner; initialization alone does not claim feature completion or PR delivery.",
        "source": "greenLock"
      }
    ]
  },
  {
    "id": "brownfield",
    "title": "Initialize existing code from evidence",
    "summary": "Scaffold → inspect bounded source → record with basis → initialize",
    "endpoint": "Source-backed knowledge records with explicit gaps and cited sources.",
    "guide": "/guides/understand-an-existing-project/",
    "asset": "lane-init-brownfield.svg",
    "map": {
      "id": "brownfield",
      "title": "Initialize existing code from evidence",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Choose this route when meaningful source exists. Initial or full work covers six logical categories through direct bounded inspection or optional scoped agents; scoped refreshes cover only declared affected categories through context-check. Actual host permissions and excluded paths apply. An agent label does not prove containment or semantic correctness.",
      "outcome": "Populated HTML knowledge records, each with its basis and cited sources, including a path-scoped code map. Material user-owned questions retain actual resolutions or explicit deferrals; other unknowns remain visible as unknown records. It does not invent a greenfield decomposition.",
      "sources": {
        "brownLock": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 6 — Initialization lock · gate: BLOCK",
          "currentQuote": "Run `knowledge.py initialize`."
        },
        "context": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 1 — Pre-flight confirmation · gate: BLOCK"
        },
        "gaps": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 4 — Gap interview · gate: BLOCK",
          "currentQuote": "## Phase 4 — Gap interview"
        },
        "init": {
          "path": "core/surface/commands/init.md",
          "quote": "The populator is **mandatory, not optional**"
        },
        "scouts": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "Dispatch six isolated `scout` subagents simultaneously.",
          "currentQuote": "Use direct bounded inspection or optional scoped agents, whichever reduces"
        },
        "synthesis": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 3 — Synthesis · gate: BLOCK"
        },
        "writeContext": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 5 — Project-state write · gate: BLOCK",
          "currentQuote": "No document approval receipt or agent profile is required."
        }
      },
      "chapters": [
        {
          "id": "inspect-code",
          "title": "Inspect bounded source evidence",
          "question": "Who reads the code, and what crosses the context boundary?",
          "output": "Initial/full work accounts for all six categories with inspected evidence and explicit unknowns. Scoped refresh retains the declared affected coverage; missing reports can be resolved through direct inspection.",
          "nodes": [
            {
              "id": "brown-init",
              "role": "command",
              "label": [
                "/ca:init"
              ],
              "title": "/ca:init: scaffold once",
              "href": "/reference/commands/init/",
              "source": "init",
              "detail": "Create the enabled stub only when absent. Select the existing-code populator rather than treating the activation flag as completed initialization.",
              "output": "The project-state scaffold."
            },
            {
              "id": "brown-entry",
              "role": "command",
              "label": [
                "/ca:create-",
                "context"
              ],
              "title": "/ca:create-context: selected strategy",
              "href": "/reference/commands/create-context/",
              "source": "init",
              "detail": "Automatic detection or --brownfield selects this existing workflow. A completed initialization marker or wrong source shape retains the route’s stop.",
              "output": "A valid existing-code extraction request."
            },
            {
              "id": "brown-preflight",
              "role": "skill",
              "label": [
                "context-",
                "creation"
              ],
              "title": "context-creation: confirm the source",
              "href": "/reference/skills/context-creation/",
              "source": "context",
              "detail": "Confirm meaningful code, an uninitialized context and primary source directories. Check actual host permissions before reading; ordinary work does not require a special scout profile.",
              "output": "A bounded source surface to inspect."
            },
            {
              "id": "brown-scouts",
              "role": "skill",
              "label": [
                "Bounded",
                "inspection"
              ],
              "title": "context-creation: direct or delegated inspection",
              "href": "/reference/skills/context-creation/",
              "source": "scouts",
              "detail": "Inspect stack, infrastructure, architecture, security, testing and data model for initial/full work; scoped refresh covers affected categories. Optional agents receive finite assignments within host limits. Retain citations, source identities, conflicts and unknowns without secret values.",
              "output": "Bounded evidence for the declared scope; agent labels and hashes do not verify semantics."
            }
          ],
          "edges": [
            {
              "to": "brown-entry",
              "kind": "sequence",
              "label": "source exists",
              "source": "init",
              "detail": "Choose the brownfield populator for existing code.",
              "from": "brown-init"
            },
            {
              "to": "brown-preflight",
              "kind": "sequence",
              "label": "validate source shape",
              "source": "context",
              "detail": "The skill validates its own preconditions.",
              "from": "brown-entry"
            },
            {
              "to": "brown-scouts",
              "kind": "sequence",
              "label": "bounded inspection",
              "source": "scouts",
              "detail": "Inspect the selected source directly or delegate finite assignments within actual host permissions.",
              "from": "brown-preflight"
            }
          ]
        },
        {
          "id": "synthesize-context",
          "title": "Resolve the evidence gaps",
          "question": "Which claims are known, and which need the user?",
          "output": "Real values come from cited inspection and actual owner decisions. Uncertainty remains visible; independent solvable work need not wait for unrelated gaps.",
          "nodes": [
            {
              "id": "brown-synthesis",
              "role": "skill",
              "label": [
                "Synthesize",
                "evidence"
              ],
              "title": "context-creation: source-backed synthesis",
              "href": "/reference/skills/context-creation/",
              "source": "synthesis",
              "detail": "Turn inspected evidence into project, stack, standards, security and code-map records, each with its basis; source-observed records cite their source and are scoped to the paths they govern. Reinspect disputed or changed sources when useful; do not turn an inferred claim into a verified fact.",
              "output": "Draft records with the evidence and unresolved facts visible."
            },
            {
              "id": "brown-gaps",
              "role": "skill",
              "label": [
                "Gap interview"
              ],
              "title": "context-creation: resolve or defer",
              "href": "/reference/skills/context-creation/",
              "source": "gaps",
              "detail": "Ask only missing material user-owned decisions. Record actual resolutions or explicit deferrals through the question owner. Real unresolved prerequisites stop dependent work; unrelated uncertainty stays visible without blocking independent work.",
              "output": "Actual decisions and explicit gaps, without invented approval or deferral."
            },
            {
              "id": "brown-write",
              "role": "skill",
              "label": [
                "Write context"
              ],
              "title": "context-creation: write project state",
              "href": "/reference/skills/context-creation/",
              "source": "writeContext",
              "detail": "Write the records with knowledge.py add and update. Each write is checked and journaled by the native engine and is safe to retry; no per-document approval receipt is required. Board mutations retain their own helper; a release-target row remains conditional on real evidence or a resolved declaration.",
              "output": "Populated knowledge documents and separately maintained task state."
            }
          ],
          "edges": [
            {
              "to": "brown-gaps",
              "kind": "return",
              "label": "missing facts",
              "source": "gaps",
              "detail": "Only the needed user facts are asked, not a second greenfield interview.",
              "from": "brown-synthesis"
            },
            {
              "to": "brown-write",
              "kind": "sequence",
              "label": "resolved or deferred",
              "source": "writeContext",
              "detail": "Apply supported claims and actual decisions while preserving human content, protected owners and explicit unknowns.",
              "from": "brown-gaps"
            }
          ]
        },
        {
          "id": "lock-brownfield",
          "title": "Bind sources and finish",
          "question": "What keeps this context inspectable after the interview?",
          "output": "The initialized marker and required files are present. The resulting evidence is inspectable; it is not a guarantee that every inferred claim is correct.",
          "nodes": [
            {
              "id": "brown-provenance",
              "role": "skill",
              "label": [
                "Sources",
                "+ code map"
              ],
              "title": "context-creation: cite evidence",
              "href": "/concepts/provenance-drift/",
              "source": "writeContext",
              "detail": "Each source-observed record cites the files it rests on, and each document keeps a baseline commit, so knowledge.py stale later lists exactly the records whose sources changed. Citations do not manufacture semantic review.",
              "output": "Traceable source pointers and the current code map."
            },
            {
              "id": "brown-lock",
              "role": "skill",
              "label": [
                "Lock + return"
              ],
              "title": "context-creation: initialization lock",
              "href": "/reference/skills/context-creation/",
              "source": "brownLock",
              "detail": "For initial population only, knowledge.py initialize checks that the five knowledge documents exist and parse and the task board is well formed, then commits the marker. Unknown records and open questions do not prevent it. Initialized refresh retains its marker and never initializes again.",
              "output": "Initialized source-backed context, not an implemented change."
            }
          ],
          "edges": [
            {
              "to": "brown-lock",
              "kind": "sequence",
              "label": "structural check",
              "source": "brownLock",
              "detail": "Initialization checks that the documents exist and parse, not that every question is answered.",
              "from": "brown-provenance"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "brown-synthesis",
          "kind": "return",
          "label": "bounded evidence",
          "source": "scouts",
          "detail": "Account for six logical categories for initial/full work, or exactly the affected categories for scoped refresh. Direct inspection may resolve missing coverage; failed or uninspected work remains unknown.",
          "from": "brown-scouts"
        },
        {
          "to": "brown-scouts",
          "kind": "repeat",
          "label": "Missing or contested evidence",
          "source": "scouts",
          "detail": "Narrow the assignment or directly reinspect the source within actual host permissions. Retain the failed attempt and unknown scope; do not invent a successful report.",
          "from": "brown-scouts"
        },
        {
          "to": "brown-provenance",
          "kind": "sequence",
          "label": "bind derived claims",
          "source": "writeContext",
          "detail": "Source-derived records retain their citations instead of only their final prose.",
          "from": "brown-write"
        }
      ]
    },
    "notes": [
      {
        "title": "This is not greenfield decomposition",
        "detail": "Existing-code extraction does not fabricate decomposition records as a retrospective roadmap.",
        "source": "context"
      },
      {
        "title": "Use actual permissions and bounded evidence",
        "detail": "Direct bounded inspection and optional scoped agents support the same source-backed claims. Neither an agent label nor a report format proves containment or semantic correctness. Actual host controls remain binding.",
        "source": "scouts"
      },
      {
        "title": "A sentinel is not a general guarantee",
        "detail": "Initialization establishes populated state and an explicit gap disposition. Inspect the source claims and test the installed enforcement separately.",
        "source": "brownLock"
      }
    ]
  }
];
/** Resolve only reviewed, explicitly registered diagrams. */
export function getWorkflow(id: string): WorkflowDefinition {
  const result = workflows.find(workflow => workflow.id === id);
  if (!result) throw new Error(`Unknown workflow: ${id}`);
  return result;
}
