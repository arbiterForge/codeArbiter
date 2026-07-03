import { describe, it, expect } from "vitest";
import {
  yamlQuoteEscape,
  yamlDescriptionLine,
} from "../../scripts/generator/yaml-quote";

describe("yamlQuoteEscape", () => {
  it("leaves a plain string unchanged", () => {
    expect(yamlQuoteEscape("plain text")).toBe("plain text");
  });

  it("escapes double quotes", () => {
    expect(yamlQuoteEscape('the "quoted" word')).toBe(
      'the \\"quoted\\" word',
    );
  });

  it("escapes backslashes before quotes so escaping is not doubled", () => {
    expect(yamlQuoteEscape('a\\"b')).toBe('a\\\\\\"b');
  });

  it("leaves colons and em-dashes unescaped (safe inside a double-quoted scalar)", () => {
    expect(yamlQuoteEscape("a: b — c")).toBe("a: b — c");
  });
});

describe("yamlDescriptionLine", () => {
  it("renders a quoted description line", () => {
    expect(yamlDescriptionLine("hello world")).toBe(
      'description: "hello world"',
    );
  });

  it("escapes quotes and colons together", () => {
    expect(yamlDescriptionLine('The "only" path: forward.')).toBe(
      'description: "The \\"only\\" path: forward."',
    );
  });

  it("returns an empty string for an empty description", () => {
    expect(yamlDescriptionLine("")).toBe("");
  });

  it("returns an empty string for an undefined description", () => {
    expect(yamlDescriptionLine(undefined)).toBe("");
  });
});
