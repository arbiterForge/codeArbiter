import { spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, expect, test, vi } from "vitest";
import { readWorkflowRecoverySnapshot, resolvePythonCommand, workflowRecoveryResult } from "../src/bridge.ts";
import type { BridgePort, BridgeResponse, PiWorkflowRecoverySnapshot } from "../src/contracts.ts";

const page: PiWorkflowRecoverySnapshot = { status: "partial", revision: 9, pending: 3, claimed: 1,
  unavailable: 2, cursor: "bmV4dA==", bytesRead: 262144, reason: null,
  notice: "Inventory is partial; unscanned obligations are unknown.", fingerprint: "a".repeat(64) };
function response(value: unknown = page): BridgeResponse {
  return { version: 1, outcome: "notice", auditCode: "PI_WORKFLOW_RECOVERY", resultPatch: { workflowRecovery: value } };
}
afterEach(() => vi.useRealTimers());

test("closed snapshot keeps partial-page counts, opaque cursor and uncertainty", () => {
  expect(workflowRecoveryResult(response())).toEqual(page);
  expect(Object.isFrozen(workflowRecoveryResult(response()))).toBe(true);
  expect(workflowRecoveryResult(response({ ...page, status: "unavailable", reason: "uncertain-effect", cursor: null })))
    .toMatchObject({ status: "unavailable", reason: "uncertain-effect" });
  expect(workflowRecoveryResult(response({ ...page, status: "absent", revision: null, pending: 0, claimed: 0, unavailable: 0, cursor: null, notice: "" })))
    .toMatchObject({ status: "absent", notice: "" });
});

test.each([
  { status: "absent", cursor: null }, { notice: "" }, { status: "unavailable", cursor: null, notice: "" },
  { pending: 33 }, { pending: -1 }, { pending: 0.5 }, { pending: 30, claimed: 3 }, { revision: 10000000001 },
  { bytesRead: 262145 }, { bytesRead: -1 }, { status: "clean" }, { cursor: null }, { cursor: "../file" },
  { cursor: "a".repeat(257) }, { status: "complete" }, { status: "absent" }, { reason: "explicit-stop" },
  { reason: "arbitrary" }, { notice: "x".repeat(769) }, { notice: "bad\u001bnotice" },
  { fingerprint: "A".repeat(64) }, { fingerprint: "grant" }, { grant: true },
])("malformed snapshot is unknown, never clear: %j", (delta) => {
  expect(workflowRecoveryResult(response({ ...page, ...delta }))).toBeUndefined();
});

test("rejects foreign envelope/patch and child-authored context fields", () => {
  for (const value of [ { ...response(), auditCode: "other" }, { ...response(), context: "approved" },
    { ...response(), resultPatch: { workflowRecovery: page, grant: true } }, { ...response(), outcome: "allow" as const } ]) {
    expect(workflowRecoveryResult(value)).toBeUndefined();
  }
});

test("trusted enabled reader uses only fixed event/cwd/session, rechecks trust after reply", async () => {
  const calls: unknown[] = []; let trusted = true;
  const bridge: BridgePort = { call: async (request) => { calls.push(request); return response(); } };
  const context = { cwd: "C:/work", signal: undefined, isProjectTrusted: () => trusted,
    sessionManager: { getSessionId: () => "session" } };
  expect(await readWorkflowRecoverySnapshot(bridge, context, { enabled: true })).toEqual(page);
  expect(calls).toEqual([{ version: 1, event: "workflow_recovery_snapshot", cwd: "C:/work", sessionId: "session" }]);
  calls.length = 0;
  for (const candidate of [ { ...context, isProjectTrusted: undefined }, { ...context, isProjectTrusted: () => false },
    { ...context, isProjectTrusted: () => { throw Error("trust"); } } ]) {
    expect(await readWorkflowRecoverySnapshot(bridge, candidate, { enabled: true })).toBeUndefined();
  }
  expect(await readWorkflowRecoverySnapshot(bridge, context, { enabled: false })).toBeUndefined();
  expect(calls).toEqual([]);
  const changing: BridgePort = { call: async () => { trusted = false; return response(); } };
  expect(await readWorkflowRecoverySnapshot(changing, context, { enabled: true })).toBeUndefined();
});

test("one-second observation deadline aborts existing bridge cleanup without waiting for an unresponsive observer", async () => {
  vi.useFakeTimers(); let signal: AbortSignal | undefined;
  const bridge: BridgePort = { call: async (_request, observed) => { signal = observed; return await new Promise(() => {}); } };
  const result = readWorkflowRecoverySnapshot(bridge, { cwd: "C:/work", signal: undefined, isProjectTrusted: () => true }, { enabled: true });
  await vi.advanceTimersByTimeAsync(1000);
  expect(await result).toBeUndefined(); expect(signal?.aborted).toBe(true);
});

test("actual owning Python read-only projection crosses the TypeScript codec without fabricating empty recovery", async () => {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-recovery-codec-"));
  try {
    const script = "import sys,json;sys.path.insert(0,sys.argv[1]);import _workflowrecoverylib as w;print(json.dumps(w.snapshot(sys.argv[2])))";
    const python = resolvePythonCommand(process.platform, undefined, tmpdir(), root);
    const actual = spawnSync(python.executable,
      [...python.prefixArgs, "-c", script, fileURLToPath(new URL("../../hooks", import.meta.url)), root], { encoding: "utf8", timeout: 3000,
        env: { ...Object.fromEntries(["SystemRoot", "WINDIR", "TEMP", "TMP", "PATH"].flatMap((key) => process.env[key] === undefined ? [] : [[key, process.env[key]]])),
          PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1" } });
    expect(actual.status, actual.stderr).toBe(0);
    const decoded = workflowRecoveryResult(response(JSON.parse(actual.stdout)));
    expect(decoded).toMatchObject({ status: "absent", pending: 0, claimed: 0, unavailable: 0, notice: "" });
  } finally { await rm(root, { recursive: true, force: true }); }
});
