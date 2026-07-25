import { randomBytes } from "node:crypto";

import { redactSecrets as redactSharedSecrets } from "../../../ca/tools/redactor.ts";

export function redactSecrets(value: string): string {
  return redactSharedSecrets(value);
}

// #449 — a known filesystem path is a STRUCTURAL field, not a value.
//
// The shared redactor is deliberately broad: any line containing `secret`,
// `token`, `password` or `api_key` is replaced wholesale, because over-redaction
// is the safe direction for content leaving the trust boundary. That is right
// for content the process cannot vouch for. It is wrong for a path the process
// ALREADY KNOWS — its own project root, its own package root — because those are
// values to COMPARE against, not shapes to guess at.
//
// Applying value-shaped matching to them means a repository or worktree whose
// directory name happens to contain a trigger word has its own diagnostics
// replaced by a redaction notice. Observed in a worktree named
// `pr432-secret-scan-narrowness`: the `package`, `core` and `child` lines of
// /ca-doctor — the three that embed the project path — each came back as
// `[REDACTED …]`. The same commit is clean from a benignly named worktree, so it
// is the path, not the content. /ca-doctor is the diagnostic of LAST RESORT, so
// this makes the tool fail hardest exactly when it is needed, and it fails
// silently: the user sees a redaction notice where a path should be, with no
// hint that their directory name was mistaken for a credential. Anyone working
// on security features is disproportionately likely to hit it — those branches
// and worktrees carry those words by nature.
//
// The exemption is EXACT-LITERAL and OPT-IN. A caller names the paths it knows;
// each occurrence is masked before matching and restored after, so the rest of
// the line is still scanned in full. A line carrying a real credential alongside
// an exempt path is still redacted whole — this removes a false positive, it
// does not create a bypass.
//
// The mask is NONCE-KEYED. A hostile report cannot forge a placeholder to make
// the restore pass inject a path the caller never named, and the nonce is minted
// per call, so a placeholder observed in one report is useless in the next.
const MIN_BENIGN_LITERAL_LENGTH = 8;

function maskBenign(
  value: string,
  benign: readonly string[],
): { masked: string; restore: (text: string) => string } {
  // Longest first: a package root nested inside a project root must be masked as
  // itself rather than half-shadowed by its parent. The length floor keeps a
  // short or empty literal from masking half the report.
  const literals = [...new Set(benign)]
    .filter((literal) => literal.length >= MIN_BENIGN_LITERAL_LENGTH)
    .sort((a, b) => b.length - a.length);
  const identity = { masked: value, restore: (text: string) => text };
  if (literals.length === 0) return identity;

  const nonce = randomBytes(8).toString("hex");
  const captured: string[] = [];
  let masked = value;
  for (const literal of literals) {
    const pattern = new RegExp(literal.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "gu");
    masked = masked.replace(pattern, (match) => `${nonce}-${captured.push(match) - 1}`);
  }
  if (captured.length === 0) return identity;

  const placeholder = new RegExp(`${nonce}-(\\d+)`, "gu");
  return {
    masked,
    restore: (text) =>
      text.replace(placeholder, (whole, index: string) => captured[Number(index)] ?? whole),
  };
}

export function safeDiagnostic(
  value: string,
  maxChars = 2_000,
  benignPaths: readonly string[] = [],
): string {
  const { masked, restore } = maskBenign(value, benignPaths);
  // Restore BEFORE the control-character scrub and the length bound, so a
  // restored path is measured and sanitized exactly as it would have been had
  // it never been masked.
  const normalized = restore(redactSecrets(masked))
    .replace(/\r\n?/gu, "\n")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "�")
    .trim();
  return normalized.length <= maxChars ? normalized : `${normalized.slice(0, maxChars)}…`;
}

export function redactJson(value: unknown, depth = 0): unknown {
  if (depth > 32) return "[REDACTED OVERSIZE VALUE]";
  if (typeof value === "string") return safeDiagnostic(value, 16_000);
  if (Array.isArray(value)) return value.map((item) => redactJson(item, depth + 1));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redactJson(item, depth + 1)]));
  }
  return value;
}
