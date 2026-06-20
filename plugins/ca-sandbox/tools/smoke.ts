/**
 * Toolchain smoke module for ca-sandbox tools (T-01 enabler).
 * Exists so the vitest harness has a real local .ts module to import and
 * exercise. Carries no sandbox logic — that arrives in later tasks.
 */
export function toolchainOk(): true {
  return true;
}
