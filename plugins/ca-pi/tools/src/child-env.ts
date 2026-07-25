/** child-env.ts - codeArbiter's explicit minimal Pi child environment. */
import { mkdir, mkdtemp, open, rm } from "node:fs/promises";
import type { RmOptions } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join } from "node:path";

export interface ChildEnvInput {
  platform: NodeJS.Platform;
  parent: Readonly<NodeJS.ProcessEnv>;
  provider: string;
  isolationRoot: string;
}

const WINDOWS_BASELINE = [
  "SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT", "TEMP", "TMP",
] as const;

const POSIX_BASELINE = [
  "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL",
] as const;

const MAX_AUTH_FILE_BYTES = 1_048_576;
const MAX_MODELS_FILE_BYTES = 1_048_576;
const MAX_PROJECTED_ENTRIES = 256;
const MAX_PROJECTED_HEADERS = 32;
const MAX_PROJECTED_KEYS = 64;
const MAX_PROJECTED_STRING_BYTES = 8_192;
const MAX_PROJECTED_DEPTH = 8;
const MAX_PROJECTED_NODES = 4_096;

/** ADR-0017 — credential-blind selected-provider CONFIGURATION projection.
 *
 * Pi binds `models.json` to `getAgentDir()` with no separate environment override
 * (`dist/config.js:425`, `dist/core/model-runtime.js:58`), so ADR-0016's private agent dir
 * leaves the child with no operator endpoint, protocol, or model definitions at all and Pi
 * silently resolves the provider from its BUILT-IN catalog — sending the operator's key to an
 * endpoint they never configured. ADR-0017 amends exactly one clause of ADR-0016 to permit
 * projecting configuration; it does NOT widen credential projection, which stays bounded by
 * ADR-0016's auth.json contract alone. */

/** Pi resolves a config value as a `!command` shell execution, a `$VAR` template, or a bare
 * literal (`dist/core/resolve-config-value.js`). Only a WHOLE-value pure environment reference
 * crosses: it names a variable the child's own allowlisted environment already carries, so it
 * transports no operator credential. A partial template (`sk-x$VAR`), Pi's escaped-literal
 * form (`$$VAR`), a bare literal, and every `!command` are refused. */
const PURE_ENV_REFERENCE = /^\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)$/u;
const PROJECTED_HEADER_NAME = /^[A-Za-z0-9_-]{1,128}$/u;
const RESERVED_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);

/** A projected endpoint is accepted POSITIVELY, never by blocklisting the parameter names that
 * carry credentials (`api-key`, `key`, `token`, `sig`, … is an unbounded list). An endpoint is
 * an `http`/`https` scheme, a host, an optional port, and a short bounded route — nothing
 * else. Query and fragment are refused outright because a provider endpoint needs neither: Pi's
 * own Azure provider carries `api-version` in `AZURE_OPENAI_API_VERSION`, not in `baseUrl`. */
const ENDPOINT_PROTOCOLS = new Set(["http:", "https:"]);
// Case-INSENSITIVE by maintainer decision (2026-07-25). A lowercase-only route looked like a
// credential control but was not one: `sk-querysecret999` passes it while `GPT4-Prod` — an
// ordinary Azure deployment name — does not. A short path segment simply cannot be told apart
// from a legitimate route, so the real controls here are the ones that do not depend on
// guessing intent: no userinfo, no query, no fragment, no percent-encoding, a bounded segment
// length (which refuses realistic key material — provider keys run well past 32 bytes), and a
// bounded segment count.
const ENDPOINT_PATH_SEGMENT = /^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$/u;
const MAX_ENDPOINT_BYTES = 512;
const MAX_ENDPOINT_PATH_SEGMENTS = 8;
const MAX_ENDPOINT_PATH_SEGMENT_BYTES = 32;

/** Pi 0.80.10's models.json provider schema (`dist/core/model-config.js`). Pinned deliberately:
 * a key outside this reviewed set cannot be shown non-secret, so it fails the launch closed
 * rather than riding along. Widening it is a reviewed change, not an edit of convenience. */
const PROJECTED_PROVIDER_KEYS: readonly string[] = [
  "name", "baseUrl", "apiKey", "api", "oauth", "headers", "compat", "authHeader", "models", "modelOverrides",
];
const PROJECTED_MODEL_KEYS: readonly string[] = [
  "id", "name", "api", "baseUrl", "reasoning", "thinkingLevelMap", "input", "cost",
  "contextWindow", "maxTokens", "headers", "compat",
];
const PROJECTED_MODEL_OVERRIDE_KEYS: readonly string[] = [
  "name", "reasoning", "thinkingLevelMap", "input", "cost", "contextWindow", "maxTokens", "headers", "compat",
];

