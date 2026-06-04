#!/usr/bin/env python3
# codeArbiter v2 statusline — dependency-free reengineer of YAS.
#
# Design vs YAS (yet-another-statusline):
#  - Single neon-violet palette, NOT the green->purple rainbow gradient.
#  - Native-font only: box-drawing + block elements + ASCII labels. No Nerd-Font
#    Private-Use glyphs, no emoji, no "Symbols for Legacy Computing".
#  - Top line = active folder; second line = git project (owner/name + branch),
#    with a no-git fallback. (YAS put the session id in the border + folder/git
#    on one line.)
#  - Cost: trust Claude Code's cost.total_cost_usd (prices each call at the model
#    used WHEN burned and includes subagent usage). YAS recomputed from transcript
#    tokens * the CURRENT model price, excluding subagents — both wrong.
#  - Context: trust context_window.used_percentage + context_window_size (already
#    model-correct: 1M for Opus 4.8 / Sonnet 4.6, 200K otherwise). YAS divided by
#    a hardcoded 150K soft-limit, producing the nonsensical ">100%".
#  - Arbiter segments (stage / tasks / open-questions / overrides-since-checkpoint)
#    render ONLY in a repo whose .codearbiter/CONTEXT.md frontmatter is
#    `arbiter: enabled`. The usage line renders everywhere (YAS replacement).
#  - Excitement: brighter border + badge when effort is xhigh/max (ultracode) or
#    a /sprint is active (.codearbiter/sprint-active marker).
#
# Stdlib only. Python >= 3.8. Reads the statusline JSON on stdin, writes ANSI to
# stdout. Toggle off with CODEARBITER_STATUSLINE=off.

import json
import os
import re
import subprocess
import sys

# ----------------------------------------------------------------------------- colors
def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITAL = "\033[3m"

VIOLET = fg(178, 102, 255)       # primary neon violet
VIOLET_HOT = fg(208, 140, 255)   # excitement / ultracode / sprint
VIOLET_DIM = fg(120, 92, 168)    # borders, separators
WHITE = fg(232, 232, 240)
GREY = fg(150, 150, 162)
OK = fg(120, 220, 150)
WARN = fg(255, 184, 76)
DANGER = fg(255, 86, 110)

# ----------------------------------------------------------------------------- glyphs (native-safe BMP only)
TL, TR, BL, BR = "╭", "╮", "╰", "╯"  # rounded corners
H, V = "─", "│"
LT, RT = "├", "┤"                              # tee left/right (separators)
DOT = "●"                                           # filled circle (init)
BAR_FULL, BAR_EMPTY = "█", "░"                 # block / light-shade
SEP = f" {VIOLET_DIM}·{RESET} "                     # middle dot separator

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def vlen(s):
    """Visible length: strip ANSI; all glyphs used are width-1."""
    return len(ANSI_RE.sub("", s))


# ----------------------------------------------------------------------------- helpers
def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


def short_path(p):
    if not p:
        return "?"
    p = p.replace("\\", "/").rstrip("/")
    home = os.path.expanduser("~").replace("\\", "/").rstrip("/")
    if p == home:
        return "~"
    if home and p.startswith(home + "/"):
        p = "~" + p[len(home):]
    parts = [x for x in p.split("/") if x]
    if not parts:
        return "/"
    drive = parts[0].endswith(":") or parts[0] == "~"
    prefix = "" if drive else "/"
    if len(parts) <= 3:
        return prefix + "/".join(parts)
    # abbreviate middle parents to first letter; keep root + last two whole
    joined = "/".join([parts[0]] + [s[0] for s in parts[1:-2]] + parts[-2:])
    return prefix + joined


def read_head_branch(root):
    """Branch from .git/HEAD without invoking git."""
    head = os.path.join(root, ".git", "HEAD")
    try:
        with open(head, "r", encoding="utf-8", errors="replace") as f:
            ref = f.read().strip()
        if ref.startswith("ref:"):
            return ref.split("/")[-1]
        return ref[:7]  # detached: short sha
    except OSError:
        return None


