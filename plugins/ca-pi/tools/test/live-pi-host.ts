/**
 * live-pi-host.ts - shared discovery of the INSTALLED Pi runtime for fixtures
 * that must run against the real host rather than a hand-written double.
 *
 * Discovery walks PATH only. It never consults npm, a user config, or an
 * environment override, so a fixture cannot be pointed at a runtime other than
 * the one this cell actually installed.
 */
import { constants } from "node:fs";
import { access, readFile, realpath } from "node:fs/promises";
import { delimiter, dirname, parse, resolve } from "node:path";

export async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export async function findPiPackageRoot(): Promise<string> {
  const pathEntries = (process.env.PATH ?? "").split(delimiter).filter(Boolean);
  const executableNames = process.platform === "win32" ? ["pi.cmd", "pi.exe", "pi.ps1", "pi"] : ["pi"];
  for (const entry of pathEntries) {
    let executable: string | undefined;
    for (const name of executableNames) {
      const candidate = resolve(entry, name);
      try {
        await access(candidate, constants.X_OK);
        executable = candidate;
        break;
      } catch {
        // Continue to the next platform-native executable spelling.
      }
    }
    if (executable === undefined) continue;
    let cursor = dirname(await realpath(executable));
    for (let depth = 0; depth < 8; depth += 1) {
      const candidate = resolve(cursor, "package.json");
      if (await exists(candidate)) {
        const manifest = JSON.parse(await readFile(candidate, "utf8")) as { name?: string };
        if (manifest.name === "@earendil-works/pi-coding-agent") return cursor;
      }
      const parent = dirname(cursor);
      if (parent === cursor || cursor === parse(cursor).root) break;
      cursor = parent;
    }
    const adjacent = resolve(entry, "node_modules", "@earendil-works", "pi-coding-agent");
    const manifestPath = resolve(adjacent, "package.json");
    if (!await exists(resolve(adjacent, "dist", "index.js")) || !await exists(manifestPath)) continue;
    const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as { name?: string };
    if (manifest.name === "@earendil-works/pi-coding-agent") return await realpath(adjacent);
  }
  throw new Error("live Pi package root was not discoverable from PATH without npm/user config");
}
