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
import hashlib
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

# The loaded Host is process-cached: hooks are single-shot processes, and the
# host's identity cannot change mid-process (its methods read env/payload state
# live at call time, so caching the OBJECT changes no verdict).
_HOST = None

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


def get_host():
    """The process's Host instance (hostapi.load_host(), cached)."""
    global _HOST
    if _HOST is None:
        _HOST = hostapi.load_host()
    return _HOST


def set_host(host):
    """Dependency-injection seam (#257 architecture-001/performance-002).

    Primes the module-cached `_HOST` that `get_host()` reads. Every entry
    script's `run(host, argv=None)` calls this BEFORE `main()`, so the Host
    instance the `__main__` guard already resolved via `hostapi.load_host()`
    is the SAME object `get_host()` serves inside `main()` — closing two
    defects at once: (1) `main()` no longer triggers its own redundant
    `hostapi.load_host()` (a second `_host.py` load per invocation), and
    (2) `run(host)` stops silently ignoring its `host` argument — a test that
    calls `run(fake_host)` now genuinely exercises `fake_host`, not whatever
    `load_host()` resolves from disk. In production the injected host IS the
    `load_host()` result the guard already computed, so this changes no
    behavior — it only removes the redundant second load and makes the
    existing `run(host)` parameter live."""
    global _HOST
    _HOST = host


def reset_host():
    """Test-only: clear the injected/cached `_HOST` so the next `get_host()`
    lazy-loads afresh. Production hook processes are single-shot and never need
    this; but `set_host()` makes `_HOST` a process-lifetime singleton, so a test
    that calls `run(fake_host)` must reset it in tearDown — otherwise the fake
    leaks into any later in-process test that calls `get_host()` without its own
    patch, silently running against the wrong host and masking a gate
    regression (security review #257, LOW)."""
    global _HOST
    _HOST = None


# project_root() memoization (performance-001/003, #260). A hook is a
# single-shot process, so CLAUDE_PROJECT_DIR and the process cwd cannot
# change mid-process — but the resolved VALUE is cached keyed on those two
# inputs (not unconditionally) rather than as one bare value, so an env/cwd
# change is a cache MISS, never a stale hit. This keeps the production
# single-shot contract (the same hook process always sees an unchanging
# env/cwd, so it resolves at most once) while staying correct for the
# in-process integration-test harnesses that legitimately re-target
# project_root() across many fixtures/envs within one Python process
# (`python -m unittest discover` runs the whole suite in ONE interpreter —
# an unconditional single-value cache would leak the FIRST test's resolved
# root into every later test that calls project_root() or warn()/block()/
# remind() in-process). A payload's `cwd` is deliberately NOT part of the
# cache key: within one real hook process the payload is parsed at most once
# and never changes, so a payload-bearing call and a later no-payload call in
# the SAME (env, cwd) context are the SAME logical resolution and must return
# the SAME value — exactly the "payload-bearing first call, later no-arg
# calls stay consistent" contract. (A payload-only scenario — Codex, no
# CLAUDE_PROJECT_DIR — still resolves once: the first call's payload wins and
# is cached against the current (env, cwd); env/cwd don't change either.)
_ROOT_CACHE = {}


def _root_cache_key():
    return (os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd())


def _reset_root_cache():
    """Test-only: drop every memoized project_root() resolution. Production
    hook processes never need this (each is single-shot); integration tests
    that simulate MANY logical hook invocations in one Python process and
    need a resolution to be genuinely re-computed (rather than served from an
    still-valid (env, cwd) cache entry) call this between scenarios."""
    _ROOT_CACHE.clear()

# Crypto/TLS and secret patterns — shared by the post-write reminder (H-09/H-10)
# and the blocking pre-commit gate (H-09b/H-10b) so the two never drift.
# Deliberately NOT matched: crypto.randomUUID / crypto.getRandomValues (benign
# ID generation tripped the gate on routine commits) — the bare `crypto\.`
# catch-all is narrowed to the members that actually sign, encrypt, derive
# keys, or produce security-relevant randomness. bcrypt stays: approved or
# not, a password-hashing change is exactly what crypto-compliance reviews.
CRYPTO_RE = re.compile(
    r"(createHash|createCipher|createHmac|\bmd5\b|\bsha1\b|\brc4\b|\bdes\b|3des"
    r"|\brc2\b|\bblowfish\b"
    r"|\bRSA\b|x509|bcrypt"
    r"|crypto\.(subtle|sign|verify|createSign|createVerify|generateKey"
    r"|publicEncrypt|privateDecrypt|pbkdf2|scrypt|randomBytes|createDiffieHellman)"
    r"|InsecureSkipVerify|verify=False"
    # Node/TS TLS-disable forms — all networked first-party code here is TS, so
    # this is where a verification bypass would actually land (2026-06-22 HIGH).
    r"|rejectUnauthorized\s*[:=]\s*false|NODE_TLS_REJECT_UNAUTHORIZED)",
    re.I,
)
# Two branches: (1) a secret keyword assigned a quoted literal, via `=` OR `:`
# (the colon/object form dominates this TS/JSON repo) — the quoted-value
# requirement keeps it from firing on every bare `token:` reference; (2) known
# high-entropy key prefixes, keyword-independent (AWS / GitHub / Anthropic).
# No LEADING word boundary on the keyword group (secrets-002): a `\b` there
# never fires when the keyword is the trailing segment of a compound identifier
# (the char left of `api_key` in `FARM_API_KEY` is `_`, a word char), so a
# hardcoded `FARM_API_KEY = "..."` silently passed the gate. The right-hand
# quoted-assignment anchor still bounds the match — a bare `token:` reference
# without a quoted value never matches.
SECRET_RE = re.compile(
    r"(?:password|secret|token|api_key|apikey|private_key|passphrase|credential"
    r"|aws_secret_access_key|client_secret)"
    r"""["']?\s*[:=]\s*["'][^"']{4,}"""
    r"|AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{36}"
    r"|sk-ant-[A-Za-z0-9_-]{16,}",
    re.I,
)


