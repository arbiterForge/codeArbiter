/** Bounded, literal matching only. No expression evaluation, network or persistence. */
export function normalizeGuideQuery(query: string): string {
  return query.normalize('NFKC').toLowerCase().trim().replace(/\s+/g, ' ').slice(0, 160);
}

/** Both the task group and every entered term must match this published guide. */
export function guideMatches(guide: { category: string; searchText: string }, query: string, category: string): boolean {
  if (category !== 'all' && category !== guide.category) return false;
  const haystack = guide.searchText.normalize('NFKC').toLowerCase();
  const normalized = normalizeGuideQuery(query);
  return normalized === '' || normalized.split(' ').every(term => haystack.includes(term));
}
