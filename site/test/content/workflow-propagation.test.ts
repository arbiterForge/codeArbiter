import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { workflows } from '../../scripts/execution-maps/workflows';
const read = (path: string) => readFileSync(path, 'utf8');
const docs = 'src/content/docs/';

describe('C04 cross-surface consistency', () => {
  it('adds a shared route comparison without duplicating a command catalog or changing old routes', () => {
    const hub = read(`${docs}concepts/workflow-routes.mdx`);
    expect(hub).toContain('<WorkflowDirectory />');
    expect(hub).toContain('not three consecutive');
    expect(read(`${docs}concepts.mdx`)).toContain('/concepts/workflow-routes/');
    for (const slug of ['recording-adrs', 'releasing-a-version']) {
      expect(existsSync(`${docs}guides/${slug}.md`)).toBe(false);
      expect(existsSync(`${docs}guides/${slug}.mdx`)).toBe(true);
    }
    for (const w of workflows) expect(existsSync(`public/diagrams/${w.asset}`)).toBe(true);
  });
  it('retains every previous heading anchor when ADR and release sources move', () => {
    for (const [slug, headings] of [
      ['recording-adrs', ['Before you start', 'Create a decision', 'Verify the result', 'Inspect a complete example', 'Supersede a decision', 'Common stops and recovery', 'Next steps']],
      ['releasing-a-version', ['Where the targets come from', 'Prerequisites', '1. Target-scoped pre-flight', '2. Derive the version and changelog', '3. Compose the local tag', '4. Review and authorize publication', 'Common stops', 'Recover from a bad published release', "codeArbiter's own declared targets"]],
    ] as const) for (const heading of headings) expect(read(`${docs}guides/${slug}.mdx`)).toContain(`## ${heading}`);
  });
  it('replaces bucket images with the complete model and retains direct SVG links', () => {
    for (const [slug, id] of [['autonomous-sprints', 'sprint'], ['adding-a-dependency', 'dependency'], ['recording-adrs', 'adr'], ['releasing-a-version', 'release']]) {
      const text = read(`${docs}guides/${slug}.mdx`);
      expect(text).toContain(`workflow="${id}"`);
      expect(text).toContain('/diagrams/lane-');
    }
    const init = read(`${docs}guides/opt-in-a-repo.mdx`);
    expect(init).toContain('workflow="greenfield"'); expect(init).toContain('workflow="brownfield"');
    expect(init).toContain('/diagrams/lane-opt-in.svg');
    expect(init).toContain('alternatives, not consecutive phases');
  });
  it('teaches current assistive work and keeps pinned attestation evidence separately scoped', () => {
    const source = read('../core/surface/SPRINT.md');
    expect(source).toContain('without a second artifact approval system');
    expect(source).toContain('does **not** grant arbitrary future scope expansion');
    const historical = execFileSync('git', ['show', '929229354e3a15ae3002c82116b66c837ab43729:core/surface/SPRINT.md'], {encoding: 'utf8'});
    expect(historical).toContain('commits approval plus plan binding in one recoverable native transaction.');
    for (const path of ['guides/autonomous-sprints.mdx', 'guides/review-artifacts.md']) {
      const text = read(docs + path);
      expect(text).toContain('DONE');
      expect(text).toMatch(/[Ee]xplicit attestation/);
      expect(text).toContain('exact-head');
      expect(text).not.toContain('Historical receipt-based workflow');
      expect(text).not.toContain('current typed adapter arms one artifact at a time');
    }
    expect(read(docs + 'guides/review-artifacts.md').replace(/\s+/g, ' ')).toContain('without requesting separate artifact approval');
    expect(read(docs + 'guides/autonomous-sprints.mdx')).toContain('Work runs directly or through useful delegation');
  });
  it('states release dry-run exclusions and the mandatory PR, hosted and receipt boundaries', () => {
    const source = read('../core/surface/skills/release/SKILL.md');
    expect(source).toContain('The release commit must merge through a pull request before any tag is composed.');
    expect(source).toContain('CI success alone never creates authorization');
    const guide = read(docs + 'guides/releasing-a-version.mdx');
    expect(guide).not.toContain('dry run performs full pre-flight');
    for (const required of ['locally evaluable', '`git fetch`', 'qualifying hosted publisher', 'separate receipt', 'exact-head', 'before tag composition']) expect(guide).toContain(required);
    for (const kind of ['commands', 'skills']) {
      const text = read(`src/curated/${kind}/release.md`);
      expect(text).toContain('release PR'); expect(text).toContain('hosted');
      expect(text).not.toContain('Composed annotated tag ca-codex-v0.3.0 locally');
      expect(text).toContain('/concepts/workflow-routes/');
    }
  });
  it('keeps decision acceptance separate from derived delivery evidence', () => {
    const guide = read(docs + 'guides/recording-adrs.mdx');
    expect(guide).toContain('subsequent commit');
    expect(guide).toContain('Remaining Proposed is a valid outcome');
    expect(guide).toContain('legacy-unsealed');
    expect(guide).not.toContain('number is gap-free');
  });
  it('keeps ordinary context inspection available without qualified scout ceremonies', () => {
    for (const path of [
      `${docs}guides/understand-an-existing-project.md`,
      `${docs}concepts/workflow-routes.mdx`,
      'src/curated/skills/context-creation.md',
      'src/curated/commands/create-context.md',
      'src/curated/agents/scout.md',
    ]) {
      const text = read(path).replace(/\s+/g, ' ');
      expect(text, path).toContain('optional');
      expect(text, path).toMatch(/direct|bounded inspection/);
      expect(text, path).not.toMatch(/six (parallel|isolated) scout|route stops before dispatch|always uses six/);
    }
    const refresh = read('src/curated/commands/context-check.md');
    expect(refresh).toContain('already selects');
    expect(refresh).not.toContain('full brownfield re-scan from scratch is `/ca:create-context`');
    const compatibility = read(`${docs}getting-started/compatibility.mdx`);
    expect(compatibility).not.toContain('context creation blocks without isolated scouts');
  });
  it('describes current typed progress without restoring approval or context-ticket prerequisites', () => {
    const format = read('../docs/artifacts/spec-and-plan-format.md').replace(/\s+/g, ' ');
    expect(format).toContain('current write schema is `0.3.2`');
    for (const term of ['`task-context`', '`task-check`', '`DONE`', 'actual user decisions']) expect(format).toContain(term);
    expect(format).not.toContain('Execution obtains contextual reads and a final delivery ticket');
    expect(format).not.toContain('passes the existing plan approval gate');
    const recovery = read('../docs/artifacts/migration-and-recovery.md').replace(/\s+/g, ' ');
    for (const term of ['context-preview', 'preview_ref', 'preview_sha256', 'forward recovery']) expect(recovery).toContain(term);
    expect(recovery).not.toContain('until the normal workflow separately obtains and binds current approvals');
  });
});
