import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
const read = (name: string) => readFileSync(`src/content/docs/${name}`, 'utf8');

describe('Concepts foundation', () => {
  it('teaches outputs, caller ownership and evidence boundaries in the first concepts', () => {
    const landing = read('concepts.mdx');
    expect(landing).toContain('<ExecutionMap');
    expect(landing).toContain('<ConceptNavigator');
    expect(landing).toContain('not a merge or deployment');
    const lanes = read('concepts/gated-lanes.mdx');
    expect(lanes).toContain('does not jump directly to commit');
    expect(lanes).toContain('H-18 activation protection has no in-session override path');
    expect(lanes).toContain('It expressly does not call that');
  });
  it('makes the three project documents and four format paths explicit', () => {
    const artifacts = read('concepts/artifacts.md');
    for (const name of ['01-architecture-breakdown.md', '02-phased-build-plan.md', '03-task-backlog.md']) expect(artifacts).toContain(name);
    for (const phrase of ['typed HTML', 'Existing Markdown pairs', 'Small-lane work', 'Greenfield Markdown', 'not a substitute for a host authority adapter']) expect(artifacts).toContain(phrase);
    expect(artifacts).toContain('not approve or execute');
    expect(artifacts).toContain('/guides/review-artifacts/');
  });
  it('distinguishes observed fixture results from host execution, approval or complete scope evidence', () => {
    const tdd = read('concepts/test-first.mdx');
    expect(tdd).toContain('inside the task');
    expect(tdd).toContain('two failing');
    expect(tdd).toContain('not a demonstrated');
    expect(tdd).toContain('same test-file digest');
    expect(tdd).toContain('not a successful proof');
    expect(tdd).toContain('/guides/review-and-ship/');
  });
});
