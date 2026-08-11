/**
 * sidebar-window-contract.test.ts — AC-7 fixture contracts: the compositor's
 * hook probe exercised against each promoted window version's captured render
 * surface. The shapes below are source-verified, not guessed:
 *
 * - 0.80.5 window: `@earendil-works/pi-tui` (0.80.10, the current `^0.80.5`
 *   resolution pinned by Pi 0.80.5) exports one `TUI` class whose `doRender`
 *   is a prototype method (`dist/tui.js:976`; TypeScript-private, so it is
 *   runtime-present but absent from the declared API) and exports
 *   `visibleWidth`/`truncateToWidth` from `dist/utils.ts`.
 * - 0.84.1 window: `@earendil-works/pi-tui` exports `TuiMainScreen` and
 *   `TuiAltScreen`, each implementing `doRender` as an own prototype method;
 *   the runtime fullscreen switch swaps between these two surfaces.
 *
 * Because `doRender` is undeclared (private/protected) in BOTH versions, this
 * surface is runtime-guarded by the probe, never source-verified API — the
 * boundary note in src/pi-api.d.ts records the same fact.
 */
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

function terminal(columns = 200): { columns: number; rows: number } {
  const value: Record<string, unknown> = { rows: 50 };
  Object.defineProperty(value, "columns", {
    value: columns,
    writable: true,
    configurable: true,
    enumerable: true,
  });
  return value as unknown as { columns: number; rows: number };
}

/** 0.80.5 window: one TUI class, doRender inherited from the prototype. */
class Tui080Shape {
  renders = 0;
  doRender(): void {
    this.renders += 1;
  }

  requestRender(): void {
    this.doRender();
  }
}

/** 0.84.1 window: two screen classes; the fullscreen switch swaps surfaces. */
class TuiMainScreenShape {
  renders = 0;
  doRender(): void {
    this.renders += 1;
  }

  requestRender(): void {
    this.doRender();
  }
}
class TuiAltScreenShape extends TuiMainScreenShape {}

function ports(tui: { doRender(): void; requestRender(): void }, term: object): SidebarCompositorPorts {
  return {
    tui,
    terminal: term as { columns?: unknown; rows?: unknown },
    metrics,
    writeOut: () => undefined,
    notify: () => undefined,
    dataSource: () => ({ session: { model: "contract" } }),
    noColor: true,
  };
}

describe("sidebar probe against the 0.80.5 window surface (AC-7)", () => {
  test("probe passes on the single prototype-doRender TUI class shape", () => {
    const tui = new Tui080Shape();
    expect(Object.prototype.hasOwnProperty.call(tui, "doRender")).toBe(false);
    expect(probeSidebarSupport(tui, terminal(), metrics).ok).toBe(true);
  });

  test("install wraps the inherited doRender and dispose restores it exactly", () => {
    const tui = new Tui080Shape();
    const original = tui.doRender;
    const compositor = installSidebar(ports(tui, terminal()), { width: 40 });
    expect(compositor.installed).toBe(true);
    expect(tui.doRender).not.toBe(original);
    compositor.dispose();
    expect(tui.doRender).toBe(Tui080Shape.prototype.doRender);
  });
});

describe("sidebar probe against the 0.84.1 window surface (AC-7)", () => {
  test("probe passes on both screen-class shapes", () => {
    for (const tui of [new TuiMainScreenShape(), new TuiAltScreenShape()]) {
      expect(probeSidebarSupport(tui, terminal(), metrics).ok).toBe(true);
    }
  });

  test("the runtime fullscreen switch disposes via geometry re-validation", () => {
    const tui = new TuiMainScreenShape();
    const term = terminal(200);
    const compositor = installSidebar(ports(tui, term), { width: 40 });
    expect(compositor.installed).toBe(true);
    // The alt-screen switch replaces the render surface: `columns` gains a
    // foreign descriptor the compositor did not install.
    Object.defineProperty(term, "columns", { get: () => 200, configurable: true });
    tui.doRender();
    tui.doRender();
    tui.doRender();
    expect(compositor.installed).toBe(false);
  });

  test("a probe against a future surface without doRender fails closed", () => {
    const gone = { requestRender: () => undefined } as { doRender?: unknown; requestRender(): void };
    expect(probeSidebarSupport(gone, terminal(), metrics)).toMatchObject({ ok: false, reason: "no-dorender" });
  });
});
