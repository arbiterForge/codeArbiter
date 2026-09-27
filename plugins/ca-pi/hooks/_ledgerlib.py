#!/usr/bin/env python3
# codeArbiter — cost/token ledger subsystem for the statusline (extracted T-12).
#
# Owns the user-level Claude accounting the statusline renders (spec
# claude-statusline-accounting-integrity): a bounded, starvation-free scanner over
# the parent transcript AND every delegated `<session>/subagents/*.jsonl`
# transcript. It is the ONE JSONL parser on the render path. Around it sit
# per-session v2 state under ~/.codearbiter/ledger.json.sessions/, incrementally
# maintained Session/Today totals with structured coverage, the separately kept
# host-reported estimate, and parent-only burn samples for the sparkline. What a
# usage record MEANS (identity, reconciliation, pricing) is owned by _usagelib;
# this module persists, schedules and aggregates. No rendering concern (no ANSI,
# no box drawing), so the accounting is unit-testable in isolation.
#
# Design principles (mirroring _metricslib.py / _taskboardlib.py):
#   - Stdlib only; no third-party imports ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O.
#   - ledger_update(), persist_sess_start() and pi_ledger_update() are the only
#     filesystem entry points; everything else is pure or a private bounded
#     persistence helper.
#   - Bounds defer work, never discard it: an offset never advances past bytes
#     that were not consumed, and backlog shows as `catching_up`.
#   - Steady-state cost never grows with history. A no-change render reads only
#     compact summaries; request evidence is loaded only for new records.
#   - Never raise on malformed user input — every reader degrades to safe blanks,
#     and uncertainty surfaces as coverage reasons, never as a fabricated figure.
#
# Public API:
#   ledger_path() -> str                     resolved ledger anchor path (env-overridable)
#   ledger_update(data, sid) -> tuple        (summary, session, today); session/today carry
#                                            in/out tokens, exact picodollars `pd`, display
#                                            `cost`, coverage `state`, `reasons`, `stale`
#   persist_sess_start(sid, value) -> bool   cache a resolved session-start epoch
#   pi_ledger_path() -> str                  separate user-global Pi ledger path
#   pi_ledger_update(session_key, scan_start, scan_end, facts, path=None) -> dict
#                                               bounded Pi session/day snapshot
#   burn_samples(rec) -> list[float]         recent per-request (parent-only) burn values

import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# _acquire_lock/_release_lock/LOCK_WAIT were hoisted to _hooklib (#271 C-2) so
# taskwrite.py's board writer can share ONE lock implementation instead of a
# second hand-rolled copy. Re-exported under their ORIGINAL private names so
# this module's own call sites (ledger_update/persist_sess_start) and the test
# suite's `mock.patch.object(L, "_acquire_lock", ...)` / `mock.patch.object(L,
# "LOCK_WAIT", ...)` seams keep working unchanged — no import-cycle risk:
# _hooklib imports only hostapi, never _ledgerlib.
from _hooklib import acquire_lock as _acquire_lock  # noqa: E402
from _hooklib import release_lock as _release_lock  # noqa: E402
from _hooklib import LOCK_WAIT  # noqa: E402
# parse_iso lives in _fmtlib, which already documents it as part of its public
# API; this module carried a byte-identical second copy (#334 item 3). Same
# re-export pattern as the lock helpers above: one owner, and `L.parse_iso`
# stays importable for this module's call sites and the test suite. No cycle
# risk — _fmtlib imports only _colorlib, never _ledgerlib.
from _fmtlib import parse_iso  # noqa: E402,F401
# Usage semantics (normalization, identity, reconciliation, pricing) have ONE
# owner; this module only persists, schedules and aggregates what it returns.
import _usagelib  # noqa: E402
try:  # presentation label for child transcripts, derived by the one parser here
    from _subagentslib import sub_label as _sub_label  # noqa: E402
except Exception:  # pragma: no cover — a label is never worth breaking accounting
    _sub_label = None

# Tunables (module constants; mirrored from the original inline statusline block).
SESSION_TTL = 36 * 3600  # prune sessions older than ~1.5 days
BURN_RING = 40           # recent per-call token-burn samples kept for the sparkline
# `last_ts` exists only to keep a live record inside SESSION_TTL. Stamping it on
# EVERY render made every render a writing render (#392) — the statusline runs in
# a fresh process per refresh, so that was two atomic replacements per refresh
# forever. Refresh it on a write we are making anyway, or at most once per
# heartbeat; 5 minutes is ~432x inside the 36-hour TTL.
LEDGER_HEARTBEAT = 300

# Pi's bridge sends only already-extracted usage facts. The bridge chunks long
# sessions so one call and one lock hold stay predictably small. `session_key` is
# a caller-derived SHA-256 digest of the stable Pi session identity, never the raw
# session name/path. These bounds mirror the footer's normalized numeric ceiling.
PI_MAX_SCAN_ENTRIES = 256
PI_MAX_SHARD_BYTES = 65_536
PI_MAX_POSITION = 2_147_483_647
PI_MAX_TOKENS = 1_000_000_000_000_000
PI_MAX_COST_USD = 1_000_000_000.0
PI_MAX_DAYS = 64
PI_MAX_SHARDS = 256
PI_MAX_DIRECTORY_ENTRIES = 8192
PI_MAX_UPDATED_AT = 9_999_999_999
PI_MAX_TIMESTAMP_CHARS = 64
PI_MAX_PATH_CHARS = 32_768
PI_MIN_YEAR = 2000
PI_MAX_YEAR = 2100
PI_LEDGER_SCHEMA = "codearbiter.pi-usage-ledger/v1"
PI_SESSION_SCHEMA = "codearbiter.pi-usage-session/v1"
PI_SESSION_KEY_RE = re.compile(r"[0-9a-f]{64}\Z")
PI_SHARD_NAME_RE = re.compile(r"([0-9a-f]{64})\.json\Z")
PI_DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
PI_TOTAL_KEYS = frozenset({
    "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens", "costUsd",
})
PI_FACT_KEYS = frozenset({"position", "timestamp"}) | PI_TOTAL_KEYS
PI_STATUSES = frozenset({"ok", "invalid", "corrupt", "lock_failed", "write_failed"})

