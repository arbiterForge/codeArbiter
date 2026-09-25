/** C04 source-bound teaching maps, not an orchestration DSL or runtime authority. */
import type { ExecutionMap } from './model';
export interface WorkflowDefinition {
  id: string; title: string; summary: string; endpoint: string; guide: string; asset: string;
  map: ExecutionMap; notes: Array<{ title: string; detail: string; source: string }>;
}
export const workflows: readonly WorkflowDefinition[] = [
  {
    "id": "sprint",
    "title": "An approved sprint reaches a PR",
    "summary": "Review the pair → execute within scope → inspect the PR",
    "endpoint": "Open PR; merge is a separate decision.",
    "guide": "/guides/autonomous-sprints/",
    "asset": "lane-sprint.svg",
    "map": {
      "id": "sprint",
      "title": "An approved sprint reaches a PR",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "New full-lane sprint, normal premium path. The initial HTML pair uses its qualified one-reply transaction. There are no attended per-batch pauses; real hard gates still stop. This is a source-traced route, not a captured host run.",
      "outcome": "An open PR and sprint receipt with current evidence, decisions and remaining work. The sprint never merges or discards the branch.",
      "sources": {
        "autonomy": {
          "path": "core/surface/SPRINT.md",
          "quote": "WITHOUT per-batch\nhuman checkpoints"
        },
        "finish": {
          "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
          "quote": "MUST NOT auto-merge under `/sprint`"
        },
        "pair": {
          "path": "core/surface/SPRINT.md",
          "quote": "commits approval plus plan binding in one recoverable native transaction."
        },
        "pr": {
          "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
          "quote": "`commit-gate` MUST have cleared on the current HEAD."
        },
        "sprint": {
          "path": "core/surface/SPRINT.md",
          "quote": "## Phase 1 — Sprint spec · gate: STOP"
        },
        "sprintExit": {
          "path": "core/surface/SPRINT.md",
          "quote": "AUTO-SELECTS open-PR and surfaces the merge decision to the user."
        },
        "sprintRecovery": {
          "path": "core/surface/SPRINT.md",
          "quote": "A failed TDD, coverage, lint, or fresh-verification result blocks acceptance, not authorized repair."
        },
        "task": {
          "path": "core/surface/skills/subagent-driven-development/SKILL.md",
          "quote": "The subagent works test-first by routing through the `tdd` skill"
        },
        "taskReview": {
          "path": "core/surface/skills/subagent-driven-development/SKILL.md",
          "quote": "Runs ONCE per scope — after every task in the current scope has cleared Phase 3 and Phase 5"
        },
        "tdd": {
          "path": "core/surface/skills/tdd/SKILL.md",
          "quote": "A `MISSING` obligation returns the workflow to Phase 2"
        }
      },
      "chapters": [
        {
          "id": "review-pair",
          "title": "Review the whole sprint",
          "question": "What must be approved before autonomy begins?",
          "output": "Both exact artifact identities are approved and bound. A draft, a generic yes or an unobserved reply cannot begin execution.",
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
              "detail": "Capture the outcome, exclusions, priorities and hard constraints. Consult recorded intent before asking for approval.",
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
              "detail": "For the initial pair, use the draft-for-pair path. Review criteria, tasks, tests, paths, dependencies and checkpoints together.",
              "output": "A same-slug draft plan. Draft readiness is not authority."
            },
            {
              "id": "sprint-approve",
              "role": "command",
              "label": [
                "Approve pair"
              ],
              "title": "/ca:sprint: initial pair approval",
              "href": "/reference/commands/sprint/",
              "source": "pair",
              "detail": "The qualified adapter arms both definitions. Its exact reply names both artifacts and approve-only or delegate-methods. One observed reply commits approval and binding in a recoverable transaction.",
              "output": "Both current approved identities, not two invented receipts."
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
              "detail": "Planning may read this ready draft only through the initial sprint pair path.",
              "from": "sprint-spec"
            },
            {
              "to": "sprint-approve",
              "kind": "return",
              "label": "review together",
              "source": "pair",
              "detail": "Present the complete pair and exact delegation terms before the host observes approval.",
              "from": "sprint-plan"
            }
          ]
        },
        {
          "id": "execute-tasks",
          "title": "Build and verify each task",
          "question": "What replaces the attended batch coordinator?",
          "output": "Each task has specification review and fresh verification. Typed REVIEW remains provisional until scope acceptance.",
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
              "detail": "The sprint hands the approved plan directly to the task engine rather than inserting executing-plans human checkpoints. Eligibility and current context tickets still constrain the task.",
              "output": "One eligible task inside the approved scope."
            },
            {
              "id": "sprint-author",
              "role": "agent",
              "label": [
                "Fresh author"
              ],
              "title": "Scope-selected author",
              "href": "/concepts/persona-and-context/",
              "source": "task",
              "detail": "Dispatch the appropriate backend, frontend or infrastructure author with the task context. The author is not the reviewer who accepts its result.",
              "output": "Bounded implementation work in a fresh author context."
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
              "detail": "Derive obligations, demonstrate the intended RED failure, then satisfy the same assertion and the declared quality requirements.",
              "output": "Evidence returned to the caller, not permission to commit."
            },
            {
              "id": "sprint-proof",
              "role": "skill",
              "label": [
                "Review +",
                "verify"
              ],
              "title": "Task engine: specification review and verification",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "taskReview",
              "detail": "Inspect specification compliance and run the plan verification afresh. A self-reported author pass cannot supply required host authority.",
              "output": "Current per-task evidence before combined review."
            }
          ],
          "edges": [
            {
              "to": "sprint-author",
              "kind": "dispatch",
              "label": "eligible task",
              "source": "task",
              "detail": "Select a fresh author for this bounded task.",
              "from": "sprint-engine"
            },
            {
              "to": "sprint-tdd",
              "kind": "dispatch",
              "label": "test first",
              "source": "task",
              "detail": "TDD happens inside the task, not after all authoring is done.",
              "from": "sprint-author"
            },
            {
              "to": "sprint-proof",
              "kind": "return",
              "label": "independent proof",
              "source": "taskReview",
              "detail": "The task caller obtains the separate review and fresh verification.",
              "from": "sprint-tdd"
            }
          ]
        },
        {
          "id": "accept-scope",
          "title": "Accept the combined scope",
          "question": "What prevents a green task from becoming a false completion claim?",
          "output": "Complete current scope acceptance, or a persisted block. Only independently eligible work may continue after a blocked task.",
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
              "detail": "Review the combined diff once the tasks have their required proof. Security, dependency and migration reviewers are path-selected rather than an unconditional roster.",
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
              "detail": "Classify findings and keep out-of-scope work separate. Correct the affected work and rerun invalidated evidence instead of redispatching to evade a gate.",
              "output": "A disposition for the current findings.",
              "conditional": true
            },
            {
              "id": "sprint-accepted",
              "role": "skill",
              "label": [
                "Accept scope"
              ],
              "title": "Task engine: current acceptance",
              "href": "/reference/skills/subagent-driven-development/",
              "source": "sprintRecovery",
              "detail": "Use the installed authority and current typed identities to accept the required scope. Missing or stale authority remains a stop; the board cannot substitute for the plan.",
              "output": "Accepted scope evidence, or an explicit blocked state."
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
              "label": "no blocker",
              "source": "sprintRecovery",
              "detail": "Only applicable current evidence permits acceptance.",
              "from": "sprint-triage"
            }
          ]
        },
        {
          "id": "handoff",
          "title": "Commit and hand off the PR",
          "question": "Where does autonomous authority end?",
          "output": "Inspect the actual PR head, observed checks, low-confidence decisions and unresolved findings. A merge requires its own authority.",
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
              "detail": "Plan completion returns through the normal permission, selected-file and fresh-evidence gate. Recovery is not additional commit or publication authority.",
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
              "output": "An open PR and an inspectable sprint receipt."
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
          "kind": "dispatch",
          "label": "After both approvals",
          "source": "autonomy",
          "detail": "The sprint calls the task engine without attended batch pauses.",
          "from": "sprint-approve"
        },
        {
          "to": "sprint-engine",
          "kind": "repeat",
          "label": "More eligible tasks",
          "source": "taskReview",
          "detail": "Finish the remaining tasks before combined scope review.",
          "from": "sprint-proof"
        },
        {
          "to": "sprint-quality",
          "kind": "sequence",
          "label": "Task evidence complete",
          "source": "taskReview",
          "detail": "Combined quality review follows per-task review and verification.",
          "from": "sprint-proof"
        },
        {
          "to": "sprint-author",
          "kind": "return",
          "label": "Correction inside scope",
          "source": "sprintRecovery",
          "detail": "Rerun the original gate and every invalidated review. A security or authority stop is not an ordinary retry.",
          "from": "sprint-triage"
        },
        {
          "to": "sprint-commit",
          "kind": "sequence",
          "label": "Plan complete",
          "source": "sprintExit",
          "detail": "Only the completed selected plan reaches commit and PR delivery.",
          "from": "sprint-accepted"
        }
      ]
    },
    "notes": [
      {
        "title": "Initial approval is one exact pair transaction",
        "detail": "This is a current source capability for a qualified installed host. An unsupported host retains drafts; it cannot invent a receipt or silently switch to Markdown. Interrupted observed approval resumes its stored transaction.",
        "source": "pair"
      },
      {
        "title": "Autonomy is bounded",
        "detail": "SMARTS logs non-hard-gate choices. Delegate-methods only permits the defined steps-only revision path; it does not satisfy prerequisites, broaden scope or grant security, provider, spending or publication authority.",
        "source": "sprint"
      },
      {
        "title": "Failure is not an endless retry",
        "detail": "After two unchanged corrective attempts without new evidence, stop that strategy. Preserve blocked state and its dependents; continue only independently eligible work.",
        "source": "sprintRecovery"
      },
      {
        "title": "HTML farm remains disabled",
        "detail": "The HTML route refuses --farm before canary or dispatch. The separate legacy farm path is not implied by this premium-path map.",
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
          "path": "core/surface/commands/adr.md",
          "quote": "Status transitions require\nexplicit user instruction"
        },
        "adrAccept": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "quote": "### Accepted/Planned binding"
        },
        "adrCommit": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
          "quote": "its `source_commit` cannot truthfully name a commit that does\n   not exist yet."
        },
        "adrWrite": {
          "path": "core/surface/skills/decision-lifecycle/SKILL.md",
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
          "quote": "`commit-gate` MUST have cleared on the current HEAD."
        },
        "release": {
          "path": "core/surface/commands/release.md",
          "quote": "## Dry run"
        },
        "releaseAssets": {
          "path": "core/surface/commands/release.md",
          "quote": "declared assets are qualified in the protected publisher before any tag push"
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
          "quote": "The base accounts for both the last compatible tag and every declared manifest."
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
    "summary": "Scaffold → interview → approve three documents → initialize",
    "endpoint": "Populated project context; implementation has not started.",
    "guide": "/guides/plan-a-new-project/",
    "asset": "lane-init-greenfield.svg",
    "map": {
      "id": "greenfield",
      "title": "Initialize a new project from intent",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Choose this route only when meaningful source does not yet exist. A decomposition persona is not an extra agent dispatch. Existing source selects the separate brownfield route.",
      "outcome": "Populated project state, the three approved project-level Markdown documents, an initialization sentinel and no abandoned decomposition drafts. Code implementation and PR delivery are later work.",
      "sources": {
        "decompose": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 2 — Draft persistence (or resume) · gate: BLOCK"
        },
        "greenLock": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 6 — Initialization lock & cleanup · gate: BLOCK"
        },
        "init": {
          "path": "core/surface/commands/init.md",
          "quote": "The populator is **mandatory, not optional**"
        },
        "interview": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "Gate: all six layers complete"
        },
        "populate": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "## Phase 5 — project-state population · gate: BLOCK"
        },
        "threeDocs": {
          "path": "core/surface/skills/decompose/SKILL.md",
          "quote": "Gate: all three artifact files on disk AND the user explicitly approves all three"
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
              "detail": "Confirm pre-flight, explain the interview and inspect any existing draft session. Resume, restart and abort are user choices; do not silently delete prior drafts.",
              "output": "A durable draft workspace or a preserved stopped session."
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
          "title": "Review three guiding documents",
          "question": "What did the interview produce that the user must inspect?",
          "output": "All three project-level documents are on disk and explicitly approved. Their tasks are not a typed feature execution plan.",
          "nodes": [
            {
              "id": "green-layers",
              "role": "skill",
              "label": [
                "Six-layer",
                "interview"
              ],
              "title": "decompose: complete each layer",
              "href": "/reference/skills/decompose/",
              "source": "interview",
              "detail": "Explore problem, users, capabilities, technical shape, integrations and risks. Persist completed layers and draft choices. Unresolved facts receive named questions instead of guesses.",
              "output": "Six durable layer records and the applicable draft decisions."
            },
            {
              "id": "green-docs",
              "role": "skill",
              "label": [
                "Three guiding",
                "documents"
              ],
              "title": "decompose: synthesize from disk",
              "href": "/guides/plan-a-new-project/",
              "source": "threeDocs",
              "detail": "Reread the drafts and write 01-architecture-breakdown.md, 02-phased-build-plan.md and 03-task-backlog.md under .codearbiter/plans/ before review.",
              "output": "Architecture, phased delivery and a prioritized project backlog."
            },
            {
              "id": "green-approve",
              "role": "skill",
              "label": [
                "Review all",
                "three"
              ],
              "title": "decompose: iterate until approval",
              "href": "/guides/plan-a-new-project/",
              "source": "threeDocs",
              "detail": "Open each document, request corrections and approve all three explicitly. The existence of files or a conversation summary cannot stand in for this decision.",
              "output": "The reviewed project definition before population."
            }
          ],
          "edges": [
            {
              "to": "green-docs",
              "kind": "sequence",
              "label": "complete durable input",
              "source": "threeDocs",
              "detail": "Synthesis rereads the layer and draft-decision files rather than trusting conversation memory.",
              "from": "green-layers"
            },
            {
              "to": "green-approve",
              "kind": "return",
              "label": "user review",
              "source": "threeDocs",
              "detail": "No population until all three outputs are approved.",
              "from": "green-docs"
            }
          ]
        },
        {
          "id": "lock-greenfield",
          "title": "Populate and lock initialization",
          "question": "What exists when control returns to normal operation?",
          "output": "Inspect the populated tree, required files and sentinel. The interview did not generate a release-target row or meaningful source-code provenance.",
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
              "detail": "Reread the approved documents and layers, populate context and the task board, and promote the draft choices as specified. Write interview-derived provenance stubs and a coarse code-map stub.",
              "output": "Actual project context with questions and roadmap intent retained."
            },
            {
              "id": "green-lock",
              "role": "skill",
              "label": [
                "Lock + return"
              ],
              "title": "decompose: initialization lock and cleanup",
              "href": "/reference/skills/decompose/",
              "source": "greenLock",
              "detail": "Write the initialization sentinel, verify required state and remove the completed draft directory. Report normal operation, leaving implementation for the appropriate next lane.",
              "output": "Initialized project state; no implied feature, commit or PR completion."
            }
          ],
          "edges": [
            {
              "to": "green-lock",
              "kind": "sequence",
              "label": "inspect then lock",
              "source": "greenLock",
              "detail": "The skill closes only after the required state and cleanup are confirmed.",
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
          "detail": "Continue from completed layer boundaries after the selected resume action.",
          "from": "green-resume"
        },
        {
          "to": "green-populate",
          "kind": "sequence",
          "label": "all three approved",
          "source": "populate",
          "detail": "Population consumes reviewed files, not a guessed summary.",
          "from": "green-approve"
        },
        {
          "to": "green-docs",
          "kind": "repeat",
          "label": "Requested corrections",
          "source": "threeDocs",
          "detail": "Revise the on-disk artifacts and ask for review again; preserve the recorded intent.",
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
        "title": "Freshness is initially unknown",
        "detail": "Interview-derived empty provenance stubs do not claim file evidence. Real source mappings can be populated after code exists through the owning refresh workflow.",
        "source": "populate"
      },
      {
        "title": "Initialization is not the first feature",
        "detail": "The actual endpoint is usable project context. Start a feature or another selected lane separately; this route does not manufacture a PR ending.",
        "source": "greenLock"
      }
    ]
  },
  {
    "id": "brownfield",
    "title": "Initialize existing code from evidence",
    "summary": "Scaffold → isolated scouts → resolve gaps → initialize",
    "endpoint": "Source-backed context; no synthetic greenfield roadmap.",
    "guide": "/guides/understand-an-existing-project/",
    "asset": "lane-init-brownfield.svg",
    "map": {
      "id": "brownfield",
      "title": "Initialize existing code from evidence",
      "reviewedAt": "929229354e3a15ae3002c82116b66c837ab43729",
      "boundary": "Choose this route when meaningful source exists. Six isolated scout reports are required; the orchestrator synthesizes their reports rather than loading raw source. Missing isolation is a capability stop.",
      "outcome": "Populated source-backed project state, provenance and a code map, with each gap resolved or explicitly deferred before initialization. It does not invent the three greenfield planning documents.",
      "sources": {
        "brownLock": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 6 — Initialization lock · gate: BLOCK"
        },
        "context": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 1 — Pre-flight confirmation · gate: BLOCK"
        },
        "gaps": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 4 — Gap interview · gate: BLOCK"
        },
        "init": {
          "path": "core/surface/commands/init.md",
          "quote": "The populator is **mandatory, not optional**"
        },
        "scouts": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "Dispatch six isolated `scout` subagents simultaneously."
        },
        "synthesis": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 3 — Synthesis · gate: BLOCK"
        },
        "writeContext": {
          "path": "core/surface/skills/context-creation/SKILL.md",
          "quote": "## Phase 5 — Project-state write · gate: BLOCK"
        }
      },
      "chapters": [
        {
          "id": "inspect-code",
          "title": "Collect six bounded reports",
          "question": "Who reads the code, and what crosses the context boundary?",
          "output": "All six reports returned, including explicit not-found results. A missing report is not empty evidence and blocks synthesis.",
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
              "detail": "Confirm meaningful code and identify its primary source directories. The general inline fallback cannot replace this route’s required isolated scouts.",
              "output": "A bounded source surface to inspect."
            },
            {
              "id": "brown-scouts",
              "role": "agent",
              "label": [
                "Six isolated",
                "scouts"
              ],
              "title": "scout: six separate source slices",
              "href": "/reference/agents/scout/",
              "source": "scouts",
              "detail": "Inspect stack, infrastructure, architecture, security, testing and data model in parallel. Return paths, lines, named values and content hashes, never secret values or raw code excerpts.",
              "output": "Six restricted evidence reports for synthesis."
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
              "kind": "dispatch",
              "label": "isolated slices",
              "source": "scouts",
              "detail": "Dispatch every required scout before synthesis.",
              "from": "brown-preflight"
            }
          ]
        },
        {
          "id": "synthesize-context",
          "title": "Resolve the evidence gaps",
          "question": "Which claims are known, and which need the user?",
          "output": "Real values are written from cited reports and explicit answers. Open uncertainty is recorded, not quietly upgraded to fact.",
          "nodes": [
            {
              "id": "brown-synthesis",
              "role": "skill",
              "label": [
                "Synthesize",
                "reports"
              ],
              "title": "context-creation: report-only synthesis",
              "href": "/reference/skills/context-creation/",
              "source": "synthesis",
              "detail": "Map the returned evidence into context, stack, standards and security drafts. Classify confidence; the orchestrator does not reopen raw source after the scout phase.",
              "output": "Draft state with the evidence and unresolved facts visible."
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
              "detail": "Ask the focused missing questions. Resolve each gap or explicitly defer it to open-questions before initialization; do not infer user decisions.",
              "output": "Reviewed values and named deferred questions."
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
              "detail": "Write the surviving state documents and route board mutations through the helper. A release-target row is conditional on real evidence or a resolved declaration, not mandatory boilerplate.",
              "output": "Populated context and the authorized task state."
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
              "detail": "Populate from reports and explicit answers without retaining placeholders as resolved values.",
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
                "Provenance",
                "+ code map"
              ],
              "title": "context-creation: record evidence",
              "href": "/concepts/provenance-drift/",
              "source": "writeContext",
              "detail": "Write per-document provenance using scout source hashes and claims. Build the coarse concern-to-path code map from architecture findings.",
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
              "detail": "Write the initialized body marker only after gaps have been resolved or explicitly deferred. Show the populated tree and return to ordinary operation.",
              "output": "Initialized source-backed context, not an implemented change."
            }
          ],
          "edges": [
            {
              "to": "brown-lock",
              "kind": "sequence",
              "label": "inspect completeness",
              "source": "brownLock",
              "detail": "Validate populated state before returning to normal work.",
              "from": "brown-provenance"
            }
          ]
        }
      ],
      "alternatives": [
        {
          "to": "brown-synthesis",
          "kind": "return",
          "label": "all six reports",
          "source": "scouts",
          "detail": "A scout that finds nothing returns not-found; silence is a missing report.",
          "from": "brown-scouts"
        },
        {
          "to": "brown-scouts",
          "kind": "repeat",
          "label": "Missing or failed report",
          "source": "scouts",
          "detail": "Re-dispatch the failed scout before synthesis rather than accepting an incomplete picture.",
          "from": "brown-scouts"
        },
        {
          "to": "brown-provenance",
          "kind": "sequence",
          "label": "bind derived claims",
          "source": "writeContext",
          "detail": "Source-derived documents retain evidence instead of only their final prose.",
          "from": "brown-write"
        }
      ]
    },
    "notes": [
      {
        "title": "This is not greenfield decomposition",
        "detail": "Existing-code extraction does not fabricate 01-architecture-breakdown.md, 02-phased-build-plan.md or 03-task-backlog.md as a retrospective roadmap.",
        "source": "context"
      },
      {
        "title": "Isolation is a real prerequisite",
        "detail": "A host without isolated subagents must stop this route. The general role fallback does not erase the report-only synthesis boundary.",
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
