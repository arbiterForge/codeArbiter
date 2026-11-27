/// <reference lib="dom" />
/** hook-gates.spec.ts - the Hook Gates reference prints each hook message as the terminal does. */
import { expect, test } from '@playwright/test';

test('hook messages render in the terminal face, so a flag keeps both hyphens', async ({ page }) => {
  await page.goto('/reference/hooks-gates/');
  const message = page.locator('.ca-hook-message p:not(.ca-hook-message__source)').filter({ hasText: "'--no-verify'" }).first();
  await expect(message).toBeVisible();
  // The characters are exact (the verbatim-flags build scan guards them); the body face then
  // draws `--` as one unbroken dash, so the message must use the monospace terminal face.
  expect(await message.textContent()).toContain("'--no-verify'");
  const style = await message.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { family: cs.fontFamily, ligatures: cs.fontVariantLigatures };
  });
  expect(style.family).toMatch(/^"?JetBrains Mono/);
  expect(style.ligatures).toBe('none');
});
