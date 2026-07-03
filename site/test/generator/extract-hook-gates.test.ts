import { describe, it, expect } from "vitest";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { extractHookGates } from "../../scripts/generator/extract-hook-gates";

const here = dirname(fileURLToPath(import.meta.url));
const fixtureDir = join(here, "fixtures", "hook-gates");
// The real plugin hooks directory — scanned for the count-floor snapshot below.
const realHooksDir = resolve(here, "..", "..", "..", "plugins", "ca", "hooks");

describe("extractHookGates — fixture", () => {
  const { callSites, skipped } = extractHookGates(fixtureDir);

  it("extracts a multi-line adjacent f-string call, concatenating placeholder text verbatim", () => {
    const site = callSites.find((c) => c.tag === "H-13");
    expect(site).toBeDefined();
    expect(site!.kind).toBe("remind");
    expect(site!.message).toBe(
      "{rel}: found {count} issue(s) on line(s) {count} (nested check) — please fix before committing.",
    );
  });

  it("handles nested parens inside a plain string literal without truncating the call", () => {
    const site = callSites.find((c) => c.tag === "H-05");
    expect(site).toBeDefined();
    expect(site!.message).toBe(
      "The audit log (overrides.log, triage.log) is append-only (see ORCHESTRATOR §7). Truncation is prohibited.",
    );
  });

  it("handles `+` concatenation, ignoring the non-literal trailing call but tracking its parens", () => {
    const site = callSites.find((c) => c.tag === "H-01");
    expect(site).toBeDefined();
    expect(site!.message).toBe("Direct commit to main is prohibited.");
  });

  it("finds two distinct tags in the same file", () => {
    const tags = new Set(callSites.map((c) => c.tag));
    expect(tags.has("H-13")).toBe(true);
    expect(tags.has("H-07")).toBe(true);
  });

  it("counts a variable-tag call into `skipped`, not silently dropped", () => {
    expect(skipped).toHaveLength(1);
    expect(skipped[0].file).toBe("sample-hook.py");
  });

  it("excludes the block()/remind() definition sites themselves", () => {
    // Only the 4 literal-tag call sites should surface — never the two `def`s.
    expect(callSites).toHaveLength(4);
  });

  it("records 1-based line numbers and the source file basename", () => {
    const site = callSites.find((c) => c.tag === "H-07");
    expect(site!.file).toBe("sample-hook.py");
    expect(site!.line).toBeGreaterThan(0);
  });
});

describe("extractHookGates — real plugin hooks (count-floor snapshot)", () => {
  // Guards against silent under-collection. Counted directly via:
  //   grep -c 'block("H-\|remind("H-' plugins/ca/hooks/*.py
  // as of this writing: git-enforce.py=8, post-write-edit.py=8, pre-bash.py=20,
  // pre-edit.py=10, pre-write.py=6 -> 52 literal-tag call sites. A future hook
  // addition only grows this number, so the assertion is a floor (>=), not an
  // exact match — it must fail if the extractor starts silently missing sites,
  // not if the source genuinely grows.
  const REAL_CALL_SITE_FLOOR = 52;

  const { callSites } = extractHookGates(realHooksDir);

  it(`finds at least ${REAL_CALL_SITE_FLOOR} literal-tag call sites in the real hooks`, () => {
    expect(callSites.length).toBeGreaterThanOrEqual(REAL_CALL_SITE_FLOOR);
  });

  it("extracts H-01's protected-branch commit message from pre-bash.py verbatim", () => {
    const site = callSites.find(
      (c) => c.tag === "H-01" && c.file === "pre-bash.py" && c.line === 623,
    );
    expect(site).toBeDefined();
    expect(site!.message).toBe(
      "Direct commit to {target} is prohibited (ORCHESTRATOR §3). Create a feature branch.",
    );
  });

  it("extracts an H-09b message from pre-bash.py verbatim", () => {
    const site = callSites.find((c) => c.tag === "H-09b" && c.file === "pre-bash.py");
    expect(site).toBeDefined();
    expect(site!.message).toBe(
      "the diff for the crypto/secret security scan could not be read (git unavailable or timed out) — failing closed (ORCHESTRATOR §2). Retry, or run the crypto-compliance / secret-handling gate, then commit.",
    );
  });
});
