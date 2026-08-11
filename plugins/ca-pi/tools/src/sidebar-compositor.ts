/** Sidebar compositor (spec pi-sidebar-panel AC-2/AC-3/AC-4).
 *
 * Re-implements pi-sidebar-tui's proven mechanism inside the adapter,
 * dependency-free: narrow the terminal's perceived width by redefining the
 * `columns` getter, wrap `tui.doRender` to paint the sidebar column with
 * synchronized output after every host render. Both hook points are
 * undocumented Pi surface, so installation is probe-gated and every failure
 * path disposes back to native rendering — the sidebar may degrade to
 * unavailable on a future Pi, but it can never wedge the terminal.
 */

import { renderSidebar } from "./sidebar.ts";
import type { SidebarInput } from "./sidebar.ts";
import type { FooterTextMetrics } from "./footer.ts";

export const SIDEBAR_DEFAULT_WIDTH = 40;
export const SIDEBAR_MIN_WIDTH = 24;
export const SIDEBAR_MAX_WIDTH = 60;
/** The compositor refuses to install (or paint) when the raw terminal is
 * narrower than width + this floor, leaving Pi a usable main column. */
export const SIDEBAR_MAIN_COLUMN_FLOOR = 60;
/** Consecutive failed geometry re-validations before the compositor disposes
 * rather than keep painting into a surface it no longer understands. */
const GEOMETRY_FAILURE_LIMIT = 3;

const ESC = "\x1b";
const SYNC_START = `${ESC}[?2026h`;
const SYNC_END = `${ESC}[?2026l`;
const CURSOR_SAVE = `${ESC}7`;
const CURSOR_RESTORE = `${ESC}8`;
const WRAP_OFF = `${ESC}[?7l`;
const WRAP_ON = `${ESC}[?7h`;
const RESET = `${ESC}[0m`;

export interface SidebarTuiPort {
  doRender?: unknown;
  requestRender(): void;
}

export interface SidebarCompositorPorts {
  readonly tui: SidebarTuiPort;
  readonly terminal: { columns?: unknown; rows?: unknown };
  readonly metrics: FooterTextMetrics;
  readonly writeOut: (text: string) => void;
  readonly notify: (message: string) => void;
  readonly dataSource: () => SidebarInput;
  readonly noColor: boolean;
}

export type SidebarProbeResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: "no-dorender" | "columns-not-configurable" | "no-metrics" };

export interface SidebarCompositor {
  readonly installed: boolean;
  /** Present only on an unavailable result; a stable short identifier. */
  readonly reason?: string;
  setWidth(width: number): void;
  dispose(): void;
}

function unavailable(reason: string): SidebarCompositor {
  return Object.freeze({
    installed: false,
    reason,
    setWidth: () => undefined,
    dispose: () => undefined,
  });
}

function columnsDescriptor(terminal: object): PropertyDescriptor | undefined {
  let target: object | null = terminal;
  while (target !== null) {
    const descriptor = Object.getOwnPropertyDescriptor(target, "columns");
    if (descriptor !== undefined) return descriptor;
    target = Object.getPrototypeOf(target);
  }
  return undefined;
}

/** AC-2: install only when every probed hook is present and rewirable. */
export function probeSidebarSupport(
  tui: SidebarTuiPort,
  terminal: object,
  metrics: FooterTextMetrics,
): SidebarProbeResult {
  if (typeof metrics?.visibleWidth !== "function" || typeof metrics?.truncateToWidth !== "function") {
    return { ok: false, reason: "no-metrics" };
  }
  if (typeof tui?.doRender !== "function") return { ok: false, reason: "no-dorender" };
  const descriptor = columnsDescriptor(terminal);
  if (descriptor === undefined || descriptor.configurable !== true) {
    return { ok: false, reason: "columns-not-configurable" };
  }
  return { ok: true };
}

function clampWidth(width: unknown): number {
  if (typeof width !== "number" || !Number.isFinite(width)) return SIDEBAR_DEFAULT_WIDTH;
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.floor(width)));
}

interface FrozenGeometry {
  readonly rawColumns: number;
  readonly rows: number;
}

class Compositor implements SidebarCompositor {
  private active = true;
  private width: number;
  private geometryFailures = 0;
  private warned = false;
  private narrowedGetter: (() => unknown) | undefined;
  private readonly originalDescriptor: PropertyDescriptor;
  private readonly originalDoRender: (...args: unknown[]) => unknown;

  constructor(private readonly ports: SidebarCompositorPorts, width: number) {
    this.width = width;
    // Probe passed: both are known present and configurable.
    this.originalDescriptor = columnsDescriptor(ports.terminal as object) as PropertyDescriptor;
    this.originalDoRender = ports.tui.doRender as (...args: unknown[]) => unknown;
    this.defineNarrowedColumns();
    const paintAfterRender = (...args: unknown[]): unknown => {
      const result = this.originalDoRender.apply(ports.tui, args);
      this.paint();
      return result;
    };
    ports.tui.doRender = paintAfterRender;
  }

  get installed(): boolean {
    return this.active;
  }

