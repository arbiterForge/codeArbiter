#!/usr/bin/env python3
# codeArbiter statusline — dependency-free (Python stdlib only, no Nerd Font).
#
# Renders a sectioned, full-width box. The usage segments (folder, git, model,
# rate limits, context, tokens, cost, burn) render in every repo. The arbiter
# segments (stage / tasks / open-questions / overrides-since-checkpoint) render
# only when the repo's .codearbiter/CONTEXT.md frontmatter is `arbiter: enabled`.
#
# Design:
#   - single neon-violet palette (a subtle dark->bright sheen, no rainbow);
#     green/amber/red are reserved strictly for threshold status (ctx, rates).
#   - native-font glyphs only: box-drawing, block elements, arrows, ASCII labels.
#   - top line = active folder; second line = git project (owner/name + branch),
#     with a no-git fallback.
#   - cost trusts the host's cost.total_cost_usd (each call priced at the model
#     used when burned; subagents included) — no token*price recompute.
#   - context trusts context_window.used_percentage + context_window_size
#     (1M for million-token models, 200K otherwise) — never exceeds 100%.
#
# A small user-level ledger (~/.codearbiter/ledger.json) accumulates per-session
# cost/token/rate samples so the box can show today's spend across sessions, a
# recent $/hr burn rate, a burn sparkline + token rate, and 5h/7d burndown trends.
#
# Robustness contract: this script must NEVER print a traceback. The host pipes
# arbitrary JSON on stdin and the output lands in the user's terminal. Every
# segment is wrapped (safe()), the whole render is guarded, all host values pass
# through num() coercion, and every row is width-clamped so a bad value or a
# narrow terminal degrades a segment — it never breaks the box.
#
# Env:
#   CODEARBITER_STATUSLINE=off   disable entirely
#   CODEARBITER_COMPACT=1        drop the burn/reset/subagent rows (lean mode)
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
from datetime import datetime

# --------------------------------------------------------------------------- color
def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"

RESET, BOLD, DIM, ITAL = "\033[0m", "\033[1m", "\033[2m", "\033[3m"

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


def vlen(s):
    return len(ANSI.sub("", s))


def clip(s, w):
    """Truncate a (possibly ANSI-colored) string to <= w visible columns,
    preserving color codes and appending an ellipsis + RESET when cut."""
    if w <= 0:
        return ""
    if vlen(s) <= w:
        return s
    out, vis, i, n = [], 0, 0, len(s)
    limit = w - 1   # leave one column for the ellipsis
    while i < n and vis < limit:
        m = ANSI.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(s[i])
        vis += 1
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
    if n >= 1_000_000:
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
            return dt.timestamp()
        return dt.timestamp()
    except Exception:
        return None


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
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return fm
    if not lines or lines[0].strip() != "---":
        return fm
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


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
    try:
        with open(os.path.join(cad, "last-checkpoint"), encoding="utf-8") as f:
            base = int(f.read().strip() or "0")
    except (OSError, ValueError):
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


SAMPLE_INTERVAL = 12.0   # seconds heartbeat between persisted samples
RING = 40                # max samples kept per session
SESSION_TTL = 36 * 3600  # prune sessions older than ~1.5 days
BURN_MIN_DT = 60.0       # dampen $/hr extrapolation from a tiny window


def _valid_sample(r):
    return (isinstance(r, list) and len(r) >= 6
            and isinstance(r[0], (int, float)) and isinstance(r[1], (int, float)))


