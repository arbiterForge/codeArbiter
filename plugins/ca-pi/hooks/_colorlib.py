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

import json
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from types import MappingProxyType


@dataclass(frozen=True)
class RGB:
    r: int
    g: int
    b: int

    def __iter__(self):
        return iter((self.r, self.g, self.b))

    def __getitem__(self, index):
        return (self.r, self.g, self.b)[index]


@dataclass(frozen=True)
class Palette:
    accent_deep: RGB
    accent_mid: RGB
    accent_primary: RGB
    accent_bright: RGB
    text_muted: RGB
    text_normal: RGB
    text_on_accent: RGB
    semantic_ok: RGB
    semantic_warn: RGB
    semantic_danger: RGB
    gradient_from: RGB
    gradient_to: RGB


def _palette(values):
    return Palette(*(RGB(*value) for value in values))


BUILTIN_PALETTES = MappingProxyType({
    "violet": _palette(((108, 70, 180), (150, 92, 230), (178, 102, 255), (208, 140, 255),
                         (150, 150, 162), (232, 232, 240), (18, 14, 26),
                         (120, 220, 150), (255, 184, 76), (255, 86, 110),
                         (120, 80, 200), (205, 140, 255))),
    "blue": _palette(((35, 91, 155), (52, 130, 205), (69, 155, 255), (125, 190, 255),
                       (145, 158, 174), (232, 240, 248), (8, 22, 36),
                       (107, 214, 158), (255, 187, 79), (255, 91, 109),
                       (40, 105, 190), (113, 190, 255))),
    "green": _palette(((31, 112, 78), (42, 157, 103), (55, 201, 132), (111, 231, 169),
                        (142, 164, 153), (230, 242, 235), (7, 30, 20),
                        (83, 219, 139), (255, 190, 76), (255, 91, 105),
                        (33, 126, 86), (102, 225, 159))),
    "amber": _palette(((145, 87, 20), (199, 123, 29), (240, 157, 43), (255, 199, 104),
                        (165, 154, 139), (244, 237, 226), (35, 22, 7),
                        (100, 210, 137), (255, 184, 76), (255, 83, 98),
                        (166, 96, 20), (255, 190, 76))),
    "mono": _palette(((104, 104, 110), (145, 145, 152), (190, 190, 198), (226, 226, 232),
                       (145, 145, 152), (232, 232, 236), (18, 18, 20),
                       (199, 224, 205), (235, 213, 174), (239, 174, 181),
                       (112, 112, 118), (218, 218, 224))),
})

