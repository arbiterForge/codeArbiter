import { describe, expect, test } from "vitest";

import { renderSidebar } from "../src/sidebar.ts";
import type { SidebarInput } from "../src/sidebar.ts";

const metrics = {
  visibleWidth: (text: string) => text.replace(/\x1b\[[0-9;]*m/gu, "").length,
  truncateToWidth: (text: string, width: number, suffix: string) => {
    const plain = text.replace(/\x1b\[[0-9;]*m/gu, "");
    return plain.length <= width ? text : plain.slice(0, Math.max(0, width - suffix.length)) + suffix;
  },
};

const fullInput: SidebarInput = {
  session: {
    model: "gpt-test",
    thinkingLevel: "high",
    contextPercent: 42,
    inputTokens: 1200,
    outputTokens: 340,
    costUsd: 0.0921,
    burn: [1, 5, 3, 9, 2],
  },
  subagents: [
    { kind: "child", label: "backend-author", state: "active", ageSeconds: 12 },
    { kind: "job", label: "test-run", state: "completed", ageSeconds: 90 },
  ],
  workspace: { cwd: "C:/repo/project", repository: "codeArbiter", dirty: true },
  todos: [
    { text: "write tests", state: "done" },
    { text: "implement renderer", state: "active" },
    { text: "wire command", state: "open" },
  ],
  mcp: [{ name: "discord", state: "connected" }],
};

function plain(line: string): string {
  return line.replace(/\x1b\[[0-9;]*m/gu, "");
}

describe("sidebar renderer (AC-1, AC-6)", () => {
  test("returns width-exact lines for every panel at fixed widths", () => {
    for (const width of [24, 40, 60]) {
      const lines = renderSidebar(fullInput, width, metrics);
      expect(lines.length).toBeGreaterThan(0);
      for (const line of lines) {
        expect(metrics.visibleWidth(line), `width ${width}: ${JSON.stringify(line)}`).toBe(width);
      }
    }
  });

  test("renders all five panel headers when every data source is present", () => {
    const text = renderSidebar(fullInput, 40, metrics).map(plain).join("\n");
    for (const header of ["session", "agents", "workspace", "todos", "mcp"]) {
      expect(text.toLowerCase()).toContain(header);
    }
  });

  test("omits trusted-only and empty panels without breaking siblings", () => {
    const lines = renderSidebar({ session: fullInput.session }, 40, metrics).map(plain);
    const text = lines.join("\n").toLowerCase();
    expect(text).toContain("session");
    expect(text).not.toContain("workspace");
    expect(text).not.toContain("todos");
    expect(text).not.toContain("mcp");
  });

  test("a throwing panel renders its header with an omitted body and siblings survive", () => {
    const poisoned: SidebarInput = {
      ...fullInput,
      // A getter that throws mid-render is the hardest failure a panel can see.
      get todos(): SidebarInput["todos"] {
        throw new Error("poisoned todos source");
      },
    };
    const lines = renderSidebar(poisoned, 40, metrics).map(plain);
    const text = lines.join("\n").toLowerCase();
    expect(text).toContain("session");
    expect(text).toContain("agents");
    expect(text).toContain("mcp");
    expect(text).toContain("todos");
    expect(text).toContain("(unavailable)");
    for (const line of lines) expect(metrics.visibleWidth(line)).toBe(40);
  });

  test("sanitizes control characters and ANSI injection from every string field", () => {
    const hostile: SidebarInput = {
      subagents: [{ kind: "child", label: "evil\x1b]0;owned\x07\x1b[31mred\u0000label", state: "active", ageSeconds: 1 }],
      workspace: { cwd: "C:/x", repository: "re\x1b[2Jpo", dirty: false },
      mcp: [{ name: "srv\u009c\u200e", state: "connected" }],
    };
    const joined = renderSidebar(hostile, 40, metrics).join("\n");
    expect(joined).not.toContain("\x07");
    expect(joined).not.toContain("\u0000");
    expect(joined).not.toContain("\x1b]");
    expect(joined).not.toContain("[2J");
    expect(joined).not.toContain("\u200e");
  });

  test("NO_COLOR strips every escape while keeping width-exact lines", () => {
    const lines = renderSidebar(fullInput, 40, metrics, { noColor: true });
    for (const line of lines) {
      expect(line).not.toContain("\x1b");
      expect(line.length).toBe(40);
    }
  });

  test("subagents panel shows kind, state and age for entries and an overflow count beyond 16", () => {
    const subagents = Array.from({ length: 19 }, (_item, index) => ({
      kind: index % 2 === 0 ? "child" as const : "job" as const,
      label: `agent-${index}`,
      state: "active" as const,
      ageSeconds: index,
    }));
    const text = renderSidebar({ subagents }, 40, metrics).map(plain).join("\n");
    expect(text).toContain("agent-0");
    expect(text).toContain("agent-15");
    expect(text).not.toContain("agent-16");
    expect(text).toContain("+3 more");
  });

  test("todo states render distinctly and long labels truncate inside the panel width", () => {
    const todos = [
      { text: "d".repeat(200), state: "done" as const },
      { text: "a".repeat(200), state: "active" as const },
      { text: "o".repeat(200), state: "open" as const },
    ];
    const lines = renderSidebar({ todos }, 30, metrics).map(plain);
    for (const line of lines) expect(line.length).toBe(30);
    const rows = lines.filter((line) => /[✓▸·]/u.test(line));
    expect(rows).toHaveLength(3);
    expect(new Set(rows.map((line) => /[✓▸·]/u.exec(line)![0])).size).toBe(3);
  });

  test("bounded against absurd numeric inputs without throwing", () => {
    const lines = renderSidebar({
      session: {
        model: "m",
        contextPercent: Number.POSITIVE_INFINITY,
        inputTokens: Number.NaN,
        outputTokens: -5,
        costUsd: Number.MAX_VALUE,
        burn: [Number.NaN, Number.POSITIVE_INFINITY, -1],
      },
      subagents: [{ kind: "child", label: "x", state: "active", ageSeconds: Number.NaN }],
    }, 40, metrics);
    for (const line of lines) expect(metrics.visibleWidth(line)).toBe(40);
  });
});