ARBITER_RE = re.compile(r"^\s*arbiter:\s*enabled\s*$", re.I)

# Append-only audit logs (H-05) and ADR-decisions paths (H-11) — centralized
# here (architecture-004) so the three pre-* hooks import ONE definition instead
# of re-encoding the regex inline (the exact drift this module exists to
# prevent: adding sprint-log.md once meant hand-editing every copy). Same home,
# same rationale, as CRYPTO_RE/SECRET_RE/MIGRATION_DEFAULT_GLOBS.
#
# AUDIT_LOG_NAMES is the bare filename alternation; pre-bash.py composes its
# shell LOG_NAMES from it, and AUDIT_LOG_RE anchors it under .codearbiter/ for
# the Write/Edit file-path guards. DECISIONS_DIR_RE is the separator-tolerant
# decisions directory token; pre-bash.py composes its shell DECISIONS from it,
# and DECISIONS_PATH_RE extends it to a full ADR file path. `[\\/]+` matches the
# norm_path'd `/` as well as a raw backslash, so both the file-path and shell
# flanks derive from one source.
#
# gate-events.log (observability-001, #186) joins this set: it is the durable,
# mechanical BLOCK/REMIND/WARN sink block()/remind()/warn() append to below —
# an append-only audit artifact exactly like the other three, so it gets the
# SAME H-05 tool-call protection (Write/Edit + shell) for free via this one
# alternation, with no separate guard to maintain. Note this protects it only
# from Write/Edit/Bash TOOL CALLS; the hooks' own os-level `open(..., "a")`
# append (below) is plain file I/O, never a tool call, so H-05 never gates it.
#
# AUDIT_LOG_BASENAMES is the single authoritative list of bare filenames — the
# ONE place a new audit log gets added. pre-bash.py's H-05 shell guard needs
# these as plain strings too (a cheap `n in cmd` substring pre-filter before
# running the regexes below), so it imports this tuple directly instead of
# re-deriving/hand-copying the name set (the exact drift this centralization
# exists to prevent — a filter that silently skips a future audit log because
# its literal name was never added to a second, hand-maintained copy).
# AUDIT_LOG_NAMES is built FROM this tuple (re.escape'd, alternated) — behavior
# is unchanged from the prior hand-written pattern (same four literal
# filenames, same (?:...) grouping), only the source of truth moved.
AUDIT_LOG_BASENAMES = ("overrides.log", "triage.log", "gate-events.log", "sprint-log.md")
AUDIT_LOG_NAMES = "(?:" + "|".join(re.escape(n) for n in AUDIT_LOG_BASENAMES) + ")"
AUDIT_LOG_RE = re.compile(r"\.codearbiter/" + AUDIT_LOG_NAMES + r"$")
DECISIONS_DIR_RE = r"\.codearbiter[\\/]+decisions"
DECISIONS_PATH_RE = re.compile(DECISIONS_DIR_RE + r"[\\/]+.+\.md$")

# The activation file (#159) and the gate-marker store (#160). CONTEXT.md is the
# master switch every hook gates on via arbiter_active(); .markers/ holds the
# gate-pass tokens (security-gate-passed, migration-gate-passed,
# adr-authoring-active). Both were writable project state with no Write/Edit
# guard — the token strings are centralized here beside the audit-log/decisions
# sets so the pre-* hooks import ONE definition (same anti-drift rationale).
CONTEXT_MD_RE = re.compile(r"\.codearbiter/CONTEXT\.md$")
MARKERS_RE = re.compile(r"\.codearbiter/\.markers(?:/|$)")
# The two load-bearing gate-pass markers a commit gate consumes (H-09b/H-10b,
# H-14). Their bare filenames feed pre-bash.py's shell flank — these are NEVER
# legitimately shell-written (the sanctioned producers are the python
# security-pass.py / migration-pass.py helpers), unlike adr-authoring-active
# which /adr legitimately `touch`es.
GATE_MARKER_NAMES = r"(?:security-gate-passed|migration-gate-passed)"


