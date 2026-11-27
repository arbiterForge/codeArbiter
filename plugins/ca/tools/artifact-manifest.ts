/** The same versioned manifest declaration consumed by the installed Python bridge. */
import contract from '../../../core/artifact-release-manifest.json';

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function keys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
}
const digest = (value: unknown) => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

export function validateArtifactReleaseManifest(value: unknown): Record<string, unknown> {
  if (!object(value) || !contract.required.every(key => Object.hasOwn(value,key)) ||
      Object.keys(value).some(key => ![...contract.required,...contract.optional].includes(key)))
    throw new Error('artifact release manifest has an unexpected shape');
  if (value.format !== contract.format || value.protocol !== contract.protocol || value.schema_version !== contract.schema_version || (typeof value.version !== 'string' || !value.version.trim()))
    throw new Error('artifact release manifest identity is unsupported');
  if (!object(value.binaries) || Object.keys(value.binaries).length === 0 || Object.keys(value.binaries).some(key => !contract.platforms.includes(key)))
    throw new Error('artifact release manifest platform map is invalid');
  const binaries = value.binaries;
  for (const [platform, entry] of Object.entries(binaries)) {
    if (!object(entry) || !keys(entry, contract.binary_fields) || typeof entry.native_tested !== 'boolean' || !digest(entry.sha256) ||
        entry.file !== 'ca-artifact-' + platform.replace('/','-') + (platform.startsWith('windows/') ? '.exe' : ''))
      throw new Error('artifact release manifest binary entry is invalid');
  }
  if (!Object.hasOwn(value, 'context_qualification')) return value;
  const context = value.context_qualification;
  if (!object(context) || Object.keys(context).some(platform => !Object.hasOwn(binaries,platform)))
    throw new Error('artifact context qualification platform map is invalid');
  for (const [platform, entry] of Object.entries(context)) {
    if (!object(entry) || !keys(entry,contract.context_fields) || typeof entry.source_commit !== 'string' || !/^[0-9a-f]{40}$/.test(entry.source_commit) ||
        entry.workflow !== contract.workflow || typeof entry.run_id !== 'string' || !/^[1-9][0-9]*$/.test(entry.run_id) ||
        !digest(entry.binary_sha256) || !digest(entry.observation_sha256) || !digest(entry.module_sha256) ||
        entry.binary_sha256 !== (binaries[platform] as Record<string,unknown>).sha256 || (binaries[platform] as Record<string,unknown>).native_tested !== true ||
        JSON.stringify(entry.native_cases) !== JSON.stringify(contract.native_cases))
      throw new Error('artifact context qualification binding is invalid');
  }
  return value;
}

export function parseArtifactReleaseManifest(text: string): Record<string, unknown> {
  if (Buffer.byteLength(text, 'utf8') > 65536) throw new Error('native manifest exceeds bounded input');
  const value: unknown = JSON.parse(text);
  const tokens = text.match(/"(?:\\[\s\S]|[^"\\])*"|[{}\[\]:,]|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null/g) ?? [];
  const stack: Array<Set<string> | null> = [];
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i] === '{') stack.push(new Set());
    else if (tokens[i] === '[') stack.push(null);
    else if (tokens[i] === '}' || tokens[i] === ']') stack.pop();
    else if (tokens[i + 1] === ':' && tokens[i].startsWith('"')) {
      const key = JSON.parse(tokens[i]) as string; const seen = stack.at(-1);
      if (seen?.has(key)) throw new Error('duplicate native manifest key');
      seen?.add(key);
    }
  }
  return validateArtifactReleaseManifest(value);
}
