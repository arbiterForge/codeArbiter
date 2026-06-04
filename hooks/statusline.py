#!/usr/bin/env python3
# codeArbiter statusline — dependency-free (Python stdlib only, no Nerd Font).
#
# Renders a sectioned, full-width box. The usage segments (folder, git, model,
# rate limits, context, tokens, cost) render in every repo. The arbiter segments
# (stage / tasks / open-questions / overrides-since-checkpoint) render only when
# the repo's .codearbiter/CONTEXT.md frontmatter is `arbiter: enabled`.
#
# Design:
#   - single neon-violet palette (a subtle dark->bright sheen, no rainbow)
#   - native-font glyphs only: box-drawing, block elements, arrows, ASCII labels
#   - top line = active folder; second line = git project (owner/name + branch),
#     with a no-git fallback
#   - cost trusts Claude Code's cost.total_cost_usd (each call priced at the
#     model used when burned; subagents included) — no token*price recompute
#   - context trusts context_window.used_percentage + context_window_size
#     (1M for Opus 4.8 / Sonnet 4.6, 200K otherwise) — never exceeds 100%
#   - excitement: [ultra] on xhigh/max effort, [SPRINT] on an active sprint
#
# Implemented: box + folder/git + rate-limits + model + context + token in/out
# + cost + arbiter line. Planned: burn-rate sparkline, day-cost row, burndown
# trend, subagent rows, task rows, skills/plugins line, model pill, reset
# countdown.
#
# Toggle off with CODEARBITER_STATUSLINE=off. Width via CODEARBITER_WIDTH/COLUMNS.

import json
import os
import re
import subprocess
import sys

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
TD, TU = "┬", "┴"            # tee down / up (column joins)
DOTH = "┄"                       # dotted horizontal (section separators)
DOT = "●"
BFULL, BEMPTY = "█", "░"
DN, UP = "↓", "↑"

ANSI = re.compile(r"\033\[[0-9;]*m")


def vlen(s):
    return len(ANSI.sub("", s))


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


# --------------------------------------------------------------------------- helpers
def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


def fmt_tok(n):
    n = float(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(int(n))


def usd(c):
    c = float(c or 0)
    return f"${c:.0f}" if c >= 100 else f"${c:.2f}"


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
    return prefix + "/".join([parts[0]] + [s[0] for s in parts[1:-2]] + parts[-2:])


def trunc(plain, w):
    return plain if len(plain) <= w else (plain[: max(0, w - 1)] + "…")


def pad(s, w):
    v = vlen(s)
    return s + " " * (w - v) if v < w else s


def project_root(data):
    pd = get(data, "workspace", "project_dir") or get(data, "cwd") or os.getcwd()
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
        return ref.split("/")[-1] if ref.startswith("ref:") else ref[:7]
    except OSError:
        return None


def git_dirty(root):
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=1.5)
        return bool(out.stdout.strip())
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


# --------------------------------------------------------------------------- box
class Box:
    def __init__(self, width):
        self.W = width
        self.inner = width - 4   # "│ " + content + " │"
        self.lines = []

    def top(self, title, badge=""):
        # ╭── title ...badge... ──╮
        left = f"{V0}{TL}{H}{H}{RESET} "
        t = gradient_h(title, len(title))
        b = f" {badge} " if badge else " "
        used = 3 + vlen(title) + vlen(b)
        fillw = max(0, self.W - 1 - used - 1)
        fill = gradient_h(H * fillw, fillw, (90, 60, 150), (170, 110, 240))
        self.lines.append(f"{left}{t}{b}{V1}{badge_pad(badge)}{fill}{V0}{TR}{RESET}")

    def row(self, content):
        self.lines.append(f"{V0}{V}{RESET} {pad(content, self.inner)} {V0}{V}{RESET}")

    def sep(self, tees=None, dotted=True):
        ch = DOTH if dotted else H
        mid = [ch] * (self.inner + 2)
        for k in (tees or []):
            pos = k + 1  # content index k -> separator middle index k+1
            if 0 <= pos < len(mid):
                mid[pos] = TD
        self.lines.append(f"{V0}{LT}{''.join(mid)}{RT}{RESET}")

    def bottom(self, tees=None):
        mid = [H] * (self.inner + 2)
        for k in (tees or []):
            pos = k + 1
            if 0 <= pos < len(mid):
                mid[pos] = TU
        self.lines.append(f"{V0}{BL}{''.join(mid)}{RESET}{V0}{BR}{RESET}")

    def render(self):
        text = "\n".join(self.lines) + "\n"
        return text.encode("utf-8", "replace").decode("utf-8")


def badge_pad(badge):
    return ""  # placeholder hook for future right-aligned badge padding


def columns(cells):
    """cells: list of (text, width). Returns (content_str, [boundary content-indices])."""
    parts, bounds, pos = [], [], 0
    for i, (text, w) in enumerate(cells):
        parts.append(pad(trunc_ansi(text, w), w))
        pos += w
        if i < len(cells) - 1:
            parts.append(f" {V0}{V}{RESET} ")
            bounds.append(pos + 1)  # index of the │ within " │ "
            pos += 3
    return "".join(parts), bounds


def trunc_ansi(s, w):
    if vlen(s) <= w:
        return s
    # crude: strip ANSI, truncate, recolor not preserved — used for plain cells
    plain = ANSI.sub("", s)
    return trunc(plain, w)


