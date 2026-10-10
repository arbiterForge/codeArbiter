/** approval-entry.ts — private, explicitly loaded Pi dialog candidate; ordinary flows stay refused. */
import { realpath } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BridgeClient, resolveGitExecutable, resolvePythonCommand } from "./bridge.ts";
import { runApprovalDialog, validApprovalLaunch } from "./approval-dialog.ts";
import type { ApprovalDialogContext } from "./approval-dialog.ts";
import { resolvePiRuntimeIdentity } from "./runtime-resolver.ts";

interface NativeContext extends ApprovalDialogContext {
  ui: ApprovalDialogContext["ui"] & { notify(message: string, type?: "info" | "warning" | "error"): void };
  shutdown(): void;
}
interface NativePi {
  on(event: string, handler: (event: unknown, context: NativeContext) => unknown): void;
  getActiveTools(): string[];
}

export default function approvalEntry(pi: NativePi): void {
  let generation: object | undefined;
  let started = false;
  // Startup args cannot contain a prompt; subsequent ordinary input is never sent to a model.
  pi.on("input", () => ({ action: "handled" }));
  for (const event of ["session_before_switch", "session_shutdown"]) {
    pi.on(event, () => { generation = undefined; });
  }
  pi.on("session_start", async (_event, context) => {
    const lease = {};
    generation = lease;
    try {
      if (started) throw new Error("one dialog per process");
      started = true;
      const entry = await realpath(fileURLToPath(import.meta.url));
      if (!validApprovalLaunch(process.argv.slice(2), entry, process.execArgv, process.env.NODE_OPTIONS)) {
        throw new Error("unsupported launch profile");
      }
      const runtime = await resolvePiRuntimeIdentity();
      if (runtime.version !== "1.0.2") throw new Error("unqualified host version");
      const packageRoot = resolve(dirname(entry), "..");
      const result = await runApprovalDialog(context, {
        isCurrent: () => generation === lease,
        activeTools: () => pi.getActiveTools(),
        bridge: (cwd) => {
          // The controller has checked genuine current host trust before this resolution.
          const python = resolvePythonCommand(process.platform, undefined, packageRoot, cwd);
          return new BridgeClient({ packageRoot, bridgeScript: resolve(packageRoot, "hooks", "pi-approval.py"),
            pythonExecutable: python.executable, pythonPrefixArgs: ["-B", ...python.prefixArgs],
            gitExecutable: resolveGitExecutable(cwd), toolClasses: {}, maxRequestBytes: 16_384,
            maxStreamBytes: 16_384, shouldAuditFailure: () => false });
        },
      });
      context.ui.notify(result.status === "approved"
        ? `Approval recorded for ${result.artifact_id}.`
        : result.status === "outcome-unknown"
          ? "Approval outcome unknown. Read the artifact's durable state before any retry."
          : `Approval ${result.status}; no approval was recorded by this dialog.`,
      result.status === "approved" ? "info" : "warning");
    } catch {
      context.ui.notify("Pi native approval unavailable for this launch. Ordinary workflow refusal remains in force.", "warning");
    } finally {
      generation = undefined;
      context.shutdown();
    }
  });
}
