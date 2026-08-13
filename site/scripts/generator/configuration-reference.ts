export type ConfigurationGroup =
  | "Core and safety"
  | "Statusline"
  | "PR watch"
  | "Transcript pruning"
  | "Farm backend";

export interface ConfigurationEntry {
  readonly name: string;
  readonly group: ConfigurationGroup;
  readonly defaultValue: string;
  readonly accepted: string;
  readonly purpose: string;
  readonly caution?: string;
}

/**
 * Operator-facing environment variables only. Test seams, derived internal
 * state paths, and host-private transport variables are intentionally omitted.
 */
export const CONFIGURATION_ENTRIES: readonly ConfigurationEntry[] = [
  {
    name: "NO_COLOR",
    group: "Core and safety",
    defaultValue: "unset",
    accepted: "any present value",
    purpose: "Removes ANSI color from terminal output while preserving content and layout.",
  },
  {
    name: "CODEARBITER_BASE_BRANCH",
    group: "Core and safety",
    defaultValue: "`main`",
    accepted: "local branch name",
    purpose: "Sets the branch used as the SessionStart comparison base when the repository uses a different default.",
    caution: "This changes startup reporting only; it does not retarget a pull request or authorize a merge.",
  },
  {
    name: "CODEARBITER_THEME",
    group: "Statusline",
    defaultValue: "`violet`",
    accepted: "`violet`, `blue`, `green`, `amber`, `mono`, or `custom`",
    purpose: "Selects the Claude Code statusline palette.",
  },
  {
    name: "CODEARBITER_THEME_FILE",
    group: "Statusline",
    defaultValue: "`~/.codearbiter/statusline-theme.json`",
    accepted: "local JSON file path",
    purpose: "Overrides the custom-theme file used when `CODEARBITER_THEME=custom`.",
  },
  {
    name: "CODEARBITER_STATUSLINE",
    group: "Statusline",
    defaultValue: "on",
    accepted: "`off` disables",
    purpose: "Disables the Claude Code statusline without uninstalling its settings entry.",
  },
  {
    name: "CODEARBITER_WIDTH",
    group: "Statusline",
    defaultValue: "terminal width",
    accepted: "integer, clamped to 70–160",
    purpose: "Overrides the rendered statusline width; otherwise `COLUMNS` and terminal probes apply.",
  },
  {
    name: "CODEARBITER_COMPACT",
    group: "Statusline",
    defaultValue: "off",
    accepted: "`1`, `true`, `on`, or `yes`",
    purpose: "Uses the lean statusline layout and drops subagent rows.",
  },
  {
    name: "CODEARBITER_COMPACT_AT",
    group: "Statusline",
    defaultValue: "`92`",
    accepted: "context percentage",
    purpose: "Sets the context-usage threshold presented as compaction pressure.",
  },
  {
    name: "CODEARBITER_BABYSIT",
    group: "PR watch",
    defaultValue: "`off`",
    accepted: "`on`, `true`, or `1`",
    purpose: "Auto-attaches the server-side PR watcher after the PR command opens a pull request.",
    caution: "It applies only in opted-in repositories and never enables itself or auto-merges.",
  },
  {
    name: "CODEARBITER_BABYSIT_ONRED",
    group: "PR watch",
    defaultValue: "`propose`",
    accepted: "`propose` or `branch`",
    purpose: "Chooses whether a red watcher only diagnoses and proposes, or also creates an unmergeable spike branch.",
    caution: "Unknown values fail closed to `propose`; the `branch` result can never be merged or opened as a PR.",
  },
  {
    name: "CODEARBITER_PRUNE",
    group: "Transcript pruning",
    defaultValue: "`off`",
    accepted: "`off`, `dry`, or `on`",
    purpose: "Controls the preview transcript-pruning service; `dry` records candidates without pruning.",
    caution: "Enable it yourself only after reviewing dry-run output; codeArbiter never opts you in.",
  },
  {
    name: "CODEARBITER_PRUNE_TIER",
    group: "Transcript pruning",
    defaultValue: "`gentle`",
    accepted: "documented pruning tier",
    purpose: "Selects the pruning strategy preset.",
  },
  {
    name: "CODEARBITER_PRUNE_STRATEGIES",
    group: "Transcript pruning",
    defaultValue: "tier defaults",
    accepted: "comma-separated strategy names",
    purpose: "Overrides the strategy set selected by the pruning tier.",
  },
  {
    name: "CODEARBITER_PRUNE_KEEP_RECENT",
    group: "Transcript pruning",
    defaultValue: "`10`",
    accepted: "non-negative integer",
    purpose: "Keeps this many recent eligible items untouched.",
  },
  {
    name: "CODEARBITER_PRUNE_MAXBYTES",
    group: "Transcript pruning",
    defaultValue: "`8192`",
    accepted: "positive byte count",
    purpose: "Caps replacement sidecar content retained for one pruned item.",
  },
  {
    name: "CODEARBITER_PRUNE_MIN_SIZE",
    group: "Transcript pruning",
    defaultValue: "`1048576`",
    accepted: "positive byte count",
    purpose: "Requires this transcript size before the service considers pruning.",
  },
  {
    name: "CODEARBITER_PRUNE_MIN_GROWTH",
    group: "Transcript pruning",
    defaultValue: "`262144`",
    accepted: "positive byte count",
    purpose: "Requires this much growth since the previous pass before reconsidering the transcript.",
  },
  {
    name: "CODEARBITER_PRUNE_BACKUPS",
    group: "Transcript pruning",
    defaultValue: "`3`",
    accepted: "non-negative integer",
    purpose: "Retains this many rotating transcript backups before older backups are removed.",
  },
  {
    name: "CODEARBITER_PRUNE_LIVE_SECS",
    group: "Transcript pruning",
    defaultValue: "`90`",
    accepted: "non-negative seconds",
    purpose: "Treats a transcript as live for this long after its latest update and avoids compacting it.",
  },
  {
    name: "CODEARBITER_PRUNE_METRICS",
    group: "Transcript pruning",
    defaultValue: "`~/.codearbiter/metrics/prune-dry.jsonl`",
    accepted: "local JSONL file path",
    purpose: "Overrides the append-only destination for dry-run pruning measurements.",
  },
  {
    name: "CODEARBITER_PRUNE_NUDGE",
    group: "Transcript pruning",
    defaultValue: "`off`",
    accepted: "`on` to arm",
    purpose: "Enables the preview cold-miss nudge when pruning is also on.",
  },
  {
    name: "CODEARBITER_PRUNE_NUDGE_IDLE_SECS",
    group: "Transcript pruning",
    defaultValue: "`240`",
    accepted: "positive seconds",
    purpose: "Sets the minimum idle period before a cold-miss nudge can appear.",
  },
  {
    name: "CODEARBITER_PRUNE_NUDGE_MIN_TOKENS",
    group: "Transcript pruning",
    defaultValue: "`80000`",
    accepted: "positive estimated token count",
    purpose: "Sets the minimum model-context size before a cold-miss nudge can appear.",
  },
  {
    name: "FARM_API_KEY",
    group: "Farm backend",
    defaultValue: "required for `--farm`",
    accepted: "provider API key",
    purpose: "Authenticates the preview OpenAI-compatible farm backend.",
    caution: "Keep it in the shell environment or the documented local tools `.env`; never commit it.",
  },
  {
    name: "FARM_API_BASE_URL",
    group: "Farm backend",
    defaultValue: "`https://opencode.ai/zen/v1`",
    accepted: "HTTPS OpenAI-compatible endpoint",
    purpose: "Selects the farm provider endpoint.",
  },
  {
    name: "FARM_MODEL",
    group: "Farm backend",
    defaultValue: "automatic selection",
    accepted: "provider model id",
    purpose: "Skips canary and cached model selection and pins one model.",
  },
  {
    name: "FARM_CANDIDATE_MODELS",
    group: "Farm backend",
    defaultValue: "unset",
    accepted: "comma-separated provider model ids",
    purpose: "Supplies the model set for a canary comparison.",
  },
  {
    name: "FARM_CONCURRENCY",
    group: "Farm backend",
    defaultValue: "`4`",
    accepted: "integer of at least 1",
    purpose: "Caps total in-flight worker calls, including best-of-N samples.",
  },
  {
    name: "FARM_BASE_BRANCH",
    group: "Farm backend",
    defaultValue: "`main`",
    accepted: "local branch name",
    purpose: "Sets the branch from which the farm integration branch is created.",
  },
  {
    name: "FARM_INTEGRATION_BRANCH",
    group: "Farm backend",
    defaultValue: "`farm/integration`",
    accepted: "new or existing local branch name",
    purpose: "Names the farm's integration branch.",
    caution: "Concurrent farm runs need distinct integration branches.",
  },
  {
    name: "FARM_SAMPLES",
    group: "Farm backend",
    defaultValue: "`1`",
    accepted: "integer of at least 1",
    purpose: "Draws this many isolated candidates per task attempt; the first gate-passing candidate wins.",
    caution: "Values above 1 can multiply provider token use even though concurrency remains capped.",
  },
  {
    name: "FARM_TEMPERATURE",
    group: "Farm backend",
    defaultValue: "`0`",
    accepted: "provider-supported number",
    purpose: "Controls worker sampling; when samples exceed 1 and this is unset, the dispatcher uses 0.7.",
  },
  {
    name: "FARM_MAX_TOKENS",
    group: "Farm backend",
    defaultValue: "provider default",
    accepted: "non-negative integer",
    purpose: "Caps completion tokens per worker call; `0` leaves the provider default.",
  },
  {
    name: "FARM_MAX_RETRIES",
    group: "Farm backend",
    defaultValue: "`2`",
    accepted: "non-negative integer",
    purpose: "Limits gate retries for one task before escalation.",
  },
  {
    name: "FARM_REQUEST_TIMEOUT_MS",
    group: "Farm backend",
    defaultValue: "`120000`",
    accepted: "positive milliseconds",
    purpose: "Bounds one provider request, including its response body.",
  },
  {
    name: "FARM_API_MAX_RETRIES",
    group: "Farm backend",
    defaultValue: "`3`",
    accepted: "non-negative integer",
    purpose: "Limits transport retries for rate limits and server errors; provider `Retry-After` is honored.",
  },
  {
    name: "FARM_ENTITLEMENT_PROBE_TIMEOUT_MS",
    group: "Farm backend",
    defaultValue: "`35000`",
    accepted: "positive milliseconds",
    purpose: "Bounds each model-entitlement probe during canary selection.",
  },
  {
    name: "FARM_GATE_TIMEOUT_MS",
    group: "Farm backend",
    defaultValue: "`300000`",
    accepted: "milliseconds of at least 1000",
    purpose: "Bounds each non-git setup, gate, and mutation child command.",
  },
  {
    name: "FARM_ABORT_ESCALATION_RATE",
    group: "Farm backend",
    defaultValue: "`0.5`",
    accepted: "number from 0 to 1",
    purpose: "Trips the dispatch circuit breaker when the settled-task escalation rate exceeds this fraction.",
  },
  {
    name: "FARM_ABORT_MIN_TASKS",
    group: "Farm backend",
    defaultValue: "`3`",
    accepted: "positive integer",
    purpose: "Requires this many settled tasks before the escalation-rate circuit breaker can abort a run.",
  },
  {
    name: "FARM_ENRICH_MAX_BYTES",
    group: "Farm backend",
    defaultValue: "`131072`",
    accepted: "positive byte count",
    purpose: "Caps test and in-scope source context injected into a worker prompt.",
  },
  {
    name: "FARM_WORKTREE_ROOT",
    group: "Farm backend",
    defaultValue: "`.farm/worktrees`",
    accepted: "repository-contained directory",
    purpose: "Sets the scratch worktree root used by farm tasks and samples.",
    caution: "An external root is refused unless `FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1` is set explicitly.",
  },
  {
    name: "FARM_ALLOW_EXTERNAL_WORKTREE_ROOT",
    group: "Farm backend",
    defaultValue: "off",
    accepted: "`1` to arm",
    purpose: "Allows `FARM_WORKTREE_ROOT` to resolve outside the repository.",
    caution: "This is a destructive-scope override: farm cleanup recursively removes task worktrees under that root.",
  },
  {
    name: "FARM_REPORT_DIR",
    group: "Farm backend",
    defaultValue: "`.farm`",
    accepted: "directory path",
    purpose: "Sets the root for run-scoped farm receipts and reports.",
  },
  {
    name: "FARM_RUN_ID",
    group: "Farm backend",
    defaultValue: "fresh random id",
    accepted: "1–64 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, or `-`",
    purpose: "Pins the run receipt directory name for reproducibility.",
    caution: "Reusing an id publishes over that run's existing receipt directory; use a fresh id per run.",
  },
  {
    name: "FARM_MUTATION",
    group: "Farm backend",
    defaultValue: "`on`",
    accepted: "`off` disables",
    purpose: "Disables the farm mutation guard for a run.",
  },
  {
    name: "FARM_MUTATION_SAMPLE",
    group: "Farm backend",
    defaultValue: "`15`",
    accepted: "positive integer",
    purpose: "Caps the number of built-in mutation candidates evaluated per task.",
  },
  {
    name: "FARM_MUTATION_BUDGET_MS",
    group: "Farm backend",
    defaultValue: "`30000`",
    accepted: "non-negative milliseconds",
    purpose: "Time-boxes mutation testing for one task.",
  },
  {
    name: "FARM_MUTATION_WARN_BELOW",
    group: "Farm backend",
    defaultValue: "`0.5`",
    accepted: "number from 0 to 1",
    purpose: "Attaches a review warning when the mutation score falls below this value.",
  },
  {
    name: "FARM_MUTATION_ESCALATE_BELOW",
    group: "Farm backend",
    defaultValue: "`0.1`",
    accepted: "number from 0 to 1",
    purpose: "Hard-escalates a sufficiently sampled task at or below this mutation score.",
  },
  {
    name: "FARM_MUTATION_CMD",
    group: "Farm backend",
    defaultValue: "built-in text mutator",
    accepted: "local executable command",
    purpose: "Replaces the built-in mutator with a language-specific mutation framework.",
    caution: "The command runs inside the task worktree; verify it independently before trusting its score.",
  },
];

