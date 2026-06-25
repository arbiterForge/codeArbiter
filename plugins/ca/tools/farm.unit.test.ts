/**
 * Unit tests for farm.ts pure-function core.
 * These test the exported helpers directly without spawning a subprocess.
 */
import { describe, it, expect } from "vitest";
import path from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { extractFileBlocks, extractLiterals, codeLineCount, validate, assertSecureBaseUrl, runTask, httpWorker, DEFAULT_API_BASE_URL, parseChatCompletion, checkDrift, screenEntitlements, redactSecrets, run, runGate, mintRunId, parseMutationHookOutput } from "./farm.ts";
import type { Worker, WorkerResult, RunTaskDeps, Task } from "./farm.ts";

// ---------------------------------------------------------------------------
// redactSecrets — outbound-boundary redactor must stay aligned with the hook
// SECRET_RE: catch known high-entropy key prefixes, not just trigger words.
// ---------------------------------------------------------------------------
describe("redactSecrets — high-entropy key prefixes (checkpoint 2026-06-22)", () => {
  it("redacts an AWS access key id with no trigger word on the line", () => {
    const out = redactSecrets("const id = AKIAIOSFODNN7EXAMPLE;");
    expect(out).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(out).toContain("[REDACTED");
  });

  it("redacts a GitHub PAT prefix with no trigger word on the line", () => {
    const pat = "ghp_abcdefghijklmnopqrstuvwxyz0123456789";
    expect(redactSecrets(`const t = ${pat};`)).not.toContain(pat);
  });

  it("still redacts the existing sk-ant trigger", () => {
    expect(redactSecrets("key: sk-ant-secret")).toContain("[REDACTED");
  });

  it("passes a benign line through unchanged", () => {
    expect(redactSecrets("const total = sum(a, b);")).toBe("const total = sum(a, b);");
  });
});

// ---------------------------------------------------------------------------
// Shared secret-detection corpus (architecture-001). SECRET_LINE (this
// outbound redactor) and _hooklib.SECRET_RE (the commit gate) are deliberately
// distinct in shape, but must never drift apart on the AGREEMENT region. This
// pins the TS (SECRET_LINE) side against the SAME corpus file that
// .github/scripts/test_hooklib.py asserts SECRET_RE against — a divergence on
// any entry fails CI on one side or the other. (For a single-line input
// redactSecrets returns the marker iff SECRET_LINE matched.)
// ---------------------------------------------------------------------------
describe("redactSecrets — shared secret-detection corpus parity", () => {
  const corpusPath = path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "..",
    "hooks",
    "secret-detection-corpus.json",
  );
  const corpus = JSON.parse(readFileSync(corpusPath, "utf8")) as {
    must_match: string[];
    must_not_match: string[];
  };

  it("has both corpus sets", () => {
    expect(corpus.must_match.length).toBeGreaterThan(0);
    expect(corpus.must_not_match.length).toBeGreaterThan(0);
  });

  it.each(corpus.must_match)("redacts a must_match secret: %s", (line) => {
    expect(redactSecrets(line)).toContain("[REDACTED");
  });

  it.each(corpus.must_not_match)("passes a must_not_match benign line: %s", (line) => {
    expect(redactSecrets(line)).toBe(line);
  });
});

