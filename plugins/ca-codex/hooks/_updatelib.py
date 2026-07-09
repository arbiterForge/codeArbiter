#!/usr/bin/env python3
# codeArbiter — update-available notifier: shared cache/compare/fetch logic.
#
# codeArbiter ships via a third-party marketplace, which Claude Code does NOT
# auto-update by default (only official Anthropic marketplaces get that). This
# module backs a lightweight notifier so a stale install is surfaced instead of
# running forever unnoticed: it reads the installed plugin.json version, reads
# a small user-global cache of the latest published GitHub release, and — when
# the cache says a newer version exists — hands back a single notice line. Both
# SessionStart and the statusline render from that SAME cache; neither makes a
# network call on its own hot path (issue #194's constraint).
#
# The only network call this module makes (fetch_latest_tag) is invoked from
# the OFF-hot-path detached refresh (see hooks/update-refresh.py, spawned by
# session-start.py). refresh_if_stale() gates that call to at most once per
# day via the cached `checked_at`, and is fail-silent end to end: any network
# error, timeout, non-200, or unparseable body degrades to "keep the last-known
# latest" — never a traceback, never a crash of the host hook.
#
# Design principles (mirroring _ledgerlib.py / _taskboardlib.py):
#   - Stdlib only (urllib, json) — no third-party dependency, ever (ADR-0004).
#   - HTTPS-only fetch target (ADR-0003); a non-https url is refused outright.
#   - Zero side effects at import time — no network, no file I/O on import.
#   - Never raise on malformed/absent input — degrade to "no notice".
#
# Public API:
#   ONE_DAY                                  once-daily refresh interval (seconds)
#   UPDATE_API_URL                           GitHub Releases API endpoint (module constant)
#   state_path() -> str                      resolved cache file path (env-overridable)
#   plugin_root(explicit=None) -> str        the running plugin's own root directory
#   installed_version(root=None) -> str|None the version in <root>/.claude-plugin/plugin.json
#   parse_version(s) -> tuple|None           numeric-tuple parse; None if malformed/absent
#   version_gt(a, b) -> bool                 True iff semver a > b (numeric-tuple compare)
#   update_available(installed, latest) -> bool   True iff latest > installed
#   notice_line(installed, latest) -> str|None    the SessionStart/statusline notice text
#   read_state(path=None) -> dict            {latest, checked_at} cache, or {} on any failure
#   write_state(state, path=None) -> None    atomic cache write; best-effort, never raises
#   is_stale(checked_at, now, interval=ONE_DAY) -> bool   True iff a refresh is due
#   fetch_latest_tag(url=UPDATE_API_URL, timeout=3.0, opener=None) -> str|None   HTTPS GET, fail-silent
#   refresh_if_stale(now=None, fetcher=None, path=None) -> dict   best-effort cache refresh

import json
import os
import re
import sys
import time
import urllib.request

# Reuse the ONE atomic-write helper defined in _hooklib.py (same rationale as
# _previewlib.py: _hooklib sits beside this file; mount its dir on sys.path the
# same way the test harness does before importing by reference).
_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
from _hooklib import write_text_atomic  # noqa: E402 — needs the sys.path mount above
import hostapi  # noqa: E402 — host seam (ADR-0011): plugin-root resolution

ONE_DAY = 24 * 60 * 60

# The repo's own GitHub Releases API — unauthenticated GET, HTTPS only (ADR-0003).
# The release tag equals plugin.json's version (an established repo invariant).
UPDATE_API_URL = "https://api.github.com/repos/arbiterForge/codeArbiter/releases/latest"

_VERSION_STRIP_RE = re.compile(r"^[vV]")


def state_path():
    """Resolved cache file path. User-GLOBAL (~/.codearbiter/...), not project-scoped
    — the notice concerns the plugin's own version, not any one project. Env-overridable
    (CODEARBITER_UPDATE_STATE) for tests, mirroring _ledgerlib.ledger_path()."""
    return os.environ.get("CODEARBITER_UPDATE_STATE") or \
        os.path.join(os.path.expanduser("~"), ".codearbiter", "update-state.json")


def plugin_root(explicit=None):
    """The running plugin's own root directory (parent of hooks/). `explicit` wins
    (tests); else CLAUDE_PLUGIN_ROOT; else derived from this file's own location —
    always resolves to the ACTUAL running install, not a stale env pin. The env
    + file-relative resolution lives on the host seam (hostapi, ADR-0011)."""
    return explicit or hostapi.load_host().plugin_root()


