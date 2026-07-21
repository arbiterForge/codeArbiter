/** child-env.test.ts - Task 6 minimal environment and help-contract obligations. */
import { readFile } from "node:fs/promises";
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
    const child = buildChildEnv({ platform: "win32", parent, provider: "openai" });
    expect(child.OPENAI_API_KEY).toBe(parent.OPENAI_API_KEY);
    expect(child.ANTHROPIC_API_KEY).toBeUndefined();
    expect(child.ANTHROPIC_OAUTH_TOKEN).toBeUndefined();
    expect(child.UNRELATED_SECRET).toBeUndefined();
    expect(child.CODEARBITER_SUBAGENT).toBe("1");
    expect(child.PI_OFFLINE).toBe("1");
    expect(child.PI_TELEMETRY).toBe("0");
  });

  test("removes unrelated codeArbiter credentials after every environment merge", async () => {
    const { buildChildEnv } = await loadImplementation();
    for (const provider of ["openai", "anthropic", "amazon-bedrock"] as const) {
      const child = buildChildEnv({ platform: "win32", parent, provider });
      expect(child.FARM_API_KEY).toBeUndefined();
      expect(child.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined();
    }
  });

  test("admits only the selected provider group", async () => {
    const { buildChildEnv } = await loadImplementation();
    const anthropic = buildChildEnv({ platform: "win32", parent, provider: "anthropic" });
    expect(anthropic.ANTHROPIC_API_KEY).toBe(parent.ANTHROPIC_API_KEY);
    expect(anthropic.ANTHROPIC_OAUTH_TOKEN).toBe(parent.ANTHROPIC_OAUTH_TOKEN);
    expect(anthropic.OPENAI_API_KEY).toBeUndefined();
    expect(anthropic.AWS_ACCESS_KEY_ID).toBeUndefined();
  });

  test("uses explicit POSIX baselines and rejects unknown platforms or providers", async () => {
    const { buildChildEnv } = await loadImplementation();
    const posixParent = { HOME: "/home/fixture", USER: "fixture", PATH: "/usr/bin", TMPDIR: "/tmp", OPENAI_API_KEY: "dummy" };
    expect(buildChildEnv({ platform: "linux", parent: posixParent, provider: "openai" })).toMatchObject({ HOME: "/home/fixture", USER: "fixture" });
    expect(buildChildEnv({ platform: "darwin", parent: posixParent, provider: "openai" })).toMatchObject({ HOME: "/home/fixture", USER: "fixture" });
    expect(() => buildChildEnv({ platform: "aix" as NodeJS.Platform, parent, provider: "openai" })).toThrow("Unsupported child platform");
    expect(() => buildChildEnv({ platform: "win32", parent, provider: "fixture-unknown" })).toThrow("Unsupported Pi provider");
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

  test("contains no Task 6 auth-store file inspection", async () => {
    await loadImplementation();
    const source = await readFile(new URL("../src/child-env.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/auth\.json|credentials(?:\W|$)|statSync|lstatSync|readFileSync|readFile\s*\(/u);
  });
});