/** Key NAMES alone are not a pin. Pi types every one of these VALUES too — `oauth` is
 * `Type.Literal("radius")`, `authHeader` is `Type.Boolean()` — and a record that satisfies the
 * name allowlist but not the value type used to project successfully and then die mutely inside
 * Pi's own `validateModelsConfig`. The projection is the fail-closed boundary, so it pins the
 * value shapes here. Where Pi's `Type.Object` tolerates unknown members (its compat union does),
 * this table is deliberately STRICTER: an unreviewed member refuses instead of riding along. */
type ShapeCheck = (value: unknown) => boolean;

const isBoolean: ShapeCheck = (value) => typeof value === "boolean";
const isFiniteNumber: ShapeCheck = (value) => typeof value === "number" && Number.isFinite(value);
const isNonEmptyText: ShapeCheck = (value) => typeof value === "string" && value !== "" && structuralOnly(value);
const isLiteral = (...allowed: readonly string[]): ShapeCheck =>
  (value) => typeof value === "string" && allowed.includes(value);

function shapedRecord(members: Readonly<Record<string, ShapeCheck>>, maxEntries = MAX_PROJECTED_KEYS): ShapeCheck {
  return (value) => {
    if (!plainRecord(value)) return false;
    const keys = Object.keys(value);
    return keys.length <= maxEntries && keys.every((key) =>
      !RESERVED_OBJECT_KEYS.has(key)
      && Object.prototype.hasOwnProperty.call(members, key)
      && members[key]!(value[key]));
  };
}

function shapedArray(item: ShapeCheck, maxEntries = MAX_PROJECTED_ENTRIES): ShapeCheck {
  return (value) => Array.isArray(value) && value.length <= maxEntries && value.every(item);
}

const isThinkingLevel: ShapeCheck = (value) => value === null || isNonEmptyText(value);
const isThinkingLevelMap = shapedRecord({
  off: isThinkingLevel, minimal: isThinkingLevel, low: isThinkingLevel, medium: isThinkingLevel,
  high: isThinkingLevel, xhigh: isThinkingLevel, max: isThinkingLevel,
});
const isModelInput = shapedArray(isLiteral("text", "image"), 8);
const COST_RATES = { input: isFiniteNumber, output: isFiniteNumber, cacheRead: isFiniteNumber, cacheWrite: isFiniteNumber };
const isCostTier = shapedRecord({ inputTokensAbove: isFiniteNumber, ...COST_RATES });
const isModelCost = shapedRecord({ ...COST_RATES, tiers: shapedArray(isCostTier, 32) });
/** Pi's `compat` is a union of three `Type.Object`s that each tolerate unknown members; this is
 * their exact declared union, and it is deliberately STRICTER than Pi (an unreviewed member
 * refuses). Three members are composite objects whose interiors Pi itself leaves open-ended
 * (`Type.Record(Type.String(), …)`, a free-string `sort`, a number-or-string `max_price`), so
 * the member NAME is pinned and its interior keeps the bounded structural check — depth, node,
 * key, and byte caps, reserved keys rejected, and every Pi `!command` form refused. */
const isBoundedStructure: ShapeCheck = (value) => plainRecord(value) && structuralOnly(value);
const isProviderCompat = shapedRecord({
  supportsStore: isBoolean,
  supportsDeveloperRole: isBoolean,
  supportsReasoningEffort: isBoolean,
  supportsUsageInStreaming: isBoolean,
  maxTokensField: isLiteral("max_completion_tokens", "max_tokens"),
  requiresToolResultName: isBoolean,
  requiresAssistantAfterToolResult: isBoolean,
  requiresThinkingAsText: isBoolean,
  requiresReasoningContentOnAssistantMessages: isBoolean,
  thinkingFormat: isLiteral(
    "openai", "openrouter", "together", "deepseek", "zai", "qwen",
    "chat-template", "qwen-chat-template", "string-thinking", "ant-ling",
  ),
  chatTemplateKwargs: isBoundedStructure,
  cacheControlFormat: isLiteral("anthropic"),
  openRouterRouting: isBoundedStructure,
  vercelGatewayRouting: isBoundedStructure,
  supportsStrictMode: isBoolean,
  sendSessionAffinityHeaders: isBoolean,
  deferredToolsMode: isLiteral("kimi"),
  sessionAffinityFormat: isLiteral("openai", "openai-nosession", "openrouter"),
  supportsLongCacheRetention: isBoolean,
  supportsToolSearch: isBoolean,
  supportsEagerToolInputStreaming: isBoolean,
  supportsCacheControlOnTools: isBoolean,
  forceAdaptiveThinking: isBoolean,
  supportsToolReferences: isBoolean,
});

