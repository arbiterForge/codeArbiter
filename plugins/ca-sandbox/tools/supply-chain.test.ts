/**
 * supply-chain.test.ts — structural supply-chain guards for the ca-sandbox driver.
 *
 * Two tribunal findings are locked down here, both about EXTERNAL BYTES that
 * ca-sandbox would otherwise pull in unpinned:
 *
 *   #401 (secrets-supply-002) — no ca-sandbox runtime path may pipe
 *     network-fetched bytes into a shell. `defaultEnsureNixpacks` used to run
 *     `bash -c "curl -fsSL https://nixpacks.com/install.sh | bash"` on the
 *     developer host, BEFORE any container boundary exists. nixpacks is a
 *     documented prerequisite (README / SKILL / command description all say so),
 *     so the missing-prerequisite path now FAILS CLOSED to the pre-existing
 *     generated-Dockerfile fallback and tells the user to install nixpacks.
 *
 *   #402 (secrets-supply-004) — every external container image reference must be
 *     bound to a reviewed content digest (`name:tag@sha256:<64 hex>`), so a retag
 *     or registry compromise cannot silently swap executable code into a sandbox
 *     build — least of all into the `--with-claude` box, which co-runs the base
 *     image with CLAUDE_CODE_OAUTH_TOKEN.
 *
 * These are STRUCTURAL tests on purpose: `defaultEnsureNixpacks` and the image
 * constants are defaults that every other suite stubs out, so the real path had
 * ZERO coverage. A structural scan cannot be stubbed past — it reads the shipped
 * bytes. Test files are exempt from the scan (lifecycle.test.ts deliberately
 * hardcodes `alpine/git:latest` when driving docker directly), which is why the
 * scan enumerates production sources explicitly rather than globbing everything.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  defaultEnsureNixpacks,
  generateDockerfile,
  type RunResult,
} from "./build.ts";
import { CLONE_IMAGE } from "./create.ts";
import { CLAUDE_BASE_IMAGE, buildClaudeImageDockerfile } from "./claude-inside.ts";

const TOOLS_DIR = path.dirname(fileURLToPath(import.meta.url));

/**
 * The production surface of the driver: every shipped source file plus the
 * committed esbuild bundle (`sandbox.js` — the bytes that actually run on a
 * user's machine). Test files, fixtures and the vitest config are NOT production
 * code and are deliberately excluded.
 */
function productionFiles(): string[] {
  const entries = readdirSync(TOOLS_DIR, { withFileTypes: true });
  const files = entries
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .filter((n) => n.endsWith(".ts") || n === "sandbox.js")
    .filter((n) => !n.endsWith(".test.ts"))
    .filter((n) => n !== "vitest.config.ts");
  return files.sort().map((n) => path.join(TOOLS_DIR, n));
}

function rel(file: string): string {
  return path.relative(TOOLS_DIR, file).replace(/\\/g, "/");
}

/** A `sha256:<64 hex>` digest binding, optionally preceded by a tag. */
const DIGEST_PINNED = /@sha256:[0-9a-f]{64}\b/;

/**
 * Does this string name an image PULLED FROM A REGISTRY (and therefore in need
 * of a digest pin), as opposed to a locally built one? An external ref carries a
 * registry namespace (`alpine/git`) or a tag (`node:22-slim`); the driver's own
 * `ca-sbx` tag prefix carries neither and has nothing upstream to pin.
 */
function isExternalImageRef(ref: string): boolean {
  return ref.includes("/") || ref.includes(":");
}

