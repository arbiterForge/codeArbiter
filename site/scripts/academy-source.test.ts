import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadAcademySource } from "./academy-source";

const fixtureRoots: string[] = [];
const fixtureLessonIds = ["F01-fork-clone-doctor", "P01-practice", "U01-operate"] as const;

const requiredTracks = [
  ["Foundation", "F01-fork-clone-doctor"],
  ["Practitioner", "P01-practice"],
  ["Power user", "U01-operate"],
] as const;

type JsonRecord = Record<string, unknown>;

function createFixture(
  manifestLessons: readonly string[] = fixtureLessonIds,
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
  for (const lessonId of fixtureLessonIds) {
    writeFileSync(
      join(academyRoot, "actions", `${lessonId}.json`),
      JSON.stringify({
        schema_version: 1,
        lesson_contract_version: 1,
        document_id: lessonId,
        actions: lessonId === "F01-fork-clone-doctor"
          ? resourceHrefs.map((href, index) => ({
              id: `F01-resource-${index}`,
              sequence: index + 1,
              title: `F01 resource ${index}`,
              actor: "learner",
              surface: "browser",
              instruction: `Open resource ${index}.`,
              rationale: null,
              resources: [{ label: `Resource ${index}`, href }],
              variants: [],
              expected_result: `Resource ${index} opens.`,
              recovery: `Recover resource ${index}.`,
              evidence: null,
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

function mutateHomeActionManifest(fixtureRoot: string, mutate: (manifest: JsonRecord) => void): void {
  const manifestPath = join(fixtureRoot, "academy-source", "academy", "actions", "home.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as JsonRecord;
  mutate(manifest);
  writeFileSync(manifestPath, JSON.stringify(manifest));
}

function homeAction(manifest: JsonRecord, index = 0): JsonRecord {
  return (manifest.actions as JsonRecord[])[index];
}

function firstHomeVariant(manifest: JsonRecord): JsonRecord {
  return (homeAction(manifest, 1).variants as JsonRecord[])[0];
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

  it.each(requiredTracks)("rejects an inventory missing the %s track", (label, missingLessonId) => {
    const fixtureRoot = createFixture(fixtureLessonIds.filter((id) => id !== missingLessonId));

    expect(() => loadAcademySource(fixtureRoot)).toThrow(new RegExp(label));
  });

  it("rejects malformed fields before routing Academy actions", () => {
    const malformedFields: Array<[string, (manifest: JsonRecord) => void]> = [
      ["schema_version", (manifest) => { manifest.schema_version = 2; }],
      ["lesson_contract_version", (manifest) => { manifest.lesson_contract_version = "1"; }],
      ["document_id", (manifest) => { manifest.document_id = "F01-fork-clone-doctor"; }],
      ["id", (manifest) => { homeAction(manifest).id = 1; }],
      ["sequence", (manifest) => { homeAction(manifest).sequence = "1"; }],
      ["title", (manifest) => { homeAction(manifest).title = 1; }],
      ["actor", (manifest) => { homeAction(manifest).actor = "student"; }],
      ["surface", (manifest) => { homeAction(manifest).surface = "terminal"; }],
      ["instruction", (manifest) => { homeAction(manifest).instruction = 1; }],
      ["rationale", (manifest) => { homeAction(manifest).rationale = false; }],
      ["resources", (manifest) => { homeAction(manifest).resources = {}; }],
      ["resource.label", (manifest) => {
        ((homeAction(manifest).resources as JsonRecord[])[0]).label = 7;
      }],
      ["resource.href", (manifest) => {
        ((homeAction(manifest).resources as JsonRecord[])[0]).href = "javascript:alert(1)";
      }],
      ["variants", (manifest) => { homeAction(manifest, 1).variants = {}; }],
      ["variant.id", (manifest) => { firstHomeVariant(manifest).id = 1; }],
      ["variant.surface", (manifest) => { firstHomeVariant(manifest).surface = "terminal"; }],
      ["variant.operating_system", (manifest) => { firstHomeVariant(manifest).operating_system = "bsd"; }],
      ["variant.host", (manifest) => { firstHomeVariant(manifest).host = "chatgpt"; }],
      ["variant.language", (manifest) => { firstHomeVariant(manifest).language = "bash"; }],
      ["variant.command", (manifest) => { firstHomeVariant(manifest).command = 1; }],
      ["variant.copy", (manifest) => { firstHomeVariant(manifest).copy = "yes"; }],
      ["expected_result", (manifest) => { homeAction(manifest).expected_result = 1; }],
      ["recovery", (manifest) => { homeAction(manifest).recovery = 1; }],
      ["evidence", (manifest) => { homeAction(manifest).evidence = false; }],
    ];

    const acceptedMalformedFields = malformedFields.flatMap(([field, mutate]) => {
      const fixtureRoot = createFixture();
      mutateHomeActionManifest(fixtureRoot, mutate);
      try {
        loadAcademySource(fixtureRoot);
        return [field];
      } catch {
        return [];
      }
    });

    expect(acceptedMalformedFields).toEqual([]);
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

  it("rejects duplicate lesson IDs in the public inventories", () => {
    const fixtureRoot = createFixture([...fixtureLessonIds, fixtureLessonIds[0]]);

    expect(() => loadAcademySource(fixtureRoot)).toThrow(/must not repeat lesson IDs/);
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