const GROUPS: readonly ConfigurationGroup[] = [
  "Core and safety",
  "Statusline",
  "PR watch",
  "Transcript pruning",
  "Farm backend",
];

function renderEntry(entry: ConfigurationEntry): string {
  const caution = entry.caution ? ` ${entry.caution}` : "";
  return `| \`${entry.name}\` | ${entry.defaultValue} | ${entry.accepted} | ${entry.purpose}${caution} |`;
}

export function renderConfigurationReference(
  entries: readonly ConfigurationEntry[] = CONFIGURATION_ENTRIES,
): string {
  const sections = GROUPS.map((group) => {
    const rows = entries.filter((entry) => entry.group === group).map(renderEntry).join("\n");
    return `## ${group}\n\n| Variable | Default | Accepted values | Effect |\n|---|---|---|---|\n${rows}`;
  }).join("\n\n");

  return `---
title: Configuration Reference
description: "Operator-facing environment variables for codeArbiter, with defaults, accepted values, effects, and safety boundaries."
---

Use environment variables only when the documented default does not fit. Host-native commands
remain the primary interface; these settings tune a feature or arm an explicitly opt-in surface.

Set a variable in the environment that launches your host, then start a fresh session. On
PowerShell, use \`$env:NAME = "value"\` for the current process. On POSIX shells, use
\`export NAME=value\`. Persist values with your operating system or shell profile only after a
temporary session behaves as expected.

Do not commit secrets or machine-specific paths. Unknown values generally fall back or fail soft,
but safety-sensitive settings can refuse a run. The tables below cover supported operator-facing
settings; test seams and internal state-path overrides are intentionally excluded.

This catalog is typed and deterministic, but its defaults and explanations are maintainer-reviewed
rather than extracted from executable code. A contract test requires every documented variable name
to exist in shipped implementation code; follow the linked feature guide and current source when a
default is release-critical.

${sections}

## Verify and undo

After changing a statusline setting, run the statusline status command and trigger a new render.
After changing pruning, run the prune status command and begin with \`dry\`. Farm settings are
recorded in the run report; inspect that receipt before trusting the result.

To undo a setting, remove it from the launch environment and start a fresh host session. Removing
\`FARM_API_KEY\` makes \`--farm\` stop at preflight; it does not affect the premium path.

## Related

- [Set Up the Statusline](/guides/the-statusline/)
- [Transcript pruning command](/reference/commands/prune/)
- [Run an Autonomous Sprint](/guides/autonomous-sprints/)
- [Feature Forge](/feature-forge/overview/)
`;
}
