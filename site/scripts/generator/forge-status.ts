/** forge-status.ts — codeArbiter's site-side Feature Forge allowlist.
 *
 * Marks which commands (or flags on commands) carry Feature Forge preview
 * status. This is the single source of truth for preview decoration on the
 * generated reference pages. It lives here — not in plugin frontmatter — to
 * hold the strict site-only boundary (AC-14, docs-site-polish spec).
 *
 * [NEEDS-TRIAGE] Allowlist drift: this list is hand-maintained. If a feature is
 * promoted to stable, this entry must be removed. A future /ca:doctor check or
 * CI reconciliation step (noted in the spec's triage section) should automate
 * the drift detection.
 */

/** A whole command is in preview. */
export interface PreviewCommandStatus {
  kind: "preview-command";
}

/** One named flag on a command is in preview; the command itself is stable. */
export interface PreviewFlagStatus {
  kind: "preview-flag";
  /** The CLI flag that is preview, e.g. "--farm". */
  flag: string;
}

export type ForgeStatus = PreviewCommandStatus | PreviewFlagStatus;

/**
 * Map of command base-names (the slug portion, e.g. "prune" not "/ca:prune")
 * to their forge status.
 *
 * - prune: the entire command is a Feature Forge preview.
 * - sprint: the --farm flag is a Feature Forge preview; the base command is stable.
 */
export const PREVIEW_COMMANDS: Record<string, ForgeStatus> = {
  prune: { kind: "preview-command" },
  sprint: { kind: "preview-flag", flag: "--farm" },
};

/**
 * Look up the forge status for a command by its base name.
 *
 * @param commandName - The command slug (e.g. "prune", "sprint", "commit").
 *   May be passed with or without a "/ca:" prefix; the prefix is stripped.
 * @returns The ForgeStatus for that command, or null if the command is stable.
 */
export function getCommandForgeStatus(commandName: string): ForgeStatus | null {
  // Strip the "/ca:" prefix if present, then normalise to lower-case.
  const base = commandName.replace(/^\/ca:/, "").toLowerCase();
  return PREVIEW_COMMANDS[base] ?? null;
}