/** Value shapes for every key NOT handled by a dedicated projector (`baseUrl`, `apiKey`,
 * `headers`, `models`, `modelOverrides` each have one). */
const PROJECTED_PROVIDER_SHAPES: Readonly<Record<string, ShapeCheck>> = {
  name: isNonEmptyText, api: isNonEmptyText, oauth: isLiteral("radius"),
  compat: isProviderCompat, authHeader: isBoolean,
};
const PROJECTED_MODEL_SHAPES: Readonly<Record<string, ShapeCheck>> = {
  id: isNonEmptyText, name: isNonEmptyText, api: isNonEmptyText, reasoning: isBoolean,
  thinkingLevelMap: isThinkingLevelMap, input: isModelInput, cost: isModelCost,
  contextWindow: isFiniteNumber, maxTokens: isFiniteNumber, compat: isProviderCompat,
};
const PROJECTED_MODEL_OVERRIDE_SHAPES: Readonly<Record<string, ShapeCheck>> = {
  name: isNonEmptyText, reasoning: isBoolean, thinkingLevelMap: isThinkingLevelMap,
  input: isModelInput, cost: isModelCost, contextWindow: isFiniteNumber, maxTokens: isFiniteNumber,
  compat: isProviderCompat,
};

/** A fixed, value-free refusal. It never carries a configuration value, credential material,
 * or a filesystem path, so it cannot reveal operator layout; the runner maps it to one
 * allowlisted degraded identifier. */
export class ChildConfigProjectionError extends Error {
  constructor() {
    super("Pi child configuration projection refused.");
    this.name = "ChildConfigProjectionError";
  }
}

function refuseProjection(): never {
  throw new ChildConfigProjectionError();
}

function plainRecord(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value) as unknown;
  return prototype === Object.prototype || prototype === null;
}

/** Bounded, non-executable, non-credential-bearing config. Any `!` prefix is Pi's shell-command
 * form, which ADR-0016 reserves to the user, so it is refused in EVERY position rather than
 * only under apiKey/headers. */
function structuralOnly(value: unknown, depth = 0, budget = { nodes: 0 }): boolean {
  budget.nodes += 1;
  if (budget.nodes > MAX_PROJECTED_NODES || depth > MAX_PROJECTED_DEPTH) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") {
    return !value.startsWith("!") && Buffer.byteLength(value, "utf8") <= MAX_PROJECTED_STRING_BYTES;
  }
  if (Array.isArray(value)) {
    return value.length <= MAX_PROJECTED_ENTRIES && value.every((item) => structuralOnly(item, depth + 1, budget));
  }
  if (!plainRecord(value)) return false;
  const keys = Object.keys(value);
  return keys.length <= MAX_PROJECTED_KEYS
    && keys.every((key) => !RESERVED_OBJECT_KEYS.has(key)
      && Buffer.byteLength(key, "utf8") <= MAX_PROJECTED_STRING_BYTES
      && structuralOnly(value[key], depth + 1, budget));
}

/** A `baseUrl` is otherwise structural, but every part of a URL can carry credential material,
 * not just its userinfo: `?api-key=` (Azure), `?key=` (Google), `#sk-…`, and `/keys/sk-…` are
 * all endpoint-shaped secrets, and the query-parameter names that carry keys are an unbounded
 * list. Acceptance is therefore POSITIVE — a value crosses only when it is provably nothing but
 * an endpoint:
 *   - a parseable absolute URL (a value that is not one is refused, never guessed at, since Pi
 *     hands it straight to `fetch`);
 *   - an `http`/`https` scheme;
 *   - no userinfo (`https://operator:pw@gateway/v1` is credential material wearing an endpoint's
 *     clothes);
 *   - no query and no fragment at all — a provider endpoint needs neither, and Pi's own Azure
 *     provider takes `api-version` from `AZURE_OPENAI_API_VERSION`;
 *   - a bounded route whose segments are short, lowercase, unencoded identifiers (`/v1`,
 *     `/openai/deployments/gpt-4o`, `/api/paas/v4`) — deliberately narrower than what Pi accepts,
 *     so an unusual path fails the launch CLOSED rather than projecting material we cannot show
 *     to be credential-free.
 *
 * Residual, stated rather than assumed away: a route can be short and lowercase and still be
 * secret-bearing. That is why the accepted value is ALSO registered in the child's sensitive-value
 * set and retained behind a scrub handle (see `prepareChildEnvironment`) — the two controls that
 * previously assumed the projection held no secret are no longer blind to it. */
