/** Editorial diagrams only: this is not a runtime router or an approval protocol. */
export type Role = 'command' | 'skill' | 'agent';
export type Relation = 'sequence' | 'dispatch' | 'return' | 'repeat' | 'reuse';
export interface MapSource {
  path: string; quote: string;
  /** Relocated current owner; path and reviewedAt retain historical evidence. */
  currentPath?: string;
  /** Exact present-day wording when the pinned historical quote predates a refactor. */
  currentQuote?: string;
}
export interface MapNode {
  id: string; role: Role; label: string[]; title: string; href: string;
  source: string; detail: string; output: string; checks?: string[]; conditional?: boolean;
}
export interface MapEdge { from: string; to: string; kind: Relation; label: string; source: string; detail: string }
export interface MapChapter {
  id: string; title: string; question: string; output: string;
  nodes: MapNode[]; edges: MapEdge[];
}
export interface ExecutionMap {
  id: string; title: string; reviewedAt: string; boundary: string; outcome: string;
  sources: Record<string, MapSource>; chapters: MapChapter[]; alternatives: MapEdge[];
}

export const featureMap: ExecutionMap = {
  "id": "feature",
  "title": "A feature request becomes a reviewed pull request",
  "reviewedAt": "a9f63fc481385680987f2ccbecede82603f011eb",
  "boundary": "The requested outcome authorizes scoped feature work. Maintain its spec and plan, follow actual dependencies, implement directly or delegate useful units, and report observed checks. Real user stops, host permissions, security controls and delivery authority remain effective.",
  "outcome": "An open PR, its source identity and observed check state. Merging and publishing remain separate decisions.",
  "sources": {
    "feature": {
      "path": "core/surface/commands/feature.md",
      "quote": "Route through the pipeline in order; each step gates the next:"
    },
    "batch": {
      "path": "core/surface/skills/executing-plans/SKILL.md",
      "quote": "Coordinate implementation of an already-authorized `/feature` plan."
    },
    "checkpoint": {
      "path": "core/surface/skills/executing-plans/SKILL.md",
      "quote": "continue to the next authorized batch without waiting for the user to acknowledge a routine status report."
    },
    "task": {
      "path": "core/surface/skills/subagent-driven-development/SKILL.md",
      "quote": "Work directly when a focused change is clearer and cheaper."
    },
    "taskReview": {
      "path": "core/surface/skills/subagent-driven-development/SKILL.md",
      "quote": "## 3. Verify truthfully and assess only relevant risks"
    },
    "scope": {
      "path": "core/surface/skills/subagent-driven-development/SKILL.md",
      "quote": "**Scoped invocation:** return completed tasks"
    },
    "tdd": {
      "path": "core/surface/skills/tdd/SKILL.md",
      "quote": "Select the verification approach before changing code."
    },
    "commit": {
      "path": "core/surface/skills/commit-gate/SKILL.md",
      "quote": "# commit-gate"
    },
    "finish": {
      "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
      "quote": "execute the **Open-PR procedure** below in this owner. Do not load or re-invoke the PR command wrapper."
    },
    "pr": {
      "path": "core/surface/skills/finishing-a-development-branch/SKILL.md",
      "quote": "Establish applicable verification for the current HEAD."
    },
    "dispatch": {
      "path": "core/surface/skills/dispatching-parallel-agents/SKILL.md",
      "quote": "finding-triage"
    },
    "brainstorm": {
      "path": "core/surface/skills/brainstorming/SKILL.md",
      "quote": "## Phase 5 - Self-review and handoff"
    },
    "planning": {
      "path": "core/surface/skills/writing-plans/SKILL.md",
      "quote": "## Build useful tasks"
    }
  },
  "chapters": [
    {
      "id": "define",
      "title": "Define the change",
      "question": "What behavior is being agreed to?",
      "output": "A maintained specification and linked plan with observable criteria, actual dependencies and unresolved choices kept visible.",
      "nodes": [
        {
          "id": "entry",
          "role": "command",
          "label": [
            "/ca:feature"
          ],
          "title": "/ca:feature",
          "href": "/reference/commands/feature/",
          "source": "feature",
          "detail": "Resolve existing work before classifying a new request. Resume its actual unfinished step and preserve the selected representation.",
          "output": "The selected lane, current scope and exact artifact route."
        },
        {
          "id": "spec",
          "role": "skill",
          "label": [
            "brainstorming"
          ],
          "title": "brainstorming",
          "href": "/reference/skills/brainstorming/",
          "source": "brainstorm",
          "detail": "Refine the agreed outcome into observable criteria and exclusions. Ask about consequential unresolved choices while retaining decisions already made.",
          "output": "A saved specification with criteria and actual open decisions."
        },
        {
          "id": "plan",
          "role": "skill",
          "label": [
            "writing-plans"
          ],
          "title": "writing-plans",
          "href": "/reference/skills/writing-plans/",
          "source": "planning",
          "detail": "Describe coherent tasks, relevant paths, actual dependencies and checks under existing authorization. Maintain in-scope methods with a reason and preserve source identity.",
          "output": "A useful working plan; missing requirements and structural failures remain explicit."
        },
        {
          "id": "batch",
          "role": "skill",
          "label": [
            "executing-",
            "plans"
          ],
          "title": "executing-plans",
          "href": "/reference/skills/executing-plans/",
          "source": "batch",
          "detail": "Select meaningful work using actual task dependencies. Preserve blocked members and authored scope while allowing independent work to continue.",
          "output": "A bounded task scope handed to the implementation owner."
        }
      ],
      "edges": [
        {
          "from": "entry",
          "to": "spec",
          "kind": "sequence",
          "label": "full lane",
          "source": "feature",
          "detail": "New full-lane work enters brainstorming."
        },
        {
          "from": "spec",
          "to": "plan",
          "kind": "sequence",
          "label": "criteria",
          "source": "brainstorm",
          "detail": "Return the selected specification and actual open decisions directly to planning."
        },
        {
          "from": "plan",
          "to": "batch",
          "kind": "sequence",
          "label": "ready plan",
          "source": "feature",
          "detail": "The coordinator receives the maintained plan and selects useful authorized work."
        }
      ]
    },
    {
      "id": "task",
      "title": "Build and verify each task",
      "question": "Who writes, and what proves this task?",
      "output": "Implemented work with actual check results and pending verification, returned to the caller.",
      "nodes": [
        {
          "id": "task-select",
          "role": "skill",
          "label": [
            "Task engine"
          ],
          "title": "subagent-driven-development: select",
          "href": "/reference/skills/subagent-driven-development/",
          "source": "task",
          "detail": "Inspect the selected scope, criteria, actual dependencies and current work. Engine eligibility is advisory; inspect outstanding workers before redispatch after interruption.",
          "output": "Useful next work with the relevant requirements and checks."
        },
        {
          "id": "author",
          "role": "agent",
          "label": [
            "Scoped author"
          ],
          "title": "Optional backend, frontend or infrastructure author",
          "href": "/concepts/persona-and-context/",
          "source": "task",
          "detail": "Choose direct implementation for focused work. Delegate when isolation, parallel work or expertise helps, supplying bounded relevant context. A delivery receipt does not grant execution permission.",
          "output": "Scoped work performed directly or by an appropriate author.",
          "conditional": true
        },
        {
          "id": "tdd",
          "role": "skill",
          "label": [
            "tdd"
          ],
          "title": "tdd: select and prove the approach",
          "href": "/reference/skills/tdd/",
          "source": "tdd",
          "detail": "Use genuine regression RED/GREEN for confirmed fixes, criterion-focused feature checks and passing characterization baselines for refactors. Non-executable changes use relevant validation.",
          "output": "Observed evidence and pending checks returned to the caller.",
          "checks": [
            "Obligations: map required claims to meaningful proving checks.",
            "Baseline: observe target RED for a fix or passing characterization before refactoring; prefer test-first features.",
            "Implement: run the scoped proving checks and affected existing contracts, preserving assertions.",
            "Verify obligations: keep missing or failed evidence visible and rerun affected checks.",
            "Coverage: meet the declared profile and critical-path requirements; report unmeasured scope.",
            "Lint and handoff: run applicable quality tools and return actual commands, results and limitations."
          ]
        },
        {
          "id": "task-proof",
          "role": "skill",
          "label": [
            "Check result"
          ],
          "title": "subagent-driven-development: verify",
          "href": "/reference/skills/subagent-driven-development/",
          "source": "taskReview",
          "detail": "Compare the result with criteria and run applicable checks. Record commands, working directories, outcomes and limitations. Reuse evidence only while its checked source and inputs remain applicable.",
          "output": "Observed verification and pending checks; task status is not test evidence."
        }
      ],
      "edges": [
        {
          "from": "task-select",
          "to": "author",
          "kind": "dispatch",
          "label": "implement",
          "source": "task",
          "detail": "Implement directly or assign a useful bounded unit; delegation is conditional."
        },
        {
          "from": "author",
          "to": "tdd",
          "kind": "reuse",
          "label": "verify approach",
          "source": "task",
          "detail": "The implementer follows the verification approach suited to the assigned work."
        },
        {
          "from": "tdd",
          "to": "task-proof",
          "kind": "return",
          "label": "return",
          "source": "taskReview",
          "detail": "Return actual results so the caller can assess criteria, source applicability and remaining work."
        }
      ]
    },
    {
      "id": "accept",
      "title": "Review and report progress",
      "question": "What evidence and next work return to the caller?",
      "output": "Current implementation progress, applicable review and check results, and the next authorized work.",
      "nodes": [
        {
          "id": "quality",
          "conditional": true,
          "role": "agent",
          "label": [
            "Applicable",
            "reviewers"
          ],
          "title": "Risk-selected reviewers",
          "href": "/reference/skills/subagent-driven-development/",
          "source": "taskReview",
          "detail": "Review the combined relevant diff when risk or policy requires it. Use specialist reviewers for applicable security, dependency or migration concerns and avoid duplicate per-task reviewer cascades.",
          "output": "Applicable findings against the actual reviewed source."
        },
        {
          "id": "triage",
          "conditional": true,
          "role": "agent",
          "label": [
            "finding-triage"
          ],
          "title": "finding-triage",
          "href": "/reference/agents/finding-triage/",
          "source": "dispatch",
          "detail": "Route a dispatched review batch through finding triage and verdict aggregation. Preserve blockers, incomplete units and out-of-scope findings without inventing a successful review.",
          "output": "One triaged verdict with its actual evidence limits."
        },
        {
          "id": "accept-scope",
          "role": "skill",
          "label": [
            "Record",
            "progress"
          ],
          "title": "subagent-driven-development: record progress",
          "href": "/reference/skills/subagent-driven-development/",
          "source": "scope",
          "detail": "Use the selected writer to record completed implementation. HTML accept-scope can record DONE without a receipt; it cannot clear pending or blocked members. Keep verification and independent acceptance distinct.",
          "output": "Completed implementation, actual checks and unresolved issues returned to the caller."
        },
        {
          "id": "checkpoint",
          "role": "skill",
          "label": [
            "Progress",
            "report"
          ],
          "title": "executing-plans: report and continue",
          "href": "/reference/skills/executing-plans/",
          "source": "checkpoint",
          "detail": "Report changes, checks and next work, then continue within existing authorization. Honor a user-requested pause, consequential decision, or actual host/security restriction for the affected work.",
          "output": "The next authorized scope or an honest delivery handoff."
        }
      ],
      "edges": [
        {
          "from": "quality",
          "to": "triage",
          "kind": "sequence",
          "label": "findings",
          "source": "dispatch",
          "detail": "When independent reviewers are dispatched, aggregate their complete findings and unit outcomes."
        },
        {
          "from": "triage",
          "to": "accept-scope",
          "kind": "return",
          "label": "results",
          "source": "scope",
          "detail": "Return applicable review results; implementation status must not conceal failures or missing checks."
        },
        {
          "from": "accept-scope",
          "to": "checkpoint",
          "kind": "return",
          "label": "to caller",
          "source": "scope",
          "detail": "The scoped invocation returns to its coordinator with work and evidence, not directly to commit."
        }
      ]
    },
    {
      "id": "deliver",
      "title": "Commit and open the PR",
      "question": "Which action is actually authorized?",
      "output": "An authorized open PR with its current source and observed checks. Merge and publication remain separate actions.",
      "nodes": [
        {
          "id": "commit",
          "role": "skill",
          "label": [
            "commit-gate"
          ],
          "title": "commit-gate",
          "href": "/reference/skills/commit-gate/",
          "source": "commit",
          "detail": "Use the commit owner only when committing is authorized. It checks the selected staged work, applicable tests, secrets and specialized controls, with fresh behavioral proof.",
          "output": "A selectively staged commit and observed gate results."
        },
        {
          "id": "finish",
          "role": "skill",
          "label": [
            "Finish branch"
          ],
          "title": "finishing-a-development-branch",
          "href": "/reference/skills/finishing-a-development-branch/",
          "source": "finish",
          "detail": "Retain an existing open-PR choice. Ask for branch disposition only if it is unclear. Merge and discard require their own explicit authorization and applicable evidence.",
          "output": "The selected terminal action supported by current branch state."
        },
        {
          "id": "pr-contract",
          "role": "command",
          "label": [
            "/ca:pr",
            "procedure"
          ],
          "title": "/ca:pr procedure, reused by finishing",
          "href": "/reference/commands/pr/",
          "source": "finish",
          "detail": "Finishing executes the PR procedure in place; the command is not re-invoked. For a committed branch, verify the explicit base-to-HEAD subject, including secrets and specialized checks, without creating another commit.",
          "output": "Current-head readiness and required review for the authorized PR."
        },
        {
          "id": "pr-review",
          "role": "agent",
          "label": [
            "PR review",
            "+ verdict"
          ],
          "title": "PR reviewers, finding-triage and verdict-aggregator",
          "href": "/reference/commands/pr/",
          "source": "pr",
          "detail": "Apply the PR path matrix and review funnel, including security review for CI/deployment/infrastructure changes. Resolve blockers and report the PR URL, current head and observed checks.",
          "output": "An open PR. Exact-head hosted CI and explicit merge authority still govern integration."
        }
      ],
      "edges": [
        {
          "from": "commit",
          "to": "finish",
          "kind": "sequence",
          "label": "committed",
          "source": "finish",
          "detail": "The branch-finishing owner checks current-head readiness and the selected delivery action."
        },
        {
          "from": "finish",
          "to": "pr-contract",
          "kind": "reuse",
          "label": "reuse",
          "source": "finish",
          "detail": "Execute the PR contract in place; do not re-invoke its command."
        },
        {
          "from": "pr-contract",
          "to": "pr-review",
          "kind": "dispatch",
          "label": "review",
          "source": "pr",
          "detail": "PR creation includes its own path-selected review and verdict."
        }
      ]
    }
  ],
  "alternatives": [
    {
      "from": "batch",
      "to": "task-select",
      "kind": "dispatch",
      "label": "Select useful scope",
      "source": "batch",
      "detail": "The coordinator hands the named scope to the implementation owner and resumes from its actual results."
    },
    {
      "from": "task-proof",
      "to": "task-select",
      "kind": "repeat",
      "label": "Continue independent work",
      "source": "taskReview",
      "detail": "Choose the next task by actual dependencies; an unrelated failure does not prohibit useful authorized work."
    },
    {
      "from": "task-proof",
      "to": "quality",
      "kind": "sequence",
      "label": "Review where warranted",
      "source": "taskReview",
      "detail": "Use applicable independent review for the combined change when risk or policy calls for it."
    },
    {
      "from": "task-proof",
      "to": "accept-scope",
      "kind": "sequence",
      "label": "Record scoped progress",
      "source": "scope",
      "detail": "Ordinary work can record implementation progress without manufacturing an independent review receipt."
    },
    {
      "from": "tdd",
      "to": "tdd",
      "kind": "repeat",
      "label": "Repair affected checks",
      "source": "tdd",
      "detail": "An unexplained failure or missing requirement remains outstanding. Repair the work and rerun the appropriate checks without weakening assertions."
    },
    {
      "from": "triage",
      "to": "author",
      "kind": "return",
      "label": "Correct blocking findings",
      "source": "taskReview",
      "detail": "Resolve affected findings within existing scope, rerun relevant checks and refresh changed review conclusions."
    },
    {
      "from": "checkpoint",
      "to": "task-select",
      "kind": "repeat",
      "label": "Next authorized scope",
      "source": "checkpoint",
      "detail": "Continue normal authorized work while preserving real dependencies and any explicit user-requested pause."
    },
    {
      "from": "checkpoint",
      "to": "commit",
      "kind": "sequence",
      "label": "Authorized delivery",
      "source": "checkpoint",
      "detail": "Hand current scope, actual check results and remaining work to the commit owner only when committing is authorized."
    }
  ]
};

