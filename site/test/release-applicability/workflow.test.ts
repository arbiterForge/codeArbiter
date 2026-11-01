import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";
import { SOURCES } from "../../scripts/version-facts";

const workflowPath = fileURLToPath(
  new URL("../../../.github/workflows/docs.yml", import.meta.url),
);

function eventPaths(workflow: string, event: "push" | "pull_request"): string[] {
  const match = workflow.match(
    new RegExp(
      // Comment-only lines inside the list (docs.yml annotates groups of paths) do not end it.
      `^  ${event}:\\n[\\s\\S]*?^    paths:\\n(?<body>(?:(?:      - \\\"[^\\\"\\n]+\\\"[^\\n]*|      #[^\\n]*)\\n)+)`,
      "m",
    ),
  );
  return [...(match?.groups?.body ?? "").matchAll(/- "([^"]+)"/g)].map(
    ([, path]) => path,
  );
}

function jobBody(workflow: string, job: "site-check" | "build"): string {
  const match = workflow.match(
    new RegExp(
      `^  ${job}:\\n(?<body>[\\s\\S]*?)(?=^  [a-z][a-z-]*:|(?![\\s\\S]))`,
      "m",
    ),
  );
  if (!match?.groups?.body) throw new Error(`missing ${job} job`);
  return match.groups.body;
}

function checkoutFetchDepth(job: string): string | undefined {
  const lines = job.split("\n");
  const checkout = lines.findIndex((line) =>
    /^      - uses: actions\/checkout@/.test(line),
  );
  if (checkout < 0) return undefined;

  const nextStep = lines.findIndex(
    (line, index) => index > checkout && /^      - /.test(line),
  );
  const step = lines.slice(checkout, nextStep < 0 ? undefined : nextStep);
  const withIndex = step.findIndex((line) => /^        with:\s*$/.test(line));
  if (withIndex < 0) return undefined;

  return step
    .slice(withIndex + 1)
    .find((line) => /^          fetch-depth:\s*/.test(line))
    ?.match(/^          fetch-depth:\s*([^\s#]+)/)?.[1];
}

function runStepIndex(job: string, command: string): number {
  return job
    .split("\n")
    .findIndex((line) => line.trim() === `run: ${command}`);
}

describe("documentation release-applicability workflow contract", () => {
  const workflow = readFileSync(workflowPath, "utf8").replaceAll("\r\n", "\n");

  test("job parsing retains a final workflow job", () => {
    expect(jobBody("jobs:\n  build:\n    steps:\n      - run: npm test\n", "build"))
      .toContain("run: npm test");
  });

  test.each(["site-check", "build"] as const)(
    "%s checks out complete release history",
    (job) => {
      expect(checkoutFetchDepth(jobBody(workflow, job))).toBe("0");
    },
  );

  test("site-check generates applicability before every consumer", () => {
    const siteCheck = jobBody(workflow, "site-check");
    const generate = runStepIndex(siteCheck, "npm run gen");
    const typecheck = runStepIndex(siteCheck, "npm run typecheck");
    const tests = runStepIndex(siteCheck, "npm run coverage");

    expect(generate, "site-check has no executable generation step").toBeGreaterThan(-1);
    expect(typecheck, "site-check has no typecheck step").toBeGreaterThan(generate);
    expect(tests, "site-check has no test step").toBeGreaterThan(generate);
  });

  test("rebuilds main after every completed release run (R-05)", () => {
    // Release tags are pushed after main's own docs build, so the release itself must re-trigger.
    expect(workflow).toMatch(
      /^  workflow_run:\n    workflows: \["release"\]\n    types: \[completed\]\n    branches: \[main\]\n/m,
    );
  });

  test.each(["push", "pull_request"] as const)(
    "%s rebuilds when any version-fact source changes (R-06)",
    (event) => {
      const patterns = eventPaths(workflow, event);
      const covered = (path: string) => patterns.some((pattern) =>
        pattern.endsWith("/**") ? path.startsWith(pattern.slice(0, -2)) : path === pattern);
      expect(Object.values(SOURCES).filter((path) => !covered(path))).toEqual([]);
    },
  );

  test.each(["push", "pull_request"] as const)(
    "%s watches every release-applicability source",
    (event) => {
      expect(eventPaths(workflow, event)).toEqual(
        expect.arrayContaining([
          ".github/published-tags.json",
          ".codearbiter/release-targets.md",
        ]),
      );
    },
  );
});


describe("browser failure evidence does not bypass publication", () => {
  const workflow = readFileSync(workflowPath, "utf8").replaceAll("\r\n", "\n");
  const build = jobBody(workflow, "build");

  /** Isolate the exact named step without matching a later step's condition. */
  function step(name: string): string {
    const parts = build.split(`      - name: ${name}\n`);
    if (parts.length !== 2) throw new Error(`missing or duplicate step: ${name}`);
    return parts[1].split(/\n      - /)[0];
  }

  test("retains completed captures and bounded failure diagnostics", () => {
    expect(step("Retain browser review evidence")).toContain("if: ${{ !cancelled() }}");
    const diagnostics = step("Retain browser failure diagnostics");
    expect(diagnostics).toContain("if: ${{ failure() && steps.browser-gate.outcome == 'failure' }}");
    expect(diagnostics).toContain("path: site/.astro/playwright/");
    expect(diagnostics).toContain("retention-days: 3");
  });

  test("a failed browser gate still blocks Pages upload and deployment", () => {
    const gate = step("Browser publication gate");
    expect(gate).toContain("id: browser-gate");
    expect(gate).toContain("run: npm run test:browser");
    expect(build).not.toContain("continue-on-error:");
    expect(step("Upload Pages artifact")).not.toContain("if:");
    expect(workflow).toContain("needs: [build, site-check]");
    expect(workflow).toContain(`${"if"}: contains(fromJSON('["push","workflow_run","workflow_dispatch"]'), github.event_name) && github.ref == 'refs/heads/main'`);
  });
});
