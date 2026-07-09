#!/usr/bin/env python3
# codeArbiter statusline — dependency-free (Python stdlib only, no Nerd Font).
#
# Renders a sectioned, full-width box. The usage segments (folder, git, model,
# rate limits, context, cumulative tokens, API-equivalent cost, per-call burn)
# render in every repo. The arbiter segments (stage / tasks / open-questions /
# overrides-since-checkpoint) render only when the repo's .codearbiter/CONTEXT.md
# frontmatter is `arbiter: enabled`.
#
# Design:
#   - single neon-violet palette (a subtle dark->bright sheen, no rainbow);
#     green/amber/red are reserved strictly for threshold status (ctx, rates).
#   - native-font glyphs only: box-drawing, block elements, arrows, ASCII labels.
#   - top line = active folder; second line = git project (owner/name + branch),
#     with a no-git fallback.
#   - token COUNTS come from the session TRANSCRIPT (deduped per requestId; the
#     host sends no cumulative counts). The COST is the host's authoritative
#     cost.total_cost_usd — it already prices every call (incl. subagents, which
#     live in separate transcripts) the way your bill does; a token*price table
#     would miss subagents and drift, so it is used only as a fallback.
#   - context trusts context_window.used_percentage + context_window_size
#     (1M for million-token models, 200K otherwise) — never exceeds 100%.
#
# A small user-level ledger (~/.codearbiter/ledger.json) tails each session's
# transcript from a stored byte offset (append-only -> O(new lines) per render),
# accumulating true cumulative tokens + API-equivalent cost per session, so the
# box shows this session, today's totals across sessions, and a sparkline of the
# real per-message token burn.
#
# Robustness contract: this script must NEVER print a traceback. The host pipes
# arbitrary JSON on stdin and the output lands in the user's terminal. Every
# segment is wrapped (safe()), the whole render is guarded, all host values pass
# through num() coercion, and every row is width-clamped so a bad value or a
# narrow terminal degrades a segment — it never breaks the box.
#
# This file is a THIN ENTRY POINT (architecture-004): it parses stdin, resolves
# the box width, and wires together the concern-group libraries below into the
# final render. Each concern lives in its own `_<name>lib.py` sibling, imported
# guarded the same defensive way as _taskboardlib/_hooklib below — a missing lib
# degrades its segment(s), it never breaks the box:
#   _colorlib        palette, glyphs, ANSI regex, width-aware clip/pad/gradient
#   _fmtlib          token/USD/duration/path/sparkline formatting
#   _gitlib          project root, branch, dirty-check
#   _arbiterstatelib .codearbiter/ frontmatter + override/question counting + cache
#   _sessionlib      true wall-clock session-start resolution
#   _subagentslib    subagent directory scan + per-subagent labeling
#   _boxlib          the box shell (top/row/sep/bottom) + column layout helpers
#   _segmentslib     the individual content segments (ctx bar, rate cells, pill, …)
#   _ledgerlib       token/cost ledger (extracted earlier, T-12)
# `seg_update` / `plugin_root_for_render` (the update-notifier surface) and
# `dev_active`'s render-time callers stay wired here because a test patches
# `statusline.plugin_root_for_render` directly — that seam must resolve through
# this module's own globals, not a lib's.
#
# Env:
#   CODEARBITER_STATUSLINE=off   disable entirely
#   CODEARBITER_COMPACT=1        drop the subagent rows (lean mode)
#   CODEARBITER_WIDTH / COLUMNS  box width (clamped 70..160)
#   CODEARBITER_COMPACT_AT=NN    context %% treated as the compaction threshold
#   CODEARBITER_LEDGER=path      override ledger location

import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)

# Shared task-board logic so the "tasks" segment counts in-flight items the same
# way the SessionStart hook does (excludes done). Guarded: a failed import must
# degrade the segment, never break the box (robustness contract above).
try:
    from _taskboardlib import count_in_flight as _count_in_flight, read_board as _read_board
