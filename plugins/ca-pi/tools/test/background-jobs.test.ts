import { EventEmitter } from "node:events";
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
import { PassThrough } from "node:stream";
import { describe, expect, test, vi } from "vitest";
import {
  JOB_OUTPUT_BYTE_LIMIT,
  JOB_MANAGER_UNHEALTHY_MESSAGE,
  MAX_JOB_COMMAND_BYTES,
  MAX_JOB_COMMAND_PREFIX_BYTES,
  MAX_JOB_ENV_ENTRIES,
  JOB_STATES,
  MAX_ACTIVE_JOBS,
  MAX_JOB_TIMEOUT_MS,
  MIN_JOB_TIMEOUT_MS,
  createBackgroundJobRuntime,
  createBackgroundJobManager,
  piShellLaunch,
} from "../src/background-jobs.ts";
import type { ManagedProcessTree, ProcessTreeCleanupReason } from "../src/process-tree.ts";

const UNSAFE_OUTPUT_POINT = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff]/u;

function expectedDisplaySuffix(source: string): string {
  const reversed: string[] = [];
  let bytes = 0;
  let end = source.length;
  while (end > 0) {
    let start = end - 1;
    const last = source.charCodeAt(start);
    if (last >= 0xdc00 && last <= 0xdfff && start > 0) {
      const prior = source.charCodeAt(start - 1);
      if (prior >= 0xd800 && prior <= 0xdbff) start -= 1;
    }
    const rawPoint = source.slice(start, end);
    const point = UNSAFE_OUTPUT_POINT.test(rawPoint) ? "\ufffd" : rawPoint;
    const pointBytes = Buffer.byteLength(point, "utf8");
    if (bytes + pointBytes > JOB_OUTPUT_BYTE_LIMIT) break;
    reversed.push(point);
    bytes += pointBytes;
    end = start;
  }
  return reversed.reverse().join("");
}

function withoutUnboundedReflection<T>(operation: () => T): T {
  const ownKeys = Reflect.ownKeys;
  const keys = Object.keys;
  const names = Object.getOwnPropertyNames;
  const descriptors = Object.getOwnPropertyDescriptors;
  const refuse = () => { throw new Error("unbounded reflection"); };
  try {
    Reflect.ownKeys = refuse;
    Object.keys = refuse;
    Object.getOwnPropertyNames = refuse;
    Object.getOwnPropertyDescriptors = refuse;
    return operation();
  } finally {
    Reflect.ownKeys = ownKeys;
    Object.keys = keys;
    Object.getOwnPropertyNames = names;
    Object.getOwnPropertyDescriptors = descriptors;
  }
}

function manager(options?: unknown) {
  const result = createBackgroundJobManager(options);
  if (result === undefined) throw new Error("valid background job manager options were rejected");
  return result;
}

function createJob(target: ReturnType<typeof manager>, label: string, timeoutMs?: number) {
  const input = timeoutMs === undefined ? { label } : { label, timeoutMs };
  const result = target.createJob(input);
  if (result === undefined) throw new Error(`valid job was rejected: ${label}`);
  return result;
}

