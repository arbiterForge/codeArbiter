/** Session-local owner of the sidebar compositor (spec pi-sidebar-panel AC-5).
 *
 * Registers the `/ca-sidebar` native parent command, applies the auto-on
 * default (install when the raw terminal is at least 120 columns wide), and
 * disposes on session switch, shutdown and unload. No preference persists
 * beyond the session. Registration is interactive-parent-gated, so child, RPC,
 * JSON and print modes never see the command or any painting.
 */

import { installSidebar, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "./sidebar-compositor.ts";
import type { SidebarCompositor, SidebarTuiPort } from "./sidebar-compositor.ts";
import type { SidebarInput } from "./sidebar.ts";
import type { FooterTextMetrics } from "./footer.ts";
import type { ExtensionContextPort, ParentPiPort } from "./contracts.ts";
import { interactiveParent } from "./session-identity.ts";

/** Raw terminal columns at or above which the sidebar defaults to ON. */
export const SIDEBAR_AUTO_ON_MIN_COLUMNS = 120;

const SIDEBAR_SYNTAX = "Usage: /ca-sidebar on|off|toggle|width N (N clamped 24..60)";
/** Probe/runtime reasons that mean the hook surface is gone — degraded, not a
 * benign off-state like a narrow terminal or an explicit /ca-sidebar off. */
const DEGRADED_REASONS = Object.freeze(new Set([
  "no-dorender",
  "columns-not-configurable",
  "no-metrics",
  "geometry-unreadable",
  "install-failed",
]));

export interface SidebarManagerPorts {
  readonly pi: Pick<ParentPiPort, "registerCommand">;
  readonly currentTui: () => SidebarTuiPort | undefined;
  readonly terminal: () => { columns?: unknown; rows?: unknown } | undefined;
  readonly loadMetrics?: () => Promise<FooterTextMetrics>;
  readonly dataSource: () => SidebarInput;
  readonly writeOut: (text: string) => void;
  readonly noColor: () => boolean;
}

export interface SidebarHealth {
  readonly expected: boolean;
  readonly installed: boolean;
  readonly degraded: boolean;
  readonly reason?: string;
}

export interface SidebarManager {
  register(context: ExtensionContextPort): boolean;
  autoInstall(context: ExtensionContextPort): Promise<void>;
  dispose(): void;
  health(): SidebarHealth;
}

function clampWidth(width: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.floor(width)));
}

function rawColumns(terminal: { columns?: unknown } | undefined): number | undefined {
  try {
    const value = terminal?.columns;
    return typeof value === "number" && Number.isFinite(value) ? Math.floor(value) : undefined;
  } catch {
    return undefined;
  }
}

class Manager implements SidebarManager {
  private registered = false;
  private expected = false;
  private compositor: SidebarCompositor | undefined;
  private width = SIDEBAR_DEFAULT_WIDTH;
  private userDisabled = false;
  private autoDecided = false;
  private lastReason: string | undefined;
  private metrics: FooterTextMetrics | undefined;

  constructor(private readonly ports: SidebarManagerPorts) {}

  register(context: ExtensionContextPort): boolean {
    if (!interactiveParent(context)) return false;
    this.expected = true;
    if (!this.registered) {
      this.ports.pi.registerCommand("ca-sidebar", {
        description: "Toggle or resize the codeArbiter sidebar (on|off|toggle|width N).",
        handler: async (args, commandContext) => { await this.handle(args, commandContext); },
      });
      this.registered = true;
    }
    return true;
  }

  async autoInstall(context: ExtensionContextPort): Promise<void> {
    if (!interactiveParent(context)) return;
    if (this.autoDecided || this.userDisabled || this.compositor?.installed === true) return;
    if (this.ports.currentTui() === undefined) return; // The footer factory has not run yet; retry on the next settle.
    const columns = rawColumns(this.ports.terminal());
    if (columns === undefined) return;
    this.autoDecided = true;
    if (columns < SIDEBAR_AUTO_ON_MIN_COLUMNS) {
      this.lastReason = "auto-off-narrow";
      return;
    }
    await this.install(context);
  }

