#!/usr/bin/env python3
# codeArbiter — cost/token ledger subsystem for the statusline (extracted T-12).
#
# Owns the user-level token/cost accounting the statusline renders: an Anthropic
# API price table, transcript-tailing accumulation (deduped per requestId), the
# per-session JSON ledger (~/.codearbiter/ledger.json) with TTL pruning + an
# atomic write, and the per-call burn samples that feed the sparkline. The
# statusline imports this for its cost segment; it carries NO rendering concern
# (no ANSI, no box drawing) so the accounting is unit-testable in isolation.
#
# Design principles (mirroring _metricslib.py / _taskboardlib.py):
#   - Stdlib only; no third-party imports ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O.
#   - Pure functions are fully testable with synthetic input. ledger_update() is
#     the only function that touches the filesystem (read-modify-write the ledger
#     + tail the transcript); everything else is pure.
#   - Never raise on malformed user input — every reader degrades to safe blanks.
#
# Public API:
#   price_for(model) -> tuple                (input,out,c5,c1,cr) USD per 1M tokens
#   api_cost(tok) -> float                   estimated API-equivalent USD for {model: tokens}
#   ledger_path() -> str                     resolved ledger file path (env-overridable)
#   _tx_accumulate(rec, tx_path) -> bool     tail a transcript into rec; True if offset advanced
#   _agg_reqs(reqs, only=None) -> dict       aggregate per-request map -> {model: tokens}
#   _totals(models) -> dict                  {in,out,cost} display totals for a model map
#   ledger_update(data, sid) -> tuple        (rec, session_totals, today_totals)
#   burn_samples(rec) -> list[float]         recent per-call token-burn values for the sparkline

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

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

# Tunables (module constants; mirrored from the original inline statusline block).
SESSION_TTL = 36 * 3600  # prune sessions older than ~1.5 days
BURN_RING = 40           # recent per-call token-burn samples kept for the sparkline
TX_MAX_NEW_LINES = 20000 # hot-path bound: transcript lines parsed per render

# API list prices, USD per 1M tokens (captured 2026-06-10 from Anthropic's
# pricing pages). Used ONLY to estimate the pay-as-you-go API-equivalent cost of
# this session's REAL tokens — the bar labels it "api≈"; it is not a bill.
# Per model family: (input, output, cache_write_5m, cache_write_1h, cache_read).
# Cache multipliers are the standard ones: write 1.25x/2x input, read 0.1x.
API_PRICES = {
    "fable":  (10.0, 50.0, 12.50, 20.0, 1.00),
    "opus":   (5.0, 25.0, 6.25, 10.0, 0.50),
    "sonnet": (3.0, 15.0, 3.75,  6.0, 0.30),
    "haiku":  (1.0,  5.0, 1.25,  2.0, 0.10),
}


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


