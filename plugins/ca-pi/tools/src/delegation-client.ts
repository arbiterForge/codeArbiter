/** Isolated child proxies: forward exact operations; never execute a local mutator. */
import { randomUUID } from "node:crypto";
import { request as httpRequest } from "node:http";
import { decodeBootstrapEnvelope, decodeOperationResponse, encodeBootstrapEnvelope, encodeOperationRequest } from "./delegation-contract.ts";
import type { DelegatedTool, DelegationEndpoint, OperationResponse } from "./delegation-contract.ts";
import type { ToolDefinitionPort } from "./contracts.ts";

const MAX_RESPONSE_BYTES = 1_100_000;
export function createDelegationClient(endpoint: DelegationEndpoint) {
  // Validate even injected callers against the same closed bootstrap grammar.
  decodeBootstrapEnvelope(encodeBootstrapEnvelope({ nonce: "0".repeat(32), delegation: endpoint }));
  const connection = Object.freeze({ endpoint: endpoint.endpoint, token: endpoint.token });
  let sequence = 0;
  let tail: Promise<unknown> = Promise.resolve();
  return Object.freeze({
    execute(tool: DelegatedTool, params: Readonly<Record<string, unknown>>, signal?: AbortSignal): Promise<OperationResponse> {
      const text = encodeOperationRequest({ seq: ++sequence, requestId: randomUUID(), tool, params });
      const send = () => new Promise<OperationResponse>((resolve, reject) => {
        if (signal?.aborted) { reject(new Error("Delegation cancelled.")); return; }
        const request = httpRequest(connection.endpoint, { method: "POST", signal,
          headers: { authorization: `Bearer ${connection.token}`, "content-type": "application/json", "content-length": Buffer.byteLength(text) } },
        (response) => {
          if (response.statusCode !== 200) { response.resume(); reject(new Error("Delegation unavailable.")); return; }
          const chunks: Buffer[] = []; let bytes = 0;
          response.on("data", (raw: Buffer) => {
            bytes += raw.length;
            if (bytes > MAX_RESPONSE_BYTES) { response.destroy(); reject(new Error("Delegation response exceeded bounds.")); }
            else chunks.push(raw);
          });
          response.on("error", () => reject(new Error("Delegation response unavailable.")));
          response.on("end", () => {
            try { resolve(decodeOperationResponse(Buffer.concat(chunks).toString("utf8"))); }
            catch { reject(new Error("Delegation response invalid.")); }
          });
        });
        request.setTimeout(610_000, () => request.destroy(new Error("Delegation timed out.")));
        request.on("error", () => reject(new Error("Delegation transport unavailable; effect outcome is unknown.")));
        request.end(text);
      });
      const response = tail.then(send); tail = response.catch(() => undefined);
      return response;
    },
  });
}

export function delegatedToolFactory(tool: DelegatedTool, native: (cwd: string) => ToolDefinitionPort,
  client: ReturnType<typeof createDelegationClient>, ready: () => boolean): (cwd: string) => ToolDefinitionPort {
  return (cwd) => {
    const metadata = native(cwd);
    return { ...metadata, execute: async (_id, params, signal) => {
      if (!ready()) throw new Error("Delegated child is not ready.");
      try {
        const response = await client.execute(tool, params, signal);
        if (response.result !== undefined) return { ...response.result, details: response };
        return { content: [{ type: "text", text: JSON.stringify(response) }], isError: true, details: response };
      } catch {
        return { content: [{ type: "text", text: "Parent delegation unavailable; effect outcome may be unknown. Observe before any new attempt." }], isError: true };
      }
    } };
  };
}
