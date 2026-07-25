/** inference-broker.ts - codeArbiter's per-child loopback inference broker (#455).
 *
 * The isolated Pi child no longer receives the operator's provider credential in ANY form. It
 * receives a per-child ephemeral token and a projected provider configuration whose `baseUrl`
 * names this broker's loopback listener. The child's Pi makes ordinary calls to it; this module
 * authenticates the token, swaps in the real credential, forwards upstream, and streams the
 * response back incrementally.
 *
 * Residual, stated rather than assumed away: a listening loopback socket is reachable by ANY
 * process running as the same OS user, and the token is the only thing standing in front of it.
 * The token is minted per child from 256 bits of CSPRNG material, bound to exactly one child's
 * handshake nonce, accepted only by the one broker that minted it, and refused the moment its
 * child exits. A captured token is worthless OFF-HOST — the listener binds 127.0.0.1 only.
 *
 * It is NOT worthless to a second process, and this module does not claim that it is. The token
 * binds to the minting BROKER, not to a process: `handle` compares the token and nothing else,
 * and no peer, pid, or connection binding is available over a loopback socket. Any same-user
 * process that OBTAINS the token can therefore USE the operator's credential — use, not read —
 * for as long as the owning child lives, replaying it freely within that window, since the token
 * is deliberately not single-use.
 *
 * That residual is accepted rather than overlooked. A process running as the operator can
 * already read the operator's credential store directly, so brokering adds no exposure such an
 * attacker did not already have, and it is strictly narrower than the projected credential file
 * it replaces — which handed that same process the raw, exfiltratable key. What the design buys
 * is use instead of disclosure, bounded by the child's lifetime and by the host.
 *
 * The token is deliberately NOT derived from the child's nonce. The child holds its own nonce
 * (the runner hands it over the capability pipe), so a nonce-derived token would make the
 * child's secret a function of a value the child already possesses. Fresh CSPRNG material
 * bound to the nonce by the broker's own record is strictly stronger. */
import { randomBytes, timingSafeEqual } from "node:crypto";
import {
  createServer,
  request as httpRequest,
  type IncomingHttpHeaders,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { request as httpsRequest } from "node:https";
import type { AddressInfo, Socket } from "node:net";
import { Transform, type TransformCallback } from "node:stream";

/** The child's projected provider configuration names this variable, never a literal token, so
 * the projected configuration file itself carries no secret material at all. */
export const BROKER_TOKEN_ENV_NAME = "CODEARBITER_PI_BROKER_TOKEN";

/** The fixed route prefix the child's projected `baseUrl` carries. Everything the child appends
 * after it is remapped onto the operator's real upstream base path. */
const BROKER_ROUTE_PREFIX = "/v1";

const MAX_REQUEST_TARGET_BYTES = 2_048;
const MAX_UPSTREAM_BASE_BYTES = 512;
const UPSTREAM_PROTOCOLS = new Set(["http:", "https:"]);

/** Hop-by-hop headers are connection-scoped by RFC 9110 and must not be relayed in either
 * direction; `host` belongs to the connection the same way, and on the request path is rewritten
 * to the upstream authority because the child's value names this loopback listener. */
const HOP_BY_HOP_HEADERS = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade", "host",
]);

/** Exactly what a provider call needs from the CHILD, and nothing else.
 *
 * This is an allow list on purpose. A deny list — hop-by-hop plus `host` — forwarded every other
 * child-supplied header verbatim onto a request the broker had just attached the operator's REAL
 * credential to. The destination origin is fixed, so that is not direct exfiltration, but the
 * operator's `baseUrl` is frequently a routing gateway (`openrouter`, `vercel-ai-gateway`,
 * `cloudflare-ai-gateway` are all pinned built-ins) and gateways route on request headers. A
 * compromised child must not get to steer a credentialed request.
 *
 * Deliberately absent, because a provider call succeeds without them: client telemetry
 * (`x-stainless-*`), attribution (`x-title`, `http-referer`), forwarding and gateway-control
 * headers, and anything unrecognised. Operator-configured headers are NOT filtered here — they
 * are parent material and are applied after this map. */
