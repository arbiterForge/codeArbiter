#!/usr/bin/env python3
# codeArbiter — statusline color palette, box-drawing glyphs, and ANSI/width-aware
# string primitives (extracted from statusline.py, architecture-004).
#
# Owns the neon-violet palette, native-safe glyph set, the ANSI-escape regex, and
# the terminal-column-width-aware string ops (clip/pad/vlen) the box layout relies
# on to stay aligned regardless of color codes or wide (CJK/emoji) glyphs. Carries
# NO rendering-decision logic (no segment content, no box structure) — purely the
# color/glyph vocabulary and the width primitives built on it.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Pure functions, fully testable with synthetic input.
#
# Public API:
#   fg(r,g,b) -> str                          truecolor foreground SGR
#   bg(r,g,b) -> str                          truecolor background SGR
#   vlen(s) -> int                            visible terminal-column width (ANSI-aware, wide-glyph-aware)
#   clip(s, w) -> str                         truncate to <= w visible columns (ANSI-preserving)
#   pad(s, w) -> str                          pad/clip to exactly w visible columns
#   gradient_h(text, width, c_from, c_to) -> str   per-character violet sheen

import re
import unicodedata


def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


RESET, BOLD, DIM, ITAL = "\033[0m", "\033[1m", "\033[2m", "\033[3m"


def bg(r, g, b):
    return f"\033[48;2;{r};{g};{b}m"

# neon-violet ramp (dark -> bright) — used for the box sheen and accents
V0 = fg(108, 70, 180)     # deep violet (border base)
V1 = fg(150, 92, 230)     # mid violet
V2 = fg(178, 102, 255)    # primary neon violet
V3 = fg(208, 140, 255)    # bright violet (excitement / highlights)
GREY = fg(150, 150, 162)
WHITE = fg(232, 232, 240)
OK = fg(120, 220, 150)
WARN = fg(255, 184, 76)
DANGER = fg(255, 86, 110)
PILL_FG = fg(18, 14, 26)   # near-black text for contrast on a colored pill bg

# native-safe glyphs only
TL, TR, BL, BR = "╭", "╮", "╰", "╯"
H, V, LT, RT = "─", "│", "├", "┤"
TD, TU = "┬", "┴"                 # tee down / up (column joins)
DOTH = "┄"                        # dotted horizontal (section separators)
DOT = "●"
SUBDOT = "◦"
ELL = "…"
BFULL, BEMPTY = "█", "░"
DN, UP = "↓", "↑"
ARR = "▸"
BOLT = "↯"
SPARK = "▁▂▃▄▅▆▇█"

ANSI = re.compile(r"\033\[[0-9;]*m")


def _cw(ch):
    """Terminal column width of one character: 0 for a combining mark, 2 for an
    East-Asian Wide/Fullwidth glyph (CJK, many emoji), 1 otherwise. Ambiguous-
    width glyphs (box-drawing, blocks, arrows used in this bar) render as 1 in a
    non-CJK terminal, so they stay 1 — only genuinely wide content counts as 2."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def vlen(s):
    """Visible terminal-column width of s, ignoring ANSI codes and counting wide
    glyphs as 2 columns — so the box never overflows on CJK/emoji content."""
    return sum(_cw(c) for c in ANSI.sub("", s))


def clip(s, w):
    """Truncate a (possibly ANSI-colored) string to <= w visible columns,
    preserving color codes and appending an ellipsis + RESET when cut."""
    if w <= 0:
        return ""
    if vlen(s) <= w:
        return s
    out, vis, i, n = [], 0, 0, len(s)
    limit = w - 1   # leave one column for the ellipsis
    while i < n:
        m = ANSI.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        cw = _cw(s[i])
        if vis + cw > limit:   # a wide glyph that would cross the limit stops here
            break
        out.append(s[i])
        vis += cw
        i += 1
    return "".join(out) + ELL + RESET


def pad(s, w):
    """Return s at exactly w visible columns: clip if over, space-pad if under."""
    v = vlen(s)
    if v > w:
        return clip(s, w)
    return s + " " * (w - v)


def gradient_h(text, width, c_from=(120, 80, 200), c_to=(205, 140, 255)):
    """Per-character violet sheen across `width` columns (dark->bright)."""
    out = []
    n = max(1, width - 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(c_from[0] + (c_to[0] - c_from[0]) * t)
        g = int(c_from[1] + (c_to[1] - c_from[1]) * t)
        b = int(c_from[2] + (c_to[2] - c_from[2]) * t)
        out.append(f"\033[38;2;{r};{g};{b}m{ch}")
    return "".join(out) + RESET
