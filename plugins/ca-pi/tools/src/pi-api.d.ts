/** Descriptor-owned Pi permission action surfaces, embedded by build.mjs for T08 composition. */
declare const __CODEARBITER_PI_PERMISSION_POLICY_SURFACES__: unknown;

declare module "@earendil-works/pi-coding-agent" {
  export const VERSION: string;

  export class ModelRegistry {}

  /**
   * Structural surface of Pi's extension host object, as observed by
   * codeArbiter's parent (extension.ts) and child (child-extension.ts)
   * adapters against the Pi 0.80.5/0.80.10 external runtime.
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