describe("session-local background job state", () => {
  test("uses a fixed public schema and monotonic, nonreused per-manager IDs", () => {
    const jobs = manager({ idLimit: 3, recentTerminalLimit: 2 });
    const first = createJob(jobs, "compile assets");
    expect(first).toEqual({
      id: 1,
      label: "compile assets",
      state: "queued",
      status: "Queued",
      timeoutMs: null,
      outputBytes: 0,
    });
    expect(Object.keys(first)).toEqual(["id", "label", "state", "status", "timeoutMs", "outputBytes"]);
    expect(Object.isFrozen(first)).toBe(true);

    expect(jobs.transitionJob({ id: 1, state: "completed" })?.id).toBe(1);
    expect(createJob(jobs, "typecheck").id).toBe(2);
    expect(jobs.transitionJob({ id: 2, state: "failed", status: "Exited unsuccessfully" })?.id).toBe(2);
    expect(createJob(jobs, "tests").id).toBe(3);
    expect(jobs.transitionJob({ id: 3, state: "cancelled" })?.id).toBe(3);

    expect(jobs.listJobs().map((job) => job.id)).toEqual([2, 3]);
    expect(jobs.createJob({ label: "overflow" })).toBeUndefined();
    expect(jobs.getJob(1)).toBeUndefined();
    expect(jobs.getJob(2)?.status).toBe("Exited unsuccessfully");
  });

  test("counts queued and active work against four bounded session slots", () => {
    const jobs = manager();
    expect(MAX_ACTIVE_JOBS).toBe(4);
    for (let index = 0; index < MAX_ACTIVE_JOBS; index += 1) {
      expect(createJob(jobs, `job ${index + 1}`).id).toBe(index + 1);
    }
    expect(jobs.activeJobIds()).toEqual([1, 2, 3, 4]);
    expect(Object.isFrozen(jobs.activeJobIds())).toBe(true);
    expect(jobs.createJob({ label: "fifth" })).toBeUndefined();

    expect(jobs.transitionJob({ id: 1, state: "active" })?.state).toBe("active");
    expect(jobs.createJob({ label: "still fifth" })).toBeUndefined();
    expect(jobs.transitionJob({ id: 1, state: "completed" })?.state).toBe("completed");
    expect(createJob(jobs, "replacement").id).toBe(5);
  });

  test("admits only conservative queued, active, and terminal transitions", () => {
    const jobs = manager();
    expect(JOB_STATES).toEqual(["queued", "active", "completed", "failed", "cancelled", "timed-out"]);
    const queued = createJob(jobs, "transition probe");

    expect(jobs.transitionJob({ id: queued.id, state: "queued" })?.state).toBe("queued");
    expect(jobs.transitionJob({ id: queued.id, state: "active", status: "Running checks" })).toMatchObject({
      state: "active",
      status: "Running checks",
    });
    expect(jobs.transitionJob({ id: queued.id, state: "active" })?.status).toBe("Running checks");
    expect(jobs.transitionJob({ id: queued.id, state: "queued" })).toBeUndefined();
    expect(jobs.transitionJob({ id: queued.id, state: "timed-out" })?.state).toBe("timed-out");
    expect(jobs.transitionJob({ id: queued.id, state: "timed-out" })?.state).toBe("timed-out");
    expect(jobs.transitionJob({ id: queued.id, state: "completed" })).toBeUndefined();
    expect(jobs.transitionJob({ id: queued.id, state: "active" })).toBeUndefined();

    const before = jobs.getJob(queued.id);
    expect(jobs.transitionJob({ id: queued.id, state: "timed-out", status: "different" })).toBeUndefined();
    expect(jobs.getJob(queued.id)).toEqual(before);

    for (const terminal of ["completed", "failed", "cancelled", "timed-out"] as const) {
      const job = createJob(jobs, terminal);
      expect(jobs.transitionJob({ id: job.id, state: terminal })?.state).toBe(terminal);
    }
  });

  test("validates optional caller timeouts without supplying a default", () => {
    const jobs = manager();
    expect(createJob(jobs, "unbounded by caller").timeoutMs).toBeNull();
    expect(createJob(jobs, "minimum", MIN_JOB_TIMEOUT_MS).timeoutMs).toBe(MIN_JOB_TIMEOUT_MS);
    expect(createJob(jobs, "maximum", MAX_JOB_TIMEOUT_MS).timeoutMs).toBe(MAX_JOB_TIMEOUT_MS);
    expect(jobs.transitionJob({ id: 1, state: "completed" })).toBeDefined();
    expect(jobs.transitionJob({ id: 2, state: "completed" })).toBeDefined();
    expect(jobs.transitionJob({ id: 3, state: "completed" })).toBeDefined();

    for (const timeoutMs of [0, -1, MIN_JOB_TIMEOUT_MS - 1, 1.5, MAX_JOB_TIMEOUT_MS + 1, Number.NaN, "1000"]) {
      expect(jobs.createJob({ label: "invalid timeout", timeoutMs })).toBeUndefined();
    }
  });

  test("rejects accessor, proxy, inherited, and unsafe known job inputs", () => {
    const jobs = manager();
    const inherited = Object.create({ label: "inherited" });
    const accessor = Object.defineProperty({}, "label", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    const hostile = [
      null,
      [],
      inherited,
      accessor,
      new Proxy({ label: "proxied" }, {}),
      { label: "undefined timeout", timeoutMs: undefined },
      { label: "" },
      { label: " padded" },
      { label: "line\nbreak" },
      { label: "line\u2028separator" },
      { label: "paragraph\u2029separator" },
      { label: "hidden\u202evalue" },
      { label: "x".repeat(129) },
      { label: "\u754c".repeat(90) },
      { label: "bad\ud800unicode" },
    ];
    for (const input of hostile) {
      expect(() => jobs.createJob(input)).not.toThrow();
      expect(jobs.createJob(input)).toBeUndefined();
    }

    const job = createJob(jobs, "safe label");
    const badTransitions = [
      null,
      new Proxy({ id: job.id, state: "active" }, {}),
      Object.defineProperty({ id: job.id }, "state", {
        enumerable: true,
        get: () => { throw new Error("must not execute"); },
      }),
      { id: job.id, state: "unknown" },
      { id: job.id, state: "active", status: undefined },
      { id: job.id, state: "active", status: "bad\u2066status" },
      { id: job.id, state: "active", status: "line\u2028separator" },
      { id: job.id, state: "active", status: "paragraph\u2029separator" },
      { id: job.id, state: "active", status: "x".repeat(257) },
      { id: job.id, state: "active", status: "\u754c".repeat(180) },
      { id: 1.5, state: "active" },
    ];
    for (const input of badTransitions) {
      expect(() => jobs.transitionJob(input)).not.toThrow();
      expect(jobs.transitionJob(input)).toBeUndefined();
    }
  });

  test("retains the exact last 65,536 ASCII bytes including the boundary", () => {
    const jobs = manager();
    const job = createJob(jobs, "output boundary");
    expect(JOB_OUTPUT_BYTE_LIMIT).toBe(65_536);

    expect(jobs.appendOutput({ id: job.id, chunk: "a".repeat(JOB_OUTPUT_BYTE_LIMIT) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("a".repeat(JOB_OUTPUT_BYTE_LIMIT));
    expect(jobs.getJob(job.id)?.outputBytes).toBe(JOB_OUTPUT_BYTE_LIMIT);

    expect(jobs.appendOutput({ id: job.id, chunk: "b" })).toBe(true);
    expect(jobs.tail(job.id)).toBe(`${"a".repeat(JOB_OUTPUT_BYTE_LIMIT - 1)}b`);
    expect(Buffer.byteLength(jobs.tail(job.id) ?? "", "utf8")).toBe(JOB_OUTPUT_BYTE_LIMIT);
  });

  test("retains emoji and CJK byte facts without splitting a code point", () => {
    const jobs = manager();
    const exactEmoji = createJob(jobs, "emoji exact");
    jobs.appendOutput({ id: exactEmoji.id, chunk: `${"a".repeat(65_532)}\u{1f600}` });
    expect(Buffer.byteLength(jobs.tail(exactEmoji.id) ?? "", "utf8")).toBe(65_536);
    expect(jobs.tail(exactEmoji.id)?.endsWith("\u{1f600}")).toBe(true);

    const exactCjk = createJob(jobs, "CJK exact");
    jobs.appendOutput({ id: exactCjk.id, chunk: `${"a".repeat(65_533)}\u754c` });
    expect(Buffer.byteLength(jobs.tail(exactCjk.id) ?? "", "utf8")).toBe(65_536);
    expect(jobs.tail(exactCjk.id)?.endsWith("\u754c")).toBe(true);

    const splitBoundary = createJob(jobs, "split boundary");
    jobs.appendOutput({ id: splitBoundary.id, chunk: `\u20ac${"a".repeat(65_535)}` });
    expect(jobs.tail(splitBoundary.id)).toBe("a".repeat(65_535));
    expect(Buffer.byteLength(jobs.tail(splitBoundary.id) ?? "", "utf8")).toBe(65_535);
    expect(jobs.tail(splitBoundary.id)).not.toContain("\ufffd");
  });

  test("decodes byte chunks split mid-codepoint and replaces invalid bytes safely", () => {
    const jobs = manager();
    const job = createJob(jobs, "stream decoder");
    expect(jobs.appendOutput({ id: job.id, chunk: Buffer.from([0xf0, 0x9f]) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("");
    expect(jobs.appendOutput({ id: job.id, chunk: new Uint8Array([0x98, 0x80]) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("\u{1f600}");
    expect(jobs.appendOutput({ id: job.id, chunk: Buffer.from([0xff, 0x61]) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("\u{1f600}\ufffda");
    expect(jobs.appendOutput({ id: job.id, chunk: "\u001b[31mred\u202e\u2028\u2029" })).toBe(true);
    expect(jobs.tail(job.id)).toBe("\u{1f600}\ufffda\ufffd[31mred\ufffd\ufffd\ufffd");
    expect(Buffer.from(jobs.tail(job.id) ?? "", "utf8").toString("utf8")).toBe(jobs.tail(job.id));

    const incomplete = createJob(jobs, "incomplete bytes");
    jobs.appendOutput({ id: incomplete.id, chunk: Buffer.from([0xe2, 0x82]) });
    expect(jobs.tail(incomplete.id)).toBe("");
    expect(jobs.transitionJob({ id: incomplete.id, state: "failed" })).toBeDefined();
    expect(jobs.tail(incomplete.id)).toBe("\ufffd");
  });

  test("accounts for pending UTF-8 carry before a maximum small invalid append", () => {
    const jobs = manager();
    const job = createJob(jobs, "pending carry bound");
    expect(jobs.appendOutput({ id: job.id, chunk: new Uint8Array([0xe2]) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("");
    expect(jobs.appendOutput({ id: job.id, chunk: new Uint8Array(16_384).fill(0xff) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("\ufffd".repeat(16_385));
    expect(jobs.getJob(job.id)?.outputBytes).toBe(16_385 * 3);
  });

  test("bounds huge buffer and Uint8Array-view chunks without retaining caller storage", () => {
    const jobs = manager();
    const job = createJob(jobs, "huge chunk");
    const source = Buffer.alloc(1_000_000, 0x78);
    expect(jobs.appendOutput({ id: job.id, chunk: source })).toBe(true);
    source.fill(0x79);
    expect(jobs.tail(job.id)).toBe("x".repeat(JOB_OUTPUT_BYTE_LIMIT));

    expect(jobs.appendOutput({ id: job.id, chunk: "q".repeat(1_000_000) })).toBe(true);
    expect(jobs.tail(job.id)).toBe("q".repeat(JOB_OUTPUT_BYTE_LIMIT));

    const framed = new Uint8Array([0x7a, 0x61, 0x62, 0x63, 0x7a]);
    expect(jobs.appendOutput({ id: job.id, chunk: framed.subarray(1, 4) })).toBe(true);
    expect(jobs.tail(job.id)?.endsWith("abc")).toBe(true);
    expect(Buffer.byteLength(jobs.tail(job.id) ?? "", "utf8")).toBe(JOB_OUTPUT_BYTE_LIMIT);
  });

  test("bounds every transient append work unit for multi-megabyte string and invalid binary input", () => {
    const jobs = manager();
    const job = createJob(jobs, "bounded transient work");
    const hugeString = "\u0001\u754c\u{1f600}q".repeat(800_000);
    const stringSliceSpy = vi.spyOn(String.prototype, "slice");
    let stringCalls: unknown[][] = [];
    try {
      expect(jobs.appendOutput({ id: job.id, chunk: hugeString })).toBe(true);
      stringCalls = stringSliceSpy.mock.calls.filter((_, index) => {
        const context = stringSliceSpy.mock.contexts[index];
        const value = typeof context === "string" ? context : context instanceof String ? context.valueOf() : undefined;
        return value === hugeString;
      });
    } finally {
      stringSliceSpy.mockRestore();
    }
    expect(stringCalls).toHaveLength(1);
    expect(stringCalls[0]![0]).toBeGreaterThanOrEqual(hugeString.length - JOB_OUTPUT_BYTE_LIMIT - 2);
    expect(jobs.tail(job.id)).toBe(expectedDisplaySuffix(hugeString));

    const invalid = new Uint8Array(4_000_000);
    invalid.fill(0xff);
    const binarySubarraySpy = vi.spyOn(Uint8Array.prototype, "subarray");
    let binaryCalls: unknown[][] = [];
    try {
      expect(jobs.appendOutput({ id: job.id, chunk: invalid })).toBe(true);
      binaryCalls = binarySubarraySpy.mock.calls.filter((_, index) => (
        binarySubarraySpy.mock.contexts[index] === invalid
      ));
    } finally {
      binarySubarraySpy.mockRestore();
    }
    expect(binaryCalls).toHaveLength(1);
    expect(binaryCalls[0]![0]).toBe(invalid.length - JOB_OUTPUT_BYTE_LIMIT - 3);
    expect(jobs.tail(job.id)).toBe("\ufffd".repeat(Math.floor(JOB_OUTPUT_BYTE_LIMIT / 3)));
    expect(Buffer.byteLength(jobs.tail(job.id) ?? "", "utf8")).toBeLessThanOrEqual(JOB_OUTPUT_BYTE_LIMIT);
    expect(Object.getOwnPropertyNames(Object.getPrototypeOf(jobs))).not.toContain("lastAppendWorkFacts");
  });

  test("matches an independent whole-stream UTF-8 suffix oracle across randomized invalid chunking", () => {
    const jobs = manager();
    const chunkedJob = createJob(jobs, "randomized chunked byte oracle");
    const wholeJob = createJob(jobs, "randomized whole byte oracle");
    const bytes = new Uint8Array(300_007);
    let random = 0x6d2b79f5;
    for (let index = 0; index < bytes.length; index += 1) {
      random = (Math.imul(random, 1_664_525) + 1_013_904_223) >>> 0;
      bytes[index] = random >>> 24;
    }
    bytes.set([0xf0, 0x9f, 0x98, 0x80, 0xff, 0xe2, 0x82], bytes.length - 7);
    let offset = 0;
    while (offset < bytes.length) {
      random = (Math.imul(random, 1_664_525) + 1_013_904_223) >>> 0;
      const length = 1 + (random % 7_919);
      expect(jobs.appendOutput({ id: chunkedJob.id, chunk: bytes.subarray(offset, offset + length) })).toBe(true);
      offset += length;
    }
    expect(jobs.appendOutput({ id: wholeJob.id, chunk: bytes })).toBe(true);
    expect(jobs.transitionJob({ id: chunkedJob.id, state: "completed" })).toBeDefined();
    expect(jobs.transitionJob({ id: wholeJob.id, state: "completed" })).toBeDefined();

    const decoded = new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(bytes);
    const expected = expectedDisplaySuffix(decoded);
    expect(jobs.tail(chunkedJob.id)).toBe(expected);
    expect(jobs.tail(wholeJob.id)).toBe(expected);
  });

  test("rejects malformed output input and output after terminal state", () => {
    const jobs = manager();
    const job = createJob(jobs, "output validation");
    const accessor = Object.defineProperty({ id: job.id }, "chunk", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    for (const input of [
      null,
      new Proxy({ id: job.id, chunk: "x" }, {}),
      accessor,
      { id: job.id, chunk: { toString: () => "x" } },
      { id: 99, chunk: "x" },
    ]) {
      expect(() => jobs.appendOutput(input)).not.toThrow();
      expect(jobs.appendOutput(input)).toBe(false);
    }
    expect(jobs.transitionJob({ id: job.id, state: "completed" })).toBeDefined();
    expect(jobs.appendOutput({ id: job.id, chunk: "late" })).toBe(false);
  });

  test("clears all session state on dispose without claiming a terminal cleanup", () => {
    const jobs = manager();
    const first = createJob(jobs, "active process");
    jobs.transitionJob({ id: first.id, state: "active" });
    jobs.appendOutput({ id: first.id, chunk: "session-only output" });
    expect(jobs.activeJobIds()).toEqual([first.id]);

    jobs.dispose();
    jobs.dispose();
    expect(jobs.activeJobIds()).toEqual([]);
    expect(jobs.listJobs()).toEqual([]);
    expect(jobs.getJob(first.id)).toBeUndefined();
    expect(jobs.tail(first.id)).toBeUndefined();
    expect(jobs.createJob({ label: "cannot resurrect disposed manager" })).toBeUndefined();
    expect(jobs.transitionJob({ id: first.id, state: "cancelled" })).toBeUndefined();

    const nextSession = manager();
    expect(createJob(nextSession, "new session").id).toBe(1);
  });

  test("has no session-entry restore or durable command metadata surface", async () => {
    const jobs = manager();
    const job = jobs.createJob({ label: "safe display label", command: "never retain", env: { TOKEN: "secret" } });
    expect(job).toMatchObject({ label: "safe display label" });
    expect(JSON.stringify(jobs)).toBe("{}");
    expect(Object.getOwnPropertyNames(Object.getPrototypeOf(jobs))).not.toEqual(expect.arrayContaining([
      "appendEntry", "restore", "serialize", "hydrate", "toJSON",
    ]));

    const sessionEntries = [{ type: "custom", customType: "background-job", data: { id: 88 } }];
    expect(createBackgroundJobManager({ sessionEntries })?.listJobs()).toEqual([]);
    expect(manager().listJobs()).toEqual([]);

    const [source, moduleExports] = await Promise.all([
      readFile(resolve(import.meta.dirname, "../src/background-jobs.ts"), "utf8"),
      import("../src/background-jobs.ts"),
    ]);
    expect(source).not.toMatch(/appendEntry|sessionEntries|serialize|hydrate/u);
    expect(source).not.toMatch(/node:child_process|spawn\s*\(/u);
    expect(source).not.toMatch(/appendWorkObserver|observeAppendWork|workFacts|test seam/iu);
    expect(Object.keys(moduleExports).some((name) => name.startsWith("__"))).toBe(false);
    expect(Object.getOwnPropertyNames(Object.getPrototypeOf(jobs))).not.toEqual(expect.arrayContaining([
      "observeAppendWork", "lastAppendWorkFacts", "workFacts",
    ]));
  });

  test("rejects hostile manager options without throwing", () => {
    const inherited = Object.create({ idLimit: 2 });
    const accessor = Object.defineProperty({}, "idLimit", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    for (const options of [
      null,
      [],
      inherited,
      accessor,
      new Proxy({ idLimit: 2 }, {}),
      { idLimit: undefined },
      { recentTerminalLimit: undefined },
      { idLimit: 0 },
      { idLimit: Number.MAX_SAFE_INTEGER + 1 },
      { recentTerminalLimit: 0 },
      { recentTerminalLimit: 65 },
    ]) {
      expect(() => createBackgroundJobManager(options)).not.toThrow();
      expect(createBackgroundJobManager(options)).toBeUndefined();
    }
  });

  test("builds Pi-compatible explicit POSIX and Windows shell argv", () => {
    expect(piShellLaunch({ shellPath: "/bin/bash", commandPrefix: "set -e", command: "printf ok" })).toEqual({
      command: "/bin/bash", args: ["-c", "set -e\nprintf ok"], stdin: undefined,
    });
    expect(piShellLaunch({ shellPath: "C:\\Program Files\\Git\\bin\\bash.exe", command: "printf ok" })).toEqual({
      command: "C:\\Program Files\\Git\\bin\\bash.exe", args: ["-c", "printf ok"], stdin: undefined,
    });
    expect(piShellLaunch({ shellPath: "C:\\Windows\\Sysnative\\bash.exe", command: "printf ok" })).toEqual({
      command: "C:\\Windows\\Sysnative\\bash.exe", args: ["-s"], stdin: "printf ok",
    });
    expect(piShellLaunch({ shellPath: "sh", command: "printf ok" })).toBeUndefined();
  });

  test("launches only with a current governed lease and completes after verified cleanup", async () => {
    const child = Object.assign(new EventEmitter(), {
      pid: 4242, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
    });
    const reasons: ProcessTreeCleanupReason[] = [];
    const tree: ManagedProcessTree = { child: child as never, cleanup: {
      ready: async () => true,
      terminate: async (reason) => {
        reasons.push(reason);
        return { reason, state: "already_exited", escalated: false, verified: true };
      },
    } };
    const openTree = vi.fn(async () => tree);
    const activityEvents: unknown[] = [];
    const runtime = createBackgroundJobRuntime({
      openTree,
      activity: { publish: (event) => {
        activityEvents.push(event);
        if (activityEvents.length === 1) throw new Error("footer unavailable");
      } },
    })!;
    const lease = Object.freeze({});
    const authorization = { lease, isCurrent: (candidate: unknown) => candidate === lease };
    const shellPath = process.platform === "win32" ? process.execPath : "/bin/bash";
    const job = await runtime.launch({ authorization, command: "printf ok", cwd: process.cwd(), env: [], label: "fixture", shellPath });
    expect(job?.state).toBe("active");
    expect(openTree).toHaveBeenCalledWith(shellPath, ["-c", "printf ok"], {
      cwd: process.cwd(), env: {}, stdio: ["pipe", "pipe", "pipe", "pipe"],
    });
    child.stdout.write("bounded output");
    child.emit("close", 0, null);
    await runtime.settled(job!.id);
    expect(runtime.getJob(job!.id)).toMatchObject({ state: "completed" });
    expect(runtime.tail(job!.id)).toBe("bounded output");
    expect(reasons).toEqual(["completed"]);
    expect(activityEvents).toEqual([
      { kind: "job", id: "1", label: "fixture", state: "active" },
      { kind: "job", id: "1", label: "fixture", state: "completed" },
    ]);
    expect(JSON.stringify(activityEvents)).not.toMatch(/printf ok|bounded output|env/u);
    expect(Object.getOwnPropertyNames(Object.getPrototypeOf(runtime))).not.toEqual(expect.arrayContaining([
      "createJob", "transitionJob", "appendOutput", "restore", "serialize", "hydrate",
    ]));
    expect(await runtime.launch({ authorization: { lease, isCurrent: () => false }, command: "never", cwd: process.cwd(), env: [], label: "stale", shellPath })).toBeUndefined();
    expect(openTree).toHaveBeenCalledTimes(1);
  });

  test.runIf(process.platform === "win32")("launches and disposes a real Git Bash background job", async () => {
    const shellPath = await realpath(resolve(process.env.ProgramFiles ?? "C:\\Program Files", "Git", "bin", "bash.exe"));
    const runtime = createBackgroundJobRuntime({})!;
    const lease = Object.freeze({});
    const job = await runtime.launch({
      authorization: { lease, isCurrent: (candidate: unknown) => candidate === lease },
      command: "printf live-runtime",
      cwd: process.cwd(),
      env: Object.entries(process.env),
      label: "live runtime",
      shellPath,
    });

    expect(job).toBeDefined();
    await runtime.settled(job!.id);
    expect(runtime.getJob(job!.id)).toMatchObject({ state: "completed" });
    expect(runtime.tail(job!.id)).toBe("live-runtime");
    expect(await runtime.dispose()).toBe(true);
  });

  test.each([
    ["cancel", "cancelled", "cancelled"], ["session-switch", "session_switch", "cancelled"],
    ["shutdown", "shutdown", "cancelled"], ["unload", "unload", "cancelled"], ["fatal", "fatal_error", "failed"],
  ] as const)("%s verifies cleanup before terminal disposal", async (trigger, cleanupReason, state) => {
    const child = Object.assign(new EventEmitter(), { pid: 4343, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    let release!: () => void;
    const gate = new Promise<void>((resolveGate) => { release = resolveGate; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => { await gate; return { reason, state: "terminated" as const, escalated: false, verified: true }; });
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => true, terminate } }) })!;
    const lease = Object.freeze({});
    const job = await runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "hold", cwd: process.cwd(), env: [], label: "held", shellPath: process.execPath });
    const stopping = trigger === "cancel" ? runtime.cancel(job!.id) : runtime.stop(trigger);
    await Promise.resolve();
    expect(runtime.getJob(job!.id)?.state).toBe("active");
    release();
    expect(await stopping).toBe(true);
    expect(terminate).toHaveBeenCalledWith(cleanupReason);
    expect(runtime.getJob(job!.id)?.state).toBe(state);
    if (trigger !== "cancel") expect(await runtime.dispose()).toBe(true);
  });

  test("timeout failure latches unhealthy, blocks launch, and preserves state for /ca-doctor", async () => {
    vi.useFakeTimers();
    try {
      const child = Object.assign(new EventEmitter(), { pid: 4545, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
      const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "failed" as const, escalated: true, verified: false }));
      const openTree = vi.fn(async () => ({ child: child as never, cleanup: { ready: async () => true, terminate } }));
      const runtime = createBackgroundJobRuntime({ openTree })!;
      const lease = Object.freeze({});
      const input = { authorization: { lease, isCurrent: () => true }, command: "hold", cwd: process.cwd(), env: [], label: "timeout fixture", shellPath: process.execPath, timeoutMs: 1_000 };
      const job = await runtime.launch(input);
      await vi.advanceTimersByTimeAsync(1_000);
      await runtime.settled(job!.id);
      expect(terminate).toHaveBeenCalledWith("timeout");
      expect(runtime.getJob(job!.id)?.state).toBe("active");
      expect(runtime.health()).toEqual({ healthy: false, diagnostic: JOB_MANAGER_UNHEALTHY_MESSAGE });
      expect(await runtime.launch({ ...input, label: "blocked" })).toBeUndefined();
      expect(openTree).toHaveBeenCalledTimes(1);
      expect(await runtime.dispose()).toBe(false);
      expect(runtime.getJob(job!.id)).toBeDefined();
    } finally { vi.useRealTimers(); }
  });

  test.each(["session-switch", "dispose"] as const)("%s waits for an in-flight launch and cleans its late tree", async (trigger) => {
    const child = Object.assign(new EventEmitter(), { pid: 4646, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    let release!: (tree: ManagedProcessTree) => void;
    const opened = new Promise<ManagedProcessTree>((resolveTree) => { release = resolveTree; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "terminated" as const, escalated: false, verified: true }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => await opened })!;
    const lease = Object.freeze({});
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "hold", cwd: process.cwd(), env: [], label: "late", shellPath: process.execPath });
    await Promise.resolve();
    const stopping = trigger === "dispose" ? runtime.dispose() : runtime.stop("session-switch");
    let stopped = false;
    void stopping.then(() => { stopped = true; });
    await Promise.resolve();
    expect(stopped).toBe(false);
    release({ child: child as never, cleanup: { ready: async () => true, terminate } });
    expect(await stopping).toBe(true);
    expect(await launching).toBeUndefined();
    expect(terminate).toHaveBeenCalledWith(trigger === "dispose" ? "unload" : "session_switch");
  });

  test("a child close racing containment readiness is settled once and never reactivated", async () => {
    const child = Object.assign(new EventEmitter(), { pid: 4747, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    let releaseReady!: () => void;
    const readyGate = new Promise<void>((resolveReady) => { releaseReady = resolveReady; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "already_exited" as const, escalated: false, verified: true }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => { await readyGate; return true; }, terminate } }) })!;
    const lease = Object.freeze({});
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "fast", cwd: process.cwd(), env: [], label: "fast", shellPath: process.execPath });
    await Promise.resolve();
    child.emit("close", 0, null);
    releaseReady();
    const job = await launching;
    expect(job?.state).toBe("completed");
    expect(terminate).toHaveBeenCalledTimes(1);
    expect(runtime.activeJobIds()).toEqual([]);
  });

  test("a lifecycle stop during readiness prevents stdin and active publication", async () => {
    const stdin = new PassThrough();
    const child = Object.assign(new EventEmitter(), { pid: 4848, stdin, stdout: new PassThrough(), stderr: new PassThrough() });
    let releaseReady!: () => void;
    const readyGate = new Promise<void>((resolveReady) => { releaseReady = resolveReady; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "terminated" as const, escalated: false, verified: true }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => { await readyGate; return true; }, terminate } }) })!;
    const lease = Object.freeze({});
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "hold", cwd: process.cwd(), env: [], label: "ready race", shellPath: process.execPath });
    await Promise.resolve();
    const stopping = runtime.stop("session-switch");
    releaseReady();
    expect(await stopping).toBe(true);
    expect(await launching).toBeUndefined();
    expect(stdin.writableEnded).toBe(false);
    expect(runtime.activeJobIds()).toEqual([]);
  });

  test("a governed lease that changes during readiness cleans before refusing publication", async () => {
    const stdin = new PassThrough();
    const child = Object.assign(new EventEmitter(), { pid: 4898, stdin, stdout: new PassThrough(), stderr: new PassThrough() });
    let releaseReady!: () => void;
    const readyGate = new Promise<void>((resolveReady) => { releaseReady = resolveReady; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "terminated" as const, escalated: false, verified: true }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => { await readyGate; return true; }, terminate } }) })!;
    const lease = Object.freeze({});
    let current = true;
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => current }, command: "hold", cwd: process.cwd(), env: [], label: "lease race", shellPath: process.execPath });
    await Promise.resolve();
    current = false;
    releaseReady();
    expect(await launching).toBeUndefined();
    expect(terminate).toHaveBeenCalledWith("cancelled");
    expect(stdin.writableEnded).toBe(false);
    expect(runtime.activeJobIds()).toEqual([]);
  });

  test("unverified close during readiness latches unhealthy without stdin or active resurrection", async () => {
    const stdin = new PassThrough();
    const child = Object.assign(new EventEmitter(), { pid: 4949, stdin, stdout: new PassThrough(), stderr: new PassThrough() });
    let releaseReady!: () => void;
    const readyGate = new Promise<void>((resolveReady) => { releaseReady = resolveReady; });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({ reason, state: "failed" as const, escalated: false, verified: false }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => { await readyGate; return true; }, terminate } }) })!;
    const lease = Object.freeze({});
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "fast", cwd: process.cwd(), env: [], label: "unverified race", shellPath: process.execPath });
    await Promise.resolve();
    child.emit("close", 0, null);
    releaseReady();
    expect(await launching).toBeUndefined();
    expect(stdin.writableEnded).toBe(false);
    expect(runtime.health().healthy).toBe(false);
    expect(runtime.getJob(1)?.state).toBe("queued");
  });

  test.each([true, false])("routes asynchronous stdin failure through verified cleanup=%s", async (verified) => {
    const stdin = new PassThrough();
    const child = Object.assign(new EventEmitter(), { pid: 5050, stdin, stdout: new PassThrough(), stderr: new PassThrough() });
    const terminate = vi.fn(async (reason: ProcessTreeCleanupReason) => ({
      reason, state: verified ? "terminated" as const : "failed" as const, escalated: false, verified,
    }));
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: { ready: async () => true, terminate } }) })!;
    const lease = Object.freeze({});
    const job = await runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "fast", cwd: process.cwd(), env: [], label: "stdin failure", shellPath: process.execPath });
    expect(job?.state).toBe("active");
    expect(() => stdin.emit("error", Object.assign(new Error("broken pipe"), { code: "EPIPE" }))).not.toThrow();
    await runtime.settled(job!.id);
    expect(terminate).toHaveBeenCalledWith("fatal_error");
    if (verified) expect(runtime.getJob(job!.id)?.state).toBe("failed");
    else {
      expect(runtime.getJob(job!.id)?.state).toBe("active");
      expect(runtime.health()).toEqual({ healthy: false, diagnostic: JOB_MANAGER_UNHEALTHY_MESSAGE });
    }
  });

  test("never publishes a natural completion after its lifecycle lease becomes stale during cleanup", async () => {
    const child = Object.assign(new EventEmitter(), { pid: 5151, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    let releaseReady!: () => void;
    let releaseCleanup!: () => void;
    const readyGate = new Promise<void>((resolveReady) => { releaseReady = resolveReady; });
    const cleanupGate = new Promise<void>((resolveCleanup) => { releaseCleanup = resolveCleanup; });
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: {
      ready: async () => { await readyGate; return true; },
      terminate: async (reason) => { await cleanupGate; return { reason, state: "already_exited" as const, escalated: false, verified: true }; },
    } }) })!;
    const lease = Object.freeze({});
    let current = true;
    const launching = runtime.launch({ authorization: { lease, isCurrent: () => current }, command: "fast", cwd: process.cwd(), env: [], label: "stale completion", shellPath: process.execPath });
    await Promise.resolve();
    child.emit("close", 0, null);
    releaseReady();
    current = false;
    releaseCleanup();
    expect(await launching).toBeUndefined();
    expect(runtime.getJob(1)?.state).toBe("completed");
    expect(runtime.activeJobIds()).toEqual([]);
  });

  test("settled waits when registered while the job is active", async () => {
    const child = Object.assign(new EventEmitter(), { pid: 5201, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    const runtime = createBackgroundJobRuntime({ openTree: async () => ({ child: child as never, cleanup: {
      ready: async () => true,
      terminate: async (reason) => ({ reason, state: "already_exited" as const, escalated: false, verified: true }),
    } }) })!;
    const lease = Object.freeze({});
    const job = await runtime.launch({ authorization: { lease, isCurrent: () => true }, command: "hold", cwd: process.cwd(), env: [], label: "watcher", shellPath: process.execPath });
    let observed = false;
    const waiting = runtime.settled(job!.id).then(() => { observed = true; });
    await Promise.resolve();
    expect(observed).toBe(false);
    child.emit("close", 0, null);
    await waiting;
    expect(runtime.getJob(job!.id)?.state).toBe("completed");
  });

  test("bounds command, prefix, and exact own-data environment before launch work", async () => {
    expect(piShellLaunch({ shellPath: process.execPath, command: "x".repeat(MAX_JOB_COMMAND_BYTES) })).toBeDefined();
    expect(piShellLaunch({ shellPath: process.execPath, command: "x".repeat(MAX_JOB_COMMAND_BYTES + 1) })).toBeUndefined();
    expect(piShellLaunch({ shellPath: process.execPath, command: "x", commandPrefix: "p".repeat(MAX_JOB_COMMAND_PREFIX_BYTES) })).toBeDefined();
    expect(piShellLaunch({ shellPath: process.execPath, command: "x", commandPrefix: "p".repeat(MAX_JOB_COMMAND_PREFIX_BYTES + 1) })).toBeUndefined();

    const childFor = () => Object.assign(new EventEmitter(), { pid: 5252, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
    const openTree = vi.fn(async () => ({ child: childFor() as never, cleanup: {
      ready: async () => true,
      terminate: async (reason: ProcessTreeCleanupReason) => ({ reason, state: "terminated" as const, escalated: false, verified: true }),
    } }));
    const lease = Object.freeze({});
    const authorization = { lease, isCurrent: () => true };
    const boundaryEnv = Array.from({ length: MAX_JOB_ENV_ENTRIES }, (_, index) => [`K${index}`, "v"] as const);
    const runtime = createBackgroundJobRuntime({ openTree })!;
    expect(await runtime.launch({ authorization, command: "ok", cwd: process.cwd(), env: boundaryEnv, label: "boundary", shellPath: process.execPath })).toBeDefined();
    await runtime.cancel(1);
    expect(await runtime.launch({ authorization, command: "ok", cwd: process.cwd(), env: [["BIG", "v".repeat(32_768)]], label: "value boundary", shellPath: process.execPath })).toBeDefined();
    await runtime.cancel(2);
    const tooMany = [...boundaryEnv, ["overflow", "v"] as const];
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: tooMany, label: "too many", shellPath: process.execPath })).toBeUndefined();
    const accessorEnv: unknown[] = [];
    Object.defineProperty(accessorEnv, "0", { enumerable: true, get: () => { throw new Error("must not execute"); } });
    accessorEnv.length = 1;
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: accessorEnv as never, label: "accessor", shellPath: process.execPath })).toBeUndefined();
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: new Proxy([], {}), label: "proxy", shellPath: process.execPath })).toBeUndefined();
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: [["K".repeat(257), "v"]], label: "long key", shellPath: process.execPath })).toBeUndefined();
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: [["BIG", "v".repeat(32_769)]], label: "long value", shellPath: process.execPath })).toBeUndefined();
    const overTotal = Array.from({ length: 9 }, (_, index) => [`B${index}`, "v".repeat(32_768)] as const);
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: overTotal, label: "large env", shellPath: process.execPath })).toBeUndefined();
    const inheritedEnv = Object.setPrototypeOf([], { TOKEN: "secret" });
    expect(await runtime.launch({ authorization, command: "never", cwd: process.cwd(), env: inheritedEnv, label: "inherited", shellPath: process.execPath })).toBeUndefined();
    const hostileLaunch = Object.defineProperty({}, "command", { enumerable: true, get: () => { throw new Error("must not execute"); } });
    await expect(runtime.launch(hostileLaunch as never)).resolves.toBeUndefined();

    const hugeEnvironment: unknown[] = new Array(20_000);
    Object.defineProperty(hugeEnvironment, "256", { enumerable: true, get: () => { throw new Error("must reject on length"); } });
    const hugeEnvironmentResult = withoutUnboundedReflection(() => runtime.launch({
      authorization, command: "never", cwd: process.cwd(), env: hugeEnvironment as never,
      label: "huge", shellPath: process.execPath,
    }));
    await expect(hugeEnvironmentResult).resolves.toBeUndefined();

    const staleAuthorization = { lease, isCurrent: () => false };
    const hugeLaunch: Record<string, unknown> = { authorization: staleAuthorization, command: "never", cwd: process.cwd(), env: [], label: "huge launch", shellPath: process.execPath };
    for (let index = 0; index < 20_000; index += 1) hugeLaunch[`EXTRA_${index}`] = "x";
    const hugeShell: Record<string, unknown> = { shellPath: process.execPath, command: "never" };
    for (let index = 0; index < 20_000; index += 1) hugeShell[`EXTRA_${index}`] = "x";
    const [hugeJob, hugeShellResult] = withoutUnboundedReflection(() => [
      runtime.launch(hugeLaunch as never), piShellLaunch(hugeShell as never),
    ] as const);
    await expect(hugeJob).resolves.toBeUndefined();
    expect(hugeShellResult).toBeDefined();
    expect(openTree).toHaveBeenCalledTimes(2);
  });
});
