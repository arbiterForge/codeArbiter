/** C02 teaching data only. Nothing here grants authority or drives product execution. */
export const evidenceSourceRevision = '6860daa3c974ae32cd9584d3e60e0a51c185a613';
export const evidenceSources = {
  smarts: { path: 'core/surface/includes/smarts/core.md', quote: 'Step 0 — recorded-intent check' },
  sprint: { path: 'core/surface/SPRINT.md', quote: 'Decide on EVERY non-hard-gate point **regardless of SMARTS' },
  methods: { path: 'core/surface/SPRINT.md', quote: 'It can\nchange only existing task `steps`' },
  reconcile: { path: 'core/surface/skills/decision-variance/SKILL.md', quote: 'confirm it back in one sentence, then append the decision' },
  decisionLog: { path: 'core/surface/includes/smarts/decision-log-format.md', quote: 'SHA-256 of the artifact section that defined the artifact' },
  lifecycle: { path: 'core/surface/skills/decision-lifecycle/SKILL.md', quote: '`accepted` means **Accepted/Planned**' },
  status: { path: 'core/surface/commands/adr-status.md', quote: 'Read-only — MUST NOT modify any file' },
  checkpoint: { path: 'core/surface/commands/checkpoint.md', quote: 'Write the current override **count**' },
  checkpointWriter: { path: 'core/surface/agents/checkpoint-aggregator.md', quote: 'Runs only after `verdict-aggregator` returns' },
  audit: { path: 'core/surface/commands/audit.md', quote: '**Triage** — every small-lane classification' },
  override: { path: 'core/surface/commands/override.md', quote: 'MUST write the log line before proceeding' },
} as const;
export type EvidenceSource = keyof typeof evidenceSources;
export const evidenceSourceUrl = (key: EvidenceSource) =>
  `https://github.com/arbiterForge/codeArbiter/blob/${evidenceSourceRevision}/${evidenceSources[key].path}`;

export type CellVerdict = 'Strong' | 'Adequate' | 'Weak' | 'Indifferent';
export interface LensCell { verdict: CellVerdict; reason: string }
/** Hypothetical project constraints, not a benchmark or a verdict about a real dependency. */
export const smartsExample = {
  title: 'Where should a saved-search export run?',
  scenario: 'Illustrative project: 50 saved searches per request, an existing application endpoint, no job infrastructure, and an approved synchronous response. These assumptions are not measurements.',
  options: ['Existing request path', 'New queue and worker'],
  intent: 'The accepted synchronous-response decision already answers the execution-mode choice. This comparison explains the tradeoffs; it cannot reopen that decision by scoring alone.',
  lenses: [
    { id: 'scalable', name: 'Scalable', question: 'Does growth fit the stated demand?', cells: [
      { verdict: 'Adequate', reason: 'Assumed 50-search bound fits the current endpoint design; no throughput benchmark is claimed.' },
      { verdict: 'Strong', reason: 'Independent workers isolate export capacity, beyond the stated requirement.' },
    ] },
    { id: 'maintainable', name: 'Maintainable', question: 'Who must understand and change the whole path?', cells: [
      { verdict: 'Strong', reason: 'One service owns serialization and delivery; existing deployment and rollback remain.' },
      { verdict: 'Weak', reason: 'Adds queue, worker, job status and retry ownership to a project without job infrastructure.' },
    ] },
    { id: 'available', name: 'Available', question: 'What must be reachable to deliver the result?', cells: [
      { verdict: 'Adequate', reason: 'Export is reachable while the application is available; it shares the application failure boundary.' },
      { verdict: 'Weak', reason: 'Successful delivery also needs the new queue, worker and result retrieval path.' },
    ] },
    { id: 'reliable', name: 'Reliable', question: 'What can fail, duplicate, or be lost?', cells: [
      { verdict: 'Adequate', reason: 'One response avoids persisted job state; interrupted requests still need an explicit retry contract.' },
      { verdict: 'Weak', reason: 'Duplicate delivery, job recovery and retention policies are not yet specified.' },
    ] },
    { id: 'testable', name: 'Testable', question: 'Which failure modes can be checked deterministically?', cells: [
      { verdict: 'Strong', reason: 'Existing request tests can check empty results, quoting and failure responses in one process.' },
      { verdict: 'Weak', reason: 'Adds queue, worker and polling integration cases without an existing test harness.' },
    ] },
    { id: 'securable', name: 'Securable', question: 'Can the design satisfy the named security posture?', cells: [
      { verdict: 'Adequate', reason: 'Uses the existing authorization boundary; CSV injection and export permission still require review.' },
      { verdict: 'Weak', reason: 'Job-result authorization, storage access and retention introduce new unreviewed boundaries.' },
    ] },
  ],
  recommendation: 'Retain the existing request path for this illustrative scope. Maintainable and Testable align; the unrequested scaling capability does not justify a new system.',
  strength: 'strong',
  limits: 'Cost, deadline, team experience, vendor lock-in and political acceptability stay outside the six lenses. No sums, automatic approval or performance guarantee follow from these cells.',
} as const;

