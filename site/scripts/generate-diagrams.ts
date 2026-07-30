import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const C = {
  bg: "#090d12",
  raised: "#0e141c",
  panel: "#121a24",
  soft: "#17212d",
  line: "#273647",
  lineStrong: "#3a4c60",
  muted: "#91a0b2",
  text: "#c7d0da",
  white: "#f6f7f9",
  gold: "#f0b92f",
  goldBright: "#ffd568",
  goldDeep: "#9b6811",
  info: "#7ab7ff",
  positive: "#58d68d",
  danger: "#ff7b72",
} as const;

const sans = "Manrope Variable, Segoe UI, Arial, sans-serif";
const mono = "JetBrains Mono Variable, Consolas, Cascadia Mono, monospace";

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function label(
  x: number,
  y: number,
  value: string,
  options: {
    size?: number;
    color?: string;
    weight?: number;
    anchor?: "start" | "middle" | "end";
    family?: "sans" | "mono";
    letterSpacing?: number;
    annotation?: boolean;
    kind?: "copy";
    maxWidth?: number;
  } = {},
): string {
  const size = options.size ?? 14;
  const family = options.family === "mono" ? mono : sans;
  const attrs = [
    `x="${x}"`,
    `y="${y}"`,
    `font-family="${family}"`,
    `font-size="${size}"`,
    `font-weight="${options.weight ?? 500}"`,
    `fill="${options.color ?? C.text}"`,
    `text-anchor="${options.anchor ?? "start"}"`,
  ];
  if (options.letterSpacing) attrs.push(`letter-spacing="${options.letterSpacing}"`);
  if (options.kind) attrs.push(`data-label-kind="${options.kind}"`);
  else if (options.annotation) attrs.push('data-label-kind="annotation"');
  if (options.maxWidth) attrs.push(`data-max-width="${options.maxWidth}"`);
  return `<text ${attrs.join(" ")}>${escapeXml(value)}</text>`;
}

function multiline(
  x: number,
  y: number,
  lines: string[],
  options: Parameters<typeof label>[3] = {},
  lineHeight = 19,
): string {
  return lines.map((line, index) => label(x, y + index * lineHeight, line, options)).join("\n");
}

function card(
  x: number,
  y: number,
  width: number,
  height: number,
  title: string,
  subtitle = "",
  accent: string = C.lineStrong,
): string {
  const titleLines = title.split("\n");
  const subtitleLines = subtitle.split("\n");
  const titleY = subtitle ? y + 31 : y + height / 2 + 5 - ((titleLines.length - 1) * 9);
  return [
    `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="10" fill="${C.panel}" stroke="${accent}" stroke-width="2"/>`,
    multiline(x + width / 2, titleY, titleLines, {
      size: 16,
      color: C.white,
      weight: 700,
      anchor: "middle",
      maxWidth: width - 24,
    }),
    subtitle
      ? multiline(x + width / 2, y + height - 18 - ((subtitleLines.length - 1) * 16), subtitleLines, {
          size: 12,
          color: C.muted,
          anchor: "middle",
          family: "mono",
          annotation: true,
          maxWidth: width - 24,
        }, 16)
      : "",
  ].join("\n");
}

function arrow(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string = C.lineStrong,
  dashed = false,
): string {
  return `<path d="M${x1} ${y1} L${x2} ${y2}" fill="none" stroke="${color}" stroke-width="2.25"${dashed ? ' stroke-dasharray="7 6"' : ""} marker-end="url(#arrow)"/>`;
}