except Exception:  # pragma: no cover — never let an import break the statusline
    _count_in_flight = None
    _read_board = None

# Reuse the enforcement-hook activation contract so the box reports "arbiter
# enabled" exactly the way the hooks gate on it (one frontmatter parser, not two).
# Guarded the same defensive way as _taskboardlib: a missing lib degrades the
# arbiter segment to a local fallback, it never breaks the box.
try:
    from _hooklib import frontmatter_enabled as _frontmatter_enabled
except Exception:  # pragma: no cover — never let an import break the statusline
    _frontmatter_enabled = None

# Update-available notifier (spec: update-available-notifier.md) — the statusline
# renders the SAME cache SessionStart reads (RENDER ONLY: no fetch, no spawn, no
# network here at all). Guarded the same defensive way as the imports above.
try:
    import _updatelib
except Exception:  # pragma: no cover — never let an import break the statusline
    _updatelib = None

# The cost/token ledger subsystem lives in _ledgerlib (extracted T-12) with zero
# import-time side effects. Re-bind its functions into this module so the cost
# segment — and the existing test suite that reaches them via statusline — keep
# working. Guarded: a missing lib leaves the names None and the cost segment
# safe()-degrades, never breaking the box.
try:
    import _ledgerlib
    ledger_update = _ledgerlib.ledger_update
    _tx_accumulate = _ledgerlib._tx_accumulate
    persist_sess_start = _ledgerlib.persist_sess_start
except Exception:  # pragma: no cover — never let an import break the statusline
    _ledgerlib = None

    def ledger_update(data, sid):   # safe blanks: keeps render()'s 3-tuple contract
        blank = {"in": 0.0, "out": 0.0, "cost": 0.0}
        return {}, dict(blank), dict(blank)

    def persist_sess_start(sid, value):   # no ledger lib -> nothing to persist into
        return False

# --------------------------------------------------------------------------- color / width primitives (_colorlib)
try:
    import _colorlib
    fg, bg = _colorlib.fg, _colorlib.bg
    RESET, BOLD, DIM, ITAL = _colorlib.RESET, _colorlib.BOLD, _colorlib.DIM, _colorlib.ITAL
    V0, V1, V2, V3 = _colorlib.V0, _colorlib.V1, _colorlib.V2, _colorlib.V3
    GREY, WHITE, OK, WARN, DANGER, PILL_FG = (_colorlib.GREY, _colorlib.WHITE, _colorlib.OK,
                                              _colorlib.WARN, _colorlib.DANGER, _colorlib.PILL_FG)
    TL, TR, BL, BR = _colorlib.TL, _colorlib.TR, _colorlib.BL, _colorlib.BR
    H, V, LT, RT = _colorlib.H, _colorlib.V, _colorlib.LT, _colorlib.RT
    TD, TU = _colorlib.TD, _colorlib.TU
    DOTH, DOT, SUBDOT, ELL = _colorlib.DOTH, _colorlib.DOT, _colorlib.SUBDOT, _colorlib.ELL
    BFULL, BEMPTY = _colorlib.BFULL, _colorlib.BEMPTY
    DN, UP, ARR, BOLT, SPARK = _colorlib.DN, _colorlib.UP, _colorlib.ARR, _colorlib.BOLT, _colorlib.SPARK
    ANSI = _colorlib.ANSI
    _cw, vlen, clip, pad, gradient_h = (_colorlib._cw, _colorlib.vlen, _colorlib.clip,
                                        _colorlib.pad, _colorlib.gradient_h)
