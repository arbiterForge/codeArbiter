/** forge-status.test.ts — codeArbiter's site-side Feature Forge allowlist tests. */
import { describe, it, expect } from "vitest";
import {
  getCommandForgeStatus,
  PREVIEW_COMMANDS,
} from "../../scripts/generator/forge-status";

describe("getCommandForgeStatus", () => {
  it("returns 'preview-command' for the prune command (whole command is preview)", () => {
    expect(getCommandForgeStatus("prune")).toEqual({ kind: "preview-command" });
  });

  it("returns 'preview-flag' with flag name for the sprint command (--farm flag is preview)", () => {
    expect(getCommandForgeStatus("sprint")).toEqual({
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
    expect(getCommandForgeStatus("/ca:prune")).toEqual({ kind: "preview-command" });
  });

  it("normalises case before lookup ('PRUNE' -> preview-command)", () => {
    expect(getCommandForgeStatus("PRUNE")).toEqual({ kind: "preview-command" });
  });

  it("handles prefix + mixed case together ('/ca:Sprint' -> preview-flag --farm)", () => {
    expect(getCommandForgeStatus("/ca:Sprint")).toEqual({
      kind: "preview-flag",
      flag: "--farm",
    });
  });

  it("returns null for a stable command passed with the /ca: prefix ('/ca:commit')", () => {
    expect(getCommandForgeStatus("/ca:commit")).toBeNull();
  });
});
