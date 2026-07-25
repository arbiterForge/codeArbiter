/**
 * session-identity.ts - the shared Pi session identity and interactive-parent predicates.
 *
 * Every native Pi command surface answers the same two questions before it will act: is this
 * context a trusted interactive parent TUI, and which session is it? Both answers - and the
 * control-character bound applied to session-facing text - live here so a new mode or job
 * surface cannot quietly adopt a weaker variant.
 */
import type { ExtensionContextPort } from "./contracts.ts";

/** Control, bidi, and zero-width characters refused in session-facing command text. */
export const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u;

/** A trusted, interactive parent TUI context - the only context a native command surface serves. */
export function interactiveParent(context: ExtensionContextPort): boolean {
  try {
    return context.mode === "tui" && context.hasUI === true && context.isProjectTrusted?.() === true;
  } catch {
    return false;
  }
}

/** The bounded, control-free identifier of the context's session, or undefined when unusable. */
export function sessionId(context: ExtensionContextPort): string | undefined {
  try {
    const value = context.sessionManager?.getSessionId?.();
    return typeof value === "string" && value.length > 0 && value.length <= 256 && !CONTROL_CHARACTERS.test(value)
      ? value
      : undefined;
  } catch {
    return undefined;
  }
}
