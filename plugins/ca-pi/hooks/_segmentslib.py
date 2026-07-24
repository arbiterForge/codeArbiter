#!/usr/bin/env python3
# codeArbiter — statusline segment renderers (extracted from statusline.py,
# architecture-004).
#
# Owns the individual content segments the box assembles into rows: the
# context-window bar, the 5h/7d rate-limit cells, the model/effort pill, the
# Session/Today usage row, the diff-churn / PR / transcript-pruner segments, and
# the /dev redshift recolor. NOT the update-available marker (`seg_update` /
# `plugin_root_for_render` stay in statusline.py — a test patches
# `statusline.plugin_root_for_render` directly, so that seam must resolve through
# the entry-point module's own globals, not a lib's).
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed input — callers already wrap these in safe(), but
#     each function still degrades on bad data rather than relying solely on that.
#
# Public API:
#   seg_ctx_lines(data, w) -> [str, str]
#   seg_window_cells(data) -> list[str]
#   seg_window_inline(data) -> str
#   model_pill(model, effort="") -> str
#   usage_row(label, tin, tout, cost, trail="") -> str
#   seg_lines(data) -> str|None
#   seg_pr(data) -> str|None
#   seg_prune(data, sid) -> str|None
#   redshift(s) -> str

import json
import os
import re
import time

try:
    import _colorlib
    _fg, _bg = _colorlib.fg, _colorlib.bg
    RESET, BOLD = _colorlib.RESET, _colorlib.BOLD
    V0, V2, V3 = _colorlib.V0, _colorlib.V2, _colorlib.V3
    GREY, WHITE, OK, WARN, DANGER, PILL_FG = (_colorlib.GREY, _colorlib.WHITE, _colorlib.OK,
                                              _colorlib.WARN, _colorlib.DANGER, _colorlib.PILL_FG)
    _VBAR = _colorlib.V
    BFULL, BEMPTY, DN, UP, ARR, BOLT = (_colorlib.BFULL, _colorlib.BEMPTY, _colorlib.DN,
                                        _colorlib.UP, _colorlib.ARR, _colorlib.BOLT)
    DIM = _colorlib.DIM
except Exception:  # pragma: no cover — never let an import break the statusline
    _colorlib = None
    RESET = BOLD = DIM = ""
    V0 = V2 = V3 = GREY = WHITE = OK = WARN = DANGER = PILL_FG = ""
    _VBAR = "|"
    BFULL, BEMPTY, DN, UP, ARR, BOLT = "#", ".", "v", "^", ">", "!"

    def _bg(r, g, b):
        return ""


def sync_palette():
    """Refresh captured color exports after _colorlib runtime activation."""
    global RESET, BOLD, DIM, V0, V2, V3, GREY, WHITE, OK, WARN, DANGER, PILL_FG
    if _colorlib is not None:
        RESET, BOLD, DIM = _colorlib.RESET, _colorlib.BOLD, _colorlib.DIM
        V0, V2, V3 = _colorlib.V0, _colorlib.V2, _colorlib.V3
        GREY, WHITE, OK = _colorlib.GREY, _colorlib.WHITE, _colorlib.OK
        WARN, DANGER, PILL_FG = _colorlib.WARN, _colorlib.DANGER, _colorlib.PILL_FG

try:
    import _fmtlib
    fmt_tok, usd_fine, human_dur, to_epoch = (_fmtlib.fmt_tok, _fmtlib.usd_fine,
                                              _fmtlib.human_dur, _fmtlib.to_epoch)
    num = _fmtlib.num
except Exception:  # pragma: no cover — never let an import break the statusline
    _fmtlib = None

    def num(x, default=0.0):
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    def fmt_tok(n):
        return str(int(num(n)))

    def usd_fine(c):
        return f"${num(c):.2f}"

    def human_dur(secs):
        return f"{int(max(0, secs))}s"

    def to_epoch(v):
        return None


def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


