/// <reference lib="dom" />
/** publication.spec.ts — codeArbiter's production-browser publication obligations. */
import { expect, test, type Browser, type Page } from "@playwright/test";

// Chrome-only behavior against this checkout's already-built site on loopback.
// These checks do not certify screen readers, visual appearance, performance,
// other browsers, operating systems, or devices. Local runs use installed Chrome;
// GitHub-hosted CI uses runner-provided Chrome maintained by the GitHub runner image.
// No exact hosted Chrome version is claimed; CI records its observed version.
const quickstartPath = "/getting-started/quickstart/";
const quickstartTitle = "Protect Your First Repository";
const publicationViewports = [{ width: 1440, height: 900 }, { width: 390, height: 844 }];

const qualitySearchCases = [
  { query: quickstartTitle, expectedPath: quickstartPath },
  { query: "data leaves my machine", expectedPath: "/faq/" },
  { query: "privacy", expectedPath: "/trust/" },
  { query: "install Pi", expectedPath: "/getting-started/pi/" },
  { query: "override", expectedPath: "/guides/overriding-a-gate/" },
];

const qualityRouteCases = [
  {
    path: "/",
    status: 200,
    title: "codeArbiter: Agentic Coding Governance for Claude Code, Codex & Pi",
    description: "codeArbiter is an open-source governance layer for AI coding agents, with repository-owned hard gates, reviews, audit trails, and durable project context for Claude Code, Codex, and Pi.",
    canonicalPath: "/",
    h1: "codeArbiter: hard gates for agentic coding.",
  },
  {
    path: "/overview/",
    status: 200,
    title: "What is Code Arbiter? | codeArbiter",
    description: "What is Code Arbiter? Open-source agentic coding governance for Claude Code, Codex, and Pi, with development gates and repository-owned project records.",
    canonicalPath: "/overview/",
    h1: "What is Code Arbiter?",
  },
  {
    path: "/academy/",
    status: 200,
    title: "Arbiter Academy | codeArbiter",
    description: "Guided, evidence-based practice for the codeArbiter workflow.",
    canonicalPath: "/academy/",
    h1: "Learn governed delivery by doing the work.",
  },
  {
    path: "/checkpoint-058-missing-route/",
    status: 404,
    title: "This path has no gate | codeArbiter",
    description: "The requested documentation route does not exist. Start from the beginning or search the source-backed reference.",
    canonicalPath: "/404/",
    h1: "This path has no gate",
  },
];

async function observeMobileQuality(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "load" });
  const opener = page.locator(".ca-docs-rail__opener");
  const drawer = page.getByRole("dialog", { name: "Documentation navigation", exact: true });
  const openerLabel = await opener.getAttribute("aria-label");
  await opener.focus();
  await page.keyboard.press("Enter");
  await drawer.waitFor({ state: "visible" });
  const opened = await drawer.isVisible();
  const openedExpanded = await opener.getAttribute("aria-expanded");
  const focusMovedInside = await drawer.evaluate((element) => element.contains(document.activeElement));
  const backgroundInert = await page.locator("body > [inert], header[inert]").count() > 0;
  const scrollLocked = await page.evaluate(() => document.body.style.overflow === "hidden");
  await page.keyboard.press("Escape");
  await drawer.waitFor({ state: "hidden" });
  const closedOnEscape = await drawer.isHidden();
  const closedExpanded = await opener.getAttribute("aria-expanded");
  const focusRestored = await opener.evaluate((element) => document.activeElement === element);
  const overflowByWidth: Record<number, number> = {
    390: await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    320: 1,
  };
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/", { waitUntil: "load" });
  overflowByWidth[320] = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await opener.focus();
  const forcedColorsActive = await page.evaluate(() => matchMedia("(forced-colors: active)").matches);
  const focusStyle = await opener.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });

  return {
    openerLabel,
    opened,
    openedExpanded,
    focusMovedInside,
    backgroundInert,
    scrollLocked,
    closedOnEscape,
    closedExpanded,
    focusRestored,
    overflowByWidth,
    forcedColorsActive,
    focusOutlineStyle: focusStyle.outlineStyle,
    focusOutlineWidth: focusStyle.outlineWidth,
  };
}

