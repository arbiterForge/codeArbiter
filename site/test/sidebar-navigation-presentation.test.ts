import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const siteRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (path: string): string => readFileSync(join(siteRoot, path), "utf8");

describe("sidebar navigation presentation prerequisites", () => {
  it("wires the generated reference tree through the single projection boundary", () => {
    const config = read("astro.config.mjs");
    expect(config).toContain('import { buildReferenceSidebar } from "./scripts/reference-sidebar.ts"');
    expect(config).toContain("referenceGroups = buildReferenceSidebar(sidebarData)");
    expect(config).not.toMatch(/referenceGroups\s*=\s*sidebarData\.map/);
    expect(config).not.toContain("localStorage");
    expect(config).not.toContain("sessionStorage");
  });

  it("does not swallow malformed generated JSON or projection failures", () => {
    const config = read("astro.config.mjs");
    expect(config).toMatch(/catch\s*\(error\)/);
    expect(config).toMatch(/error[\s\S]*code[\s\S]*ENOENT/);
    expect(config).toMatch(/throw error/);
    expect(config).not.toMatch(/catch\s*\{[\s\S]*sidebar\.json not generated yet/);
  });

  // This fixture exercises the real config's JSON/error boundary and real sidebar
  // projection, not Astro/Starlight startup. Their cold import graph was consuming
  // the unchanged five-second test budget before malformed JSON could be read.
  let configCase = 0;
  async function loadWithSidebar(value: string | Error) {
    vi.doMock("astro/config", () => ({ defineConfig: (config: unknown) => config }));
    vi.doMock("@astrojs/starlight", () => ({ default: () => ({ name: "fixture-starlight" }) }));
    vi.doMock("@astrojs/markdown-remark", () => ({ unified: () => ({}) }));
    vi.doMock("node:fs", async (importOriginal) => {
      const actual = await importOriginal<typeof import("node:fs")>();
      return {
        ...actual,
        readFileSync(path: Parameters<typeof readFileSync>[0], options?: Parameters<typeof readFileSync>[1]) {
          if (String(path).includes("/src/generated/sidebar.json")) {
            if (value instanceof Error) throw value;
            return value;
          }
          return actual.readFileSync(path, options as never);
        },
      };
    });
    try {
      return await import(`${pathToFileURL(join(siteRoot, "astro.config.mjs")).href}?sidebar-case=${++configCase}`);
    } finally {
      for (const module of ["node:fs", "astro/config", "@astrojs/starlight", "@astrojs/markdown-remark"]) {
        vi.doUnmock(module);
      }
    }
  }

  it("fails configuration loading when generated sidebar JSON is malformed", async () => {
    await expect(loadWithSidebar("{ malformed")).rejects.toThrow(SyntaxError);
  });

  it("allows valid generated metadata and only the documented missing-file case", async () => {
    const valid = read("src/generated/sidebar.json");
    await expect(loadWithSidebar(valid)).resolves.toHaveProperty("default");
    await expect(loadWithSidebar(Object.assign(new Error("fixture missing"), { code: "ENOENT" })))
      .resolves.toHaveProperty("default");
  });

  it("still rejects incompatible metadata and unrelated read failures", async () => {
    await expect(loadWithSidebar("[]"))
      .rejects.toThrow("Generated sidebar must contain exactly one Commands group");
    const denied = Object.assign(new Error("fixture denied"), { code: "EACCES" });
    await expect(loadWithSidebar(denied)).rejects.toBe(denied);
  });

  it("keeps nested native disclosures, current-page ancestor expansion, and visible focus", () => {
    const sidebar = read("src/components/Sidebar.astro");
    const sublist = read("src/components/SidebarSublist.astro");
    const design = read("src/styles/design-system.css");

    expect(sidebar).toContain("<SidebarSublist sublist={sidebar} />");
    expect(sublist).toContain("<details open={hasCurrentLink(entry.entries) || !entry.collapsed}>");
    expect(sublist).toContain("<summary>");
    expect(sublist).toContain("<Astro.self sublist={entry.entries} nested />");
    expect(sublist).toMatch(/hasCurrentLink\(entry\.entries\)/);
    expect(design).toMatch(/:focus-visible\s*\{[^}]*outline:/s);
  });

  it("reuses the canonical Sidebar in the branded rail and retains mobile/scroll controls", () => {
    const sidebar = read("src/components/Sidebar.astro");
    const rail = read("src/components/SplashDocsRail.astro");
    const landing = read("src/styles/landing.css");

    expect(rail).toContain('import Sidebar from "./Sidebar.astro"');
    expect(rail).toContain("<Sidebar />");
    expect(rail).not.toContain("<SidebarSublist");
    expect(sidebar).toContain("<MobileMenuFooter />");
    expect(landing).toMatch(/\.ca-docs-drawer[^}]*overflow-y:\s*auto/s);
    expect(rail).toContain('"summary"');
  });
});
