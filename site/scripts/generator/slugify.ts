/**
 * Produce a stable, URL-safe kebab-case slug.
 *
 * - Lowercases the input.
 * - Replaces every run of non-alphanumeric characters with a single `-`.
 * - Strips leading and trailing `-`.
 * - Idempotent: `slugify(slugify(x)) === slugify(x)`.
 */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
