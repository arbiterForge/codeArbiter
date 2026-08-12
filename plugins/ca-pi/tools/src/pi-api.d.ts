/** Descriptor-owned Pi permission action surfaces, embedded by build.mjs for T08 composition. */
declare const __CODEARBITER_PI_PERMISSION_POLICY_SURFACES__: unknown;

/*
 * Boundary note — sidebar hook surface (spec pi-sidebar-panel AC-7).
 *
 * The sidebar compositor (sidebar-compositor.ts) relies on two members that
 * are deliberately NOT declared here because they are not part of Pi's
 * declared API in either promoted window version:
 *
 * - `tui.doRender()` — TypeScript-private on pi-tui 0.80.x's `TUI` class and
 *   protected-abstract on 0.84.x's screen classes (`TuiMainScreen`/
 *   `TuiAltScreen`). Runtime-present in both, declared in neither.
 * - the `terminal.columns` property descriptor's configurability.
 *
 * That surface is RUNTIME-GUARDED, not source-verified API: every install is
 * gated by `probeSidebarSupport`, every paint re-validates geometry, and any
 * failure disposes back to native rendering. A future Pi that removes either
 * hook degrades the sidebar to a /ca-doctor "unavailable" row — it does not
 * break the adapter. Fixture + live contracts: sidebar-window-contract.test.ts
 * and sidebar-probe-live.test.ts.
 */

declare module "@earendil-works/pi-coding-agent" {
  export const VERSION: string;

  export class ModelRegistry {}

  /**
   * Structural surface of Pi's extension host object, as observed by
   * codeArbiter's parent (extension.ts) and child (child-extension.ts)
   * adapters against the Pi 0.80.5/0.84.1 external runtime.
   *
   * Only members actually consumed by those adapters are declared here.
   * `context` is typed as ExtensionContextPort (contracts.ts) because that
   * is the exact subset of Pi's real context object codeArbiter reads;
   * every optional member there (e.g. `isProjectTrusted`) is optional
   * because the adapters runtime-guard its absence before use.
   */
  export interface ExtensionAPI {
    on(
      event: string,
      handler: (event: Record<string, unknown>, context: import("./contracts.ts").ExtensionContextPort) => unknown,
    ): void;
    registerTool(tool: {
      name: string;
      execute(
        toolCallId: string,
        params: Record<string, unknown>,
        signal?: AbortSignal,
        onUpdate?: unknown,
        context?: unknown,
      ): Promise<Record<string, unknown>>;
      [key: string]: unknown;
    }): void;
    registerCommand(
      name: string,
      options: {
        description?: string;
        handler: (args: string, context: import("./contracts.ts").ExtensionContextPort) => unknown;
      },
    ): void;
    sendUserMessage(content: string, options?: { deliverAs?: "steer" | "followUp" }): void;
    /** Source-verified in Pi 0.80.5 and 0.80.10; optional locally for fail-soft adaptation. */
    getSessionName?(): unknown;
    /** Source-verified in Pi 0.80.5 and 0.80.10; optional locally for fail-soft adaptation. */
    getThinkingLevel?(): unknown;
    getCommands(): Array<{
      name: string;
      description?: string;
      source: "extension" | "prompt" | "skill";
      sourceInfo: {
        path: string;
        source: string;
        scope: "user" | "project" | "temporary";
        origin: "package" | "top-level";
        baseDir?: string;
      };
    }>;
    getActiveTools(): string[];
    getAllTools(): Array<{ name: string; sourceInfo: { path: string } }>;
  }
}
