/** forge-status.ts — codeArbiter's site-side Feature Forge allowlist.
 *
 * Single source of truth for what is in the Feature Forge (preview, off by
 * default). It feeds two surfaces:
 *   1. the "What's in the Forge" catalog page (via FORGE_FEATURES), and
 *   2. the `preview` badge on generated reference pages (via the derived
 *      PREVIEW_COMMANDS map + getCommandForgeStatus).
 *
 * It mirrors the authoritative forge list in the repo README. It lives here, not
 * in plugin frontmatter, to hold the strict site-only boundary (AC-14,
 * docs-site-polish spec).
 *
 * [NEEDS-TRIAGE] Allowlist drift: this list is hand-maintained. When a feature is
 * promoted to stable, remove it here. A future /ca:doctor check or CI
 * reconciliation step (noted in the spec's triage section) should automate the
 * drift detection against the README and the decision log.
 */

/** An environment variable a preview feature reads. */
export interface ForgeEnvVar {
  /** The variable name, e.g. "FARM_API_KEY". */
  name: string;
  /** Whether the feature cannot run without it. */
  required: boolean;
  /** One-line, user-facing description of what it controls. */
  description: string;
}

/** A single feature in the Forge. `kind` selects how it is opted into:
 *  - preview-command: a whole /ca: command is preview (carries `command`);
 *  - preview-flag: a flag on an otherwise-stable command (carries `command` + `flag`);
 *  - preview-plugin: a separate sibling plugin you install (no /ca: command). */
export interface ForgeFeature {
  /** Display name, e.g. "Live transcript pruning". */
  name: string;
  kind: "preview-command" | "preview-flag" | "preview-plugin";
  /** One or two plain sentences on what the feature does and its headline
   *  value, shown in the catalog card so the list is self-explanatory. The
   *  fuller "why it's cool" narrative lives in the hand-authored deep-dive. */
  summary: string;
  /** How you opt in, e.g. "CODEARBITER_PRUNE=dry", "/ca:sprint --farm". */
  optIn: string;
  /** The ca command slug for the reference link + badge (command/flag kinds). */
  command?: string;
  /** The preview flag, e.g. "--farm" (preview-flag kind). */
  flag?: string;
  /** Environment variables the feature reads; omitted/empty means none. */
  env?: ForgeEnvVar[];
  /** Non-env prerequisites, e.g. "Docker and nixpacks on PATH". */
  requires?: string;
  /** One line on how a user helps it graduate to stable. */
  helpGraduate: string;
  /** External reference, for features with no generated site reference page. */
  href?: string;
}

/** The Forge contents, in README order. */
export const FORGE_FEATURES: ForgeFeature[] = [
  {
    name: "Live transcript pruning",
    kind: "preview-command",
    summary:
      "Reclaims room in a long session's context window by trimming transcript bulk (tool-output sidecars, oversized results, folded thinking, stale file reads) at safe boundaries, while keeping the message chain and the most recent turns verbatim.",
    command: "prune",
    optIn: "CODEARBITER_PRUNE=dry",
    env: [
      {
        name: "CODEARBITER_PRUNE",
        required: true,
        description:
          "The opt-in switch, with three modes: off (default, fully dormant), dry (logs what it would trim without touching the transcript), and on (active pruning).",
      },
    ],
    helpGraduate: "run it in dry mode and send the log.",
  },
  {
    name: "Pluggable execution farm",
    kind: "preview-flag",
    summary:
      "Routes each implementation task to worker agents running in isolated git worktrees, behind the same review chain and hard gates as a normal sprint. It changes who writes the code, never whether it is reviewed, so you can put a cheaper or different model on the keyboard without loosening a single gate.",
    command: "sprint",
    flag: "--farm",
    optIn: "/ca:sprint --farm",
    env: [
      {
        name: "FARM_API_KEY",
        required: true,
        description:
          "API key for the OpenAI-compatible endpoint that runs the farm workers. Without it, --farm cannot dispatch.",
      },
      {
        name: "FARM_API_BASE_URL",
        required: false,
        description:
          "Endpoint base URL for the worker API. Defaults to the OpenCode Zen endpoint when unset.",
      },
      {
        name: "FARM_MODEL",
        required: false,
        description:
          "Pin a specific worker model id. Normally left unset so the dispatch skill auto-selects one.",
      },
    ],
    helpGraduate: "run it on a real sprint and report the results.",
  },
  {
    name: "ca-sandbox (local Codespace)",
    kind: "preview-plugin",
    summary:
      "A local Codespace equivalent: clone an untrusted repo into an ephemeral, host-isolated Docker container and explore it under isolation that holds by construction (cap-drop ALL, non-root, read-only root, offline by default), not by trust.",
    optIn: "install the ca-sandbox plugin",
    requires: "Docker and nixpacks on PATH",
    helpGraduate: "explore real repos in it, run --with-claude, and report back.",
    href: "https://github.com/arbiterForge/codeArbiter#ca-sandbox-local-codespace",
  },
];

/** A whole command is in preview. */
export interface PreviewCommandStatus {
  kind: "preview-command";
  env?: ForgeEnvVar[];
}

/** One named flag on a command is in preview; the command itself is stable. */
export interface PreviewFlagStatus {
  kind: "preview-flag";
  flag: string;
  env?: ForgeEnvVar[];
}

export type ForgeStatus = PreviewCommandStatus | PreviewFlagStatus;

/**
 * Command-keyed forge status, derived from FORGE_FEATURES, for reference-page
 * badging. preview-plugin features have no /ca: command and are excluded.
 */
export const PREVIEW_COMMANDS: Record<string, ForgeStatus> = Object.fromEntries(
  FORGE_FEATURES.filter(
    (f) => f.kind === "preview-command" || f.kind === "preview-flag",
  ).map((f) => [
    f.command,
    f.kind === "preview-flag"
      ? { kind: "preview-flag", flag: f.flag, env: f.env }
      : { kind: "preview-command", env: f.env },
  ]),
);

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
