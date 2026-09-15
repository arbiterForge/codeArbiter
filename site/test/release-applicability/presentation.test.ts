import { describe, expect, it } from "vitest";

import sitePackage from "../../package.json";
import { presentProofApplicability } from "../../src/release-applicability-presentation";

describe("release applicability presentation", () => {
  it("generates applicability once before top-level test and coverage runners", () => {
    expect(sitePackage.scripts.pretest).toBe("npm run gen");
    expect(sitePackage.scripts.precoverage).toBe("npm run gen");
    expect(sitePackage.scripts["test:release-applicability-rendered"]).toBe(
      "astro build && tsx test/release-applicability/rendered.ts",
    );
  });

  it("distinguishes a published-artifact mismatch from a current-source mismatch (O-13)", () => {
    const publishedMismatch = presentProofApplicability({
      applicable: false,
      publishedSource: { matchesReplay: false },
      currentSource: { matchesReplay: true },
    });
    const currentMismatch = presentProofApplicability({
      applicable: false,
      publishedSource: { matchesReplay: true },
      currentSource: { matchesReplay: false },
    });

    expect(publishedMismatch).toEqual({
      isMismatch: true,
      message: "Digest mismatch: the exact latest published ca artifact does not match the replay source",
    });
    expect(currentMismatch).toEqual({
      isMismatch: true,
      message:
        "Replay source matches the exact latest published ca artifact, but differs from the current hook source",
    });
    expect(publishedMismatch.message).not.toBe(currentMismatch.message);
  });

  it("rejects an internally inconsistent applicability claim (O-13)", () => {
    expect(() =>
      presentProofApplicability({
        applicable: true,
        publishedSource: { matchesReplay: false },
        currentSource: { matchesReplay: true },
      }),
    ).toThrow(/internally inconsistent/);
  });
});
