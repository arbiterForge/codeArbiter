/** approval-dialog.test.ts — synthetic dialog controls, never human qualification. */
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

const source = new URL("../src/approval-dialog.ts", import.meta.url);
// The absent producer is an explicit unavailable result, not an import-error RED.
const candidate = existsSync(fileURLToPath(source))
  ? await import(/* @vite-ignore */ source.href)
  : { runApprovalDialog: async () => ({ status: "producer-unavailable" }), validApprovalLaunch: () => false };

const sessionId = "f04b8659-e0f5-4c77-a382-2b8bd7d1e214";
const pending = { artifact_id: "SPEC-EXAMPLE", kind: "spec", revision: 7,
  model_sha256: "1".repeat(64), normative_sha256: "2".repeat(64), pending_sha256: "3".repeat(64) };
function fixture(reply: unknown = "approve SPEC-EXAMPLE synthetic-pi-token") {
  let active = true;
  let currentSession = sessionId;
  let trusted = true;
  const input = vi.fn(async (_title: string, _placeholder?: string, _options?: unknown) => reply);
  const context = { cwd: process.cwd(), mode: "tui", hasUI: true,
    isProjectTrusted: () => trusted, sessionManager: { getSessionId: () => currentSession },
    ui: { input }, };
  const bridge = { call: vi.fn(async (request: any) => request.event === "native_approval_inspect"
    ? { version: 1, outcome: "allow", resultPatch: pending }
    : { version: 1, outcome: "allow", resultPatch: { approved: true, artifact_id: pending.artifact_id } }) };
  const options = { isCurrent: () => active, activeTools: () => [], bridge: () => bridge };
  return { context, options, bridge, input, invalidate: () => { active = false; },
    changeSession: () => { currentSession = "a77d6932-3eb9-4720-b1bf-d201bed22a98"; },
    revokeTrust: () => { trusted = false; } };
}

describe("isolated Pi native approval dialog", () => {
  it("passes only the exact native return with pending, session and fresh generation bindings", async () => {
    const f = fixture();
    expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: "approved", artifact_id: pending.artifact_id });
    const request = f.bridge.call.mock.calls[1]![0];
    expect(request.input.reply).toBe("approve SPEC-EXAMPLE synthetic-pi-token");
    expect(request.input.pending_sha256).toBe(pending.pending_sha256);
    expect(request.sessionId).toBe(sessionId);
    expect(request.input.generation).toMatch(/^[0-9a-f-]{36}$/u);
    expect(f.input).toHaveBeenCalledOnce();
    expect(f.input.mock.calls[0]![0]).toContain(pending.normative_sha256);
  });
  it.each([undefined, "deny"])("preserves the request without authority on cancel or denial (%s)", async (reply) => {
    const f = fixture(); f.input.mockResolvedValue(reply);
    expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: reply === undefined ? "cancelled" : "denied" });
    expect(f.bridge.call).toHaveBeenCalledTimes(1);
  });
  it.each(["invalidate", "changeSession", "revokeTrust"] as const)("refuses a reply after %s", async (change) => {
    const f = fixture();
    f.input.mockImplementation(async () => { f[change](); return "approve SPEC-EXAMPLE synthetic-pi-token"; });
    expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: "stale" });
    expect(f.bridge.call).toHaveBeenCalledTimes(1);
  });
  it("refuses RPC, missing trust and active tools before constructing a bridge", async () => {
    for (const change of ["rpc", "trust", "tools"]) {
      const f = fixture(); const create = vi.fn(f.options.bridge); f.options.bridge = create;
      if (change === "rpc") f.context.mode = "rpc";
      if (change === "trust") f.revokeTrust();
      if (change === "tools") f.options.activeTools = () => ["bash"] as never[];
      expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: "unavailable" });
      expect(create).not.toHaveBeenCalled(); expect(f.input).not.toHaveBeenCalled();
    }
  });
  it("does not normalize a wrong reply into an approval", async () => {
    const f = fixture(" approve SPEC-EXAMPLE synthetic-pi-token ");
    f.bridge.call.mockImplementation(async (request: any) => request.event === "native_approval_inspect"
      ? { version: 1, outcome: "allow", resultPatch: pending }
      : { version: 1, outcome: "allow", resultPatch: { approved: false, matched: false } } as any);
    expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: "unmatched" });
    expect(f.bridge.call.mock.calls[1]![0].input.reply).toBe(" approve SPEC-EXAMPLE synthetic-pi-token ");
  });
  it("reports an uncertain outcome after a consume transport failure", async () => {
    const f = fixture();
    f.bridge.call.mockImplementation(async (request: any) => request.event === "native_approval_inspect"
      ? { version: 1, outcome: "allow", resultPatch: pending }
      : { version: 1, outcome: "warn" } as any);
    expect(await candidate.runApprovalDialog(f.context, f.options)).toEqual({ status: "outcome-unknown" });
  });
  it("requires one exact closed CLI launch and rejects added commands, tools, extensions or preloads", () => {
    const entry = fileURLToPath(new URL("../helpers/approval-dialog.js", import.meta.url));
    const args = ["--no-extensions", "--no-tools", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-session", "-e", entry];
    expect(candidate.validApprovalLaunch(args, entry, [], undefined)).toBe(true);
    for (const changed of [args.slice(1), [...args, "approve something"], [...args, "-e", "other.js"], [...args, "--trust"], [...args, "--tools", "read"]]) {
      expect(candidate.validApprovalLaunch(changed, entry, [], undefined)).toBe(false);
    }
    expect(candidate.validApprovalLaunch(args, entry, ["--import", "other.js"], undefined)).toBe(false);
    expect(candidate.validApprovalLaunch(args, entry, [], "--import other.js")).toBe(false);
  });
});
