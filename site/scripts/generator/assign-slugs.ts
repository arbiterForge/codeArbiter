import { slugify } from "./slugify";

/**
 * Assign collision-free slugs to a list of names, preserving input order.
 *
 * Each name is slugified via {@link slugify}. When a slug is already taken,
 * the occurrence gets the lowest numeric suffix (`-2`, `-3`, ...) above the
 * last one tried for that base that is not itself already emitted.
 *
 * Every EMITTED slug is reserved, not just base names (HW-24, GEN-B01): the
 * earlier per-base counter emitted `foo-2` twice for `foo, foo, foo-2`. The
 * result is deterministic for a stable input order, and inputs without
 * suffix collisions keep exactly the slugs the per-base counter produced.
 */
export function assignSlugs(names: string[]): string[] {
  const used = new Set<string>();
  const next = new Map<string, number>();
  const result: string[] = [];

  for (const name of names) {
    const base = slugify(name);
    let slug = base;
    if (used.has(slug)) {
      let n = next.get(base) ?? 2;
      while (used.has(`${base}-${n}`)) n += 1;
      slug = `${base}-${n}`;
      next.set(base, n + 1);
    }
    used.add(slug);
    result.push(slug);
  }

  return result;
}
