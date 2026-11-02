/** capture-harness.test.ts - AC-05: captured runs are reproducible.
 *
 * The normalizer is proven on raw Windows and Linux samples of the same run;
 * the harness is proven by capturing real targets twice and comparing the two
 * runs with each other (never with the committed asset, which was made on a
 * different Python and operating system than CI uses).
 */
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import {
  hashFileLf,
  normalizeArgv,
  normalizeText,
  sha256Lf,
  sha256Raw,
  type PathAlias,
} from "../../scripts/capture/normalize";
import { buildCaptureEnv, createFixture, disposeFixtureRoot } from "../../scripts/capture/fixture";
import { runCapture, type CaptureTarget } from "../../scripts/capture/harness";
import { CAPTURE_TARGETS } from "../../scripts/capture/targets";

const repoRoot = resolve(import.meta.dirname, "..", "..", "..");

const WINDOWS_ROOT = "C:\\Users\\brenn\\AppData\\Local\\Temp\\codearbiter-capture-aB3dE9";
const LINUX_ROOT = "/tmp/codearbiter-capture-Zz91Qa";

/** One run's raw output, as each operating system would produce it. */
function rawSample(root: string, sep: string, eol: string, stamp: string, sha: string): string {
  return [
    `[${stamp}] | BY: you@example.com | GATE: design-review | REASON: retain the selector`,
    `appended mandatory override audit row: ${root}${sep}project${sep}.codearbiter${sep}overrides.log`,
    `base ${sha}`,
    `home ${root}${sep}home${sep}.claude${sep}settings.json`,
    "",
  ].join(eol);
}

const windowsRaw = rawSample(WINDOWS_ROOT, "\\", "\r\n", "2026-11-01T10:15:30Z", "0123456789abcdef0123456789abcdef01234567");
const linuxRaw = rawSample(LINUX_ROOT, "/", "\n", "2026-11-02T01:02:03Z", "fedcba9876543210fedcba9876543210fedcba98");

const aliasesFor = (root: string, sep: string): PathAlias[] => [
  { path: `${root}${sep}home`, token: "~" },
  { path: `${root}${sep}project`, token: "<project>" },
  { path: root, token: "<fixture>" },
];

describe("normalizer (AC-05)", () => {
  it("normalizes a Windows raw sample and a Linux raw sample of the same run to identical bytes", () => {
    const windows = normalizeText(windowsRaw, { aliases: aliasesFor(WINDOWS_ROOT, "\\") });
    const linux = normalizeText(linuxRaw, { aliases: aliasesFor(LINUX_ROOT, "/") });
    expect(windows).toBe(linux);
    expect(windows).toBe(
      [
        "[<timestamp>] | BY: you@example.com | GATE: design-review | REASON: retain the selector",
        "appended mandatory override audit row: <project>/.codearbiter/overrides.log",
        "base <commit>",
        "home ~/.claude/settings.json",
      ].join("\n"),
    );
  });

  it("still agrees when no roots are supplied, by recognising the fixture directory prefix", () => {
    const windows = normalizeText(windowsRaw);
    const linux = normalizeText(linuxRaw);
    expect(windows).toBe(linux);
    expect(windows).toContain("<fixture>/project/.codearbiter/overrides.log");
    expect(windows).not.toMatch(/Users|AppData|\/tmp\/|\\/);
  });

  it("replaces every spelling of one root: backslash, slash, JSON-escaped, drive case and 8.3 short name", () => {
    const short = "C:\\Users\\BRENN~1\\AppData\\Local\\Temp\\codearbiter-capture-aB3dE9\\project";
    const long = "C:\\Users\\brenn\\AppData\\Local\\Temp\\codearbiter-capture-aB3dE9\\project";
    const spellings = [
      `${long}\\sub\\file.txt`,
      `${short}\\sub\\file.txt`,
      "c:/Users/brenn/AppData/Local/Temp/codearbiter-capture-aB3dE9/project/sub/file.txt",
      "C:\\\\Users\\\\brenn\\\\AppData\\\\Local\\\\Temp\\\\codearbiter-capture-aB3dE9\\\\project\\\\sub\\\\file.txt",
      "/c/Users/brenn/AppData/Local/Temp/codearbiter-capture-aB3dE9/project/sub/file.txt",
    ];
    const aliases: PathAlias[] = [
      { path: short, token: "<project>" },
      { path: long, token: "<project>" },
    ];
    for (const spelling of spellings) {
      expect(normalizeText(`in ${spelling} done`, { aliases })).toBe("in <project>/sub/file.txt done");
    }
  });

  it("replaces ISO timestamps and leaves bare dates, digit runs and dotted numbers alone", () => {
    const raw = [
      "2026-06-27T14:30:00Z",
      "2026-06-27T14:30:00.123456+00:00",
      "2026-06-27 14:30:00",
      "date 2026-06-27 digits 20260627 dotted 1.2.3",
    ].join("\n");
    expect(normalizeText(raw)).toBe(
      ["<timestamp>", "<timestamp>", "<timestamp>", "date 2026-06-27 digits 20260627 dotted 1.2.3"].join("\n"),
    );
  });

  it("replaces 40-hex commit SHAs and leaves SHA-256 digests and abbreviated hex alone", () => {
    const commit = "0123456789abcdef0123456789abcdef01234567";
    const digest = "b2cf1a875a6ec0aa4c36e59bfdc2c9f64a81a70dcc901a5bbc46465b087e4873";
    expect(normalizeText(`commit ${commit} digest ${digest} short 0123456789ab`)).toBe(
      `commit <commit> digest ${digest} short 0123456789ab`,
    );
  });

  it("converts CRLF to LF and drops trailing blank lines", () => {
    expect(normalizeText("a\r\nb\r\n\r\n")).toBe("a\nb");
  });

  it("normalizes argv entries the same way as output", () => {
    const aliases = aliasesFor(WINDOWS_ROOT, "\\");
    expect(normalizeArgv(["--settings", `${WINDOWS_ROOT}\\home\\.claude\\settings.json`], { aliases })).toEqual([
      "--settings",
      "~/.claude/settings.json",
    ]);
  });
});

