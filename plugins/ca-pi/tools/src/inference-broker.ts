/** inference-broker.ts - codeArbiter's per-child loopback inference broker (#455).
 *
 * The isolated Pi child no longer receives the operator's provider credential in ANY form. It
 * receives a per-child ephemeral token and a `models.json` whose `baseUrl` names this broker's
 * loopback listener. The child's Pi makes ordinary provider calls to loopback; this module
 * authenticates the token, swaps in the real credential, forwards upstream, and streams the
 * response back incrementally.
 *
 * Residual, stated rather than assumed away: a listening loopback socket is reachable by ANY
 * process running as the same OS user. The token is what contains that residual — it is minted
 * per child from 256 bits of CSPRNG material, bound to exactly one child's handshake nonce,
 * accepted only by the one broker that minted it, and refused the moment its child exits. A
 * captured token is therefore worthless to a second process and worthless off-host.
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

/** The child's `models.json` names this variable, never a literal token, so the projected
 * configuration file itself carries no secret material at all. */
export const BROKER_TOKEN_ENV_NAME = "CODEARBITER_PI_BROKER_TOKEN";

/** The fixed route prefix the child's projected `baseUrl` carries. Everything the child appends
 * after it is remapped onto the operator's real upstream base path. */
const BROKER_ROUTE_PREFIX = "/v1";

const MAX_REQUEST_TARGET_BYTES = 2_048;
const MAX_UPSTREAM_BASE_BYTES = 512;
const UPSTREAM_PROTOCOLS = new Set(["http:", "https:"]);

/** Hop-by-hop headers are connection-scoped by RFC 9110 and must not be forwarded; `host` is
 * rewritten to the upstream authority rather than forwarded, because the child's value names
 * this loopback listener. */
const HOP_BY_HOP_HEADERS = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade", "host",
]);

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
   * not projected into the child's `models.json`. */
  headers?: Readonly<Record<string, string>>;
}

interface BoundUpstream {
  origin: string;
  basePath: string;
  secure: boolean;
  credential: string;
  headers: Readonly<Record<string, string>>;
}

export interface InferenceBroker {
  /** The handshake nonce of the one child this broker serves. */
  readonly nonce: string;
  /** The loopback endpoint projected into the child's `models.json`. */
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
    if (value === undefined || HOP_BY_HOP_HEADERS.has(name.toLowerCase())) continue;
    if (typeof value === "string") {
      const substituted = substituteToken(value, token, upstream.credential);
      if (substituted === undefined) headers[name] = value;
      else {
        headers[name] = substituted;
        authenticated = true;
      }
      continue;
    }
    // A repeated header can never carry the token: Pi sends auth exactly once, and accepting a
    // token from an array position would widen the authentication surface for no gain.
    headers[name] = value;
  }
  if (!authenticated) return undefined;
  headers.host = new URL(upstream.origin).host;
  // Operator headers are applied LAST so a child cannot displace them by sending its own copy.
  for (const [name, value] of Object.entries(upstream.headers)) headers[name] = value;
  return headers;
}

function upstreamTarget(requestUrl: string | undefined, upstream: BoundUpstream): URL | undefined {
  if (typeof requestUrl !== "string" || Buffer.byteLength(requestUrl, "utf8") > MAX_REQUEST_TARGET_BYTES) return undefined;
  let parsed: URL;
  try { parsed = new URL(requestUrl, "http://127.0.0.1"); }
  catch { return undefined; }
  // `new URL` has already resolved `..` segments, so a traversal attempt simply fails the
  // prefix test rather than escaping the upstream base path.
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
    const forward = send(target, { method: request.method ?? "POST", headers }, (upstreamResponse) => {
      if (response.writableEnded || response.destroyed) {
        upstreamResponse.destroy();
        return;
      }
      const responseHeaders: Record<string, string | string[]> = Object.create(null) as Record<string, string | string[]>;
      for (const [name, value] of Object.entries(upstreamResponse.headers)) {
        if (value === undefined || HOP_BY_HOP_HEADERS.has(name.toLowerCase())) continue;
        responseHeaders[name] = value;
      }
      response.writeHead(upstreamResponse.statusCode ?? 502, responseHeaders);
      // Header flush + pipe, never buffer-to-completion: a long streamed generation must reach
      // the child frame by frame or it breaks outright.
      response.flushHeaders();
      upstreamResponse.on("error", () => response.destroy());
      upstreamResponse.pipe(response);
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
    // Loopback ONLY and port 0 so the OS assigns. Never `0.0.0.0`, never a fixed port.
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
      const endpoint = boundedUpstream(authority.baseUrl);
      upstream = Object.freeze({
        ...endpoint,
        credential: authority.credential,
        headers: Object.freeze({ ...authority.headers }),
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
