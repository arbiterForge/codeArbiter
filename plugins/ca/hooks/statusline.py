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
#   - tokens + cost derive from the session TRANSCRIPT, not host snapshots: each
#     assistant message's real per-model usage is accumulated, and the cost shown
#     is the estimated pay-as-you-go API-equivalent (tokens * API list price,
#     cache rates included), labelled "api≈" so it reads as an estimate.
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


def arbiter_state(root):
    cad = os.path.join(root, ".codearbiter")
    fm = frontmatter(os.path.join(cad, "CONTEXT.md"))
    if fm.get("arbiter", "").lower() != "enabled":
        return None
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
    return {
        "stage": fm.get("stage", "-"),
        "tasks": count_matches(os.path.join(cad, "open-tasks.md"), r"^- "),
        "q": count_matches(os.path.join(cad, "open-questions.md"), r"CONFIRM-[0-9]+"),
        "over": max(0, total_over - base),
        "sprint": os.path.exists(os.path.join(cad, "sprint-active")),
    }


# --------------------------------------------------------------------------- ledger
def ledger_path():
    return os.environ.get("CODEARBITER_LEDGER") or \
        os.path.join(os.path.expanduser("~"), ".codearbiter", "ledger.json")


SESSION_TTL = 36 * 3600  # prune sessions older than ~1.5 days
BURN_RING = 40           # recent per-call token-burn samples kept for the sparkline
TX_MAX_NEW_LINES = 20000 # hot-path bound: transcript lines parsed per render

# API list prices, USD per 1M tokens (captured 2026-06-06 from Anthropic's
# pricing pages). Used ONLY to estimate the pay-as-you-go API-equivalent cost of
# this session's REAL tokens — the bar labels it "api≈"; it is not a bill.
# Per model family: (input, output, cache_write_5m, cache_write_1h, cache_read).
API_PRICES = {
    "opus":   (5.0, 25.0, 6.25, 10.0, 0.50),
    "sonnet": (3.0, 15.0, 3.75,  6.0, 0.30),
    "haiku":  (1.0,  5.0, 1.25,  2.0, 0.10),
}


def price_for(model):
    ml = str(model).lower()
    for fam, p in API_PRICES.items():
        if fam in ml:
            return p
    return API_PRICES["sonnet"]   # reasonable mid default for an unrecognized model


def api_cost(tok):
    """Estimated pay-as-you-go API cost (USD) for accumulated per-model tokens."""
    total = 0.0
    for model, t in (tok or {}).items():
        if not isinstance(t, dict):
            continue
        pin, pout, p5, p1, pr = price_for(model)
        total += (num(t.get("in")) * pin + num(t.get("out")) * pout
                  + num(t.get("c5")) * p5 + num(t.get("c1")) * p1
                  + num(t.get("cr")) * pr) / 1e6
    return total


def _msg_date(ts):
    """Local calendar date (YYYY-MM-DD) of a transcript message's timestamp, so
    tokens are attributed to the day they were actually burned (a session that
    crosses midnight splits correctly across days)."""
    e = parse_iso(ts) if isinstance(ts, str) else None
    if e is None:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        return datetime.fromtimestamp(e).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return datetime.now().strftime("%Y-%m-%d")


