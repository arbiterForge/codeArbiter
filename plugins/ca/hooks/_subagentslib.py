#!/usr/bin/env python3
# codeArbiter — statusline subagent-rows helpers (extracted from statusline.py,
# architecture-004).
#
# Owns resolving the current session's subagents directory, reading its recent
# `.jsonl` transcripts (deduped per requestId, same rule as the Session/Today
# rows), and labeling each subagent from its first user message. Carries no
# rendering concern — the statusline turns the returned dicts into rows.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed input — every reader degrades to a safe blank.
#
# Public API:
#   subagent_dir(data, root, sid) -> str|None
#   read_subagents(sdir) -> (active, recent, shown, (tot_in, tot_out))
#   sub_label(content) -> str
#   display_model(model_id) -> str

import json
import os
import re
import time

ACTIVE_WINDOW = 150       # secs: a subagent file touched this recently is "active"
SHOW_WINDOW = 600         # secs: still display recently-finished subagents
MAX_SUB_ROWS = 4
MAX_SUB_FILES = 12        # hot-path bound: parse at most this many files / render
MAX_SUB_LINES = 2500      # per-file line cap


def display_model(model_id):
    """Compact a host model ID while retaining its family and version."""
    if not isinstance(model_id, str):
        return "model:?"
    name = model_id.strip()
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
        models = []
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
                    if msg.get("role") == "assistant":
                        raw_model = msg.get("model")
                        if isinstance(raw_model, str) and raw_model.strip():
                            raw_model = raw_model.strip()
                            if raw_model not in models:
                                models.append(raw_model)
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
