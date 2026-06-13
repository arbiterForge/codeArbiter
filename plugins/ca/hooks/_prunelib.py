#!/usr/bin/env python3
# codeArbiter — session-transcript pruner core (the safe, testable engine).
#
# Claude Code session transcripts (~/.claude/projects/<slug>/<session>.jsonl)
# accumulate clutter — bulky `toolUseResult` sidecars, oversized tool_result
# bodies, thinking blocks, MCP/shell noise — that shortens how long a session
# stays usable before compaction. This module trims that clutter while treating
# transcript integrity as sacred.
#
# Two structural guarantees make corruption hard:
#   1. We never edit bytes. A line is parsed, its object mutated, and ONLY THEN
#      re-serialized. Lines we don't touch are emitted as their original raw
#      bytes — so unknown line types, exotic key order, and odd escapes survive
#      byte-identical. Re-serialization drift can only affect lines we chose to
#      edit.
#   2. Phases 1-4 are stub-in-place only: every line survives and the
#      uuid/parentUuid chain is never altered. Whole-line deletion (with
#      re-linking) is a separate, gated capability and is NOT in this module yet.
#
# Stdlib only (hooks must run on a stock interpreter — see _hooklib.py).

import hashlib
import json
import os
import re
import shutil
import time

BOM = b"\xef\xbb\xbf"
MARKER_PREFIX = "[ca-condensed "


def _dumps(o):
    """Compact, UTF-8-preserving serialization used for every line we rewrite."""
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def _marker(orig_text):
    """Self-describing elision marker. The 8-hex sha doubles as the idempotency
    guard: a strategy skips any content already carrying a marker, so
    prune(prune(x)) == prune(x)."""
    b = orig_text.encode("utf-8")
    return f"{MARKER_PREFIX}{len(b)}B #{hashlib.sha256(b).hexdigest()[:8]}]"


def _has_marker(s):
    return isinstance(s, str) and MARKER_PREFIX in s


def est_tokens(nbytes):
    """Dependency-free token estimate. Deliberately labeled `est≈` everywhere it
    surfaces — mirrors statusline's honest `api≈` convention."""
    return nbytes // 4


# --------------------------------------------------------------------------- #
# Line model + load/serialize (the byte-identity backbone)
# --------------------------------------------------------------------------- #

class Line:
    __slots__ = ("idx", "raw", "obj", "dirty", "bom", "fp0")

    def __init__(self, idx, raw):
        self.idx = idx
        self.bom = raw.startswith(BOM)
        body = raw[len(BOM):] if self.bom else raw
        self.raw = raw
        self.dirty = False
        try:
            self.obj = json.loads(body) if body.strip() else None
        except Exception:  # noqa: BLE001 — a malformed line is preserved verbatim
            self.obj = None
        # Original structural fingerprint, captured BEFORE any strategy mutates
        # obj, so validators compare against the true original.
        if isinstance(self.obj, dict):
            self.fp0 = (self.obj.get("type"), self.obj.get("uuid"),
                        self.obj.get("parentUuid"))
        else:
            self.fp0 = None

    def out_bytes(self):
        if not self.dirty:
            return self.raw
        body = _dumps(self.obj).encode("utf-8")
        return (BOM + body) if self.bom else body


def load_lines(data):
    """Split on b'\\n' keeping every part — including a trailing empty part for a
    newline-terminated file and any blank interior lines — so b'\\n'.join of the
    untouched parts reproduces the input exactly."""
    return [Line(i, raw) for i, raw in enumerate(data.split(b"\n"))]


def serialize(lines):
    return b"\n".join(ln.out_bytes() for ln in lines)


# --------------------------------------------------------------------------- #
# Index + protected tail
# --------------------------------------------------------------------------- #

