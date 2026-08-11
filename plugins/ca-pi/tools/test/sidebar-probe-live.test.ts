/**
 * sidebar-probe-live.test.ts — AC-7's live leg: the compositor's hook probe
 * exercised against the INSTALLED Pi runtime's own `@earendil-works/pi-tui`,
 * with no hand-written double for the Pi-owned parts. The hosted matrix runs
 * this cell at both promoted window versions (0.80.5 and 0.84.1), so a Pi
 * release that renames the screen classes, removes the undocumented
 * `doRender` method, or changes the text-metrics exports fails here before it
 * can strand the sidebar.
 *
 * The terminal leg (a configurable `columns` descriptor) is Node/tty-owned,
 * not Pi-owned, and headless CI has no TTY — so the terminal stays a minimal
 * fixture while the tui and metrics legs are the real host's.
 */
import { readFile, realpath } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, test } from "vitest";

import { probeSidebarSupport } from "../src/sidebar-compositor.ts";
import type { SidebarTuiPort } from "../src/sidebar-compositor.ts";
import type { FooterTextMetrics } from "../src/footer.ts";
import { findPiPackageRoot } from "./live-pi-host.ts";

function configurableTerminal(): { columns: number; rows: number } {
  const value: Record<string, unknown> = { rows: 50 };
  Object.defineProperty(value, "columns", {
    value: 200,
    writable: true,
    configurable: true,
    enumerable: true,
  });
  return value as unknown as { columns: number; rows: number };
}

async function loadInstalledPiTui(): Promise<{
  piVersion: string;
  module: Record<string, unknown>;
}> {
  const packageRoot = await findPiPackageRoot();
  const manifest = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8")) as { version?: string };
  const runtimeRequire = createRequire(resolve(packageRoot, "dist", "index.js"));
  const entry = await realpath(runtimeRequire.resolve("@earendil-works/pi-tui"));
  const module = await import(pathToFileURL(entry).href) as Record<string, unknown>;
  return { piVersion: manifest.version ?? "unknown", module };
}

function doRenderImplementors(module: Record<string, unknown>): string[] {
  return Object.keys(module).filter((name) => {
    const value = module[name];
    return typeof value === "function"
      && value.prototype !== undefined
      && typeof Object.getOwnPropertyDescriptor(value.prototype as object, "doRender")?.value === "function";
  });
}

describe("sidebar probe against the installed Pi host (AC-7 live)", () => {
  test("the installed pi-tui exposes the probed metrics and doRender surface", async () => {
    const { piVersion, module } = await loadInstalledPiTui();
    expect(typeof module.visibleWidth, `pi ${piVersion}`).toBe("function");
    expect(typeof module.truncateToWidth, `pi ${piVersion}`).toBe("function");

    const implementors = doRenderImplementors(module);
    expect(implementors.length, `pi ${piVersion}: no exported class implements doRender`).toBeGreaterThan(0);
    // The per-window shapes the fixture contract encodes, pinned live.
    if (piVersion.startsWith("0.80.")) {
      expect(implementors, `pi ${piVersion}`).toContain("TUI");
    } else {
      expect(implementors, `pi ${piVersion}`).toEqual(expect.arrayContaining(["TuiMainScreen", "TuiAltScreen"]));
    }

    const metrics: FooterTextMetrics = {
      visibleWidth: module.visibleWidth as FooterTextMetrics["visibleWidth"],
      truncateToWidth: module.truncateToWidth as FooterTextMetrics["truncateToWidth"],
    };
    for (const name of implementors) {
      const prototype = (module[name] as { prototype: object }).prototype;
      const tui = Object.create(prototype) as SidebarTuiPort;
      const probe = probeSidebarSupport(tui, configurableTerminal(), metrics);
      expect(probe.ok, `pi ${piVersion}: probe failed for ${name}`).toBe(true);
    }
  });
});
