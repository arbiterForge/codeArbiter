// Read-only source behavior probe. No native tool, network, or persistent action executes.
// Run with: node --experimental-transform-types audit-work/probe-pi-child-mutation.mjs
import { installChild } from '../codeArbiter/plugins/ca-pi/tools/src/child-extension.ts';
class FakePi {
  handlers = new Map(); commands = new Map(); definitions = new Map();
  registerCommand(name, options) { this.commands.set(name, options.handler); }
  registerTool(tool) { this.definitions.set(tool.name, tool); }
  on(name, handler) { this.handlers.set(name, [...(this.handlers.get(name) || []), handler]); }
  getActiveTools() { return ['read', 'bash', 'edit', 'write']; }
  getAllTools() { return [...this.definitions.keys()].map(name => ({ name, sourceInfo: { path: '/fixture/child.js' } })); }
  async emit(name, event, context) { for (const handler of this.handlers.get(name) || []) await handler(event, context); }
}
const pi = new FakePi(), executions = [];
const context = { cwd: '/fixture/repo', mode: 'rpc', hasUI: true,
  model: { provider: 'openai', id: 'gpt-test' }, isProjectTrusted: () => false,
  ui: { confirm: async () => true, notify() {}, setStatus() {} } };
installChild(pi, { marker: '1', expectedNonce: '0123456789abcdef0123456789abcdef',
  cwd: context.cwd, wrapperSourcePath: '/fixture/child.js',
  bridge: { call: async () => ({ version: 1, outcome: 'allow' }) },
  factories: Object.fromEntries(pi.getActiveTools().map(name => [name, () => ({ name,
    execute: async () => { executions.push(name); return { content: [] }; } })])) });
await pi.emit('session_start', {}, context);
await pi.commands.get('codearbiter-internal-child-handshake')(
  '0123456789abcdef0123456789abcdef fedcba9876543210fedcba9876543210', context);
const results = [];
for (const [tool, params] of [
  ['read', { path: 'src/a.ts' }],
  ['write', { path: 'src/a.ts', content: 'x' }],
  ['edit', { path: 'src/a.ts', oldText: 'x', newText: 'y' }],
  ['bash', { command: 'node --test' }],
]) {
  try { results.push({ tool, result: await pi.definitions.get(tool).execute('id-' + tool, params, undefined, undefined, context) }); }
  catch (error) { results.push({ tool, error: error.message }); }
}
console.log(JSON.stringify({ commit: 'fd7eb34b2da439551443d09526ab48fd1d1bb9bf', runtime: process.version, results, executions }, null, 2));
