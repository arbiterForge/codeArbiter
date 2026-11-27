import { describe, expect, it } from "vitest";
import { decodeHookOutput, normalizeTerminalText, type DecoderSite } from "../../src/scripts/gate-decoder";
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
});
