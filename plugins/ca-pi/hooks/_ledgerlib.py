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
#   - Pure functions are fully testable with synthetic input. ledger_update()
#     and pi_ledger_update() are the only filesystem entry points; everything
#     else is pure or a private bounded persistence helper.
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
#   pi_ledger_path() -> str                  separate user-global Pi ledger path
#   pi_ledger_update(session_key, scan_start, scan_end, facts, path=None) -> dict
#                                               bounded Pi session/day snapshot
#   burn_samples(rec) -> list[float]         recent per-call token-burn values for the sparkline

import hashlib
import json
import math
import os
import re
import stat
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
    """Recent per-message token-burn values (most-recent window) for the sparkline —
    real per-API-call totals accumulated from the transcript, not a time-extrapolated
    estimate. Returns [] when there is too little data to draw a line. The statusline
    turns this list into a colored sparkline; this lib stays render-free."""
    b = [num(x) for x in (rec.get("burn") or []) if isinstance(x, (int, float))]
    return b[-24:] if len(b) >= 2 else []
