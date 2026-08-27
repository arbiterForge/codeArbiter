import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadAcademySource } from "./academy-source";

const fixtureRoots: string[] = [];

function createFixture(
  manifestLessons = ["F01-fork-clone-doctor", "P01-practice", "U01-operate"],
  resourceHrefs: string[] = [],
): string {
  const root = mkdtempSync(join(tmpdir(), "academy-source-"));
  fixtureRoots.push(root);
  const academyRoot = join(root, "academy-source", "academy");

  mkdirSync(join(academyRoot, "publication"), { recursive: true });
  mkdirSync(join(academyRoot, "tracks", "foundations"), { recursive: true });
  mkdirSync(join(academyRoot, "tracks", "practitioner"), { recursive: true });
  mkdirSync(join(academyRoot, "tracks", "power-user"), { recursive: true });
  mkdirSync(join(academyRoot, "actions"), { recursive: true });

  writeFileSync(
    join(academyRoot, "publication", "preview-0.30.json"),
    JSON.stringify({
      release: "preview-0.30",
      available_labs: manifestLessons,
      runnable_labs: manifestLessons,
      guided_labs: manifestLessons,
    }),
  );
  writeFileSync(
    join(academyRoot, "tracks", "foundations", "F01-fork-clone-doctor.md"),
    "---\nid: F01-fork-clone-doctor\ntrack: foundations\n---\n# Fork, clone, and doctor safety\n",
  );
  writeFileSync(
    join(academyRoot, "tracks", "practitioner", "P01-practice.md"),
    "---\nid: P01-practice\ntrack: practitioner\n---\n# Practice safely\n",
  );
  writeFileSync(
    join(academyRoot, "tracks", "power-user", "U01-operate.md"),
    "---\nid: U01-operate\ntrack: power-user\n---\n# Operate with proof\n",
  );
  mkdirSync(join(academyRoot, "guides"), { recursive: true });
  writeFileSync(
    join(academyRoot, "guides", "home.md"),
    "# Start here\n\n## Complete these five setup steps before F01\n\nComplete these steps in order before Prepare in F01:\n\n1. [Create your practice fork](#create-your-practice-fork).\n2. [Clone it to your computer](#clone-it-to-your-computer).\n3. [Enter the cloned repository](#enter-the-cloned-repository).\n4. [Verify and install the Academy tools](#verify-and-install-the-academy-tools).\n5. [Run readiness checks](#run-readiness-checks).\n\n## Create your practice fork\n\n{{action:home-fork}}\n\n## Clone it to your computer\n\n{{action:home-clone}}\n\n## Enter the cloned repository\n\n{{action:home-enter-clone}}\n\n## Verify and install the Academy tools\n\n{{action:home-install}}\n\n## Run readiness checks\n\n{{action:home-doctor}}\n",
  );
  writeFileSync(
    join(academyRoot, "actions", "home.json"),
    JSON.stringify({
      schema_version: 1,
      lesson_contract_version: 1,
      document_id: "home",
      actions: [
        ["home-fork", "Open the Academy fork page.", [{ label: "Open fork page", href: "https://example.com/fork" }], []],
        ["home-clone", "Clone your fork in a Native terminal.", [], [{
          id: "windows",
          surface: "native-terminal",
          operating_system: "windows",
          host: "none",
          language: "powershell",
          command: "git clone https://example.com/your-account/arbiter-academy.git",
          copy: true,
        }]],
        ["home-enter-clone", "Enter the cloned repository.", [], []],
        ["home-install", "Install the reviewed Academy tools.", [], []],
        ["home-doctor", "Run the Academy Doctor command.", [], []],
      ].map(([id, instruction, resources, variants], index) => ({
        id,
        sequence: index + 1,
        title: `Home setup ${index + 1}`,
        actor: "learner",
        surface: null,
        instruction,
        rationale: null,
        resources,
        variants,
        expected_result: `Setup step ${index + 1} completes.`,
        recovery: `Recover setup step ${index + 1}.`,
        evidence: null,
      })),
    }),
  );
  for (const lessonId of ["F01-fork-clone-doctor", "P01-practice", "U01-operate"]) {
    writeFileSync(
      join(academyRoot, "actions", `${lessonId}.json`),
      JSON.stringify({
        document_id: lessonId,
        actions: lessonId === "F01-fork-clone-doctor"
          ? resourceHrefs.map((href, index) => ({
              id: `F01-resource-${index}`,
              resources: [{ label: `Resource ${index}`, href }],
            }))
          : [],
      }),
    );
  }
  const submoduleRoot = join(root, "academy-source");
  execFileSync("git", ["init", "--quiet", submoduleRoot]);
  execFileSync("git", ["-C", submoduleRoot, "config", "core.autocrlf", "false"]);
  execFileSync("git", ["-C", submoduleRoot, "add", "academy"]);
  execFileSync("git", [
    "-C",
    submoduleRoot,
    "-c",
    "user.name=Academy source test",
    "-c",
    "user.email=academy-source-test@example.com",
    "commit",
    "--quiet",
    "-m",
    "Fixture source",
  ]);

  return root;
}

