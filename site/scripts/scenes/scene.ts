/** scene.ts - the model behind the site's step-through scenes.
 *
 * A scene draws machine parts (nodes), the handoffs between them (edges) and terminal notes,
 * then reveals them in ordered steps. One model renders two compositions: a wide one for
 * desktop columns and a tall one for phones, so a narrow screen gets a re-laid diagram
 * instead of a shrunken one. Every step also carries its text (title, caption and any
 * terminal output), which is the complete reading path without JavaScript.
 *
 * Pure data and functions: no Node or DOM dependency, so the build and the tests share it.
 */

export type FrameShape = "circle" | "square" | "shield" | "hex" | "chevron" | "doc" | "rect" | "diamond" | "dashed";
/** Colour meanings from the machine key: gold decides, blue predicts, red refuses, green passes. */
export type Tone = "brand" | "signal" | "danger" | "positive" | "record" | "steel";
/** What happens at a step's focus: work moves, a gate refuses, a gate allows, a person decides, a record is written. */
export type Verdict = "run" | "block" | "pass" | "decide" | "record";
export type Layout = "wide" | "tall";

export interface Box { x: number; y: number; w: number; h: number }
export interface NoteBox { x: number; y: number; w: number }

export interface SceneNode {
  id: string;
  /** The machine part this node stands for (scripts/machine/machine-data/parts.json). */
  part: string;
  label: string;
  /** A short second line, drawn in the wide composition only. */
  sub?: string;
  /** The machine zone's name, drawn above the node in the wide composition. */
  zone: string;
  shape: FrameShape;
  tone: Tone;
  at: Record<Layout, Box>;
}

export interface SceneEdge {
  id: string;
  from: string;
  to: string;
  /** Absolute M, H, V and L commands only, so length is exact at build time. */
  path: Record<Layout, string>;
}

/**
 * Text drawn beside the parts in the wide composition; phones read it in the step text.
 * A terminal note is output and sits in a terminal box; an annotation is the site's own words
 * about that output, drawn as plain text so it is never mistaken for captured output.
 */
export interface SceneNote {
  id: string;
  kind?: "terminal" | "annotation";
  tone: Tone;
  lines: string[];
  at: NoteBox;
}

export interface SceneStep {
  id: string;
  title: string;
  /** One or two sentences; `code` spans render as code. */
  caption: string;
  /** Elements that light up at this step. Everything is revealed exactly once. */
  reveal: string[];
  focus: string;
  /** Edges a token travels along, in order. */
  travel?: string[];
  verdict?: Verdict;
  /** Exact terminal text for the step's reading path. */
  terminal?: string;
  /** The terminal text is real captured output. Every step is captured or illustrative. */
  captured?: boolean;
  /** The step shows what happens but was not captured. */
  illustrative?: boolean;
  /** Dwell time in milliseconds while playing. */
  ms?: number;
}

export interface Scene {
  id: string;
  title: string;
  summary: string;
  size: Record<Layout, { w: number; h: number }>;
  nodes: SceneNode[];
  edges: SceneEdge[];
  notes: SceneNote[];
  steps: SceneStep[];
  /** One line saying what is captured and what is illustrative. */
  evidence: string;
}

/** Type metrics shared by the renderer and the validator (JetBrains Mono advances 0.6em). */
export const METRICS = {
  label: { size: 15, char: 8.25 },
  labelTall: { size: 14, char: 7.7 },
  sub: { size: 12, char: 7.2 },
  note: { size: 13, char: 7.8, line: 18, padX: 12, padY: 11 },
  annotation: { size: 12.5, char: 7.1, line: 16 },
  glyph: 22,
  textInset: 50,
} as const;

export const LAYOUTS: Layout[] = ["wide", "tall"];

/** How many monospace characters fit on one line of a note box. */
export function noteColumns(width: number): number {
  return Math.floor((width - METRICS.note.padX * 2) / METRICS.note.char);
}

export function noteHeight(lines: number, kind: SceneNote["kind"] = "terminal"): number {
  return kind === "annotation" ? lines * METRICS.annotation.line + 4 : lines * METRICS.note.line + METRICS.note.padY * 2;
}

/**
 * The vertices of a path made of absolute straight segments, one run per `M`. Curves and
 * relative commands are refused rather than guessed, so length and bounds stay exact.
 */
export function pathRuns(d: string): { x: number; y: number }[][] {
  const tokens = d.match(/[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?/g) ?? [];
  const runs: { x: number; y: number }[][] = [];
  let x = 0;
  let y = 0;
  let command = "";
  let index = 0;
  const next = () => {
    const value = Number(tokens[index++]);
    if (Number.isNaN(value)) throw new Error(`malformed path: ${d}`);
    return value;
  };
  const visit = () => runs.at(-1)!.push({ x, y });
  while (index < tokens.length) {
    if (/[A-Za-z]/.test(tokens[index])) {
      command = tokens[index++];
      if (!"MLHV".includes(command)) throw new Error(`unsupported path command ${command} in ${d}`);
    }
    if (command === "M") {
      x = next();
      y = next();
      runs.push([]);
      visit();
      command = "L";
    } else if (runs.length === 0) {
      throw new Error(`malformed path: ${d}`);
    } else if (command === "L") {
      x = next();
      y = next();
      visit();
    } else if (command === "H") {
      x = next();
      visit();
    } else if (command === "V") {
      y = next();
      visit();
    } else {
      throw new Error(`malformed path: ${d}`);
    }
  }
  return runs;
}

/** Exact length of a path made of absolute straight segments. */
export function pathLength(d: string): number {
  let total = 0;
  for (const run of pathRuns(d)) {
    for (let i = 1; i < run.length; i += 1) total += Math.hypot(run[i].x - run[i - 1].x, run[i].y - run[i - 1].y);
  }
  return Math.round(total * 100) / 100;
}

/** Wrap monospace text at word boundaries; break a word only when it alone is too long. */
export function wrapMono(text: string, cols: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    const pieces: string[] = [];
    for (let at = 0; at < word.length || pieces.length === 0; at += cols) pieces.push(word.slice(at, at + cols));
    for (const [i, piece] of pieces.entries()) {
      const joined = line === "" ? piece : `${line} ${piece}`;
      if (i === 0 && joined.length <= cols) {
        line = joined;
      } else {
        if (line !== "") lines.push(line);
        line = piece;
      }
    }
  }
  if (line !== "") lines.push(line);
  return lines;
}

