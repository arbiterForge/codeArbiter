/** inference-broker.test.ts - #455 loopback inference broker contract.
 *
 * The child never holds the operator credential. It holds a per-child ephemeral token bound to
 * its own nonce, and the parent's loopback broker exchanges that token for the real credential
 * on the way upstream. These are the obligations that make that safe. */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { AddressInfo } from "node:net";
import { afterEach, describe, expect, test } from "vitest";

type BrokerModule = typeof import("../src/inference-broker.ts");

async function loadImplementation(): Promise<BrokerModule> {
  const path = "../src/inference-broker.ts";
  try {
    return await import(path) as BrokerModule;
  } catch (error) {
    throw new Error("#455 loopback inference broker implementation is missing", { cause: error });
  }
}

/** A planted literal, not real key material: the probe only needs a value it can search
 * for on both sides of the broker. */
const PLANTED_UPSTREAM_LITERAL = "planted-upstream-literal-0123456789";
const NONCE_A = "0123456789abcdef0123456789abcde0";
const NONCE_B = "fedcba9876543210fedcba98765432f1";

interface UpstreamCapture {
  server: Server;
  baseUrl: string;
  requests: { path: string; method: string; headers: Record<string, string | string[] | undefined>; body: string }[];
  /** Resolves once the handler has written the first SSE frame but BEFORE it writes the last. */
  holdSecondFrame: () => void;
}

/** A deliberately SLOW streaming upstream: it writes one frame, waits for an external release,
 * then writes the rest. A buffering proxy cannot deliver the first frame before the release. */
function startUpstream(): Promise<UpstreamCapture> {
  let release = (): void => undefined;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const requests: UpstreamCapture["requests"] = [];
  const handler = (request: IncomingMessage, response: ServerResponse): void => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      requests.push({
        path: request.url ?? "",
        method: request.method ?? "",
        headers: { ...request.headers },
        body: Buffer.concat(chunks).toString("utf8"),
      });
      if (request.headers.authorization !== `Bearer ${PLANTED_UPSTREAM_LITERAL}`) {
        response.writeHead(401, { "Content-Type": "application/json" });
        response.end('{"error":"missing operator credential"}');
        return;
      }
      response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
      response.write("data: {\"first\":true}\n\n");
      void gate.then(() => {
        response.write("data: {\"second\":true}\n\n");
        response.end("data: [DONE]\n\n");
      });
    });
  };
  const server = createServer(handler);
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address() as AddressInfo;
      resolve({
        server,
        baseUrl: `http://127.0.0.1:${address.port}/v1`,
        requests,
        holdSecondFrame: () => release(),
      });
    });
  });
}

const openBrokers: { close(): Promise<void> }[] = [];
const openUpstreams: Server[] = [];

