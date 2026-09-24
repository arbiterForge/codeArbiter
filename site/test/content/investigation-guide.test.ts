import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { guideGroups } from '../../scripts/guide-directory';
import { buildJourneySidebar } from '../../scripts/journey-navigation';
const read = (path: string) => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8');
const guide = read('src/content/docs/guides/investigate-and-fix.mdx');

describe('investigation and repair guidance', () => {
  it('appears in guide discovery, navigation and the installation/application distinction', () => {
    expect(guideGroups.find(group => group.id === 'make-a-change')!.slugs).toContain('investigate-and-fix');
    expect(JSON.stringify(buildJourneySidebar([], []))).toContain('guides/investigate-and-fix');
    expect(read('src/content/docs/guides/troubleshooting.md')).toContain('For a defect in **your application**');
    expect(read('src/content/docs/guides/return-to-a-project.md')).toContain('/guides/investigate-and-fix/');
  });
  it('preserves the owning debug skill evidence floor and board-write exception', () => {
    const skill = read('../core/surface/skills/debug/SKILL.md');
    expect(skill).toContain('at least three distinct candidate causes');
    expect(skill).toContain('CONFIRMED, REFUTED, or INCONCLUSIVE');
    expect(skill).toContain('queued entry **through the board helper');
    expect(guide).toContain('at least three distinct mechanisms');
    expect(guide).toContain('INCONCLUSIVE remains INCONCLUSIVE');
    expect(guide).toContain('queued board note through the task');
    expect(guide).toContain('not a\nzero-write operation');
    expect(guide).toContain('contract does not promise a new, fixed-path');
    const curated = read('src/curated/commands/debug.md');
    expect(curated).not.toContain('every phase is read-only');
    expect(curated).toContain('not universally zero-write');
  });
  it('teaches unchanged behavioral assertions and does not invent a fixed repro from an import error', () => {
    expect(read('../core/surface/skills/tdd/SKILL.md')).toContain("assertions MUST be unchanged between red and green");
    expect(guide).toContain('minimum correction then makes the same assertion pass');
    expect(guide).toContain('missing module');
    expect(guide).toContain('/guides/review-artifacts/#check-your-hosts-authority-capability');
    expect(guide).toContain('does not create those receipts');
  });
  it('accurately bounds the existing fixture evidence without manufacturing a debugging transcript', () => {
    const recorded = JSON.parse(read('public/examples/saved-searches/test-runs.json'));
    expect(recorded.red.output).toContain("None is not an instance of <class 'str'>");
    expect(recorded.red.exit_code).toBe(1); expect(recorded.green.exit_code).toBe(0);
    expect(guide).toContain('not a demonstrated quoting-only defect');
    expect(guide).toContain('not a\nrecorded debug session');
    expect(guide).toContain('/examples/saved-searches/test-runs.json');
  });
  it('does not create a public command, permission bypass or destructive cleanup instruction', () => {
    for (const shortcut of ['/ca:investigate', 'git reset --hard', 'git clean -fd', '--no-verify']) expect(guide).not.toContain(shortcut);
    expect(guide).toContain('Do not dump all environment variables');
    expect(guide).toContain('Authorship requires your attribution');
    expect(guide).toContain('/guides/review-and-ship/');
  });
});
