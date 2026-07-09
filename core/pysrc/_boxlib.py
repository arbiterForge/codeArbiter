#!/usr/bin/env python3
# codeArbiter — statusline box-drawing layout (extracted from statusline.py,
# architecture-004).
#
# Owns the sectioned box shell (top/row/sep/bottom) and the two small layout
# helpers (left+right justify, equal-width columns) segments use to lay content
# out inside a row. Carries no segment CONTENT — purely the box structure and
# column math, built on the ANSI/width-aware primitives in _colorlib.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#
# Public API:
#   Box(width)                        the box shell: .top/.row/.sep/.bottom/.render
#   lr(left, right, inner) -> str     left+right justified within inner
#   cols(cells, inner) -> (str, list) equal-column layout with tee-aligned separators

try:
    import _colorlib
    _RESET = _colorlib.RESET
    _V0 = _colorlib.V0
    _TL, _TR, _BL, _BR = _colorlib.TL, _colorlib.TR, _colorlib.BL, _colorlib.BR
    _H, _V, _LT, _RT = _colorlib.H, _colorlib.V, _colorlib.LT, _colorlib.RT
    _TD, _TU, _DOTH = _colorlib.TD, _colorlib.TU, _colorlib.DOTH
    _pad, _vlen, _clip, _gradient_h = (_colorlib.pad, _colorlib.vlen,
                                       _colorlib.clip, _colorlib.gradient_h)
    _ANSI = _colorlib.ANSI
except Exception:  # pragma: no cover — never let an import break the statusline
    _colorlib = None
    _RESET = _V0 = ""
    _TL = _TR = _BL = _BR = _H = _V = _LT = _RT = _TD = _TU = _DOTH = ""

    def _pad(s, w):
        return s

    def _vlen(s):
        return len(s)

    def _clip(s, w):
        return s[:w]

    def _gradient_h(text, width, c_from=None, c_to=None):
        return text

    import re as _re
    _ANSI = _re.compile(r"\033\[[0-9;]*m")


class Box:
    def __init__(self, width):
        self.W = width
        self.inner = width - 4   # "│ " + content + " │"
        self.lines = []

    def top(self, title, badge=""):
        left = f"{_V0}{_TL}{_H}{_H}{_RESET} "          # 4 visible cols
        b = f" {badge} " if badge else " "
        budget = max(1, self.W - 5 - _vlen(b))     # keep room for ╮ + >=0 fill
        title = _clip(title, budget) if _vlen(title) > budget else title
        t = _gradient_h(_ANSI.sub("", title), _vlen(title))
        used = 3 + _vlen(title) + _vlen(b)
        fillw = max(0, self.W - 1 - used - 1)
        fill = _gradient_h(_H * fillw, fillw, (90, 60, 150), (170, 110, 240)) if fillw else ""
        self.lines.append(f"{left}{t}{b}{fill}{_V0}{_TR}{_RESET}")

    def row(self, content):
        self.lines.append(f"{_V0}{_V}{_RESET} {_pad(content, self.inner)} {_V0}{_V}{_RESET}")

    def sep(self, tees=None):
        mid = [_DOTH] * (self.inner + 2)
        for k in (tees or []):
            if 0 <= k + 1 < len(mid):
                mid[k + 1] = _TD
        self.lines.append(f"{_V0}{_LT}{''.join(mid)}{_RT}{_RESET}")

    def bottom(self, tees=None):
        mid = [_H] * (self.inner + 2)
        for k in (tees or []):
            if 0 <= k + 1 < len(mid):
                mid[k + 1] = _TU
        self.lines.append(f"{_V0}{_BL}{''.join(mid)}{_BR}{_RESET}")

    def render(self):
        # No trailing newline: a multi-line statusline that ends in '\n' adds a
        # phantom row, so the host's height accounting drifts on re-render and the
        # bar eventually clears itself. Lines are separated, not terminated.
        return "\n".join(self.lines)


def lr(left, right, inner):
    """Left + right justified within inner; never exceeds inner (clips left)."""
    right = _clip(right, inner)
    rw = _vlen(right)
    left = _clip(left, max(0, inner - rw - 1))
    gap = max(1, inner - _vlen(left) - rw)
    return left + " " * gap + right


def cols(cells, inner):
    """Lay out cells in equal columns with ' │ ' joins. Each cell is clamped to
    its column via pad(), so total visible width == inner exactly and the
    separator tees line up with the content joins. Returns (content, bounds)."""
    n = len(cells)
    if n == 1:
        return _pad(cells[0], inner), []
    seps = n - 1
    avail = inner - seps * 3
    base = avail // n
    widths = [base] * n
    widths[-1] = avail - base * (n - 1)
    parts, bounds, pos = [], [], 0
    for i, c in enumerate(cells):
        parts.append(_pad(c, widths[i]))
        pos += widths[i]
        if i < n - 1:
            parts.append(f" {_V0}{_V}{_RESET} ")
            bounds.append(pos + 1)
            pos += 3
    return "".join(parts), bounds