def _tx_accumulate(rec, tx_path):
    """Tail the session transcript JSONL from the stored byte offset, folding each
    NEW assistant message's real token usage into per-DAY, per-model buckets and
    pushing a per-message burn sample. The transcript is append-only, so each
    render parses only the bytes since last time — O(new lines). Returns True if
    the offset advanced (state changed)."""
    if not tx_path or not os.path.isfile(tx_path):
        return False
    try:
        size = os.path.getsize(tx_path)
    except OSError:
        return False
    if not isinstance(rec.get("days"), dict):
        rec["days"] = {}          # fresh record, or migrating from the pre-day schema
        rec["tx_off"] = 0
        rec.pop("tok", None)
    if not isinstance(rec.get("burn"), list):
        rec["burn"] = []
    off = int(num(rec.get("tx_off")))
    # New transcript for this session, or truncation/rotation -> reparse from start.
    if rec.get("tx_path") != tx_path or off > size:
        off, rec["days"], rec["burn"], rec["tx_path"] = 0, {}, [], tx_path
    if off >= size:
        return False
    try:
        with open(tx_path, "rb") as f:
            f.seek(off)
            chunk = f.read()
    except OSError:
        return False
    new_off = size
    # A writer may flush mid-line; keep a trailing partial line for next render.
    if chunk and not chunk.endswith(b"\n"):
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return False                 # no complete line yet
        new_off = off + cut + 1
        chunk = chunk[:cut]
    parsed = 0
    for raw in chunk.split(b"\n"):
        if not raw.strip():
            continue
        parsed += 1
        if parsed > TX_MAX_NEW_LINES:
            break
        try:
            o = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("type") != "assistant":
            continue
        m = o.get("message")
        u = m.get("usage") if isinstance(m, dict) else None
        if not isinstance(u, dict):
            continue
        model = m.get("model") or "?"
        i = num(u.get("input_tokens"))
        cr = num(u.get("cache_read_input_tokens"))
        cc = u.get("cache_creation")
        if isinstance(cc, dict):
            c5 = num(cc.get("ephemeral_5m_input_tokens"))
            c1 = num(cc.get("ephemeral_1h_input_tokens"))
        else:
            c5 = c1 = 0.0
        cw = num(u.get("cache_creation_input_tokens"))
        if cw and not (c5 or c1):        # 5m/1h split absent -> treat all as 5m
            c5 = cw
        out = num(u.get("output_tokens"))
        daymap = rec["days"].setdefault(_msg_date(o.get("timestamp")), {})
        t = daymap.setdefault(
            model, {"in": 0.0, "cr": 0.0, "c5": 0.0, "c1": 0.0, "out": 0.0})
        t["in"] += i; t["cr"] += cr; t["c5"] += c5; t["c1"] += c1; t["out"] += out
        rec["burn"].append(i + cr + c5 + c1 + out)   # total tokens billed this call
    if len(rec["burn"]) > BURN_RING:
        rec["burn"] = rec["burn"][-BURN_RING:]
    rec["tx_off"] = new_off
    return True


def _merge_days(days, only=None):
    """Merge {date:{model:tokens}} into {model: tokens}; if `only` is a date,
    merge just that day's bucket (used for the per-calendar-day Today totals)."""
    out = {}
    for d, daymap in (days or {}).items():
        if only is not None and d != only:
            continue
        if not isinstance(daymap, dict):
            continue
        for model, t in daymap.items():
            if not isinstance(t, dict):
                continue
            o = out.setdefault(model, {"in": 0.0, "cr": 0.0, "c5": 0.0, "c1": 0.0, "out": 0.0})
            for k in o:
                o[k] += num(t.get(k))
    return out


def _totals(models):
    """Display totals (in incl. cache, out) + API-equivalent cost for a model map."""
    tin = tout = 0.0
    for t in (models or {}).values():
        if isinstance(t, dict):
            tin += num(t.get("in")) + num(t.get("cr")) + num(t.get("c5")) + num(t.get("c1"))
            tout += num(t.get("out"))
    return {"in": tin, "out": tout, "cost": api_cost(models)}


