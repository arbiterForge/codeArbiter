/** collect-lenses.ts — discovers the tribunal lens cards.
 *
 * The tribunal deep-audit lane ships one generic `tribunal-lens-reviewer`
 * agent plus one lens card per lens under
 * `skills/tribunal/references/lenses/<lens>.md`. The cards are the only
 * per-lens documentation, so the site publishes each one as a reference page
 * (see `render-lens-page.ts`). They are skill reference data, not a fourth
 * plugin source type, so they get their own collection pass instead of
 * joining `collect-sources.ts`'s command/skill/agent walk.
 */
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import type { LensCard } from "./types";

/**
 * Collect every lens card under `<rootDir>/skills/tribunal/references/lenses/`.
 *
 * Returns one entry per `.md` file, slug = file basename, sorted by slug for
 * stable output. A source tree without the lenses directory (e.g. a synthetic
 * test fixture) yields an empty array.
 */
export function collectLenses(rootDir: string): LensCard[] {
  const lensesDir = join(rootDir, "skills", "tribunal", "references", "lenses");
  if (!existsSync(lensesDir)) return [];

  return readdirSync(lensesDir)
    .filter((entry) => entry.endsWith(".md"))
    .map((entry) => ({
      slug: entry.replace(/\.md$/, ""),
      raw: readFileSync(join(lensesDir, entry), "utf-8"),
    }))
    .sort((a, b) => a.slug.localeCompare(b.slug));
}
