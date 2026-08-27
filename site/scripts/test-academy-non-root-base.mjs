import { execFileSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = fileURLToPath(new URL("..", import.meta.url));
const outputRoot = join(siteRoot, ".academy-non-root-dist");
const npmCli = process.env.npm_execpath;

if (!npmCli) throw new Error("npm_execpath is required to run the Academy non-root build test");

try {
  execFileSync(
    process.execPath,
    [npmCli, "run", "build", "--", "--config", "test/fixtures/non-root-astro.config.mjs"],
    { cwd: siteRoot, stdio: "pipe" },
  );

  const academyHtml = readFileSync(join(outputRoot, "academy", "index.html"), "utf8");
  const inventoryHrefs = [...academyHtml.matchAll(
    /data-academy-lesson="[^"]+"[\s\S]*?<h4><a href="([^"]+)"/g,
  )].map((match) => match[1]);
  const startHref = academyHtml.match(/academy-overview__start-link" href="([^"]+)"/)?.[1];

  if (inventoryHrefs.length !== 19) {
    throw new Error(`expected 19 Academy inventory links, found ${inventoryHrefs.length}`);
  }
  if (startHref !== "/docs/academy/f01-fork-clone-doctor/") {
    throw new Error(`expected the Academy start link beneath /docs/, found ${startHref ?? "none"}`);
  }
  const rootHref = inventoryHrefs.find((href) => !href.startsWith("/docs/academy/"));
  if (rootHref) {
    throw new Error(`expected every Academy inventory link beneath /docs/, found ${rootHref}`);
  }

  process.stdout.write("Academy non-root base build: 20 lesson links remain beneath /docs/academy/.\n");
} finally {
  rmSync(outputRoot, { force: true, recursive: true });
}
