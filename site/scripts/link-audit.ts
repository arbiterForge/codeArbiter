/** link-audit.ts — thin CLI over link-audit/lib.ts's pure functions.
 *
 * Runs the post-build dangling-link + base-path-safety gate against
 * site/dist/ and exits non-zero on any failure. See link-audit/lib.ts for
 * the resolution rules and rationale.
 */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { auditDist, missingRequiredAssets, BASE } from "./link-audit/lib";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");

function main(): void {
  if (!existsSync(DIST)) {
    console.error(`link-audit: dist not found at ${DIST}. Run \`npm run build\` first.`);
    process.exit(1);
  }

  const { failures, checked, pageCount } = auditDist(DIST, BASE);
  const requiredAssets = missingRequiredAssets(DIST);

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
