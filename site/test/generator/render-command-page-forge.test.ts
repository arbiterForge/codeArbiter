/** render-command-page-forge.test.ts — codeArbiter's preview badge/callout rendering tests. */
import { describe, it, expect } from "vitest";
import { renderCommandPage } from "../../scripts/generator/render-command-page";

describe("renderCommandPage — forge status badges and callouts", () => {
  it("renders a preview badge for a preview-command (prune)", () => {
    const md = renderCommandPage({
      name: "/ca:prune",
      description: "Trim transcript clutter.",
      forgeStatus: { kind: "preview-command" },
    });
    // Must contain the badge with data-kind="preview"
    expect(md).toContain('class="ca-badge"');
    expect(md).toContain('data-kind="preview"');
    expect(md).toContain("preview");
  });

  it("renders a --farm preview callout for a preview-flag (sprint)", () => {
    const md = renderCommandPage({
      name: "/ca:sprint",
      description: "Autonomous sprint.",
      forgeStatus: { kind: "preview-flag", flag: "--farm" },
    });
    // Must contain the preview callout with the flag name
    expect(md).toContain("ca-callout--preview");
    expect(md).toContain("--farm");
    expect(md).toContain("preview");
  });

  it("does NOT render a badge or callout for a stable command (commit)", () => {
    const md = renderCommandPage({
      name: "/ca:commit",
      description: "Run the full commit gate.",
      forgeStatus: null,
    });
    expect(md).not.toContain("ca-badge");
    expect(md).not.toContain("ca-callout--preview");
  });

  it("does NOT render a badge or callout when forgeStatus is omitted", () => {
    const md = renderCommandPage({
      name: "/ca:commit",
      description: "Run the full commit gate.",
    });
    expect(md).not.toContain("ca-badge");
    expect(md).not.toContain("ca-callout--preview");
  });

  it("preview-flag callout uses the contract callout classes", () => {
    const md = renderCommandPage({
      name: "/ca:sprint",
      description: "Autonomous sprint.",
      forgeStatus: { kind: "preview-flag", flag: "--farm" },
    });
    // Must carry both base class and variant modifier
    expect(md).toContain("ca-callout");
    expect(md).toContain("ca-callout--preview");
  });

  it("preview-command badge uses the contract badge class and data-kind attribute", () => {
    const md = renderCommandPage({
      name: "/ca:prune",
      description: "Trim transcript clutter.",
      forgeStatus: { kind: "preview-command" },
    });
    expect(md).toContain('class="ca-badge"');
    expect(md).toContain('data-kind="preview"');
  });

  it("preview-command badge is the first body element, before the description", () => {
    const md = renderCommandPage({
      name: "/ca:prune",
      description: "Trim transcript clutter.",
      forgeStatus: { kind: "preview-command" },
    });
    // Body starts after the closing frontmatter `---` fence.
    const body = md.slice(md.indexOf("---", 3) + 3);
    const badgeIndex = body.indexOf('class="ca-badge"');
    const descIndex = body.indexOf("Trim transcript clutter.");
    expect(badgeIndex).toBeGreaterThan(-1);
    expect(descIndex).toBeGreaterThan(badgeIndex);
  });

  it("preview-flag callout is the first body element, before the description", () => {
    const md = renderCommandPage({
      name: "/ca:sprint",
      description: "Autonomous sprint.",
      forgeStatus: { kind: "preview-flag", flag: "--farm" },
    });
    // Body starts after the closing frontmatter `---` fence.
    const body = md.slice(md.indexOf("---", 3) + 3);
    const calloutIndex = body.indexOf("ca-callout--preview");
    const descIndex = body.indexOf("Autonomous sprint.");
    expect(calloutIndex).toBeGreaterThan(-1);
    expect(descIndex).toBeGreaterThan(calloutIndex);
  });
});
