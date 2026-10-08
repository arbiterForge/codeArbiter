import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = process.cwd();
const repoRoot = resolve(siteRoot, "..");

function readRepo(relativePath: string): string {
  return readFileSync(join(repoRoot, relativePath), "utf8");
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ");
}

describe("public trust-policy claims", () => {
  it("separates the Python hook core from the pinned native artifact runtime", () => {
    const compatibility = normalizeWhitespace(
      readRepo("site/src/content/docs/getting-started/compatibility.mdx"),
    );
    const security = normalizeWhitespace(readRepo("SECURITY.md"));

    expect(compatibility).toContain("Python hook core");
    expect(compatibility).not.toContain("no compiled binaries");
    expect(compatibility).not.toContain("Zero, for the plugin itself");
    for (const boundary of ["installation-pinned", "`ca-artifact`", "native-platform qualification", "binary digest"]) {
      expect(security).toContain(boundary);
      expect(compatibility).toContain(boundary);
    }
  });

  it("keeps the Codex farm cell within its owning backend exception", () => {
    const compatibility = readRepo("site/src/content/docs/getting-started/compatibility.mdx");
    const parity = readRepo("docs/parity.md");
    const notes = normalizeWhitespace(readRepo("core/surface/includes/codex-host-notes.md"));
    const row = compatibility.split("\n").find((line) => line.startsWith("| `/ca:sprint --farm` |"));
    const parityRow = parity.split("\n").find((line) => line.startsWith("| `--farm` |"));

    expect(row).toBeDefined();
    expect(parityRow).toBeDefined();
    const codexCell = row!.split("|")[3];
    expect(notes).toContain("premium-subagent path");
    expect(parityRow!.split("|")[3]).toContain("until backend packaging lands");
    expect(codexCell).toContain("premium-subagent path");
    expect(codexCell).toContain("backend is not packaged");
    expect(codexCell).not.toContain("shared `farm.js` backend");
  });

  it("discloses the optional tribunal KPI submission boundary", () => {
    const privacy = normalizeWhitespace(readRepo("PRIVACY.md"));

    expect(privacy).toContain("## Optional tribunal KPI feedback");
    expect(privacy).toContain("off by default");
    expect(privacy).toContain("explicit approval for that run");
    expect(privacy).toContain("public GitHub issue");
    expect(privacy).toContain("aggregate run and lens metrics");
    for (const excluded of [
      "code",
      "file paths",
      "finding text",
      "commit hashes",
      "remote URLs",
      "repository identity",
    ]) {
      expect(privacy).toContain(excluded);
    }
    expect(privacy).toContain("optional free-form `--tag`");
    expect(privacy).toContain("local `telemetry.json` receipt");
    expect(privacy).toContain("shows the complete payload");
    expect(privacy).toContain("prints a `gh issue create` command without sending it");
    expect(privacy).toContain("After an approved submission");
    expect(privacy).toContain("records a local `telemetry-sent` audit event");
    expect(privacy).toContain("GitHub handles the public issue under its own");
  });

  it("states each network activity's actual default", () => {
    const compatibility = normalizeWhitespace(
      readRepo("site/src/content/docs/getting-started/compatibility.mdx"),
    );
    const hooks = normalizeWhitespace(readRepo("docs/hooks.md"));

    expect(compatibility).not.toContain("opt-in-by-default exceptions");
    expect(compatibility).not.toContain("easy to make fully offline");
    expect(compatibility).not.toContain("README for the opt-out");
    expect(compatibility).toContain("gate-enforcement hook chain makes zero network calls");
    expect(compatibility).toContain("launched by default for an active arbiter session");
    expect(compatibility).toContain("runs automatically when its cache is stale");
    expect(compatibility).toContain("at most once per day");
    expect(compatibility).toContain("The pluggable execution farm");
    expect(compatibility).toContain("separate, explicitly opt-in feature");
    expect(hooks).toContain("launches `update-refresh.py` as a detached process");
    expect(hooks).toContain("only when the cache is stale");
    expect(hooks).toContain("checks GitHub's public Releases API");
  });

  it("keeps the public policy aligned with the tribunal's canonical contract", () => {
    const privacy = normalizeWhitespace(readRepo("PRIVACY.md"));
    const telemetry = normalizeWhitespace(readRepo(
      "core/surface/skills/tribunal/references/telemetry.md",
    ));
    const faq = readRepo("site/src/content/docs/faq.md");

    for (const boundary of [
      "off by default",
      "explicit per-run authorization",
      "public codeArbiter repository",
      "Exclude repository identity, source fingerprints, commit hashes",
      "paths, code, finding text/titles",
      "optional user-entered --tag <label>",
      "never auto-populate it",
      "--tag itself grants no send authorization",
      "telemetry-sent",
    ]) {
      expect(telemetry).toContain(boundary);
    }
    for (const boundary of [
      "This feedback is off by default",
      "Only explicit approval for that run",
      "public GitHub issue in the codeArbiter repository",
      "repository identity. A contributor can add an optional free-form `--tag`",
      "records a local `telemetry-sent` audit event",
    ]) {
      expect(privacy).toContain(boundary);
    }
    expect(privacy).toContain("tribunal telemetry contract");
    expect(normalizeWhitespace(faq)).toContain(
      "codeArbiter has no hosted account or telemetry service that receives it",
    );
  });
});
