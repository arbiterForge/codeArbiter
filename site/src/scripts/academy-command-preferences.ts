export type AcademyPreference = {
  os: string | null;
  host: string | null;
};

export type AcademyVariant = {
  os?: string;
  host?: string;
};

export type StorageReader = {
  getItem(key: string): string | null;
};

export function readPreference(storage: StorageReader, key: string, allowed: Set<string>): string | null {
  try {
    const value = storage.getItem(key);
    return value && allowed.has(value) ? value : null;
  } catch {
    return null;
  }
}

export function visibleVariantIndexes(variants: AcademyVariant[], preference: AcademyPreference): number[] {
  const matching = variants.flatMap((variant, index) => (
    (preference.os === null || variant.os === "all" || variant.os === preference.os)
      && (preference.host === null || variant.host === "none" || variant.host === preference.host)
      ? [index]
      : []
  ));
  return matching.length > 0 ? matching : variants.map((_, index) => index);
}

export async function copyCommand(
  command: string,
  writeClipboard: (text: string) => Promise<void>,
  selectFallback: () => void,
): Promise<"copied" | "fallback"> {
  try {
    await writeClipboard(command);
    return "copied";
  } catch {
    selectFallback();
    return "fallback";
  }
}
