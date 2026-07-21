import { describe, expect, test, vi } from "vitest";

import {
  ACTIVITY_POLICY,
  createSessionActivityRegistry,
  publishActivity,
} from "../src/activity.ts";

describe("Pi session activity registry", () => {
  test("projects bounded active and recent dispatch and job activity", () => {
    let now = 1_000;
    const activity = createSessionActivityRegistry({
      now: () => now,
      maxActive: 2,
      maxRecent: 2,
      activeTtlMs: 10_000,
      recentTtlMs: 5_000,
    })!;

    activity.publish({ kind: "child", id: "dispatch-1", label: "reviewer", state: "active" });
    now += 1_000;
    activity.publish({ kind: "job", id: "job-1", label: "tests", state: "active" });
    now += 1_000;
    activity.publish({ kind: "child", id: "dispatch-2", label: "author", state: "active" });

    expect(activity.snapshot()).toEqual([
      { kind: "child", label: "author", state: "active", ageSeconds: 0 },
      { kind: "job", label: "tests", state: "active", ageSeconds: 1 },
    ]);

    now += 1_000;
    activity.publish({ kind: "job", id: "job-1", label: "tests", state: "completed" });
    now += 1_000;
    activity.publish({ kind: "child", id: "dispatch-2", label: "author", state: "completed" });
    now += 1_000;
    activity.publish({ kind: "job", id: "job-2", label: "lint", state: "completed" });

    expect(activity.snapshot()).toEqual([
      { kind: "job", label: "lint", state: "completed", ageSeconds: 0 },
      { kind: "child", label: "author", state: "completed", ageSeconds: 1 },
    ]);
  });

  test("evicts stale events, treats completion as a transition, and isolates disposed sessions", () => {
    let now = 5_000;
    const first = createSessionActivityRegistry({
      now: () => now,
      activeTtlMs: 2_000,
      recentTtlMs: 1_000,
    })!;
    first.publish({ kind: "child", id: "same", label: "review", state: "active" });
    first.publish({ kind: "child", id: "same", label: "review", state: "completed" });
    expect(first.snapshot()).toHaveLength(1);
    first.publish({ kind: "child", id: "same", label: "stale reactivation", state: "active" });
    expect(first.snapshot()).toEqual([
      { kind: "child", label: "review", state: "completed", ageSeconds: 0 },
    ]);

    now += 1_001;
    expect(first.snapshot()).toEqual([]);
    first.dispose();
    first.publish({ kind: "job", id: "late", label: "late", state: "active" });
    expect(first.snapshot()).toEqual([]);

    const second = createSessionActivityRegistry({ now: () => now })!;
    expect(second.snapshot()).toEqual([]);
  });

  test("sanitizes control text and never projects commands, environments, or output", () => {
    const activity = createSessionActivityRegistry()!;
    activity.publish({
      kind: "job",
      id: "job-1",
      label: "\u001b[31mrun\nsecret\u202esecret",
      state: "active",
      command: "never",
      env: { TOKEN: "never" },
      output: "never",
    } as never);

    const snapshot = activity.snapshot();
    expect(snapshot).toEqual([{ kind: "job", label: "runsecretsecret", state: "active", ageSeconds: 0 }]);
    expect(JSON.stringify(snapshot)).not.toMatch(/TOKEN|never/u);
    expect(JSON.stringify(snapshot)).not.toMatch(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e]/u);
    expect(ACTIVITY_POLICY.maxLabelCodePoints).toBeLessThanOrEqual(128);
  });

  test("rejects proxy and accessor events without evaluating hostile fields", () => {
    const activity = createSessionActivityRegistry()!;
    let idReads = 0;
    const accessor = {
      kind: "job",
      label: "hidden",
      state: "active",
    } as Record<string, unknown>;
    Object.defineProperty(accessor, "id", {
      enumerable: true,
      get: () => { idReads += 1; return idReads < 4 ? "ok" : "x".repeat(1_000_000); },
    });

    activity.publish(accessor as never);
    activity.publish(new Proxy({ kind: "job", id: "proxy", label: "hidden", state: "active" }, {}) as never);

    expect(idReads).toBe(0);
    expect(activity.snapshot()).toEqual([]);
  });

  test("rejects invalid construction and contains hostile publishers", () => {
    expect(createSessionActivityRegistry({ maxActive: 0 })).toBeUndefined();
    expect(createSessionActivityRegistry({ maxRecent: Number.POSITIVE_INFINITY })).toBeUndefined();
    const hostile = { publish: vi.fn(() => { throw new Error("activity unavailable"); }) };
    expect(() => publishActivity(hostile, {
      kind: "child", id: "dispatch-1", label: "review", state: "active",
    })).not.toThrow();
  });

  test("requests a render on transitions without allowing render failure to escape", () => {
    const onChange = vi.fn(() => { throw new Error("render unavailable"); });
    const activity = createSessionActivityRegistry({ onChange })!;
    expect(() => activity.publish({ kind: "job", id: "1", label: "tests", state: "active" })).not.toThrow();
    expect(() => activity.publish({ kind: "job", id: "1", label: "tests", state: "completed" })).not.toThrow();
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(activity.snapshot()).toMatchObject([{ state: "completed" }]);
  });
});
