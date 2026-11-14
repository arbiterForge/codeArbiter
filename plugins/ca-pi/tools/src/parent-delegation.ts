/** Parent-generated run authority joining the final gate, durable executor and private channel. */
import { createHash } from "node:crypto";
import { deepFreeze, MAX_OPERATIONS_PER_GRANT, refusalResponse } from "./delegation-contract.ts";
import type { OperationRequest, OperationResponse, RunGrant } from "./delegation-contract.ts";
import { startDelegationChannel } from "./delegation-session.ts";
import type { PiRole } from "./roles.ts";
import type { createDelegatedExecutor } from "./delegated-executor.ts";

type Axes = Omit<OperationResponse, "v">;
export interface ParentDelegationOptions {
  readonly runId: string;
  readonly role: PiRole;
  readonly parentToolCallId: string;
  readonly worktree: string;
  readonly isCurrent: () => boolean;
  readonly enabled: () => Promise<boolean>;
  readonly signal: AbortSignal;
  readonly executor: ReturnType<typeof createDelegatedExecutor>;
  readonly commandBinding?: Readonly<{ shellPath: string; commandPrefix?: string }> | null;
  readonly gate: (request: OperationRequest, signal: AbortSignal,
    effect: (approved: Record<string, unknown>) => Promise<Record<string, unknown>>, executionDescription?: string) => Promise<{ admitted: boolean; reason?: "no-parent-ui" }>;
}
export async function openParentDelegation(options: ParentDelegationOptions) {
  if (options.role.classification !== "author" || options.parentToolCallId.trim() === ""
    || !options.isCurrent() || !await options.enabled() || options.signal.aborted) throw new Error("Parent delegation authority is unavailable.");
  const tools = options.role.tools.filter((tool): tool is "write" | "edit" | "bash" => tool !== "read");
  const grant: RunGrant = deepFreeze({ runId: options.runId, role: options.role.name,
    callerCorrelation: createHash("sha256").update(options.parentToolCallId).digest("hex"), worktree: options.worktree,
    tools, maxOperations: MAX_OPERATIONS_PER_GRANT, expiresAtMonotonicMs: performance.now() + 120_000 });
  const channel = await startDelegationChannel({ grant, isCurrent: options.isCurrent, signal: options.signal,
    execute: async (request, signal) => {
      if (!options.isCurrent() || !await options.enabled()) return refusalResponse(request.requestId, "revoked", "grant-revoked");
      let outcome: Axes | undefined;
      const gated = await options.gate(request, signal, async (approved) => {
        outcome = await options.executor.execute({ grant, requestId: request.requestId, tool: request.tool,
          params: approved, digest: request.digest, toolCallId: `${grant.callerCorrelation}:${request.requestId}`, signal,
          permissionCorrelation: createHash("sha256").update(`${options.parentToolCallId}:${request.requestId}`).digest("hex"),
          ...(options.commandBinding === undefined ? {} : { shellBinding: options.commandBinding }),
          isCurrent: async () => options.isCurrent() && await options.enabled() });
        return { content: outcome.result?.content ?? [], isError: outcome.execution !== "completed" };
      }, request.tool === "bash" ? `Parent shell binding: ${JSON.stringify(options.commandBinding ?? "unavailable")}` : undefined);
      return gated.admitted && outcome !== undefined ? outcome : refusalResponse(request.requestId,
        gated.reason === "no-parent-ui" ? "unavailable" : "denied", gated.reason ?? "permission-denied");
    },
  });
  let observing = false;
  const monitor = setInterval(() => {
    if (observing) return;
    observing = true;
    void options.enabled().then((enabled) => {
      try { if (!enabled || !options.isCurrent()) channel.revoke(); } catch { channel.revoke(); }
    }, () => channel.revoke())
      .finally(() => { observing = false; });
  }, 250);
  monitor.unref();
  return Object.freeze({ endpoint: channel.endpoint, token: channel.token, revoke: channel.revoke, summary: channel.summary,
    close: async () => { clearInterval(monitor); await channel.close(); } });
}
