#!/usr/bin/env python3
# codeArbiter — shared hook helpers (issues #24, #25).
#
# Replaces the bash+jq hook layer with a cross-platform, fail-LOUD Python
# implementation. The bash hooks began with `which jq > /dev/null || exit 0`,
# so on any machine without jq (e.g. a stock Windows install) EVERY safety gate
# silently evaporated with no signal — the plugin appeared installed but was
# inert. Python is already a plugin dependency (statusline, scaffolder), needs
# no jq, and lets a hook fail loud instead of fail open.
#
# Blocking contract: a PreToolUse hook BLOCKS the tool call by exiting 2 (its
# stderr is fed back to Claude). Exit 0 allows. The prior bash hooks used
# exit 1 — a NON-blocking error under Claude Code's hook contract — so their
# "BLOCKED" gates may not have been stopping the tool at all; this port closes
# that latent gap.
#
# Interpreter launch: hooks.json registers every hook TWICE — `python <script>`
# plus a fallback `python -c "" || python3 <script>`. Preferring `python` avoids
# activating Windows' python3 MSIX app-execution alias for every hook; POSIX
# installs that expose only python3 still use the fallback. A single
# `python x || python3 x` entry would be wrong: when python exists and the
# script BLOCKS (exit 2), `||` would re-run it against a
# drained stdin and the rerun's exit 0 would swallow the block. Separate hook
# entries each receive their own stdin, so the block survives.
#
# Public API:
#   get_host() -> Host                   the process's Host instance (hostapi.load_host(), cached)
#   set_host(host) -> None               DI seam (#257): prime the process-cached Host that
#                                         get_host() returns. Every entry script's run(host) calls
#                                         this BEFORE main(), so the Host the __main__ guard already
#                                         loaded is the one get_host() serves — main() no longer
#                                         triggers a second hostapi.load_host(), and a test calling
#                                         run(fake_host) genuinely runs against fake_host.
#   utf8_stdio() -> None                 force UTF-8 on stdout/stderr
#   norm_path(p) -> str                  normalize path separators to forward-slash
#   frontmatter_enabled(ctx_path) -> tuple[bool, bool]   (enabled, malformed)
#   frontmatter_enabled_text(text) -> tuple[bool, bool]  same, over content not a path
#   arbiter_active(root) -> bool         True iff repo opted in via CONTEXT.md frontmatter
#   read_input() -> dict                 parse hook JSON from stdin; fail-open on error
#   tool_input(data) -> dict             extract tool_input sub-dict from hook payload
#   project_root(payload=None) -> str    CLAUDE_PROJECT_DIR, else git repo root, else cwd
#                                         (memoized per process, keyed on the
#                                         inputs that could change it — #260)
#   marker_root(payload=None) -> str     project_root(payload), escalated to the MAIN
#                                         checkout when that names a LINKED worktree's
#                                         own checkout — the root gate MARKERS
#                                         (.codearbiter/.markers/) live under (#604)
#   repo_rel(fpath, root) -> str         repo-relative POSIX path, or "" if outside root
#   line_digest(line) -> str             sha256 hex of one diff line (H-09b/H-10b gate)
#   content_digest(text) -> str          sha256 hex of a whole file's content (H-14 gate)
#   migration_globs(root) -> tuple[list, list]   (includes, excludes) for migration detection
#   scope_globs(root, defaults, decl_re) -> tuple[list, list]   generic glob scope resolver
#   path_in_globs(rel, root, defaults, decl_re) -> bool         True iff path matches scope
#   is_migration_path(rel, root) -> bool  True iff rel is a DB migration (H-14)
#   is_ci_path(rel, root) -> bool         True iff rel is a CI/CD workflow (H-15)
#   is_deploy_path(rel, root) -> bool     True iff rel is a deployment/IaC manifest (H-16)
#   is_audit_log(rel) -> bool             True iff rel is an append-only audit log (H-05)
#   is_tail_append(current, old, new) -> bool  True iff old_string is current's exact
#                                          trailing content AND new_string extends it (H-05)
#   is_decisions_path(rel) -> bool        True iff rel is an ADR under decisions/ (H-11)
#   is_context_md(rel) -> bool            True iff rel is the CONTEXT.md activation file (#159)
#   is_marker_path(rel) -> bool           True iff rel is under .codearbiter/.markers/ (#160)
#   classify_protected(fpath, root) -> set  protected classes hit, raw+realpath (#162)
#   is_sensitive_scan_exempt(rel) -> bool  True iff rel is exempt from the H-09b/H-10b
#                                         crypto/secret scan (gate-events.log only, #279)
#   SECURITY_DIFF_GIT_ARGS                pinned `git diff` argv suffix (fixed a/ b/
#                                         prefixes, no external diff) every H-09b/H-10b
#                                         sensitive-line reader MUST use (#279 review)
#   diff_added_lines(diff_text) -> list[tuple[str|None, str]]  path-aware walk of a unified
#                                         diff's added ('+') lines (from SECURITY_DIFF_GIT_ARGS
#                                         output), paired with the destination path each
#                                         belongs to, attributed from `+++ b/<path>` via a
#                                         fixed-prefix strip within an unspoofable `diff `
#                                         section (#279 review)
#   sensitive_scan_added_lines(diff_text) -> list[str]  diff_added_lines() narrowed to the
#                                         H-09b/H-10b candidate set (exempt paths dropped)
#   MARKER_FRESHNESS_MINUTES -> int        the single H-11 authoring-marker
#                                         freshness window (30 minutes). Issue
#                                         #567: this used to be five
#                                         independent hardcoded `30` literals
#                                         (pre-write.py, pre-edit.py,
#                                         _bashguardlib.py, git-enforce.py,
#                                         _protectedstatelib.py) with no
#                                         import relationship, so widening or
#                                         narrowing one silently desynced the
#                                         window across enforcement flanks.
#                                         Declared HERE, beside marker_fresh
#                                         itself (the one freshness
#                                         implementation every caller already
#                                         delegates to) — every flank now
#                                         imports this name rather than
#                                         restating the literal.
#   marker_fresh(path, minutes) -> bool   True iff marker file exists and is recent
#   write_text_atomic(path, text) -> None  crash-safe write (temp + os.replace)
#   acquire_lock(path) -> handle|None     OS-owned cross-process file lock (#271 C-2);
#                                         non-blocking + bounded LOCK_WAIT retry spin,
#                                         fail-soft None on contention/timeout/OSError
#   release_lock(handle) -> None          release + close; None handle is a no-op
#   block(tag, msg) -> None              BLOCK tool call: print to stderr and exit 2
#   remind(tag, msg) -> None             non-blocking nudge to stderr
#   warn(msg) -> None                    loud degradation breadcrumb to stderr
#   staleness_warning(root, now=None, window_minutes=30) -> list[str]
#                                         (CONFIRM-09) active-flow audit-log staleness
#                                         messages, WARN-only, never raises