describe("supply chain: no remote-fetch-and-execute in production code (#401)", () => {
  it("has at least one production file to scan (guards the scanner itself)", () => {
    const files = productionFiles();
    expect(files.length).toBeGreaterThan(5);
    expect(files.map(rel)).toContain("build.ts");
    expect(files.map(rel)).toContain("sandbox.js");
  });

  it("never pipes network-fetched bytes into a shell or interpreter", () => {
    // A downloader (curl/wget/Invoke-WebRequest) whose output flows into a shell,
    // an interpreter, or `source`/`eval` — in any order, on one line.
    const PIPE_TO_SHELL = [
      /\b(curl|wget|iwr|Invoke-WebRequest)\b[^\n]*\|[^\n]*\b(ba|z|da|k)?sh\b/i,
      /\b(curl|wget|iwr|Invoke-WebRequest)\b[^\n]*\|[^\n]*\b(python3?|node|perl|ruby)\b/i,
      /\b(eval|source)\b[^\n]*\$\([^\n]*\b(curl|wget)\b/i,
      /\b(ba|z)?sh\b[^\n]*<\(\s*(curl|wget)\b/i,
    ];
    const hits: string[] = [];
    for (const file of productionFiles()) {
      const lines = readFileSync(file, "utf8").split(/\r?\n/);
      lines.forEach((line, i) => {
        if (PIPE_TO_SHELL.some((re) => re.test(line))) {
          hits.push(`${rel(file)}:${i + 1}: ${line.trim()}`);
        }
      });
    }
    expect(
      hits,
      "ca-sandbox production code must never execute network-fetched bytes " +
        "(no `curl | bash`): remote code would run with the developer's privileges " +
        "BEFORE any container boundary exists. Declare the tool a prerequisite and " +
        "fail closed to the generated-Dockerfile fallback instead.",
    ).toEqual([]);
  });

  it("ships no remote-installer endpoint constant", async () => {
    const build = (await import("./build.ts")) as Record<string, unknown>;
    expect(Object.keys(build)).not.toContain("NIXPACKS_INSTALL_URL");
    const src = readFileSync(path.join(TOOLS_DIR, "build.ts"), "utf8");
    expect(src).not.toMatch(/nixpacks\.com\/install\.sh/);
  });

  it("fails closed when nixpacks is absent: probes only, no host mutation", async () => {
    const calls: Array<{ cmd: string; args: string[] }> = [];
    const absent: RunResult = { code: 127, out: "not found", stdout: "", stderr: "not found" };
    const probe = async (cmd: string, args: string[]): Promise<RunResult> => {
      calls.push({ cmd, args });
      return absent;
    };

    const res = await defaultEnsureNixpacks(probe);

    // Fails CLOSED to the documented fallback, with an actionable note.
    expect(res.available).toBe(false);
    expect(res.via).toBeUndefined();
    expect(res.note).toMatch(/install nixpacks/i);

    // And it mutated NOTHING on the host: every command spawned is a read-only
    // version/location probe of an already-installed tool.
    const argv = calls.map((c) => [c.cmd, ...c.args].join(" "));
    const installerish = argv.filter((s) =>
      /\b(curl|wget|Invoke-WebRequest)\b|\binstall\b|\|\s*(ba)?sh\b/i.test(s),
    );
    expect(
      installerish,
      "a missing nixpacks prerequisite must not fetch or install anything",
    ).toEqual([]);
    expect(calls.map((c) => c.cmd).every((c) => c === "nixpacks" || c === "wsl.exe")).toBe(true);
  });
});

describe("supply chain: container inputs are digest-pinned (#402)", () => {
  it("pins the throwaway clone image by digest", () => {
    expect(CLONE_IMAGE).toMatch(DIGEST_PINNED);
  });

  it("pins the --with-claude base image by digest (token co-runs with it)", () => {
    expect(CLAUDE_BASE_IMAGE).toMatch(DIGEST_PINNED);
  });

  it("emits only digest-pinned FROM lines from every generated Dockerfile", () => {
    const dockerfiles = [
      generateDockerfile({ node: false, python: false }),
      generateDockerfile({ node: true, python: true }),
      buildClaudeImageDockerfile(),
    ];
    for (const df of dockerfiles) {
      const froms = df.split(/\r?\n/).filter((l) => /^\s*FROM\s/i.test(l));
      expect(froms.length).toBeGreaterThan(0);
      for (const line of froms) {
        expect(line, `unpinned base image: ${line}`).toMatch(DIGEST_PINNED);
      }
    }
  });

  it("references no floating `:latest` tag in production code", () => {
    const hits: string[] = [];
    for (const file of productionFiles()) {
      const lines = readFileSync(file, "utf8").split(/\r?\n/);
      lines.forEach((line, i) => {
        // `:latest` is tolerated ONLY when immediately bound to a digest.
        for (const m of line.matchAll(/:latest\b(@sha256:[0-9a-f]{64})?/g)) {
          if (!m[1]) hits.push(`${rel(file)}:${i + 1}: ${line.trim()}`);
        }
      });
    }
    expect(
      hits,
      "a floating `:latest` tag lets a retag or registry compromise swap " +
        "executable code into a sandbox build; bind it as name:tag@sha256:<digest>",
    ).toEqual([]);
  });

  it("digest-pins every image constant and literal FROM in production code", () => {
    const hits: string[] = [];
    for (const file of productionFiles()) {
      const src = readFileSync(file, "utf8");
      const lines = src.split(/\r?\n/);
      lines.forEach((line, i) => {
        // (a) named image constants: `export const CLONE_IMAGE = "..."` (and the
        //     bundled `var CLONE_IMAGE = "..."` form in sandbox.js). Only refs
        //     that name an EXTERNAL registry image are in scope — a bare local
        //     tag prefix like `ca-sbx` (IMAGE_PREFIX, images this driver builds
        //     itself) has no registry namespace or tag and nothing to pin.
        const constDecl = line.match(/\b(?:const|let|var)\s+\w*IMAGE\w*\s*=\s*(["'`])([^"'`]+)\1/);
        if (constDecl && isExternalImageRef(constDecl[2]) && !DIGEST_PINNED.test(constDecl[2])) {
          hits.push(`${rel(file)}:${i + 1}: unpinned image constant: ${constDecl[2]}`);
        }
        // (b) literal `FROM <ref>` inside emitted Dockerfile text. A `${...}`
        //     interpolation is allowed — the constant it reads is covered by (a)
        //     and by the generated-Dockerfile assertions above.
        const from = line.match(/\bFROM\s+([^\s"'`\\]+)/);
        if (from && !from[1].includes("${") && !DIGEST_PINNED.test(from[1])) {
          hits.push(`${rel(file)}:${i + 1}: unpinned FROM: ${from[1]}`);
        }
      });
    }
    expect(
      hits,
      "every external container image reference must be bound to a reviewed " +
        "sha256 digest (name:tag@sha256:<digest>)",
    ).toEqual([]);
  });
});
