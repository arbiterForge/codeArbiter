/**
 * mounts.ts — the structural host-FS isolation guard for ca-sandbox (AC-02).
 *
 * The load-bearing invariant (spec "Load-bearing invariant" / AC-01 / AC-02):
 * untrusted code inside a sandbox container must never be able to reach the host
 * filesystem. A sandbox container therefore NEVER receives a bind mount. This
 * module is the single chokepoint that turns mount specs into docker `--mount`
 * argv, and it enforces that invariant by construction:
 *
 *   - it accepts ONLY `type=volume` and `type=tmpfs` specs;
 *   - it THROWS on ANY bind expression — an explicit `type=bind` spec, the
 *     classic `-v host:container` shorthand (object `{ v: "..." }` or a bare
 *     `"host:container"` string), or any other unknown mount type;
 *   - rejection is all-or-nothing: a single bind spec anywhere in the input
 *     throws before any argv is returned, so a caller can never accidentally ship
 *     a partial argv that drops the offending bind silently.
 *
 * Keeping this the one place mount argv is built means run.ts / cp.ts (and the
 * farm item-3 seam) can never hand docker a bind mount: a bind is a thrown error,
 * not a filtered-out entry.
 *
 * Argv shape mirrors what the spike proved out:
 *   --mount type=volume,source=ca-sbx-vol-<id>,target=/work/repo
 *   --mount type=tmpfs,target=/tmp
 */

/** A volume mount: a docker named volume mapped to a container path. */
export type VolumeMountSpec = {
  type: "volume";
  /** The docker named volume (must already exist / be created by the caller). */
  source: string;
  /** Absolute in-container mount point. */
  target: string;
  /** Mount the volume read-only (e.g. baked `/deps`). */
  readonly?: boolean;
};

/** A tmpfs mount: an in-memory filesystem at a container path. No host backing. */
export type TmpfsMountSpec = {
  type: "tmpfs";
  /** Absolute in-container mount point. */
  target: string;
  /** Mount read-only. */
  readonly?: boolean;
};

/**
 * The ONLY accepted spec shapes. Bind specs are deliberately NOT part of this
 * union — a caller that constructs one is a type error at compile time, and the
 * runtime guard below rejects it even when types are bypassed (untrusted/dynamic
 * input).
 */
export type MountSpec = VolumeMountSpec | TmpfsMountSpec;

/** Error thrown when a bind mount (or any non-volume/tmpfs spec) is supplied. */
export class BindMountRejectedError extends Error {
  constructor(detail: string) {
    super(
      `ca-sandbox: bind mount rejected — a sandbox container never gets a host bind mount (${detail}). ` +
        `Only type=volume and type=tmpfs mounts are permitted.`,
    );
    this.name = "BindMountRejectedError";
  }
}

// The `-v` / `--volume` shorthand is `source:target[:opts]`. When the source is
// an absolute host path (or a Windows drive path / a `.`-relative path) it is a
// bind mount; when it is a bare name it is a named volume. ca-sandbox does not
// accept the shorthand AT ALL — even the named-volume form must go through the
// structured `{ type: "volume", ... }` spec so there is exactly one parse path —
// so any `-v`-shaped input is rejected as a bind.
function looksLikeShorthand(value: unknown): value is string {
  return typeof value === "string" && value.includes(":");
}

/**
 * Validate a single spec and render it to a docker `--mount` value token.
 * Throws (BindMountRejectedError) on anything that is not a volume/tmpfs spec.
 */
function renderSpec(spec: MountSpec, index: number): string {
  // Reject the bare `-v` string form: a string spec is always shorthand, which
  // is a bind expression by ca-sandbox's rule.
  if (typeof spec === "string") {
    throw new BindMountRejectedError(
      `spec[${index}] is a "-v host:container" shorthand string ${JSON.stringify(spec)}`,
    );
  }
  if (spec === null || typeof spec !== "object") {
    throw new BindMountRejectedError(`spec[${index}] is not a mount spec object (${String(spec)})`);
  }

  // Reject the object `-v`/`--volume` shorthand form: `{ v: "host:container" }`.
  const asRecord = spec as Record<string, unknown>;
  if ("v" in asRecord || "volume" in asRecord) {
    const sh = asRecord.v ?? asRecord.volume;
    throw new BindMountRejectedError(
      `spec[${index}] uses the "-v" shorthand (${JSON.stringify(sh)})` +
        (looksLikeShorthand(sh) ? " which expresses a host:container bind" : ""),
    );
  }

  const type = asRecord.type;
  if (type === "bind") {
    throw new BindMountRejectedError(`spec[${index}] is an explicit type=bind mount`);
  }
  if (type !== "volume" && type !== "tmpfs") {
    throw new BindMountRejectedError(
      `spec[${index}] has unsupported mount type ${JSON.stringify(type)} (expected "volume" or "tmpfs")`,
    );
  }

  const parts: string[] = [`type=${type}`];

  if (type === "volume") {
    const v = spec as VolumeMountSpec;
    if (!v.source) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty source`);
    }
    if (!v.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty target`);
    }
    parts.push(`source=${v.source}`, `target=${v.target}`);
    if (v.readonly) parts.push("readonly");
  } else {
    const t = spec as TmpfsMountSpec;
    if (!t.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=tmpfs requires a non-empty target`);
    }
    parts.push(`target=${t.target}`);
    if (t.readonly) parts.push("readonly");
  }

  return parts.join(",");
}

/**
 * Build the docker `--mount` argv for a set of mount specs.
 *
 * Returns a flat argv array (`["--mount", "<value>", "--mount", "<value>", ...]`)
 * ready to splice into a `docker run`/`docker create` command line. Validation is
 * all-or-nothing: if ANY spec is a bind (or otherwise not volume/tmpfs) this
 * throws BindMountRejectedError and returns nothing — a partial, bind-stripped
 * argv is never produced.
 */
export function buildMountArgs(specs: ReadonlyArray<MountSpec>): string[] {
  if (!Array.isArray(specs)) {
    throw new Error("ca-sandbox: buildMountArgs expects an array of mount specs");
  }
  // Render all specs first (each call validates). Because we build the full list
  // before emitting argv, a throw on any spec aborts the whole build.
  const values = specs.map((spec, i) => renderSpec(spec, i));
  const argv: string[] = [];
  for (const value of values) {
    argv.push("--mount", value);
  }
  return argv;
}
