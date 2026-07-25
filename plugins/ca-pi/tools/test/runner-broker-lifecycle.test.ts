/** runner-broker-lifecycle.test.ts - #455 broker listener teardown, asserted BEHAVIOURALLY.
 *
 * The runner closes its per-child broker at two independent call sites: the refused-launch
 * `catch` (a launch that never reaches the `try/finally`) and the `finally` that backstops every
 * path after a successful prepare. A source-text guard cannot tell them apart — deleting either
 * leaves the other's identical text in place — so each obligation is pinned here by connecting to
 * the REAL loopback port the REAL broker bound and asserting the connection is refused after
 * `runPiChild` returns. A leaked listener still holds the operator's real credential and still
 * honours the child's token, so this is a credential-authority obligation, not tidiness.
 *
 * The broker module is wrapped, never replaced: `startInferenceBroker` delegates to the real
 * implementation and only records the endpoint it produced. */
import { EventEmitter } from "node:events";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { connect } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { PassThrough } from "node:stream";
import { afterEach, describe, expect, test, vi } from "vitest";

const lifecycleMocks = vi.hoisted(() => {
  const spawn = vi.fn();
  const cleanupTerminate = vi.fn(async (reason: string) => ({ escalated: false, reason, state: "terminated", verified: true }));
  const cleanupReady = vi.fn(async () => true);
  const processTreeSpawnOptions = vi.fn((_platform?: NodeJS.Platform) => ({ detached: true, shell: false, windowsHide: true }));
  return {
    spawn,
    cleanupTerminate,
    cleanupReady,
    processTreeSpawnOptions,
    createProcessTreeCleanup: vi.fn(() => ({ ready: cleanupReady, terminate: cleanupTerminate })),
    spawnProcessTree: vi.fn(async (command: string, args: readonly string[], options: Record<string, unknown>) =>
      spawn(command, args, { ...processTreeSpawnOptions(process.platform), ...options })),
    resolveRuntimeIdentity: vi.fn(),
    /** Every broker endpoint the runner actually bound, in order. Recorded, never faked. The
     * TOKEN is deliberately NOT captured: this suite only needs the port, and a live per-child
     * token has no business outliving the broker that minted it, even in a test's memory. */
    bound: [] as { baseUrl: string }[],
  };
});

vi.mock("node:child_process", async (importOriginal) => ({
  ...await importOriginal<typeof import("node:child_process")>(),
  spawn: lifecycleMocks.spawn,
}));
vi.mock("../src/runtime-resolver.ts", async (importOriginal) => ({
  ...await importOriginal<typeof import("../src/runtime-resolver.ts")>(),
  resolvePiRuntimeIdentity: lifecycleMocks.resolveRuntimeIdentity,
}));
vi.mock("../src/process-tree.ts", async (importOriginal) => ({
  ...await importOriginal<typeof import("../src/process-tree.ts")>(),
  createProcessTreeCleanup: lifecycleMocks.createProcessTreeCleanup,
  processTreeSpawnOptions: lifecycleMocks.processTreeSpawnOptions,
  spawnProcessTree: lifecycleMocks.spawnProcessTree,
}));
// A transparent wrapper: the REAL broker binds a REAL loopback port, and the only added
// behaviour is recording the endpoint so the test can probe it after runPiChild returns.
vi.mock("../src/inference-broker.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/inference-broker.ts")>();
  return {
    ...actual,
    startInferenceBroker: vi.fn(async (options: { nonce: string }) => {
      const broker = await actual.startInferenceBroker(options);
      lifecycleMocks.bound.push({ baseUrl: broker.baseUrl });
      return broker;
    }),
  };
});

type RunnerModule = typeof import("../src/runner.ts");

class FakeChild extends EventEmitter {
  readonly pid = 4242;
  exitCode: number | null = null;
  signalCode: NodeJS.Signals | null = null;
  readonly stdin = new PassThrough();
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  readonly capability = new PassThrough();
  readonly stdio = [this.stdin, this.stdout, this.stderr, this.capability] as const;
  kill(): boolean { return true; }
}

const temporaryRoots: string[] = [];

async function materializedRequest(provider = "openai") {
  const root = await realpath(await mkdtemp(resolve(tmpdir(), "ca-pi-broker-life-")));
  temporaryRoots.push(root);
  const packageRoot = resolve(import.meta.dirname, "..", "..");
  const piRoot = resolve(root, "pi-runtime");
  const request = {
    nodePath: process.execPath,
    piCliPath: resolve(piRoot, "dist", "cli.js"),
    provider,
    model: "gpt-test",
    tools: ["read", "bash", "edit", "write"] as const,
    cwd: resolve(root, "repo"),
    childExtensionPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
    skillPaths: [resolve(packageRoot, "routines", "tdd", "SKILL.md")],
    charterPath: resolve(packageRoot, "agents", "backend-author.md"),
    task: "task-broker-lifecycle",
    parentEnv: {
      ...process.env,
      // A DISPOSABLE operator home, pinned before anything reads one. `prepareChildEnvironment`
      // resolves the operator's store from PI_CODING_AGENT_DIR ?? USERPROFILE ?? HOME and opens
      // the real `auth.json`/`models.json` found there; without this the suite would read the
      // developer's own Pi credential store, which the project's security controls forbid
      // outright, and test 1's outcome would depend on whatever that operator had configured.
      HOME: resolve(root, "operator-home"),
      USERPROFILE: resolve(root, "operator-home"),
      PI_CODING_AGENT_DIR: resolve(root, "operator-home", ".pi", "agent"),
      OPENAI_API_KEY: "dummy-openai-value",
      ANTHROPIC_API_KEY: "dummy-anthropic-value",
    } as NodeJS.ProcessEnv,
    platform: process.platform,
    timeoutMs: 5_000,
  };
  await mkdir(resolve(root, "operator-home", ".pi", "agent"), { recursive: true });
  await mkdir(request.cwd, { recursive: true });
  await mkdir(dirname(request.piCliPath), { recursive: true });
  await writeFile(request.piCliPath, "// broker lifecycle Pi CLI fixture\n", "utf8");
  await writeFile(resolve(piRoot, "package.json"), '{"name":"@earendil-works/pi-coding-agent","version":"0.80.10","bin":{"pi":"dist/cli.js"}}\n', "utf8");
  lifecycleMocks.resolveRuntimeIdentity.mockImplementation(async (candidate: string) => ({
    cliEntry: candidate,
    packageRoot: resolve(dirname(candidate), ".."),
    version: "0.80.10",
  }));
  return request;
}