async function observeHomepageStructureAndSearch(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "load" });
  // The outcomes render as a plain list (DOCS-OVERHAUL M5); each item keeps its heading.
  const outcomes = page.getByRole("region", { name: "What changes when codeArbiter is active.", exact: true }).getByRole("list");
  const listItems = outcomes.getByRole("listitem");
  const headingsByListItem = [];
  for (const listItem of await listItems.all()) {
    headingsByListItem.push(await listItem.getByRole("heading", { level: 3 }).innerText());
  }
  const search = page.getByRole("combobox", { name: "Search the docs", exact: true });
  const results = page.getByRole("listbox", { name: "Search results", exact: true });
  const rankings = [];
  for (const { query } of qualitySearchCases) {
    await page.keyboard.press("ControlOrMeta+k");
    await search.fill(query);
    await results.waitFor({ state: "visible" });
    rankings.push({
      query,
      firstPath: await results.getByRole("option").first().getAttribute("href") ?? "",
    });
    await search.press("Escape");
  }

  return {
    listItemCount: await listItems.count(),
    headingsByListItem,
    rankings,
  };
}

async function observeRouteAndPerformanceQuality(browser: Browser) {
  const baseURL = "http://127.0.0.1:4322";
  const routes = [];
  let custom404Actions: string[] = [];
  for (const { path } of qualityRouteCases) {
    const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    const response = await page.goto(path, { waitUntil: "load" });
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href") ?? "";
    routes.push({
      path,
      status: response?.status() ?? 0,
      title: await page.title(),
      description: await page.locator('meta[name="description"]').getAttribute("content") ?? "",
      canonicalPath: new URL(canonical, baseURL).pathname,
      visibleH1Count: await page.locator("h1:visible").count(),
      h1: await page.locator("h1:visible").innerText(),
    });
    if (path === "/checkpoint-058-missing-route/") {
      custom404Actions = await Promise.all([
        "Start here",
        "Search the reference",
        "Return home",
      ].map(async (name) => await page.getByRole("link", { name, exact: true }).getAttribute("href") ?? ""));
    }
    await context.close();
  }

  const observations = [];
  for (const path of ["/", "/overview/", "/academy/"]) {
    const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto(path, { waitUntil: "load" });
    observations.push(await page.evaluate((currentPath) => {
      const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
      return {
        path: currentPath,
        loadEventEnd: navigation.loadEventEnd,
        resourceCount: resources.length,
        observedTransferBytes: resources.reduce((sum, resource) => sum + resource.transferSize, 0),
      };
    }, path));
    await context.close();
  }

  return {
    routes,
    custom404Actions,
    observations,
  };
}

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
  await expect(page.getByRole("heading", { level: 1, name: "codeArbiter: hard gates for agentic coding.", exact: true })).toBeVisible();
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

test("WEB-008 + WEB-030: mobile navigation preserves its accessible reflow contract", async ({ page }) => {
  const evidence = await observeMobileQuality(page);

  expect(evidence.openerLabel).toBe("Open documentation navigation");
  expect(evidence.opened).toBe(true);
  expect(evidence.openedExpanded).toBe("true");
  expect(evidence.focusMovedInside).toBe(true);
  expect(evidence.backgroundInert).toBe(true);
  expect(evidence.scrollLocked).toBe(true);
  expect(evidence.closedOnEscape).toBe(true);
  expect(evidence.closedExpanded).toBe("false");
  expect(evidence.focusRestored).toBe(true);
  expect(evidence.overflowByWidth).toEqual({ 390: 0, 320: 0 });
  expect(evidence.forcedColorsActive).toBe(true);
  expect(evidence.focusOutlineStyle).not.toBe("none");
  expect(Number.parseFloat(evidence.focusOutlineWidth)).toBeGreaterThan(0);
});

test("WEB-016 + WEB-027: homepage structure and representative search rankings stay usable", async ({ page }) => {
  const evidence = await observeHomepageStructureAndSearch(page);

  expect(evidence.listItemCount).toBe(3);
  expect(evidence.headingsByListItem).toEqual([
    "It stops at the tool boundary",
    "The record lives in your repository",
    "Every bypass leaves a trail",
  ]);
  expect(evidence.rankings).toEqual(qualitySearchCases.map(({ query, expectedPath }) => ({
    query,
    firstPath: expectedPath,
  })));
});

