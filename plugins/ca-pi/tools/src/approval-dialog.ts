/** approval-dialog.ts — one isolated native Pi approval dialog, without chat-input authority. */
import { randomUUID } from "node:crypto";
import { isAbsolute, resolve } from "node:path";
import type { BridgePort } from "./contracts.ts";

const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u;
const HASH = /^[0-9a-f]{64}$/u;
const FLAGS = ["--no-extensions", "--no-tools", "--no-skills", "--no-prompt-templates",
  "--no-themes", "--no-context-files", "--no-session", "-e"];

export interface ApprovalDialogContext {
  cwd: string;
  mode?: string;
  hasUI?: boolean;
  signal?: AbortSignal;
  isProjectTrusted?: () => boolean;
  sessionManager?: { getSessionId?: () => unknown };
  ui: { input?: (title: string, placeholder?: string, options?: { signal: AbortSignal; timeout: number }) => Promise<unknown> };
}

export interface ApprovalDialogOptions {
  isCurrent: () => boolean;
  activeTools: () => unknown;
  bridge: (cwd: string) => BridgePort;
}

type DialogResult = { status: "unavailable" | "stale" | "cancelled" | "denied" | "unmatched" | "outcome-unknown" }
  | { status: "approved"; artifact_id: string };

/** Exact CLI profile only. This closes discovery/tools; it is not an inference sandbox. */
export function validApprovalLaunch(args: readonly string[], entry: string,
  execArgs: readonly string[], nodeOptions: string | undefined): boolean {
  return isAbsolute(entry) && execArgs.length === 0 && !nodeOptions
    && args.length === FLAGS.length + 1
    && FLAGS.every((flag, index) => args[index] === flag)
    && isAbsolute(args[FLAGS.length]!) && resolve(args[FLAGS.length]!) === resolve(entry);
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function pendingSnapshot(value: unknown): value is Record<string, unknown> & { artifact_id: string } {
  return record(value)
    && Object.keys(value).sort().join(",") === "artifact_id,kind,model_sha256,normative_sha256,pending_sha256,revision"
    && typeof value.artifact_id === "string" && /^[A-Z][A-Z0-9-]{1,79}$/u.test(value.artifact_id)
    && (value.kind === "spec" || value.kind === "plan")
    && Number.isSafeInteger(value.revision) && (value.revision as number) >= 1
    && [value.model_sha256, value.normative_sha256, value.pending_sha256]
      .every((hash) => typeof hash === "string" && HASH.test(hash));
}

export async function runApprovalDialog(context: ApprovalDialogContext, options: ApprovalDialogOptions): Promise<DialogResult> {
  let consuming = false;
  const controller = new AbortController();
  const abort = () => controller.abort();
  context.signal?.addEventListener("abort", abort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const session = context.sessionManager?.getSessionId?.();
    const cwd = context.cwd;
    const valid = () => options.isCurrent() && context.mode === "tui" && context.hasUI === true
      && context.isProjectTrusted?.() === true && context.cwd === cwd && isAbsolute(cwd)
      && context.sessionManager?.getSessionId?.() === session && typeof session === "string" && UUID.test(session)
      && !context.signal?.aborted && !controller.signal.aborted
      && Array.isArray(options.activeTools()) && (options.activeTools() as unknown[]).length === 0;
    if (!valid() || typeof context.ui.input !== "function") return { status: "unavailable" };
    const generation = randomUUID();
    const bridge = options.bridge(cwd);
    const snapshot = await bridge.call({ version: 1, event: "native_approval_inspect", cwd }, controller.signal);
    if (!valid()) return { status: "stale" };
    if (snapshot.outcome !== "allow" || !pendingSnapshot(snapshot.resultPatch)) return { status: "unavailable" };
    const pending = snapshot.resultPatch;
    timer = setTimeout(abort, 300_000);
    const reply = await context.ui.input(
      `Review ${pending.kind} ${pending.artifact_id} revision ${pending.revision}\n`
      + `Normative SHA-256: ${pending.normative_sha256}\n`
      + "Enter the exact armed approval reply, or deny. Escape preserves the request.",
      undefined, { signal: controller.signal, timeout: 300_000 },
    );
    if (!valid()) return { status: "stale" };
    if (reply === undefined) return { status: "cancelled" };
    if (reply === "deny") return { status: "denied" };
    if (typeof reply !== "string" || Buffer.byteLength(reply, "utf8") > 512) return { status: "unmatched" };
    consuming = true;
    const response = await bridge.call({ version: 1, event: "native_approval_consume", cwd,
      sessionId: session as string, input: { reply, generation, pending_sha256: pending.pending_sha256 } }, controller.signal);
    // A lost response may follow a durable commit. Never retry or call that a denial.
    if (!valid() || response.outcome !== "allow" || !record(response.resultPatch)) return { status: "outcome-unknown" };
    if (response.resultPatch.approved === true && response.resultPatch.artifact_id === pending.artifact_id) {
      return { status: "approved", artifact_id: pending.artifact_id };
    }
    if (response.resultPatch.approved === false && response.resultPatch.matched === false) return { status: "unmatched" };
    return { status: "outcome-unknown" };
  } catch {
    return { status: consuming ? "outcome-unknown" : "unavailable" };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    controller.abort();
    context.signal?.removeEventListener("abort", abort);
  }
}
