/** render-gates-table.ts — codeArbiter's curated `gates:` table renderer. */
import type { GateSpec } from "./types";

/**
 * Render a list of {@link GateSpec} entries as a markdown table.
 *
 * Returns an empty string for an empty/absent list, so callers can splice
 * the result in unconditionally and get nothing when there is nothing to
 * show. Column order is fixed: Gate, When, Effect.
 */
export function renderGatesTable(gates: GateSpec[] | undefined): string {
  if (!gates || gates.length === 0) return "";

  const header = "| Gate | When | Effect |\n| --- | --- | --- |";
  const rows = gates
    .map((g) => `| ${g.gate} | ${g.when} | ${g.effect} |`)
    .join("\n");

  return `${header}\n${rows}`;
}