# --------------------------------------------------------------------------- coercion
def num(x, default=0.0):
    """Coerce any host value to float; tolerate strings, None, and containers."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def safe(fn, *a, **k):
    """Run fn; swallow any failure so one bad input can't break the ledger.
    Returns None on error (caller treats it as a no-op / blank)."""
    try:
        return fn(*a, **k)
    except Exception:  # noqa: BLE001
        return None


def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


# --------------------------------------------------------------------------- ledger files
def ledger_path():
    return os.environ.get("CODEARBITER_LEDGER") or \
        os.path.join(os.path.expanduser("~"), ".codearbiter", "ledger.json")


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value
    except (OSError, ValueError):
        return default


def _atomic_json(path, value):
    """Atomically replace one JSON file without sharing a staging pathname."""
    tmp = None
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _session_dir(path):
    return f"{path}.sessions"


def _session_key(sid):
    return hashlib.sha256(str(sid).encode("utf-8", "replace")).hexdigest()


def _session_file(path, sid):
    """The LEGACY (v1) per-session shard. v2 never writes it; it is read once to
    seed a migrating session and otherwise only stat-ed for pruning."""
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.json")


def _start_file(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.start.json")


def _acct_file(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.acct.json")


def _hot_file(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.hot.json")


def _ev_dir(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.ev")


# --------------------------------------------------------------------------- v2 accounting (spec
# claude-statusline-accounting-integrity). One compact SUMMARY per session is read
# on every render; request EVIDENCE lives in a bounded hot file plus hash-prefix
# partitions that split before they exceed PART_MAX, and is loaded only for the
# identities a render's new records touch. Derived totals are maintained by
# subtract-old / add-new, so steady-state work never grows with history.
ACCT_SCHEMA = "codearbiter.claude-accounting/v2"
ACCT_BYTE_BUDGET = 8 * 1024 * 1024     # transcript bytes read per render, all sources
ACCT_RECORD_BUDGET = 50000             # complete JSONL lines consumed per render
ACCT_SOURCE_BUDGET = 16                # sources opened per render
MAX_RECORD_BYTES = 4 * 1024 * 1024     # per-line ceiling (~14x the largest observed line)
DISCOVERY_BOUND = 4096                 # child transcripts discovered per session
HOT_MAX = 256                          # hot evidence entries before eviction to cold
PART_MAX = 256                         # entries per cold partition before it splits
UI_LOCK_WAIT = 0.02                    # render-path try-lock budget (seconds)
FP_WINDOW = 512                        # head/tail fingerprint window (bytes)
UNPROVEN_KEEP = 8                      # byte positions of unproven records kept per source
_LEGACY_SHARD = re.compile(r"[0-9a-f]{64}\.json\Z")
_HEX = "0123456789abcdef"


class _Inconsistent(Exception):
    """Evidence on disk does not match the summary that should own it."""


def _local_day(ts):
    """Local calendar day (YYYY-MM-DD) of a trustworthy transcript timestamp."""
    e = parse_iso(ts)
    try:
        return datetime.fromtimestamp(e).strftime("%Y-%m-%d")
    except (TypeError, OSError, OverflowError, ValueError):
        return None


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _order_sources(ids):
    """Deterministic child scheduling order (a test seam for order independence)."""
    return sorted(ids)


def _ident_hash(key):
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()


def _fresh_summary(sid, now):
    return {"v": 2, "sid": sid, "first_ts": now, "last_ts": now, "reg": _usagelib.REGISTRY_VERSION,
            "seq": 0, "hot_seq": 0, "parts": {}, "mid_only": 0, "src": {}, "cursor": "",
            "tot": {"in": 0, "out": 0, "pd": 0}, "rc": {}, "days": {}, "unk_time": 0,
            "host": {"latest": None, "max": None, "anom": False, "missing": False, "seen": False},
            "burn": [], "flags": {}, "cov": {}}


def _summary_valid(rec, sid):
    try:
        return (rec.get("v") == 2 and rec.get("sid") == sid
                and isinstance(rec.get("src"), dict) and isinstance(rec.get("tot"), dict)
                and isinstance(rec.get("days"), dict) and isinstance(rec.get("parts"), dict)
                and isinstance(rec.get("host"), dict) and isinstance(rec.get("burn"), list)
                and isinstance(rec.get("rc"), dict) and isinstance(rec.get("seq"), int))
    except AttributeError:
        return False


class _Store:
    """Evidence for one session: a bounded LRU hot map plus cold hash-prefix
    partitions. Every file carries the summary sequence number it was written
    under; a mismatch on load means a torn commit and raises _Inconsistent."""

    def __init__(self, path, sid, rec):
        self.path, self.sid, self.rec = path, sid, rec
        self.hot = None
        self.hot_dirty = False
        self.parts = {}
        self.parts_dirty = set()
        self.obsolete = []

    def _part_file(self, prefix):
        return os.path.join(_ev_dir(self.path, self.sid), f"p{prefix}.json")

    def _load_hot(self):
        if self.hot is None:
            want = self.rec.get("hot_seq", 0)
            if want:
                v = _read_json(_hot_file(self.path, self.sid))
                if not (isinstance(v, dict) and v.get("seq") == want
                        and isinstance(v.get("ev"), dict) and isinstance(v.get("order"), list)):
                    raise _Inconsistent
                self.hot = {"ev": v["ev"], "order": [k for k in v["order"] if k in v["ev"]]}
            else:
                self.hot = {"ev": {}, "order": []}
        return self.hot

    def _leaf(self, h):
        parts = self.rec["parts"]
        for k in range(len(h) + 1):
            if h[:k] in parts:
                return h[:k]
        raise _Inconsistent

    def _load_part(self, prefix):
        if prefix not in self.parts:
            want = self.rec["parts"].get(prefix, 0)
            if not want:
                self.parts[prefix] = {}
            else:
                v = _read_json(self._part_file(prefix))
                if not (isinstance(v, dict) and v.get("seq") == want and isinstance(v.get("ev"), dict)):
                    raise _Inconsistent
                self.parts[prefix] = v["ev"]
        return self.parts[prefix]

    def get(self, key):
        """(entry, location) where location is "hot" or a partition prefix."""
        hot = self._load_hot()
        if key in hot["ev"]:
            return hot["ev"][key], "hot"
        if self.rec["parts"]:
            prefix = self._leaf(_ident_hash(key))
            part = self._load_part(prefix)
            if key in part:
                return part[key], prefix
        return None, None

    def put(self, key, entry, where):
        if where is None or where == "hot":
            hot = self._load_hot()
            if key in hot["ev"]:
                hot["order"].remove(key)
            hot["ev"][key] = entry
            hot["order"].append(key)
            self.hot_dirty = True
        else:
            self._load_part(where)[key] = entry
            self.parts_dirty.add(where)

    def delete(self, key, where):
        if where == "hot":
            hot = self._load_hot()
            hot["ev"].pop(key, None)
            if key in hot["order"]:
                hot["order"].remove(key)
            self.hot_dirty = True
        elif where is not None:
            self._load_part(where).pop(key, None)
            self.parts_dirty.add(where)

    def evict(self):
        hot = self.hot
        if hot is None or len(hot["ev"]) <= HOT_MAX:
            return
        if not self.rec["parts"]:
            self.rec["parts"][""] = 0
        n = len(hot["ev"]) - HOT_MAX // 2
        victims, hot["order"] = hot["order"][:n], hot["order"][n:]
        for key in victims:
            entry = hot["ev"].pop(key)
            prefix = self._leaf(_ident_hash(key))
            self._load_part(prefix)[key] = entry
            self.parts_dirty.add(prefix)
        self.hot_dirty = True
        for prefix in list(self.parts_dirty):
            self._split(prefix)

    def _split(self, prefix):
        part = self._load_part(prefix)
        if len(part) <= PART_MAX or len(prefix) >= 64:
            return
        if self.rec["parts"].get(prefix):
            self.obsolete.append(self._part_file(prefix))
        del self.rec["parts"][prefix]
        del self.parts[prefix]
        self.parts_dirty.discard(prefix)
        children = {prefix + c: {} for c in _HEX}
        for key, entry in part.items():
            children[prefix + _ident_hash(key)[len(prefix)]][key] = entry
        for child, entries in children.items():
            self.rec["parts"][child] = 0
            self.parts[child] = entries
            self.parts_dirty.add(child)
        for child in children:
            self._split(child)

    def all_locations(self):
        """Every (key, entry, location) — a full walk, only for rebuilds."""
        hot = self._load_hot()
        for key in list(hot["ev"]):
            yield key, hot["ev"][key], "hot"
        for prefix in list(self.rec["parts"]):
            part = self._load_part(prefix)
            for key in list(part):
                yield key, part[key], prefix

    def flush(self, seq):
        """Write dirty evidence under `seq`; False on any failure (the caller
        must then NOT commit the summary)."""
        for prefix in sorted(self.parts_dirty):
            if prefix not in self.rec["parts"]:
                continue
            entries = self.parts.get(prefix, {})
            if entries:
                if not _atomic_json(self._part_file(prefix), {"seq": seq, "ev": entries}):
                    return False
                self.rec["parts"][prefix] = seq
            else:
                if self.rec["parts"].get(prefix):
                    self.obsolete.append(self._part_file(prefix))
                self.rec["parts"][prefix] = 0
        if self.hot_dirty:
            hot = self._load_hot()
            if not _atomic_json(_hot_file(self.path, self.sid),
                                {"seq": seq, "ev": hot["ev"], "order": hot["order"]}):
                return False
            self.rec["hot_seq"] = seq
        return True


def _bump(counts, reason, sign):
    n = counts.get(reason, 0) + sign
    if n:
        counts[reason] = n
    else:
        counts.pop(reason, None)


def _contrib(entry):
    """Priced contribution of one request's accepted evidence."""
    facts = entry["s"]
    acc = None
    for src in sorted(facts):
        acc = _usagelib.merge(acc, facts[src])
    p = _usagelib.price(acc)
    return {"o": "p" if "p" in facts else min(facts), "day": _usagelib.event_day(acc),
            "days": _usagelib.days_seen(acc), "in": p["in"], "out": p["out"], "pd": p["pd"],
            "r": sorted(p["reasons"])}