import datetime
import errno
import json
import os
import re
import subprocess  # noqa: F401 — no longer used directly; kept so any external
#                     consumer referencing _hooklib.subprocess keeps resolving
import sys
import tempfile
import threading
import time

import hostapi

# Issue #321 - the H-09b/H-10b sensitive-line scan moved to _sensitivelib, the
# protected-path classifiers to _protectedlib, the H-14/H-15/H-16 scope
# detection to _scopelib, activation and the host/root caches to
# _activationlib, and the path primitives to the
# _pathnorm floor beneath both. Re-exported here, unchanged, so
# every one of the 59 consuming files keeps importing from _hooklib and the
# pre-existing suites prove parity without moving. New code SHOULD import from
# the owning module; this facade exists so the partition costs no caller a diff.
from _pathnorm import norm_path, repo_rel  # noqa: F401
from _activationlib import (  # noqa: F401
    # `_HOST` is deliberately ABSENT: importing a mutable global binds its VALUE,
    # so a later set_host() would rebind it in _activationlib and leave a stale
    # copy here forever. The accessors below all read and write that module's
    # global, so one cache is shared however a caller reached them. Verified that
    # nothing in the repo reads _hooklib._HOST directly.
    # `_reset_root_cache` is a FUNCTION and has a consumer (test_hooklib calls it
    # through `_hooklib.`), so it is re-exported: a function binding stays live.
    # `_ROOT_CACHE` and `_root_cache_key` have none and are dropped rather than
    # relocated.
    _reset_root_cache,
    ARBITER_RE,
    arbiter_active,
    frontmatter_enabled,
    frontmatter_enabled_text,
    get_host,
    marker_root,
    project_root,
    reset_host,
    set_host,
)
from _scopelib import (  # noqa: F401
    # The private names are re-exported too, deliberately. `_read_controls`,
    # `_glob_to_re` and the precompiled default tuples have real consumers
    # (test_hooklib reaches them through `_hooklib.`), and `_CONTROLS_CACHE` is
    # mutated in place rather than rebound, so sharing the binding shares the
    # cache correctly. Slice 1 taught this: an underscore prefix means "not
    # public", never "unused".
    _CI_DECL_RE,
    _CI_DEFAULT_RES,
    _CONTROLS_CACHE,
    _DEFAULT_RES_BY_GLOBS,
    _DEPLOY_DECL_RE,
    _DEPLOY_DEFAULT_RES,
    _MIG_DECL_RE,
    _MIGRATION_DEFAULT_RES,
    _controls_mtime,
    _custom_re_cache,
    _glob_to_re,
    _read_controls,
    _scope_res,
    CI_DEFAULT_GLOBS,
    DEPLOY_DEFAULT_GLOBS,
    MIGRATION_DEFAULT_GLOBS,
    is_ci_path,
    is_deploy_path,
    is_migration_path,
    migration_globs,
    path_in_globs,
    scope_globs,
)
from _protectedlib import (  # noqa: F401
    AUDIT_LOG_BASENAMES,
    AUDIT_LOG_FLAT_BASENAMES,
    AUDIT_LOG_NAMES,
    AUDIT_LOG_RE,
    CONTEXT_MD_RE,
    DECISIONS_DIR_RE,
    DECISIONS_PATH_RE,
    DECISION_LOG_BASENAME,
    DECISION_LOG_RE,
    GATE_MARKER_NAMES,
    MARKERS_RE,
    classify_protected,
    is_audit_log,
    is_context_md,
    is_decisions_path,
    is_marker_path,
    is_tail_append,
)
from _sensitivelib import (  # noqa: F401
    CRYPTO_RE,
    SECRET_RE,
    SECURITY_DIFF_GIT_ARGS,
    SENSITIVE_SCAN_EXEMPT_RELPATHS,
    content_digest,
    diff_added_lines,
    is_sensitive_scan_exempt,
    line_digest,
    sensitive_scan_added_lines,
)


