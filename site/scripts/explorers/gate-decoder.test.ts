import { describe, expect, it } from "vitest";
import { bestTier, decodeHookOutput, MAX_INPUT, normalizeTerminalText, overlap, type DecoderSite } from "../../src/scripts/gate-decoder";
import { loadGateIndex } from "./gate-index";
import proof from "../../src/assets/proof/hook-proof.json" with { type: "json" };

const sites: DecoderSite[] = loadGateIndex().flatMap((gate) => gate.sites.map((site) => ({ tag: gate.tag, ...site })));

describe("decoding what a hook printed", () => {
  it("finds the exact call site of a captured hook refusal", () => {
    const capture = (proof as { invocation: { stderr: string } }).invocation.stderr;
    const [best] = decodeHookOutput(capture, sites);
    expect(best.tag).toBe("H-03");
    expect(best.how).toBe("exact");
    expect(best.site?.message).toMatch(/^'git add -A'/);
  });

  it("fills placeholders with whatever the hook printed there", () => {
    const [best] = decodeHookOutput("BLOCKED [H-01]: Direct commit to main is prohibited (ORCHESTRATOR §3). Create a feature branch.", sites);
    expect(best.tag).toBe("H-01");
    expect(best.how).toBe("exact");
    expect(best.site?.message).toContain("Direct commit to {target}");
  });

  it("finds the gate from a message pasted without its BLOCKED or REMINDER prefix", () => {
    const [best] = decodeHookOutput("Force-push is prohibited (ORCHESTRATOR §3).", sites);
    expect(best.tag).toBe("H-02");
  });

  it("finds the gate from part of a message, ignoring curly quotes, dash spellings and line wraps", () => {
    const [best] = decodeHookOutput("Wildcard staging is prohibited – a glob stages a non-explicit\n   file set", sites);
    expect(best.tag).toBe("H-03");
    expect(best.how).not.toBe("gate");
  });

  it("names the gate even when the message is not one this version prints", () => {
    const [best] = decodeHookOutput("REMINDER [H-12]: something an older release printed", sites);
    expect(best.tag).toBe("H-12");
    expect(best.how).toBe("gate");
    expect(best.site).toBeNull();
  });

  it("says nothing for text no gate prints, and never matches on a placeholder alone", () => {
    expect(decodeHookOutput("hello world", sites)).toEqual([]);
    expect(decodeHookOutput("", sites)).toEqual([]);
    const placeholderOnly: DecoderSite[] = [{ tag: "H-99", kind: "block", file: "x.py", line: 1, message: "{recovery}" }];
    expect(decodeHookOutput("anything at all that is long enough", placeholderOnly)).toEqual([]);
  });

  it("an unknown gate ID is reported as unknown rather than matched to another gate", () => {
    const [best] = decodeHookOutput("BLOCKED [H-42]: Force-push is prohibited (ORCHESTRATOR §3).", sites);
    expect(best).toMatchObject({ tag: "H-42", how: "unknown", site: null });
  });

  it("normalizes terminal text the way a paste arrives", () => {
    expect(normalizeTerminalText("  ‘git add -A’ — x\r\n y ")).toBe("'git add -A' - x y");
  });

  it("still matches exactly when a terminal wrap splits a word", () => {
    const capture = (proof as { invocation: { stderr: string } }).invocation.stderr;
    const at = capture.indexOf("explicitly");
    expect(at).toBeGreaterThan(0);
    const wrapped = `${capture.slice(0, at + 4)}\n${capture.slice(at + 4)}`;
    const [best] = decodeHookOutput(wrapped, sites);
    expect(best).toMatchObject({ tag: "H-03", how: "exact" });
  });

  it("names every gate that prints a shared message, and the printed ID picks one", () => {
    const shared = "No security-gate PASS is recorded for this staged candidate.";
    const owners = sites.filter((site) => site.message.startsWith(shared) && site.file === "_bashguardlib.py");
    expect(new Set(owners.map((site) => site.tag))).toEqual(new Set(["H-09b", "H-10b"]));

    const tier = bestTier(decodeHookOutput(shared, sites));
    expect(new Set(tier.map((match) => match.tag))).toEqual(new Set(["H-09b", "H-10b"]));
    for (const match of tier) expect(match.how).toBe("exact");

    const printed = bestTier(decodeHookOutput(`BLOCKED [H-10b]: ${shared}`, sites));
    expect(printed.map((match) => match.tag)).toEqual(printed.map(() => "H-10b"));
    expect(printed.length).toBeGreaterThan(0);
  });

  it("lists every call site that prints the same text word for word", () => {
    const stale = sites.filter((site) => site.tag === "H-11" && site.message.startsWith("ADR authoring marker is stale"));
    expect(stale.length).toBeGreaterThan(1);
    const tier = bestTier(decodeHookOutput("BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr.", sites));
    expect(tier.map((match) => `${match.site?.file}:${match.site?.line}`).sort()).toEqual(stale.map((site) => `${site.file}:${site.line}`).sort());
  });

  it("matches a piece copied across a value the hook filled in, even with a wrap mid-word", () => {
    const [commit] = decodeHookOutput("Direct commit to main is prohibited", sites);
    expect(commit).toMatchObject({ tag: "H-01", how: "partial" });
    expect(commit.site?.message).toContain("Direct commit to {target}");
    const [staging] = decodeHookOutput("Wildcard staging is prohib\nited - a glob stages a non-explicit file set", sites);
    expect(staging).toMatchObject({ tag: "H-03", how: "partial" });
  });

  it("measures overlaps exactly", () => {
    expect(overlap("abcde", "cdefg")).toBe(3);
    expect(overlap("aaaa", "aaab")).toBe(3);
    expect(overlap("abab", "ab")).toBe(2);
    expect(overlap("aab", "ab")).toBe(2);
    expect(overlap("abc", "xyz")).toBe(0);
    expect(overlap("", "x")).toBe(0);
  });

  it("does not match on words that most hook messages share", () => {
    expect(decodeHookOutput("codeArbiter hook: could not read config", sites)).toEqual([]);
  });

  it("decodes adversarial pastes in linear time", () => {
    const adversarial = [
      "x is governed by ADR-1 (".repeat(400),
      ": em/en dash used as a prose separator on line(s) ".repeat(200),
      `REMINDER [H-13]: ${"a: em/en dash used as a prose separator on line(s) 1".repeat(120)}`,
      "{".repeat(MAX_INPUT),
      "BLOCKED [H-01]: ".repeat(400),
    ].map((text) => text.slice(0, MAX_INPUT));
    const started = performance.now();
    for (const text of adversarial) decodeHookOutput(text, sites);
    // The old matcher took 6.7 s on the first input and did not finish the second in 90 s.
    expect(performance.now() - started).toBeLessThan(1000);
  });
});
