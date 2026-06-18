import { describe, it, expect } from "vitest";
import { classifySource } from "../../scripts/generator/classify-source";

describe("classifySource", () => {
  it("classifies a command path", () => {
    expect(classifySource("plugins/ca/commands/commit.md")).toBe("command");
  });

  it("classifies a skill path", () => {
    expect(classifySource("plugins/ca/skills/tdd/SKILL.md")).toBe("skill");
  });

  it("classifies an agent path", () => {
    expect(classifySource("plugins/ca/agents/scout.md")).toBe("agent");
  });

  it("normalizes backslash separators", () => {
    expect(classifySource("plugins\\ca\\agents\\scout.md")).toBe("agent");
  });

  it("throws on an unrecognized path", () => {
    expect(() => classifySource("plugins/ca/readme.md")).toThrow();
  });
});
