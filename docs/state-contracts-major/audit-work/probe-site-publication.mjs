// Bounded pure-function probe. No Git/network/publication activity occurs.
// Node's built-in TypeScript transformer loads the actual source. The unused
// TypeScript AST dependency is replaced with a throwing stub: this probe calls
// only selectCurrentGovernanceReleases, not parsePublishedPiSupport.
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
const path = new URL('../codeArbiter/site/scripts/release-applicability.ts', import.meta.url);
const raw = readFileSync(path, 'utf8');
const source = raw.replace('import ts from "typescript";', 'const ts = new Proxy({}, { get() { throw new Error("unused AST dependency reached"); } });');
const code = stripTypeScriptTypes(source, { mode: 'transform' });
const { selectCurrentGovernanceReleases } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const declarations = readFileSync(new URL('../codeArbiter/.codearbiter/release-targets.md', import.meta.url), 'utf8');
const ledger = JSON.stringify({ $comment: [], namespaces: ['v*', 'ca-sandbox-v*', 'ca-codex-v*', 'ca-pi-v*'], verified_at: '2026-11-09', tags: {} });
const tags = [{tag:'v999.0.0',commit:'a'.repeat(40)}, {tag:'ca-codex-v999.0.0',commit:'b'.repeat(40)}, {tag:'ca-pi-v999.0.0',commit:'c'.repeat(40)}];
const selected = selectCurrentGovernanceReleases(declarations, ledger, tags);
console.log(JSON.stringify({ commit: 'fd7eb34b2da439551443d09526ab48fd1d1bb9bf', runtime: process.version,
 fixture: 'Synthetic stable tags; no original publication receipts and no GitHub Release-status input',
 selected, external_operations: 0, boundary: 'Proves tag-only selection behavior, not that any actual production tag is unpublished.' },null,2));