def git_dirty(root):
    """Best-effort dirty flag; silent if git missing."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            capture_output=True, text=True, timeout=1.5,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def project_root(data):
    """Resolve repo root: project_dir -> git toplevel of cwd -> cwd."""
    pd = get(data, "workspace", "project_dir") or get(data, "cwd") or os.getcwd()
    # walk up for a .git or .codearbiter marker
    cur = os.path.abspath(pd)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isdir(os.path.join(cur, ".codearbiter")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(pd)
        cur = parent


# ----------------------------------------------------------------------------- arbiter state
def frontmatter(path):
    """Parse leading YAML-ish frontmatter into a dict (first --- ... --- block)."""
    fm = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
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
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return len(re.findall(pattern, f.read(), re.MULTILINE))
    except OSError:
        return 0


def arbiter_state(root):
    """Return dict of arbiter segments, or None if not arbiter-enabled."""
    cad = os.path.join(root, ".codearbiter")
    ctx = os.path.join(cad, "CONTEXT.md")
    fm = frontmatter(ctx)
    if fm.get("arbiter", "").lower() != "enabled":
        return None
    stage = fm.get("stage", "-")
    tasks = count_matches(os.path.join(cad, "open-tasks.md"), r"^- ")
    qs = count_matches(os.path.join(cad, "open-questions.md"), r"CONFIRM-[0-9]+")
    # overrides since last checkpoint: current non-comment lines minus the count
    # stored at last checkpoint.
    total_over = count_matches(os.path.join(cad, "overrides.log"), r"^(?!\s*#)(?!\s*$).+")
    base = 0
    try:
        with open(os.path.join(cad, "last-checkpoint"), "r", encoding="utf-8") as f:
            base = int((f.read().strip() or "0"))
    except (OSError, ValueError):
        base = 0
    over = max(0, total_over - base)
    sprint = os.path.exists(os.path.join(cad, "sprint-active"))
    return {"stage": stage, "tasks": tasks, "q": qs, "over": over, "sprint": sprint}


# ----------------------------------------------------------------------------- segments
def context_segment(data):
    cw = get(data, "context_window", default={}) or {}
    pct = cw.get("used_percentage")
    if pct is None:
        return f"{GREY}ctx --{RESET}"
    size = cw.get("context_window_size") or 200000
    tin = cw.get("total_input_tokens") or 0
    tout = cw.get("total_output_tokens") or 0
    toks = tin + tout
    pctf = float(pct)
    # color by compaction proximity (replaces YAS's bogus soft-limit %)
    col = VIOLET if pctf < 75 else (WARN if pctf < 90 else DANGER)
    width = 10
    filled = max(0, min(width, round(pctf / 100 * width)))
    bar = col + BAR_FULL * filled + VIOLET_DIM + BAR_EMPTY * (width - filled) + RESET
    win = "1M" if size >= 1_000_000 else f"{size // 1000}K"
    return f"{GREY}ctx{RESET} {bar} {col}{pctf:.0f}%{RESET} {DIM}{fmt_tok(toks)}/{win}{RESET}"


def fmt_tok(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(int(n))


def usd(c):
    if c is None:
        c = 0.0
    if c >= 100:
        return f"${c:.0f}"
    return f"${c:.2f}"


def fmt_dur(ms):
    if not ms:
        return None
    s = int(ms / 1000)
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def rate_color(p):
    p = float(p)
    return VIOLET if p < 75 else (WARN if p < 90 else DANGER)


# ----------------------------------------------------------------------------- render
def main():
    if os.environ.get("CODEARBITER_STATUSLINE", "").lower() == "off":
        return
    # Force UTF-8 I/O regardless of platform default (Windows defaults to cp1252,
    # which cannot encode the box-drawing / block glyphs).
    for stream in (sys.stdout, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        data = {}

    root = project_root(data)
    arb = arbiter_state(root)

    effort = (get(data, "effort", "level") or "").lower()
    sprint_active = bool(arb and arb.get("sprint"))
    excited = effort in ("xhigh", "max") or sprint_active
    border = VIOLET_HOT if excited else VIOLET_DIM

    lines = []  # content lines (without borders)

    # --- line 1: active folder ---
    folder = short_path(get(data, "workspace", "current_dir") or get(data, "cwd"))
    badge = ""
    if sprint_active:
        badge = f"  {VIOLET_HOT}{BOLD}[SPRINT]{RESET}"
    elif effort in ("xhigh", "max"):
        badge = f"  {VIOLET_HOT}[ultra]{RESET}"
    lines.append(f"{VIOLET}{BOLD}{folder}{RESET}{badge}")

    # --- line 2: git project (owner/name + branch + dirty) or no-git ---
    owner = get(data, "workspace", "repo", "owner")
    name = get(data, "workspace", "repo", "name")
    branch = read_head_branch(root)
    if name:
        proj = f"{owner + '/' if owner else ''}{name}"
        seg = f"{GREY}git{RESET} {WHITE}{proj}{RESET}"
        if branch:
            dirty = "*" if git_dirty(root) else ""
            bcol = WARN if dirty else OK
            seg += f" {VIOLET_DIM}{V}{RESET} {bcol}{branch}{dirty}{RESET}"
        lines.append(seg)
    elif branch:
        dirty = "*" if git_dirty(root) else ""
        bcol = WARN if dirty else OK
        base = os.path.basename(root)
        lines.append(f"{GREY}git{RESET} {WHITE}{base}{RESET} {VIOLET_DIM}{V}{RESET} {bcol}{branch}{dirty}{RESET}")
    else:
        lines.append(f"{GREY}no git{RESET}")

    # --- arbiter line (only when arbiter: enabled) ---
    if arb:
        qcol = DANGER if arb["q"] > 0 else GREY
        ocol = DANGER if arb["over"] > 0 else GREY
        tcol = WARN if arb["tasks"] > 0 else GREY
        seg = (
            f"{OK}{DOT}{RESET} {WHITE}stage:{arb['stage']}{RESET}"
            f"{SEP}{tcol}tasks:{arb['tasks']}{RESET}"
            f"{SEP}{qcol}q:{arb['q']}{RESET}"
            f"{SEP}{ocol}over:{arb['over']}{RESET}"
        )
        lines.append(seg)

    # --- usage line: model | context | cost | rate-limits or elapsed ---
    model = get(data, "model", "display_name") or get(data, "model", "id") or "?"
    parts = [f"{VIOLET}{model}{RESET}", context_segment(data), f"{OK}{usd(get(data, 'cost', 'total_cost_usd'))}{RESET}"]
    fh = get(data, "rate_limits", "five_hour", "used_percentage")
    sd = get(data, "rate_limits", "seven_day", "used_percentage")
    if fh is not None or sd is not None:
        rl = []
        if fh is not None:
            rl.append(f"{rate_color(fh)}5h:{float(fh):.0f}%{RESET}")
        if sd is not None:
            rl.append(f"{rate_color(sd)}7d:{float(sd):.0f}%{RESET}")
        parts.append(" ".join(rl))
    else:
        dur = fmt_dur(get(data, "cost", "total_duration_ms"))
        if dur:
            parts.append(f"{DIM}{dur}{RESET}")
    lines.append(SEP.join(parts))

    # --- draw the box, sized to content ---
    inner = max(vlen(ln) for ln in lines)
    out = []
    out.append(f"{border}{TL}{H}{H}{RESET} " + lines[0] + " " + f"{border}" + H * (inner - vlen(lines[0]) - 1) + TR + RESET)
    for ln in lines[1:]:
        pad = " " * (inner - vlen(ln))
        out.append(f"{border}{V}{RESET} {ln}{pad} {border}{V}{RESET}")
    out.append(f"{border}{BL}{H * (inner + 2)}{BR}{RESET}")
    text = "\n".join(out) + "\n"
    # Safety net: guarantee valid UTF-8 even if some field carried an undecodable
    # byte (surrogate). Replaces stray chars rather than crashing the statusline.
    text = text.encode("utf-8", "replace").decode("utf-8")
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
