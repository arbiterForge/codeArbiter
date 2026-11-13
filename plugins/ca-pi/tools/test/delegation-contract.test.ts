import { describe, expect, test } from "vitest";

import {
  BOOTSTRAP_ENVELOPE_VERSION,
  DELEGATION_PROFILE,
  DelegationContractError,
  MAX_BOOTSTRAP_BYTES,
  canonicalJson,
  decodeBootstrapEnvelope,
  decodeJournalRecord,
  decodeOperationRequest,
  decodeOperationResponse,
  encodeBootstrapEnvelope,
  encodeOperationRequest,
  encodeOperationResponse,
  operationDigest,
  operationId,
  refusalResponse,
  validRunGrant,
} from "../src/delegation-contract.ts";

const NONCE = "0123456789abcdef0123456789abcdef";
const TOKEN = "a".repeat(64);
const ENDPOINT = "http://127.0.0.1:41234/v1/operation";

function reason(fn: () => unknown): string | undefined {
  try { fn(); return undefined; } catch (error) {
    return error instanceof DelegationContractError ? error.reason : `other:${String(error)}`;
  }
}

describe("bootstrap envelope v2 (PI-D01)", () => {
  test("round-trips a reviewer (no delegation) and an author (with delegation) envelope", () => {
    expect(decodeBootstrapEnvelope(encodeBootstrapEnvelope({ nonce: NONCE }))).toEqual({ nonce: NONCE });
    const author = encodeBootstrapEnvelope({ nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN } });
    expect(Buffer.byteLength(author)).toBeLessThanOrEqual(MAX_BOOTSTRAP_BYTES);
    expect(decodeBootstrapEnvelope(author)).toEqual({ nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN } });
  });

  test.each([
    ["old 32-byte bare nonce (mixed bundle)", NONCE],
    ["unknown version", JSON.stringify({ v: 3, nonce: NONCE })],
    ["v1", JSON.stringify({ v: 1, nonce: NONCE })],
    ["truncated", encodeBootstrapEnvelope({ nonce: NONCE }).slice(0, -1)],
    ["oversized", JSON.stringify({ v: BOOTSTRAP_ENVELOPE_VERSION, nonce: NONCE, pad: "x".repeat(600) })],
    ["unexpected field", JSON.stringify({ v: 2, nonce: NONCE, grant: "all" })],
    ["nonlocal endpoint", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: "http://10.0.0.1:1/v1/operation", token: TOKEN } })],
    ["localhost hostname", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: "http://localhost:1/v1/operation", token: TOKEN } })],
    ["wrong path", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: "http://127.0.0.1:1/v1/other", token: TOKEN } })],
    ["port overflow", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: "http://127.0.0.1:99999/v1/operation", token: TOKEN } })],
    ["short token", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: ENDPOINT, token: "ab" } })],
    ["extra delegation field", JSON.stringify({ v: 2, nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN, role: "author" } })],
  ])("refuses %s", (_label, text) => {
    expect(reason(() => decodeBootstrapEnvelope(text))).toBe("protocol-invalid");
  });
});