def is_audit_log(rel):
    """True iff `rel` is one of the append-only .codearbiter audit logs
    (overrides.log, triage.log, sprint-log.md, gate-events.log) — the H-05
    guard set."""
    return bool(AUDIT_LOG_RE.search(norm_path(rel)))


def is_tail_append(current, old, new):
    """True iff an Edit's (old_string, new_string) pair is a verifiable,
    TAIL-ANCHORED pure append against `current` (the file's REAL on-disk
    content) — the H-05 guard (reliability-003, #172).

    `new.startswith(old)` alone is not sufficient: `old` could be any interior
    line that happens to be a prefix of `new`, which inserts content BETWEEN
    existing lines rather than appending at the end. This requires TWO things:
    `current` must literally END with `old` (old_string is the file's actual
    trailing content, not just some substring elsewhere), and `new` must
    extend `old`. An empty `old` is never a valid append — every string
    "ends with" the empty string, so the tail-anchor check would trivially
    pass and reopen the migration-003 empty-old_string hole this closes.

    `old` must also occur EXACTLY ONCE in `current`: a non-unique old_string
    that happens to also match the tail is not self-evidently an append — this
    keeps the guard correct on its own terms rather than depending on the Edit
    tool's own (client-side, not re-verified here) uniqueness enforcement for
    a non-replace_all Edit."""
    if not old:
        return False
    if current.count(old) != 1:
        return False
    return current.endswith(old) and new.startswith(old)


def is_decisions_path(rel):
    """True iff `rel` is a `.md` ADR anywhere under .codearbiter/decisions/ —
    the H-11 guard set (a non-numbered draft or a nested path still counts)."""
    return bool(DECISIONS_PATH_RE.search(norm_path(rel)))


def is_context_md(rel):
    """True iff `rel` is the .codearbiter/CONTEXT.md activation file (#159) —
    the master switch arbiter_active() reads. Guarded so it can't be flipped to
    `arbiter: disabled` (or corrupted) to make every enforcement hook dormant."""
    return bool(CONTEXT_MD_RE.search(norm_path(rel)))


def is_marker_path(rel):
    """True iff `rel` is anywhere under .codearbiter/.markers/ (#160) — the
    gate-pass token store. Load-bearing markers turn a BLOCK into an allow, so a
    hand-written marker must not be admitted by the Write/Edit tools."""
    return bool(MARKERS_RE.search(norm_path(rel)))


def classify_protected(fpath, root):
    """The set of protected classes a Write/Edit `fpath` targets, resolving
    symlinks (#162). Each classifier runs against BOTH the raw normalized path
    AND the realpath-resolved repo-relative form: a symlink alias whose visible
    path lacks `.codearbiter/` still realpaths back inside the repo, so an alias
    can no longer launder a write past the guard. Centralized so pre-write.py and
    pre-edit.py apply the identical symlink-safe check to every class (H-05,
    H-11, #159 CONTEXT.md, #160 markers) instead of re-encoding it twice.

    Classes: "audit", "decisions", "context", "marker". repo_rel() returns "" for
    a target outside the repo (which cannot be a `.codearbiter` path), so that
    flank is simply skipped."""
    hits = set()
    for p in (norm_path(fpath), repo_rel(fpath, root)):
        if not p:
            continue
        if is_audit_log(p):
            hits.add("audit")
        if is_decisions_path(p):
            hits.add("decisions")
        if is_context_md(p):
            hits.add("context")
        if is_marker_path(p):
            hits.add("marker")
    return hits


# Sensitive-scan exemption (H-09b/H-10b, #279). gate-events.log is the durable
# BLOCK/REMIND/WARN sink block()/remind()/warn() append to (observability-001,
# #186) — it is machine-written, never source code, and structurally
# guaranteed to echo the crypto/secret detector's OWN message text back at
# itself the moment the gate ever fires a crypto/secret REMIND (e.g. "Crypto/
# TLS pattern detected" itself matches CRYPTO_RE). That makes it a permanent,
# self-perpetuating false positive with zero disclosure value: nothing
# written there is a genuine crypto/secret USE, only a report ABOUT one.
# Deliberately narrow — overrides.log/triage.log/sprint-log.md stay IN SCOPE:
# they carry human-written prose (an override reason, a triage note) that
# COULD legitimately contain a leaked secret worth catching. This set is
# anchored on the REPO-RELATIVE PATH a line belongs to, never a substring
# match on the line's own text — a secret cannot escape the scan by merely
# mentioning gate-events.log on its line; only lines that actually LIVE in
# that file are exempt.
SENSITIVE_SCAN_EXEMPT_RELPATHS = frozenset({".codearbiter/gate-events.log"})


