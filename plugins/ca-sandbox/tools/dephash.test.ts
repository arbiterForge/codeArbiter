/**
 * dephash.test.ts — T-04. Covers AC-04 / AC-05.
 *
 * computeDepHash(manifestFiles, nixpacksVersion?) computes a stable cache key
 * over the set of dependency manifests/lockfiles. The contract (spec AC-04/05):
 *   - identical manifest set  -> identical hash (cache hit / no rebuild)
 *   - changing a manifest/lockfile byte -> different hash (rebuild)
 *   - changing the pinned nixpacks version -> different hash (toolchain rebuild)
 *   - deterministic across repeated calls and input ORDERING (the hash is over
 *     the SET, not the listing order)
 *   - 12 hex chars (truncated sha256), so it is safe in a docker image TAG
 *
 * Pure unit — no filesystem, no docker. Manifest bytes are passed in directly
 * (mirrors farm.ts's deterministic crypto hashing over buffers).
 */
import { describe, it, expect } from "vitest";
import { createHash } from "node:crypto";
import { computeDepHash, type ManifestFile } from "./dephash.ts";

const NIX = "1.40.0";

function mf(path: string, bytes: string): ManifestFile {
  return { path, bytes: Buffer.from(bytes, "utf8") };
}

describe("computeDepHash", () => {
  const base: ManifestFile[] = [
    mf("package.json", '{"name":"x","dependencies":{"lodash":"^4"}}'),
    mf("package-lock.json", '{"lockfileVersion":3}'),
  ];

  it("is 12 lowercase hex chars", () => {
    const h = computeDepHash(base, NIX);
    expect(h).toMatch(/^[0-9a-f]{12}$/);
  });

  it("returns an identical hash for an identical manifest set", () => {
    const a = computeDepHash(base, NIX);
    const b = computeDepHash(
      [
        mf("package.json", '{"name":"x","dependencies":{"lodash":"^4"}}'),
        mf("package-lock.json", '{"lockfileVersion":3}'),
      ],
      NIX,
    );
    expect(a).toBe(b);
  });

  it("is deterministic across two calls on the same input", () => {
    expect(computeDepHash(base, NIX)).toBe(computeDepHash(base, NIX));
  });

  it("is order-independent — the hash is over the SET, not the listing order", () => {
    const reordered = [base[1], base[0]];
    expect(computeDepHash(reordered, NIX)).toBe(computeDepHash(base, NIX));
  });

  it("changes when a manifest byte changes (manifest edit -> rebuild)", () => {
    const edited = [
      mf("package.json", '{"name":"x","dependencies":{"lodash":"^5"}}'),
      base[1],
    ];
    expect(computeDepHash(edited, NIX)).not.toBe(computeDepHash(base, NIX));
  });

  it("changes when a lockfile byte changes (lockfile edit -> rebuild)", () => {
    const edited = [base[0], mf("package-lock.json", '{"lockfileVersion":4}')];
    expect(computeDepHash(edited, NIX)).not.toBe(computeDepHash(base, NIX));
  });

  it("changes when a manifest is added to the set", () => {
    const more = [...base, mf("requirements.txt", "requests==2.31.0")];
    expect(computeDepHash(more, NIX)).not.toBe(computeDepHash(base, NIX));
  });

  it("changes when a manifest is removed from the set", () => {
    expect(computeDepHash([base[0]], NIX)).not.toBe(computeDepHash(base, NIX));
  });

  it("binds the path: same bytes at a different relpath -> different hash", () => {
    const renamed = [mf("sub/package.json", base[0].bytes.toString("utf8")), base[1]];
    expect(computeDepHash(renamed, NIX)).not.toBe(computeDepHash(base, NIX));
  });

  it("changes when the pinned nixpacks version changes (toolchain rebuild)", () => {
    expect(computeDepHash(base, "1.41.0")).not.toBe(computeDepHash(base, NIX));
  });

  it("accepts string and Uint8Array bytes equivalently to a Buffer", () => {
    const asString: ManifestFile[] = [
      { path: "package.json", bytes: '{"name":"x","dependencies":{"lodash":"^4"}}' },
      { path: "package-lock.json", bytes: new Uint8Array(Buffer.from('{"lockfileVersion":3}')) },
    ];
    expect(computeDepHash(asString, NIX)).toBe(computeDepHash(base, NIX));
  });

  it("matches an independently computed reference digest (algorithm is the documented one)", () => {
    // Reference: sha256 over the sorted "<relpath>\0<sha256(bytes)>\n" lines
    // followed by the nixpacks version line, truncated to 12 hex.
    const lines = base
      .map((f) => `${f.path}\0${createHash("sha256").update(f.bytes as Buffer).digest("hex")}`)
      .sort();
    const expected = createHash("sha256")
      .update(lines.join("\n") + "\n" + `nixpacks=${NIX}`)
      .digest("hex")
      .slice(0, 12);
    expect(computeDepHash(base, NIX)).toBe(expected);
  });

  it("rejects a duplicate relpath in the manifest set", () => {
    const dup = [base[0], base[1], mf("package.json", "different")];
    expect(() => computeDepHash(dup, NIX)).toThrow(/duplicate/i);
  });
});
