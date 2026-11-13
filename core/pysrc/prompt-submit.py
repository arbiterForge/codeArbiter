#!/usr/bin/env python3
# codeArbiter — the mode-plane prompt-seam interceptor (#437,
# mode-plane-deterministic-flip, T-27..T-39).
#
# Registered on UserPromptSubmit (Claude + Codex) and, Claude-only, on
# PreCompact (see the compaction-generation note below). Three jobs, in this
# priority order:
#
#   1. A whole-prompt mode control token (`mode` / `mode --arbiter|--dangerous
#      |--ops`, matched by `_modelib.match_mode_token` — never a substring)
#      flips or reports the mode DETERMINISTICALLY: no persona is composed or
#      injected on this turn, and the turn never reaches the model. On Claude
#      that is exit 2 + a named stderr line (`shouldQuery:false`, a host
#      invariant this module treats as a design assumption, not something it
#      re-derives). On Codex it is the seven-key `user-prompt-submit.command.
#      output` envelope with `continue:false`/`decision:"block"`, exit 0 —
#      the JSON body carries the verdict, not the process exit code (mirrors
#      `plugins/ca-codex/hooks/pre-tool-adapter.py`'s own structured-block
#      convention for a sibling event).
#   2. Any OTHER prompt: compose `includes/safety-core.md` + the CURRENT
#      mode's body (refusing a non-arbiter body the audit trail does not back
#      — AC-11) and inject it whenever the (effective mode, compaction
#      generation) differs from the one LAST delivered to this session
#      (HW-01), so a steady-state session pays for one injection per real
#      transition, not per turn, and a return to an earlier mode redelivers.
#      Claude: plain stdout (host fact — plugin-scoped
#      `additionalContext` is unreliable, claude-code#16538; see
#      `session-start.py:14-19`). Codex: `hookSpecificOutput.additionalContext`
#      inside a (deliberately leaner, non-blocking) envelope.
#   3. PreCompact (Claude only — Codex registers no PreCompact hook at all,
#      `.github/scripts/test_codex_adapter.py::test_ledgered_out_surfaces_
#      not_registered` pins that absence): bump THIS session's compaction
#      generation. `SessionStart` also fires on `compact` with no matcher
#      (`hooks.json:3-10`), which is what makes a naive (session, mode) dedup
#      marker go permanently persona-free after the first compaction — a
#      green suite, because no test spans a compaction (the spec's
#      "compaction hole"). Bumping the generation here, independent of
#      whatever SessionStart itself does, changes the NEXT turn's dedup key
#      so the persona re-injects. Deliberately NOT keyed off any Lane-E
#      SessionStart internal (e.g. session-start.py's dev-session-owner
#      bookkeeping) — that state's shape is owned by a different lane and
#      actively changing (T-47/T-48); a silent shape drift there must never
#      silently reopen this hole. Whether Claude fires PreCompact exactly
#      once per compaction is an INFERRED assumption (mirrors the spec's
#      treatment of `shouldQuery:false` — recorded, not re-verified from a
#      live binary here) — see the module's cross-lane report for what that
#      assumption is standing in for on Codex/Pi (neither gets a bump path).
#
# Dormant repos (no `arbiter: enabled` in CONTEXT.md) get none of this — the
# flip, the report, and the injection all gate on `_hooklib.arbiter_active`,
# the same convention every other entry script in this plugin follows
# (pre-bash.py, pre-write.py, pre-edit.py, post-write-edit.py, pre-read.py).
#
# AC-11 residual (NEEDS-TRIAGE, not fixed here): `_modelib.flip`/
# `ledger_backs` resolve `marker_root(payload)` while `session-start.py`'s
# `clear_dev_marker`/`_settle_dev_close` resolve `project_root(payload)` for
# the SAME audit log. In a linked worktree those can be different
# directories, so an enter/exit pair can land in two separate overrides.log
# files and the ledger-backing guarantee degrades silently. This module's
# own AC-11 test only proves the single-root case; see the plan's
# ROOT-RESOLUTION SPLIT entry (owner: Lane E) for the open half.

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _approvallib  # noqa: E402 — host-owned artifact approval capture
import _artifactauthoritylib  # noqa: E402 — exact context preview approval capture
import _hooklib  # noqa: E402
import _modelib  # noqa: E402 — mode plane core (T-06..T-16, Lane A)
import _prerequisitelib  # noqa: E402 — host-owned prerequisite capture
import _reconciliationlib  # noqa: E402 — host-owned reconciliation capture
import _readinjectlib  # noqa: E402 — marker_path(prefix=) (T-30)


