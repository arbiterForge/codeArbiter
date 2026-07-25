/**
 * path-boundary.ts - the single owner of codeArbiter's Pi path-containment semantics.
 *
 * Every Pi trust boundary that decides whether a path belongs to a root - command
 * ownership, runtime and TUI identity, bridge and executable placement, role catalogs,
 * doctor claims, child launch inputs, and process-tree artifacts - asks this module.
 * Containment is expressed in exactly two named operations so a call site cannot
 * silently disagree with another about canonicalization or platform semantics:
 *
 * - `lexicallyInside` compares text only. It never touches the filesystem, so a symlink
 *   planted inside `root` still reads as contained. Callers that have already
 *   canonicalized both operands (the common case on this boundary) want this one.
 * - `canonicallyInside` resolves both operands through the filesystem first, so a
 *   symlink that escapes `root` reads as outside.
 *
 * The path flavor is injectable so Windows and POSIX semantics are testable from either
 * host; it defaults to the host platform, matching `node:path`'s own default binding.
 */
import { realpathSync } from "node:fs";
import { posix, resolve, win32 } from "node:path";

/** Which platform's path grammar a containment question is asked in. */
export type PathFlavor = "win32" | "posix";

type PathApi = Pick<typeof win32, "isAbsolute" | "relative">;

/** Map a Node platform identifier onto the path grammar it uses. */
export function flavorForPlatform(platform: NodeJS.Platform): PathFlavor {
  return platform === "win32" ? "win32" : "posix";
}

function pathApiFor(flavor: PathFlavor): PathApi {
  return flavor === "win32" ? win32 : posix;
}

/**
 * Lexical containment: is `path` the same as `root`, or beneath it, by path text alone?
 * A root always contains itself. No filesystem access and no canonicalization happen
 * here - a caller that must defeat symlinks canonicalizes first or uses
 * `canonicallyInside`.
 */
export function lexicallyInside(
  path: string,
  root: string,
  flavor: PathFlavor = flavorForPlatform(process.platform),
): boolean {
  const pathApi = pathApiFor(flavor);
  const suffix = pathApi.relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !pathApi.isAbsolute(suffix));
}

/**
 * Resolve `path` through the filesystem, falling back to lexical resolution when the
 * path does not exist or cannot be inspected. This is the canonicalization the Pi
 * boundary uses whenever it must compare identities rather than text.
 */
export function canonicalPath(path: string): string {
  try {
    return realpathSync.native(path);
  } catch {
    return resolve(path);
  }
}

/**
 * Canonical containment: is `path` the same as `root`, or beneath it, after both
 * operands are resolved through the filesystem? A symlink inside `root` whose target
 * escapes `root` is not contained.
 */
export function canonicallyInside(path: string, root: string): boolean {
  return lexicallyInside(canonicalPath(path), canonicalPath(root));
}
