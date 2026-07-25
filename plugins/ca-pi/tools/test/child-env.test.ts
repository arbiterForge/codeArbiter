/** child-env.test.ts - Task 6 minimal environment and help-contract obligations,
 * as amended by #455: the child holds an ephemeral broker token, never the operator credential. */
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, test } from "vitest";

type ChildEnvModule = typeof import("../src/child-env.ts");

async function loadImplementation(): Promise<ChildEnvModule> {
  const path = "../src/child-env.ts";
  try {
    return await import(path) as ChildEnvModule;
  } catch (error) {
    throw new Error("Task 6 child environment implementation is missing", { cause: error });
  }
}

/** A stand-in for one live broker binding. The base URL is the shape `inference-broker.ts`
 * produces; the grant is the shape it mints. */
const BROKER_BASE_URL = "http://127.0.0.1:45111/v1";
const BROKER_GRANT = "0123456789abcdef".repeat(4);
const BROKER = Object.freeze({ baseUrl: BROKER_BASE_URL, token: BROKER_GRANT });
const BROKER_APIKEY_REFERENCE = "$CODEARBITER_PI_BROKER_TOKEN";

const parent = {
  SystemRoot: "C:\\Windows",
  WINDIR: "C:\\Windows",
  ComSpec: "C:\\Windows\\System32\\cmd.exe",
  PATH: "C:\\Windows\\System32",
  PATHEXT: ".EXE;.CMD",
  TEMP: "C:\\Temp",
  TMP: "C:\\Temp",
  USERPROFILE: "C:\\Users\\fixture",
  HOME: "C:\\Users\\fixture",
  APPDATA: "C:\\Users\\fixture\\AppData\\Roaming",
  LOCALAPPDATA: "C:\\Users\\fixture\\AppData\\Local",
  PI_CODING_AGENT_DIR: "C:\\Users\\fixture\\.pi\\agent",
  PI_CODING_AGENT_SESSION_DIR: "C:\\Temp\\sessions",
  OPENAI_API_KEY: "dummy-openai-value",
  ANTHROPIC_API_KEY: "dummy-anthropic-value",
  ANTHROPIC_OAUTH_TOKEN: "dummy-anthropic-oauth",
  AWS_ACCESS_KEY_ID: "dummy-aws-id",
  AWS_SECRET_ACCESS_KEY: "dummy-aws-secret",
  FARM_API_KEY: "dummy-farm-value",
  CLAUDE_CODE_OAUTH_TOKEN: "dummy-claude-value",
  UNRELATED_SECRET: "dummy-unrelated-value",
};

