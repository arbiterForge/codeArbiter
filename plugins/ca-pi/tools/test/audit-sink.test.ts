/**
 * audit-sink.test.ts - the one adversarial matrix every Pi `gate-events.log` producer runs.
 *
 * Two tables live here. The producer table drives the real filesystem cases (regular append,
 * file symlink, directory junction, hardlink, nonregular sink) across every writer that can put
 * a row into the governance log, so a new producer that reimplements the sink is caught by the
 * negative cases rather than by review. The primitive table drives the injected-io race cases
 * (validation-open swap, opened-handle mismatch, post-append swap, create race) against the one
 * shared primitive; `module-structure.test.ts` proves there is no second implementation for
 * those cases to miss.
 */
import { link, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { afterEach, describe, expect, test, vi } from "vitest";

import { BridgeClient } from "../src/bridge.ts";
import { appendPiCompactionAudit } from "../src/compaction.ts";
import { appendDispatchAudit } from "../src/dispatch.ts";
import { appendBackgroundJobAudit, appendPermissionAudit } from "../src/tool-guard.ts";
import { appendAuditLineWithIo, NODE_AUDIT_SINK_IO, type AuditSinkIoPort, type AuditSinkStatsPort } from "../src/audit-sink.ts";

const { lstat } = NODE_AUDIT_SINK_IO;
const open = async (path: string, flags: number | "a", mode?: number) =>
  await NODE_AUDIT_SINK_IO.open(path, flags === "a" ? constants.O_WRONLY | constants.O_APPEND : flags, mode);

const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

async function temporaryRoot(prefix: string): Promise<string> {
  const root = await realpath(await mkdtemp(resolve(tmpdir(), prefix)));
  temporaryRoots.push(root);
  return root;
}

/** File symlinks need an elevated or developer-mode Windows session; probe once. */
async function fileSymlinksAvailable(): Promise<boolean> {
  const root = await temporaryRoot("ca-pi-symlink-probe-");
  try {
    await writeFile(resolve(root, "target"), "probe\n", "utf8");
    await symlink(resolve(root, "target"), resolve(root, "alias"), "file");
    return true;
  } catch {
    return false;
  }
}

const FILE_SYMLINKS = await fileSymlinksAvailable();

/** A Pi writer that emits exactly one governance row into the project's own audit log. */
interface AuditProducer {
  readonly name: string;
  readonly rule: string;
  emit(cwd: string): Promise<void>;
}

/** Reaches `BridgeClient.auditFailure` without spawning Python: an unresolvable interpreter
 * rejects path validation, which is the bridge's own audited failure path. */
async function emitBridgeFailure(cwd: string): Promise<void> {
  const bridge = new BridgeClient({
    bridgeScript: resolve(cwd, "hooks", "pi-bridge.py"),
    packageRoot: resolve(cwd, "hooks"),
    toolClasses: { bash: "EXEC" },
  });
  const response = await bridge.call(
    { version: 1, event: "tool_call", cwd, tool: "bash", input: { command: "git status" } },
    new AbortController().signal,
  );
  expect(response.outcome).toBe("block");
}

const PRODUCERS: readonly AuditProducer[] = Object.freeze([
  {
    name: "permission",
    rule: "RULE: PI-PERMISSION",
    emit: async (cwd) => {
      await appendPermissionAudit(cwd, {
        timestamp: "2026-07-24T00:00:00.000Z",
        correlation: "a".repeat(64),
        toolClass: "EXEC",
        actionClasses: ["shell-mutation"],
        decision: "approved",
      });
    },
  },
  {
    name: "background-job",
    rule: "RULE: PI-BACKGROUND-JOB",
    emit: async (cwd) => {
      await appendBackgroundJobAudit(cwd, {
        timestamp: "2026-07-24T00:00:00.000Z",
        lifecycleId: "b".repeat(64),
        correlation: "c".repeat(64),
        event: "cancel",
        id: 1,
        accepted: true,
      });
    },
  },
  { name: "bridge-failure", rule: "RULE: PI-BRIDGE", emit: emitBridgeFailure },
  {
    name: "dispatch",
    rule: "RULE: PI-DISPATCH",
    emit: async (cwd) => {
      await appendDispatchAudit({
        cwd,
        role: "security-reviewer",
        provider: "openai",
        model: "gpt-5",
        terminal: "completed",
        exitCode: 0,
        durationMs: 1,
        stdoutBytes: 1,
        stderrBytes: 0,
      });
    },
  },
  {
    name: "compaction",
    rule: "RULE: PI-PRUNE",
    emit: async (cwd) => {
      await appendPiCompactionAudit({
        cwd,
        auditCodes: ["CA-PRUNE-PLAN"],
        metrics: { entriesBefore: 5, candidateEntries: 3 },
        planFingerprint: "plan-123",
      });
    },
  },
]);

describe("Pi audit sink hardening", () => {
  test.each(PRODUCERS)("$name writes its row into the project's own state directory", async (producer) => {
    const root = await temporaryRoot("ca-pi-audit-regular-");
    await mkdir(resolve(root, ".codearbiter"));

    await producer.emit(root);

    const audit = await readFile(resolve(root, ".codearbiter", "gate-events.log"), "utf8");
    expect(audit).toContain("HOST: pi");
    expect(audit).toContain(producer.rule);
    expect(audit.endsWith("\n")).toBe(true);
    expect(audit.split("\n").filter((line) => line !== "")).toHaveLength(1);
  });

  test.skipIf(!FILE_SYMLINKS).each(PRODUCERS)(
    "$name refuses a gate-events.log symlinked at an external sentinel",
    async (producer) => {
      const root = await temporaryRoot("ca-pi-audit-file-link-");
      const outside = await temporaryRoot("ca-pi-audit-file-sentinel-");
      const sentinel = resolve(outside, "sentinel.log");
      await mkdir(resolve(root, ".codearbiter"));
      await writeFile(sentinel, "sentinel\n", "utf8");
      await symlink(sentinel, resolve(root, ".codearbiter", "gate-events.log"), "file");

      await producer.emit(root);

      expect(await readFile(sentinel, "utf8")).toBe("sentinel\n");
    },
  );

  test.each(PRODUCERS)("$name refuses a .codearbiter directory linked at an external sentinel", async (producer) => {
    const root = await temporaryRoot("ca-pi-audit-dir-link-");
    const outside = await temporaryRoot("ca-pi-audit-dir-sentinel-");
    const sentinel = resolve(outside, "gate-events.log");
    await writeFile(sentinel, "sentinel\n", "utf8");
    await symlink(outside, resolve(root, ".codearbiter"), process.platform === "win32" ? "junction" : "dir");

    await producer.emit(root);

    expect(await readFile(sentinel, "utf8")).toBe("sentinel\n");
  });

  test.each(PRODUCERS)("$name refuses a gate-events.log hardlinked at an external sentinel", async (producer) => {
    const root = await temporaryRoot("ca-pi-audit-hardlink-");
    const sentinel = resolve(root, "sentinel.log");
    await mkdir(resolve(root, ".codearbiter"));
    await writeFile(sentinel, "sentinel\n", "utf8");
    await link(sentinel, resolve(root, ".codearbiter", "gate-events.log"));

    await producer.emit(root);

    expect(await readFile(sentinel, "utf8")).toBe("sentinel\n");
  });

  test.each(PRODUCERS)("$name keeps its fail-open result when the sink is not a regular file", async (producer) => {
    const root = await temporaryRoot("ca-pi-audit-nonregular-");
    await mkdir(resolve(root, ".codearbiter", "gate-events.log"), { recursive: true });

    await expect(producer.emit(root)).resolves.toBeUndefined();

    expect((await lstat(resolve(root, ".codearbiter", "gate-events.log"))).isDirectory()).toBe(true);
  });

  test.each(PRODUCERS)("$name never creates a state directory the project does not have", async (producer) => {
    const root = await temporaryRoot("ca-pi-audit-absent-state-");

    await producer.emit(root);

    await expect(lstat(resolve(root, ".codearbiter"))).rejects.toMatchObject({ code: "ENOENT" });
  });
});

describe("Pi audit sink race cases", () => {
  const line = "[2026-07-24T00:00:00.000Z] | HOST: pi | RULE: PI-TEST | AUDIT: PI_TEST\n";

  async function fixture(): Promise<{ root: string; target: string; replacement: string }> {
    const root = await temporaryRoot("ca-pi-audit-race-");
    const state = resolve(root, ".codearbiter");
    await mkdir(state);
    return { root, target: resolve(state, "gate-events.log"), replacement: resolve(state, "replacement.log") };
  }

  test("rejects a target swapped between validation and open", async () => {
    const { root, target, replacement } = await fixture();
    await writeFile(target, "target\n", "utf8");
    await writeFile(replacement, "replacement\n", "utf8");
    const targetStats = await lstat(target);
    const replacementStats = await lstat(replacement);
    let targetLstats = 0;
    const { appendAuditLineWithIo } = await import("../src/audit-sink.ts");

    await expect(appendAuditLineWithIo(root, line, {
      realpath,
      lstat: async (path: string) => {
        if (path === target) return ++targetLstats === 1 ? targetStats : replacementStats;
        return await lstat(path);
      },
      open: async () => await open(replacement, "a"),
    })).resolves.toBe(false);
    expect(await readFile(replacement, "utf8")).toBe("replacement\n");
  });

  test("rejects an opened handle whose identity is not the validated path", async () => {
    const { root, target, replacement } = await fixture();
    await writeFile(target, "target\n", "utf8");
    await writeFile(replacement, "replacement\n", "utf8");
    const { appendAuditLineWithIo } = await import("../src/audit-sink.ts");

    await expect(appendAuditLineWithIo(root, line, {
      realpath,
      lstat,
      open: async () => await open(replacement, "a"),
    })).resolves.toBe(false);
    expect(await readFile(replacement, "utf8")).toBe("replacement\n");
  });

  test("rejects a target swapped after the append", async () => {
    const { root, target, replacement } = await fixture();
    await writeFile(target, "target\n", "utf8");
    await writeFile(replacement, "replacement\n", "utf8");
    const targetStats = await lstat(target);
    const replacementStats = await lstat(replacement);
    let targetLstats = 0;
    const { appendAuditLineWithIo } = await import("../src/audit-sink.ts");

    await expect(appendAuditLineWithIo(root, line, {
      realpath,
      lstat: async (path: string) => {
        if (path === target) return ++targetLstats < 4 ? targetStats : replacementStats;
        return await lstat(path);
      },
      open: async () => await open(target, "a"),
    })).resolves.toBe(false);
    expect(await readFile(replacement, "utf8")).toBe("replacement\n");
  });

  test("rejects a hardlink raced into an absent target", async () => {
    const { root, target } = await fixture();
    const sentinel = resolve(root, "sentinel.log");
    await writeFile(sentinel, "sentinel\n", "utf8");
    let raced = false;
    const { appendAuditLineWithIo } = await import("../src/audit-sink.ts");

    await expect(appendAuditLineWithIo(root, line, {
      realpath,
      lstat,
      open: async (path: string, flags: number, mode?: number) => {
        if (path === target && !raced) {
          raced = true;
          await link(sentinel, target);
        }
        return await open(path, flags, mode);
      },
    })).resolves.toBe(false);
    expect(await readFile(sentinel, "utf8")).toBe("sentinel\n");
  });

  test("rejects a line that is unbounded, unterminated, or carries an embedded newline", async () => {
    const { root } = await fixture();
    const { appendAuditLine } = await import("../src/audit-sink.ts");

    await expect(appendAuditLine(root, `${"x".repeat(2_049)}\n`)).resolves.toBe(false);
    await expect(appendAuditLine(root, "no terminator")).resolves.toBe(false);
    await expect(appendAuditLine(root, "forged\ninjection\n")).resolves.toBe(false);
    await expect(lstat(resolve(root, ".codearbiter", "gate-events.log"))).rejects.toMatchObject({ code: "ENOENT" });
  });
});

// Adjacent real 64-bit IDs collapse when represented as JS numbers.
const exact = 9_007_199_254_740_992n;
function stat(ino: number | bigint, directory = false): AuditSinkStatsPort {
  return { dev: 1, ino, nlink: 1, size: 0,
    isFile: () => !directory, isDirectory: () => directory, isSymbolicLink: () => false };
}
function fixture(expected: number | bigint, opened: number | bigint, directory: number | bigint = 1) {
  const root = resolve("audit-identity-inert");
  const state = resolve(root, ".codearbiter");
  const line = "audit fixture\n";
  let size = 0;
  const appendFile = vi.fn(async () => { size += Buffer.byteLength(line); });
  const close = vi.fn(async () => {});
  const handle = { stat: async () => ({ ...stat(opened), size }), appendFile,
    sync: async () => {}, close };
  let seen = 0;
  const io: AuditSinkIoPort = {
    realpath: async (path) => path,
    lstat: async (path) => path === state ? stat(directory, true)
      : { ...stat(++seen === 1 ? expected : opened), size },
    open: async () => handle,
  };
  return { root, line, io, appendFile, close };
}

describe("exact audit file identities", () => {
  test("refuses rounded numeric IDs before writing even when two distinct IDs compare equal", async () => {
    expect(Number(exact)).toBe(Number(exact + 1n));
    const f = fixture(Number(exact), Number(exact + 1n));
    await expect(appendAuditLineWithIo(f.root, f.line, f.io)).resolves.toBe(false);
    expect(f.appendFile).not.toHaveBeenCalled();
  });

  test("refuses unsafe directory identities before opening a sink", async () => {
    const f = fixture(2, 2, Number(exact));
    const open = vi.spyOn(f.io, "open");
    await expect(appendAuditLineWithIo(f.root, f.line, f.io)).resolves.toBe(false);
    expect(open).not.toHaveBeenCalled();
  });

  test("rejects adjacent exact bigint file IDs and closes the mismatched handle", async () => {
    const f = fixture(exact, exact + 1n);
    await expect(appendAuditLineWithIo(f.root, f.line, f.io)).resolves.toBe(false);
    expect(f.appendFile).not.toHaveBeenCalled();
    expect(f.close).toHaveBeenCalledOnce();
  });

  test.each([2, exact])("accepts the same precise identity %s and still appends and closes", async (id) => {
    const f = fixture(id, id);
    await expect(appendAuditLineWithIo(f.root, f.line, f.io)).resolves.toBe(true);
    expect(f.appendFile).toHaveBeenCalledOnce();
    expect(f.close).toHaveBeenCalledOnce();
  });

  test("the real filesystem port returns exact bigint device and inode values", async () => {
    const observed = await NODE_AUDIT_SINK_IO.lstat(import.meta.filename);
    expect(typeof observed.dev).toBe("bigint");
    expect(typeof observed.ino).toBe("bigint");
    expect(observed.isFile()).toBe(true);
    expect(Number.isSafeInteger(observed.size)).toBe(true);
  });

  test.each([NaN, Infinity, -1, -1n])("refuses invalid injected identity %s before writing", async (id) => {
    const f = fixture(id, id);
    await expect(appendAuditLineWithIo(f.root, f.line, f.io)).resolves.toBe(false);
    expect(f.appendFile).not.toHaveBeenCalled();
  });
});
