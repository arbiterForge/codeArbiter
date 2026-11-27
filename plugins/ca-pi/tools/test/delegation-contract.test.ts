import { describe, expect, test } from "vitest";

import {
  BOOTSTRAP_ENVELOPE_VERSION,
  DELEGATION_PROFILE,
  DelegationContractError,
  MAX_BOOTSTRAP_BYTES,
  canonicalJson,
  createSequenceChecker,
  deepFreeze,
  encodeJournalRecord,
  tokenMatches,
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
// Shape fixture only: a 64-hex string, not a credential.
const TOKEN_SHAPE_FIXTURE = "a".repeat(64);
const ENDPOINT = "http://127.0.0.1:41234/v1/operation";

function reason(fn: () => unknown): string | undefined {
  try { fn(); return undefined; } catch (error) {
    return error instanceof DelegationContractError ? error.reason : `other:${String(error)}`;
  }
}

describe("bootstrap envelope v2 (PI-D01)", () => {
  test("round-trips a reviewer (no delegation) and an author (with delegation) envelope", () => {
    expect(decodeBootstrapEnvelope(encodeBootstrapEnvelope({ nonce: NONCE }))).toEqual({ nonce: NONCE });
    const author = encodeBootstrapEnvelope({ nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN_SHAPE_FIXTURE } });
    expect(Buffer.byteLength(author)).toBeLessThanOrEqual(MAX_BOOTSTRAP_BYTES);
    expect(decodeBootstrapEnvelope(author)).toEqual({ nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN_SHAPE_FIXTURE } });
  });

  test.each([
    ["old 32-byte bare nonce (mixed bundle)", NONCE],
    ["unknown version", canonicalJson({ v: 3, nonce: NONCE })],
    ["v1", canonicalJson({ v: 1, nonce: NONCE })],
    ["truncated", encodeBootstrapEnvelope({ nonce: NONCE }).slice(0, -1)],
    ["oversized", canonicalJson({ v: BOOTSTRAP_ENVELOPE_VERSION, nonce: NONCE, pad: "x".repeat(600) })],
    ["unexpected field", canonicalJson({ v: 2, nonce: NONCE, grant: "all" })],
    ["nonlocal endpoint", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: "http://10.0.0.1:1/v1/operation", token: TOKEN_SHAPE_FIXTURE } })],
    ["localhost hostname", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: "http://localhost:1/v1/operation", token: TOKEN_SHAPE_FIXTURE } })],
    ["wrong path", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: "http://127.0.0.1:1/v1/other", token: TOKEN_SHAPE_FIXTURE } })],
    ["port overflow", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: "http://127.0.0.1:99999/v1/operation", token: TOKEN_SHAPE_FIXTURE } })],
    ["short token", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: ENDPOINT, token: "ab" } })],
    ["extra delegation field", canonicalJson({ v: 2, nonce: NONCE, delegation: { endpoint: ENDPOINT, token: TOKEN_SHAPE_FIXTURE, role: "author" } })],
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
    expect(reason(() => decodeOperationRequest(canonicalJson({ ...base, ...patch })))).toBe("protocol-invalid");
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
    const forged = canonicalJson({ v: 1, seq: 1, requestId: "r", tool, params, digest: operationDigest(tool as "write", params) });
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
    expect(reason(() => decodeOperationResponse(canonicalJson(merged)))).toBe("protocol-invalid");
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
    expect(decodeJournalRecord(canonicalJson(claim))).toMatchObject(claim);
    const observed = { ...claim, phase: "observed", execution: "outcome-unknown", containment: "unverified" };
    expect(decodeJournalRecord(canonicalJson(observed))).toMatchObject(observed);
    for (const bad of [
      { ...claim, v: 2 },
      { ...claim, token: TOKEN_SHAPE_FIXTURE },
      { ...claim, content: "secret" },
      { ...claim, profile: "confined-v1" },
      { ...observed, execution: "not-started" },
      { ...claim, phase: "observed" },
      { ...claim, targetHash: "maybe" },
    ]) expect(reason(() => decodeJournalRecord(canonicalJson(bad)))).toBe("protocol-invalid");
    expect(reason(() => decodeJournalRecord("x".repeat(9_000)))).toBe("protocol-invalid");
  });
});