const FORWARDED_REQUEST_HEADERS = new Set([
  "accept", "content-length", "content-type", "user-agent",
  // The auth carriers Pi 0.80.x builds around a provider `apiKey`. Because only these cross, the
  // credential can only ever be substituted under one of these names — never one the child picks.
  "api-key", "authorization", "x-api-key", "x-goog-api-key",
  // Protocol/version negotiation, which decides the response SHAPE the child has to parse.
  "anthropic-beta", "anthropic-dangerous-direct-browser-access", "anthropic-version",
  "openai-beta", "openai-organization", "openai-project",
  // opencode's opaque client/session identity. Those providers require an explicit operator
  // `baseUrl` anyway, and neither value is a routing directive.
  "x-opencode-client", "x-opencode-session",
]);

/** How many trailing bytes of the upstream body stay in the scan window. A sensitive value split
 * across two TCP writes is whole in the next window and is caught there; only a value longer than
 * this could straddle undetected, and no provider credential, operator header value, endpoint, or
 * broker token comes close. */
const RESPONSE_SCAN_OVERLAP_BYTES = 4_096;

/** A fixed, bounded, value-free refusal body. It never carries a credential, a token, an
 * upstream endpoint, or a filesystem path, so a compromised child learns exactly one bit —
 * that the broker refused. */
const FAIL_CLOSED_BODY = '{"error":{"type":"codearbiter_broker_refused",'
  + '"message":"codeArbiter inference broker failed closed."}}';

/** A fixed, value-free refusal. Mirrors `ChildConfigProjectionError`: the runner maps it to one
 * allowlisted degraded stage identifier and it never carries operator material. */
export class InferenceBrokerError extends Error {
  constructor() {
    super("codeArbiter inference broker refused.");
    this.name = "InferenceBrokerError";
  }
}

function refuseBroker(): never {
  throw new InferenceBrokerError();
}

export interface BrokerUpstreamAuthority {
  /** The owning child's handshake nonce. The broker refuses an authority carrying any other
   * nonce, so an upstream credential can only ever be attached to the one child this broker
   * was started for. */
  nonce: string;
  /** The operator's REAL provider endpoint. Never projected into the child. */
  baseUrl: string;
  /** The operator's REAL provider credential. Never projected into the child. */
  credential: string;
  /** Operator-configured provider headers, already resolved from the PARENT environment. These
   * can themselves carry credential material, which is exactly why they are attached here and
   * not projected into the child's configuration. */
  headers?: Readonly<Record<string, string>>;
  /** The parent's own scrub predicate (`prepareChildEnvironment`), which recognises every value
   * the child must never see: the upstream credential, the operator's stored credential, every
   * resolved operator header value, the operator's real endpoint, and this child's token.
   *
   * Required, not optional. The broker forwards a response the child then reads, so without this
   * an upstream that reflects the request credential — a debug/echo mode on an operator-run
   * gateway, a verbose 401 — turns the broker into the one channel that hands the credential
   * back. The PREDICATE is passed rather than the values, so the broker never enumerates the
   * parent's scrub set. */
  containsSensitiveValue: (text: string) => boolean;
}

interface BoundUpstream {
  origin: string;
  basePath: string;
  secure: boolean;
  credential: string;
  headers: Readonly<Record<string, string>>;
  containsSensitiveValue: (text: string) => boolean;
}

/** Streams the upstream body through untouched until it carries operator material, then fails
 * the stream rather than delivering it. Never buffers to completion: a long generation must reach
 * the child frame by frame, so bytes are forwarded as they arrive and only a bounded overlap
 * window is retained for scanning.
 *
 * Residual, stated: because bytes are forwarded eagerly, a value straddling a chunk boundary has
 * its leading fragment already delivered when the following chunk completes the match and the
 * stream is destroyed. The complete value is never delivered. That is the deliberate trade — the
 * alternative is holding back a window of bytes, which deadlocks incremental streaming. */