def is_sensitive_scan_exempt(rel):
    """True iff `rel` (a repo-relative path, as attributed by `diff_added_
    lines` or as returned by a bare `git ls-files` listing) names a file
    exempt from the H-09b/H-10b crypto/secret scan. The ONE predicate both
    the diff walk and the untracked/unborn-branch file listings route
    through (#279 review LOW) — deliberately strict: no case-folding, no
    `./`/`//` collapsing. An identifier that isn't an exact, `norm_path`'d
    match resolves toward IN SCOPE (not exempt), which is the safe
    direction. See SENSITIVE_SCAN_EXEMPT_RELPATHS."""
    return norm_path(rel) in SENSITIVE_SCAN_EXEMPT_RELPATHS


# Every H-09b/H-10b sensitive-line reader (security-pass.py, pre-bash.py,
# git-enforce.py) MUST run `git diff` through this pinned argv, never a bare
# `["diff", ...]` (#279 review MEDIUM-1). Two independent user/global git
# config knobs change the destination-path prefix `diff_added_lines` below
# depends on: `diff.mnemonicPrefix=true` emits `c/`/`w/`/`i/`/`o/` instead of
# `a/`/`b/`, and `diff.noprefix=true` emits no prefix at all. Either one, left
# unpinned, silently un-exempts the REAL gate-events.log for any dev/CI runner
# with that config set — bringing back the exact self-DoS this whole change
# exists to close. `-c` overrides win over any config file (including repo,
# global, and system config), so pinning both flags to false here forces the
# standard `a/`/`b/` prefixes regardless of the caller's environment.
# `--no-ext-diff` additionally blocks a configured `GIT_EXTERNAL_DIFF` /
# `diff.external` from replacing git's own unified-diff output with something
# this parser was never designed to read. Centralized so a call site cannot
# forget to pin it (that was exactly how this hole would keep reopening).
SECURITY_DIFF_GIT_ARGS = (
    "-c", "diff.mnemonicPrefix=false", "-c", "diff.noprefix=false",
    "diff", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/",
)

# The fixed-width destination-path prefix `diff_added_lines` strips off a
# preamble `+++ ` line. MUST be a fixed-length slice, never a search for a
# separator: a greedy/`.+`-based parse of "diff --git a/<path> b/<path>" (the
# prior approach) resolves ambiguously when <path> itself contains " b/" —
# e.g. a real repo path `x b/.codearbiter/gate-events.log` renders that
# header as `diff --git a/x b/.codearbiter/gate-events.log b/x
# b/.codearbiter/gate-events.log`, and a greedy match backtracks group(1) to
# `.codearbiter/gate-events.log`, exempting the WHOLE unrelated source file
# (#279 review HIGH — reproduced end-to-end: an md5() call and a committed
# password both passed H-09b with no marker). Stripping a FIXED 6-character
# prefix has no such ambiguity: `"+++ b/x b/.codearbiter/gate-events.log"[6:]`
# is unconditionally `"x b/.codearbiter/gate-events.log"`, the correct full
# path, no matter what the path itself contains.
_PLUS_B_PREFIX = "+++ b/"
_PLUS_DEV_NULL = "+++ /dev/null"