# --------------------------------------------------------------------------- context / rate limits
def seg_ctx_lines(data, w):
    """Two lines of context-window detail for the right column: a gradient bar +
    used% on top, then resident/window + headroom-to-compaction below. The bar
    scales to the available width w."""
    cw = get(data, "context_window", default={}) or {}
    pf = num(cw.get("used_percentage"), None)
    if pf is None:
        return [f"{GREY}ctx --{RESET}", ""]
    pctf = max(0.0, min(100.0, pf))
    size_raw = cw.get("context_window_size")
    has_size = size_raw is not None
    size = int(num(size_raw, 200000)) or 200000
    win = "1M" if size >= 1_000_000 else f"{size // 1000}K"
    resident = round(pctf / 100.0 * size)
    col = V2 if pctf < 75 else (WARN if pctf < 90 else DANGER)
    barw = max(10, min(46, w - 12))
    filled = max(0, min(barw, round(pctf / 100 * barw)))
    # below WARN: the violet sheen; at/over the 75/90 thresholds the FILL itself
    # carries the threshold color so budget pressure shows on the dominant
    # element, not just the trailing % glyph.
    fill = _colorlib.gradient_h(BFULL * filled, max(1, filled)) if (pctf < 75 and _colorlib) else f"{col}{BFULL * filled}"
    bar = fill + f"{V0}" + BEMPTY * (barw - filled) + RESET
    pdisp = "<1%" if 0 < pctf < 1 else f"{pctf:.0f}%"
    line1 = f"{GREY}ctx{RESET} {bar} {col}{pdisp}{RESET}"
    thresh = num(os.environ.get("CODEARBITER_COMPACT_AT"), 92.0)
    head = thresh - pctf
    if head <= 0:
        comp = f"{DANGER}{BOLT} compact imminent{RESET}"
    else:
        ccol = OK if head > 30 else (WARN if head > 12 else DANGER)
        comp = f"{GREY}{BOLT} compact{RESET} {ccol}~{head:.0f}%{RESET}"
    # only assert resident/window when the host actually sent the window size;
    # otherwise show just the (percentage-based) compaction headroom, no fake /200K.
    line2 = f"{DIM}{fmt_tok(resident)} / {win}{RESET}   {comp}" if has_size else comp
    return [line1, line2]


def seg_window_cells(data):
    """5h / 7d rate-limit cells: used% + reset countdown. The countdown shows when
    the host sends rate_limits.*.resets_at (ISO string or epoch); absent that, the
    cell still shows the used%. Rendered wherever rate_limits exists."""
    cells = []
    now = time.time()
    for key, lbl in (("five_hour", "5h"), ("seven_day", "7d")):
        p = get(data, "rate_limits", key, "used_percentage")
        if p is None:
            continue
        pf = num(p, None)
        if pf is None:
            continue
        c = V2 if pf < 75 else (WARN if pf < 90 else DANGER)
        cell = f"{GREY}{lbl}{RESET} {c}{pf:.0f}%{RESET}"
        r = to_epoch(get(data, "rate_limits", key, "resets_at"))
        if r:
            dt = r - now
            # a reset already in the past is stale data, not "rolls over now"
            tail = f"{WHITE}{human_dur(dt)}{RESET}" if dt > 0 else f"{GREY}--{RESET}"
            cell += f" {GREY}{ARR}{RESET} {tail}"
        cells.append(cell)
    return cells


def seg_window_inline(data):
    """Compact single-string rate-limit readout for the header line."""
    cells = seg_window_cells(data)
    return f" {V0}·{RESET} ".join(cells) if cells else ""


EFF_DISP = {"low": "Low", "medium": "Medium", "high": "High",
            "xhigh": "XHigh", "max": "Max", "ultracode": "Ultracode"}


def model_pill(model, effort=""):
    """A gradient-filled pill carrying the model AND its effort level, e.g.
    " Opus 4.8 │ Ultracode ", keyed by family — Fable gold, Opus violet, Sonnet
    blue, Haiku green. The background ramps dark->bright across the pill (a sheen
    matching the box). Plain block ends (half-circle caps don't align in a
    monospace cell)."""
    m = str(model)
    ml = m.lower()
    if "fable" in ml:
        c = (235, 184, 90)        # gold — the tier above Opus
    elif "opus" in ml:
        c = (188, 120, 255)       # violet
    elif "sonnet" in ml:
        c = (96, 174, 235)        # blue
    elif "haiku" in ml:
        c = (120, 220, 150)       # green
    else:
        c = (150, 150, 162)       # grey (unknown)
    eff = str(effort).strip().lower()
    body = f" {m} {_VBAR} {EFF_DISP.get(eff, eff.capitalize())} " if eff else f" {m} "
    lo = tuple(int(v * 0.5) for v in c)           # dark start of the sheen
    n = max(1, len(body) - 1)
    cells = []
    for idx, ch in enumerate(body):
        t = idx / n
        rr = int(lo[0] + (c[0] - lo[0]) * t)
        gg = int(lo[1] + (c[1] - lo[1]) * t)
        bb = int(lo[2] + (c[2] - lo[2]) * t)
        cells.append(f"{_bg(rr, gg, bb)}{PILL_FG}{BOLD}{ch}")
    return "".join(cells) + RESET


