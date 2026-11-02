/** label.ts - the one label every rendering of a capture carries.
 *
 * It is the tool's repository path and the first 12 hex characters of the entry
 * script's sha256: the hash is what identifies the source that produced the
 * output. It carries no version number (the site has a version-drift gate).
 * Kept free of file access so the Astro component can import it into a bundle.
 */

export interface LabelledCapture {
  id: string;
  tool: string;
  sources: ReadonlyArray<{ path: string; sha256: string }>;
}

/** First 12 hex characters of the entry script's recorded sha256. */
export function entryHash12(capture: LabelledCapture): string {
  const entry = capture.sources.find((source) => source.path === capture.tool);
  if (!entry) throw new Error(`Capture "${capture.id}" does not hash its entry script ${capture.tool}`);
  return entry.sha256.slice(0, 12);
}

/** The frame title: where the output came from and which bytes of the entry script produced it. */
export function capturedRunLabel(capture: LabelledCapture): string {
  return `Captured output of ${capture.tool} (sha256 ${entryHash12(capture)})`;
}
