/** run.ts - `npm run capture`: regenerate every committed capture from the current tools.
 *
 * Runs each target in a fresh temporary fixture (no model call, no network, no
 * write outside the fixture and the capture assets), rewrites a capture file
 * only when its bytes changed, removes captures whose target is gone, and then
 * refreshes the landing hook proof, which keeps its own binding. A second run
 * with nothing changed leaves the working tree untouched.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { captureHookProof } from "../capture-hook-proof";
import { REPO_ROOT, runCapture } from "./harness";
import { CAPTURE_TARGETS } from "./targets";
import { assertCapturesFresh } from "./verify";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const CAPTURES_DIR = join(siteRoot, "src", "assets", "captures");

mkdirSync(CAPTURES_DIR, { recursive: true });

const wanted = new Set(CAPTURE_TARGETS.map((target) => `${target.id}.json`));
for (const name of readdirSync(CAPTURES_DIR)) {
  if (name.endsWith(".json") && !wanted.has(name)) {
    rmSync(join(CAPTURES_DIR, name));
    console.log(`Removed capture with no target: ${name}`);
  }
}

for (const target of CAPTURE_TARGETS) {
  const record = runCapture(target);
  const path = join(CAPTURES_DIR, `${target.id}.json`);
  const content = `${JSON.stringify(record, null, 2)}\n`;
  const changed = !existsSync(path) || readFileSync(path, "utf8") !== content;
  if (changed) writeFileSync(path, content, "utf8");
  console.log(`${changed ? "Captured" : "Unchanged"} ${target.id}: ${record.sources.length} sources from ${target.tool}`);
}

assertCapturesFresh(REPO_ROOT, CAPTURES_DIR);
await captureHookProof();