def ledger_update(data, sid):
    """Read-modify-write the per-session ledger; return (session record, today's
    total cost across sessions). Best-effort; ({}, 0.0) on any failure. Corrupt
    sample rows are dropped on load and the file self-heals on the next write."""
    if not sid:
        return {}, 0.0
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

    cost = num(get(data, "cost", "total_cost_usd"))
    cw = get(data, "context_window", default={}) or {}
    toks = num(cw.get("total_input_tokens")) + num(cw.get("total_output_tokens"))
    fh = get(data, "rate_limits", "five_hour", "used_percentage")
    sd = get(data, "rate_limits", "seven_day", "used_percentage")
    ctx = cw.get("used_percentage")

    rec = sessions.get(sid)
    if not isinstance(rec, dict):
        rec = {"first_ts": now, "samples": []}
    rec.setdefault("first_ts", now)
    rec["date"] = today
    rec["last_ts"] = now
    rec["last_cost"] = cost

    samples = rec.get("samples")
    samples = [r for r in samples if _valid_sample(r)] if isinstance(samples, list) else []
    # sample schema: [ts, cost, tokens, fh_pct, sd_pct, ctx_pct]
    changed = (samples != rec.get("samples"))   # dropped corrupt rows -> must persist
    last = samples[-1] if samples else None
    if last is None or (now - last[0]) >= SAMPLE_INTERVAL or cost != last[1]:
        samples.append([now, cost, toks,
                        num(fh, None), num(sd, None), num(ctx, None)])
        if len(samples) > RING:
            samples = samples[-RING:]
        changed = True
    rec["samples"] = samples
    sessions[sid] = rec

    for k in list(sessions.keys()):
        ts = sessions[k].get("last_ts", 0) if isinstance(sessions[k], dict) else 0
        if now - num(ts) > SESSION_TTL:
            del sessions[k]
            changed = True

    led["sessions"] = sessions

    if changed:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"   # per-process staging: no concurrent clobber
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(led, f)
            os.replace(tmp, path)
        except OSError:
            pass

    day_cost = 0.0
    for v in sessions.values():
        if isinstance(v, dict) and v.get("date") == today:
            day_cost += num(v.get("last_cost"))
    return rec, day_cost


def ledger_metrics(rec, dur_ms=None):
    """Derive recent $/hr burn, sparkline series, token rate, and burndown trends
    from a session's sample ring. $/hr is the rate over the sampled window (not
    anchored to first-seen time), with a host-duration fallback."""
    s = [r for r in (rec.get("samples") or []) if _valid_sample(r)]
    m = {"burn_hr": None, "cost_spark": "", "tok_rate": None,
         "fh_spark": "", "sd_spark": "", "session_cost": num(rec.get("last_cost"))}
    if len(s) >= 2 and s[-1][0] > s[0][0]:
        dc = max(0.0, (s[-1][1] or 0) - (s[0][1] or 0))
        dt = max(BURN_MIN_DT, s[-1][0] - s[0][0])
        m["burn_hr"] = dc / (dt / 3600.0)
    elif dur_ms:
        hrs = num(dur_ms) / 1000.0 / 3600.0
        if hrs > 0:
            m["burn_hr"] = m["session_cost"] / hrs

    deltas = []
    for i in range(1, len(s)):
        dt = max(1.0, s[i][0] - s[i - 1][0])
        deltas.append(max(0.0, (s[i][1] or 0) - (s[i - 1][1] or 0)) / dt)
    m["cost_spark"] = sparkline(deltas)

    tok_pts = [(p[0], p[2]) for p in s if isinstance(p[2], (int, float))]
    if len(tok_pts) >= 2:
        dt = tok_pts[-1][0] - tok_pts[0][0]
        dtok = tok_pts[-1][1] - tok_pts[0][1]
        if dt > 0 and dtok >= 0:
            m["tok_rate"] = dtok / (dt / 60.0)

    m["fh_spark"] = sparkline([p[3] for p in s], grad=False)
    m["sd_spark"] = sparkline([p[4] for p in s], grad=False)
    return m


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
    """Return (active_count, shown[{label,inp,out,age}], (tot_in, tot_out))."""
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
                        inp += num(u.get("input_tokens")) + num(u.get("cache_creation_input_tokens"))
                        out += num(u.get("output_tokens"))
        except OSError:
            continue
        tot_in += inp
        tot_out += out
        if len(shown) < MAX_SUB_ROWS:
            shown.append({"label": label or ("agent-" + re.sub(r"\.jsonl$", "", nm)[-6:]),
                          "inp": inp, "out": out, "age": now - mtime})
    return active, shown, (tot_in, tot_out)


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
def seg_context(data):
    cw = get(data, "context_window", default={}) or {}
    pct = cw.get("used_percentage")
    if pct is None:
        return f"{GREY}ctx --{RESET}"
    pf = num(pct, None)
    if pf is None:
        return f"{GREY}ctx --{RESET}"
    pctf = max(0.0, min(100.0, pf))
    size = int(num(cw.get("context_window_size"), 200000)) or 200000
    win = "1M" if size >= 1_000_000 else f"{size // 1000}K"
    resident = round(pctf / 100.0 * size)   # tracks the bar; not cumulative throughput
    col = V2 if pctf < 75 else (WARN if pctf < 90 else DANGER)
    barw = 22
    filled = max(0, min(barw, round(pctf / 100 * barw)))
    bar = gradient_h(BFULL * filled, max(1, filled)) + f"{V0}" + BEMPTY * (barw - filled) + RESET
    return f"{GREY}ctx{RESET} {bar} {col}{pctf:.0f}%{RESET} {DIM}{fmt_tok(resident)}/{win}{RESET}"