# ---------------------------------------------------------------------------
# Persona sources — read off the RUNNING plugin's own generated surface, not
# core/surface/ (that source carries {{...}} template placeholders resolved
# only at build-surface.py time; the vendored copy under plugin_root/ is
# already plain text for every host).
# ---------------------------------------------------------------------------

_SAFETY_CORE_RELPATH = os.path.join("includes", "safety-core.md")
_MODE_BODY_RELPATH = {
    "arbiter": "arbiter.md",
    "dangerous": os.path.join("includes", "dangerous-mode.md"),
    "ops": os.path.join("includes", "ops-mode.md"),
}

_ELLIPSIS = "…"  # U+2026 HORIZONTAL ELLIPSIS — mirrors _readinjectlib's truncation marker

# This script's OWN compaction-generation ledger (see the module docstring's
# job 3). Lives beside the mode marker and the readinject markers, but is a
# file this script alone reads and writes.
_COMPACTION_GEN_FILENAME = "mode-compaction-gen.json"

# Codex's per-hook additionalContextLimit (R-4, AC-28): the ~2,500-token
# default is already under the composed `arbiter` persona alone — measured
# at commit time, safety-core.md (~980 tokens) + arbiter.md (~2,360 tokens)
# is ~3,340 tokens by this codebase's established ceil(len/4) proxy
# (`_readinjectlib.token_estimate`) — so accepting the default would spill
# the arbiter persona to disk on EVERY injection. Set generously above every
# mode body measured today, with headroom for `ops-mode.md` (not yet
# authored — Lane D, T-22).
CODEX_ADDITIONAL_CONTEXT_LIMIT = 8000


