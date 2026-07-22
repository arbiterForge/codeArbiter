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
  child.PI_PACKAGE_DIR = join(input.isolationRoot, "packages");
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

async function boundedAuthText(handle: AuthReadHandle): Promise<string | undefined> {
  const buffer = Buffer.allocUnsafe(MAX_AUTH_FILE_BYTES + 1);
  let offset = 0;
  while (offset < buffer.byteLength) {
    const { bytesRead } = await handle.read(buffer, offset, buffer.byteLength - offset, offset);
    if (!Number.isSafeInteger(bytesRead) || bytesRead < 0 || bytesRead > buffer.byteLength - offset) return undefined;
    if (bytesRead === 0) break;
    offset += bytesRead;
  }
  return offset > MAX_AUTH_FILE_BYTES ? undefined : buffer.subarray(0, offset).toString("utf8");
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
    const text = await boundedAuthText(handle);
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

export async function prepareChildEnvironment(
  input: Omit<ChildEnvInput, "isolationRoot">,
  cleanupIo: ChildEnvironmentCleanupIo = DEFAULT_CLEANUP_IO,
  authIo: ChildEnvironmentAuthIo = DEFAULT_AUTH_IO,
): Promise<PreparedChildEnvironment> {
  const isolationRoot = await mkdtemp(join(tmpdir(), "codearbiter-pi-child-"));
  const env = buildChildEnv({ ...input, isolationRoot });
  const authPath = join(env.PI_CODING_AGENT_DIR!, "auth.json");
  let credentialHandle: FileHandle | undefined;
  const sensitiveValues = new Set<string>();
  for (const name of PI_PROVIDER_ENV[input.provider] ?? []) {
    const value = env[name];
    if (typeof value === "string" && value !== "") sensitiveValues.add(value);
  }
  const containsSensitiveValue = (text: string): boolean => {
    for (const value of sensitiveValues) if (text.includes(value)) return true;
    return false;
  };
  const cleanup = async (): Promise<void> => {
    let credentialRemoved = credentialHandle === undefined;
    if (credentialHandle !== undefined) {
      const handle = credentialHandle;
      credentialHandle = undefined;
      try {
        await handle.truncate(0);
        credentialRemoved = true;
      } catch { /* caller receives a fixed degraded result */ }
      await handle.close().catch(() => undefined);
    }
    await cleanupIo.remove(authPath, { force: true, maxRetries: 5, retryDelay: 50 }).catch(() => undefined);
    let isolationRemoved = true;
    try {
      await cleanupIo.remove(isolationRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 });
    } catch {
      isolationRemoved = false;
    }
    // Never report cleanup success when an unverified replacement file or any
    // other child-created credential state may still exist under the root.
    if (!credentialRemoved || !isolationRemoved) throw new Error("Pi child credential cleanup failed safely.");
  };

  try {
    await Promise.all([
      mkdir(env.HOME!, { recursive: true, mode: 0o700 }),
      mkdir(env.PI_CODING_AGENT_DIR!, { recursive: true, mode: 0o700 }),
      mkdir(env.PI_CODING_AGENT_SESSION_DIR!, { recursive: true, mode: 0o700 }),
      mkdir(env.PI_PACKAGE_DIR!, { recursive: true, mode: 0o700 }),
      ...(input.platform === "win32"
        ? [mkdir(env.APPDATA!, { recursive: true, mode: 0o700 }), mkdir(env.LOCALAPPDATA!, { recursive: true, mode: 0o700 })]
        : [mkdir(env.XDG_CONFIG_HOME!, { recursive: true, mode: 0o700 }), mkdir(env.XDG_CACHE_HOME!, { recursive: true, mode: 0o700 }), mkdir(env.XDG_DATA_HOME!, { recursive: true, mode: 0o700 })]),
    ]);
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
