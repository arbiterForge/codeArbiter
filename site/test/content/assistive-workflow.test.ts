import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { generate } from '../../scripts/generator/generate';
import type { RenderedPage } from '../../scripts/generator/types';

const site = fileURLToPath(new URL('../..', import.meta.url));
const read = (path: string) => readFileSync(join(site, path), 'utf8').replace(/\s+/g, ' ');
let output: string;
let pages: RenderedPage[];
beforeAll(() => {
  output = mkdtempSync(join(tmpdir(), 'ca-assistive-reference-'));
  pages = generate(join(site, '../plugins/ca'), output, undefined, join(site, 'src/curated'), true).pages;
});
afterAll(() => { if (output) rmSync(output, { recursive: true, force: true }); });
const reference = (type: RenderedPage['type'], slug: string) => {
  const page = pages.find(page => page.type === type && page.slug === slug)!;
  expect(page, `${type}/${slug} must render`).toBeDefined();
  const [guidance, source] = page.markdown.split('## Source\n\n');
  expect(source, `${slug} must retain its source embed`).toBeTruthy();
  return { guidance: guidance.replace(/\s+/g, ' '), source: source.replace(/\s+/g, ' ') };
};

describe('composed assistive workflow references', () => {
  it('reuses current checks and reviews across commit and PR phases', () => {
    for (const slug of ['commit-gate', 'finishing-a-development-branch']) {
      const {guidance, source} = reference('skill', slug);
      for (const text of [guidance, source]) {
        expect(text).toMatch(/[Rr]euse/);
        expect(text).toContain('affected');
      }
    }
    const commit = reference('skill', 'commit-gate');
    expect(commit.source).toContain('Never pass v2 records to `rebaseline`');
    expect(commit.guidance).toContain('managed v2 pairs');
    const guide = read('src/content/docs/guides/first-feature.mdx');
    expect(guide).toContain('reuse applicable checks and reviews on unchanged inputs');
    expect(guide).not.toMatch(/collect fresh evidence for `REVIEW`|Pi has no qualified prompt-approval seam/);
  });
  it('uses existing sprint and refactor authorization throughout public guidance', () => {
    for (const type of ['command', 'skill'] as const) {
      const refactor = reference(type, 'refactor');
      for (const text of [refactor.guidance, refactor.source]) {
        expect(text).toContain('existing');
        expect(text).not.toMatch(/user-signed-off surface table|explicit user-approved amendment/);
      }
    }
    const pages = [reference('command', 'sprint').guidance,
      read('src/content/docs/glossary.md'), read('src/content/docs/concepts/smarts.mdx')];
    for (const text of pages) {
      expect(text).not.toMatch(/every auto-decision|every non-hard-gate decision|spec and plan must be approved|delegate-methods|smarts-apply/);
    }
  });
  it('retains real greenfield confirmation and native population without discarding sources', () => {
    for (const type of ['command', 'skill'] as const) {
      const { guidance, source } = reference(type, 'decompose');
      // Repositories that keep the Markdown format retain the paired-writer procedure.
      const legacy = read('../core/surface/skills/decompose/references/markdown-format.md');
      for (const text of [guidance, legacy]) {
        expect(text).toContain('.codearbiter/plans/decomposition/');
        expect(text).toContain('_session.md');
        expect(text).toContain('--context-finalize');
        expect(text).toMatch(/unchanged (?:accepted work|artifacts)/);
      }
      expect(source).toContain('references/markdown-format.md');
      expect(source).toContain('knowledge.py initialize');
      expect(guidance).not.toMatch(/promote every draft|no draft decision records|remove the (?:working )?draft directory/);
    }
    const guide = read('src/content/docs/guides/plan-a-new-project.mdx');
    expect(guide).toContain('five document/provenance pairs');
    expect(guide).toContain('thirteen required outputs');
    expect(guide).toContain('retain the interview');
    expect(guide).not.toContain('60–110');
  });
  it('carries actual feature decisions into a maintained plan without a second approval cycle', () => {
    const brainstorming = reference('skill', 'brainstorming');
    expect(brainstorming.guidance).toContain('consequential');
    expect(brainstorming.guidance).toContain('already');
    expect(brainstorming.guidance).not.toMatch(/requires an applicable host-observed|hard stop until/);
    const plan = reference('skill', 'writing-plans');
    expect(plan.guidance).toContain('existing authorization');
    expect(plan.guidance).toContain('criterion IDs');
    expect(plan.guidance).toContain('dependencies');
    expect(plan.guidance).not.toContain('required approval');
    expect(plan.source).toContain('Structural errors or a conflicting write remain actual operation failures');
  });
  it('selects verification by work while preserving genuine regression and characterization checks', () => {
    const { guidance, source } = reference('skill', 'tdd');
    for (const text of [guidance, source]) {
      expect(text).toMatch(/[Cc]onfirmed fix/);
      expect(text).toContain('characterization');
      expect(text).toContain('coverage');
      expect(text).toContain('lint');
    }
    expect(guidance).toContain('assertions unchanged between RED and GREEN');
    expect(guidance).toContain('initially passing');
    expect(guidance).not.toMatch(/failing test (?:must exist )?for every obligation|no feature code exists/);
    expect(source).toContain('do not alter correct production behavior merely to obtain a failure');
  });
  it.each(['backend-author', 'frontend-author', 'infra-author'])('keeps %s aligned with the caller-selected verification and staging scope', slug => {
    const { guidance, source } = reference('agent', slug);
    expect(guidance).toContain("caller's selected verification approach");
    expect(guidance).toContain('characterization');
    expect(guidance).toContain('stage only when assigned and authorized');
    expect(guidance).not.toMatch(/never writes implementation code before|Dispatched fresh per task/);
    expect(source).toContain('author-tdd-workflow.md');
    expect(source).toContain('security-reviewer');
  });
  it('preserves the measured refactor baseline while allowing mechanical reference updates', () => {
    for (const type of ['command', 'skill'] as const) {
      const { guidance, source } = reference(type, 'refactor');
      expect(guidance).toContain('post-backfill baseline');
      expect(guidance).toContain('behavioral assertions');
      expect(guidance).toContain('import or symbol-reference');
      expect(guidance).not.toMatch(/zero modifications|parity tests pass locally without edits/);
      expect(source).toContain('at least one direct test');
    }
  });
  it('continues independent authorized work and reserves pauses for actual stops', () => {
    const coordinator = reference('skill', 'executing-plans');
    expect(coordinator.guidance).toContain('continue independent work');
    expect(coordinator.guidance).toContain('user-requested pause');
    expect(coordinator.guidance).not.toMatch(/wait for your acknowledgment|every plan task is accepted/);
    const implementation = reference('skill', 'subagent-driven-development');
    expect(implementation.guidance).toContain('direct implementation');
    expect(implementation.guidance).toContain('actual dependencies');
    expect(implementation.guidance).toContain('`DONE`');
    expect(implementation.guidance).toContain('pending checks');
    expect(implementation.guidance).not.toContain('Each task gets its own fresh agent');
    expect(implementation.source).toContain('Do not clear a user stop');
  });
  it('checks the committed branch and preserves commit, merge and discard authority', () => {
    for (const [type, slug] of [['command', 'pr'], ['skill', 'finishing-a-development-branch']] as const) {
      const { guidance, source } = reference(type, slug);
      expect(guidance).toContain('base-to-HEAD');
      expect(guidance).toContain('secrets');
      expect(guidance).toContain('current-head');
      expect(guidance).not.toMatch(/commit gate.*(?:cleared|passed|clean).*this session/);
      expect(source).toContain('Merge requires explicit authorization');
      expect(source).toContain('confirmation naming the branch');
    }
    const commit = reference('skill', 'commit-gate');
    expect(commit.guidance).toContain('explicit authorization to commit');
    expect(commit.guidance).toContain('Unfinished plan tasks');
    expect(commit.source).toContain('Do not call `_preflight_current_acceptance` for ordinary commits');
  });
  it('anchors checkpoint audit windows to reviewed source and time rather than an override count', () => {
    for (const slug of ['checkpoint', 'audit']) {
      const { guidance, source } = reference('command', slug);
      for (const text of [guidance, source]) {
        expect(text).toMatch(/source_commit|reviewed commit/);
        expect(text).toMatch(/recorded_at|UTC review-start time/);
        expect(text).toMatch(/worktree_dirty|worktree was dirty/);
      }
      expect(guidance).not.toContain('source-contract discrepancy');
    }
    expect(reference('command', 'audit').guidance).toContain('ancestor of HEAD');
  });
  it('teaches current test-first work without embedding an obsolete execution route', () => {
    const text = read('src/content/docs/concepts/test-first.mdx');
    expect(text).toContain('direct implementation');
    expect(text).toContain('passing characterization');
    expect(text).not.toContain('<ExecutionMap');
    expect(text).not.toContain('historical attended workflow');
    expect(text).toContain('explicitly requested pause');
    expect(text).not.toMatch(/selects a fresh author for a task|needs the actual current authority records|waits for its human checkpoint/);
  });
  it('teaches the feature lane without per-task fleets or routine approval stops', () => {
    const text = read('src/content/docs/guides/feature-lane.mdx');
    expect(text).toContain('direct implementation');
    expect(text).toContain('criterion-focused');
    expect(text).toContain('explicitly requested pause');
    expect(text).toContain('`DONE`');
    expect(text).not.toContain('lane-feature.svg');
    expect(text).not.toContain('/concepts/gated-lanes/#follow-the-full-feature-path');
    expect(text).not.toMatch(/fresh author agent and a full reviewer fleet|failing test for each obligation|execution stops for a human checkpoint|every plan task is `ACCEPTED`|Approve the current plan before execution|No source file is touched until you do/);
  });
  it('scopes recovery diagnostics without treating ordinary progress as attestation', () => {
    const text = read('src/content/docs/guides/resume-and-recover.mdx');
    const explorer = read('src/components/RecoveryExplorer.astro');
    for (const prose of [text, explorer]) {
      expect(prose).toContain('DONE');
      expect(prose).toContain('explicit attestation');
      expect(prose).toContain('advisory');
    }
    expect(text).not.toMatch(/Complete its review\/readiness\/approval path|engine must still establish eligibility|leave the work stopped/);
    expect(explorer).not.toMatch(/make the plan executable|unsupported host adapter remains a stop/);
    expect(text).toContain('exact stored operation');
    expect(text).toContain('never clears a user stop');
  });
  it.each(['concepts.mdx', 'concepts/gated-lanes.mdx'])('keeps %s aligned with the current shared feature map', path => {
    const text = read(`src/content/docs/${path}`);
    expect(text).toContain('direct implementation');
    expect(text).toContain('DONE');
    expect(text).toContain('explicit');
    expect(text).not.toMatch(/waits for the human acknowledgement|returns to you between scopes|must establish current eligibility and acceptance|next human acknowledgement/);
  });
  it('reports implementation and check state separately in the status companion', () => {
    const text = reference('command', 'status').guidance;
    expect(text).toContain('`DONE`');
    expect(text).toContain('Verification is reported separately');
    expect(text).toContain('Drafts do not create a permission wait');
    expect(text).toContain('/ca:status drift');
    expect(text).not.toMatch(/only `ACCEPTED` tasks count|approval is required to resume/);
  });
  it('limits missing authority diagnostics to the operation and actual evidence gap', () => {
    const text = read('src/content/docs/guides/troubleshooting.md');
    expect(text).toContain('draft status does not block ordinary authorized work');
    expect(text).toContain('An explicit attestation operation lacks required evidence');
    expect(text).toContain('continue independent authorized work');
  });
  it('documents paired native context writes and retained initialization sources', () => {
    const text = read('src/content/docs/codearbiter-directory.md');
    expect(text).toContain('native preview/apply with paired provenance');
    expect(text).toContain('plans/decomposition/');
    expect(text).toContain('Keep them after initialization');
    expect(text).toContain('Coverage, identity freshness and semantic review remain distinct');
    expect(text).toContain('implementation completion and verification separately');
    expect(text).not.toContain('These living references are maintained by hand');
  });
  it('keeps role context bounded without requiring a fresh author or delivery ticket', () => {
    const text = read('src/content/docs/concepts/persona-and-context.mdx');
    expect(text).toContain('implement it directly or delegate');
    expect(text).toContain('context ticket is not required to start authorized work');
    expect(text).toContain('required information is absent, surface the gap');
    expect(text).toContain('Every unit must be accounted for as DONE, ERRORED or DEFERRED');
    expect(text).not.toMatch(/every task gets a fresh author|must obtain a context ticket/);
  });
  it('keeps checkpoint anchors and real review accounting independent of task progress', () => {
    const text = read('src/content/docs/concepts/checkpoints.mdx');
    for (const field of ['source_commit', 'recorded_at', 'worktree_dirty']) expect(text).toContain(field);
    expect(text).toContain('missing observations remain unknown');
    expect(text).toContain('preserve incomplete-unit results');
    expect(text).toContain('never overwritten');
    expect(text).toContain('bare integer');
    expect(text).toContain('pauses only when the user requested that pause or a real decision is missing');
    expect(text).not.toMatch(/waits for (?:your|the user.s) acknowledgement|all tasks must be `ACCEPTED`/);
  });
  it('keeps current feature and sprint guidance consistent with their real authorization and checks', () => {
    const feature = reference('command', 'feature').guidance;
    expect(feature).toContain('implemented directly or delegated when useful');
    expect(feature).toContain('exact-head hosted CI remains mandatory before merge');
    expect(feature).not.toContain('fresh author');
    const sprint = read('src/content/docs/guides/autonomous-sprints.mdx');
    expect(sprint).toContain('genuine failing regression before its fix');
    expect(sprint).toContain('passing characterization checks');
    expect(sprint).toContain('Preserve user stops');
    expect(sprint).toContain('request does not authorize merging or publication');
    expect(sprint).not.toMatch(/Historical workflow reference|ready with no blockers or warnings before you approve|arm-sprint-approval/);
  });
});