# --------------------------------------------------------------------------- segments
def seg_context(data):
    cw = get(data, "context_window", default={}) or {}
    pct = cw.get("used_percentage")
    size = cw.get("context_window_size") or 200000
    win = "1M" if size >= 1_000_000 else f"{size // 1000}K"
    toks = (cw.get("total_input_tokens") or 0) + (cw.get("total_output_tokens") or 0)
    if pct is None:
        return f"{GREY}ctx --{RESET}"
    pctf = float(pct)
    col = V2 if pctf < 75 else (WARN if pctf < 90 else DANGER)
    barw = 24
    filled = max(0, min(barw, round(pctf / 100 * barw)))
    bar = gradient_h(BFULL * filled, filled) + f"{V0}" + BEMPTY * (barw - filled) + RESET
    return f"{GREY}ctx{RESET} {bar} {col}{pctf:.0f}%{RESET} {DIM}{fmt_tok(toks)}/{win}{RESET}"


def seg_rates(data):
    fh = get(data, "rate_limits", "five_hour", "used_percentage")
    sd = get(data, "rate_limits", "seven_day", "used_percentage")
    out = []
    if fh is not None:
        c = V2 if float(fh) < 75 else (WARN if float(fh) < 90 else DANGER)
        out.append(f"{GREY}5h{RESET} {c}{float(fh):.0f}%{RESET}")
    if sd is not None:
        c = V2 if float(sd) < 75 else (WARN if float(sd) < 90 else DANGER)
        out.append(f"{GREY}7d{RESET} {c}{float(sd):.0f}%{RESET}")
    return "  ".join(out)


def main():
    if os.environ.get("CODEARBITER_STATUSLINE", "").lower() == "off":
        return
    for s in (sys.stdout, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        data = {}

    try:
        W = int(os.environ.get("CODEARBITER_WIDTH") or os.environ.get("COLUMNS") or 100)
    except ValueError:
        W = 100
    W = max(70, min(140, W))

    root = project_root(data)
    arb = arbiter_state(root)
    effort = (get(data, "effort", "level") or "").lower()
    sprint = bool(arb and arb.get("sprint"))
    badge = f"{V3}{BOLD}[SPRINT]{RESET}" if sprint else (f"{V3}[ultra]{RESET}" if effort in ("xhigh", "max") else "")

    box = Box(W)

    folder = short_path(get(data, "workspace", "current_dir") or get(data, "cwd"))
    box.top(folder, badge)

    # row: git project (left) ... rate-limits + model (right)
    owner, name = get(data, "workspace", "repo", "owner"), get(data, "workspace", "repo", "name")
    branch = head_branch(root)
    if name:
        gp = f"{GREY}git{RESET} {WHITE}{(owner + '/' if owner else '') + name}{RESET}"
    elif branch:
        gp = f"{GREY}git{RESET} {WHITE}{os.path.basename(root)}{RESET}"
    else:
        gp = f"{GREY}no git{RESET}"
    if branch:
        dirty = "*" if git_dirty(root) else ""
        gp += f" {V0}{V}{RESET} {(WARN if dirty else OK)}{branch}{dirty}{RESET}"
    model = get(data, "model", "display_name") or get(data, "model", "id") or "?"
    right = seg_rates(data)
    right = (right + "   " if right else "") + f"{V2}{model}{RESET}"
    gapw = max(1, box.inner - vlen(gp) - vlen(right))
    box.row(gp + " " * gapw + right)

    box.sep()

    if arb:
        qcol = DANGER if arb["q"] > 0 else GREY
        ocol = DANGER if arb["over"] > 0 else GREY
        tcol = WARN if arb["tasks"] > 0 else GREY
        s = SEPd = f" {V0}·{RESET} "
        box.row(
            f"{OK}{DOT}{RESET} {WHITE}stage:{arb['stage']}{RESET}{s}{tcol}tasks:{arb['tasks']}{RESET}"
            f"{s}{qcol}q:{arb['q']}{RESET}{s}{ocol}over:{arb['over']}{RESET}"
        )
        box.sep()

    box.row(seg_context(data))

    # token / cost columns
    cw = get(data, "context_window", "current_usage", default={}) or {}
    tin = cw.get("input_tokens") or get(data, "context_window", "total_input_tokens") or 0
    tout = cw.get("output_tokens") or get(data, "context_window", "total_output_tokens") or 0
    cache = cw.get("cache_read_input_tokens") or 0
    cost = usd(get(data, "cost", "total_cost_usd"))
    tok_cell = f"{V2}{DN}{RESET} {WHITE}{fmt_tok(tin)}{RESET} {DIM}({fmt_tok(cache)}){RESET} {V2}{UP}{RESET} {WHITE}{fmt_tok(tout)}{RESET}"
    cost_cell = f"{OK}{cost}{RESET}"
    # rough session token-rate (avg over wall-clock minutes); burn sparkline TBD
    dur_ms = get(data, "cost", "total_duration_ms") or 0
    mins = max(1, dur_ms / 60000) if dur_ms else 0
    rate = f"{GREY}{int((tin + tout) / mins) if mins else 0} t/m{RESET}" if mins else f"{GREY}-- t/m{RESET}"
    cost_w = 10
    rest = box.inner - cost_w - 6  # two " │ " separators
    c1 = rest * 2 // 3
    c3 = rest - c1
    content, bounds = columns([(tok_cell, c1), (cost_cell, cost_w), (rate, c3)])
    box.sep(tees=bounds)
    box.row(content)
    box.bottom(tees=bounds)

    sys.stdout.write(box.render())


if __name__ == "__main__":
    main()
