/** Site-only conceptual order. Page frontmatter owns titles and descriptions. */
export const conceptGroups = [
  { id: 'work-and-records', title: 'Work and its records', question: 'How does an intention become controlled work?', items: [
    { slug: 'concepts/gated-lanes', question: 'Why does the route depend on the kind of change?' },
    { slug: 'concepts/artifacts', question: 'Which record answers which question?' },
    { slug: 'concepts/test-first', question: 'What makes a passing test meaningful evidence?' },
  ] },
  { id: 'decisions-and-authority', title: 'Decisions and authority', question: 'Who chooses, and what does that choice authorize?', items: [
    { slug: 'concepts/smarts', question: 'How are alternatives compared without hiding uncertainty?' },
    { slug: 'concepts/adrs', question: 'How does an accepted choice differ from delivered behavior?' },
  ] },
  { id: 'repository-context', title: 'Repository context', question: 'How do relevant rules reach the work?', items: [
    { slug: 'concepts/provenance-drift', question: 'What happens when source and derived knowledge disagree?' },
    { slug: 'concepts/jit-context-injection', question: 'Why is only some context loaded for a file read?' },
  ] },
  { id: 'roles-and-review', title: 'Roles and review', question: 'Who does the work, and who challenges it?', items: [
    { slug: 'concepts/persona-and-context', question: 'Why separate coordination, authorship and review?' },
    { slug: 'concepts/checkpoints', question: 'What does a repository review find outside one change?' },
  ] },
  { id: 'evidence-and-limits', title: 'Evidence and limits', question: 'What can the record establish afterward?', items: [
    { slug: 'concepts/auditability', question: 'How is a window of recorded work assembled?' },
    { slug: 'enforcement', question: 'Which protections are mechanical, advisory or host-specific?' },
  ] },
] as const;
export const conceptBackground = [
  { slug: 'concepts/persona-research-basis', title: 'Historical persona research rationale' },
  { slug: 'concepts/hardening-history', title: 'Historical hardening lessons' },
] as const;

type Page = { id: string; data: { title: string; description?: string } };
/** Resolve every destination against real content rather than copying an independent catalog. */
export function buildConceptDirectory(pages: readonly Page[]) {
  const entries = new Map(pages.map(page => [page.id, page]));
  const seen = new Set<string>();
  return conceptGroups.map(group => ({ ...group, items: group.items.map(item => {
    if (seen.has(item.slug)) throw new Error(`Duplicate concept: ${item.slug}`);
    seen.add(item.slug);
    const page = entries.get(item.slug);
    if (!page?.data.title.trim() || !page.data.description?.trim()) throw new Error(`Missing concept metadata: ${item.slug}`);
    return { ...item, title: page.data.title, description: page.data.description };
  }) }));
}
