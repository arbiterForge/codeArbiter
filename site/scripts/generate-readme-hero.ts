import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(siteRoot, "..");
const backgroundPath = join(siteRoot, "src", "assets", "hero-gates.webp");
const gateMarkPath = join(siteRoot, "src", "assets", "gate-mark.svg");
const outputPath = join(repoRoot, "docs", "readme-hero.webp");
const width = 1600;
const height = 640;

const gateMark = await sharp(readFileSync(gateMarkPath), { density: 240 })
  .resize({ width: 58 })
  .png()
  .toBuffer();

const typography = Buffer.from(`
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="shade" x1="0" x2="1">
      <stop offset="0" stop-color="#070b10" stop-opacity=".96"/>
      <stop offset=".46" stop-color="#070b10" stop-opacity=".72"/>
      <stop offset=".78" stop-color="#070b10" stop-opacity=".12"/>
      <stop offset="1" stop-color="#070b10" stop-opacity=".05"/>
    </linearGradient>
    <linearGradient id="edge" x1="0" x2="1">
      <stop stop-color="#9b6811"/>
      <stop offset=".5" stop-color="#3a4c60"/>
      <stop offset="1" stop-color="#9b6811"/>
    </linearGradient>
  </defs>
  <rect width="${width}" height="${height}" fill="url(#shade)"/>
  <rect x="20" y="20" width="1560" height="600" rx="18" fill="none" stroke="url(#edge)" stroke-opacity=".55"/>

  <text x="165" y="93" fill="#f6f7f9" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="500">code<tspan fill="#f0b92f" font-weight="750">Arbiter</tspan></text>

  <text x="98" y="205" fill="#f0b92f" font-family="Consolas, monospace" font-size="16" font-weight="700" letter-spacing="4.1">GOVERNED AUTONOMY FOR SERIOUS REPOSITORIES</text>
  <text x="98" y="313" fill="#f6f7f9" font-family="Segoe UI, Arial, sans-serif" font-size="72" font-weight="750" letter-spacing="-2.8">Hard gates for</text>
  <text x="98" y="397" fill="#f6f7f9" font-family="Segoe UI, Arial, sans-serif" font-size="72" font-weight="750" letter-spacing="-2.8">agentic coding.</text>
  <rect x="98" y="436" width="92" height="4" rx="2" fill="#f0b92f"/>
  <text x="98" y="493" fill="#c7d0da" font-family="Segoe UI, Arial, sans-serif" font-size="23" font-weight="400">Shared enforcement. Durable context.</text>
  <text x="98" y="531" fill="#c7d0da" font-family="Segoe UI, Arial, sans-serif" font-size="23" font-weight="400">Auditable decisions.</text>
</svg>
`);

await sharp(backgroundPath)
  .resize(width, height, { fit: "cover", position: "centre" })
  .composite([
    { input: typography, left: 0, top: 0 },
    { input: gateMark, left: 96, top: 66 },
  ])
  .webp({ quality: 90, effort: 6 })
  .toFile(outputPath);

console.log(`generated README hero -> ${outputPath}`);