describe("reviewer LOW items (PI-D01 follow-up)", () => {
  test("duplicate keys, whitespace and reordered keys are refused on every decoder", () => {
    const envelope = encodeBootstrapEnvelope({ nonce: NONCE });
    expect(reason(() => decodeBootstrapEnvelope(envelope.replace('{"nonce"', '{"nonce":"' + "f".repeat(32) + '","nonce"')))).toBe("protocol-invalid");
    expect(reason(() => decodeBootstrapEnvelope(envelope.replace(":", ": ")))).toBe("protocol-invalid");
    const request = encodeOperationRequest({ seq: 1, requestId: "r", tool: "write", params: { path: "a", content: "b" } });
    // A duplicate "path" would let a renderer show one value while the executor uses another.
    const duplicated = request.replace('"params":{', '"params":{"path":"../evil",');
    expect(reason(() => decodeOperationRequest(duplicated))).toBe("protocol-invalid");
    const reordered = '{"v":1,' + request.slice(1).replace(',"v":1', "");
    expect(reason(() => decodeOperationRequest(reordered))).toBe("protocol-invalid");
    const response = encodeOperationResponse(refusalResponse("r", "denied", "permission-denied"));
    expect(reason(() => decodeOperationResponse(response.replace('{"admission"', '{"admission":"admitted","admission"')))).toBe("protocol-invalid");
  });

  test("decoded params are deeply frozen", () => {
    const decoded = decodeOperationRequest(encodeOperationRequest({
      seq: 1, requestId: "r", tool: "edit", params: { path: "a", edits: [{ oldText: "x", newText: "y" }] },
    }));
    expect(Object.isFrozen(decoded.params)).toBe(true);
    expect(Object.isFrozen((decoded.params.edits as object[])[0])).toBe(true);
    expect(deepFreeze({ a: [{ b: 1 }] }).a[0]).toSatisfy(Object.isFrozen);
  });

  test("tokenMatches requires two 64-hex values and compares in constant time", () => {
    const other = "b".repeat(64);
    expect(tokenMatches(TOKEN_SHAPE_FIXTURE, TOKEN_SHAPE_FIXTURE)).toBe(true);
    expect(tokenMatches(TOKEN_SHAPE_FIXTURE, other)).toBe(false);
    expect(tokenMatches(TOKEN_SHAPE_FIXTURE, TOKEN_SHAPE_FIXTURE.toUpperCase())).toBe(false);
    expect(tokenMatches(TOKEN_SHAPE_FIXTURE, TOKEN_SHAPE_FIXTURE.slice(1))).toBe(false);
    expect(tokenMatches(TOKEN_SHAPE_FIXTURE, undefined)).toBe(false);
    expect(tokenMatches("short", "short")).toBe(false);
  });

  test("the sequence checker admits strictly increasing values only", () => {
    const seq = createSequenceChecker();
    expect(seq.accept(0)).toBe(false);
    expect(seq.accept(1)).toBe(true);
    expect(seq.accept(1)).toBe(false);
    expect(seq.accept(3)).toBe(true);
    expect(seq.accept(2)).toBe(false);
    expect(seq.accept(1.5)).toBe(false);
    expect(seq.last).toBe(3);
  });

  test("encodeBootstrapEnvelope refuses a port above 65535", () => {
    expect(reason(() => encodeBootstrapEnvelope({ nonce: NONCE,
      delegation: { endpoint: "http://127.0.0.1:65536/v1/operation", token: TOKEN_SHAPE_FIXTURE } }))).toBe("protocol-invalid");
    expect(reason(() => encodeBootstrapEnvelope({ nonce: NONCE,
      delegation: { endpoint: "http://127.0.0.1:65535/v1/operation", token: TOKEN_SHAPE_FIXTURE } }))).toBeUndefined();
  });

  test("journal records encode canonically and round-trip", () => {
    const claim = {
      v: 1, phase: "claimed", operationId: "c".repeat(64), runId: NONCE, callerCorrelation: "b".repeat(64),
      role: "backend-author", tool: "bash", digest: "d".repeat(64), profile: DELEGATION_PROFILE,
      recordedAt: new Date(0).toISOString(),
    } as const;
    expect(decodeJournalRecord(encodeJournalRecord(claim))).toEqual(claim);
  });
});