function endpointOnlyValue(value: unknown, endpoints: Set<string>): string {
  if (typeof value !== "string" || !structuralOnly(value)) refuseProjection();
  if (Buffer.byteLength(value, "utf8") > MAX_ENDPOINT_BYTES) refuseProjection();
  // Checked on the RAW value as well as the parsed URL: `https://host/v1?` and `https://host/v1#`
  // parse to an empty search/hash yet still hand a delimiter to Pi's `fetch`.
  if (value.includes("?") || value.includes("#")) refuseProjection();
  const endpoint = parsedEndpoint(value);
  if (!ENDPOINT_PROTOCOLS.has(endpoint.protocol)) refuseProjection();
  if (endpoint.username !== "" || endpoint.password !== "") refuseProjection();
  if (endpoint.search !== "" || endpoint.hash !== "") refuseProjection();
  const segments = endpoint.pathname.split("/").filter((segment) => segment !== "");
  if (segments.length > MAX_ENDPOINT_PATH_SEGMENTS) refuseProjection();
  for (const segment of segments) {
    if (Buffer.byteLength(segment, "utf8") > MAX_ENDPOINT_PATH_SEGMENT_BYTES) refuseProjection();
    if (!ENDPOINT_PATH_SEGMENT.test(segment)) refuseProjection();
  }
  endpoints.add(value);
  return value;
}

function parsedEndpoint(value: string): URL {
  try { return new URL(value); }
  catch { refuseProjection(); }
}

function templateOnlyValue(value: unknown): string {
  if (typeof value !== "string" || !PURE_ENV_REFERENCE.test(value)) refuseProjection();
  return value;
}

function sanitizedHeaderMap(value: unknown): Record<string, string> {
  if (!plainRecord(value)) refuseProjection();
  const entries = Object.entries(value);
  if (entries.length > MAX_PROJECTED_HEADERS) refuseProjection();
  const headers = Object.create(null) as Record<string, string>;
  for (const [name, raw] of entries) {
    // The reserved-key rule applies HERE too. `PROJECTED_HEADER_NAME` admits `__proto__`,
    // `constructor`, and `prototype`, and this was the module's only place that skipped the
    // guard every other projected record applies.
    if (RESERVED_OBJECT_KEYS.has(name) || !PROJECTED_HEADER_NAME.test(name)) refuseProjection();
    headers[name] = templateOnlyValue(raw);
  }
  return headers;
}

function projectedModelRecord(
  value: unknown,
  allowed: readonly string[],
  shapes: Readonly<Record<string, ShapeCheck>>,
  endpoints: Set<string>,
): Record<string, unknown> {
  if (!plainRecord(value)) refuseProjection();
  const record = Object.create(null) as Record<string, unknown>;
  for (const [key, raw] of Object.entries(value)) {
    if (!allowed.includes(key)) refuseProjection();
    if (key === "headers") { record[key] = sanitizedHeaderMap(raw); continue; }
    if (key === "baseUrl") { record[key] = endpointOnlyValue(raw, endpoints); continue; }
    if (!Object.prototype.hasOwnProperty.call(shapes, key) || !shapes[key]!(raw)) refuseProjection();
    record[key] = raw;
  }
  return record;
}

function projectedProviderRecord(value: unknown, endpoints: Set<string>): Record<string, unknown> {
  if (!plainRecord(value)) refuseProjection();
  const record = Object.create(null) as Record<string, unknown>;
  for (const [key, raw] of Object.entries(value)) {
    if (!PROJECTED_PROVIDER_KEYS.includes(key)) refuseProjection();
    if (key === "apiKey") { record[key] = templateOnlyValue(raw); continue; }
    if (key === "headers") { record[key] = sanitizedHeaderMap(raw); continue; }
    if (key === "baseUrl") { record[key] = endpointOnlyValue(raw, endpoints); continue; }
    if (key === "models") {
      if (!Array.isArray(raw) || raw.length > MAX_PROJECTED_ENTRIES) refuseProjection();
      record[key] = raw.map((entry) => projectedModelRecord(entry, PROJECTED_MODEL_KEYS, PROJECTED_MODEL_SHAPES, endpoints));
      continue;
    }
    if (key === "modelOverrides") {
      if (!plainRecord(raw)) refuseProjection();
      const entries = Object.entries(raw);
      if (entries.length > MAX_PROJECTED_ENTRIES) refuseProjection();
      const overrides = Object.create(null) as Record<string, unknown>;
      for (const [id, entry] of entries) {
        if (id === "" || RESERVED_OBJECT_KEYS.has(id) || Buffer.byteLength(id, "utf8") > MAX_PROJECTED_STRING_BYTES) refuseProjection();
        overrides[id] = projectedModelRecord(entry, PROJECTED_MODEL_OVERRIDE_KEYS, PROJECTED_MODEL_OVERRIDE_SHAPES, endpoints);
      }
      record[key] = overrides;
      continue;
    }
    if (!Object.prototype.hasOwnProperty.call(PROJECTED_PROVIDER_SHAPES, key) || !PROJECTED_PROVIDER_SHAPES[key]!(raw)) refuseProjection();
    record[key] = raw;
  }
  return record;
}

