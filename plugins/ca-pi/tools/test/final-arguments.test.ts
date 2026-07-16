import { describe, expect, test } from "vitest";
import { guardUnknownTools, wrapBuiltins } from "../src/tool-guard.ts";
import type { BridgeRequest, BridgeResponse, ToolCategory } from "../src/contracts.ts";

type Handler = (event: Record<string, unknown>) => unknown;
type Definition = {
  name: string;
  execute: (
    id: string,
    params: Record<string, unknown>,
    signal?: AbortSignal,
    update?: unknown,
    context?: unknown,
  ) => Promise<Record<string, unknown>>;
};

const WRAPPER = "C:/package/extensions/codearbiter.js";
const descriptor: Readonly<Record<string, ToolCategory>> = {
  bash: "EXEC",
  write: "WRITE",
  edit: "EDIT",
  read: "READ",
  codearbiter_farm_preview: "EXEC",
};

class OrderedPi {
  readonly handlers: Handler[] = [];
  readonly definitions = new Map<string, Definition>();
  readonly sources = new Map<string, string>();
  readonly active = new Set<string>();

  on(event: string, handler: Handler): void {
    if (event === "tool_call") this.handlers.push(handler);
  }

  registerTool(definition: Definition): void {
    this.definitions.set(definition.name, definition);
    this.sources.set(definition.name, WRAPPER);
    this.active.add(definition.name);
  }

  getActiveTools(): string[] { return [...this.active]; }

  getAllTools(): Array<{ name: string; sourceInfo: { path: string } }> {
    return [...this.sources].map(([name, path]) => ({ name, sourceInfo: { path } }));
  }

  async beforeExecution(event: Record<string, unknown>): Promise<unknown> {
    let result: unknown;
    for (const handler of this.handlers) {
      const candidate = await handler(event);
      if (candidate !== undefined) result = candidate;
      if ((candidate as { block?: boolean } | undefined)?.block === true) return candidate;
    }
    return result;
  }
}

function factories(executions: Array<{ name: string; input: Record<string, unknown> }>) {
  const factory = (name: string) => () => ({
    name,
    execute: async (_id: string, input: Record<string, unknown>) => {
      executions.push({ name, input: structuredClone(input) });
      return { content: [{ type: "text", text: "executed" }] };
    },
  });
  return { bash: factory("bash"), write: factory("write"), edit: factory("edit"), read: factory("read") };
}

describe("live-order final-argument promotion proof", () => {
  test("a later extension mutation is re-judged inside the final executor", async () => {
    const pi = new OrderedPi();
    const requests: BridgeRequest[] = [];
    const executions: Array<{ name: string; input: Record<string, unknown> }> = [];
    const bridge = {
      call: async (request: BridgeRequest): Promise<BridgeResponse> => {
        requests.push(request);
        return (request.input as Record<string, unknown>).command === "git commit --no-verify"
          ? { version: 1, outcome: "block", ruleId: "H-20", message: "blocked by H-20" }
          : { version: 1, outcome: "allow" };
      },
    };
    guardUnknownTools(pi as never, descriptor, WRAPPER);
    wrapBuiltins(pi as never, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories(executions),
      wrapperSourcePath: WRAPPER,
    });
    // Pi 0.80.5/0.80.6 run tool_call handlers in extension order over one input
    // object, then pass the resulting object to the registered tool executor.
    pi.on("tool_call", (event) => {
      (event.input as Record<string, unknown>).command = "git commit --no-verify";
    });
    const event = { toolName: "bash", input: { command: "git status" } };

    await expect(pi.beforeExecution(event)).resolves.toBeUndefined();
    await expect(pi.definitions.get("bash")!.execute("call-final", event.input)).rejects.toThrow("H-20");
    expect(requests.at(-1)?.input).toEqual({ command: "git commit --no-verify" });
    expect(executions).toEqual([]);
  });

  test("a later extension cannot replace a governed built-in owner", async () => {
    const pi = new OrderedPi();
    guardUnknownTools(pi as never, descriptor, WRAPPER);
    pi.active.add("bash");
    pi.sources.set("bash", "C:/foreign/later-extension.js");

    const result = await pi.beforeExecution({ toolName: "bash", input: { command: "git status" } });

    expect(result).toMatchObject({ block: true, reason: expect.stringContaining("source drift") });
  });

  test("farm preview remains parent-extension owned", async () => {
    const pi = new OrderedPi();
    guardUnknownTools(pi as never, descriptor, WRAPPER);
    pi.active.add("codearbiter_farm_preview");
    pi.sources.set("codearbiter_farm_preview", "C:/foreign/farm-replacement.js");

    const result = await pi.beforeExecution({ toolName: "codearbiter_farm_preview", input: {} });

    expect(result).toMatchObject({ block: true, reason: expect.stringContaining("source drift") });
  });
});
