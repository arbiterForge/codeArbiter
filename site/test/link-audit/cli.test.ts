/** cli.test.ts — end-to-end exit-code coverage for scripts/link-audit.ts.
 *
 * lib.test.ts proves the pure audit functions; this unit proves the CLI
 * actually turns those results into the right process exit code. Without it a
 * regression in the CLI's success/failure branch could let a red audit exit 0.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = join(HERE, "..", "..");
const CLI = join(SITE_ROOT, "scripts", "link-audit.ts");

/** The production default the CLI falls back to when given no argument. */
const DEFAULT_DIST = join(SITE_ROOT, "dist");

// Resolve tsx's executable from its own `bin` field rather than hardcoding
// `node_modules/tsx/dist/cli.mjs`. tsx is ranged `^4.19.2`, so a minor bump
// that relocates or renames that entrypoint would otherwise break every case
// in this file.
const require_ = createRequire(import.meta.url);
const TSX_PKG_JSON = require_.resolve("tsx/package.json");
const TSX_BIN = require_("tsx/package.json").bin;
const TSX_CLI = resolve(
  dirname(TSX_PKG_JSON),
  typeof TSX_BIN === "string" ? TSX_BIN : TSX_BIN.tsx,
);

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
  it("exits non-zero and reports the given dist when that directory does not exist", () => {
    const missing = join(tmpdir(), "link-audit-cli-does-not-exist-xyz");
    const { status, stderr } = runCli(missing);

    expect(status).toBe(1);
    // Asserting only "dist not found" would pass vacuously against a CLI that
    // ignores argv: it would report its own default site/dist and exit 1 for
    // its own reason. Pinning the *argument* path — and pinning that the
    // default is NOT the path reported — is what exercises argv handling.
    expect(stderr).toContain(`dist not found at ${missing}`);
    expect(stderr).not.toContain(DEFAULT_DIST);
  }, 60_000);

  it("exits non-zero on a zero-page dist even with both required assets present", () => {
    const dist = makeDist({});
    const { status, stderr } = runCli(dist);
    expect(status).toBe(1);
    expect(stderr).toMatch(/zero HTML pages/i);
  }, 60_000);

  it("exits zero on a minimal complete dist", () => {
    const dist = makeDist({ "index.html": `<a href="/favicon.svg">icon</a>` });
    const { status, stdout } = runCli(dist);
    expect(status).toBe(0);
    expect(stdout).toContain("link-audit: OK");
  }, 60_000);

  it("exits non-zero on a dangling internal link", () => {
    const dist = makeDist({ "index.html": `<a href="/missing/">dangling</a>` });
    const { status, stderr } = runCli(dist);
    expect(status).toBe(1);
    expect(stderr).toContain("link failure");
  }, 60_000);
});