test("WEB-033: route contracts and fresh-cache post-load observations remain recordable", async ({ browser }, testInfo) => {
  const evidence = await observeRouteAndPerformanceQuality(browser);

  expect(evidence.routes).toEqual(qualityRouteCases.map((route) => ({ ...route, visibleH1Count: 1 })));
  expect(evidence.custom404Actions).toEqual(["/overview/", "/reference/", "/"]);
  expect(evidence.observations.map(({ path }) => path)).toEqual(["/", "/overview/", "/academy/"]);
  for (const observation of evidence.observations) {
    expect(observation.loadEventEnd).toBeGreaterThan(0);
    expect(observation.resourceCount).toBeGreaterThan(0);
    expect(observation.observedTransferBytes).toBeGreaterThanOrEqual(0);
  }
  console.info("checkpoint-058 fresh-cache observations", JSON.stringify(evidence.observations));
  await testInfo.attach("checkpoint-058-fresh-cache-observations", {
    body: Buffer.from(JSON.stringify(evidence.observations, null, 2)),
    contentType: "application/json",
  });
});

// These acceptance setups modify only existing built DOM state. No fixture HTML
// or replacement drawer script stands in for the original Pages payload.
async function openBuiltDocumentationDrawer(page: Page) {
  const baseURL = test.info().project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("A loopback base URL is required");
  const origin = new URL(baseURL);
  if (origin.protocol !== "http:" || origin.hostname !== "127.0.0.1" || origin.username || origin.password) {
    throw new Error("Built drawer acceptance requires the owned loopback server");
  }
  await page.route("**/*", route => {
    const requested = new URL(route.request().url());
    return requested.origin === origin.origin || requested.protocol === "data:" || requested.protocol === "blob:"
      ? route.continue() : route.abort("blockedbyclient");
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator("ca-splash-docs")).toHaveAttribute("data-initialized", "true");
  return page.locator("ca-splash-docs .ca-docs-rail__opener");
}

async function observedDrawerBackgrounds(page: Page) {
  return page.evaluate(() => ({
    overflow: document.body.style.overflow,
    backgrounds: Array.from(document.querySelectorAll<HTMLElement>("[data-drawer-acceptance-background]"))
      .map(node => ({ index: Number(node.dataset.drawerAcceptanceBackground), inert: node.inert, ariaHidden: node.getAttribute("aria-hidden") }))
      .sort((a, b) => a.index - b.index),
  }));
}

test("S62: backdrop restores heterogeneous saved background and scroll state", async ({ page }) => {
  const opener = await openBuiltDocumentationDrawer(page);
  const seeded = await page.locator("ca-splash-docs").evaluate(element => {
    const nodes = [...new Set([
      document.querySelector<HTMLElement>("header"),
      ...Array.from(element.parentElement!.children).filter((node): node is HTMLElement => node instanceof HTMLElement && node !== element),
    ].filter((node): node is HTMLElement => node instanceof HTMLElement))];
    document.body.style.overflow = "clip";
    nodes.forEach((node, index) => {
      node.dataset.drawerAcceptanceBackground = String(index);
      node.inert = index % 2 === 0;
      if (index % 3 === 0) node.removeAttribute("aria-hidden");
      else node.setAttribute("aria-hidden", index % 3 === 1 ? "false" : "true");
    });
    return {
      overflow: document.body.style.overflow,
      backgrounds: nodes.map((node, index) => ({ index, inert: node.inert, ariaHidden: node.getAttribute("aria-hidden") })),
    };
  });
  expect(seeded.backgrounds.length).toBeGreaterThanOrEqual(3);
  expect(seeded.backgrounds.map(node => node.ariaHidden)).toEqual(expect.arrayContaining([null, "false", "true"]));
  await opener.click();
  await expect(opener).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("dialog", { name: "Documentation navigation", exact: true })).toBeVisible();
  const locked = await observedDrawerBackgrounds(page);
  expect(locked.overflow).toBe("hidden");
  expect(locked.backgrounds.every(node => node.inert && node.ariaHidden === "true")).toBe(true);

  const backdrop = page.locator("ca-splash-docs [data-ca-docs-drawer-close]");
  await expect(backdrop).toHaveCount(1);
  const box = await backdrop.boundingBox();
  if (!box) throw new Error("The built backdrop must have a pointer target");
  expect(box.width).toBeGreaterThan(8);
  expect(box.height).toBeGreaterThan(8);
  // The right edge lies outside the actual drawer; do not force an obscured click.
  await backdrop.click({ position: { x: box.width - 4, y: 4 } });
  expect(await observedDrawerBackgrounds(page)).toEqual(seeded);
  await expect(opener).toHaveAttribute("aria-expanded", "false");
  await expect(opener).toBeFocused();
  await expect(page.locator("#ca-docs-drawer")).toHaveAttribute("aria-hidden", "true");
  expect(await page.locator("#ca-docs-drawer").evaluate(node => (node as HTMLElement).inert)).toBe(true);
  expect(await page.locator("[data-ca-docs-drawer-layer]").evaluate(node => (node as HTMLElement).hidden)).toBe(true);
});

