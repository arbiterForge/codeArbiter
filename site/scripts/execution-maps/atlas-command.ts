import { commandDescription, ID } from './atlas-model';
/** Resolve the canonical command form, not an installed host's generated copy.
 * The read callback must check each file against the reviewed source revision.
 * Only the whole-file SKILL_ENTRY form is a delegation; no recursive templating.
 */
export function commandMetadata(id: string, readReviewed: (path: string) => string): {description:string; path:string} {
  if (!ID.test(id)) throw new Error(`Invalid atlas entry: ${id}`);
  let path = `core/surface/commands/${id}.md`;
  let raw = readReviewed(path).replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  const entry = /^\s*\{\{SKILL_ENTRY:([a-z][a-z0-9-]*)\}\}\s*$/.exec(raw);
  if (entry) {
    path = `core/surface/skills/${entry[1]}/SKILL.md`;
    raw = readReviewed(path).replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  }
  try { return {description:commandDescription(raw), path}; }
  catch (error) { throw new Error(`Atlas description for /${id} at ${path}: ${error instanceof Error ? error.message : String(error)}`); }
}
