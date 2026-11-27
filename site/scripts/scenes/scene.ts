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

/** Terminal output drawn beside the parts in the wide composition. Phones read it in the step text. */
export interface SceneNote {
  id: string;
  tone: Tone;
  lines: string[];
  at: NoteBox;
}

export interface SceneStep {
  id: string;
  title: string;
  /** One or two sentences; `code` spans and H-xx gate IDs are rendered as such. */
  caption: string;
  /** Elements that light up at this step. Everything is revealed exactly once. */
  reveal: string[];
  focus: string;
  /** Edges a token travels along, in order. */
  travel?: string[];
  verdict?: Verdict;
  /** Exact terminal text for the step's reading path. */
  terminal?: string;
  /** The terminal text is real captured output. */
  captured?: boolean;
  /** The step shows what happens next but was not captured. */
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
  glyph: 22,
  textInset: 50,
} as const;

export const LAYOUTS: Layout[] = ["wide", "tall"];

/** How many monospace characters fit on one line of a note box. */
export function noteColumns(width: number): number {
  return Math.floor((width - METRICS.note.padX * 2) / METRICS.note.char);
}

export function noteHeight(lines: number): number {
  return lines * METRICS.note.line + METRICS.note.padY * 2;
}

/** Exact length of a path made of absolute straight segments. */
export function pathLength(d: string): number {
  const tokens = d.match(/[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?/g) ?? [];
  let x = 0;
  let y = 0;
  let total = 0;
  let command = "";
  let index = 0;
  const next = () => {
    const value = Number(tokens[index++]);
    if (Number.isNaN(value)) throw new Error(`malformed path: ${d}`);
    return value;
  };
  while (index < tokens.length) {
    if (/[A-Za-z]/.test(tokens[index])) {
      command = tokens[index++];
      if (!"MLHV".includes(command)) throw new Error(`unsupported path command ${command} in ${d}`);
    }
    if (command === "M") {
      x = next();
      y = next();
      command = "L";
    } else if (command === "L") {
      const nx = next();
      const ny = next();
      total += Math.hypot(nx - x, ny - y);
      x = nx;
      y = ny;
    } else if (command === "H") {
      const nx = next();
      total += Math.abs(nx - x);
      x = nx;
    } else if (command === "V") {
      const ny = next();
      total += Math.abs(ny - y);
      y = ny;
    } else {
      throw new Error(`malformed path: ${d}`);
    }
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
    const cols = noteColumns(note.at.w);
    note.lines.forEach((line, index) => {
      if (line.length > cols) findings.push(`note ${note.id} line ${index + 1} is wider than its box`);
    });
    if (!inside({ ...note.at, h: noteHeight(note.lines.length) }, scene.size.wide)) findings.push(`note ${note.id} leaves the wide composition`);
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
    if (step.captured && !step.terminal) findings.push(`step ${step.id} is captured but shows no terminal text`);
  });

  return findings;
}
