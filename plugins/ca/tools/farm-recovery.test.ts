import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, realpath, mkdir, writeFile, readFile, readdir, rm, link, rename, appendFile, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const probe = vi.hoisted(() => ({
  wholeReads: 0, readBytes: 0,
  beforeRead: undefined as undefined | (() => Promise<void>),
}));
vi.mock("node:fs/promises", async (load) => {
  const actual = await load<typeof import("node:fs/promises")>();
  return { ...actual,
    readFile: (...args: Parameters<typeof actual.readFile>) => {
      if (String(args[0]).endsWith("task-a.json")) probe.wholeReads++;
      return actual.readFile(...args);
    },
    open: async (...args: Parameters<typeof actual.open>) => {
      const handle = await actual.open(...args);
      if (!String(args[0]).endsWith("task-a.json")) return handle;
      return new Proxy(handle, { get(target, property) {
        if (property === "read") return async (...readArgs: Parameters<typeof handle.read>) => {
          const callback = probe.beforeRead; probe.beforeRead = undefined;
          await callback?.();
          const result = await target.read(...readArgs);
          probe.readBytes += result.bytesRead;
          return result;
        };
        if (property === "readFile") return (...readArgs: Parameters<typeof handle.readFile>) => {
          probe.wholeReads++; return target.readFile(...readArgs);
        };
        const value = Reflect.get(target, property);
        return typeof value === "function" ? value.bind(target) : value;
      }});
    },
  };
});
import { recoverReceipt } from "./farm-recovery.ts";

describe("bounded recovery effect records", () => {
  const maximum = 128 * 1024;
  let root: string, run: string, effect: string;
  const identity = "a".repeat(40);
  const git = async (args: string[]) => args.includes("--git-common-dir")
    ? { code: 0, stdout: root } : { code: 0, stdout: identity };
  const record = () => ({ schema: 1, runId: "bounded", taskId: "task-a", repository: root,
    branch: "farm/task-a", integration: "farm/integration", worktree: "unused", attempt: 1,
    stage: "settled", candidate: { commit: identity, tree: identity },
    integrationAfter: { commit: identity, tree: identity },
    runCleanup: { verified: true, failures: [] }, result: { status: "green" }, padding: "" });
  const receipts = async () => (await readdir(run)).filter(name => name.startsWith("farm-recovered-"));
  beforeEach(async () => {
    root = await realpath(await mkdtemp(path.join(tmpdir(), "ca-farm-bounded-")));
    run = path.join(root, "runs", "bounded");
    await mkdir(path.join(run, "effects"), { recursive: true });
    effect = path.join(run, "effects", "task-a.json");
    probe.wholeReads = 0; probe.readBytes = 0; probe.beforeRead = undefined;
  });
  afterEach(async () => { await rm(root, { recursive: true, force: true }); });

  it("refuses a known oversized file without an unbounded or payload read", async () => {
    await writeFile(effect, " ".repeat(maximum + 1));
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/oversized/);
    expect(probe.wholeReads).toBe(0);
    expect(probe.readBytes).toBe(0);
    expect(await receipts()).toEqual([]);
  });
  it("applies the limit to UTF-8 bytes rather than decoded characters", async () => {
    await writeFile(effect, JSON.stringify({ ...record(), padding: "é".repeat(maximum / 2) }));
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/oversized/);
    expect(probe.wholeReads).toBe(0);
    expect(await receipts()).toEqual([]);
  });
  it("preserves exact-limit valid receipt, refs and cleanup semantics", async () => {
    const data = record();
    data.padding = "x".repeat(maximum - Buffer.byteLength(JSON.stringify(data)));
    const bytes = JSON.stringify(data);
    expect(Buffer.byteLength(bytes)).toBe(maximum);
    await writeFile(effect, bytes);
    const receipt = await recoverReceipt(run, "bounded", git);
    expect(receipt.results).toMatchObject([{ status: "green", merge: "observed", cleanup: "recorded-verified", author: "not-invoked" }]);
    expect(probe.wholeReads).toBe(0);
    expect(probe.readBytes).toBe(maximum);
    expect(await readFile(effect, "utf8")).toBe(bytes);
    expect(await receipts()).toHaveLength(1);
  });
  it("bounds and refuses actual file growth during the read", async () => {
    await writeFile(effect, JSON.stringify(record()));
    probe.beforeRead = () => appendFile(effect, " ".repeat(maximum * 2));
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/oversized|changed/);
    expect(probe.wholeReads).toBe(0);
    expect(probe.readBytes).toBeLessThanOrEqual(maximum + 1);
    expect(await receipts()).toEqual([]);
  });
  it("refuses a path replacement while the original descriptor is open", async () => {
    await writeFile(effect, JSON.stringify(record()));
    probe.beforeRead = async () => {
      await rename(effect, effect + ".retained");
      await writeFile(effect, JSON.stringify(record()));
    };
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/changed/);
    expect(await receipts()).toEqual([]);
  });
  it("refuses a hard-linked effect entry before reading content", async () => {
    const original = path.join(root, "retained.json");
    await writeFile(original, JSON.stringify(record())); await link(original, effect);
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/regular|unsafe/);
    expect(probe.wholeReads).toBe(0); expect(probe.readBytes).toBe(0);
    expect(await receipts()).toEqual([]);
  });
  it("refuses a directory or junction effect entry before reading content", async () => {
    const original = path.join(root, "retained-directory"); await mkdir(original);
    await symlink(original, effect, process.platform === "win32" ? "junction" : "dir");
    await expect(recoverReceipt(run, "bounded", git)).rejects.toThrow(/regular|unsafe|path/);
    expect(probe.wholeReads).toBe(0); expect(probe.readBytes).toBe(0);
    expect(await receipts()).toEqual([]);
  });
});