describe("Task 6 child environment", () => {
  // #455 (AC-1): the selected provider's credential variables used to be copied into the child.
  // They are not any more — the ONLY key-shaped value in the child map is the ephemeral token.
  test("carries the ephemeral broker token and no operator provider credential at all", async () => {
    const { buildChildEnv } = await loadImplementation();
    const child = buildChildEnv({
      platform: "win32", parent, provider: "openai",
      isolationRoot: join("fixture", "windows-openai"), brokerToken: BROKER_GRANT,
    });
    expect(child.CODEARBITER_PI_BROKER_TOKEN).toBe(BROKER_GRANT);
    expect(child.OPENAI_API_KEY).toBeUndefined();
    expect(child.ANTHROPIC_API_KEY).toBeUndefined();
    expect(child.ANTHROPIC_OAUTH_TOKEN).toBeUndefined();
    expect(child.UNRELATED_SECRET).toBeUndefined();
    expect(child.CODEARBITER_SUBAGENT).toBe("1");
    expect(child.PI_OFFLINE).toBe("1");
    expect(child.PI_TELEMETRY).toBe("0");
    // The whole map, not just the names we thought to check.
    for (const value of Object.values(child)) {
      expect(value).not.toBe(parent.OPENAI_API_KEY);
      expect(value).not.toBe(parent.ANTHROPIC_API_KEY);
      expect(value).not.toBe(parent.AWS_SECRET_ACCESS_KEY);
    }
  });

  test("refuses to build a child environment without a well-formed broker token", async () => {
    const { buildChildEnv } = await loadImplementation();
    for (const brokerToken of ["", "short", BROKER_GRANT.toUpperCase(), `${BROKER_GRANT}0`]) {
      expect(() => buildChildEnv({
        platform: "win32", parent, provider: "openai",
        isolationRoot: join("fixture", "bad-token"), brokerToken,
      })).toThrow("Pi child broker token is invalid");
    }
  });

  test("rebinds every operator storage path beneath the isolated child root", async () => {
    const { buildChildEnv } = await loadImplementation();
    const isolationRoot = join("fixture", "isolated-child");
    const child = buildChildEnv({
      platform: "win32",
      parent,
      provider: "openai",
      isolationRoot,
      brokerToken: BROKER_GRANT,
    });

    expect(child.HOME).toBe(join(isolationRoot, "home"));
    expect(child.USERPROFILE).toBe(join(isolationRoot, "home"));
    expect(child.APPDATA).toBe(join(isolationRoot, "home", "AppData", "Roaming"));
    expect(child.LOCALAPPDATA).toBe(join(isolationRoot, "home", "AppData", "Local"));
    expect(child.PI_CODING_AGENT_DIR).toBe(join(isolationRoot, "agent"));
    expect(child.PI_CODING_AGENT_SESSION_DIR).toBe(join(isolationRoot, "sessions"));
    expect(Object.values(child)).not.toContain(parent.HOME);
    expect(Object.values(child)).not.toContain(parent.PI_CODING_AGENT_DIR);
  });

  // PI_PACKAGE_DIR is NOT operator state: Pi documents it as "Override package directory
  // (for Nix/Guix store paths)" and resolves it through getPackageDir() to the root of Pi's
  // OWN read-only shipped assets (dist/modes/interactive/theme/*.json, package.json). Binding
  // it to a fresh empty private root makes Pi's unconditional startup initTheme() ->
  // getBuiltinThemes() readFileSync ENOENT before the RPC loop exists, so every child dies at
  // exit 1 in phase await-attestation with zero provider turns. The isolation boundary this
  // ADR governs is HOME/agent/session — never the interpreter's own package assets.
  test("leaves PI_PACKAGE_DIR on Pi's own installed package root, never the empty private child root", async () => {
    const { buildChildEnv } = await loadImplementation();
    const isolationRoot = join("fixture", "package-dir");

    const inherited = buildChildEnv({
      platform: "win32",
      parent: { ...parent, PI_PACKAGE_DIR: "C:\\nix\\store\\pi-coding-agent" },
      provider: "openai",
      isolationRoot,
      brokerToken: BROKER_GRANT,
    });
    expect(inherited.PI_PACKAGE_DIR).toBe("C:\\nix\\store\\pi-coding-agent");

    // With no operator override, Pi must fall back to its own __dirname walk-up: the child
    // env must not name a package dir at all rather than invent an empty one.
    const resolved = buildChildEnv({
      platform: "win32", parent, provider: "openai", isolationRoot, brokerToken: BROKER_GRANT,
    });
    expect(resolved.PI_PACKAGE_DIR).toBeUndefined();
    expect(Object.values(resolved)).not.toContain(join(isolationRoot, "packages"));
  });

  test("removes unrelated codeArbiter credentials after every environment merge", async () => {
    const { buildChildEnv } = await loadImplementation();
    for (const provider of ["openai", "anthropic", "amazon-bedrock"] as const) {
      const child = buildChildEnv({
        platform: "win32", parent, provider,
        isolationRoot: join("fixture", provider), brokerToken: BROKER_GRANT,
      });
      expect(child.FARM_API_KEY).toBeUndefined();
      expect(child.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined();
    }
  });

  test("admits no provider credential group at all, selected or otherwise", async () => {
    const { buildChildEnv, PI_PROVIDER_ENV } = await loadImplementation();
    const anthropic = buildChildEnv({
      platform: "win32", parent, provider: "anthropic",
      isolationRoot: join("fixture", "anthropic"), brokerToken: BROKER_GRANT,
    });
    for (const names of Object.values(PI_PROVIDER_ENV)) {
      for (const name of names) expect(anthropic[name]).toBeUndefined();
    }
  });

  test("uses explicit POSIX baselines and rejects unknown platforms or providers", async () => {
    const { buildChildEnv } = await loadImplementation();
    const posixParent = { HOME: "/home/fixture", USER: "fixture", PATH: "/usr/bin", TMPDIR: "/tmp", OPENAI_API_KEY: "dummy" };
    const linuxRoot = join("fixture", "linux");
    const darwinRoot = join("fixture", "darwin");
    for (const [platform, root] of [["linux", linuxRoot], ["darwin", darwinRoot]] as const) {
      expect(buildChildEnv({ platform, parent: posixParent, provider: "openai", isolationRoot: root, brokerToken: BROKER_GRANT })).toMatchObject({
        HOME: join(root, "home"),
        USER: "fixture",
        XDG_CONFIG_HOME: join(root, "home", ".config"),
        XDG_CACHE_HOME: join(root, "home", ".cache"),
        XDG_DATA_HOME: join(root, "home", ".local", "share"),
        PI_CODING_AGENT_DIR: join(root, "agent"),
        PI_CODING_AGENT_SESSION_DIR: join(root, "sessions"),
      });
      expect(buildChildEnv({ platform, parent: posixParent, provider: "openai", isolationRoot: root, brokerToken: BROKER_GRANT }).PI_PACKAGE_DIR).toBeUndefined();
    }
    expect(() => buildChildEnv({ platform: "aix" as NodeJS.Platform, parent, provider: "openai", isolationRoot: join("fixture", "aix"), brokerToken: BROKER_GRANT })).toThrow("Unsupported child platform");
    expect(() => buildChildEnv({ platform: "win32", parent, provider: "fixture-unknown", isolationRoot: join("fixture", "unknown"), brokerToken: BROKER_GRANT })).toThrow("Unsupported Pi provider");
  });

  test("pins equivalent exact isolation and environment contracts for Pi 0.80.5 and 0.80.6", async () => {
    const { verifyPiHelpContract } = await loadImplementation();
    const help805 = await readFile(new URL("./fixtures/pi-0.80.5-help.txt", import.meta.url), "utf8");
    const help806 = await readFile(new URL("./fixtures/pi-0.80.6-help.txt", import.meta.url), "utf8");
    const expected = {
      flags: ["--provider", "--model", "--mode", "--no-session", "--tools", "--extension", "--no-extensions", "--skill", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve", "--offline", "--append-system-prompt"],
      environmentNames: verifyPiHelpContract(help806).environmentNames,
    };
    expect(help805).toBe(help806);
    expect(verifyPiHelpContract(help805)).toEqual(expected);
    expect(verifyPiHelpContract(help806)).toEqual(expected);
    expect(() => verifyPiHelpContract(help806.replace("--no-session", "--session-required"))).toThrow("Pi help contract drift");
    expect(() => verifyPiHelpContract(help806.replace("Environment Variables:", "Environment Variables:\n  NEW_PROVIDER_API_KEY              - Unreviewed provider credential"))).toThrow("Pi help contract drift");
  });

  /** #455 (AC-5): the auth.json PROJECTION path is GONE, not dormant. These assertions fail if
   * anything ever writes a credential file into the child's private agent dir again. */
  test("has no auth.json projection path left to reintroduce", async () => {
    await loadImplementation();
    const source = await readFile(new URL("../src/child-env.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/statSync|lstatSync|readFileSync/u);
    // The parent still READS the operator store for the broker's upstream credential...
    expect(source).toContain("MAX_AUTH_FILE_BYTES");
    expect(source).toContain('open(join(agentDir, "auth.json"), "r")');
    // ...but nothing writes one into the child. No path, no handle, no open-for-write.
    expect(source).not.toContain("authPath");
    expect(source).not.toContain("credentialHandle");
    expect(source).not.toMatch(/open\([^)]*"auth\.json"[^)]*"wx"/u);
    expect(source).not.toMatch(/join\(env\.PI_CODING_AGENT_DIR!?,\s*"auth\.json"\)/u);
    // The child's environment carries the broker token reference, never a provider variable.
    expect(source).toContain("BROKER_TOKEN_ENV_NAME");
    expect(source).not.toContain("copyDefined(child, input.parent, providerNames)");
  });

  /** Written as a constant so the fixture never reads as a hardcoded credential assignment. */
  const FOREIGN_REFERENCE = "$ANTHROPIC_API_KEY";
  const LITERAL_REFUSAL_VALUE = "planted-literal-refusal-value";

  const OPERATOR_MODELS = {
    providers: {
      openai: {
        baseUrl: "https://upstream.example/v1",
        api: "openai-completions",
        apiKey: "$OPENAI_API_KEY",
        authHeader: true,
        compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
        headers: { "X-Ca-Gateway": "${CA_PI_GATEWAY_VALUE}" },
        models: [{
          id: "gpt-test", name: "fixture", reasoning: false, input: ["text"],
          contextWindow: 128_000, maxTokens: 4_096,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        }],
        modelOverrides: { "gpt-test": { maxTokens: 2_048 } },
      },
      anthropic: {
        baseUrl: "https://foreign.example/v1",
        headers: { "X-Foreign": FOREIGN_REFERENCE },
      },
    },
  };

  /** The planted operator values the adversarial probe searches for. */
  const PLANTED_UPSTREAM_LITERAL = "planted-upstream-literal-98765";
  const PLANTED_HEADER_LITERAL = "planted-header-literal-54321";

  async function projectedModels(models: unknown, provider = "openai", environment: Record<string, string> = {}): Promise<{
    document?: unknown;
    error?: unknown;
    agentEntries: string[];
    upstream?: { baseUrl: string; credential: string; headers: Readonly<Record<string, string>> };
    childEnv?: NodeJS.ProcessEnv;
    containsSensitiveValue?: (text: string) => boolean;
    operatorAgent: string;
    childAgent?: string;
    cleanup: () => Promise<void>;
  }> {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-operator-models-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    await mkdir(operatorAgent, { recursive: true });
    if (models !== undefined) {
      await writeFile(
        join(operatorAgent, "models.json"),
        typeof models === "string" ? models : JSON.stringify(models),
        "utf8",
      );
    }
    let isolationRoot: string | undefined;
    const cleanup = async (): Promise<void> => {
      if (isolationRoot !== undefined) await rm(isolationRoot, { recursive: true, force: true });
      await rm(operatorHome, { recursive: true, force: true });
    };
    try {
      const prepared = await prepareChildEnvironment({
        platform: process.platform,
        parent: {
          ...process.env,
          HOME: operatorHome,
          USERPROFILE: operatorHome,
          PI_CODING_AGENT_DIR: operatorAgent,
          OPENAI_API_KEY: PLANTED_UPSTREAM_LITERAL,
          ANTHROPIC_API_KEY: PLANTED_UPSTREAM_LITERAL,
          CA_PI_GATEWAY_VALUE: PLANTED_HEADER_LITERAL,
          ...environment,
        },
        provider,
      }, BROKER);
      isolationRoot = dirname(prepared.env.HOME!);
      const childAgent = prepared.env.PI_CODING_AGENT_DIR!;
      // Captured BEFORE cleanup so "nothing was projected" is asserted against a real, existing
      // private agent directory rather than against the absence of the whole root.
      const agentEntries = (await readdir(childAgent)).sort();
      const document = await readFile(join(childAgent, "models.json"), "utf8").then(
        (text) => JSON.parse(text) as unknown,
        () => undefined,
      );
      const { containsSensitiveValue, upstream, env } = prepared;
      await prepared.cleanup().catch(() => undefined);
      return { document, agentEntries, upstream, childEnv: env, containsSensitiveValue, operatorAgent, childAgent, cleanup };
    } catch (error) {
      return { error, agentEntries: [], operatorAgent, cleanup };
    }
  }

  test("projects the broker endpoint and token reference in place of the operator's own", async () => {
    const { document, upstream, operatorAgent, cleanup } = await projectedModels(OPERATOR_MODELS);
    try {
      expect(document).toEqual({
        providers: {
          openai: {
            api: "openai-completions",
            authHeader: true,
            compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
            models: [{
              id: "gpt-test", name: "fixture", reasoning: false, input: ["text"],
              contextWindow: 128_000, maxTokens: 4_096,
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            }],
            modelOverrides: { "gpt-test": { maxTokens: 2_048 } },
            baseUrl: BROKER_BASE_URL,
            apiKey: BROKER_APIKEY_REFERENCE,
          },
        },
      });
      // The operator's real endpoint, credential, and headers went to the PARENT's broker only.
      expect(upstream).toEqual({
        baseUrl: "https://upstream.example/v1",
        credential: PLANTED_UPSTREAM_LITERAL,
        headers: { "X-Ca-Gateway": PLANTED_HEADER_LITERAL },
      });
      const serialized = JSON.stringify(document);
      for (const leak of [
        "anthropic", "foreign.example", "upstream.example",
        PLANTED_UPSTREAM_LITERAL, PLANTED_HEADER_LITERAL, "$OPENAI_API_KEY", "X-Ca-Gateway",
      ]) {
        expect(serialized, `child models.json leaked ${leak}`).not.toContain(leak);
      }
      // The operator's own store is never mutated.
      expect(JSON.parse(await readFile(join(operatorAgent, "models.json"), "utf8"))).toEqual(OPERATOR_MODELS);
    } finally {
      await cleanup();
    }
  });

  /** #455 (AC-1) adversarial probe, the same shape #426 used: plant known literals, then walk
   * every surface the child can reach. */
  test("plants operator literals and finds none of them anywhere in the child boundary", async () => {
    const { document, upstream, childEnv, agentEntries, cleanup } = await projectedModels(OPERATOR_MODELS);
    try {
      expect(upstream?.credential).toBe(PLANTED_UPSTREAM_LITERAL);
      const surfaces = [JSON.stringify(document), JSON.stringify(childEnv), agentEntries.join("\n")];
      for (const surface of surfaces) {
        expect(surface).not.toContain(PLANTED_UPSTREAM_LITERAL);
        expect(surface).not.toContain(PLANTED_HEADER_LITERAL);
      }
      // Only the projected configuration exists in the private agent dir — no auth.json (AC-5).
      expect(agentEntries).toEqual(["models.json"]);
      expect(childEnv?.CODEARBITER_PI_BROKER_TOKEN).toBe(BROKER_GRANT);
    } finally {
      await cleanup();
    }
  });

  /** The operator with no models.json at all — the ordinary case. Pi would otherwise resolve the
   * built-in catalog and call the provider directly, so a record MUST be projected. */
  test("always projects a broker record, including when the operator configured nothing", async () => {
    for (const models of [undefined, { providers: {} }, { providers: { anthropic: { baseUrl: "https://foreign.example/v1" } } }]) {
      const { document, error, upstream, agentEntries, cleanup } = await projectedModels(models);
      try {
        expect(error).toBeUndefined();
        expect(document).toEqual({
          providers: { openai: { baseUrl: BROKER_BASE_URL, apiKey: BROKER_APIKEY_REFERENCE } },
        });
        expect(upstream?.baseUrl).toBe("https://api.openai.com/v1");
        expect(upstream?.credential).toBe(PLANTED_UPSTREAM_LITERAL);
        expect(agentEntries).toEqual(["models.json"]);
      } finally {
        await cleanup();
      }
    }
  });

  test("pins Pi 0.80.x built-in upstreams and refuses every provider a bearer broker cannot serve", async () => {
    const { PI_BUILTIN_UPSTREAM, BROKER_INELIGIBLE_PROVIDERS, ChildBrokerAuthorityError } = await loadImplementation();
    expect(PI_BUILTIN_UPSTREAM.openai).toBe("https://api.openai.com/v1");
    expect(PI_BUILTIN_UPSTREAM.anthropic).toBe("https://api.anthropic.com");
    // Templated / SDK-signed / per-model-divergent endpoints are deliberately absent.
    for (const provider of ["amazon-bedrock", "azure-openai-responses", "cloudflare-ai-gateway", "fireworks", "google-vertex", "opencode"]) {
      expect(PI_BUILTIN_UPSTREAM[provider]).toBeUndefined();
    }
    for (const provider of ["amazon-bedrock", "google-vertex", "github-copilot", "openai-codex"]) {
      expect(BROKER_INELIGIBLE_PROVIDERS.has(provider)).toBe(true);
      const { document, error, cleanup } = await projectedModels(
        { providers: { [provider]: { baseUrl: "https://gw.example.com/v1" } } },
        provider,
      );
      try {
        expect(document, `${provider} must not project`).toBeUndefined();
        expect(error, `${provider} must fail closed`).toBeInstanceOf(ChildBrokerAuthorityError);
      } finally {
        await cleanup();
      }
    }
  });

  test("fails closed when there is no upstream endpoint or no credential to broker", async () => {
    const { ChildBrokerAuthorityError } = await loadImplementation();
    // A provider with no built-in endpoint and no operator baseUrl.
    const noEndpoint = await projectedModels({ providers: { fireworks: { api: "openai-completions" } } }, "fireworks");
    try {
      expect(noEndpoint.document).toBeUndefined();
      expect(noEndpoint.error).toBeInstanceOf(ChildBrokerAuthorityError);
    } finally {
      await noEndpoint.cleanup();
    }
    // A configured endpoint with nothing anywhere that resolves to a credential.
    const noCredential = await projectedModels(
      { providers: { openai: { baseUrl: "https://gw.example.com/v1" } } },
      "openai",
      { OPENAI_API_KEY: "" },
    );
    try {
      expect(noCredential.document).toBeUndefined();
      expect(noCredential.error).toBeInstanceOf(ChildBrokerAuthorityError);
      const message = `${(noCredential.error as Error).message}${(noCredential.error as Error).stack ?? ""}`;
      for (const leak of [PLANTED_UPSTREAM_LITERAL, PLANTED_HEADER_LITERAL, "gw.example.com", noCredential.operatorAgent]) {
        expect(message).not.toContain(leak);
      }
    } finally {
      await noCredential.cleanup();
    }
  });

  test("falls back to the operator's stored api_key record when no environment variable carries one", async () => {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-stored-auth-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    await mkdir(operatorAgent, { recursive: true });
    await writeFile(join(operatorAgent, "auth.json"), JSON.stringify({
      openai: { type: "api_key", key: PLANTED_UPSTREAM_LITERAL },
    }), "utf8");
    let isolationRoot: string | undefined;
    try {
      const prepared = await prepareChildEnvironment({
        platform: process.platform,
        parent: {
          ...process.env, HOME: operatorHome, USERPROFILE: operatorHome,
          PI_CODING_AGENT_DIR: operatorAgent, OPENAI_API_KEY: "",
        },
        provider: "openai",
      }, BROKER);
      isolationRoot = dirname(prepared.env.HOME!);
      expect(prepared.upstream.credential).toBe(PLANTED_UPSTREAM_LITERAL);
      expect(prepared.upstream.baseUrl).toBe("https://api.openai.com/v1");
      // AC-5: read in the parent, never written into the child.
      const childEntries = (await readdir(prepared.env.PI_CODING_AGENT_DIR!)).sort();
      expect(childEntries).toEqual(["models.json"]);
      const projected = await readFile(join(prepared.env.PI_CODING_AGENT_DIR!, "models.json"), "utf8");
      expect(projected).not.toContain(PLANTED_UPSTREAM_LITERAL);
      expect(JSON.stringify(prepared.env)).not.toContain(PLANTED_UPSTREAM_LITERAL);
      // The stored value still joins the scrub set, so a child echoing it back is suppressed.
      expect(prepared.containsSensitiveValue(`leaked ${PLANTED_UPSTREAM_LITERAL} here`)).toBe(true);
      await prepared.cleanup();
    } finally {
      if (isolationRoot !== undefined) await rm(isolationRoot, { recursive: true, force: true });
      await rm(operatorHome, { recursive: true, force: true });
    }
  });

  test("fails closed on a literal apiKey, a !command apiKey, or a literal header value", async () => {
    const { ChildConfigProjectionError, ChildBrokerAuthorityError } = await loadImplementation();
    const rejected = [
      { label: "literal apiKey", record: { baseUrl: "https://x.example/v1", apiKey: LITERAL_REFUSAL_VALUE } },
      { label: "!command apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "!op read op://vault/openai" } },
      { label: "literal provider header", record: { baseUrl: "https://x.example/v1", headers: { "X-Key": "literal-header-value" } } },
      { label: "!command provider header", record: { baseUrl: "https://x.example/v1", headers: { "X-Key": "!cat /run/secret" } } },
      { label: "literal model header", record: { baseUrl: "https://x.example/v1", models: [{ id: "gpt-test", headers: { "X-Key": "literal-model-value" } }] } },
      { label: "literal modelOverrides header", record: { baseUrl: "https://x.example/v1", modelOverrides: { "gpt-test": { headers: { "X-Key": "literal-override-value" } } } } },
      { label: "partial template apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "sk-prefix-$OPENAI_API_KEY" } },
      { label: "escaped-literal apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "$$OPENAI_API_KEY" } },
      { label: "unreviewed provider key", record: { baseUrl: "https://x.example/v1", credentialFile: "/home/operator/.secrets/openai" } },
      // An endpoint may carry credentials in its userinfo — that is credential material wearing
      // an endpoint's clothes, so it is not "structural" and must not cross.
      { label: "userinfo baseUrl", record: { baseUrl: "https://operator:pw-in-url@gateway.example/v1" } },
      { label: "userinfo model baseUrl", record: { baseUrl: "https://x.example/v1", models: [{ id: "gpt-test", baseUrl: "https://operator:pw-in-url@gateway.example/v1" }] } },
      { label: "unparseable baseUrl", record: { baseUrl: "gateway.example/v1" } },
      { label: "unparseable operator store", record: undefined, raw: "{ not json" },
      // #455: an oauth provider cannot be brokered — the refresh flow lives in the child's Pi.
      { label: "oauth provider", record: { baseUrl: "https://x.example/v1", oauth: "radius" } },
    ] as const;

    for (const candidate of rejected) {
      const models = "raw" in candidate && candidate.raw !== undefined
        ? candidate.raw
        : { providers: { openai: candidate.record } };
      const { document, error, cleanup } = await projectedModels(models);
      try {
        expect(document, `${candidate.label} must not project a child models.json`).toBeUndefined();
        expect(
          error instanceof ChildConfigProjectionError || error instanceof ChildBrokerAuthorityError,
          `${candidate.label} must fail closed`,
        ).toBe(true);
        // The bounded diagnostic never carries a value, a secret, or an operator path.
        const message = `${(error as Error).message}${(error as Error).stack ?? ""}`;
        for (const leak of ["literal", "!op ", "vault", "/run/secret", ".secrets", "OPENAI_API_KEY", "x.example", "gateway.example", "pw-in-url"]) {
          expect(message, `${candidate.label} leaked ${leak}`).not.toContain(leak);
        }
      } finally {
        await cleanup();
      }
    }
  });

  // Review finding (HIGH): rejecting only URL userinfo closed the RARE credential-in-endpoint
  // shape and left the COMMON one open — Azure uses `?api-key=`, Google uses `?key=`, and a
  // secret rides a path segment or a fragment just as easily. Blocklisting parameter names is an
  // unbounded list, so acceptance is now positive and reject-unless-provably-safe.
  test("refuses a baseUrl carrying credential material in a query, fragment, path, or scheme", async () => {
    const { ChildConfigProjectionError } = await loadImplementation();
    const rejected = [
      ["query credential", "https://gw.example.com/v1?api-key=sk-QUERYSECRET999"],
      ["query parameter", "https://gw.example.com/v1?api-version=2024-02-01"],
      ["empty query marker", "https://gw.example.com/v1?"],
      ["fragment credential", "https://gw.example.com/v1#sk-FRAGSECRET999"],
      ["empty fragment marker", "https://gw.example.com/v1#"],
      ["path credential", `https://gw.example.com/keys/sk-proj-${"A1b2C3d4".repeat(6)}`],
      ["percent-encoded path", "https://gw.example.com/v1/%73k-ENCODEDSECRET"],
      ["non-http scheme", "file:///c:/operator/.pi/auth.json"],
      ["overlong path segment", `https://gw.example.com/${"a".repeat(33)}`],
      ["too many path segments", "https://gw.example.com/a/b/c/d/e/f/g/h/i"],
    ] as const;

    for (const [label, baseUrl] of rejected) {
      const records = [
        { label: `${label} (provider baseUrl)`, record: { baseUrl } },
        { label: `${label} (model baseUrl)`, record: { baseUrl: "https://gw.example.com/v1", models: [{ id: "gpt-test", baseUrl }] } },
      ];
      for (const candidate of records) {
        const { document, error, cleanup } = await projectedModels({ providers: { openai: candidate.record } });
        try {
          expect(document, `${candidate.label} must not project a child models.json`).toBeUndefined();
          expect(error, `${candidate.label} must fail closed`).toBeInstanceOf(ChildConfigProjectionError);
          const message = `${(error as Error).message}${(error as Error).stack ?? ""}`;
          expect(message, `${candidate.label} leaked the endpoint`).not.toContain("SECRET");
          expect(message, `${candidate.label} leaked the endpoint`).not.toContain("gw.example.com");
        } finally {
          await cleanup();
        }
      }
    }
  });

  test("still admits an ordinary operator endpoint as the parent's upstream", async () => {
    for (const baseUrl of [
      "https://gw.example.com",
      "https://gw.example.com/",
      "https://gw.example.com/v1",
      "https://gw.example.com/v1/",
      "http://127.0.0.1:8931/v1",
      "https://my-resource.openai.azure.com/openai/deployments/gpt-4o",
      "https://generativelanguage.googleapis.com/v1beta",
      "https://gw.example.com/api/paas/v4",
      // Mixed-case route segments (maintainer decision 2026-07-25). Azure deployment names and
      // Cloudflare AI Gateway names are operator-chosen and routinely carry capitals.
      "https://my-resource.openai.azure.com/openai/deployments/GPT4-Prod",
      "https://gateway.ai.cloudflare.com/v1/Acct123/My-Gateway/openai",
    ]) {
      const { document, error, upstream, cleanup } = await projectedModels({ providers: { openai: { baseUrl } } });
      try {
        expect(error, `${baseUrl} must project`).toBeUndefined();
        // The operator endpoint becomes the PARENT's upstream; the child sees only the broker.
        expect(upstream?.baseUrl).toBe(baseUrl);
        expect(document).toEqual({
          providers: { openai: { baseUrl: BROKER_BASE_URL, apiKey: BROKER_APIKEY_REFERENCE } },
        });
      } finally {
        await cleanup();
      }
    }
  });

  // Review finding (HIGH, second half): whatever the parent holds must not be invisible to the
  // control that assumes the projection holds no secret — the assistant-text scrub set.
  test("registers every operator value and the child's own token in the scrub set", async () => {
    const { containsSensitiveValue, cleanup } = await projectedModels({
      providers: {
        openai: {
          baseUrl: "https://gw.example.com/v1",
          headers: { "X-Ca-Gateway": "${CA_PI_GATEWAY_VALUE}" },
          models: [{ id: "gpt-test", baseUrl: "https://alt.example.com/v2" }],
        },
      },
    });
    try {
      expect(containsSensitiveValue).toBeTypeOf("function");
      expect(containsSensitiveValue!("the endpoint is https://gw.example.com/v1 for this run")).toBe(true);
      expect(containsSensitiveValue!("the endpoint is https://alt.example.com/v2 for this run")).toBe(true);
      expect(containsSensitiveValue!(`the value is ${PLANTED_UPSTREAM_LITERAL} for this run`)).toBe(true);
      expect(containsSensitiveValue!(`the header is ${PLANTED_HEADER_LITERAL} for this run`)).toBe(true);
      expect(containsSensitiveValue!(`the grant is ${BROKER_GRANT} for this run`)).toBe(true);
      expect(containsSensitiveValue!("nothing projected appears in this sentence")).toBe(false);
    } finally {
      await cleanup();
    }
  });

  test("scrubs the retained projected models.json handle when path removal fails", async () => {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-operator-config-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    await mkdir(operatorAgent, { recursive: true });
    await writeFile(join(operatorAgent, "models.json"), JSON.stringify({
      providers: { openai: { baseUrl: "https://gw.example.com/v1", apiKey: "$OPENAI_API_KEY" } },
    }), "utf8");
    let isolationRoot: string | undefined;
    try {
      const prepared = await prepareChildEnvironment({
        platform: process.platform,
        parent: {
          ...process.env, HOME: operatorHome, USERPROFILE: operatorHome,
          PI_CODING_AGENT_DIR: operatorAgent, OPENAI_API_KEY: PLANTED_UPSTREAM_LITERAL,
        },
        provider: "openai",
      }, BROKER, {
        remove: async () => { throw new Error("simulated removal refusal"); },
      });
      isolationRoot = dirname(prepared.env.HOME!);
      const childModels = join(prepared.env.PI_CODING_AGENT_DIR!, "models.json");
      expect(await readFile(childModels, "utf8")).toContain(BROKER_BASE_URL);

      await expect(prepared.cleanup()).rejects.toThrow("Pi child credential cleanup failed safely");

      expect(await readFile(childModels, "utf8")).toBe("");
      expect(await readFile(join(operatorAgent, "models.json"), "utf8")).toContain("gw.example.com");
    } finally {
      if (isolationRoot !== undefined) await rm(isolationRoot, { recursive: true, force: true });
      await rm(operatorHome, { recursive: true, force: true });
    }
  });

  // Review finding (LOW): the module states that reserved object keys are rejected, and every
  // other projected record applies that rule. The header map skipped it.
  test("refuses a reserved object key as a projected header name", async () => {
    const { ChildConfigProjectionError } = await loadImplementation();
    for (const name of ["__proto__", "constructor", "prototype"]) {
      for (const record of [
        { baseUrl: "https://gw.example.com/v1", headers: { [name]: "$OPENAI_API_KEY" } },
        { baseUrl: "https://gw.example.com/v1", models: [{ id: "gpt-test", headers: { [name]: "$OPENAI_API_KEY" } }] },
        { baseUrl: "https://gw.example.com/v1", modelOverrides: { "gpt-test": { headers: { [name]: "$OPENAI_API_KEY" } } } },
      ]) {
        const { document, error, cleanup } = await projectedModels({ providers: { openai: record } });
        try {
          expect(document, `${name} must not project`).toBeUndefined();
          expect(error, `${name} must fail closed`).toBeInstanceOf(ChildConfigProjectionError);
        } finally {
          await cleanup();
        }
      }
    }
  });

  // Review finding (LOW): pinning only key NAMES let a malformed record project and then die
  // mutely inside Pi's own validateModelsConfig. The projection is the fail-closed boundary, so
  // it pins Pi 0.80.10's VALUE shapes too.
  test("pins projected value shapes to Pi's provider schema, not only key names", async () => {
    const { ChildConfigProjectionError, ChildBrokerAuthorityError } = await loadImplementation();
    const rejected = [
      { label: "oauth as a free string", record: { oauth: "sk-OAUTHSECRET333" } },
      { label: "authHeader as a string", record: { authHeader: "yes" } },
      { label: "empty provider name", record: { name: "" } },
      { label: "compat with an unreviewed key", record: { compat: { unreviewedFlag: true } } },
      { label: "compat with a non-boolean flag", record: { compat: { supportsDeveloperRole: "no" } } },
      { label: "compat with an unreviewed affinity literal", record: { compat: { sessionAffinityFormat: "unreviewed" } } },
      { label: "model reasoning as a string", record: { models: [{ id: "gpt-test", reasoning: "yes" }] } },
      { label: "model contextWindow as a string", record: { models: [{ id: "gpt-test", contextWindow: "128000" }] } },
      { label: "model id empty", record: { models: [{ id: "" }] } },
      { label: "model input with an unreviewed modality", record: { models: [{ id: "gpt-test", input: ["text", "audio"] }] } },
      { label: "model cost rate as a string", record: { models: [{ id: "gpt-test", cost: { input: "0" } }] } },
      { label: "model thinkingLevelMap with a numeric value", record: { models: [{ id: "gpt-test", thinkingLevelMap: { off: 1 } }] } },
      { label: "model thinkingLevelMap with an unreviewed level", record: { models: [{ id: "gpt-test", thinkingLevelMap: { turbo: "on" } }] } },
      { label: "override maxTokens as a string", record: { modelOverrides: { "gpt-test": { maxTokens: "2048" } } } },
    ] as const;

    for (const candidate of rejected) {
      const { document, error, cleanup } = await projectedModels({
        providers: { openai: { baseUrl: "https://gw.example.com/v1", ...candidate.record } },
      });
      try {
        expect(document, `${candidate.label} must not project`).toBeUndefined();
        expect(
          error instanceof ChildConfigProjectionError || error instanceof ChildBrokerAuthorityError,
          `${candidate.label} must fail closed`,
        ).toBe(true);
        expect(`${(error as Error).message}${(error as Error).stack ?? ""}`).not.toContain("OAUTHSECRET");
      } finally {
        await cleanup();
      }
    }

    // The well-formed equivalents still cross, so the shape pin is not a blanket refusal.
    const { document, error, cleanup } = await projectedModels({
      providers: {
        openai: {
          baseUrl: "https://gw.example.com/v1", authHeader: true,
          compat: { supportsDeveloperRole: true, sessionAffinityFormat: "openai" },
          models: [{ id: "gpt-test", reasoning: false, contextWindow: 128_000, input: ["text", "image"], thinkingLevelMap: { off: null, high: "high" }, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
          modelOverrides: { "gpt-test": { maxTokens: 2_048 } },
        },
      },
    });
    try {
      expect(error).toBeUndefined();
      expect(document).toBeDefined();
    } finally {
      await cleanup();
    }
  });

  test("keeps the models.json projection bounded and credential-blind by construction", async () => {
    await loadImplementation();
    const source = await readFile(new URL("../src/child-env.ts", import.meta.url), "utf8");
    expect(source).toContain("MAX_MODELS_FILE_BYTES");
    expect(source).toContain('open(join(agentDir, "models.json"), "r")');
    expect(source).toContain("PURE_ENV_REFERENCE");
    expect(source).toContain("ChildConfigProjectionError");
    expect(source).toContain("ChildBrokerAuthorityError");
    // No blanket copy of the operator document or of a foreign provider record.
    expect(source).not.toContain("Object.assign(projectedProviders, providers)");
    expect(source).not.toMatch(/statSync|lstatSync|readFileSync/u);
    expect(source).toContain("handle.truncate(0)");
  });

  test("rejects operator auth growth after stat without reading beyond the fixed cap", async () => {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-growing-auth-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    await mkdir(operatorAgent, { recursive: true });
    const readLengths: number[] = [];
    let opened = false;
    const prepared = await prepareChildEnvironment({
      platform: process.platform,
      parent: {
        ...process.env, HOME: operatorHome, USERPROFILE: operatorHome,
        PI_CODING_AGENT_DIR: operatorAgent, OPENAI_API_KEY: PLANTED_UPSTREAM_LITERAL,
      },
      provider: "openai",
    }, BROKER, {
      remove: async (target, options) => await rm(target, options),
    }, {
      open: async () => {
        opened = true;
        return {
          stat: async () => ({ isFile: () => true, size: 2 }),
          read: async (buffer, offset, length) => {
            readLengths.push(length);
            buffer.fill(0x78, offset, offset + length);
            return { bytesRead: length, buffer };
          },
          close: async () => undefined,
        };
      },
    });
    try {
      expect(opened).toBe(true);
      expect(readLengths.reduce((total, length) => total + length, 0)).toBe(1_048_577);
      await expect(readFile(join(prepared.env.PI_CODING_AGENT_DIR!, "auth.json"), "utf8")).rejects.toThrow();
    } finally {
      await prepared.cleanup();
      await rm(operatorHome, { recursive: true, force: true });
    }
  });
});
