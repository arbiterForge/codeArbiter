/** forge-status.test.ts — codeArbiter's site-side Feature Forge allowlist tests. */
import { describe, it, expect } from "vitest";
import {
  getCommandForgeStatus,
  PREVIEW_COMMANDS,
  FORGE_FEATURES,
} from "../../scripts/generator/forge-status";

describe("getCommandForgeStatus", () => {
  it("returns 'preview-command' for the prune command (whole command is preview)", () => {
    expect(getCommandForgeStatus("prune")).toMatchObject({ kind: "preview-command" });
  });

  it("returns 'preview-flag' with flag name for the sprint command (--farm flag is preview)", () => {
    // toMatchObject so the assertion stays focused on kind+flag and is resilient
    // to the optional `env` payload carried alongside.
    expect(getCommandForgeStatus("sprint")).toMatchObject({
      kind: "preview-flag",
      flag: "--farm",
    });
  });

  it("returns null for a stable command (commit)", () => {
    expect(getCommandForgeStatus("commit")).toBeNull();
  });

  it("returns null for an unknown command", () => {
    expect(getCommandForgeStatus("nonexistent-command")).toBeNull();
  });

  it("PREVIEW_COMMANDS includes prune and sprint", () => {
    expect(Object.keys(PREVIEW_COMMANDS)).toContain("prune");
    expect(Object.keys(PREVIEW_COMMANDS)).toContain("sprint");
  });

  it("PREVIEW_COMMANDS does not include commit", () => {
    expect(Object.keys(PREVIEW_COMMANDS)).not.toContain("commit");
  });

  // Edge cases: the "/ca:" prefix-strip and case-normalisation paths (AC-9/20a).
  it("strips the /ca: prefix before lookup ('/ca:prune' -> preview-command)", () => {
    expect(getCommandForgeStatus("/ca:prune")).toMatchObject({ kind: "preview-command" });
  });

  it("normalises case before lookup ('PRUNE' -> preview-command)", () => {
    expect(getCommandForgeStatus("PRUNE")).toMatchObject({ kind: "preview-command" });
  });

  it("handles prefix + mixed case together ('/ca:Sprint' -> preview-flag --farm)", () => {
    expect(getCommandForgeStatus("/ca:Sprint")).toMatchObject({
      kind: "preview-flag",
      flag: "--farm",
    });
  });

  it("sprint --farm declares FARM_API_KEY as a required env var (drives the catalog env list)", () => {
    const farm = getCommandForgeStatus("sprint");
    const apiKey = farm?.env?.find((e) => e.name === "FARM_API_KEY");
    expect(apiKey).toBeDefined();
    expect(apiKey?.required).toBe(true);
  });

  it("the prune feature opts in via the CODEARBITER_PRUNE env var", () => {
    const prune = getCommandForgeStatus("prune");
    const sw = prune?.env?.find((e) => e.name === "CODEARBITER_PRUNE");
    expect(sw).toBeDefined();
    expect(sw?.required).toBe(true);
  });

  it("returns null for a stable command passed with the /ca: prefix ('/ca:commit')", () => {
    expect(getCommandForgeStatus("/ca:commit")).toBeNull();
  });
});

describe("FORGE_FEATURES (the catalog source)", () => {
  it("mirrors the README forge list: pruning, the farm, and ca-sandbox", () => {
    const names = FORGE_FEATURES.map((f) => f.name.toLowerCase());
    expect(names.some((n) => n.includes("pruning"))).toBe(true);
    expect(names.some((n) => n.includes("farm"))).toBe(true);
    expect(names.some((n) => n.includes("ca-sandbox"))).toBe(true);
  });

  it("includes ca-sandbox as a preview-plugin with prerequisites and no /ca: command", () => {
    const sandbox = FORGE_FEATURES.find((f) => f.name.toLowerCase().includes("ca-sandbox"));
    expect(sandbox?.kind).toBe("preview-plugin");
    expect(sandbox?.command).toBeUndefined();
    expect(sandbox?.requires).toMatch(/docker/i);
  });

  it("only command/flag features reach PREVIEW_COMMANDS (plugins are excluded from badging)", () => {
    const commandFeatures = FORGE_FEATURES.filter((f) => f.command).map((f) => f.command);
    expect(Object.keys(PREVIEW_COMMANDS).sort()).toEqual([...commandFeatures].sort());
  });
});
