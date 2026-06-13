/**
 * Unit tests for farm.ts pure-function core.
 * These test the exported helpers directly without spawning a subprocess.
 */
import { describe, it, expect } from "vitest";
import { extractFileBlocks, extractLiterals, codeLineCount, validate, assertSecureBaseUrl } from "./farm.ts";

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
