# anti-slop-design · medium: CLI / terminal output

Load for output rendered in a terminal: status lines, progress, reports printed to stdout, log lines,
TUI panels. Pair with `core`. Type/color/layout leaves mostly do not apply (the terminal owns the
font; color is a constrained palette).

## 7.F CLI / terminal output

- **The terminal is a constrained medium; respect it.** Variable width, a 16/256/truecolor palette
  that the user's theme controls, monospace only, and a reader who often pipes or greps the output.
- **Degrade without color.** Never let color be the only carrier of meaning (core 3.B/§5 spirit): a
  red number must also read as bad when color is stripped. Always honor `NO_COLOR`. For a normal CLI,
  also drop ANSI on a non-TTY pipe so redirected output stays parseable. The exception is an
  *intentionally-piped colored UI* (e.g. a statusline the host always pipes and renders in color):
  there, keep color and gate only on `NO_COLOR`, never on `isatty` — an isatty test would strip color
  in normal use.
- **Width is unknown.** Fit to the reported width with a margin; never assume 80. A line that wraps in
  a narrow terminal corrupts a box or table. Clamp and truncate deterministically.
- **Glyph width is real.** CJK and many emoji are two columns; combining marks are zero. Count visible
  columns, not characters, or box-drawing and alignment break.
- **No decoration tax.** Emoji sprinkled per line, gratuitous box-drawing, and rainbow ANSI are the
  terminal equivalent of clip art. One accent color, aligned columns, and whitespace carry it.
- **Copy laws still apply.** core §3.A/§3.B hold for any prose in help text, errors, and summaries.
  Error messages say what happened and what to do, not "an error occurred."

## Tells (CLI)

- Color as the sole signal; ignoring `NO_COLOR` (or, for a normal CLI, no non-TTY fallback).
- Hardcoded 80-column assumptions; lines that wrap and corrupt a box.
- Character-count math that misaligns on CJK/emoji width.
- Emoji or box-drawing as decoration rather than structure.
- Vague error strings ("something went wrong").

## Pre-flight slice (CLI)

- [ ] Renders correctly at narrow and wide widths; no wrap corruption.
- [ ] Honors `NO_COLOR`; a normal CLI emits plain output when piped; color is never the only signal.
- [ ] Column math counts visible width (CJK/emoji safe).
- [ ] Decoration earns its place; errors are actionable.
