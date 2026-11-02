/** render.ts - show a capture in a plain Markdown guide.
 *
 * Two routes show a capture, and both take their label from label.ts:
 *  - an `.mdx` guide uses <CapturedRun id="..." /> (src/components/CapturedRun.astro);
 *  - a `.md` guide cannot host a component, so it writes an empty fenced block
 *    whose info string carries `capture="<id>"`, and remarkCapturedRun() fills
 *    it from the capture at build time, the way remarkVersionFacts() resolves
 *    its tokens. The page's file name and URL do not change.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CaptureRecord } from "./harness";
import { capturedRunLabel } from "./label";

const ID = /^[a-z0-9][a-z0-9-]*$/;
/** `capture="<id>"` in a fence's info string, as a whole word. */
const FENCE_MARKER = /(?:^|\s)capture="([^"\s]*)"(?=\s|$)/;

/** Valid capture ids are lowercase words joined by hyphens, so a guide can never name a path. */
export function isCaptureId(id: string): boolean {
  return ID.test(id);
}

/** Read a capture by id from `capturesDir`. */
export function readCapture(id: string, capturesDir: string): CaptureRecord {
  if (!isCaptureId(id)) throw new Error(`Invalid capture id: ${JSON.stringify(id)}`);
  let record: CaptureRecord;
  try {
    record = JSON.parse(readFileSync(join(capturesDir, `${id}.json`), "utf8")) as CaptureRecord;
  } catch (error) {
    throw new Error(`Capture "${id}" could not be read from ${capturesDir}: ${(error as Error).message}. Run \`npm run capture\`.`);
  }
  if (record.id !== id) throw new Error(`Capture file for "${id}" declares id ${JSON.stringify(record.id)}`);
  return record;
}

interface MarkdownNode {
  type: string;
  lang?: string | null;
  meta?: string | null;
  value?: string;
  children?: MarkdownNode[];
}

/** The id named by a fence's `capture="..."` marker, or undefined for an ordinary block. */
export function captureMarker(meta: string | null | undefined): string | undefined {
  return meta ? FENCE_MARKER.exec(meta)?.[1] : undefined;
}

/**
 * Remark plugin: fill an empty ```text capture="<id>"``` fence from the capture.
 * A marker with a missing capture, or with hand-written text inside the fence,
 * fails the build: the point is that no such example in a guide is typed by hand.
 */
export function remarkCapturedRun(options: { capturesDir: string }) {
  return () => (tree: MarkdownNode, file?: { path?: string }) => {
    const where = file?.path ?? "markdown";
    const visit = (node: MarkdownNode) => {
      if (node.type === "code") {
        const id = captureMarker(node.meta);
        if (id !== undefined) {
          if ((node.value ?? "").trim() !== "") {
            throw new Error(`${where}: the fenced block for capture "${id}" must be empty; its text comes from the capture.`);
          }
          const capture = readCapture(id, options.capturesDir);
          node.lang = "text";
          node.value = capture.output;
          node.meta = `title="${capturedRunLabel(capture)}" wrap`;
        }
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}
