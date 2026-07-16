/** Task 8 Pi-native semantic compaction contracts. */
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { describe, expect, test, vi } from "vitest";

import {
  createPiCompactionRunner,
  handleAfterCompact,
  handleBeforeCompact,
  installPiCompaction,
  piSemanticEntries,
  type CompactionRunner,
  type PiCompactionEvent,
} from "../src/compaction.ts";
import { childAttestationDigest } from "../src/attestation.ts";
import { installChild } from "../src/child-extension.ts";
import { buildChildArgv, validateChildLaunch } from "../src/runner.ts";

function branchEntries(): Array<Record<string, any>> {
  return [
    { type: "message", id: "u0", parentId: null, timestamp: "2026-07-16T00:00:00Z", message: { role: "user", content: [{ type: "text", text: "OPENAI_API_KEY=synthetic-secret" }], timestamp: 1 } },
    { type: "message", id: "a0", parentId: "u0", timestamp: "2026-07-16T00:00:01Z", message: { role: "assistant", content: [{ type: "toolCall", id: "t0", name: "read", arguments: {} }], provider: "openai", model: "gpt-test", timestamp: 2 } },
    { type: "message", id: "r0", parentId: "a0", timestamp: "2026-07-16T00:00:02Z", message: { role: "toolResult", toolCallId: "t0", toolName: "read", content: [{ type: "text", text: "old output" }], isError: false, timestamp: 3 } },
    { type: "message", id: "u1", parentId: "r0", timestamp: "2026-07-16T00:00:03Z", message: { role: "user", content: [{ type: "text", text: "continue" }], timestamp: 4 } },
    { type: "message", id: "a1", parentId: "u1", timestamp: "2026-07-16T00:00:04Z", message: { role: "assistant", content: [{ type: "text", text: "kept" }], provider: "openai", model: "gpt-test", timestamp: 5 } },
  ];
}

function event(entries = branchEntries()): PiCompactionEvent {
  return {
    branchEntries: entries,
    preparation: { firstKeptEntryId: "u1", tokensBefore: 12_345, previousSummary: "prior" },
    customInstructions: "focus on decisions",
    reason: "threshold",
    willRetry: false,
    signal: new AbortController().signal,
  };
}

function runner(): CompactionRunner {
  return {
    plan: vi.fn(async () => ({
      firstKeptEntryId: "u1",
      protectedIds: ["u1", "a1"],
      actions: [{ entryId: "u0", action: "summarize" }],
      metrics: { entriesBefore: 5, candidateEntries: 3, bytesBefore: 1_000 },
      auditCodes: ["CA-PRUNE-PLAN"],
      fingerprint: "plan-123",
    })),
    summarize: vi.fn(async () => `summary\nOPENAI_API_KEY=synthetic-secret\n${"🙂".repeat(20_000)}`),
  };
}