def _tool_use_ids(o):
    ids = set()
    msg = o.get("message") if isinstance(o, dict) else None
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        for b in msg["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                ids.add(b["id"])
    return ids


def _tool_result_ids(o):
    ids = set()
    msg = o.get("message") if isinstance(o, dict) else None
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        for b in msg["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id"):
                ids.add(b["tool_use_id"])
    return ids


class Index:
    __slots__ = ("protected_from", "last_assistant_idx", "tu_ids", "tr_ids",
                 "edited_paths", "edited_at", "tool_meta")


def build_index(lines, cfg):
    """Compute the protected tail and pre-strategy tool-id sets. The protected
    tail is everything at/after the earlier of (a) the start of the K-th most
    recent tool-bearing TURN and (b) the last assistant message (whose thinking
    signature must never be touched).

    keep_recent counts TURNS, not lines: a turn is anchored by its assistant
    tool_use line, and protecting that line's index also protects the
    tool_result lines that follow it. (Counting result lines too would silently
    halve the protection an operator asked for via KEEP_RECENT.)"""
    idx = Index()
    turn_anchor_idxs = []     # assistant tool_use-bearing lines: one per turn
    result_line_idxs = []     # fallback anchors for a results-only transcript
    last_assistant = -1
    tu, tr = set(), set()
    edited = set()
    edited_at = {}        # file_path -> highest line idx that Wrote/Edited it
    tool_meta = {}        # tool_use id -> {"name", "path", "idx"}
    for ln in lines:
        o = ln.obj
        if not isinstance(o, dict):
            continue
        if o.get("type") == "assistant":
            last_assistant = ln.idx
        a, b = _tool_use_ids(o), _tool_result_ids(o)
        if a:
            turn_anchor_idxs.append(ln.idx)
        elif b:
            result_line_idxs.append(ln.idx)
        tu |= a
        tr |= b
        msg = o.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            for blk in msg["content"]:
                if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                    continue
                name = blk.get("name")
                path = (blk.get("input") or {}).get("file_path")
                if blk.get("id"):
                    tool_meta[blk["id"]] = {"name": name, "path": path, "idx": ln.idx}
                # Track files a later Write/Edit superseded (Phase-3 strategy).
                if name in ("Write", "Edit") and path:
                    edited.add(path)
                    edited_at[path] = max(edited_at.get(path, -1), ln.idx)
    anchors = turn_anchor_idxs or result_line_idxs
    keep = cfg.keep_recent
    if keep <= 0:
        prot_tool = len(lines)
    elif len(anchors) > keep:
        prot_tool = anchors[-keep]
    elif anchors:
        prot_tool = anchors[0]
    else:
        prot_tool = len(lines)
    prot = prot_tool
    if last_assistant >= 0:
        prot = min(prot, last_assistant)
    idx.protected_from = prot
    idx.last_assistant_idx = last_assistant
    idx.tu_ids = tu
    idx.tr_ids = tr
    idx.edited_paths = edited
    idx.edited_at = edited_at
    idx.tool_meta = tool_meta
    return idx


def _is_small_scalar(v, limit=200):
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        return len(v) <= limit
    return False


# --------------------------------------------------------------------------- #
# Strategies (Phase 1). Each mutates obj, sets dirty, records a report row.
# All obey the net-negative guard: a strategy is a no-op on any unit whose
# replacement would not be strictly smaller than the original.
# --------------------------------------------------------------------------- #

def _record(report, name, touched, before, after):
    report[name] = {"lines": touched, "bytes_before": before, "bytes_after": after}


def s_sidecar_collapse(lines, index, cfg, report):
    """Replace the bulky top-level `toolUseResult` sidecar with a marker plus the
    small scalar fields worth keeping (status, exit codes, agentId, paths)."""
    touched = before = after = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        tur = ln.obj.get("toolUseResult")
        if not isinstance(tur, (dict, list, str)):
            continue
        orig = _dumps(tur)
        if _has_marker(orig):
            continue
        kept = {}
        if isinstance(tur, dict):
            kept = {k: v for k, v in tur.items() if _is_small_scalar(v)}
        new = dict(kept)
        new["_ca_condensed"] = _marker(orig)
        new_s = _dumps(new)
        if len(new_s) >= len(orig):  # net-negative guard
            continue
        ln.obj["toolUseResult"] = new
        ln.dirty = True
        touched += 1
        before += len(orig)
        after += len(new_s)
    _record(report, "sidecar-collapse", touched, before, after)


def _clamp_text(s, max_bytes, max_lines):
    """Return (clamped_or_None). None means leave as-is (under threshold)."""
    b = s.encode("utf-8")
    if len(b) <= max_bytes and s.count("\n") < max_lines:
        return None
    head = b[:max_bytes].decode("utf-8", "ignore")
    clamped = head + "\n" + _marker(s)
    if len(clamped.encode("utf-8")) >= len(b):  # net-negative guard
        return None
    return clamped


def s_oversize_result_clamp(lines, index, cfg, report):
    """Truncate tool_result bodies over MAXBYTES or >100 lines to a head + marker.
    Handles both the string form and the list-of-{type:text} form."""
    touched = before = after = 0
    mb, ml = cfg.max_bytes, 100
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        msg = ln.obj.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
            continue
        changed = False
        for blk in msg["content"]:
            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                continue
            c = blk.get("content")
            if isinstance(c, str):
                if _has_marker(c):
                    continue
                clamped = _clamp_text(c, mb, ml)
                if clamped is not None:
                    before += len(c.encode("utf-8"))
                    after += len(clamped.encode("utf-8"))
                    blk["content"] = clamped
                    changed = True
            elif isinstance(c, list):
                for tb in c:
                    if not isinstance(tb, dict) or tb.get("type") != "text":
                        continue
                    txt = tb.get("text")
                    if not isinstance(txt, str) or _has_marker(txt):
                        continue
                    clamped = _clamp_text(txt, mb, ml)
                    if clamped is not None:
                        before += len(txt.encode("utf-8"))
                        after += len(clamped.encode("utf-8"))
                        tb["text"] = clamped
                        changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "oversize-result-clamp", touched, before, after)


def _content_list(o):
    msg = o.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        return msg["content"]
    return None


