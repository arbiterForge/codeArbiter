# anti-slop-design · color

Load it for any medium that renders color (per the INDEX load map). As with type, the named palettes
below are *current* reflexes and reasonable reaches, not a closed list; the rule is a palette chosen
for the brief, not a specific set of hex values.

## 5.A The defaults to avoid

- **No AI-purple / blue glow** as a reflex. No automatic violet button glows, no random neon
  gradients. Use a neutral base (zinc, slate, stone, warm grey) with a single high-contrast accent
  (emerald, electric blue, deep rose, burnt orange, cobalt). Purple is fine *when the brand asks for
  it*, executed with intent.
- **No premium-consumer beige+brass+oxblood+espresso** as a reflex for cookware/wellness/artisan/luxury
  briefs. This palette is so over-used the brand becomes invisible. Rotate to a different family (cold
  luxury silver-grey, forest green + bone, black + tan, cobalt + cream, terracotta + slate, monochrome
  + one saturated pop) unless the brand names those colors.
- **No rainbow.** Max one accent. Saturation under ~80% by default. One palette per artifact, not warm
  greys in one section and cool in another.

## 5.B Contrast and accessibility

For **screen and interactive output**, contrast is mandatory, not optional:

- Body text meets WCAG AA (4.5:1) against its background; large text meets 3:1; aim AAA for primary
  reading.
- Audit every interactive element: no white text on a white button, no light placeholder on a
  near-white field, no ghost button on a photo without a scrim or stroke.

For **print and other static** output, AA ratios are not literally measurable but the spirit holds:
keep text legible against its ground. These two always apply regardless of medium:

- Never use pure `#000000` or pure `#ffffff` for large fills; off-black and off-white preserve depth.
- Color is never the *only* carrier of meaning (colorblind users). Pair it with text, shape, or
  position.

## Tells (color)

Universal visual tells (AI-purple/blue glow, rainbow palettes, pure `#000`/`#fff` fills) live in core
§8. Color-specific tells:

- Beige+brass+oxblood reflex for any "premium" brief.
- More than one accent without a documented reason.
- Color as the sole carrier of meaning.
