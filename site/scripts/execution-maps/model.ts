/** Editorial diagrams only: this is not a runtime router or an approval protocol. */
export type Role = 'command' | 'skill' | 'agent';
export type Relation = 'sequence' | 'dispatch' | 'return' | 'repeat' | 'reuse';
export interface MapSource {
  path: string; quote: string;
  /** Relocated current owner; path and reviewedAt retain historical evidence. */
  currentPath?: string;
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
  id: 'feature', title: 'A feature request becomes a reviewed pull request',
  reviewedAt: '29f84168ab7592a5d7bb0550cb1f25cf29608a9d',
  boundary: 'Attended full-lane example, choosing Open a PR. Read left to right within each chapter, then continue downward. These are source-contract relationships, not a captured run or installed-host certification.',
  outcome: 'An open PR, its source identity and observed check state. Merging and publishing remain separate decisions.',
  sources: {
    feature: { path: 'core/surface/commands/feature.md', quote: 'Route through the pipeline in order; each step gates the next:' },
    batch: { path: 'core/surface/skills/executing-plans/SKILL.md', quote: 'Do not implement anything here — the author agents,' },
    checkpoint: { path: 'core/surface/skills/executing-plans/SKILL.md', quote: 'Do not begin the next batch until the user acknowledges.' },
    task: { path: 'core/surface/skills/subagent-driven-development/SKILL.md', quote: 'The subagent works test-first by routing through the `tdd` skill' },
    taskReview: { path: 'core/surface/skills/subagent-driven-development/SKILL.md', quote: 'Runs ONCE per scope — after every task in the current scope has cleared Phase 3 and Phase 5' },
    scope: { path: 'core/surface/skills/subagent-driven-development/SKILL.md', quote: 'batch complete and return to `executing-plans`. Do NOT hand to `commit-gate`' },
    tdd: { path: 'core/surface/skills/tdd/SKILL.md', quote: 'A `MISSING` obligation returns the workflow to Phase 2' },
    commit: { path: 'core/surface/skills/commit-gate/SKILL.md', quote: '# commit-gate' },
    finish: { path: 'core/surface/skills/finishing-a-development-branch/SKILL.md', quote: 'MUST NOT auto-merge under `/sprint`' },
    pr: { path: 'core/surface/skills/finishing-a-development-branch/SKILL.md', quote: '`commit-gate` MUST have cleared on the current HEAD.' },
    dispatch: { path: 'core/surface/skills/dispatching-parallel-agents/SKILL.md', quote: 'finding-triage' },
  },
  chapters: [
    {
      id: 'define', title: 'Define the change', question: 'What behavior is being agreed to?',
      output: 'A specification, a linked plan, and the current approvals required by the selected artifact format.',
      nodes: [
        { id: 'entry', role: 'command', label: ['/ca:feature'], title: '/ca:feature', href: '/reference/commands/feature/', source: 'feature',
          detail: 'Resolve existing work before classifying a new request. This map follows new full-lane work; small and resume routes are separate.', output: 'A selected lane and exact artifact route.' },
        { id: 'spec', role: 'skill', label: ['brainstorming'], title: 'brainstorming', href: '/reference/skills/brainstorming/', source: 'feature',
          detail: 'Turn the request into concrete acceptance criteria. Surface unresolved questions and obtain the required specification approval before planning.', output: 'The reviewed specification, not implementation code.' },
        { id: 'plan', role: 'skill', label: ['writing-plans'], title: 'writing-plans', href: '/reference/skills/writing-plans/', source: 'feature',
          detail: 'Map the specification into tasks, paths, dependencies and verification. Preserve the selected format and its approval binding.', output: 'An executable plan only when its required bindings are current.' },
        { id: 'batch', role: 'skill', label: ['executing-', 'plans'], title: 'executing-plans', href: '/reference/skills/executing-plans/', source: 'batch',
          detail: 'Coordinate attended work. On HTML, use authored checkpoint membership rather than inventing smaller acceptance scopes.', output: 'One complete scope delegated to the task engine.' },
      ],
      edges: [
        { from: 'entry', to: 'spec', kind: 'sequence', label: 'full lane', source: 'feature', detail: 'New full-lane work enters brainstorming.' },
        { from: 'spec', to: 'plan', kind: 'sequence', label: 'approved', source: 'feature', detail: 'Specification approval precedes implementation planning.' },
        { from: 'plan', to: 'batch', kind: 'sequence', label: 'ready plan', source: 'feature', detail: 'The attended coordinator receives the approved, bound plan.' },
      ],
    },
    {
      id: 'task', title: 'Build and verify each task', question: 'Who writes, and what proves this task?',
      output: 'Per-task specification review and fresh verification. This is not yet whole-scope acceptance.',
      nodes: [
        { id: 'task-select', role: 'skill', label: ['Task engine'], title: 'subagent-driven-development: select', href: '/reference/skills/subagent-driven-development/', source: 'task',
          detail: 'Select eligible work inside the caller’s scope and retain its requirement, target paths and verification command. Typed work uses engine eligibility and a current context ticket.', output: 'One eligible task, dispatched with bounded context.' },
        { id: 'author', role: 'agent', label: ['Fresh author'], title: 'backend-author, frontend-author or infra-author', href: '/concepts/persona-and-context/', source: 'task',
          detail: 'Select the author from the project’s scope mapping. The author runs the test-first procedure inside this task; authoring is not a completed stage before TDD.', output: 'One fresh author context, not a persistent team of simultaneous writers.' },
        { id: 'tdd', role: 'skill', label: ['tdd'], title: 'tdd: six gated phases', href: '/reference/skills/tdd/', source: 'tdd',
          detail: 'Derive obligations, observe a meaningful failing test, implement the minimum change, then verify coverage of the obligations and project quality requirements.', output: 'Test-first work returned to its caller, not permission to commit.',
          checks: ['Obligation scan: identify each verifiable claim.', 'Red: the new test fails for the intended behavior.', 'Green: satisfy the same assertion with the minimum change.', 'Obligation verify: every claim has meaningful passing evidence.', 'Coverage: apply the declared threshold or cited no-tooling treatment.', 'Lint: pass the declared lint and applicable type checks.'] },
        { id: 'task-proof', role: 'skill', label: ['Spec review', '+ fresh verify'], title: 'subagent-driven-development: review and verify', href: '/reference/skills/subagent-driven-development/', source: 'taskReview',
          detail: 'Check the change against its task obligation and run the plan’s verification afresh. An author’s report does not substitute for this evidence.', output: 'The task’s review and verification results; typed REVIEW remains provisional.' },
      ],
      edges: [
        { from: 'task-select', to: 'author', kind: 'dispatch', label: 'dispatch', source: 'task', detail: 'One fresh, scope-selected author receives the task.' },
        { from: 'author', to: 'tdd', kind: 'dispatch', label: 'uses tdd', source: 'task', detail: 'The author follows the test-first procedure, not a separate later test service.' },
        { from: 'tdd', to: 'task-proof', kind: 'return', label: 'return', source: 'taskReview', detail: 'The caller performs specification review and fresh verification after authoring.' },
      ],
    },
    {
      id: 'accept', title: 'Accept the scope, then checkpoint', question: 'What returns to the human coordinator?',
      output: 'Accepted scope evidence and a human acknowledgement before the next attended batch.',
      nodes: [
        { id: 'quality', conditional: true, role: 'agent', label: ['Applicable', 'reviewers'], title: 'Scope-selected quality reviewers', href: '/reference/skills/subagent-driven-development/', source: 'taskReview',
          detail: 'Review the combined diff once per scope after task review and verification. Dispatch security, auth/crypto, dependency or migration reviewers only where applicable; ordinary work retains its TDD/coverage quality bar.', output: 'Findings against the combined scope, not a blanket reviewer roster.' },
        { id: 'triage', conditional: true, role: 'agent', label: ['finding-triage'], title: 'finding-triage', href: '/reference/agents/finding-triage/', source: 'taskReview',
          detail: 'Classify the dispatched findings. Security CRITICAL stops the loop; HIGH returns the affected work for correction. The active caller owns lower-severity disposition.', output: 'A severity-aware result with out-of-scope work kept separate.' },
        { id: 'accept-scope', role: 'skill', label: ['Accept scope'], title: 'subagent-driven-development: accept', href: '/reference/skills/subagent-driven-development/', source: 'scope',
          detail: 'Accept only after task proof and combined quality review. The HTML path records current whole-scope acceptance through the installed authority and engine, not an edited checkbox.', output: 'A completed scope returned to executing-plans.' },
        { id: 'checkpoint', role: 'skill', label: ['Human', 'checkpoint'], title: 'executing-plans: human checkpoint', href: '/reference/skills/executing-plans/', source: 'checkpoint',
          detail: 'Report what landed, what is next and what remains open. Wait for acknowledgement. This attended stop is different from a periodic checkpoint report and from an HTML acceptance scope.', output: 'Acknowledgement, then another scope or the commit gate.' },
      ],
      edges: [
        { from: 'quality', to: 'triage', kind: 'sequence', label: 'findings', source: 'taskReview', detail: 'Applicable reviewer findings are classified before the scope can be accepted.' },
        { from: 'triage', to: 'accept-scope', kind: 'return', label: 'no blocker', source: 'scope', detail: 'Return quality results to the task engine; current evidence still governs acceptance.' },
        { from: 'accept-scope', to: 'checkpoint', kind: 'return', label: 'to caller', source: 'scope', detail: 'A scoped invocation returns to executing-plans, not directly to commit-gate.' },
      ],
    },
    {
      id: 'deliver', title: 'Commit and open the PR', question: 'Which action is actually authorized?',
      output: 'The chosen Open a PR outcome, with current source and evidence. The PR is not an automatic merge or release.',
      nodes: [
        { id: 'commit', role: 'skill', label: ['commit-gate'], title: 'commit-gate', href: '/reference/skills/commit-gate/', source: 'commit',
          detail: 'The coordinator hands off only after all required scopes and acknowledgements. The commit gate checks permission, selected work and fresh evidence; /ca:commit is also a standalone entry, not an extra command this path must type.', output: 'A selectively staged commit after the applicable gates.' },
        { id: 'finish', role: 'skill', label: ['Finish branch'], title: 'finishing-a-development-branch', href: '/reference/skills/finishing-a-development-branch/', source: 'finish',
          detail: 'Present the supported terminal choices with actual state. This illustration follows the user choosing Open a PR; merging via PR and confirmed discard are separate outcomes.', output: 'An explicit terminal choice, with no direct write to main.' },
        { id: 'pr-contract', role: 'command', label: ['/ca:pr', 'procedure'], title: '/ca:pr procedure, reused by finishing', href: '/reference/commands/pr/', source: 'finish',
          detail: 'Finishing executes the PR procedure here. The command is not re-invoked: routing back into it would create a loop. A standalone /ca:pr remains an entry to the same contract.', output: 'The required PR preparation and review, not a new authorization.' },
        { id: 'pr-review', role: 'agent', label: ['PR review', '+ verdict'], title: 'PR reviewers, finding-triage and verdict-aggregator', href: '/reference/commands/pr/', source: 'pr',
          detail: 'Apply the PR path matrix and read-only review funnel. Resolve blocking findings before opening. The final handoff names the PR URL, current head and actually observed checks.', output: 'An open pull request. Exact-head merge readiness and merge permission remain separate.' },
      ],
      edges: [
        { from: 'commit', to: 'finish', kind: 'sequence', label: 'committed', source: 'finish', detail: 'The finishing procedure requires a cleared commit gate on current work.' },
        { from: 'finish', to: 'pr-contract', kind: 'reuse', label: 'reuse', source: 'finish', detail: 'Execute the PR contract in place; do not re-invoke its command.' },
        { from: 'pr-contract', to: 'pr-review', kind: 'dispatch', label: 'review', source: 'pr', detail: 'PR creation includes its own path-selected review and verdict.' },
      ],
    },
  ],
  alternatives: [
    { from: 'batch', to: 'task-select', kind: 'dispatch', label: 'Delegate the complete scope', source: 'batch', detail: 'The attended coordinator calls the task engine with the authored scope, then waits for its return.' },
    { from: 'task-proof', to: 'task-select', kind: 'repeat', label: 'More tasks in this scope', source: 'taskReview', detail: 'Build the remaining eligible tasks. Combined quality review occurs after task specification review and fresh verification, despite its earlier phase number.' },
    { from: 'task-proof', to: 'quality', kind: 'sequence', label: 'Scope ready for quality review', source: 'taskReview', detail: 'Proceed only once every task has the required per-task evidence.' },
    { from: 'tdd', to: 'tdd', kind: 'repeat', label: 'Missing obligation returns to red', source: 'tdd', detail: 'Phase 4 returns to Phase 2 for a meaningful failing test, then reruns implementation. Tests are not weakened to clear a gate.' },
    { from: 'triage', to: 'author', kind: 'return', label: 'HIGH finding requires correction', source: 'taskReview', detail: 'Correct the affected task, repeat its proof and rerun the combined quality review. Real authority/security blocks remain stops.' },
    { from: 'checkpoint', to: 'task-select', kind: 'repeat', label: 'Next acknowledged scope', source: 'checkpoint', detail: 'The coordinator delegates the next scope only after human acknowledgement. A changed typed partition uses the owning amendment path.' },
    { from: 'checkpoint', to: 'commit', kind: 'sequence', label: 'Final scope acknowledged', source: 'checkpoint', detail: 'Current acceptance of the entire selected plan is checked again before commit handoff.' },
  ],
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
