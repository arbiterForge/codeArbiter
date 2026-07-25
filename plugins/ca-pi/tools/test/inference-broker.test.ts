/** inference-broker.test.ts - #455 loopback inference broker contract.
 *
 * The child never holds the operator credential. It holds a per-child ephemeral token bound to
 * its own nonce, and the parent's loopback broker exchanges that token for the real credential
 * on the way upstream. These are the obligations that make that safe. */
import { once } from "node:events";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { AddressInfo, connect, type Socket } from "node:net";
import { gzipSync } from "node:zlib";
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
/** A second planted literal standing for an operator-configured provider header value — the
 * parent resolves those from ITS environment, so they are operator material on the same footing
 * as the credential and belong to the same scrub set. */
const PLANTED_OPERATOR_HEADER = "planted-operator-header-9876543210";
const NONCE_A = "0123456789abcdef0123456789abcde0";
const NONCE_B = "fedcba9876543210fedcba98765432f1";

/** The parent's own sensitive-value predicate, in the shape `prepareChildEnvironment` produces
 * it. The broker is handed the predicate rather than the values, so it can refuse to relay
 * operator material back to the child without ever enumerating the scrub set itself. */
const containsPlantedValue = (text: string): boolean =>
  text.includes(PLANTED_UPSTREAM_LITERAL) || text.includes(PLANTED_OPERATOR_HEADER);

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

/** A bare upstream under the probe's exact control, for the response-path obligations: the test
 * decides byte for byte what comes back, including a deliberately leaky provider. */
function startRawUpstream(
  handler: (request: IncomingMessage, response: ServerResponse) => void,
): Promise<{ server: Server; baseUrl: string; requests: number }> {
  const state = { requests: 0 };
  const server = createServer((request, response) => {
    state.requests += 1;
    request.resume();
    request.on("end", () => handler(request, response));
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address() as AddressInfo;
      resolve(Object.defineProperty({ server, baseUrl: `http://127.0.0.1:${address.port}/v1` }, "requests", {
        get: () => state.requests,
      }) as { server: Server; baseUrl: string; requests: number });
    });
  });
}

/** Exactly what the CHILD ends up holding. A refusal on the response path can surface either as a
 * failed `fetch` (the reset lands before the response resolves) or as a body stream that errors
 * mid-read; both are the same outcome to the child, and the assertion that matters is what bytes
 * it actually got. */
async function clientOutcome(
  broker: { baseUrl: string; token: string },
): Promise<{ failed: boolean; received: string; status?: number }> {
  let response: Response;
  try {
    response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
  } catch {
    return { failed: true, received: "" };
  }
  let received = "";
  try {
    for await (const chunk of response.body as unknown as AsyncIterable<Uint8Array>) {
      received += new TextDecoder().decode(chunk);
    }
  } catch {
    return { failed: true, received, status: response.status };
  }
  return { failed: false, received, status: response.status };
}

const openBrokers: { close(): Promise<void> }[] = [];
const openUpstreams: Server[] = [];
const openSockets: Socket[] = [];

