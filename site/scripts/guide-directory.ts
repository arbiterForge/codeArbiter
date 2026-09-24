/** Site-only task order. Page frontmatter owns every title, outcome and time estimate. */
export const guideGroups = [
  { id: 'initialize-and-understand', title: 'Initialize and understand',
    description: 'Start with the repository you have, then inspect the context it produces.',
    slugs: ['opt-in-a-repo', 'plan-a-new-project', 'understand-an-existing-project'] },
  { id: 'make-a-change', title: 'Make a change',
    description: 'Define the behavior, review the artifacts, and choose attended or autonomous work.',
    slugs: ['first-feature', 'feature-lane', 'review-artifacts', 'autonomous-sprints'] },
  { id: 'review-and-ship', title: 'Review and ship',
    description: 'Distinguish findings, decisions, commits, pull requests and publication.',
    slugs: ['review-and-ship', 'adding-a-dependency', 'recording-adrs', 'releasing-a-version'] },
  { id: 'operate-and-recover', title: 'Operate and recover',
    description: 'Read the current state before resuming, repairing or removing anything.',
    slugs: ['return-to-a-project', 'resume-and-recover', 'troubleshooting', 'overriding-a-gate', 'uninstalling', 'the-statusline'] },
  { id: 'practice-and-advanced-tooling', title: 'Practice and advanced tooling',
    description: 'Use separate tooling only when its boundary fits your task.',
    slugs: ['ca-sandbox'] },
] as const;

export type GuidePage = {
  id: string;
  data: { title: string; description?: string; journey?: { level: string; time: string; outcome: string } };
};
export type GuideEntry = {
  id: string; category: string; href: string; title: string; description: string;
  outcome: string; level: string; time: string; searchText: string;
};

/** Join validated content-collection entries to reader order, failing on inventory drift. */
export function buildGuideDirectory(pages: readonly GuidePage[]) {
  const byId = new Map<string, GuidePage>();
  const expected = new Set<string>(guideGroups.flatMap(group => group.slugs.map(slug => `guides/${slug}`)));
  for (const page of pages) {
    if (!page.id.startsWith('guides/') || page.id === 'guides/index') continue;
    if (!expected.has(page.id)) throw new Error(`Unclassified guide: ${page.id}`);
    if (byId.has(page.id)) throw new Error(`Duplicate guide: ${page.id}`);
    byId.set(page.id, page);
  }
  return guideGroups.map(group => ({
    id: group.id, title: group.title, description: group.description,
    guides: group.slugs.map((slug): GuideEntry => {
      const id = `guides/${slug}`;
      const page = byId.get(id);
      if (!page) throw new Error(`Missing guide: ${id}`);
      const { title, description, journey } = page.data;
      if (![title, description, journey?.outcome, journey?.level, journey?.time]
        .every(value => typeof value === 'string' && value.trim().length > 0)) {
        throw new Error(`Incomplete guide metadata: ${id}`);
      }
      return { id, category: group.id, href: `/${id}/`, title, description: description!,
        outcome: journey!.outcome, level: journey!.level, time: journey!.time,
        searchText: `${title} ${description} ${journey!.outcome} ${group.title}` };
    }),
  }));
}