except Exception:  # pragma: no cover — never let an import break the statusline
    _colorlib = None
    ANSI = re.compile(r"\033\[[0-9;]*m")
    fg = bg = lambda *a: ""
    RESET = BOLD = DIM = ITAL = ""
    V0 = V1 = V2 = V3 = GREY = WHITE = OK = WARN = DANGER = PILL_FG = ""
    TL = TR = BL = BR = H = V = LT = RT = TD = TU = DOTH = DOT = SUBDOT = ELL = BFULL = BEMPTY = ""
    DN = UP = ARR = BOLT = ""
    SPARK = " "

    def vlen(s):
        return len(ANSI.sub("", s))

    def clip(s, w):
        return ANSI.sub("", s)[:max(0, w)]

    def pad(s, w):
        v = vlen(s)
        return s if v >= w else s + " " * (w - v)

    def gradient_h(text, width, c_from=None, c_to=None):
        return text

# --------------------------------------------------------------------------- coercion
def num(x, default=0.0):
    """Coerce any host value to float; tolerate strings, None, and containers."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def safe(fn, *a, **k):
    """Run a segment builder; swallow any failure so one bad segment can't break
    the whole statusline. Returns None on error (caller omits the segment)."""
    try:
        return fn(*a, **k)
    except Exception:
        return None


def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur

# --------------------------------------------------------------------------- format (_fmtlib)
try:
    import _fmtlib
    fmt_tok, usd, usd_fine, short_path = (_fmtlib.fmt_tok, _fmtlib.usd,
                                          _fmtlib.usd_fine, _fmtlib.short_path)
    human_dur, parse_iso, to_epoch, sparkline = (_fmtlib.human_dur, _fmtlib.parse_iso,
                                                 _fmtlib.to_epoch, _fmtlib.sparkline)
except Exception:  # pragma: no cover — never let an import break the statusline
    _fmtlib = None

    def fmt_tok(n):
        return str(int(num(n)))

    def usd(c):
        return f"${num(c):.2f}"

    def usd_fine(c):
        return f"${num(c):.2f}"

    def short_path(p):
        return str(p) if p else "?"

    def human_dur(secs):
        return f"{int(max(0, secs))}s"

    def parse_iso(s):
        return None

    def to_epoch(v):
        return None

    def sparkline(vals, grad=True):
        return ""

# --------------------------------------------------------------------------- git (_gitlib)
try:
    import _gitlib
    project_root, head_branch, git_dirty = (_gitlib.project_root, _gitlib.head_branch,
                                            _gitlib.git_dirty)
except Exception:  # pragma: no cover — never let an import break the statusline
    _gitlib = None

    def project_root(data):
        return get(data, "workspace", "project_dir") or get(data, "cwd") or os.getcwd()

    def head_branch(root):
        return None

    def git_dirty(root):
        return False

# --------------------------------------------------------------------------- arbiter (_arbiterstatelib)
# arbiter_state's task-in-flight count and enabled-gate dependencies
# (_count_in_flight / _read_board / _frontmatter_enabled) are guarded-imported
# ABOVE, in this module — arbiter_state() below passes them through EACH CALL
# (not at import time) so a test that monkeypatches this module's fallback (e.g.
# `mod._count_in_flight = None`) is observed on the next call, exactly as before
# the extraction.
try:
    import _arbiterstatelib
    frontmatter, count_matches = _arbiterstatelib.frontmatter, _arbiterstatelib.count_matches
    _ARBITER_CACHE, _ARBITER_FILES = _arbiterstatelib._ARBITER_CACHE, _arbiterstatelib._ARBITER_FILES
    _arbiter_mtime_key = _arbiterstatelib._arbiter_mtime_key
    dev_active = _arbiterstatelib.dev_active

    def _arbiter_enabled(ctx_path):
        return _arbiterstatelib._arbiter_enabled(ctx_path, _frontmatter_enabled)

    def arbiter_state(root, ctx_text=None, ot_text=None, oq_text=None):
        # performance-003 (#194): ctx_text/ot_text/oq_text let a caller (e.g.
        # session-start.py's governance_line) that already read CONTEXT.md/
        # open-tasks.md/open-questions.md thread that content through instead of
        # a second disk read. Every existing caller passes nothing and is
        # unaffected.
        return _arbiterstatelib.arbiter_state(
            root, _count_in_flight, _read_board, _frontmatter_enabled,
            ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
except Exception:  # pragma: no cover — never let an import break the statusline
    _arbiterstatelib = None
    _ARBITER_CACHE = {}
    _ARBITER_FILES = ()

    def frontmatter(path):
        return {}

    def count_matches(path, pattern):
        return 0

    def _arbiter_mtime_key(cad):
        return -1.0

    def _arbiter_enabled(ctx_path):
        return False

    def arbiter_state(root, ctx_text=None, ot_text=None, oq_text=None):
        return None

    def dev_active(root):
        return False

# --------------------------------------------------------------------------- subagents (_subagentslib)
try:
    import _subagentslib
    subagent_dir, read_subagents, sub_label = (_subagentslib.subagent_dir,
                                               _subagentslib.read_subagents,
                                               _subagentslib.sub_label)
    ACTIVE_WINDOW, SHOW_WINDOW = _subagentslib.ACTIVE_WINDOW, _subagentslib.SHOW_WINDOW
    MAX_SUB_ROWS, MAX_SUB_FILES, MAX_SUB_LINES = (_subagentslib.MAX_SUB_ROWS,
                                                  _subagentslib.MAX_SUB_FILES,
                                                  _subagentslib.MAX_SUB_LINES)
except Exception:  # pragma: no cover — never let an import break the statusline
    _subagentslib = None
    ACTIVE_WINDOW = SHOW_WINDOW = MAX_SUB_ROWS = MAX_SUB_FILES = MAX_SUB_LINES = 0

    def subagent_dir(data, root, sid):
        return None

    def read_subagents(sdir):
        return 0, 0, [], (0, 0)

    def sub_label(content):
        return ""

# --------------------------------------------------------------------------- box (_boxlib)
try:
    import _boxlib
    Box, lr, cols = _boxlib.Box, _boxlib.lr, _boxlib.cols
except Exception:  # pragma: no cover — never let an import break the statusline
    _boxlib = None

    class Box:  # minimal degrade: plain lines, no box drawing
        def __init__(self, width):
            self.W = width
            self.inner = max(1, width - 4)
            self.lines = []

        def top(self, title, badge=""):
            self.lines.append(pad(title, self.inner))

        def row(self, content):
            self.lines.append(pad(content, self.inner))

        def sep(self, tees=None):
            self.lines.append(H * self.inner if H else "-" * self.inner)

        def bottom(self, tees=None):
            self.lines.append("")

        def render(self):
            return "\n".join(self.lines)

    def lr(left, right, inner):
        gap = max(1, inner - vlen(left) - vlen(right))
        return left + " " * gap + right

    def cols(cells, inner):
        return pad(" ".join(cells), inner), []

# --------------------------------------------------------------------------- segments (_segmentslib)
try:
    import _segmentslib
    seg_ctx_lines = _segmentslib.seg_ctx_lines
    seg_window_cells, seg_window_inline = _segmentslib.seg_window_cells, _segmentslib.seg_window_inline
    EFF_DISP, model_pill, usage_row = _segmentslib.EFF_DISP, _segmentslib.model_pill, _segmentslib.usage_row
    seg_lines, seg_pr, seg_prune = _segmentslib.seg_lines, _segmentslib.seg_pr, _segmentslib.seg_prune
    redshift = _segmentslib.redshift
except Exception:  # pragma: no cover — never let an import break the statusline
    _segmentslib = None
    EFF_DISP = {}

    def seg_ctx_lines(data, w):
        return [f"{GREY}ctx --{RESET}", ""]

    def seg_window_cells(data):
        return []

    def seg_window_inline(data):
        return ""

    def model_pill(model, effort=""):
        return f"{V2}{model}{RESET}"

    def usage_row(label, tin, tout, cost, trail=""):
        return f"{label} {fmt_tok(tin)}/{fmt_tok(tout)} {usd_fine(cost)}"

    def seg_lines(data):
        return None

    def seg_pr(data):
        return None

    def seg_prune(data, sid):
        return None

    def redshift(s):
        return s

# --------------------------------------------------------------------------- session start (_sessionlib)
try:
    import _sessionlib
    session_start = _sessionlib.session_start
except Exception:  # pragma: no cover — never let an import break the statusline
    _sessionlib = None

    def session_start(sid, rec=None):
        return None


# --------------------------------------------------------------------------- ledger render-bridge
# burn_spark stays here (not in _ledgerlib): it is the render bridge that turns
# the lib's numeric samples into a colored sparkline, so it keeps the ANSI
# dependency out of the lib.
def burn_spark(rec):
    """Sparkline of recent per-message token burn — real per-API-call totals
    accumulated from the transcript (via _ledgerlib.burn_samples), not a
    time-extrapolated estimate."""
    samples = _ledgerlib.burn_samples(rec) if _ledgerlib is not None else []
    return sparkline(samples) if len(samples) >= 2 else ""


# --------------------------------------------------------------------------- update-available marker
def plugin_root_for_render():
    """The plugin root to resolve the installed version against, for seg_update.
    Delegates to _updatelib.plugin_root() (CLAUDE_PLUGIN_ROOT, else derived from
    this install's own file location) — a thin seam so tests can monkeypatch it
    without touching env vars. None if _updatelib failed to import."""
    if _updatelib is None:
        return None
    return _updatelib.plugin_root()


def seg_update(plugin=None):
    """Update-available marker (spec: update-available-notifier.md, AC-1/AC-2):
    reads the SAME user-global cache SessionStart reads and compares against the
    installed plugin.json version. RENDER ONLY — no fetch, no spawn, no network
    call of any kind; a missing/corrupt cache or an up-to-date install both
    degrade to None (no segment), and any error is swallowed (never breaks the
    box, mirrors seg_prune)."""
    if _updatelib is None:
        return None
    try:
        plugin = plugin if plugin is not None else plugin_root_for_render()
        state = _updatelib.read_state(_updatelib.state_path())
        latest = state.get("latest") if isinstance(state, dict) else None
        installed = _updatelib.installed_version(plugin)
        if not _updatelib.update_available(installed, latest):
            return None
        return f"{V2}{UP}{RESET} {WHITE}{latest}{RESET}"
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- main
WIDTH_MARGIN = 6   # columns kept clear of the terminal's right edge


def detect_box_width():
    """Fit the box to the terminal, leaving a margin so the right border never
    lands in the final column — writing there auto-wraps and corrupts a
    multi-line statusline. The host runs this command with stdout as a pipe (no
    tty), so COLUMNS (which the host sets) is the primary source; terminal-size
    probes are a fallback. Explicit CODEARBITER_WIDTH wins and is used verbatim."""
    env = os.environ.get("CODEARBITER_WIDTH")
    if env:
        try:
            return max(40, min(200, int(env)))
        except ValueError:
            pass
    raw = 0
    try:
        raw = int(os.environ.get("COLUMNS") or 0)
    except ValueError:
        raw = 0
    if raw <= 0:
        raw = shutil.get_terminal_size(fallback=(0, 0)).columns
    if raw <= 0:
        for fd in (1, 2, 0):
            try:
                raw = os.get_terminal_size(fd).columns
                if raw > 0:
                    break
            except OSError:
                pass
    if raw <= 0:
        raw = 140   # wide default when nothing reports a width
    return max(60, min(160, raw - WIDTH_MARGIN))


def render(raw):
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    W = detect_box_width()
    compact = os.environ.get("CODEARBITER_COMPACT", "").lower() in ("1", "true", "on", "yes")

    root = safe(project_root, data) or os.getcwd()
    sid = data.get("session_id") or data.get("sessionId")
    arb = safe(arbiter_state, root)
    effort = (get(data, "effort", "level") or "").lower()
    sprint = bool(arb and arb.get("sprint"))
    # /dev takes precedence over sprint: a textual [DEV] tell rides alongside the
    # full-bar redshift so dev mode reads even where color is stripped or unseen.
    if safe(dev_active, root):
        badge = f"{BOLD}[DEV]{RESET}"
    elif sprint:
        badge = f"{V3}{BOLD}[SPRINT]{RESET}"   # effort now shows by the model pill
    else:
        badge = ""

    led = safe(ledger_update, data, sid)
    if not (isinstance(led, tuple) and len(led) == 3):
        led = ({}, {"in": 0.0, "out": 0.0, "cost": 0.0}, {"in": 0.0, "out": 0.0, "cost": 0.0})
    rec, sess, day = led
    spark = safe(burn_spark, rec) or ""
    # True session age from Claude Code's session metadata (the wall clock /usage
    # shows, incl. idle gaps); fall back to the current transcript's first message.
    had_cached_start = isinstance(rec, dict) and bool(num(rec.get("sess_start"), None))
    s0 = safe(session_start, sid, rec)
    # Freshly resolved (not from cache) -> persist into the ledger so the next render
    # skips the ~/.claude/sessions scan. ledger_update already ran this render, so a
    # targeted write seeds the cache now rather than waiting for the next dirty write.
    if s0 is not None and not had_cached_start and sid:
        safe(persist_sess_start, sid, s0)
    if s0 is None:
        s0 = num(rec.get("t0"), num(rec.get("first_ts"), time.time()))
    age_str = f"{GREY}age{RESET} {WHITE}{human_dur(time.time() - s0)}{RESET}"
    s_trail = spark   # age moves under the ctx bar (next to compact %), not here

    box = Box(W)
    inner = box.inner

    folder = safe(short_path, get(data, "workspace", "current_dir") or get(data, "cwd")) or "?"
    box.top(folder, badge)

    # git project + rates + model
    owner = get(data, "workspace", "repo", "owner")
    name = get(data, "workspace", "repo", "name")
    branch = safe(head_branch, root)
    if name:
        gp = f"{GREY}git{RESET} {WHITE}{(str(owner) + '/' if owner else '') + str(name)}{RESET}"
    elif branch:
        gp = f"{GREY}git{RESET} {WHITE}{os.path.basename(root)}{RESET}"
    else:
        gp = f"{GREY}no git{RESET}"
    if branch:
        dirty = "*" if safe(git_dirty, root) else ""
        gp += f" {V0}{V}{RESET} {(WARN if dirty else OK)}{branch}{dirty}{RESET}"
    model = get(data, "model", "display_name") or get(data, "model", "id") or "?"
    pill = safe(model_pill, model, effort) or f"{V2}{model}{RESET}"
    rates = safe(seg_window_inline, data) or ""
    prseg = safe(seg_pr, data) or ""
    updseg = safe(seg_update) or ""
    head_bits = [b for b in (rates, prseg, updseg) if b]
    right = ("   ".join(head_bits) + "   " if head_bits else "") + pill
    # churn is the lowest-priority left segment: append it only if the whole
    # "+N/-M" fits beside the right cluster — never let lr() clip it to "lines …".
    ln = safe(seg_lines, data)
    if ln and vlen(gp) + 2 + vlen(ln) + 3 + vlen(right) <= inner:
        gp += f"  {ln}"
    box.row(lr(gp, right, inner))

    box.sep()

    # arbiter line (gated)
    if arb:
        s = f" {V0}·{RESET} "
        qcol = DANGER if arb["q"] > 0 else GREY
        ocol = DANGER if arb["over"] > 0 else GREY
        tcol = WHITE if arb["tasks"] > 0 else GREY
        arbline = (
            f"{OK}{DOT}{RESET} {WHITE}stage:{arb['stage']}{RESET}{s}{tcol}tasks:{arb['tasks']}{RESET}"
            f"{s}{qcol}q:{arb['q']}{RESET}{s}{ocol}over:{arb['over']}{RESET}"
        )
        prune_bit = safe(seg_prune, data, sid)
        if prune_bit:
            arbline += f"{s}{prune_bit}"
        box.row(arbline)
        box.sep()

    # usage block — Session over Total (label │ ↓ in  ↑ out │ $cost), a
    # double-height left table; the right column carries the context-window
    # detail. Rate limits live on the header line now, not their own row.
    LW = max(34, min(50, inner // 2))   # proportional: don't starve the ctx panel at narrow widths
    srow = safe(usage_row, "Session", sess["in"], sess["out"], sess["cost"], s_trail) or ""
    trow = safe(usage_row, "Today", day["in"], day["out"], day["cost"]) or ""
    ctxl = safe(seg_ctx_lines, data, max(8, inner - LW - 3)) or [f"{GREY}ctx --{RESET}", ""]
    div = f"{V0}{V}{RESET}"
    box.row(f"{pad(srow, LW)} {div} {ctxl[0]}")
    cl2 = ctxl[1] if len(ctxl) > 1 else ""
    cl2 = f"{cl2}   {age_str}" if cl2 else age_str   # session age sits under the bar, by the compact %
    box.row(f"{pad(trow, LW)} {div} {cl2}")
    tail_tees = []

    # subagent rows (gated on presence; lean mode drops)
    if not compact:
        sdir = safe(subagent_dir, data, root, sid)
        if sdir:
            res = safe(read_subagents, sdir)
            if res:
                active, recent, shown, (tin, tout) = res
                if shown:
                    box.sep()
                    hdr = f"{V3}subagents{RESET} {WHITE}{active}{RESET} {GREY}active{RESET}"
                    if recent > active:   # reconcile the header with the rows shown
                        hdr += f" {V0}·{RESET} {GREY}{recent} recent{RESET}"
                    hdr += (f"  {V2}{DN}{RESET} {WHITE}{fmt_tok(tin)}{RESET}"
                            f" {V2}{UP}{RESET} {WHITE}{fmt_tok(tout)}{RESET}")
                    box.row(hdr)
                    for sub in shown:
                        live = sub.get("active")
                        glyph = f"{OK}{DOT}{RESET}" if live else f"{GREY}✓{RESET}"
                        lcol = WHITE if live else GREY
                        # build the token/duration tail once so its width is known
                        tail = (f" {V2}{DN}{RESET} {GREY}{fmt_tok(sub['inp'])}{RESET}"
                                f" {V2}{UP}{RESET} {GREY}{fmt_tok(sub['out'])}{RESET}"
                                f"  {DIM}{human_dur(sub['age'])}{RESET}")
                        # grow the label to its natural width up to the row limit, then the
                        # tail sits right after it (was a fixed 22, wasting wide terminals);
                        # clip (not pad) keeps the metrics adjacent and leaves trailing space
                        lw = max(22, inner - 4 - vlen(tail))   # cap so the row can't overflow
                        box.row(f"  {glyph} {lcol}{clip(sub['label'], lw)}{RESET}{tail}")
                    tail_tees = []

    box.bottom(tees=tail_tees)
    out = box.render()
    out = redshift(out) if safe(dev_active, root) else out
    # Honor the NO_COLOR convention by stripping SGR from the final render. Do NOT gate on
    # isatty: a Claude Code statusline is intentionally piped, so an isatty test would drop
    # color in normal use. Width math already ignores ANSI, so stripping keeps alignment.
    if os.environ.get("NO_COLOR"):
        out = ANSI.sub("", out)
    return out


def main():
    if os.environ.get("CODEARBITER_STATUSLINE", "").lower() == "off":
        return
    for s in (sys.stdout, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raw = ""
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        raw = ""
    try:
        out = render(raw)
        b = out.encode("utf-8", "replace")
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(b)
            buf.flush()
        else:
            sys.stdout.write(out)
    except Exception:
        # A statusline must never emit a traceback. Degrade to no output.
        return


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through)."""
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
