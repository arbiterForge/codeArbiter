import { describe, it, expect } from "vitest";
import { formatToolsList } from "../../scripts/generator/format-tools-list";

describe("formatToolsList", () => {
  it("formats a comma-separated list with backticks", () => {
    expect(formatToolsList("Read, Grep, Glob")).toBe("`Read`, `Grep`, `Glob`");
  });

  it("trims entries even without spaces after commas", () => {
    expect(formatToolsList("Read,Grep")).toBe("`Read`, `Grep`");
  });

  it("handles a single tool", () => {
    expect(formatToolsList("All tools")).toBe("`All tools`");
  });

  it("returns an em dash for missing or empty input", () => {
    expect(formatToolsList(undefined)).toBe("—");
    expect(formatToolsList("")).toBe("—");
  });
});