# Serialize same-process Windows writers before taking the cross-process lock.
_GATE_EVENTS_WINDOWS_LOCK = threading.Lock()
_WINDOWS_LOCK_TIMEOUT_SECONDS = 5.0
_WINDOWS_LOCK_RETRY_SECONDS = 0.01
_WINDOWS_CRT_EDEADLK = 36

# Bounded best-effort wait for another cross-process writer to release
# acquire_lock()'s sidecar lock file (#271 C-2). Originally _ledgerlib-private
# (the statusline's cost/token ledger); hoisted here so taskwrite.py's board
# writer (a second, genuinely different caller) can share ONE lock
# implementation instead of a second hand-rolled copy. _ledgerlib re-exports
# this name (`from _hooklib import LOCK_WAIT`) so its own module-level
# mock.patch.object(L, "LOCK_WAIT", ...) test seam keeps working unchanged.
LOCK_WAIT = 0.2


def _is_lock_contention(exc):
    """True only for CRT/Windows byte-range lock conflict errors."""
    return (getattr(exc, "errno", None) in (errno.EACCES, _WINDOWS_CRT_EDEADLK) or
            getattr(exc, "winerror", None) in (32, 33))
















def utf8_stdio():
    """Force UTF-8 on stdout/stderr. Windows pipes default to the locale code
    page (cp1252), and ORCHESTRATOR.md contains non-cp1252 glyphs — without this
    the SessionStart injection dies with UnicodeEncodeError."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass






def read_input():
    """Parse the hook JSON from stdin.

    Deliberately fail-open on unreadable input: a malformed stdin payload must
    NOT brick the session by blocking every subsequent tool call. This is an
    explicit, documented exception to the fail-loud principle — the correct
    behaviour here is warn + allow, not warn + block.

    "Unreadable" covers a malformed SHAPE as well as malformed syntax
    (ADR-0020). A payload that is valid JSON but not an object — `[]`, `3`,
    `"str"`, `true`, `null` — parses cleanly and never reaches the except
    branch, so it used to be handed downstream as a non-dict: `tool_input()`
    evaluates `(data or {}).get(...)`, which makes the falsy ones accidentally
    safe and raises AttributeError out of the guard on the truthy ones. Both
    are normalized to `{}` here instead, at the one chokepoint that decides it.

    The distinction between the two failures carries no security content: the
    hook envelope is host-produced (Claude Code, Codex, Pi), not
    model-produced. A model can place hostile content INSIDE `tool_input`, but
    cannot make the top-level object a list — so a non-dict envelope means host
    misbehaviour or version drift, the same compatibility event the parse-error
    branch already rules on.
    """
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as e:  # noqa: BLE001 — any malformed input
        warn(f"hook input unparseable ({e}); proceeding without enforcement")
        return {}
    if not isinstance(data, dict):
        warn(f"hook input is a JSON {type(data).__name__}, not an object; "
             "proceeding without enforcement")
        return {}
    return data


def tool_input(data):
    return (data or {}).get("tool_input", {}) or {}










def write_text_atomic(path, text, newline=None):
    """Write `text` to `path` atomically: a sibling temp file in the same dir,
    then os.replace() into place (atomic on POSIX; a same-volume rename on
    Windows). A crash between open() and the rename never leaves a half-written
    file at `path`. The gate-marker writers (migration-pass / security-pass) rely
    on this so a partial digest set can't be read back as an unrecognized token
    and force a spurious gate re-run (migration-002). On any failure the temp
    file is cleaned up and the original `path` is left untouched.

    `newline` is passed through to open()/fdopen() unchanged (default None keeps
    the prior text-mode translation behaviour for existing callers); pass "\\n"
    to force LF output regardless of platform (e.g. for a canonical-EOL file)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def acquire_lock(path):
    """Acquire an OS-owned cross-process file lock keyed on `path`; process
    death releases it automatically (#271 C-2 — hoisted from the
    statusline-ledger-only `_ledgerlib._acquire_lock`, now shared with
    taskwrite.py's board writer).

    Sidecar lock file `f"{abspath(path)}.lock"`, opened `"a+b"` and seeded
    with one byte so the OS byte-range lock has a byte to lock (an empty file
    has no range to range-lock). Non-blocking (`msvcrt.locking(..., LK_NBLCK,
    1)` on Windows, `fcntl.flock(..., LOCK_EX | LOCK_NB)` elsewhere) with a
    bounded `LOCK_WAIT`-second retry spin; any `OSError` opening the lock file,
    or exhausting the deadline still contended, is FAIL-SOFT: returns `None`
    rather than raising or blocking indefinitely. Callers decide what
    "fail-soft" means for them — `_ledgerlib.ledger_update`/`persist_sess_start`
    treat `None` as a disposable no-op (a statusline render is throwaway), but
    `taskwrite.py` treats it as a hard error (a board write is NOT disposable;
    see its module docstring)."""
    lock_path = f"{os.path.abspath(path)}.lock"
    parent = os.path.dirname(lock_path)
    try:
        os.makedirs(parent, exist_ok=True)
        handle = open(lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
    except OSError:
        return None
    deadline = time.monotonic() + LOCK_WAIT
    while True:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except (OSError, BlockingIOError):
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(0.005)


def release_lock(handle):
    """Release + close a handle from acquire_lock(). None is a no-op —
    callers that never got the lock don't need to guard the release call."""
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            handle.close()
        except OSError:
            pass


# The H-11 authoring-marker freshness window (issue #567) — the single
# declaration every `marker_fresh(marker, minutes)` call site resolves by
# import. Previously five independent `30` literals (pre-write.py,
# pre-edit.py, _bashguardlib.py, git-enforce.py, _protectedstatelib.py) with
# no shared source, so a change to one never propagated to the others and
# nothing went red. All five call sites use this exact marker-freshness
# shape (a marker file minted immediately before a gated action and checked
# fresh at the point of use) with no documented reason to diverge, so this is
# ONE window, not several disguised as one.
MARKER_FRESHNESS_MINUTES = 30


def marker_fresh(path, minutes):
    """True if the marker file exists and was touched within `minutes`."""
    try:
        return os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < minutes * 60
    except Exception:  # noqa: BLE001
        return False


def _log_gate_event(kind, tag, msg):
    """Best-effort durable append of one gate decision to
    .codearbiter/gate-events.log (observability-001, issue #186) — the durable
    sink block()/remind()/warn() funnel every BLOCK/REMIND/WARN through, so a
    decision is no longer visible ONLY in the ephemeral per-turn stderr
    transcript.

    One line per event: `[ISO-8601Z] KIND [tag] host=<host> hook=<script> | msg`.
    `tag` may be None (warn() carries no tag) — the bracket is simply omitted
    then. `hook` is the invoking script's basename (`sys.argv[0]`), the one
    "which hook fired this" signal available at this shared layer without
    threading a new parameter through all 21 call sites across the 16 entry
    hooks. `host` is `get_host().name` ("claude"/"codex"/"unknown") — added
    for observability-001/ADR-0012: with three hosts now sharing one
    gate-events.log (ADR-0011), a line could not be attributed to the host
    that wrote it. Placed BEFORE `hook=` (both are `key=value` tokens with no
    internal whitespace, so the line stays trivially greppable/parseable by
    either field, and existing `hook=<script>` substring matches are
    unaffected).

    FAIL-OPEN BY CONTRACT (AC-2): this function must NEVER raise and must
    NEVER be allowed to change the caller's exit code or suppress its stderr
    output. A missing `.codearbiter/` dir, an unwritable/locked/missing log
    file, project_root() itself misbehaving, or host resolution itself
    misbehaving are ALL swallowed silently here — the ONE deliberate
    exception to this module's fail-loud discipline, mirroring the documented
    fail-open exception in read_input()."""
    try:
        root = project_root()
        cad = os.path.join(root, ".codearbiter")
        if not os.path.isdir(cad):
            return  # repo never opted in (no .codearbiter/) — nothing to append to
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        hook = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "-"
        try:
            host = get_host().name
        except Exception:  # noqa: BLE001 — host resolution must never break the sink
            host = "unknown"
        tag_part = f"[{tag}] " if tag else ""
        line = f"[{ts}] {kind} {tag_part}host={host} hook={hook} | {msg}\n"
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        process_lock_acquired = False
        if os.name == "nt":
            _GATE_EVENTS_WINDOWS_LOCK.acquire()
            process_lock_acquired = True
        fd = None
        os_lock_acquired = False
        try:
            fd = os.open(os.path.join(cad, "gate-events.log"), flags, 0o600)
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                lock_mode = getattr(msvcrt, "LK_NBLCK", msvcrt.LK_LOCK)
                lock_deadline = time.monotonic() + _WINDOWS_LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        msvcrt.locking(fd, lock_mode, 1)
                        os_lock_acquired = True
                        break
                    except OSError as exc:
                        if not _is_lock_contention(exc):
                            raise
                        if time.monotonic() >= lock_deadline:
                            raise
                        time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)
            os.write(fd, line.encode("utf-8"))
        finally:
            if os.name == "nt" and os_lock_acquired:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except Exception:  # noqa: BLE001 — outer sink remains fail-open
                    pass
            if process_lock_acquired:
                _GATE_EVENTS_WINDOWS_LOCK.release()
            if fd is not None:
                os.close(fd)
    except Exception:  # noqa: BLE001 — fail-open: the sink must never affect the gate
        pass