describe("Task 8 Pi compaction", () => {
  test("maps Pi entries semantically without retaining mutable session objects", () => {
    const original = branchEntries();
    const semantic = piSemanticEntries(original);
    expect(semantic.map((entry) => [entry.id, entry.role, entry.toolBearing])).toEqual([
      ["u0", "user", false], ["a0", "assistant", true], ["r0", "tool", false],
      ["u1", "user", false], ["a1", "assistant", false],
    ]);
    original[0]!.message.content[0]!.text = "mutated";
    expect(JSON.stringify(semantic)).not.toContain("mutated");
    expect(() => piSemanticEntries([{ ...original[0], id: "duplicate" }, { ...original[1], id: "duplicate" }])).toThrow(/entry|duplicate/u);
    expect(() => piSemanticEntries([{ ...original[0], id: "bad\ncontrol" }])).toThrow(/entry|id/u);
  });

  test("returns a policy-selected native result through an exact no-tool summarizer", async () => {
    const activeWrites = { writeFile: vi.fn(), appendFile: vi.fn(), persist: vi.fn() };
    const child = runner();
    const result = await handleBeforeCompact(event(), {
      cwd: resolve("C:/repo"),
      packageRoot: resolve("C:/package"),
      model: { provider: "openai", id: "gpt-test" },
      sessionManager: activeWrites,
    }, child);

    expect(result).toMatchObject({ firstKeptEntryId: "u1", tokensBefore: 12_345 });
    expect(Buffer.byteLength(result!.summary, "utf8")).toBeLessThanOrEqual(16_000);
    expect(result!.summary).not.toContain("synthetic-secret");
    expect(activeWrites.writeFile).not.toHaveBeenCalled();
    expect(activeWrites.appendFile).not.toHaveBeenCalled();
    expect(activeWrites.persist).not.toHaveBeenCalled();
    expect(child.summarize).toHaveBeenCalledWith(expect.objectContaining({
      provider: "openai",
      model: "gpt-test",
      tools: [],
      charterPath: resolve("C:/package", "includes", "compaction-charter.md"),
    }), expect.any(AbortSignal));
    const input = vi.mocked(child.summarize).mock.calls[0]![0];
    expect(input.conversation).not.toContain("synthetic-secret");
    expect(input.conversation).toContain("old output");
    expect(Buffer.byteLength(input.conversation, "utf8")).toBeLessThanOrEqual(65_536);
  });

  test("fails closed on absent identity, invalid boundaries, runner degradation, or cancellation", async () => {
    const baseContext = { cwd: resolve("C:/repo"), packageRoot: resolve("C:/package"), model: { provider: "openai", id: "gpt-test" } };
    await expect(handleBeforeCompact(event(), { ...baseContext, model: undefined }, runner())).rejects.toThrow(/provider|model/u);
    const invalidPlan = runner();
    vi.mocked(invalidPlan.plan).mockResolvedValue({
      firstKeptEntryId: "missing", protectedIds: [], actions: [], metrics: { entriesBefore: 5, candidateEntries: 5, bytesBefore: 10 }, auditCodes: [], fingerprint: "bad",
    });
    await expect(handleBeforeCompact(event(), baseContext, invalidPlan)).rejects.toThrow(/boundary/u);
    const nonContiguous = runner();
    vi.mocked(nonContiguous.plan).mockResolvedValue({
      firstKeptEntryId: "u1", protectedIds: ["a1", "u0"], actions: [{ entryId: "u0", action: "retain" }],
      metrics: { entriesBefore: 5, candidateEntries: 3, bytesBefore: 10 }, auditCodes: ["CA-PRUNE-PLAN"], fingerprint: "bad-tail",
    });
    await expect(handleBeforeCompact(event(), baseContext, nonContiguous)).rejects.toThrow(/boundary/u);
    const controlBearing = runner();
    vi.mocked(controlBearing.plan).mockResolvedValue({
      firstKeptEntryId: "u1", protectedIds: ["u1", "a1"], actions: [],
      metrics: { entriesBefore: 5, candidateEntries: 3, "OPENAI_API_KEY=synthetic-secret\n": 1 },
      auditCodes: ["CA-PRUNE-PLAN"], fingerprint: "unsafe-metrics",
    });
    await expect(handleBeforeCompact(event(), baseContext, controlBearing)).rejects.toThrow(/invalid kept boundary/u);
    const degraded = runner();
    vi.mocked(degraded.summarize).mockRejectedValue(new Error("raw secret detail"));
    await expect(handleBeforeCompact(event(), baseContext, degraded)).rejects.toThrow("Pi native compaction failed safely; run /ca-doctor.");
    const controller = new AbortController();
    controller.abort();
    await expect(handleBeforeCompact({ ...event(), signal: controller.signal }, baseContext, runner())).rejects.toThrow(/cancel/u);
  });

  test("never splits a UTF-8 scalar at the summary byte boundary", async () => {
    const child = runner();
    vi.mocked(child.summarize).mockResolvedValue(`aa${"🙂".repeat(20_000)}`);
    const result = await handleBeforeCompact(event(), {
      cwd: resolve("C:/repo"), packageRoot: resolve("C:/package"), model: { provider: "openai", id: "gpt-test" },
    }, child);
    expect(Buffer.byteLength(result!.summary, "utf8")).toBeLessThanOrEqual(16_000);
    expect(result!.summary).not.toContain("�");
  });

  test("does not launch a summarizer when policy selects no candidates", async () => {
    const child = runner();
    vi.mocked(child.plan).mockResolvedValue({
      firstKeptEntryId: "u0", protectedIds: ["u0", "a0", "r0", "u1", "a1"], actions: [],
      metrics: { entriesBefore: 5, candidateEntries: 0 }, auditCodes: ["CA-PRUNE-NOOP"], fingerprint: "noop-plan",
    });
    expect(await handleBeforeCompact(event(), {
      cwd: resolve("C:/repo"), packageRoot: resolve("C:/package"), model: { provider: "openai", id: "gpt-test" },
    }, child)).toBeUndefined();
    expect(child.summarize).not.toHaveBeenCalled();
  });

  test("is idempotent for an already-confirmed identical plan and audits only after confirmation", async () => {
    const entries = [...branchEntries(), {
      type: "compaction", id: "c1", parentId: "a1", timestamp: "2026-07-16T00:00:05Z",
      summary: "summary", firstKeptEntryId: "u1", tokensBefore: 12_345,
      details: { codearbiter: { version: 1, planFingerprint: "plan-123", auditCodes: ["CA-PRUNE-PLAN"], metrics: { candidateEntries: 3 } } },
      fromHook: true,
    }];
    const child = runner();
    expect(await handleBeforeCompact(event(entries), {
      cwd: resolve("C:/repo"), packageRoot: resolve("C:/package"), model: { provider: "openai", id: "gpt-test" },
    }, child)).toBeUndefined();
    expect(child.plan).not.toHaveBeenCalled();
    expect(child.summarize).not.toHaveBeenCalled();

    const audit = { record: vi.fn(async () => undefined) };
    await handleAfterCompact({ compactionEntry: entries.at(-1)!, fromExtension: true, reason: "threshold", willRetry: false }, audit);
    expect(audit.record).toHaveBeenCalledWith({
      auditCodes: ["CA-PRUNE-PLAN"], metrics: { candidateEntries: 3 }, planFingerprint: "plan-123",
    });
    expect(audit.record).toHaveBeenCalledOnce();
    await handleAfterCompact({
      compactionEntry: {
        ...entries.at(-1)!,
        details: { codearbiter: { version: 1, planFingerprint: "OPENAI_API_KEY=synthetic-secret\n", auditCodes: ["CA-PRUNE-PLAN"], metrics: { candidateEntries: 3 } } },
      },
      fromExtension: true, reason: "threshold", willRetry: false,
    }, audit);
    expect(audit.record).toHaveBeenCalledOnce();
  });
});