afterEach(async () => {
  while (openSockets.length > 0) openSockets.pop()!.destroy();
  while (openBrokers.length > 0) await openBrokers.pop()!.close().catch(() => undefined);
  while (openUpstreams.length > 0) {
    const server = openUpstreams.pop()!;
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

async function brokerFor(
  nonce: string,
  upstreamBaseUrl?: string,
  headers?: Record<string, string>,
) {
  const { startInferenceBroker } = await loadImplementation();
  const broker = await startInferenceBroker({ nonce });
  openBrokers.push(broker);
  if (upstreamBaseUrl !== undefined) {
    broker.authorize({
      nonce,
      baseUrl: upstreamBaseUrl,
      credential: PLANTED_UPSTREAM_LITERAL,
      containsSensitiveValue: containsPlantedValue,
      ...(headers === undefined ? {} : { headers }),
    });
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
      nonce: NONCE_B, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL, containsSensitiveValue: containsPlantedValue,
    })).toThrow();
    expect(() => broker.authorize({
      nonce: `${NONCE_A}extra`, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL, containsSensitiveValue: containsPlantedValue,
    })).toThrow();
    expect(() => broker.authorize({
      nonce: NONCE_A, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL, containsSensitiveValue: containsPlantedValue,
    })).not.toThrow();
  });

  test("refuses to attach an upstream authority once the owning child has exited", async () => {
    const broker = await brokerFor(NONCE_A);
    broker.revoke();
    expect(() => broker.authorize({
      nonce: NONCE_A, baseUrl: "https://api.example/v1", credential: PLANTED_UPSTREAM_LITERAL, containsSensitiveValue: containsPlantedValue,
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
      expect(() => broker.authorize({ nonce: NONCE_A, baseUrl, credential: PLANTED_UPSTREAM_LITERAL, containsSensitiveValue: containsPlantedValue })).toThrow();
    }
  });

  test("refuses a nonce that is not the runner's 128-bit hex handshake nonce", async () => {
    const { startInferenceBroker } = await loadImplementation();
    for (const nonce of ["", "short", "0123456789ABCDEF0123456789ABCDEF", `${NONCE_A}0`]) {
      await expect(startInferenceBroker({ nonce })).rejects.toThrow();
    }
  });

  // Review finding (MEDIUM): the forwarded-header rule was a DENY list — hop-by-hop plus `host` —
  // so every other child-supplied header rode verbatim onto a request that the broker had just
  // attached the operator's real credential to. The operator's `baseUrl` is frequently a routing
  // gateway (openrouter, vercel-ai-gateway, cloudflare-ai-gateway are all in the pinned table),
  // and gateways route on request headers. A compromised child must not steer a credentialed
  // request, so the rule is now an ALLOW list of what a provider call actually needs.
  test("drops every child header a provider call does not need", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    upstream.holdSecondFrame();
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${broker.token}`,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-probe-pid": "42480",
        "x-forwarded-for": "10.0.0.1",
        "cf-aig-metadata": "gateway-routing-directive",
        "x-stainless-lang": "js",
        "x-title": "child-chosen-attribution",
      },
      body: "{}",
    });
    await response.text();
    const forwarded = upstream.requests[0]!.headers;
    // What a provider call legitimately needs still crosses...
    expect(forwarded.authorization).toBe(`Bearer ${PLANTED_UPSTREAM_LITERAL}`);
    expect(forwarded["content-type"]).toBe("application/json");
    expect(forwarded["anthropic-version"]).toBe("2023-06-01");
    // ...and everything unrecognised is dropped rather than ridden upstream.
    for (const dropped of ["x-probe-pid", "x-forwarded-for", "cf-aig-metadata", "x-stainless-lang", "x-title"]) {
      expect(forwarded[dropped], `${dropped} rode onto a credentialed upstream request`).toBeUndefined();
    }
    // The child's own `host` names the loopback broker and must never reach the provider.
    expect(forwarded.host).toBe(new URL(upstream.baseUrl).host);
  });

  test("will not place the operator credential under a header name of the child's choosing", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    // The broker deliberately hard-codes no auth scheme, so before the allow-list it would
    // substitute the real credential into ANY header carrying the token.
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { "x-whatever": `Bearer ${broker.token}`, "Content-Type": "application/json" },
      body: "{}",
    });
    expect(response.status).toBe(401);
    expect(upstream.requests).toHaveLength(0);
  });

  // The upstream must see plaintext for the response filter below to mean anything: a gzipped
  // body would carry an echoed credential straight past a byte scan.
  test("negotiates an unencoded upstream body whatever the child asked for", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    upstream.holdSecondFrame();
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}`, "Accept-Encoding": "gzip, br", "Content-Type": "application/json" },
      body: "{}",
    });
    await response.text();
    expect(upstream.requests[0]!.headers["accept-encoding"]).toBe("identity");
  });

  // Review finding (MEDIUM): operator-configured headers are applied LAST so a child cannot
  // displace them, but nothing asserted it — deleting the loop entirely stayed green. Node
  // lower-cases inbound header names, so the child's spelling and the operator's rarely match
  // by case; an overwrite that is not case-insensitive emits BOTH values.
  test("applies operator headers last so a child cannot displace or duplicate them", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl, {
      "Anthropic-Beta": PLANTED_OPERATOR_HEADER,
      "X-Ca-Gateway": PLANTED_OPERATOR_HEADER,
    });
    upstream.holdSecondFrame();
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${broker.token}`,
        // An allow-listed header the operator also configures — the only shape that can actually
        // contest the operator's value.
        "anthropic-beta": "child-controlled",
        "x-ca-gateway": "child-controlled",
      },
      body: "{}",
    });
    await response.text();
    const forwarded = upstream.requests[0]!.headers;
    expect(forwarded["anthropic-beta"]).toBe(PLANTED_OPERATOR_HEADER);
    expect(forwarded["x-ca-gateway"]).toBe(PLANTED_OPERATOR_HEADER);
    expect(JSON.stringify(forwarded)).not.toContain("child-controlled");
  });

  // Review finding (MEDIUM): `upstreamResponse.pipe(response)` handed the child the provider's
  // bytes verbatim, headers included, and the design document did not enumerate it. Any upstream
  // that reflects the request credential — a debug/echo mode on an operator-run gateway, a
  // verbose 401 — delivered the operator credential into the child. The parent already holds the
  // predicate that recognises its own operator material; the broker now applies it.
  test("fails closed when the upstream reflects operator material in a response header", async () => {
    const upstream = await startRawUpstream((_request, response) => {
      response.writeHead(200, {
        "Content-Type": "application/json",
        "x-debug-echo-auth": `Bearer ${PLANTED_UPSTREAM_LITERAL}`,
      });
      response.end('{"ok":true}');
    });
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(upstream.requests).toBe(1);
    expect(response.status).toBe(502);
    expect(response.headers.get("x-debug-echo-auth")).toBeNull();
    const body = await response.text();
    expect(body).not.toContain(PLANTED_UPSTREAM_LITERAL);
    expect(body).toContain("codeArbiter inference broker");
  });

  // The common shape: a verbose provider error that echoes the credential arrives whole in the
  // first chunk, before any byte is committed to the child. Because headers are held until the
  // first byte clears the filter, that refuses with the ordinary fixed body and a real status —
  // never a torn connection, and never a clean empty 200 the child could mistake for an answer.
  test("refuses with the fixed diagnostic when the upstream reflects operator material", async () => {
    const upstream = await startRawUpstream((_request, response) => {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(`{"error":{"message":"invalid key ${PLANTED_UPSTREAM_LITERAL}"}}`);
    });
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const outcome = await clientOutcome(broker);
    expect(outcome.failed).toBe(false);
    expect(outcome.status).toBe(502);
    expect(outcome.received).not.toContain(PLANTED_UPSTREAM_LITERAL);
    // Byte-identical to every other refusal, so the child learns only that the broker refused.
    expect(outcome.received).toContain("codeArbiter inference broker");
    expect(outcome.received.length).toBeLessThanOrEqual(256);
  });

  // The request negotiates `identity`, so an encoded body means an upstream that ignored it —
  // and an encoded body is one the filter cannot read. Relaying it blind would hand the child a
  // channel the whole response control is deaf to.
  test("refuses a compressed upstream body rather than relaying one it cannot scan", async () => {
    const compressed = gzipSync(Buffer.from(`{"error":"invalid key ${PLANTED_UPSTREAM_LITERAL}"}`, "utf8"));
    const upstream = await startRawUpstream((_request, response) => {
      response.writeHead(200, { "Content-Type": "application/json", "Content-Encoding": "gzip" });
      response.end(compressed);
    });
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const outcome = await clientOutcome(broker);
    expect(outcome.status).toBe(502);
    expect(outcome.received).toContain("codeArbiter inference broker");
    expect(outcome.received).not.toContain(PLANTED_UPSTREAM_LITERAL);
  });

  // A value split across two TCP writes is the shape a naive per-chunk scan misses. The filter
  // keeps an overlap window so the value is whole in some scanned window.
  //
  // Stated residual, matching the module comment: because clean bytes are forwarded eagerly (the
  // alternative — holding a window back — deadlocks incremental streaming), the LEADING fragment
  // written before the match completes has already reached the child. The complete value never
  // does, and the stream is left truncated rather than terminated.
  test("catches operator material split across upstream chunk boundaries", async () => {
    const half = Math.floor(PLANTED_OPERATOR_HEADER.length / 2);
    const terminator = '"}\n\n';
    const upstream = await startRawUpstream((_request, response) => {
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.write(`data: {"note":"${PLANTED_OPERATOR_HEADER.slice(0, half)}`);
      setTimeout(() => response.end(`${PLANTED_OPERATOR_HEADER.slice(half)}${terminator}`), 25);
    });
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const outcome = await clientOutcome(broker);
    expect(outcome.received).not.toContain(PLANTED_OPERATOR_HEADER);
    // The second half never crossed, so the frame the upstream sent is truncated in flight.
    expect(outcome.received).not.toContain(PLANTED_OPERATOR_HEADER.slice(half));
    expect(outcome.received).not.toContain(terminator);
  });

  // The filter must not be a blunt "always abort": an ordinary provider answer still arrives
  // byte for byte, or the control would be indistinguishable from a broken broker.
  test("passes an ordinary provider response through untouched", async () => {
    const payload = '{"choices":[{"message":{"content":"an ordinary answer"}}]}';
    const upstream = await startRawUpstream((_request, response) => {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(payload);
    });
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const response = await fetch(`${broker.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(response.status).toBe(200);
    expect(await response.text()).toBe(payload);
  });

  // Review finding (LOW): the traversal comment claimed `new URL` resolution made the prefix test
  // sufficient. It does for `..`, `%2e%2e`, `%2E%2E` and `.%2e`, but WHATWG URL normalises encoded
  // dots and NOT encoded slashes, so `/v1/..%2fadmin` passed the prefix test and was forwarded
  // with its encoding intact — leaving the escape to the upstream's own decode-then-route order.
  test("refuses a request target carrying an encoded path separator", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    for (const target of ["/v1/..%2fadmin", "/v1/..%2Fadmin", "/v1/..%5cadmin", "/v1/%2e%2e%2fadmin"]) {
      const response = await fetch(`${broker.baseUrl.replace(/\/v1$/u, "")}${target}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${broker.token}` },
        body: "{}",
      });
      expect(response.status, `${target} must not reach the upstream`).toBe(404);
    }
    // The unencoded shapes stay closed too, and nothing was forwarded at all.
    expect(upstream.requests).toHaveLength(0);
  });

  // Review finding (LOW): the request-target byte cap carried no test — removing it stayed green.
  test("refuses an oversized request target before contacting the upstream", async () => {
    const upstream = await startUpstream();
    openUpstreams.push(upstream.server);
    const broker = await brokerFor(NONCE_A, upstream.baseUrl);
    const response = await fetch(`${broker.baseUrl}/chat/${"a".repeat(2_100)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${broker.token}` },
      body: "{}",
    });
    expect(response.status).toBe(404);
    expect(upstream.requests).toHaveLength(0);
  });

  // Review finding (LOW): the interface promises `close()` "destroys every open socket", but
  // deleting the destruction loop stayed green. It is load-bearing — `server.close()` alone waits
  // for every idle keep-alive connection, so a child holding one open would keep an authorized
  // listener alive for as long as it liked.
  test("close() destroys a still-open connection instead of waiting on it", async () => {
    const broker = await brokerFor(NONCE_A);
    const { hostname, port } = new URL(broker.baseUrl);
    const socket = connect({ host: hostname, port: Number(port) });
    openSockets.push(socket);
    await once(socket, "connect");
    const peerClosed = once(socket, "close");
    // `server.close()` alone waits for every open connection, so without the destruction loop the
    // broker cannot finish closing while any child holds a socket open.
    const closed = await Promise.race([
      broker.close().then(() => "closed" as const),
      new Promise<"hung">((resolve) => setTimeout(() => resolve("hung"), 3_000)),
    ]);
    expect(closed).toBe("closed");
    // ...and the connection is torn down from the broker's end, not merely orphaned.
    await Promise.race([
      peerClosed,
      new Promise((_resolve, reject) => setTimeout(() => reject(new Error("connection survived close()")), 3_000)),
    ]);
  });
});
