/** compatibility.ts - codeArbiter's pure Pi host prerequisite directions. */

export interface HostCompatibility {
  piVersion: string;
  nodeVersion: string;
  pythonMajor: number | null;
}

const SUPPORTED_PI_VERSIONS = new Set(["0.80.5", "0.80.10"]);
const MINIMUM_NODE = [22, 19, 0] as const;

// Anchored so the three numeric groups must be followed by end-of-string or a
// prerelease/build separator ("-"/"+"). This is the single shared semver-prefix
// parse used for every "is this version at least X" comparison in ca-pi:
// doctor.ts's versionAtLeast() imports this pattern rather than duplicating it,
// so the two floor checks can never drift apart. A looser, unanchored pattern
// (no trailing anchor) would greedily match a malformed or non-numeric-suffixed
// string's numeric prefix and wrongly report it as satisfying a stable floor.
export const SEMVER_PREFIX = /^(\d+)\.(\d+)\.(\d+)(?:$|[-+])/u;

export function atLeast(version: string, minimum: readonly number[]): boolean {
  const match = SEMVER_PREFIX.exec(version.replace(/^v/u, ""));
  if (match === null) return false;
  const actual = match.slice(1).map(Number);
  for (let index = 0; index < minimum.length; index += 1) {
    if (actual[index] > minimum[index]) return true;
    if (actual[index] < minimum[index]) return false;
  }
  return true;
}

export function compatibilityDirection(input: HostCompatibility): string | null {
  if (!SUPPORTED_PI_VERSIONS.has(input.piVersion)) {
    return "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.";
  }
  if (!atLeast(input.nodeVersion, MINIMUM_NODE)) {
    return "codeArbiter requires Node >=22.19.0 for Pi; upgrade Node and run /ca-doctor.";
  }
  if (input.pythonMajor !== 3) {
    return "codeArbiter requires Python 3; install Python 3 and run /ca-doctor.";
  }
  return null;
}
