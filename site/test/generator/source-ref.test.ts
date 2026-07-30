import { describe, expect, it } from "vitest";

import { repositorySourceRef } from "../../scripts/generator/source-ref";

describe("repositorySourceRef", () => {
  it("uses the exact GitHub Actions commit when available", () => {
    const sha = "0123456789abcdef0123456789abcdef01234567";
    expect(repositorySourceRef({ GITHUB_SHA: sha })).toBe(sha);
  });

  it("uses main for local and malformed environments", () => {
    expect(repositorySourceRef({})).toBe("main");
    expect(repositorySourceRef({ GITHUB_SHA: "pull/123/merge" })).toBe("main");
  });
});
