import { afterEach, describe, expect, it, vi } from "vitest";
import * as fs from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { AcademySource, AcademyLessonSource } from "./academy-source";
import { generateAcademy } from "./generate-academy";
import { assertComplete } from "./owned-output";

vi.mock("node:fs", async original => {
  const actual = await original<typeof import("node:fs")>();
  return { ...actual, renameSync: vi.fn(actual.renameSync) };
});

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function lesson(id: string, track: AcademyLessonSource["track"]): AcademyLessonSource {
  return {
    id, track,
    guide: [
      "---", `id: ${id}`, `track: ${track}`, "order: 1", `title: ${id}`,
      "outcome: Owned publication fixture.", "prerequisites: none", "estimated_minutes: 1",
      "scenario_command: fixture", "checkpoint_command: fixture", "next_lab: none", "---",
      "", `# ${id}`, "", "Fixture lesson.",
    ].join("\n"),
    actions: { schema_version: 1, lesson_contract_version: 1, document_id: id, actions: [] },
  };
}

function source(): AcademySource {
  return {
    release: "fixture-old", commit: "a".repeat(40),
    home: { title: "Owned fixture", anchor: "complete-these-five-setup-steps-before-f01", steps: [] },
    lessons: [lesson("F01-foundation", "foundations"), lesson("P01-practice", "practitioner"),
      lesson("U01-advanced", "power-user")],
  };
}

function snapshot(root: string): Record<string, string> {
  return Object.fromEntries((fs.readdirSync(root, { recursive: true }) as string[])
    .filter(path => fs.lstatSync(join(root, path)).isFile()).sort()
    .map(path => [path.replaceAll("\\", "/"), fs.readFileSync(join(root, path)).toString("hex")]));
}

describe("Academy caller publication recovery", () => {
  it("restores every prior output after a late cross-root failure and converges on rerun", async () => {
    const root = fs.realpathSync(fs.mkdtempSync(join(tmpdir(), "ca-academy-publication-")));
    roots.push(root);
    const docs = join(root, "content", "docs"), generated = join(root, "generated");
    const old = source();
    generateAcademy(old, docs, generated);
    const orphan = join(docs, "academy", "000-stale.mdx");
    fs.writeFileSync(orphan, "old generated orphan\n");
    const manual = join(docs, "handwritten.mdx");
    fs.writeFileSync(manual, "handwritten keep\n");
    const foreign = join(root, "unrelated", "keep");
    fs.mkdirSync(dirname(foreign));
    fs.writeFileSync(foreign, "foreign keep\n");
    const before = snapshot(root);
    const candidate = { ...old, release: "fixture-new", commit: "b".repeat(40),
      lessons: [...old.lessons, lesson("F02-new-lesson", "foundations")] };
    const index = join(docs, "academy", "index.mdx");
    const added = join(docs, "academy", "F02-new-lesson.mdx");
    const late = join(generated, "academy-sidebar.json");
    const real = (await vi.importActual<typeof import("node:fs")>("node:fs")).renameSync;
    let faults = 0;
    vi.mocked(fs.renameSync).mockImplementation((from, to) => {
      if (String(from).endsWith(".new") && to === late) {
        expect(fs.readFileSync(index, "utf8")).toContain('release: "fixture-new"');
        expect(fs.existsSync(added)).toBe(true);
        expect(fs.existsSync(orphan)).toBe(false);
        faults++;
        throw new Error("controlled late Academy publication failure");
      }
      real(from, to);
    });
    try {
      expect(() => generateAcademy(candidate, docs, generated)).toThrow("controlled late Academy publication failure");
    } finally {
      vi.mocked(fs.renameSync).mockImplementation(real);
    }
    expect(faults).toBe(1);
    expect(snapshot(root)).toEqual(before);
    expect(fs.readdirSync(root).filter(path => path.startsWith(".generated-"))).toEqual([]);
    assertComplete(root, "academy");

    generateAcademy(candidate, docs, generated);
    expect(fs.readFileSync(index, "utf8")).toContain('release: "fixture-new"');
    expect(fs.existsSync(added)).toBe(true);
    expect(fs.existsSync(orphan)).toBe(false);
    expect(fs.readFileSync(manual, "utf8")).toBe("handwritten keep\n");
    expect(fs.readFileSync(foreign, "utf8")).toBe("foreign keep\n");
    const settled = snapshot(root);
    generateAcademy(candidate, docs, generated);
    expect(snapshot(root)).toEqual(settled);
    assertComplete(root, "academy");
  });
});
