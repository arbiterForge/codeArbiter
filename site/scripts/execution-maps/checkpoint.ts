import type { ExecutionMap } from './model';
import { evidenceSourceRevision } from '../decision-evidence';

/** Periodic review only. This is not the attended or typed execution checkpoint. */
export const checkpointMap: ExecutionMap = {
  id: 'checkpoint', title: 'A repository sweep becomes a retained report', reviewedAt: evidenceSourceRevision,
  boundary: 'Arrows follow the ordered result handoffs, not every nested call. The read-only verdict returns before the separate writer is dispatched.',
  outcome: 'A dated report and an override-count baseline. No code repair, commit, PR, promotion or task acceptance is performed by this command.',
  sources: {
    checkpoint: { path: 'core/surface/commands/checkpoint.md', quote: 'After the verdict returns, separately dispatch `checkpoint-aggregator`' },
    dispatch: { path: 'core/surface/skills/dispatching-parallel-agents/SKILL.md', quote: 'verdict-aggregator' },
    writer: { path: 'core/surface/agents/checkpoint-aggregator.md', quote: 'Every finding and incomplete-unit result' },
  },
  chapters: [
    { id: 'review', title: 'Inspect and triage', question: 'What did the dispatched reviewers actually find?',
      output: 'A triaged result, including incomplete evidence, still on the read-only side of the boundary.',
      nodes: [
        { id: 'sweep-entry', role: 'command', label: ['/ca:checkpoint'], title: '/ca:checkpoint', href: '/reference/commands/checkpoint/', source: 'checkpoint', detail: 'Define the whole-repository reviewer unit list against the project records. The source identity and inspected scope matter.', output: 'Named review units and their required inputs.' },
        { id: 'sweep-dispatch', role: 'skill', label: ['Parallel', 'dispatch'], title: 'dispatching-parallel-agents', href: '/reference/skills/dispatching-parallel-agents/', source: 'checkpoint', detail: 'Own the parallel read-only batch and deduplicate its results. A generic batch does not authorize report persistence.', output: 'Bounded review dispatch and collected results.' },
        { id: 'sweep-reviewers', role: 'agent', label: ['Reviewer', 'units'], title: 'The checkpoint reviewer fleet', href: '/reference/commands/checkpoint/', source: 'checkpoint', detail: 'Inspect security, auth/crypto, dependencies, migrations, coverage and architecture against their applicable project evidence.', output: 'Findings and explicit incomplete-unit results, not a clean result inferred from silence.' },
        { id: 'sweep-triage', role: 'agent', label: ['finding-triage'], title: 'finding-triage', href: '/reference/agents/finding-triage/', source: 'checkpoint', detail: 'Classify severity and scope after the collected batch. Preserve unresolved questions and out-of-scope findings.', output: 'One triaged input for verdict aggregation.' },
      ],
      edges: [
        { from: 'sweep-entry', to: 'sweep-dispatch', kind: 'dispatch', label: 'unit list', source: 'checkpoint', detail: 'The caller supplies whole-repository review units.' },
        { from: 'sweep-dispatch', to: 'sweep-reviewers', kind: 'dispatch', label: 'read-only batch', source: 'checkpoint', detail: 'The skill dispatches the named units and collects their results.' },
        { from: 'sweep-reviewers', to: 'sweep-triage', kind: 'return', label: 'collected findings', source: 'checkpoint', detail: 'Results enter the fixed triage funnel; they are not consumed as a final verdict.' },
      ] },
    { id: 'retain', title: 'Return the verdict, then persist', question: 'Which step is permitted to write the report?',
      output: 'The writer returns its exact selected filename, and the command records its separate counter baseline.',
      nodes: [
        { id: 'sweep-verdict', role: 'agent', label: ['verdict-', 'aggregator'], title: 'verdict-aggregator', href: '/reference/agents/verdict-aggregator/', source: 'checkpoint', detail: 'Return one complete read-only verdict to the caller. This is where a generic review can finish without a repository write.', output: 'A complete verdict, not yet a checkpoint document.' },
        { id: 'sweep-write', role: 'agent', label: ['checkpoint-', 'aggregator'], title: 'checkpoint-aggregator', href: '/reference/agents/checkpoint-aggregator/', source: 'writer', detail: 'The checkpoint caller separately dispatches this writer with the verdict. It selects a non-overwriting dated filename and retains every finding and incomplete result.', output: 'The dated report and exact path; eligible follow-ups are surfaced for the separate harvest.' },
        { id: 'sweep-return', role: 'command', label: ['Return to', 'checkpoint'], title: 'checkpoint: baseline and return', href: '/reference/commands/checkpoint/', source: 'checkpoint', detail: 'The original command records the current override count and reports the path. This is a return to the caller, not a second invocation.', output: 'Report path plus integer accounting baseline, with no delivery sign-off.' },
      ],
      edges: [
        { from: 'sweep-verdict', to: 'sweep-write', kind: 'dispatch', label: 'separate writer', source: 'checkpoint', detail: 'Only after verdict return does the checkpoint caller dispatch persistence.' },
        { from: 'sweep-write', to: 'sweep-return', kind: 'return', label: 'report path', source: 'checkpoint', detail: 'Return the selected path so the original caller can finish its accounting.' },
      ] },
  ],
  alternatives: [{ from: 'sweep-triage', to: 'sweep-verdict', kind: 'sequence', label: 'aggregate verdict', source: 'checkpoint', detail: 'The triaged result passes to the read-only verdict aggregator before any report writer.' }],
};
