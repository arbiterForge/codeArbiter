#!/usr/bin/env python3
# codeArbiter — installs the git-level enforcement hooks (#161).
#
# The PreToolUse Bash hook (pre-bash.py) gates git operations by matching the
# literal command string, so shell indirection (`g=git; c=commit; $g $c`) walks
# past it. There is no enforcement below that layer. This module installs
# repo-level .git/hooks/pre-commit and pre-push that invoke git-enforce.py at the
# git operation itself, where spelling no longer matters.
#
# Design decisions:
#   * The shim is a tiny POSIX `sh` script that detects the interpreter ONCE
#     (python3 else python) and runs the enforcer EXACTLY once — never
#     `python3 X || python X`, which would (a) swallow a BLOCK when python3 both
#     exists and blocks, and (b) drain stdin before the fallback (pre-push feeds
#     the ref list on stdin). Same hazard hooks.json avoids via two entries; a
#     single hook file must guard it inline.
#   * The shim points at the enforcer by ABSOLUTE PATH, resolved from THIS file's
#     location (inside the plugin) at install time. install() is re-run every
#     SessionStart, so the path is refreshed each session — if a plugin update
#     moves the install dir, the next session rewrites the shim. During the brief
#     window before that, a missing enforcer makes the shim exit 0 (fail-OPEN on
#     our OWN staleness only — never brick a user's commits because our path
#     drifted; the pre-bash + Claude layers still apply).
#   * A pre-existing NON-ours hook is NEVER clobbered — we warn loudly and skip,
#     so an existing husky / pre-commit-framework setup is preserved.
#   * Idempotent: an up-to-date ours-hook is left untouched (no churn); a stale
#     ours-hook is refreshed.
#   * performance-002 (#194): re-resolving hooks_dir() every SessionStart costs
#     up to two blocking `git` subprocess spawns (config --get core.hooksPath,
#     rev-parse --git-path hooks) even on the common steady-state call where
#     nothing changed. install() first checks a cheap on-disk cache (a single
#     small file read, no git spawn) recording the hooks_dir a prior successful
#     resolution used; if BOTH phase shims at that cached location already
#     match what we'd install right now, it returns immediately. Any mismatch
#     or absence (including a genuinely fresh/cold repo) falls through to the
#     full git-based probe unchanged — the cache is a pure latency optimization,
#     never load-bearing for correctness.
#
#     CRITICAL fix (security review, post-#194): the fast path must NEVER trust
#     a cached hooks_dir without CHEAPLY (no git spawn) proving the EFFECTIVE
#     hooks dir has not moved since that cache was written. The original cut
#     only re-checked that the shims AT the cached location were current — it
#     never re-checked that git would still read hooks FROM that location. A
#     LOCAL core.hooksPath change after the cache was written (the realistic
#     case: the user later adopts husky / pre-commit-framework, which set
#     `core.hooksPath` in `.git/config`) left the fast path returning `[]`
#     (success) while the NEW hooks dir got no codeArbiter shim at all — the
#     #161 backstop silently unwired. Fixed: the fast path now ALSO requires
#     (a) the cached dir be exactly the DEFAULT `<root>/.git/hooks` (never a
#     cached custom hooksPath — those must always re-confirm via git, since a
#     custom path is exactly the kind of thing that gets repointed), and (b) a
#     direct read of `.git/config` (and `.git/config.worktree`, for
#     extensions.worktreeConfig repos) positively CONFIRMS no local
#     core.hooksPath key is set. Any read failure, parse ambiguity, or a
#     detected key falls through to the full git-based probe — fail direction
#     is "install when unsure," never "skip when unsure."
#
#     Documented residual (accepted, not cheaply closable): a GLOBAL/SYSTEM
#     core.hooksPath (~/.gitconfig, /etc/gitconfig) set AFTER a default-location
#     install is not caught by the `.git/config` read alone — closed for the
#     common `~/.gitconfig` case by also keying the cache on that file's mtime
#     (below), but a `/etc/gitconfig` (or an equivalent `GIT_CONFIG_*` env/
#     `--system` override) change is not cheaply detectable and remains
#     residual. This is rare (a system-wide hooksPath predating a later
#     default-location install is the unusual order), and a cold/first install
#     always resolves it correctly via the full git-based probe regardless.

import os
import re
import stat
import subprocess
import sys

import _hooklib

