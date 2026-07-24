import { describe, it, expect } from "vitest";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  extractHookGates,
  type HookCallSite,
} from "../../scripts/generator/extract-hook-gates";

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

  it("resolves a bare-assignment variable tag to its single literal tag", () => {
    const site = callSites.find((c) => c.tag === "H-14");
    expect(site).toBeDefined();
    expect(site!.kind).toBe("block");
    expect(site!.message).toBe("migration gate pass missing.");
  });

  it("resolves a conditional-assignment variable tag to BOTH tags with the same message and line pin", () => {
    const h09b = callSites.find((c) => c.tag === "H-09b");
    const h10b = callSites.find((c) => c.tag === "H-10b");
    expect(h09b).toBeDefined();
    expect(h10b).toBeDefined();
    const message =
      "This commit introduces {kind} changes without a recorded security-gate pass.";
    expect(h09b!.message).toBe(message);
    expect(h10b!.message).toBe(message);
    expect(h09b!.line).toBe(h10b!.line);
    expect(h09b!.line).toBeGreaterThan(0);
  });

  it("counts an unresolvable variable-tag call (loop unpack) into `skipped`, not silently dropped", () => {
    expect(skipped).toHaveLength(1);
    expect(skipped[0].file).toBe("sample-hook.py");
  });

  it("excludes the block()/remind() definition sites themselves", () => {
    // 4 literal-tag sites + 1 bare-assignment + 2 from the conditional split
    // should surface — never the two `def`s or the unresolvable loop-unpack call.
    expect(callSites).toHaveLength(7);
  });

  it("records 1-based line numbers and the source file basename", () => {
    const site = callSites.find((c) => c.tag === "H-07");
    expect(site!.file).toBe("sample-hook.py");
    expect(site!.line).toBeGreaterThan(0);
  });

});

type StableHookKey = Pick<HookCallSite, "kind" | "tag" | "file" | "message">;

function selectUniqueCallSite(
  callSites: HookCallSite[],
  key: StableHookKey,
): HookCallSite {
  const matches = callSites.filter(
    (site) =>
      site.kind === key.kind &&
      site.tag === key.tag &&
      site.file === key.file &&
      site.message === key.message,
  );
  expect(matches, `unique call site for ${key.kind} ${key.tag} in ${key.file}`).toHaveLength(1);
  return matches[0];
}

// H-01/H-09b/H-10b's block() call sites live in _bashguardlib.py, the shared
// bash-guard module pre-bash.py and git-enforce.py both delegate to (their
// entry-hook prologues were hoisted to _entrylib.py in the same move). The
// literal-tag scan already covers _bashguardlib.py as a top-level *.py file
// in hooksDir — no generator change was needed, only these file attributions.
const H10B_NO_PASS: StableHookKey = {
  kind: "block",
  tag: "H-10b",
  file: "_bashguardlib.py",
  message:
    "This commit introduces {kind} changes, but no security-gate pass is recorded (.codearbiter/.markers/security-gate-passed). Run the {skill} gate (it records the pass), then commit. To bypass a security gate, /override requires its heavier security-acknowledgement path.",
};

const H01_PROTECTED_BRANCH: StableHookKey = {
  kind: "block",
  tag: "H-01",
  file: "_bashguardlib.py",
  message:
    "Direct commit to {target} is prohibited (ORCHESTRATOR §3). Create a feature branch.",
};

function assertRealStructuralSites(callSites: HookCallSite[]) {
  return {
    h10b: selectUniqueCallSite(callSites, H10B_NO_PASS),
    h01: selectUniqueCallSite(callSites, H01_PROTECTED_BRANCH),
  };
}

describe("extractHookGates — real plugin hooks (count-floor snapshot)", () => {
  // Guards against silent under-collection. Counted directly via:
  //   grep -c 'block("H-\|remind("H-' plugins/ca/hooks/*.py
  // After the pre-bash.py/git-enforce.py guard-logic hoist into
  // _bashguardlib.py (and the entry prologue into _entrylib.py), the H-01/
  // H-09b/H-10b call sites now live in _bashguardlib.py rather than
  // pre-bash.py; the extractor already scans it (it's a flat *.py file in
  // hooksDir), so this needed no code change — only the file-attribution
  // fixtures below. As of this writing the extractor reports 65 total call
  // sites (57 literal-tag + 8 from resolved conditional-assignment splits)
  // with 1 genuinely unresolvable site (pre-edit.py's loop unpack) staying in
  // `skipped`. A future hook addition only grows this number, so the
  // assertion is a floor (>=), not an exact match — it must fail if the
  // extractor starts silently missing sites, not if the source genuinely grows.
  const REAL_CALL_SITE_FLOOR = 60;

  const { callSites, skipped } = extractHookGates(realHooksDir);

  it(`finds at least ${REAL_CALL_SITE_FLOOR} attributed call sites in the real hooks`, () => {
    expect(callSites.length).toBeGreaterThanOrEqual(REAL_CALL_SITE_FLOOR);
  });

  it("attributes at least one H-10b entry (the conditional-assignment split) with its real message", () => {
    const h10b = callSites.filter((c) => c.tag === "H-10b");
    expect(h10b.length).toBeGreaterThanOrEqual(1);
    expect(selectUniqueCallSite(callSites, H10B_NO_PASS).message).toBe(H10B_NO_PASS.message);
  });

  it("keeps the genuinely unresolvable loop-unpack call site in `skipped`", () => {
    expect(skipped.some((s) => s.file === "pre-edit.py")).toBe(true);
  });

  it("extracts H-01's protected-branch commit message from _bashguardlib.py verbatim", () => {
    expect(selectUniqueCallSite(callSites, H01_PROTECTED_BRANCH).message).toBe(
      H01_PROTECTED_BRANCH.message,
    );
  });

  it("keeps the same real-hook structural assertions after unrelated _bashguardlib.py line insertions", () => {
    const shiftedRoot = mkdtempSync(join(tmpdir(), "real-hook-gates-shifted-"));
    const shiftedHooksDir = join(shiftedRoot, "hooks");
    try {
      cpSync(realHooksDir, shiftedHooksDir, { recursive: true });
      const shiftedBashguard = join(shiftedHooksDir, "_bashguardlib.py");
      const source = readFileSync(shiftedBashguard, "utf8");
      writeFileSync(
        shiftedBashguard,
        `# unrelated line inserted above real gates\n# exact source lines must not be structural keys\n${source}`,
      );

      const originalSites = assertRealStructuralSites(callSites);
      const shiftedSites = assertRealStructuralSites(
        extractHookGates(shiftedHooksDir).callSites,
      );

      expect(shiftedSites.h10b.line).toBe(originalSites.h10b.line + 2);
      expect(shiftedSites.h01.line).toBe(originalSites.h01.line + 2);
    } finally {
      rmSync(shiftedRoot, { recursive: true, force: true });
    }
  });

  it("extracts an H-09b message from _bashguardlib.py verbatim", () => {
    const site = callSites.find((c) => c.tag === "H-09b" && c.file === "_bashguardlib.py");
    expect(site).toBeDefined();
    expect(site!.message).toBe(
      "the diff for the crypto/secret security scan could not be read (git unavailable or timed out) — failing closed (ORCHESTRATOR §2). Retry, or run the crypto-compliance / secret-handling gate, then commit.",
    );
  });
});
