import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildJourneySidebar } from '../../scripts/journey-navigation';
import { guideGroups } from '../../scripts/guide-directory';

const site = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, site), 'utf8');
const guide = read('src/content/docs/guides/review-and-ship.mdx');

describe('review-to-delivery guidance', () => {
  it('leads the review-and-ship sidebar with procedures; the guide links the exact references', () => {
    const guides = buildJourneySidebar([], [])[1];
    const group = guides.items.find(item => item.label === 'Review and ship');
    // Guides list guides; command reference is one click away from the guide itself (DOCS-OVERHAUL M2).
    expect(group && 'items' in group ? group.items.map(item => 'slug' in item && item.slug) : []).toEqual([
      'guides/review-and-ship', 'guides/adding-a-dependency', 'guides/recording-adrs',
      'guides/releasing-a-version',
    ]);
    for (const command of ['review', 'commit', 'pr']) expect(guide).toContain(`/reference/commands/${command}/`);
  });
  it('keeps Review and ship guide membership consistent with the task directory', () => {
    const sidebar = buildJourneySidebar([], [])[1];
    const review = sidebar.items.find(item => item.label === 'Review and ship');
    const change = sidebar.items.find(item => item.label === 'Make a change');
    const directory = guideGroups.find(group => group.id === 'review-and-ship')!;
    const expected = directory.slugs.map(slug => `guides/${slug}`);
    const reviewGuides = review && 'items' in review
      ? review.items.flatMap(item => 'slug' in item && item.slug.startsWith('guides/') ? [item.slug] : []) : [];
    expect(reviewGuides).toEqual(expected);
    expect(change && 'items' in change
      ? change.items.some(item => 'slug' in item && expected.includes(item.slug)) : true).toBe(false);
  });
  it('preserves the read-only inbound scope and separate outward-facing permission', () => {
    const source = read('../core/surface/commands/review.md');
    expect(source).toContain('For a PR target, posting the verdict is a separate, confirmed step');
    expect(source).toContain('MUST NOT check out, merge');
    expect(guide).toContain('A local inbound-PR verdict is the deliverable');
    expect(guide).toContain('does not issue GitHub **Approve** or **Request changes**');
    expect(guide).toContain('must not fall back to your local diff');
    const curated = read('src/curated/commands/review.md');
    expect(curated).toContain('a CRITICAL or HIGH finding surfaces on your own change');
    expect(curated).toContain('/ca:review [path | #<pr> | <pr-url>]');
    expect(curated).toContain('Posting a comment requires separate');
  });
  it('does not turn the checkpoint count or a verdict into acceptance authority', () => {
    const source = read('../core/surface/commands/checkpoint.md');
    expect(source).toContain('current override **count**');
    expect(guide).toContain('integer override-count baseline, not proof that the commit gate passed');
    expect(guide).toContain('`source_commit`, `recorded_at` and `worktree_dirty`');
    expect(guide.replace(/\s+/g, ' ')).toContain('An acceptance receipt is not a prerequisite for an ordinary authorized commit or PR');
    expect(guide.replace(/\s+/g, ' ')).toContain('explicit attested verification or review claim');
    expect(guide).toContain('/guides/review-artifacts/#check-your-hosts-authority-capability');
  });
  it('keeps automatic review distinct from a redundant standalone ceremony', () => {
    expect(read('../core/surface/commands/pr.md')).toBe('{{SKILL_ENTRY:finishing-a-development-branch}}\n');
    const source = read('../core/surface/skills/finishing-a-development-branch/SKILL.md').replace(/\s+/g, ' ');
    expect(source).toContain('Confirm current-head readiness');
    expect(source).toContain('explicit base-to-HEAD diff');
    expect(source).toContain('An empty staged set does not establish branch coverage');
    expect(source).toContain('Bind secrets scanning and specialized security/migration checks to that same base-to-HEAD subject');
    expect(guide).toContain('not required as a redundant ceremony');
    expect(guide).toContain('missing, pending, cancelled, stale, mismatched or failing');
    expect(guide).toContain('Sprint autonomy ends with opening the PR');
    expect(guide).toContain('The remote branch is not deleted');
    expect(guide).toContain('Unknown residue remains unique');
  });
  it('asks for branch disposition only when no action is already selected', () => {
    const text = read('src/curated/skills/finishing-a-development-branch.md');
    expect(text).toContain('when: current-head verification is assembled and no action is selected');
    expect(text).toContain('If no action is selected, it presents exactly three ways');
    expect(text).toContain('If the request or caller has not selected an action, present the three terminal options');
    expect(text).toContain('A direct open-PR request keeps that selection');
    expect(text).toContain('an autonomous sprint selects open PR only');
    expect(text).toContain('only an authorized merge through that PR lands the work');
    expect(text).toContain('confirming any unpushed work');
    expect(text).not.toContain('then presents exactly three ways');
    expect(text).not.toContain('2. Present the three terminal options');
  });
  it('labels the fictional example and avoids a new command or cleanup shortcut', () => {
    expect(guide).toContain('Illustrative review excerpt, not captured execution');
    expect(guide).not.toContain('/ca:review-pr');
    expect(guide).not.toContain('git clean');
    expect(guide).not.toContain('git reset --hard');
    expect(guide).not.toContain('gh pr merge --admin');
    expect(guide).toContain('/ca:pr --cleanup');
    expect(read('../docs/artifacts/consumer-inventory.json')).toContain('site/src/content/docs/guides/review-and-ship.mdx');
  });
});
