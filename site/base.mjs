/** base.mjs — the site's base path, single source of truth.
 *
 * Imported by astro.config.mjs (which sets Astro's `base` and feeds
 * rehypeBaseLinks), by scripts/link-audit/lib.ts, and by the tests that assert
 * base-dependent output. It lives in its own module so none of those has to
 * import the full Astro config just to learn one string.
 *
 * This file exists because the literal was previously copied into six places —
 * astro.config.mjs, link-audit/lib.ts, and four test files — each with a comment
 * saying it had to match the others. Moving the site to the codearbiter.dev apex
 * domain desynced all six at once: four test failures and 19,940 link-audit
 * failures from a one-line change.
 *
 * For a project subpath the value is "/<repo>" with no trailing slash, e.g.
 * "/codeArbiter" when served from arbiterforge.github.io/codeArbiter/. For an
 * apex domain it is the empty string.
 */

/** The configured value, before validation. */
const RAW_BASE = "";

/** Reject any base that would corrupt links, loudly and at import time.
 *
 * The dangerous value is "/". rehypeBaseLinks prefixes every root-absolute
 * href/src with the base, so a base of "/" rewrites "/diagrams/x.svg" into
 * "//diagrams/x.svg" — a protocol-relative URL that resolves against a
 * DIFFERENT HOST. It does not 404. The build succeeds, the link audit passes
 * (the target still parses), and the page quietly fetches from somewhere else.
 * That failure mode is why this is a thrown error and not a comment: prose
 * cannot stop anyone, and "/" is the obvious thing to reach for when moving a
 * site to a domain root.
 *
 * Exported for the tests; callers should import BASE.
 *
 * @param {string} value
 * @returns {string} the validated base
 */
export function validateBase(value) {
  if (typeof value !== "string") {
    throw new TypeError(`site base must be a string, got ${typeof value}`);
  }
  // The apex-domain form. Makes rehypeBaseLinks a correct no-op, because a
  // root-absolute target already starts with `${BASE}/`.
  if (value === "") return value;
  if (!value.startsWith("/")) {
    throw new Error(
      `site base ${JSON.stringify(value)} must be "" or start with "/" ` +
        `(a base is a root-absolute path, e.g. "/codeArbiter")`,
    );
  }
  // Catches "/" as well as "/codeArbiter/". A trailing slash doubles the
  // separator when the base is prefixed onto a root-absolute target.
  if (value.endsWith("/")) {
    const hint =
      value === "/"
        ? ` Use "" for a domain root: a base of "/" turns "/diagrams/x.svg" into ` +
          `"//diagrams/x.svg", a protocol-relative URL pointing at another host.`
        : ` Drop the trailing slash.`;
    throw new Error(`site base ${JSON.stringify(value)} must not end with "/".${hint}`);
  }
  return value;
}

export const BASE = validateBase(RAW_BASE);
