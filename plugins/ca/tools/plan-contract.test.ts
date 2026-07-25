/**
 * plan-contract.test.ts — the farm plan handoff contract.
 *
 * Two issues share this surface:
 *
 *  #412 — the runtime boundary. `main()` used to do
 *  `JSON.parse(...) as Plan` and hand the result straight to `validate()`,
 *  which dereferences `plan.meta` and iterates `plan.tasks` with no shape
 *  check. `parsePlan()` is the exact runtime validator that closes that hole,
 *  and PLAN_SHAPE is the single declarative description both it and the
 *  schema-parity test read.
 *
 *  #391 — setup phases. `resetWorktree` is `git reset --hard` + `git clean -fd`
 *  (no `-x`), which PRESERVES ignored paths, so a gitignored dependency tree
 *  survives the inter-attempt reset. `setup` must therefore run ONCE per
 *  worktree, with an explicit `setupEachAttempt` phase for commands that
 *  genuinely must rerun, and `setupInputs` fingerprinting for the case where
 *  the baseline moves under the worktree (regenerate-on-conflict).
 */
import { describe, it, expect } from "vitest";
import path from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parsePlan, PLAN_SHAPE, validate, runTask } from "./farm.ts";
import type { Task, RunTaskDeps, Worker, WorkerResult } from "./farm.ts";

const validPlan = () => ({
  meta: { name: "p" },
  tasks: [
    {
      id: "task-a",
      description: "make the test pass",
      filesInScope: ["src/a.ts"],
      test: { path: "src/a.test.ts" },
      gate: { commands: ["node -p 0"] },
    },
  ],
});