  dispose(): void {
    try { this.compositor?.dispose(); } catch { /* Restore is fail-soft; native stays authoritative. */ }
    this.compositor = undefined;
    this.expected = false;
    this.userDisabled = false;
    this.autoDecided = false;
    this.lastReason = undefined;
    // No preference persists beyond the session, width included.
    this.width = SIDEBAR_DEFAULT_WIDTH;
  }

  health(): SidebarHealth {
    const installed = this.compositor?.installed === true;
    const reason = installed ? undefined : (this.compositor?.reason ?? this.lastReason);
    return Object.freeze({
      expected: this.expected,
      installed,
      degraded: !installed && reason !== undefined && DEGRADED_REASONS.has(reason),
      ...(reason === undefined ? {} : { reason }),
    });
  }

  private async install(context: ExtensionContextPort): Promise<boolean> {
    const tui = this.ports.currentTui();
    const terminal = this.ports.terminal();
    if (tui === undefined || terminal === undefined) {
      this.lastReason = tui === undefined ? "no-tui" : "no-terminal";
      return false;
    }
    if (this.metrics === undefined) {
      try {
        this.metrics = await this.ports.loadMetrics?.();
      } catch {
        this.metrics = undefined;
      }
      if (this.metrics === undefined) {
        this.lastReason = "no-metrics";
        return false;
      }
    }
    const notify = (message: string) => {
      try { context.ui.notify(message, "warning"); } catch { /* Notification is best-effort. */ }
    };
    const compositor = installSidebar({
      tui,
      terminal,
      metrics: this.metrics,
      writeOut: this.ports.writeOut,
      notify,
      dataSource: this.ports.dataSource,
      noColor: this.ports.noColor(),
    }, { width: this.width });
    this.compositor = compositor;
    this.lastReason = compositor.installed ? undefined : compositor.reason;
    return compositor.installed;
  }

  private notifyInfo(context: ExtensionContextPort, message: string, level: "info" | "warning" = "info"): void {
    try { context.ui.notify(message, level); } catch { /* Notification is best-effort. */ }
  }

  private async turnOn(context: ExtensionContextPort): Promise<void> {
    this.userDisabled = false;
    this.autoDecided = true;
    if (this.compositor?.installed === true) {
      this.notifyInfo(context, "codeArbiter sidebar is already on.");
      return;
    }
    const installed = await this.install(context);
    if (!installed) {
      this.notifyInfo(context, `codeArbiter sidebar unavailable (${this.lastReason ?? "unknown"}); native rendering is untouched.`, "warning");
    }
  }

  private turnOff(context: ExtensionContextPort): void {
    this.userDisabled = true;
    this.autoDecided = true;
    try { this.compositor?.dispose(); } catch { /* Restore is fail-soft. */ }
    this.compositor = undefined;
    this.lastReason = "off";
    this.notifyInfo(context, "codeArbiter sidebar off.");
  }

  private async handle(rawArgs: string, context: ExtensionContextPort): Promise<void> {
    if (!interactiveParent(context)) return;
    const args = typeof rawArgs === "string" ? rawArgs.trim().split(/\s+/u).filter(Boolean) : [];
    if (args.length === 0 || (args.length === 1 && args[0] === "toggle")) {
      if (this.compositor?.installed === true) this.turnOff(context);
      else await this.turnOn(context);
      return;
    }
    if (args.length === 1 && args[0] === "on") { await this.turnOn(context); return; }
    if (args.length === 1 && args[0] === "off") { this.turnOff(context); return; }
    if (args.length === 2 && args[0] === "width" && /^\d{1,4}$/u.test(args[1]!)) {
      this.width = clampWidth(Number(args[1]));
      if (this.compositor?.installed === true) this.compositor.setWidth(this.width);
      else this.notifyInfo(context, `codeArbiter sidebar width set to ${this.width}; the sidebar is off.`);
      return;
    }
    this.notifyInfo(context, SIDEBAR_SYNTAX, "warning");
  }
}

export function createSidebarManager(ports: SidebarManagerPorts): SidebarManager {
  return new Manager(ports);
}