SENTINEL = "# codeArbiter-managed git hook (#161) — refreshed each session; edits are overwritten."
PHASES = ("pre-commit", "pre-push")
# The hooks_dir() resolution cache lives INSIDE .git/ itself (never under
# .codearbiter/): a linked worktree's `.git` is a FILE (not a directory)
# pointing at the real gitdir elsewhere, so os.path.isdir(...) on it is
# naturally False there — the cache silently declines to engage and every call
# falls through to the full probe, rather than ever risking a wrong-repo guess.
_HOOKSDIR_CACHE_NAME = "codearbiter-hooksdir-cache"

# Minimal git-config section/key matcher — used ONLY to detect the PRESENCE of
# a `core.hooksPath` key (never its value) so the fast path can conservatively
# decline whenever the answer isn't a clean "definitely not set". Deliberately
# does not attempt full git-config-file fidelity (line continuations, quoted
# subsections, etc.) — see _config_has_core_hooks_path's fail-direction note.
_SECTION_RE = re.compile(r'^\[\s*([^\s\]"]+)\s*(?:"[^"]*")?\s*\]')
_KEY_RE = re.compile(r'^([A-Za-z][A-Za-z0-9-]*)\s*(?:=.*)?$')


def _warn(msg):
    print(f"codeArbiter git-hooks: {msg}", file=sys.stderr)


def _git(args, cwd):
    try:
        return subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
    except Exception:  # noqa: BLE001
        return None


def hooks_dir(root):
    """The directory git actually reads hooks from for `root`, or None.

    Honors core.hooksPath (when set, git IGNORES .git/hooks entirely), and
    resolves the real git dir via `rev-parse --git-path hooks` so linked
    worktrees and submodules land in the right place. Falls back to
    <root>/.git/hooks only if git can't answer."""
    cfg = _git(["config", "--get", "core.hooksPath"], root)
    if cfg is not None and cfg.returncode == 0 and cfg.stdout.strip():
        hp = cfg.stdout.strip()
        return hp if os.path.isabs(hp) else os.path.join(root, hp)
    gp = _git(["rev-parse", "--git-path", "hooks"], root)
    if gp is not None and gp.returncode == 0 and gp.stdout.strip():
        hp = gp.stdout.strip()
        return hp if os.path.isabs(hp) else os.path.join(root, hp)
    default = os.path.join(root, ".git", "hooks")
    return default if os.path.isdir(os.path.join(root, ".git")) else None


def _enforcer_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "git-enforce.py")


def _shim(enforcer, phase):
    # Single-interpreter selection preserves stdin (pre-push) and the BLOCK exit
    # code. `exit 0` when the enforcer file is absent is deliberate fail-open on
    # our own path staleness (see module header).
    return (
        "#!/bin/sh\n"
        f"{SENTINEL}\n"
        f'E="{enforcer}"\n'
        '[ -f "$E" ] || exit 0\n'
        'if python3 -c "" 2>/dev/null; then PY=python3; else PY=python; fi\n'
        f'exec "$PY" "$E" {phase}\n'
    )


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def _config_has_core_hooks_path(text):
    """True iff git-config-file `text` sets `core.hooksPath` inside a `[core]`
    section. Minimal section/key matcher, not a full git-config parser (no
    line-continuation support) — it only answers "did I positively see a
    hooksPath key under [core]?"."""
    section = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1).lower()
            continue
        if section == "core":
            km = _KEY_RE.match(line)
            if km and km.group(1).lower() == "hookspath":
                return True
    return False


def _config_has_include_directive(text):
    """True iff `text` contains an `[include]`/`[includeIf ...]` section —
    git-config's mechanism for pulling in ANOTHER file (which this module's
    minimal parser does not follow). Presence makes `.git/config` itself
    unconfirmable for our purposes (a hooksPath could be set in the included
    file instead), so the caller must fail safe on it — see
    _confirmed_no_local_hooks_path."""
    return bool(re.search(r'^\[\s*include(if\b[^\]]*)?\s*\]', text or "",
                          re.IGNORECASE | re.MULTILINE))


def _local_config_paths(root):
    """git-config files whose `[core]` section could define a LOCAL
    core.hooksPath override for `root` — `.git/config` (always checked, even
    if the file happens to be missing — see _confirmed_no_local_hooks_path)
    plus `.git/config.worktree` (extensions.worktreeConfig repos), when it
    exists. Deliberately excludes global (~/.gitconfig) and system
    (/etc/gitconfig) config — see the module header's documented residual."""
    git_dir = os.path.join(root, ".git")
    return [os.path.join(git_dir, "config"), os.path.join(git_dir, "config.worktree")]