def block(tag, msg):
    """BLOCK the tool call: stderr is surfaced to Claude, exit 2."""
    _log_gate_event("BLOCK", tag, msg)
    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)
    sys.exit(2)


def remind(tag, msg):
    """Non-blocking nudge to stderr."""
    _log_gate_event("REMIND", tag, msg)
    print(f"REMINDER [{tag}]: {msg}", file=sys.stderr)


def warn(msg):
    """Loud degradation/diagnostic breadcrumb — never silent."""
    _log_gate_event("WARN", None, msg)
    print(f"codeArbiter hook: {msg}", file=sys.stderr)


# --- CONFIRM-09: audit-trail completeness staleness-warn ---------------------
# The H-05 guards above are INTEGRITY controls (a written audit line can't be
# rewritten/deleted) — they don't compel a write in the first place. This is
# the accepted-strategy (a) completeness half (security-controls.md § Audit
# trail, 2026-07-02): a lightweight WARN, never a gate, surfaced when an
# active long-running flow's marker has sat around past `window_minutes` with
# no matching activity in its expected audit log.
#
# Only /dev and /sprint have a persistent "in-progress" marker today
# (.codearbiter/.markers/dev-active and .codearbiter/sprint-active — the same
# state _arbiterstatelib.dev_active()/arbiter_state() already read). /override
# is a single synchronous action (announce-then-log in one turn, per
# override.md) with no analogous "still in progress" marker anywhere in the
# framework, so per CONFIRM-09's own "do not invent new state" constraint it
# is not tracked here — there is no existing signal to detect it from.
#
# #271 C-5: this staleness WARN is presence + age based (marker mtime vs. an
# audit-log write), which is unaffected by session-start.py's newer
# session-scoped CLEARING decision for the SAME dev-active marker — the two
# consumers ask different questions ("has this sat around too long with no
# matching log activity?" vs. "am I sure enough this belongs to nobody live
# right now that I should force-close it?") and neither needs to agree with
# the other's answer. A dev marker owned by a still-live different session
# can legitimately trip THIS warning (it really has been open a while) even
# though session-start.py correctly declines to clobber it.
_STALE_FLOWS = (
    # (flow name, marker path parts, expected-log path parts)
    ("dev", (".markers", "dev-active"), ("overrides.log",)),
    ("sprint", ("sprint-active",), ("sprint-log.md",)),
)