  setWidth(width: number): void {
    if (!this.active) return;
    this.width = clampWidth(width);
    this.defineNarrowedColumns();
    try { this.ports.tui.requestRender(); } catch { /* Fail-soft; the next host render repaints. */ }
  }

  dispose(): void {
    if (!this.active) return;
    this.active = false;
    try {
      Object.defineProperty(this.ports.terminal, "columns", this.originalDescriptor);
    } catch { /* The descriptor may already be foreign; native remains authoritative. */ }
    try {
      this.ports.tui.doRender = this.originalDoRender;
    } catch { /* Same fail-soft posture. */ }
    try { this.ports.tui.requestRender(); } catch { /* A later host render restores the surface. */ }
  }

  private rawGeometry(): FrozenGeometry | undefined {
    // A foreign redefinition of `columns` (Pi 0.84's runtime fullscreen switch
    // swaps the render surface) means the raw value this compositor snapshotted
    // no longer describes the live terminal — treat it as a geometry failure.
    const own = Object.getOwnPropertyDescriptor(this.ports.terminal, "columns");
    if (own?.get !== this.narrowedGetter) return undefined;
    let rawColumns: unknown;
    try {
      rawColumns = this.originalDescriptor.get !== undefined
        ? this.originalDescriptor.get.call(this.ports.terminal)
        : this.originalDescriptor.value;
    } catch {
      return undefined;
    }
    const rows = (this.ports.terminal as { rows?: unknown }).rows;
    if (typeof rawColumns !== "number" || !Number.isFinite(rawColumns)) return undefined;
    if (typeof rows !== "number" || !Number.isFinite(rows) || rows <= 0) return undefined;
    if (rawColumns < this.width + SIDEBAR_MAIN_COLUMN_FLOOR) return undefined;
    return { rawColumns: Math.floor(rawColumns), rows: Math.floor(rows) };
  }

  private defineNarrowedColumns(): void {
    const narrowed = () => {
        const geometry = this.rawGeometry();
        if (geometry === undefined) {
          // Fall back to whatever the host would have seen natively.
          try {
            return this.originalDescriptor.get !== undefined
              ? this.originalDescriptor.get.call(this.ports.terminal)
              : this.originalDescriptor.value;
          } catch {
            return this.width + SIDEBAR_MAIN_COLUMN_FLOOR;
          }
        }
        return geometry.rawColumns - (this.width + 1);
    };
    this.narrowedGetter = narrowed;
    Object.defineProperty(this.ports.terminal, "columns", {
      configurable: true,
      enumerable: true,
      get: narrowed,
    });
  }

  /** AC-3: paint inside a synchronized-output envelope; every cycle
   * re-validates raw geometry first and a persistent failure disposes. */
  private paint(): void {
    if (!this.active) return;
    try {
      const geometry = this.rawGeometry();
      if (geometry === undefined) {
        this.geometryFailures += 1;
        if (this.geometryFailures >= GEOMETRY_FAILURE_LIMIT) this.dispose();
        return;
      }
      this.geometryFailures = 0;
      const lines = renderSidebar(this.ports.dataSource(), this.width, this.ports.metrics, {
        noColor: this.ports.noColor,
      });
      const column = geometry.rawColumns - this.width;
      const separatorColumn = column - 1;
      const parts: string[] = [SYNC_START, CURSOR_SAVE, WRAP_OFF];
      for (let row = 1; row <= geometry.rows; row += 1) {
        const content = row - 1 < lines.length ? lines[row - 1] : " ".repeat(this.width);
        parts.push(`${ESC}[${row};${separatorColumn}H${RESET}│${content}`);
      }
      parts.push(WRAP_ON, CURSOR_RESTORE, SYNC_END);
      this.ports.writeOut(parts.join(""));
    } catch {
      // Any compositor/renderer throw disposes back to native rendering with
      // one bounded warning — never a wedged terminal, never repeated noise.
      this.dispose();
      if (!this.warned) {
        this.warned = true;
        try {
          this.ports.notify("codeArbiter sidebar disabled after a paint failure; run /ca-doctor.");
        } catch { /* Notification is best-effort. */ }
      }
    }
  }
}

/** Install the sidebar, or report unavailable without touching native rendering. */
export function installSidebar(
  ports: SidebarCompositorPorts,
  options: { readonly width?: number },
): SidebarCompositor {
  const probe = probeSidebarSupport(ports.tui, ports.terminal as object, ports.metrics);
  if (!probe.ok) return unavailable(probe.reason);
  const width = clampWidth(options.width);
  const descriptor = columnsDescriptor(ports.terminal as object) as PropertyDescriptor;
  let rawColumns: unknown;
  try {
    rawColumns = descriptor.get !== undefined ? descriptor.get.call(ports.terminal) : descriptor.value;
  } catch {
    return unavailable("geometry-unreadable");
  }
  if (typeof rawColumns !== "number" || !Number.isFinite(rawColumns)
    || rawColumns < width + SIDEBAR_MAIN_COLUMN_FLOOR) {
    return unavailable("terminal-too-narrow");
  }
  return new Compositor(ports, width);
}