export const PI_PROVIDER_ENV: Readonly<Record<string, readonly string[]>> = Object.freeze({
  "amazon-bedrock": ["AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION"],
  "ant-ling": ["ANT_LING_API_KEY"],
  anthropic: ["ANTHROPIC_OAUTH_TOKEN", "ANTHROPIC_API_KEY"],
  "azure-openai-responses": ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL", "AZURE_OPENAI_RESOURCE_NAME", "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_DEPLOYMENT_NAME_MAP"],
  cerebras: ["CEREBRAS_API_KEY"],
  "cloudflare-ai-gateway": ["CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_GATEWAY_ID"],
  "cloudflare-workers-ai": ["CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"],
  deepseek: ["DEEPSEEK_API_KEY"],
  fireworks: ["FIREWORKS_API_KEY"],
  "github-copilot": [],
  google: ["GEMINI_API_KEY"],
  "google-vertex": [],
  groq: ["GROQ_API_KEY"],
  huggingface: [],
  "kimi-coding": ["KIMI_API_KEY"],
  minimax: ["MINIMAX_API_KEY"],
  "minimax-cn": ["MINIMAX_API_KEY"],
  mistral: ["MISTRAL_API_KEY"],
  moonshotai: ["MOONSHOT_API_KEY"],
  "moonshotai-cn": ["MOONSHOT_API_KEY"],
  nvidia: ["NVIDIA_API_KEY"],
  openai: ["OPENAI_API_KEY"],
  "openai-codex": [],
  opencode: ["OPENCODE_API_KEY"],
  "opencode-go": ["OPENCODE_API_KEY"],
  openrouter: ["OPENROUTER_API_KEY"],
  together: ["TOGETHER_API_KEY"],
  "vercel-ai-gateway": ["AI_GATEWAY_API_KEY"],
  xai: ["XAI_API_KEY"],
  xiaomi: ["XIAOMI_API_KEY"],
  "xiaomi-token-plan-ams": ["XIAOMI_TOKEN_PLAN_AMS_API_KEY"],
  "xiaomi-token-plan-cn": ["XIAOMI_TOKEN_PLAN_CN_API_KEY"],
  "xiaomi-token-plan-sgp": ["XIAOMI_TOKEN_PLAN_SGP_API_KEY"],
  zai: ["ZAI_API_KEY"],
  "zai-coding-cn": ["ZAI_CODING_CN_API_KEY"],
});

const REVIEWED_HELP_FLAGS = [
  "--provider", "--model", "--mode", "--no-session", "--tools", "--extension",
  "--no-extensions", "--skill", "--no-skills", "--no-prompt-templates", "--no-themes",
  "--no-context-files", "--no-approve", "--offline", "--append-system-prompt",
] as const;

const REVIEWED_PI_ENV = [
  "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR", "PI_PACKAGE_DIR",
  "PI_OFFLINE", "PI_TELEMETRY", "PI_SHARE_VIEWER_URL",
] as const;

function copyDefined(
  target: NodeJS.ProcessEnv,
  source: Readonly<NodeJS.ProcessEnv>,
  names: readonly string[],
): void {
  for (const name of names) {
    const value = source[name];
    if (typeof value === "string" && value.length > 0) target[name] = value;
  }
}

