import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APPROVED_COLORS = new Set([
  "#090d12",
  "#0e141c",
  "#121a24",
  "#17212d",
  "#273647",
  "#3a4c60",
  "#91a0b2",
  "#c7d0da",
  "#f6f7f9",
  "#f0b92f",
  "#ffd568",
  "#9b6811",
  "#7ab7ff",
  "#58d68d",
  "#ff7b72",
]);

const APPROVED_FONTS = ["Manrope Variable", "JetBrains Mono Variable"];

export function auditDiagram(svg: string, filename: string): string[] {
  const violations: string[] = [];

  if (!/<svg\b[^>]*data-diagram-system="ca-v2"/.test(svg)) {
    violations.push(`${filename}: root must declare data-diagram-system="ca-v2"`);
  }
  if (!/<title\b[^>]*>[^<]+<\/title>/.test(svg)) {
    violations.push(`${filename}: missing non-empty title`);
  }
  if (!/<desc\b[^>]*>[^<]+<\/desc>/.test(svg)) {
    violations.push(`${filename}: missing non-empty description`);
  }
  if (/<filter\b/.test(svg)) {
    violations.push(`${filename}: filters are prohibited`);
  }

  for (const match of svg.matchAll(/font-family="([^"]+)"/g)) {
    if (!APPROVED_FONTS.some((font) => match[1].includes(font))) {
      violations.push(`${filename}: unapproved font family "${match[1]}"`);
    }
  }

  for (const match of svg.matchAll(/font-size="([\d.]+)"/g)) {
    const size = Number(match[1]);
    const tagStart = svg.lastIndexOf("<text", match.index);
    const tagEnd = svg.indexOf(">", tagStart);
    const tag = svg.slice(tagStart, tagEnd + 1);
    const minimum = tag.includes('data-label-kind="annotation"') ? 12 : 14;
    if (size < minimum) {
      violations.push(`${filename}: ${size}px label is below the ${minimum}px minimum`);
    }
  }

  const seenUnknownColors = new Set<string>();
  for (const match of svg.matchAll(/#[0-9a-fA-F]{6}\b/g)) {
    const color = match[0].toLowerCase();
    if (!APPROVED_COLORS.has(color) && !seenUnknownColors.has(color)) {
      seenUnknownColors.add(color);
      violations.push(`${filename}: unapproved color ${color}`);
    }
  }

  return violations;
}

function runCli(): void {
  const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const diagramRoot = join(siteRoot, "public", "diagrams");
  const violations = readdirSync(diagramRoot)
    .filter((name) => name.endsWith(".svg"))
    .sort()
    .flatMap((name) => auditDiagram(readFileSync(join(diagramRoot, name), "utf8"), name));

  if (violations.length === 0) {
    console.log("diagram-audit: OK");
    return;
  }

  console.error(violations.join("\n"));
  process.exitCode = 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runCli();
}
