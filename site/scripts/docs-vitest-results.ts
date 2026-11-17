import { lstatSync, realpathSync } from "node:fs";
import { basename, dirname, isAbsolute, resolve } from "node:path";

export const ORIGINAL_COVERAGE_SCRIPT =
  "vitest run --coverage && npm run test:academy-base && npm run test:release-applicability-rendered";

/** Opt-in reporting for the primary command, never an npm followup or worker. */
export function primaryNamedResults(
  env: Record<string, string | undefined> = process.env,
  argv: readonly string[] = process.argv.slice(2),
) {
  const output = env.CODEARBITER_DOCS_NAMED_RESULTS;
  if (!output || env.npm_lifecycle_event !== "coverage" ||
      argv.length !== 2 || argv[0] !== "run" || argv[1] !== "--coverage") return {};
  if (env.npm_lifecycle_script !== ORIGINAL_COVERAGE_SCRIPT ||
      output.length > 4096 || /[\x00-\x1f\x7f]/.test(output) || !isAbsolute(output) ||
      basename(output) !== "primary-vitest.json") {
    throw new Error("Original Docs named-result role or output is invalid");
  }
  const parent = dirname(output);
  let directory;
  let canonicalParent;
  try { directory = lstatSync(parent); canonicalParent = realpathSync(parent); }
  catch { throw new Error("Docs named-result parent ownership is unavailable"); }
  if (!directory.isDirectory() || directory.isSymbolicLink() || canonicalParent !== resolve(parent)) {
    throw new Error("Docs named-result parent is not an owned regular directory");
  }
  try {
    const file = lstatSync(output);
    if (!file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size !== 0) {
      throw new Error("Docs named-result output is not fresh");
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw new Error("Docs named-result output is not fresh or is unavailable");
    }
  }
  return { reporters: ["default" as const, "json" as const], outputFile: { json: output } };
}
