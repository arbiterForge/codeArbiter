#!/usr/bin/env python3
# codeArbiter — Claude transcript usage normalization, identity, reconciliation
# and pricing (spec: claude-statusline-accounting-integrity D-5..D-10, D-26, D-27).
#
# The ONE owner of what a Claude transcript usage record means. _ledgerlib persists
# and schedules, and the statusline renders. Neither re-derives usage semantics.
#
# Design principles:
#   - Stdlib only; pure functions over immutable tables; no I/O, no classes.
#   - Money is exact: integer picodollars (1e-12 USD), with every rate and
#     modifier held as an exact decimal/rational. There is no float math anywhere
#     in pricing, so derived totals can be subtracted and re-added exactly.
#   - A normalized fact merges with another fact of the same request by
#     element-wise max (counters), min (event time) and union (days, modifier
#     values). That is commutative, associative and idempotent, so neither scan
#     order nor replay order can change the accepted state (spec D-6).
#   - Unknown things are never priced as something else. They add a coverage
#     reason and contribute no dollars (spec D-8, D-10, D-26, D-27).
#
# Public API:
#   rates(model, speed="standard", geo="global") -> tuple|None   picodollars/token
#   canonical_model(model) -> str|None
#   known_models() -> list[str]
#   classify_identity(record) -> (key|None, alias|None)
#   normalize(record, day_fn) -> {"kind": "usage"|"malformed"|"ignore", ...}
#   merge(fact_a, fact_b) -> fact
#   price(fact) -> {"pd", "in", "out", "cr", "reasons"}
#   event_day(fact) -> str|None ; days_seen(fact) -> list[str]
#   usage_bearing(line_bytes) -> bool

import math
import os
import re
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fmtlib import parse_iso  # noqa: E402

# --------------------------------------------------------------------------- pricing registry
# Anthropic API list prices, USD per million tokens, copied verbatim from the
# official pricing page. Tuple order: input, output, 5-minute cache write,
# 1-hour cache write, cache read. Strings keep every value an exact decimal.
REGISTRY_CAPTURED = "2026-09-27"
REGISTRY_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
# Bump whenever a rate or rule changes: stored ledger state re-prices from its
# retained evidence when the version it was priced under differs (spec D-21).
REGISTRY_VERSION = "2026-09-27.1"

_OPUS_45_TO_5 = ("5", "25", "6.25", "10", "0.50")
_OPUS_4_41 = ("15", "75", "18.75", "30", "1.50")
_SONNET_4X = ("3", "15", "3.75", "6", "0.30")
_FABLE_51 = ("10", "50", "12.50", "20", "0.25")
_FABLE_5 = ("10", "50", "12.50", "20", "1")
_PRICES = {
    "claude-fable-5-1": _FABLE_51,
    "claude-mythos-5-1": _FABLE_51,
    "claude-fable-5": _FABLE_5,
    "claude-mythos-5": _FABLE_5,
    "claude-opus-5-5": ("4", "20", "5", "8", "0.20"),
    "claude-opus-5": _OPUS_45_TO_5,
    "claude-opus-4-8": _OPUS_45_TO_5,
    "claude-opus-4-7": _OPUS_45_TO_5,
    "claude-opus-4-6": _OPUS_45_TO_5,
    "claude-opus-4-5": _OPUS_45_TO_5,
    "claude-opus-4-1": _OPUS_4_41,
    "claude-opus-4": _OPUS_4_41,
    "claude-sonnet-5": ("2", "10", "2.50", "4", "0.20"),
    "claude-sonnet-4-6": _SONNET_4X,
    "claude-sonnet-4-5": _SONNET_4X,
    "claude-sonnet-4": _SONNET_4X,
    "claude-haiku-4-5": ("1", "5", "1.25", "2", "0.10"),
    "claude-3-5-haiku": ("0.80", "4", "1", "1.60", "0.08"),
}
# Explicit alternate spellings only. Dated snapshot suffixes (-YYYYMMDD) are
# stripped by rule below; nothing else is guessed.
_ALIASES = {
    "claude-opus-4-0": "claude-opus-4",
    "claude-sonnet-4-0": "claude-sonnet-4",
}
# Fast mode (research preview): published input/output rates. Cache multipliers
# stack on the fast input rate in the model's own standard ratios.
_FAST = {
    "claude-opus-5-5": ("8", "40"),
    "claude-opus-5": ("10", "50"),
    "claude-opus-4-8": ("10", "50"),
}
# Claude 4.6-and-later models: `inference_geo: "us"` is billed at 1.1x, and the
# 1M context window is billed at standard rates (so a `[1m]` label is an alias).
_MODERN = frozenset({
    "claude-fable-5-1", "claude-mythos-5-1", "claude-fable-5", "claude-mythos-5",
    "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6",
})
_GEO_US_MULTIPLIER = Fraction(11, 10)
_STANDARD_SPEED = "standard"
_STANDARD_GEO = frozenset({"global", "not_available"})   # not_available: see spec D-27
_STANDARD_TIER = "standard"

