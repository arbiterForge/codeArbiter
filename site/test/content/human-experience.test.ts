/** human-experience.test.ts — factual and navigation boundaries of the product window. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildJourneySidebar, primaryNavigation } from "../../scripts/journey-navigation";
import { loadProductExample } from "../../scripts/product-example";

const site = fileURLToPath(new URL("../..", import.meta.url));
const read = (path: string) => readFileSync(`${site}/${path}`, "utf8");

describe("human-operable product window", () => {
  it("orders learning before inventories without hiding Academy's prerequisites", () => {
    const academy = [{ label: "Foundation", collapsed: true as const, items: [{ label: "F01", slug: "academy/f01" }] }];
    const sidebar = buildJourneySidebar([], academy);
    expect(sidebar.map((group) => group.label)).toEqual(primaryNavigation.map((item) => item.label));
    expect(sidebar[0].items.map((item) => "slug" in item ? item.slug : undefined)).toEqual([
      "overview", "product-tour", "getting-started/choose-your-host", "getting-started/install",
      "guides/opt-in-a-repo", "getting-started/quickstart", "guides/first-feature", "learn", "faq",
    ]);
    expect(sidebar[3].items).toContainEqual(academy[0]);
  });

  it("keeps the exact greenfield contract separate from typed feature plans", () => {
    const guide = read("src/content/docs/guides/plan-a-new-project.mdx");
    const source = read("../core/surface/skills/decompose/SKILL.md");
    for (const filename of ["01-architecture-breakdown.md", "02-phased-build-plan.md", "03-task-backlog.md"]) {
      expect(guide).toContain(filename);
      expect(source).toContain(filename);
    }
    expect(read("src/curated/commands/decompose.md")).not.toContain("each answer lands on disk as it's given");
    expect(read("src/content/docs/guides/understand-an-existing-project.md")).toContain("does not create the greenfield three-document set");
  });

  it("does not tell new HTML sprints to use the legacy farm", () => {
    expect(read("src/content/docs/guides/autonomous-sprints.md")).toContain("HTML plans cannot use `--farm`");
    expect(read("src/content/docs/codearbiter-directory.md")).not.toContain("a plan that referenced the missing spec\nstill runs");
  });

  it("documents the current generic release selection and dry-run boundary", () => {
    const guide = read("src/content/docs/guides/releasing-a-version.md");
    expect(guide).toContain("/ca:release --dry-run");
    expect(guide).toContain("exactly one target");
    expect(guide).not.toContain("A bare `/ca:release` means `ca`");
    expect(guide).not.toContain("Invoke one of the four exact target names");
  });

  it("matches the override request to its illustrative receipt", () => {
    const guide = read("src/content/docs/guides/overriding-a-gate.md");
    expect(guide).toContain("GATE: design review");
    expect(guide).not.toContain("GATE: H-03 wildcard staging");
  });

  it("introduces setup before statusline customization", () => {
    const guide = read("src/content/docs/guides/the-statusline.md");
    expect(guide.indexOf("## Wire It In")).toBeLessThan(guide.indexOf("## Choose a Color Theme"));
  });

  it("covers the real typed diagnostic codes without binary or authority bypasses", () => {
    const guide = read("src/content/docs/guides/resume-and-recover.mdx");
    for (const code of ["CAPABILITY_MISSING", "DRAFT_BINDING", "STALE_CURSOR", "RECOVERY_REQUIRED", "COMMIT_OUTCOME_UNKNOWN"]) {
      expect(guide).toContain(code);
      expect(read("../docs/artifacts/spec-and-plan-format.md")).toContain(code);
    }
  });

  it("bounds typed authority by host rather than equating entry syntax with capability", () => {
    const source = read("../core/surface/includes/artifacts.md").replace(/\s+/g, " ");
    expect(source).toContain("Verification and review authority below is currently Codex-only");
    expect(source).toContain("Pi has no qualified pre-model prompt seam and must remain blocked");
    const guide = read("src/content/docs/guides/review-artifacts.md");
    expect(guide).toContain("## Check your host's authority capability");
    expect(guide).toContain("| Claude Code | Host-observed prompt approval | Not supported");
    expect(guide).toContain("| Codex | Host-observed prompt approval | Codex-only");
    expect(guide).toContain("| Pi | Not supported | Not supported");
    for (const path of ["guides/first-feature.mdx", "guides/feature-lane.md", "guides/autonomous-sprints.md", "concepts/artifacts.md"]) {
      expect(read(`src/content/docs/${path}`)).toContain("/guides/review-artifacts/#check-your-hosts-authority-capability");
    }
    expect(read("src/content/docs/guides/feature-lane.md")).not.toContain("The persisted artifacts and gates are the same.");
    expect(read("src/components/HostViews.astro")).toContain("verification and review authority are not supported");
  });

  it("separates the sprint review package from per-artifact approval and scope acceptance", () => {
    const adapter = read("../core/pysrc/_approvallib.py");
    expect(adapter).toContain("PENDING_APPROVAL");
    expect(adapter).toContain('"reply": f"approve {artifact_id} {token}"');
    const guide = read("src/content/docs/guides/autonomous-sprints.md");
    expect(guide).toContain("current typed adapter arms one artifact at a time");
    expect(guide).not.toContain("This is not two approvals.");
    expect(guide).not.toContain("record the accepted task state on disk");
    expect(guide).toContain("checkpoint scope together");
    expect(guide).toContain("SMARTS prerequisite authority is not supported");
  });

  it("keeps old authority receipts inspection-only rather than relabelling them after upgrade", () => {
    const source = read("../core/surface/includes/artifacts.md").replace(/\s+/g, " ");
    expect(source).toContain("Receipt format 0.1.0 remains readable for inspection after upgrade but is not authority-bearing");
    const guide = read("src/content/docs/guides/resume-and-recover.mdx");
    expect(guide).toContain("0.1.0");
    expect(guide).toContain("inspection-only");
    expect(guide).toContain("0.2.0");
    expect(guide).toContain("exact stored operation");
    expect(read("src/components/RecoveryExplorer.astro")).toContain("AUTHORITY_UNVERIFIED");
  });

  it("loads a real, draft-only native-rendered pair with complete criterion coverage", () => {
    const example = loadProductExample();
    expect(example.spec.governance.state).toBe("draft");
    expect(example.plan.governance.state).toBe("draft");
    expect(example.criteria).toHaveLength(3);
    expect(example.criteria.every((criterion) => criterion.tasks.length > 0)).toBe(true);
    expect(example.provenance.authority).toBe("unapproved documentation fixture");
  });
});