def _clamp_in_block_content(c, max_bytes, max_lines):
    """Clamp a tool_result `content` (str or list-of-{text}) in place. Returns
    (changed, bytes_before, bytes_after)."""
    before = after = 0
    changed = False
    if isinstance(c, str):
        if not _has_marker(c):
            clamped = _clamp_text(c, max_bytes, max_lines)
            if clamped is not None:
                before += len(c.encode("utf-8"))
                after += len(clamped.encode("utf-8"))
                return True, before, after, clamped
        return False, 0, 0, c
    if isinstance(c, list):
        for tb in c:
            if not isinstance(tb, dict) or tb.get("type") != "text":
                continue
            txt = tb.get("text")
            if not isinstance(txt, str) or _has_marker(txt):
                continue
            clamped = _clamp_text(txt, max_bytes, max_lines)
            if clamped is not None:
                before += len(txt.encode("utf-8"))
                after += len(clamped.encode("utf-8"))
                tb["text"] = clamped
                changed = True
    return changed, before, after, c


def s_reasoning_fold(lines, index, cfg, report):
    """Drop thinking blocks from older assistant turns. We REMOVE the block
    rather than leave an empty-signature stub: a thinking block with an invalid
    signature can be rejected on resume, whereas an absent one never is. The
    most recent assistant turn is always inside the protected tail."""
    touched = before = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        if ln.obj.get("type") != "assistant":
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        thinking = [b for b in content
                    if isinstance(b, dict) and b.get("type") == "thinking"]
        if not thinking:
            continue
        keep = [b for b in content if b not in thinking]
        if not keep:  # never empty a message
            continue
        for b in thinking:
            before += len(_dumps(b))
        ln.obj["message"]["content"] = keep
        ln.dirty = True
        touched += 1
    _record(report, "reasoning-fold", touched, before, 0)


def s_aged_result_condense(lines, index, cfg, report):
    """Condense any remaining (unmarked) older tool_result body to a small head
    + marker — harder than the gentle clamp, for results past the protected
    tail. Specific handlers (shell/superseded) run earlier and mark their own."""
    touched = before = after = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        changed = False
        for blk in content:
            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                continue
            ch, b, a, newc = _clamp_in_block_content(blk.get("content"), 200, 10 ** 9)
            if ch:
                blk["content"] = newc
                before += b
                after += a
                changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "aged-result-condense", touched, before, after)


def s_mcp_payload_condense(lines, index, cfg, report):
    """Condense the bulky `input` of mcp__ tool_use blocks (older turns)."""
    touched = before = after = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        changed = False
        for blk in content:
            if (not isinstance(blk, dict) or blk.get("type") != "tool_use"
                    or not str(blk.get("name", "")).startswith("mcp__")):
                continue
            inp = blk.get("input")
            if not isinstance(inp, (dict, list, str)):
                continue
            orig = _dumps(inp)
            if _has_marker(orig):
                continue
            kept = ({k: v for k, v in inp.items() if _is_small_scalar(v)}
                    if isinstance(inp, dict) else {})
            new = dict(kept)
            new["_ca_condensed"] = _marker(orig)
            if len(_dumps(new)) >= len(orig):
                continue
            blk["input"] = new
            before += len(orig)
            after += len(_dumps(new))
            changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "mcp-payload-condense", touched, before, after)


def s_shell_tail_keep(lines, index, cfg, report):
    """For Bash/PowerShell results, keep only the last N lines (the tail carries
    the exit verdict). Claims its targets before the generic condenser."""
    keep_lines = 30
    touched = before = after = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        changed = False
        for blk in content:
            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                continue
            meta = index.tool_meta.get(blk.get("tool_use_id"))
            if not meta or meta.get("name") not in ("Bash", "PowerShell", "Shell"):
                continue

            def tail(s):
                if _has_marker(s):
                    return None
                parts = s.split("\n")
                if len(parts) <= keep_lines:
                    return None
                new = _marker(s) + "\n" + "\n".join(parts[-keep_lines:])
                if len(new.encode("utf-8")) >= len(s.encode("utf-8")):
                    return None
                return new
            c = blk.get("content")
            if isinstance(c, str):
                nt = tail(c)
                if nt is not None:
                    before += len(c.encode("utf-8"))
                    after += len(nt.encode("utf-8"))
                    blk["content"] = nt
                    changed = True
            elif isinstance(c, list):
                for tb in c:
                    if isinstance(tb, dict) and tb.get("type") == "text" \
                            and isinstance(tb.get("text"), str):
                        nt = tail(tb["text"])
                        if nt is not None:
                            before += len(tb["text"].encode("utf-8"))
                            after += len(nt.encode("utf-8"))
                            tb["text"] = nt
                            changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "shell-tail-keep", touched, before, after)