def parse_iso(s):
    """Parse an ISO-8601 timestamp (tolerating a trailing Z) to epoch seconds."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)   # naive timestamps are UTC, not local
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- pricing
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


# --------------------------------------------------------------------------- ledger
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


def _session_dir(path):
    return f"{path}.sessions"


def _session_key(sid):
    return hashlib.sha256(str(sid).encode("utf-8", "replace")).hexdigest()


def _session_file(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.json")


def _start_file(path, sid):
    return os.path.join(_session_dir(path), f"{_session_key(sid)}.start.json")


def _load_sessions(path):
    """Merge the legacy snapshot with authoritative independently-written shards."""
    led = _read_json(path, {})
    legacy = led.get("sessions") if isinstance(led, dict) else None
    sessions = dict(legacy) if isinstance(legacy, dict) else {}
    directory = _session_dir(path)
    try:
        names = os.listdir(directory)
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json") or name.endswith(".start.json"):
            continue
        enumerated = os.path.join(directory, name)
        item = _read_json(enumerated)
        if not isinstance(item, dict) or not isinstance(item.get("rec"), dict):
            try:
                os.remove(enumerated)
            except OSError:
                pass
            continue
        sid = str(item.get("sid"))
        if os.path.basename(_session_file(path, sid)) != name:
            try:
                os.remove(enumerated)
            except OSError:
                pass
            continue
        rec = item["rec"]
        if time.time() - num(rec.get("last_ts")) > SESSION_TTL:
            for stale in (enumerated, _start_file(path, sid)):
                try:
                    os.remove(stale)
                except OSError:
                    pass
            sessions.pop(sid, None)
            continue
        sessions[sid] = rec
    for name in names:
        if not name.endswith(".start.json"):
            continue
        enumerated = os.path.join(directory, name)
        item = _read_json(enumerated)
        if not isinstance(item, dict):
            try:
                os.remove(enumerated)
            except OSError:
                pass
            continue
        sid = str(item.get("sid"))
        start = num(item.get("sess_start"), None)
        valid_name = os.path.basename(_start_file(path, sid)) == name
        if valid_name and sid in sessions and start is not None:
            sessions[sid]["sess_start"] = float(start)
        else:
            try:
                os.remove(enumerated)
            except OSError:
                pass
    now = time.time()
    sessions = {sid: rec for sid, rec in sessions.items()
                if isinstance(rec, dict)
                and now - num(rec.get("last_ts")) <= SESSION_TTL}
    return sessions


def _write_snapshot(path, sessions):
    return _atomic_json(path, {"sessions": sessions})


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
    """Tail the session transcript JSONL from the stored byte offset, UPSERTING each
    assistant message's usage into a per-requestId dedup map (the transcript logs a
    single API call several times via streaming/replay; counting each request once
    is what keeps tokens AND cost honest) and pushing a per-call burn sample. Append-
    only -> O(new lines)/render. Returns True if the offset advanced."""
    if not tx_path or not os.path.isfile(tx_path):
        return False
    try:
        size = os.path.getsize(tx_path)
    except OSError:
        return False
    if not isinstance(rec.get("reqs"), dict):
        rec["reqs"] = {}          # fresh record, or migrating from an earlier schema
        rec["tx_off"] = 0
        rec.pop("days", None)
        rec.pop("tok", None)
    if not isinstance(rec.get("burn"), list):
        rec["burn"] = []
    off = int(num(rec.get("tx_off")))
    # New transcript for this session, or truncation/rotation -> reparse from start.
    if rec.get("tx_path") != tx_path or off > size:
        off, rec["reqs"], rec["burn"], rec["tx_path"] = 0, {}, [], tx_path
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
        ts = o.get("timestamp")
        e = parse_iso(ts) if isinstance(ts, str) else None
        if e is not None:                       # earliest message ts = true session start
            t0 = rec.get("t0")
            if not isinstance(t0, (int, float)) or e < t0:
                rec["t0"] = e
        # Dedupe by requestId: the transcript logs each API call multiple times
        # (streaming/replay), so UPSERT each request's final usage exactly once
        # instead of summing every line, which 2-3x over-counts BOTH tokens and cost.
        key = o.get("requestId") or m.get("id") or f"_p{int(off) + parsed}"
        is_new = key not in rec["reqs"]
        rec["reqs"][key] = {"d": _msg_date(ts), "m": model,
                            "in": i, "cr": cr, "c5": c5, "c1": c1, "out": out}
        if is_new:
            rec["burn"].append(i + c5 + c1 + out)   # fresh input + output (cache reads excluded)
    if len(rec["burn"]) > BURN_RING:
        rec["burn"] = rec["burn"][-BURN_RING:]
    rec["tx_off"] = new_off
    return True


def _agg_reqs(reqs, only=None):
    """Aggregate the per-request dedup map into {model: tokens}; if `only` is a
    date, include just that local-calendar-day's requests (for the Today totals)."""
    out = {}
    for r in (reqs or {}).values():
        if not isinstance(r, dict):
            continue
        if only is not None and r.get("d") != only:
            continue
        o = out.setdefault(r.get("m") or "?",
                           {"in": 0.0, "cr": 0.0, "c5": 0.0, "c1": 0.0, "out": 0.0})
        for k in o:
            o[k] += num(r.get(k))
    return out


def _totals(models):
    """Display totals + API-equivalent cost for a model map. The displayed "in" is
    FRESH input (uncached input + cache writes) — cache READS are excluded from the
    token count (they re-serve already-sent context every turn and would inflate it
    30-100x), but they ARE still priced into the cost via api_cost()."""
    tin = tout = 0.0
    for t in (models or {}).values():
        if isinstance(t, dict):
            tin += num(t.get("in")) + num(t.get("c5")) + num(t.get("c1"))
            tout += num(t.get("out"))
    return {"in": tin, "out": tout, "cost": api_cost(models)}


