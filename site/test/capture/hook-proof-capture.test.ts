/** hook-proof-capture.test.ts - the landing hook proof is refreshed only by a render that succeeded.
 *
 * `npm run capture` rewrites hook-proof.json only when the recorded evidence
 * differs. If the record were written before the media render, a failed render
 * (ffmpeg missing, say) would leave a record that already matches the hook, so
 * every later run would say "unchanged" and the mp4, webm and poster would never
 * be regenerated. The record is therefore written last.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { captureHookProof } from "../../scripts/capture-hook-proof";
import { sha256Raw } from "../../scripts/capture/normalize";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const repoRoot = resolve(siteRoot, "..");
const committed = JSON.parse(readFileSync(join(siteRoot, "src", "assets", "proof", "hook-proof.json"), "utf8"));

let dir: string;
let proofPath: string;

/** The shape of a value: keys at every level and the type of every leaf. */
function shape(value: unknown): unknown {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, shape(item)]));
  }
  return typeof value;
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "hook-proof-capture-test-"));
  proofPath = join(dir, "hook-proof.json");
  vi.spyOn(process.stdout, "write").mockImplementation(() => true);
});

afterEach(() => {
  vi.restoreAllMocks();
  rmSync(dir, { recursive: true, force: true });
});

/** A record that no longer matches what the hook produces, as if the hook had changed since. */
function seedStaleRecord(): string {
  writeFileSync(proofPath, `${JSON.stringify({ ...committed, sourceSha256: "0".repeat(64) }, null, 2)}\n`);
  return readFileSync(proofPath, "utf8");
}

describe("hook proof refresh", () => {
  it("leaves the old record in place when the media render fails, so the next run still sees it as stale", async () => {
    const stale = seedStaleRecord();
    const failing = vi.fn(async () => {
      throw new Error("ffmpeg is not installed");
    });
    await expect(captureHookProof({ outputDir: dir, render: failing })).rejects.toThrow("ffmpeg is not installed");
    expect(failing).toHaveBeenCalledTimes(1);
    expect(readFileSync(proofPath, "utf8")).toBe(stale);

    const render = vi.fn(async () => undefined);
    await captureHookProof({ outputDir: dir, render });
    expect(render).toHaveBeenCalledTimes(1);
    expect(JSON.parse(readFileSync(proofPath, "utf8")).sourceSha256).toBe(
      sha256Raw(readFileSync(join(repoRoot, committed.source))),
    );
  }, 120_000);

  it("writes the record only after the render has finished", async () => {
    const stale = seedStaleRecord();
    let recordDuringRender: string | undefined;
    await captureHookProof({
      outputDir: dir,
      render: async () => {
        recordDuringRender = readFileSync(proofPath, "utf8");
      },
    });
    expect(recordDuringRender).toBe(stale);
    expect(readFileSync(proofPath, "utf8")).not.toBe(stale);
  }, 120_000);

  it("renders nothing when the recorded evidence still matches, unless forced", async () => {
    writeFileSync(proofPath, `${JSON.stringify(committed, null, 2)}\n`);
    const before = readFileSync(proofPath, "utf8");
    const render = vi.fn(async () => undefined);
    await captureHookProof({ outputDir: dir, render });
    expect(render).not.toHaveBeenCalled();
    expect(readFileSync(proofPath, "utf8")).toBe(before);

    await captureHookProof({ outputDir: dir, render, force: true });
    expect(render).toHaveBeenCalledTimes(1);
  }, 120_000);

  it("writes a record with the committed schema and renders into the directory it was given", async () => {
    const render = vi.fn(async (_frames: unknown, _label: string, _frameRoot: string, outDir: string) => {
      expect(outDir).toBe(dir);
    });
    await captureHookProof({ outputDir: dir, render });
    expect(existsSync(proofPath)).toBe(true);
    const written = JSON.parse(readFileSync(proofPath, "utf8"));
    expect(shape(written)).toEqual(shape(committed));
    expect(written.sourceSha256).toBe(committed.sourceSha256);
  }, 120_000);
});