test("S62: Tab wraps at both ends of the built drawer", async ({ page }) => {
  const opener = await openBuiltDocumentationDrawer(page);
  await opener.click();
  await expect(opener).toHaveAttribute("aria-expanded", "true");
  const count = await page.locator("[data-ca-docs-tray]").evaluate(tray => {
    // Match the declared owner eligibility on real laid-out controls, then use
    // actual keyboard input to test the effect rather than invoking its handler.
    const eligible = Array.from(tray.querySelectorAll<HTMLElement>(
      'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])',
    )).filter(node => !node.hasAttribute("hidden") && node.getAttribute("aria-hidden") !== "true" && !node.closest("[inert]") && node.getClientRects().length > 0);
    if (eligible.length >= 2) {
      eligible[0].dataset.drawerAcceptanceBoundary = "first";
      eligible[eligible.length - 1].dataset.drawerAcceptanceBoundary = "last";
    }
    return eligible.length;
  });
  expect(count).toBeGreaterThanOrEqual(2);
  const first = page.locator('[data-drawer-acceptance-boundary="first"]');
  const last = page.locator('[data-drawer-acceptance-boundary="last"]');
  await last.focus();
  await expect(last).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(first).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(last).toBeFocused();
  await expect(opener).toHaveAttribute("aria-expanded", "true");
});

type DrawerListenerWitness = { element: HTMLElement; signal: AbortSignal; calls: number };

test("S62: disconnecting an open drawer releases its document listener", async ({ page }) => {
  const opener = await openBuiltDocumentationDrawer(page);
  const capture = await page.locator("ca-splash-docs").evaluate(element => {
    const parent = element.parentElement!;
    const next = element.nextSibling;
    const descriptor = Object.getOwnPropertyDescriptor(document, "addEventListener");
    const nativeAdd = document.addEventListener;
    const records: DrawerListenerWitness[] = [];
    Object.defineProperty(document, "addEventListener", {
      configurable: true,
      value: function (this: Document, type: string, listener: EventListenerOrEventListenerObject | null, options?: boolean | AddEventListenerOptions) {
        if (type === "keydown" && listener && typeof options === "object" && options.signal instanceof AbortSignal) {
          const witness = { element: element as HTMLElement, signal: options.signal, calls: 0 };
          records.push(witness);
          const observed: EventListener = function (this: EventTarget, event: Event) {
            witness.calls += 1;
            if (typeof listener === "function") return listener.call(this, event);
            return listener.handleEvent(event);
          };
          // Keep the actual native AbortSignal and original listener options.
          return Reflect.apply(nativeAdd, this, [type, observed, options]);
        }
        return Reflect.apply(nativeAdd, this, [type, listener, options]);
      },
    });
    try {
      // One setup reconnect isolates this element's new document registration.
      // Repeated reconnect behavior is already tested by the existing cases.
      element.remove();
      parent.insertBefore(element, next);
    } finally {
      if (descriptor) Object.defineProperty(document, "addEventListener", descriptor);
      else Reflect.deleteProperty(document, "addEventListener");
    }
    if (records.length === 1) Reflect.set(window, "__drawerAcceptanceWitness", records[0]);
    document.body.style.overflow = "clip";
    return { registrations: records.length, initialized: (element as HTMLElement).dataset.initialized, aborted: records.map(record => record.signal.aborted) };
  });
  expect(capture).toEqual({ registrations: 1, initialized: "true", aborted: [false] });
  await opener.click();
  await expect(opener).toHaveAttribute("aria-expanded", "true");
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
  const detached = await page.evaluate(() => {
    const witness = Reflect.get(window, "__drawerAcceptanceWitness") as DrawerListenerWitness;
    witness.element.remove();
    return { connected: witness.element.isConnected, initialized: witness.element.hasAttribute("data-initialized"), aborted: witness.signal.aborted, calls: witness.calls };
  });
  expect(detached).toEqual({ connected: false, initialized: false, aborted: true, calls: 0 });
  await page.keyboard.press("Escape");
  expect(await page.evaluate(() => {
    const witness = Reflect.get(window, "__drawerAcceptanceWitness") as DrawerListenerWitness;
    return { calls: witness.calls, overflow: document.body.style.overflow, focusInDetached: witness.element.contains(document.activeElement) };
  })).toEqual({ calls: 0, overflow: "clip", focusInDetached: false });
});
