/** cli.test.ts — end-to-end exit-code coverage for scripts/link-audit.ts.
 *
 * lib.test.ts proves the pure audit functions; this unit proves the CLI
 * actually turns those results into the right process exit code. Without it a
 * regression in the CLI's success/failure branch could let a red audit exit 0.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = join(HERE, "..", "..");
const CLI = join(SITE_ROOT, "scripts", "link-audit.ts");
const TSX_CLI = join(SITE_ROOT, "node_modules", "tsx", "dist", "cli.mjs");

const dists: string[] = [];

afterAll(() => {
  for (const d of dists) rmSync(d, { recursive: true, force: true });
});

/** Build a throwaway dist/ with the pinned chrome assets plus `pages`. */
function makeDist(pages: Record<string, string>): string {
  const dist = mkdtempSync(join(tmpdir(), "link-audit-cli-"));
  dists.push(dist);
  writeFileSync(join(dist, "favicon.svg"), "<svg/>");
  mkdirSync(join(dist, "_astro"), { recursive: true });
  writeFileSync(join(dist, "_astro", "logo.abc123.svg"), "<svg/>");
  for (const [rel, contents] of Object.entries(pages)) {
    const full = join(dist, ...rel.split("/"));
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, contents);
  }
  return dist;
}

function runCli(distArg: string): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync(process.execPath, [TSX_CLI, CLI, distArg], {
    encoding: "utf8",
    cwd: SITE_ROOT,
  });
  return { status: result.status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

describe("link-audit CLI", () => {
  it("exits non-zero when the dist directory does not exist", () => {
    const missing = join(tmpdir(), "link-audit-cli-does-not-exist-xyz");
    const { status, stderr } = runCli(missing);
    expect(status).toBe(1);
    expect(stderr).toContain("dist not found");
  }, 60_000);

  it("exits non-zero on a zero-page dist even with both required assets present", () => {
    const dist = makeDist({});
    const { status, stderr } = runCli(dist);
    expect(status).toBe(1);
    expect(stderr).toMatch(/zero HTML pages/i);
  }, 60_000);

  it("exits zero on a minimal complete dist", () => {
    const dist = makeDist({ "index.html": `<a href="/codeArbiter/favicon.svg">icon</a>` });
    const { status, stdout } = runCli(dist);
    expect(status).toBe(0);
    expect(stdout).toContain("link-audit: OK");
  }, 60_000);

  it("exits non-zero on a dangling internal link", () => {
    const dist = makeDist({ "index.html": `<a href="/codeArbiter/missing/">dangling</a>` });
    const { status, stderr } = runCli(dist);
    expect(status).toBe(1);
    expect(stderr).toContain("link failure");
  }, 60_000);
});