export function buildChildEnv(input: ChildEnvInput): NodeJS.ProcessEnv {
  const providerNames = PI_PROVIDER_ENV[input.provider];
  if (providerNames === undefined) throw new Error("Unsupported Pi provider for isolated child launch.");
  const baseline = input.platform === "win32"
    ? WINDOWS_BASELINE
    : input.platform === "linux" || input.platform === "darwin"
      ? POSIX_BASELINE
      : undefined;
  if (baseline === undefined) throw new Error("Unsupported child platform for isolated Pi launch.");

  const child: NodeJS.ProcessEnv = {};
  copyDefined(child, input.parent, baseline);
  copyDefined(child, input.parent, providerNames);
  const home = join(input.isolationRoot, "home");
  child.HOME = home;
  child.PI_CODING_AGENT_DIR = join(input.isolationRoot, "agent");
  child.PI_CODING_AGENT_SESSION_DIR = join(input.isolationRoot, "sessions");
  // PI_PACKAGE_DIR is Pi's OWN read-only shipped-asset root ("Override package directory
  // (for Nix/Guix store paths)"), not operator state: getPackageDir() resolves built-in
  // themes and package metadata beneath it. It is the same installation the parent already
  // executes via piCliPath, so it carries no operator credential, session, or home data and
  // is passed through unchanged when the operator has pinned one. Binding it to the private
  // isolation root instead makes Pi's unconditional startup initTheme() fail ENOENT before
  // the RPC loop exists, killing every child at exit 1 with zero provider turns.
  copyDefined(child, input.parent, ["PI_PACKAGE_DIR"]);
  if (input.platform === "win32") {
    child.USERPROFILE = home;
    child.APPDATA = join(home, "AppData", "Roaming");
    child.LOCALAPPDATA = join(home, "AppData", "Local");
  } else {
    child.XDG_CONFIG_HOME = join(home, ".config");
    child.XDG_CACHE_HOME = join(home, ".cache");
    child.XDG_DATA_HOME = join(home, ".local", "share");
  }
  child.CODEARBITER_SUBAGENT = "1";
  child.PI_OFFLINE = "1";
  child.PI_TELEMETRY = "0";
  delete child.FARM_API_KEY;
  delete child.CLAUDE_CODE_OAUTH_TOKEN;
  return child;
}

export interface PreparedChildEnvironment {
  env: NodeJS.ProcessEnv;
  containsSensitiveValue(text: string): boolean;
  cleanup(): Promise<void>;
}

export interface ChildEnvironmentCleanupIo {
  remove(path: string, options: RmOptions): Promise<void>;
}

const DEFAULT_CLEANUP_IO: ChildEnvironmentCleanupIo = Object.freeze({
  remove: async (target: string, options: RmOptions) => await rm(target, options),
});

interface AuthReadStats {
  size: number;
  isFile(): boolean;
}

interface AuthReadHandle {
  stat(): Promise<AuthReadStats>;
  read(buffer: Buffer, offset: number, length: number, position: number | null): Promise<{ bytesRead: number }>;
  close(): Promise<void>;
}

export interface ChildEnvironmentAuthIo {
  open(path: string, flags: "r"): Promise<AuthReadHandle>;
}

const DEFAULT_AUTH_IO: ChildEnvironmentAuthIo = Object.freeze({
  open: async (path: string, flags: "r") => await open(path, flags),
});

interface StoredCredential {
  value: unknown;
  sensitiveValues: readonly string[];
}

function credentialStrings(value: unknown): readonly string[] | undefined {
  const strings = new Set<string>();
  const pending: unknown[] = [value];
  while (pending.length > 0) {
    const item = pending.pop();
    if (typeof item === "string") {
      if (item !== "") strings.add(item);
      if (strings.size > 1_024) return undefined;
    } else if (item !== null && typeof item === "object") {
      pending.push(...Object.values(item as Record<string, unknown>));
    }
  }
  return [...strings];
}

async function boundedFileText(handle: AuthReadHandle, cap: number): Promise<string | undefined> {
  const buffer = Buffer.allocUnsafe(cap + 1);
  let offset = 0;
  while (offset < buffer.byteLength) {
    const { bytesRead } = await handle.read(buffer, offset, buffer.byteLength - offset, offset);
    if (!Number.isSafeInteger(bytesRead) || bytesRead < 0 || bytesRead > buffer.byteLength - offset) return undefined;
    if (bytesRead === 0) break;
    offset += bytesRead;
  }
  return offset > cap ? undefined : buffer.subarray(0, offset).toString("utf8");
}

function operatorAgentDir(input: Omit<ChildEnvInput, "isolationRoot">): string | undefined {
  const explicit = input.parent.PI_CODING_AGENT_DIR;
  if (typeof explicit === "string" && isAbsolute(explicit)) return explicit;
  const home = input.platform === "win32"
    ? input.parent.USERPROFILE ?? input.parent.HOME
    : input.parent.HOME;
  return typeof home === "string" && isAbsolute(home) ? join(home, ".pi", "agent") : undefined;
}

async function selectedStoredCredential(
  input: Omit<ChildEnvInput, "isolationRoot">,
  authIo: ChildEnvironmentAuthIo,
): Promise<StoredCredential | undefined> {
  const agentDir = operatorAgentDir(input);
  if (agentDir === undefined) return undefined;
  let handle;
  try {
    handle = await authIo.open(join(agentDir, "auth.json"), "r");
    const metadata = await handle.stat();
    if (!metadata.isFile() || metadata.size > MAX_AUTH_FILE_BYTES) return undefined;
    const text = await boundedFileText(handle, MAX_AUTH_FILE_BYTES);
    if (text === undefined) return undefined;
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
    const record = parsed as Record<string, unknown>;
    if (!Object.prototype.hasOwnProperty.call(record, input.provider)) return undefined;
    const selected = record[input.provider];
    if (selected === null || typeof selected !== "object" || Array.isArray(selected)) return undefined;
    const sensitiveValues = credentialStrings(selected);
    return sensitiveValues === undefined ? undefined : { value: selected, sensitiveValues };
  } catch {
    return undefined;
  } finally {
    await handle?.close().catch(() => undefined);
  }
}