def staleness_warning(root, now=None, window_minutes=30):
    """(CONFIRM-09) One WARN message per active flow (see _STALE_FLOWS) whose
    marker has existed for at least `window_minutes` with no audit-log
    activity (marker touch OR log write) inside that same window. Returns []
    when nothing is stale (including when no flow is active at all).

    WARN-ONLY BY CONTRACT: this function only computes strings — it has no
    side effects, never calls warn()/block() itself, and can NEVER raise (any
    per-flow stat failure just skips that flow, exactly like marker_fresh's
    own degrade-to-False). The caller decides whether to surface the result,
    typically via warn(), which is itself non-blocking."""
    now = time.time() if now is None else now
    cad = os.path.join(root, ".codearbiter")
    messages = []
    for name, marker_parts, log_parts in _STALE_FLOWS:
        try:
            marker = os.path.join(cad, *marker_parts)
            if not os.path.isfile(marker):
                continue
            marker_mtime = os.path.getmtime(marker)
            if now - marker_mtime < window_minutes * 60:
                continue  # flow started too recently to call it stale yet
            log_path = os.path.join(cad, *log_parts)
            try:
                log_mtime = os.path.getmtime(log_path)
            except OSError:
                log_mtime = 0  # log never written at all -> definitely stale
            last_activity = max(marker_mtime, log_mtime)
            if now - last_activity >= window_minutes * 60:
                messages.append(
                    f"/{name} has been active for over {window_minutes} min with no "
                    f"matching {os.path.basename(log_path)} entry since — confirm the "
                    f"expected audit line landed (CONFIRM-09)."
                )
        except Exception:  # noqa: BLE001 — never raise; skip this flow, not the caller
            continue
    return messages
