#!/usr/bin/env python3
# codeArbiter — statusline subagent-rows helpers (extracted from statusline.py,
# architecture-004).
#
# Owns resolving the current session's subagents directory and turning the
# accounting scanner's per-child presentation summaries (from the ledger record)
# into rows, plus labeling a subagent from its first user message (sub_label is
# called BY that scanner). It never parses a child transcript itself: the render
# path has one JSONL parser (_ledgerlib). No rendering concern — the statusline
# turns the returned dicts into rows.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed input — every reader degrades to a safe blank.
#
# Public API:
#   subagent_dir(data, root, sid) -> str|None
#   read_subagents(sdir, rec=None) -> (active, recent, shown, (tot_in, tot_out))
#   sub_label(content) -> str
#   display_model(model_id) -> str

import os
import re
import time

try:
    import _colorlib
    strip_control = _colorlib.strip_control
except Exception:  # pragma: no cover — never let an import break the statusline
    _colorlib = None

    def strip_control(s):
        return s if not isinstance(s, str) else re.sub(r"[\000-\037]", "", s)

ACTIVE_WINDOW = 150       # secs: a subagent file touched this recently is "active"
SHOW_WINDOW = 600         # secs: still display recently-finished subagents
MAX_SUB_ROWS = 4
MAX_SUB_FILES = 12        # rows considered per render (presentation bound, not accounting)


def display_model(model_id):
    """Compact a host model ID while retaining its family and version."""
    if not isinstance(model_id, str):
        return "model:?"
    name = strip_control(model_id).strip()
    if not name:
        return "model:?"
    if name.startswith("claude-"):
        name = name[len("claude-"):]
    name = re.sub(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$", "", name)
    return "model:" + name[:24]


def num(x, default=0.0):
    """Coerce any host value to float; tolerate strings, None, and containers."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


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


def read_subagents(sdir, rec=None):
    """Return (active, recent, shown[{label,model,inp,out,age,active}], (tot_in, tot_out)).
    `active` = files touched within ACTIVE_WINDOW (a liveness proxy); `recent` =
    all files within SHOW_WINDOW (active + recently finished).

    Rows come from the accounting scanner's per-source PRESENTATION SUMMARIES in
    the ledger record `rec` (spec D-7): label, observed models and owner-attributed
    tokens, with fork-replayed parent requests excluded. This reader only lists
    the directory and stats files for liveness. It never opens or parses a child
    transcript, so the render path has exactly one JSONL parser. A child the
    scanner has not reached yet shows its fallback name and zero tokens until it
    has.

    ONE result shape on EVERY path (#413). The element types are stable — int,
    int, list, (int|float, int|float) — so a caller may unpack four names
    unconditionally. statusline.py does exactly that, OUTSIDE its safe()
    wrapper, so an error branch returning a shorter tuple would be a hard
    ValueError. An unreadable/absent directory is an EMPTY result."""
    empty = (0, 0, [], (0, 0))
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
        return empty
    files.sort(reverse=True)   # most-recently-touched first

    sources = rec.get("src") if isinstance(rec, dict) else None
    sources = sources if isinstance(sources, dict) else {}
    active = sum(1 for mtime, _, _, _ in files if now - mtime <= ACTIVE_WINDOW)
    shown, tot_in, tot_out = [], 0, 0
    for mtime, size, _fp, nm in files[:MAX_SUB_FILES]:
        if size > 16 * 1024 * 1024:
            continue
        summary = sources.get("c:" + nm)
        summary = summary if isinstance(summary, dict) else {}
        tok = summary.get("tok")
        inp, out = ((num(tok[0]), num(tok[1])) if isinstance(tok, list) and len(tok) == 2
                    else (0, 0))
        models = [m for m in (summary.get("models") or []) if isinstance(m, str)]
        label = summary.get("label") if isinstance(summary.get("label"), str) else None
        tot_in += inp
        tot_out += out
        if len(shown) < MAX_SUB_ROWS:
            shown.append({"label": label or ("agent-" + re.sub(r"\.jsonl$", "", nm)[-6:]),
                          "model": (display_model(models[0]) if len(models) == 1 else
                                    ("model:mixed" if models else "model:?")),
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
    raw = strip_control(str(text))
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
