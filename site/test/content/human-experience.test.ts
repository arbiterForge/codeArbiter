/** human-experience.test.ts — factual and navigation boundaries of the product window. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildJourneySidebar, primaryNavigation } from "../../scripts/journey-navigation";
import { loadProductExample } from "../../scripts/product-example";
import { repositoryVersionFacts, resolveFactTokens } from "../../scripts/version-facts";

const site = fileURLToPath(new URL("../..", import.meta.url));
const read = (path: string) => readFileSync(`${site}/${path}`, "utf8");

describe("human-operable product window", () => {
  it("orders learning before inventories without hiding Academy's prerequisites", () => {
    const academy = [{ label: "Foundation", collapsed: true as const, items: [{ label: "F01", slug: "academy/f01" }] }];
    const sidebar = buildJourneySidebar([], academy);
    expect(sidebar.map((group) => group.label)).toEqual(primaryNavigation.map((item) => item.label));
    // One linear start path (DOCS-OVERHAUL M2): choose, install, protect, complete one feature.
    expect(sidebar[0].items.map((item) => "slug" in item ? item.slug : undefined)).toEqual([
      "overview", "getting-started/choose-your-host", "getting-started/install",
      "getting-started/quickstart", "guides/first-feature", "faq",
    ]);
    expect(sidebar[3].items).toContainEqual(academy[0]);
    // The self-guided Learning Path and the product tour live with the Academy, not as rival starts.
    const academySlugs = sidebar[3].items.map((item) => "slug" in item ? item.slug : undefined);
    expect(academySlugs.slice(0, 3)).toEqual(["academy", "learn", "product-tour"]);
  });

  it("keeps the exact greenfield contract separate from typed feature plans", () => {
    const guide = read("src/content/docs/guides/plan-a-new-project.mdx");
    // Repositories that keep the Markdown format retain the three-document procedure.
    const source = read("../core/surface/skills/decompose/references/markdown-format.md");
    for (const filename of ["01-architecture-breakdown.md", "02-phased-build-plan.md", "03-task-backlog.md"]) {
      expect(guide).toContain(filename);
      expect(source).toContain(filename);
    }
    expect(read("src/curated/skills/decompose.md")).not.toContain("each answer lands on disk as it's given");
    expect(read("src/content/docs/guides/understand-an-existing-project.md")).toContain("does not create the greenfield three-document set");
  });

  it("does not tell new HTML sprints to use the legacy farm", () => {
    expect(read("src/content/docs/guides/autonomous-sprints.mdx")).toContain("HTML plans cannot use `--farm`");
    expect(read("src/content/docs/codearbiter-directory.md") + read("src/content/docs/codearbiter-directory/files.md")).not.toContain("a plan that referenced the missing spec\nstill runs");
  });

  it("documents the current generic release selection and dry-run boundary", () => {
    const guide = read("src/content/docs/guides/releasing-a-version.mdx");
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
    const normal = read("../core/surface/includes/artifacts.md").replace(/\s+/g, " ");
    expect(normal).toContain("includes/artifacts-attestation.md");
    expect(normal).not.toContain("Verification and review authority below is supported on Codex and Claude Code");
    const source = read("../core/surface/includes/artifacts-attestation.md").replace(/\s+/g, " ");
    expect(source).toContain("Verification and review authority below is supported on Codex and Claude Code");
    // Explicit historical verification/review authority remains host-limited,
    // but Pi native drafting and ordinary progress are not blocked by its
    // missing legacy prompt adapter.
    expect(normal).toContain("This includes the native Pi writer");
    expect(normal).toContain("no certification code");
    const guide = read("src/content/docs/guides/review-artifacts.md");
    expect(guide).toContain("## Check your host's authority capability");
    expect(guide).toContain("| Artifact integrity |");
    expect(guide).toContain("| Work authorization |");
    expect(guide).toContain("| Explicit attestation |");
    expect(guide).toContain("Native writer support includes Pi");
    expect(guide.replace(/\s+/g, " ")).toContain("not a prerequisite for ordinary drafting or implementation");
    for (const path of ["guides/first-feature.mdx", "guides/feature-lane.mdx", "guides/autonomous-sprints.mdx", "concepts/artifacts.md"]) {
      expect(read(`src/content/docs/${path}`)).toContain("/guides/review-artifacts/#check-your-hosts-authority-capability");
    }
    expect(read("src/content/docs/guides/feature-lane.mdx")).not.toContain("The persisted artifacts and gates are the same.");
    expect(read("src/components/HostViews.astro")).toContain("verification and review authority are not supported");
  });

  it("separates current assisted execution from explicit attestation", () => {
    const adapter = read("../core/pysrc/_approvallib.py");
    expect(adapter).toContain("PENDING_APPROVAL");
    expect(adapter).toContain('reply = f"approve {artifact_id} {token}"');
    const guide = read("src/content/docs/guides/autonomous-sprints.mdx");
    const sprint = read("../core/surface/SPRINT.md");
    expect(sprint).toContain("without a second artifact approval system");
    expect(sprint).toContain("Do not arm");
    expect(sprint).toContain("a local `DONE` batch is not a shipped release".replace("a local", "A local"));
    expect(guide).toContain("Explicit attestation has separate host support requirements");
    expect(guide).not.toContain("Historical receipt-based workflow");
    expect(guide).toContain("Ordinary plan maintenance and task progress need no additional artifact approval");
    expect(guide).toContain("REVIEW and DONE describe implementation progress");
    expect(guide).not.toContain("record the accepted task state on disk");
    expect(guide).toContain("Merge and publication need their own authorization");
  });

  it("keeps old authority receipts inspection-only rather than relabelling them after upgrade", () => {
    const normal = read("../core/surface/includes/artifacts.md").replace(/\s+/g, " ");
    expect(normal).toContain("includes/artifacts-attestation.md");
    expect(normal).not.toContain("Verification and review authority below is supported on Codex and Claude Code");
    const source = read("../core/surface/includes/artifacts-attestation.md").replace(/\s+/g, " ");
    expect(source).toContain("Receipt format 0.1.0 remains readable for inspection after upgrade but is not authority-bearing");
    const facts = repositoryVersionFacts();
    const guide = resolveFactTokens(read("src/content/docs/guides/resume-and-recover.mdx"), facts, "resume-and-recover.mdx");
    expect(facts["receipt.legacy"].value).toBe("codearbiter.receipt/0.1.0");
    expect(guide).toContain(facts["receipt.legacy"].value);
    expect(guide).toContain("inspection-only");
    expect(guide).toContain(facts["receipt.current"].value);
    expect(guide).toContain("exact stored operation");
    expect(read("src/components/RecoveryExplorer.astro")).toContain("AUTHORITY_UNVERIFIED");
  });

  it("keeps curated review guidance aligned with the producer contract", () => {
    const decompose = read("src/curated/skills/decompose.md");
    expect(decompose.replace(/\s+/g, " ")).toContain("Review all three planning documents");
    const source = read("../core/surface/skills/decompose/references/markdown-format.md").replace(/\s+/g, " ");
    expect(source).toContain("record the user's actual confirmation in `_session.md`");
    expect(source).toContain("existing confirmation covers unchanged artifacts");
    const entry = read("../core/surface/skills/decompose/SKILL.md").replace(/\s+/g, " ");
    expect(entry).toContain("Record the user's actual confirmation as an answered question");
    expect(read("src/curated/skills/brainstorming.md")).not.toContain("single test");
    expect(read("src/curated/skills/brainstorming.md")).toContain("one or more named tests");
    expect(read("../core/surface/skills/brainstorming/SKILL.md")).toContain("one or more focused tests");
    expect(read("src/content/docs/guides/review-artifacts.md")).toContain("Three exact named Markdown documents under `.codearbiter/plans/`");
    expect(read("examples/README.md")).toContain("capabilities, create, identity, validate and eligible");
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
