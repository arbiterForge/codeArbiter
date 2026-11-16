import { describe, expect, test, vi } from "vitest";
import { resolve } from "node:path";
import { appendAuditLineWithIo, NODE_AUDIT_SINK_IO, type AuditSinkIoPort, type AuditSinkStatsPort } from "../src/audit-sink.ts";

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
