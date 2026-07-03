/** link-audit/lib.ts — pure functions backing the post-build dangling-link
 * gate (docs-site-polish AC-2 / AC-4; hardened for base-path safety).
 *
 * Walks every built HTML page under site/dist/ and extracts the targets of
 * `<a href>` and `<img src>`. For each target that looks internal (no URL
 * scheme, not protocol-relative, not a pure fragment) it classifies the
 * target and resolves it to a file on disk under dist/, asserting that file
 * exists.
 *
 * Resolution rules (base path is /codeArbiter, see astro.config.mjs):
 *   - Root-absolute under the base  "/codeArbiter/x/"        -> dist/x/index.html
 *   - Root-absolute asset           "/codeArbiter/foo.svg"   -> dist/foo.svg
 *   - Page-relative directory link  "../concepts/"           -> dist/concepts/index.html
 *   - Page-relative asset           "diagrams/lane-flow.svg" -> dist/diagrams/lane-flow.svg
 *
 * Skipped entirely (not internal-to-dist): external URLs (http:, https:,
 * mailto:, etc.), protocol-relative (//host), pure fragments (#anchor), and
 * data: URIs.
 *
 * FAILED, not skipped: a root-absolute target that does not fall under the
 * base prefix, or a page-relative target that normalizes outside the base.
 * Before the local rehype-base-links build step existed, root-absolute
 * markdown links like `](/overview)` silently rendered unprefixed and 404'd
 * in production — this gate used to skip them as "out of scope" instead of
 * catching that. They are now recorded as failures alongside dangling links.
 *
 * Uses Node built-ins + a small regex HTML scan only — no added dependency.
 */
import { readdirSync, statSync, readFileSync, existsSync } from "node:fs";
import { join, posix, relative, sep } from "node:path";

export const BASE = "/codeArbiter"; // must match astro.config.mjs `base`

/** Recursively collect every *.html file under dir. */
export function htmlFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...htmlFiles(full));
    else if (entry.endsWith(".html")) out.push(full);
  }
  return out;
}

/** Extract href/src attribute values from one HTML string. */
export function extractTargets(html: string): string[] {
  const targets: string[] = [];
  const re = /\b(?:href|src)\s*=\s*"([^"]*)"/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) targets.push(m[1]);
  return targets;
}

/** True for targets we do not evaluate at all: empty, pure fragment,
 * protocol-relative, or carrying a URL scheme (http:, mailto:, data:, ...). */
export function isExternalOrSkippable(target: string): boolean {
  if (target === "") return true;
  if (target.startsWith("#")) return true; // pure fragment
  if (target.startsWith("//")) return true; // protocol-relative
  if (/^[a-z][a-z0-9+.-]*:/i.test(target)) return true; // has a scheme (http:, mailto:, data:, ...)
  return false;
}

/** Strip a query string and/or fragment from a URL path. */
export function stripQueryHash(target: string): string {
  return target.split("#")[0].split("?")[0];
}

export type Resolution =
  | { kind: "resolved"; distFile: string }
  | { kind: "outside-base"; normalizedPath: string };

/**
 * Classify + resolve an internal-looking URL path against the base prefix
 * and, if in scope, map it to the file it must resolve to under dist/.
 *
 * `pageUrlDir` is the page's own URL directory (posix), e.g.
 * "/codeArbiter/overview". `base` defaults to the site's configured BASE.
 */
export function resolveToDistFile(
  target: string,
  pageUrlDir: string,
  distRoot: string,
  base: string = BASE,
): Resolution | null {
  let urlPath = stripQueryHash(target);
  if (urlPath === "") return null;

  let absUrlPath: string;
  let normalizedPath: string;
  if (urlPath.startsWith("/")) {
    // Root-absolute.
    normalizedPath = urlPath;
    if (normalizedPath !== base && !normalizedPath.startsWith(`${base}/`)) {
      return { kind: "outside-base", normalizedPath };
    }
    absUrlPath = normalizedPath.slice(base.length) || "/";
  } else {
    // Page-relative: resolve against the page's URL directory.
    normalizedPath = posix.normalize(posix.join(pageUrlDir, urlPath));
    if (normalizedPath !== base && !normalizedPath.startsWith(`${base}/`)) {
      return { kind: "outside-base", normalizedPath };
    }
    absUrlPath = normalizedPath.slice(base.length) || "/";
  }

  // absUrlPath now starts at the site root (base stripped). Trailing slash or
  // a bare directory means an index.html; otherwise it is a file path
  // verbatim.
  let rel: string;
  if (absUrlPath.endsWith("/")) {
    rel = `${absUrlPath}index.html`;
  } else if (posix.basename(absUrlPath).includes(".")) {
    rel = absUrlPath; // looks like a file (has an extension)
  } else {
    rel = `${absUrlPath}/index.html`; // extensionless route -> directory index
  }

  return { kind: "resolved", distFile: join(distRoot, ...rel.split("/").filter(Boolean)) };
}

export interface AuditFailure {
  message: string;
}

export interface AuditResult {
  failures: AuditFailure[];
  checked: number;
  pageCount: number;
}

/** Run the full dangling-link + base-safety audit against a built dist/ dir. */
export function auditDist(distRoot: string, base: string = BASE): AuditResult {
  const pages = htmlFiles(distRoot);
  const failures: AuditFailure[] = [];
  let checked = 0;

  for (const page of pages) {
    // The page's URL directory, base-prefixed, in posix form.
    const relFromDist = relative(distRoot, page).split(sep).join("/");
    const pageUrlDir = posix.dirname(`${base}/${relFromDist}`);
    const html = readFileSync(page, "utf8");

    for (const target of extractTargets(html)) {
      if (isExternalOrSkippable(target)) continue;
      const resolution = resolveToDistFile(target, pageUrlDir, distRoot, base);
      if (resolution === null) continue; // empty target, nothing to check
      checked++;

      if (resolution.kind === "outside-base") {
        failures.push({
          message: `${relFromDist}  ->  ${target}  (outside base path: resolves to ${resolution.normalizedPath}, not under ${base})`,
        });
        continue;
      }

      if (!existsSync(resolution.distFile)) {
        failures.push({
          message: `${relFromDist}  ->  ${target}  (missing ${relative(distRoot, resolution.distFile).split(sep).join("/")})`,
        });
      }
    }
  }

  return { failures, checked, pageCount: pages.length };
}

/** Chrome assets the spec pins (AC-4): favicon.svg and a hashed logo asset. */
export function missingRequiredAssets(distRoot: string): string[] {
  const missing: string[] = [];
  if (!existsSync(join(distRoot, "favicon.svg"))) missing.push("dist/favicon.svg");
  const astroDir = join(distRoot, "_astro");
  const hasLogo =
    existsSync(astroDir) && readdirSync(astroDir).some((f) => /^logo\..*\.svg$/.test(f));
  if (!hasLogo) missing.push("dist/_astro/logo.*.svg");
  return missing;
}
