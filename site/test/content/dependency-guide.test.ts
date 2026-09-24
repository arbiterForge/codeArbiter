import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { guideGroups } from '../../scripts/guide-directory';
import { buildJourneySidebar } from '../../scripts/journey-navigation';

/** Read current source rather than a copied fixture contract. */
const read = (path: string) => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8');
const guide = read('src/content/docs/guides/adding-a-dependency.mdx');
const command = read('../core/surface/commands/add-dep.md');
const curated = read('src/curated/commands/add-dep.md');

describe('dependency adoption and one-time inspection guidance', () => {
  it('preserves the public route and discovery classification without adding a guide or verb', () => {
    expect(existsSync(new URL('../../src/content/docs/guides/adding-a-dependency.md', import.meta.url))).toBe(false);
    expect(guideGroups.flatMap(group => group.slugs).filter(slug => slug === 'adding-a-dependency')).toHaveLength(1);
    expect(guideGroups.find(group => group.id === 'review-and-ship')!.slugs).toContain('adding-a-dependency');
    expect(JSON.stringify(buildJourneySidebar([], []))).toContain('guides/adding-a-dependency');
    expect(guide).toContain('id="dependency-decision-map"');
    expect(guide).toContain('/diagrams/lane-add-dep.svg');
  });
  it('teaches every owning eligibility condition and keeps adoption outside the exception', () => {
    for (const term of ['by name, in this session', 'It runs ONCE', 'a manifest, a lockfile, or a committed artifact', 'If any is unclear']) {
      expect(command).toContain(term);
    }
    for (const term of ['specific tool by name in the current session', 'runs once for inspection or analysis',
      'changes no manifest, lockfile, base image or committed artifact', 'If eligibility is unclear, use full dependency review',
      'not exempt merely because it uses `npx`']) expect(guide).toContain(term);
  });
  it('retains pinning, registry, confirmation and output obligations on all host projections', () => {
    for (const path of ['../plugins/ca/commands/add-dep.md', '../plugins/ca-codex/skills/ca-add-dep/SKILL.md', '../plugins/ca-pi/skills/ca-add-dep/SKILL.md']) {
      const host = read(path);
      for (const term of ['Pin the exact version', 'https://registry.npmjs.org', 'Confirm before running', 'Report what ran', 'MUST NOT modify a manifest or a lockfile']) expect(host).toContain(term);
    }
    for (const term of ['/ca:add-dep', '$ca-add-dep', '/ca-add-dep', 'https://registry.npmjs.org', 'system temporary directory']) expect(guide).toContain(term);
    expect(guide).toContain('confirmation naming the\nexact command before execution');
  });
  it('distinguishes content preservation from status-code equality and temporary paths from isolation', () => {
    expect(command).toContain('git status --porcelain');
    for (const term of ['already-dirty file can change again', 'git diff --cached', 'before/after content snapshots or hashes',
      'untracked or ignored', 'does not isolate execution, block network access', 'stop this path and inspect the']) expect(guide).toContain(term);
    expect(guide).toContain('orchestrator-enforced, not hook-enforced');
    expect(guide).toContain('H-07 manifest-change signal is an advisory');
  });
  it('uses actual project policy and does not fabricate a package safety review', () => {
    const reviewer = read('../core/surface/agents/dependency-reviewer.md');
    expect(reviewer).toContain('If `tech-stack.md` enumerates allowed licenses, that list governs');
    expect(reviewer).toContain('Do not run install commands');
    expect(guide).toContain('`tech-stack.md` precedence');
    expect(guide).toContain('entire dependency graph has no advisories');
    for (const source of [guide, curated]) {
      expect(source).not.toContain('6M+ weekly downloads');
      expect(source).not.toContain('left-pad@1.3.0');
      expect(source).not.toContain('no known advisories');
    }
    expect(guide).toContain('No package was downloaded or executed');
    expect(curated).toContain('not a captured run or a current package assessment');
    expect(curated).toContain('The\nlegacy `btw` reference in the embedded source');
  });
  it('connects investigation, return, reference and delivery without losing existing anchors', () => {
    expect(read('src/content/docs/guides/investigate-and-fix.mdx')).toContain('/guides/adding-a-dependency/#one-time-inspection-nothing-adopted');
    expect(read('src/content/docs/guides/return-to-a-project.md')).toContain('/guides/adding-a-dependency/');
    for (const heading of ['Run the Command', 'What the Reviewer Checks', "The Repository's License Policy", 'The CVE Gate', 'After Clearance', 'When the Review Fails', 'When Not to Use This Command', 'Related']) expect(guide).toContain(`## ${heading}`);
    expect(guide).toContain('/guides/review-and-ship/');
    expect(curated).toContain('/guides/adding-a-dependency/');
  });
});
