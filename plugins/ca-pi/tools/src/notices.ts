import { createHash } from "node:crypto";

import type { BridgeResponse } from "./contracts.ts";
import { redactSecrets } from "./redaction.ts";

const MAX_NOTICE_BYTES = 16_000;
const TRUNCATED = "\n[codeArbiter notice truncated]";

interface OwnedNoticeIdentity {
  kind: "codearbiter-notice";
  version: 1;
  id: string;
}

interface OwnedNoticeBlock {
  type: "text";
  text: string;
  codearbiter: OwnedNoticeIdentity;
}

export interface ToolResultPatch {
  content: unknown[];
}

function normalized(value: string): string {
  return redactSecrets(value)
    .replace(/\r\n?/gu, "\n")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "�")
    .trim();
}

function identity(ruleId: string | undefined, value: string): string {
  const normalizedRule = normalized(ruleId ?? "context");
  return createHash("sha256").update(`${normalizedRule}\0${value}`, "utf8").digest("hex");
}

function owned(block: unknown, id: string): boolean {
  if (block === null || typeof block !== "object" || Array.isArray(block)) return false;
  const value = block as Partial<OwnedNoticeBlock>;
  return value.type === "text"
    && value.codearbiter?.kind === "codearbiter-notice"
    && value.codearbiter.version === 1
    && value.codearbiter.id === id
    && typeof value.text === "string"
    && value.text.includes(`:${id} -->`);
}

function truncateBody(prefix: string, body: string): string {
  if (Buffer.byteLength(prefix + body, "utf8") <= MAX_NOTICE_BYTES) return prefix + body;
  const budget = MAX_NOTICE_BYTES - Buffer.byteLength(prefix + TRUNCATED, "utf8");
  let kept = "";
  let used = 0;
  for (const character of body) {
    const size = Buffer.byteLength(character, "utf8");
    if (used + size > budget) break;
    kept += character;
    used += size;
  }
  return prefix + kept + TRUNCATED;
}

export function applyToolResultNotice(
  event: { content?: unknown },
  response: BridgeResponse,
): ToolResultPatch | undefined {
  if (response.outcome !== "notice" && response.outcome !== "warn") return undefined;
  const raw = response.message ?? response.context;
  if (typeof raw !== "string" || raw.length === 0) return undefined;
  const body = normalized(raw);
  if (body.length === 0) return undefined;
  const id = identity(response.ruleId, body);
  const original = Array.isArray(event.content) ? event.content : [];
  if (original.some((block) => owned(block, id))) return undefined;
  const prefix = `<!-- codearbiter:pi-tool-result:${id} -->\n`;
  const block: OwnedNoticeBlock = {
    type: "text",
    text: truncateBody(prefix, body),
    codearbiter: { kind: "codearbiter-notice", version: 1, id },
  };
  return { content: [...original, block] };
}