class SensitiveResponseFilter extends Transform {
  private tail: Buffer = Buffer.alloc(0);

  constructor(private readonly containsSensitiveValue: (text: string) => boolean) {
    super();
  }

  override _transform(chunk: Buffer, _encoding: BufferEncoding, callback: TransformCallback): void {
    const window = this.tail.byteLength === 0 ? chunk : Buffer.concat([this.tail, chunk]);
    // Scanned as utf8 AND latin1: the predicate compares JS strings, and a value's bytes decode
    // back to it under one or the other depending on how the value itself is encoded.
    if (this.containsSensitiveValue(window.toString("utf8")) || this.containsSensitiveValue(window.toString("latin1"))) {
      callback(new InferenceBrokerError());
      return;
    }
    // Copied, never a view: a `subarray` would pin the whole preceding chunk in memory.
    this.tail = window.byteLength <= RESPONSE_SCAN_OVERLAP_BYTES
      ? Buffer.from(window)
      : Buffer.from(window.subarray(window.byteLength - RESPONSE_SCAN_OVERLAP_BYTES));
    callback(null, chunk);
  }
}

/** True when any response header name or value carries operator material. Headers arrive whole,
 * so unlike the body this check is exact. */
function responseHeadersLeak(
  headers: Readonly<Record<string, string | string[]>>,
  containsSensitiveValue: (text: string) => boolean,
): boolean {
  for (const [name, value] of Object.entries(headers)) {
    if (containsSensitiveValue(name)) return true;
    for (const item of Array.isArray(value) ? value : [value]) {
      if (containsSensitiveValue(item)) return true;
    }
  }
  return false;
}

export interface InferenceBroker {
  /** The handshake nonce of the one child this broker serves. */
  readonly nonce: string;
  /** The loopback endpoint projected as the child's provider base URL. */
  readonly baseUrl: string;
  /** The per-child ephemeral token projected into the child's environment. */
  readonly token: string;
  /** Bind the real upstream. Until this is called every request fails closed. */
  authorize(authority: BrokerUpstreamAuthority): void;
  /** Refuse every subsequent request. Called the moment the owning child exits. */
  revoke(): void;
  /** Revoke, stop listening, and destroy every open socket. Idempotent. */
  close(): Promise<void>;
}

export interface InferenceBrokerOptions {
  /** The owning child's handshake nonce (`runner.ts`), 128 bits of hex. */
  nonce: string;
}

function boundedUpstream(baseUrl: string): { origin: string; basePath: string; secure: boolean } {
  if (typeof baseUrl !== "string" || Buffer.byteLength(baseUrl, "utf8") > MAX_UPSTREAM_BASE_BYTES) refuseBroker();
  // Checked on the RAW value too: `https://host/v1?` and `https://host/v1#` parse to an empty
  // search/hash yet still hand a delimiter to the upstream request.
  if (baseUrl.includes("?") || baseUrl.includes("#")) refuseBroker();
  let url: URL;
  try { url = new URL(baseUrl); }
  catch { refuseBroker(); }
  if (!UPSTREAM_PROTOCOLS.has(url.protocol)) refuseBroker();
  if (url.username !== "" || url.password !== "") refuseBroker();
  if (url.search !== "" || url.hash !== "") refuseBroker();
  return {
    origin: url.origin,
    basePath: url.pathname.replace(/\/+$/u, ""),
    secure: url.protocol === "https:",
  };
}

/** Constant-time equality over the token. Length is compared first because `timingSafeEqual`
 * throws on unequal lengths; the token's length is fixed and public, so that leaks nothing. */
function sameToken(candidate: string, token: string): boolean {
  const left = Buffer.from(candidate, "utf8");
  const right = Buffer.from(token, "utf8");
  return left.byteLength === right.byteLength && timingSafeEqual(left, right);
}