def installed_version(root=None):
    """The `version` field from <root>/.claude-plugin/plugin.json, or None on any
    failure (missing file, corrupt JSON, missing/blank field)."""
    root = root or plugin_root()
    try:
        with open(os.path.join(root, ".claude-plugin", "plugin.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    v = data.get("version") if isinstance(data, dict) else None
    return v if isinstance(v, str) and v.strip() else None


def parse_version(s):
    """Parse a version string into a numeric tuple, e.g. "v2.10.0+build.5" -> (2, 10, 0).
    A leading 'v', build metadata (+...), and a prerelease suffix (-...) are tolerated
    and stripped. Returns None for anything that isn't a dotted run of digits (AC-6:
    malformed/absent -> None, so the caller yields no notice)."""
    if not isinstance(s, str):
        return None
    s = _VERSION_STRIP_RE.sub("", s.strip())
    s = s.split("+", 1)[0]
    s = s.split("-", 1)[0]
    if not s:
        return None
    parts = s.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def version_gt(a, b):
    """True iff semver `a` > `b`, numeric-tuple compared (2.10.0 > 2.9.0, never a
    lexicographic string compare). Either side malformed/absent -> False (AC-6)."""
    ta, tb = parse_version(a), parse_version(b)
    if ta is None or tb is None:
        return False
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return ta > tb


def update_available(installed, latest):
    """True iff `latest` is a well-formed version strictly greater than `installed`."""
    return version_gt(latest, installed)


def notice_line(installed, latest):
    """The single-line SessionStart/statusline notice, or None when no update is due
    (AC-1/AC-2): `codeArbiter: update available X -> Y (run /plugin marketplace update
    codearbiter)`. Never multi-line; never emitted for equal, lesser, missing, or
    malformed `latest`."""
    if not update_available(installed, latest):
        return None
    return (f"codeArbiter: update available {installed} -> {latest} "
            f"(run /plugin marketplace update codearbiter)")


def read_state(path=None):
    """The cached `{latest, checked_at}` state, or {} on ANY failure (missing file,
    corrupt JSON, non-dict content) — a corrupt cache degrades to 'no notice', never
    a crash of the host hook."""
    path = path or state_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(state, path=None):
    """Atomically persist `state` to the cache file, creating parent dirs as needed.
    Best-effort: ANY failure (permissions, missing/blocked parent) is swallowed — a
    cache write must never crash the caller (the detached refresh, or a test)."""
    path = path or state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomic(path, json.dumps(state), newline="\n")
    except Exception:  # noqa: BLE001 — best-effort cache write, never raise
        pass


def is_stale(checked_at, now, interval=ONE_DAY):
    """True iff a refresh is due: no prior check, or `interval` seconds have elapsed
    since `checked_at`. A malformed `checked_at` is treated as stale (never crashes,
    never wedges the gate closed)."""
    if checked_at is None:
        return True
    try:
        return (now - float(checked_at)) >= interval
    except (TypeError, ValueError):
        return True


class _HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow any redirect whose target isn't `https://` (ADR-0003,
    defense-in-depth). The pre-connection scheme guard in fetch_latest_tag below
    only covers the INITIAL url — urllib's default opener otherwise follows a
    3xx transparently, including an https->http downgrade, without ever
    re-checking the scheme. Returning None here means the redirect is NOT
    handled, so urllib's error chain raises the original HTTPError instead of
    silently continuing the chain over a downgraded (or otherwise non-https)
    target; fetch_latest_tag's broad except then degrades that to None, same as
    every other fetch failure (fail-silent, AC-5)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not (isinstance(newurl, str) and newurl.lower().startswith("https://")):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener():
    """Factory for the HTTPS-only-redirect opener. A thin seam — not called
    directly by fetch_latest_tag's default path only, but exposed as a factory
    (rather than a module-level singleton) so `opener=` injection in tests never
    has to touch real urllib internals."""
    return urllib.request.build_opener(_HTTPSOnlyRedirectHandler())


def fetch_latest_tag(url=UPDATE_API_URL, timeout=3.0, opener=None):
    """GET the GitHub Releases API and return `tag_name`, or None on ANY problem
    (AC-5): non-https url, network error, timeout, non-200, an unparseable/absent
    body, or a redirect to a non-https target. HTTPS-only per ADR-0003 — a
    non-https INITIAL url is refused before any connection is attempted, and a
    non-https REDIRECT target is refused too (via `_HTTPSOnlyRedirectHandler`,
    since urllib's default opener would otherwise follow an https->http
    downgrade transparently). `opener` is injectable (tests); production builds
    the hardened opener via `_build_opener()`."""
    if not isinstance(url, str) or not url.lower().startswith("https://"):
        return None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "codeArbiter-update-check",
            "Accept": "application/vnd.github+json",
        })
        op = opener or _build_opener()
        with op.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            if status != 200:
                return None
            body = resp.read()
        data = json.loads(body.decode("utf-8", "replace"))
        tag = data.get("tag_name") if isinstance(data, dict) else None
        return tag.strip() if isinstance(tag, str) and tag.strip() else None
    except Exception:  # noqa: BLE001 — AC-5: fail-silent on any network/parse error
        return None


def refresh_if_stale(now=None, fetcher=None, path=None):
    """Best-effort, once-daily, fail-silent cache refresh (AC-3/AC-4/AC-5).

    Reads the cache; if `checked_at` is still fresh (is_stale() False), returns it
    UNCHANGED and calls the fetcher NOT AT ALL (AC-4 — at most one fetch per day).
    Otherwise calls `fetcher()` (default fetch_latest_tag): on success the new
    `latest` is cached; on ANY exception or a None/falsy return, the PRIOR `latest`
    is preserved (fail-silent — a network hiccup never blanks a known-good notice)
    and `checked_at` still advances, so a persistently-unreachable network is not
    retried every single session that day. Never raises (AC-3)."""
    now = time.time() if now is None else now
    path = path or state_path()
    state = read_state(path)
    checked_at = state.get("checked_at") if isinstance(state, dict) else None
    if not is_stale(checked_at, now):
        return state
    fetch = fetcher or fetch_latest_tag
    try:
        latest = fetch()
    except Exception:  # noqa: BLE001 — AC-3/AC-5: never propagate a fetch failure
        latest = None
    new_state = {
        "latest": latest if latest else state.get("latest"),
        "checked_at": now,
    }
    write_state(new_state, path)
    return new_state
