import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { afterEach, describe, expect, test } from "vitest";
import { createDelegatedExecutor, credentialBlindCommandEnvironment, credentialBlindHostEnvironment, observeTarget } from "../src/delegated-executor.ts";
import { openDelegationJournal } from "../src/delegation-journal.ts";
import { operationDigest, encodeOperationResponse, decodeOperationResponse } from "../src/delegation-contract.ts";
import { startDelegationChannel } from "../src/delegation-session.ts";
import { createDelegationClient } from "../src/delegation-client.ts";
import type { RunGrant } from "../src/delegation-contract.ts";
import type { DelegationJournal } from "../src/delegation-journal.ts";
import type { ToolDefinitionPort } from "../src/contracts.ts";

const roots: string[] = [];
afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "ca-delegated-effect-")); roots.push(root); await mkdir(join(root, ".git"));
  const grant: RunGrant = { runId: "a".repeat(32), role: "backend-author", callerCorrelation: "b".repeat(64),
    worktree: root, tools: ["write", "edit", "bash"], maxOperations: 10, expiresAtMonotonicMs: performance.now() + 60000 };
  const controller = new AbortController(); const params = { path: "result.txt", content: "approved bytes" };
  const request = { grant, requestId: "req-1", tool: "write" as const, params, digest: operationDigest("write", params),
    toolCallId: "test-call", signal: controller.signal };
  let effects = 0;
  const write = () => ({ name: "write", execute: async (_id: string, p: Record<string, unknown>) => {
    effects++; await writeFile(p.path as string, p.content as string); return { content: [{ type: "text", text: "written" }] };
  } }) as ToolDefinitionPort;
  const journal = (await openDelegationJournal(root))!;
  const executor = (store: DelegationJournal = journal) => createDelegatedExecutor({ journal: store, write, edit: write,
    shell: async () => undefined, environment: {} });
  return { root, request, journal, executor, controller, effects: () => effects };
}
describe("parent delegated effect executor", () => {
  test.each((["spawn", "started"] as const).flatMap((window) =>
    (["cancelled", "revoked", "expired"] as const).map((loss) => [window, loss] as const)))("authority loss during %s:%s cannot release legacy command stdin", async (window, loss) => {
      const f = await fixture(); let live = true; let released = false; let cleanups = 0;
      const grant = { ...f.request.grant };
      const retire = () => { if (loss === "cancelled") f.controller.abort(); else if (loss === "revoked") live = false; else grant.expiresAtMonotonicMs = 0; };
      const child = Object.assign(new EventEmitter(), { pid: 4321,
        stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), stdio: [null, null, null, new PassThrough()],
      });
      child.stdin.on("data", () => { released = true; });
      const executor = createDelegatedExecutor({ journal: { ...f.journal, started: async (record) => {
        const persisted = await f.journal.started(record); if (window === "started") retire(); return persisted;
      } }, write: () => ({ name: "write", execute: async () => ({}) }), edit: () => ({ name: "edit", execute: async () => ({}) }),
      shell: async () => ({ shellPath: "C:/Windows/System32/bash.exe" }), environment: {}, openTree: async () => {
        if (window === "spawn") retire(); setTimeout(() => child.emit("close", 0), 1);
        return { child, cleanup: { terminate: async () => { cleanups++; return { verified: true }; } } } as never;
      } });
      const params = { command: "must not release this command after retirement" };
      const outcome = await executor.execute({ ...f.request, grant, tool: "bash", params, digest: operationDigest("bash", params), isCurrent: () => live });
      expect(released, `${window}:${loss}`).toBe(false);
      expect(cleanups, `${window}:${loss}`).toBe(1);
      expect(decodeOperationResponse(encodeOperationResponse(outcome))).toMatchObject({ admission: "admitted", execution: "outcome-unknown",
        containment: "verified-stopped", recovery: "read-only-reconciliation", reason: loss === "expired" ? "grant-expired" : "grant-revoked" });
  });
  test.each(["cancelled", "revoked", "expired"] as const)("the full channel preserves post-started %s observations", async (loss) => {
    const f = await fixture(); const grant = { ...f.request.grant }; let live = true; let released = false; let cleanups = 0;
    const child = Object.assign(new EventEmitter(), { pid: 4321,
      stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), stdio: [null, null, null, new PassThrough()],
    });
    child.stdin.on("data", () => { released = true; }); child.stdin.on("finish", () => child.emit("close", 0));
    const executor = createDelegatedExecutor({ journal: { ...f.journal, started: async (record) => {
      const persisted = await f.journal.started(record);
      if (loss === "cancelled") f.controller.abort(); else if (loss === "revoked") live = false; else grant.expiresAtMonotonicMs = 0;
      return persisted;
    } }, write: () => ({ name: "write", execute: async () => ({}) }), edit: () => ({ name: "edit", execute: async () => ({}) }),
    shell: async () => ({ shellPath: "C:/Windows/System32/bash.exe" }), environment: {}, openTree: async () => ({ child,
      cleanup: { terminate: async () => { cleanups++; child.emit("close", 0); return { verified: true }; } } }) as never });
    const channel = await startDelegationChannel({ grant, isCurrent: () => live, signal: f.controller.signal,
      execute: async (request, signal) => await executor.execute({ grant, requestId: request.requestId, tool: request.tool,
        params: request.params, digest: request.digest, toolCallId: "parent-fixture-call", signal, isCurrent: () => live }) });
    try {
      const result = await createDelegationClient(channel).execute("bash", { command: "withhold this command" });
      expect(released).toBe(false); expect(cleanups).toBe(1);
      expect(result).toMatchObject({ admission: "admitted", execution: "outcome-unknown", containment: "verified-stopped",
        recovery: "read-only-reconciliation", reason: loss === "expired" ? "grant-expired" : "grant-revoked" });
      expect(channel.summary()).toMatchObject({ requested: 1, unknown: 1, refused: 0, containmentUnverified: 0 });
    } finally { await channel.close(); }
  });
  test("bounds existing target observations before admitting mutation", async () => {
    const f = await fixture(); await writeFile(join(f.root, "result.txt"), Buffer.alloc(16 * 1024 * 1024 + 1));
    expect(await observeTarget(join(f.root, "result.txt"))).toBe("unreadable");
    expect((await f.executor().execute(f.request)).admission).toBe("denied"); expect(f.effects()).toBe(0);
  });
  test("performs approved file bytes once and observes exact replay without another effect", async () => {
    const f = await fixture(); const executor = f.executor();
    expect((await executor.execute(f.request)).execution).toBe("completed");
    expect(await readFile(join(f.root, "result.txt"), "utf8")).toBe("approved bytes");
    expect((await executor.execute(f.request)).execution).toBe("completed");
    expect(f.effects()).toBe(1);
  });
  test("retains uncertain effect when outcome persistence fails", async () => {
    const f = await fixture(); const executor = f.executor({ ...f.journal, observe: async () => false });
    expect((await executor.execute(f.request)).execution).toBe("outcome-unknown");
    expect(f.effects()).toBe(1);
    expect((await executor.execute(f.request)).execution).toBe("outcome-unknown");
    expect(f.effects()).toBe(1);
  });
  test("an unresolved file effect holds its target while a disjoint edit can proceed", async () => {
    const f = await fixture();
    await f.executor({ ...f.journal, observe: async () => false }).execute(f.request);
    await writeFile(join(f.root, "result.txt"), "later user bytes");
    const executor = f.executor();
    const dependent = await executor.execute({ ...f.request, requestId: "new-dependent" });
    expect(dependent.admission).toBe("unavailable");
    expect(dependent.recovery).toBe("dependent-resource-held");
    expect(await readFile(join(f.root, "result.txt"), "utf8")).toBe("later user bytes");
    const params = { path: "unrelated.txt", content: "ordinary progress" };
    expect((await executor.execute({ ...f.request, requestId: "disjoint", params,
      digest: operationDigest("write", params) })).execution).toBe("completed");
    expect(f.effects()).toBe(2);
  });
  test("cancellation before execution cannot claim or perform an effect", async () => {
    const f = await fixture(); f.controller.abort();
    expect((await f.executor().execute(f.request)).admission).toBe("cancelled");
    expect(f.effects()).toBe(0); expect(await f.journal.unresolved()).toEqual([]);
  });
  test("cancellation during claim cannot execute after the await", async () => {
    const f = await fixture(); const executor = f.executor({ ...f.journal, claim: async (r) => {
      const result = await f.journal.claim(r); f.controller.abort(); return result;
    } });
    expect((await executor.execute(f.request)).execution).toBe("not-started");
    expect(f.effects()).toBe(0);
  });
  test("a concurrent later target edit after claim is preserved without executing", async () => {
    const f = await fixture(); const executor = f.executor({ ...f.journal, claim: async (r) => {
      const result = await f.journal.claim(r); await writeFile(join(f.root, "result.txt"), "later user bytes"); return result;
    } });
    const outcome = await executor.execute(f.request);
    expect(outcome.execution).toBe("failed"); expect(outcome.observation).toBe("stale");
    expect(await readFile(join(f.root, "result.txt"), "utf8")).toBe("later user bytes"); expect(f.effects()).toBe(0);
  });
  test("different concurrent requests serialize their owned effects", async () => {
    const f = await fixture(); let active = 0; let maximum = 0;
    const write = () => ({ name: "write", execute: async (_id: string, params: Record<string, unknown>) => {
      active++; maximum = Math.max(maximum, active); await new Promise((resolve) => setTimeout(resolve, 5));
      await writeFile(params.path as string, params.content as string); active--; return {};
    } });
    const executor = createDelegatedExecutor({ journal: f.journal, write, edit: write, shell: async () => undefined, environment: {} });
    const secondParams = { path: "second.txt", content: "second" };
    const results = await Promise.all([executor.execute(f.request), executor.execute({ ...f.request, requestId: "second", params: secondParams,
      digest: operationDigest("write", secondParams) })]);
    expect(results.map((r) => r.execution)).toEqual(["completed", "completed"]); expect(maximum).toBe(1);
  });
  test("credential-blind environment retains only host baseline with Windows case folding", () => {
    expect(credentialBlindCommandEnvironment({ Path: "host-path", SYSTEMROOT: "root", EXAMPLE_PROVIDER_VALUE: "dummy" }, "win32"))
      .toEqual({ PATH: "host-path", SystemRoot: "root", CODEARBITER_DELEGATED: "1" });
    expect(credentialBlindHostEnvironment({ PATH: "host-path", OPENAI_API_KEY: "dummy-provider-fixture", CODEARBITER_DELEGATED: "1" }, "win32"))
      .toEqual({ PATH: "host-path" });
  });
  test("raw executor exception text cannot cross into child results", async () => {
    const f = await fixture(); const fail = () => ({ name: "write", execute: async () => {
      throw new Error("private diagnostic fixture; must stay in parent");
    } }) as ToolDefinitionPort;
    const executor = createDelegatedExecutor({ journal: f.journal, write: fail, edit: fail, shell: async () => undefined, environment: {} });
    const outcome = await executor.execute(f.request);
    expect(outcome.execution).toBe("failed"); expect(JSON.stringify(outcome)).not.toContain("private diagnostic fixture");
  });
  test("a successful native return without approved write bytes cannot claim completion", async () => {
    const f = await fixture(); const noEffect = () => ({ name: "write", execute: async () => ({ isError: false }) });
    const executor = createDelegatedExecutor({ journal: f.journal, write: noEffect, edit: noEffect, shell: async () => undefined, environment: {} });
    expect((await executor.execute(f.request)).execution).toBe("outcome-unknown");
  });
  test("a shell exit with unverified tree cleanup holds subsequent delegated effects", async () => {
    const f = await fixture(); const child = Object.assign(new EventEmitter(), {
      stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), stdio: [null, null, null, new PassThrough()],
    });
    const executor = createDelegatedExecutor({ journal: f.journal,
      write: () => ({ name: "write", execute: async () => { throw new Error("must not execute while held"); } }),
      edit: () => ({ name: "edit", execute: async () => ({}) }), shell: async () => ({ shellPath: process.execPath }), environment: {},
      openTree: async () => { setTimeout(() => child.emit("close", 0), 1); return {
        child, cleanup: { terminate: async () => ({ verified: false }) },
      } as never; } });
    const params = { command: "harmless fixture" };
    const command = await executor.execute({ ...f.request, tool: "bash", params, digest: operationDigest("bash", params) });
    expect(command.containment).toBe("unverified"); expect(command.recovery).toBe("dependent-resource-held");
    expect((await executor.execute({ ...f.request, requestId: "second" })).admission).toBe("unavailable");
    expect((await f.executor().execute({ ...f.request, requestId: "after-restart" })).admission).toBe("unavailable");
  });
  test("a failed command launch observation settles owned cleanup and preserves unknown effects", async () => {
    const f = await fixture(); let cleanups = 0;
    const child = Object.assign(new EventEmitter(), { pid: 4321,
      stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), stdio: [null, null, null, new PassThrough()],
    });
    const executor = createDelegatedExecutor({ journal: { ...f.journal, started: async () => false },
      write: () => ({ name: "write", execute: async () => ({}) }), edit: () => ({ name: "edit", execute: async () => ({}) }),
      shell: async () => ({ shellPath: process.execPath }), environment: {}, openTree: async () => ({ child,
        cleanup: { terminate: async () => { cleanups++; return { verified: true }; } } }) as never });
    const params = { command: "fixture command" };
    const outcome = await executor.execute({ ...f.request, tool: "bash", params, digest: operationDigest("bash", params) });
    expect(outcome.execution).toBe("outcome-unknown"); expect(outcome.reason).toBe("journal-unknown");
    expect(cleanups).toBe(1); expect((await f.journal.unresolved())[0]?.observed?.processId).toBe(4321);
  });
});
