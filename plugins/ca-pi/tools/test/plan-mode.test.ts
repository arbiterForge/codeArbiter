import { createHash } from "node:crypto";
import { describe, expect, test } from "vitest";
import type { BridgePort, BridgeRequest, BridgeResponse } from "../src/contracts.ts";
import {
  PLAN_SESSION_ENTRY_TYPE,
  approvePlan,
  cancelPlan,
  encodePlanSessionState,
  enterPlan,
  operatePlanFile,
  parsePlanLedger,
  reconcilePlanState,
  restorePlanSessionState,
  transitionPlanTask,
  updatePlanLedger,
  type PlanSessionState,
} from "../src/plan-mode.ts";

const ledger = (rows: readonly string[]) => [
  "# Example plan",
  "",
  "| Task | Deliverable | Status |",
  "|---|---|---|",
  ...rows,
  "",
].join("\n");

const baseLedger = ledger([
  "| T-01 | First task | PENDING |",
  "| T-02 | Second task | IN-PROGRESS |",
  "| T-03 | Third task | ACCEPTED |",
]);

function customEntry(data: unknown): Record<string, unknown> {
  return {
    type: "custom", id: "entry-1", parentId: null,
    timestamp: "2026-07-19T00:00:00.000Z",
    customType: PLAN_SESSION_ENTRY_TYPE, data,
  };
}

