#!/usr/bin/env python3
# codeArbiter — statusline display-formatting helpers (extracted from
# statusline.py, architecture-004).
#
# Owns the small pure formatters the box uses to turn raw numbers/paths/durations
# into the compact strings it renders: token/USD formatting, a home-relative path
# abbreviator, human-friendly durations, ISO-timestamp parsing, and the per-call
# burn sparkline. Carries no box-layout or segment-assembly logic.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Pure functions, fully testable with synthetic input.
#   - Never raise on malformed input — degrade to a safe default.
#
# Public API:
#   fmt_tok(n) -> str                 compact token count (999 / 1.5K / 1.0M)
#   usd(c) -> str                     whole-dollar-above-$100 USD format
#   usd_fine(c) -> str                finer-grained USD format (statusline cost cells)
#   short_path(p) -> str              home-relative, middle-truncated path
#   human_dur(secs) -> str            compact duration (3h12m, 4d6h, 45m, 30s)
#   parse_iso(s) -> float|None        ISO-8601 (tolerating trailing Z) -> epoch seconds
#   to_epoch(v) -> float|None         ISO string OR numeric (s/ms) epoch -> epoch seconds
#   sparkline(vals, grad=True) -> str colored sparkline of recent values

import os
from datetime import datetime, timezone

try:
    import _colorlib
    _RESET, _V2, _SPARK, _gradient_h = (_colorlib.RESET, _colorlib.V2,
                                        _colorlib.SPARK, _colorlib.gradient_h)
except Exception:  # pragma: no cover — never let an import break the statusline
    _colorlib = None
    _RESET, _V2, _SPARK = "", "", "▁▂▃▄▅▆▇█"

    def _gradient_h(text, width, c_from=(120, 80, 200), c_to=(205, 140, 255)):
        return text


def sync_palette():
    """Refresh captured color exports after _colorlib runtime activation."""
    global _RESET, _V2, _gradient_h
    if _colorlib is not None:
        _RESET, _V2, _gradient_h = _colorlib.RESET, _colorlib.V2, _colorlib.gradient_h


def num(x, default=0.0):
    """Coerce any host value to float; tolerate strings, None, and containers."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def fmt_tok(n):
    n = num(n)
    if n >= 999_500:                 # round into M before the K branch can print 1000.0K
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(int(n))


def usd(c):
    c = num(c)
    return f"${c:.0f}" if c >= 100 else f"${c:.2f}"


def usd_fine(c):
    c = num(c)
    if c >= 100:
        return f"${c:.0f}"
    if c >= 10:
        return f"${c:.1f}"
    if 0 < c < 0.01:                 # don't render a measured nonzero cost as $0.00
        return "<$.01"
    return f"${c:.2f}"


def short_path(p):
    if not p:
        return "?"
    p = str(p).replace("\\", "/").rstrip("/")
    unc = p.startswith("//")            # UNC share: \\server\share -> //server/share
    home = os.path.expanduser("~").replace("\\", "/").rstrip("/")
    if p == home:
        return "~"
    if home and p.startswith(home + "/"):
        p = "~" + p[len(home):]
    parts = [x for x in p.split("/") if x]
    if not parts:
        return "//" if unc else "/"
    if unc:
        # keep //server/share intact, abbreviate any deep middle
        if len(parts) <= 3:
            return "//" + "/".join(parts)
        return "//" + "/".join(parts[:2] + [s[0] for s in parts[2:-2]] + parts[-2:])
    drive = parts[0].endswith(":") or parts[0] == "~"
    prefix = "" if drive else "/"
    if len(parts) <= 3:
        return prefix + "/".join(parts)
    return prefix + "/".join([parts[0]] + [s[0] for s in parts[1:-2]] + parts[-2:])


def human_dur(secs):
    """Compact human duration: 3h12m, 4d6h, 45m, 30s."""
    secs = int(max(0, secs))
    if secs < 60:
        return f"{secs}s"
    m = secs // 60
    if m < 60:
        return f"{m}m"
    h = m // 60
    m = m % 60
    if h < 24:
        return f"{h}h{m:02d}m" if m else f"{h}h"
    d = h // 24
    h = h % 24
    return f"{d}d{h}h" if h else f"{d}d"


def parse_iso(s):
    """Parse an ISO-8601 timestamp (tolerating a trailing Z) to epoch seconds."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)   # naive timestamps are UTC, not local
        return dt.timestamp()
    except Exception:
        return None


def to_epoch(v):
    """A reset timestamp may arrive as an ISO-8601 string OR a numeric epoch
    (seconds or milliseconds). Normalize to epoch seconds; None if unusable."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        v = float(v)
        if v > 1e12:        # milliseconds
            v /= 1000.0
        return v if v > 0 else None
    return parse_iso(v)


def sparkline(vals, grad=True):
    vals = [num(v, None) for v in vals]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = hi - lo
    chars = []
    for v in vals:
        idx = 3 if span <= 0 else int((v - lo) / span * (len(_SPARK) - 1) + 0.5)
        chars.append(_SPARK[max(0, min(len(_SPARK) - 1, idx))])
    s = "".join(chars)
    return _gradient_h(s, len(s)) if grad else f"{_V2}{s}{_RESET}"
