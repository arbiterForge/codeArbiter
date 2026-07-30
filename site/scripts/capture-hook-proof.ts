import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import sharp from "sharp";

const repoRoot = resolve(import.meta.dirname, "../..");
const siteRoot = resolve(import.meta.dirname, "..");
const hookPath = join(repoRoot, "plugins", "ca", "hooks", "pre-bash.py");
const outputDir = join(siteRoot, "src", "assets", "proof");
const fixtureRoot = mkdtempSync(join(tmpdir(), "codearbiter-hook-proof-"));
const frameRoot = mkdtempSync(join(tmpdir(), "codearbiter-proof-frames-"));
const python = process.env.PYTHON || "python";
const attemptedCommand = ["git", "add", "-A"].join(" ");

function run(
  command: string,
  args: string[],
  cwd: string,
  options: { input?: string; env?: NodeJS.ProcessEnv } = {},
) {
  return spawnSync(command, args, {
    cwd,
    input: options.input,
    env: options.env ?? process.env,
    encoding: "utf8",
    windowsHide: true,
  });
}

function mustRun(command: string, args: string[], cwd: string) {
  const result = run(command, args, cwd);
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(" ")} failed (${result.status}):\n${result.stderr || result.stdout}`,
    );
  }
  return result;
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

async function makeVideo(frames: Array<{ lines: TranscriptLine[]; duration: number }>, label: string) {
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
    [...shared, "-c:v", "libx264", "-crf", "24", "-preset", "slow", "-movflags", "+faststart", "-y", join(outputDir, "hook-proof.mp4")],
    siteRoot,
  );
  if (mp4.status !== 0) {
    throw new Error(`ffmpeg MP4 render failed (${mp4.status}):\n${mp4.stderr}`);
  }
  const webm = run(
    "ffmpeg",
    [...shared, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "35", "-an", "-y", join(outputDir, "hook-proof.webm")],
    siteRoot,
  );
  if (webm.status !== 0) {
    throw new Error(`ffmpeg WebM render failed (${webm.status}):\n${webm.stderr}`);
  }
  await sharp(lastFrame).webp({ quality: 88 }).toFile(join(outputDir, "hook-proof-poster.webp"));
}

async function main() {
  mkdirSync(outputDir, { recursive: true });
  mkdirSync(join(fixtureRoot, ".codearbiter"), { recursive: true });
  writeFileSync(
    join(fixtureRoot, ".codearbiter", "CONTEXT.md"),
    "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nDisposable documentation proof fixture.\n",
    "utf8",
  );
  writeFileSync(join(fixtureRoot, ".codearbiter", "gate-events.log"), "", "utf8");
  mustRun("git", ["init", "-q", "-b", "feat/proof"], fixtureRoot);
  mustRun("git", ["config", "user.name", "codeArbiter proof"], fixtureRoot);
  mustRun("git", ["config", "user.email", "proof@codearbiter.invalid"], fixtureRoot);
  mustRun("git", ["add", ".codearbiter/CONTEXT.md", ".codearbiter/gate-events.log"], fixtureRoot);
  mustRun("git", ["commit", "-q", "-m", "chore: initialize proof fixture"], fixtureRoot);
  writeFileSync(join(fixtureRoot, "note.txt"), "This file must remain unstaged.\n", "utf8");

  const statusBefore = mustRun("git", ["status", "--short"], fixtureRoot).stdout.trimEnd();
  const stagedBefore = mustRun("git", ["diff", "--cached", "--name-only"], fixtureRoot).stdout.trimEnd();
  const payload = JSON.stringify({
    hook_event_name: "PreToolUse",
    tool_name: "Bash",
    cwd: fixtureRoot,
    tool_input: { command: attemptedCommand },
  });
  const hook = run(python, [hookPath], fixtureRoot, {
    input: payload,
    env: { ...process.env, CLAUDE_PROJECT_DIR: fixtureRoot, CODEARBITER_HOST: "claude" },
  });
  const statusAfter = mustRun("git", ["status", "--short"], fixtureRoot).stdout.trimEnd();
  const stagedAfter = mustRun("git", ["diff", "--cached", "--name-only"], fixtureRoot).stdout.trimEnd();
  const stderr = hook.stderr.trim().replace(/\r\n/g, "\n");
  const gateEvent = readFileSync(join(fixtureRoot, ".codearbiter", "gate-events.log"), "utf8").trim();

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
  const sourceSha256 = createHash("sha256").update(readFileSync(hookPath)).digest("hex");
  const record = {
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
  writeFileSync(join(outputDir, "hook-proof.json"), `${JSON.stringify(record, null, 2)}\n`, "utf8");

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
  await makeVideo(timeline.length ? frames : [], capturedAt.slice(0, 10));
  process.stdout.write(
    `Captured direct H-03 hook invocation from ${record.source} at ${capturedAt}\n` +
    `Source SHA-256: ${sourceSha256}\n` +
    `Artifacts: ${relative(siteRoot, outputDir)}\n`,
  );
}

try {
  await main();
} finally {
  const safeTempRoot = resolve(tmpdir()).toLowerCase();
  for (const target of [fixtureRoot, frameRoot]) {
    const resolved = resolve(target).toLowerCase();
    if (!resolved.startsWith(`${safeTempRoot}\\`) && !resolved.startsWith(`${safeTempRoot}/`)) {
      throw new Error(`Refusing to remove non-temporary capture path: ${target}`);
    }
    rmSync(target, { recursive: true, force: true });
  }
}