MAX_THEME_BYTES = 16 * 1024
_CUSTOM_FIELDS = MappingProxyType({
    "accent": MappingProxyType({"deep": "accent_deep", "mid": "accent_mid",
                                "primary": "accent_primary", "bright": "accent_bright"}),
    "text": MappingProxyType({"muted": "text_muted", "normal": "text_normal",
                              "on_accent": "text_on_accent"}),
    "semantic": MappingProxyType({"ok": "semantic_ok", "warn": "semantic_warn",
                                  "danger": "semantic_danger"}),
    "gradient": MappingProxyType({"from": "gradient_from", "to": "gradient_to"}),
})
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _read_custom(path):
    """Read one bounded local JSON object; return None for every failure mode."""
    try:
        path = os.path.expanduser(os.path.expandvars(path))
        if os.path.getsize(path) > MAX_THEME_BYTES:
            return None
        with open(path, "rb") as handle:
            raw = handle.read(MAX_THEME_BYTES + 1)
        if len(raw) > MAX_THEME_BYTES:
            return None
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _resolve_palette(theme_name=None, custom_path=None):
    """Return (effective theme name, palette), falling back wholly to violet."""
    violet = BUILTIN_PALETTES["violet"]
    name = str(theme_name or "violet").strip().lower()
    if name != "custom":
        return (name, BUILTIN_PALETTES[name]) if name in BUILTIN_PALETTES else ("violet", violet)
    path = custom_path or os.environ.get("CODEARBITER_THEME_FILE") or os.path.join(
        "~", ".codearbiter", "statusline-theme.json")
    data = _read_custom(path)
    if data is None:
        return "violet", violet
    updates = {}
    for group_name, fields in _CUSTOM_FIELDS.items():
        group = data.get(group_name)
        if not isinstance(group, dict):
            continue
        for key, field_name in fields.items():
            value = group.get(key)
            if isinstance(value, str) and _HEX.fullmatch(value):
                updates[field_name] = RGB(int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    return "custom", replace(violet, **updates)


def resolve_palette(theme_name=None, custom_path=None):
    """Resolve a built-in or partial custom palette, always falling back to violet."""
    return _resolve_palette(theme_name, custom_path)[1]


def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


RESET, BOLD, DIM, ITAL = "\033[0m", "\033[1m", "\033[2m", "\033[3m"


def bg(r, g, b):
    return f"\033[48;2;{r};{g};{b}m"

# neon-violet ramp (dark -> bright) — used for the box sheen and accents
ACTIVE_THEME_NAME = str(os.environ.get("CODEARBITER_THEME") or "violet").strip().lower()
if ACTIVE_THEME_NAME not in (*BUILTIN_PALETTES, "custom"):
    ACTIVE_THEME_NAME = "violet"
ACTIVE_PALETTE = (BUILTIN_PALETTES["violet"] if ACTIVE_THEME_NAME == "custom"
                  else resolve_palette(ACTIVE_THEME_NAME))


def _project_palette(name, palette):
    global ACTIVE_THEME_NAME, ACTIVE_PALETTE
    global V0, V1, V2, V3, GREY, WHITE, OK, WARN, DANGER, PILL_FG
    ACTIVE_THEME_NAME, ACTIVE_PALETTE = name, palette
    V0 = fg(*palette.accent_deep)
    V1 = fg(*palette.accent_mid)
    V2 = fg(*palette.accent_primary)
    V3 = fg(*palette.accent_bright)
    GREY = fg(*palette.text_muted)
    WHITE = fg(*palette.text_normal)
    OK = fg(*palette.semantic_ok)
    WARN = fg(*palette.semantic_warn)
    DANGER = fg(*palette.semantic_danger)
    PILL_FG = fg(*palette.text_on_accent)


def activate_palette(theme_name=None, custom_path=None):
    """Resolve and project the process palette at render time.

    Custom themes may touch the filesystem, so callers must invoke this from a
    runtime path rather than relying on module import. Repeated calls re-resolve
    the current environment deterministically.
    """
    name = str(theme_name if theme_name is not None else
               (os.environ.get("CODEARBITER_THEME") or "violet")).strip().lower()
    if name not in (*BUILTIN_PALETTES, "custom"):
        name = "violet"
    effective_name, palette = _resolve_palette(name, custom_path)
    _project_palette(effective_name, palette)
    return palette


# Built-ins are pure data and retain legacy import-time exports. Custom stays
# violet until the explicit render-time activation above.
_project_palette(ACTIVE_THEME_NAME, ACTIVE_PALETTE)

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


def gradient_h(text, width, c_from=None, c_to=None):
    """Per-character violet sheen across `width` columns (dark->bright)."""
    c_from = ACTIVE_PALETTE.gradient_from if c_from is None else c_from
    c_to = ACTIVE_PALETTE.gradient_to if c_to is None else c_to
    out = []
    n = max(1, width - 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(c_from[0] + (c_to[0] - c_from[0]) * t)
        g = int(c_from[1] + (c_to[1] - c_from[1]) * t)
        b = int(c_from[2] + (c_to[2] - c_from[2]) * t)
        out.append(f"\033[38;2;{r};{g};{b}m{ch}")
    return "".join(out) + RESET


def box_gradient_h(text, width):
    """Header-border sheen, retaining the original violet bytes by default."""
    if ACTIVE_THEME_NAME == "violet":
        return gradient_h(text, width, (90, 60, 150), (170, 110, 240))
    return gradient_h(text, width)