def diff_added_lines(diff_text):
    """Added (`+`) lines of a unified `git diff`-style text (produced via
    SECURITY_DIFF_GIT_ARGS — pinned `a/`/`b/` prefixes, no external diff), as
    `(path, line)` tuples — a PATH-AWARE walk so a caller can exclude lines by
    the FILE they live in, never by matching the line's own text (which a
    hidden secret could otherwise dodge by naming the excluded file).

    Two-phase state machine per file section, `path`/`in_hunk`/`seen_section`:

    1. A bare, UNPREFIXED `diff ` line (`diff --git`, `diff --cc`, `diff
       --combined`, ...) starts a new section: `path` resets to `None` and
       `in_hunk` resets to False. Content can NEVER forge this line at column
       0 — every diff-body line (context/added/removed) carries a leading
       ' '/'+'/'-'/'\\' character, so a file whose own content is literally
       "diff --git a/x b/y" renders as "+diff --git a/x b/y" (added), never as
       a bare match. Resetting `path` to None (not inheriting the PREVIOUS
       section's path) on ANY `diff ` spelling matters for combined/merge
       diffs (#279 review MEDIUM-2): git-enforce.py's `git diff --cached` at a
       merge commit emits `diff --cc <path>` sections, which the prior
       `diff --git`-only reset missed, letting a `--cc` section's added lines
       silently inherit whatever path the section before it had — failing
       toward EXEMPTION if that was gate-events.log.
    2. While NOT yet `in_hunk` (the section's preamble, before its first `@@`
       / `@@@` hunk header), a `+++ b/<path>` line sets `path` by stripping
       the FIXED 6-character prefix `_PLUS_B_PREFIX` — never a regex search
       for a separator (see `_PLUS_B_PREFIX`'s comment for the ambiguity a
       greedy `diff --git` parse had). `+++ /dev/null` (a deleted
       destination) sets `path` back to None explicitly — no added lines are
       expected in a deletion's hunk body anyway. Every other preamble line
       (`--- a/<path>`, `index ...`, `new/deleted file mode`, `rename
       from/to`, `similarity index`, `Binary files ... differ`) is inert
       noise. A `+++ b/...`-shaped line can ONLY be trusted here, before the
       section's first `@@`: once `in_hunk` is True, an apparently identical
       `+++ b/...` string is body CONTENT (it carries the hunk body's own
       leading `+`, i.e. the underlying source line was "++ b/..." or "+++
       b/..." before diff-prefixing) and is captured as an added line like any
       other, never re-parsed as an attribution header (closes the #279
       review's own earlier finding: an added content line forging `+++
       b/<path>` used to hijack attribution for the rest of the file).
    3. Once `in_hunk`, `+`-prefixed lines are collected as `(path, content)`;
       `-`/` `/`\\` (no-newline-marker) lines are skipped; anything else ends
       the hunk (not producible by well-formed `git diff` output there, but
       handled rather than guessed at).

    FAILS SAFE: a `+` line seen before ANY `diff ` section header at all (not
    producible by real `git diff` output) is attributed to `path=None` and
    STILL COLLECTED, never silently dropped. `sensitive_scan_added_lines`
    treats an unattributed (`None`) path as NOT exempt — in scope for
    scanning. Exempting, or discarding, an unattributable line would be the
    dangerous direction; over-scanning only risks a false positive, the
    harmless failure mode here.

    The shared primitive behind the H-09b/H-10b crypto/secret gate's producer
    (security-pass.py) and both consumers (pre-bash.py, git-enforce.py) —
    implemented once here so the gate-events.log exemption can never drift
    between the three independent line-collectors that used to each do their
    own flat `[ln[1:] for ln in text.splitlines() if ln.startswith("+") ...]`
    walk with no path information (and no forgery-resistance) at all."""
    path = None
    in_hunk = False
    seen_section = False  # True once the first `diff ` section header is seen
    out = []
    for line in diff_text.splitlines():
        if line.startswith("diff "):
            path = None
            in_hunk = False
            seen_section = True
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            if not seen_section:
                # No `diff ` section header seen yet at all: not producible
                # by real `git diff` output. Fail SAFE (see docstring) rather
                # than silently dropping a line that cannot be confidently
                # classed as header noise either.
                if line.startswith("+"):
                    out.append((None, line[1:]))
                continue
            # Section preamble: only a genuine `+++ b/<path>` (or `+++
            # /dev/null`) line here can set `path` — see point 2 above.
            if line.startswith(_PLUS_B_PREFIX):
                path = line[len(_PLUS_B_PREFIX):]
            elif line == _PLUS_DEV_NULL:
                path = None
            continue
        if line.startswith("+"):
            out.append((path, line[1:]))
        elif line.startswith(("-", " ", "\\")):
            pass  # removed / context / "\ No newline at end of file"
        else:
            # Not producible by well-formed `git diff` output (a hunk body
            # line is always one of the four prefixes above); treat it as the
            # hunk having ended rather than guessing.
            in_hunk = False
    return out


def sensitive_scan_added_lines(diff_text):
    """`diff_added_lines(diff_text)` narrowed to the H-09b/H-10b crypto/secret
    scan's candidate set: every added line EXCEPT those belonging to a
    sensitive-scan-exempt path (currently only gate-events.log). Call this
    instead of a raw `+`-line filter anywhere the crypto/secret scan reads a
    diff, so the exemption is applied uniformly."""
    return [ln for path, ln in diff_added_lines(diff_text)
            if not (path and is_sensitive_scan_exempt(path))]


