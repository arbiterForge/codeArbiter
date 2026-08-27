import { execFileSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = fileURLToPath(new URL("..", import.meta.url));
const outputRoot = join(siteRoot, ".academy-non-root-dist");
const npmCli = process.env.npm_execpath;

if (!npmCli) throw new Error("npm_execpath is required to run the Academy non-root build test");

const expectedLessonLinks = [
  ["F01-fork-clone-doctor", "/docs/academy/f01-fork-clone-doctor/"],
  ["F02-orient-to-state", "/docs/academy/f02-orient-to-state/"],
  ["F03-work-the-board", "/docs/academy/f03-work-the-board/"],
  ["F04-fix-with-evidence", "/docs/academy/f04-fix-with-evidence/"],
  ["P01-feature-through-plan", "/docs/academy/p01-feature-through-plan/"],
  ["P02-commit-review-pr", "/docs/academy/p02-commit-review-pr/"],
  ["P03-record-an-adr", "/docs/academy/p03-record-an-adr/"],
  ["P04-review-a-dependency", "/docs/academy/p04-review-a-dependency/"],
  ["P05-checkpoint-remediation", "/docs/academy/p05-checkpoint-remediation/"],
  ["P06-context-drift-recovery", "/docs/academy/p06-context-drift-recovery/"],
  ["P07-threat-model", "/docs/academy/p07-threat-model/"],
  ["P08-repository-hygiene", "/docs/academy/p08-repository-hygiene/"],
  ["U01-autonomous-sprint", "/docs/academy/u01-autonomous-sprint/"],
  ["U02-override-audit-metrics", "/docs/academy/u02-override-audit-metrics/"],
  ["U03-refactor-chore-release", "/docs/academy/u03-refactor-chore-release/"],
  ["U04-initialize-projects", "/docs/academy/u04-initialize-projects/"],
  ["U05-debug-spike-conflict", "/docs/academy/u05-debug-spike-conflict/"],
  ["U06-preview-and-advanced-surfaces", "/docs/academy/u06-preview-and-advanced-surfaces/"],
  ["U07-capstone", "/docs/academy/u07-capstone/"],
];

try {
  execFileSync(
    process.execPath,
    [npmCli, "run", "build", "--", "--config", "test/fixtures/non-root-astro.config.mjs"],
    { cwd: siteRoot, stdio: "pipe" },
  );

  const academyHtml = readFileSync(join(outputRoot, "academy", "index.html"), "utf8");
  const inventoryLinks = [...academyHtml.matchAll(
    /data-academy-lesson="([^"]+)"[\s\S]*?<h4><a href="([^"]+)"/g,
  )].map((match) => [match[1], match[2]]);
  const startHref = academyHtml.match(/academy-overview__start-link" href="([^"]+)"/)?.[1];

  if (JSON.stringify(inventoryLinks) !== JSON.stringify(expectedLessonLinks)) {
    throw new Error(
      `Academy inventory links did not match the canonical public lesson mapping:\n` +
      `expected ${JSON.stringify(expectedLessonLinks)}\n` +
      `received ${JSON.stringify(inventoryLinks)}`,
    );
  }
  const [firstLessonId, firstLessonHref] = expectedLessonLinks[0];
  if (startHref !== firstLessonHref) {
    throw new Error(
      `expected the Academy start link for ${firstLessonId} to be ${firstLessonHref}, ` +
      `found ${startHref ?? "none"}`,
    );
  }

  process.stdout.write("Academy non-root base build: 19 lesson links remain beneath /docs/academy/.\n");
} finally {
  rmSync(outputRoot, { force: true, recursive: true });
}
