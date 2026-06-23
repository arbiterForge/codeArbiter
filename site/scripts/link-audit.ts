/** link-audit.ts — post-build dangling-link gate (docs-site-polish AC-2 / AC-4).
 *
 * Walks every built HTML page under site/dist/ and extracts the targets of
 * `<a href>` and `<img src>`. For each INTERNAL target it resolves the URL to a
 * file on disk under dist/ and asserts that file exists. Any dangling internal
 * link makes the process exit non-zero, so a broken slug fails CI before deploy.
 *
 * Resolution rules (base path is /codeArbiter, see astro.config.mjs):
 *   - Root-absolute under the base  "/codeArbiter/x/"        -> dist/x/index.html
 *   - Root-absolute asset           "/codeArbiter/foo.svg"   -> dist/foo.svg
 *   - Page-relative directory link  "../concepts/"           -> dist/concepts/index.html
 *   - Page-relative asset           "diagrams/lane-flow.svg" -> dist/diagrams/lane-flow.svg
 *
 * Skipped (not internal-to-dist): external URLs (http:, https:, mailto:, etc.),
 * protocol-relative (//host), pure fragments (#anchor), data: URIs, and
 * root-absolute links that fall OUTSIDE the base prefix (not ours to resolve).
 *
 * Also asserts the always-present chrome assets exist: dist/favicon.svg and a
 * hashed dist/_astro/logo.*.svg.
 *
 * Uses Node built-ins + a small regex HTML scan only — no added dependency.
 */
import { readdirSync, statSync, readFileSync, existsSync } from "node:fs";
import { join, posix, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const BASE = "/codeArbiter"; // must match astro.config.mjs `base`

/** Recursively collect every *.html file under dir. */
function htmlFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...htmlFiles(full));
    else if (entry.endsWith(".html")) out.push(full);
  }
  return out;
}

/** Extract href/src attribute values from one HTML string. */
function extractTargets(html: string): string[] {
  const targets: string[] = [];
  const re = /\b(?:href|src)\s*=\s*"([^"]*)"/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) targets.push(m[1]);
  return targets;
}

/** True for targets we do not resolve against the local dist tree. */
function isExternalOrSkippable(target: string): boolean {
  if (target === "") return true;
  if (target.startsWith("#")) return true; // pure fragment
  if (target.startsWith("//")) return true; // protocol-relative
  if (/^[a-z][a-z0-9+.-]*:/i.test(target)) return true; // has a scheme (http:, mailto:, data:, ...)
  return false;
}

/** Strip a query string and/or fragment from a URL path. */
function stripQueryHash(target: string): string {
  return target.split("#")[0].split("?")[0];
}

/**
 * Map an internal URL path to the file it must resolve to under dist/.
 * `pageUrlDir` is the page's own URL directory (posix), e.g. "/codeArbiter/overview".
 * Returns the absolute dist file path, or null if the target is out of scope.
 */
function resolveToDistFile(target: string, pageUrlDir: string): string | null {
  let urlPath = stripQueryHash(target);
  if (urlPath === "") return null;

  let absUrlPath: string;
  if (urlPath.startsWith("/")) {
    // Root-absolute. Only ours if it lives under the base prefix.
    if (urlPath !== BASE && !urlPath.startsWith(`${BASE}/`)) return null;
    absUrlPath = urlPath.slice(BASE.length) || "/";
  } else {
    // Page-relative: resolve against the page's URL directory, then drop base.
    const joined = posix.normalize(posix.join(pageUrlDir, urlPath));
    if (joined !== BASE && !joined.startsWith(`${BASE}/`)) return null;
    absUrlPath = joined.slice(BASE.length) || "/";
  }

  // absUrlPath now starts at the site root (base stripped). Trailing slash or a
  // bare directory means an index.html; otherwise it is a file path verbatim.
  let rel: string;
  if (absUrlPath.endsWith("/")) {
    rel = `${absUrlPath}index.html`;
  } else if (posix.basename(absUrlPath).includes(".")) {
    rel = absUrlPath; // looks like a file (has an extension)
  } else {
    rel = `${absUrlPath}/index.html`; // extensionless route -> directory index
  }

  return join(DIST, ...rel.split("/").filter(Boolean));
}

function main(): void {
  if (!existsSync(DIST)) {
    console.error(`link-audit: dist not found at ${DIST}. Run \`npm run build\` first.`);
    process.exit(1);
  }

  const pages = htmlFiles(DIST);
  const dangling: string[] = [];
  let checked = 0;

  for (const page of pages) {
    // The page's URL directory, base-prefixed, in posix form.
    const relFromDist = relative(DIST, page).split(sep).join("/");
    const pageUrlDir = posix.dirname(`${BASE}/${relFromDist}`);
    const html = readFileSync(page, "utf8");

    for (const target of extractTargets(html)) {
      if (isExternalOrSkippable(target)) continue;
      const distFile = resolveToDistFile(target, pageUrlDir);
      if (distFile === null) continue; // out of scope (e.g. a non-base absolute path)
      checked++;
      if (!existsSync(distFile)) {
        dangling.push(`${relFromDist}  ->  ${target}  (missing ${relative(DIST, distFile).split(sep).join("/")})`);
      }
    }
  }

  // Chrome assets the spec pins (AC-4).
  const requiredAssets: string[] = [];
  if (!existsSync(join(DIST, "favicon.svg"))) requiredAssets.push("dist/favicon.svg");
  const astroDir = join(DIST, "_astro");
  const hasLogo =
    existsSync(astroDir) &&
    readdirSync(astroDir).some((f) => /^logo\..*\.svg$/.test(f));
  if (!hasLogo) requiredAssets.push("dist/_astro/logo.*.svg");

  if (dangling.length > 0 || requiredAssets.length > 0) {
    if (dangling.length > 0) {
      console.error(`link-audit: ${dangling.length} dangling internal link(s):`);
      for (const d of dangling) console.error(`  ${d}`);
    }
    for (const a of requiredAssets) console.error(`link-audit: required asset missing: ${a}`);
    process.exit(1);
  }

  console.log(
    `link-audit: OK — ${checked} internal link(s) across ${pages.length} page(s) resolve; favicon + hashed logo present.`,
  );
}

main();
