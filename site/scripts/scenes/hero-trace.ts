/** hero-trace.ts - the landing page's scene: one command through the machine.
 *
 * Every part is a real machine part, framed and zoned by the machine key. Every terminal
 * string comes from the captured hook proof (src/assets/proof/hook-proof.json), whose
 * digest test binds it to the shipped pre-bash.py. The narrowed retry and the merge are
 * marked illustrative. hero-trace.test.ts fails if any of that drifts.
 */
import proof from "../../src/assets/proof/hook-proof.json" with { type: "json" };
import parts from "../machine/machine-data/parts.json" with { type: "json" };
import key from "../machine/machine-data/key.json" with { type: "json" };
import layout from "../machine/machine-data/layout.json" with { type: "json" };
import { noteColumns, wrapMono, type FrameShape, type Scene, type SceneNode, type Tone } from "./scene";

export interface HookProof {
  source: string;
  capturedAt: string;
  fixture: { branch: string; untrackedBefore: string; stagedAfter: string; statusAfter: string; gateEvent: string };
  invocation: { attemptedCommand: string; exitCode: number; stderr: string; commandExecuted: boolean };
}

export interface MachinePartLite {
  kind: string;
  zone: string;
  /** Lane parts carry a command instead of a name. */
  name?: string;
  cmd?: string;
  hooks?: string[];
}

export interface HeroTraceInput {
  proof: HookProof;
  parts: Record<string, MachinePartLite>;
  kindFrames: Record<string, string>;
  zones: Record<string, { name: string }>;
}

export function heroTraceInput(): HeroTraceInput {
  return {
    proof: proof as HookProof,
    parts: parts as unknown as Record<string, MachinePartLite>,
    kindFrames: key.kindFrames as Record<string, string>,
    zones: layout.zones as Record<string, { name: string }>,
  };
}

const basename = (path: string) => path.slice(path.lastIndexOf("/") + 1);

/** Wrap captured text into a note, keeping whole lines and marking any cut with an ellipsis. */
function excerpt(text: string, cols: number, maxLines: number): string[] {
  const lines = wrapMono(text, cols);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  let last = kept[maxLines - 1];
  while (last.length + 2 > cols && last.includes(" ")) last = last.slice(0, last.lastIndexOf(" "));
  kept[maxLines - 1] = `${last} …`;
  return kept;
}