def s_superseded_read_condense(lines, index, cfg, report):
    """Condense a Read result whose file was Written/Edited later in the
    transcript — that snapshot is stale; the later edit is the source of truth."""
    touched = before = after = 0
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        changed = False
        for blk in content:
            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                continue
            meta = index.tool_meta.get(blk.get("tool_use_id"))
            if not meta or meta.get("name") != "Read":
                continue
            path = meta.get("path")
            if not path or index.edited_at.get(path, -1) <= meta.get("idx", -1):
                continue
            ch, b, a, newc = _clamp_in_block_content(blk.get("content"), 80, 10 ** 9)
            if ch:
                blk["content"] = newc
                before += b
                after += a
                changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "superseded-read-condense", touched, before, after)


def s_repeat_reminder_fold(lines, index, cfg, report):
    """Dedup repeated identical <system-reminder> text blocks — keep the first,
    fold later copies to a marker."""
    seen = set()
    touched = before = after = 0
    for ln in lines:
        if not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        changed = False
        for blk in content:
            if not isinstance(blk, dict) or blk.get("type") != "text":
                continue
            txt = blk.get("text")
            if not isinstance(txt, str) or "<system-reminder>" not in txt or _has_marker(txt):
                continue
            key = hashlib.sha256(txt.encode("utf-8")).hexdigest()
            if key not in seen:
                seen.add(key)
                continue
            # A later duplicate: fold it (only past the protected tail).
            if ln.idx >= index.protected_from:
                continue
            marker = _marker(txt)
            if len(marker.encode("utf-8")) >= len(txt.encode("utf-8")):
                continue
            before += len(txt.encode("utf-8"))
            after += len(marker.encode("utf-8"))
            blk["text"] = marker
            changed = True
        if changed:
            ln.dirty = True
            touched += 1
    _record(report, "repeat-reminder-fold", touched, before, after)


def s_inline_image_evict(lines, index, cfg, report):
    """Replace base64 image payloads (older turns) with a marker."""
    touched = before = after = 0

    def walk(blocks):
        nonlocal before, after
        changed = False
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "image" and isinstance(blk.get("source"), dict):
                src = blk["source"]
                data = src.get("data")
                if isinstance(data, str) and not _has_marker(data) and len(data) > 64:
                    before += len(data)
                    src["data"] = _marker(data)
                    after += len(src["data"])
                    changed = True
            # tool_result content may itself be a list with image blocks
            if isinstance(blk.get("content"), list):
                if walk(blk["content"]):
                    changed = True
        return changed
    for ln in lines:
        if ln.idx >= index.protected_from or not isinstance(ln.obj, dict):
            continue
        content = _content_list(ln.obj)
        if not content:
            continue
        if walk(content):
            ln.dirty = True
            touched += 1
    _record(report, "inline-image-evict", touched, before, after)


# name -> (tier, function). The pinned order matters: specific result handlers
# (shell tail, superseded read) and payload condensers claim and mark their
# targets BEFORE the generic aged/oversize condensers run, so each result is
# trimmed by the most appropriate strategy exactly once (the marker enforces
# single-processing). Selection preserves this order.
TIERS = {"gentle": 0, "standard": 1, "aggressive": 2}
STRATEGIES = {
    "sidecar-collapse": ("gentle", s_sidecar_collapse),
    "reasoning-fold": ("standard", s_reasoning_fold),
    "mcp-payload-condense": ("standard", s_mcp_payload_condense),
    "shell-tail-keep": ("standard", s_shell_tail_keep),
    "superseded-read-condense": ("aggressive", s_superseded_read_condense),
    "repeat-reminder-fold": ("aggressive", s_repeat_reminder_fold),
    "inline-image-evict": ("aggressive", s_inline_image_evict),
    "aged-result-condense": ("standard", s_aged_result_condense),
    "oversize-result-clamp": ("gentle", s_oversize_result_clamp),
}
STRATEGY_ORDER = [
    "sidecar-collapse",
    "reasoning-fold",
    "mcp-payload-condense",
    "shell-tail-keep",
    "superseded-read-condense",
    "repeat-reminder-fold",
    "inline-image-evict",
    "aged-result-condense",
    "oversize-result-clamp",
]


def selected_strategies(cfg):
    if cfg.strategies:
        want = set(cfg.strategies)
        return [n for n in STRATEGY_ORDER if n in want and n in STRATEGIES]
    ceil = TIERS.get(cfg.tier, 0)
    return [n for n in STRATEGY_ORDER
            if n in STRATEGIES and TIERS[STRATEGIES[n][0]] <= ceil]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