def seg_compaction(data):
    pct = get(data, "context_window", "used_percentage")
    if pct is None:
        return None
    pf = num(pct, None)
    if pf is None:
        return None
    thresh = num(os.environ.get("CODEARBITER_COMPACT_AT"), 92.0)
    head = thresh - pf
    if head <= 0:
        return f"{DANGER}{BOLT} compact imminent{RESET}"
    col = OK if head > 30 else (WARN if head > 12 else DANGER)
    return f"{GREY}{BOLT} compact{RESET} {col}~{head:.0f}%{RESET}"


def seg_rates(data):
    out = []
    for key, lbl in (("five_hour", "5h"), ("seven_day", "7d")):
        p = get(data, "rate_limits", key, "used_percentage")
        if p is None:
            continue
        pf = num(p, None)
        if pf is None:
            continue
        c = V2 if pf < 75 else (WARN if pf < 90 else DANGER)
        out.append(f"{GREY}{lbl}{RESET} {c}{pf:.0f}%{RESET}")
    return "  ".join(out)


def seg_tokens(data):
    cu = get(data, "context_window", "current_usage", default={}) or {}
    # keep in/out/cache on one basis: current_usage when present, else the totals
    if isinstance(cu, dict) and ("input_tokens" in cu or "output_tokens" in cu):
        tin, tout = num(cu.get("input_tokens")), num(cu.get("output_tokens"))
        cache = num(cu.get("cache_read_input_tokens"))
    else:
        tin = num(get(data, "context_window", "total_input_tokens"))
        tout = num(get(data, "context_window", "total_output_tokens"))
        cache = num(cu.get("cache_read_input_tokens")) if isinstance(cu, dict) else 0
    return (f"{V2}{DN}{RESET} {WHITE}{fmt_tok(tin)}{RESET} {DIM}({fmt_tok(cache)}){RESET} "
            f"{V2}{UP}{RESET} {WHITE}{fmt_tok(tout)}{RESET}")


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


def seg_daycost(day_cost, m):
    parts = [f"{OK}{usd_fine(day_cost)}{RESET} {GREY}today{RESET}"]
    if m.get("burn_hr") is not None:
        bc = WARN if m["burn_hr"] >= 8 else V2
        parts.append(f"{bc}{usd_fine(m['burn_hr'])}{GREY}/hr{RESET}")
    if m.get("cost_spark"):
        seg = f"{GREY}burn{RESET} {m['cost_spark']}"
        if m.get("tok_rate") is not None:
            seg += f" {DIM}{fmt_tok(m['tok_rate'])} t/m{RESET}"
        parts.append(seg)
    return f" {V0}·{RESET} ".join(parts)