def utf8_stdio():
    """Force UTF-8 on stdout/stderr. Windows pipes default to the locale code
    page (cp1252), and ORCHESTRATOR.md contains non-cp1252 glyphs — without this
    the SessionStart injection dies with UnicodeEncodeError."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def norm_path(p):
    """Normalize separators so guard regexes match Windows backslash paths."""
    return (p or "").replace("\\", "/")


def frontmatter_enabled_text(text):
    """(enabled, malformed) for CONTEXT.md *content* (see frontmatter_enabled).
    Split out so the #159 Write/Edit guard can vet the RESULTING content of an
    edit — 'does this edit keep the repo arbiter-enabled?' — without going to
    disk, sharing one parser with the on-disk activation check so the two never
    disagree on what 'enabled' means."""
    lines = (text or "").split("\n")
    if not lines:
        return (False, False)
    first = lines[0].lstrip("﻿")  # tolerate a leading UTF-8 BOM
    if first.strip() != "---":
        return (False, False)  # no opening delimiter — dormant, not malformed
    found = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            return (found, False)  # closing delimiter — decision is final
        if ARBITER_RE.match(ln):
            found = True
    return (False, True)  # opened but never closed — malformed


def frontmatter_enabled(ctx_path):
    """Return (enabled, malformed) for CONTEXT.md ON DISK. `enabled` iff
    `arbiter: enabled` appears in a properly-closed leading YAML frontmatter
    block. `malformed` iff a block opens (`---` on line 1) but never closes — the
    fail-loud case. A file with no frontmatter at all is simply dormant (not
    malformed). Unreadable file -> (False, False)."""
    try:
        with open(ctx_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        return (False, False)
    return frontmatter_enabled_text(text)


def arbiter_active(root):
    """True iff this repo opted in (`arbiter: enabled` in CONTEXT.md frontmatter).
    Every enforcement hook gates on this so the plugin is genuinely dormant in
    repos that never opted in — the plugin.json activation contract."""
    enabled, _ = frontmatter_enabled(os.path.join(root, ".codearbiter", "CONTEXT.md"))
    return enabled


def read_input():
    """Parse the hook JSON from stdin.

    Deliberately fail-open on parse error: a malformed stdin input must NOT
    brick the session by blocking every subsequent tool call. This is an
    explicit, documented exception to the fail-loud principle — the correct
    behaviour here is warn + allow, not warn + block.
    """
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:  # noqa: BLE001 — any malformed input
        warn(f"hook input unparseable ({e}); proceeding without enforcement")
        return {}


def tool_input(data):
    return (data or {}).get("tool_input", {}) or {}


def project_root(payload=None):
    """The project root. `CLAUDE_PROJECT_DIR` is the harness's own authoritative
    signal and is trusted first: a hook subprocess is not guaranteed to start
    with the project directory as its cwd, and a `git rev-parse` from elsewhere
    can resolve to a different repo entirely (e.g. the plugin's own marketplace
    clone). The env-first read also saves one git spawn per hook invocation.
    Test harnesses that spawn hooks into fixture repos must pin the variable to
    the fixture, as the production harness pins it to the project.

    The resolution itself lives on the Host seam (hostapi.Host.project_root,
    ADR-0011) — this function keeps its public signature (now accepting an
    optional `payload`, architecture-006/#260, so a caller that already has
    the parsed hook payload can hand it through to the payload-cwd leg) and
    delegates, so every existing no-arg caller/import keeps working unchanged.

    Memoized per (CLAUDE_PROJECT_DIR, process cwd) — see _ROOT_CACHE above for
    the full contract (performance-001/003, #260): at most one resolution
    (and at most one git spawn) per that key, so the repeated project_root()
    reads inside block()/remind()/warn()'s gate-event logging don't each pay
    a fresh subprocess."""
    key = _root_cache_key()
    if key not in _ROOT_CACHE:
        _ROOT_CACHE[key] = get_host().project_root(payload)
    return _ROOT_CACHE[key]


def repo_rel(fpath, root):
    """Repo-relative POSIX path for `fpath`, or "" when it lies outside `root`.

    realpath BOTH sides before relpath: `git rev-parse --show-toplevel`
    (project_root) canonicalizes symlinks and 8.3 short names, but the
    `file_path` in a hook payload may not — so on macOS (TMPDIR `/var` ->
    `/private/var`) and Windows (`RUNNER~1` -> `runneradmin`) the two name the
    same repo via divergent forms. A purely lexical relpath on those forms
    yields a bogus `..`-prefixed path, which silently suppressed every
    path-scoped reminder (#125 CI: H-12/H-15/H-16/H-13 dropped on macOS +
    Windows runners while ubuntu passed)."""
    if not fpath:
        return ""
    rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(root))
    rel = rel.replace(os.sep, "/")
    return "" if rel == ".." or rel.startswith("../") else rel


def line_digest(line):
    """Digest of one added diff line, for the security-gate binding
    (H-09b/H-10b). The gate-pass marker stores these digests instead of being
    an empty `touch`d file, so a recorded pass admits only the exact sensitive
    lines it reviewed — not whatever lands in the next 30 minutes. Trailing
    whitespace is stripped so CRLF translation between worktree and index
    never breaks the match."""
    return hashlib.sha256(line.rstrip().encode("utf-8", "replace")).hexdigest()


def content_digest(text):
    """Digest of a whole migration file's content, for the H-14 migration-gate
    binding. Lines are rstripped and rejoined with \\n so CRLF translation
    between worktree and index never breaks the match (same rationale as
    line_digest). The producer (migration-pass.py) and the backstop
    (pre-bash.py) both digest worktree content this way, so the two never
    disagree on what a recorded pass covers."""
    norm = "\n".join(line.rstrip() for line in text.splitlines())
    return hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()


# Migration-path detection (H-14). Shared by migration-pass.py (the producer)
# and pre-bash.py (the backstop) so the two never drift on what counts as a
# migration. Default globs cover the common ORM/migration ecosystems; a project
# extends or narrows the set via a `migration-paths` block in
# security-controls.md. `**` matches any run of path segments (including none);
# `*`/`?` stay within one segment.
MIGRATION_DEFAULT_GLOBS = (
    "**/migrations/**",
    "**/migrate/**",
    "**/db/migrate/**",
    "**/alembic/versions/*.py",
    "**/prisma/migrations/**",
)
_MIG_DECL_RE = re.compile(
    r"<!--\s*migration-paths\s*-->(.*?)<!--\s*/migration-paths\s*-->", re.S | re.I)

# CI/CD workflow detection (H-15, #73). Advisory only — no commit gate; the
# defaults cover the common CI ecosystems and a project extends/narrows them via
# a `ci-paths` block in security-controls.md (same `+`/`-` grammar as migrations).
CI_DEFAULT_GLOBS = (
    ".github/workflows/**",
    ".circleci/**",
    "**/.gitlab-ci.yml",
    "**/Jenkinsfile",
    "**/azure-pipelines.yml",
    "**/bitbucket-pipelines.yml",
)
_CI_DECL_RE = re.compile(
    r"<!--\s*ci-paths\s*-->(.*?)<!--\s*/ci-paths\s*-->", re.S | re.I)

# Deployment / IaC detection (H-16, #73). Advisory only. Defaults cover the
# common container/orchestration/IaC manifests; extend/narrow via a
# `deploy-paths` block in security-controls.md.
DEPLOY_DEFAULT_GLOBS = (
    "**/Dockerfile",
    "**/Dockerfile.*",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/*.tf",
    "**/*.tfvars",
    "**/k8s/**",
    "**/helm/**",
    "**/kustomization.yaml",
    "**/kustomization.yml",
    "**/Procfile",
)
_DEPLOY_DECL_RE = re.compile(
    r"<!--\s*deploy-paths\s*-->(.*?)<!--\s*/deploy-paths\s*-->", re.S | re.I)


def _glob_to_re(glob):
    """Compile a forward-slash glob into a full-path regex. `**/` is an optional
    run of leading segments, `**` is any chars, `*`/`?` stay within a segment."""
    g = norm_path(glob)
    out, i = ["^"], 0
    while i < len(g):
        if g[i:i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif g[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        elif g[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


# performance-002: the DEFAULT glob tuples are module constants, so compile each
# to a regex ONCE at module load instead of per glob per path_in_globs() call.
# A single post-write-edit.py invocation otherwise recompiled up to 44 regexes
# (5 migration + 6 CI + 11 deploy x the calls that hit them). These compiled
# tuples line up 1:1 with their string tuples; the matcher uses them directly
# for the defaults and only compiles the per-controls custom globs on demand.
_MIGRATION_DEFAULT_RES = tuple(_glob_to_re(g) for g in MIGRATION_DEFAULT_GLOBS)
_CI_DEFAULT_RES = tuple(_glob_to_re(g) for g in CI_DEFAULT_GLOBS)
_DEPLOY_DEFAULT_RES = tuple(_glob_to_re(g) for g in DEPLOY_DEFAULT_GLOBS)

# Map each default string tuple to its precompiled regex tuple, so the matcher
# can look up the right precompiled set from the `defaults` argument alone
# (preserving the existing public signatures of scope_globs/path_in_globs).
_DEFAULT_RES_BY_GLOBS = {
    MIGRATION_DEFAULT_GLOBS: _MIGRATION_DEFAULT_RES,
    CI_DEFAULT_GLOBS: _CI_DEFAULT_RES,
    DEPLOY_DEFAULT_GLOBS: _DEPLOY_DEFAULT_RES,
}


# performance-001: hooks are EPHEMERAL single-shot processes (one invocation
# then exit), so a module-level cache lives for exactly one invocation — there
# is NO cross-invocation persistence. Within that one process, scope_globs reads
# security-controls.md on every is_migration_path/is_ci_path/is_deploy_path call
# (2-3 reads per hook). Cache the controls text keyed by (root, mtime) so a hit
# skips the read; the mtime key keeps it correct even on an intra-process change
# (the file is re-read when its mtime moves), and keys the absent-file state too.
_CONTROLS_CACHE = {}


def _controls_mtime(root):
    """mtime of `root`'s security-controls.md, or None when absent/unreadable.
    The cache key — distinct mtimes (and the None absent-state) bust the cache."""
    try:
        return os.path.getmtime(
            os.path.join(root, ".codearbiter", "security-controls.md"))
    except Exception:  # noqa: BLE001 — no controls file -> None (defaults only)
        return None


def _read_controls(root):
    """The repo's security-controls.md text, or "" when absent/unreadable.

    Process-cached keyed by (root, mtime): a cache hit skips the file read, and
    the mtime component invalidates the entry whenever the file changes (or is
    created/removed), so verdicts are unchanged. Single-shot hook process only —
    no cross-invocation persistence."""
    mtime = _controls_mtime(root)
    key = (root, mtime)
    cached = _CONTROLS_CACHE.get(key)
    if cached is not None:
        return cached[0]
    try:
        with open(os.path.join(root, ".codearbiter", "security-controls.md"),
                  encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001 — no controls file -> defaults only
        text = ""
    # Cache the text AND the compiled custom globs per scope (filled lazily by
    # scope_globs) under the same mtime key, so a custom-glob set compiles at
    # most once per (root, mtime) instead of once per path_in_globs() call.
    _CONTROLS_CACHE[key] = (text, {})
    return text


def _custom_re_cache(root):
    """The per-(root, mtime) dict that caches compiled custom-glob regexes for
    this controls revision. Populated lazily by scope_globs. Returns a throwaway
    dict only if the controls entry is somehow missing (defensive; the read
    above always seeds it first)."""
    entry = _CONTROLS_CACHE.get((root, _controls_mtime(root)))
    return entry[1] if entry is not None else {}


def scope_globs(root, defaults, decl_re):
    """(includes, excludes) for one scope category: the built-in `defaults` plus
    any declaration block matched by `decl_re` in security-controls.md
    (`+ glob` extends, `- glob` excludes). Shared by every path-glob scope
    detector (migration/CI/deploy) so they never drift on the grammar."""
    includes, excludes = list(defaults), []
    m = decl_re.search(_read_controls(root))
    if not m:
        return includes, excludes
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if ln.startswith("+ "):
            includes.append(ln[2:].strip())
        elif ln.startswith("- "):
            excludes.append(ln[2:].strip())
    return includes, excludes


def _scope_res(root, defaults, decl_re):
    """(include_res, exclude_res) as compiled regexes for one scope category.
    Default globs use the module-precompiled regexes (zero per-call compilation);
    any per-controls custom globs are compiled at most once per (root, mtime) and
    cached. Equivalent to compiling each string from scope_globs() — verdicts are
    identical; only the regex work is amortised."""
    includes, excludes = scope_globs(root, defaults, decl_re)
    default_res = _DEFAULT_RES_BY_GLOBS.get(defaults)
    if default_res is None:
        # Unknown defaults set (no precompiled tuple) — compile everything.
        return ([_glob_to_re(g) for g in includes],
                [_glob_to_re(g) for g in excludes])
    # Defaults occupy the head of `includes` (scope_globs builds list(defaults)
    # then appends customs); reuse the precompiled regexes for that head and
    # compile only the trailing customs. Excludes are all custom.
    custom_cache = _custom_re_cache(root)

    def _compile(g):
        r = custom_cache.get(g)
        if r is None:
            r = _glob_to_re(g)
            custom_cache[g] = r
        return r

    n = len(defaults)
    include_res = list(default_res) + [_compile(g) for g in includes[n:]]
    exclude_res = [_compile(g) for g in excludes]
    return include_res, exclude_res


def path_in_globs(rel, root, defaults, decl_re):
    """True iff `rel` (a repo-relative path) matches an include glob and no
    exclude glob for the given scope category. Excludes win — the false-positive
    escape hatch. The one matcher behind is_migration_path/is_ci_path/
    is_deploy_path."""
    rel = norm_path(rel).lstrip("/")
    include_res, exclude_res = _scope_res(root, defaults, decl_re)
    if any(r.match(rel) for r in exclude_res):
        return False
    return any(r.match(rel) for r in include_res)


def migration_globs(root):
    """(includes, excludes) for migration detection: defaults plus any
    `migration-paths` declaration in security-controls.md."""
    return scope_globs(root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_migration_path(rel, root):
    """True iff `rel` is a database migration (H-14). Excludes win — the
    escape hatch for a project whose `migrations/` dir holds non-DB files."""
    return path_in_globs(rel, root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_ci_path(rel, root):
    """True iff `rel` is a CI/CD workflow file (H-15, advisory)."""
    return path_in_globs(rel, root, CI_DEFAULT_GLOBS, _CI_DECL_RE)


def is_deploy_path(rel, root):
    """True iff `rel` is a deployment / IaC manifest (H-16, advisory)."""
    return path_in_globs(rel, root, DEPLOY_DEFAULT_GLOBS, _DEPLOY_DECL_RE)


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
    for observability-001/ADR-0012: with two hosts now sharing one
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
