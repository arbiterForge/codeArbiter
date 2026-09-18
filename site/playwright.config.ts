/** playwright.config.ts — codeArbiter's production-browser publication gate. */
import { defineConfig } from "@playwright/test";

// Chrome-only proof against the already-built production output on loopback.
// Hosted Chrome is maintained by the GitHub runner image:
// the npm lockfile does not authenticate browser bytes.
// No browser download: hosted and focused local runs use installed Chrome.
// No exact hosted Chrome version is claimed; CI records its observed version.
const hostedCI = process.env.GITHUB_ACTIONS === "true";
const artifactOnly = process.env.ARTIFACT_BROWSER_ONLY === "true";

export default defineConfig({
  testDir: "./test/browser",
  outputDir: "./.astro/playwright",
  fullyParallel: false,
  workers: 1,
  forbidOnly: hostedCI,
  retries: 0,
  timeout: 30_000,
  reporter: "list",
  preserveOutput: artifactOnly ? "always" : "failures-only",
  testMatch: artifactOnly ? "artifact-review.spec.ts" : undefined,
  testIgnore: artifactOnly ? undefined : "artifact-review.spec.ts",
  use: {
    baseURL: "http://127.0.0.1:4322",
    trace: hostedCI ? "retain-on-failure" : "off",
  },
  projects: [{
    name: "chrome",
    use: {
      browserName: "chromium",
      channel: "chrome",
    },
  }],
  webServer: artifactOnly ? undefined : {
    command: "npm run preview -- --host 127.0.0.1 --port 4322",
    // Astro's agent detection otherwise detaches preview, escaping runner ownership.
    env: { ASTRO_PREVIEW_BACKGROUND: "1" },
    url: "http://127.0.0.1:4322",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
