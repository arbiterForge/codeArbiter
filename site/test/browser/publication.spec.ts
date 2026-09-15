/// <reference lib="dom" />
/** publication.spec.ts — codeArbiter's production-browser publication obligations. */
import { expect, test } from "@playwright/test";

// Chrome-only behavior against this checkout's already-built site on loopback.
// These checks do not certify screen readers, visual appearance, performance,
// other browsers, operating systems, or devices. Local runs use installed Chrome;
// GitHub-hosted CI uses runner-provided Chrome maintained by the GitHub runner image.
// No exact hosted Chrome version is claimed; CI records its observed version.
const quickstartPath = "/getting-started/quickstart/";
const quickstartTitle = "Protect Your First Repository";
const publicationViewports = [{ width: 1440, height: 900 }, { width: 390, height: 844 }];

test("AC-01: production documentation loads its expected heading", async ({ page }) => {
  const response = await page.goto(quickstartPath);
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: quickstartTitle, exact: true })).toBeVisible();
});

for (const viewport of publicationViewports) {
  test(`AC-04: Academy and search fit ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/academy/");
    await expect(page.getByRole("heading", { level: 1, name: "Learn governed delivery by doing the work.", exact: true })).toBeVisible();
    const expectNoHorizontalOverflow = async () => {
      await expect.poll(() => page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )).toBeLessThanOrEqual(0);
    };
    await expectNoHorizontalOverflow();
    const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
    const results = page.getByRole("listbox", { name: "Search results", exact: true });
    await page.keyboard.press("ControlOrMeta+k");
    await expect(search).toBeFocused();
    await search.fill(quickstartTitle);
    await expect(results).toBeVisible();
    await expect(results.getByRole("option", { name: new RegExp(`^${quickstartTitle}`) })).toBeVisible();
    await expectNoHorizontalOverflow();
    await search.press("Escape");
    await expect(results).toBeHidden();
    await expectNoHorizontalOverflow();
  });
}

test("AC-02: keyboard search restores its opener and global navigation reaches home", async ({ page }) => {
  await page.goto(quickstartPath);
  const home = page.getByRole("banner").getByRole("link", { name: /^codeArbiter/ });
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await home.focus();
  await page.keyboard.press("ControlOrMeta+k");
  await expect(search).toBeFocused();
  await search.fill(quickstartTitle);
  await expect(results).toBeVisible();
  await search.press("Escape");
  await expect(results).toBeHidden();
  await expect(search).toHaveAttribute("aria-expanded", "false");
  await expect(home).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { level: 1, name: "Hard gates for agentic coding.", exact: true })).toBeVisible();
});

test("AC-02: dismissing during debounce cannot reopen stale search results", async ({ page }) => {
  await page.goto(quickstartPath);
  const home = page.getByRole("banner").getByRole("link", { name: /^codeArbiter/ });
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await home.focus();
  await page.keyboard.press("ControlOrMeta+k");
  await search.fill(quickstartTitle);
  await search.press("Escape");
  await expect(home).toBeFocused();
  await page.waitForTimeout(500);
  await expect(results).toBeHidden();
  await expect(search).toHaveAttribute("aria-expanded", "false");
});

test("AC-02: outside dismissal invalidates in-flight Pagefind work", async ({ page }) => {
  let releasePagefind!: () => void;
  const pagefindReleased = new Promise<void>((resolve) => {
    releasePagefind = resolve;
  });
  await page.route("**/pagefind/pagefind.js", async (route) => {
    await pagefindReleased;
    await route.continue();
  });
  await page.goto(quickstartPath);
  const heading = page.getByRole("heading", { level: 1, name: quickstartTitle, exact: true });
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await page.keyboard.press("ControlOrMeta+k");
  await search.fill(quickstartTitle);
  await page.waitForTimeout(200);
  await heading.click();
  await expect(results).toBeHidden();
  releasePagefind();
  await page.waitForTimeout(500);
  await expect(results).toBeHidden();
  await expect(search).toHaveAttribute("aria-expanded", "false");
});

test("WEB-035: clearing during in-flight Pagefind work cannot reopen results", async ({ page }) => {
  let releasePagefind!: () => void;
  const pagefindReleased = new Promise<void>((resolve) => {
    releasePagefind = resolve;
  });
  await page.route("**/pagefind/pagefind.js", async (route) => {
    await pagefindReleased;
    await route.continue();
  });
  await page.goto(quickstartPath);
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await page.keyboard.press("ControlOrMeta+k");
  await search.fill(quickstartTitle);
  await page.waitForTimeout(200);
  await search.fill("");
  await expect(results).toBeHidden();
  releasePagefind();
  await page.waitForTimeout(500);
  await expect(results).toBeHidden();
  await expect(search).toHaveAttribute("aria-expanded", "false");
});

test("WEB-035: Pagefind load failure is visible and retryable", async ({ page }) => {
  let loadAttempts = 0;
  await page.route("**/pagefind/pagefind.js*", async (route) => {
    loadAttempts += 1;
    if (loadAttempts === 1) {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      contentType: "text/javascript",
      body: `
        export async function options() {}
        export async function search() {
          return { results: [{ data: async () => ({
            url: "/retry-result/",
            meta: { title: "Recovered search result" },
            excerpt: "Search recovered after retry."
          }) }] };
        }
      `,
    });
  });
  await page.goto(quickstartPath);
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await page.keyboard.press("ControlOrMeta+k");
  await search.fill("recoverable query");
  await expect(page.getByText("Search is temporarily unavailable.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retry search", exact: true }).click();
  await expect(results.getByRole("option", { name: /^Recovered search result/ })).toBeVisible();
  expect(loadAttempts).toBe(2);
});

test("WEB-035: results beyond the first eight remain reachable", async ({ page }) => {
  await page.route("**/pagefind/pagefind.js*", async (route) => {
    await route.fulfill({
      contentType: "text/javascript",
      body: `
        export async function options() {}
        export async function search() {
          return { results: Array.from({ length: 10 }, (_, index) => ({
            data: async () => ({
              url: \`/mock-result-\${index + 1}/\`,
              meta: { title: \`Mock result \${index + 1}\` },
              excerpt: \`Result \${index + 1}\`
            })
          })) };
        }
      `,
    });
  });
  await page.goto(quickstartPath);
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await page.keyboard.press("ControlOrMeta+k");
  await search.fill("many results");
  await expect(results.getByRole("option")).toHaveCount(8);
  await page.getByRole("button", { name: "Show all 10 results", exact: true }).click();
  await expect(results.getByRole("option")).toHaveCount(10);
  await expect(results.getByRole("option", { name: /^Mock result 10/ })).toBeVisible();
});

test("AC-03: Pagefind keyboard results survive client navigation and reset cleanly", async ({ page }) => {
  await page.goto("/academy/");
  // A listener attached to this document survives a client transition but not a
  // full reload, so a successful marker proves the actual client-navigation path.
  await page.evaluate(() => {
    document.addEventListener("astro:page-load", () => {
      document.documentElement.dataset.publicationClientNavigation = "observed";
    }, { once: true });
  });
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  await page.keyboard.press("ControlOrMeta+k");
  await expect(search).toBeFocused();
  await search.fill(quickstartTitle);
  const target = results.getByRole("option", { name: new RegExp(`^${quickstartTitle}`) });
  await expect(target).toHaveAttribute("href", quickstartPath);
  await search.press("ArrowDown");
  await expect(target).toHaveAttribute("aria-selected", "true");
  await expect(search).toHaveAttribute("aria-activedescendant", await target.getAttribute("id") as string);
  await search.press("Enter");
  await expect(page).toHaveURL(quickstartPath);
  await expect(page.locator("html")).toHaveAttribute("data-publication-client-navigation", "observed");
  await expect(page.getByRole("heading", { level: 1, name: quickstartTitle, exact: true })).toBeVisible();

  const home = page.getByRole("banner").getByRole("link", { name: /^codeArbiter/ });
  // Repeated open/close cycles after a client transition catch duplicate visible
  // search surfaces and shortcut handlers that steal focus from the current opener.
  for (let cycle = 0; cycle < 2; cycle += 1) {
    await home.focus();
    await page.keyboard.press("ControlOrMeta+k");
    await expect(search).toHaveCount(1);
    await expect(search).toBeFocused();
    await search.fill(quickstartTitle);
    await expect(results).toBeVisible();
    await search.fill("");
    await expect(results).toBeHidden();
    await expect(search).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("option")).toHaveCount(0);
    await search.press("Escape");
    await expect(home).toBeFocused();
  }
});