describe("plan session state and canonical ledger", () => {
  test("enters plan mode with stable bounded task IDs and one canonical plan/ledger path", () => {
    const state = enterPlan("example-plan", baseLedger);
    expect(state).toEqual({
      version: 1,
      revision: 1,
      mode: "plan",
      activePlan: {
        slug: "example-plan",
        specPath: ".codearbiter/specs/example-plan.md",
        planPath: ".codearbiter/plans/example-plan.md",
        ledgerPath: ".codearbiter/plans/example-plan.md",
        disposition: "draft",
        tasks: [
          { id: "T-01", status: "PENDING" },
          { id: "T-02", status: "IN_PROGRESS" },
          { id: "T-03", status: "ACCEPTED" },
        ],
      },
    });
    expect(parsePlanLedger(baseLedger)).toEqual(state?.activePlan?.tasks);
  });

  test("rejects ambiguous, duplicate, controlled, oversized, and unsupported status ledgers", () => {
    expect(parsePlanLedger(ledger(["| T-01 | One | PENDING |", "| T-01 | Two | ACCEPTED |"])) ).toBeUndefined();
    expect(parsePlanLedger(ledger(["| bad id | One | PENDING |"])) ).toBeUndefined();
    expect(parsePlanLedger(ledger(["| T-01\u0000 | One | PENDING |"])) ).toBeUndefined();
    expect(parsePlanLedger(ledger(["| T-01 | One | MAGIC |"])) ).toBeUndefined();
    expect(parsePlanLedger(`| Task | Status | Status |\n|---|---|---|\n| T-01 | PENDING | ACCEPTED |\n`)).toBeUndefined();
    expect(parsePlanLedger("x".repeat(524_289))).toBeUndefined();
    expect(enterPlan("../escape", baseLedger)).toBeUndefined();
    expect(enterPlan("x".repeat(129), baseLedger)).toBeUndefined();
  });

  test("enforces forward task transitions without renumbering or inventing tasks", () => {
    const state = enterPlan("example-plan", baseLedger)!;
    const started = transitionPlanTask(state, "T-01", "IN_PROGRESS")!;
    const accepted = transitionPlanTask(started, "T-01", "ACCEPTED")!;
    expect(accepted.revision).toBe(3);
    expect(accepted.activePlan?.tasks.map((task) => task.id)).toEqual(["T-01", "T-02", "T-03"]);
    expect(transitionPlanTask(accepted, "T-01", "PENDING")).toBeUndefined();
    expect(transitionPlanTask(state, "T-99", "IN_PROGRESS")).toBeUndefined();
    expect(transitionPlanTask(state, "T-01", "ACCEPTED")?.activePlan?.tasks[0]?.status).toBe("ACCEPTED");
  });

  test("updates only the canonical status cell and supports escaped table pipes", () => {
    const source = "# Exact\r\n\r\n| Task  | Deliverable                 |  Status   | Note |\n"
      + "|:------|:----------------------------|-----------:|:-----|\r\n"
      + "| T-01  | First \\| detailed task    |  PENDING  |  keep   |\n"
      + "| T-02  | Second task                 | IN-PROGRESS | keep |\r\n";
    expect(parsePlanLedger(source)).toEqual([
      { id: "T-01", status: "PENDING" },
      { id: "T-02", status: "IN_PROGRESS" },
    ]);
    const updated = updatePlanLedger(source, "T-01", "IN_PROGRESS")!;
    const expected = source.replace("PENDING", "IN-PROGRESS");
    expect(Buffer.from(updated)).toEqual(Buffer.from(expected));
    expect(updatePlanLedger(updated, "T-01", "PENDING")).toBeUndefined();
    expect(updatePlanLedger(source, "T-99", "ACCEPTED")).toBeUndefined();

    const nbsp = "| Task | Status |\n|---|---|\n| T-01 |\u00a0PENDING\u00a0|\n";
    expect(updatePlanLedger(nbsp, "T-01", "ACCEPTED")).toBe(
      "| Task | Status |\n|---|---|\n| T-01 |\u00a0ACCEPTED\u00a0|\n",
    );
  });

  test("approve and cancel return to execute while only approval changes disposition", () => {
    const state = enterPlan("example-plan", baseLedger)!;
    expect(approvePlan(state)).toMatchObject({ mode: "execute", activePlan: { disposition: "approved" } });
    expect(cancelPlan(state)).toMatchObject({ mode: "execute", activePlan: { disposition: "draft" } });
    expect(cancelPlan(state)?.activePlan?.tasks).toEqual(state.activePlan?.tasks);
    expect(approvePlan(approvePlan(state)!)).toBeUndefined();
  });

  test("disk status cells are the source of truth during deterministic reconciliation", () => {
    const state = transitionPlanTask(enterPlan("example-plan", baseLedger)!, "T-01", "ACCEPTED")!;
    const disk = ledger([
      "| T-01 | First task | IN-PROGRESS |",
      "| T-02 | Second task | ACCEPTED — receipt |",
      "| T-03 | Third task | ACCEPTED |",
    ]);
    const reconciled = reconcilePlanState(state, disk)!;
    expect(reconciled.activePlan?.tasks).toEqual([
      { id: "T-01", status: "IN_PROGRESS" },
      { id: "T-02", status: "ACCEPTED" },
      { id: "T-03", status: "ACCEPTED" },
    ]);
    expect(reconciled.revision).toBe(state.revision);
    expect(reconcilePlanState(state, ledger(["| T-99 | Different | PENDING |"])) ).toBeUndefined();
  });

  test("accepts the canonical literal em-dash receipt and bounds bridge-consumable ledgers", () => {
    expect(parsePlanLedger("| Task | Status |\n|---|---|\n| T-01 | ACCEPTED — receipt |\n"))
      .toEqual([{ id: "T-01", status: "ACCEPTED" }]);
    expect(parsePlanLedger(`| Task | Status |\n|---|---|\n| T-01 | PENDING |\n${"x".repeat(92_161)}`))
      .toBeUndefined();
  });
});
describe("bounded Pi custom session entries", () => {
  test("round-trips the latest custom entry and reconciles it with disk", () => {
    const older = enterPlan("example-plan", baseLedger)!;
    const newer = transitionPlanTask(older, "T-01", "ACCEPTED")!;
    const encoded = encodePlanSessionState(newer)!;
    expect(JSON.stringify(encoded).length).toBeLessThanOrEqual(16_384);
    const restored = restorePlanSessionState([
      { type: "message", message: "ignored" },
      customEntry(encodePlanSessionState(older)),
      customEntry(encoded),
    ], baseLedger);
    expect(restored?.activePlan?.tasks[0]?.status).toBe("PENDING");
    expect(restored?.revision).toBe(newer.revision);
  });

  test("fails closed on a malformed latest matching entry instead of rolling back", () => {
    const valid = encodePlanSessionState(enterPlan("example-plan", baseLedger)!)!;
    expect(restorePlanSessionState([customEntry(valid), customEntry({ ...valid, mode: "admin" })], baseLedger)).toBeUndefined();
    expect(restorePlanSessionState(new Proxy([], {}), baseLedger)).toBeUndefined();

    const accessor = customEntry(valid);
    Object.defineProperty(accessor, "data", { enumerable: true, get: () => valid });
    expect(restorePlanSessionState([accessor], baseLedger)).toBeUndefined();

    const hostileData = { ...valid };
    Object.defineProperty(hostileData, "mode", { enumerable: true, get: () => "plan" });
    expect(restorePlanSessionState([customEntry(hostileData)], baseLedger)).toBeUndefined();
    expect(restorePlanSessionState([customEntry(new Proxy(valid, {}))], baseLedger)).toBeUndefined();
  });

  test("rejects controls, oversized collections, unsafe keys, and invalid revisions", () => {
    const valid = encodePlanSessionState(enterPlan("example-plan", baseLedger)!)! as unknown as Record<string, unknown>;
    expect(restorePlanSessionState([customEntry({ ...valid, revision: -1 })], baseLedger)).toBeUndefined();
    expect(restorePlanSessionState([customEntry({ ...valid, extra: true })], baseLedger)).toBeUndefined();
    expect(restorePlanSessionState([customEntry({ ...valid, activePlan: { ...(valid.activePlan as object), slug: "bad\u0000slug" } })], baseLedger)).toBeUndefined();
    expect(restorePlanSessionState([customEntry({ ...valid, activePlan: { ...(valid.activePlan as object), tasks: Array(257).fill({ id: "T-01", status: "PENDING" }) } })], baseLedger)).toBeUndefined();
  });

  test("never admits a runtime state that exceeds the custom-entry byte bound", () => {
    const rows = Array.from({ length: 256 }, (_, index) => {
      const suffix = String(index).padStart(3, "0");
      const id = `T${suffix}${"x".repeat(60)}`;
      return `| ${id} | bounded-state repro | PENDING |`;
    });
    expect(parsePlanLedger(ledger(rows))).toHaveLength(256);
    expect(enterPlan("example-plan", ledger(rows))).toBeUndefined();
  });

  test("rejects plan-mode approved state and lone carriage-return ledger controls", () => {
    const valid = encodePlanSessionState(enterPlan("example-plan", baseLedger)!)! as unknown as Record<string, unknown>;
    expect(restorePlanSessionState([customEntry({
      ...valid,
      activePlan: { ...(valid.activePlan as object), disposition: "approved" },
    })], baseLedger)).toBeUndefined();
    expect(parsePlanLedger(baseLedger.replace("First", "First\rbroken"))).toBeUndefined();
  });
});