export interface EvidenceCase {
  id: string; label: string; record: string; example: string; supports: string;
  missing: string; inspect: string; href: string; source: EvidenceSource;
}
export const adrCases: EvidenceCase[] = [
  { id: 'accepted', label: 'Accepted / Planned', record: 'ADR + acceptance binding',
    example: 'Illustrative choice: keep saved-search exports synchronous. The owner accepted the decision; its implementation obligations remain open.',
    supports: 'The choice is recorded and attributed. A sealed acceptance binding fixes which normative obligations later evidence must cover.',
    missing: 'Acceptance does not establish implemented code, passing tests, installed-host behavior or publication.',
    inspect: 'Resolve the full filename stem, acceptance source commit and complete sealed obligation set. An unsealed legacy baseline stays Accepted/Planned.',
    href: '/reference/skills/decision-lifecycle/', source: 'lifecycle' },
  { id: 'implemented', label: 'Implemented', record: 'Current implementation evidence',
    example: 'Each sealed obligation now maps to a named source commit and the relevant input digests. The example has not yet supplied fresh verification for every obligation.',
    supports: 'The repository can derive Implemented only when every sealed obligation has the required current implementation evidence.',
    missing: 'One changed file or successful build does not prove every obligation, and Implemented is not Verified.',
    inspect: 'Check completeness and recomputed inputs for each obligation. Missing or changed inputs prevent promotion.',
    href: '/reference/commands/adr-status/', source: 'lifecycle' },
  { id: 'verified', label: 'Verified', record: 'Current, scoped verification events',
    example: 'Every sealed obligation has a fresh, input-bound verification event with an explicit repository claim, producer, observation time and expiry.',
    supports: 'The named repository proof contract is satisfied for the current bound inputs while its evidence remains valid.',
    missing: 'This is not a certification of every platform, a user approval, a legal conclusion, or proof that a release was distributed.',
    inspect: 'Inspect the claim scope, producer, command/workflow identity, input digests, observation time and expiry. Recheck after new commits.',
    href: '/reference/commands/adr-status/', source: 'lifecycle' },
  { id: 'stale', label: 'Stale or incomplete', record: 'History retained; current claim withheld',
    example: 'The serializer or another relevant input changes, or a verification event expires. The earlier record remains present.',
    supports: 'Historical evidence still explains what was observed then; the governance decision can remain accepted.',
    missing: 'The older verification cannot be reused as current just because its result said pass.',
    inspect: 'Follow the reported stale, expired, unsealed, incomplete or mismatched reason. Obtain fresh applicable evidence without rewriting history.',
    href: '/guides/resume-and-recover/', source: 'lifecycle' },
];
export const auditCases: EvidenceCase[] = [
  { id: 'choice', label: 'Decision', record: 'decisions/ + decision-log.md',
    example: 'The selected export approach is recorded with the user attribution and the relevant decision context.',
    supports: 'What was chosen, whose decision was recorded, and which prior record it supersedes.',
    missing: 'A recommendation or attribution string is not authenticated human identity or proof that the choice was implemented.',
    inspect: 'Read the complete ADR stem and ledger entry; check forward supersession and separate lifecycle evidence for delivery claims.',
    href: '/concepts/adrs/', source: 'decisionLog' },
  { id: 'autonomy', label: 'Autonomous choice', record: 'sprint-log.md',
    example: 'A moderate in-scope choice is logged with its options, rationale, low confidence and recorded-intent citation.',
    supports: 'Which choice the sprint made under its existing authority and which uncertainty deserves follow-up.',
    missing: 'Low confidence is not automatically a hard stop. A log entry cannot widen approved scope or satisfy an unsupported prerequisite.',
    inspect: 'Check the initial scope, intent, strength-to-confidence mapping and any applicable typed method grant. Review low-confidence entries verbatim.',
    href: '/concepts/smarts/', source: 'sprint' },
  { id: 'exception', label: 'Sanctioned bypass', record: 'overrides.log',
    example: 'A specific gate exception has a timestamp, BY identity and reason written before the immediate action.',
    supports: 'A sanctioned bypass was recorded at that boundary; the heavier security form carries the specific acknowledged finding.',
    missing: 'It is not a standing exception, proof that every action was mediated, or resistance to an unrestricted same-user filesystem writer.',
    inspect: 'Compare the exact line, gate, reason and action. Protect the original record; redaction for sharing is a separate labelled derivative.',
    href: '/guides/overriding-a-gate/', source: 'override' },
  { id: 'sweep', label: 'Review finding', record: 'checkpoints/*.md',
    example: 'A dated sweep reports an unresolved export-handling finding and retains an incomplete reviewer result.',
    supports: 'What that sweep found in its observed scope, including missing evidence and follow-up dispositions.',
    missing: 'A dated report is neither task acceptance nor a promotion sign-off. An incomplete review is not a clean result.',
    inspect: 'Check source identity, reviewer coverage, complete verdict and current disposition. Revalidate findings against later work.',
    href: '/concepts/checkpoints/', source: 'checkpointWriter' },
  { id: 'packet', label: 'Audit packet', record: 'audits/YYYY-MM-DD.md',
    example: 'A packet combines range-bound commits and events with currently unresolved questions and the latest open checkpoint findings.',
    supports: 'A traceable assembly of the available records, with commit and time ranges in its header.',
    missing: 'The packet does not run a new review, reconstruct missing events, freeze all sections to one past instant, or certify a release.',
    inspect: 'Resolve the range and verify sampled records against their sources. Distinguish empty, missing and unreadable inputs; do not manufacture history.',
    href: '/reference/commands/audit/', source: 'audit' },
];