class Config:
    def __init__(self, tier="gentle", strategies=None, max_bytes=8192,
                 keep_recent=10, min_size=1 << 20, min_growth=1 << 18,
                 backups=3, live_secs=90, execute=False):
        self.tier = tier
        self.strategies = strategies
        self.max_bytes = max_bytes
        self.keep_recent = keep_recent
        self.min_size = min_size
        self.min_growth = min_growth
        self.backups = backups
        self.live_secs = live_secs
        self.execute = execute

    @classmethod
    def from_env(cls, env=None, **over):
        e = env if env is not None else os.environ

        def num(key, default):
            try:
                return int(e[key])
            except Exception:  # noqa: BLE001
                return default
        cfg = cls(
            tier=e.get("CODEARBITER_PRUNE_TIER", "gentle"),
            strategies=([s.strip() for s in e["CODEARBITER_PRUNE_STRATEGIES"].split(",") if s.strip()]
                        if e.get("CODEARBITER_PRUNE_STRATEGIES") else None),
            max_bytes=num("CODEARBITER_PRUNE_MAXBYTES", 8192),
            keep_recent=num("CODEARBITER_PRUNE_KEEP_RECENT", 10),
            min_size=num("CODEARBITER_PRUNE_MIN_SIZE", 1 << 20),
            min_growth=num("CODEARBITER_PRUNE_MIN_GROWTH", 1 << 18),
            backups=num("CODEARBITER_PRUNE_BACKUPS", 3),
            live_secs=num("CODEARBITER_PRUNE_LIVE_SECS", 90),
        )
        for k, v in over.items():
            setattr(cfg, k, v)
        return cfg


# --------------------------------------------------------------------------- #
# Pipeline + validation
# --------------------------------------------------------------------------- #

def apply_strategies(lines, index, cfg):
    report = {}
    for name in selected_strategies(cfg):
        STRATEGIES[name][1](lines, index, cfg, report)
    return report


def _parts_objs(data):
    """Parse each line; returns list where each item is dict/None, or the tuple
    ('<<bad>>', err) for an unparseable non-blank line."""
    out = []
    for p in data.split(b"\n"):
        body = p[len(BOM):] if p.startswith(BOM) else p
        if not body.strip():
            out.append(None)
            continue
        try:
            out.append(json.loads(body))
        except Exception as e:  # noqa: BLE001
            out.append(("<<bad>>", str(e)))
    return out


def _orphans(objs):
    uuids = {o.get("uuid") for o in objs if isinstance(o, dict) and o.get("uuid")}
    bad = set()
    for o in objs:
        if isinstance(o, dict):
            p = o.get("parentUuid")
            if p is not None and p not in uuids:
                bad.add(p)
    return bad


def validate(orig_bytes, new_bytes, lines, cfg, phase5=False):
    """Run the full validator battery. Returns a list of error strings (empty ==
    safe to write). Used both pre-write (in-memory result) and post-write (a
    fresh read of what actually landed on disk)."""
    errs = []
    old_parts = orig_bytes.split(b"\n")
    new_parts = new_bytes.split(b"\n")

    # v_shrink
    if len(new_bytes) > len(orig_bytes):
        errs.append("v_shrink: output is larger than input")

    # v_linecount (hard invariant for stub-in-place phases)
    if not phase5 and len(old_parts) != len(new_parts):
        errs.append(f"v_linecount: {len(old_parts)} -> {len(new_parts)} lines")
        return errs  # per-line comparisons below would be meaningless

    new_objs = _parts_objs(new_bytes)

    # v_parse
    for i, o in enumerate(new_objs):
        if isinstance(o, tuple):
            errs.append(f"v_parse: line {i} unparseable: {o[1]}")

    # v_identity (byte-identity of untouched lines; structural stability of edits)
    if not phase5:
        for i, ln in enumerate(lines):
            if not ln.dirty:
                if new_parts[i] != ln.raw:
                    errs.append(f"v_identity: untouched line {i} changed")
            else:
                no = new_objs[i]
                if isinstance(no, dict) and ln.fp0 is not None:
                    fp1 = (no.get("type"), no.get("uuid"), no.get("parentUuid"))
                    if fp1 != ln.fp0:
                        errs.append(f"v_identity: edited line {i} changed type/uuid/parent")

    # v_pairs (tool_use / tool_result id sets unchanged)
    new_tu, new_tr = set(), set()
    for o in new_objs:
        if isinstance(o, dict):
            new_tu |= _tool_use_ids(o)
            new_tr |= _tool_result_ids(o)
    old_objs = _parts_objs(orig_bytes)
    old_tu, old_tr = set(), set()
    for o in old_objs:
        if isinstance(o, dict):
            old_tu |= _tool_use_ids(o)
            old_tr |= _tool_result_ids(o)
    if new_tu != old_tu:
        errs.append("v_pairs: tool_use id set changed")
    if new_tr != old_tr:
        errs.append("v_pairs: tool_result id set changed")

    # v_chain (introduce no NEW parentUuid orphans)
    new_orphans = _orphans(new_objs) - _orphans(old_objs)
    if new_orphans:
        errs.append(f"v_chain: new orphaned parentUuid(s): {sorted(new_orphans)}")

    return errs


# --------------------------------------------------------------------------- #
# Audit / integrity report (the read-only `audit` subcommand)
# --------------------------------------------------------------------------- #

