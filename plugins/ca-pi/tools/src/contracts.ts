export interface BridgeRequest {
  version: 1;
  event: string;
  cwd: string;
  sessionId?: string;
  tool?: string;
  input?: unknown;
  result?: unknown;
}

export interface BridgeResponse {
  version: 1;
  outcome: "allow" | "block" | "warn" | "notice";
  ruleId?: string;
  message?: string;
  context?: string;
  resultPatch?: unknown;
  auditCode?: string;
}

export interface BridgePort {
  call(request: BridgeRequest, signal: AbortSignal): Promise<BridgeResponse>;
}

export type ToolCategory = "EXEC" | "WRITE" | "EDIT" | "READ" | "OTHER";

export interface ToolExecutionContextPort {
  cwd?: unknown;
  signal?: AbortSignal;
  model?: { provider?: unknown; id?: unknown };
  isProjectTrusted?: () => boolean;
  sessionManager?: {
    getSessionId?: () => unknown;
  };
}

/** Opaque identity for one ready Pi session lifecycle. */
export type LifecycleLease = Readonly<object>;

export interface LifecycleAuthorization {
  readonly lease: LifecycleLease;
  readonly isCurrent: (lease: LifecycleLease) => boolean;
}

export interface ToolDefinitionPort {
  name: string;
  execute(
    toolCallId: string,
    params: Record<string, unknown>,
    signal?: AbortSignal,
    onUpdate?: unknown,
    context?: ToolExecutionContextPort,
  ): Promise<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface ToolInfoPort {
  name: string;
  sourceInfo: Pick<SourceInfo, "path">;
}

export interface ToolGuardPiPort {
  on(
    event: "tool_call",
    handler: (event: Record<string, unknown>, context: ExtensionContextPort) => unknown,
  ): void;
  registerTool(tool: ToolDefinitionPort): void;
  getActiveTools(): string[];
  getAllTools(): ToolInfoPort[];
}

export interface ToolResultPiPort {
  on(
    event: "tool_result",
    handler: (event: Record<string, unknown>, context: ExtensionContextPort) => unknown,
  ): void;
}

export interface BuiltinToolFactories {
  bash(cwd: string): ToolDefinitionPort;
  write(cwd: string): ToolDefinitionPort;
  edit(cwd: string): ToolDefinitionPort;
  read(cwd: string): ToolDefinitionPort;
}

export interface ExtensionUiPort {
  setStatus(key: string, text: string | undefined): void;
  notify(message: string, type?: "info" | "warning" | "error"): void;
  confirm?(title: string, message: string, options?: { timeout?: number }): Promise<boolean>;
}

export interface ExtensionContextPort {
  cwd: string;
  signal: AbortSignal | undefined;
  ui: ExtensionUiPort;
  isProjectTrusted?: () => boolean;
  mode?: "tui" | "rpc" | "json" | "print";
  hasUI?: boolean;
  model?: { provider?: unknown; id?: unknown };
}

export interface SourceInfo {
  path: string;
  source: string;
  scope: "user" | "project" | "temporary";
  origin: "package" | "top-level";
  baseDir?: string;
}

export interface SlashCommand {
  name: string;
  description?: string;
  source: "extension" | "prompt" | "skill";
  sourceInfo: SourceInfo;
}

export interface ParentPiPort {
  on(
    event: string,
    handler: (event: Record<string, unknown>, context: ExtensionContextPort) => unknown,
  ): void;
  registerCommand(
    name: string,
    options: {
      description?: string;
      handler: (args: string, context: ExtensionContextPort) => unknown;
    },
  ): void;
  sendUserMessage(content: string, options?: { deliverAs?: "steer" | "followUp" }): void;
  getCommands(): SlashCommand[];
}

export interface CommandCatalogEntry {
  name: string;
  description: string;
  skillPath: string;
}

export type CollisionReason =
  | "missing-alias"
  | "suffixed-alias"
  | "duplicate-alias"
  | "foreign-owner"
  | "missing-fallback";

export interface Collision {
  command: string;
  reason: CollisionReason;
  owner?: string;
}
