/** link-audit.ts — thin CLI over link-audit/lib.ts's pure functions.
 *
 * Runs the post-build dangling-link + base-path-safety gate against
 * site/dist/ and exits non-zero on any failure. See link-audit/lib.ts for
 * the resolution rules and rationale.
 *
 * Usage: tsx scripts/link-audit.ts [distDir]
 * `distDir` defaults to site/dist; it exists so the CLI's exit-code behavior
 * is testable against fixture dist trees.
 */
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { auditDist, missingRequiredAssets, BASE } from "./link-audit/lib";

const DEFAULT_DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");

function main(): void {
  const arg = process.argv[2];
  const dist = arg ? resolve(arg) : DEFAULT_DIST;

  if (!existsSync(dist)) {
    console.error(`link-audit: dist not found at ${dist}. Run \`npm run build\` first.`);
    process.exit(1);
  }

  const { failures, checked, pageCount } = auditDist(dist, BASE);
  const requiredAssets = missingRequiredAssets(dist);

  if (failures.length > 0 || requiredAssets.length > 0) {
    if (failures.length > 0) {
      console.error(`link-audit: ${failures.length} link failure(s):`);
      for (const f of failures) console.error(`  ${f.message}`);
    }
    for (const a of requiredAssets) console.error(`link-audit: required asset missing: ${a}`);
    process.exit(1);
  }

  console.log(
    `link-audit: OK — ${checked} internal link(s) across ${pageCount} page(s) resolve; favicon + hashed logo present.`,
  );
}

main();