afterEach(async () => {
  while (openBrokers.length > 0) await openBrokers.pop()!.close().catch(() => undefined);
  while (openUpstreams.length > 0) {
    const server = openUpstreams.pop()!;
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

async function brokerFor(nonce: string, upstreamBaseUrl?: string) {
  const { startInferenceBroker } = await loadImplementation();
  const broker = await startInferenceBroker({ nonce });
  openBrokers.push(broker);
  if (upstreamBaseUrl !== undefined) {
    broker.authorize({ nonce, baseUrl: upstreamBaseUrl, credential: PLANTED_UPSTREAM_LITERAL });
  }
  return broker;
}

describe("#455 loopback inference broker", () => {
  test("binds loopback on an OS-assigned port and never a wildcard address", async () => {
    const broker = await brokerFor(NONCE_A);
    const url = new URL(broker.baseUrl);
    expect(url.protocol).toBe("http:");
    expect(url.hostname).toBe("127.0.0.1");
    expect(url.pathname).toBe("/v1");
    expect(url.search).toBe("");
    expect(Number(url.port)).toBeGreaterThan(0);
    const second = await brokerFor(NONCE_B);
    expect(new URL(second.baseUrl).port).not.toBe(url.port);
  });

  test("mints a per-child token bound to that child's nonce", async () => {
    const first = await brokerFor(NONCE_A);
    const second = await brokerFor(NONCE_A);
    const other = await brokerFor(NONCE_B);
    expect(first.token).toMatch(/^[0-9a-f]{64}$/u);
    expect(first.nonce).toBe(NONCE_A);
    // Same nonce, different child: still a distinct secret (per-child, not per-nonce-only), and
    // never a function of the nonce the child itself holds.
    expect(second.token).not.toBe(first.token);
    expect(other.token).not.toBe(first.token);
    expect(first.token).not.toContain(NONCE_A);
  });

  test("refuses to attach the operator credential under any other child's nonce", async () => {
    const broker = await brokerFor(NONCE_A);
    expect(() => broker.authorize({
      nonce: NONCE_B, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL,
    })).toThrow();
    expect(() => broker.authorize({
      nonce: `${NONCE_A}extra`, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL,
    })).toThrow();
    expect(() => broker.authorize({
      nonce: NONCE_A, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL,
    })).not.toThrow();
  });

  test("refuses to attach an upstream authority once the owning child has exited", async () => {
    const broker = await brokerFor(NONCE_A);
    broker.revoke();
    expect(() => broker.authorize({
      nonce: NONCE_A, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL,
    })).toThrow();
  });

  test("exchanges the child token for the operator credential and streams incrementally", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "gpt-test", stream: true }),
    });
    expect(response.status).toBe(200);
    const reader = response.body!.getReader();
    // The upstream is still holding the second frame. A broker that buffered to completion
    // could not have produced this chunk yet.
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toContain("\"first\":true");
    upstream.holdSecondFrame();
    let rest = "";
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      rest += new TextDecoder().decode(next.value);
    }
    expect(rest).toContain("\"second\":true");
    expect(upstream.requests).toHaveLength(1);
    expect(upstream.requests[0]!.path).toBe("/v1/chat/completions");
    expect(upstream.requests[0]!.headers.authorization).toBe(`Bearer ${PLANTED_UPSTREAM_LITERAL}`);
    expect(JSON.stringify(upstream.requests[0]!.headers)).not.toContain(broker.token);
  });

  test("substitutes a bare api-key header as well as a bearer scheme", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    upstream.holdSecondFrame();
    const response = await fetch(`${broker.baseUrl}/messages`, {
      method: "POST",
      headers: { "x-api-key": broker.token, "Content-Type": "application/json" },
      body: "{}",
    });
    await response.text();
    expect(upstream.requests[0]!.headers["x-api-key"]).toBe(PLANTED_UPSTREAM_LITERAL);
  });

  test("rejects a token captured from one child when a second child's broker sees it", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const victim = await brokerFor(NONCE_A, upstream.baseUrl);
    const attacker = await brokerFor(NONCE_B, upstream.baseUrl);
    const response = await fetch(`${attacker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${victim.token}` },
      body: "{}",
    });
    expect(response.status).toBe(401);
    expect(upstream.requests).toHaveLength(0);
  });

  test("rejects the owning child's token once that child has exited", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    broker.revoke();
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(response.status).toBe(503);
    expect(upstream.requests).toHaveLength(0);
  });

  test("refuses every request before the upstream authority is bound", async () => {
    const broker = await brokerFor(NONCE_A);
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(response.status).toBe(503);
  });

  test("the fail-closed diagnostic is fixed and leaks no credential, token, or operator path", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const bodies: string[] = [];
    for (const init of [
      { headers: { Authorization: "Bearer not-the-token" } },
      { headers: { Authorization: `Bearer ${broker.token}` }, path: "/../../etc/passwd" },
      { headers: {}, path: "/chat/completions" },
    ]) {
      const response = await fetch(`${broker.baseUrl}${(init as { path?: string }).path ?? "/chat/completions"}`, {
        method: "POST",
        headers: init.headers as Record<string, string>,
        body: "{}",
      });
      expect(response.status).toBeGreaterThanOrEqual(400);
      bodies.push(await response.text());
    }
    for (const body of bodies) {
      expect(body.length).toBeLessThanOrEqual(256);
      expect(body).not.toContain(PLANTED_UPSTREAM_LITERAL);
      expect(body).not.toContain(broker.token);
      expect(body).not.toContain(upstream.baseUrl);
      expect(body).toContain("codeArbiter inference broker");
    }
    expect(new Set(bodies).size).toBe(1);
  });

  test("an unreachable upstream fails closed rather than surfacing the endpoint", async () => {
    const dead = await startUpstream();
    const deadBaseUrl = dead.baseUrl;
    await new Promise<void>((resolve) => dead.server.close(() => resolve()));
    const broker = await brokerFor(NONCE_A, deadBaseUrl);
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(response.status).toBe(502);
    const body = await response.text();
    expect(body).not.toContain(deadBaseUrl);
    expect(body).toContain("codeArbiter inference broker");
  });

  test("closing the broker stops the listener so it cannot outlive the child", async () => {
    const broker = await brokerFor(NONCE_A);
    const baseUrl = broker.baseUrl;
    await broker.close();
    await expect(fetch(`${baseUrl}/chat/completions`, { method: "POST", body: "{}" })).rejects.toThrow();
    await expect(broker.close()).resolves.toBeUndefined();
  });

  test("refuses an upstream authority that is not a bare credential-free endpoint", async () => {
    const broker = await brokerFor(NONCE_A);
    for (const baseUrl of [
      "file:///c:/operator/.pi/auth.json",
      "https://operator:pw@gateway.example/v1",
      "https://gateway.example/v1?api-key=sk-live",
      "https://gateway.example/v1#sk-live",
      "not-a-url",
    ]) {
      expect(() => broker.authorize({ nonce: NONCE_A, baseUrl, credential: PLANTED_UPSTREAM_LITERAL })).toThrow();
    }
  });

  test("refuses a nonce that is not the runner's 128-bit hex handshake nonce", async () => {
    const { startInferenceBroker } = await loadImplementation();
    for (const nonce of ["", "short", "0123456789ABCDEF0123456789ABCDEF", `${NONCE_A}0`]) {
      await expect(startInferenceBroker({ nonce })).rejects.toThrow();
    }
  });
});
