import { describe, it, expect } from "vitest";
import { deriveName } from "../../scripts/generator/derive-name";

describe("deriveName", () => {
  it("uses the name field when present", () => {
    expect(deriveName("x/agents/myagent.md", { name: "myagent" })).toBe("myagent");
  });

  it("derives a command name from the filename when no name field", () => {
    expect(deriveName("x/commands/commit.md", {})).toBe("commit");
    expect(deriveName("x/commands/adr-status.md", { description: "d" })).toBe(
      "adr-status",
    );
  });

  it("derives a skill name from the parent directory for SKILL.md", () => {
    expect(deriveName("x/skills/tdd/SKILL.md", {})).toBe("tdd");
  });

  it("normalizes backslash separators", () => {
    expect(deriveName("x\\commands\\commit.md", {})).toBe("commit");
  });
});
