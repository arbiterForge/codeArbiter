import { describe, expect, it } from "vitest";
import {
  copyCommand,
  readPreference,
  readPreferences,
  shouldRenderCommandPreferences,
  visibleVariantIndexes,
} from "../src/scripts/academy-command-preferences";

const variants = [
  { os: "windows", host: "codex" },
  { os: "macos", host: "codex" },
  { os: "all", host: "none" },
  { os: "linux", host: "pi" },
];

describe("Academy command preferences", () => {
  it("keeps universal commands while narrowing a lesson to the selected OS and host", () => {
    expect(visibleVariantIndexes(variants, { os: "windows", host: "codex" })).toEqual([0, 2]);
  });

  it("falls back to every command when a saved combination has no matching variant", () => {
    const hostSpecificVariants = variants.filter((variant) => variant.host !== "none");
    expect(visibleVariantIndexes(hostSpecificVariants, { os: "macos", host: "pi" })).toEqual([0, 1, 2]);
  });

  it("accepts only a persisted preference that is still supported", () => {
    const values = new Map([["academy-os", "linux"], ["academy-host", "retired-host"]]);
    const storage = { getItem: (key: string) => values.get(key) ?? null };

    expect(readPreference(storage, "academy-os", new Set(["windows", "macos", "linux"]))).toBe("linux");
    expect(readPreference(storage, "academy-host", new Set(["codex", "pi"]))).toBeNull();
  });

  it("keeps command controls usable when acquiring browser storage throws", () => {
    expect(readPreferences(
      () => { throw new Error("blocked"); },
      new Set(["windows", "macos", "linux"]),
      new Set(["claude-code", "codex", "pi"]),
    )).toEqual({ os: null, host: null });
  });

  it("renders the custom element for all/none-only variants so copy handlers still attach", () => {
    expect(shouldRenderCommandPreferences([{ os: "all", host: "none" }])).toBe(true);
    expect(shouldRenderCommandPreferences([])).toBe(false);
  });

  it("returns a selection fallback when clipboard access is unavailable", async () => {
    let selected = false;
    await expect(copyCommand("$ca-status", async () => { throw new Error("denied"); }, () => { selected = true; }))
      .resolves.toBe("fallback");
    expect(selected).toBe(true);
  });

  it("reports copied only after the clipboard receives the exact command", async () => {
    let copied = "";
    await expect(copyCommand("$ca-status", async (text) => { copied = text; }, () => { throw new Error("should not select"); }))
      .resolves.toBe("copied");
    expect(copied).toBe("$ca-status");
  });
});
