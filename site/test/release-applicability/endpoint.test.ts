import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { GET, prerender } from "../../src/pages/release-applicability.json";

const generatedRecordPath = fileURLToPath(
  new URL("../../src/generated/release-applicability.json", import.meta.url),
);

describe("release applicability endpoint", () => {
  it("statically serves the canonical generated record as JSON", async () => {
    const generatedRecord = JSON.parse(readFileSync(generatedRecordPath, "utf8"));
    const canonicalBody = `${JSON.stringify(generatedRecord, null, 2)}\n`;

    expect(prerender).toBe(true);

    const response = GET();
    expect(response.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(await response.text()).toBe(canonicalBody);
  });
});