function elbow(
  points: Array<[number, number]>,
  color: string = C.lineStrong,
  dashed = false,
): string {
  return `<polyline points="${points.map(([x, y]) => `${x},${y}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2.25"${dashed ? ' stroke-dasharray="7 6"' : ""} marker-end="url(#arrow)"/>`;
}

function declareCanvasTextBounds(body: string, width: number): string {
  const inset = 24;
  return body.replace(/<text\b(?<attributes>[^>]*)>/g, (tag, attributes: string) => {
    if (/\bdata-max-width=/.test(attributes)) return tag;
    const x = Number(attributes.match(/\bx="([\d.]+)"/)?.[1]);
    if (!Number.isFinite(x)) return tag;
    const anchor = attributes.match(/\btext-anchor="([^"]+)"/)?.[1] ?? "start";
    const maximum =
      anchor === "middle"
        ? 2 * Math.min(x - inset, width - inset - x)
        : anchor === "end"
          ? x - inset
          : width - inset - x;
    return tag.replace(/>$/, ` data-max-width="${Math.max(1, Math.floor(maximum))}">`);
  });
}

function shell(title: string, desc: string, width: number, height: number, body: string): string {
  const boundedBody = declareCanvasTextBounds(body, width);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" data-diagram-system="ca-v2">
  <title>${escapeXml(title)}</title>
  <desc>${escapeXml(desc)}</desc>
  <defs>
    <linearGradient id="canvas" x1="0" y1="0" x2="0" y2="1">
      <stop stop-color="${C.bg}"/>
      <stop offset="1" stop-color="${C.raised}"/>
    </linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="${C.line}" stroke-width="1" stroke-opacity=".24"/>
    </pattern>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
      <path d="M0 0 8 4 0 8z" fill="context-stroke"/>
    </marker>
  </defs>
  <rect width="${width}" height="${height}" rx="14" fill="url(#canvas)"/>
  <rect width="${width}" height="${height}" rx="14" fill="url(#grid)"/>
  <rect x="1" y="1" width="${width - 2}" height="${height - 2}" rx="13" fill="none" stroke="${C.lineStrong}" stroke-width="2"/>
  ${boundedBody}
</svg>
`;
}

type LaneColumn = { heading: string; tone: "gold" | "info" | "positive"; items: string[] };

function laneDiagram(title: string, desc: string, columns: LaneColumn[], note: string): string {
  const width = 1120;
  const height = 360;
  const gap = 38;
  const outer = 52;
  const columnWidth = (width - outer * 2 - gap * (columns.length - 1)) / columns.length;
  const tones = { gold: C.gold, info: C.info, positive: C.positive };
  const body: string[] = [
    label(52, 48, title.toUpperCase(), {
      size: 14,
      family: "mono",
      color: C.gold,
      weight: 750,
      letterSpacing: 2,
    }),
    label(52, 78, desc, { size: 18, color: C.white, weight: 700 }),
  ];

  columns.forEach((column, index) => {
    const x = outer + index * (columnWidth + gap);
    const tone = tones[column.tone];
    body.push(`<rect x="${x}" y="112" width="${columnWidth}" height="180" rx="12" fill="${C.panel}" stroke="${C.lineStrong}" stroke-width="2"/>`);
    body.push(label(x + 18, 140, column.heading.toUpperCase(), {
      size: 12,
      annotation: true,
      family: "mono",
      color: tone,
      weight: 750,
      letterSpacing: 1.6,
    }));
    column.items.forEach((item, itemIndex) => {
      const itemY = 160 + itemIndex * 38;
      body.push(`<rect x="${x + 16}" y="${itemY}" width="${columnWidth - 32}" height="30" rx="6" fill="${C.soft}" stroke="${tone}" stroke-width="1.5"/>`);
      body.push(label(x + columnWidth / 2, itemY + 20, item, {
        size: item.length > 25 ? 12 : 14,
        annotation: item.length > 25,
        family: "mono",
        color: C.white,
        weight: 650,
        anchor: "middle",
        maxWidth: columnWidth - 42,
      }));
    });
    if (index < columns.length - 1) {
      body.push(arrow(x + columnWidth + 6, 202, x + columnWidth + gap - 8, 202, tone));
    }
  });

  body.push(label(width - 52, 329, note, {
    size: 12,
    annotation: true,
    family: "mono",
    color: C.muted,
    anchor: "end",
  }));
  return shell(title, desc, width, height, body.join("\n"));
}

function horizontalFlow(
  title: string,
  desc: string,
  steps: Array<{ title: string; subtitle: string; accent?: string }>,
  footer: string,
): string {
  const width = 1200;
  const height = 310;
  const outer = 42;
  const gap = 42;
  const cardWidth = (width - outer * 2 - gap * (steps.length - 1)) / steps.length;
  const body = [
    label(42, 48, title.toUpperCase(), { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, desc, { size: 18, color: C.white, weight: 700 }),
  ];
  steps.forEach((step, index) => {
    const x = outer + index * (cardWidth + gap);
    body.push(card(x, 120, cardWidth, 92, step.title, step.subtitle, step.accent ?? C.lineStrong));
    if (index < steps.length - 1) {
      body.push(arrow(x + cardWidth + 6, 166, x + cardWidth + gap - 8, 166, step.accent ?? C.lineStrong));
    }
  });
  body.push(label(width - 42, 274, footer, {
    size: 12,
    annotation: true,
    family: "mono",
    color: C.muted,
    anchor: "end",
  }));
  return shell(title, desc, width, height, body.join("\n"));
}

function gateModel(): string {
  const title = "Soft gates surface; hard gates stop";
  const desc = "Matched soft and hard gate paths. A soft gate waits for a human decision and then continues. A hard gate blocks until the user performs the required action.";
  const body = [
    label(44, 50, "GATE BEHAVIOR", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(44, 82, "The same approach. Two different outcomes.", { size: 20, color: C.white, weight: 750 }),
    `<rect x="44" y="116" width="512" height="284" rx="14" fill="${C.panel}" stroke="${C.goldDeep}" stroke-width="2"/>`,
    `<rect x="584" y="116" width="512" height="284" rx="14" fill="${C.panel}" stroke="${C.danger}" stroke-width="2"/>`,
    label(74, 154, "SOFT GATE", { size: 12, annotation: true, family: "mono", color: C.gold, weight: 750, letterSpacing: 1.8 }),
    label(614, 154, "HARD GATE", { size: 12, annotation: true, family: "mono", color: C.danger, weight: 750, letterSpacing: 1.8 }),
    card(74, 184, 190, 94, "Decision\nsurfaced", "waiting for user", C.gold),
    card(344, 184, 182, 94, "Work proceeds", "after user acts", C.positive),
    arrow(270, 231, 334, 231, C.gold),
    label(300, 216, "DECISION", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.gold,
      anchor: "middle",
      letterSpacing: 0.8,
      maxWidth: 70,
    }),
    card(614, 184, 190, 94, "Stopped", "never auto-decided", C.danger),
    card(884, 184, 182, 94, "User action", "required\nto continue", C.danger),
    arrow(810, 231, 874, 231, C.danger),
    label(840, 216, "STOP", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.danger,
      anchor: "middle",
      letterSpacing: 0.8,
      maxWidth: 36,
    }),
    multiline(74, 322, ["Surfaces the exact choice.", "Resumes when the user decides."], {
      size: 14,
      color: C.text,
      kind: "copy",
      maxWidth: 452,
    }),
    multiline(614, 322, [
      "Security, auth/crypto, and irreversible ops stop.",
      "Gate bypass and merge-to-default stop.",
      "Only the user can clear the gate.",
    ], {
      size: 14,
      color: C.text,
      kind: "copy",
      maxWidth: 452,
    }),
    label(44, 436, "Frequent hard-gate trips indicate a thin specification, not a normal control loop.", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.muted,
    }),
  ];
  return shell(title, desc, 1140, 470, body.join("\n"));
}

function activationStates(): string {
  const title = "Repository activation contract";
  const desc = "The leading YAML frontmatter in .codearbiter/CONTEXT.md classifies a repository as dormant, malformed, or enabled.";
  const body = [
    label(42, 48, "ACTIVATION CONTRACT", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "Read .codearbiter/CONTEXT.md once; classify its leading frontmatter.", { size: 18, color: C.white, weight: 700 }),
    card(42, 126, 248, 96, "Read CONTEXT.md", "leading YAML only", C.info),
    card(372, 112, 240, 94, "Dormant", "missing file or no block", C.lineStrong),
    card(372, 236, 240, 94, "Malformed", "error surfaced", C.danger),
    card(694, 174, 240, 94, "Enabled", "arbiter: enabled", C.positive),
    arrow(296, 174, 362, 159, C.lineStrong),
    arrow(296, 174, 362, 283, C.danger),
    arrow(618, 252, 684, 221, C.positive),
    label(492, 354, "A malformed block never silently disables enforcement.", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.danger,
      anchor: "middle",
    }),
    label(492, 378, "The next activation check sees any file change.", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.muted,
      anchor: "middle",
    }),
  ];
  return shell(title, desc, 976, 410, body.join("\n"));
}

function fourTierMap(): string {
  const title = "File-to-knowledge priority map";
  const desc = "A file read is matched in priority order against security controls, accepted architecture decisions, approved specifications, and fresh provenance.";
  const tiers = [
    ["1", "security-\ncontrols.md", "security-entry\nfiles", C.danger],
    ["2", "decisions/", "accepted ADR\ngoverns glob", C.gold],
    ["3", "specs/", "approved Governs\nheader", C.info],
    ["4", "provenance", "stored hash\nstill matches", C.positive],
  ] as const;
  const body = [
    label(42, 48, "JUST-IN-TIME CONTEXT", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "Read(file) checks four tiers in strict priority order.", { size: 18, color: C.white, weight: 700 }),
    card(42, 154, 188, 92, "Read(file)", "PreToolUse hook", C.info),
  ];
  tiers.forEach(([number, name, subtitle, tone], index) => {
    const x = 300 + index * 200;
    body.push(card(x, 132, 184, 136, `${number}\n${name}`, subtitle, tone));
    if (index === 0) body.push(arrow(236, 200, 290, 200, C.info));
  });
  body.push(card(300, 310, 375, 82, "Inject highest-priority pointer", "budget ≤ 150 tokens", C.gold));
  body.push(card(710, 310, 375, 82, "No tier matches", "no injection · zero git calls", C.lineStrong));
  body.push(elbow([[642, 268], [642, 290], [487, 290], [487, 300]], C.gold));
  body.push(elbow([[970, 268], [970, 300]], C.lineStrong, true));
  return shell(title, desc, 1128, 430, body.join("\n"));
}

function coreFanout(): string {
  const title = "One core, three host plugins";
  const desc = "Shared Python and surface sources are generated into Claude Code, Codex, and Pi plugins behind a byte-identity check, while all hosts use one repository-owned state store.";
  const body = [
    label(42, 48, "BUILD-TIME GENERATION", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "One source fans out only after the byte-identity gate.", { size: 18, color: C.white, weight: 700 }),
    card(42, 190, 220, 110, "core/pysrc\ncore/surface", "shared hook core\n+ surface", C.info),
    card(334, 190, 190, 110, "CI gate", "byte-identity check", C.gold),
    arrow(268, 245, 324, 245, C.info),
    card(604, 118, 220, 84, "ca", "Claude Code plugin", C.gold),
    card(604, 222, 220, 84, "ca-codex", "Codex plugin", C.gold),
    card(604, 326, 220, 84, "ca-pi", "Pi plugin", C.gold),
    elbow([[530, 245], [564, 245], [564, 160], [594, 160]], C.gold),
    arrow(530, 245, 594, 264, C.gold),
    elbow([[530, 245], [564, 245], [564, 368], [594, 368]], C.gold),
    card(904, 222, 220, 84, "one .codearbiter/", "shared checked-in state", C.positive),
    elbow([[830, 160], [864, 160], [864, 264], [894, 264]], C.lineStrong, true),
    arrow(830, 264, 894, 264, C.lineStrong, true),
    elbow([[830, 368], [864, 368], [864, 264], [894, 264]], C.lineStrong, true),
    label(42, 444, "sync-core.py and build-surface.py generate host-native surfaces; CI gates every edge.", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.muted,
    }),
  ];
  return shell(title, desc, 1166, 476, body.join("\n"));
}

function provenanceFlow(): string {
  return horizontalFlow(
    "Context-drift provenance",
    "Detect, surface, and heal stale documentation claims.",
    [
      { title: "Source changes", subtitle: "tracked file edited", accent: C.info },
      { title: "Drift detected", subtitle: "hash mismatch", accent: C.danger },
      { title: "SessionStart", subtitle: "one passive line", accent: C.gold },
      { title: "Commit-gate", subtitle: "re-baseline or update", accent: C.positive },
    ],
    "A drifted claim is suppressed; /ca:context-check performs the same detection manually.",
  );
}

function sandboxBoundary(): string {
  const title = "Host filesystem isolation";
  const desc = "The untrusted repository lives in a read-only, capability-dropped container volume with no host bind mounts, no Docker socket, and no network.";
  const body = [
    label(42, 48, "CA-SANDBOX BOUNDARY", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "The repository enters a constrained container; the host does not.", { size: 18, color: C.white, weight: 700 }),
    `<rect x="42" y="116" width="1020" height="336" rx="16" fill="${C.panel}" stroke="${C.lineStrong}" stroke-width="2"/>`,
    label(68, 148, "HOST", { size: 12, annotation: true, family: "mono", color: C.muted, weight: 750, letterSpacing: 1.6 }),
    card(68, 176, 230, 96, "Host filesystem", "projects · credentials", C.lineStrong),
    card(68, 312, 230, 96, "Docker daemon", "socket never mounted", C.danger),
    `<rect x="372" y="146" width="650" height="272" rx="14" fill="${C.soft}" stroke="${C.gold}" stroke-width="2"/>`,
    label(398, 178, "CONTAINER", { size: 12, annotation: true, family: "mono", color: C.gold, weight: 750, letterSpacing: 1.6 }),
    card(398, 202, 260, 92, "/work/repo", "Docker named volume", C.gold),
    card(714, 202, 276, 92, "Runtime controls", "read-only · user 1000:1000", C.info),
    card(398, 322, 260, 68, "No host mounts", "no socket · no bind", C.danger),
    card(714, 322, 276, 68, "Policy controls", "no network · resource caps", C.positive),
    arrow(304, 224, 362, 248, C.gold),
    elbow([[658, 248], [688, 248], [688, 356], [704, 356]], C.lineStrong),
    label(552, 478, "Reviewed output leaves only through host-initiated docker cp. Unknown network policy fails closed.", {
      size: 12,
      annotation: true,
      family: "mono",
      color: C.muted,
      anchor: "middle",
    }),
  ];
  return shell(title, desc, 1104, 510, body.join("\n"));
}

function twoAxisModel(): string {
  const title = "Two independent release axes";
  const desc = "Semantic versioning governs the whole plugin payload. Feature Forge status governs each feature from preview to stable using evidence.";
  const body = [
    label(42, 48, "RELEASE MODEL", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "Payload versions and feature maturity answer different questions.", { size: 18, color: C.white, weight: 700 }),
    `<rect x="42" y="116" width="500" height="300" rx="14" fill="${C.panel}" stroke="${C.info}" stroke-width="2"/>`,
    `<rect x="570" y="116" width="500" height="300" rx="14" fill="${C.panel}" stroke="${C.gold}" stroke-width="2"/>`,
    label(72, 154, "SEMVER AXIS", { size: 12, annotation: true, family: "mono", color: C.info, weight: 750, letterSpacing: 1.8 }),
    label(600, 154, "FEATURE FORGE AXIS", { size: 12, annotation: true, family: "mono", color: C.gold, weight: 750, letterSpacing: 1.8 }),
    label(72, 188, "Whole payload", { size: 20, color: C.white, weight: 750 }),
    label(600, 188, "Per-feature maturity", { size: 20, color: C.white, weight: 750 }),
    card(72, 224, 124, 76, "v2.5.1", "released", C.lineStrong),
    card(230, 224, 124, 76, "v2.5.2", "current", C.info),
    card(388, 224, 124, 76, "v2.6.0", "next", C.lineStrong),
    arrow(202, 262, 220, 262, C.info),
    arrow(360, 262, 378, 262, C.info),
    card(600, 224, 154, 76, "preview", "opt-in · dormant", C.gold),
    card(886, 224, 154, 76, "stable", "on by default", C.positive),
    arrow(760, 262, 876, 262, C.gold),
    label(818, 246, "evidence", { size: 12, annotation: true, family: "mono", color: C.muted, anchor: "middle" }),
    multiline(72, 344, ["A version bump reaches every user.", "Governed by MAJOR · MINOR · PATCH."], {
      size: 14,
      color: C.text,
      kind: "copy",
      maxWidth: 440,
    }),
    multiline(600, 344, ["A preview can exist inside a stable release.", "Promotion requires real-world evidence."], {
      size: 14,
      color: C.text,
      kind: "copy",
      maxWidth: 440,
    }),
  ];
  return shell(title, desc, 1112, 450, body.join("\n"));
}

function commitGatePhases(): string {
  const title = "Commit-gate: nine hard-gated phases";
  const desc = "Permission, branch, classification, verification, behavioral proof, diff review, selective stage, message, and commit form a nine-phase pipeline. Provenance auto-heal is a conditional side lane after behavioral proof.";
  const phases = [
    ["1", "Permission"], ["2", "Branch"], ["3", "Classify"],
    ["4", "Verify"], ["5", "Behavioral\nproof"], ["6", "Diff review"],
    ["7", "Selective\nstage"], ["8", "Message"], ["9", "Commit"],
  ];
  const positions: Array<[number, number]> = [
    [42, 126], [376, 126], [710, 126],
    [710, 258], [376, 258], [42, 258],
    [42, 390], [376, 390], [710, 390],
  ];
  const body = [
    label(42, 48, "COMMIT-GATE", { size: 14, family: "mono", color: C.gold, weight: 750, letterSpacing: 2 }),
    label(42, 78, "Nine phases. Every failure is a hard BLOCK.", { size: 18, color: C.white, weight: 700 }),
  ];
  phases.forEach(([number, name], index) => {
    const [x, y] = positions[index];
    body.push(card(x, y, 260, 92, name, `phase ${number}`, index === 8 ? C.positive : C.lineStrong));
    if (index < phases.length - 1) {
      const [nextX, nextY] = positions[index + 1];
      if (y === nextY) {
        const direction = nextX > x ? 1 : -1;
        body.push(arrow(
          direction > 0 ? x + 266 : x - 6,
          y + 46,
          direction > 0 ? nextX - 10 : nextX + 270,
          nextY + 46,
          C.gold,
        ));
      } else {
        body.push(elbow([[x + 130, y + 98], [x + 130, nextY - 10]], C.gold));
      }
    }
  });
  body.push(`<rect x="970" y="258" width="218" height="92" rx="10" fill="${C.soft}" stroke="${C.gold}" stroke-width="2" stroke-dasharray="7 6"/>`);
  body.push(multiline(1079, 289, ["5.5 · Provenance", "auto-heal"], { size: 14, color: C.white, weight: 700, anchor: "middle" }));
  body.push(label(1079, 334, "only on drift", { size: 12, annotation: true, family: "mono", color: C.muted, anchor: "middle" }));
  body.push(elbow([[636, 304], [956, 304]], C.gold, true));
  body.push(label(1188, 508, "A BLOCK clears only through the logged /ca:override path.", {
    size: 12,
    annotation: true,
    family: "mono",
    color: C.muted,
    anchor: "end",
  }));
  return shell(title, desc, 1230, 540, body.join("\n"));
}

const diagrams: Record<string, string> = {
  "activation-states.svg": activationStates(),
  "commit-gate-phases.svg": commitGatePhases(),
  "core-fanout.svg": coreFanout(),
  "four-tier-map.svg": fourTierMap(),
  "gate-model.svg": gateModel(),
  "lane-add-dep.svg": laneDiagram(
    "Dependency lane",
    "Review the supply chain before installation.",
    [
      { heading: "Command", tone: "gold", items: ["/ca:add-dep"] },
      { heading: "Agent", tone: "positive", items: ["dependency-reviewer"] },
    ],
    "license · provenance · vulnerability review must clear before install",
  ),
  "lane-adr.svg": laneDiagram(
    "Decision lane",
    "Author a durable decision, then inspect its health.",
    [
      { heading: "Commands", tone: "gold", items: ["/ca:adr", "/ca:adr-status"] },
      { heading: "Skill", tone: "info", items: ["decision-lifecycle"] },
    ],
    "the ADR is numbered, dated, user-attributed, and governed",
  ),
  "lane-feature.svg": laneDiagram(
    "Feature lane",
    "From approved intent to reviewed pull request.",
    [
      { heading: "Commands", tone: "gold", items: ["/ca:feature", "/ca:commit", "/ca:pr"] },
      { heading: "Skills", tone: "info", items: ["brainstorming", "writing-plans", "tdd"] },
      { heading: "Agents", tone: "positive", items: ["author agents", "reviewer agents"] },
    ],
    "execution order is governed; the default branch is never a direct write",
  ),
  "lane-flow.svg": horizontalFlow(
    "Gated lane flow",
    "Intent routes to its owner, clears the applicable gates, and ships through a pull request.",
    [
      { title: "/ca:fix", subtitle: "COMMAND", accent: C.gold },
      { title: "orchestrator", subtitle: "ROUTE", accent: C.info },
      { title: "tests · review\nsecurity", subtitle: "GATE", accent: C.gold },
      { title: "version control", subtitle: "SHIP", accent: C.positive },
      { title: "pull request", subtitle: "MERGE PATH", accent: C.positive },
    ],
    "never a direct write to the default branch",
  ),
  "lane-opt-in.svg": laneDiagram(
    "Repository opt-in",
    "Choose exactly one initialization path.",
    [
      { heading: "New project", tone: "gold", items: ["/ca:init", "/ca:decompose"] },
      { heading: "Existing code", tone: "gold", items: ["/ca:create-context"] },
      { heading: "Skills", tone: "info", items: ["decompose", "context-creation"] },
    ],
    "one repository routes to one initialization path",
  ),
  "lane-release.svg": laneDiagram(
    "Release lane",
    "Derive a version, update the record, and clear commit-gate.",
    [
      { heading: "Command", tone: "gold", items: ["/ca:release"] },
      { heading: "Skills", tone: "info", items: ["release", "commit-gate"] },
    ],
    "SemVer, changelog, commit, and annotated tag move together",
  ),
  "lane-sprint.svg": laneDiagram(
    "Autonomous sprint lane",
    "One approved target, then governed plan-to-PR execution.",
    [
      { heading: "Command", tone: "gold", items: ["/ca:sprint"] },
      { heading: "Skills", tone: "info", items: ["writing-plans", "subagent-driven-development", "commit-gate"] },
      { heading: "Roles", tone: "positive", items: ["author worker", "reviewer fleet", "branch finisher"] },
    ],
    "SMARTS calls are logged; hard gates remain true stops",
  ),
  "provenance-drift-flow.svg": provenanceFlow(),
  "sandbox-boundary.svg": sandboxBoundary(),
  "two-axis-model.svg": twoAxisModel(),
};

const outputDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public", "diagrams");
mkdirSync(outputDir, { recursive: true });
for (const [name, svg] of Object.entries(diagrams)) {
  writeFileSync(join(outputDir, name), svg, "utf8");
}
console.log(`generated ${Object.keys(diagrams).length} diagrams -> ${outputDir}`);
