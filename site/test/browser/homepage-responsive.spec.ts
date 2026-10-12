/// <reference lib="dom" />
/** homepage-responsive.spec.ts — readable title and contained proof at every hero layout. */
import { expect, test } from "@playwright/test";

for (const width of [320, 390, 768, 1062, 1200, 1440, 1920]) {
  test(`homepage title and proof fit at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const heading = page.locator("#ca-splash-title");
    await expect(heading).toHaveText("codeArbiter: hard gates for agentic coding.");

    const layout = await heading.evaluate((element) => {
      const words = [];
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        for (const match of (node.textContent ?? "").matchAll(/\S+/g)) {
          const range = document.createRange();
          range.setStart(node, match.index!);
          range.setEnd(node, match.index! + match[0].length);
          const rects = Array.from(range.getClientRects());
          words.push({
            word: match[0],
            lines: new Set(rects.map((rect) => Math.round(rect.top))).size,
            left: Math.min(...rects.map((rect) => rect.left)),
            right: Math.max(...rects.map((rect) => rect.right)),
          });
        }
      }
      const proof = document.querySelector(".ca-splash__proof")!.getBoundingClientRect();
      return {
        words,
        proof: { left: proof.left, right: proof.right },
        viewport: document.documentElement.clientWidth,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });

    await page.screenshot({ path: testInfo.outputPath(`homepage-${width}.png`) });
    for (const word of layout.words) {
      expect.soft(word.lines, `"${word.word}" must not split across lines`).toBe(1);
      expect.soft(word.left).toBeGreaterThanOrEqual(0);
      expect.soft(word.right).toBeLessThanOrEqual(layout.viewport);
    }
    expect.soft(layout.proof.left).toBeGreaterThanOrEqual(0);
    expect.soft(layout.proof.right, "proof card must not be clipped outside the viewport").toBeLessThanOrEqual(layout.viewport);
    expect.soft(layout.overflow).toBe(0);
    const video = page.locator(".ca-hook-proof__video");
    await video.scrollIntoViewIfNeeded();
    await expect(video).toBeInViewport();
    await expect(video).toHaveAttribute("controls", "");
  });
}
