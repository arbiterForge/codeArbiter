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
