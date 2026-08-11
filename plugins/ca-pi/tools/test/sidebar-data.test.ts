import { describe, expect, test } from "vitest";

import { sidebarInputFromFooter, sidebarTodosFromPlan } from "../src/sidebar-data.ts";
import type { FooterInput } from "../src/footer.ts";
import type { PlanSessionState } from "../src/plan-mode.ts";

const fullFooter: FooterInput = {
  folder: "C:/repo/project",
  git: { repository: "codeArbiter", branch: "main", dirty: true },
  model: { name: "gpt-test", provider: "test", thinking: "high" },
  session: { inputTokens: 1200, outputTokens: 340, costUsd: 0.0921 },
  context: { usedTokens: 42_000, windowTokens: 100_000 },
  activity: [
    { kind: "child", label: "backend-author", state: "active", ageSeconds: 12 },
    { kind: "job", label: "test-run", state: "completed", ageSeconds: 90 },
  ],
  sparkline: [1, 5, 3, 9, 2],
};

describe("sidebarInputFromFooter (AC-6)", () => {
  test("an absent footer maps to an empty input with no panels", () => {
    expect(sidebarInputFromFooter(undefined)).toEqual({});
  });

  test("session panel mirrors the footer facts without new sources", () => {
    const input = sidebarInputFromFooter(fullFooter);
    expect(input.session).toMatchObject({
      model: "gpt-test",
      thinkingLevel: "high",
      contextPercent: 42,
      inputTokens: 1200,
      outputTokens: 340,
      costUsd: 0.0921,
    });
    expect(input.session?.burn).toEqual([1, 5, 3, 9, 2]);
  });

  test("context percent is omitted when the window is unknown or zero", () => {
    const zeroWindow = sidebarInputFromFooter({
      folder: "x",
      model: { name: "m" },
      context: { usedTokens: 10, windowTokens: 0 },
    });
    expect(zeroWindow.session?.contextPercent).toBeUndefined();
    const noContext = sidebarInputFromFooter({ folder: "x", model: { name: "m" } });
    expect(noContext.session?.contextPercent).toBeUndefined();
  });

  test("subagent rows pass through kind, label, state and age", () => {
    const input = sidebarInputFromFooter(fullFooter);
    expect(input.subagents).toEqual([
      { kind: "child", label: "backend-author", state: "active", ageSeconds: 12 },
      { kind: "job", label: "test-run", state: "completed", ageSeconds: 90 },
    ]);
  });

  test("workspace renders only when the trust-gated git facts are present", () => {
    const trusted = sidebarInputFromFooter(fullFooter);
    expect(trusted.workspace).toEqual({ cwd: "C:/repo/project", repository: "codeArbiter", dirty: true });
    const untrusted = sidebarInputFromFooter({ folder: "C:/repo/project", model: { name: "m" } });
    expect(untrusted.workspace).toBeUndefined();
  });

  test("no panel key is emitted for an absent source", () => {
    const input = sidebarInputFromFooter({ folder: "x" });
    expect(Object.keys(input)).toEqual([]);
  });
});

function planState(tasks: PlanSessionState["activePlan"]["tasks"]): PlanSessionState {
  return {
    version: 1,
    revision: 1,
    mode: "plan",
    activePlan: {
      slug: "demo",
      specPath: "specs/demo.md",
      planPath: "plans/demo.md",
      ledgerPath: "plans/demo.md",
      disposition: "approved",
      tasks,
    },
  };
}

describe("sidebarTodosFromPlan (AC-6)", () => {
  test("maps ledger statuses onto todo states", () => {
    expect(sidebarTodosFromPlan(planState([
      { id: "T1", status: "PENDING" },
      { id: "T2", status: "IN_PROGRESS" },
      { id: "T3", status: "ACCEPTED" },
    ]))).toEqual([
      { text: "T1", state: "open" },
      { text: "T2", state: "active" },
      { text: "T3", state: "done" },
    ]);
  });

  test("no plan session or an empty ledger yields no todos panel", () => {
    expect(sidebarTodosFromPlan(undefined)).toBeUndefined();
    expect(sidebarTodosFromPlan(planState([]))).toBeUndefined();
  });
});
