import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir:'./test/components', outputDir:'./.astro/component-playwright', workers:1, retries:0, timeout:10000, expect:{timeout:2000}, reporter:process.env.CA_COMPONENT_PLAYWRIGHT_JSON ? [['list'],['json',{outputFile:process.env.CA_COMPONENT_PLAYWRIGHT_JSON}]] : 'list', use:{ browserName:'chromium', channel:'chrome' } });
