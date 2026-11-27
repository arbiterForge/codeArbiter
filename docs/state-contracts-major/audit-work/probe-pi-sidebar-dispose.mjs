// Read-only in-memory lifecycle probe; no host terminal or filesystem mutation.
import { createSidebarManager } from '../codeArbiter/plugins/ca-pi/tools/src/sidebar-manager.ts';
let resolveMetrics;
const metrics = new Promise(resolve => { resolveMetrics = resolve; });
const nativeRender = () => {};
const terminal = { columns: 140, rows: 40 };
const tui = { doRender: nativeRender, requestRender() {} };
const context = { mode: 'tui', hasUI: true, isProjectTrusted: () => true,
  ui: { notify() {} } };
const manager = createSidebarManager({ pi: { registerCommand() {} },
  currentTui: () => tui, terminal: () => terminal,
  loadMetrics: () => metrics, dataSource: () => ({}), writeOut() {}, noColor: () => true });
manager.register(context);
const pending = manager.autoInstall(context);
manager.dispose();
const disposed = { health: manager.health(), columns: terminal.columns, nativeRender: tui.doRender === nativeRender };
resolveMetrics({ visibleWidth: text => text.length, truncateToWidth: (text, width) => text.slice(0, width) });
await pending;
const afterPendingCompletes = { health: manager.health(), columns: terminal.columns, nativeRender: tui.doRender === nativeRender };
manager.dispose();
console.log(JSON.stringify({ commit: 'fd7eb34b2da439551443d09526ab48fd1d1bb9bf', runtime: process.version,
  disposed, afterPendingCompletes, finalColumns: terminal.columns }, null, 2));