def _confirmed_no_local_hooks_path(root):
    """True ONLY if a direct, no-git-spawn read of the config file(s) that
    could set a LOCAL core.hooksPath for `root` positively confirms NONE of
    them do. Any read failure (a file exists but can't be read) or a detected
    hooksPath key returns False. A simply-ABSENT `config.worktree` is not an
    error (most repos don't have one) and contributes no override, exactly
    like git itself.

    This is the fail-direction-critical check (CRITICAL fix, post-#194): the
    fast path in install() must never trust a cached hooks_dir without this
    positive confirmation, or a later `core.hooksPath` change (husky /
    pre-commit-framework) would silently leave the NEW hooks dir unwired."""
    for path in _local_config_paths(root):
        if not os.path.isfile(path):
            continue  # absent -> no override possible from this file
        text = _read(path)
        if text is None:
            return False  # exists but unreadable -> can't confirm -> unsafe to skip
        if _config_has_core_hooks_path(text):
            return False
        if _config_has_include_directive(text):
            return False  # could pull in a hooksPath from elsewhere -> can't confirm
    return True


def _global_gitconfig_mtime_token():
    """A cheap cache-invalidation token for ~/.gitconfig: its mtime, or the
    literal 'absent' if the file doesn't exist. Included in the on-disk cache
    so a LATER edit to the user's global config (e.g. adding a global
    core.hooksPath) invalidates a previously-fast-pathable cache instead of
    silently going unnoticed — narrows, but does not eliminate, the documented
    global/system-config residual (module header)."""
    try:
        return repr(os.stat(os.path.join(os.path.expanduser("~"), ".gitconfig")).st_mtime)
    except OSError:
        return "absent"


def _cached_hooks_dir(root):
    """The last hooks_dir() a successful resolution used for `root`, read from
    the on-disk cache — NO git spawn. Returns None (cache miss) if the cache
    file is absent/unreadable/blank/malformed, if it names a directory that no
    longer exists (e.g. deleted between sessions), or if ~/.gitconfig has
    changed since the cache was written (see _global_gitconfig_mtime_token). A
    None return always falls the caller through to the real git-based
    hooks_dir() probe."""
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return None
    text = _read(os.path.join(git_dir, _HOOKSDIR_CACHE_NAME))
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) < 2:
        return None  # malformed/legacy cache shape -> treat as a miss
    hd, stored_token = lines[0].strip(), lines[1].strip()
    if not hd or not os.path.isdir(hd):
        return None
    if stored_token != _global_gitconfig_mtime_token():
        return None  # ~/.gitconfig changed since this cache was written
    return hd


def _write_hooks_dir_cache(root, hd):
    """Best-effort persistence of the resolved hooks_dir (+ the ~/.gitconfig
    invalidation token) so a LATER session can skip the git-config/rev-parse
    re-probe (performance-002) when nothing has changed. Any failure —
    including `.git` being a FILE, not a directory, for a linked worktree — is
    swallowed: this cache is a pure optimization and is never allowed to
    affect whether hooks actually get installed."""
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return
    try:
        payload = f"{hd}\n{_global_gitconfig_mtime_token()}\n"
        _hooklib.write_text_atomic(
            os.path.join(git_dir, _HOOKSDIR_CACHE_NAME), payload, newline="\n")
    except Exception:  # noqa: BLE001 — best-effort cache, never fatal
        pass


def _hooks_current(hd, enforcer):
    """True iff BOTH phase shims at `hd` already match what install() would
    write right now for `enforcer` — i.e. install() would be a complete no-op.
    Filesystem-only (no git spawn): this is exactly the check that lets
    install() skip the git-config/rev-parse re-probe when a prior session
    already installed current hooks. A foreign (non-sentinel) hook, a stale
    shim, or a missing file all correctly return False here, falling the
    caller through to the full probe (which then re-derives the right action:
    refresh, warn-and-preserve, or install fresh)."""
    for phase in PHASES:
        existing = _read(os.path.join(hd, phase))
        if existing is None or existing != _shim(enforcer, phase):
            return False
    return True


def _default_hooks_dir(root):
    return os.path.join(root, ".git", "hooks")