/** The step at which each element first lights up. */
export function revealStep(scene: Scene): Map<string, number> {
  const at = new Map<string, number>();
  scene.steps.forEach((step, index) => {
    for (const id of step.reveal) if (!at.has(id)) at.set(id, index);
  });
  return at;
}

const inside = (box: Box, size: { w: number; h: number }) =>
  box.x >= 0 && box.y >= 0 && box.x + box.w <= size.w && box.y + box.h <= size.h;

/** Every rule a scene must satisfy before it is drawn. An empty list means valid. */
export function validateScene(scene: Scene): string[] {
  const findings: string[] = [];
  const nodes = new Map(scene.nodes.map((node) => [node.id, node]));
  const edges = new Map(scene.edges.map((edge) => [edge.id, edge]));
  const ids = [...scene.nodes, ...scene.edges, ...scene.notes].map((element) => element.id);
  const seen = new Set<string>();
  for (const id of ids) {
    if (seen.has(id)) findings.push(`duplicate id ${id}`);
    seen.add(id);
  }

  for (const edge of scene.edges) {
    for (const end of [edge.from, edge.to]) {
      if (!nodes.has(end)) findings.push(`edge ${edge.id} ends at unknown node ${end}`);
    }
    for (const layout of LAYOUTS) {
      try {
        if (pathLength(edge.path[layout]) <= 0) findings.push(`edge ${edge.id} has no length in the ${layout} composition`);
        const size = scene.size[layout];
        const outside = pathRuns(edge.path[layout]).flat().find((p) => p.x < 0 || p.y < 0 || p.x > size.w || p.y > size.h);
        if (outside) findings.push(`edge ${edge.id} leaves the ${layout} composition at (${outside.x}, ${outside.y})`);
      } catch (error) {
        findings.push(`edge ${edge.id}: ${(error as Error).message}`);
      }
    }
  }

  for (const node of scene.nodes) {
    for (const layout of LAYOUTS) {
      const box = node.at[layout];
      if (!inside(box, scene.size[layout])) findings.push(`node ${node.id} leaves the ${layout} composition`);
      const metric = layout === "wide" ? METRICS.label : METRICS.labelTall;
      if (node.label.length * metric.char > box.w - METRICS.textInset - 8) findings.push(`node ${node.id} label does not fit its ${layout} box`);
    }
    if (node.sub && node.sub.length * METRICS.sub.char > node.at.wide.w - METRICS.textInset - 8) findings.push(`node ${node.id} sub-label does not fit its wide box`);
  }

  for (const note of scene.notes) {
    const fits = (line: string) =>
      note.kind === "annotation" ? line.length * METRICS.annotation.char <= note.at.w : line.length <= noteColumns(note.at.w);
    note.lines.forEach((line, index) => {
      if (!fits(line)) findings.push(`note ${note.id} line ${index + 1} is wider than its box`);
    });
    if (!inside({ ...note.at, h: noteHeight(note.lines.length, note.kind) }, scene.size.wide)) findings.push(`note ${note.id} leaves the wide composition`);
  }

  if (scene.steps.length === 0) findings.push("scene has no steps");
  const reveals = new Map<string, number>();
  const stepIds = new Set<string>();
  scene.steps.forEach((step, index) => {
    if (stepIds.has(step.id)) findings.push(`duplicate step ${step.id}`);
    stepIds.add(step.id);
    if (!step.caption.trim()) findings.push(`step ${step.id} has no caption`);
    if (step.title.length > 40) findings.push(`step ${step.id} title is longer than 40 characters`);
    for (const id of step.reveal) {
      if (!seen.has(id)) findings.push(`step ${step.id} reveals unknown element ${id}`);
      else if (reveals.has(id)) findings.push(`${id} is revealed more than once`);
      else reveals.set(id, index);
    }
  });
  for (const id of ids) if (!reveals.has(id)) findings.push(`${id} is never revealed`);

  scene.steps.forEach((step, index) => {
    const shownBy = (id: string) => (reveals.get(id) ?? Infinity) <= index;
    if (!seen.has(step.focus)) findings.push(`step ${step.id} focuses unknown element ${step.focus}`);
    else if (!shownBy(step.focus)) findings.push(`step ${step.id} focuses ${step.focus} before it is revealed`);
    for (const id of step.travel ?? []) {
      const edge = edges.get(id);
      if (!edge) {
        findings.push(`step ${step.id} travels unknown edge ${id}`);
        continue;
      }
      if (!shownBy(id)) findings.push(`step ${step.id} travels ${id} before it is revealed`);
      for (const end of [edge.from, edge.to]) {
        if (nodes.has(end) && !shownBy(end)) findings.push(`step ${step.id} travels ${id} before its end ${end} is revealed`);
      }
    }
    if (step.captured && step.illustrative) findings.push(`step ${step.id} cannot be both captured and illustrative`);
    if (!step.captured && !step.illustrative) findings.push(`step ${step.id} is labelled neither captured nor illustrative`);
    if (step.captured && !step.terminal) findings.push(`step ${step.id} is captured but shows no terminal text`);
  });

  return findings;
}
