import { slugify } from "./slugify";

/**
 * Assign collision-free slugs to a list of names, preserving input order.
 *
 * Each name is slugified via {@link slugify}. When a slug repeats, later
 * occurrences get a numeric suffix (`-2`, `-3`, ...) in order of appearance.
 * The returned array has the same length and order as the input.
 */
export function assignSlugs(names: string[]): string[] {
  const counts = new Map<string, number>();
  const result: string[] = [];

  for (const name of names) {
    const base = slugify(name);
    const count = counts.get(base) ?? 0;
    if (count === 0) {
      result.push(base);
      counts.set(base, 1);
    } else {
      const newCount = count + 1;
      result.push(`${base}-${newCount}`);
      counts.set(base, newCount);
    }
  }

  return result;
}
