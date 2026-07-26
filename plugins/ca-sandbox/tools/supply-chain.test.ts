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

// --------------------------------------------------------------------------
// the digest scanner (#402 AC-2)
// --------------------------------------------------------------------------
//
// This scanner reads JOINED FILE TEXT, never line-by-line. That is load-bearing:
// every image constant in this driver is written with the value on its own
// continuation line —
//
//     export const CLONE_IMAGE =
//       "alpine/git:latest@sha256:...";
//
// — so a per-line rule that expects `const NAME = "<ref>"` on ONE line matches
// none of the shipped declarations and is silently inert. `scannerSelfTest`
// below locks that in: it runs these same rules against synthetic multi-line
// sources and asserts they actually fire.

/** 1-based line number of `index` within `src`. */
function lineOf(src: string, index: number): number {
  return src.slice(0, index).split(/\r?\n/).length;
}

/**
 * A named image constant — `export const CLONE_IMAGE = "<ref>"`, the bundled
 * `var CLONE_IMAGE = "<ref>"` form, and (critically) the multi-line form where
 * the literal sits on the next line. `\s*` spans the newline; the value class
 * does not, so the literal itself is still single-line.
 */
const IMAGE_CONST = /\b(?:const|let|var)\s+(\w*IMAGE\w*)\s*=\s*(["'`])([^"'`\n]*)\2/g;

/**
 * A string literal that IS a namespaced registry reference (`ns/name:tag`) —
 * name-independent, so `const TRIVY = "aquasec/trivy:0.50.0"` and a bare argv
 * element `"alpine/git:latest"` are both caught even though neither is named
 * `*IMAGE*`. Requiring the `/` namespace is what keeps this free of false
 * positives: node builtin specifiers (`node:path`, `node:fs/promises`) and
 * docs placeholders (`host:container`, `1000:1000`) never match.
 *
 * Residual, accepted: an official-library image with no namespace and a
 * non-`latest` tag (`"node:22-slim"`) bound to a constant NOT named `*IMAGE*`
 * would evade this rule — `node:<builtin>` import specifiers are structurally
 * identical to it. Today's two such images are both `*IMAGE*`-named (caught by
 * IMAGE_CONST) and additionally asserted by name in the tests below.
 */
const NAMESPACED_IMAGE_LITERAL =
  /(["'`])([a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)+:[A-Za-z0-9][A-Za-z0-9._-]*(?:@sha256:[0-9a-f]{64})?)\1/g;

/** `FROM <ref>` inside emitted Dockerfile text. */
const FROM_REF = /\bFROM\s+([^\s"'`\\]+)/g;

/** `const <name> = <initializer>` — used to follow a FROM interpolation home. */
const ANY_BINDING = /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]*)/g;

/**
 * Names that provably carry a digest-pinned image in this file: the pinned image
 * constants themselves, plus bindings initialized from one (`const base =
 * opts.baseImage ?? CLAUDE_BASE_IMAGE`). Anything else interpolated into a
 * `FROM` is unproven and is reported.
 */
function pinnedNames(src: string, pinnedConsts: Set<string>): Set<string> {
  const names = new Set(pinnedConsts);
  // Iterate to a fixed point so an alias of an alias still resolves.
  for (let pass = 0; pass < 3; pass++) {
    const before = names.size;
    for (const m of src.matchAll(ANY_BINDING)) {
      const [, name, init] = m;
      const ids = init.match(/[A-Za-z_$][\w$]*/g) ?? [];
      if (ids.some((id) => names.has(id))) names.add(name);
    }
    if (names.size === before) break;
  }
  return names;
}

/**
 * Report every external image reference in `src` that is not bound to a reviewed
 * sha256 digest. `label` prefixes each hit so failures name the file and line.
 */
function scanUnpinnedImages(src: string, label: string): string[] {
  const hits: string[] = [];
  const pinnedConsts = new Set<string>();
  // Literal offsets already reported, so the namespaced-literal pass does not
  // double-report a constant the named-constant pass just flagged.
  const reported = new Set<number>();

  // (a) named image constants, single- OR multi-line. Only refs that name an
  //     EXTERNAL registry image are in scope — a bare local tag prefix like
  //     `ca-sbx` (IMAGE_PREFIX, images this driver builds itself) has no
  //     registry namespace or tag and nothing upstream to pin.
  for (const m of src.matchAll(IMAGE_CONST)) {
    const [, name, , value] = m;
    if (!isExternalImageRef(value)) continue;
    if (DIGEST_PINNED.test(value)) {
      pinnedConsts.add(name);
      continue;
    }
    const quoteAt = m.index + m[0].length - value.length - 2;
    reported.add(quoteAt);
    hits.push(`${label}:${lineOf(src, quoteAt)}: unpinned image constant: ${name} = ${value}`);
  }

  // (b) any namespaced registry ref, whatever it is bound to.
  for (const m of src.matchAll(NAMESPACED_IMAGE_LITERAL)) {
    if (DIGEST_PINNED.test(m[2]) || reported.has(m.index)) continue;
    hits.push(`${label}:${lineOf(src, m.index)}: unpinned image reference: ${m[2]}`);
  }

  // (c) `FROM <ref>` in emitted Dockerfile text. An interpolation is allowed
  //     ONLY when it demonstrably reads a digest-pinned constant from this file;
  //     a blanket `${...}` pass would let an unpinned constant through (a) via
  //     the Dockerfile it emits.
  const resolvable = pinnedNames(src, pinnedConsts);
  for (const m of src.matchAll(FROM_REF)) {
    const ref = m[1];
    const at = `${label}:${lineOf(src, m.index)}`;
    const interpolated = ref.match(/^\$\{(.*)\}$/);
    if (interpolated) {
      const ids = interpolated[1].match(/[A-Za-z_$][\w$]*/g) ?? [];
      if (!ids.some((id) => resolvable.has(id))) {
        hits.push(`${at}: FROM ${ref} does not resolve to a digest-pinned image constant`);
      }
      continue;
    }
    if (!DIGEST_PINNED.test(ref)) hits.push(`${at}: unpinned FROM: ${ref}`);
  }

  return hits;
}

describe("supply chain: no remote-fetch-and-execute in production code (#401)", () => {
  it("has at least one production file to scan (guards the scanner itself)", async () => {
    const files = productionFiles();
    expect(files.length).toBeGreaterThan(5);
    expect(files.map(rel)).toContain("build.ts");
    expect(files.map(rel)).toContain("sandbox.js");
  });

  it("never pipes network-fetched bytes into a shell or interpreter", async () => {
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
  it("pins the throwaway clone image by digest", async () => {
    expect(CLONE_IMAGE).toMatch(DIGEST_PINNED);
  });

  it("pins the --with-claude base image by digest (token co-runs with it)", async () => {
    expect(CLAUDE_BASE_IMAGE).toMatch(DIGEST_PINNED);
  });

  it("emits only digest-pinned FROM lines from every generated Dockerfile", async () => {
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

  it("references no floating `:latest` tag in production code", async () => {
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

  it("digest-pins every image constant and literal FROM in production code", async () => {
    const hits: string[] = [];
    for (const file of productionFiles()) {
      hits.push(...scanUnpinnedImages(readFileSync(file, "utf8"), rel(file)));
    }
    expect(
      hits,
      "every external container image reference must be bound to a reviewed " +
        "sha256 digest (name:tag@sha256:<digest>)",
    ).toEqual([]);
  });
});

/**
 * The scanner's own regression suite. The rules above are only worth the bytes
 * they occupy if they FIRE, and a scanner that quietly matches nothing looks
 * exactly like a clean codebase. The previous per-line version of this scanner
 * shipped inert against the multi-line declaration style every image constant in
 * this driver uses; these cases make that failure mode loud.
 */
describe("supply chain: the digest scanner itself fires (#402)", () => {
  it("catches an unpinned image constant declared across two lines", async () => {
    const src = ["export const PROBE_HELPER_IMAGE =", '  "aquasec/trivy:0.50.0";'].join("\n");
    expect(scanUnpinnedImages(src, "probe.ts")).toEqual([
      "probe.ts:2: unpinned image constant: PROBE_HELPER_IMAGE = aquasec/trivy:0.50.0",
    ]);
  });

  it("catches an unpinned namespaced ref bound to a constant not named *IMAGE*", async () => {
    const src = 'const scanner =\n  "aquasec/trivy:0.50.0";';
    expect(scanUnpinnedImages(src, "probe.ts")).toEqual([
      "probe.ts:2: unpinned image reference: aquasec/trivy:0.50.0",
    ]);
  });

  it("catches a literal FROM and a FROM interpolating an unproven binding", async () => {
    const src = [
      "const other = opts.baseImage;",
      "lines.push(`FROM ${other}`);",
      "lines.push(`FROM debian:bookworm`);",
    ].join("\n");
    expect(scanUnpinnedImages(src, "probe.ts")).toEqual([
      "probe.ts:2: FROM ${other} does not resolve to a digest-pinned image constant",
      "probe.ts:3: unpinned FROM: debian:bookworm",
    ]);
  });

  it("reports an unpinned constant exactly once, not once per rule", async () => {
    const src = 'export const CLONE_IMAGE =\n  "alpine/git:latest";';
    expect(scanUnpinnedImages(src, "probe.ts")).toHaveLength(1);
  });

  it("stays silent on the pinned multi-line form the driver actually ships", async () => {
    const pinned = `alpine/git:latest@sha256:${"0".repeat(64)}`;
    const src = [
      "export const CLONE_IMAGE =",
      `  "${pinned}";`,
      "const base = opts.baseImage ?? CLONE_IMAGE;",
      "lines.push(`FROM ${base}`);",
      'const IMAGE_PREFIX = "ca-sbx";',
      'import { x } from "node:fs/promises";',
    ].join("\n");
    expect(scanUnpinnedImages(src, "probe.ts")).toEqual([]);
  });
});
