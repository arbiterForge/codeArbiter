import type { ExtensionContextPort } from "./contracts.ts";

export function setArbiterStatus(
  context: Pick<ExtensionContextPort, "ui">,
  text: string | undefined,
): void {
  context.ui.setStatus("codearbiter", text);
}
