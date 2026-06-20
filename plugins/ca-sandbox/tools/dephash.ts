/**
 * dephash.ts — ca-sandbox dependency cache key (T-04, covers AC-04 / AC-05).
 *
 * A sandbox image is tagged `ca-sbx:<repo>-<dephash>`. The dephash is the cache
 * discriminator: a `create` from an unchanged repo recomputes the SAME dephash,
 * finds the existing tag, and skips the nixpacks build (AC-04). Editing a
 * dependency manifest or lockfile recomputes a DIFFERENT dephash, missing the
 * tag and forcing a rebuild; editing only source leaves the manifest set
 * untouched, so the dephash is stable and no rebuild happens (AC-05). This
 * aligns with the Spike A model: deps resolve from the build-time manifest baked
 * into `/deps`, so only a manifest/lockfile change is a dep change.
 *
 * Algorithm (the documented, falsifiable contract):
 *   1. For each manifest file, compute `<relpath>\0<sha256(bytes)>`.
 *   2. Sort those lines lexicographically — so the hash is over the SET of
 *      manifests, independent of the order they were discovered/listed.
 *   3. Join with "\n", append a trailing "\n" and a `nixpacks=<version>` line —
 *      the pinned toolchain version is part of the key, so a nixpacks bump
 *      invalidates the cache (a new toolchain can bake different artifacts).
 *   4. sha256 the whole thing, truncate to 12 lowercase hex chars — short enough
 *      to live in a docker image tag, with ~48 bits of collision resistance.
 *
 * Pure: bytes are passed in (no filesystem, no docker), mirroring farm.ts's
 * deterministic `createHash("sha256").update(buf)` hashing. The caller (T-05's
 * build module) is responsible for discovering which files are manifests and
 * reading their bytes; this module only turns that set into a stable key.
 */
import { createHash } from "node:crypto";

/** A dependency manifest or lockfile and its raw bytes. */
export type ManifestFile = {
  /**
   * Repo-relative path, POSIX-style (e.g. "package.json", "sub/go.mod"). The
   * path is part of the hash: the same bytes at a different relpath produce a
   * different key, so moving a manifest is correctly treated as a dep change.
   */
  path: string;
  /** Raw file contents. Buffer | Uint8Array | string are all accepted. */
  bytes: Buffer | Uint8Array | string;
};

/** Number of hex chars the digest is truncated to (fits a docker image tag). */
export const DEPHASH_LENGTH = 12;

function sha256Hex(data: Buffer | Uint8Array | string): string {
  const buf =
    typeof data === "string"
      ? Buffer.from(data, "utf8")
      : Buffer.isBuffer(data)
        ? data
        : Buffer.from(data);
  return createHash("sha256").update(buf).digest("hex");
}

/**
 * Compute the dependency cache key for a set of manifest/lockfile contents.
 *
 * @param manifestFiles the manifest/lockfile set (order-independent).
 * @param nixpacksVersion the pinned nixpacks version; part of the key so a
 *   toolchain bump invalidates the cache. Empty string when unknown — still
 *   folded in so the key shape is stable.
 * @returns a 12-char lowercase-hex cache key.
 * @throws if two manifests share the same relpath (an ambiguous set).
 */
export function computeDepHash(
  manifestFiles: ManifestFile[],
  nixpacksVersion = "",
): string {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const f of manifestFiles) {
    if (seen.has(f.path)) {
      throw new Error(`computeDepHash: duplicate manifest relpath "${f.path}"`);
    }
    seen.add(f.path);
    lines.push(`${f.path}\0${sha256Hex(f.bytes)}`);
  }
  // Sort so the key reflects the SET, not the discovery/listing order.
  lines.sort();
  const payload = lines.join("\n") + "\n" + `nixpacks=${nixpacksVersion}`;
  return createHash("sha256").update(payload, "utf8").digest("hex").slice(0, DEPHASH_LENGTH);
}
