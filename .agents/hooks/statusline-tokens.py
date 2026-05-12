#!/usr/bin/env python3
# codeArbiter statusline usage segment: ctx %, optional $ cost (API mode),
# optional 5h / 7d rate limits (subscription mode).
# Invoked from statusline.sh; stdin = Claude Code statusline JSON.
# Docs: .agents/hooks/STATUSLINE.md

import json
import os
import sys


def color_for_pct(pct):
    if pct is None:
        return "\033[2m"
    if pct < 50:
        return "\033[2m"
    if pct < 75:
        return "\033[33m"
    if pct < 90:
        return "\033[1;33m"
    return "\033[1;31m"


RESET = "\033[0m"
DIM = "\033[2m"


def fmt_pct(pct):
    if pct is None:
        return None
    return f"{int(pct)}"


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    cw = data.get("context_window") or {}
    pct = cw.get("used_percentage")
    if pct is None and isinstance(cw.get("current_usage"), dict):
        cu = cw["current_usage"]
        size = cw.get("context_window_size") or 200000
        used = (cu.get("input_tokens") or 0) + (cu.get("cache_creation_input_tokens") or 0) + (cu.get("cache_read_input_tokens") or 0)
        if size > 0 and used > 0:
            pct = (used / size) * 100

    parts = []
    if pct is not None:
        parts.append(f"{color_for_pct(pct)}ctx:{fmt_pct(pct)}%{RESET}")

    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        cost = (data.get("cost") or {}).get("total_cost_usd")
        if isinstance(cost, (int, float)) and cost > 0:
            parts.append(f"{DIM}${cost:.2f}{RESET}")
    else:
        rl = data.get("rate_limits") or {}
        for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
            window = rl.get(key) or {}
            wpct = window.get("used_percentage")
            if isinstance(wpct, (int, float)):
                parts.append(f"{color_for_pct(wpct)}{label}:{int(wpct)}%{RESET}")

    if parts:
        sys.stdout.write(" ".join(parts))


if __name__ == "__main__":
    main()
