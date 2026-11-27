import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildCommandMatrix, loadCommandMatrix, type RoutesManifest } from "./command-matrix";
import { REPO_ROOT } from "../machine/machine-model";

const routes = JSON.parse(readFileSync(join(REPO_ROOT, "core/surface/command-routes.json"), "utf8")) as RoutesManifest;

describe("the command matrix", () => {
  const rows = loadCommandMatrix();

  it("has one row per command in the route manifest, ordered by level, then workflow, then name", () => {
    expect(rows.map((row) => row.name).sort()).toEqual(Object.keys(routes.commands).sort());
    const level = (name: string) => routes.visibilityOrder.indexOf(routes.commands[name].visibility);
    const flow = (name: string) => routes.workflowOrder.indexOf(routes.commands[name].workflow);
    for (let i = 1; i < rows.length; i += 1) {
      const [a, b] = [rows[i - 1].name, rows[i].name];
      const key = (n: string) => [level(n), flow(n)];
      const [ka, kb] = [key(a), key(b)];
      expect(ka[0] < kb[0] || (ka[0] === kb[0] && (ka[1] < kb[1] || (ka[1] === kb[1] && a < b))), `${a} before ${b}`).toBe(true);
    }
  });

  it("spells each command with each host's own command form, and only where that host ships it", () => {
    const feature = rows.find((row) => row.name === "feature")!;
    expect(feature.hosts.claude).toEqual({ available: true, spelled: "/ca:feature" });
    expect(feature.hosts.codex).toEqual({ available: true, spelled: "$ca-feature" });
    expect(feature.hosts.pi).toEqual({ available: true, spelled: "/ca-feature" });
    for (const row of rows) {
      for (const host of ["claude", "codex", "pi"] as const) {
        const catalog = readFileSync(join(REPO_ROOT, "plugins", { claude: "ca", codex: "ca-codex", pi: "ca-pi" }[host], "COMMANDS.md"), "utf8");
        expect(row.hosts[host].available, `${row.name} on ${host}`).toBe(catalog.includes(`\`${row.hosts[host].spelled}\``));
      }
    }
  });

  it("carries each lane's real route from the machine model, and no route where the model keeps no lane", () => {
    const fix = rows.find((row) => row.name === "fix")!;
    expect(fix.lane?.href).toBe("/concepts/machine/#part-ca-fix");
    expect(fix.lane?.stops.length).toBeGreaterThan(3);
    expect(fix.lane?.stops.some((stop) => stop.verdict === "fail")).toBe(true);
    for (const row of rows.filter((r) => r.visibility === "alias")) expect(row.lane, row.name).toBeNull();
  });

  it("names what replaces each alias, and that replacement is a real command", () => {
    const aliases = rows.filter((row) => row.visibility === "alias");
    expect(aliases.length).toBeGreaterThan(0);
    for (const alias of aliases) {
      expect(alias.replacement, alias.name).toMatch(/^[a-z-]+( .+)?$/);
      const target = alias.replacement!.split(" ")[0];
      expect(target, alias.name).toBe(alias.canonical);
      expect(rows.some((row) => row.name === target && row.visibility !== "alias"), alias.name).toBe(true);
    }
    expect(rows.find((row) => row.name === "cleanup")?.replacement).toBe("pr --cleanup");
  });

  it("refuses a manifest command the hosts do not know, rather than printing a guess", () => {
    const bogus: RoutesManifest = { ...routes, commands: { ...routes.commands, ghost: { visibility: "core", workflow: "change", canonical: "ghost", legacyRoutes: [] } } };
    expect(() => buildCommandMatrix(bogus, {})).toThrow(/ghost is shipped by no host/);
  });
});
