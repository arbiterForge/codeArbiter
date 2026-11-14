import { describe, expect, test, vi } from "vitest";
import { createDelegationSession, startDelegationChannel } from "../src/delegation-session.ts";
import { createDelegationClient } from "../src/delegation-client.ts";
import { encodeOperationRequest } from "../src/delegation-contract.ts";
import type { OperationRequest, OperationResponse, RunGrant } from "../src/delegation-contract.ts";

const grant: RunGrant = { runId: "a".repeat(32), callerCorrelation: "b".repeat(64), role: "backend-author",
  worktree: "C:/fixture", tools: ["write"], maxOperations: 2, expiresAtMonotonicMs: 500 };
const request = (seq = 1, requestId = "one", content = "approved") => encodeOperationRequest({
  seq, requestId, tool: "write", params: { path: "a.txt", content },
});
const completed = (r: OperationRequest): Omit<OperationResponse, "v"> => ({ requestId: r.requestId, admission: "admitted",
  execution: "completed", containment: "not-applicable", observation: "exact", recovery: "none",
  result: { content: [{ type: "text", text: "written" }], isError: false } });
describe("parent-owned delegation session", () => {
  test("lifecycle loss aborts active execution while its owned cleanup can settle", async () => {
    vi.useFakeTimers();
    try {
      let current = true; let signal: AbortSignal | undefined;
      const session = createDelegationSession({ grant, isCurrent: () => current, now: () => 1,
        execute: async (r, activeSignal) => { signal = activeSignal; await new Promise<void>((resolve) => activeSignal.addEventListener("abort", () => resolve(), { once: true }));
          return { requestId: r.requestId, admission: "admitted", execution: "outcome-unknown", containment: "verified-stopped",
            observation: "unavailable", recovery: "read-only-reconciliation" }; } });
      const pending = session.handle(session.token, request()); await Promise.resolve();
      current = false; await vi.advanceTimersByTimeAsync(50);
      expect(signal?.aborted).toBe(true); expect((await pending).execution).toBe("outcome-unknown"); await session.settle();
    } finally { vi.useRealTimers(); }
  });
  test("real loopback client sends only exact tool data, serializes concurrent requests and revokes", async () => {
    const seen: OperationRequest[] = [];
    const channel = await startDelegationChannel({ grant: { ...grant, expiresAtMonotonicMs: performance.now() + 60000 },
      isCurrent: () => true, execute: async (r) => { seen.push(r); return completed(r); } });
    try {
      const client = createDelegationClient(channel);
      const results = await Promise.all([client.execute("write", { path: "one.txt", content: "one" }),
        client.execute("write", { path: "two.txt", content: "two" })]);
      expect(results.map((r) => r.execution)).toEqual(["completed", "completed"]);
      expect(seen.map((r) => r.seq)).toEqual([1, 2]);
      expect(Object.keys(seen[0]!).sort()).toEqual(["digest", "params", "requestId", "seq", "tool", "v"]);
      channel.revoke();
      expect((await client.execute("write", { path: "three.txt", content: "three" })).admission).toBe("revoked");
      expect(seen).toHaveLength(2);
    } finally { await channel.close(); }
  });
  test("authenticates and joins duplicate requests; changed request identity never repeats effects", async () => {
    let effects = 0;
    const session = createDelegationSession({ grant, isCurrent: () => true, now: () => 1,
      execute: async (r) => { effects++; return completed(r); } });
    const denied = await session.handle("not-the-parent-token", request()); expect(denied.reason).toBe("token-invalid");
    const [one, replay] = await Promise.all([session.handle(session.token, request()), session.handle(session.token, request())]);
    expect(one).toEqual(replay); expect(effects).toBe(1);
    expect((await session.handle(session.token, request(2, "one", "changed"))).reason).toBe("operation-id-reused");
    expect(effects).toBe(1);
  });
  test("bounds sequence and grant operation population", async () => {
    const session = createDelegationSession({ grant, isCurrent: () => true, now: () => 1, execute: async (r) => completed(r) });
    expect((await session.handle(session.token, request())).execution).toBe("completed");
    expect((await session.handle(session.token, request(1, "two"))).reason).toBe("sequence-invalid");
    expect((await session.handle(session.token, request(2, "two"))).execution).toBe("completed");
    expect((await session.handle(session.token, request(3, "three"))).reason).toBe("grant-exhausted");
  });
  test("expiry, lifecycle loss, explicit revoke and forged authority never admit effects", async () => {
    let current = true; let now = 1; let effects = 0;
    const session = createDelegationSession({ grant, isCurrent: () => current, now: () => now,
      execute: async (r) => { effects++; return completed(r); } });
    expect((await session.handle(session.token, '{"grant":"all"}')).reason).toBe("protocol-invalid");
    now = 501; expect((await session.handle(session.token, request())).admission).toBe("expired");
    now = 1; current = false; expect((await session.handle(session.token, request())).admission).toBe("revoked");
    current = true; session.revoke(); expect((await session.handle(session.token, request())).admission).toBe("revoked");
    expect(effects).toBe(0);
  });
});
