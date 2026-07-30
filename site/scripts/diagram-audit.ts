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

const APPROVED_FONT_STACKS = new Set([
  "Manrope Variable, Segoe UI, Arial, sans-serif",
  "JetBrains Mono Variable, Consolas, Cascadia Mono, monospace",
]);

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
    if (!APPROVED_FONT_STACKS.has(match[1])) {
      violations.push(`${filename}: font stack is not self-contained "${match[1]}"`);
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

  for (const match of svg.matchAll(/<text\b(?<attributes>[^>]*)>(?<copy>[^<]*)<\/text>/g)) {
    const attributes = match.groups?.attributes ?? "";
    const maximumMatch = attributes.match(/\bdata-max-width="([\d.]+)"/);
    if (!maximumMatch) {
      violations.push(`${filename}: text has no declared maximum width`);
      continue;
    }
    const sizeMatch = attributes.match(/\bfont-size="([\d.]+)"/);
    const familyMatch = attributes.match(/\bfont-family="([^"]+)"/);
    if (!sizeMatch || !familyMatch) {
      violations.push(`${filename}: bounded text is missing measurable font metrics`);
      continue;
    }

    const size = Number(sizeMatch[1]);
    const maximum = Number(maximumMatch[1]);
    const copy = (match.groups?.copy ?? "")
      .replaceAll("&amp;", "&")
      .replaceAll("&lt;", "<")
      .replaceAll("&gt;", ">")
      .replaceAll("&quot;", '"');
    const characters = [...copy];
    const mono = familyMatch[1].includes("monospace");
    const weight = Number(attributes.match(/\bfont-weight="([\d.]+)"/)?.[1] ?? 500);
    const weightFactor = weight >= 700 ? 1.03 : weight >= 600 ? 1.015 : 1;
    const letterSpacing = Number(
      attributes.match(/\bletter-spacing="(-?[\d.]+)"/)?.[1] ?? 0,
    );
    const glyphWidth = characters.reduce((total, character) => {
      if (mono) return total + size * 0.66;
      if (character === " ") return total + size * 0.34;
      if (/[ilI1.,:;|!'`]/.test(character)) return total + size * 0.38;
      if (/[mw]/.test(character)) return total + size * 0.92;
      if (/[MW@%&#]/.test(character)) return total + size;
      if (/[A-Z0-9]/.test(character)) return total + size * 0.74;
      if (/[-/()[\]]/.test(character)) return total + size * 0.46;
      return total + size * 0.64;
    }, 0);
    const width =
      glyphWidth * weightFactor + Math.max(0, characters.length - 1) * letterSpacing;

    if (width > maximum) {
      const kind = attributes.match(/\bdata-label-kind="([^"]+)"/)?.[1] ?? "text";
      violations.push(
        `${filename}: ${kind} width ${Math.round(width * 10) / 10} exceeds declared maximum ${maximum}`,
      );
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