def install(root):
    """Ensure the git-level enforcement hooks are installed for `root`.
    Idempotent and safe to call every session. Returns a list of human-readable
    actions taken (possibly empty). Never raises for an expected condition
    (no git dir, foreign hook) — those are reported, not fatal.

    performance-002 (#194): before doing any git spawn, checks a cheap on-disk
    cache of the last resolved hooks_dir. The fast path (zero git subprocess
    calls) fires ONLY when ALL of the following hold — every one of them is a
    cheap, no-git-spawn check:
      1. a cached hooks_dir exists and still exists on disk;
      2. that cached dir is EXACTLY the default `<root>/.git/hooks` — a cached
         CUSTOM hooksPath is never fast-pathed, since a custom path is exactly
         the kind of value that gets repointed later;
      3. a direct read of `.git/config` (+ `.git/config.worktree`) positively
         CONFIRMS no local core.hooksPath override is set right now (see
         _confirmed_no_local_hooks_path — CRITICAL fix, post-#194: the
         original cut skipped this check entirely, so a LOCAL hooksPath added
         after the cache was written — e.g. adopting husky / pre-commit-
         framework — silently left the NEW hooks dir unwired while returning
         `[]`);
      4. the shims at that dir are already current for the CURRENT enforcer
         path (_hooks_current).
    Any single miss/mismatch — including a genuine cold install, a moved
    plugin path, a foreign hook, a changed core.hooksPath, or ambiguity in the
    config read — falls through to the original git-based probe below,
    unchanged. Fail direction is "install when unsure," never "skip when
    unsure"."""
    enforcer = _enforcer_path()
    cached_hd = _cached_hooks_dir(root)
    if cached_hd is not None:
        default_hd = os.path.normcase(os.path.abspath(_default_hooks_dir(root)))
        cached_norm = os.path.normcase(os.path.abspath(cached_hd))
        if (cached_norm == default_hd
                and _confirmed_no_local_hooks_path(root)
                and _hooks_current(cached_hd, enforcer)):
            return []
    hd = hooks_dir(root)
    if not hd:
        return []
    try:
        os.makedirs(hd, exist_ok=True)
    except Exception:  # noqa: BLE001
        _warn(f"could not create hooks dir {hd}; skipping git-hook install")
        return []
    actions = []
    for phase in PHASES:
        dest = os.path.join(hd, phase)
        desired = _shim(enforcer, phase)
        if os.path.exists(dest):
            existing = _read(dest)
            if existing is not None and SENTINEL not in existing:
                _warn(f"an existing {phase} hook is not codeArbiter-managed — leaving it "
                      f"untouched. For git-level enforcement, call "
                      f"'{os.path.basename(enforcer)} {phase}' from it (see includes docs).")
                actions.append(f"{phase}: foreign hook preserved (not installed)")
                continue
            if existing == desired:
                continue  # already current — no churn
        try:
            # reliability-010: atomic sibling-temp + os.replace (mirrors
            # write_provenance/save_state). A crash mid-write with a plain
            # open('w') could leave a sentinel-less partial shim that the
            # foreign-hook guard above then preserves forever; os.replace
            # guarantees `dest` is either the complete new shim or the prior
            # (sentinel-bearing, or absent) file — never a torn write.
            _hooklib.write_text_atomic(dest, desired, newline="\n")
            st = os.stat(dest)
            os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            actions.append(f"{phase}: installed")
        except Exception as e:  # noqa: BLE001
            _warn(f"could not write {dest}: {e}")
    # Cache the resolved location so the NEXT call can skip the git-config/
    # rev-parse re-probe entirely (performance-002) — best-effort, never fatal.
    _write_hooks_dir_cache(root, hd)
    return actions


def uninstall(root):
    """Remove ONLY codeArbiter-managed hooks (identified by the sentinel);
    a foreign hook is left in place. Returns the actions taken."""
    hd = hooks_dir(root)
    if not hd:
        return []
    actions = []
    for phase in PHASES:
        dest = os.path.join(hd, phase)
        existing = _read(dest)
        if existing is not None and SENTINEL in existing:
            try:
                os.remove(dest)
                actions.append(f"{phase}: removed")
            except Exception as e:  # noqa: BLE001
                _warn(f"could not remove {dest}: {e}")
    return actions


if __name__ == "__main__":
    # Manual install/uninstall: `python _githooks.py [install|uninstall] [root]`.
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    where = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    done = uninstall(where) if cmd == "uninstall" else install(where)
    print(f"{cmd}: " + (", ".join(done) if done else "no changes"))
