// The Guard lab and the example session print the hooks' own messages: each key names one block() call
// site by gate, file and the start of its message, and the text comes from the model built from the hook
// sources. scripts/machine/machine-viewer.test.ts checks that every key matches exactly one call site.
import { GATES } from './content.js';

export const MESSAGE_SITES = {
  'H-01c': ['H-01', '_bashguardlib.py', 'Direct commit to'],
  'H-01p': ['H-01', '_bashguardlib.py', 'Pushing to a protected branch'],
  'H-01a': ['H-01', '_bashguardlib.py', "'git push --all'"],
  'H-01b': ['H-01', '_bashguardlib.py', 'Bare `git push`'],
  'H-02': ['H-02', '_bashguardlib.py', 'Force-push is prohibited'],
  'H-03a': ['H-03', '_bashguardlib.py', "'git add -A'"],
  'H-03b': ['H-03', '_bashguardlib.py', 'Wildcard staging is prohibited'],
  'H-05': ['H-05', '_bashguardlib.py', 'The .codearbiter audit logs'],
  'H-10b': ['H-10b', '_bashguardlib.py', 'No security-gate PASS is recorded'],
  'H-11': ['H-11', '_bashguardlib.py', 'ADR files under'],
  'H-11w': ['H-11', 'pre-write.py', 'ADR files are authored only via /adr'],
  'H-14': ['H-14', '_bashguardlib.py', 'The migration PASS is missing'],
  'H-18': ['H-18', '_bashguardlib.py', '.codearbiter/CONTEXT.md is the activation switch'],
  'H-20c': ['H-20', '_bashguardlib.py', "'--no-verify' / '-n' on git commit"],
  'H-20p': ['H-20', '_bashguardlib.py', "'--no-verify' on git push"],
  'G-01c': ['H-01', 'git-enforce.py', 'Direct commit to'],
  'G-01p': ['H-01', 'git-enforce.py', 'Pushing to a protected branch'],
  'G-02': ['H-02', 'git-enforce.py', 'Force-push'],
};

/** Every call site a key could mean; exactly one is expected. */
export function sitesFor(key, gates = GATES) {
  const [tag, file, start] = MESSAGE_SITES[key] ?? [];
  return (gates[tag]?.sites ?? []).filter((site) => site.file === file && site.message.startsWith(start));
}

/** The hook's message for a key, with its run-time value filled in. A message the hook continues
 *  with run-time details (the extractor keeps only its literal start) ends with an ellipsis. */
export function messageFor(key, value = '', gates = GATES) {
  const site = sitesFor(key, gates)[0];
  if (!site) return '';
  const filled = site.message.replace(/\{[^}]+\}/g, () => value);
  return /\s$/.test(site.message) ? `${filled.trim()} …` : filled;
}

/** MSG['H-02']() style access, as the lab and the story call it. */
export const MSG = new Proxy({}, { get: (_target, key) => (value) => messageFor(String(key), value) });