// ---------------------------------------------------------------------------
// #412 — parsePlan: the runtime schema check at the JSON boundary
// ---------------------------------------------------------------------------
describe("#412 parsePlan — rejects malformed plans before any field access", () => {
  it("accepts a minimal valid plan and returns it", () => {
    const p = validPlan();
    expect(parsePlan(p)).toBe(p);
  });

  it("accepts every optional field declared by the schema", () => {
    expect(() =>
      parsePlan({
        meta: {
          name: "p",
          repo: "r",
          model: "m",
          apiBaseUrl: "https://api.example/v1",
          setup: ["npm ci"],
          setupEachAttempt: ["npm run build"],
          setupInputs: ["package-lock.json"],
        },
        tasks: [
          {
            ...validPlan().tasks[0],
            deps: [],
            context: "ctx",
            model: "m2",
            maxRetries: 0,
            setup: ["npm ci"],
            setupEachAttempt: ["npm run build"],
            setupInputs: ["package-lock.json"],
          },
        ],
      }),
    ).not.toThrow();
  });

  it("rejects null instead of throwing a raw TypeError", () => {
    expect(() => parsePlan(null)).toThrow(/plan must be a JSON object/);
  });

  it("rejects an array root", () => {
    expect(() => parsePlan([])).toThrow(/plan must be a JSON object/);
  });

  it("rejects a scalar root", () => {
    expect(() => parsePlan(42)).toThrow(/plan must be a JSON object/);
  });

  it("rejects {} — meta and tasks are required", () => {
    expect(() => parsePlan({})).toThrow(/plan\.meta.*required/);
  });

  it("rejects a missing tasks array", () => {
    expect(() => parsePlan({ meta: { name: "p" } })).toThrow(/plan\.tasks.*required/);
  });

  it("rejects a null meta", () => {
    expect(() => parsePlan({ meta: null, tasks: validPlan().tasks })).toThrow(/plan\.meta/);
  });

  it("rejects meta without a name", () => {
    expect(() => parsePlan({ meta: {}, tasks: validPlan().tasks })).toThrow(/plan\.meta\.name.*required/);
  });

  it("rejects a non-string meta.name", () => {
    expect(() => parsePlan({ meta: { name: 7 }, tasks: validPlan().tasks })).toThrow(
      /plan\.meta\.name must be a string/,
    );
  });

  it("rejects an empty tasks array (schema minItems: 1)", () => {
    expect(() => parsePlan({ meta: { name: "p" }, tasks: [] })).toThrow(/plan\.tasks.*at least one/);
  });

  it("rejects a non-array tasks", () => {
    expect(() => parsePlan({ meta: { name: "p" }, tasks: {} })).toThrow(/plan\.tasks/);
  });

  it("rejects a non-object task entry", () => {
    expect(() => parsePlan({ meta: { name: "p" }, tasks: [null] })).toThrow(/plan\.tasks\[0\]/);
  });

  it("rejects a numeric task id (SAFE_TASK_ID assumed a string)", () => {
    const p = validPlan();
    (p.tasks[0] as Record<string, unknown>).id = 7;
    expect(() => parsePlan(p)).toThrow(/plan\.tasks\[0\]\.id must be a string/);
  });

  it("rejects a numeric task description", () => {
    const p = validPlan();
    (p.tasks[0] as Record<string, unknown>).description = 7;
    expect(() => parsePlan(p)).toThrow(/plan\.tasks\[0\]\.description must be a string/);
  });

  it("rejects an unknown root property", () => {
    expect(() => parsePlan({ ...validPlan(), bogus: 1 })).toThrow(/plan: unknown property "bogus"/);
  });

  it("rejects an unknown meta property", () => {
    expect(() => parsePlan({ meta: { name: "p", bogus: 1 }, tasks: validPlan().tasks })).toThrow(
      /plan\.meta: unknown property "bogus"/,
    );
  });

  it("rejects an unknown task property", () => {
    const p = validPlan();
    (p.tasks[0] as Record<string, unknown>).bogus = 1;
    expect(() => parsePlan(p)).toThrow(/plan\.tasks\[0\]: unknown property "bogus"/);
  });

  it("rejects an unknown test/gate property (nested closed objects)", () => {
    const a = validPlan();
    (a.tasks[0].test as Record<string, unknown>).bogus = 1;
    expect(() => parsePlan(a)).toThrow(/plan\.tasks\[0\]\.test: unknown property "bogus"/);
    const b = validPlan();
    (b.tasks[0].gate as Record<string, unknown>).bogus = 1;
    expect(() => parsePlan(b)).toThrow(/plan\.tasks\[0\]\.gate: unknown property "bogus"/);
  });

  it("rejects a non-string entry inside deps / filesInScope / gate.commands / setup", () => {
    const mk = (patch: Record<string, unknown>) => {
      const p = validPlan();
      Object.assign(p.tasks[0], patch);
      return p;
    };
    expect(() => parsePlan(mk({ deps: [7] }))).toThrow(/plan\.tasks\[0\]\.deps/);
    expect(() => parsePlan(mk({ filesInScope: [7] }))).toThrow(/plan\.tasks\[0\]\.filesInScope/);
    expect(() => parsePlan(mk({ gate: { commands: [7] } }))).toThrow(/plan\.tasks\[0\]\.gate\.commands/);
    expect(() => parsePlan(mk({ setup: [7] }))).toThrow(/plan\.tasks\[0\]\.setup/);
  });

  it("rejects empty filesInScope and empty gate.commands (schema minItems: 1)", () => {
    const p1 = validPlan();
    p1.tasks[0].filesInScope = [];
    expect(() => parsePlan(p1)).toThrow(/plan\.tasks\[0\]\.filesInScope.*at least one/);
    const p2 = validPlan();
    p2.tasks[0].gate.commands = [];
    expect(() => parsePlan(p2)).toThrow(/plan\.tasks\[0\]\.gate\.commands.*at least one/);
  });

  it("rejects a missing / non-object test and gate", () => {
    const p1 = validPlan();
    (p1.tasks[0] as Record<string, unknown>).test = "src/a.test.ts";
    expect(() => parsePlan(p1)).toThrow(/plan\.tasks\[0\]\.test/);
    const p2 = validPlan();
    delete (p2.tasks[0] as Record<string, unknown>).gate;
    expect(() => parsePlan(p2)).toThrow(/plan\.tasks\[0\]\.gate.*required/);
  });

  it("rejects a non-integer, fractional, or negative maxRetries", () => {
    const mk = (v: unknown) => {
      const p = validPlan();
      (p.tasks[0] as Record<string, unknown>).maxRetries = v;
      return p;
    };
    expect(() => parsePlan(mk("2"))).toThrow(/plan\.tasks\[0\]\.maxRetries must be an integer/);
    expect(() => parsePlan(mk(1.5))).toThrow(/plan\.tasks\[0\]\.maxRetries must be an integer/);
    expect(() => parsePlan(mk(-1))).toThrow(/plan\.tasks\[0\]\.maxRetries must be an integer >= 0/);
    expect(() => parsePlan(mk(NaN))).toThrow(/plan\.tasks\[0\]\.maxRetries must be an integer/);
    expect(() => parsePlan(mk(0))).not.toThrow();
  });

  it("names the offending task by INDEX, not by an unvalidated id", () => {
    const p = validPlan();
    p.tasks.push({ ...validPlan().tasks[0], id: "task-b", description: 7 as unknown as string });
    expect(() => parsePlan(p)).toThrow(/plan\.tasks\[1\]\.description/);
  });

  it("bounds its messages — an absurd key or value is never echoed whole", () => {
    const key = "z".repeat(5000);
    let msg = "";
    try {
      parsePlan({ ...validPlan(), [key]: 1 });
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    expect(msg).toMatch(/unknown property/);
    expect(msg.length).toBeLessThan(200);
    expect(msg).not.toContain(key);

    let msg2 = "";
    try {
      const p = validPlan();
      (p.tasks[0] as Record<string, unknown>).description = "q".repeat(5000);
      (p.tasks[0] as Record<string, unknown>).context = 7;
      parsePlan(p);
    } catch (e) {
      msg2 = e instanceof Error ? e.message : String(e);
    }
    expect(msg2.length).toBeLessThan(200);
  });

  it("hands validate() a plan it can safely dereference (no raw TypeError path left)", () => {
    // The composition main() performs: parsePlan first, then validate.
    expect(() => validate(parsePlan(validPlan()))).not.toThrow();
    expect(() => validate(null as never)).toThrow(); // validate alone is NOT the boundary
  });
});

// ---------------------------------------------------------------------------
// #412 — schema/validator/type parity.
//
// AUTHORITY: parsePlan (via PLAN_SHAPE) is the EXECUTED contract. plan.schema.json
// is the AUTHORING contract writing-plans validates against, and must mirror
// PLAN_SHAPE key-for-key and type-for-type. This test is what keeps them
// synchronized: adding a field on one side without the other fails here.
// ---------------------------------------------------------------------------
describe("#412 plan.schema.json <-> PLAN_SHAPE parity", () => {
  const schema = JSON.parse(
    readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "plan.schema.json"), "utf8"),
  );

  // schema sub-object -> PLAN_SHAPE key
  const pairs: Array<[string, Record<string, unknown>, keyof typeof PLAN_SHAPE]> = [
    ["root", schema, "plan"],
    ["meta", schema.properties.meta, "meta"],
    ["task", schema.$defs.task, "task"],
    ["task.test", schema.$defs.task.properties.test, "test"],
    ["task.gate", schema.$defs.task.properties.gate, "gate"],
  ];

  // How a schema property is spelled as a PLAN_SHAPE field type.
  function schemaTypeOf(prop: Record<string, any>): string {
    if (prop.$ref === "#/$defs/task") return "task";
    if (prop.type === "array") return `${schemaTypeOf(prop.items)}[]`;
    if (prop.type === "object") return "object";
    return String(prop.type);
  }

  for (const [label, node, shapeKey] of pairs) {
    const spec = PLAN_SHAPE[shapeKey];

    it(`${label}: property sets match exactly`, () => {
      expect(Object.keys(node.properties as object).sort()).toEqual(Object.keys(spec.props).sort());
    });

    it(`${label}: required sets match exactly`, () => {
      expect([...((node.required as string[]) ?? [])].sort()).toEqual([...spec.required].sort());
    });

    it(`${label}: is a closed object on both sides (additionalProperties:false)`, () => {
      expect(node.additionalProperties).toBe(false);
    });

    it(`${label}: every property's declared type matches`, () => {
      for (const [k, prop] of Object.entries(node.properties as Record<string, any>)) {
        const runtime = (spec.props as Record<string, string>)[k];
        // A nested object in PLAN_SHAPE is named by its sub-spec ("meta"/"test"/
        // "gate"/"task[]"); the schema spells those as object/$ref.
        const expected =
          runtime === "meta" || runtime === "test" || runtime === "gate" ? "object" : runtime;
        expect(`${label}.${k}: ${schemaTypeOf(prop)}`).toBe(`${label}.${k}: ${expected}`);
      }
    });
  }

  it("keeps minItems:1 on exactly the arrays parsePlan requires non-empty", () => {
    expect(schema.properties.tasks.minItems).toBe(1);
    expect(schema.$defs.task.properties.filesInScope.minItems).toBe(1);
    expect(schema.$defs.task.properties.gate.properties.commands.minItems).toBe(1);
    // …and NOT on the ones it accepts empty.
    expect(schema.$defs.task.properties.deps.minItems).toBeUndefined();
    expect(schema.properties.meta.properties.setup.minItems).toBeUndefined();
  });

  it("documents the one RATIFIED divergence: the id pattern", () => {
    // The schema's kebab-case `id` pattern is the narrower AUTHORING rule;
    // SAFE_TASK_ID (checked in validate()) is the broader runtime path-traversal
    // defense. parsePlan checks the TYPE only and leaves the character rule to
    // validate(), so a hand-edited plan that never went through the authoring
    // gate is still refused by the runtime defense — not by a pattern the
    // authoring layer owns.
    expect(schema.$defs.task.properties.id.pattern).toBe("^[a-z0-9][a-z0-9-]*$");
    const p = validPlan();
    p.tasks[0].id = "my.task_v1"; // schema-invalid, runtime-safe
    expect(() => validate(parsePlan(p))).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// #391 — setup phases. `git clean -fd` preserves ignored paths, so the
// documented dependency-only setup survives the inter-attempt reset.
// ---------------------------------------------------------------------------
describe("#391 setup runs once per worktree; setupEachAttempt reruns", () => {
  const baseTask: Task = {
    id: "setup-task",
    description: "make the test pass",
    filesInScope: ["src/s.ts"],
    test: { path: "src/s.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  /**
   * deps that record every runGate command set, fail the GATE for the first
   * `failGateTimes` attempts (forcing worker retries), and answer fileHash from
   * a programmable table so setupInputs fingerprinting can be driven.
   */
  function retryDeps(opts: {
    calls: string[][];
    failGateTimes?: number;
    hashes?: Record<string, string[]>; // path suffix -> hash per read
  }): RunTaskDeps {
    let gateRuns = 0;
    const reads: Record<string, number> = {};
    const worker: Worker = {
      async apply() {
        return { ok: true, filesWritten: ["src/s.ts"] } satisfies WorkerResult;
      },
    };
    return {
      worker,
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async (p: string) => {
        for (const [suffix, seq] of Object.entries(opts.hashes ?? {})) {
          if (p.replace(/\\/g, "/").endsWith(suffix)) {
            const n = reads[suffix] ?? 0;
            reads[suffix] = n + 1;
            return seq[Math.min(n, seq.length - 1)];
          }
        }
        return null;
      },
      checkDrift: async () => [],
      runGate: async (_cwd: string, commands: string[]) => {
        opts.calls.push(commands);
        const isGate = commands.join(",") === baseTask.gate.commands.join(",");
        if (isGate) {
          gateRuns++;
          if (gateRuns <= (opts.failGateTimes ?? 0))
            return { ok: false as const, failed: commands[0], tail: "red" };
        }
        return { ok: true as const };
      },
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  const countOf = (calls: string[][], cmd: string) =>
    calls.filter((c) => c.join(",") === cmd).length;

  it("invokes a dependency-only `npm ci` setup ONCE across two worker retries", async () => {
    const calls: string[][] = [];
    const r = await runTask(
      { ...baseTask, maxRetries: 2, setup: ["npm ci"] },
      "m", "https://api.example/v1", "k",
      retryDeps({ calls, failGateTimes: 2 }),
    );
    expect(r.status).toBe("green");
    expect(r.attempts).toBe(3); // three attempts really happened
    expect(countOf(calls, "npm ci")).toBe(1); // …and one install
  });

  it("reruns `setupEachAttempt` before every attempt", async () => {
    const calls: string[][] = [];
    const r = await runTask(
      { ...baseTask, maxRetries: 2, setup: ["npm ci"], setupEachAttempt: ["npm run codegen"] },
      "m", "https://api.example/v1", "k",
      retryDeps({ calls, failGateTimes: 2 }),
    );
    expect(r.status).toBe("green");
    expect(countOf(calls, "npm ci")).toBe(1);
    expect(countOf(calls, "npm run codegen")).toBe(3);
  });

  it("still runs setup BEFORE the worker on the first attempt", async () => {
    const calls: string[][] = [];
    await runTask(
      { ...baseTask, setup: ["npm ci"], setupEachAttempt: ["npm run codegen"] },
      "m", "https://api.example/v1", "k",
      retryDeps({ calls }),
    );
    expect(calls[0]).toEqual(["npm ci"]);
    expect(calls[1]).toEqual(["npm run codegen"]);
  });

  it("escalates immediately when setupEachAttempt fails", async () => {
    const calls: string[][] = [];
    const deps = retryDeps({ calls });
    const failing: RunTaskDeps = {
      ...deps,
      runGate: async (cwd: string, commands: string[]) => {
        if (commands[0] === "npm run codegen")
          return { ok: false as const, failed: commands[0], tail: "boom" };
        return deps.runGate(cwd, commands);
      },
    };
    const r = await runTask(
      { ...baseTask, setupEachAttempt: ["npm run codegen"] },
      "m", "https://api.example/v1", "k",
      failing,
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/setup failed/i);
  });

  it("reruns cached setup when a declared setupInput changes under the worktree", async () => {
    // The regenerate-on-conflict path resets the worktree onto a NEW integration
    // HEAD, so a lockfile really can change between attempts. The fingerprint is
    // what notices.
    const calls: string[][] = [];
    const r = await runTask(
      { ...baseTask, maxRetries: 1, setup: ["npm ci"], setupInputs: ["package-lock.json"] },
      "m", "https://api.example/v1", "k",
      retryDeps({ calls, failGateTimes: 1, hashes: { "package-lock.json": ["hash-1", "hash-2"] } }),
    );
    expect(r.status).toBe("green");
    expect(countOf(calls, "npm ci")).toBe(2);
  });

  it("does NOT rerun setup when the declared setupInput is unchanged", async () => {
    const calls: string[][] = [];
    const r = await runTask(
      { ...baseTask, maxRetries: 1, setup: ["npm ci"], setupInputs: ["package-lock.json"] },
      "m", "https://api.example/v1", "k",
      retryDeps({ calls, failGateTimes: 1, hashes: { "package-lock.json": ["hash-1"] } }),
    );
    expect(r.status).toBe("green");
    expect(countOf(calls, "npm ci")).toBe(1);
  });

  it("is a no-op when neither setup phase is configured", async () => {
    const calls: string[][] = [];
    const r = await runTask(baseTask, "m", "https://api.example/v1", "k", retryDeps({ calls }));
    expect(r.status).toBe("green");
    expect(calls).toEqual([baseTask.gate.commands]);
  });
});