/** The child's Pi builds the provider's own auth header shape around whatever `apiKey` it was
 * given, so the broker deliberately does NOT hard-code a scheme. It accepts the token as either
 * a whole header value (`x-api-key: <token>`) or the argument of a single-word auth scheme
 * (`Authorization: Bearer <token>`), and substitutes the real credential in place. Anything
 * else is left untouched and does not authenticate the request. */
function substituteToken(value: string, token: string, credential: string): string | undefined {
  if (sameToken(value, token)) return credential;
  const separator = value.indexOf(" ");
  if (separator <= 0) return undefined;
  const scheme = value.slice(0, separator);
  const argument = value.slice(separator + 1);
  if (scheme.includes(" ") || !sameToken(argument, token)) return undefined;
  return `${scheme} ${credential}`;
}

function forwardedHeaders(
  raw: IncomingHttpHeaders,
  upstream: BoundUpstream,
  token: string,
): Record<string, string | string[]> | undefined {
  let authenticated = false;
  const headers: Record<string, string | string[]> = Object.create(null) as Record<string, string | string[]>;
  for (const [name, value] of Object.entries(raw)) {
    const lower = name.toLowerCase();
    if (value === undefined || !FORWARDED_REQUEST_HEADERS.has(lower)) continue;
    if (typeof value === "string") {
      const substituted = substituteToken(value, token, upstream.credential);
      if (substituted === undefined) headers[lower] = value;
      else {
        headers[lower] = substituted;
        authenticated = true;
      }
      continue;
    }
    // A repeated header can never carry the token: Pi sends auth exactly once, and accepting a
    // token from an array position would widen the authentication surface for no gain.
    headers[lower] = value;
  }
  if (!authenticated) return undefined;
  headers.host = new URL(upstream.origin).host;
  // A compressed body would carry an echoed operator secret straight past the response filter, so
  // the broker negotiates plaintext regardless of what the child asked for.
  headers["accept-encoding"] = "identity";
  // Operator headers are applied LAST, and case-insensitively, so a child cannot displace one by
  // sending its own copy — nor smuggle a second value alongside it under a different spelling.
  for (const [name, value] of Object.entries(upstream.headers)) {
    delete headers[name.toLowerCase()];
    headers[name] = value;
  }
  return headers;
}

function upstreamTarget(requestUrl: string | undefined, upstream: BoundUpstream): URL | undefined {
  if (typeof requestUrl !== "string" || Buffer.byteLength(requestUrl, "utf8") > MAX_REQUEST_TARGET_BYTES) return undefined;
  let parsed: URL;
  try { parsed = new URL(requestUrl, "http://127.0.0.1"); }
  catch { return undefined; }
  // `new URL` resolves `..` segments and normalises percent-encoded DOTS, so `..`, `%2e%2e`,
  // `%2E%2E` and `.%2e` all collapse before the prefix test and simply fail it. It does NOT
  // decode an encoded SEPARATOR: `%2f`/`%5c` survives normalisation, passes the prefix test, and
  // reaches the upstream with its encoding intact, leaving the escape to the upstream's own
  // decode-then-route order. No provider route needs an encoded separator, so refusing them
  // outright is what makes the prefix test's guarantee true as stated rather than nearly true.
  if (/%2f|%5c/iu.test(parsed.pathname)) return undefined;
  if (parsed.pathname !== BROKER_ROUTE_PREFIX && !parsed.pathname.startsWith(`${BROKER_ROUTE_PREFIX}/`)) return undefined;
  const suffix = parsed.pathname.slice(BROKER_ROUTE_PREFIX.length);
  try { return new URL(`${upstream.origin}${upstream.basePath}${suffix}${parsed.search}`); }
  catch { return undefined; }
}