describe("operation request (PI-D01)", () => {
  const write = { seq: 1, requestId: "req-1", tool: "write" as const, params: { path: "src/a.ts", content: "x\n" } };

  test("round-trips write, edit and bash and binds the digest to tool, params and profile", () => {
    for (const input of [
      write,
      { seq: 2, requestId: "req-2", tool: "edit" as const, params: { path: "src/a.ts", edits: [{ oldText: "x", newText: "y" }] } },
      { seq: 3, requestId: "req-3", tool: "bash" as const, params: { command: "npm test", timeout: 30 } },
    ]) {
      const decoded = decodeOperationRequest(encodeOperationRequest(input));
      expect(decoded).toMatchObject({ ...input, v: 1 });
      expect(decoded.digest).toBe(operationDigest(input.tool, input.params));
    }
    // Same params under a different tool or reordered keys: digest follows content, not spelling.
    expect(operationDigest("write", { path: "a", content: "b" })).toBe(operationDigest("write", { content: "b", path: "a" }));
    expect(operationDigest("write", { path: "a", content: "b" })).not.toBe(operationDigest("write", { path: "a", content: "c" }));
    expect(canonicalJson({ profile: DELEGATION_PROFILE })).toContain("trusted-host-exact-operation-v1");
  });

  test("a digest that does not match the params is refused", () => {
    const text = encodeOperationRequest(write).replace('"x\\n"', '"y\\n"');
    expect(reason(() => decodeOperationRequest(text))).toBe("digest-mismatch");
  });

  test.each([
    ["model-supplied authority field", { grant: "all" }],
    ["model-supplied consent", { approved: true }],
    ["model-supplied cwd", { cwd: "/" }],
    ["unknown version", { v: 2 }],
    ["zero sequence", { seq: 0 }],
    ["request id with path characters", { requestId: "../x" }],
    ["undelegated tool", { tool: "read" }],
  ])("refuses %s", (_label, patch) => {
    const base = JSON.parse(encodeOperationRequest(write)) as Record<string, unknown>;
    expect(reason(() => decodeOperationRequest(JSON.stringify({ ...base, ...patch })))).toBe("protocol-invalid");
  });

  test.each([
    ["write with extra key", "write", { path: "a", content: "b", mode: "0777" }],
    ["write with empty path", "write", { path: "", content: "b" }],
    ["edit with no edits", "edit", { path: "a", edits: [] }],
    ["edit with empty oldText", "edit", { path: "a", edits: [{ oldText: "", newText: "b" }] }],
    ["bash with env override", "bash", { command: "ls", env: { A: "1" } }],
    ["bash with cwd override", "bash", { command: "ls", cwd: "/" }],
    ["bash with negative timeout", "bash", { command: "ls", timeout: -1 }],
    ["bash with blank command", "bash", { command: "  " }],
  ])("refuses invalid params: %s", (_label, tool, params) => {
    expect(reason(() => encodeOperationRequest({ seq: 1, requestId: "r", tool: tool as "write", params }))).toBe("protocol-invalid");
    const forged = JSON.stringify({ v: 1, seq: 1, requestId: "r", tool, params, digest: operationDigest(tool as "write", params) });
    expect(reason(() => decodeOperationRequest(forged))).toBe("protocol-invalid");
  });
});

describe("operation response axes (PI-D01)", () => {
  test("all five axes round-trip without collapsing unknown into failure or no-effect", () => {
    const unknown = { requestId: "r", admission: "admitted", execution: "outcome-unknown", containment: "unverified",
      observation: "target-state-only", recovery: "read-only-reconciliation" } as const;
    expect(decodeOperationResponse(encodeOperationResponse(unknown))).toMatchObject(unknown);
    const completed = { requestId: "r", admission: "admitted", execution: "completed", containment: "verified-stopped",
      observation: "exact", recovery: "none", result: { content: [{ type: "text", text: "ok" }], isError: false } } as const;
    expect(decodeOperationResponse(encodeOperationResponse(completed))).toMatchObject(completed);
    const joined = { requestId: "r", admission: "admitted", execution: "executing", containment: "running",
      observation: "unavailable", recovery: "dependent-resource-held" } as const;
    expect(decodeOperationResponse(encodeOperationResponse(joined))).toMatchObject(joined);
    const stale = { requestId: "r", admission: "admitted", execution: "failed", containment: "not-applicable",
      observation: "stale", recovery: "new-operation-required", reason: "target-invalid" } as const;
    expect(decodeOperationResponse(encodeOperationResponse(stale))).toMatchObject(stale);
    const refused = refusalResponse("r", "denied", "permission-denied");
    expect(decodeOperationResponse(encodeOperationResponse(refused))).toMatchObject({ execution: "not-started", reason: "permission-denied" });
  });

  test.each([
    ["denied but completed", { admission: "denied", execution: "completed", reason: "permission-denied" }],
    ["denied with a result", { admission: "denied", execution: "not-started", reason: "permission-denied", result: { content: [], isError: false } }],
    ["denied without a reason", { admission: "denied", execution: "not-started" }],
    ["unknown outcome claiming nothing to recover", { admission: "admitted", execution: "outcome-unknown", recovery: "none" }],
    ["unknown outcome carrying a result", { admission: "admitted", execution: "outcome-unknown", recovery: "read-only-reconciliation", result: { content: [], isError: false } }],
    ["completed without a result", { admission: "admitted", execution: "completed", result: undefined }],
    ["containment inferred on refusal", { admission: "revoked", execution: "not-started", reason: "grant-revoked", containment: "verified-stopped" }],
    ["free-text reason", { admission: "denied", execution: "not-started", reason: "because the user said so" }],
    ["executing with a result", { admission: "admitted", execution: "executing", recovery: "dependent-resource-held", result: { content: [], isError: false } }],
    ["executing with nothing to recover", { admission: "admitted", execution: "executing", recovery: "none", result: undefined }],
    ["running containment on a completed effect", { admission: "admitted", execution: "completed", containment: "running" }],
    ["stale observation on a completed effect", { admission: "admitted", execution: "completed", observation: "stale" }],
  ])("refuses inconsistent axes: %s", (_label, patch) => {
    const base = { v: 1, requestId: "r", admission: "admitted", execution: "completed", containment: "not-applicable",
      observation: "unavailable", recovery: "none", result: { content: [{ type: "text", text: "ok" }], isError: false } };
    const merged: Record<string, unknown> = { ...base, ...patch };
    if (!("result" in patch) && patch.execution !== "completed") delete merged.result;
    expect(reason(() => decodeOperationResponse(JSON.stringify(merged)))).toBe("protocol-invalid");
  });
});

