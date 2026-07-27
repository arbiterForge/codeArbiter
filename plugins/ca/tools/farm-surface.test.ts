/**
 * #511 slice 5 — farm.ts's exported surface.
 *
 * farm.ts is the last module below the stage-2 branch floor, and almost all of
 * its uncovered arms sit behind `main()`, which is only reachable through
 * `spawn()` — a subprocess the v8 coverage provider does not instrument. What IS
 * reachable in-process is the exported surface: `runTask` (through its
 * `RunTaskDeps` seam), `buildPrompt`, `validate`, and — via runTask — the
 * private enrichment/byte-cap path that decides what crosses the trust boundary.
 * That is what this file drives.
 *
 * Two rules this file holds to, both learned the hard way earlier in #511:
 *
 * 1. EVERY escalation asserts its EXACT note string, never just
 *    `status === "escalate"`. runTask has eleven distinct escalation paths; a
 *    test that only checks the status lets any two of them collapse into each
 *    other, and a mutant that swaps one note for another survives.
 *
 * 2. Where a value is a threshold or a truncation width, the test pins the
 *    NUMBER, not just the shape. `expect(note).toContain("commit failed")`
 *    passes whether the slice is 200 or 2000 characters wide.
 */
import { describe, it, expect, afterEach } from "vitest";
import path from "node:path";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { runTask, buildPrompt, parsePlan, validate } from "./farm.ts";
import type { Plan, RunTaskDeps, Task, Worker, WorkerResult } from "./farm.ts";
import { MUT } from "./mutation.ts";

// runTask derives the task worktree as `path.resolve(ENV.worktreeRoot, t.id)`,
// and ENV.worktreeRoot is fixed at module load. Mirroring it here is what lets
// the enrichment tests below put real files where runTask will read them.
const WORKTREE_ROOT = path.resolve(process.env.FARM_WORKTREE_ROOT ?? ".farm/worktrees");
const worktreeFor = (id: string) => path.join(WORKTREE_ROOT, id);

const created: string[] = [];
afterEach(async () => {
  for (const wt of created.splice(0)) await rm(wt, { recursive: true, force: true });
});

async function seedWorktree(id: string, files: Record<string, string>): Promise<string> {
  const wt = worktreeFor(id);
  created.push(wt);
  await rm(wt, { recursive: true, force: true });
  for (const [rel, body] of Object.entries(files)) {
    const abs = path.join(wt, rel);
    await mkdir(path.dirname(abs), { recursive: true });
    await writeFile(abs, body, "utf8");
  }
  return wt;
}

function task(over: Partial<Task> & { id: string }): Task {
  return {
    description: "make the test pass",
    filesInScope: ["src/impl.ts"],
    test: { path: "src/impl.test.ts" },
    gate: { commands: ["node -p 0"] },
    ...over,
  };
}

const okGit = { code: 0, out: "", stdout: "", stderr: "" };

/** Every side effect stubbed; override exactly the one the test is about. */
function deps(over: Partial<RunTaskDeps> = {}): RunTaskDeps {
  return {
    worker: { async apply() { return { ok: true, filesWritten: ["src/impl.ts"] } satisfies WorkerResult; } },
    prepareWorktree: async () => null,
    resetWorktree: async () => {},
    fileHash: async () => null, // null short-circuits the tamper comparison
    checkDrift: async () => [],
    runGate: async () => ({ ok: true as const }),
    antiGamingCheck: async () => ({ risk: "none" as const }),
    mutationCheck: async () => null,
    git: async () => okGit,
    withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    ...over,
  };
}

const RUN = (t: Task, d: RunTaskDeps) => runTask(t, "run-model", "https://api.example/v1", "test-key", d);

/** Captures every prompt the worker was handed, in order. */
function recordingWorker(prompts: string[], files: string[] = ["src/impl.ts"]): Worker {
  return {
    async apply(ctx) {
      prompts.push(ctx.prompt);
      return { ok: true, filesWritten: files } satisfies WorkerResult;
    },
  };
}

