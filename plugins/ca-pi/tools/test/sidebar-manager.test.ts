import { describe, expect, test } from "vitest";

import { createSidebarManager, SIDEBAR_AUTO_ON_MIN_COLUMNS } from "../src/sidebar-manager.ts";
import type { SidebarManagerPorts } from "../src/sidebar-manager.ts";
import type { ExtensionContextPort } from "../src/contracts.ts";

const metrics = {
  visibleWidth: (text: string) => text.replace(/\x1b\[[0-9;]*m/gu, "").length,
  truncateToWidth: (text: string, width: number, suffix: string) => {
    const plain = text.replace(/\x1b\[[0-9;]*m/gu, "");
    return plain.length <= width ? text : plain.slice(0, Math.max(0, width - suffix.length)) + suffix;
  },
};

interface Harness {
  readonly ports: SidebarManagerPorts;
  readonly terminal: { columns: number; rows: number };
  readonly notices: string[];
  readonly registrations: Map<string, (args: string, context: ExtensionContextPort) => unknown>;
  readonly registerCalls: () => number;
  context(overrides?: Partial<{ mode: string; hasUI: boolean; trusted: boolean }>): ExtensionContextPort;
  command(args: string, context?: ExtensionContextPort): Promise<void>;
  setTuiPresent(present: boolean): void;
}

function harness(overrides?: {
  columns?: number;
  configurableColumns?: boolean;
  tuiPresent?: boolean;
}): Harness {
  const terminal: Record<string, unknown> = { rows: 50 };
  Object.defineProperty(terminal, "columns", {
    value: overrides?.columns ?? 200,
    writable: true,
    configurable: overrides?.configurableColumns ?? true,
    enumerable: true,
  });
  const tui = { doRender: () => undefined, requestRender: () => undefined };
  let tuiPresent = overrides?.tuiPresent ?? true;
  const notices: string[] = [];
  const registrations = new Map<string, (args: string, context: ExtensionContextPort) => unknown>();
  let registerCallCount = 0;
  const makeContext = (contextOverrides?: Partial<{ mode: string; hasUI: boolean; trusted: boolean }>): ExtensionContextPort => ({
    cwd: "C:/repo",
    hasUI: contextOverrides?.hasUI ?? true,
    mode: (contextOverrides?.mode ?? "tui") as ExtensionContextPort["mode"],
    isProjectTrusted: () => contextOverrides?.trusted ?? true,
    ui: {
      notify: (message: string) => { notices.push(message); },
      setStatus: () => undefined,
    },
  } as unknown as ExtensionContextPort);
  const ports: SidebarManagerPorts = {
    pi: {
      registerCommand: (name, options) => {
        registerCallCount += 1;
        registrations.set(name, options.handler);
      },
    },
    currentTui: () => (tuiPresent ? tui : undefined),
    terminal: () => terminal as unknown as { columns?: unknown; rows?: unknown },
    loadMetrics: async () => metrics,
    dataSource: () => ({ session: { model: "gpt-test" } }),
    writeOut: () => undefined,
    noColor: () => true,
  };
  return {
    ports,
    terminal: terminal as unknown as { columns: number; rows: number },
    notices,
    registrations,
    registerCalls: () => registerCallCount,
    context: makeContext,
    command: async (args, context) => {
      const handler = registrations.get("ca-sidebar");
      if (handler === undefined) throw new Error("ca-sidebar not registered");
      await handler(args, context ?? makeContext());
    },
    setTuiPresent: (present) => { tuiPresent = present; },
  };
}

describe("sidebar manager registration (AC-5)", () => {
  test("registers /ca-sidebar once in an interactive parent and never twice", () => {
    const h = harness();
    const manager = createSidebarManager(h.ports);
    expect(manager.register(h.context())).toBe(true);
    expect(manager.register(h.context())).toBe(true);
    expect(h.registerCalls()).toBe(1);
    expect(h.registrations.has("ca-sidebar")).toBe(true);
  });

  test("refuses every non-interactive context without registering or painting", () => {
    for (const overrides of [
      { mode: "rpc" },
      { mode: "json" },
      { mode: "print" },
      { hasUI: false },
      { trusted: false },
    ]) {
      const h = harness();
      const manager = createSidebarManager(h.ports);
      expect(manager.register(h.context(overrides))).toBe(false);
      expect(h.registrations.size).toBe(0);
      expect(manager.health().expected).toBe(false);
    }
  });
});

describe("sidebar manager auto-install (AC-5)", () => {
  test("auto-installs at or above the 120-column threshold", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(true);
    expect(h.terminal.columns).toBe(200 - 41);
    manager.dispose();
  });

  test("installs at exactly the 120-column boundary", async () => {
    const h = harness({ columns: SIDEBAR_AUTO_ON_MIN_COLUMNS });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(true);
    manager.dispose();
  });

  test("stays off below 120 columns and does not re-decide", async () => {
    const h = harness({ columns: SIDEBAR_AUTO_ON_MIN_COLUMNS - 1 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(false);
    expect(h.terminal.columns).toBe(SIDEBAR_AUTO_ON_MIN_COLUMNS - 1);
    h.terminal.columns = 200;
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(false);
  });

  test("retries while the tui handle is not yet available", async () => {
    const h = harness({ columns: 200, tuiPresent: false });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(false);
    h.setTuiPresent(true);
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(true);
    manager.dispose();
  });

  test("never auto-installs again after the user turned it off", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    await h.command("off");
    expect(manager.health().installed).toBe(false);
    await manager.autoInstall(h.context());
    expect(manager.health().installed).toBe(false);
  });
});

describe("/ca-sidebar command (AC-5)", () => {
  test("on installs, off disposes and restores, toggle flips", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await h.command("on");
    expect(manager.health().installed).toBe(true);
    expect(h.terminal.columns).toBe(200 - 41);
    await h.command("off");
    expect(manager.health().installed).toBe(false);
    expect(h.terminal.columns).toBe(200);
    await h.command("toggle");
    expect(manager.health().installed).toBe(true);
    await h.command("toggle");
    expect(manager.health().installed).toBe(false);
    expect(h.terminal.columns).toBe(200);
  });

  test("width N applies with 24..60 clamping and persists for a later install", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await h.command("on");
    await h.command("width 50");
    expect(h.terminal.columns).toBe(200 - 51);
    await h.command("width 999");
    expect(h.terminal.columns).toBe(200 - 61);
    await h.command("off");
    await h.command("width 30");
    await h.command("on");
    expect(h.terminal.columns).toBe(200 - 31);
    manager.dispose();
  });

  test("invalid arguments produce a syntax notice and change nothing", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await h.command("on");
    h.notices.length = 0;
    await h.command("width abc");
    await h.command("frobnicate");
    expect(h.notices.length).toBe(2);
    expect(h.terminal.columns).toBe(200 - 41);
    manager.dispose();
  });

  test("on reports the probe reason when the sidebar is unavailable", async () => {
    const h = harness({ configurableColumns: false });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await h.command("on");
    expect(manager.health().installed).toBe(false);
    expect(manager.health().reason).toBe("columns-not-configurable");
    expect(h.notices.join("\n")).toContain("columns-not-configurable");
  });
});

describe("sidebar manager lifecycle (AC-4/AC-5)", () => {
  test("dispose restores native rendering and resets session state", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    manager.register(h.context());
    await manager.autoInstall(h.context());
    expect(h.terminal.columns).toBe(200 - 41);
    manager.dispose();
    expect(h.terminal.columns).toBe(200);
    expect(manager.health().installed).toBe(false);
    manager.dispose();
    expect(h.terminal.columns).toBe(200);
  });

  test("health reports expected, installed and reason for the doctor row", async () => {
    const h = harness({ columns: 200 });
    const manager = createSidebarManager(h.ports);
    expect(manager.health()).toMatchObject({ expected: false, installed: false });
    manager.register(h.context());
    expect(manager.health().expected).toBe(true);
    await manager.autoInstall(h.context());
    expect(manager.health()).toMatchObject({ expected: true, installed: true, degraded: false });
    manager.dispose();
  });
});
