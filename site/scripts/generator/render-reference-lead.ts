import type { CommandHost, CommandHostAvailability } from "./host-command-catalog";

export type ReferenceKind = "command" | "skill" | "agent";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const HOST_LABEL: Readonly<Record<CommandHost, string>> = {
  claude: "Claude Code",
  codex: "Codex",
  pi: "Pi",
};

function syntaxFor(host: CommandHost, name: string): string {
  if (host === "claude") return `/ca:${name}`;
  if (host === "codex") return `$ca-${name}`;
  return `/ca-${name}`;
}

function usageFor(
  kind: ReferenceKind,
  name: string,
  commandHosts?: CommandHostAvailability,
): string {

  if (kind === "command") {
    const availability = commandHosts ?? {
      claude: true,
      codex: false,
      pi: false,
    };
    const rows = (Object.keys(HOST_LABEL) as CommandHost[]).map((host) => {
      const value = availability[host]
        ? `<code>${escapeHtml(syntaxFor(host, name))}</code>`
        : '<span class="ca-reference-lead__unsupported">Not shipped</span>';
      return `<div class="ca-reference-lead__host"><span>${HOST_LABEL[host]}</span>${value}</div>`;
    });
    return [
      '<span class="ca-reference-lead__usage-label">Invoke it</span>',
      '<div class="ca-reference-lead__hosts">',
      ...rows,
      "</div>",
      "<p>Availability is read from each shipped host catalog. Preview-only commands are marked on the page.</p>",
    ].join("\n");
  }

  if (kind === "skill") {
    return [
      '<span class="ca-reference-lead__usage-label">How it is used</span>',
      "<p>The orchestrator routes to this skill from an owning command. It is not a direct user entry point.</p>",
    ].join("\n");
  }

  return [
    '<span class="ca-reference-lead__usage-label">How it is used</span>',
    "<p>An owning skill dispatches this specialist. You invoke the command that owns the lane, not the agent directly.</p>",
  ].join("\n");
}

/**
 * Render the collection-specific orientation shared by all generated reference
 * pages. It makes the command/skill/agent distinction visible before the
 * curated detail while keeping the exact source embed further down the page.
 */
export function renderReferenceLead(
  kind: ReferenceKind,
  name: string,
  description: string,
  commandHosts?: CommandHostAvailability,
): string {
  const label = kind === "command" ? "Command" : kind === "skill" ? "Routed skill" : "Specialist agent";
  const summary = escapeHtml(description);

  return [
    `<div class="ca-reference-lead" data-reference-kind="${kind}">`,
    '<div class="ca-reference-lead__copy">',
    `<span class="ca-reference-lead__kind">${label}</span>`,
    `<p class="ca-reference-lead__summary">${summary}</p>`,
    "</div>",
    '<div class="ca-reference-lead__usage">',
    usageFor(kind, name, commandHosts),
    "</div>",
    "</div>",
  ].join("\n");
}
