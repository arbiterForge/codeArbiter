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
    expect(child.PI_PACKAGE_DIR).toBe(join(isolationRoot, "packages"));
    expect(Object.values(child)).not.toContain(parent.HOME);
    expect(Object.values(child)).not.toContain(parent.PI_CODING_AGENT_DIR);
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
        PI_PACKAGE_DIR: join(root, "packages"),
      });
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
