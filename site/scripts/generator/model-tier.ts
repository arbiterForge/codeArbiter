/**
 * Map a raw model id to a display label for the agent reference.
 *
 * - Missing or empty → `"default"`.
 * - Known tiers are capitalized: `sonnet`→`Sonnet`, `opus`→`Opus`, `haiku`→`Haiku`.
 * - Any other value is returned unchanged.
 */
export function modelTier(model?: string): string {
  throw new Error("not implemented");
}