def ledger_update(data, sid):
    """Read-modify-write the per-session ledger. Accumulate the session's TRUE
    token usage by tailing its transcript, derive the API-equivalent cost, and
    return (session record, this-session totals, today's totals across sessions).
    Best-effort; safe blanks on any failure. The file self-heals on next write."""
    blank = {"in": 0.0, "out": 0.0, "cost": 0.0}
    if not sid:
        return {}, dict(blank), dict(blank)
    path = ledger_path()
    now = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    led = {}
    try:
        with open(path, encoding="utf-8") as f:
            led = json.load(f)
    except (OSError, ValueError):
        led = {}
    if not isinstance(led, dict):
        led = {}
    sessions = led.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}

    rec = sessions.get(sid)
    dirty = not isinstance(rec, dict)
    if dirty:
        rec = {}
    rec.setdefault("first_ts", now)
    rec["last_ts"] = now
    rec["host_cost"] = num(get(data, "cost", "total_cost_usd"))

    tx = data.get("transcript_path") if isinstance(data, dict) else None
    if safe(_tx_accumulate, rec, tx):
        dirty = True
    sess = _totals(_merge_days(rec.get("days")))            # this session, all its days
    rec["today"] = dict(_totals(_merge_days(rec.get("days"), only=today)), date=today)
    rec.pop("tot", None)                    # retire the batch-1 whole-session cache key
    sessions[sid] = rec

    for k in list(sessions.keys()):
        v = sessions[k]
        if not isinstance(v, dict) or now - num(v.get("last_ts")) > SESSION_TTL:
            del sessions[k]
            dirty = True
    led["sessions"] = sessions

    if dirty:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"   # per-process staging: no concurrent clobber
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(led, f)
            os.replace(tmp, path)
        except OSError:
            pass

    # Today = each session's TODAY bucket (tokens whose transcript timestamp falls
    # on the current local day), summed across sessions — not whole-session totals.
    day = dict(blank)
    for v in sessions.values():
        t = v.get("today") if isinstance(v, dict) and isinstance(v.get("today"), dict) else None
        if t and t.get("date") == today:
            day["in"] += num(t.get("in"))
            day["out"] += num(t.get("out"))
            day["cost"] += num(t.get("cost"))
    return rec, sess, day


def burn_spark(rec):
    """Sparkline of recent per-message token burn — real per-API-call totals
    accumulated from the transcript, not a time-extrapolated estimate."""
    b = [num(x) for x in (rec.get("burn") or []) if isinstance(x, (int, float))]
    return sparkline(b[-24:]) if len(b) >= 2 else ""


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
        inp = out = 0
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
                        inp += (num(u.get("input_tokens")) + num(u.get("cache_read_input_tokens"))
                                + num(u.get("cache_creation_input_tokens")))
                        out += num(u.get("output_tokens"))
        except OSError:
            continue
        tot_in += inp
        tot_out += out
        if len(shown) < MAX_SUB_ROWS:
            shown.append({"label": label or ("agent-" + re.sub(r"\.jsonl$", "", nm)[-6:]),
                          "inp": inp, "out": out, "age": now - mtime,
                          "active": now - mtime <= ACTIVE_WINDOW})
    return active, len(files), shown, (tot_in, tot_out)


def sub_label(content):
    """Derive a short, sanitized label from a subagent's first user message."""
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
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = re.sub(r"^<[^>]+>\s*", "", text)   # strip a leading reminder/system tag
    return (text[:21] + ELL) if len(text) > 22 else text


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
            tail = f"{WHITE}{human_dur(dt)}{RESET}" if dt > 0 else f"{GREY}—{RESET}"
            cell += f" {GREY}{ARR}{RESET} {tail}"
        cells.append(cell)
    return cells


def seg_window_inline(data):
    """Compact single-string rate-limit readout for the header line."""
    cells = seg_window_cells(data)
    return f" {V0}·{RESET} ".join(cells) if cells else ""


def model_pill(model):
    """A colored pill behind the model name, keyed by family — Opus pops violet,
    Sonnet reads blue (the daily driver), Haiku green — so the active model is
    obvious at a glance instead of plain text."""
    m = str(model)
    ml = m.lower()
    if "opus" in ml:
        b = bg(178, 102, 255)     # neon violet
    elif "sonnet" in ml:
        b = bg(96, 174, 235)      # blue
    elif "haiku" in ml:
        b = bg(120, 220, 150)     # green
    else:
        b = bg(150, 150, 162)     # grey (unknown)
    return f"{b}{PILL_FG}{BOLD} {m} {RESET}"


