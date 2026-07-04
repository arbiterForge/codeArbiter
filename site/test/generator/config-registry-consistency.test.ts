/** config-registry-consistency.test.ts — the Forge catalog's env vars must be
 * a subset of the plugin's settings registry (plugins/ca/config/registry.json),
 * and carry preview status there. Closes the registry side of the drift noted
 * in forge-status.ts's header: a Forge env var that is renamed or added
 * without a registry entry fails here. */
import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";
import { FORGE_FEATURES } from "../../scripts/generator/forge-status";

interface RegistryEntry {
  name: string;
  status?: string;
  description: string;
}

const registry = JSON.parse(
  readFileSync(new URL("../../../plugins/ca/config/registry.json", import.meta.url), "utf8"),
) as { version: number; settings: RegistryEntry[] };

const byName = new Map(registry.settings.map((s) => [s.name, s]));
const forgeEnvNames = FORGE_FEATURES.flatMap((f) => f.env ?? []).map((v) => v.name);

describe("forge-status env vars vs the settings registry", () => {
  it("references at least one env var (guard against silent decoupling)", () => {
    expect(forgeEnvNames.length).toBeGreaterThan(0);
  });

  it.each(forgeEnvNames)("%s is registered", (name) => {
    expect(byName.has(name), `${name} missing from plugins/ca/config/registry.json`).toBe(true);
  });

  it.each(forgeEnvNames)("%s carries preview status in the registry", (name) => {
    expect(byName.get(name)?.status).toBe("preview");
  });

  it("registry itself is well-formed enough to consume", () => {
    expect(registry.version).toBe(1);
    for (const s of registry.settings) {
      expect(s.name, "every entry needs a name").toBeTruthy();
      expect(s.description, `${s.name} needs a description`).toBeTruthy();
    }
  });
});
