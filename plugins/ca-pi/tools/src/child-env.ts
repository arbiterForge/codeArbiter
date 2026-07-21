/** child-env.ts - codeArbiter's explicit minimal Pi child environment. */

export interface ChildEnvInput {
  platform: NodeJS.Platform;
  parent: Readonly<NodeJS.ProcessEnv>;
  provider: string;
}

const WINDOWS_BASELINE = [
  "SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT", "TEMP", "TMP",
  "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA",
] as const;

const POSIX_BASELINE = [
  "HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL",
  "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
] as const;

const PI_RUNTIME = [
  "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR", "PI_PACKAGE_DIR",
] as const;

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
  copyDefined(child, input.parent, PI_RUNTIME);
  copyDefined(child, input.parent, providerNames);
  child.CODEARBITER_SUBAGENT = "1";
  child.PI_OFFLINE = "1";
  child.PI_TELEMETRY = "0";
  delete child.FARM_API_KEY;
  delete child.CLAUDE_CODE_OAUTH_TOKEN;
  return child;
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
