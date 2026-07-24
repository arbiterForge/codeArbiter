# anti-slop-design · medium: web and interactive

Load for landing pages, portfolios, and component UIs. Pair with `core`; add `typography`, `color`,
`layout`, `images`. This is the leaf `frontend-author` loads.

## 7.D Web and interactive interfaces

Front ends carry every universal law in `core` §3 plus these web-specific essentials:

- **Real images, not fake-div screenshots.** A product UI built from styled `<div>` rectangles to
  simulate a screenshot is the number-one web tell. Use a real screenshot, a generated image, a real
  mini-component, or no preview.
- **Motion must be motivated.** Every animation answers "what does this communicate?" (hierarchy,
  sequence, feedback, state change). "It looked cool" is not an answer. Honor `prefers-reduced-motion`
  and collapse infinite, parallax, or scroll-hijack motion to static under it.
- **One design system per project.** Do not mix component libraries in one tree.
- **Real logos for social proof**, not text wordmarks; logo wall under the hero, logos only, no
  category labels beneath them.
- **Both color schemes from the start.** Design light and dark together and respect
  `prefers-color-scheme`; never ship one mode by accident, and keep brand identity and contrast intact
  in both.
- **Viewport-stable layout.** Use dynamic viewport units for full-height sections so mobile browser
  chrome does not cause layout jumps, and keep primary navigation on a single line at desktop width.

## Tells (web)

- Fake-div screenshots; hand-rolled decorative SVG instead of real imagery.
- Unmotivated motion; infinite/parallax/scroll-hijack with no `prefers-reduced-motion` fallback.
- Mixed component libraries in one tree.
- Text wordmarks as social proof instead of real logos.
- One color scheme shipped by accident; nav wrapping to two lines at desktop width.

## Pre-flight slice (web)

- [ ] Real images, no fake-div screenshots.
- [ ] Motion motivated and reduced-motion honored.
- [ ] One design system; real logos for social proof.
- [ ] Light and dark both designed and tested; nav fits one line; full-height sections use dynamic
  viewport units.