// ---------------------------------------------------------------------------
// runTask — the eleven escalations, each pinned to its own note
// ---------------------------------------------------------------------------
describe("runTask escalations are distinguished by note, not just by status", () => {
  it("returns prepareWorktree's own message with attempts: 0 — it never reached a worker", async () => {
    let workerCalls = 0;
    const r = await RUN(
      task({ id: "s5-prep" }),
      deps({
        prepareWorktree: async () => "worktree add failed: fatal: 'farm/s5-prep' is already checked out",
        worker: { async apply() { workerCalls += 1; return { ok: true, filesWritten: [] }; } },
      }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe("worktree add failed: fatal: 'farm/s5-prep' is already checked out");
    // 0, not 1: the count is "worker attempts spent", and this path spent none.
    expect(r.attempts).toBe(0);
    expect(workerCalls).toBe(0);
  });

  it("escalates immediately on a setup failure WITHOUT burning a worker retry", async () => {
    const prompts: string[] = [];
    const r = await RUN(
      task({ id: "s5-setup", setup: ["npm ci"], maxRetries: 3 }),
      deps({
        worker: recordingWorker(prompts),
        runGate: async (_cwd, cmds) =>
          cmds[0] === "npm ci" ? { ok: false as const, failed: "npm ci", tail: "ENOTFOUND registry" } : { ok: true as const },
      }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe("setup failed: npm ci\nENOTFOUND registry");
    // The environment is broken, not the worker — with 3 retries available it
    // must still stop at the first attempt rather than spend them.
    expect(r.attempts).toBe(1);
    expect(prompts).toEqual([]);
  });

  it("names the tampered test path when the test hash moves under the worker", async () => {
    let call = 0;
    const r = await RUN(
      task({ id: "s5-tamper", test: { path: "src/guard.test.ts" } }),
      deps({ fileHash: async () => (call++ === 0 ? "hash-before" : "hash-after") }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe("tampered test: src/guard.test.ts");
    expect(r.attempts).toBe(1);
    expect(r.filesWritten).toEqual(["src/impl.ts"]);
  });

  it("does NOT call it tampering when the hash was UNREADABLE before the worker ran", async () => {
    // fileHash returns null for a file it could not read. A null "before" means
    // "unknown", not "changed" — without the `!== null` guard every
    // unreadable-then-readable test file becomes a false tamper escalation.
    let call = 0;
    const r = await RUN(
      task({ id: "s5-tamper-null" }),
      deps({ fileHash: async () => (call++ === 0 ? null : "now-readable") }),
    );
    expect(r.status).toBe("green");
  });

  it("retries ONCE on drift, naming the offending paths in the next prompt", async () => {
    const prompts: string[] = [];
    let call = 0;
    const r = await RUN(
      task({ id: "s5-drift-retry", maxRetries: 2 }),
      deps({
        worker: recordingWorker(prompts, ["src/impl.ts", "docs/notes.md"]),
        checkDrift: async () => (++call === 1 ? ["docs/notes.md"] : []),
      }),
    );
    expect(r.status).toBe("green");
    expect(r.attempts).toBe(2);
    expect(prompts).toHaveLength(2);
    expect(prompts[0]).not.toContain("drift:");
    expect(prompts[1]).toContain("drift: you wrote outside the allowed files: docs/notes.md");
    // The retry is also told, separately, not to touch the path again.
    expect(prompts[1]).toContain("Your previous attempt wrote these FORBIDDEN paths");
    expect(prompts[1]).toContain("  - docs/notes.md");
  });

  it("escalates with the comma-joined drift list, in order, once the retry is spent", async () => {
    const r = await RUN(
      task({ id: "s5-drift-esc", maxRetries: 1 }),
      deps({ checkDrift: async () => ["docs/a.md", "docs/b.md"] }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe("drift: docs/a.md, docs/b.md");
    expect(r.attempts).toBe(2);
  });

  it("escalates on the SECOND drift even with retries left — the latch, not the counter", async () => {
    // maxRetries 5 leaves four attempts unspent. The `driftedOnce` latch is the
    // only thing that stops the loop here; if it never sets, this runs to 6.
    const r = await RUN(
      task({ id: "s5-drift-latch", maxRetries: 5 }),
      deps({ checkDrift: async () => ["docs/a.md"] }),
    );
    expect(r.status).toBe("escalate");
    expect(r.attempts).toBe(2);
    expect(r.note).toBe("drift: docs/a.md");
  });

  it("spends one retry on a high anti-gaming risk, then escalates with its note", async () => {
    const prompts: string[] = [];
    const r = await RUN(
      task({ id: "s5-gaming", maxRetries: 1 }),
      deps({
        worker: recordingWorker(prompts),
        antiGamingCheck: async () => ({ risk: "high" as const, note: "gaming: impl returns the asserted literal" }),
      }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe("gaming: impl returns the asserted literal");
    expect(r.attempts).toBe(2);
    expect(prompts).toHaveLength(2);
    expect(prompts[1]).toContain(
      "gaming: impl returns the asserted literal. Implement real logic; do not hard-code or special-case the asserted value.",
    );
  });

  it("escalates on a failed commit, truncating git's output at exactly 200 characters", async () => {
    const noisy = "E".repeat(500);
    const r = await RUN(
      task({ id: "s5-commit" }),
      deps({
        git: async (args: string[]) =>
          args.includes("commit") ? { code: 1, out: noisy, stdout: noisy, stderr: "" } : okGit,
      }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe(`commit failed: ${"E".repeat(200)}`);
    expect(r.note).toHaveLength("commit failed: ".length + 200);
  });

  it("escalates after the last attempt carrying only the FIRST line of the prior failure", async () => {
    const r = await RUN(
      task({ id: "s5-exhausted", maxRetries: 1 }),
      deps({ runGate: async () => ({ ok: false as const, failed: "npm test", tail: "line one\nline two\nline three" }) }),
    );
    expect(r.status).toBe("escalate");
    // limit + 1 — the initial attempt plus the one retry.
    expect(r.attempts).toBe(2);
    // The report gets a headline, not the whole gate tail.
    expect(r.note).toBe("failed: npm test");
    expect(r.note).not.toContain("line two");
  });
});

// ---------------------------------------------------------------------------
// runTask — the mutation-score arms. Thresholds are compared, not just shapes.
// ---------------------------------------------------------------------------
describe("runTask mutation-score handling", () => {
  const noEnvOverride = !process.env.FARM_MUTATION_WARN_BELOW && !process.env.FARM_MUTATION_ESCALATE_BELOW;

  it.skipIf(!noEnvOverride)("pins the default thresholds the boundary tests below reason about", () => {
    // Without these two literals, a boundary test that uses MUT.warnBelow on
    // both sides proves nothing — it would still pass if the default moved.
    expect(MUT.warnBelow).toBe(0.5);
    expect(MUT.escalateBelow).toBe(0.1);
  });

  it("escalates on a near-zero score once at least 5 mutants were evaluated", async () => {
    const r = await RUN(
      task({ id: "s5-mut-escalate", maxRetries: 0 }),
      deps({ mutationCheck: async () => ({ score: 0.05, evaluated: 8, survivors: ["a", "b"] }) }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toBe(
      "gaming: mutation score 0.05 (8 mutants survived — the test does not constrain the implementation)",
    );
    expect(r.mutationScore).toBe(0.05);
  });

  it("does NOT escalate the same near-zero score when fewer than 5 mutants were evaluated", async () => {
    // The `evaluated >= 5` floor exists because a 1-of-2 sample is noise. Drop
    // it and every tiny mutation run hard-escalates.
    const r = await RUN(
      task({ id: "s5-mut-floor", maxRetries: 0 }),
      deps({ mutationCheck: async () => ({ score: 0.05, evaluated: 4, survivors: ["a"] }) }),
    );
    expect(r.status).toBe("green");
    expect(r.mutationScore).toBe(0.05);
    // It still falls through to the softer warn arm rather than vanishing.
    expect(r.warning).toBe("mutation-risk: score 0.05 (1/4 survived) — weak test or under-implemented logic");
  });

  it("treats a score EXACTLY at warnBelow as clean — the comparison is strict", async () => {
    const r = await RUN(
      task({ id: "s5-mut-boundary", maxRetries: 0 }),
      deps({ mutationCheck: async () => ({ score: MUT.warnBelow, evaluated: 8, survivors: [] }) }),
    );
    expect(r.status).toBe("green");
    expect(r.warning).toBeUndefined();
    expect(r.mutationScore).toBe(MUT.warnBelow);
  });

  it("warns — never escalates — when the mutation HOOK itself failed, carrying its detail", async () => {
    // A broken FARM_MUTATION_CMD is infrastructure, not the worker's fault. It
    // must be visible (otherwise it is indistinguishable from "not configured")
    // and must not block the task.
    const r = await RUN(
      task({ id: "s5-mut-hook", maxRetries: 0 }),
      deps({ mutationCheck: async () => ({ failed: true as const, detail: "exit 3: hook not installed" }) }),
    );
    expect(r.status).toBe("green");
    expect(r.warning).toBe("mutation-hook-failed: exit 3: hook not installed");
    expect(r.mutationScore).toBeNull();
  });

  it("lets a failed hook NOT overwrite an anti-gaming warning already raised", async () => {
    const r = await RUN(
      task({ id: "s5-mut-hook-keep", maxRetries: 0 }),
      deps({
        antiGamingCheck: async () => ({ risk: "warn" as const, note: "anti-gaming: borderline literal reuse" }),
        mutationCheck: async () => ({ failed: true as const, detail: "exit 3" }),
      }),
    );
    expect(r.status).toBe("green");
    expect(r.warning).toBe("anti-gaming: borderline literal reuse");
  });

  it("keeps the anti-gaming warning when the mutation score is ALSO only warn-level", async () => {
    const r = await RUN(
      task({ id: "s5-mut-warn-keep", maxRetries: 0 }),
      deps({
        antiGamingCheck: async () => ({ risk: "warn" as const, note: "anti-gaming: borderline literal reuse" }),
        mutationCheck: async () => ({ score: 0.3, evaluated: 8, survivors: ["a"] }),
      }),
    );
    expect(r.status).toBe("green");
    expect(r.warning).toBe("anti-gaming: borderline literal reuse");
    // The score is still recorded even though its warning lost the tie.
    expect(r.mutationScore).toBe(0.3);
  });
});

// ---------------------------------------------------------------------------
// runTask — best-of-N sample failures. Each sample failure kind produces its
// own note, and that note is what seeds the escalation.
// ---------------------------------------------------------------------------
describe("best-of-N sample failures each surface their own cause", () => {
  const savedSamples = process.env.FARM_SAMPLES;
  const savedTemp = process.env.FARM_TEMPERATURE;
  afterEach(() => {
    const restore = (k: string, v: string | undefined) => (v === undefined ? delete process.env[k] : (process.env[k] = v));
    restore("FARM_SAMPLES", savedSamples);
    restore("FARM_TEMPERATURE", savedTemp);
  });

  const isSample = (cwd: string) => /__s\d+$/.test(cwd);

  /** Drives 2 samples, all failing the same way, with no retries left. */
  async function escalateVia(id: string, over: Partial<RunTaskDeps>, t: Partial<Task> = {}): Promise<string | undefined> {
    process.env.FARM_SAMPLES = "2";
    const r = await RUN(task({ id, maxRetries: 0, ...t }), deps(over));
    expect(r.status).toBe("escalate");
    return r.note;
  }

  it("reports a sample's worktree-preparation refusal", async () => {
    const note = await escalateVia("s5-bon-prep", {
      // The TASK worktree still prepares fine; only the samples are refused.
      prepareWorktree: async (_b: string, wt: string) => (isSample(wt) ? "sample worktree add failed" : null),
    });
    expect(note).toBe("sample worktree add failed");
  });

  it("reports a sample's setup failure", async () => {
    const note = await escalateVia(
      "s5-bon-setup",
      {
        runGate: async (cwd: string, cmds: string[]) =>
          isSample(cwd) && cmds[0] === "npm ci"
            ? { ok: false as const, failed: "npm ci", tail: "no lockfile" }
            : { ok: true as const },
      },
      { setup: ["npm ci"] },
    );
    expect(note).toBe("setup failed: npm ci");
  });

  it("reports a sample's worker error", async () => {
    const note = await escalateVia("s5-bon-worker", {
      worker: { async apply() { return { ok: false, filesWritten: [], error: "upstream 500" } satisfies WorkerResult; } },
    });
    expect(note).toBe("worker error: upstream 500");
  });

  it("reports a sample that wrote the read-only test path", async () => {
    const note = await escalateVia("s5-bon-sweep", {
      worker: {
        async apply() { return { ok: true, filesWritten: ["src/impl.ts", "src/impl.test.ts"] } satisfies WorkerResult; },
      },
    });
    expect(note).toBe("worker wrote read-only path: src/impl.test.ts");
  });

  it("lets a CLEAN sample win when a SIBLING sample wrote the read-only test path", async () => {
    // The escalation test above cannot, on its own, tell the sample-level sweep
    // from the task-level one — both emit the identical note, so disabling the
    // sample sweep still produces the same escalation via the task sweep. This
    // one separates them: with the sample sweep live, sample 0 is rejected and
    // clean sample 1 wins. Without it, sample 0 is accepted (first green by
    // index) and its forbidden write trips the task sweep instead.
    process.env.FARM_SAMPLES = "2";
    const r = await RUN(
      task({ id: "s5-bon-sweep-sibling", maxRetries: 0 }),
      deps({
        worker: {
          async apply(ctx) {
            const k = Number(ctx.cwd.match(/__s(\d+)$/)?.[1] ?? -1);
            return k === 0
              ? ({ ok: true, filesWritten: ["src/impl.ts", "src/impl.test.ts"] } satisfies WorkerResult)
              : ({ ok: true, filesWritten: ["src/clean.ts"] } satisfies WorkerResult);
          },
        },
      }),
    );
    expect(r.status).toBe("green");
    expect(r.filesWritten).toEqual(["src/clean.ts"]);
  });

  it("does NOT reject a sample whose test hash was UNREADABLE before the worker ran", async () => {
    // The same null-means-unknown rule as the task-level guard. Drop it inside a
    // sample and every sample fails, so the task escalates reporting tampering
    // that never happened.
    process.env.FARM_SAMPLES = "2";
    const seen = new Set<string>();
    const r = await RUN(
      task({ id: "s5-bon-tamper-null", maxRetries: 0 }),
      deps({
        fileHash: async (p: string) => {
          const wt = path.dirname(path.dirname(p));
          if (!seen.has(wt)) { seen.add(wt); return null; }
          return "now-readable";
        },
      }),
    );
    expect(r.status).toBe("green");
  });

  it("reports a sample that tampered with the test", async () => {
    const seen = new Set<string>();
    const note = await escalateVia("s5-bon-tamper", {
      // Keyed on the worktree, not a call counter: the samples run concurrently,
      // so a counter would interleave and the hashes would not pair up.
      fileHash: async (p: string) => {
        const wt = path.dirname(path.dirname(p));
        if (!seen.has(wt)) { seen.add(wt); return "hash-before"; }
        return "hash-after";
      },
    });
    expect(note).toBe("tampered test: src/impl.test.ts");
  });

  it("reports a sample that drifted outside its allowed files", async () => {
    const note = await escalateVia("s5-bon-drift", {
      checkDrift: async (cwd: string) => (isSample(cwd) ? ["docs/stray.md"] : []),
    });
    expect(note).toBe("drift: docs/stray.md");
  });

  it("carries the text of a NON-Error thrown inside a sample", async () => {
    // A sample that throws must resolve to a failure OUTCOME, never reject —
    // and a thrown string still has to say what it said.
    const note = await escalateVia("s5-bon-throw", {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      worker: { async apply() { throw "raw string failure"; } },
    });
    expect(note).toBe("sample error: raw string failure");
  });
});

// ---------------------------------------------------------------------------
// buildPrompt — pure, and the last thing between a task and the model
// ---------------------------------------------------------------------------
describe("buildPrompt optional blocks", () => {
  const t = task({ id: "bp" });

  it("includes the task context block when the task carries one", () => {
    const p = buildPrompt({ ...t, context: "The parser already handles UTF-16." }, []);
    expect(p).toContain("CONTEXT:\nThe parser already handles UTF-16.");
  });

  it("omits the context block entirely when the task has none", () => {
    expect(buildPrompt(t, [])).not.toContain("CONTEXT:");
  });

  it("lists forbidden paths when the previous attempt drifted", () => {
    const p = buildPrompt(t, [], undefined, ["docs/a.md", "docs/b.md"]);
    expect(p).toContain("Your previous attempt wrote these FORBIDDEN paths — do NOT touch them again:");
    expect(p).toContain("  - docs/a.md\n  - docs/b.md");
  });

  it("omits the forbidden block for an EMPTY list, not just an absent one", () => {
    // `forbiddenExtra && forbiddenExtra.length` — drop the length check and an
    // empty array renders the heading with nothing under it.
    expect(buildPrompt(t, [], undefined, [])).not.toContain("FORBIDDEN paths");
    expect(buildPrompt(t, [], undefined, undefined)).not.toContain("FORBIDDEN paths");
  });
});

// ---------------------------------------------------------------------------
// validate — the setup/setupInputs rules (#92 / #391)
// ---------------------------------------------------------------------------
describe("validate — setup, setupEachAttempt, and setupInputs", () => {
  const plan = (over: Partial<Plan["meta"]>, taskOver: Partial<Task> = {}): Plan => ({
    meta: { model: "m", ...over } as Plan["meta"],
    tasks: [
      {
        id: "t1",
        description: "d",
        filesInScope: ["src/a.ts"],
        test: { path: "src/a.test.ts" },
        gate: { commands: ["node -p 0"] },
        ...taskOver,
      },
    ],
  });

  it("accepts a plan whose setup fields are all well-formed", () => {
    expect(() =>
      validate(
        plan(
          { setup: ["npm ci"], setupEachAttempt: ["npm run clean"], setupInputs: ["package-lock.json"] },
          { setup: ["pip install -e ."], setupEachAttempt: ["rm -rf .cache"], setupInputs: ["requirements.txt"] },
        ),
      ),
    ).not.toThrow();
  });

  it.each([
    ["plan.meta.setupEachAttempt", { setupEachAttempt: [""] }, "plan.meta.setupEachAttempt: setup entries must be non-empty strings"],
    ["plan.meta.setupEachAttempt length", { setupEachAttempt: ["x".repeat(1025)] }, "plan.meta.setupEachAttempt: setup command exceeds 1024 chars"],
    ["plan.meta.setupInputs empty", { setupInputs: [""] }, "plan.meta: setupInputs entries must be non-empty strings"],
    ["plan.meta.setupInputs traversal", { setupInputs: ["../secrets/.env"] }, 'plan.meta: setupInputs entry "../secrets/.env" must be a relative path with no ".." segments'],
    ["plan.meta.setupInputs absolute", { setupInputs: ["/etc/passwd"] }, 'plan.meta: setupInputs entry "/etc/passwd" must be a relative path with no ".." segments'],
  ])("rejects %s", (_label, meta, message) => {
    expect(() => validate(plan(meta))).toThrowError(message);
  });

  it.each([
    ["task setupEachAttempt", { setupEachAttempt: [""] }, "task t1 setupEachAttempt: setup entries must be non-empty strings"],
    ["task setupInputs empty", { setupInputs: [""] }, "task t1: setupInputs entries must be non-empty strings"],
    ["task setupInputs traversal", { setupInputs: ["../../etc/hosts"] }, 'task t1: setupInputs entry "../../etc/hosts" must be a relative path with no ".." segments'],
    ["task setupInputs absolute", { setupInputs: ["/etc/passwd"] }, 'task t1: setupInputs entry "/etc/passwd" must be a relative path with no ".." segments'],
  ])("rejects %s", (_label, taskOver, message) => {
    expect(() => validate(plan({}, taskOver))).toThrowError(message);
  });
});

// ---------------------------------------------------------------------------
// parsePlan — the runtime boundary (#412). A plan reaching validate() has
// already been asserted `as Plan`, so these guards are the only thing between a
// hand-edited plan.json and an opaque TypeError deep inside runTask.
// ---------------------------------------------------------------------------
describe("parsePlan — declared-type guards name the field AND what arrived", () => {
  const good = {
    meta: { name: "p", model: "m" },
    tasks: [
      { id: "t1", description: "d", filesInScope: ["src/a.ts"], test: { path: "src/a.test.ts" }, gate: { commands: ["node -p 0"] } },
    ],
  };
  const withTask = (over: Record<string, unknown>) => ({ ...good, tasks: [{ ...good.tasks[0], ...over }] });

  it("accepts the well-formed plan unchanged", () => {
    expect(parsePlan(good)).toBe(good);
  });

  it("rejects a bare string where an array of strings is declared", () => {
    expect(() => parsePlan(withTask({ filesInScope: "src/a.ts" }))).toThrowError(
      "plan.tasks[0].filesInScope must be an array of strings (got string)",
    );
  });

  it("rejects a null there too — distinct from the field being absent", () => {
    expect(() => parsePlan(withTask({ filesInScope: null }))).toThrowError(
      "plan.tasks[0].filesInScope must be an array of strings (got null)",
    );
  });

  it("names the offending index when one entry of the array is not a string", () => {
    expect(() => parsePlan(withTask({ filesInScope: ["src/a.ts", 7] }))).toThrowError(
      "plan.tasks[0].filesInScope[1] must be a string (got number)",
    );
  });

  it("rejects an empty filesInScope — the schema declares minItems 1", () => {
    expect(() => parsePlan(withTask({ filesInScope: [] }))).toThrowError(
      "plan.tasks[0].filesInScope must list at least one entry",
    );
  });

  it("rejects a negative maxRetries against the declared minimum of 0", () => {
    expect(() => parsePlan(withTask({ maxRetries: -1 }))).toThrowError(
      "plan.tasks[0].maxRetries must be an integer >= 0",
    );
  });

  it("rejects a non-integer maxRetries", () => {
    expect(() => parsePlan(withTask({ maxRetries: 1.5 }))).toThrowError(
      "plan.tasks[0].maxRetries must be an integer >= 0 (got number)",
    );
  });
});

// ---------------------------------------------------------------------------
// Enrichment — what actually crosses the trust boundary. Driven through
// runTask against a REAL worktree, because the reader hits the filesystem.
// ---------------------------------------------------------------------------
describe("prompt enrichment reads the worktree and refuses secret-bearing names", () => {
  /** Runs one attempt and returns the prompt the worker was handed. */
  async function promptFor(t: Task, over: Partial<RunTaskDeps> = {}): Promise<string> {
    const prompts: string[] = [];
    await RUN(t, deps({ worker: recordingWorker(prompts), ...over }));
    expect(prompts).toHaveLength(1);
    return prompts[0];
  }

  it("injects the failing test read-only and the existing in-scope source", async () => {
    const id = "s5-enrich-basic";
    await seedWorktree(id, {
      "src/impl.test.ts": "expect(add(1, 2)).toBe(3);",
      "src/impl.ts": "export const add = () => 0;",
    });
    const p = await promptFor(task({ id }));
    expect(p).toContain("--- src/impl.test.ts (read-only — the failing test) ---\nexpect(add(1, 2)).toBe(3);");
    expect(p).toContain("--- src/impl.ts ---\nexport const add = () => 0;");
  });

  it("injects nothing for an in-scope file that does not exist yet", async () => {
    const id = "s5-enrich-missing";
    await seedWorktree(id, { "src/impl.test.ts": "expect(add(1, 2)).toBe(3);" });
    const p = await promptFor(task({ id }));
    expect(p).toContain("--- src/impl.test.ts (read-only — the failing test) ---");
    // No header, and above all no "null" body, for the not-yet-written target.
    expect(p).not.toContain("--- src/impl.ts ---");
    expect(p).not.toContain("null");
  });

  it("injects nothing at all when even the test file is unreadable", async () => {
    const id = "s5-enrich-notest";
    await seedWorktree(id, { "src/other.ts": "unused" });
    const p = await promptFor(task({ id }));
    expect(p).not.toContain("--- src/impl.test.ts");
    expect(p).not.toContain("Current source of the relevant files");
  });

  it("never reads a secret-bearing in-scope filename, even to redact it", async () => {
    const id = "s5-enrich-secret-scope";
    await seedWorktree(id, {
      "src/impl.test.ts": "expect(cfg.token).toBeDefined();",
      ".env": "API_TOKEN=hunter2-not-a-real-value",
      "src/impl.ts": "export const cfg = {};",
    });
    const p = await promptFor(task({ id, filesInScope: [".env", "src/impl.ts"] }));
    // Data minimization: the body never crosses the boundary, and neither does
    // the header that would advertise it.
    expect(p).not.toContain("hunter2-not-a-real-value");
    expect(p).not.toContain("--- .env ---");
    // The benign sibling in the same list is still injected.
    expect(p).toContain("--- src/impl.ts ---\nexport const cfg = {};");
  });

  it("never reads a secret-bearing TEST path", async () => {
    const id = "s5-enrich-secret-test";
    await seedWorktree(id, {
      "config/app.key": "SIGNING_MATERIAL=do-not-emit-this",
      "src/impl.ts": "export const cfg = {};",
    });
    const p = await promptFor(task({ id, test: { path: "config/app.key" }, filesInScope: ["config/app.key", "src/impl.ts"] }));
    expect(p).not.toContain("do-not-emit-this");
    expect(p).not.toContain("--- config/app.key");
    expect(p).toContain("--- src/impl.ts ---");
  });

  it("injects a file listed BOTH as the test and as in-scope exactly once", async () => {
    const id = "s5-enrich-dup";
    await seedWorktree(id, { "src/impl.test.ts": "expect(add(1, 2)).toBe(3);" });
    const p = await promptFor(task({ id, filesInScope: ["src/impl.test.ts", "src/impl.ts"] }));
    const headers = p.split("--- src/impl.test.ts").length - 1;
    expect(headers).toBe(1);
    // and it keeps the read-only framing rather than being re-injected as editable
    expect(p).toContain("--- src/impl.test.ts (read-only — the failing test) ---");
  });

  it("re-shows the previous attempt's own output, labelled as the failed attempt", async () => {
    const id = "s5-enrich-prior";
    await seedWorktree(id, {
      "src/impl.test.ts": "expect(add(1, 2)).toBe(3);",
      "src/impl.ts": "export const add = () => 0;",
    });
    const prompts: string[] = [];
    await RUN(
      task({ id, maxRetries: 1 }),
      deps({
        worker: recordingWorker(prompts),
        runGate: async () => ({ ok: false as const, failed: "npm test", tail: "red" }),
      }),
    );
    expect(prompts).toHaveLength(2);
    expect(prompts[0]).not.toContain("your previous attempt — FAILED");
    expect(prompts[1]).toContain("--- src/impl.ts (your previous attempt — FAILED) ---");
  });

  it("never re-shows a secret-bearing file as previous-attempt output", async () => {
    // Two layers refuse this: captureInScope skips the name on the way IN, and
    // buildEnrichment skips it again on the way OUT. Neither is asserted by
    // disabling one of them — the property is that the body never reaches the
    // retry prompt, so that is what this asserts.
    const id = "s5-enrich-secret-prior";
    await seedWorktree(id, {
      "src/impl.test.ts": "expect(cfg.token).toBeDefined();",
      ".env": "API_TOKEN=hunter2-not-a-real-value",
      "src/impl.ts": "export const cfg = {};",
    });
    const prompts: string[] = [];
    await RUN(
      task({ id, filesInScope: [".env", "src/impl.ts"], maxRetries: 1 }),
      deps({
        worker: recordingWorker(prompts, [".env", "src/impl.ts"]),
        runGate: async () => ({ ok: false as const, failed: "npm test", tail: "red" }),
      }),
    );
    expect(prompts).toHaveLength(2);
    // The retry DOES get its own prior output — just not this file.
    expect(prompts[1]).toContain("--- src/impl.ts (your previous attempt — FAILED) ---");
    expect(prompts[1]).not.toContain("hunter2-not-a-real-value");
    expect(prompts[1]).not.toContain(".env (your previous attempt");
  });

  it("does NOT re-show prior output when the previous attempt wrote nothing", async () => {
    // An API-level failure writes no files. Re-showing the worktree then labels
    // the untouched BASELINE as "your previous attempt", which is a lie the next
    // attempt will act on.
    const id = "s5-enrich-noprior";
    await seedWorktree(id, {
      "src/impl.test.ts": "expect(add(1, 2)).toBe(3);",
      "src/impl.ts": "export const add = () => 0;",
    });
    const prompts: string[] = [];
    await RUN(
      task({ id, maxRetries: 1 }),
      deps({
        worker: {
          async apply(ctx) {
            prompts.push(ctx.prompt);
            return { ok: false, filesWritten: [], error: "connection reset" } satisfies WorkerResult;
          },
        },
      }),
    );
    expect(prompts).toHaveLength(2);
    expect(prompts[1]).not.toContain("your previous attempt — FAILED");
  });
});

// ---------------------------------------------------------------------------
// Enrichment byte cap — the prompt is never unbounded
// ---------------------------------------------------------------------------
describe("enrichment is byte-capped before it leaves the trust boundary", () => {
  const MARKER = "--- [TRUNCATED — injected context exceeded FARM_ENRICH_MAX_BYTES] ---";

  it("truncates the overflowing file, marks it, and drops everything after it", async () => {
    const id = "s5-cap";
    // The default cap is 131072 bytes. 100k of test source fits; the next 100k
    // file overflows and is truncated mid-body; the third is dropped whole.
    await seedWorktree(id, {
      "src/impl.test.ts": "A".repeat(100_000),
      "src/first.ts": "B".repeat(100_000),
      "src/second.ts": "C".repeat(1_000),
    });
    const prompts: string[] = [];
    await RUN(task({ id, filesInScope: ["src/first.ts", "src/second.ts"] }), deps({ worker: recordingWorker(prompts) }));
    const p = prompts[0];

    expect(p).toContain("A".repeat(100_000)); // the first file survives whole
    expect(p).toContain(MARKER);
    // The overflowing file is present but cut: some of it got through, not all.
    expect(p).toContain("B".repeat(20_000));
    expect(p).not.toContain("B".repeat(60_000));
    // And the file AFTER the truncation point is dropped entirely — `break`,
    // not `continue`. Without that, the cap only limits one file, not the total.
    expect(p).not.toContain("--- src/second.ts ---");
    expect(p).not.toContain("C".repeat(1_000));
  });
});