describe("source hashing (AC-05)", () => {
  it("hashes a CRLF copy and an LF copy of the same text identically", () => {
    const lf = Buffer.from("alpha\nbeta\n");
    const crlf = Buffer.from("alpha\r\nbeta\r\n");
    expect(sha256Lf(crlf)).toBe(sha256Lf(lf));
    expect(sha256Lf(lf)).toBe(createHash("sha256").update(lf).digest("hex"));
  });

  it("keeps the raw digest byte-exact, as release applicability computes it", () => {
    const lf = Buffer.from("alpha\nbeta\n");
    const crlf = Buffer.from("alpha\r\nbeta\r\n");
    expect(sha256Raw(crlf)).toBe(createHash("sha256").update(crlf).digest("hex"));
    expect(sha256Raw(crlf)).not.toBe(sha256Raw(lf));
  });

  it("does not turn a lone carriage return into a newline", () => {
    expect(sha256Lf(Buffer.from("a\rb"))).not.toBe(sha256Lf(Buffer.from("a\nb")));
  });

  it("hashes files on disk by their LF-normalized bytes", () => {
    const dir = mkdtempSync(join(tmpdir(), "capture-hash-test-"));
    try {
      writeFileSync(join(dir, "lf.py"), "x = 1\ny = 2\n");
      writeFileSync(join(dir, "crlf.py"), "x = 1\r\ny = 2\r\n");
      expect(hashFileLf(join(dir, "crlf.py"))).toBe(hashFileLf(join(dir, "lf.py")));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("capture environment (CON-03)", () => {
  it("passes an explicit minimal environment and drops everything the caller leaked in", () => {
    const polluted: NodeJS.ProcessEnv = {
      PATH: process.env.PATH ?? process.env.Path ?? "",
      SYSTEMROOT: process.env.SYSTEMROOT ?? "C:\\Windows",
      CLAUDE_PROJECT_DIR: "/leak/project",
      CLAUDE_PLUGIN_ROOT: "/leak/plugin",
      CODEARBITER_THEME: "leak",
      GIT_AUTHOR_EMAIL: "leak@example.com",
      GIT_DIR: "/leak/.git",
      ANTHROPIC_API_KEY: "sk-leak",
      PYTHONPATH: "/leak/python",
      HOME: "/leak/home",
      USERPROFILE: "/leak/home",
    };
    const fixture = { project: "/fx/project", home: "/fx/home", tmp: "/fx/tmp" };
    const env = buildCaptureEnv(polluted, fixture);
    const keys = Object.keys(env).map((key) => key.toUpperCase());
    for (const leaked of ["CLAUDE_PLUGIN_ROOT", "CODEARBITER_THEME", "GIT_AUTHOR_EMAIL", "GIT_DIR", "ANTHROPIC_API_KEY", "PYTHONPATH"]) {
      expect(keys).not.toContain(leaked);
    }
    expect(env.CLAUDE_PROJECT_DIR).toBe(fixture.project);
    expect(env.HOME).toBe(fixture.home);
    expect(env.USERPROFILE).toBe(fixture.home);
    expect(env.TMP).toBe(fixture.tmp);
    expect(env.TEMP).toBe(fixture.tmp);
    expect(env.GIT_CONFIG_NOSYSTEM).toBe("1");
    expect(env.GIT_CONFIG_GLOBAL).toContain(fixture.home.replaceAll("\\", "/"));
    expect(env.PYTHONDONTWRITEBYTECODE).toBe("1");
    expect(env.PYTHONUTF8).toBe("1");
  });
});

/** Recursive name/size/mtime listing, to prove a run wrote nothing under a directory. */
function listing(dir: string): string[] {
  const out: string[] = [];
  const walk = (current: string) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = join(current, entry.name);
      const info = statSync(full);
      out.push(`${full}|${info.size}|${info.mtimeMs}`);
      if (entry.isDirectory()) walk(full);
    }
  };
  walk(dir);
  return out.sort();
}

describe("captured runs (AC-05)", () => {
  const roots: string[] = [];
  afterAll(() => {
    for (const root of roots) rmSync(root, { recursive: true, force: true });
  });

  it("declares unique targets whose entry scripts exist in the repository", () => {
    const ids = CAPTURE_TARGETS.map((target) => target.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const target of CAPTURE_TARGETS) {
      expect(() => statSync(join(repoRoot, target.tool))).not.toThrow();
    }
  });

  it.each(CAPTURE_TARGETS.map((target) => [target.id, target] as const))(
    "captures %s twice into identical records",
    (_id, target) => {
      const first = runCapture(target);
      const second = runCapture(target);
      expect(second).toEqual(first);
      expect(JSON.stringify(second)).toBe(JSON.stringify(first));
    },
    60_000,
  );

  it.each(CAPTURE_TARGETS.map((target) => [target.id, target] as const))(
    "records argv, normalized output and a hash for every repository source of %s",
    (_id, target) => {
      const record = runCapture(target);
      expect(record.argv[0]).toBe("python");
      expect(record.argv[1]).toBe(target.tool);
      expect(record.output.length).toBeGreaterThan(0);
      const paths = record.sources.map((source) => source.path);
      expect(paths).toContain(target.tool);
      expect([...paths].sort()).toEqual(paths);
      for (const source of record.sources) {
        expect(source.sha256).toBe(hashFileLf(join(repoRoot, source.path)));
        expect(source.path).not.toMatch(/^[A-Za-z]:|\\|^\//);
      }
      const text = JSON.stringify(record);
      expect(text).not.toContain("codearbiter-capture-");
      expect(text).not.toMatch(/[A-Za-z]:\\\\|\/tmp\/|AppData|\/Users\//);
      expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
      expect(text).not.toMatch(/\b[0-9a-f]{40}\b/);
      expect(text).not.toContain("\\r");
    },
    60_000,
  );

  it("records the library modules the interpreter actually loaded, not just the entry script", () => {
    const target = CAPTURE_TARGETS.find((candidate) => candidate.id === "override-gate-row")!;
    const paths = runCapture(target).sources.map((source) => source.path);
    expect(paths).toContain("plugins/ca/hooks/append-override.py");
    expect(paths).toContain("plugins/ca/hooks/_overrideappendlib.py");
    expect(paths).toContain("plugins/ca/hooks/_hooklib.py");
    expect(paths).toContain("plugins/ca/hooks/_gitexec.py");
    expect(paths.every((path) => !path.startsWith("site/"))).toBe(true);
  }, 60_000);

  it("captures the exit status and stderr of a refusal, not only successful stdout", () => {
    const target = CAPTURE_TARGETS.find((candidate) => candidate.id === "statusline-refusal")!;
    const record = runCapture(target);
    expect(record.exitCode).toBe(1);
    expect(record.output).toMatch(/^REFUSING TO WRITE: ~\/\.claude\/settings\.json is not valid JSON \(/);
  }, 60_000);

  it("refuses to record a run whose exit code is not the declared one", () => {
    const base = CAPTURE_TARGETS.find((candidate) => candidate.id === "statusline-refusal")!;
    const wrong: CaptureTarget = { ...base, id: "wrong-exit", expectExitCode: 0 };
    expect(() => runCapture(wrong)).toThrow(/wrong-exit.*exit code 1.*expected 0/s);
  }, 60_000);

  it.each(CAPTURE_TARGETS.map((target) => [target.id, target] as const))(
    "writes nothing under the plugin tree while capturing %s",
    (_id, target) => {
      const hooks = join(repoRoot, "plugins", "ca", "hooks");
      const before = listing(hooks);
      runCapture(target);
      expect(listing(hooks)).toEqual(before);
    },
    60_000,
  );

  it("removes its temporary fixture after the run", () => {
    const fixture = createFixture();
    roots.push(fixture.root);
    const root = fixture.root;
    expect(statSync(root).isDirectory()).toBe(true);
    fixture.dispose();
    expect(() => statSync(root)).toThrow();
  });

  it("refuses to dispose a directory that is not one of its own temporary fixtures", () => {
    expect(() => disposeFixtureRoot(repoRoot)).toThrow(/non-temporary|not a capture fixture/i);
    expect(() => disposeFixtureRoot(tmpdir())).toThrow(/non-temporary|not a capture fixture/i);
    expect(statSync(repoRoot).isDirectory()).toBe(true);
  });

  it("keeps the committed hook-proof entry byte-compatible with the raw digest release applicability reads", () => {
    const proof = JSON.parse(readFileSync(join(repoRoot, "site", "src", "assets", "proof", "hook-proof.json"), "utf8"));
    const hook = readFileSync(join(repoRoot, proof.source));
    expect(proof.sourceSha256).toBe(sha256Raw(hook));
    expect(proof.sourceSha256).toBe(sha256Lf(hook));
  });
});
