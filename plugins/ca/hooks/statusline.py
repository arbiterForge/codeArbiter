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
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone

# Shared task-board logic so the "tasks" segment counts in-flight items the same
# way the SessionStart hook does (excludes done). Guarded: a failed import must
# degrade the segment, never break the box (robustness contract above).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _taskboardlib import count_in_flight as _count_in_flight, read_board as _read_board
except Exception:  # pragma: no cover — never let an import break the statusline
    _count_in_flight = None

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

# The cost/token ledger subsystem now lives in _ledgerlib (extracted T-12) with
# zero import-time side effects. Re-bind its functions into this module so the
# cost segment — and the existing test suite that reaches them via statusline —
# keep working. Guarded: a missing lib leaves the names None and the cost segment
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

# --------------------------------------------------------------------------- color
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


# --------------------------------------------------------------------------- coercion / width
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


# --------------------------------------------------------------------------- format
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
        idx = 3 if span <= 0 else int((v - lo) / span * (len(SPARK) - 1) + 0.5)
        chars.append(SPARK[max(0, min(len(SPARK) - 1, idx))])
    s = "".join(chars)
    return gradient_h(s, len(s)) if grad else f"{V2}{s}{RESET}"


# --------------------------------------------------------------------------- git
def project_root(data):
    pd = (get(data, "workspace", "project_dir")
          or get(data, "workspace", "current_dir")
          or get(data, "cwd") or os.getcwd())
    cur = os.path.abspath(pd)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isdir(os.path.join(cur, ".codearbiter")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(pd)
        cur = parent


def head_branch(root):
    try:
        with open(os.path.join(root, ".git", "HEAD"), encoding="utf-8", errors="replace") as f:
            ref = f.read().strip()
        if ref.startswith("ref:"):
            name = ref.split(" ", 1)[1].strip() if " " in ref else ref[4:].strip()
            for p in ("refs/heads/", "refs/remotes/", "refs/tags/"):
                if name.startswith(p):
                    return name[len(p):]
            return name
        return ref[:7]   # detached HEAD -> short sha
    except OSError:
        return None


def git_dirty(root):
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=1.5,
                             encoding="utf-8", errors="replace")
        return bool((out.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return False


# --------------------------------------------------------------------------- arbiter
def frontmatter(path):
    """Parse a properly-closed leading YAML frontmatter block into a key map. The
    *arbiter-enabled* decision is NOT made here — that activation contract is owned
    by _hooklib.frontmatter_enabled (see arbiter_state) so the box and the
    enforcement hooks read it one way. This reader exists only to surface the
    remaining display keys (e.g. `stage`) the boolean gate doesn't carry."""
    fm = {}
    try:
        # utf-8-sig transparently strips a leading BOM (Windows editors / PowerShell
        # Out-File default to UTF-8-with-BOM); plain utf-8 would leave it on line 1
        # and break the "---" frontmatter check.
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return fm
    if not lines or lines[0].strip() != "---":
        return fm
    closed = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    # A valid YAML frontmatter block is bounded by BOTH delimiters; an unterminated
    # block (no closing "---") is malformed — don't honor keys parsed to EOF.
    return fm if closed else {}


def count_matches(path, pattern):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return len(re.findall(pattern, f.read(), re.MULTILINE))
    except OSError:
        return 0


# mtime-keyed memo: statusline.py is a short-lived subprocess, but a single render
# can resolve arbiter_state more than once (safe() probes), and the StopHook fires
# the whole script on every tool-call completion. Caching on max(input mtime) makes
# the 5 .codearbiter/ reads happen at most once per (root, change), re-reading only
# when one of the inputs actually changes between renders.
_ARBITER_CACHE = {}        # root -> (mtime_key, result)
_ARBITER_FILES = ("CONTEXT.md", "overrides.log", "last-checkpoint",
                  "open-tasks.md", "open-questions.md", "sprint-active")


def _arbiter_mtime_key(cad):
    """Max mtime across the arbiter input files (missing files stat as -1.0). Two
    renders with the same key saw identical inputs, so the cached state is valid."""
    latest = -1.0
    for nm in _ARBITER_FILES:
        try:
            latest = max(latest, os.stat(os.path.join(cad, nm)).st_mtime)
        except OSError:
            pass
    return latest


def _arbiter_enabled(ctx_path):
    """The arbiter-enabled gate, owned by _hooklib.frontmatter_enabled when the lib
    is importable (so the box and the enforcement hooks agree on the activation
    contract). Falls back to the local frontmatter() parser only if the import
    failed — the defensive degrade path, never a hard dependency."""
    if _frontmatter_enabled is not None:
        try:
            enabled, _malformed = _frontmatter_enabled(ctx_path)
            return enabled
        except Exception:  # noqa: BLE001 — degrade to the local parser, never crash
            pass
    return frontmatter(ctx_path).get("arbiter", "").lower() == "enabled"


def arbiter_state(root):
    cad = os.path.join(root, ".codearbiter")
    mkey = _arbiter_mtime_key(cad)
    cached = _ARBITER_CACHE.get(root)
    if cached is not None and cached[0] == mkey:
        return cached[1]
    result = _arbiter_state_uncached(cad)
    _ARBITER_CACHE[root] = (mkey, result)
    return result


def _arbiter_state_uncached(cad):
    if not _arbiter_enabled(os.path.join(cad, "CONTEXT.md")):
        return None
    fm = frontmatter(os.path.join(cad, "CONTEXT.md"))
    total_over = count_matches(os.path.join(cad, "overrides.log"), r"^(?!\s*#)(?!\s*$).+")
    # last-checkpoint holds the override COUNT at the last /ca:checkpoint. A value
    # outside [0, total] is not a valid count (e.g. a timestamp from a stale writer)
    # -> fail safe to 0 so overrides are surfaced, never silently hidden.
    try:
        with open(os.path.join(cad, "last-checkpoint"), encoding="utf-8") as f:
            base = int(f.read().strip() or "0")
    except (OSError, ValueError):
        base = 0
    if base < 0 or base > total_over:
        base = 0
    ot_path = os.path.join(cad, "open-tasks.md")
    if _count_in_flight is not None:
        tasks = _count_in_flight(_read_board(ot_path) or "")
    else:
        # Degraded fallback (only if _taskboardlib failed to import): mirror
        # count_in_flight's done-exclusion inline so the segment never silently
        # re-inflates to the pre-schema count. Never crashes the box.
        tasks = count_matches(ot_path, r"^- (?!\[[xX]\])")
    return {
        "stage": fm.get("stage", "-"),
        "tasks": tasks,
        "q": count_matches(os.path.join(cad, "open-questions.md"), r"CONFIRM-[0-9]+"),
        "over": max(0, total_over - base),
        "sprint": os.path.exists(os.path.join(cad, "sprint-active")),
    }


# --------------------------------------------------------------------------- ledger
# The token/cost ledger (pricing table, transcript accumulation, JSON persistence,
# burn samples) lives in _ledgerlib (extracted T-12). Its functions actually used
# from this module — ledger_update, _tx_accumulate, persist_sess_start — are bound
# into this module at import time (see the guarded import at the top), so the cost
# segment and the test suite reach them unchanged. Only burn_spark stays here: it
# is the render bridge that turns the lib's numeric samples into a colored
# sparkline, so it keeps the ANSI dependency out of the lib.
def burn_spark(rec):
    """Sparkline of recent per-message token burn — real per-API-call totals
    accumulated from the transcript (via _ledgerlib.burn_samples), not a
    time-extrapolated estimate."""
    samples = _ledgerlib.burn_samples(rec) if _ledgerlib is not None else []
    return sparkline(samples) if len(samples) >= 2 else ""


def _session_start_scan(sid):
    """The O(N) fallback: scan ~/.claude/sessions/*.json for the one whose
    sessionId matches `sid` and read its startedAt. The metadata file is named by
    the host PID, not the sessionId, so a direct name lookup isn't possible from
    here — a match-on-content scan is the only correct resolver. The caller caches
    the result in the ledger so this scan runs at most once per session."""
    d = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for nm in names:
        if not nm.endswith(".json"):
            continue
        fp = os.path.join(d, nm)
        try:
            if os.path.getsize(fp) > 65536:   # metadata is <1KB; never read a large file
                continue
            with open(fp, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and meta.get("sessionId") == sid:
            sa = num(meta.get("startedAt"), None)
            if sa:
                return sa / 1000.0 if sa > 1e12 else sa   # ms epoch -> seconds
    return None


def session_start(sid, rec=None):
    """True session start (epoch seconds) from Claude Code's own session metadata
    (~/.claude/sessions/<pid>.json, matched on sessionId). This is the wall-clock
    start /usage reports, INCLUDING idle/suspend gaps the current transcript can't
    show. None if unavailable -> caller falls back to the transcript.

    Fast path: the resolved value is cached in the ledger record (`rec["sess_start"]`),
    which ledger_update persists, so subsequent renders skip the per-render directory
    scan entirely. On a cache miss the full scan runs once and seeds the cache."""
    if not sid:
        return None
    if isinstance(rec, dict):
        cached = num(rec.get("sess_start"), None)
        if cached:
            return cached
    sa = _session_start_scan(sid)
    if sa and isinstance(rec, dict):
        rec["sess_start"] = sa   # seed the ledger cache; ledger_update persists it
    return sa


# --------------------------------------------------------------------------- subagents
def subagent_dir(data, root, sid):
    """Resolve the current session's subagents directory: prefer transcript_path
    (authoritative), else derive the project slug from cwd + session id."""
    tp = data.get("transcript_path") if isinstance(data, dict) else None
    if tp:
        base = os.path.dirname(tp)
        sess = os.path.splitext(os.path.basename(tp))[0]
        cand = os.path.join(base, sess, "subagents")
        if os.path.isdir(cand):
            return cand
    if sid:
        cwd = get(data, "workspace", "current_dir") or get(data, "cwd") or root
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd))
        cand = os.path.join(os.path.expanduser("~"), ".claude", "projects", slug, sid, "subagents")
        if os.path.isdir(cand):
            return cand
    return None


ACTIVE_WINDOW = 150       # secs: a subagent file touched this recently is "active"
SHOW_WINDOW = 600         # secs: still display recently-finished subagents
MAX_SUB_ROWS = 4
MAX_SUB_FILES = 12        # hot-path bound: parse at most this many files / render
MAX_SUB_LINES = 2500      # per-file line cap


def read_subagents(sdir):
    """Return (active, recent, shown[{label,inp,out,age,active}], (tot_in, tot_out)).
    `active` = files touched within ACTIVE_WINDOW (a liveness proxy); `recent` =
    all files within SHOW_WINDOW (active + recently finished)."""
    now = time.time()
    files = []
    try:
        for nm in os.listdir(sdir):
            if not nm.endswith(".jsonl"):
                continue
            fp = os.path.join(sdir, nm)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            if now - st.st_mtime <= SHOW_WINDOW:
                files.append((st.st_mtime, st.st_size, fp, nm))
    except OSError:
        return 0, [], (0, 0)
    files.sort(reverse=True)   # most-recently-touched first

    active = sum(1 for mtime, _, _, _ in files if now - mtime <= ACTIVE_WINDOW)
    shown, tot_in, tot_out = [], 0, 0
    for mtime, size, fp, nm in files[:MAX_SUB_FILES]:
        if size > 16 * 1024 * 1024:
            continue
        reqs = {}
        label = None
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, ln in enumerate(f):
                    if i > MAX_SUB_LINES:
                        break
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        d = json.loads(ln)
                    except ValueError:
                        continue
                    msg = d.get("message")
                    if not isinstance(msg, dict):
                        continue
                    if label is None and msg.get("role") == "user":
                        label = sub_label(msg.get("content"))
                    u = msg.get("usage")
                    if isinstance(u, dict):
                        # dedupe by requestId; fresh input only (cache reads excluded)
                        # — same definition as the Session/Today rows.
                        reqs[d.get("requestId") or msg.get("id") or i] = (
                            num(u.get("input_tokens")) + num(u.get("cache_creation_input_tokens")),
                            num(u.get("output_tokens")))
        except OSError:
            continue
        inp = sum(v[0] for v in reqs.values())
        out = sum(v[1] for v in reqs.values())
        tot_in += inp
        tot_out += out
        if len(shown) < MAX_SUB_ROWS:
            shown.append({"label": label or ("agent-" + re.sub(r"\.jsonl$", "", nm)[-6:]),
                          "inp": inp, "out": out, "age": now - mtime,
                          "active": now - mtime <= ACTIVE_WINDOW})
    return active, len(files), shown, (tot_in, tot_out)


def sub_label(content):
    """Derive a label from a subagent's first user message. A short, title-like
    first line wins (a dispatcher may lead the prompt with one); otherwise flatten
    and drop a boilerplate role-assignment preamble so the visible text carries
    signal instead of "You are a...". Truncation to the row width is the render's
    job (clip()), so this returns the full cleaned string up to a sane cap."""
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                text = blk.get("text", "")
                break
            if isinstance(blk, str):
                text = blk
                break
    raw = str(text)
    # strip leading reminder/system blocks up front (multi-line safe), then a lone tag
    raw = re.sub(r"^\s*(?:<([^>\s]+)[^>]*>.*?</\1>\s*)+", "", raw, flags=re.S)
    raw = re.sub(r"^\s*<[^>]+>\s*", "", raw)
    # a short, title-like first line wins (rewards a leading title line)
    first = ""
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln:
            first = ln
            break
    if 0 < len(first) <= 60 and not re.match(r"(?i)^(you are|act as|role\s*:)\b", first):
        return first
    # otherwise flatten and strip a leading role-assignment preamble (one or more sentences)
    flat = re.sub(r"\s+", " ", raw).strip()
    flat = re.sub(r"(?i)^(?:(?:you are|you're|act as|role\s*:)\b[^.]*\.\s*)+", "", flat)
    return flat[:80].strip()


# --------------------------------------------------------------------------- box
class Box:
    def __init__(self, width):
        self.W = width
        self.inner = width - 4   # "│ " + content + " │"
        self.lines = []

    def top(self, title, badge=""):
        left = f"{V0}{TL}{H}{H}{RESET} "          # 4 visible cols
        b = f" {badge} " if badge else " "
        budget = max(1, self.W - 5 - vlen(b))     # keep room for ╮ + >=0 fill
        title = clip(title, budget) if vlen(title) > budget else title
        t = gradient_h(ANSI.sub("", title), vlen(title))
        used = 3 + vlen(title) + vlen(b)
        fillw = max(0, self.W - 1 - used - 1)
        fill = gradient_h(H * fillw, fillw, (90, 60, 150), (170, 110, 240)) if fillw else ""
        self.lines.append(f"{left}{t}{b}{fill}{V0}{TR}{RESET}")

    def row(self, content):
        self.lines.append(f"{V0}{V}{RESET} {pad(content, self.inner)} {V0}{V}{RESET}")

    def sep(self, tees=None):
        mid = [DOTH] * (self.inner + 2)
        for k in (tees or []):
            if 0 <= k + 1 < len(mid):
                mid[k + 1] = TD
        self.lines.append(f"{V0}{LT}{''.join(mid)}{RT}{RESET}")

    def bottom(self, tees=None):
        mid = [H] * (self.inner + 2)
        for k in (tees or []):
            if 0 <= k + 1 < len(mid):
                mid[k + 1] = TU
        self.lines.append(f"{V0}{BL}{''.join(mid)}{BR}{RESET}")

    def render(self):
        # No trailing newline: a multi-line statusline that ends in '\n' adds a
        # phantom row, so the host's height accounting drifts on re-render and the
        # bar eventually clears itself. Lines are separated, not terminated.
        return "\n".join(self.lines)


def lr(left, right, inner):
    """Left + right justified within inner; never exceeds inner (clips left)."""
    right = clip(right, inner)
    rw = vlen(right)
    left = clip(left, max(0, inner - rw - 1))
    gap = max(1, inner - vlen(left) - rw)
    return left + " " * gap + right


def cols(cells, inner):
    """Lay out cells in equal columns with ' │ ' joins. Each cell is clamped to
    its column via pad(), so total visible width == inner exactly and the
    separator tees line up with the content joins. Returns (content, bounds)."""
    n = len(cells)
    if n == 1:
        return pad(cells[0], inner), []
    seps = n - 1
    avail = inner - seps * 3
    base = avail // n
    widths = [base] * n
    widths[-1] = avail - base * (n - 1)
    parts, bounds, pos = [], [], 0
    for i, c in enumerate(cells):
        parts.append(pad(c, widths[i]))
        pos += widths[i]
        if i < n - 1:
            parts.append(f" {V0}{V}{RESET} ")
            bounds.append(pos + 1)
            pos += 3
    return "".join(parts), bounds


# --------------------------------------------------------------------------- segments
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
    fill = gradient_h(BFULL * filled, max(1, filled)) if pctf < 75 else f"{col}{BFULL * filled}"
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
    body = f" {m} {V} {EFF_DISP.get(eff, eff.capitalize())} " if eff else f" {m} "
    lo = tuple(int(v * 0.5) for v in c)           # dark start of the sheen
    n = max(1, len(body) - 1)
    cells = []
    for idx, ch in enumerate(body):
        t = idx / n
        rr = int(lo[0] + (c[0] - lo[0]) * t)
        gg = int(lo[1] + (c[1] - lo[1]) * t)
        bb = int(lo[2] + (c[2] - lo[2]) * t)
        cells.append(f"{bg(rr, gg, bb)}{PILL_FG}{BOLD}{ch}")
    return "".join(cells) + RESET


def usage_row(label, tin, tout, cost, trail=""):
    """One row of the Session/Today mini-table: label │ ↓in ↑out │ $cost. in/out are
    fresh (sent) tokens; `cost` is Claude Code's real session cost (cost.total_cost_usd),
    not an estimate. `trail` carries extras (session age, burn sparkline)."""
    base = (f"{GREY}{label:<7}{RESET} {V0}{V}{RESET} "
            f"{V2}{DN}{RESET} {WHITE}{fmt_tok(tin):>6}{RESET} "
            f"{V2}{UP}{RESET} {WHITE}{fmt_tok(tout):>6}{RESET} {V0}{V}{RESET} "
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


def seg_prune(data, sid):
    """Transcript-pruner indicator: cumulative reduction and age of the last
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
        pct = rec.get("pct") or 0
        if pct <= 0:
            return None
        age = human_dur(max(0, time.time() - num(rec.get("last_run_ts"), time.time())))
        return f"{GREY}✂{RESET} {WHITE}{pct:.0f}%{RESET} {GREY}{age}{RESET}"
    except Exception:  # noqa: BLE001
        return None


def dev_active(root):
    """True when /dev developer-override mode is on — signalled by a transient marker
    the orchestrator drops on /dev and clears on /arbiter (a local UI flag, not a log)."""
    return os.path.exists(os.path.join(root, ".codearbiter", ".markers", "dev-active"))


def redshift(s):
    """/dev tell: recolor every truecolor SGR to a red of matching brightness, so the
    WHOLE bar turns alarm-red — a glaring sign orchestration is suspended."""
    def repl(m):
        lum = max(int(m.group(2)), int(m.group(3)), int(m.group(4)))
        return f"\033[{m.group(1)};2;{min(255, 96 + lum)};{lum // 6};{lum // 7}m"
    return re.sub(r"\033\[(38|48);2;(\d+);(\d+);(\d+)m", repl, s)


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


if __name__ == "__main__":
    main()