export const decisionRoutes = [
  { id: 'reconcile', label: 'Interactive reconciliation', entry: '/ca:reconcile', question: 'Which competing position should govern?', source: 'reconcile' as EvidenceSource,
    steps: [
      { role: 'Command → skill', title: 'Locate and compare', detail: 'decision-variance selects full or named scope, locates the required exact sources and indexes relevant decisions plus scaffold evidence. Report-only returns without decision capture; missing inputs remain visible.' },
      { role: 'Skill · optional agents', title: 'Recommend with evidence', detail: 'The skill classifies variances and applies SMARTS. Large passes may use scout and grader; an optional decision-challenger does not decide for you.' },
      { role: 'Human decision', title: 'Choose explicitly', detail: 'Report-only returns before this step. In reconciliation, the user resolves remaining variances; an already-selected concrete choice is not requested again. A strong recommendation is not decision authority.' },
      { role: 'Skill return', title: 'Append and recommend', detail: 'In reconciliation, append the attributed choice immediately without rewriting history. Recommend downstream work; do not edit project artifacts or code to make the variance disappear.' },
    ], endpoint: 'A read-only report, or a recorded user choice in reconciliation, with downstream recommendations. Replacement ADR authoring and implementation remain separately directed.' },
  { id: 'sprint', label: 'Autonomous execution', entry: '/ca:sprint', question: 'How can approved work proceed within its boundary?', source: 'sprint' as EvidenceSource,
    steps: [
      { role: 'Human approval', title: 'Establish the scope', detail: 'Review the initial specification and plan. Satisfy the actual installed approval requirements; typed method delegation is an additional scoped grant.' },
      { role: 'Recorded-intent check', title: 'Conform before scoring', detail: 'Follow the highest-ranked applicable decision. Constrained choices carry its citation; silent records allow scoring. A real contradiction surfaces.' },
      { role: 'Skill → task execution', title: 'Decide within scope', detail: 'Score non-hard-gate choices, including moderate and tied results. Retain tests and scope; a failure requires the original gate to pass after repair.' },
      { role: 'Retained evidence', title: 'Log and hand off', detail: 'Append each auto-decision with intent and confidence. Genuine security, authority, irreversible-action and merge boundaries still stop.' },
    ], endpoint: 'Approved work proceeds to the PR handoff, not an autonomous merge. The log is evidence of reasoning, not universal mutation authority.' },
] as const;

/** Fail malformed teaching data; source-excerpt tests are drift alerts, not semantic proof. */
export function validateDecisionEvidence(): string[] {
  const errors: string[] = [];
  if (!/^[0-9a-f]{40}$/.test(evidenceSourceRevision)) errors.push('invalid source revision');
  for (const cases of [adrCases, auditCases]) {
    const ids = new Set<string>();
    for (const item of cases) {
      if (ids.has(item.id) || !/^[a-z][a-z0-9-]*$/.test(item.id)) errors.push('duplicate or invalid case');
      ids.add(item.id);
      if (!evidenceSources[item.source]) errors.push('missing case owner');
      if (!item.href.startsWith('/') || item.href.startsWith('//')) errors.push('invalid continuation');
      if (![item.label,item.record,item.example,item.supports,item.missing,item.inspect].every(s => s.trim())) errors.push('incomplete case');
    }
  }
  for (const lens of smartsExample.lenses) for (const cell of lens.cells) {
    if (cell.reason.split(/\s+/).length > 20) errors.push(`long ${lens.id} cell`);
    if (/\b(potentially|might|arguably|perhaps|generally|tends to|could be|may)\b/i.test(cell.reason)) errors.push(`hedged ${lens.id} cell`);
  }
  return errors;
}
