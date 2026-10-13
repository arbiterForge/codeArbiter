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
  it('preserves the owning debug skill evidence floor and no-default-board-write rule', () => {
    const skill = read('../core/surface/skills/debug/SKILL.md');
    expect(skill).toContain('A cited failure with an unknown trigger can enter scoped investigation');
    expect(skill).toContain('There is no fixed minimum or maximum count of hypotheses');
    expect(skill).toContain('CONFIRMED, REFUTED, or INCONCLUSIVE');
    for (const result of ['confirmed_code_defect', 'confirmed_noncode_cause', 'design_question', 'no_action', 'unresolved']) {
      expect(skill).toContain(result);
      expect(guide).toContain(result);
    }
    expect(skill).toContain('Make no default board write');
    expect(skill).toContain('If a separately authorized concrete follow-up is needed');
    expect(guide).toContain('There is no fixed hypothesis count');
    expect(guide).toContain('INCONCLUSIVE remains INCONCLUSIVE');
    expect(guide).toContain('Close without a default board write');
    expect(guide).toContain('A separately authorized concrete task follow-up');
    expect(guide).toContain('contract does not promise a new, fixed-path');
    const curated = read('src/curated/commands/debug.md');
    expect(curated).not.toContain('every phase is read-only');
    expect(curated).toMatch(/makes no default board\s+write/);
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
    expect(guide).toContain('An ADR is optional and needs its own attributed owner');
    expect(guide).toContain('cannot convert a diagnosis-only request into repair authority');
    expect(guide).toContain('/guides/review-and-ship/');
  });
});
