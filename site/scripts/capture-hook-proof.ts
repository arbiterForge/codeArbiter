import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import sharp from "sharp";
import { createFixture } from "./capture/fixture";
import { REPO_ROOT, runPythonEntry } from "./capture/harness";
import { normalizeText, sha256Raw } from "./capture/normalize";

// The hook runs through the shared capture harness (fixture and isolated
// environment). The hook-proof.json it writes keeps its original schema and its
// original sourceSha256 semantics: release applicability digests the raw hook
// bytes, so this does too. The harness also reports the modules the hook run
// loaded, but they are not persisted: the landing proof keeps its own
// current-and-published applicability statement (AC-06), not a stale check.
const repoRoot = REPO_ROOT;
const siteRoot = resolve(import.meta.dirname, "..");
const hookTool = "plugins/ca/hooks/pre-bash.py";
const hookPath = join(repoRoot, ...hookTool.split("/"));
const outputDir = join(siteRoot, "src", "assets", "proof");
const attemptedCommand = ["git", "add", "-A"].join(" ");
// The audit sink the hook appends to inside the disposable fixture.
const gateEventsPath = ".codearbiter/gate-events.log";

/** Create a temporary directory, refusing one that resolves outside tmpdir() before anything can delete it. */
function temporaryDirectory(prefix: string): string {
  const path = mkdtempSync(join(tmpdir(), prefix));
  const safeTempRoot = resolve(tmpdir()).toLowerCase();
  const resolved = resolve(path).toLowerCase();
  if (!resolved.startsWith(`${safeTempRoot}\\`) && !resolved.startsWith(`${safeTempRoot}/`)) {
    throw new Error(`Refusing to use non-temporary capture path: ${path}`);
  }
  return path;
}