def usage_row(label, tin, tout, cost, trail=""):
    """One row of the Session/Today mini-table: label │ ↓in ↑out │ $cost. in/out are
    fresh (sent) tokens; `cost` is Claude Code's real session cost (cost.total_cost_usd),
    not an estimate. `trail` carries extras (session age, burn sparkline)."""
    base = (f"{GREY}{label:<7}{RESET} {V0}{_VBAR}{RESET} "
            f"{V2}{DN}{RESET} {WHITE}{fmt_tok(tin):>6}{RESET} "
            f"{V2}{UP}{RESET} {WHITE}{fmt_tok(tout):>6}{RESET} {V0}{_VBAR}{RESET} "
            f"{OK}{usd_fine(cost)}{RESET}")
    return base + (f"  {trail}" if trail else "")


def seg_lines(data):
    add = get(data, "cost", "total_lines_added")
    rem = get(data, "cost", "total_lines_removed")
    if add is None and rem is None:
        return None
    return f"{GREY}diff{RESET} {OK}+{fmt_tok(add)}{RESET}{GREY}/{RESET}{DANGER}-{fmt_tok(rem)}{RESET}"


def seg_pr(data):
    num_ = get(data, "pr", "number")
    if not num_:
        return None
    state = str(get(data, "pr", "state") or "").lower()
    checks = str(get(data, "pr", "checks") or "").lower()
    mark, col = "", V2
    if checks in ("pass", "passing", "success", "green"):
        mark, col = "✓", OK
    elif checks in ("fail", "failing", "error", "red"):
        mark, col = "✕", DANGER
    elif checks in ("pending", "running", "queued"):
        mark, col = "…", WARN
    scol = OK if state == "open" else (V3 if state == "merged" else GREY)
    tail = f" {col}{mark}{RESET}" if mark else ""
    return f"{GREY}PR{RESET} {scol}#{num_}{RESET}{tail}"


def seg_prune(data, sid):
    """Transcript-pruner indicator: model-context reduction and age of the last
    prune for this session, read from ~/.codearbiter/prune-state.json (written
    by prune-transcript.py). Fail-soft — returns None on any problem, and never
    raises, so it can never break statusline rendering."""
    if not sid:
        return None
    try:
        p = os.path.join(os.path.expanduser("~"), ".codearbiter", "prune-state.json")
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        rec = st.get(sid) if isinstance(st, dict) else None
        if not isinstance(rec, dict):
            return None
        file_freed = num(rec.get("file_bytes_freed", rec.get("freed_bytes")), 0)
        if file_freed <= 0:
            return None
        age = human_dur(max(0, time.time() - num(rec.get("last_run_ts"), time.time())))
        if "context_est_tokens_freed" not in rec:
            pct = num(rec.get("file_pct", rec.get("pct")), 0)
            return f"{GREY}✂{RESET} {WHITE}file:{pct:.0f}%{RESET} {GREY}{age}{RESET}"
        context_tokens = max(0, num(rec.get("context_est_tokens_freed"), 0))
        return (f"{GREY}✂{RESET} {WHITE}ctx:{fmt_tok(context_tokens)}{RESET} "
                f"{GREY}{age}{RESET}")
    except Exception:  # noqa: BLE001
        return None


def redshift(s):
    """/dev tell: recolor every truecolor SGR to a red of matching brightness, so the
    WHOLE bar turns alarm-red — a glaring sign orchestration is suspended."""
    def repl(m):
        lum = max(int(m.group(2)), int(m.group(3)), int(m.group(4)))
        return f"\033[{m.group(1)};2;{min(255, 96 + lum)};{lum // 6};{lum // 7}m"
    return re.sub(r"\033\[(38|48);2;(\d+);(\d+);(\d+)m", repl, s)