# Separately metered server-tool counters (spec D-10): picodollars per unit.
# Web search $10 / 1,000 searches; web fetch has no charge beyond tokens. Any
# other counter (incl. code execution, billed by unobservable container time)
# is unknown and makes coverage partial when non-zero.
TOOL_PRICES = {
    "web_search_requests": 10 * 10**12 // 1000,
    "web_fetch_requests": 0,
}

_PD_PER_USD_PER_MTOK = 10**6        # $/MTok -> picodollars per token
_DATED = re.compile(r"-\d{8}$")


def _pd(value):
    v = Fraction(value) * _PD_PER_USD_PER_MTOK
    if v.denominator != 1:           # a rate that is not a whole picodollar is a registry bug
        raise ValueError(f"non-integral rate {value!r}")
    return int(v)


def known_models():
    return sorted(_PRICES)


def canonical_model(model):
    """The registry id for a model string, or None when it is not known."""
    if not isinstance(model, str):
        return None
    s = model.strip().lower()
    long_ctx = s.endswith("[1m]")
    if long_ctx:
        s = s[:-4]
    s = _ALIASES.get(s, s)
    if s not in _PRICES and _DATED.search(s):
        s = _DATED.sub("", s)
        s = _ALIASES.get(s, s)
    if s not in _PRICES:
        return None
    if long_ctx and s not in _MODERN:
        return None                  # pre-4.6 long context had its own premium
    return s


def rates(model, speed=_STANDARD_SPEED, geo="global"):
    """(input, output, 5m write, 1h write, cache read) in integer picodollars per
    token, or None when the model or the modifier combination is not priceable."""
    canon = canonical_model(model)
    if canon is None:
        return None
    base = [Fraction(v) for v in _PRICES[canon]]
    if speed == "fast":
        if canon not in _FAST:
            return None
        fin, fout = (Fraction(v) for v in _FAST[canon])
        base = [fin, fout, fin * base[2] / base[0], fin * base[3] / base[0],
                fin * base[4] / base[0]]
    elif speed != _STANDARD_SPEED:
        return None
    if geo == "us":
        if canon not in _MODERN:
            return None
        base = [v * _GEO_US_MULTIPLIER for v in base]
    elif geo not in _STANDARD_GEO:
        return None
    return tuple(_pd(v) for v in base)


# --------------------------------------------------------------------------- identity
_MAX_ID = 256


def _valid_id(v):
    return (isinstance(v, str) and 0 < len(v) <= _MAX_ID
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in v))


def classify_identity(record):
    """(identity key, message-id alias) for a usage record (spec D-5).

    Keys are domain-separated by class prefix. A record carrying both IDs
    returns its `mid:` key as an alias, so a message-ID-only representation of
    the same request can be merged in either arrival order. Anything missing
    or structurally invalid is unproven: (None, None)."""
    if not isinstance(record, dict):
        return None, None
    msg = record.get("message")
    mid = msg.get("id") if isinstance(msg, dict) else None
    mid_key = "mid:" + mid if _valid_id(mid) else None
    rid = record.get("requestId")
    if _valid_id(rid):
        return "rid:" + rid, mid_key
    return mid_key, None


# --------------------------------------------------------------------------- normalization
MAX_COUNTER = 10**15                 # sanity ceiling for any single usage counter
_MIN_EPOCH, _MAX_EPOCH = 946684800, 4102444800   # 2000-01-01 .. 2100-01-01
_TOP = ("input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens")


class _Malformed(Exception):
    pass


def _count(v):
    """A usage counter as a non-negative int. Absent/None is 0. Booleans,
    strings, negatives, non-finite, fractional and absurd values are malformed."""
    if v is None:
        return 0
    if isinstance(v, bool):
        raise _Malformed
    if isinstance(v, int):
        n = v
    elif isinstance(v, float):
        if not math.isfinite(v) or not v.is_integer():
            raise _Malformed
        n = int(v)
    else:
        raise _Malformed
    if n < 0 or n > MAX_COUNTER:
        raise _Malformed
    return n


def _split(obj):
    """(c5, c1) from a cache_creation object, or None when absent."""
    if obj is None:
        return None
    if not isinstance(obj, dict):
        raise _Malformed
    return (_count(obj.get("ephemeral_5m_input_tokens")),
            _count(obj.get("ephemeral_1h_input_tokens")))