function run(command: string, args: string[], cwd: string) {
  return spawnSync(command, args, {
    cwd,
    env: process.env,
    encoding: "utf8",
    windowsHide: true,
  });
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function wrapLine(value: string, width = 78): string[] {
  const words = value.trim().split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    if (!line) {
      line = word;
    } else if (`${line} ${word}`.length <= width) {
      line += ` ${word}`;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

type TranscriptLine = {
  text: string;
  tone?: "normal" | "muted" | "command" | "blocked" | "success";
};

function renderFrame(lines: TranscriptLine[], label: string): string {
  const colors = {
    normal: "#c7d0da",
    muted: "#7f8da0",
    command: "#ffd568",
    blocked: "#ff7b72",
    success: "#58d68d",
  };
  const rows = lines.map((line, index) => {
    const y = 146 + index * 31;
    return `<text x="78" y="${y}" fill="${colors[line.tone ?? "normal"]}" font-family="Cascadia Code, Consolas, monospace" font-size="18">${escapeXml(line.text)}</text>`;
  }).join("\n");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <radialGradient id="glow" cx="82%" cy="8%" r="72%">
      <stop offset="0" stop-color="#f0b92f" stop-opacity=".11"/>
      <stop offset=".58" stop-color="#f0b92f" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="edge" x1="0" x2="1">
      <stop stop-color="#f0b92f"/>
      <stop offset="1" stop-color="#ffd568"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="#090d12"/>
  <rect width="1280" height="720" fill="url(#glow)"/>
  <rect x="36" y="36" width="1208" height="648" rx="20" fill="#0e141c" stroke="#314153"/>
  <rect x="36" y="36" width="1208" height="5" rx="2.5" fill="url(#edge)"/>
  <circle cx="76" cy="79" r="6" fill="#ff7b72"/>
  <circle cx="98" cy="79" r="6" fill="#f0b92f"/>
  <circle cx="120" cy="79" r="6" fill="#58d68d"/>
  <text x="156" y="86" fill="#91a0b2" font-family="Cascadia Code, Consolas, monospace" font-size="15" letter-spacing="2">DIRECT HOOK REPLAY · ${escapeXml(label)}</text>
  <line x1="60" y1="108" x2="1220" y2="108" stroke="#273647"/>
  ${rows}
  <text x="78" y="650" fill="#5f6d7e" font-family="Cascadia Code, Consolas, monospace" font-size="14">direct invocation · disposable repository · exact captured stderr</text>
</svg>`;
}

type Frames = Array<{ lines: TranscriptLine[]; duration: number }>;
/** Renders the replay media (mp4, webm, poster) for `frames` into `outDir`. */
type RenderMedia = (frames: Frames, label: string, frameRoot: string, outDir: string) => Promise<void>;

const makeVideo: RenderMedia = async (frames, label, frameRoot, outDir) => {
  const concatLines: string[] = [];
  for (const [index, frame] of frames.entries()) {
    const framePath = join(frameRoot, `frame-${index.toString().padStart(2, "0")}.png`);
    await sharp(Buffer.from(renderFrame(frame.lines, label))).png().toFile(framePath);
    concatLines.push(`file '${framePath.replaceAll("\\", "/").replaceAll("'", "'\\''")}'`);
    concatLines.push(`duration ${frame.duration}`);
  }
  const lastFrame = join(frameRoot, `frame-${(frames.length - 1).toString().padStart(2, "0")}.png`);
  concatLines.push(`file '${lastFrame.replaceAll("\\", "/").replaceAll("'", "'\\''")}'`);
  const concatPath = join(frameRoot, "frames.txt");
  writeFileSync(concatPath, `${concatLines.join("\n")}\n`, "utf8");

  const shared = ["-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concatPath, "-vf", "fps=30,format=yuv420p"];
  const mp4 = run(
    "ffmpeg",
    [...shared, "-c:v", "libx264", "-crf", "24", "-preset", "slow", "-movflags", "+faststart", "-y", join(outDir, "hook-proof.mp4")],
    siteRoot,
  );
  if (mp4.status !== 0) {
    throw new Error(`ffmpeg MP4 render failed (${mp4.status}):\n${mp4.stderr}`);
  }
  const webm = run(
    "ffmpeg",
    [...shared, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "35", "-an", "-y", join(outDir, "hook-proof.webm")],
    siteRoot,
  );
  if (webm.status !== 0) {
    throw new Error(`ffmpeg WebM render failed (${webm.status}):\n${webm.stderr}`);
  }
  await sharp(lastFrame).webp({ quality: 88 }).toFile(join(outDir, "hook-proof-poster.webp"));
};

/** The record release applicability reads. Its schema is fixed; see the header comment. */
interface HookProofRecord {
  schema: 1;
  evidenceKind: "direct-hook-invocation-rendered-replay";
  hostDiscoveryProven: false;
  capturedAt: string;
  source: string;
  sourceSha256: string;
  fixture: {
    branch: string;
    activation: string;
    untrackedBefore: string;
    statusAfter: string;
    stagedBefore: string;
    stagedAfter: string;
    gateEvent: string;
  };
  invocation: {
    attemptedCommand: string;
    hookEvent: string;
    toolName: string;
    exitCode: number;
    stderr: string;
    commandExecuted: false;
  };
}

/** The record without the run's clock, with timestamps inside its text normalized, for comparing two runs. */
function evidenceOf(record: HookProofRecord): string {
  const { capturedAt: _capturedAt, ...evidence } = record;
  return normalizeText(JSON.stringify(evidence));
}

/**
 * Re-run the hook against a fresh fixture and refresh the landing proof.
 *
 * hook-proof.json carries a capture time and the media carry a rendered date,
 * so rewriting them on every run would leave the working tree dirty for no new
 * evidence. They are rewritten only when the recorded evidence differs (the
 * hook changed, or its behavior did) or when `force` asks for a fresh render.
 */
export async function captureHookProof(
  options: {
    force?: boolean;
    /** Where the proof record and media live. Defaults to the committed landing assets. */
    outputDir?: string;
    /** Renders the replay media. Defaults to ffmpeg and sharp; replaceable so a render failure can be tested. */
    render?: RenderMedia;
  } = {},
): Promise<void> {
  const outDir = options.outputDir ?? outputDir;
  const render = options.render ?? makeVideo;
  mkdirSync(outDir, { recursive: true });
  const fixture = createFixture();
  let frameRoot: string | undefined;
  try {
    fixture.write(
      ".codearbiter/CONTEXT.md",
      "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nDisposable documentation proof fixture.\n",
    );
    fixture.write(gateEventsPath, "");
    fixture.initGit({ branch: "feat/proof", email: "proof@codearbiter.invalid", name: "codeArbiter proof" });
    fixture.git("add", ".codearbiter/CONTEXT.md", gateEventsPath);
    fixture.git("commit", "-q", "-m", "chore: initialize proof fixture");
    fixture.write("note.txt", "This file must remain unstaged.\n");

    const statusBefore = fixture.git("status", "--short").trimEnd();
    const stagedBefore = fixture.git("diff", "--cached", "--name-only").trimEnd();
    const payload = JSON.stringify({
      hook_event_name: "PreToolUse",
      tool_name: "Bash",
      cwd: fixture.project,
      tool_input: { command: attemptedCommand },
    });
    const hook = runPythonEntry(fixture, hookTool, [], { stdin: payload });
    const statusAfter = fixture.git("status", "--short").trimEnd();
    const stagedAfter = fixture.git("diff", "--cached", "--name-only").trimEnd();
    const stderr = hook.stderr.trim().replace(/\r\n/g, "\n");
    const gateEvent = readFileSync(join(fixture.project, ...gateEventsPath.split("/")), "utf8").trim();

    if (hook.status !== 2 || !stderr.includes("BLOCKED [H-03]")) {
      throw new Error(`Expected a real H-03 exit-2 block; got exit=${hook.status} stderr=${stderr}`);
    }
    if (stagedAfter !== stagedBefore || !statusAfter.includes("?? note.txt")) {
      throw new Error(
        `The blocked call staged content or changed the intended file state:\n` +
        `staged before=${stagedBefore}\nstaged after=${stagedAfter}\nstatus=${statusAfter}`,
      );
    }
    if (!gateEvent.includes("BLOCK [H-03]")) {
      throw new Error(`Expected H-03 to append a real gate event; got: ${gateEvent}`);
    }

    const capturedAt = new Date().toISOString();
    const sourceSha256 = sha256Raw(readFileSync(hookPath));
    const record: HookProofRecord = {
      schema: 1,
      evidenceKind: "direct-hook-invocation-rendered-replay",
      hostDiscoveryProven: false,
      capturedAt,
      source: relative(repoRoot, hookPath).replaceAll("\\", "/"),
      sourceSha256,
      fixture: {
        branch: "feat/proof",
        activation: "arbiter: enabled",
        untrackedBefore: statusBefore,
        statusAfter,
        stagedBefore,
        stagedAfter,
        gateEvent,
      },
      invocation: {
        attemptedCommand,
        hookEvent: "PreToolUse",
        toolName: "Bash",
        exitCode: hook.status,
        stderr,
        commandExecuted: false,
      },
    };

    const proofPath = join(outDir, "hook-proof.json");
    const previous = existsSync(proofPath) ? (JSON.parse(readFileSync(proofPath, "utf8")) as HookProofRecord) : undefined;
    if (!options.force && previous && evidenceOf(previous) === evidenceOf(record)) {
      process.stdout.write(
        `Hook proof unchanged: ${record.source} still produces the recorded H-03 block (sha256 ${sourceSha256}).\n` +
        `Run \`npm run capture:proof\` to force a fresh render of the landing replay.\n`,
      );
      return;
    }

    const blockLines = stderr.split("\n").flatMap((line) => wrapLine(line, 77));
    const timeline: TranscriptLine[] = [
      { text: "codeArbiter hook verification", tone: "muted" },
      { text: "repo  feat/proof · arbiter: enabled", tone: "normal" },
    ];
    const frames: Array<{ lines: TranscriptLine[]; duration: number }> = [
      { lines: [...timeline], duration: 1.2 },
      {
        lines: [...timeline, { text: "$ git status --short", tone: "command" }, { text: statusBefore, tone: "normal" }],
        duration: 1.8,
      },
      {
        lines: [
          ...timeline,
          { text: "$ git status --short", tone: "command" },
          { text: statusBefore, tone: "normal" },
          { text: `$ ${attemptedCommand}`, tone: "command" },
          { text: "→ PreToolUse · plugins/ca/hooks/pre-bash.py", tone: "muted" },
        ],
        duration: 1.6,
      },
      {
        lines: [
          ...timeline,
          { text: `$ ${attemptedCommand}`, tone: "command" },
          { text: "→ PreToolUse · plugins/ca/hooks/pre-bash.py", tone: "muted" },
          ...blockLines.map((text) => ({ text, tone: "blocked" as const })),
        ],
        duration: 3.2,
      },
      {
        lines: [
          ...timeline,
          { text: `$ ${attemptedCommand}`, tone: "command" },
          ...blockLines.map((text) => ({ text, tone: "blocked" as const })),
          { text: "exit 2 · tool call denied · command not executed", tone: "blocked" },
        ],
        duration: 2.2,
      },
      {
        lines: [
          ...timeline,
          { text: "$ git diff --cached --name-only", tone: "command" },
          { text: stagedAfter || "(no staged files)", tone: "normal" },
          { text: "$ git status --short", tone: "command" },
          ...statusAfter.split("\n").map((text) => ({ text, tone: "normal" as const })),
          { text: "✓ note.txt remained unstaged", tone: "success" },
          { text: "✓ H-03 block appended to gate-events.log", tone: "success" },
        ],
        duration: 3,
      },
    ];
    frameRoot = temporaryDirectory("codearbiter-proof-frames-");
    await render(timeline.length ? frames : [], capturedAt.slice(0, 10), frameRoot, outDir);
    // Last, and only once the media exist: a record that already matches the hook
    // would make every later run report "unchanged" and never retry a failed render.
    writeFileSync(proofPath, `${JSON.stringify(record, null, 2)}\n`, "utf8");
    process.stdout.write(
      `Captured direct H-03 hook invocation from ${record.source} at ${capturedAt}\n` +
      `Source SHA-256: ${sourceSha256}\n` +
      `Artifacts: ${relative(siteRoot, outDir)}\n`,
    );
  } finally {
    // Nested so the frame directory is still removed when dispose() throws.
    try {
      fixture.dispose();
    } finally {
      if (frameRoot) rmSync(frameRoot, { recursive: true, force: true });
    }
  }
}

// `npm run capture:proof` runs this file directly and always re-renders;
// `npm run capture` imports captureHookProof() and renders only on new evidence.
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await captureHookProof({ force: true });
}