def audit(data):
    """Read-only integrity checks on any transcript (touched or not). Returns a
    list of (level, message) — OK / WARN / FAIL, in doctor.py's style."""
    out = []
    objs = _parts_objs(data)
    bad = [i for i, o in enumerate(objs) if isinstance(o, tuple)]
    if bad:
        out.append(("FAIL", f"{len(bad)} unparseable line(s): {bad[:10]}"))
    else:
        out.append(("OK", f"all {sum(1 for o in objs if o is not None)} non-blank lines parse"))
    orph = _orphans(objs)
    out.append(("WARN" if orph else "OK",
                f"{len(orph)} orphaned parentUuid(s)" if orph else "uuid/parentUuid chain intact"))
    tu = set()
    tr = set()
    for o in objs:
        if isinstance(o, dict):
            tu |= _tool_use_ids(o)
            tr |= _tool_result_ids(o)
    unpaired = tr - tu
    out.append(("WARN" if unpaired else "OK",
                f"{len(unpaired)} tool_result(s) with no tool_use" if unpaired
                else f"{len(tu)} tool_use / {len(tr)} tool_result ids paired"))
    marked = sum(1 for o in objs if MARKER_PREFIX in _dumps(o)) if objs else 0
    out.append(("OK", f"{marked} line(s) carry ca-condensed markers"))
    return out


# --------------------------------------------------------------------------- #
# Write protocol (live-race-safe; see plan "Biggest risk" §3-§5)
# --------------------------------------------------------------------------- #

def backup_dir():
    return os.path.join(os.path.expanduser("~"), ".codearbiter", "prune-backups")


def _safe_session(s):
    """Reduce a session id to a safe single-path-component filename. The hook
    payload's `session_id` is external input that feeds the backup filename and a
    glob prefix in _prune_old_backups; an unsanitized value containing `..` or a
    path separator could escape the backup dir. Normally a UUID, but never trust
    it."""
    s = str(s) if s is not None else "session"
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s).strip(".")
    return (s or "session")[:128]


def _prune_old_backups(session, keep):
    d = backup_dir()
    try:
        entries = sorted(f for f in os.listdir(d) if f.startswith(session + "."))
    except Exception:  # noqa: BLE001
        return
    for f in entries[:-keep] if keep > 0 else entries:
        try:
            os.remove(os.path.join(d, f))
        except Exception:  # noqa: BLE001
            pass


def self_heal(path, session="session"):
    """Detect and repair the mid-write crash corpse, before any new prune.

    write_in_place writes new_bytes (shorter) over the original and THEN
    truncates. A process death between the two leaves the file as
    new_bytes + orig[len(new_bytes):] — the boundary lands inside an old line,
    so exactly one line is unparseable JSON. The newest backup for the session
    holds the original; restore it, preserving any lines a live appender added
    after the crash (they sit beyond len(backup)).

    Conservative by design: heals ONLY when the damage matches that splice
    signature — one bad line, file at least backup-sized, and the bytes from
    the end of the bad line up to len(backup) identical to the backup's. Any
    other corruption is left alone for a human. Returns (healed, note).
    """
    if os.path.islink(path):
        return False, "symlink"
    try:
        with open(path, "rb") as f:
            corpse = f.read()
    except OSError as e:
        return False, f"unreadable ({e})"
    parts = corpse.split(b"\n")
    objs = _parts_objs(corpse)
    bad = [i for i, o in enumerate(objs) if isinstance(o, tuple)]
    if not bad:
        return False, "clean"
    session = _safe_session(session)
    d = backup_dir()
    try:
        entries = sorted(f for f in os.listdir(d) if f.startswith(session + "."))
    except OSError:
        entries = []
    if not entries:
        return False, "corrupt, but no backup for this session"
    bpath = os.path.join(d, entries[-1])
    try:
        with open(bpath, "rb") as f:
            backup = f.read()
    except OSError as e:
        return False, f"backup unreadable ({e})"
    if any(isinstance(o, tuple) for o in _parts_objs(backup)):
        return False, "backup itself is corrupt"
    # --- splice-signature checks -------------------------------------------
    if len(bad) != 1:
        return False, "corruption does not match a prune splice (multiple bad lines)"
    if len(corpse) < len(backup):
        return False, "file shorter than backup; not an interrupted truncate"
    # Byte offset just past the bad line (its trailing \n included).
    end_off = sum(len(p) + 1 for p in parts[:bad[0] + 1])
    end_off = min(end_off, len(corpse))
    if end_off > len(backup) or corpse[end_off:len(backup)] != backup[end_off:len(backup)]:
        return False, "corruption does not match a prune splice (tail differs from backup)"
    # --- heal ----------------------------------------------------------------
    # Everything past len(backup) was appended by the live session AFTER the
    # crash (the file was exactly backup-sized when the prune died); keep it.
    tail = corpse[len(backup):]
    healed = backup + tail  # len(healed) == len(corpse): no truncate needed,
    #                          and an append racing this write lands beyond it.
    with open(path, "r+b") as f:
        f.write(healed)
        f.flush()
        os.fsync(f.fileno())
    append_audit_log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session, "path": path,
        "verdict": f"self-healed from {entries[-1]}",
    })
    return True, f"healed from backup {entries[-1]}"


