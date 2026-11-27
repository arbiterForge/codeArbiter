import { describe, expect, it } from "vitest";
import { buildHeroTrace, heroTraceInput } from "./hero-trace";
import { validateScene } from "./scene";

const input = heroTraceInput();
const scene = buildHeroTrace(input);
const step = (id: string) => scene.steps.find((candidate) => candidate.id === id)!;
const note = (id: string) => scene.notes.find((candidate) => candidate.id === id)!;
const unwrap = (lines: string[]) => lines.join(" ");

describe("hero trace scene", () => {
  it("is a valid scene in both compositions", () => {
    expect(validateScene(scene)).toEqual([]);
  });

  it("draws every node as a real machine part, framed and zoned by the machine's own key", () => {
    for (const node of scene.nodes) {
      const part = input.parts[node.part];
      expect(part, `${node.id} stands for machine part ${node.part}`).toBeDefined();
      expect(node.shape, node.id).toBe(input.kindFrames[part.kind]);
      expect(node.zone, node.id).toBe(input.zones[part.zone].name);
    }
  });

  it("puts the H-03 refusal on the machine part that owns H-03", () => {
    const guard = scene.nodes.find((node) => node.id === "guard")!;
    expect(input.parts[guard.part].hooks).toContain("H-03");
    expect(step("block").title).toBe("BLOCKED [H-03]");
    expect(step("block").focus).toBe("guard");
  });

  it("labels as captured only what the shipped hook printed, exactly as it printed it", () => {
    const { invocation, fixture } = input.proof;
    const captured = scene.steps.filter((candidate) => candidate.captured);
    expect(captured.map((candidate) => candidate.id)).toEqual(["block", "log"]);
    for (const candidate of captured) expect([invocation.stderr, fixture.gateEvent]).toContain(candidate.terminal);
    expect(unwrap(note("n-block").lines)).toBe(invocation.stderr);
    const excerpt = unwrap(note("n-log").lines);
    expect(excerpt.endsWith(" …")).toBe(true);
    expect(fixture.gateEvent.startsWith(excerpt.slice(0, -2))).toBe(true);
  });

  it("binds the illustrative command to the one the capture sent, and labels every step", () => {
    const { invocation } = input.proof;
    expect(step("call").terminal).toBe(`$ ${invocation.attemptedCommand}`);
    expect(unwrap(note("n-call").lines)).toBe(`$ ${invocation.attemptedCommand}`);
    for (const candidate of scene.steps) {
      expect(Boolean(candidate.captured) !== Boolean(candidate.illustrative), candidate.id).toBe(true);
    }
  });

  it("states the refusal's effect only as far as the capture shows it, outside the captured box", () => {
    const { invocation, fixture } = input.proof;
    expect(invocation.exitCode).toBe(2);
    expect(invocation.commandExecuted).toBe(false);
    expect(fixture.stagedAfter).toBe("");
    expect(note("n-exit").kind).toBe("annotation");
    expect(note("n-exit").lines).toEqual(["exit 2 · the command never ran"]);
    expect(note("n-block").kind ?? "terminal").toBe("terminal");
    expect(step("block").caption).toContain("exit code 2");
    expect(fixture.statusAfter).toContain(".codearbiter/gate-events.log");
    expect(step("log").caption).toContain("`.codearbiter/gate-events.log`");
  });

  it("narrows the retry to the fixture's own untracked file", () => {
    const file = input.proof.fixture.untrackedBefore.replace(/^\?\? /, "");
    expect(step("retry").terminal).toBe(`$ git add ${file}`);
  });

  it("accounts for every step in the evidence line", () => {
    const number = (id: string) => scene.steps.findIndex((candidate) => candidate.id === id) + 1;
    expect(scene.evidence).toContain(`Steps ${number("block")} and ${number("log")} are the real output of the shipped \`pre-bash.py\``);
    expect(scene.evidence).toContain(`by sending it the command in step ${number("call")} directly`);
    expect(scene.evidence).toContain("Steps 1, 2, 3, 6 and 7 are illustrative.");
    const mentioned = new Set([...scene.evidence.matchAll(/\d+/g)].map(([n]) => Number(n)).filter((n) => n <= scene.steps.length));
    for (let n = 1; n <= scene.steps.length; n += 1) expect(mentioned.has(n), `step ${n}`).toBe(true);
  });

  it("keeps caveat vocabulary out of the landing's reader layer", () => {
    const text = [scene.summary, scene.evidence, ...scene.steps.flatMap((s) => [s.title, s.caption])].join("\n");
    expect(text).not.toMatch(/\b(?:bounded|receipts?|charters?|does not prove|not proof)\b/i);
    expect(text).not.toMatch(/\s[—–]\s/);
  });
});