def _apply(rec, c, sign):
    """Add (sign=+1) or remove (sign=-1) one contribution from every derived index."""
    tot = rec["tot"]
    tot["in"] += sign * c["in"]
    tot["out"] += sign * c["out"]
    tot["pd"] += sign * c["pd"]
    for r in c["r"]:
        _bump(rec["rc"], r, sign)
    if c["day"]:
        day = rec["days"].setdefault(c["day"], {"in": 0, "out": 0, "pd": 0, "rc": {}})
        day["in"] += sign * c["in"]
        day["out"] += sign * c["out"]
        day["pd"] += sign * c["pd"]
        for r in c["r"]:
            _bump(day["rc"], r, sign)
        if len(c["days"]) > 1:
            for d in c["days"]:
                other = rec["days"].setdefault(d, {"in": 0, "out": 0, "pd": 0, "rc": {}})
                _bump(other["rc"], "conflicting_event_day", sign)
        for d in set(c["days"]) | {c["day"]}:
            b = rec["days"].get(d)
            if b is not None and not (b["in"] or b["out"] or b["pd"] or b["rc"]):
                del rec["days"][d]
    else:
        rec["unk_time"] += sign
    src = rec["src"].get(c["o"])
    if src is not None:
        src["tok"][0] += sign * c["in"]
        src["tok"][1] += sign * c["out"]
        src["pd"] += sign * c["pd"]


def _burn_touch(rec, key, old, new):
    """Parent-only burn (spec AC-24): one sample per parent-owned request, in
    order of first acceptance, updated as later snapshots grow it."""
    if new is None or new["o"] != "p":
        return
    tag = _ident_hash(key)[:12]
    value = new["in"] + new["out"]
    for item in rec["burn"]:
        if item[0] == tag:
            item[1] = value
            return
    if old is None or old["o"] != "p":
        rec["burn"].append([tag, value])
        if len(rec["burn"]) > BURN_RING:
            rec["burn"] = rec["burn"][-BURN_RING:]


def _find_by_mid(store, mid_key):
    """(rid key, entry, location) of the request whose stored message id is
    `mid_key`. A full evidence walk: it runs only for a message-ID-only record
    whose alias is not yet known, which the observed corpus never produced for
    billable usage (spec observation 5)."""
    for key, entry, where in list(store.all_locations()):
        if entry.get("m") == mid_key and "s" in entry:
            return key, entry, where
    return None, None, None


def _ingest(store, rec, src, key, alias, fact):
    """Merge one source's fact into its request's evidence and move the derived
    indices by exactly (new contribution - old contribution).

    Identity is `rid:` when a request id exists. The record's message id is kept
    inside that entry (`m`), so a message-ID-only representation of the same
    request resolves to it in either arrival order without an eager alias entry
    per request (spec D-5)."""
    entry, where = store.get(key)
    if entry is not None and "a" in entry:     # message-ID-only record of an aliased request
        key = entry["a"]
        entry, where = store.get(key)
    elif entry is None and key.startswith("mid:"):
        found, fentry, fwhere = _find_by_mid(store, key)
        if found is not None:
            store.put(key, {"a": found}, "hot")        # remember: no second walk
            key, entry, where = found, fentry, fwhere
    old = _contrib(entry) if entry is not None and entry.get("s") else None
    if entry is None:
        entry, where = {"s": {}}, None
    folded = False
    if alias and rec.get("mid_only", 0) > 0:
        aentry, awhere = store.get(alias)
        if aentry is not None and aentry.get("s"):
            _apply(rec, _contrib(aentry), -1)          # earlier mid-only evidence joins
            for s2, f2 in aentry["s"].items():
                entry["s"][s2] = _usagelib.merge(entry["s"].get(s2), f2)
            rec["mid_only"] -= 1
            store.put(alias, {"a": key}, awhere)
            folded = True
    if alias and entry.get("m") != alias:
        entry["m"] = alias
        folded = folded or old is not None
    prev = entry["s"].get(src)
    merged = _usagelib.merge(prev, fact)
    if not folded and old is not None and merged == prev:
        return False
    entry["s"][src] = merged
    if old is None and not folded and key.startswith("mid:"):
        rec["mid_only"] = rec.get("mid_only", 0) + 1
    new = _contrib(entry)
    if old is not None:
        _apply(rec, old, -1)
    _apply(rec, new, +1)
    _burn_touch(rec, key, old, new)
    store.put(key, entry, where)
    return True


def _drop_source(store, rec, src_id):
    """Remove every trace of one source generation (replacement/truncation).
    A full evidence walk — permitted only for this rebuild case (spec D-21)."""
    for key, entry, where in list(store.all_locations()):
        if "s" not in entry or src_id not in entry["s"]:
            continue
        _apply(rec, _contrib(entry), -1)
        del entry["s"][src_id]
        if entry["s"]:
            new = _contrib(entry)
            _apply(rec, new, +1)
            store.put(key, entry, where)
        else:
            store.delete(key, where)
            if key.startswith("mid:"):
                rec["mid_only"] = max(0, rec.get("mid_only", 0) - 1)
    if src_id == "p":
        rec["burn"] = []


def _reprice(store, rec):
    """Recompute every derived index from evidence (registry version change)."""
    rec["tot"] = {"in": 0, "out": 0, "pd": 0}
    rec["rc"], rec["days"], rec["unk_time"] = {}, {}, 0
    for s in rec["src"].values():
        s["tok"], s["pd"] = [0, 0], 0
    for _key, entry, _where in store.all_locations():
        if "s" in entry:
            _apply(rec, _contrib(entry), +1)
    rec["reg"] = _usagelib.REGISTRY_VERSION


