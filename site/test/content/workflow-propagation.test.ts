import { readFileSync, existsSync } from 'node:fs';
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
  it('documents the real initial-pair transaction separately from feature approval', () => {
    const source = read('../core/surface/SPRINT.md');
    expect(source).toContain('commits approval plus plan binding in one recoverable native transaction.');
    for (const path of ['guides/autonomous-sprints.mdx', 'guides/review-artifacts.md']) {
      const text = read(docs + path);
      for (const term of ['arm-sprint', 'sprint-approve', 'resume-sprint', 'approve-only', 'delegate-methods']) expect(text).toContain(term);
      expect(text).not.toContain('current typed adapter arms one artifact at a time');
    }
    expect(read(docs + 'guides/review-artifacts.md')).toContain('An attended feature normally approves');
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
});