export function buildHeroTrace(input: HeroTraceInput): Scene {
  const { invocation, fixture } = input.proof;
  if (invocation.commandExecuted || invocation.exitCode !== 2) {
    throw new Error("hook proof no longer shows a refused, unexecuted command; review the hero trace");
  }
  const hook = basename(input.proof.source);
  const logPath = /(?:^|\n)\s*M (\S*gate-events\.log)/.exec(fixture.statusAfter)?.[1];
  if (!logPath) throw new Error("hook proof no longer shows the gate-events log being written");
  const retryFile = fixture.untrackedBefore.replace(/^\?\? /, "");

  const node = (id: string, part: string, label: string, sub: string, tone: Tone, wide: [number, number], tall: [number, number]): SceneNode => {
    const machinePart = input.parts[part];
    if (!machinePart) throw new Error(`hero trace names unknown machine part ${part}`);
    return {
      id,
      part,
      label,
      sub,
      zone: input.zones[machinePart.zone]?.name ?? machinePart.zone,
      shape: input.kindFrames[machinePart.kind] as FrameShape,
      tone,
      at: {
        wide: { x: wide[0], y: wide[1], w: 190, h: 64 },
        tall: { x: tall[0], y: tall[1], w: 160, h: 52 },
      },
    };
  };

  const nodes: SceneNode[] = [
    node("you", "operator", "You", "at the console", "brand", [24, 210], [10, 18]),
    node("agent", "agent-loop", "Agent loop", "model and tools", "signal", [290, 210], [190, 110]),
    node("guard", "guard-bash", "Shell gate", hook, "danger", [556, 210], [100, 202]),
    node("log", "audit-ledger", "Audit log", basename(logPath), "record", [556, 390], [10, 294]),
    node("repo", "repo", "Working tree", `branch ${fixture.branch}`, "steel", [822, 210], [190, 294]),
    node("pr", "remote-ci", "Pull request", "exact-head CI", "steel", [1066, 210], [190, 386]),
    node("merge", "approval-key", "Your approval", "merges ask first", "brand", [1066, 390], [100, 478]),
  ];

  const blockWidth = 660;
  const logWidth = 356;

  const scene: Scene = {
    id: "hero-trace",
    title: "One command through the machine",
    summary: `The agent tries to stage everything, the shell gate refuses it with H-03, the refusal is logged in your repository, and the narrowed change ships through a pull request you approve.`,
    size: { wide: { w: 1280, h: 480 }, tall: { w: 360, h: 540 } },
    nodes,
    edges: [
      { id: "e-ask", from: "you", to: "agent", path: { wide: "M214,242 H290", tall: "M90,70 V90 H270 V110" } },
      { id: "e-call", from: "agent", to: "guard", path: { wide: "M480,242 H556", tall: "M270,162 V182 H180 V202" } },
      { id: "e-log", from: "guard", to: "log", path: { wide: "M651,274 V390", tall: "M150,254 V274 H90 V294" } },
      { id: "e-allow", from: "guard", to: "repo", path: { wide: "M746,242 H822", tall: "M210,254 V274 H270 V294" } },
      { id: "e-ship", from: "repo", to: "pr", path: { wide: "M1012,242 H1066", tall: "M270,346 V386" } },
      { id: "e-merge", from: "pr", to: "merge", path: { wide: "M1161,274 V390", tall: "M270,438 V458 H180 V478" } },
    ],
    notes: [
      { id: "n-call", tone: "signal", lines: [`$ ${invocation.attemptedCommand}`], at: { x: 290, y: 122, w: 190 } },
      { id: "n-block", tone: "danger", lines: wrapMono(invocation.stderr, noteColumns(blockWidth)), at: { x: 452, y: 24, w: blockWidth } },
      // The site's words about the capture, drawn outside the captured box.
      { id: "n-exit", kind: "annotation", tone: "danger", lines: [`exit ${invocation.exitCode} · the command never ran`], at: { x: 464, y: 88, w: 420 } },
      { id: "n-log", tone: "record", lines: excerpt(fixture.gateEvent, noteColumns(logWidth), 3), at: { x: 176, y: 384, w: logWidth } },
      { id: "n-retry", tone: "signal", lines: [`$ git add ${retryFile}`], at: { x: 290, y: 300, w: 190 } },
      { id: "n-allow", tone: "positive", lines: ["allowed"], at: { x: 762, y: 146, w: 120 } },
    ],
    steps: [
      {
        id: "ask",
        title: "You ask for an outcome",
        caption: "You describe the change you want. The agent loop turns it into tool calls.",
        reveal: ["you", "agent", "e-ask"],
        focus: "you",
        travel: ["e-ask"],
        verdict: "run",
        illustrative: true,
      },
      {
        id: "call",
        title: "The agent reaches for the shell",
        caption: `The model proposes \`${invocation.attemptedCommand}\`, staging every change at once.`,
        reveal: ["n-call"],
        focus: "agent",
        verdict: "run",
        terminal: `$ ${invocation.attemptedCommand}`,
        // The exact command the capture sent to the hook. No model proposed it there.
        illustrative: true,
      },
      {
        id: "hook",
        title: "The gate runs first",
        caption: `Before the shell runs anything, the host hands the call to codeArbiter's shell gate, \`${hook}\`.`,
        reveal: ["guard", "e-call"],
        focus: "guard",
        travel: ["e-call"],
        verdict: "decide",
        illustrative: true,
      },
      {
        id: "block",
        title: "BLOCKED [H-03]",
        caption: `The gate refuses with exit code ${invocation.exitCode}. The command never runs, so nothing is staged.`,
        reveal: ["n-block", "n-exit"],
        focus: "guard",
        verdict: "block",
        terminal: invocation.stderr,
        captured: true,
        ms: 4200,
      },
      {
        id: "log",
        title: "The refusal is written down",
        caption: `The block is appended to \`${logPath}\`, inside your repository.`,
        reveal: ["log", "e-log", "n-log"],
        focus: "log",
        travel: ["e-log"],
        verdict: "record",
        terminal: fixture.gateEvent,
        captured: true,
        ms: 3800,
      },
      {
        id: "retry",
        title: "The agent narrows the change",
        caption: "Following the message, the agent stages the one file by name. The gate allows it.",
        reveal: ["n-retry", "repo", "e-allow", "n-allow"],
        focus: "guard",
        travel: ["e-call", "e-allow"],
        verdict: "pass",
        terminal: `$ git add ${retryFile}`,
        illustrative: true,
      },
      {
        id: "ship",
        title: "You approve the merge",
        caption: "The change goes through the governed commit and a pull request. Merging stays your decision.",
        reveal: ["pr", "e-ship", "merge", "e-merge"],
        focus: "merge",
        travel: ["e-ship", "e-merge"],
        verdict: "decide",
        illustrative: true,
        ms: 3400,
      },
    ],
    evidence: "",
  };

  const number = (id: string) => scene.steps.findIndex((step) => step.id === id) + 1;
  const captured = scene.steps.filter((step) => step.captured).map((step) => number(step.id));
  const illustrative = scene.steps.filter((step) => step.illustrative).map((step) => number(step.id));
  const list = (items: number[]) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : `${items[0]}`);
  scene.evidence =
    `Steps ${list(captured)} are the real output of the shipped \`${hook}\`, captured on ${input.proof.capturedAt.slice(0, 10)} ` +
    `by sending it the command in step ${number("call")} directly in a disposable test repository. ` +
    `Steps ${list(illustrative)} are illustrative.`;
  return scene;
}