def write_in_place(path, new_bytes, pre_stat, cfg, session="session",
                   _probe=None):
    """Same-inode, shrink-only rewrite that is safe against a concurrent appender.

    Returns (ok: bool, verdict: str). `_probe`, if given, is invoked right after
    write+fsync and before the truncate decision — a test seam to simulate a
    concurrent append.
    """
    # Refuse to follow a symlink: we rewrite in place and back up the target, so
    # a symlinked transcript path would let us rewrite (and copy out) an
    # arbitrary file. Transcripts are always real files under ~/.claude/projects.
    if os.path.islink(path):
        return False, "skipped: refusing to write through a symlink"
    session = _safe_session(session)
    # Re-stat: bail if the session moved on since we read it.
    try:
        now = os.stat(path)
    except OSError as e:
        return False, f"skipped: stat failed ({e})"
    if (now.st_size, now.st_mtime_ns) != (pre_stat.st_size, pre_stat.st_mtime_ns):
        return False, "skipped: file changed since read"

    old_size = pre_stat.st_size
    with open(path, "rb") as f:
        orig_bytes = f.read()

    # Backup first.
    d = backup_dir()
    os.makedirs(d, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bpath = os.path.join(d, f"{session}.{ts}.jsonl")
    shutil.copy2(path, bpath)

    def _restore_prefix():
        # Rewrite the original prefix; leave anything appended past old_size.
        with open(path, "r+b") as f:
            f.write(orig_bytes)
            f.flush()
            os.fsync(f.fileno())

    with open(path, "r+b") as f:
        f.write(new_bytes)
        f.flush()
        os.fsync(f.fileno())
        if _probe is not None:
            _probe(path)
        grown = os.fstat(f.fileno()).st_size
        if grown > old_size:
            # A concurrent append landed during our write. Truncating now would
            # eat that line. Restore the prefix and bail.
            f.close()
            _restore_prefix()
            _prune_old_backups(session, cfg.backups)
            return False, "rolled-back: concurrent append during write"
        f.truncate(len(new_bytes))
        f.flush()
        os.fsync(f.fileno())

    # Post-write: re-read and re-validate what actually landed. We have no
    # dirty-flag context here, so this is a phase-agnostic structural check of
    # the disk image against the original.
    with open(path, "rb") as f:
        landed = f.read()
    errs = _post_write_check(orig_bytes, landed)
    if errs:
        # Roll back without eating a concurrent append. At this point the file
        # is new_bytes (we truncated above); a live appender may have added
        # lines at offset len(new_bytes) since. Those bytes sit BELOW
        # len(orig_bytes), so blindly rewriting the original prefix (let alone
        # truncating) would destroy them. Capture the appended tail first,
        # restore the original, and re-append the tail after it.
        with open(path, "r+b") as f:
            cur = os.fstat(f.fileno()).st_size
            tail = b""
            if cur > len(new_bytes):
                f.seek(len(new_bytes))
                tail = f.read()
            f.seek(0)
            f.write(orig_bytes + tail)
            f.flush()
            os.fsync(f.fileno())
            # Mirror the main-path growth guard: truncate only if nothing newer
            # landed during the restore itself.
            end = os.fstat(f.fileno()).st_size
            if end <= len(orig_bytes) + len(tail):
                f.truncate(len(orig_bytes) + len(tail))
        _prune_old_backups(session, cfg.backups)
        return False, "rolled-back: post-write validation failed: " + "; ".join(errs)

    _prune_old_backups(session, cfg.backups)
    return True, "written"


def _post_write_check(orig_bytes, landed):
    """Structural re-validation of the on-disk result (no dirty-flag context)."""
    errs = []
    new_objs = _parts_objs(landed)
    for i, o in enumerate(new_objs):
        if isinstance(o, tuple):
            errs.append(f"line {i} unparseable")
    if len(orig_bytes.split(b"\n")) != len(landed.split(b"\n")):
        errs.append("line count changed on disk")
    if len(landed) > len(orig_bytes):
        errs.append("disk image larger than original")
    old_objs = _parts_objs(orig_bytes)

    def ids(objs):
        tu, tr = set(), set()
        for o in objs:
            if isinstance(o, dict):
                tu |= _tool_use_ids(o)
                tr |= _tool_result_ids(o)
        return tu, tr
    if ids(new_objs) != ids(old_objs):
        errs.append("tool id sets changed on disk")
    if (_orphans(new_objs) - _orphans(old_objs)):
        errs.append("new orphaned parentUuid on disk")
    return errs


def state_path():
    return os.path.join(os.path.expanduser("~"), ".codearbiter", "prune-state.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(state):
    d = os.path.dirname(state_path())
    try:
        os.makedirs(d, exist_ok=True)
        with open(state_path(), "w", encoding="utf-8") as f:
            f.write(_dumps(state))
    except Exception:  # noqa: BLE001
        pass


def tail_is_settled(lines):
    """True iff the transcript tail is a clean turn boundary: the most recent
    assistant turn's tool calls are all resolved and we're not mid queue-op."""
    last_asst = None
    tr = set()
    for ln in lines:
        if isinstance(ln.obj, dict):
            if ln.obj.get("type") == "assistant":
                last_asst = ln
            tr |= _tool_result_ids(ln.obj)
    if last_asst is not None and (_tool_use_ids(last_asst.obj) - tr):
        return False  # an open tool loop on the latest assistant turn
    for ln in reversed(lines):
        if isinstance(ln.obj, dict):
            if ln.obj.get("type") == "queue-operation":
                return False
            break
    return True


def hook_run(payload, env=None):
    """Service-mode entry: gate, short-circuit cheaply, prune at a safe point,
    and record state for the statusline. ALWAYS returns 0 — a pruner failure
    must never block the user's prompt or break the session."""
    e = env if env is not None else os.environ
    mode = (e.get("CODEARBITER_PRUNE", "off") or "off").lower()
    if mode not in ("dry", "on"):
        return 0
    path = payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        return 0
    # N-1: containment — transcript must live under ~/.claude/ to prevent an
    # attacker-controlled payload from pointing the pruner at arbitrary files.
    try:
        _claude_home = os.path.normcase(os.path.normpath(
            os.path.realpath(os.path.expanduser("~/.claude"))
        ))
        _real_path = os.path.normcase(os.path.normpath(os.path.realpath(path)))
        if not _real_path.startswith(_claude_home):
            return 0
    except Exception:  # noqa: BLE001 — realpath can fail on unusual mounts
        return 0
    root = payload.get("cwd") or os.getcwd()
    try:
        import _hooklib
        if not _hooklib.arbiter_active(root):
            return 0
    except Exception:  # noqa: BLE001
        return 0
    session = payload.get("session_id") or os.path.splitext(os.path.basename(path))[0]
    cfg = Config.from_env(e)
    cfg.execute = (mode == "on")
    if cfg.execute:
        # Repair the corpse a prune killed mid write/truncate may have left,
        # BEFORE any gate reads or short-circuits on the damaged file.
        try:
            self_heal(path, session)
        except Exception:  # noqa: BLE001 — never let healing break the turn
            return 0
    try:
        st = os.stat(path)
    except OSError:
        return 0
    if st.st_size < cfg.min_size or st.st_size > (50 << 20):
        return 0
    state = load_state()
    rec = state.get(session, {})
    if rec and (st.st_size - rec.get("last_pruned_size", 0)) < cfg.min_growth:
        return 0  # cheap stat short-circuit: not enough new bytes
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:  # noqa: BLE001
        return 0
    if not tail_is_settled(load_lines(data)):
        return 0
    try:
        res = run(path, cfg, session=session)
    except Exception:  # noqa: BLE001 — never let pruning break the turn
        return 0
    b0, b1 = res["bytes_before"], res["bytes_after"]
    state[session] = {
        "path": path,
        "last_size": b1 if res["executed"] else b0,
        "last_pruned_size": (b1 if res["executed"] else st.st_size),
        "last_run_ts": int(time.time()),
        "pct": round(100.0 * (b0 - b1) / b0, 1) if b0 else 0.0,
        "freed_bytes": b0 - b1,
        "verdict": res["verdict"],
    }
    save_state(state)
    return 0


def append_audit_log(record):
    d = os.path.join(os.path.expanduser("~"), ".codearbiter")
    os.makedirs(d, exist_ok=True)
    try:
        with open(os.path.join(d, "prune.log"), "a", encoding="utf-8") as f:
            f.write(_dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Top-level run (dry-run analysis; execute optionally writes)
# --------------------------------------------------------------------------- #

def run(path, cfg, session="session"):
    """Prune `path` per `cfg`. Always computes the report; writes only when
    cfg.execute and validation passes. Returns a result dict."""
    if cfg.execute:
        # A prior prune killed between write and truncate leaves a spliced
        # file; restore it from backup before analyzing. (Dry-run never writes,
        # including this.)
        self_heal(path, session)
    with open(path, "rb") as f:
        orig_bytes = f.read()
        pre_stat = os.fstat(f.fileno())

    lines = load_lines(orig_bytes)
    index = build_index(lines, cfg)
    report = apply_strategies(lines, index, cfg)
    new_bytes = serialize(lines)

    errs = validate(orig_bytes, new_bytes, lines, cfg)
    result = {
        "path": path,
        "bytes_before": len(orig_bytes),
        "bytes_after": len(new_bytes),
        "est_tokens_before": est_tokens(len(orig_bytes)),
        "est_tokens_after": est_tokens(len(new_bytes)),
        "strategies": report,
        "validation_errors": errs,
        "executed": False,
        "verdict": "dry-run",
    }
    if errs:
        result["verdict"] = "refused: validation failed"
        return result
    if cfg.execute:
        ok, verdict = write_in_place(path, new_bytes, pre_stat, cfg, session=session)
        result["executed"] = ok
        result["verdict"] = verdict
        append_audit_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session": session, "path": path,
            "bytes_before": len(orig_bytes), "bytes_after": len(new_bytes),
            "strategies": {k: v["bytes_before"] - v["bytes_after"]
                           for k, v in report.items()},
            "verdict": verdict,
        })
    return result