function failClosed(response: ServerResponse, status: number): void {
  if (response.headersSent || response.writableEnded) {
    response.destroy();
    return;
  }
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": String(Buffer.byteLength(FAIL_CLOSED_BODY, "utf8")),
    "Cache-Control": "no-store",
  });
  response.end(FAIL_CLOSED_BODY);
}

export async function startInferenceBroker(options: InferenceBrokerOptions): Promise<InferenceBroker> {
  if (typeof options?.nonce !== "string" || !/^[0-9a-f]{32}$/u.test(options.nonce)) refuseBroker();
  const ownerNonce = options.nonce;
  // 256 bits of CSPRNG material, minted once, for exactly one child. Two children never share a
  // token even when they somehow share a nonce, and nothing the child holds predicts it.
  const token = randomBytes(32).toString("hex");

  let upstream: BoundUpstream | undefined;
  let revoked = false;
  let closed: Promise<void> | undefined;
  const sockets = new Set<Socket>();

  const handle = (request: IncomingMessage, response: ServerResponse): void => {
    const bound = upstream;
    if (revoked || bound === undefined) {
      request.resume();
      failClosed(response, 503);
      return;
    }
    const target = upstreamTarget(request.url, bound);
    if (target === undefined) {
      request.resume();
      failClosed(response, 404);
      return;
    }
    const headers = forwardedHeaders(request.headers, bound, token);
    if (headers === undefined) {
      request.resume();
      failClosed(response, 401);
      return;
    }
    request.socket.setNoDelay(true);
    const send = bound.secure ? httpsRequest : httpRequest;
    // `agent: false` keeps the broker's own upstream sockets out of Node's keep-alive pool, so
    // closing the broker genuinely tears down every connection it opened.
    const forward = send(target, { method: request.method ?? "POST", headers, agent: false }, (upstreamResponse) => {
      if (response.writableEnded || response.destroyed) {
        upstreamResponse.destroy();
        return;
      }
      const responseHeaders: Record<string, string | string[]> = Object.create(null) as Record<string, string | string[]>;
      for (const [name, value] of Object.entries(upstreamResponse.headers)) {
        if (value === undefined || HOP_BY_HOP_HEADERS.has(name.toLowerCase())) continue;
        responseHeaders[name] = value;
      }
      // The response path is the one remaining route by which the operator's credential could
      // reach the child, so the parent's own scrub predicate is applied to it. An upstream that
      // reflects the request credential in a header hands it over outright; fail closed.
      if (responseHeadersLeak(responseHeaders, bound.containsSensitiveValue)) {
        upstreamResponse.destroy();
        failClosed(response, 502);
        return;
      }
      // The request negotiated `identity`, so an encoded body means an upstream that ignored it —
      // and an encoded body is one the filter below cannot read. Refuse rather than relay blind.
      const contentEncoding = responseHeaders["content-encoding"];
      if (contentEncoding !== undefined && String(contentEncoding).toLowerCase() !== "identity") {
        upstreamResponse.destroy();
        failClosed(response, 502);
        return;
      }
      // One request, one connection, and the UPSTREAM's own body framing.
      //
      // Both halves of that matter. A kept-alive socket to a per-child broker is a live handle
      // in the CHILD's event loop, so nothing may outlive the exchange that needed it. And when
      // the upstream declares no length, re-framing its stream as `Transfer-Encoding: chunked`
      // splits "body ended" from "connection closed" into two events the child observes at
      // different times — which on Windows lands the FIN inside Pi's own shutdown and aborts the
      // child in libuv (`uv_async_send` on a closing handle) AFTER a fully successful run.
      // Clearing `useChunkedEncodingByDefault` restores close-delimited framing, so body end and
      // socket close are the same event, exactly as the provider sent them.
      responseHeaders.connection = "close";
      if (responseHeaders["content-length"] === undefined) response.useChunkedEncodingByDefault = false;
      // Filtered, not merely relayed. The filter forwards every clean byte the moment it arrives
      // and fails the exchange the moment operator material appears.
      const filter = new SensitiveResponseFilter(bound.containsSensitiveValue);
      // Headers are held until the FIRST byte clears the filter, and no longer. That is what lets
      // the common reflection case — a verbose provider error that echoes the credential, which
      // arrives whole in the first chunk — refuse with the ordinary fixed 502 body instead of a
      // torn connection. It costs nothing in streaming terms: the headers go out with the first
      // frame rather than before it.
      let headersSent = false;
      const sendHeaders = (): void => {
        if (headersSent || response.headersSent || response.writableEnded || response.destroyed) return;
        headersSent = true;
        response.writeHead(upstreamResponse.statusCode ?? 502, responseHeaders);
        // Never buffer to completion: a long streamed generation must reach the child frame by
        // frame or it breaks outright.
        response.flushHeaders();
      };
      const abort = (): void => {
        upstreamResponse.destroy();
        filter.destroy();
        // Nothing has been committed yet, so the child gets a clean, fixed, value-free refusal.
        if (!headersSent) {
          failClosed(response, 502);
          return;
        }
        // Past that point the status line is already spent, so the exchange is RESET rather than
        // closed. The broker mirrors the upstream's framing, and on a close-delimited response a
        // FIN is byte-for-byte indistinguishable from a complete body — the child would read a
        // suppressed answer as a whole one.
        const socket = response.socket;
        if (socket !== null && !socket.destroyed) socket.resetAndDestroy();
        response.destroy();
      };
      upstreamResponse.on("error", abort);
      filter.on("error", abort);
      filter.on("data", (chunk: Buffer) => {
        sendHeaders();
        if (!response.write(chunk)) filter.pause();
      });
      response.on("drain", () => filter.resume());
      filter.on("end", () => {
        sendHeaders();
        response.end();
      });
      upstreamResponse.pipe(filter);
    });
    forward.setNoDelay(true);
    forward.on("error", () => failClosed(response, 502));
    response.on("close", () => { if (!response.writableEnded) forward.destroy(); });
    request.on("error", () => forward.destroy());
    request.pipe(forward);
  };

  const server: Server = createServer(handle);
  server.on("connection", (socket: Socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    // Loopback ONLY and port 0 so the OS assigns. Never a wildcard bind, never a fixed port.
    server.listen({ host: "127.0.0.1", port: 0, exclusive: true }, () => {
      server.removeListener("error", reject);
      resolve();
    });
  }).catch(() => refuseBroker());

  const address = server.address();
  if (address === null || typeof address === "string") {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    refuseBroker();
  }
  const baseUrl = `http://127.0.0.1:${(address as AddressInfo).port}${BROKER_ROUTE_PREFIX}`;

  return Object.freeze({
    nonce: ownerNonce,
    baseUrl,
    token,
    authorize(authority: BrokerUpstreamAuthority): void {
      if (revoked) refuseBroker();
      if (typeof authority?.nonce !== "string" || !sameToken(authority.nonce, ownerNonce)) refuseBroker();
      if (typeof authority?.credential !== "string" || authority.credential === "") refuseBroker();
      // No predicate, no forwarding: without it the broker cannot tell whether a response is
      // handing the operator's own material back to the child, and must not guess.
      if (typeof authority?.containsSensitiveValue !== "function") refuseBroker();
      const endpoint = boundedUpstream(authority.baseUrl);
      upstream = Object.freeze({
        ...endpoint,
        credential: authority.credential,
        headers: Object.freeze({ ...authority.headers }),
        containsSensitiveValue: authority.containsSensitiveValue,
      });
    },
    revoke(): void {
      revoked = true;
      upstream = undefined;
    },
    async close(): Promise<void> {
      revoked = true;
      upstream = undefined;
      closed ??= new Promise<void>((resolve) => {
        server.close(() => resolve());
        for (const socket of sockets) socket.destroy();
        sockets.clear();
      });
      await closed;
    },
  });
}
