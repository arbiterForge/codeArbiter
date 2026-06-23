/** forge-allowlist-consistency.test.ts — AC-14 self-consistency drift check.
 *
 * PREVIEW_COMMANDS in forge-status.ts is hand-maintained and can drift: a typo'd
 * or stale slug would silently decorate (or fail to decorate) the wrong page.
 * This guard asserts every allowlist slug maps to a real command source file at
 * plugins/ca/commands/<slug>.md, so a bogus slug fails fast.
 *
 * Scope note: this is the UNBLOCKED self-consistency form. The stronger check —
 * reconciling the allowlist against a recorded promotion in the decision log —
 * is tracked separately (CONFIRM-05) and intentionally NOT built here. This test
 * READS plugins/ca/commands/ to check existence only; it never writes there.
 */
import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { PREVIEW_COMMANDS } from "../../scripts/generator/forge-status";

// site/test/generator -> repo root is three levels up.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const COMMANDS_DIR = join(REPO_ROOT, "plugins", "ca", "commands");

describe("PREVIEW_COMMANDS allowlist self-consistency (AC-14)", () => {
  const slugs = Object.keys(PREVIEW_COMMANDS);

  it("has at least one allowlisted slug to check", () => {
    expect(slugs.length).toBeGreaterThan(0);
  });

  for (const slug of slugs) {
    it(`slug "${slug}" maps to a real command file plugins/ca/commands/${slug}.md`, () => {
      const cmdFile = join(COMMANDS_DIR, `${slug}.md`);
      expect(existsSync(cmdFile)).toBe(true);
    });
  }
});
