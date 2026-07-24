import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { BridgeResponse } from "../src/contracts.ts";
import { applyToolResultNotice } from "../src/notices.ts";

function text(result: { content?: unknown }): string {
  return JSON.stringify(result.content ?? []);
}

describe("Pi governed result notices", () => {
  test.each(["H-07", "H-09", "H-10", "H-12", "H-13", "H-15", "H-16", "H-17"])(
    "appends the shared %s write reminder with a stable de-duplication marker",
    (ruleId) => {
      const original = { content: [{ type: "text", text: "native write result" }], details: { bytes: 1 } };
      const response: BridgeResponse = {
        version: 1,
        outcome: "notice",
        ruleId,
        message: `REMINDER [${ruleId}]: shared-core reminder`,
      };
      const patch = applyToolResultNotice(original, response);
      expect(patch).toBeDefined();
      const result = { ...original, ...patch };
      expect(result.details).toEqual(original.details);
      expect(result.content[0]).toEqual(original.content[0]);
      expect(JSON.stringify(result.content)).toMatch(/codearbiter:pi-tool-result:[a-f0-9]{64}/u);
      expect(applyToolResultNotice(result, response)).toBeUndefined();
    },
  );

  test("adds each governed write reminder once without replacing native details", () => {
    const response: BridgeResponse = {
      version: 1,
      outcome: "notice",
      ruleId: "H-17",
      message: "REMIND [H-17]: dispatch security-reviewer before merging",
    };
    const original = {
      content: [{ type: "text", text: "Wrote src/auth.ts" }],
      details: { path: "src/auth.ts", bytes: 42 },
      isError: false,
    };
    const first = applyToolResultNotice(original, response);
    expect(first).toBeDefined();
    const afterFirst = { ...original, ...first };
    const second = applyToolResultNotice(afterFirst, response);

    expect(afterFirst.details).toEqual(original.details);
    expect(afterFirst.content[0]).toEqual(original.content[0]);
    expect(text(afterFirst).match(/H-17/gu)).toHaveLength(1); // visible reminder only; marker is digest-only
    expect(second).toBeUndefined();
  });

  test("adds bounded read context once while preserving image and text blocks", () => {
    const original = {
      content: [
        { type: "image", data: "synthetic-image" },
        { type: "text", text: "native read output" },
      ],
      details: { path: "README.md" },
    };
    const response: BridgeResponse = {
      version: 1,
      outcome: "notice",
      context: `project context ${"x".repeat(40_000)}`,
    };
    const patch = applyToolResultNotice(original, response);
    expect(patch).toBeDefined();
    const result = { ...original, ...patch };

    expect(result.content.slice(0, 2)).toEqual(original.content);
    expect(Buffer.byteLength(text(result), "utf8")).toBeLessThan(20_000);
    expect(applyToolResultNotice(result, response)).toBeUndefined();
  });

  test("does not add a notice for allow responses or empty advisory text", () => {
    const event = { content: [{ type: "text", text: "native" }] };
    expect(applyToolResultNotice(event, { version: 1, outcome: "allow" })).toBeUndefined();
    expect(applyToolResultNotice(event, { version: 1, outcome: "notice", message: "" })).toBeUndefined();
  });

  test("does not let native marker-looking text suppress an owned notice", () => {
    const native = { content: [{ type: "text", text: "<!-- codearbiter:pi-tool-result:H-17 -->" }] };
    const response: BridgeResponse = { version: 1, outcome: "notice", ruleId: "H-17", message: "first" };
    expect(applyToolResultNotice(native, response)).toBeDefined();
  });

  test("deduplicates exact identities but retains same-rule changes and distinct read contexts", () => {
    const original = { content: [{ type: "text", text: "native" }] };
    const first = { version: 1, outcome: "notice", ruleId: "H-17", message: "first" } as const;
    const changed = { ...first, message: "second" };
    const one = { ...original, ...applyToolResultNotice(original, first)! };
    expect(applyToolResultNotice(one, first)).toBeUndefined();
    const two = { ...one, ...applyToolResultNotice(one, changed)! };
    expect(JSON.stringify(two.content)).toContain("first");
    expect(JSON.stringify(two.content)).toContain("second");
    const readA = { version: 1, outcome: "notice", context: "context A" } as const;
    const readB = { ...readA, context: "context B" };
    const three = { ...two, ...applyToolResultNotice(two, readA)! };
    expect(applyToolResultNotice(three, readB)).toBeDefined();
  });

  test("redacts at the boundary and caps the complete owned block at 16000 UTF-8 bytes", () => {
    const response: BridgeResponse = {
      version: 1,
      outcome: "notice",
      ruleId: "H-10",
      message: `sk-ant-api03-${"A".repeat(20_000)}🙂`,
    };
    const patch = applyToolResultNotice({ content: [] }, response)!;
    const inserted = (patch.content.at(-1) as { text: string }).text;
    expect(inserted).not.toContain("sk-ant-api03-");
    expect(inserted).not.toContain("�");
    expect(Buffer.byteLength(inserted, "utf8")).toBeLessThanOrEqual(16_000);
  });

  test("keeps an adversarial oversized rule id out of the marker and inside the UTF-8 cap", () => {
    const secret = `sk-ant-api03-${"A".repeat(256)}`;
    const ruleId = `${secret}${"R".repeat(20_000)}`;
    const patch = applyToolResultNotice(
      { content: [] },
      { version: 1, outcome: "notice", ruleId, message: `${secret}${"🙂".repeat(20_000)}` },
    )!;
    const inserted = (patch.content.at(-1) as { text: string }).text;
    expect(Buffer.byteLength(inserted, "utf8")).toBeLessThanOrEqual(16_000);
    expect(inserted).not.toContain(ruleId);
    expect(inserted).not.toContain(secret);
    expect(inserted).toMatch(/^<!-- codearbiter:pi-tool-result:[a-f0-9]{64} -->\n/u);
    expect(Buffer.from(inserted, "utf8").toString("utf8")).toBe(inserted);
  });

  test("redacts every must-match shared secret corpus entry in the direct helper", () => {
    const corpus = JSON.parse(readFileSync(
      fileURLToPath(new URL("../../../ca/hooks/secret-detection-corpus.json", import.meta.url)),
      "utf8",
    )) as { must_match: string[] };
    for (const secret of corpus.must_match) {
      const patch = applyToolResultNotice(
        { content: [] },
        { version: 1, outcome: "notice", ruleId: "H-10", message: secret },
      )!;
      const serialized = JSON.stringify(patch);
      expect(serialized, secret).not.toContain(secret);
      expect(serialized, secret).toContain("[REDACTED");
    }
  });
});
