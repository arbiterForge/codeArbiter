/** Parent-only grant lifetime and exact-request replay. No request can create authority. */
import { randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { DELEGATION_PROFILE, createSequenceChecker, decodeOperationRequest, decodeOperationResponse, deepFreeze,
  encodeOperationResponse, MAX_OPERATION_REQUEST_BYTES, refusalResponse, tokenMatches, validRunGrant } from "./delegation-contract.ts";
import type { DelegationReason, DelegationSummary, OperationRequest, OperationResponse, RunGrant } from "./delegation-contract.ts";

export interface DelegationSessionOptions {
  readonly grant: RunGrant;
  readonly isCurrent: () => boolean;
  readonly execute: (request: OperationRequest, signal: AbortSignal) => Promise<Omit<OperationResponse, "v">>;
  readonly signal?: AbortSignal;
  readonly now?: () => number;
}

export function createDelegationSession(options: DelegationSessionOptions) {
  if (!validRunGrant(options.grant)) throw new Error("Invalid parent delegation grant.");
  const grant = deepFreeze(structuredClone(options.grant));
  const token = randomBytes(32).toString("hex");
  const controller = new AbortController();
  const now = options.now ?? (() => performance.now());
  const sequence = createSequenceChecker();
  const requests = new Map<string, { digest: string; response: Promise<OperationResponse> }>();
  const outcomes = new Map<string, OperationResponse>();
  let tail: Promise<unknown> = Promise.resolve();
  const revoke = () => controller.abort();
  options.signal?.addEventListener("abort", revoke, { once: true });
  if (options.signal?.aborted) revoke();
  const current = () => { try { return options.isCurrent() === true; } catch { return false; } };
  // Live run authority also governs already-running commands; cleanup ownership survives abort.
  const monitor = setInterval(() => { if (!current() || now() >= grant.expiresAtMonotonicMs) revoke(); }, 50);
  monitor.unref();
  const refusal = (requestId: string, reason: DelegationReason, admission: "denied" | "expired" | "revoked" = "denied") =>
    decodeOperationResponse(encodeOperationResponse(refusalResponse(requestId, admission, reason)));
  const authorityFailure = (id: string): OperationResponse | undefined => {
    if (controller.signal.aborted || !current()) return refusal(id, "grant-revoked", "revoked");
    if (now() >= grant.expiresAtMonotonicMs) return refusal(id, "grant-expired", "expired");
    return undefined;
  };
  return Object.freeze({
    token,
    revoke,
    summary(): DelegationSummary {
      const values = [...outcomes.values()];
      return Object.freeze({ profile: DELEGATION_PROFILE, observation: "parent-recorded", requested: requests.size,
        completed: values.filter((r) => r.execution === "completed").length,
        failed: values.filter((r) => r.execution === "failed").length,
        refused: values.filter((r) => r.admission !== "admitted").length,
        unknown: values.filter((r) => r.execution === "outcome-unknown").length,
        unsettled: requests.size - outcomes.size,
        containmentUnverified: values.filter((r) => r.containment === "unverified").length });
    },
    async settle(): Promise<void> { revoke(); clearInterval(monitor); await tail; options.signal?.removeEventListener("abort", revoke); },
    async handle(presented: unknown, text: string): Promise<OperationResponse> {
      if (!tokenMatches(token, presented)) return refusal("invalid", "token-invalid");
      let request: OperationRequest;
      try { request = decodeOperationRequest(text); } catch { return refusal("invalid", "protocol-invalid"); }
      const denied = authorityFailure(request.requestId); if (denied !== undefined) return denied;
      const prior = requests.get(request.requestId);
      if (prior !== undefined) return prior.digest === request.digest ? await prior.response : refusal(request.requestId, "operation-id-reused");
      if (!grant.tools.includes(request.tool)) return refusal(request.requestId, "tool-not-delegated");
      if (requests.size >= grant.maxOperations) return refusal(request.requestId, "grant-exhausted");
      if (!sequence.accept(request.seq)) return refusal(request.requestId, "sequence-invalid");
      const response = tail.then(async () => {
        const stopped = authorityFailure(request.requestId); if (stopped !== undefined) return stopped;
        try {
          const result = await options.execute(request, controller.signal);
          return decodeOperationResponse(encodeOperationResponse(result));
        } catch {
          // A throw is not evidence that an admitted operation had no effect.
          return decodeOperationResponse(encodeOperationResponse({ requestId: request.requestId, admission: "admitted",
            execution: "outcome-unknown", containment: "unverified", observation: "unavailable",
            recovery: "read-only-reconciliation", reason: "executor-failed" }));
        }
      });
      requests.set(request.requestId, { digest: request.digest, response });
      void response.then((outcome) => outcomes.set(request.requestId, outcome));
      tail = response;
      return await response;
    },
  });
}

/** Authenticated loopback channel. The bearer travels only in the private bootstrap pipe. */
export async function startDelegationChannel(options: DelegationSessionOptions) {
  const session = createDelegationSession(options);
  const server = createServer(async (request, response) => {
    const deny = () => { response.writeHead(403); response.end(); request.resume(); };
    const auth = request.headers.authorization;
    if (request.method !== "POST" || request.url !== "/v1/operation" || request.headers.origin !== undefined
      || typeof auth !== "string" || !tokenMatches(session.token, auth.startsWith("Bearer ") ? auth.slice(7) : undefined)) {
      deny(); return;
    }
    const chunks: Buffer[] = []; let bytes = 0;
    try {
      for await (const raw of request) {
        const chunk = Buffer.isBuffer(raw) ? raw : Buffer.from(raw as string);
        bytes += chunk.length;
        if (bytes > MAX_OPERATION_REQUEST_BYTES) { response.writeHead(413); response.end(); request.destroy(); return; }
        chunks.push(chunk);
      }
      const result = await session.handle(session.token, Buffer.concat(chunks).toString("utf8"));
      response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
      response.end(encodeOperationResponse(result));
    } catch { if (!response.headersSent) response.writeHead(400); response.end(); }
  });
  server.requestTimeout = 30_000; server.headersTimeout = 10_000; server.maxHeadersCount = 16;
  server.maxConnections = 8;
  try {
    await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
    const address = server.address(); if (address === null || typeof address === "string") throw new Error("Unavailable channel address.");
    return Object.freeze({ endpoint: `http://127.0.0.1:${address.port}/v1/operation`, token: session.token, summary: session.summary,
      revoke: session.revoke, close: async () => {
        session.revoke(); server.closeAllConnections();
        await new Promise<void>((resolve) => server.close(() => resolve())); await session.settle();
      } });
  } catch (error) { session.revoke(); server.close(); throw error; }
}
