#!/usr/bin/env python3
# codeArbiter — host-neutral semantic selection policy for transcript pruning.
"""Host-neutral semantic selection policy for transcript pruning.

Codecs own host serialization. This module owns only deterministic selection,
tier ordering, markers, dry metrics, and audit outcomes.
"""
#
# Public API:
#   reduction_metrics(bytes_before, bytes_after) -> dict  dry/run reduction metrics
#                                            with the shared token estimate
#   audit_outcomes(parse_errors, orphans, unpaired) -> tuple  host-neutral integrity
#                                            levels; codecs retain native messages
#   marker_for(original_text) -> str        deterministic condensed-content marker;
#                                            an existing marker is returned unchanged
#   has_marker(value) -> bool               True iff value already carries the marker
#   select_strategies(tier, strategies=None) -> tuple  strategies admitted by tier,
#                                            or an explicit requested subset
#   protected_ordinal(entries, keep_recent) -> int  the protected-tail boundary
#   plan_prune(entries, policy) -> PrunePlan  full selection/action/audit plan over
#                                            a SemanticEntry sequence

from dataclasses import dataclass
import hashlib
import json
from typing import Optional


MARKER_PREFIX = "[ca-condensed "
TIERS = {"gentle": 0, "standard": 1, "aggressive": 2}
STRATEGY_TIERS = {
    "sidecar-collapse": "gentle",
    "reasoning-fold": "standard",
    "mcp-payload-condense": "standard",
    "shell-tail-keep": "standard",
    "superseded-read-condense": "aggressive",
    "repeat-reminder-fold": "aggressive",
    "inline-image-evict": "aggressive",
    "aged-result-condense": "standard",
    "oversize-result-clamp": "gentle",
}
STRATEGY_ORDER = (
    "sidecar-collapse",
    "reasoning-fold",
    "mcp-payload-condense",
    "shell-tail-keep",
    "superseded-read-condense",
    "repeat-reminder-fold",
    "inline-image-evict",
    "aged-result-condense",
    "oversize-result-clamp",
)


@dataclass(frozen=True)
class SemanticEntry:
    id: str
    ordinal: int
    role: str
    kind: str
    byte_size: int
    tool_bearing: bool = False
    marked: bool = False


@dataclass(frozen=True)
class PrunePolicy:
    tier: str = "gentle"
    keep_recent: int = 10
    max_bytes: int = 8192
    strategies: tuple = ()


@dataclass(frozen=True)
class PrunePlan:
    protected_ids: tuple
    first_kept_id: Optional[str]
    protected_from: int
    actions: tuple
    metrics: dict
    audit_codes: tuple
    fingerprint: str


STANDARD_POLICY = PrunePolicy(tier="standard")


def reduction_metrics(bytes_before, bytes_after):
    """Host-neutral dry/run reduction metrics with the shared token estimate."""
    if type(bytes_before) is not int or type(bytes_after) is not int \
            or bytes_before < 0 or bytes_after < 0:
        raise ValueError("prune byte metrics are invalid")
    return {
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "freed_bytes": bytes_before - bytes_after,
        "est_tokens_before": bytes_before // 4,
        "est_tokens_after": bytes_after // 4,
        "pct": round(100.0 * (bytes_before - bytes_after) / bytes_before, 1)
        if bytes_before else 0.0,
    }


def audit_outcomes(parse_errors=0, orphans=0, unpaired=0):
    """Select host-neutral integrity levels; codecs retain native messages."""
    return (
        "FAIL" if parse_errors else "OK",
        "WARN" if orphans else "OK",
        "WARN" if unpaired else "OK",
        "OK",
    )


def marker_for(original_text):
    """Return one deterministic marker; an existing marker is unchanged."""
    if has_marker(original_text):
        return original_text
    data = str(original_text).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()[:8]
    return f"{MARKER_PREFIX}{len(data)}B #{digest}]"


def has_marker(value):
    return isinstance(value, str) and MARKER_PREFIX in value


def select_strategies(tier, strategies=None):
    if strategies:
        requested = set(strategies)
        return tuple(name for name in STRATEGY_ORDER if name in requested)
    ceiling = TIERS.get(tier, 0)
    return tuple(name for name in STRATEGY_ORDER
                 if TIERS[STRATEGY_TIERS[name]] <= ceiling)


def protected_ordinal(entries, keep_recent):
    """Match the existing protected-tail rule over semantic entries."""
    anchors = [entry.ordinal for entry in entries if entry.tool_bearing]
    result_anchors = [entry.ordinal for entry in entries
                      if entry.kind == "tool-result"]
    anchors = anchors or result_anchors
    if keep_recent <= 0:
        tool_boundary = len(entries)
    elif len(anchors) > keep_recent:
        tool_boundary = anchors[-keep_recent]
    elif anchors:
        tool_boundary = anchors[0]
    else:
        tool_boundary = len(entries)
    assistants = [entry.ordinal for entry in entries if entry.role == "assistant"]
    return min(tool_boundary, assistants[-1]) if assistants else tool_boundary


def _action_for(entry, selected, policy):
    if entry.marked:
        return "already-condensed"
    if entry.kind == "tool-result" and entry.byte_size > policy.max_bytes \
            and "oversize-result-clamp" in selected:
        return "oversize-result-clamp"
    if entry.role == "assistant" and "reasoning-fold" in selected:
        return "reasoning-fold"
    return "retain"


def plan_prune(entries, policy):
    entries = tuple(entries)
    if any(not isinstance(entry, SemanticEntry) for entry in entries):
        raise TypeError("plan_prune requires SemanticEntry values")
    if [entry.ordinal for entry in entries] != list(range(len(entries))):
        raise ValueError("semantic entry ordinals must be contiguous and ordered")
    boundary = protected_ordinal(entries, policy.keep_recent)
    protected = tuple(entry.id for entry in entries if entry.ordinal >= boundary)
    selected = select_strategies(policy.tier, policy.strategies)
    actions = tuple((entry.id, _action_for(entry, selected, policy))
                    for entry in entries if entry.ordinal < boundary)
    marked = sum(1 for entry in entries if entry.ordinal < boundary and entry.marked)
    metrics = {
        "entries_before": len(entries),
        "candidate_entries": boundary,
        "protected_entries": len(protected),
        "marked_candidates": marked,
    }
    audit_codes = (("CA-PRUNE-NOOP",) if boundary == 0
                   else ("CA-PRUNE-IDEMPOTENT",) if marked == boundary
                   else ("CA-PRUNE-PLAN",))
    fingerprint_source = {
        "boundary": boundary,
        "protected": protected,
        "actions": actions,
        "metrics": metrics,
        "audit": audit_codes,
        "tier": policy.tier,
        "strategies": selected,
    }
    fingerprint = hashlib.sha256(json.dumps(
        fingerprint_source, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return PrunePlan(
        protected_ids=protected,
        first_kept_id=(entries[boundary].id if boundary < len(entries) else None),
        protected_from=boundary,
        actions=actions,
        metrics=metrics,
        audit_codes=audit_codes,
        fingerprint=fingerprint,
    )