describe("Task 8 hardened runner seam (RED until Task 7 is stable)", () => {
  const common = {
    nodePath: resolve("C:/runtime/node.exe"),
    piCliPath: resolve("C:/runtime/pi.js"),
    provider: "openai",
    model: "gpt-test",
    cwd: resolve("C:/repo"),
    childExtensionPath: resolve("C:/package/extensions/codearbiter-child.js"),
  };

  test("discriminates one exact packaged no-tool compaction launch from ordinary roles", () => {
    const compaction = {
      ...common,
      launchKind: "internal-compaction",
      tools: [] as const,
      skillPaths: [] as const,
      charterPath: resolve("C:/package/includes/compaction-charter.md"),
    };
    const argv = buildChildArgv(compaction as never);
    expect(argv).toContain("--no-tools");
    expect(argv).not.toContain("--tools");
    expect(argv).not.toContain("--skill");
    expect(argv).toContain(compaction.charterPath);

    expect(() => buildChildArgv({ ...compaction, tools: ["read"] } as never)).toThrow(/no tools|compaction/u);
    expect(() => buildChildArgv({ ...compaction, skillPaths: [resolve("C:/package/routines/tdd/SKILL.md")] } as never)).toThrow(/no skills|compaction/u);
    expect(() => buildChildArgv({ ...compaction, charterPath: resolve("C:/package/agents/backend-author.md") } as never)).toThrow(/compaction charter|resource/u);
    expect(() => buildChildArgv({
      ...common,
      launchKind: "role",
      tools: [],
      skillPaths: [resolve("C:/package/routines/tdd/SKILL.md")],
      charterPath: resolve("C:/package/agents/backend-author.md"),
    } as never)).toThrow(/nonempty|allowlist|role tools/u);
  });

  test("canonical validation admits only the installed internal compaction charter", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-compaction-launch-"));
    try {
      const packageRoot = resolve(import.meta.dirname, "..", "..");
      const piRoot = resolve(root, "pi-runtime");
      const piCliPath = resolve(piRoot, "dist", "cli.js");
      const cwd = resolve(root, "repo");
      await mkdir(resolve(piRoot, "dist"), { recursive: true });
      await mkdir(cwd, { recursive: true });
      await writeFile(piCliPath, "// Pi fixture\n", "utf8");
      await writeFile(resolve(piRoot, "package.json"), '{"name":"@earendil-works/pi-coding-agent","version":"0.80.6"}\n', "utf8");
      const request = {
        launchKind: "internal-compaction",
        nodePath: process.execPath,
        piCliPath,
        provider: "openai",
        model: "gpt-test",
        tools: [] as const,
        cwd,
        childExtensionPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
        skillPaths: [] as const,
        charterPath: resolve(packageRoot, "includes", "compaction-charter.md"),
      };
      const dependencies = {
        activeNodePath: process.execPath,
        packageRoot,
        resolveRuntimeIdentity: async () => ({ cliEntry: piCliPath, packageRoot: piRoot, version: "0.80.6" }),
      };
      await expect(validateChildLaunch(request as never, dependencies)).resolves.toMatchObject({
        launchKind: "internal-compaction", tools: [], skillPaths: [], charterPath: request.charterPath,
      });
      await expect(validateChildLaunch({
        ...request,
        charterPath: resolve(packageRoot, "includes", "reference-map.md"),
      } as never, dependencies)).rejects.toThrow(/compaction charter|resource/u);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("attests the private no-tool compaction child without weakening role allowlists", async () => {
    const handlers = new Map<string, Array<(event: Record<string, unknown>, context: Record<string, any>) => unknown>>();
    const commands = new Map<string, (args: string, context: Record<string, any>) => unknown>();
    const definitions = new Map<string, Record<string, unknown>>();
    const pi = {
      on(name: string, handler: (event: Record<string, unknown>, context: Record<string, any>) => unknown) {
        handlers.set(name, [...(handlers.get(name) ?? []), handler]);
      },
      registerCommand(name: string, options: { handler: (args: string, context: Record<string, any>) => unknown }) {
        commands.set(name, options.handler);
      },
      registerTool(tool: Record<string, unknown> & { name: string }) { definitions.set(tool.name, tool); },
      getActiveTools: () => [] as string[],
      getAllTools: () => [...definitions.keys()].map((name) => ({ name, sourceInfo: { path: "C:/package/extensions/codearbiter-child.js" } })),
    };
    const nonce = "0123456789abcdef0123456789abcdef";
    const challenge = "fedcba9876543210fedcba9876543210";
    const factories = Object.fromEntries(["read", "bash", "edit", "write"].map((name) => [name, () => ({
      name, execute: async () => ({ content: [] }),
    })]));
    installChild(pi as never, {
      marker: "1", expectedNonce: nonce, cwd: "C:/repo", wrapperSourcePath: "C:/package/extensions/codearbiter-child.js",
      descriptor: { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" },
      bridge: { call: async () => ({ version: 1, outcome: "allow" }) }, factories,
    } as never);
    for (const handler of handlers.get("session_start") ?? []) {
      await handler({}, { cwd: "C:/repo", signal: new AbortController().signal, ui: { notify() {}, setStatus() {} } });
    }
    const confirm = vi.fn(async () => true);
    await commands.get("codearbiter-internal-child-handshake")!(`${nonce} ${challenge}`, {
      cwd: "C:/repo", mode: "rpc", hasUI: true,
      model: { provider: "openai", id: "gpt-test" }, isProjectTrusted: () => false,
      signal: new AbortController().signal, ui: { confirm, notify() {}, setStatus() {} },
    });
    expect(confirm).toHaveBeenCalledWith(
      "codeArbiter isolated child readiness",
      childAttestationDigest({ nonce, challenge, cwd: "C:/repo", provider: "openai", model: "gpt-test", tools: [], projectTrusted: false, mode: "rpc" }),
      { timeout: 5_000 },
    );
  });
});

describe("Task 8 Pi compaction lifecycle integration", () => {
  test("gets policy only through the bridge and summarizes through one exact internal child", async () => {
    const bridge = { call: vi.fn(async () => ({
      version: 1 as const, outcome: "notice" as const,
      resultPatch: { prunePlan: {
        firstKeptEntryId: "u1", protectedIds: ["u1", "a1"],
        actions: [{ entryId: "u0", action: "retain" }],
        metrics: { entriesBefore: 5, candidateEntries: 3, protectedEntries: 2, markedCandidates: 0 },
        auditCodes: ["CA-PRUNE-PLAN"], fingerprint: "plan-bridge",
      } },
    })) };
    const runChild = vi.fn(async (_request: import("../src/runner.ts").PiChildRequest, _signal: AbortSignal) => ({
      terminal: "completed" as const, output: "bounded summary",
    }));
    const adapter = createPiCompactionRunner({
      bridge,
      runtime: {
        nodePath: process.execPath, piCliPath: resolve("C:/runtime/pi.js"),
        packageRoot: resolve("C:/package"), childExtensionPath: resolve("C:/package/extensions/codearbiter-child.js"),
        parentEnv: {}, platform: process.platform,
      },
      runChild,
    });
    const semantic = piSemanticEntries(branchEntries());
    await expect(adapter.plan(semantic, new AbortController().signal, resolve("C:/repo"))).resolves.toMatchObject({ fingerprint: "plan-bridge" });
    const summary = await adapter.summarize({
      provider: "openai", model: "gpt-test", tools: [], cwd: resolve("C:/repo"),
      charterPath: resolve("C:/package/includes/compaction-charter.md"), conversation: "safe conversation",
      previousSummary: "prior", customInstructions: "focus",
    }, new AbortController().signal);
    expect(summary).toBe("bounded summary");
    expect(bridge.call).toHaveBeenCalledWith({
      version: 1, event: "prune_plan", cwd: resolve("C:/repo"),
      input: { entries: semantic, policy: { tier: "standard", keepRecent: 10, maxBytes: 8_192 } },
    }, expect.any(AbortSignal));
    expect(runChild).toHaveBeenCalledWith(expect.objectContaining({
      launchKind: "internal-compaction", provider: "openai", model: "gpt-test",
      tools: [], skillPaths: [], charterPath: resolve("C:/package/includes/compaction-charter.md"),
    }), expect.any(AbortSignal));
    const task = vi.mocked(runChild).mock.calls[0]![0].task;
    expect(Buffer.byteLength(task, "utf8")).toBeLessThanOrEqual(65_536);
    expect(task).toContain("safe conversation");
  });

  test("registers native events behind lifecycle and trust, then audits only confirmed compaction", async () => {
    const handlers = new Map<string, (event: any, context: any) => unknown>();
    const pi = { on: (name: string, handler: (event: any, context: any) => unknown) => handlers.set(name, handler) };
    let ready = false;
    const child = runner();
    const audit = vi.fn(async () => undefined);
    installPiCompaction(pi, {
      packageRoot: resolve("C:/package"), isLifecycleReady: () => ready,
      runner: child, audit,
    });
    const context = {
      cwd: resolve("C:/repo"), model: { provider: "openai", id: "gpt-test" },
      isProjectTrusted: () => true,
    };
    expect(await handlers.get("session_before_compact")!(event(), context)).toBeUndefined();
    expect(child.plan).not.toHaveBeenCalled();
    ready = true;
    const before = await handlers.get("session_before_compact")!(event(), context) as any;
    expect(before.compaction).toMatchObject({ firstKeptEntryId: "u1", tokensBefore: 12_345 });
    expect(before.compaction.summary).not.toContain("synthetic-secret");
    await handlers.get("session_compact")!({
      compactionEntry: { ...before.compaction, type: "compaction", fromHook: true },
      fromExtension: true, reason: "threshold", willRetry: false,
    }, context);
    expect(audit).toHaveBeenCalledWith({
      cwd: resolve("C:/repo"), auditCodes: ["CA-PRUNE-PLAN"],
      metrics: { entriesBefore: 5, candidateEntries: 3, bytesBefore: 1_000 }, planFingerprint: "plan-123",
    });
    ready = false;
    await handlers.get("session_compact")!({
      compactionEntry: { ...before.compaction, type: "compaction" },
      fromExtension: true, reason: "threshold", willRetry: false,
    }, context);
    expect(audit).toHaveBeenCalledOnce();
  });
});
