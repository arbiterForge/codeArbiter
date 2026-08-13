import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CONFIGURATION_ENTRIES,
  renderConfigurationReference,
} from "../../scripts/generator/configuration-reference";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const implementationExtensions = new Set([".py", ".ts", ".js", ".mjs", ".json", ".sh"]);

function implementationCorpus(root: string): string {
  const contents: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === "test" || entry.name === "tests") continue;
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (implementationExtensions.has(extname(entry.name))) {
        contents.push(readFileSync(path, "utf8"));
      }
    }
  };
  walk(root);
  return contents.join("\n");
}

describe("configuration reference", () => {
  it("keeps names unique and uses only public prefixes", () => {
    const names = CONFIGURATION_ENTRIES.map((entry) => entry.name);
    expect(new Set(names).size).toBe(names.length);
    expect(names.every((name) => name === "NO_COLOR" || /^(CODEARBITER|FARM)_/.test(name))).toBe(true);
  });

  it("does not document the removed CODEARBITER_DEV surface", () => {
    const page = renderConfigurationReference();
    expect(page).not.toContain("CODEARBITER_DEV");
  });

  it("documents the opt-in and spending-sensitive boundaries", () => {
    const page = renderConfigurationReference();
    expect(page).toContain("CODEARBITER_BASE_BRANCH");
    expect(page).toContain("CODEARBITER_BABYSIT_ONRED");
    expect(page).toContain("CODEARBITER_PRUNE");
    expect(page).toContain("CODEARBITER_PRUNE_METRICS");
    expect(page).toContain("FARM_API_KEY");
    expect(page).toContain("FARM_ALLOW_EXTERNAL_WORKTREE_ROOT");
    expect(page).toContain("FARM_MUTATION_ESCALATE_BELOW");
    expect(page).toContain("multiply provider token use");
    expect(page).toContain("never commit it");
    expect(page).toContain("destructive-scope override");
  });

  it("covers every operator control promised by the farm and watch docs", () => {
    const names = new Set(CONFIGURATION_ENTRIES.map((entry) => entry.name));
    const required = [
      "CODEARBITER_BABYSIT",
      "CODEARBITER_BABYSIT_ONRED",
      "FARM_BASE_BRANCH",
      "FARM_INTEGRATION_BRANCH",
      "FARM_API_MAX_RETRIES",
      "FARM_ENTITLEMENT_PROBE_TIMEOUT_MS",
      "FARM_ABORT_ESCALATION_RATE",
      "FARM_ABORT_MIN_TASKS",
      "FARM_RUN_ID",
      "FARM_MUTATION",
      "FARM_MUTATION_SAMPLE",
      "FARM_MUTATION_BUDGET_MS",
      "FARM_MUTATION_WARN_BELOW",
      "FARM_MUTATION_ESCALATE_BELOW",
      "FARM_MUTATION_CMD",
    ];
    expect(required.filter((name) => !names.has(name))).toEqual([]);
  });

  it("renders every typed entry exactly once", () => {
    const page = renderConfigurationReference();
    for (const entry of CONFIGURATION_ENTRIES) {
      expect(page.match(new RegExp(`^\\| \\\`${entry.name}\\\` \\|`, "gm"))).toHaveLength(1);
    }
  });

  it("backs every documented variable name with shipped implementation code", () => {
    const source = implementationCorpus(join(repoRoot, "plugins"));
    const missing = CONFIGURATION_ENTRIES
      .map((entry) => entry.name)
      .filter((name) => !source.includes(name));
    expect(missing).toEqual([]);
  });

  it("is deterministic", () => {
    expect(renderConfigurationReference()).toBe(renderConfigurationReference());
  });
});