/** Check presentation integrity; source tests and human tracing establish semantic fidelity. */
export function validateExecutionMap(map: ExecutionMap): string[] {
  const errors: string[] = [];
  const ids = new Set<string>();
  const chapters = new Set<string>();
  if (!map.outcome.trim()) errors.push('missing terminal outcome');
  if (!/^[0-9a-f]{40}$/.test(map.reviewedAt)) errors.push('missing source revision');
  for (const chapter of map.chapters) {
    if (chapters.has(chapter.id)) errors.push(`duplicate chapter ${chapter.id}`);
    chapters.add(chapter.id);
    if (!/^[a-z][a-z0-9-]*$/.test(chapter.id)) errors.push('invalid chapter ID');
    if (!chapter.nodes.length || chapter.nodes.length > 4) errors.push('chapter must contain one to four readable nodes');
    for (const node of chapter.nodes) {
      if (ids.has(node.id)) errors.push(`duplicate node ${node.id}`);
      ids.add(node.id);
      if (!/^[a-z][a-z0-9-]*$/.test(node.id)) errors.push('invalid node ID');
      if (!map.sources[node.source]) errors.push(`missing owner ${node.source}`);
      if (!['command', 'skill', 'agent'].includes(node.role)) errors.push('unknown role');
      if (!node.href.startsWith('/') || node.href.startsWith('//')) errors.push('invalid reference link');
      if (!node.title || !node.output || !node.detail || !node.label.length) errors.push('incomplete node');
    }
    if (chapter.edges.length !== chapter.nodes.length - 1) errors.push('missing chapter handoff');
    for (let i = 0; i < chapter.edges.length; i++) {
      const edge = chapter.edges[i];
      if (edge.from !== chapter.nodes[i]?.id || edge.to !== chapter.nodes[i + 1]?.id) errors.push('unknown or unordered chapter edge');
    }
  }
  for (const source of Object.values(map.sources)) {
    if (!/^core\/surface\//.test(source.path) || source.path.split('/').includes('..') || !source.quote.trim()) errors.push('invalid source anchor');
    if (source.currentPath !== undefined && (!/^core\/surface\//.test(source.currentPath) || source.currentPath.split('/').includes('..'))) errors.push('invalid current source anchor');
    if (source.currentQuote !== undefined && !source.currentQuote.trim()) errors.push('invalid current source quote');
  }
  for (const edge of [...map.chapters.flatMap(chapter => chapter.edges), ...map.alternatives]) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) errors.push('unknown edge endpoint');
    if (!map.sources[edge.source]) errors.push(`missing edge owner ${edge.source}`);
    if (!edge.detail || !edge.label) errors.push('unexplained edge');
    if (!['sequence', 'dispatch', 'return', 'repeat', 'reuse'].includes(edge.kind)) errors.push('unknown relation');
  }
  const reached = new Set<string>();
  const allEdges = [...map.chapters.flatMap(chapter => chapter.edges), ...map.alternatives];
  const queue = [map.chapters[0]?.nodes[0]?.id];
  while (queue.length) {
    const id = queue.shift();
    if (!id || reached.has(id)) continue;
    reached.add(id);
    queue.push(...allEdges.filter(edge => edge.from === id).map(edge => edge.to));
  }
  if ([...ids].some(id => !reached.has(id))) errors.push('disconnected execution path');
  return errors;
}
