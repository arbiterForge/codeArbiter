/**
 * Map a raw model id to a display label for the agent reference.
 *
 * - Missing or empty → `"default"`.
 * - Known tiers are capitalized: `sonnet`→`Sonnet`, `opus`→`Opus`, `haiku`→`Haiku`.
 * - Any other value is returned unchanged.
 */

const KNOWN_TIERS: Record<string, string> = {
  sonnet: 'Sonnet',
  opus: 'Opus',
  haiku: 'Haiku',
};

export function modelTier(model?: string): string {
  if (model == null || model === '') {
    return 'default';
  }
  const normalized = model.toLowerCase();
  const tier = KNOWN_TIERS[normalized];
  return tier ?? model;
}