function digest(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

function bridgeResponse(planFile: Record<string, unknown>): BridgeResponse {
  const output = { ...planFile };
  if (output.status === "committed" && output.observed === undefined) output.observed = true;
  if (Object.hasOwn(output, "content")) {
    const content = output.content;
    delete output.content;
    output.contentBase64 = content === null ? null : Buffer.from(String(content), "utf8").toString("base64");
  }
  return { version: 1, outcome: "notice", auditCode: "PI_PLAN_FILE", resultPatch: { planFile: output } };
}

class FakeBridge implements BridgePort {
  readonly calls: BridgeRequest[] = [];
  constructor(private readonly responses: BridgeResponse[]) {}
  async call(request: BridgeRequest): Promise<BridgeResponse> {
    this.calls.push(request);
    const response = this.responses.shift();
    if (response === undefined) throw new Error("unexpected bridge call");
    return response;
  }
}

describe("canonical plan-file bridge operations", () => {
  test("uses only slug+kind for read then CAS replace and returns committed bridge bytes", async () => {
    const old = "# Example spec\n";
    const wanted = "# Revised spec\n";
    const bridge = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: true, hash: digest(old), content: old }),
      bridgeResponse({ status: "committed", exists: true, hash: digest(wanted), content: wanted, directoryDurable: false }),
    ]);
    const state = enterPlan("example-plan", baseLedger)!;
    const result = await operatePlanFile(
      state, "C:/repo", state.activePlan.specPath, { kind: "replace", content: wanted }, bridge,
    );
    expect(result).toEqual({ ok: true, content: wanted, state });
    expect(bridge.calls.map((call) => call.input)).toEqual([
      { slug: "example-plan", kind: "spec", action: "read" },
      { slug: "example-plan", kind: "spec", action: "replace", expectedHash: digest(old),
        contentBase64: Buffer.from(wanted, "utf8").toString("base64") },
    ]);
    expect(JSON.stringify(bridge.calls)).not.toContain(".codearbiter");
  });

  test("reads the canonical plan, transitions through shared state logic, and increments revision", async () => {
    const wanted = updatePlanLedger(baseLedger, "T-01", "IN_PROGRESS")!;
    const bridge = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: true, hash: digest(baseLedger), content: baseLedger }),
      bridgeResponse({ status: "committed", exists: true, hash: digest(wanted), content: wanted, directoryDurable: true }),
    ]);
    const state = enterPlan("example-plan", baseLedger)!;
    const result = await operatePlanFile(
      state, "C:/repo", state.activePlan.planPath,
      { kind: "transition", taskId: "T-01", status: "IN_PROGRESS" }, bridge,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.content).toBe(wanted);
    expect(result.state.revision).toBe(state.revision + 1);
    expect(result.state.activePlan.tasks[0]).toEqual({ id: "T-01", status: "IN_PROGRESS" });
  });

  test("supports bridge-owned exclusive creation only for replace", async () => {
    const wanted = "# New spec\n";
    const bridge = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: false, hash: null, content: "" }),
      bridgeResponse({ status: "committed", exists: true, hash: digest(wanted), content: wanted, directoryDurable: false }),
    ]);
    const state = enterPlan("example-plan", baseLedger)!;
    await expect(operatePlanFile(
      state, "C:/repo", state.activePlan.specPath, { kind: "replace", content: wanted }, bridge,
    )).resolves.toMatchObject({ ok: true, content: wanted });
    expect(bridge.calls[1]?.input).toMatchObject({ expectedHash: null });
  });

  test("surfaces committed-but-changed and reconciles parseable observed plan bytes", async () => {
    const wanted = updatePlanLedger(baseLedger, "T-01", "IN_PROGRESS")!;
    const observed = updatePlanLedger(baseLedger, "T-01", "ACCEPTED")!;
    const bridge = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: true, hash: digest(baseLedger), content: baseLedger }),
      bridgeResponse({ status: "committed", observed: true, exists: true, hash: digest(observed),
        content: observed, directoryDurable: false, postCommitDiagnostic: "postcommit_changed" }),
    ]);
    const state = enterPlan("example-plan", baseLedger)!;
    const result = await operatePlanFile(
      state, "C:/repo", state.activePlan.planPath,
      { kind: "transition", taskId: "T-01", status: "IN_PROGRESS" }, bridge,
    );
    expect(result).toMatchObject({ ok: false, committed: true, content: observed });
    if (result.ok || !("state" in result) || result.state === undefined) return;
    expect(result.state.revision).toBe(state.revision + 1);
    expect(result.state.activePlan.tasks[0]).toEqual({ id: "T-01", status: "ACCEPTED" });
    expect(wanted).not.toBe(observed);
  });

  test("fails closed on conflict, malformed hashes/content, missing reads, and unrelated state paths", async () => {
    const state = enterPlan("example-plan", baseLedger)!;
    const missing = new FakeBridge([bridgeResponse({ status: "unchanged", exists: false, hash: null, content: "" })]);
    await expect(operatePlanFile(
      state, "C:/repo", state.activePlan.specPath, { kind: "read" }, missing,
    )).resolves.toEqual({ ok: false });

    const conflict = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: true, hash: digest("# old\n"), content: "# old\n" }),
      bridgeResponse({ status: "conflict" }),
    ]);
    await expect(operatePlanFile(
      state, "C:/repo", state.activePlan.specPath, { kind: "replace", content: "# new\n" }, conflict,
    )).resolves.toEqual({ ok: false });

    const malformed = new FakeBridge([
      bridgeResponse({ status: "unchanged", exists: true, hash: "0".repeat(64), content: "# mismatch\n" }),
    ]);
    await expect(operatePlanFile(
      state, "C:/repo", state.activePlan.specPath, { kind: "read" }, malformed,
    )).resolves.toEqual({ ok: false });

    const untouched = new FakeBridge([]);
    await expect(operatePlanFile(
      state, "C:/repo", ".codearbiter/open-tasks.md", { kind: "read" }, untouched,
    )).resolves.toEqual({ ok: false });
    expect(untouched.calls).toEqual([]);
  });

  test("requires active plan mode and exact canonical target identity", async () => {
    const plan = enterPlan("example-plan", baseLedger)!;
    const execute = cancelPlan(plan)!;
    const bridge = new FakeBridge([]);
    await expect(operatePlanFile(
      execute, "C:/repo", plan.activePlan.planPath, { kind: "read" }, bridge,
    )).resolves.toEqual({ ok: false });
    await expect(operatePlanFile(
      { ...plan, mode: "unknown" } as unknown as PlanSessionState,
      "C:/repo", plan.activePlan.planPath, { kind: "read" }, bridge,
    )).resolves.toEqual({ ok: false });
    expect(bridge.calls).toEqual([]);
  });
});
