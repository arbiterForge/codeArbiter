import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = fileURLToPath(new URL("..", import.meta.url));
const outputRoot = join(siteRoot, ".academy-non-root-dist");
const npmCli = process.env.npm_execpath;

if (!npmCli) throw new Error("npm_execpath is required to run the Academy non-root build test");

const expectedLessonLinks = [
  ["F01-fork-clone-doctor", "/docs/academy/f01-fork-clone-doctor/"],
  ["F02-orient-to-state", "/docs/academy/f02-orient-to-state/"],
  ["F03-work-the-board", "/docs/academy/f03-work-the-board/"],
  ["F04-fix-with-evidence", "/docs/academy/f04-fix-with-evidence/"],
  ["P01-feature-through-plan", "/docs/academy/p01-feature-through-plan/"],
  ["P02-commit-review-pr", "/docs/academy/p02-commit-review-pr/"],
  ["P03-record-an-adr", "/docs/academy/p03-record-an-adr/"],
  ["P04-review-a-dependency", "/docs/academy/p04-review-a-dependency/"],
  ["P05-checkpoint-remediation", "/docs/academy/p05-checkpoint-remediation/"],
  ["P06-context-drift-recovery", "/docs/academy/p06-context-drift-recovery/"],
  ["P07-threat-model", "/docs/academy/p07-threat-model/"],
  ["P08-repository-hygiene", "/docs/academy/p08-repository-hygiene/"],
  ["U01-autonomous-sprint", "/docs/academy/u01-autonomous-sprint/"],
  ["U02-override-audit-metrics", "/docs/academy/u02-override-audit-metrics/"],
  ["U03-refactor-chore-release", "/docs/academy/u03-refactor-chore-release/"],
  ["U04-initialize-projects", "/docs/academy/u04-initialize-projects/"],
  ["U05-debug-spike-conflict", "/docs/academy/u05-debug-spike-conflict/"],
  ["U06-preview-and-advanced-surfaces", "/docs/academy/u06-preview-and-advanced-surfaces/"],
  ["U07-capstone", "/docs/academy/u07-capstone/"],
];