interface ProjectedProviderConfig {
  record: Record<string, unknown>;
  /** Every endpoint the projection accepted. Bounded and structural, but not PROVABLY
   * credential-free, so the caller registers them in the child's sensitive-value set rather
   * than assuming their innocence. */
  endpoints: readonly string[];
}

/** Read the operator's canonical models.json and return ONLY the exactly-selected provider's
 * record, credential-blind. `undefined` means there is simply nothing to project — no store,
 * no `providers`, or the selected provider is one of Pi's built-ins — which is the operator's
 * own parent behaviour and never a failure. Anything else refuses, so a record we cannot prove
 * credential-blind stops the launch instead of falling back to Pi's built-in endpoint. */
async function selectedProviderConfig(
  input: Omit<ChildEnvInput, "isolationRoot">,
  modelsIo: ChildEnvironmentAuthIo,
): Promise<ProjectedProviderConfig | undefined> {
  const agentDir = operatorAgentDir(input);
  if (agentDir === undefined) return undefined;
  const handle = await modelsIo.open(join(agentDir, "models.json"), "r").catch((error: unknown) => {
    if ((error as NodeJS.ErrnoException | null)?.code === "ENOENT") return undefined;
    refuseProjection();
  });
  if (handle === undefined) return undefined;
  try {
    const metadata = await handle.stat();
    if (!metadata.isFile() || metadata.size > MAX_MODELS_FILE_BYTES) refuseProjection();
    const text = await boundedFileText(handle, MAX_MODELS_FILE_BYTES);
    if (text === undefined) refuseProjection();
    let parsed: unknown;
    try { parsed = JSON.parse(text); }
    catch { refuseProjection(); }
    if (!plainRecord(parsed)) refuseProjection();
    const providers = parsed.providers;
    if (providers === undefined) return undefined;
    if (!plainRecord(providers)) refuseProjection();
    if (!Object.prototype.hasOwnProperty.call(providers, input.provider)) return undefined;
    const endpoints = new Set<string>();
    const record = projectedProviderRecord(providers[input.provider], endpoints);
    return { record, endpoints: [...endpoints] };
  } finally {
    await handle.close().catch(() => undefined);
  }
}