def ledger_update(data, sid):
    blank = {"in": 0.0, "out": 0.0, "cost": 0.0}
    if not sid:
        return {}, dict(blank), dict(blank)
    path = ledger_path()
    lock = _acquire_lock(path)
    if lock is None:
        return {}, dict(blank), dict(blank)
    try:
        return _ledger_update_unlocked(data, sid, path)
    finally:
        _release_lock(lock)


def _ledger_update_unlocked(data, sid, path):
    """Read-modify-write the per-session ledger. Accumulate the session's TRUE token
    COUNTS by tailing its transcript (deduped per requestId), take the COST from the
    host's cost.total_cost_usd, and return (session record, this-session totals,
    today's totals across sessions). Best-effort; safe blanks on any failure."""
    blank = {"in": 0.0, "out": 0.0, "cost": 0.0}
    now = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    sessions = _load_sessions(path)

    rec = sessions.get(sid)
    dirty = not isinstance(rec, dict)
    if dirty:
        rec = {}
    rec.setdefault("first_ts", now)
    rec["last_ts"] = now
    rec["last_day"] = today
    rec["host_cost"] = num(get(data, "cost", "total_cost_usd"))

    tx = data.get("transcript_path") if isinstance(data, dict) else None
    if safe(_tx_accumulate, rec, tx):
        dirty = True
    sess = _totals(_agg_reqs(rec.get("reqs")))             # tokens: this session, all requests (deduped)
    # Cost = Claude Code's authoritative cost.total_cost_usd — it already prices every
    # call (including subagents in separate transcripts) exactly as your bill does, so
    # it is far more accurate than recomputing tokens*price. api_cost is fallback only.
    if rec["host_cost"] > 0:
        sess["cost"] = rec["host_cost"]
    rec["today"] = dict(_totals(_agg_reqs(rec.get("reqs"), only=today)), date=today)
    rec.pop("tot", None)                    # retire the batch-1 whole-session cache key
    sessions[sid] = rec

    for k in list(sessions.keys()):
        v = sessions[k]
        if not isinstance(v, dict) or now - num(v.get("last_ts")) > SESSION_TTL:
            del sessions[k]
            dirty = True
    # Each session owns one independently replaced shard. A writer for another
    # session therefore cannot replace this record with an older snapshot.
    _atomic_json(_session_file(path, sid), {"sid": sid, "rec": rec})
    sessions = _load_sessions(path)
    _write_snapshot(path, sessions)  # compatibility/readability cache; shards are truth

    # Today = each session's TODAY bucket (tokens whose transcript timestamp falls
    # on the current local day), summed across sessions — not whole-session totals.
    day = dict(blank)
    for v in sessions.values():
        if not isinstance(v, dict):
            continue
        t = v.get("today") if isinstance(v.get("today"), dict) else None
        if t and t.get("date") == today:            # tokens: true per-calendar-day buckets
            day["in"] += num(t.get("in"))
            day["out"] += num(t.get("out"))
        if v.get("last_day") == today:              # cost: host per-session total, day-attributed
            day["cost"] += num(v.get("host_cost"))
    return rec, sess, day


def persist_sess_start(sid, value):
    """Write a resolved wall-clock session-start epoch into the ledger record for
    `sid` so later renders read it from the ledger instead of re-scanning the host's
    session-metadata directory (the statusline fast path). Best-effort and idempotent:
    a no-op if already stored, and a silent skip on any I/O error — it must never
    break a render. Returns True iff the ledger was written."""
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
    sessions = _load_sessions(path)
    rec = sessions.get(sid)
    if not isinstance(rec, dict):
        return False
    if num(rec.get("sess_start"), None) == float(value):
        return False                     # already cached — nothing to do
    # Cache metadata has its own file, so it cannot overwrite a concurrently
    # refreshed token/cost shard for the same session.
    if not _atomic_json(_start_file(path, sid),
                        {"sid": sid, "sess_start": float(value)}):
        return False
    sessions = _load_sessions(path)
    _write_snapshot(path, sessions)
    return True


def burn_samples(rec):
    """Recent per-message token-burn values (most-recent window) for the sparkline —
    real per-API-call totals accumulated from the transcript, not a time-extrapolated
    estimate. Returns [] when there is too little data to draw a line. The statusline
    turns this list into a colored sparkline; this lib stays render-free."""
    b = [num(x) for x in (rec.get("burn") or []) if isinstance(x, (int, float))]
    return b[-24:] if len(b) >= 2 else []