def _vector(obj):
    """[in, out, cache_read, cache_write_total, c5, c1, classified] for one
    usage-shaped object (a top-level usage or one iteration)."""
    inp, out, cr, cw = (_count(obj.get(k)) for k in _TOP)
    split = _split(obj.get("cache_creation"))
    if split is None:
        return [inp, out, cr, cw, 0, 0, 0]
    return [inp, out, cr, cw, split[0], split[1], 1]


def _add(a, b):
    """Sum two vectors of the SAME representation (several iterations of one kind)."""
    out = [x + y for x, y in zip(a[:6], b[:6])]
    return out + [min(a[6], b[6])]


def _model_key(model):
    canon = canonical_model(model)
    if canon is not None:
        return canon
    return "?" + model.strip().lower() if isinstance(model, str) and model.strip() else "?"


def _modifier(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() or default
    return "invalid"


def _trusted_ts(ts):
    if not isinstance(ts, str):
        return None
    e = parse_iso(ts)
    if e is None or not (_MIN_EPOCH <= e < _MAX_EPOCH):
        return None
    return e


def normalize(record, day_fn):
    """Classify one decoded transcript record.

    Returns {"kind": "ignore"} for anything that is not billable assistant usage
    (non-objects, other record types, zero-usage records such as `<synthetic>`),
    {"kind": "malformed", "reason": "malformed_record", "id": ...} when usage is
    present but cannot be trusted, or {"kind": "usage", "id", "alias", "fact"}.
    `day_fn(timestamp_string)` maps a trustworthy timestamp to its local day."""
    if not isinstance(record, dict) or record.get("type") != "assistant":
        return {"kind": "ignore"}
    msg = record.get("message")
    if not isinstance(msg, dict) or "usage" not in msg:
        return {"kind": "ignore"}
    ident, alias = classify_identity(record)
    try:
        fact = _fact(record, msg, msg.get("usage"), day_fn)
    except _Malformed:
        return {"kind": "malformed", "reason": "malformed_record", "id": ident}
    if fact is None:
        return {"kind": "ignore"}
    return {"kind": "usage", "id": ident, "alias": alias, "fact": fact}


def _fact(record, msg, usage, day_fn):
    if not isinstance(usage, dict):
        raise _Malformed
    comps = {}
    top = _vector(usage)
    iters = usage.get("iterations")
    if iters is None:
        iters = []
    if not isinstance(iters, list):
        raise _Malformed
    msg_split = None
    for it in iters:
        if not isinstance(it, dict):
            raise _Malformed
        kind = it.get("type")
        vec = _vector(it)
        if kind == "message":
            msg_split = vec if msg_split is None else _add(msg_split, vec)
            continue
        if kind == "advisor_message":
            key = "a|" + _model_key(it.get("model"))
        else:
            key = "x|" + (kind if isinstance(kind, str) else "?") + "|" + _model_key(it.get("model"))
        comps[key] = vec if key not in comps else _add(comps[key], vec)
    # The top-level counters are the message iterations (spec observation 2). Their
    # TTL split is taken from the per-iteration splits when those account for the
    # whole aggregate; the top-level split can be stale on multi-iteration records.
    if msg_split is not None and msg_split[6] and msg_split[4] + msg_split[5] == top[3]:
        top[4], top[5], top[6] = msg_split[4], msg_split[5], 1
    comps["m|" + _model_key(msg.get("model"))] = top
    tools = {}
    stu = usage.get("server_tool_use")
    if stu is not None:
        if not isinstance(stu, dict):
            raise _Malformed
        for name, v in stu.items():
            tools[str(name)] = _count(v)
    if not any(any(v[:6]) for v in comps.values()) and not any(tools.values()):
        return None                  # non-billable (e.g. <synthetic>, all zero)
    t = _trusted_ts(record.get("timestamp"))
    day = day_fn(record["timestamp"]) if t is not None else None
    return {
        "t": t,
        "td": day,
        "d": [day] if day else [],
        "c": comps,
        "tl": tools,
        "md": {"speed": [_modifier(usage.get("speed"), "standard")],
               "geo": [_modifier(usage.get("inference_geo"), "global")],
               "tier": [_modifier(usage.get("service_tier"), "standard")]},
    }


# --------------------------------------------------------------------------- reconciliation
def merge(a, b):
    """Reconcile two facts of the SAME request (spec D-6). Commutative,
    associative and idempotent: counters by max, event time by min, day and
    modifier sets by union. Cache-write classification is a max-join whose
    consistency is judged at pricing time (spec D-9)."""
    if a is None:
        return b
    if b is None:
        return a
    if a["t"] is None:
        t, td = b["t"], b["td"]
    elif b["t"] is None or a["t"] < b["t"]:
        t, td = a["t"], a["td"]
    elif b["t"] < a["t"]:
        t, td = b["t"], b["td"]
    else:
        t, td = a["t"], min(x for x in (a["td"], b["td"]) if x) if (a["td"] or b["td"]) else None
    comps = {}
    for key in set(a["c"]) | set(b["c"]):
        x, y = a["c"].get(key), b["c"].get(key)
        comps[key] = list(x) if y is None else list(y) if x is None else \
            [max(p, q) for p, q in zip(x, y)]
    tools = {k: max(a["tl"].get(k, 0), b["tl"].get(k, 0)) for k in set(a["tl"]) | set(b["tl"])}
    mods = {k: sorted(set(a["md"].get(k, [])) | set(b["md"].get(k, [])))
            for k in set(a["md"]) | set(b["md"])}
    return {"t": t, "td": td, "d": sorted(set(a["d"]) | set(b["d"])), "c": comps,
            "tl": tools, "md": mods}


def event_day(fact):
    return fact.get("td") if fact else None


def days_seen(fact):
    return list(fact.get("d") or []) if fact else []


# --------------------------------------------------------------------------- pricing a fact
def _vec_cost(vec, r, reasons):
    """Picodollars for one component vector at rates `r` (None = unpriced)."""
    inp, out, cr, cw, c5, c1, classified = vec
    if not (classified and c5 + c1 <= cw):
        c5 = c1 = 0                  # no classification, or one that cannot be trusted
    if cw - c5 - c1 > 0:
        reasons.add("unknown_cache_ttl")
    if r is None:
        return 0
    return inp * r[0] + out * r[1] + c5 * r[2] + c1 * r[3] + cr * r[4]


def price(fact):
    """Tokens and exact picodollars for one accepted request, plus the set of
    coverage reasons that keep it from being completely priced. Display input
    counts uncached input plus every cache write; cache reads are priced but not
    counted as input."""
    reasons = set()
    total = tin = tout = tcr = 0
    comps = fact["c"]
    mods = fact.get("md", {})
    speeds, geos, tiers = mods.get("speed", ["standard"]), mods.get("geo", ["global"]), \
        mods.get("tier", ["standard"])
    modifiers_ok = len(speeds) == 1 and len(geos) == 1 and tiers == [_STANDARD_TIER]

    top_keys = sorted(k for k in comps if k.startswith("m|"))
    if len(top_keys) > 1:
        # One request cannot have run on two models. Count tokens once (the
        # component-wise max, never a sum) and price nothing until proven.
        reasons.add("model_conflict")
        vec = [max(col) for col in zip(*(comps[k] for k in top_keys))]
        _vec_cost(vec, None, reasons)
        tin, tout, tcr = vec[0] + vec[3], vec[1], vec[2]
    elif top_keys:
        vec = comps[top_keys[0]]
        model = top_keys[0][2:]
        r = None
        if model.startswith("?"):
            reasons.add("unknown_model")
        elif modifiers_ok:
            r = rates(model, speed=speeds[0], geo=geos[0])
            if r is None:
                reasons.add("unpriced_modifier")
        else:
            reasons.add("unpriced_modifier")
        total += _vec_cost(vec, r, reasons)
        tin, tout, tcr = vec[0] + vec[3], vec[1], vec[2]

    for key in sorted(comps):
        if key.startswith("m|"):
            continue
        vec = comps[key]
        tin += vec[0] + vec[3]
        tout += vec[1]
        tcr += vec[2]
        if key.startswith("a|"):
            model = key[2:]
            r = None if model.startswith("?") else rates(model)
            if r is None and any(vec[:6]):
                reasons.add("unknown_model")
            total += _vec_cost(vec, r, reasons)
        elif any(vec[:6]):
            reasons.add("unknown_iteration")

    for name, n in sorted(fact.get("tl", {}).items()):
        if n <= 0:
            continue
        if name in TOOL_PRICES:
            total += n * TOOL_PRICES[name]
        else:
            reasons.add("unknown_charge")
    return {"pd": total, "in": tin, "out": tout, "cr": tcr, "reasons": reasons}


# --------------------------------------------------------------------------- byte-level classification
TAIL_WINDOW = 65536
_USAGE_KEY = b'"usage":'
_ASSISTANT = (b'"type":"assistant"', b'"type": "assistant"')


def usage_bearing(line):
    """True when a raw JSONL line may carry billable assistant usage: its final
    64 KiB contain both a `"usage":` key and an assistant type marker (spec
    observation 10). Used to skip decoding every other line, and to classify an
    undecodable or oversized line."""
    tail = line[-TAIL_WINDOW:]
    return _USAGE_KEY in tail and any(m in tail for m in _ASSISTANT)