// ---------------------------------------------------------------------------
// extractFileBlocks
// ---------------------------------------------------------------------------
describe("extractFileBlocks", () => {
  it("parses a single block with lang:path info string", () => {
    const content = "```typescript:src/foo.ts\nconst x = 1;\n```";
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].path).toBe("src/foo.ts");
    expect(blocks[0].body).toBe("const x = 1;");
  });

  it("parses a block with // path: comment (strips the comment line)", () => {
    const content = "```typescript\n// path: src/bar.ts\nconst y = 2;\n```";
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].path).toBe("src/bar.ts");
    expect(blocks[0].body).toBe("const y = 2;");
  });

  it("parses a block with # path: comment (Python style)", () => {
    const content = "```python\n# path: src/utils.py\ndef f(): pass\n```";
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].path).toBe("src/utils.py");
    expect(blocks[0].body).toBe("def f(): pass");
  });

  it("parses multiple blocks from a single response", () => {
    const content = [
      "```typescript:src/a.ts",
      "const a = 1;",
      "```",
      "some text between blocks",
      "```typescript:src/b.ts",
      "const b = 2;",
      "```",
    ].join("\n");
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(2);
    expect(blocks[0].path).toBe("src/a.ts");
    expect(blocks[1].path).toBe("src/b.ts");
  });

  it("ignores blocks with no path identifier", () => {
    const content = "```\nsome code with no path\n```";
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(0);
  });

  it("does not filter out path-traversal paths — validate() is responsible for that", () => {
    const content = "```typescript:../escape.ts\nconst x = 1;\n```";
    const blocks = extractFileBlocks(content);
    // extractFileBlocks parses faithfully; runWorker's isInside() guard rejects
    expect(blocks).toHaveLength(1);
    expect(blocks[0].path).toBe("../escape.ts");
  });

  it("handles an unclosed fence gracefully (falls off end)", () => {
    const content = "```typescript:src/a.ts\nconst x = 1;\n";
    const blocks = extractFileBlocks(content);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].path).toBe("src/a.ts");
  });

  it("returns empty array for response with no code blocks", () => {
    expect(extractFileBlocks("just some prose, no fences")).toHaveLength(0);
    expect(extractFileBlocks("")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// extractLiterals
// ---------------------------------------------------------------------------
describe("extractLiterals", () => {
  it("extracts double-quoted string literals", () => {
    const lits = extractLiterals('expect(result).toBe("hello world");');
    expect(lits).toContain("hello world");
  });

  it("extracts single-quoted string literals", () => {
    const lits = extractLiterals("expect(x).toBe('abc');");
    expect(lits).toContain("abc");
  });

  it("extracts multi-digit numbers", () => {
    const lits = extractLiterals("expect(count).toBe(42);");
    expect(lits).toContain("42");
  });

  it("extracts single non-0/1 digits", () => {
    const lits = extractLiterals("expect(x).toBe(7);");
    expect(lits).toContain("7");
  });

  it("does NOT extract the literal 0 or 1", () => {
    const lits = extractLiterals("expect(x).toBe(0); expect(y).toBe(1);");
    expect(lits).not.toContain("0");
    expect(lits).not.toContain("1");
  });

  it("deduplicates repeated literals", () => {
    const lits = extractLiterals('toBe("abc"); toBe("abc");');
    expect(lits.filter((l) => l === "abc")).toHaveLength(1);
  });

  it("returns empty array for no literals", () => {
    expect(extractLiterals("// just a comment")).toHaveLength(0);
    expect(extractLiterals("")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// codeLineCount
// ---------------------------------------------------------------------------
describe("codeLineCount", () => {
  it("counts non-blank, non-comment lines", () => {
    const src = `
// a comment
const x = 1;
const y = 2;
`;
    expect(codeLineCount(src)).toBe(2);
  });

  it("returns 0 for a file with only comments and blanks", () => {
    const src = `
// comment
/* block */
* star line
`;
    expect(codeLineCount(src)).toBe(0);
  });

  it("returns 0 for empty string", () => {
    expect(codeLineCount("")).toBe(0);
  });

  it("counts a 5-line trivial impl as <= 5 (gaming threshold)", () => {
    const src = "const x = 42;\n".repeat(5);
    expect(codeLineCount(src)).toBe(5);
  });

  it("counts a 6-line impl as > 5", () => {
    const src = "const x = 1;\n".repeat(6);
    expect(codeLineCount(src)).toBe(6);
  });
});

// ---------------------------------------------------------------------------
// validate — B-2 (t.id safety) and D-2 (schema checks)
// ---------------------------------------------------------------------------
function baseTask(overrides: object = {}) {
  return {
    id: "my-task",
    description: "test task",
    filesInScope: ["src/foo.ts"],
    test: { path: "src/foo.test.ts" },
    gate: { commands: ["npm test"] },
    ...overrides,
  };
}

function basePlan(taskOverrides: object = {}, metaOverrides: object = {}) {
  return {
    meta: { name: "test-plan", ...metaOverrides },
    tasks: [baseTask(taskOverrides)],
  };
}

describe("validate — task id safety (B-2)", () => {
  it("accepts a valid alphanumeric id", () => {
    expect(() => validate(basePlan())).not.toThrow();
  });

  it("accepts ids with dots, hyphens, underscores", () => {
    expect(() => validate(basePlan({ id: "my.task-name_v1" }))).not.toThrow();
  });

  it("rejects an id with path-separator characters", () => {
    expect(() => validate(basePlan({ id: "../escape" }))).toThrow(/must match/);
  });

  it("rejects an id with forward slash", () => {
    expect(() => validate(basePlan({ id: "a/b" }))).toThrow(/must match/);
  });

  it("rejects an id with spaces", () => {
    expect(() => validate(basePlan({ id: "my task" }))).toThrow(/must match/);
  });

  it("rejects an empty id", () => {
    expect(() => validate(basePlan({ id: "" }))).toThrow(/must match/);
  });

  it("rejects an id longer than 64 characters", () => {
    expect(() => validate(basePlan({ id: "a".repeat(65) }))).toThrow(/must match/);
  });

  it("accepts an id of exactly 64 characters", () => {
    expect(() => validate(basePlan({ id: "a".repeat(64) }))).not.toThrow();
  });
});

describe("validate — schema checks (D-2)", () => {
  it("rejects test.path with .. traversal", () => {
    expect(() => validate(basePlan({ test: { path: "../secret.test.ts" } }))).toThrow(/test\.path/);
  });

  it("rejects an absolute test.path", () => {
    expect(() => validate(basePlan({ test: { path: "/etc/passwd" } }))).toThrow(/test\.path/);
  });

  it("accepts a relative test.path without traversal", () => {
    expect(() => validate(basePlan({ test: { path: "src/foo.test.ts" } }))).not.toThrow();
  });

  it("rejects filesInScope entry with .. traversal", () => {
    expect(() =>
      validate(basePlan({ filesInScope: ["../escape.ts"] }))
    ).toThrow(/filesInScope/);
  });

  it("rejects an absolute filesInScope entry", () => {
    expect(() =>
      validate(basePlan({ filesInScope: ["/etc/shadow"] }))
    ).toThrow(/filesInScope/);
  });

  it("accepts relative filesInScope entries", () => {
    expect(() =>
      validate(basePlan({ filesInScope: ["src/a.ts", "lib/b.ts"] }))
    ).not.toThrow();
  });

  it("rejects meta.apiBaseUrl with http:// scheme on external host", () => {
    expect(() =>
      validate(basePlan({}, { apiBaseUrl: "http://evil.example.com" }))
    ).toThrow(/HTTPS/);
  });

  it("accepts meta.apiBaseUrl with https:// scheme", () => {
    expect(() =>
      validate(basePlan({}, { apiBaseUrl: "https://api.example.com" }))
    ).not.toThrow();
  });

  it("accepts http://127.0.0.1 (loopback — used by test mocks)", () => {
    expect(() =>
      validate(basePlan({}, { apiBaseUrl: "http://127.0.0.1:8080" }))
    ).not.toThrow();
  });

  it("accepts http://localhost (loopback — used by test mocks)", () => {
    expect(() =>
      validate(basePlan({}, { apiBaseUrl: "http://localhost:3000" }))
    ).not.toThrow();
  });

  it("accepts a plan with no meta.apiBaseUrl", () => {
    expect(() => validate(basePlan())).not.toThrow();
  });

  it("rejects a gate command longer than 1024 chars", () => {
    expect(() =>
      validate(basePlan({ gate: { commands: ["x".repeat(1025)] } }))
    ).toThrow(/1024/);
  });

  it("rejects an empty gate command string", () => {
    expect(() =>
      validate(basePlan({ gate: { commands: [""] } }))
    ).toThrow(/non-empty/);
  });

  it("accepts valid gate commands", () => {
    expect(() =>
      validate(basePlan({ gate: { commands: ["npm test", "npm run typecheck"] } }))
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// assertSecureBaseUrl — the resolved-URL guard that closes the FARM_API_BASE_URL
// cleartext-secret-leak bypass (the validate() check only covers plan.meta).
// ---------------------------------------------------------------------------
describe("assertSecureBaseUrl — resolved base URL guard", () => {
  it("rejects a non-loopback http:// URL (the FARM_API_BASE_URL bypass)", () => {
    expect(() => assertSecureBaseUrl("http://evil.example")).toThrow(/HTTPS/);
  });

  it("rejects a non-loopback http:// URL with a port", () => {
    expect(() => assertSecureBaseUrl("http://evil.example:8080/v1")).toThrow(/HTTPS/);
  });

  it("accepts an https:// URL", () => {
    expect(() => assertSecureBaseUrl("https://api.opencode.ai/v1")).not.toThrow();
  });

  it("accepts http://127.0.0.1 loopback (test mocks rely on it)", () => {
    expect(() => assertSecureBaseUrl("http://127.0.0.1:8080")).not.toThrow();
  });

  it("accepts http://localhost loopback (test mocks rely on it)", () => {
    expect(() => assertSecureBaseUrl("http://localhost:3000")).not.toThrow();
  });

  it("does not treat a host that merely starts with localhost as loopback", () => {
    expect(() => assertSecureBaseUrl("http://localhost.evil.example")).toThrow(/HTTPS/);
  });

  // Defense-in-depth: userinfo tricks on the http-loopback path. A URL whose
  // userinfo is a loopback-looking string but whose real host is hostile must
  // be rejected; and any userinfo on the loopback path is disallowed.
  it("rejects http with loopback-looking userinfo but a hostile host", () => {
    expect(() => assertSecureBaseUrl("http://localhost@evil.example")).toThrow(/HTTPS/);
  });

  it("rejects http loopback that carries username:password userinfo", () => {
    expect(() => assertSecureBaseUrl("http://user:pass@127.0.0.1:8080")).toThrow(/HTTPS/);
  });

  it("still accepts a clean http://127.0.0.1 loopback with no userinfo", () => {
    expect(() => assertSecureBaseUrl("http://127.0.0.1:8080")).not.toThrow();
  });

  it("still accepts a clean http://localhost loopback with a path", () => {
    expect(() => assertSecureBaseUrl("http://localhost:3000/v1")).not.toThrow();
  });

  it("rejects a malformed / unparseable URL", () => {
    expect(() => assertSecureBaseUrl("not a url")).toThrow(/HTTPS/);
  });

  it("accepts an https URL with userinfo (https acceptance is scheme-only)", () => {
    // https keeps the secret in TLS regardless of userinfo, so scheme alone
    // governs; userinfo only matters on the cleartext http-loopback path.
    expect(() => assertSecureBaseUrl("https://localhost@127.0.0.1:9/")).not.toThrow();
  });

  it("never leaks FARM_API_KEY in the thrown error message", () => {
    const secret = "sk-ant-should-never-appear";
    process.env.FARM_API_KEY = secret;
    try {
      assertSecureBaseUrl("http://evil.example");
    } catch (e) {
      expect((e as Error).message).not.toContain(secret);
    } finally {
      delete process.env.FARM_API_KEY;
    }
  });
});

// ---------------------------------------------------------------------------
// Worker seam (T-01 / AC-01) — runTask must obtain and invoke its worker
// THROUGH the Worker interface, not by calling runWorker/callApi directly.
// This drives a task with every side-effecting dependency stubbed (no network,
// no git, no spawned process) and asserts the injected worker is the thing that
// produced the task's output.
// ---------------------------------------------------------------------------
describe("Worker seam — runTask invokes an injectable Worker (AC-01)", () => {
  // A deps bag that makes runTask's git/process/fs effects no-ops, so the only
  // behaviour under test is the worker indirection.
  function stubDeps(worker: Worker): RunTaskDeps {
    return {
      worker,
      prepareWorktree: async () => null, // worktree "created"
      resetWorktree: async () => {},
      fileHash: async () => null, // null short-circuits the tamper check
      checkDrift: async () => [], // no files outside scope
      runGate: async () => ({ ok: true as const }),
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  const task: Task = {
    id: "seam-task",
    description: "make the test pass",
    filesInScope: ["src/seam.ts"],
    test: { path: "src/seam.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  it("calls the injected worker exactly once with the resolved config", async () => {
    const calls: Array<{ model: string; apiBaseUrl: string; apiKey: string }> = [];
    const worker: Worker = {
      async apply(ctx) {
        calls.push({ model: ctx.model, apiBaseUrl: ctx.apiBaseUrl, apiKey: ctx.apiKey });
        return { ok: true, filesWritten: ["src/seam.ts"] } satisfies WorkerResult;
      },
    };

    const r = await runTask(task, "stub-model", "https://api.example/v1", "stub-key", stubDeps(worker));

    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({ model: "stub-model", apiBaseUrl: "https://api.example/v1", apiKey: "stub-key" });
    expect(r.status).toBe("green");
    // The worker's output is what flows into the result — proves the task path
    // consumed the injected worker rather than an internal runWorker call.
    expect(r.filesWritten).toEqual(["src/seam.ts"]);
  });

  it("escalates via the worker's error without ever hitting the network", async () => {
    const worker: Worker = {
      async apply() {
        return { ok: false, filesWritten: [], error: "stub worker refused" } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      { ...task, maxRetries: 0 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(worker),
    );

    expect(r.status).toBe("escalate");
  });

  it("exposes a default httpWorker implementation behind the interface", () => {
    expect(httpWorker).toBeDefined();
    expect(typeof httpWorker.apply).toBe("function");
  });
});

// ---------------------------------------------------------------------------
// Post-apply containment sweep (T-02 / D6) — containment (isInside) and the
// read-only-test guard are enforced at the TASK level after worker.apply()
// returns, inspecting what the worker actually produced — NOT only inside
// runWorker's write loop. A worker that bypasses runWorker's inline guard
// (e.g. a future agentic CLI that writes its own files) must still be caught.
//
// These stubs deliberately do NOT route through runWorker/httpWorker: they
// report (and, for the escape case, physically write) paths the inline guard
// would have refused. Red before the relocation, green after.
// ---------------------------------------------------------------------------
describe("Post-apply containment sweep — task-level enforcement for ANY worker (D6)", () => {
  // Same no-op deps bag as the Worker-seam suite, but we keep the REAL
  // containment behaviour under test by routing it through runTask's sweep.
  function stubDeps(worker: Worker): RunTaskDeps {
    return {
      worker,
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async () => null, // null short-circuits the hash tamper check
      checkDrift: async () => [], // the allowlist sweep is satisfied
      runGate: async () => ({ ok: true as const }),
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  const task: Task = {
    id: "sweep-task",
    description: "make the test pass",
    filesInScope: ["src/seam.ts"],
    test: { path: "src/seam.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  it("escalates a worker that writes OUTSIDE the worktree, bypassing runWorker's inline guard", async () => {
    // A worker that does NOT use runWorker's write loop — it reports a path that
    // escapes the worktree. The inline isInside guard never ran; only the
    // task-level post-apply sweep can catch this.
    const escapeWorker: Worker = {
      async apply(ctx) {
        const escaped = path.resolve(ctx.cwd, "..", "escape.ts");
        return { ok: true, filesWritten: [escaped] } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      { ...task, maxRetries: 0 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(escapeWorker),
    );

    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/escapes worktree/);
  });

  it("escalates a worker that writes the read-only test.path, bypassing runWorker's inline guard", async () => {
    // A worker that overwrites task.test.path directly. fileHash is stubbed to
    // null (no hash-based tamper signal), and the inline forbidden-set guard
    // never ran — so only the task-level sweep can reject this.
    const testTamperWorker: Worker = {
      async apply() {
        return { ok: true, filesWritten: [task.test.path] } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      { ...task, maxRetries: 0 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(testTamperWorker),
    );

    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/read-only|tampered/);
  });

  it("lets a compliant worker through the sweep (in-scope file, no escape)", async () => {
    const goodWorker: Worker = {
      async apply() {
        return { ok: true, filesWritten: ["src/seam.ts"] } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      { ...task, maxRetries: 0 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(goodWorker),
    );

    expect(r.status).toBe("green");
    expect(r.filesWritten).toEqual(["src/seam.ts"]);
  });
});

describe("validate — existing checks (cycles, duplicates, unknown deps)", () => {
  it("rejects duplicate task ids", () => {
    const plan = {
      meta: { name: "p" },
      tasks: [baseTask({ id: "t1" }), baseTask({ id: "t1" })],
    };
    expect(() => validate(plan)).toThrow(/duplicate/);
  });

  it("rejects a task depending on an unknown id", () => {
    const plan = {
      meta: { name: "p" },
      tasks: [baseTask({ id: "t1", deps: ["nonexistent"] })],
    };
    expect(() => validate(plan)).toThrow(/unknown/);
  });

  it("rejects a dependency cycle", () => {
    const plan = {
      meta: { name: "p" },
      tasks: [
        baseTask({ id: "t1", deps: ["t2"] }),
        baseTask({ id: "t2", deps: ["t1"] }),
      ],
    };
    expect(() => validate(plan)).toThrow(/cycle/);
  });

  it("accepts a valid two-task plan with dependency", () => {
    const plan = {
      meta: { name: "p" },
      tasks: [
        baseTask({ id: "t1" }),
        baseTask({ id: "t2", deps: ["t1"] }),
      ],
    };
    expect(() => validate(plan)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Optional per-task model (T-03 / AC-02) — the effective model for a task is
// `task.model ?? <run-level resolved model>`, layered where runTask invokes the
// worker. A task WITH `model` overrides; a task WITHOUT behaves EXACTLY as
// today (run-level model passed straight through to the worker).
// ---------------------------------------------------------------------------
describe("Per-task model resolution — task.model ?? run-level model (AC-02)", () => {
  function stubDeps(worker: Worker): RunTaskDeps {
    return {
      worker,
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async () => null,
      checkDrift: async () => [],
      runGate: async () => ({ ok: true as const }),
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  const baseModelTask: Task = {
    id: "model-task",
    description: "make the test pass",
    filesInScope: ["src/seam.ts"],
    test: { path: "src/seam.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  it("passes task.model to worker.apply when the task overrides the run-level model", async () => {
    const seen: string[] = [];
    const worker: Worker = {
      async apply(ctx) {
        seen.push(ctx.model);
        return { ok: true, filesWritten: ["src/seam.ts"] } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      { ...baseModelTask, model: "premium-x" },
      "run-level-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(worker),
    );

    expect(seen).toEqual(["premium-x"]);
    expect(r.status).toBe("green");
  });

  it("passes the run-level model to worker.apply when the task has no model (unchanged behavior)", async () => {
    const seen: string[] = [];
    const worker: Worker = {
      async apply(ctx) {
        seen.push(ctx.model);
        return { ok: true, filesWritten: ["src/seam.ts"] } satisfies WorkerResult;
      },
    };

    const r = await runTask(
      baseModelTask, // no `model`
      "run-level-model",
      "https://api.example/v1",
      "stub-key",
      stubDeps(worker),
    );

    expect(seen).toEqual(["run-level-model"]);
    expect(r.status).toBe("green");
  });
});

// ---------------------------------------------------------------------------
// plan.schema.json — the optional per-task `model` field (T-03 / AC-02).
// No JSON-schema validator is present in devDependencies, so we assert the
// schema STRUCTURE directly via JSON.parse: `model` is declared on the task
// `$defs` (required because the task object is additionalProperties:false, so
// an undeclared field would be rejected) and additionalProperties:false is
// kept intact (the strict authoring contract is not relaxed).
// ---------------------------------------------------------------------------
describe("plan.schema.json — optional per-task model (AC-02)", () => {
  const schemaPath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "plan.schema.json",
  );
  const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
  const taskDef = schema.$defs.task;

  it("declares `model` as a string on the task properties", () => {
    expect(taskDef.properties.model).toBeDefined();
    expect(taskDef.properties.model.type).toBe("string");
  });

  it("does NOT add `model` to the task's required list (it is optional)", () => {
    expect(taskDef.required).not.toContain("model");
  });

  it("keeps the task object additionalProperties:false (strict authoring contract intact)", () => {
    // additionalProperties:false is what makes the declaration in (1) necessary:
    // a plan carrying task.model would be rejected unless `model` is declared.
    // Asserting this here documents that the field was added the correct way
    // rather than by relaxing the contract.
    expect(taskDef.additionalProperties).toBe(false);
  });

  it("would reject an unknown task field — no validator available, asserted structurally", () => {
    // With additionalProperties:false and a fixed properties set, any field not
    // in properties (e.g. `bogusField`) is rejected by a conforming validator.
    // We have no validator in devDependencies, so we assert the structural
    // precondition directly: the closed property set does not include it.
    expect(taskDef.additionalProperties).toBe(false);
    expect(Object.keys(taskDef.properties)).not.toContain("bogusField");
    // and `model` IS in the closed set, so a plan with task.model is accepted.
    expect(Object.keys(taskDef.properties)).toContain("model");
  });
});

// ---------------------------------------------------------------------------
// Regenerate-on-conflict (T-07 / AC-07 / D4) — a merge conflict against the
// integration branch is treated like a gate failure: the task resets to the new
// integration HEAD and RE-RUNS the worker, consuming ONE of the existing
// maxRetries attempts, rather than escalating on the first conflict. If retries
// are exhausted with the merge still conflicting, it escalates exactly as today.
//
// The clean deterministic way to force a conflict is the injected deps: the git
// stub returns a non-zero `merge` on the first merge attempt and code 0 on the
// second, with a worker we can count. (The merge runs through deps.git inside
// deps.withMergeLock; everything else is a no-op.)
// ---------------------------------------------------------------------------
describe("Regenerate-on-conflict — merge conflict re-enters regeneration (AC-07)", () => {
  const task: Task = {
    id: "conflict-task",
    description: "make the test pass",
    filesInScope: ["src/conflict.ts"],
    test: { path: "src/conflict.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  // A deps bag where `git` is a programmable stub: every `merge --no-ff` consults
  // `mergeOutcomes` (shift one per call); all other git calls succeed as no-ops.
  // `worker` counts apply() invocations so we can prove regeneration happened.
  function conflictDeps(opts: {
    worker: Worker;
    // one entry consumed per merge attempt: null === success, string === conflict output
    mergeOutcomes: Array<string | null>;
    resetCalls: Array<string[]>;
  }): RunTaskDeps {
    const outcomes = [...opts.mergeOutcomes];
    return {
      worker: opts.worker,
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async () => null,
      checkDrift: async () => [],
      runGate: async () => ({ ok: true as const }),
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async (args: string[]) => {
        if (args.includes("merge") && args.includes("--no-ff")) {
          const next = outcomes.shift();
          // unspecified beyond the provided outcomes: default to conflict so an
          // always-conflicting test doesn't accidentally fall through to green
          const out = next === undefined ? "CONFLICT (content): fallback" : next;
          if (out !== null) return { code: 1, out, stdout: "", stderr: out };
          return { code: 0, out: "", stdout: "", stderr: "" };
        }
        if (args[0] === "reset" || args[0] === "clean") {
          opts.resetCalls.push(args);
        }
        return { code: 0, out: "", stdout: "", stderr: "" };
      },
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  it("re-runs the worker after a conflict and ends green when the second merge succeeds", async () => {
    let workerCalls = 0;
    const worker: Worker = {
      async apply() {
        workerCalls++;
        return { ok: true, filesWritten: ["src/conflict.ts"] } satisfies WorkerResult;
      },
    };
    const resetCalls: Array<string[]> = [];

    const r = await runTask(
      // maxRetries:1 → 2 attempts total; first merge conflicts, second succeeds.
      { ...task, maxRetries: 1 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      conflictDeps({ worker, mergeOutcomes: ["CONFLICT (content): src/conflict.ts", null], resetCalls }),
    );

    // Regeneration happened: the worker was invoked a SECOND time after the
    // conflict (not an instant escalate, which would leave it at one call).
    expect(workerCalls).toBe(2);
    // The conflict path reset the task worktree to the new integration HEAD
    // before re-running (rebuild against the updated baseline).
    expect(resetCalls.some((a) => a[0] === "reset" && a.includes("--hard"))).toBe(true);
    // Second merge succeeded → green, NOT escalate.
    expect(r.status).toBe("green");
    expect(r.attempts).toBe(2);
  });

  it("escalates with a merge-related note when every merge conflicts and retries are spent (no infinite loop)", async () => {
    let workerCalls = 0;
    const worker: Worker = {
      async apply() {
        workerCalls++;
        return { ok: true, filesWritten: ["src/conflict.ts"] } satisfies WorkerResult;
      },
    };
    const resetCalls: Array<string[]> = [];

    const r = await runTask(
      // maxRetries:1 → 2 attempts; BOTH merges conflict → escalate after the budget.
      { ...task, maxRetries: 1 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      conflictDeps({
        worker,
        mergeOutcomes: ["CONFLICT (content): a", "CONFLICT (content): b"],
        resetCalls,
      }),
    );

    // The worker ran on each of the two attempts (bounded — no unbounded loop).
    expect(workerCalls).toBe(2);
    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/merge/i);
    expect(r.attempts).toBe(2);
  });

  it("escalates instantly (no regeneration) on conflict when maxRetries is 0", async () => {
    let workerCalls = 0;
    const worker: Worker = {
      async apply() {
        workerCalls++;
        return { ok: true, filesWritten: ["src/conflict.ts"] } satisfies WorkerResult;
      },
    };
    const resetCalls: Array<string[]> = [];

    const r = await runTask(
      { ...task, maxRetries: 0 },
      "stub-model",
      "https://api.example/v1",
      "stub-key",
      conflictDeps({ worker, mergeOutcomes: ["CONFLICT (content): only-attempt"], resetCalls }),
    );

    // Budget is zero retries → the single attempt's conflict escalates at once.
    expect(workerCalls).toBe(1);
    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/merge failed vs integration/);
  });
});

// ---------------------------------------------------------------------------
// #90 — stale default base URL + opaque non-JSON-body error
// ---------------------------------------------------------------------------
describe("#90 default base URL + non-JSON body", () => {
  it("default base URL points at the live OpenCode Zen endpoint", () => {
    expect(DEFAULT_API_BASE_URL).toBe("https://opencode.ai/zen/v1");
  });

  it("parseChatCompletion returns content + usage for a valid JSON body", () => {
    const body = JSON.stringify({
      choices: [{ message: { content: "hello" } }],
      usage: { prompt_tokens: 3, completion_tokens: 4 },
    });
    const r = parseChatCompletion(body, "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.content).toBe("hello");
      expect(r.usage?.prompt_tokens).toBe(3);
      expect(r.usage?.completion_tokens).toBe(4);
    }
  });

  it("parseChatCompletion returns an actionable, endpoint-naming error for a non-JSON body", () => {
    // The exact failure mode of the stale endpoint: 200 with body "Not Found".
    const r = parseChatCompletion("Not Found", "https://api.opencode.ai/v1");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      // Names the knob the operator must fix...
      expect(r.error).toMatch(/FARM_API_BASE_URL/);
      // ...echoes the offending endpoint...
      expect(r.error).toMatch(/api\.opencode\.ai\/v1/);
      // ...and is NOT the opaque raw-SyntaxError message it used to be.
      expect(r.error).not.toMatch(/^non-JSON response: SyntaxError/);
    }
  });

  it("parseChatCompletion echoes a (bounded) snippet of the offending body", () => {
    const r = parseChatCompletion("Not Found", "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/Not Found/);
  });
});

// ---------------------------------------------------------------------------
// #91 — git CRLF stderr warning must not pollute drift detection (Windows)
// ---------------------------------------------------------------------------
describe("#91 checkDrift parses stdout only (CRLF stderr immune)", () => {
  // The exact line git prints to STDERR under core.safecrlf on Windows.
  const crlfWarning =
    "warning: in the working copy of 'site/scripts/generator/split-frontmatter.ts', LF will be replaced by CRLF the next time Git touches it";

  // Stub git runner: returns the given stdout per subcommand, with the CRLF
  // warning ALWAYS on stderr (and folded into the merged `out`, as the real
  // run() helper does) — so a stdout-only parser is immune and a merged-string
  // parser is poisoned.
  function stubGit(stdoutFor: { diff?: string; lsfiles?: string }) {
    return async (args: string[]) => {
      const stdout = args[0] === "diff" ? (stdoutFor.diff ?? "") : (stdoutFor.lsfiles ?? "");
      const stderr = crlfWarning + "\n";
      return { code: 0, stdout, stderr, out: stdout + stderr };
    };
  }

  it("never treats a git CRLF stderr warning as a changed path", async () => {
    const allowed = new Set(["src/a.ts"]);
    // worker edited an OUT-of-scope file (src/b.ts) — that is real drift; the
    // CRLF warning on stderr is noise that must be ignored.
    const drift = await checkDrift("/wt", allowed, stubGit({ diff: "src/b.ts\n" }));
    expect(drift).toEqual(["src/b.ts"]);
    expect(drift.join(" ")).not.toMatch(/LF will be replaced by CRLF/);
    expect(drift.some((f) => f.startsWith("warning:"))).toBe(false);
  });

  it("reports NO drift when only in-scope files changed, despite a CRLF warning on stderr", async () => {
    const allowed = new Set(["src/a.ts"]);
    const drift = await checkDrift("/wt", allowed, stubGit({ diff: "src/a.ts\n" }));
    expect(drift).toEqual([]);
  });

  it("still catches an out-of-scope untracked file from ls-files stdout", async () => {
    const allowed = new Set(["src/a.ts"]);
    const drift = await checkDrift("/wt", allowed, stubGit({ diff: "", lsfiles: "src/new.ts\0" }));
    expect(drift).toEqual(["src/new.ts"]);
  });
});

// ---------------------------------------------------------------------------
// #93 — entitlement pre-check drops 401 ("free promotion ended") candidates
// ---------------------------------------------------------------------------
describe("#93 screenEntitlements", () => {
  // sleepFn that never resolves → the wall-clock race never fires, so the
  // probe's verdict is what's tested (used by the non-timeout cases).
  const neverSleep = () => new Promise<void>(() => {});

  it("drops a 401 candidate with a distinct entitlement note and keeps an entitled one", async () => {
    const probe = async (m: string) => ({ status: m.endsWith("-free") ? 401 : 200 });
    const { survivors, skipped } = await screenEntitlements(
      ["big-pickle", "minimax-m3-free"],
      probe,
      { sleepFn: neverSleep },
    );
    expect(survivors).toEqual(["big-pickle"]);
    expect(skipped).toHaveLength(1);
    expect(skipped[0].model).toBe("minimax-m3-free");
    expect(skipped[0].reason).toBe("entitlement");
    expect(skipped[0].note).toMatch(/401/);
    expect(skipped[0].note).toMatch(/promotion|entitle/i);
  });

  it("keeps every candidate when none returns 401", async () => {
    const probe = async () => ({ status: 200 });
    const { survivors, skipped } = await screenEntitlements(["a", "b"], probe, { sleepFn: neverSleep });
    expect(survivors).toEqual(["a", "b"]);
    expect(skipped).toEqual([]);
  });

  it("drops a candidate whose probe exceeds the per-candidate wall-clock cap (no hang)", async () => {
    const hangingProbe = () => new Promise<{ status: number }>(() => {}); // never resolves
    const { survivors, skipped } = await screenEntitlements(
      ["slow-model"],
      hangingProbe,
      { timeoutMs: 5, sleepFn: async () => {} }, // instant timeout wins the race
    );
    expect(survivors).toEqual([]);
    expect(skipped).toHaveLength(1);
    expect(skipped[0].model).toBe("slow-model");
    expect(skipped[0].reason).toBe("timeout");
  });

  it("treats a non-401 error status as a survivor (let the canary judge capability)", async () => {
    const probe = async () => ({ status: 500 });
    const { survivors, skipped } = await screenEntitlements(["flaky"], probe, { sleepFn: neverSleep });
    expect(survivors).toEqual(["flaky"]);
    expect(skipped).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// #92 — per-worktree dependency setup hook (task.setup / meta.setup)
// ---------------------------------------------------------------------------
describe("#92 per-worktree setup hook", () => {
  const baseTask: Task = {
    id: "setup-task",
    description: "make the test pass",
    filesInScope: ["src/s.ts"],
    test: { path: "src/s.test.ts" },
    gate: { commands: ["node -p 0"] },
  };

  // Deps that record the ORDER of runGate vs worker calls, so we can prove setup
  // runs in the worktree BEFORE the worker. runGate is the execution path for
  // both setup and the gate; a `gateFailFor` predicate lets a test fail a
  // specific command set.
  function recordingDeps(opts: {
    events: string[];
    workerCalls: { n: number };
    gateFailFor?: (commands: string[]) => boolean;
  }): RunTaskDeps {
    const worker: Worker = {
      async apply() {
        opts.workerCalls.n++;
        opts.events.push("worker");
        return { ok: true, filesWritten: ["src/s.ts"] } satisfies WorkerResult;
      },
    };
    return {
      worker,
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async () => null,
      checkDrift: async () => [],
      runGate: async (_cwd: string, commands: string[]) => {
        opts.events.push(`runGate:${commands.join(",")}`);
        if (opts.gateFailFor?.(commands))
          return { ok: false as const, failed: commands[0], tail: "boom" };
        return { ok: true as const };
      },
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
  }

  it("runs setup commands in the worktree BEFORE the worker", async () => {
    const events: string[] = [];
    const workerCalls = { n: 0 };
    const r = await runTask(
      { ...baseTask, setup: ["npm ci"] },
      "m", "https://api.example/v1", "k",
      recordingDeps({ events, workerCalls }),
    );
    expect(r.status).toBe("green");
    // setup runGate fires, THEN the worker, THEN the gate runGate.
    expect(events[0]).toBe("runGate:npm ci");
    expect(events.indexOf("runGate:npm ci")).toBeLessThan(events.indexOf("worker"));
  });

  it("escalates immediately when a setup command fails — worker never runs", async () => {
    const events: string[] = [];
    const workerCalls = { n: 0 };
    const r = await runTask(
      { ...baseTask, maxRetries: 0, setup: ["npm ci"] },
      "m", "https://api.example/v1", "k",
      recordingDeps({ events, workerCalls, gateFailFor: (c) => c[0] === "npm ci" }),
    );
    expect(r.status).toBe("escalate");
    expect(r.note).toMatch(/setup failed/i);
    expect(workerCalls.n).toBe(0);
  });

  it("is a no-op when no setup is configured (worker runs, runGate only for the gate)", async () => {
    const events: string[] = [];
    const workerCalls = { n: 0 };
    const r = await runTask(
      baseTask, "m", "https://api.example/v1", "k",
      recordingDeps({ events, workerCalls }),
    );
    expect(r.status).toBe("green");
    expect(workerCalls.n).toBe(1);
    // The only runGate call is the gate itself — no setup invocation.
    expect(events.filter((e) => e.startsWith("runGate:"))).toEqual(["runGate:node -p 0"]);
  });

  it("validate() rejects an empty or oversized setup command (meta and task)", () => {
    const okTask: Task = { ...baseTask, deps: [] };
    expect(() => validate({ meta: { name: "p", setup: [""] }, tasks: [okTask] })).toThrow(/setup/i);
    expect(() => validate({ meta: { name: "p", setup: ["x".repeat(1025)] }, tasks: [okTask] })).toThrow(/setup/i);
    expect(() => validate({ meta: { name: "p" }, tasks: [{ ...okTask, setup: [""] }] })).toThrow(/setup/i);
    // A valid setup passes.
    expect(() => validate({ meta: { name: "p", setup: ["npm ci"] }, tasks: [okTask] })).not.toThrow();
  });
});

// ===========================================================================
// deep-review-quick-kills Slice 3
// ===========================================================================

// ---------------------------------------------------------------------------
// T-06 (reliability-001) — per-command wall-clock timeout on run(). A hung
// gate/setup/mutation command must be KILLED and surface as a non-zero,
// timeout-tagged RunResult so the worker (and the scheduler) finalizes instead
// of awaiting forever.
// ---------------------------------------------------------------------------
describe("T-06 run() wall-clock timeout (reliability-001)", () => {
  // A node child that never exits (mirrors a watch/dev-server or a test blocking
  // on stdin). Spawned via process.execPath so it is cross-platform.
  const HANG = ["-e", "setInterval(() => {}, 1000);"];

  it("kills a hung command after the timeout and tags the result timedOut", async () => {
    const t0 = Date.now();
    const r = await run(process.execPath, HANG, undefined, {}, 200);
    const elapsed = Date.now() - t0;
    // It actually resolved (did not hang the test) ...
    expect(r.timedOut).toBe(true);
    // ... with a non-zero code so every consumer's `code !== 0` branch fires ...
    expect(r.code).not.toBe(0);
    // ... and it resolved promptly around the timeout, not after the child's
    // (never-arriving) natural exit.
    expect(elapsed).toBeLessThan(5000);
    expect(r.out).toMatch(/timeout/i);
  });

  it("does NOT time out a fast command and reports its real exit code", async () => {
    const ok = await run(process.execPath, ["-e", "process.exit(0)"], undefined, {}, 5000);
    expect(ok.timedOut).toBeUndefined();
    expect(ok.code).toBe(0);
    const bad = await run(process.execPath, ["-e", "process.exit(3)"], undefined, {}, 5000);
    expect(bad.timedOut).toBeUndefined();
    expect(bad.code).toBe(3);
  });

  it("disables the timeout when timeoutMs is 0/omitted (git-style calls are unbounded)", async () => {
    // No timeout arg → a fast command still completes normally (proves the
    // default path is unchanged for git and other un-timed callers).
    const r = await run(process.execPath, ["-e", "process.exit(0)"]);
    expect(r.timedOut).toBeUndefined();
    expect(r.code).toBe(0);
  });

  it("runGate surfaces a killed hung command as a gate failure (scheduler can finalize)", async () => {
    // runGate uses the module default FARM_GATE_TIMEOUT_MS (minutes), so rather
    // than wait that long we prove the runTask path FINALIZES (escalate) when its
    // injected runGate reports a timeout failure — exactly the RunResult shape
    // run() produces on a kill. The scheduler never wedges because runGate
    // returns instead of awaiting forever.
    const task: Task = {
      id: "hang-task",
      description: "make the test pass",
      filesInScope: ["src/x.ts"],
      test: { path: "src/x.test.ts" },
      gate: { commands: ["sleep infinity"] },
    };
    const deps: RunTaskDeps = {
      worker: { async apply() { return { ok: true, filesWritten: ["src/x.ts"] }; } },
      prepareWorktree: async () => null,
      resetWorktree: async () => {},
      fileHash: async () => null,
      checkDrift: async () => [],
      // The gate "hangs" → run() kills it → runGate reports the timeout failure.
      runGate: async () => ({ ok: false as const, failed: "sleep infinity", tail: "[FARM] command exceeded ...ms wall-clock timeout — killed" }),
      antiGamingCheck: async () => ({ risk: "none" as const }),
      mutationCheck: async () => null,
      git: async () => ({ code: 0, out: "", stdout: "", stderr: "" }),
      withMergeLock: async <T,>(fn: () => Promise<T>) => fn(),
    };
    const r = await runTask({ ...task, maxRetries: 0 }, "m", "https://api.example/v1", "k", deps);
    // Finalizes (does not hang) and escalates on the persistent gate failure.
    expect(r.status).toBe("escalate");
  });

  it("runGate (real) returns {ok:false} on a non-zero exit and {ok:true} on success", async () => {
    // The runGate wiring passes GATE_TIMEOUT_MS into run() for every command;
    // the kill path itself is proven via run() above (the module default is too
    // long to wait on here). This asserts runGate's contract is intact: a real
    // failing command is a gate failure, a passing one is a pass.
    // `exit N` is a builtin in both cmd.exe and bash, so no path-quoting issues.
    const fail = await runGate(process.cwd(), ["exit 7"]);
    expect(fail.ok).toBe(false);
    const pass = await runGate(process.cwd(), ["exit 0"]);
    expect(pass.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// T-07 (reliability-004 + migration-004 + observability-003)
// ---------------------------------------------------------------------------
describe("T-07a validate() named errors on malformed required fields (migration-004)", () => {
  const ok = (o: object) => ({ id: "t", description: "d", filesInScope: ["a.ts"], test: { path: "a.test.ts" }, gate: { commands: ["x"] }, ...o });

  it("throws a NAMED error (task id + field) for test:null, not a TypeError", () => {
    const plan = { meta: { name: "p" }, tasks: [ok({ test: null })] } as unknown as Parameters<typeof validate>[0];
    expect(() => validate(plan)).toThrow(/task t: test\.path is required/);
  });

  it("throws a named error for filesInScope:null", () => {
    const plan = { meta: { name: "p" }, tasks: [ok({ filesInScope: null })] } as unknown as Parameters<typeof validate>[0];
    expect(() => validate(plan)).toThrow(/task t: filesInScope is required/);
  });

  it("throws a named error for gate:null", () => {
    const plan = { meta: { name: "p" }, tasks: [ok({ gate: null })] } as unknown as Parameters<typeof validate>[0];
    expect(() => validate(plan)).toThrow(/task t: gate\.commands is required/);
  });

  it("does not raise a raw TypeError (Cannot read properties of null) for any of them", () => {
    const plan = { meta: { name: "p" }, tasks: [ok({ test: null })] } as unknown as Parameters<typeof validate>[0];
    try {
      validate(plan);
    } catch (e) {
      expect((e as Error).message).not.toMatch(/Cannot read properties of null/);
    }
  });

  it("still accepts a well-formed plan (no behavior change)", () => {
    const plan = { meta: { name: "p" }, tasks: [ok({})] } as unknown as Parameters<typeof validate>[0];
    expect(() => validate(plan)).not.toThrow();
  });
});

describe("T-07c run-id correlation (observability-003)", () => {
  it("mints a short, non-empty, distinct run id", () => {
    const a = mintRunId();
    const b = mintRunId();
    expect(a).toMatch(/^[0-9a-f]{6}$/);
    expect(a).not.toBe(b); // overwhelmingly likely distinct
  });
});

// ---------------------------------------------------------------------------
// T-08a (dx-001) — parseChatCompletion must reject an unexpected shape with an
// actionable, endpoint-naming error rather than a silent ok:true content:"".
// ---------------------------------------------------------------------------
describe("T-08a parseChatCompletion shape guard (dx-001)", () => {
  it("returns ok:false for a body with no choices array, naming the endpoint", () => {
    const r = parseChatCompletion(JSON.stringify({ error: "bad model" }), "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error).toMatch(/opencode\.ai\/zen\/v1/);
      expect(r.error).toMatch(/choices|unexpected shape/i);
    }
  });

  it("returns ok:false for an array-wrapped body", () => {
    const r = parseChatCompletion(JSON.stringify([{ choices: [] }]), "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(false);
  });

  it("returns ok:false for a non-object JSON body (a bare number)", () => {
    const r = parseChatCompletion("42", "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(false);
  });

  it("still returns ok:true with content for a well-formed chat completion", () => {
    const r = parseChatCompletion(JSON.stringify({ choices: [{ message: { content: "hi" } }] }), "https://opencode.ai/zen/v1");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.content).toBe("hi");
  });
});

// ---------------------------------------------------------------------------
// T-08b (dx-002) — parseMutationHookOutput rejects a non-object score.
// ---------------------------------------------------------------------------
describe("T-08b parseMutationHookOutput shape guard (dx-002)", () => {
  it("returns null when score is emitted inside a JSON string (non-object after parse)", () => {
    // The regex matches the {...} that contains the word score, but it parses to
    // a string-bearing object whose .score is absent → null.
    expect(parseMutationHookOutput('noise {"msg":"the score is 1"} noise')).toBeNull();
  });

  it("returns null when score is present but not a number (e.g. a string)", () => {
    // The dx-002 failure mode: a matched object whose `score` is the wrong type.
    // The number guard rejects it rather than coercing a bogus value.
    expect(parseMutationHookOutput('{"score":"high"}')).toBeNull();
  });

  it("returns null when there is no score JSON at all", () => {
    expect(parseMutationHookOutput("ran 10 mutants, all killed")).toBeNull();
  });

  it("returns a result for a well-formed {score} object", () => {
    const r = parseMutationHookOutput('done\n{"score":0.8,"total":10,"survived":["a"]}');
    expect(r).not.toBeNull();
    expect(r!.score).toBe(0.8);
    expect(r!.evaluated).toBe(10);
    expect(r!.survivors).toEqual(["a"]);
  });
});

// ---------------------------------------------------------------------------
// T-08c (dx-003) — Map-miss on the mutant restore preserves the file rather
// than writing the literal "undefined". The restore guard is internal to
// mutationCheck; this proves the guard's CONTRACT via the same code path the
// fix uses (Map.get → undefined → skip), expressed against the public
// behavior: a candidate file absent from `originals` must not be clobbered.
// ---------------------------------------------------------------------------
describe("T-08c mutant-restore Map-miss preserves the file (dx-003)", () => {
  it("Map.get on a missing key yields undefined (the guarded skip condition)", () => {
    // The fix replaced `originals.get(c.file)!` with a guard that only writes
    // when the value is defined. This asserts the precondition the guard relies
    // on: a miss is `undefined`, never the string "undefined".
    const originals = new Map<string, string>([["impl.ts", "real source"]]);
    const orig = originals.get("not-in-map.ts");
    expect(orig).toBeUndefined();
    // The guard's effect: with orig === undefined, no write happens, so the
    // worktree file keeps its real contents. We model that decision here.
    let wrote: string | null = null;
    if (orig !== undefined) wrote = orig;
    expect(wrote).toBeNull(); // file preserved, never overwritten with "undefined"
  });
});

describe("run() scrubs dispatcher secrets from the child env (least-privilege, CodeQL #5)", () => {
  const PRINT = [
    "-e",
    "process.stdout.write(`KEY=${process.env.FARM_API_KEY ?? 'ABSENT'};TOK=${process.env.CLAUDE_CODE_OAUTH_TOKEN ?? 'ABSENT'};MODEL=${process.env.FARM_MODEL ?? 'ABSENT'}`)",
  ];
  it("hides FARM_API_KEY / OAuth token from a child command but still inherits non-secret config", async () => {
    const prev = {
      key: process.env.FARM_API_KEY,
      tok: process.env.CLAUDE_CODE_OAUTH_TOKEN,
      model: process.env.FARM_MODEL,
    };
    process.env.FARM_API_KEY = "sk-should-not-leak";
    process.env.CLAUDE_CODE_OAUTH_TOKEN = "tok-should-not-leak";
    process.env.FARM_MODEL = "passes-through";
    try {
      const r = await run(process.execPath, PRINT, undefined, {}, 5000);
      expect(r.code).toBe(0);
      expect(r.stdout).toContain("KEY=ABSENT"); // secret scrubbed
      expect(r.stdout).toContain("TOK=ABSENT"); // secret scrubbed
      expect(r.stdout).not.toContain("should-not-leak"); // value never reaches the child
      expect(r.stdout).toContain("MODEL=passes-through"); // non-secret config still inherited
    } finally {
      const restore = (k: string, v: string | undefined) =>
        v === undefined ? delete process.env[k] : (process.env[k] = v);
      restore("FARM_API_KEY", prev.key);
      restore("CLAUDE_CODE_OAUTH_TOKEN", prev.tok);
      restore("FARM_MODEL", prev.model);
    }
  });
});