def _read_text(path):
    """Best-effort UTF-8 read; "" on any error (missing file, permission,
    encoding). Never raises — a persona source going missing must degrade,
    never crash the turn."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return ""


def _persona_for_mode(plugin_root, mode):
    """(safety_core_text, body_text) for `mode`, read off `plugin_root`.  An
    unrecognized mode (should not happen — `_effective_mode` already
    resolves through `_modelib.MODES`) falls back to the arbiter body rather
    than raising a KeyError on a hot path.

    Either text may come back "" — the callers treat BOTH as required and
    inject neither half alone; see `_persona_unavailable`."""
    safety = _read_text(os.path.join(plugin_root, _SAFETY_CORE_RELPATH))
    rel = _MODE_BODY_RELPATH.get(mode, _MODE_BODY_RELPATH[_modelib.MODES[0]])
    body = _read_text(os.path.join(plugin_root, rel))
    return safety, body


def _persona_unavailable(safety, body):
    """The composed persona is BOTH halves or neither.

    An earlier form rejected only the case where both reads came back empty,
    which meant an unreadable `safety-core.md` beside a readable body injected
    the mode body ALONE. For `dangerous` and `ops` that body is the permissive
    half — the session would carry the posture's licence with none of its
    floor, and nothing would say so.

    Suppressing entirely is the safe direction. The model is ungoverned either
    way, but a missing persona is conspicuous in the transcript while a half
    persona reads exactly like a whole one."""
    return not (safety.strip() and body.strip())


def _compose_persona(safety_core_text, body_text, limit_tokens=None):
    """(composed_text, truncated) — safety_core_text + body_text, joined by a
    blank line, with `_modelib.PERSONA_SENTINEL` appended as the LAST line so
    a later prune pass (`_prunelib`/`_prunepolicy`, T-49/T-50) can recognize
    and pin the whole injected block (AC-26).

    When `limit_tokens` is given and the composed estimate
    (`_readinjectlib.token_estimate`) would exceed it, ONLY the MODE BODY is
    truncated from its tail — `safety_core_text` is NEVER cut, because it
    carries the residual invariants that hold in every mode (T-17..T-19); an
    ellipsis marker is appended, mirroring `_readinjectlib.assemble_context`'s
    established truncation contract in this codebase: bounded, visible, never
    a silent drop. `truncated` is True iff that cut happened."""
    safety_core_text = safety_core_text or ""
    body_text = body_text or ""
    body_for_compose = body_text
    truncated = False
    if limit_tokens is not None:
        overhead = (_readinjectlib.token_estimate(safety_core_text)
                    + _readinjectlib.token_estimate(_modelib.PERSONA_SENTINEL)
                    + 2)  # +2: the two blank-line joins, a coarse token each
        body_budget = max(0, limit_tokens - overhead)
        if _readinjectlib.token_estimate(body_text) > body_budget:
            max_chars = max(0, body_budget * 4 - len(_ELLIPSIS))
            body_for_compose = body_text[:max_chars] + _ELLIPSIS
            truncated = True
    composed = (safety_core_text.rstrip("\n") + "\n\n"
                + body_for_compose.rstrip("\n") + "\n\n"
                + _modelib.PERSONA_SENTINEL + "\n")
    return composed, truncated


def _effective_mode(root, session_id, payload):
    """(mode, diagnostic) to COMPOSE — never `current_mode`'s raw answer
    unchecked. AC-11: the injector refuses to compose a non-arbiter body when
    `overrides.log` holds no matching `MODE: <mode> enter` row (or, for
    `dangerous`, a legacy `DEV: enter` row); it resolves `arbiter` instead and
    reports why. `diagnostic` is None on a clean resolution."""
    return _modelib.effective_mode(session_id, root=root, payload=payload)


# ---------------------------------------------------------------------------
# Delivery identity — the LAST persona delivered to a session (HW-01)
# ---------------------------------------------------------------------------
#
# The earlier dedup recorded "ever delivered" per (session, mode, compaction
# generation) and never cleared it, so arbiter->dangerous->arbiter found the
# old arbiter marker and delivered NOTHING on the return: the model's last
# persona stayed `dangerous` while the plane said arbiter (HOOK-F01).
#
# Delivery now compares against ONE per-session record of what was last
# delivered — {effective mode, compaction generation}. A persona is owed
# exactly when the current (effective mode, generation) differs from it:
#   * a real effective transition (A->B, B->A, an owed enter row settling)
#     changes the mode half and redelivers;
#   * a compaction changes the generation half and redelivers;
#   * an unchanged turn, a duplicate host event, and a no-op same-mode token
#     match and deliver nothing;
#   * A->B->A with no ordinary prompt between the flips is NOT a transition
#     the model saw (flip turns never reach it), so A is not repeated.
# Emission is not proof the model kept the text; the record only says what
# this hook last emitted.
#
# Versioned (`v`), and in its own `modedelivery-v2-` namespace: a rolled-back
# reader never sees it, and this reader never reinterprets a legacy
# `modeinject-` marker. Unreadable or mismatched -> treated as "nothing
# delivered", which fails toward a redundant persona, never a missing one.

MODEDELIVERY_PREFIX = "modedelivery-v2-"
_DELIVERY_RECORD_VERSION = 2


def _delivery_record_path(root, session_id):
    return _readinjectlib.marker_path(
        root, session_id, "last-delivered", prefix=MODEDELIVERY_PREFIX)


def _read_delivery_record(root, session_id):
    """(mode, generation) last delivered to `session_id`, or None when absent,
    unreadable, foreign, or of another version. Never raises."""
    try:
        with open(_delivery_record_path(root, session_id), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001 — degrade toward delivering again
        return None
    if (not isinstance(data, dict) or data.get("v") != _DELIVERY_RECORD_VERSION
            or data.get("session") != str(session_id)
            or data.get("mode") not in _modelib.MODES):
        return None
    generation = data.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int):
        return None
    return data["mode"], generation


def _already_delivered(root, session_id, mode, generation):
    return _read_delivery_record(root, session_id) == (mode, generation)


def _record_delivered(root, session_id, mode, generation):
    try:
        path = _delivery_record_path(root, session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _hooklib.write_text_atomic(path, json.dumps({
            "v": _DELIVERY_RECORD_VERSION, "session": str(session_id),
            "mode": mode, "generation": generation}))
    except Exception:  # noqa: BLE001 — a failed record write only costs a redundant re-delivery
        pass


# ---------------------------------------------------------------------------
# Compaction generation (job 3) — this script's own ledger
# ---------------------------------------------------------------------------

def _compaction_gen_path(root):
    return os.path.join(root, ".codearbiter", ".markers", _COMPACTION_GEN_FILENAME)


def _read_compaction_generation(root, session_id):
    """Current compaction generation for `session_id` — 0 when absent,
    corrupt, or unrecognized. Never raises."""
    try:
        with open(_compaction_gen_path(root), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return 0
        value = data.get(str(session_id))
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value
    except Exception:  # noqa: BLE001
        return 0


def _invalidate_injection_markers(root, session_id):
    """Remove `session_id`'s last-delivered record.

    The fallback when the generation cannot advance. Deleting the record
    forces the next turn's `_already_delivered` to miss, so the persona is
    re-injected — the same outcome a successful bump produces, reached by the
    other side. Never raises: this runs on an already-degraded path, and a
    failure here costs the re-injection it was trying to guarantee, so it must
    not also cost the PreCompact turn."""
    try:
        os.remove(_delivery_record_path(root, session_id))
    except Exception:  # noqa: BLE001 — absent is the desired state anyway
        pass


def _bump_compaction_generation(root, session_id):
    """Increment and persist `session_id`'s compaction generation; returns
    the NEW value. Best-effort (never raises) — PreCompact must not crash.

    A FAILED bump is not the harmless case the earlier docstring claimed. It
    returned the PRIOR generation, and the marker recorded under that
    generation still existed — so the first post-compaction turn was
    SUPPRESSED and the session continued without the persona compaction had
    just removed. That is precisely the hole this counter exists to close,
    reopened by its own failure path.

    So when the write fails, the dedup markers are invalidated instead. The
    generation stays put and the next turn re-injects, which fails toward a
    redundant persona rather than a missing one."""
    try:
        path = _compaction_gen_path(root)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:  # noqa: BLE001 — absent/corrupt -> start fresh
            data = {}
        key = str(session_id)
        current = data.get(key)
        if isinstance(current, bool) or not isinstance(current, int):
            current = 0
        data[key] = current + 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _hooklib.write_text_atomic(path, json.dumps(data))
        return data[key]
    except Exception:  # noqa: BLE001
        _invalidate_injection_markers(root, session_id)
        return _read_compaction_generation(root, session_id)


# ---------------------------------------------------------------------------
# Claude stderr messages (AC-7/9/10)
# ---------------------------------------------------------------------------

def _flip_stderr_line(outcome):
    """One user-visible line rendered from `_modelib.flip_outcome`'s ACTUAL
    result (HW-02). The earlier blanket failure line ("the session remains in
    its current mode") was false whenever the marker HAD changed and only its
    audit row was owed — the raw value moved, the effective mode did or did
    not, and the user was told neither. Each branch below states only what
    was observed; no rollback is claimed because none is performed. Mode is a
    persona posture: nothing here says a mode switches enforcement."""
    mode = outcome["requested"]
    result = outcome["result"]
    effective = outcome["effective_after"]
    if result == _modelib.FLIP_FLIPPED:
        return "codeArbiter: mode flipped to {} (MODE: {} enter logged)".format(mode, mode)
    if result == _modelib.FLIP_NOOP:
        return "codeArbiter: mode already {}".format(mode)
    if outcome["audit"] == _modelib.AUDIT_OWED:
        if outcome["raw_after"] == mode:
            head = ("codeArbiter: mode flip to {m} INCOMPLETE — the session marker now "
                    "records {m}, but its MODE: {m} enter audit row is not yet on the "
                    "trail".format(m=mode))
        else:
            head = ("codeArbiter: mode flip to {m} INCOMPLETE — its MODE: {m} enter "
                    "audit row is not yet on the trail".format(m=mode))
        return "{}; effective mode is {} ({} audit row(s) owed). Next: {}".format(
            head, effective, outcome["owed_rows"], outcome["next_action"])
    if outcome["raw_changed"]:
        state = "marker now records {}".format(outcome["raw_after"])
    elif outcome["raw_diagnostic"] not in (None, _modelib.MODE_DIAG_ABSENT):
        state = "marker could not be confirmed ({})".format(outcome["raw_diagnostic"])
    else:
        state = "marker unchanged"
    return ("codeArbiter: mode flip to {} FAILED (marker write error) — {}; "
            "effective mode is {}. Next: {}".format(
                mode, state, effective, outcome["next_action"]))


def _report_stderr_line(root, session_id, payload):
    """Bare `mode` report: the EFFECTIVE mode, plus the raw marker and owed
    audit debt whenever they differ (hooks:mode:06 used to report the raw
    value, which named a mode no persona or ledger was honouring)."""
    effective, diag = _modelib.effective_mode(session_id, root=root, payload=payload)
    raw, raw_diag = _modelib.current_mode(session_id, root=root, payload=payload)
    line = "codeArbiter: current mode is {} — legal values: {}".format(
        effective, ", ".join(_modelib.MODES))
    notes = []
    if raw != effective:
        notes.append("marker records {} without a backing MODE: {} enter row".format(raw, raw))
    elif diag or raw_diag:
        notes.append(diag or raw_diag)
    owed = _modelib.owed_audit_rows(root)
    if owed:
        notes.append("{} audit row(s) owed".format(owed))
    if notes:
        line += " ({})".format("; ".join(notes))
    return line


# ---------------------------------------------------------------------------
# Codex envelope (T-38, AC-13/28) — user-prompt-submit.command.output.
# additionalProperties:false, seven permitted keys; `permissionDecision`
# (the PreToolUse-schema key) must never appear here.
# ---------------------------------------------------------------------------

CODEX_ENVELOPE_KEYS = frozenset((
    "continue", "decision", "hookSpecificOutput", "reason",
    "stopReason", "suppressOutput", "systemMessage",
))


def _codex_block_envelope(reason, stop_reason):
    """The BLOCK shape (flip/report): exactly the seven schema-permitted
    keys, every time — `decision` is Codex's `BlockDecisionWire` enum, whose
    only member is "block", so this shape is used ONLY when actually
    blocking (never with a placeholder/empty `decision` value, which would
    not validate against the enum)."""
    return {
        "continue": False,
        "decision": "block",
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit"},
        "reason": reason,
        "stopReason": stop_reason,
        "suppressOutput": False,
        "systemMessage": reason,
    }


def _codex_allow_envelope(additional_context):
    """The non-blocking injection shape: a valid SUBSET of the seven keys
    (no `decision` — there is nothing to block, and an empty/placeholder
    `decision` would not validate against the enum either)."""
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        },
    }


# ---------------------------------------------------------------------------
# Injection (job 2), host-neutral core + per-host output
# ---------------------------------------------------------------------------

def _inject_claude(payload, host, root, session_id, approval_context=""):
    mode, diag = _effective_mode(root, session_id, payload)
    if diag:
        sys.stderr.write("codeArbiter: " + diag + "\n")
    generation = _read_compaction_generation(root, session_id)
    if _already_delivered(root, session_id, mode, generation):
        if approval_context:
            print(approval_context)
        return
    safety, body = _persona_for_mode(host.plugin_root(), mode)
    if _persona_unavailable(safety, body):
        sys.stderr.write("codeArbiter: persona sources incomplete for mode '{}' — "
                         "injecting nothing this turn rather than a body without its "
                         "safety floor.\n".format(mode))
        if approval_context:
            print(approval_context)
        return
    composed, _truncated = _compose_persona(safety, body)
    print("\n\n".join(value for value in (approval_context, composed) if value))
    _record_delivered(root, session_id, mode, generation)


def _inject_codex(payload, host, root, session_id, approval_context=""):
    mode, diag = _effective_mode(root, session_id, payload)
    generation = _read_compaction_generation(root, session_id)
    if _already_delivered(root, session_id, mode, generation):
        if approval_context:
            print(json.dumps(_codex_allow_envelope(approval_context)))
        return
    safety, body = _persona_for_mode(host.plugin_root(), mode)
    if _persona_unavailable(safety, body):
        sys.stderr.write("codeArbiter: persona sources incomplete for mode '{}' — "
                         "injecting nothing this turn rather than a body without its "
                         "safety floor.\n".format(mode))
        if approval_context:
            print(json.dumps(_codex_allow_envelope(approval_context)))
        return
    composed, _truncated = _compose_persona(
        safety, body, limit_tokens=CODEX_ADDITIONAL_CONTEXT_LIMIT)
    context = "\n\n".join(value for value in (approval_context, composed) if value)
    print(json.dumps(_codex_allow_envelope(context)))
    _record_delivered(root, session_id, mode, generation)


# ---------------------------------------------------------------------------
# UserPromptSubmit dispatch (jobs 1 + 2)
# ---------------------------------------------------------------------------

def _handle_claude(payload, host, root, session_id, token, approval_context=""):
    if token == _modelib.MODE_TOKEN_REPORT:
        sys.stderr.write(_report_stderr_line(root, session_id, payload) + "\n")
        return 2
    if token in _modelib.MODES:
        outcome = _modelib.flip_outcome(session_id, token, root=root, payload=payload,
                                        host_name=host.name)
        sys.stderr.write(_flip_stderr_line(outcome) + "\n")
        return 2
    _inject_claude(payload, host, root, session_id, approval_context)
    return 0


def _handle_codex(payload, host, root, session_id, token, approval_context=""):
    if token == _modelib.MODE_TOKEN_REPORT:
        msg = _report_stderr_line(root, session_id, payload)
        print(json.dumps(_codex_block_envelope(msg, msg)))
        return 0
    if token in _modelib.MODES:
        outcome = _modelib.flip_outcome(session_id, token, root=root, payload=payload,
                                        host_name=host.name)
        msg = _flip_stderr_line(outcome)
        print(json.dumps(_codex_block_envelope(msg, msg)))
        return 0
    _inject_codex(payload, host, root, session_id, approval_context)
    return 0


def _handle_user_prompt_submit(payload, host):
    session_id = payload.get("session_id") or ""
    root = _hooklib.project_root(payload)
    active = _hooklib.arbiter_active(root)
    state_root = _hooklib.marker_root(payload) if active else root
    prompt = payload.get("prompt")
    prompt = prompt if isinstance(prompt, str) else ""
    token = _modelib.match_mode_token(prompt)
    approval_context = ""
    if token is None:
        contexts = []
        approval = _approvallib.consume_from_hook(
            root=root,
            plugin_root=host.plugin_root(),
            prompt=prompt,
            host=host.name,
            session_id=session_id,
        )
        if approval:
            contexts.append(approval)
        prerequisite = _prerequisitelib.consume_from_hook(
            root=root,
            plugin_root=host.plugin_root(),
            prompt=prompt,
            host=host.name,
            session_id=session_id,
        )
        if prerequisite:
            contexts.append(prerequisite)
        reconciliation = _reconciliationlib.consume_from_hook(
            root=root,
            plugin_root=host.plugin_root(),
            prompt=prompt,
            host=host.name,
            session_id=session_id,
        )
        if reconciliation:
            contexts.append(reconciliation)
        context_preview = _artifactauthoritylib.capture_context_preview_from_hook(
            root=root,
            plugin_root=host.plugin_root(),
            prompt=prompt,
            host=host.name,
            session_id=session_id,
        )
        if context_preview:
            contexts.append(context_preview)
        approval_context = "\n".join(contexts)
    if not active:
        if not approval_context:
            return 0
        if host.name == "codex":
            print(json.dumps(_codex_allow_envelope(approval_context)))
        else:
            print(approval_context)
        return 0
    recovery_notice = None
    recovery_library = None
    if token is None and host.name != "pi":
        try:
            import _workflowrecoverylib as recovery_library
            recovery_notice = recovery_library.presentation(root, session_id)
        except Exception:
            recovery_notice = {"text": "codeArbiter: workflow recovery notice unavailable; independent authorized work continues.", "fingerprint": None}
        approval_context = "\n".join(value for value in (approval_context, recovery_notice["text"]) if value)
    if host.name == "codex":
        result = _handle_codex(
            payload, host, state_root, session_id, token, approval_context
        )
    else:
        result = _handle_claude(
            payload, host, state_root, session_id, token, approval_context
        )
    if recovery_library is not None and recovery_notice is not None and recovery_notice["text"] and recovery_notice["fingerprint"]:
        sys.stdout.flush()
        recovery_library.record_notice_emitted(root, session_id, recovery_notice["fingerprint"])
    return result


def _handle_precompact(payload, host):
    """Job 3 — bump this session's compaction generation. Claude-only (see
    the module docstring); never blocks, never raises."""
    session_id = payload.get("session_id") or ""
    if not session_id:
        return 0
    root = _hooklib.project_root(payload)
    if not _hooklib.arbiter_active(root):
        return 0
    _bump_compaction_generation(_hooklib.marker_root(payload), session_id)
    # Read-time context pointers have their own worktree-local epoch. A
    # surviving read marker cannot prove that a compacted actor still carries
    # those pointers. Keep this separate from the persona generation above.
    _readinjectlib.bump_context_generation(root, session_id)
    return 0


def main(argv=None):
    _hooklib.utf8_stdio()
    payload = _hooklib.read_input()
    host = _hooklib.get_host()
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if event == "PreCompact":
        return _handle_precompact(payload, host)
    if event == "UserPromptSubmit":
        return _handle_user_prompt_submit(payload, host)
    return 0


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with
    the plugin's loaded Host, primes `_hooklib`'s process-cached Host BEFORE
    main() runs (#257), then delegates."""
    _hooklib.set_host(host)
    return main(argv)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