afterEach(() => {
  for (const root of fixtureRoots.splice(0)) rmSync(root, { force: true, recursive: true });
});

describe("loadAcademySource", () => {
  it("loads only the pinned manifest public inventory in its declared order", () => {
    const fixtureRoot = createFixture();

    const source = loadAcademySource(fixtureRoot);

    expect(source.lessons.map(({ id }) => id)).toEqual([
      "F01-fork-clone-doctor",
      "P01-practice",
      "U01-operate",
    ]);
    expect(source.commit).toBe(
      execFileSync("git", ["-C", join(fixtureRoot, "academy-source"), "rev-parse", "HEAD"], {
        encoding: "utf8",
      }).trim(),
    );
  });

  it("loads the Home guide title and five ordered setup steps", () => {
    const fixtureRoot = createFixture();

    const source = loadAcademySource(fixtureRoot);

    expect(source.home.anchor).toBe("complete-these-five-setup-steps-before-f01");
    expect(source.home.steps).toHaveLength(5);
    expect(source.home.steps[0]).toMatchObject({ title: "Create your practice fork" });
    expect(source.home.steps[0]).toMatchObject({
      anchor: "create-your-practice-fork",
      action: {
        id: "home-fork",
        instruction: "Open the Academy fork page.",
        resources: [{ label: "Open fork page", href: "https://example.com/fork" }],
      },
    });
    expect(source.home.steps[1]).toMatchObject({
      action: {
        id: "home-clone",
        variants: [{ command: "git clone https://example.com/your-account/arbiter-academy.git" }],
      },
    });
  });

  it("rejects a missing Home action manifest", () => {
    const fixtureRoot = createFixture();

    rmSync(join(fixtureRoot, "academy-source", "academy", "actions", "home.json"));

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/Home action manifest/);
  });

  it("rejects an inventory missing a required Academy track", () => {
    const fixtureRoot = createFixture(["F01-fork-clone-doctor", "U01-operate"]);

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/Practitioner/);
  });

  it("rejects a missing Home guide", () => {
    const fixtureRoot = createFixture();

    rmSync(join(fixtureRoot, "academy-source", "academy", "guides", "home.md"));

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/Home guide/);
  });

  it("rejects a malformed Home guide", () => {
    const fixtureRoot = createFixture();
    writeFileSync(
      join(fixtureRoot, "academy-source", "academy", "guides", "home.md"),
      "# Start here\n\n## Complete these five setup steps before F01\n\n1. Create your practice fork\n",
    );

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/Home guide/);
  });

  it("rejects a malformed numbered item before an otherwise valid setup sequence", () => {
    const fixtureRoot = createFixture();
    writeFileSync(
      join(fixtureRoot, "academy-source", "academy", "guides", "home.md"),
      "# Start here\n\n## Complete these five setup steps before F01\n\n1. Create your practice fork\n1. [Create your practice fork](#create-your-practice-fork).\n2. [Clone it to your computer](#clone-it-to-your-computer).\n3. [Enter the cloned repository](#enter-the-cloned-repository).\n4. [Verify and install the Academy tools](#verify-and-install-the-academy-tools).\n5. [Run readiness checks](#run-readiness-checks).\n",
    );

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/Home guide/);
  });

  it("rejects a manifest lesson outside its approved track/action paths", () => {
    const unsafeFixtureRoot = createFixture(["../../private"]);

    expect(() => loadAcademySource(unsafeFixtureRoot)).toThrow(/Academy source path/);
  });

  it("requires the same ordered lesson IDs in every public inventory", () => {
    const fixtureRoot = createFixture();
    const manifestPath = join(
      fixtureRoot,
      "academy-source",
      "academy",
      "publication",
      "preview-0.30.json",
    );
    writeFileSync(
      manifestPath,
      JSON.stringify({
        release: "preview-0.30",
        available_labs: ["F01-fork-clone-doctor"],
        runnable_labs: [],
        guided_labs: ["F01-fork-clone-doctor"],
      }),
    );

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/public inventories/);
  });

  it("accepts only HTTPS and relative Academy action resource URLs", () => {
    const fixtureRoot = createFixture(undefined, ["https://example.com/review", "/academy/f01/", "#evidence"]);

    expect(() => loadAcademySource(fixtureRoot)).not.toThrow();
  });

  it("rejects an unsafe Academy action resource URL", () => {
    const fixtureRoot = createFixture(undefined, ["javascript:alert(1)"]);

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/resource URL/);
  });
});
