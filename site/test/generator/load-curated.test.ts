import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { loadCurated } from "../../scripts/generator/load-curated";

const base = join(tmpdir(), "ca-load-curated-test");

function writeCurated(relPath: string, content: string) {
  const full = join(base, relPath);
  mkdirSync(join(full, ".."), { recursive: true });
  writeFileSync(full, content);
}

describe("loadCurated", () => {
  beforeEach(() => {
    rmSync(base, { recursive: true, force: true });
    mkdirSync(base, { recursive: true });
  });
  afterEach(() => {
    rmSync(base, { recursive: true, force: true });
  });

  it("returns an empty map when the curated dir does not exist", () => {
    const result = loadCurated(join(base, "does-not-exist"), new Set(["commands/sprint"]));
    expect(result.size).toBe(0);
  });

  it("parses a curated file's entity, body, related, and gates", () => {
    writeCurated(
      "commands/sprint.md",
      `---
entity: commands/sprint
related: [commit, skills/tdd]
gates:
  - gate: spec approval
    when: before execution
    effect: hard stop
---

## What it does

Curated prose about sprint.
`,
    );
    const result = loadCurated(base, new Set(["commands/sprint"]));
    const doc = result.get("commands/sprint");
    expect(doc).toBeDefined();
    expect(doc!.entity).toBe("commands/sprint");
    expect(doc!.related).toEqual(["commit", "skills/tdd"]);
    expect(doc!.gates).toEqual([
      { gate: "spec approval", when: "before execution", effect: "hard stop" },
    ]);
    expect(doc!.body).toContain("Curated prose about sprint.");
  });

  it("returns undefined (falls back) for a collected source with no curated file", () => {
    writeCurated(
      "commands/sprint.md",
      `---\nentity: commands/sprint\n---\n\nBody.\n`,
    );
    const result = loadCurated(base, new Set(["commands/sprint", "commands/commit"]));
    expect(result.get("commands/commit")).toBeUndefined();
    expect(result.get("commands/sprint")).toBeDefined();
  });

  it("throws on an orphan curated file (entity has no matching collected source), naming the filename", () => {
    writeCurated(
      "commands/ghost.md",
      `---\nentity: commands/ghost\n---\n\nBody.\n`,
    );
    expect(() => loadCurated(base, new Set(["commands/sprint"]))).toThrow(/ghost\.md/);
  });

  it("throws on duplicate curated files declaring the same entity", () => {
    writeCurated(
      "commands/sprint.md",
      `---\nentity: commands/sprint\n---\n\nBody A.\n`,
    );
    // A second, differently-named file that (mistakenly) declares the same
    // entity — a genuine duplicate, not merely a filename collision.
    writeCurated(
      "commands/sprint-old.md",
      `---\nentity: commands/sprint\n---\n\nBody B.\n`,
    );
    expect(() =>
      loadCurated(base, new Set(["commands/sprint"])),
    ).toThrow(/[Dd]uplicate/);
  });
});