# --------------------------------------------------------------------------- scanning
def _stat_key(st):
    return [st.st_size, st.st_mtime_ns, getattr(st, "st_ino", 0) or 0]


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _new_source(kind, locator):
    return {"k": kind, "path": locator, "off": 0, "stat": None, "size": 0, "fp": None,
            "seen": None, "skip": None, "life": "live", "label": None, "label_done": kind == "p",
            "models": [], "tok": [0, 0], "pd": 0, "mt": 0, "unp": 0, "unpp": [], "mal": 0,
            "ovr": 0}


def _reset_source(s):
    keep = {k: s[k] for k in ("k", "path")}
    s.clear()
    s.update(_new_source(keep["k"], keep["path"]))


def _verify(f, s, st_key):
    """True when the stored consumed region is still this file's content."""
    off = s["off"]
    if off == 0 or s["fp"] is None:
        return True
    size = st_key[0]
    if size < off:
        return False
    old = s.get("seen") or [0, 0, 0]
    head_len, head, tail = s["fp"]
    grew_in_place = old[2] == st_key[2] and size > old[0]
    if not grew_in_place:
        f.seek(0)
        if _digest(f.read(head_len)) != head:
            return False
    start = max(0, off - FP_WINDOW)
    f.seek(start)
    return _digest(f.read(off - start)) == tail


class _Scan:
    """Result of scanning one source within a render's remaining budget."""

    def __init__(self):
        self.facts, self.bytes, self.records = [], 0, 0
        self.unp, self.unpp, self.mal, self.ovr = 0, [], 0, 0
        self.label, self.models, self.t0 = None, [], None
        self.stop = "budget"


def _scan(s, f, byte_budget, record_budget, sid_kind):
    """Consume complete records from s["off"] of the open file `f` within the
    budgets. Never advances past bytes it did not consume; an oversized line is
    passed deterministically across renders via the persisted `skip` line start."""
    out = _Scan()
    pos = s["off"]
    consumed_tail = b""
    f.seek(pos)
    while out.bytes < byte_budget and out.records < record_budget:
        if s["skip"] is not None:
            line_start = s["skip"]
            line_tail = b""
            done = False
            while out.bytes < byte_budget:
                chunk = f.read(min(65536, byte_budget - out.bytes))
                if not chunk:
                    break
                out.bytes += len(chunk)
                nl = chunk.find(b"\n")
                if nl < 0:
                    pos += len(chunk)
                    line_tail = (line_tail + chunk)[-_usagelib.TAIL_WINDOW:]
                    continue
                pos += nl + 1
                line_tail = (line_tail + chunk[:nl + 1])[-_usagelib.TAIL_WINDOW:]
                done = True
                break
            if not done:
                s["off"] = pos
                out.stop = "skip"
                break
            want = min(_usagelib.TAIL_WINDOW, pos - line_start)
            if len(line_tail) < want:
                f.seek(pos - want)
                line_tail = f.read(want)
                out.bytes += want
            if _usagelib.usage_bearing(line_tail):
                out.ovr += 1
            s["skip"] = None
            s["off"] = pos
            out.records += 1
            consumed_tail = line_tail[-FP_WINDOW:]
            f.seek(pos)
            continue
        remaining = byte_budget - out.bytes
        limit = min(MAX_RECORD_BYTES, remaining) + 1
        line = f.readline(limit)
        out.bytes += len(line)
        if not line:
            out.stop = "eof"
            break
        if line.endswith(b"\n"):
            pos += len(line)
            out.records += 1
            consumed_tail = (consumed_tail + line)[-FP_WINDOW:]
            _consume(line, pos - len(line), out, s, sid_kind)
            s["off"] = pos
            continue
        if len(line) < limit:
            out.stop = "partial"           # writer-flushed partial line: wait
            break
        if limit - 1 >= MAX_RECORD_BYTES:
            s["skip"] = pos                # oversized: pass it without decoding
            pos += len(line)
            s["off"] = pos
            continue
        break                              # fits the ceiling, not this render's budget
    # Fingerprint the consumed region for replacement detection (spec D-15).
    if s["off"]:
        head_len = min(FP_WINDOW, s["off"])
        if s["fp"] is None or s["fp"][0] < head_len:
            f.seek(0)
            head = _digest(f.read(head_len))
        else:
            head_len, head = s["fp"][0], s["fp"][1]
        want = min(FP_WINDOW, s["off"])
        if len(consumed_tail) < want:
            f.seek(s["off"] - want)
            consumed_tail = f.read(want)
        s["fp"] = [head_len, head, _digest(consumed_tail[-want:])]
    return out


def _consume(line, start, out, s, kind):
    if not s["label_done"] and (b'"role":"user"' in line or b'"role": "user"' in line):
        try:
            o = json.loads(line)
        except ValueError:
            o = None
        msg = o.get("message") if isinstance(o, dict) else None
        if isinstance(msg, dict) and msg.get("role") == "user":
            s["label_done"] = True
            if _sub_label is not None:
                label = safe(_sub_label, msg.get("content"))
                s["label"] = label or None
    if not _usagelib.usage_bearing(line):
        return
    try:
        o = json.loads(line)
    except ValueError:
        out.mal += 1
        return
    n = _usagelib.normalize(o, _local_day)
    if n["kind"] == "ignore":
        return
    if n["kind"] == "malformed":
        out.mal += 1
        return
    if n["id"] is None:
        out.unp += 1
        out.unpp.append(start)
        return
    out.facts.append((n["id"], n["alias"], n["fact"]))
    if kind == "p":
        t = n["fact"]["t"]
        if t is not None and (out.t0 is None or t < out.t0):
            out.t0 = t
    else:
        model = o["message"].get("model")
        if isinstance(model, str) and model.strip() and model not in out.models:
            out.models.append(model.strip())


# --------------------------------------------------------------------------- one render
def _children_dir(tx):
    return os.path.join(os.path.dirname(tx), os.path.splitext(os.path.basename(tx))[0],
                        "subagents")


def _discover(rec, tx):
    """{source id: (path, stat key, mtime)} for the parent and up to
    DISCOVERY_BOUND children, plus whether listing failed / hit the bound."""
    found, failed, bounded = {}, False, False
    try:
        st = os.stat(tx)
        found["p"] = (tx, _stat_key(st), st.st_mtime)
    except OSError:
        pass
    sub = _children_dir(tx)
    count = 0
    try:
        with os.scandir(sub) as it:
            for entry in it:
                if not entry.name.endswith(".jsonl"):
                    continue
                if count >= DISCOVERY_BOUND:
                    bounded = True
                    break
                count += 1
                try:
                    st = entry.stat()
                except OSError:
                    continue
                found["c:" + entry.name] = (entry.path, _stat_key(st), st.st_mtime)
    except FileNotFoundError:
        pass
    except OSError:
        failed = True
    return found, failed, bounded


def _needs_work(s, stat_key):
    """A source needs scanning when it changed since it was last caught up. A
    source with deferred work (budget backlog, or an oversized line in progress)
    never records a caught-up stat, so it always compares unequal."""
    return s["stat"] != stat_key