def usage_row(label, tin, tout, cost, spark=""):
    """One row of the Session/Today mini-table: label │ ↓in ↑out │ api≈$cost, with
    fixed-width numeric fields so the rows align. `cost` is the estimated API-
    equivalent price of the real tokens (hence api≈); `spark` is the per-call burn."""
    base = (f"{GREY}{label:<7}{RESET} {V0}{V}{RESET} "
            f"{V2}{DN}{RESET} {WHITE}{fmt_tok(tin):>6}{RESET} "
            f"{V2}{UP}{RESET} {WHITE}{fmt_tok(tout):>6}{RESET} {V0}{V}{RESET} "
            f"{DIM}api{RESET}{OK}≈{usd_fine(cost)}{RESET}")
    return base + (f"  {spark}" if spark else "")


def seg_lines(data):
    add = get(data, "cost", "total_lines_added")
    rem = get(data, "cost", "total_lines_removed")
    if add is None and rem is None:
        return None
    return f"{GREY}lines{RESET} {OK}+{fmt_tok(add)}{RESET}{GREY}/{RESET}{DANGER}-{fmt_tok(rem)}{RESET}"


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
    badge = (f"{V3}{BOLD}[SPRINT]{RESET}" if sprint
             else (f"{V3}[ultra]{RESET}" if effort in ("xhigh", "max") else ""))

    led = safe(ledger_update, data, sid)
    if not (isinstance(led, tuple) and len(led) == 3):
        led = ({}, {"in": 0.0, "out": 0.0, "cost": 0.0}, {"in": 0.0, "out": 0.0, "cost": 0.0})
    rec, sess, day = led
    spark = safe(burn_spark, rec) or ""

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
    pill = safe(model_pill, model) or f"{V2}{model}{RESET}"
    rates = safe(seg_window_inline, data) or ""
    prseg = safe(seg_pr, data) or ""
    head_bits = [b for b in (rates, prseg) if b]
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
        box.row(
            f"{OK}{DOT}{RESET} {WHITE}stage:{arb['stage']}{RESET}{s}{tcol}tasks:{arb['tasks']}{RESET}"
            f"{s}{qcol}q:{arb['q']}{RESET}{s}{ocol}over:{arb['over']}{RESET}"
        )
        box.sep()

    # usage block — Session over Total (label │ ↓ in  ↑ out │ $cost), a
    # double-height left table; the right column carries the context-window
    # detail. Rate limits live on the header line now, not their own row.
    LW = max(34, min(50, inner // 2))   # proportional: don't starve the ctx panel at narrow widths
    srow = safe(usage_row, "Session", sess["in"], sess["out"], sess["cost"], spark) or ""
    trow = safe(usage_row, "Today", day["in"], day["out"], day["cost"]) or ""
    ctxl = safe(seg_ctx_lines, data, max(8, inner - LW - 3)) or [f"{GREY}ctx --{RESET}", ""]
    div = f"{V0}{V}{RESET}"
    box.row(f"{pad(srow, LW)} {div} {ctxl[0]}")
    box.row(f"{pad(trow, LW)} {div} {ctxl[1] if len(ctxl) > 1 else ''}")
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
                        box.row(f"  {glyph} {lcol}{pad(sub['label'], 22)}{RESET}"
                                f" {V2}{DN}{RESET} {GREY}{fmt_tok(sub['inp'])}{RESET}"
                                f" {V2}{UP}{RESET} {GREY}{fmt_tok(sub['out'])}{RESET}"
                                f"  {DIM}{human_dur(sub['age'])}{RESET}")
                    tail_tees = []

    box.bottom(tees=tail_tees)
    return box.render()


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
