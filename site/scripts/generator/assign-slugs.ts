import { slugify } from "./slugify";

/**
 * Assign collision-free slugs to a list of names, preserving input order.
 *
 * Each name is slugified via {@link slugify}. When a slug repeats, later
 * occurrences get a numeric suffix (`-2`, `-3`, ...) in order of appearance.
 * The returned array has the same length and order as the input.
 */
export function assignSlugs(names: string[]): string[] {
  throw new Error("not implemented");
}
