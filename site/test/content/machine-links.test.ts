/** machine-links.test.ts - every link into the machine page lands on a real part, zone or scenario.
 *
 * The link audit checks routes, not fragments. Command, skill, agent and hook-gate pages and the
 * orientation strip now link into /concepts/machine/ by fragment, so this scans the build that
 * `npm test` makes first and resolves each fragment against the machine page's own ids.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const dist = resolve(import.meta.dirname, "..", "..", "dist");
const machinePage = join(dist, "concepts", "machine", "index.html");

function pages(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === "pagefind" || entry.name === "workflow-atlas" ? [] : pages(path);
    return entry.name === "index.html" ? [path] : [];
  });
}

describe("links into the machine", () => {
  it.skipIf(!existsSync(machinePage))("resolve to an id on the machine page", () => {
    const ids = new Set([...readFileSync(machinePage, "utf8").matchAll(/\sid="([^"]+)"/g)].map(([, id]) => id));
    const links = pages(dist).flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(/href="[^"]*\/concepts\/machine\/#([^"]+)"/g)].map(([, fragment]) => ({ file, fragment })),
    );
    expect(links.length).toBeGreaterThan(100);
    const broken = links.filter(({ fragment }) => !ids.has(decodeURIComponent(fragment))).map(({ file, fragment }) => `${relative(dist, file)} -> #${fragment}`);
    expect([...new Set(broken)]).toEqual([]);
  });
});