try {
  execFileSync(
    process.execPath,
    [npmCli, "run", "build", "--", "--config", "test/fixtures/non-root-astro.config.mjs"],
    { cwd: siteRoot, stdio: "pipe" },
  );

  const academyHtml = readFileSync(join(outputRoot, "academy", "index.html"), "utf8");
  const learningHtml = readFileSync(join(outputRoot, "learn", "index.html"), "utf8");
  const inventoryLinks = [...academyHtml.matchAll(
    /data-academy-lesson="([^"]+)"[\s\S]*?<h4><a href="([^"]+)"/g,
  )].map((match) => [match[1], match[2]]);
  const startHref = academyHtml.match(/academy-overview__start-link" href="([^"]+)"/)?.[1];

  if (JSON.stringify(inventoryLinks) !== JSON.stringify(expectedLessonLinks)) {
    throw new Error(
      `Academy inventory links did not match the canonical public lesson mapping:\n` +
      `expected ${JSON.stringify(expectedLessonLinks)}\n` +
      `received ${JSON.stringify(inventoryLinks)}`,
    );
  }
  const [firstLessonId, firstLessonHref] = expectedLessonLinks[0];
  if (startHref !== firstLessonHref) {
    throw new Error(
      `expected the Academy start link for ${firstLessonId} to be ${firstLessonHref}, ` +
      `found ${startHref ?? "none"}`,
    );
  }
  if (!academyHtml.includes('href="/docs/learn/"')) {
    throw new Error("expected the Academy chooser to link to /docs/learn/");
  }
  if (!learningHtml.includes('href="/docs/academy/"')) {
    throw new Error("expected the Learning Path chooser to link to /docs/academy/");
  }

  for (const [track, count] of [["foundations", 4], ["practitioner", 8], ["power-user", 7]]) {
    const html = readFileSync(join(outputRoot, "academy", "tracks", track, "index.html"), "utf8");
    if ((html.match(/data-academy-track-lesson=/g) ?? []).length !== count ||
        !html.includes('data-base="/docs"') || !html.includes('href="/docs/academy/#setup"')) {
      throw new Error(`Academy ${track} track lost its source inventory or base path`);
    }
  }
  for (const [id, href] of expectedLessonLinks) {
    const html = readFileSync(join(outputRoot, "academy", id.toLowerCase(), "index.html"), "utf8");
    if (!html.includes('data-base="/docs"') || !html.includes('href="/docs/academy/#academy-curriculum"')) {
      throw new Error(`Academy ${id} wayfinding lost its base path`);
    }
    for (const match of html.matchAll(/href="([^"]+)" rel="(?:prev|next)"/g)) {
      const destination = new URL(match[1], `https://example.invalid${href}`);
      if (!expectedLessonLinks.some(([, expected]) => destination.pathname === expected)) {
        throw new Error(`Academy ${id} pagination escaped its published curriculum: ${destination.pathname}`);
      }
    }
  }

  // These three guides use MDX HTML for retained diagrams and the authority link.
  // Inspect built bytes so unit fixtures cannot mask a missing MDX transform.
  for (const [slug, diagram] of [["opt-in-a-repo", "lane-opt-in"], ["feature-lane", "lane-feature"], ["autonomous-sprints", "lane-sprint"]]) {
    const html = readFileSync(join(outputRoot, "guides", slug, "index.html"), "utf8");
    const map = html.match(/<section[^>]*data-reader-journey=[\s\S]*?<\/section>/)?.[0];
    const links = [...(map ?? "").matchAll(/href="([^"]+)"/g)].map(match => match[1]);
    if (links.length !== 4 || links.some(href => !href.startsWith("/docs/")) ||
        !(html.includes(`src="/docs/diagrams/${diagram}.svg"`) ||
          (slug !== "feature-lane" && html.includes(`href="/docs/diagrams/${diagram}.svg"`) && html.includes('data-workflow=')))) {
      throw new Error(`Reader map ${slug} lost a base-prefixed link or implementation diagram`);
    }
    readFileSync(join(outputRoot, "diagrams", `${diagram}.svg`));
    if (slug === "feature-lane" && !html.includes('href="/docs/guides/review-artifacts/#check-your-hosts-authority-capability"')) {
      throw new Error("The feature guide's raw MDX authority link escaped /docs/");
    }
  }
  process.stdout.write("Reader maps: all twelve links and three retained diagrams remain beneath /docs/.\n");

  const expectedGuideIds = readdirSync(join(siteRoot, "src", "content", "docs", "guides"))
    .filter(name => /\.mdx?$/.test(name) && !/^index\./.test(name))
    .map(name => `guides/${name.replace(/\.mdx?$/, "")}`).sort();
  const guideIndex = readFileSync(join(outputRoot, "guides", "index.html"), "utf8");
  // Validate the component's actual substantive content, not just its short MDX shell.
  const directoryHtml = guideIndex.match(/<ca-guide-directory\b[\s\S]*?<\/ca-guide-directory>/)?.[0] ?? "";
  const sectionIds = [...directoryHtml.matchAll(/<h2\b[^>]*id="([^"]+)"/g)].map(match => match[1]);
  const expectedSections = ["initialize-and-understand", "make-a-change", "review-and-ship", "operate-and-recover", "practice-and-advanced-tooling"];
  // Measure only the generated component's plain text nodes. This is not an HTML
  // sanitizer and its output is never rendered. Scripts are not valid directory
  // content; reject them instead of attempting to strip or repair HTML.
  if (/<\s*script\b/i.test(directoryHtml)) {
    throw new Error("The guide directory must keep executable scripts outside its content");
  }
  const visibleDirectoryText = [...directoryHtml.matchAll(/<(?:h2|a|p|dt|dd)\b[^>]*>([^<>]+)</g)]
    .map(([, text]) => text).join(" ");
  const cardContent = [...directoryHtml.matchAll(/<li\b[^>]*data-guide-entry="([^"]+)"[\s\S]*?<\/li>/g)];
  if (JSON.stringify(sectionIds) !== JSON.stringify(expectedSections) ||
      (visibleDirectoryText.match(/\b[\p{L}\p{N}][\p{L}\p{N}'-]*\b/gu)?.length ?? 0) < 250 ||
      cardContent.length !== expectedGuideIds.length || cardContent.some(([card]) =>
        !/<p\b[^>]*>[^<]+<\/p>/.test(card) || !card.includes("Guide estimate") || !card.includes("Level"))) {
    throw new Error("The rendered guide directory lost substantive sections, outcomes or context");
  }
  const guideCards = [...guideIndex.matchAll(/data-guide-entry="([^"]+)"[\s\S]*?<h3\b[^>]*><a\b[^>]*href="([^"]+)"/g)];
  if (JSON.stringify(guideCards.map(([, id]) => id).sort()) !== JSON.stringify(expectedGuideIds) || guideCards.some(([, id, href]) => href !== `/docs/${id}/`)) {
    throw new Error("The guide finder lost an entry or escaped the /docs/ base");
  }
  for (const [, id] of guideCards) readFileSync(join(outputRoot, id, "index.html"));
  const delivery = readFileSync(join(outputRoot, "guides", "review-and-ship", "index.html"), "utf8");
  const deliveryMap = delivery.match(/<section[^>]*data-reader-journey="review-delivery-map"[\s\S]*?<\/section>/)?.[0] ?? "";
  const deliveryLinks = [...deliveryMap.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
  if (deliveryLinks.length !== 4 || deliveryLinks.some(href => !href.startsWith("/docs/"))) {
    throw new Error("The review-to-delivery map escaped the /docs/ base");
  }
  const dependency = readFileSync(join(outputRoot, "guides", "adding-a-dependency", "index.html"), "utf8");
  const dependencyMap = dependency.match(/<section[^>]*data-reader-journey="dependency-decision-map"[\s\S]*?<\/section>/)?.[0] ?? "";
  const dependencyLinks = [...dependencyMap.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
  if (dependencyLinks.length !== 4 || dependencyLinks.some(href => !href.startsWith("/docs/")) ||
      !dependency.includes('href="/docs/diagrams/lane-add-dep.svg"') || !dependency.includes('data-workflow="dependency"') ||
      !dependency.includes('id="one-time-inspection-nothing-adopted"') ||
      !dependency.includes('data-ca-table="stacked"') ||
      !dependency.includes('No package was downloaded or executed')) {
    throw new Error("The dependency guide lost its base-prefixed reading map, diagram, decision or example boundary");
  }
  const dependencyReference = readFileSync(join(outputRoot, "reference", "commands", "add-dep", "index.html"), "utf8");
  if (!dependencyReference.includes('href="/docs/guides/adding-a-dependency/"') ||
      !dependencyReference.includes('One-time inspection')) {
    throw new Error("The dependency reference lost the bounded one-time path or its non-root guide link");
  }
  process.stdout.write("Dependency guide: all four map links, bounded-tool decision and retained diagram remain beneath /docs/.\n");
  // Verify table enhancement on actual MDX output, not only the AST unit fixture.
  for (const slug of ["review-and-ship", "investigate-and-fix"]) {
    const html = readFileSync(join(outputRoot, "guides", slug, "index.html"), "utf8");
    if (!html.includes('data-ca-table="stacked"') || !html.includes('class="ca-table-cell-value"')) {
      throw new Error(`The ${slug} guide lost its single-source mobile table presentation`);
    }
  }
  process.stdout.write(`Guide discovery: ${expectedGuideIds.length} guides, four delivery-map links and mobile table content remain beneath /docs/.\n`);

  for (const route of ["concepts", "concepts/gated-lanes", "concepts/test-first"]) {
    const html = readFileSync(join(outputRoot, route, "index.html"), "utf8");
    const model = html.match(/<ca-execution-map\b[\s\S]*?<\/ca-execution-map>/)?.[0] ?? "";
    const steps = [...model.matchAll(/data-map-step="([^"]+)"/g)];
    const localLinks = [...model.matchAll(/href="(\/[^"]+)"/g)].map(match => match[1]);
    if (steps.length !== 16 || new Set(steps.map(match => match[1])).size !== 16 ||
        localLinks.length < 16 || localLinks.some(href => !href.startsWith("/docs/"))) {
      throw new Error(`Concept execution map ${route} lost its complete reading path or base-prefixed links`);
    }
  }
  process.stdout.write("Concepts: all three execution maps preserve 16 steps and /docs/ destinations.\n");

  // C04: check the real model output, not just an imported component tag.
  const c04 = [
    ["autonomous-sprints", "sprint", 15], ["adding-a-dependency", "dependency", 4],
    ["recording-adrs", "adr", 7], ["releasing-a-version", "release", 13],
    ["opt-in-a-repo", "greenfield", 8], ["opt-in-a-repo", "brownfield", 9],
  ];
  for (const [slug, id, count] of c04) {
    const html = readFileSync(join(outputRoot, "guides", slug, "index.html"), "utf8");
    const map = html.match(new RegExp(`<ca-execution-map[^>]*id="(?:init-)?${id}(?:-execution-map)?"[\\s\\S]*?<\\/ca-execution-map>`))?.[0] ?? "";
    const steps = [...map.matchAll(/data-map-step="([^"]+)"/g)];
    const links = [...map.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
    if (steps.length !== count || !links.length || links.some(href => href.startsWith("/") && !href.startsWith("/docs/"))) {
      throw new Error(`C04 ${id} lost its full ordered text or a base-prefixed destination`);
    }
  }
  const routes = readFileSync(join(outputRoot, "concepts", "workflow-routes", "index.html"), "utf8");
  if ((routes.match(/data-workflow-link=/g) ?? []).length !== c04.length) throw new Error("Workflow comparison lost a route");
  process.stdout.write("C04: all six workflow maps retain 56 stages and /docs/ destinations.\n");

  process.stdout.write("Academy non-root base build: 19 lesson links, three tracks, bookmarks and lesson pagination remain beneath /docs/.\n");
  for (const slug of ["smarts", "adrs", "checkpoints", "auditability"]) {
    const html = readFileSync(join(outputRoot, "concepts", slug, "index.html"), "utf8");
    const contract = {
      smarts: ['data-smarts-lens="scalable"', 'data-decision-route="reconcile"', 'data-decision-route="sprint"'],
      adrs: ['data-evidence-case="accepted"', 'data-evidence-case="verified"', 'data-evidence-case="stale"'],
      checkpoints: ['data-checkpoint-step="sweep-verdict"', 'data-checkpoint-step="sweep-write"', 'data-checkpoint-step="sweep-return"'],
      auditability: ['data-evidence-case="choice"', 'data-evidence-case="packet"'],
    }[slug];
    if (!contract.every(value => html.includes(value))) throw new Error(`C02 ${slug} lost its evidence content`);
    for (const [, href] of html.matchAll(/href="(\/(?:concepts|guides|reference)\/[^"]*)"/g)) {
      throw new Error(`C02 ${slug} link escaped the base: ${href}`);
    }
  }
  process.stdout.write("C02: comparison, caller routes, ADR/audit views and seven-step checkpoint remain beneath /docs/.\n");

  for (const slug of ["provenance-drift", "jit-context-injection", "persona-and-context"]) {
    const html = readFileSync(join(outputRoot, "concepts", slug, "index.html"), "utf8");
    if (slug === "persona-and-context") {
      if (!html.includes('id="roles-task-handoff"') ||
          (html.match(/data-map-step=/g) ?? []).length !== 16) {
        throw new Error("C03 role separation lost the complete feature handoff");
      }
    } else if ((html.match(/data-context-case=/g) ?? []).length !== 4 ||
               !html.includes('href="/docs/examples/context-observations.json"')) {
      throw new Error(`C03 ${slug} lost its recorded helper evidence or data link`);
    }
    for (const [, href] of html.matchAll(/(?:href|src)="(\/(?:concepts|guides|reference|diagrams|examples)\/[^"]*)"/g)) {
      throw new Error(`C03 ${slug} destination escaped the base: ${href}`);
    }
  }
  const servedCapture = JSON.parse(readFileSync(join(outputRoot, "examples", "context-observations.json"), "utf8"));
  const sourceCapture = JSON.parse(readFileSync(join(siteRoot, "src", "data", "context-examples.json"), "utf8"));
  if (JSON.stringify(servedCapture) !== JSON.stringify(sourceCapture)) throw new Error("Context evidence endpoint differs from its capture");
  process.stdout.write("C03: all recorded context cases, full role map and exact JSON evidence remain beneath /docs/.\n");

} finally {
  rmSync(outputRoot, { force: true, recursive: true });
}
