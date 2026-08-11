import { describe, expect, test } from "vitest";

import { installSidebar, probeSidebarSupport } from "../src/sidebar-compositor.ts";
import type { SidebarCompositorPorts } from "../src/sidebar-compositor.ts";

const metrics = {
  visibleWidth: (text: string) => text.replace(/\x1b\[[0-9;]*m/gu, "").length,
  truncateToWidth: (text: string, width: number, suffix: string) => {
    const plain = text.replace(/\x1b\[[0-9;]*m/gu, "");
    return plain.length <= width ? text : plain.slice(0, Math.max(0, width - suffix.length)) + suffix;
  },
};

interface Harness {
  readonly ports: SidebarCompositorPorts;
  readonly terminal: { columns: number; rows: number };
  readonly writes: string[];
  readonly notices: string[];
  renderNative(): void;
  nativeRenders: () => number;
}

function harness(overrides?: {
  columns?: number;
  rows?: number;
  configurableColumns?: boolean;
  doRender?: unknown;
  dataSource?: SidebarCompositorPorts["dataSource"];
}): Harness {
  let nativeRenderCount = 0;
  const terminal: Record<string, unknown> = { rows: overrides?.rows ?? 50 };
  Object.defineProperty(terminal, "columns", {
    value: overrides?.columns ?? 200,
    writable: true,
    configurable: overrides?.configurableColumns ?? true,
    enumerable: true,
  });
  const tui: Record<string, unknown> = {
    doRender: overrides && "doRender" in overrides ? overrides.doRender : () => { nativeRenderCount += 1; },
    requestRender: () => { nativeRenderCount += 1; },
  };
  const writes: string[] = [];
  const notices: string[] = [];
  const ports: SidebarCompositorPorts = {
    tui: tui as unknown as SidebarCompositorPorts["tui"],
    terminal: terminal as unknown as SidebarCompositorPorts["terminal"],
    metrics,
    writeOut: (text) => { writes.push(text); },
    notify: (message) => { notices.push(message); },
    dataSource: overrides?.dataSource ?? (() => ({ session: { model: "gpt-test" } })),
    noColor: true,
  };
  return {
    ports,
    terminal: terminal as unknown as { columns: number; rows: number },
    writes,
    notices,
    renderNative: () => { (tui.doRender as () => void)(); },
    nativeRenders: () => nativeRenderCount,
  };
}

describe("sidebar compositor probe (AC-2)", () => {
  test("probe passes on a conforming tui/terminal and fails closed on each missing hook", () => {
    const good = harness();
    expect(probeSidebarSupport(good.ports.tui, good.ports.terminal, metrics).ok).toBe(true);

    const noRender = harness({ doRender: undefined });
    expect(probeSidebarSupport(noRender.ports.tui, noRender.ports.terminal, metrics)).toMatchObject({ ok: false, reason: "no-dorender" });

    const sealed = harness({ configurableColumns: false });
    expect(probeSidebarSupport(sealed.ports.tui, sealed.ports.terminal, metrics)).toMatchObject({ ok: false, reason: "columns-not-configurable" });

    const badMetrics = { visibleWidth: undefined, truncateToWidth: metrics.truncateToWidth } as never;
    expect(probeSidebarSupport(good.ports.tui, good.ports.terminal, badMetrics)).toMatchObject({ ok: false, reason: "no-metrics" });
  });

  test("a failed probe leaves native rendering untouched", () => {
    const sealed = harness({ configurableColumns: false });
    const result = installSidebar(sealed.ports, { width: 40 });
    expect(result.installed).toBe(false);
    expect(sealed.terminal.columns).toBe(200);
    sealed.renderNative();
    expect(sealed.nativeRenders()).toBe(1);
    expect(sealed.writes).toEqual([]);
  });

  test("install refuses when the raw terminal is narrower than width + 60", () => {
    const narrow = harness({ columns: 90 });
    const result = installSidebar(narrow.ports, { width: 40 });
    expect(result.installed).toBe(false);
    expect(narrow.terminal.columns).toBe(90);
  });
});

describe("sidebar compositor paint (AC-3)", () => {
  test("perceived columns shrink by width + 1 while raw geometry drives the paint", () => {
    const h = harness({ columns: 200 });
    const compositor = installSidebar(h.ports, { width: 40 });
    expect(compositor.installed).toBe(true);
    expect(h.terminal.columns).toBe(200 - 41);
    compositor.dispose();
    expect(h.terminal.columns).toBe(200);
  });

  test("each native render is followed by one synchronized-output sidebar paint", () => {
    const h = harness();
    const compositor = installSidebar(h.ports, { width: 40 });
    expect(compositor.installed).toBe(true);
    h.renderNative();
    const paint = h.writes.join("");
    expect(paint).toContain("\x1b[?2026h");
    expect(paint).toContain("\x1b[?2026l");
    expect(paint).toContain("\x1b7");
    expect(paint).toContain("\x1b8");
    expect(paint).toContain("\x1b[?7l");
    expect(paint).toContain("\x1b[?7h");
    expect(paint).toContain("gpt-test");
    expect(paint).toContain("│");
    compositor.dispose();
  });

  test("a failed geometry re-validation skips the paint and persistent failure disposes", () => {
    const h = harness({ columns: 200 });
    const compositor = installSidebar(h.ports, { width: 40 });
    expect(compositor.installed).toBe(true);
    // Fullscreen-style surface change: raw width collapses under the floor.
    Object.defineProperty(h.ports.terminal, "columns", {
      get: () => 80,
      configurable: true,
    });
    h.writes.length = 0;
    h.renderNative();
    expect(h.writes.join("")).toBe("");
    expect(compositor.installed).toBe(true);
    h.renderNative();
    h.renderNative();
    expect(compositor.installed).toBe(false);
  });
});

describe("sidebar compositor dispose (AC-4)", () => {
  test("dispose restores the original descriptor and doRender and requests a native re-render", () => {
    const h = harness({ columns: 200 });
    const original = h.ports.tui.doRender;
    const compositor = installSidebar(h.ports, { width: 40 });
    expect(compositor.installed).toBe(true);
    expect(h.ports.tui.doRender).not.toBe(original);
    const rendersBefore = h.nativeRenders();
    compositor.dispose();
    expect(h.ports.tui.doRender).toBe(original);
    expect(h.terminal.columns).toBe(200);
    expect(h.nativeRenders()).toBeGreaterThan(rendersBefore);
    compositor.dispose();
    expect(h.terminal.columns).toBe(200);
  });

  test("a throwing paint auto-disposes with a single bounded warning", () => {
    const h = harness({
      dataSource: () => { throw new Error("hostile data source"); },
    });
    const compositor = installSidebar(h.ports, { width: 40 });
    expect(compositor.installed).toBe(true);
    h.renderNative();
    expect(compositor.installed).toBe(false);
    expect(h.terminal.columns).toBe(200);
    h.renderNative();
    h.renderNative();
    expect(h.notices.length).toBe(1);
  });

  test("the wrapped doRender never breaks the native render even while disposing", () => {
    const h = harness({
      dataSource: () => { throw new Error("hostile data source"); },
    });
    installSidebar(h.ports, { width: 40 });
    expect(() => h.renderNative()).not.toThrow();
    // The native render ran; auto-dispose may legitimately request one more.
    expect(h.nativeRenders()).toBeGreaterThanOrEqual(1);
  });

  test("setWidth clamps to 24..60 and reinstalls the narrowed columns", () => {
    const h = harness({ columns: 200 });
    const compositor = installSidebar(h.ports, { width: 40 });
    compositor.setWidth(999);
    expect(h.terminal.columns).toBe(200 - 61);
    compositor.setWidth(1);
    expect(h.terminal.columns).toBe(200 - 25);
    compositor.dispose();
  });
});