def seg_trends(data, m):
    cells = []
    now = time.time()
    for key, lbl, spark in (("five_hour", "5h", "fh_spark"), ("seven_day", "7d", "sd_spark")):
        r = parse_iso(get(data, "rate_limits", key, "resets_at"))
        if r:
            c = f"{GREY}{lbl} {ARR}{RESET} {WHITE}{human_dur(r - now)}{RESET}"
            if m.get(spark):
                c += f" {m[spark]}"
            cells.append(c)
    if m.get("session_cost") is not None:
        cells.append(f"{GREY}session{RESET} {OK}{usd_fine(m['session_cost'])}{RESET}")
    return cells


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

    rec, day_cost = safe(ledger_update, data, sid) or ({}, 0.0)
    dur_ms = get(data, "cost", "total_duration_ms")
    metrics = (safe(ledger_metrics, rec, dur_ms) or {}) if rec else {}

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
    ln = safe(seg_lines, data)   # churn sits up here, next to the repo
    if ln:
        gp += f"  {ln}"
    model = get(data, "model", "display_name") or get(data, "model", "id") or "?"
    right = safe(seg_rates, data) or ""
    right = (right + "   " if right else "") + f"{V2}{model}{RESET}"
    box.row(lr(gp, right, inner))

    box.sep()

    # arbiter line (gated)
    if arb:
        s = f" {V0}·{RESET} "
        qcol = DANGER if arb["q"] > 0 else GREY
        ocol = DANGER if arb["over"] > 0 else GREY
        tcol = WARN if arb["tasks"] > 0 else GREY
        box.row(
            f"{OK}{DOT}{RESET} {WHITE}stage:{arb['stage']}{RESET}{s}{tcol}tasks:{arb['tasks']}{RESET}"
            f"{s}{qcol}q:{arb['q']}{RESET}{s}{ocol}over:{arb['over']}{RESET}"
        )
        box.sep()

    # context (+ compaction cue)
    ctx = safe(seg_context, data) or f"{GREY}ctx --{RESET}"
    comp = safe(seg_compaction, data)
    box.row(lr(ctx, comp, inner) if comp else ctx)

    # tokens │ PR  (lines churn moved up to the repo row)
    cells = [safe(seg_tokens, data) or f"{V2}{DN}{RESET} {WHITE}--{RESET}"]
    pr = safe(seg_pr, data)
    if pr:
        cells.append(pr)
    content, bounds = cols(cells, inner)
    box.sep(tees=bounds)
    box.row(content)
    tail_tees = bounds

    # cost / burn rows (lean mode drops these)
    if not compact:
        box.sep()
        box.row(safe(seg_daycost, day_cost, metrics) or f"{OK}{usd_fine(day_cost)}{RESET} {GREY}today{RESET}")
        tcells = safe(seg_trends, data, metrics) or []
        if tcells:
            tcontent, _ = cols(tcells, inner)
            box.row(tcontent)
        tail_tees = []

    # subagent rows (gated on presence; lean mode drops)
    if not compact:
        sdir = safe(subagent_dir, data, root, sid)
        if sdir:
            res = safe(read_subagents, sdir)
            if res:
                active, shown, (tin, tout) = res
                if shown:
                    box.sep()
                    box.row(f"{V3}subagents{RESET} {WHITE}{active}{RESET} {GREY}active{RESET}"
                            f"  {V2}{DN}{RESET} {WHITE}{fmt_tok(tin)}{RESET}"
                            f" {V2}{UP}{RESET} {WHITE}{fmt_tok(tout)}{RESET}")
                    for sub in shown:
                        box.row(f"  {V1}{SUBDOT}{RESET} {WHITE}{pad(sub['label'], 22)}{RESET}"
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