def _account(store, rec, tx):
    """Scan changed sources within budgets and fold them into the summary."""
    flags = {"list_failed": False, "bound": False, "catching": False}
    if rec["reg"] != _usagelib.REGISTRY_VERSION:
        _reprice(store, rec)
    found, flags["list_failed"], flags["bound"] = _discover(rec, tx)
    for sid_, (path, st_key, mtime) in found.items():
        if sid_ not in rec["src"]:
            rec["src"][sid_] = _new_source("p" if sid_ == "p" else "c",
                                           path if sid_ == "p" else sid_[2:])
        s = rec["src"][sid_]
        s["life"] = "live"
        s["mt"] = mtime
    if not flags["list_failed"]:
        for sid_, s in rec["src"].items():
            if sid_ not in found:
                s["life"] = "gone"
    elif "p" not in found and "p" in rec["src"]:
        rec["src"]["p"]["life"] = "gone"
    work = [k for k, (_p, st_key, _m) in found.items() if _needs_work(rec["src"][k], st_key)]
    children = [k for k in work if k != "p"]
    ordered = _order_sources(children)
    if rec.get("cursor") and ordered:
        after = [k for k in ordered if k > rec["cursor"]]
        ordered = after + [k for k in ordered if k <= rec["cursor"]] if after else ordered
    plan = (["p"] if "p" in work else []) + ordered
    bytes_left, records_left = ACCT_BYTE_BUDGET, ACCT_RECORD_BUDGET
    opened = 0
    for sid_ in plan:
        if opened >= ACCT_SOURCE_BUDGET or bytes_left <= 0 or records_left <= 0:
            break
        path, st_key, _m = found[sid_]
        s = rec["src"][sid_]
        share_b, share_r = bytes_left, records_left
        if sid_ == "p" and children:
            share_b, share_r = max(1, bytes_left // 2), max(1, records_left // 2)
        opened += 1
        try:
            with open(path, "rb") as f:          # one handle: verify, then scan
                if not _verify(f, s, st_key):
                    _drop_source(store, rec, sid_)
                    _reset_source(s)
                result = _scan(s, f, share_b, share_r, s["k"])
        except OSError:
            continue
        bytes_left -= result.bytes
        records_left -= result.records
        for key, alias, fact in result.facts:
            _ingest(store, rec, sid_, key, alias, fact)
            store.evict()
        s["unp"] += result.unp
        s["unpp"] = (s["unpp"] + result.unpp)[-UNPROVEN_KEEP:]
        s["mal"] += result.mal
        s["ovr"] += result.ovr
        for m in result.models:
            if m not in s["models"] and len(s["models"]) < 3:
                s["models"].append(m)
        if result.t0 is not None and (rec.get("t0") is None or result.t0 < rec["t0"]):
            rec["t0"] = result.t0
        s["size"] = st_key[0]
        s["seen"] = st_key
        caught_up = s["skip"] is None and (result.stop in ("eof", "partial")
                                           or s["off"] >= st_key[0])
        s["stat"] = st_key if caught_up else None
        if sid_ != "p":
            rec["cursor"] = sid_
    for sid_, (_p, st_key, _m) in found.items():
        if _needs_work(rec["src"][sid_], st_key):
            flags["catching"] = True
    return flags


def _session_reasons(rec, flags):
    reasons = set(rec["rc"])
    srcs = rec["src"].values()
    if any(s["unp"] for s in srcs):
        reasons.add("unproven_identity")
    if any(s["mal"] for s in srcs):
        reasons.add("malformed_record")
    if any(s["ovr"] for s in srcs):
        reasons.add("oversized_record")
    if flags.get("bound"):
        reasons.add("discovery_bound")
    if any(s["life"] == "gone" and (s["stat"] is None or s["skip"] is not None)
           for s in srcs):
        reasons.add("source_vanished_with_backlog")
    return reasons


def _session_state(rec, flags, reasons, has_parent):
    if not has_parent and not rec["src"]:
        return "unavailable"
    if flags.get("catching") or flags.get("list_failed"):
        return "catching_up"
    return "partial" if reasons else "complete"


def _update_host(rec, data):
    host = rec["host"]
    v = get(data, "cost", "total_cost_usd") if isinstance(data, dict) else None
    valid = (isinstance(v, (int, float)) and not isinstance(v, bool)
             and math.isfinite(v) and v >= 0)
    if valid:
        v = float(v)
        host["latest"] = v
        host["max"] = v if host["max"] is None else max(host["max"], v)
        host["anom"] = v < host["max"]
        host["missing"] = False
        host["seen"] = True
    elif host["seen"]:
        host["missing"] = True


def _usd(pd):
    return pd / 1e12


def _scope(totals, state, reasons, stale):
    return {"in": float(totals["in"]), "out": float(totals["out"]), "pd": int(totals["pd"]),
            "cost": _usd(totals["pd"]), "state": state, "reasons": sorted(reasons),
            "stale": stale}


def _unavailable(stale=False):
    out = _scope({"in": 0, "out": 0, "pd": 0}, "unavailable", (), stale)
    out.update(host=None, host_delta=None)
    return out


def _session_output(rec, stale):
    cov = rec.get("cov") or {}
    out = _scope(rec["tot"], cov.get("state", "unavailable"), cov.get("reasons", []), stale)
    out["host"] = rec["host"].get("max")
    out["host_delta"] = None
    if out["state"] == "complete" and out["host"] is not None:
        out["host_delta"] = out["host"] - out["cost"]
    return out


def _today_output(path, sid, rec, stale, prune):
    """Today across every live session's COMPACT summary (never its evidence)."""
    today = _today()
    now = time.time()
    totals = {"in": 0, "out": 0, "pd": 0}
    reasons, catching, any_data = set(), False, False
    own_key = _session_key(sid)
    summaries = []
    if rec is not None:
        summaries.append(rec)
    directory = _session_dir(path)
    try:
        names = os.listdir(directory)
    except OSError:
        names = []
    acct_keys = {n[:-10] for n in names if n.endswith(".acct.json")}
    for name in names:
        full = os.path.join(directory, name)
        if name.endswith(".acct.json"):
            if name[:-10] == own_key:
                continue
            payload = _read_json(full)
            other = payload.get("rec") if isinstance(payload, dict) else None
            if not (isinstance(other, dict) and _summary_valid(other, payload.get("sid"))):
                if prune:
                    _remove(full)
                continue
            if now - num(other.get("last_ts")) > SESSION_TTL:
                if prune:
                    _prune_session(path, name[:-10])
                continue
            summaries.append(other)
        elif _LEGACY_SHARD.match(name) and name[:-5] != own_key:
            try:
                mtime = os.stat(full).st_mtime
            except OSError:
                continue
            if now - mtime > SESSION_TTL:
                if prune:
                    _remove(full)
                    if name[:-5] not in acct_keys:
                        _remove(os.path.join(directory, name[:-5] + ".start.json"))
            elif now - mtime <= 86400 and name[:-5] not in acct_keys:
                reasons.add("unmigrated_session")
    for s in summaries:
        bucket = s["days"].get(today)
        cov = s.get("cov") or {}
        active = bucket is not None or s.get("last_day") == today
        if bucket:
            any_data = True
            totals["in"] += bucket["in"]
            totals["out"] += bucket["out"]
            totals["pd"] += bucket["pd"]
            reasons.update(bucket["rc"])
        if active:
            if s.get("unk_time"):
                reasons.add("unknown_event_time")
            reasons.update(cov.get("src_reasons", []))
            if cov.get("state") == "catching_up":
                catching = True
    if catching:
        state = "catching_up"
    elif reasons:
        state = "partial"
    elif rec is None and not any_data:
        state = "unavailable"
    else:
        state = "complete"
    return _scope(totals, state, reasons, stale)


def _prune_session(path, key):
    directory = _session_dir(path)
    for suffix in (".acct.json", ".hot.json", ".start.json", ".json"):
        _remove(os.path.join(directory, key + suffix))
    shutil.rmtree(os.path.join(directory, key + ".ev"), ignore_errors=True)


def _load_summary(path, sid):
    payload = _read_json(_acct_file(path, sid))
    if (isinstance(payload, dict) and payload.get("schema") == ACCT_SCHEMA
            and payload.get("sid") == sid and isinstance(payload.get("rec"), dict)
            and _summary_valid(payload["rec"], sid)):
        return payload["rec"]
    return None


def _seed_summary(path, sid, now, keep=None):
    """A fresh summary; carries session metadata over from a discarded v2 summary
    (`keep`) or, once, from the legacy v1 shard — never its cost (spec D-16)."""
    rec = _fresh_summary(sid, now)
    if keep:
        for k in ("first_ts", "sess_start", "t0"):
            if keep.get(k) is not None:
                rec[k] = keep[k]
        if isinstance(keep.get("host"), dict):
            rec["host"] = keep["host"]
        return rec
    legacy = _read_json(_session_file(path, sid))
    old = legacy.get("rec") if isinstance(legacy, dict) else None
    if isinstance(old, dict):
        first = num(old.get("first_ts"), None)
        if first is not None and math.isfinite(first) and 0 < first <= now:
            rec["first_ts"] = first
        hc = old.get("host_cost")
        if isinstance(hc, (int, float)) and not isinstance(hc, bool) and math.isfinite(hc) and hc > 0:
            rec["host"].update(max=float(hc), seen=True)
    return rec


def _discard_evidence(path, sid):
    _remove(_hot_file(path, sid))
    shutil.rmtree(_ev_dir(path, sid), ignore_errors=True)


def ledger_update(data, sid):
    """One render's accounting: returns (summary, session, today). Session/today
    carry in/out tokens, exact picodollars (`pd`), display `cost`, a coverage
    `state` (complete | catching_up | partial | unavailable), `reasons`, and
    `stale` (True when this render could not take the lock and is showing the
    last committed snapshot instead — never fabricated zeros)."""
    if not sid:
        return {}, _unavailable(), _unavailable()
    path = ledger_path()
    lock = _acquire_lock(path, UI_LOCK_WAIT)
    if lock is None:
        return _stale_view(path, sid)
    try:
        return _ledger_update_unlocked(data, sid, path)
    finally:
        _release_lock(lock)


def _stale_view(path, sid):
    rec = _load_summary(path, sid)
    if rec is None:
        return {}, _unavailable(stale=True), _unavailable(stale=True)
    return rec, _session_output(rec, True), _today_output(path, sid, rec, True, prune=False)


def _ledger_update_unlocked(data, sid, path):
    now = time.time()
    tx = data.get("transcript_path") if isinstance(data, dict) else None
    tx = tx if isinstance(tx, str) and tx else None
    rec = _load_summary(path, sid)
    on_disk = json.dumps(rec, sort_keys=True) if rec is not None else None
    if rec is None:
        stale_disk = os.path.exists(_acct_file(path, sid))
        _discard_evidence(path, sid)
        if stale_disk:
            _remove(_acct_file(path, sid))
        rec = _seed_summary(path, sid, now)
    if "sess_start" not in rec:
        start = _read_json(_start_file(path, sid))
        value = num(start.get("sess_start"), None) if isinstance(start, dict) else None
        if value is not None and math.isfinite(value):
            rec["sess_start"] = float(value)
    if tx and rec.get("ppath") not in (None, tx):
        _discard_evidence(path, sid)
        rec = _seed_summary(path, sid, now, keep=rec)
    _update_host(rec, data)
    flags = {"catching": False, "list_failed": False, "bound": False}
    store = _Store(path, sid, rec)
    if tx:
        rec["ppath"] = tx
        try:
            flags = _account(store, rec, tx)
        except _Inconsistent:
            _discard_evidence(path, sid)
            rec = _seed_summary(path, sid, now, keep=rec)
            rec["ppath"] = tx
            store = _Store(path, sid, rec)
            flags = _account(store, rec, tx)
    reasons = _session_reasons(rec, flags)
    state = _session_state(rec, flags, reasons, tx is not None)
    src_reasons = sorted(r for r in reasons if r not in rec["rc"])
    rec["cov"] = {"state": state, "reasons": sorted(reasons), "src_reasons": src_reasons}
    if rec["days"].get(_today()) is not None or rec.get("last_day") is None:
        rec["last_day"] = _today()
    changed = on_disk is None or json.dumps(rec, sort_keys=True) != on_disk
    if changed or now - num(rec.get("last_ts")) >= LEDGER_HEARTBEAT:
        rec["last_ts"] = now
        seq = rec["seq"] + 1
        if store.flush(seq):
            rec["seq"] = seq
            if _atomic_json(_acct_file(path, sid), {"schema": ACCT_SCHEMA, "sid": sid,
                                                    "seq": seq, "rec": rec}):
                for obsolete in store.obsolete:
                    _remove(obsolete)
    return rec, _session_output(rec, False), _today_output(path, sid, rec, False, prune=True)


def persist_sess_start(sid, value):
    """Write a resolved wall-clock session-start epoch beside the session's ledger
    summary so later renders read it instead of re-scanning the host's session
    metadata directory. Best-effort and idempotent; never breaks a render.
    Returns True iff the start file was written."""
    if not sid or not value:
        return False
    path = ledger_path()
    lock = _acquire_lock(path)
    if lock is None:
        return False
    try:
        return _persist_sess_start_unlocked(sid, value, path)
    finally:
        _release_lock(lock)


def _persist_sess_start_unlocked(sid, value, path):
    rec = _load_summary(path, sid)
    if rec is None:
        return False
    if num(rec.get("sess_start"), None) == float(value):
        return False
    current = _read_json(_start_file(path, sid))
    if isinstance(current, dict) and num(current.get("sess_start"), None) == float(value):
        return False
    # Its own file, so it can never overwrite a concurrently refreshed summary.
    return _atomic_json(_start_file(path, sid), {"sid": sid, "sess_start": float(value)})


# --------------------------------------------------------------------------- Pi usage ledger
def pi_ledger_path():
    """Return Pi's separate user-global usage ledger anchor.

    This path is fixed: runtime environment cannot redirect Pi accounting into
    Claude's `ledger.json` schema or session namespace. Tests inject an explicit
    isolated anchor through `pi_ledger_update(..., path=...)` instead.
    """
    return os.path.join(
        os.path.expanduser("~"), ".codearbiter", "pi-usage-ledger.json"
    )


def pi_blank_totals():
    """Fresh bounded empty Pi totals for fail-soft results."""
    return {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "costUsd": 0.0,
    }


def _pi_result(status, session=None, today=None, high_water=-1,
               accepted_through=-1):
    """Return durable state plus a distinct acknowledgment for this call."""
    if status not in PI_STATUSES:
        status = "corrupt"
    return {
        "status": status,
        "session": dict(session) if isinstance(session, dict) else pi_blank_totals(),
        "today": dict(today) if isinstance(today, dict) else pi_blank_totals(),
        "acceptedThrough": accepted_through if type(accepted_through) is int else -1,
        "highWater": high_water if type(high_water) is int else -1,
    }


def _pi_session_file(path, session_key):
    """A validated digest is both the bounded identity and safe shard basename."""
    return os.path.join(f"{path}.sessions", f"{session_key}.json")


def _pi_canonical_path(path):
    """Resolve symlinks/junctions in the existing prefix of a future path."""
    if not isinstance(path, str) or not path or len(path) > PI_MAX_PATH_CHARS \
            or path != path.strip() \
            or any(ord(char) < 32 or ord(char) == 127 for char in path):
        return None
    try:
        absolute = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
    except (OSError, TypeError, ValueError):
        return None
    if len(absolute) > PI_MAX_PATH_CHARS:
        return None
    probe = absolute
    suffix = []
    try:
        while not os.path.lexists(probe):
            parent, name = os.path.split(probe)
            if not name or parent == probe:
                return None
            suffix.append(name)
            probe = parent
        if suffix and not os.path.isdir(probe):
            return None
        resolved = os.path.realpath(probe)
    except (OSError, TypeError, ValueError):
        return None
    for name in reversed(suffix):
        resolved = os.path.join(resolved, name)
    return os.path.normcase(os.path.normpath(resolved))


def _pi_paths_overlap(left, right):
    try:
        common = os.path.commonpath((left, right))
    except (OSError, TypeError, ValueError):
        return False
    return common == left or common == right


def _pi_resolve_path(path):
    """Return an isolated canonical Pi anchor, or None before lock/write."""
    explicit = path is not None
    candidate = pi_ledger_path() if path is None else path
    if explicit and (not isinstance(candidate, str) or not os.path.isabs(candidate)):
        return None
    try:
        if os.path.isdir(candidate):
            return None
    except (OSError, TypeError, ValueError):
        return None
    pi_anchor = _pi_canonical_path(candidate)
    pi_sessions = _pi_canonical_path(f"{candidate}.sessions") \
        if isinstance(candidate, str) else None
    pi_lock = _pi_canonical_path(f"{candidate}.lock") \
        if isinstance(candidate, str) else None
    claude = ledger_path()
    claude_anchor = _pi_canonical_path(claude)
    claude_sessions = _pi_canonical_path(f"{claude}.sessions") \
        if isinstance(claude, str) else None
    claude_lock = _pi_canonical_path(f"{claude}.lock") \
        if isinstance(claude, str) else None
    if None in (
            pi_anchor, pi_sessions, pi_lock,
            claude_anchor, claude_sessions, claude_lock):
        return None
    if any(_pi_paths_overlap(pi_path, claude_path)
           for pi_path in (pi_anchor, pi_sessions, pi_lock)
           for claude_path in (claude_anchor, claude_sessions, claude_lock)):
        return None
    return pi_anchor


def _pi_timestamp_day(value):
    if not isinstance(value, str) or not value or len(value) > PI_MAX_TIMESTAMP_CHARS:
        return None
    if value != value.strip() \
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        return None
    source = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(source)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        local = parsed.astimezone()
    except (OSError, OverflowError, ValueError):
        return None
    if not PI_MIN_YEAR <= parsed.year <= PI_MAX_YEAR \
            or not PI_MIN_YEAR <= local.year <= PI_MAX_YEAR:
        return None
    return local.date().isoformat()


def _pi_token(value):
    return type(value) is int and 0 <= value <= PI_MAX_TOKENS


def _pi_cost(value):
    if type(value) is int:
        return 0 <= value <= PI_MAX_COST_USD
    return type(value) is float and math.isfinite(value) \
        and 0 <= value <= PI_MAX_COST_USD


def _pi_totals_valid(value):
    return isinstance(value, dict) and set(value) == PI_TOTAL_KEYS \
        and all(_pi_token(value[key]) for key in PI_TOTAL_KEYS if key != "costUsd") \
        and _pi_cost(value["costUsd"])


def _pi_day_valid(value):
    if not isinstance(value, str) or PI_DAY_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return PI_MIN_YEAR <= parsed.year <= PI_MAX_YEAR


def _pi_updated_at(value):
    return type(value) is int and 0 <= value <= PI_MAX_UPDATED_AT


def _pi_now():
    try:
        return max(0, min(PI_MAX_UPDATED_AT, int(time.time())))
    except (OverflowError, TypeError, ValueError):
        return 0


def _pi_normalize_chunk(session_key, scan_start, scan_end, facts):
    """Validate the entire boundary before any lock or filesystem operation."""
    if not isinstance(session_key, str) \
            or PI_SESSION_KEY_RE.fullmatch(session_key) is None \
            or type(scan_start) is not int or type(scan_end) is not int \
            or not 0 <= scan_start <= scan_end <= PI_MAX_POSITION \
            or scan_end - scan_start + 1 > PI_MAX_SCAN_ENTRIES \
            or not isinstance(facts, list) or len(facts) > PI_MAX_SCAN_ENTRIES:
        return None
    normalized = []
    previous = -1
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != PI_FACT_KEYS:
            return None
        position = fact["position"]
        if type(position) is not int or not 0 <= position <= PI_MAX_POSITION \
                or not scan_start <= position <= scan_end or position <= previous:
            return None
        day = _pi_timestamp_day(fact["timestamp"])
        totals = {key: fact[key] for key in PI_TOTAL_KEYS}
        if day is None or not _pi_totals_valid(totals):
            return None
        totals["costUsd"] = round(float(totals["costUsd"]), 9)
        normalized.append((position, day, totals))
        previous = position
    return normalized


def _pi_add_totals(left, right):
    if not _pi_totals_valid(left) or not _pi_totals_valid(right):
        return None
    output = {}
    for key in PI_TOTAL_KEYS:
        if key == "costUsd":
            total = round(float(left[key]) + float(right[key]), 9)
            if not _pi_cost(total):
                return None
        else:
            total = left[key] + right[key]
            if not _pi_token(total):
                return None
        output[key] = total
    return output


def _pi_shard_valid(value, session_key):
    if not isinstance(value, dict) or set(value) != {
            "schema", "sessionKey", "highWater", "updatedAt", "totals", "days"}:
        return False
    high_water = value.get("highWater")
    days = value.get("days")
    return value.get("schema") == PI_SESSION_SCHEMA \
        and value.get("sessionKey") == session_key \
        and type(high_water) is int and -1 <= high_water <= PI_MAX_POSITION \
        and _pi_updated_at(value.get("updatedAt")) \
        and _pi_totals_valid(value.get("totals")) \
        and isinstance(days, dict) and len(days) <= PI_MAX_DAYS \
        and all(_pi_day_valid(day) and _pi_totals_valid(totals)
                for day, totals in days.items())


def _pi_file_kind(path):
    """Classify a path without following links or opening special objects."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "error"
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    if not stat.S_ISREG(info.st_mode) \
            or getattr(info, "st_file_attributes", 0) & reparse_flag:
        return "special"
    return "regular"


def _pi_read_shard(path, session_key):
    kind = _pi_file_kind(path)
    if kind == "missing":
        return None, "missing"
    if kind != "regular":
        return None, "corrupt"
    try:
        with open(path, "rb") as stream:
            raw = stream.read(PI_MAX_SHARD_BYTES + 1)
    except OSError:
        return None, "corrupt"
    if len(raw) > PI_MAX_SHARD_BYTES:
        return None, "corrupt"
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, "corrupt"
    if not _pi_shard_valid(value, session_key):
        return None, "corrupt"
    return value, "ok"


def _pi_apply_facts(shard, facts, scan_end):
    """Return a new shard, or None if bounded cumulative state would overflow."""
    updated = {
        "schema": shard["schema"],
        "sessionKey": shard["sessionKey"],
        "highWater": shard["highWater"],
        "updatedAt": shard["updatedAt"],
        "totals": dict(shard["totals"]),
        "days": {day: dict(totals) for day, totals in shard["days"].items()},
    }
    for position, day, totals in facts:
        if position <= updated["highWater"]:
            continue
        session = _pi_add_totals(updated["totals"], totals)
        day_totals = _pi_add_totals(updated["days"].get(day, pi_blank_totals()), totals)
        if session is None or day_totals is None:
            return None
        updated["totals"] = session
        updated["days"][day] = day_totals
        while len(updated["days"]) > PI_MAX_DAYS:
            del updated["days"][min(updated["days"])]
    updated["highWater"] = scan_end
    return updated


def _pi_collect_shards(path):
    """Return valid regular Pi shards only; unrelated/temp entries are ignored."""
    directory = f"{path}.sessions"
    shards = []
    corrupt = False
    try:
        with os.scandir(directory) as entries:
            recognized = 0
            for entry in entries:
                match = PI_SHARD_NAME_RE.fullmatch(entry.name)
                if match is None:
                    continue
                recognized += 1
                if recognized > PI_MAX_DIRECTORY_ENTRIES:
                    return [], True
                kind = _pi_file_kind(entry.path)
                if kind in {"missing", "special"}:
                    continue
                if kind != "regular":
                    corrupt = True
                    continue
                session_key = match.group(1)
                shard, state = _pi_read_shard(entry.path, session_key)
                if state != "ok":
                    corrupt = True
                    continue
                shards.append((entry.path, shard))
    except FileNotFoundError:
        return [], False
    except OSError:
        return [], True
    return shards, corrupt


def _pi_retain_shards(path, current_key):
    """Prune valid shards deterministically, always retaining the current shard."""
    shards, corrupt = _pi_collect_shards(path)
    ranked = sorted(
        shards,
        key=lambda item: (
            0 if item[1]["sessionKey"] == current_key else 1,
            -item[1]["updatedAt"],
            item[1]["sessionKey"],
        ),
    )
    write_failed = False
    for shard_path, _shard in ranked[max(1, PI_MAX_SHARDS):]:
        try:
            os.remove(shard_path)
        except OSError:
            write_failed = True
    retained, after_corrupt = _pi_collect_shards(path)
    return retained, corrupt or after_corrupt, write_failed


def _pi_today_from_shards(path, today, current_key):
    """Retain, reload, then sum today's authoritative fixed totals."""
    shards, corrupt, write_failed = _pi_retain_shards(path, current_key)
    total = pi_blank_totals()
    for _shard_path, shard in shards:
        day_totals = shard["days"].get(today)
        if day_totals is None:
            continue
        added = _pi_add_totals(total, day_totals)
        if added is None:
            corrupt = True
            continue
        total = added
    return total, corrupt, write_failed


def _write_pi_snapshot(path, today_date, today):
    """Atomically refresh Pi's bounded root readability cache."""
    try:
        return _atomic_json(path, {
            "schema": PI_LEDGER_SCHEMA, "date": today_date, "today": today,
        })
    except Exception:  # noqa: BLE001 - cache failures have one fixed status
        return False


def _pi_finish_update(path, shard, current_key, accepted_through):
    """Prune, aggregate, cache, and shape one new-or-replayed result."""
    today_date = datetime.now().astimezone().date().isoformat()
    today, aggregate_corrupt, retain_failed = _pi_today_from_shards(
        path, today_date, current_key
    )
    status = "write_failed" if retain_failed else (
        "corrupt" if aggregate_corrupt else "ok"
    )
    if status == "ok" and not _write_pi_snapshot(path, today_date, today):
        status = "write_failed"
    return _pi_result(
        status,
        shard["totals"],
        today,
        shard["highWater"],
        accepted_through if status == "ok" else -1,
    )


def pi_ledger_update(session_key, scan_start, scan_end, facts, path=None):
    """Add one bounded, sorted Pi usage-fact chunk and return session/day totals.

    `scan_start..scan_end` acknowledges one contiguous bounded slice of the raw
    append-only Pi session-entry array. Usage facts are sparse within that range
    because non-assistant entries are omitted. A successful atomic shard replace
    advances the cursor to `scan_end`, including for an empty fact list. No
    message, path, command, environment, output, or raw session identity is
    accepted or persisted.
    """
    normalized = _pi_normalize_chunk(session_key, scan_start, scan_end, facts)
    if normalized is None:
        return _pi_result("invalid")
    path = _pi_resolve_path(path)
    if path is None:
        return _pi_result("invalid")
    try:
        lock = _acquire_lock(path)
    except Exception:  # noqa: BLE001 - lock/path failures are a fixed fail-soft status
        return _pi_result("lock_failed")
    if lock is None:
        return _pi_result("lock_failed")
    try:
        return _pi_ledger_update_unlocked(
            path, session_key, scan_start, scan_end, normalized
        )
    except Exception:  # noqa: BLE001 - a footer usage snapshot is always fail-soft
        return _pi_result("corrupt")
    finally:
        _release_lock(lock)


def _pi_ledger_update_unlocked(path, session_key, scan_start, scan_end, facts):
    shard_path = _pi_session_file(path, session_key)
    shard, state = _pi_read_shard(shard_path, session_key)
    if state == "corrupt":
        return _pi_result("corrupt")
    if state == "missing":
        shard = {
            "schema": PI_SESSION_SCHEMA,
            "sessionKey": session_key,
            "highWater": -1,
            "updatedAt": 0,
            "totals": pi_blank_totals(),
            "days": {},
        }
    if scan_end <= shard["highWater"]:
        return _pi_finish_update(path, shard, session_key, scan_end)
    if scan_start != shard["highWater"] + 1:
        return _pi_result("invalid")
    updated = _pi_apply_facts(shard, facts, scan_end)
    if updated is None:
        return _pi_result("invalid")
    updated["updatedAt"] = _pi_now()
    if state == "missing" or updated != shard:
        if not _atomic_json(shard_path, updated):
            return _pi_result("write_failed")
    return _pi_finish_update(path, updated, session_key, scan_end)


def burn_samples(rec):
    """Recent per-request token-burn values (most-recent window) for the sparkline:
    one sample per accepted PARENT request (spec AC-24), not a time-extrapolated
    estimate. Returns [] when there is too little data to draw a line. The
    statusline turns this list into a colored sparkline; this lib stays render-free."""
    out = []
    for item in (rec.get("burn") or []) if isinstance(rec, dict) else []:
        v = item[1] if isinstance(item, list) and len(item) == 2 else item
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
    return out[-24:] if len(out) >= 2 else []
