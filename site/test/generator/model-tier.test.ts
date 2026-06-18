import { describe, it, expect } from "vitest";
import { modelTier } from "../../scripts/generator/model-tier";

describe("modelTier", () => {
  it("capitalizes known tiers", () => {
    expect(modelTier("sonnet")).toBe("Sonnet");
    expect(modelTier("opus")).toBe("Opus");
    expect(modelTier("haiku")).toBe("Haiku");
  });

  it("returns 'default' for a missing or empty model", () => {
    expect(modelTier(undefined)).toBe("default");
    expect(modelTier("")).toBe("default");
  });

  it("returns an unknown model unchanged", () => {
    expect(modelTier("custom-model")).toBe("custom-model");
  });
});
