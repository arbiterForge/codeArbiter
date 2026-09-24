import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildJourneySidebar } from '../../scripts/journey-navigation';
import { guideGroups } from '../../scripts/guide-directory';

const site = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, site), 'utf8');
const guide = read('src/content/docs/guides/review-and-ship.mdx');

describe('review-to-delivery guidance', () => {
  it('leads the review-and-ship sidebar with a procedure while retaining exact references', () => {
    const guides = buildJourneySidebar([], [])[1];
    const group = guides.items.find(item => item.label === 'Review and ship');
    expect(group && 'items' in group ? group.items.map(item => 'slug' in item && item.slug) : []).toEqual([
      'guides/review-and-ship', 'guides/adding-a-dependency', 'guides/recording-adrs',
      'reference/commands/review', 'reference/commands/commit',
      'reference/commands/pr', 'guides/releasing-a-version',
    ]);
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
    expect(guide).toContain('all_accepted_and_current: true');
    expect(guide).toContain('Codex-only production verification/review authority');
    expect(guide).toContain('/guides/review-artifacts/#check-your-hosts-authority-capability');
  });
  it('keeps automatic review distinct from a redundant standalone ceremony', () => {
    expect(read('../core/surface/commands/pr.md')).toContain('Confirm the commit gate cleared');
    expect(guide).toContain('not required as a redundant ceremony');
    expect(guide).toContain('missing, pending, cancelled, stale, mismatched or failing');
    expect(guide).toContain('Sprint autonomy ends with opening the PR');
    expect(guide).toContain('The remote branch is not deleted');
    expect(guide).toContain('Unknown residue remains unique');
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