/** A real TCP connect against the endpoint the broker actually bound. `true` means something is
 * still accepting connections on that port — i.e. the listener outlived its child.
 *
 * Only ECONNREFUSED counts as dead. Anything else — a timeout, a routing error, a port the OS
 * reassigned to an unrelated same-user service — is reported as alive, so the probe fails the
 * assertion rather than silently excusing a listener it could not disprove. */
async function listenerAlive(baseUrl: string): Promise<boolean> {
  const { hostname, port } = new URL(baseUrl);
  return await new Promise<boolean>((resolveAlive) => {
    const socket = connect({ host: hostname, port: Number(port) });
    const settle = (alive: boolean): void => {
      socket.removeAllListeners();
      socket.destroy();
      resolveAlive(alive);
    };
    socket.setTimeout(2_000);
    socket.once("connect", () => settle(true));
    socket.once("timeout", () => settle(true));
    socket.once("error", (error: NodeJS.ErrnoException) => settle(error.code !== "ECONNREFUSED"));
  });
}

afterEach(async () => {
  lifecycleMocks.bound.length = 0;
  lifecycleMocks.spawn.mockReset();
  lifecycleMocks.cleanupReady.mockReset();
  lifecycleMocks.cleanupReady.mockResolvedValue(true);
  lifecycleMocks.cleanupTerminate.mockReset();
  lifecycleMocks.cleanupTerminate.mockImplementation(async (reason: string) => ({ escalated: false, reason, state: "terminated", verified: true }));
  lifecycleMocks.createProcessTreeCleanup.mockReset();
  lifecycleMocks.createProcessTreeCleanup.mockImplementation(() => ({ ready: lifecycleMocks.cleanupReady, terminate: lifecycleMocks.cleanupTerminate }));
  lifecycleMocks.spawnProcessTree.mockReset();
  lifecycleMocks.spawnProcessTree.mockImplementation(async (command: string, args: readonly string[], options: Record<string, unknown>) =>
    lifecycleMocks.spawn(command, args, { ...lifecycleMocks.processTreeSpawnOptions(process.platform), ...options }));
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

describe("#455 broker listener lifetime", () => {
  // Pins the `finally`. An unexpected throw after a successful prepare must not strand a bound
  // loopback listener that still carries the operator's authorized upstream.
  test("unbinds the loopback listener when the launch throws after the broker has bound", async () => {
    const { runPiChild } = await import("../src/runner.ts") as RunnerModule;
    const request = await materializedRequest();
    lifecycleMocks.spawn.mockImplementation(() => new FakeChild());
    lifecycleMocks.cleanupReady.mockRejectedValue(new Error("unexpected containment readiness failure"));

    await expect(runPiChild(request as never, new AbortController().signal))
      .rejects.toThrow("unexpected containment readiness failure");

    expect(lifecycleMocks.bound).toHaveLength(1);
    // The broker genuinely bound and was genuinely reachable, so a "closed" result cannot pass
    // vacuously: the same probe must have answered `true` while it was live.
    expect(await listenerAlive(lifecycleMocks.bound[0]!.baseUrl)).toBe(false);
  });

  // Pins the refused-launch `catch`, which is a DIFFERENT call site: this path returns before the
  // `try/finally` is ever entered, so the `finally` cannot cover it.
  test("unbinds the loopback listener when the launch is refused at the broker-authority stage", async () => {
    const { runPiChild } = await import("../src/runner.ts") as RunnerModule;
    // `amazon-bedrock` is broker-ineligible, so prepareChildEnvironment refuses and runPiChild
    // returns through the catch at the broker-authority stage without ever spawning.
    const request = await materializedRequest("amazon-bedrock");
    let spawnCalls = 0;
    lifecycleMocks.spawn.mockImplementation(() => { spawnCalls += 1; throw new Error("unreachable"); });

    const result = await runPiChild(request as never, new AbortController().signal);

    expect(result).toEqual({
      terminal: "degraded",
      diagnostic: "Pi child isolation failed safely (isolation-broker); no inline promotion is available; run /ca-doctor.",
    });
    expect(spawnCalls).toBe(0);
    expect(lifecycleMocks.bound).toHaveLength(1);
    expect(await listenerAlive(lifecycleMocks.bound[0]!.baseUrl)).toBe(false);
  });

  // The probe above is only meaningful if it can observe a LIVE listener. Without this the two
  // assertions could both pass against a broker that never bound anything at all.
  test("the liveness probe observes a bound broker before it is closed", async () => {
    const { startInferenceBroker } = await import("../src/inference-broker.ts");
    const broker = await startInferenceBroker({ nonce: "0123456789abcdef0123456789abcdef" });
    try {
      expect(await listenerAlive(broker.baseUrl)).toBe(true);
    } finally {
      await broker.close();
    }
    expect(await listenerAlive(broker.baseUrl)).toBe(false);
  });
});
