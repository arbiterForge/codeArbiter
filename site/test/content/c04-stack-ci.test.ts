import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// Identical executable workflows, pinned in retained main history rather than the open stack.
const base = '929229354e3a15ae3002c82116b66c837ab43729';
const parent = 'docs/concepts-decisions-evidence';
/** Ignore explanatory comments, but compare every executable workflow line. */
const executable = (text: string) => text.split('\n').filter(line => !/^\s*#/.test(line)).join('\n');

describe('C04 stacked review runs the unchanged required gates', () => {
  for (const file of ['ci.yml', 'docs.yml']) it(`${file} changes only the exact PR-base allowlist`, () => {
    const path = `.github/workflows/${file}`;
    const before = execFileSync('git', ['show', `${base}:${path}`], { encoding: 'utf8' });
    const current = readFileSync(`../${path}`, 'utf8');
    const allowed = file === 'ci.yml' ? ['main', 'feat/codex-support-m0'] : ['main'];
    const original = `branches: [${allowed.join(', ')}]`;
    const replacement = `branches: [${[...allowed, parent].join(', ')}]`;
    // Replace only inside pull_request, never a push or deployment trigger.
    const position = before.indexOf('  pull_request:');
    expect(position).toBeGreaterThan(0);
    const expected = before.slice(0, position) + before.slice(position).replace(original, replacement);
    expect(executable(current)).toBe(executable(expected));
    expect(current).not.toContain('pull_request_target:');
  });
});
