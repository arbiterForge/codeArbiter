import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import type {
  BridgePort,
  BridgeRequest,
  BridgeResponse,
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
} from "../src/contracts.ts";
import { installParent } from "../src/extension.ts";
import { setArbiterStatus } from "../src/status.ts";

type Handler = (event: Record<string, unknown>, context: ExtensionContextPort) => unknown;

class StatusHost implements ParentPiPort {
  readonly handlers = new Map<string, Handler[]>();
  readonly calls: Array<{ key: string; text: string | undefined }> = [];
  private readonly registered = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
  lateCollision = false;

  constructor(private readonly packageRoot: string, private readonly catalog: CommandCatalogEntry[]) {}

  on(event: string, handler: Handler): void {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
  registerCommand(name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }): void {
    this.registered.set(name, options);
  }
  sendUserMessage(): void {}
  getCommands() {
    const sourceInfo = {
      path: resolve(this.packageRoot, "extensions", "codearbiter.js"),
      source: "fixture",
      scope: "user",
      origin: "package",
      baseDir: this.packageRoot,
    } as const;
    return [
      ...[...this.registered.keys()].flatMap((name) => this.lateCollision
        ? [
          { name: `${name}:1`, source: "extension" as const, sourceInfo },
          { name: `${name}:2`, source: "extension" as const, sourceInfo },
        ]
        : [{ name, source: "extension" as const, sourceInfo }]),
      ...this.catalog.map((entry) => ({
        name: `skill:ca-${entry.name}`,
        source: "skill" as const,
        sourceInfo: { ...sourceInfo, path: resolve(this.packageRoot, ...entry.skillPath.split("/")) },
      })),
    ];
  }
  context(cwd: string, projectTrusted = true): ExtensionContextPort {
    return {
      cwd,
      signal: undefined,
      isProjectTrusted: () => projectTrusted,
      ui: {
        notify: () => undefined,
        setStatus: (key, text) => this.calls.push({ key, text }),
      },
    };
  }
  async emit(event: string, context: ExtensionContextPort): Promise<void> {
    for (const handler of this.handlers.get(event) ?? []) await handler({ type: event }, context);
  }
  async invoke(name: string, args: string, context: ExtensionContextPort): Promise<void> {
    await this.registered.get(name)!.handler(args, context);
  }
  last(): string | undefined { return this.calls.at(-1)?.text; }
}

class StatusBridge implements BridgePort {
  async call(_request: BridgeRequest, _signal: AbortSignal): Promise<BridgeResponse> {
    return { version: 1, outcome: "notice", context: "host: pi" };
  }
}

const roots: string[] = [];

async function enabledProject(): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-status-"));
  roots.push(root);
  await mkdir(resolve(root, ".codearbiter"), { recursive: true });
  await writeFile(resolve(root, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
  return root;
}

async function bareProject(): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-status-bare-"));
  roots.push(root);
  return root;
}

async function preparePackage(root: string, catalog: CommandCatalogEntry[]): Promise<void> {
  await mkdir(resolve(root, "extensions"), { recursive: true });
  await mkdir(resolve(root, "skills"), { recursive: true });
  await writeFile(resolve(root, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
  await writeFile(resolve(root, "package.json"), JSON.stringify({
    name: "ca-pi",
    pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
  }) + "\n", "utf8");
  for (const entry of catalog) {
    const path = resolve(root, ...entry.skillPath.split("/"));
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, `---\nname: ca-${entry.name}\ndescription: ${entry.description}\n---\nbody\n`, "utf8");
  }
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("Pi keyed status lifecycle", () => {
  test("setArbiterStatus composes through only the codearbiter key", () => {
    const calls: Array<[string, string | undefined]> = [];
    setArbiterStatus({ ui: { setStatus: (key, text) => calls.push([key, text]), notify: () => undefined } }, "working");
    expect(calls).toEqual([["codearbiter", "working"]]);
  });

  test("retains status through end, retry, and compaction and clears only when settled", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    await host.emit("agent_start", context);
    const active = host.last();
    expect(active).toContain("host: pi");
    await host.emit("agent_end", context);
    expect(host.last()).toBe(active);
    await host.emit("session_before_compact", context);
    await host.emit("session_compact", context);
    await host.emit("agent_start", context);
    expect(host.last()).toBe(active);
    await host.emit("agent_settled", context);
    expect(host.last()).toBeUndefined();
    expect(new Set(host.calls.map((call) => call.key))).toEqual(new Set(["codearbiter"]));
  });

  test("session shutdown is the only non-settled lifecycle clear", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    expect(host.last()).toBeDefined();
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });

  test("a never-published dormant lifecycle remains status-silent through shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    await host.emit("session_shutdown", context);
    expect(host.calls).toEqual([]);
  });

  test("failed activation clears its unhealthy status on a dormant start and on shutdown", async () => {
    const enabled = await enabledProject();
    const dormant = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let attempts = 0;
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      installEnforcement: () => {
        attempts += 1;
        throw new Error("fixture install failure");
      },
    });

    const failedContext = host.context(enabled);
    await expect(host.emit("session_start", failedContext)).rejects.toThrow("/ca-doctor");
    expect(host.last()).toContain("unhealthy");
    const callCount = host.calls.length;
    await host.emit("session_start", host.context(dormant));
    expect(host.calls).toHaveLength(callCount + 1);
    expect(host.calls.at(-1)).toEqual({ key: "codearbiter", text: undefined });

    await expect(host.emit("session_start", failedContext)).rejects.toThrow("/ca-doctor");
    expect(host.last()).toContain("unhealthy");
    await host.emit("session_shutdown", failedContext);
    expect(host.calls.at(-1)).toEqual({ key: "codearbiter", text: undefined });
    expect(attempts).toBe(2);
  });

  test("agent work and settling never erase a persistent command-ownership degradation", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    const baseline = host.last();
    expect(baseline).toContain("command ownership conflict");
    await host.emit("agent_start", context);
    expect(host.last()).toBe(baseline);
    await host.emit("agent_settled", context);
    expect(host.last()).toBe(baseline);
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });

  test("a late alias collision becomes the persistent baseline through agent_settled", async () => {
    const cwd = await enabledProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    host.lateCollision = true;
    await host.invoke("ca-feature", "args", context);
    const baseline = host.last();
    expect(baseline).toContain("command surface");
    await host.emit("agent_settled", context);
    expect(host.last()).toBe(baseline);
  });

  test("an explicit alias degradation in a bare repo clears on session shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    expect(host.calls).toEqual([]);
    host.lateCollision = true;
    await host.invoke("ca-feature", "args", context);
    expect(host.last()).toContain("command surface");
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });
});
