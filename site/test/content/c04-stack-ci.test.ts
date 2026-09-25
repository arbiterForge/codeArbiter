import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const base = '090773ec6aa98687cd7b207985cb29ebb8f9c8e1';
const parent = 'docs/concepts-decisions-evidence';
/** Ignore explanatory comments, but compare every executable workflow line. */
const executable = (text: string) => text.split('\n').filter(line => !/^\s*#/.test(line)).join('\n');

describe('C04 stacked review runs the unchanged required gates', () => {
  for (const file of ['ci.yml', 'docs.yml']) it(`${file} changes only the exact PR-base allowlist`, () => {
    const path = `.github/workflows/${file}`;
    const before = execFileSync('git', ['show', `${base}:${path}`], { encoding: 'utf8' });
    const current = readFileSync(`../${path}`, 'utf8');
    const original = file === 'ci.yml' ? 'branches: [main, feat/codex-support-m0]' : 'branches: [main]';
    const replacement = original.replace(']', `, ${parent}]`);
    // Replace only inside pull_request, never a push or deployment trigger.
    const position = before.indexOf('  pull_request:');
    expect(position).toBeGreaterThan(0);
    const expected = before.slice(0, position) + before.slice(position).replace(original, replacement);
    expect(executable(current)).toBe(executable(expected));
    expect(current).not.toContain('pull_request_target:');
  });
});