describe("run grant and journal identity (PI-D01)", () => {
  const grant = {
    runId: NONCE, role: "backend-author", callerCorrelation: "b".repeat(64), worktree: "/repo",
    tools: ["write", "edit", "bash"] as const, maxOperations: 64, expiresAtMonotonicMs: 1_000,
  };

  test("a legitimate author grant validates; unsupported tools, overflow and duplicates refuse", () => {
    expect(validRunGrant(grant)).toBe(true);
    expect(validRunGrant({ ...grant, tools: ["write", "read" as "write"] })).toBe(false);
    expect(validRunGrant({ ...grant, tools: ["write", "write"] })).toBe(false);
    expect(validRunGrant({ ...grant, maxOperations: 10_000 })).toBe(false);
    expect(validRunGrant({ ...grant, runId: "short" })).toBe(false);
  });

  test("two grants with the same role and task text still get distinct operation identities", () => {
    expect(operationId(NONCE, "req-1")).not.toBe(operationId("f".repeat(32), "req-1"));
    // The digest is not part of the id, so reusing an id with new bytes collides by design.
    expect(operationId(NONCE, "req-1")).toBe(operationId(NONCE, "req-1"));
  });

  test("journal records decode only as closed bounded versioned data", () => {
    const claim = {
      v: 1, phase: "claimed", operationId: "c".repeat(64), runId: NONCE, callerCorrelation: "b".repeat(64),
      role: "backend-author", tool: "write", digest: "d".repeat(64), profile: DELEGATION_PROFILE,
      target: "src/a.ts", targetHash: "absent", recordedAt: new Date(0).toISOString(),
    };
    expect(decodeJournalRecord(JSON.stringify(claim))).toMatchObject(claim);
    const observed = { ...claim, phase: "observed", execution: "outcome-unknown", containment: "unverified" };
    expect(decodeJournalRecord(JSON.stringify(observed))).toMatchObject(observed);
    for (const bad of [
      { ...claim, v: 2 },
      { ...claim, token: TOKEN },
      { ...claim, content: "secret" },
      { ...claim, profile: "confined-v1" },
      { ...observed, execution: "not-started" },
      { ...claim, phase: "observed" },
      { ...claim, targetHash: "maybe" },
    ]) expect(reason(() => decodeJournalRecord(JSON.stringify(bad)))).toBe("protocol-invalid");
    expect(reason(() => decodeJournalRecord("x".repeat(9_000)))).toBe("protocol-invalid");
  });
});
