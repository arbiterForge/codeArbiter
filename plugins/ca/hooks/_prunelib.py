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
                 "edited_paths")


def build_index(lines, cfg):
    """Compute the protected tail and pre-strategy tool-id sets. The protected
    tail is everything at/after the earlier of (a) the K-th most recent
    tool-bearing line and (b) the last assistant message (whose thinking
    signature must never be touched)."""
    idx = Index()
    tool_line_idxs = []
    last_assistant = -1
    tu, tr = set(), set()
    edited = set()
    for ln in lines:
        o = ln.obj
        if not isinstance(o, dict):
            continue
        if o.get("type") == "assistant":
            last_assistant = ln.idx
        a, b = _tool_use_ids(o), _tool_result_ids(o)
        if a or b:
            tool_line_idxs.append(ln.idx)
        tu |= a
        tr |= b
        # Track files a later Write/Edit superseded (used by Phase-3 strategy).
        msg = o.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            for blk in msg["content"]:
                if (isinstance(blk, dict) and blk.get("type") == "tool_use"
                        and blk.get("name") in ("Write", "Edit")):
                    fp = (blk.get("input") or {}).get("file_path")
                    if fp:
                        edited.add(fp)
    keep = cfg.keep_recent
    if keep <= 0:
        prot_tool = len(lines)
    elif len(tool_line_idxs) > keep:
        prot_tool = tool_line_idxs[-keep]
    elif tool_line_idxs:
        prot_tool = tool_line_idxs[0]
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


# name -> (tier, function). Pinned order matters (data dependencies); selection
# preserves this order. Only Phase-1 strategies are wired today; later phases
# register here without touching the pipeline.
TIERS = {"gentle": 0, "standard": 1, "aggressive": 2}
STRATEGIES = {
    "sidecar-collapse": ("gentle", s_sidecar_collapse),
    "oversize-result-clamp": ("gentle", s_oversize_result_clamp),
}
STRATEGY_ORDER = ["sidecar-collapse", "oversize-result-clamp"]


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


def write_in_place(path, new_bytes, pre_stat, cfg, session="session",
                   _probe=None):
    """Same-inode, shrink-only rewrite that is safe against a concurrent appender.

    Returns (ok: bool, verdict: str). `_probe`, if given, is invoked right after
    write+fsync and before the truncate decision — a test seam to simulate a
    concurrent append.
    """
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
        _restore_prefix()
        with open(path, "r+b") as f:
            f.truncate(len(orig_bytes))
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
