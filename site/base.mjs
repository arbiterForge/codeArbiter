/** base.mjs — the site's base path, single source of truth.
 *
 * Imported by astro.config.mjs (which sets Astro's `base` and feeds
 * rehypeBaseLinks), by scripts/link-audit/lib.ts, and by the tests that assert
 * base-dependent output. It lives in its own module so none of those has to
 * import the full Astro config just to learn one string.
 *
 * This file exists because the literal was previously copied into four places
 * — astro.config.mjs, link-audit/lib.ts, and three test files — each with a
 * comment saying it had to match the others. Moving the site to the
 * codearbiter.dev apex domain desynced all four at once: four test failures and
 * 19,940 link-audit failures from a one-line change.
 *
 * MUST be "" for an apex domain, never "/". rehypeBaseLinks prefixes every
 * root-absolute href/src with this value, so "/" would rewrite
 * "/diagrams/x.svg" into "//diagrams/x.svg" — a protocol-relative URL that
 * resolves against a different host and fails silently rather than 404-ing.
 * Empty string makes the prefixing a correct no-op. Consumers that need a real
 * path (Astro's own `base`) use `BASE || "/"`.
 *
 * For a project subpath the value is "/<repo>" with no trailing slash, e.g.
 * "/codeArbiter" when served from arbiterforge.github.io/codeArbiter/.
 */
export const BASE = "";