export async function prepareChildEnvironment(
  input: Omit<ChildEnvInput, "isolationRoot">,
  cleanupIo: ChildEnvironmentCleanupIo = DEFAULT_CLEANUP_IO,
  authIo: ChildEnvironmentAuthIo = DEFAULT_AUTH_IO,
  modelsIo: ChildEnvironmentAuthIo = DEFAULT_AUTH_IO,
): Promise<PreparedChildEnvironment> {
  const isolationRoot = await mkdtemp(join(tmpdir(), "codearbiter-pi-child-"));
  const env = buildChildEnv({ ...input, isolationRoot });
  const authPath = join(env.PI_CODING_AGENT_DIR!, "auth.json");
  const configPath = join(env.PI_CODING_AGENT_DIR!, "models.json");
  let credentialHandle: FileHandle | undefined;
  let configHandle: FileHandle | undefined;
  const sensitiveValues = new Set<string>();
  for (const name of PI_PROVIDER_ENV[input.provider] ?? []) {
    const value = env[name];
    if (typeof value === "string" && value !== "") sensitiveValues.add(value);
  }
  const containsSensitiveValue = (text: string): boolean => {
    for (const value of sensitiveValues) if (text.includes(value)) return true;
    return false;
  };
  // Path-safe scrub of a file this process created and still holds open: truncating through the
  // retained handle cannot be redirected by a symlink swap at the path.
  const scrubRetainedFile = async (handle: FileHandle | undefined): Promise<boolean> => {
    if (handle === undefined) return true;
    try {
      await handle.truncate(0);
      return true;
    } catch {
      return false; /* caller receives a fixed degraded result */
    } finally {
      await handle.close().catch(() => undefined);
    }
  };
  const cleanup = async (): Promise<void> => {
    const credential = credentialHandle;
    const config = configHandle;
    credentialHandle = undefined;
    configHandle = undefined;
    // The projected models.json is scrubbed on exactly the same footing as auth.json. It is
    // credential-BLIND by construction, not provably credential-FREE, so leaving it behind on
    // the removal-failure path while auth.json is truncated would be an unstated residual.
    const credentialRemoved = await scrubRetainedFile(credential);
    const configRemoved = await scrubRetainedFile(config);
    await cleanupIo.remove(authPath, { force: true, maxRetries: 5, retryDelay: 50 }).catch(() => undefined);
    await cleanupIo.remove(configPath, { force: true, maxRetries: 5, retryDelay: 50 }).catch(() => undefined);
    let isolationRemoved = true;
    try {
      await cleanupIo.remove(isolationRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 });
    } catch {
      isolationRemoved = false;
    }
    // Never report cleanup success when an unverified replacement file or any
    // other child-created credential state may still exist under the root.
    if (!credentialRemoved || !configRemoved || !isolationRemoved) throw new Error("Pi child credential cleanup failed safely.");
  };

  try {
    await Promise.all([
      mkdir(env.HOME!, { recursive: true, mode: 0o700 }),
      mkdir(env.PI_CODING_AGENT_DIR!, { recursive: true, mode: 0o700 }),
      mkdir(env.PI_CODING_AGENT_SESSION_DIR!, { recursive: true, mode: 0o700 }),
      ...(input.platform === "win32"
        ? [mkdir(env.APPDATA!, { recursive: true, mode: 0o700 }), mkdir(env.LOCALAPPDATA!, { recursive: true, mode: 0o700 })]
        : [mkdir(env.XDG_CONFIG_HOME!, { recursive: true, mode: 0o700 }), mkdir(env.XDG_CACHE_HOME!, { recursive: true, mode: 0o700 }), mkdir(env.XDG_DATA_HOME!, { recursive: true, mode: 0o700 })]),
    ]);
    // Configuration first: a record that cannot be projected credential-blind must refuse the
    // whole launch before any credential file is created.
    const providerConfig = await selectedProviderConfig(input, modelsIo);
    if (providerConfig !== undefined) {
      const providers = Object.create(null) as Record<string, unknown>;
      providers[input.provider] = providerConfig.record;
      const document = JSON.stringify({ providers });
      if (Buffer.byteLength(document, "utf8") > MAX_MODELS_FILE_BYTES) refuseProjection();
      // Endpoints are bounded and structural but not provably credential-free, so they join the
      // scrub set that suppresses a child echoing them back into its final assistant message.
      // Without this, `containsSensitiveValue` was blind to every value the config projection
      // put on the wire.
      for (const endpoint of providerConfig.endpoints) sensitiveValues.add(endpoint);
      configHandle = await open(configPath, "wx", 0o600);
      await configHandle.writeFile(document + "\n", { encoding: "utf8" });
    }
    const credential = await selectedStoredCredential(input, authIo);
    if (credential !== undefined) {
      const projected = Object.create(null) as Record<string, unknown>;
      projected[input.provider] = credential.value;
      const serialized = JSON.stringify(projected);
      if (Buffer.byteLength(serialized, "utf8") > MAX_AUTH_FILE_BYTES) throw new Error("Selected Pi credential exceeds the isolation limit.");
      for (const value of credential.sensitiveValues) sensitiveValues.add(value);
      credentialHandle = await open(authPath, "wx", 0o600);
      await credentialHandle.writeFile(serialized + "\n", { encoding: "utf8" });
    }
    return Object.freeze({ env, containsSensitiveValue, cleanup });
  } catch (error) {
    await cleanup().catch(() => undefined);
    throw error;
  }
}

export interface PiHelpContract {
  flags: string[];
  environmentNames: string[];
}

export function verifyPiHelpContract(help: string): PiHelpContract {
  const environmentNames = [...help.matchAll(/^\s{2}([A-Z][A-Z0-9_]+)\s+-/gmu)].map((match) => match[1]!);
  if (REVIEWED_HELP_FLAGS.some((flag) => !new RegExp(`(?:^|\\s)${flag}(?:\\s|,|$)`, "mu").test(help))) {
    throw new Error("Pi help contract drift detected; review child isolation before proceeding.");
  }
  const reviewedEnvironmentNames = new Set([...Object.values(PI_PROVIDER_ENV).flat(), ...REVIEWED_PI_ENV]);
  if (environmentNames.length !== reviewedEnvironmentNames.size
    || environmentNames.some((name) => !reviewedEnvironmentNames.has(name))
    || [...reviewedEnvironmentNames].some((name) => !environmentNames.includes(name))) {
    throw new Error("Pi help contract drift detected; environment allowlist requires review.");
  }
  return { flags: [...REVIEWED_HELP_FLAGS], environmentNames };
}
