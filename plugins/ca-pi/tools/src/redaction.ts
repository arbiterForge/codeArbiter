import { redactSecrets as redactSharedSecrets } from "../../../ca/tools/redactor.ts";

export function redactSecrets(value: string): string {
  return redactSharedSecrets(value);
}

export function safeDiagnostic(value: string, maxChars = 2_000): string {
  const normalized = redactSecrets(value)
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
