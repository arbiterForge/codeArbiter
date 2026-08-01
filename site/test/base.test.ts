/** base.test.ts — the site base path is the one value that silently corrupts
 * every internal link when it is wrong, so its invariants are gated rather than
 * documented.
 *
 * The motivating failure: a base of "/" makes rehypeBaseLinks rewrite
 * "/diagrams/x.svg" into "//diagrams/x.svg", a protocol-relative URL that
 * resolves against a DIFFERENT HOST. Nothing 404s. The build succeeds and the
 * link audit passes, because the target still parses as a valid reference — the
 * page just quietly fetches from somewhere else. A comment saying "never use
 * '/'" stops nobody; "/" is the obvious thing to reach for when moving a site to
 * a domain root.
 */
import { describe, it, expect } from "vitest";
// @ts-expect-error -- untyped .mjs module
import { BASE, validateBase } from "../base.mjs";

/** The link-prefixing rule from scripts/rehype-base-links.ts, reproduced so this
 * file can demonstrate the corruption a bad base causes without depending on the
 * plugin's internals. */
function prefix(value: string, base: string): string {
  if (value === "" || value.startsWith("#") || value.startsWith("//") || !value.startsWith("/")) {
    return value;
  }
  if (value === base || value.startsWith(`${base}/`)) return value;
  return `${base}${value}`;
}

describe("validateBase", () => {
  it("accepts the apex-domain form", () => {
    expect(validateBase("")).toBe("");
  });

  it("accepts a project subpath", () => {
    expect(validateBase("/codeArbiter")).toBe("/codeArbiter");
  });

  it("rejects '/' — the value that produces protocol-relative URLs", () => {
    expect(() => validateBase("/")).toThrow(/protocol-relative/);
  });

  it("rejects a trailing slash", () => {
    expect(() => validateBase("/codeArbiter/")).toThrow(/must not end with/);
  });

  it("rejects a base that is not root-absolute", () => {
    expect(() => validateBase("codeArbiter")).toThrow(/must be "" or start with/);
  });

  it("rejects a non-string", () => {
    expect(() => validateBase(42 as unknown as string)).toThrow(TypeError);
  });
});

describe("why '/' is rejected", () => {
  it("would rewrite a root-absolute asset into a protocol-relative URL", () => {
    // This is the corruption the guard exists to prevent. Pinned as an
    // executable statement of the hazard, not a comment about it.
    expect(prefix("/diagrams/x.svg", "/")).toBe("//diagrams/x.svg");
    expect(prefix("/diagrams/x.svg", "/").startsWith("//")).toBe(true);
  });

  it("is a correct no-op under the sanctioned apex form", () => {
    expect(prefix("/diagrams/x.svg", "")).toBe("/diagrams/x.svg");
  });

  it("prefixes correctly under a sanctioned subpath", () => {
    expect(prefix("/diagrams/x.svg", "/codeArbiter")).toBe("/codeArbiter/diagrams/x.svg");
  });
});

describe("the configured BASE", () => {
  it("is itself valid — the guard runs at import time, so this cannot regress", () => {
    expect(() => validateBase(BASE)).not.toThrow();
  });

  it("never ends with a slash", () => {
    expect(BASE.endsWith("/")).toBe(false);
  });
});
