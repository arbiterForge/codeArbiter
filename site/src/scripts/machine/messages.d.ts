/** Typed boundary for messages.js: the hook messages the Guard lab and example session print. */
import type { GateSite } from "../../../scripts/machine/machine-model";

type Gates = Record<string, { kind: "block" | "remind"; sites: GateSite[] }>;

/** Each key names one block() call site: [gate, hook file, start of the message]. */
export const MESSAGE_SITES: Record<string, [tag: string, file: string, start: string]>;
export function sitesFor(key: string, gates?: Gates): GateSite[];
export function messageFor(key: string, value?: string, gates?: Gates): string;
export const MSG: Record<string, (value?: string) => string>;
