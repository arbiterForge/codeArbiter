/** child-env.test.ts - Task 6 minimal environment and help-contract obligations. */
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
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
  test("starts from a minimal selected-provider Windows environment", async () => {
    const { buildChildEnv } = await loadImplementation();
    const child = buildChildEnv({ platform: "win32", parent, provider: "openai", isolationRoot: join("fixture", "windows-openai") });
    expect(child.OPENAI_API_KEY).toBe(parent.OPENAI_API_KEY);
    expect(child.ANTHROPIC_API_KEY).toBeUndefined();
    expect(child.ANTHROPIC_OAUTH_TOKEN).toBeUndefined();
    expect(child.UNRELATED_SECRET).toBeUndefined();
    expect(child.CODEARBITER_SUBAGENT).toBe("1");
    expect(child.PI_OFFLINE).toBe("1");
    expect(child.PI_TELEMETRY).toBe("0");
  });

  test("rebinds every operator storage path beneath the isolated child root", async () => {
    const { buildChildEnv } = await loadImplementation();
    const isolationRoot = join("fixture", "isolated-child");
    const child = buildChildEnv({
      platform: "win32",
      parent,
      provider: "openai",
      isolationRoot,
    } as never);

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
    });
    expect(inherited.PI_PACKAGE_DIR).toBe("C:\\nix\\store\\pi-coding-agent");

    // With no operator override, Pi must fall back to its own __dirname walk-up: the child
    // env must not name a package dir at all rather than invent an empty one.
    const resolved = buildChildEnv({ platform: "win32", parent, provider: "openai", isolationRoot });
    expect(resolved.PI_PACKAGE_DIR).toBeUndefined();
    expect(Object.values(resolved)).not.toContain(join(isolationRoot, "packages"));
  });

  test("removes unrelated codeArbiter credentials after every environment merge", async () => {
    const { buildChildEnv } = await loadImplementation();
    for (const provider of ["openai", "anthropic", "amazon-bedrock"] as const) {
      const child = buildChildEnv({ platform: "win32", parent, provider, isolationRoot: join("fixture", provider) });
      expect(child.FARM_API_KEY).toBeUndefined();
      expect(child.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined();
    }
  });

  test("admits only the selected provider group", async () => {
    const { buildChildEnv } = await loadImplementation();
    const anthropic = buildChildEnv({ platform: "win32", parent, provider: "anthropic", isolationRoot: join("fixture", "anthropic") });
    expect(anthropic.ANTHROPIC_API_KEY).toBe(parent.ANTHROPIC_API_KEY);
    expect(anthropic.ANTHROPIC_OAUTH_TOKEN).toBe(parent.ANTHROPIC_OAUTH_TOKEN);
    expect(anthropic.OPENAI_API_KEY).toBeUndefined();
    expect(anthropic.AWS_ACCESS_KEY_ID).toBeUndefined();
  });

  test("uses explicit POSIX baselines and rejects unknown platforms or providers", async () => {
    const { buildChildEnv } = await loadImplementation();
    const posixParent = { HOME: "/home/fixture", USER: "fixture", PATH: "/usr/bin", TMPDIR: "/tmp", OPENAI_API_KEY: "dummy" };
    const linuxRoot = join("fixture", "linux");
    const darwinRoot = join("fixture", "darwin");
    for (const [platform, root] of [["linux", linuxRoot], ["darwin", darwinRoot]] as const) {
      expect(buildChildEnv({ platform, parent: posixParent, provider: "openai", isolationRoot: root })).toMatchObject({
        HOME: join(root, "home"),
        USER: "fixture",
        XDG_CONFIG_HOME: join(root, "home", ".config"),
        XDG_CACHE_HOME: join(root, "home", ".cache"),
        XDG_DATA_HOME: join(root, "home", ".local", "share"),
        PI_CODING_AGENT_DIR: join(root, "agent"),
        PI_CODING_AGENT_SESSION_DIR: join(root, "sessions"),
      });
      expect(buildChildEnv({ platform, parent: posixParent, provider: "openai", isolationRoot: root }).PI_PACKAGE_DIR).toBeUndefined();
    }
    expect(() => buildChildEnv({ platform: "aix" as NodeJS.Platform, parent, provider: "openai", isolationRoot: join("fixture", "aix") })).toThrow("Unsupported child platform");
    expect(() => buildChildEnv({ platform: "win32", parent, provider: "fixture-unknown", isolationRoot: join("fixture", "unknown") })).toThrow("Unsupported Pi provider");
  });

  test("scrubs the retained credential handle when path removal fails", async () => {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-operator-auth-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    const externalSentinel = join(operatorHome, "external-sentinel.txt");
    const operatorAuth = {
      openai: { type: "api_key", key: "selected-file-secret" },
      anthropic: { type: "api_key", key: "foreign-file-secret" },
    };
    await mkdir(operatorAgent, { recursive: true });
    await writeFile(join(operatorAgent, "auth.json"), JSON.stringify(operatorAuth), "utf8");
    await writeFile(externalSentinel, "external-must-survive", "utf8");
    let isolationRoot: string | undefined;
    try {
      const prepared = await prepareChildEnvironment({
        platform: process.platform,
        parent: { ...process.env, HOME: operatorHome, USERPROFILE: operatorHome, PI_CODING_AGENT_DIR: operatorAgent },
        provider: "openai",
      }, {
        remove: async () => { throw new Error("simulated removal refusal"); },
      });
      isolationRoot = dirname(prepared.env.HOME!);
      const childAuthPath = join(prepared.env.PI_CODING_AGENT_DIR!, "auth.json");
      expect(JSON.parse(await readFile(childAuthPath, "utf8"))).toEqual({ openai: operatorAuth.openai });
      if (process.platform !== "win32") {
        await rm(childAuthPath);
        await symlink(externalSentinel, childAuthPath, "file");
      }

      await expect(prepared.cleanup()).rejects.toThrow("Pi child credential cleanup failed safely");

      if (process.platform === "win32") expect(await readFile(childAuthPath, "utf8")).toBe("");
      expect(await readFile(externalSentinel, "utf8")).toBe("external-must-survive");
      expect(JSON.parse(await readFile(join(operatorAgent, "auth.json"), "utf8"))).toEqual(operatorAuth);
    } finally {
      if (isolationRoot !== undefined) await rm(isolationRoot, { recursive: true, force: true });
      await rm(operatorHome, { recursive: true, force: true });
    }
  });

  test("reports degraded cleanup when a replacement credential file cannot be removed", async () => {
    const { prepareChildEnvironment } = await loadImplementation();
    const operatorHome = await mkdtemp(join(tmpdir(), "ca-pi-replaced-auth-"));
    const operatorAgent = join(operatorHome, ".pi", "agent");
    const operatorAuth = { openai: { type: "api_key", key: "selected-file-secret" } };
    await mkdir(operatorAgent, { recursive: true });
    await writeFile(join(operatorAgent, "auth.json"), JSON.stringify(operatorAuth), "utf8");
    let isolationRoot: string | undefined;
    try {
      const prepared = await prepareChildEnvironment({
        platform: process.platform,
        parent: { ...process.env, HOME: operatorHome, USERPROFILE: operatorHome, PI_CODING_AGENT_DIR: operatorAgent },
        provider: "openai",
      }, {
        remove: async () => { throw new Error("simulated removal refusal"); },
      });
      isolationRoot = dirname(prepared.env.HOME!);
      const childAuthPath = join(prepared.env.PI_CODING_AGENT_DIR!, "auth.json");
      await rm(childAuthPath);
      await writeFile(childAuthPath, JSON.stringify({ openai: { type: "api_key", key: "replacement-secret" } }), "utf8");

      await expect(prepared.cleanup()).rejects.toThrow("Pi child credential cleanup failed safely");
      expect(await readFile(childAuthPath, "utf8")).toContain("replacement-secret");
      expect(JSON.parse(await readFile(join(operatorAgent, "auth.json"), "utf8"))).toEqual(operatorAuth);
    } finally {
      if (isolationRoot !== undefined) await rm(isolationRoot, { recursive: true, force: true });
      await rm(operatorHome, { recursive: true, force: true });
    }
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

  test("keeps stored-auth projection bounded, async, and selected-provider-only", async () => {
    await loadImplementation();
    const source = await readFile(new URL("../src/child-env.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/statSync|lstatSync|readFileSync/u);
    expect(source).toContain("MAX_AUTH_FILE_BYTES");
    expect(source).toContain('open(join(agentDir, "auth.json"), "r")');
    expect(source).toContain("hasOwnProperty.call(record, input.provider)");
    expect(source).not.toContain("Object.assign(projected, record)");
    expect(source).not.toContain('writeFile(authPath, "{}');
    expect(source).toContain("handle.truncate(0)");
  });

  // ADR-0017 — credential-blind selected-provider CONFIGURATION projection. Pi binds
  // models.json to getAgentDir() with no separate env override, so ADR-0016's private agent
  // dir silently strips every operator endpoint/protocol/model and the child resolves the
  // provider from Pi's BUILT-IN catalog — sending the operator's key to an endpoint they
  // never configured. The amendment permits configuration, never credentials.
  const OPERATOR_MODELS = {
    providers: {
      openai: {
        baseUrl: "http://127.0.0.1:8931/v1",
        api: "openai-completions",
        apiKey: "$OPENAI_API_KEY",
        authHeader: true,
        compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
        headers: { "X-Ca-Gateway": "${CA_PI_GATEWAY_TOKEN}" },
        models: [{
          id: "gpt-test", name: "fixture", reasoning: false, input: ["text"],
          contextWindow: 128_000, maxTokens: 4_096,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        }],
        modelOverrides: { "gpt-test": { maxTokens: 2_048 } },
      },
      anthropic: {
        baseUrl: "https://foreign.example/v1",
        apiKey: "sk-foreign-literal-operator-secret",
        headers: { "X-Foreign": "foreign-literal-header-secret" },
      },
    },
  };

  async function projectedModels(models: unknown, provider = "openai"): Promise<{
    document?: unknown;
    error?: unknown;
    operatorAgent: string;
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
        parent: { ...process.env, HOME: operatorHome, USERPROFILE: operatorHome, PI_CODING_AGENT_DIR: operatorAgent },
        provider,
      });
      isolationRoot = dirname(prepared.env.HOME!);
      const childModels = join(prepared.env.PI_CODING_AGENT_DIR!, "models.json");
      const document = await readFile(childModels, "utf8").then(
        (text) => JSON.parse(text) as unknown,
        () => undefined,
      );
      await prepared.cleanup().catch(() => undefined);
      return { document, operatorAgent, cleanup };
    } catch (error) {
      return { error, operatorAgent, cleanup };
    }
  }

  test("projects only the selected provider's credential-blind models.json configuration", async () => {
    const { document, operatorAgent, cleanup } = await projectedModels(OPERATOR_MODELS);
    try {
      expect(document).toEqual({ providers: { openai: OPERATOR_MODELS.providers.openai } });
      // The second operator provider record exists in the store and must be absent from the
      // child entirely — record, endpoint, literal key, and literal header alike.
      const serialized = JSON.stringify(document);
      expect(serialized).not.toContain("anthropic");
      expect(serialized).not.toContain("foreign.example");
      expect(serialized).not.toContain("sk-foreign-literal-operator-secret");
      expect(serialized).not.toContain("foreign-literal-header-secret");
      // The operator's own store is never mutated.
      expect(JSON.parse(await readFile(join(operatorAgent, "models.json"), "utf8"))).toEqual(OPERATOR_MODELS);
    } finally {
      await cleanup();
    }
  });

  test("fails closed on a literal apiKey, a !command apiKey, or a literal header value", async () => {
    const { ChildConfigProjectionError } = await loadImplementation();
    const rejected = [
      { label: "literal apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "sk-literal-operator-secret" } },
      { label: "!command apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "!op read op://vault/openai" } },
      { label: "literal provider header", record: { baseUrl: "https://x.example/v1", headers: { "X-Key": "literal-header-secret" } } },
      { label: "!command provider header", record: { baseUrl: "https://x.example/v1", headers: { "X-Key": "!cat /run/secret" } } },
      { label: "literal model header", record: { baseUrl: "https://x.example/v1", models: [{ id: "gpt-test", headers: { "X-Key": "literal-model-secret" } }] } },
      { label: "literal modelOverrides header", record: { baseUrl: "https://x.example/v1", modelOverrides: { "gpt-test": { headers: { "X-Key": "literal-override-secret" } } } } },
      { label: "partial template apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "sk-prefix-$OPENAI_API_KEY" } },
      { label: "escaped-literal apiKey", record: { baseUrl: "https://x.example/v1", apiKey: "$$OPENAI_API_KEY" } },
      { label: "unreviewed provider key", record: { baseUrl: "https://x.example/v1", credentialFile: "/home/operator/.secrets/openai" } },
      // An endpoint may carry credentials in its userinfo — that is credential material wearing
      // an endpoint's clothes, so it is not "structural" and must not cross.
      { label: "userinfo baseUrl", record: { baseUrl: "https://operator:pw-in-url@gateway.example/v1" } },
      { label: "userinfo model baseUrl", record: { baseUrl: "https://x.example/v1", models: [{ id: "gpt-test", baseUrl: "https://operator:pw-in-url@gateway.example/v1" }] } },
      { label: "unparseable baseUrl", record: { baseUrl: "gateway.example/v1" } },
      { label: "unparseable operator store", record: undefined, raw: "{ not json" },
    ] as const;

    for (const candidate of rejected) {
      const models = "raw" in candidate && candidate.raw !== undefined
        ? candidate.raw
        : { providers: { openai: candidate.record } };
      const { document, error, cleanup } = await projectedModels(models);
      try {
        expect(document, `${candidate.label} must not project a child models.json`).toBeUndefined();
        expect(error, `${candidate.label} must fail closed`).toBeInstanceOf(ChildConfigProjectionError);
        // The bounded diagnostic never carries a value, a secret, or an operator path.
        const message = `${(error as Error).message}${(error as Error).stack ?? ""}`;
        for (const leak of ["literal", "secret", "!op ", "vault", "/run/secret", ".secrets", "$OPENAI_API_KEY", "x.example", "gateway.example", "pw-in-url"]) {
          expect(message, `${candidate.label} leaked ${leak}`).not.toContain(leak);
        }
      } finally {
        await cleanup();
      }
    }
  });

  test("leaves the child without models.json when the operator configures nothing to project", async () => {
    for (const models of [
      undefined,
      { providers: {} },
      { providers: { anthropic: { baseUrl: "https://foreign.example/v1", apiKey: "sk-foreign-literal" } } },
    ]) {
      const { document, error, cleanup } = await projectedModels(models);
      try {
        expect(error).toBeUndefined();
        expect(document).toBeUndefined();
      } finally {
        await cleanup();
      }
    }
  });

  test("keeps the models.json projection bounded and credential-blind by construction", async () => {
    await loadImplementation();
    const source = await readFile(new URL("../src/child-env.ts", import.meta.url), "utf8");
    expect(source).toContain("MAX_MODELS_FILE_BYTES");
    expect(source).toContain('open(join(agentDir, "models.json"), "r")');
    expect(source).toContain("PURE_ENV_REFERENCE");
    expect(source).toContain("ChildConfigProjectionError");
    // No blanket copy of the operator document or of a foreign provider record.
    expect(source).not.toContain("Object.assign(projectedProviders, providers)");
    expect(source).not.toMatch(/statSync|lstatSync|readFileSync/u);
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
      parent: { ...process.env, HOME: operatorHome, USERPROFILE: operatorHome, PI_CODING_AGENT_DIR: operatorAgent },
      provider: "openai",
    }, {
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
