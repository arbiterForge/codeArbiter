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

  it("shows the captured command, refusal and log line exactly as the shipped hook produced them", () => {
    const { invocation, fixture } = input.proof;
    expect(step("call").terminal).toBe(`$ ${invocation.attemptedCommand}`);
    expect(unwrap(note("n-call").lines)).toBe(`$ ${invocation.attemptedCommand}`);
    expect(step("block").terminal).toBe(invocation.stderr);
    expect(unwrap(note("n-block").lines.slice(0, -1))).toBe(invocation.stderr);
    expect(step("log").terminal).toBe(fixture.gateEvent);
    const excerpt = unwrap(note("n-log").lines);
    expect(excerpt.endsWith(" …")).toBe(true);
    expect(fixture.gateEvent.startsWith(excerpt.slice(0, -2))).toBe(true);
    for (const id of ["call", "block", "log"]) expect(step(id).captured, id).toBe(true);
  });

  it("states the refusal's effect only as far as the capture shows it", () => {
    const { invocation, fixture } = input.proof;
    expect(invocation.exitCode).toBe(2);
    expect(invocation.commandExecuted).toBe(false);
    expect(fixture.stagedAfter).toBe("");
    expect(note("n-block").lines.at(-1)).toBe("exit 2 · the command never ran");
    expect(step("block").caption).toContain("exit code 2");
    expect(fixture.statusAfter).toContain(".codearbiter/gate-events.log");
    expect(step("log").caption).toContain("`.codearbiter/gate-events.log`");
  });

  it("narrows the retry to the fixture's own untracked file and labels what was not captured", () => {
    const file = input.proof.fixture.untrackedBefore.replace(/^\?\? /, "");
    expect(step("retry").terminal).toBe(`$ git add ${file}`);
    for (const id of ["retry", "ship"]) {
      expect(step(id).illustrative, id).toBe(true);
      expect(step(id).captured, id).toBeFalsy();
    }
    const number = (id: string) => scene.steps.findIndex((candidate) => candidate.id === id) + 1;
    expect(scene.evidence).toContain(`steps ${number("call")}, ${number("block")} and ${number("log")}`);
    expect(scene.evidence).toContain(`Steps ${number("retry")} and ${number("ship")} are illustrative`);
  });

  it("keeps caveat vocabulary out of the landing's reader layer", () => {
    const text = [scene.summary, scene.evidence, ...scene.steps.flatMap((s) => [s.title, s.caption])].join("\n");
    expect(text).not.toMatch(/\b(?:bounded|receipts?|charters?|does not prove|not proof)\b/i);
    expect(text).not.toMatch(/\s[—–]\s/);
  });
});
