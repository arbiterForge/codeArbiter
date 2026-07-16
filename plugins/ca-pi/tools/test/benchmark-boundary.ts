/** Production Pi TypeScript adapter boundary used by the relative benchmark. */
import { performance } from "node:perf_hooks";

import { wrapBuiltins } from "../src/tool-guard.ts";
import type {
  BridgePort,
  BuiltinToolFactories,
  ToolDefinitionPort,
  ToolGuardPiPort,
} from "../src/contracts.ts";

const samples = Number(process.argv[2]);
if (!Number.isInteger(samples) || samples !== 100) throw new Error("benchmark requires 100 samples");

const definitions = new Map<string, ToolDefinitionPort>();
let bridgeCallCount = 0;
let nativeCallCount = 0;
const pi: ToolGuardPiPort = {
  on: () => undefined,
  registerTool: (tool) => { definitions.set(tool.name, tool); },
  getActiveTools: () => [...definitions.keys()],
  getAllTools: () => [...definitions.values()].map((tool) => ({
    name: tool.name,
    sourceInfo: { path: import.meta.filename },
  })),
};
const create = (name: string) => () => ({
  name,
  execute: async () => {
    nativeCallCount += 1;
    return { content: [{ type: "text", text: "fixture" }], isError: false };
  },
});
const factories: BuiltinToolFactories = {
  bash: create("bash"),
  edit: create("edit"),
  read: create("read"),
  write: create("write"),
};
const bridge: BridgePort = {
  call: async () => {
    bridgeCallCount += 1;
    return { version: 1, outcome: "allow" };
  },
};
const startup = performance.now();
wrapBuiltins(pi, bridge, {
  cwd: process.cwd(),
  descriptor: { bash: "EXEC", edit: "EDIT", read: "READ", write: "WRITE" },
  factories,
  wrapperSourcePath: import.meta.filename,
});
const registrationMs = performance.now() - startup;
process.stdout.write(JSON.stringify({ phase: "ready", wrapperCount: definitions.size, registrationMs }) + "\n");
const corpus: ReadonlyArray<readonly [string, Record<string, unknown>]> = [
  ["read", { path: "fixture π.txt" }],
  ["bash", { command: "git status --short" }],
  ["write", { path: "generated/fixture.txt", content: "fixture\n" }],
];
const timings: number[] = [];
for (let index = 0; index < samples + 5; index += 1) {
  const [name, input] = corpus[index % corpus.length]!;
  const begin = performance.now();
  await definitions.get(name)!.execute(`benchmark-${index}`, input);
  const elapsed = performance.now() - begin;
  if (index >= 5) timings.push(elapsed);
}
process.stdout.write(JSON.stringify({
  phase: "complete",
  timings,
  bridgeCallCount,
  nativeCallCount,
}) + "\n");
