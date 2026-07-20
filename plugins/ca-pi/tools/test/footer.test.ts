import { readFileSync } from "node:fs";
import { describe, expect, test, vi } from "vitest";

import { renderFooter as renderFooterWithMetrics } from "../src/footer.ts";
import type { FooterInput, FooterRenderOptions, FooterTextMetrics } from "../src/footer.ts";
import * as footerStateModule from "../src/footer-state.ts";
import { adaptPiFooterState } from "../src/footer-state.ts";

const ANSI_RE = /\x1b\[[0-9;]*m/gu;

function plain(value: string): string {
  return value.replace(ANSI_RE, "");
}

const REFERENCE_SEGMENTER = new Intl.Segmenter("en", { granularity: "grapheme" });
const FIXTURE_WIDTHS = new Map<string, number>([
  ["e\u0301", 1],
  ["©", 1],
  ["™", 1],
  ["❤", 1],
  ["❤️", 2],
  ["1\ufe0f\u20e3", 2],
  ["👍🏽", 2],
  ["👨‍👩‍👧‍👦", 2],
  ["🇺🇸", 2],
  ["界", 2],
  ["𗀀", 2],
]);

/** Independent fixture oracle: special grapheme widths are explicit test data. */
function fixtureTerminalWidth(value: string, widths = FIXTURE_WIDTHS): number {
  return [...REFERENCE_SEGMENTER.segment(plain(value))]
    .reduce((width, { segment }) => width + (widths.get(segment) ?? 1), 0);
}

function fixtureTruncate(text: string, width: number, suffix: string, widths = FIXTURE_WIDTHS): string {
  if (fixtureTerminalWidth(text, widths) <= width) return text;
  const target = Math.max(0, width - fixtureTerminalWidth(suffix, widths));
  const plainText = plain(text);
  let output = "";
  let used = 0;
  for (const { segment } of REFERENCE_SEGMENTER.segment(plainText)) {
    const next = widths.get(segment) ?? 1;
    if (used + next > target) break;
    output += segment;
    used += next;
  }
  return output + suffix;
}

const TEST_METRICS: FooterTextMetrics = {
  visibleWidth: fixtureTerminalWidth,
  truncateToWidth: fixtureTruncate,
};

function renderFooter(
  input: FooterInput,
  options: FooterRenderOptions,
  metrics: FooterTextMetrics = TEST_METRICS,
): string {
  return renderFooterWithMetrics(input, options, metrics);
}

function layoutSnapshot(value: string): string {
  return plain(value)
    .split("\n")
    .map((line) => line
      .replace(/─{2,}/gu, "─")
      .replace(/┄{2,}/gu, "┄")
      .replace(/ {2,}/gu, "  ")
      .replace(/ +(?=[│╮])/gu, " "))
    .join("\n");
}

const WIDE_INPUT: FooterInput = {
  folder: "C:/work/codearbiter",
  sessionName: "parity sprint",
  git: { repository: "brenn/codearbiter", branch: "feat/pi", dirty: true },
  model: { name: "Claude Opus 4.8", provider: "anthropic", thinking: "xhigh" },
  session: {
    inputTokens: 12_345,
    outputTokens: 4_567,
    cacheReadTokens: 2_500,
    cacheWriteTokens: 600,
    costUsd: 1.234,
    ageSeconds: 3_661,
  },
  context: { usedTokens: 136_000, windowTokens: 200_000 },
  daily: { inputTokens: 98_765, outputTokens: 5_432, costUsd: 7.891 },
  update: { version: "2.8.0" },
  governance: { stage: "implementation", tasks: 2, questions: 1, overrides: 0, sprint: true },
  activity: [
    { kind: "job", label: "focused tests", state: "active", ageSeconds: 120 },
    { kind: "child", label: "footer review", state: "completed", ageSeconds: 30 },
  ],
};

describe("renderFooter", () => {
  test("snapshots the wide sectioned layout from normalized Pi-owned facts", () => {
    const output = renderFooter(WIDE_INPUT, { width: 104, noColor: true });

    expect(layoutSnapshot(output)).toMatchInlineSnapshot(`
      "╭─ C:/work/codearbiter • parity sprint ─╮
      │ git brenn/codearbiter │ feat/pi*  update 2.8.0  anthropic/Claude Opus 4.8 │ XHigh │
      ├┄┤
      │ ● stage:implementation · tasks:2 · q:1 · over:0 [SPRINT] │
      ├┄┤
      │ Session │ ↓  12.3K ↑  4.6K │ $1.23 │ ctx ███████████████████░░░░░░░░░ 68% │
      │ Today │ ↓  98.8K ↑  5.4K │ $7.89 │ cache r 2.5K w 600 hit 81% · age 1h01m │
      ├┄┤
      │ activity ● job:focused tests 2m · ✓ child:footer review 30s │
      ╰─╯"
    `);
    for (const line of output.split("\n")) expect(fixtureTerminalWidth(line)).toBe(104);
  });

  test("snapshots the compact layout and omits lower-priority activity", () => {
    const output = renderFooter(WIDE_INPUT, { width: 60, compact: true, noColor: true });

    expect(layoutSnapshot(output)).toMatchInlineSnapshot(`
      "╭─ C:/work/codearbiter • parity sprint ─╮
      │ git feat/pi*  Claude Opus 4.8 │ XHigh │
      ├┄┤
      │ sess ↓12.3K ↑4.6K $1.23 · ctx 68% │
      │ cache 81% · age 1h01m · today 104.2K $7.89 │
      ╰─╯"
    `);
    expect(output).not.toContain("focused tests");
    for (const line of output.split("\n")) expect(fixtureTerminalWidth(line)).toBe(60);
  });

  test("uses the violet, warning, and danger context thresholds", () => {
    const renderAt = (usedTokens: number) => renderFooter({
      folder: "repo",
      context: { usedTokens, windowTokens: 100 },
    }, { width: 64 });

    expect(renderAt(74)).toContain("\x1b[38;2;178;102;255m74%");
    expect(renderAt(75)).toContain("\x1b[38;2;255;184;76m75%");
    expect(renderAt(90)).toContain("\x1b[38;2;255;86;110m90%");
  });

  test("renders bounded trusted prune context in the governance row", () => {
    const output = renderFooter({
      folder: "repo",
      governance: {
        stage: "implementation",
        tasks: 1,
        questions: 0,
        overrides: 0,
        prune: "checkpoint ready\u0007",
      },
    }, { width: 100, noColor: true });

    expect(output).toContain("prune:checkpoint ready");
    expect(output).not.toContain("\u0007");
  });

  test("keeps compact token, cost, duration, and cache-hit formatting bounded", () => {
    const output = plain(renderFooter({
      folder: "repo",
      session: {
        inputTokens: 999,
        outputTokens: 1_500,
        cacheReadTokens: 999_500,
        cacheWriteTokens: 500,
        costUsd: 0.001,
        ageSeconds: 4 * 86_400 + 6 * 3_600,
      },
      daily: { inputTokens: 999_500, outputTokens: 0, costUsd: 123.45 },
    }, { width: 100 }));

    expect(output).toContain("↓    999");
    expect(output).toContain("↑   1.5K");
    expect(output).toContain("<$.01");
    expect(output).toContain("cache r 1.0M w 500 hit 100%");
    expect(output).toContain("age 4d6h");
    expect(output).toContain("Today   │ ↓   1.0M ↑      0 │ $123");
  });

  test("omits missing optional segments without inventing placeholders", () => {
    const output = renderFooter({ folder: "repo" }, { width: 48, noColor: true });

    expect(layoutSnapshot(output)).toMatchInlineSnapshot(`
      "╭─ repo ─╮
      │ no git │
      ╰─╯"
    `);
    expect(output).not.toMatch(/Session|Today|cache|ctx|update|activity|stage/u);
  });

  test("has no rate-window input and ignores hostile runtime lookalikes", () => {
    const input: FooterInput = {
      folder: "repo",
      // The renderer contract intentionally cannot represent provider rate windows.
      // @ts-expect-error rate-window telemetry does not belong in FooterInput
      rateWindows: { fiveHour: "99%", sevenDay: "fabricated" },
    };

    const output = renderFooter(input, { width: 48, noColor: true });
    expect(output).not.toMatch(/99%|five|seven|fabricated|rate/iu);
  });

  test("strips control sequences before composing terminal rows", () => {
    const output = renderFooter({
      folder: "repo\nspoof\x1b]8;;https://evil.example\x07link\x1b]8;;\x07",
      git: { branch: "main\x1b[2J\rowned" },
      model: { name: "safe\x00model" },
      activity: [{ kind: "job", label: "work\x1b[31mred", state: "active" }],
    }, { width: 72, noColor: true });

    expect(output).toContain("repospooflink");
    expect(output).toContain("mainowned");
    expect(output).toContain("safemodel");
    expect(output).toContain("workred");
    expect(output).not.toMatch(/[\u0000-\u0009\u000b-\u001f\u007f\u009b]/u);
  });

  test("honors NO_COLOR explicitly without changing layout width", () => {
    const colored = renderFooter(WIDE_INPUT, { width: 80 });
    const noColor = renderFooter(WIDE_INPUT, { width: 80, noColor: true });

    expect(colored).toContain("\x1b[");
    expect(noColor).not.toContain("\x1b[");
    expect(plain(colored)).toBe(noColor);
  });

  test("isolates one failing segment and keeps the remaining footer usable", () => {
    const hostile = {
      folder: "repo",
      get git(): never { throw new Error("git unavailable"); },
      model: { name: "Claude Sonnet", thinking: "high" },
      session: { inputTokens: 10, outputTokens: 5, costUsd: 0.02 },
      context: { usedTokens: 20, windowTokens: 100 },
    } as FooterInput;

    const output = plain(renderFooter(hostile, { width: 72 }));
    expect(output).toContain("Claude Sonnet │ High");
    expect(output).toContain("Session");
    expect(output).toContain("ctx");
    expect(output).not.toContain("footer unavailable");
  });

  test("returns a bounded minimal safe line after an outer render failure", () => {
    const hostileOptions = new Proxy({} as FooterRenderOptions, {
      get(): never { throw new Error("options unavailable"); },
    });

    const output = renderFooter({ folder: "repo" }, hostileOptions);
    expect(output).toBe("codeArbiter footer unavailable");
    expect(fixtureTerminalWidth(output)).toBeLessThanOrEqual(60);
  });

  test("clamps invalid runtime numbers and every rendered row to the normalized width", () => {
    const output = renderFooter({
      folder: "界".repeat(80),
      session: {
        inputTokens: Number.POSITIVE_INFINITY,
        outputTokens: -500,
        cacheReadTokens: 1e100,
        cacheWriteTokens: Number.NaN,
        costUsd: -10,
        ageSeconds: 1e100,
      },
      context: { usedTokens: 1e100, windowTokens: -1 },
      governance: { stage: "x".repeat(10_000), tasks: -2, questions: 1e100, overrides: Number.NaN },
    } as FooterInput, { width: 42, noColor: true });

    expect(output).not.toMatch(/Infinity|NaN|-500|-10/u);
    expect(output).not.toMatch(/[\u0000-\u0009\u000b-\u001f\u007f\u009b]/u);
    for (const line of output.split("\n")) expect(fixtureTerminalWidth(line)).toBe(42);
  });

  test.each([
    ["combining accent", "e\u0301", 1],
    ["copyright text", "©", 1],
    ["trademark text", "™", 1],
    ["text heart", "❤", 1],
    ["VS16 heart", "❤️", 2],
    ["keycap", "1\ufe0f\u20e3", 2],
    ["skin-tone emoji", "👍🏽", 2],
    ["ZWJ family", "👨‍👩‍👧‍👦", 2],
    ["regional-indicator flag", "🇺🇸", 2],
    ["Tangut ideograph", "𗀀", 2],
  ])("measures a %s grapheme at its known terminal width", (_name, grapheme, expectedWidth) => {
    expect(FIXTURE_WIDTHS.get(grapheme)).toBe(expectedWidth);
    const output = renderFooter({ folder: `a${grapheme}b` }, { width: 24, noColor: true });
    expect(output).toContain(`a${grapheme}b`);
    for (const line of output.split("\n")) expect(fixtureTerminalWidth(line)).toBe(24);
  });

  test("delegates every conflicting measurement and truncation decision to the supplied port", () => {
    const customWidths = new Map(FIXTURE_WIDTHS);
    customWidths.set("©", 4);
    customWidths.set("™", 3);
    customWidths.set("❤", 2);
    const visibleWidth = vi.fn((text: string) => fixtureTerminalWidth(text, customWidths));
    const truncateToWidth = vi.fn((text: string, width: number, suffix: string) =>
      fixtureTruncate(text, width, suffix, customWidths));
    const metrics: FooterTextMetrics = { visibleWidth, truncateToWidth };

    const output = renderFooter({ folder: "©™❤❤️𗀀👨‍👩‍👧‍👦1️⃣🇺🇸".repeat(4) }, {
      width: 24,
      noColor: true,
    }, metrics);

    expect(visibleWidth).toHaveBeenCalled();
    expect(truncateToWidth).toHaveBeenCalled();
    expect(truncateToWidth).toHaveBeenCalledWith(expect.any(String), expect.any(Number), "…");
    for (const line of output.split("\n")) expect(visibleWidth(line)).toBe(24);
  });

  test("honors narrow valid widths and degrades safely at extremely small or invalid widths", () => {
    for (const width of [8, 12, 24, 39]) {
      const output = renderFooter({ folder: "narrow" }, { width, noColor: true });
      for (const line of output.split("\n")) expect(fixtureTerminalWidth(line)).toBe(width);
    }
    expect(renderFooter({ folder: "repo" }, { width: 3, noColor: true })).toBe("co…");
    expect(renderFooter({ folder: "repo" }, { width: 1, noColor: true })).toBe("…");
    expect(renderFooter({ folder: "repo" }, { width: 0, noColor: true })).toBe("");
    expect(renderFooter({ folder: "repo" }, { width: -1, noColor: true })).toBe("");
    expect(renderFooter({ folder: "repo" }, { width: Number.NaN, noColor: true })).toBe("");
  });

  test("keeps the minimal fallback within a width read before a later option failure", () => {
    const options = {
      width: 8,
      get compact(): never { throw new Error("compact option unavailable"); },
    } as FooterRenderOptions;

    const output = renderFooter({ folder: "repo" }, options);
    expect(fixtureTerminalWidth(output)).toBeLessThanOrEqual(8);
  });

  test("compact mode omits only a session segment whose nested getter throws", () => {
    const input = {
      folder: "repo",
      git: { branch: "main" },
      model: { name: "Claude Sonnet", thinking: "high" },
      context: { usedTokens: 20, windowTokens: 100 },
      session: {
        get inputTokens(): never { throw new Error("session unavailable"); },
        outputTokens: 5,
        costUsd: 0.02,
      },
    } as FooterInput;

    const output = plain(renderFooter(input, { width: 60, compact: true }));
    expect(output).toContain("git main");
    expect(output).toContain("Claude Sonnet │ High");
    expect(output).toContain("ctx 20%");
    expect(output).not.toMatch(/sess|footer unavailable/u);
  });

  test("compact mode omits only a daily segment whose nested getter throws", () => {
    const input = {
      folder: "repo",
      git: { branch: "main" },
      model: { name: "Claude Sonnet", thinking: "high" },
      context: { usedTokens: 20, windowTokens: 100 },
      daily: {
        get inputTokens(): never { throw new Error("daily unavailable"); },
        outputTokens: 5,
        costUsd: 0.02,
      },
    } as FooterInput;

    const output = plain(renderFooter(input, { width: 60, compact: true }));
    expect(output).toContain("git main");
    expect(output).toContain("Claude Sonnet │ High");
    expect(output).toContain("ctx 20%");
    expect(output).not.toMatch(/today|footer unavailable/u);
  });
});

function assistantEntry(input: number, output: number, cost: number, cacheRead = 0, cacheWrite = 0) {
  return {
    type: "message",
    message: {
      role: "assistant",
      usage: { input, output, cacheRead, cacheWrite, cost: { total: cost } },
    },
  };
}

function baseContext(entries: unknown[]) {
  return {
    cwd: "C:/work/codearbiter",
    signal: undefined,
    ui: { setStatus() {}, notify() {} },
    model: { provider: "anthropic", id: "claude-opus-4-8", contextWindow: 200_000 },
    sessionManager: {
      getSessionName: () => "fallback name",
      getHeader: () => ({ timestamp: "2026-07-18T10:59:00-04:00" }),
      getEntries: () => entries,
    },
    getContextUsage: () => ({ tokens: 136_000, contextWindow: 200_000, percent: 68 }),
  };
}

describe("Pi footer state adapter", () => {
  test("exports only the pure adapter and contains no filesystem or crypto capability", () => {
    expect(Object.keys(footerStateModule).sort()).toEqual(["adaptPiFooterState"]);
    const source = readFileSync(new URL("../src/footer-state.ts", import.meta.url), "utf8");

    expect(source).not.toMatch(/node:(?:fs|path|os|crypto)/u);
    expect(source).not.toMatch(/createPiUsageLedger|resolvePiUsageLedgerPath|readFile|writeFile|lock|shard/iu);
  });

  test("normalizes all source-verified Pi facts without a usage snapshot", () => {
    const input = adaptPiFooterState({
      pi: { getSessionName: () => "parity sprint", getThinkingLevel: () => "xhigh" },
      context: baseContext([assistantEntry(12_345, 4_567, 1.234, 2_500, 600)]),
      footerData: { getGitBranch: () => "feat/pi" },
      now: new Date("2026-07-18T12:00:00-04:00"),
      updateVersion: "0.80.11",
    });

    expect(input).toEqual({
      folder: "C:/work/codearbiter",
      sessionName: "parity sprint",
      git: { branch: "feat/pi" },
      model: { name: "claude-opus-4-8", provider: "anthropic", thinking: "xhigh" },
      session: {
        inputTokens: 12_345,
        outputTokens: 4_567,
        cacheReadTokens: 2_500,
        cacheWriteTokens: 600,
        costUsd: 1.234,
        ageSeconds: 3_660,
      },
      context: { usedTokens: 136_000, windowTokens: 200_000 },
      update: { version: "0.80.11" },
    });
  });

  test("maps a bounded composition-owned usage snapshot into session and today totals", () => {
    const input = adaptPiFooterState({
      pi: { getThinkingLevel: () => "high" },
      context: baseContext([assistantEntry(1, 1, 0.01)]),
      footerData: { getGitBranch: () => "main" },
      now: new Date("2026-07-18T12:00:00-04:00"),
      usageSnapshot: {
        session: {
          inputTokens: 20,
          outputTokens: 8,
          cacheReadTokens: 5,
          cacheWriteTokens: 2,
          costUsd: 2.5,
        },
        today: { inputTokens: 100, outputTokens: 30, costUsd: 7.25 },
      },
    });

    expect(input.session).toEqual({
      inputTokens: 20,
      outputTokens: 8,
      cacheReadTokens: 5,
      cacheWriteTokens: 2,
      costUsd: 2.5,
      ageSeconds: 3_660,
    });
    expect(input.daily).toEqual({ inputTokens: 100, outputTokens: 30, costUsd: 7.25 });
  });

  test("omits malformed today data and falls back to Pi-owned session entries", () => {
    const input = adaptPiFooterState({
      pi: {},
      context: baseContext([assistantEntry(4, 2, 0.1, 1, 3)]),
      footerData: {},
      now: new Date("2026-07-18T12:00:00-04:00"),
      usageSnapshot: {
        session: { inputTokens: "bad", outputTokens: 9, costUsd: 1 },
        today: { inputTokens: 10, outputTokens: "bad", costUsd: 1 },
      } as never,
    });

    expect(input.session).toEqual({
      inputTokens: 4,
      outputTokens: 2,
      cacheReadTokens: 1,
      cacheWriteTokens: 3,
      costUsd: 0.1,
      ageSeconds: 3_660,
    });
    expect(input).not.toHaveProperty("daily");
  });

  test("bounds hostile numeric snapshot values without exposing non-finite totals", () => {
    const input = adaptPiFooterState({
      pi: {},
      context: baseContext([]),
      footerData: {},
      now: new Date("2026-07-18T12:00:00-04:00"),
      usageSnapshot: {
        session: {
          inputTokens: -1,
          outputTokens: Number.POSITIVE_INFINITY,
          cacheReadTokens: Number.NaN,
          cacheWriteTokens: 1e100,
          costUsd: -5,
        },
        today: {
          inputTokens: Number.NaN,
          outputTokens: -10,
          costUsd: Number.POSITIVE_INFINITY,
        },
      },
    });

    expect(input.session).toEqual({
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 1_000_000_000_000_000,
      costUsd: 0,
      ageSeconds: 3_660,
    });
    expect(input.daily).toEqual({ inputTokens: 0, outputTokens: 0, costUsd: 0 });
  });

  test("runtime-guards missing or hostile members and preserves method receivers", () => {
    const pi = {
      name: "receiver session",
      getSessionName() { return this.name; },
      getThinkingLevel() { throw new Error("not available"); },
    };
    const footerData = { branch: "main", getGitBranch() { return this.branch; } };
    const input = adaptPiFooterState({
      pi,
      context: {
        cwd: "\n",
        signal: undefined,
        ui: { setStatus() {}, notify() {} },
        model: { provider: 42, id: "\u001b[2Jmodel", contextWindow: Number.POSITIVE_INFINITY },
        sessionManager: {
          getEntries: () => [assistantEntry(-1, Number.NaN, -2, Number.POSITIVE_INFINITY, 3)],
        },
        getContextUsage: () => { throw new Error("not available"); },
      },
      footerData,
      now: new Date("2026-07-18T12:00:00-04:00"),
      updateVersion: "bad\nversion",
    });

    expect(input).toEqual({
      folder: ".",
      sessionName: "receiver session",
      git: { branch: "main" },
      model: { name: "model" },
      session: {
        inputTokens: 0,
        outputTokens: 0,
        cacheReadTokens: 0,
        cacheWriteTokens: 3,
        costUsd: 0,
      },
      update: { version: "badversion" },
    });
    expect(input).not.toHaveProperty("governance");
    expect(input).not.toHaveProperty("activity");
  });

  test("projects session activity without allowing snapshot failure to break other footer facts", () => {
    const active = adaptPiFooterState({
      pi: {},
      context: baseContext([]),
      footerData: { getGitBranch: () => "main" },
      activity: { snapshot: () => [{ kind: "job", label: "tests", state: "active", ageSeconds: 3 }] },
    });
    expect(active.activity).toEqual([{ kind: "job", label: "tests", state: "active", ageSeconds: 3 }]);

    const failed = adaptPiFooterState({
      pi: {},
      context: baseContext([]),
      footerData: { getGitBranch: () => "main" },
      activity: { snapshot: () => { throw new Error("display unavailable"); } },
    });
    expect(failed.folder).toBe("C:/work/codearbiter");
    expect(failed.git).toEqual({ branch: "main" });
    expect(failed).not.toHaveProperty("activity");
  });
});
