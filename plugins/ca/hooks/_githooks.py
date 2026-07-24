#!/usr/bin/env python3
# codeArbiter — installs the git-level enforcement hooks (#161).
#
# The PreToolUse Bash hook (pre-bash.py) gates git operations by matching the
# literal command string, so shell indirection (`g=git; c=commit; $g $c`) walks
# past it. There is no enforcement below that layer. This module installs
# repo-level .git/hooks/pre-commit and pre-push that invoke git-enforce.py at the
# git operation itself, where spelling no longer matters.
#
# Design decisions (ADR-0014, resolves #265 / tribunal reliability-009):
#   * The shim is a tiny POSIX `sh` script that detects the interpreter ONCE
#     (python3 else python) and runs the enforcer EXACTLY once — never
#     `python3 X || python X`, which would (a) swallow a BLOCK when python3 both
#     exists and blocks, and (b) drain stdin before the fallback (pre-push feeds
#     the ref list on stdin). Same hazard hooks.json avoids via two entries; a
#     single hook file must guard it inline.
#   * The shim itself is HOST-NEUTRAL: it embeds no absolute enforcer path at
#     all. It instead points at a shared, non-versioned drop-in directory
#     inside the repo's OWN `.git/`:
#
#         .git/codearbiter-hooksd/<plugin>.path      # e.g. ca.path, ca-codex.path
#
#     Each installed host writes its OWN current `_enforcer_path()` into its
#     own `<plugin>.path` file every SessionStart (install() below) — a live
#     host self-heals a stale entry on its very next session. The shim runs
#     every resolving enforcer until one blocks; all must allow for Git to
#     proceed. A dead entry from an uninstalled plugin is skipped.
#     `uninstall()` removes only ITS OWN
#     `.path` file — never the shared shim, which a sibling plugin may still
#     depend on.
#   * FAIL CLOSED, not fail-open: if the directory is empty, absent, or every
#     entry it contains names a file that no longer exists, the shim prints a
#     diagnostic to stderr and exits non-zero — it BLOCKS the git operation
#     rather than silently allowing it. This is a deliberate reversal of the
#     single-plugin fail-open era: ADR-0014 records why. Before this drop-in dir
#     existed, the shim embedded ONE absolute enforcer path (whichever plugin's
#     SessionStart ran last), so uninstalling that plugin — or even the OTHER
#     plugin, if IT never got a chance to write its own copy afterward — could
#     silently unwire the git-level backstop for every host. The drop-in dir
#     removes the reason fail-open existed (a plugin no longer has to derive a
#     SIBLING's path — each writes only its own), so the residual failure mode
#     (truly nothing resolves) can safely — and must — fail closed instead.
#   * The drop-in directory itself is resolved via the repo's git COMMON dir
#     (mirrors `git rev-parse --git-common-dir`, resolved without a git spawn
#     when possible — see `_git_common_dir`), never `--git-dir` and never a
#     per-worktree path: a linked worktree's `.git` is a FILE pointing at
#     `<main>/.git/worktrees/<name>`, and the shared hooks/backstop must resolve
#     to the ONE drop-in dir inside the MAIN repo's `.git/`, so every worktree
#     and every host agree on the same directory — a per-worktree drop-in dir
#     would defeat the entire cross-host purpose.
#   * A pre-existing NON-ours hook is NEVER clobbered — we warn loudly and skip,
#     so an existing husky / pre-commit-framework setup is preserved.
#   * Idempotent: an up-to-date ours-hook is left untouched (no churn); a stale
#     ours-hook is refreshed. Because the shim no longer embeds any
#     plugin-specific path, an enforcer-path change (e.g. a version bump moving
#     the install dir) does NOT by itself require rewriting the shim file — only
#     this plugin's own `<plugin>.path` drop-in entry, which install() refreshes
#     unconditionally every session regardless of whether the shim itself needed
#     a rewrite.
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
#     core.hooksPath set AFTER a default-location install is not caught by the
#     `.git/config` read alone. This covers ALL of git's global/system config
#     locations, not just `~/.gitconfig`: `~/.config/git/config` (or
#     `$XDG_CONFIG_HOME/git/config`), and a `$GIT_CONFIG_GLOBAL`/
#     `$GIT_CONFIG_SYSTEM` env override repointing the file entirely. The cache
#     is keyed on the mtime of `~/.gitconfig` AND the XDG path (below), which
#     closes the common case of a later edit to either of those two files; a
#     `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` env override, or an edit to
#     `/etc/gitconfig`, is not cheaply detectable from a fixed path and remains
#     residual. This is rare (those overrides predating a later default-location
#     install is the unusual order), and a cold/first install always resolves
#     it correctly via the full git-based probe regardless.

import json
import os
import re
import stat
import subprocess
import sys

import _hooklib
from _gitexec import git_executable, trusted_git_executable, trusted_python_executable

SENTINEL = "# codeArbiter-managed git hook (#161) — refreshed each session; edits are overwritten."
PHASES = ("pre-commit", "pre-push")
# The hooks_dir() resolution cache lives INSIDE .git/ itself (never under
# .codearbiter/): a linked worktree's `.git` is a FILE (not a directory)
# pointing at the real gitdir elsewhere, so os.path.isdir(...) on it is
# naturally False there — the cache silently declines to engage and every call
# falls through to the full probe, rather than ever risking a wrong-repo guess.
_HOOKSDIR_CACHE_NAME = "codearbiter-hooksdir-cache"


def _warn(msg):
    print(f"codeArbiter git-hooks: {msg}", file=sys.stderr)


def _git(args, cwd):
    try:
        return subprocess.run(
            [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
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


def _plugin_name():
    """A stable per-plugin identifier for THIS install's drop-in `.path`
    filename (ADR-0014). Host caches insert a version directory between the
    plugin name and `hooks/`, so the package-directory basename is not stable.
    Prefer the shipped host manifest. A damaged versioned cache falls back to
    its parent plugin directory; a source-tree install falls back to its
    package-directory basename. Every returned key is filename-safe."""
    hooks_dir_path = os.path.dirname(os.path.abspath(__file__))
    package_dir = os.path.dirname(hooks_dir_path)
    manifests = (
        os.path.join(package_dir, ".claude-plugin", "plugin.json"),
        os.path.join(package_dir, ".codex-plugin", "plugin.json"),
        os.path.join(package_dir, "package.json"),
    )
    safe_name = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    for manifest in manifests:
        try:
            with open(manifest, encoding="utf-8") as f:
                name = json.load(f).get("name")
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
            continue
        if isinstance(name, str) and safe_name.fullmatch(name):
            return name

    package_name = os.path.basename(package_dir)
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?", package_name):
        package_name = os.path.basename(os.path.dirname(package_dir))
    return package_name if safe_name.fullmatch(package_name or "") else "plugin"


_DROPIN_DIRNAME = "codearbiter-hooksd"


def _git_common_dir(root):
    """The directory `git rev-parse --git-common-dir` would report for
    `root` — resolved WITHOUT a git spawn whenever the on-disk layout is
    cheaply readable, falling back to a real git spawn only when it isn't.

    Deliberately mirrors --git-common-dir, NOT --git-dir: a linked worktree's
    `.git` is a FILE (not a directory) holding a `gitdir: <path>` pointer into
    `<main>/.git/worktrees/<name>`, and THAT directory in turn holds a
    `commondir` file naming the real, SHARED main `.git`. Every worktree of a
    repo must resolve to the SAME common dir here, or the #265 drop-in dir
    would fork per-worktree and defeat the entire cross-host purpose (a shim
    installed from worktree A would never see an entry written from
    worktree B). The main-repo case (`.git` is a directory) needs no spawn at
    all: it IS its own common dir. Returns None if nothing resolves — callers
    must treat that as "can't place the drop-in dir right now" and never
    invent a per-worktree fallback."""
    git_path = os.path.join(root, ".git")
    if os.path.isdir(git_path):
        return os.path.abspath(git_path)
    if os.path.isfile(git_path):
        text = _read(git_path)
        if text:
            for line in text.splitlines():
                line = line.strip()
                if line.lower().startswith("gitdir:"):
                    wt_gitdir = line.split(":", 1)[1].strip()
                    if not os.path.isabs(wt_gitdir):
                        wt_gitdir = os.path.normpath(os.path.join(root, wt_gitdir))
                    cd_text = _read(os.path.join(wt_gitdir, "commondir"))
                    if cd_text:
                        cd = cd_text.strip()
                        common = (cd if os.path.isabs(cd)
                                  else os.path.normpath(os.path.join(wt_gitdir, cd)))
                        return os.path.abspath(common)
                    break
    r = _git(["rev-parse", "--git-common-dir"], root)
    if r is not None and r.returncode == 0 and r.stdout.strip():
        out = r.stdout.strip()
        return os.path.abspath(out if os.path.isabs(out) else os.path.join(root, out))
    return None


def _dropin_dir(root):
    """The shared, non-versioned drop-in directory (ADR-0014) each installed
    host writes its own `<plugin>.path` entry into. Lives inside the repo's
    git COMMON dir (never a per-worktree one — see `_git_common_dir`) so
    every worktree and every host share exactly ONE directory. Returns None
    when the common dir itself can't be resolved (no git dir at all)."""
    common = _git_common_dir(root)
    return os.path.join(common, _DROPIN_DIRNAME) if common else None


def _path_entry_file(dropin_dir, plugin):
    return os.path.join(dropin_dir, f"{plugin}.path")


def _shell_path(path):
    """Render an absolute native path for the POSIX sh git-hook boundary.

    Git for Windows executes these hooks through its POSIX shell. Native
    backslashes are ordinary characters there, so both globbing the drop-in
    directory and testing an enforcer entry would fail closed even though the
    Windows files exist. Forward slashes remain valid to Windows Python and
    Git while also being unambiguous to the shell.
    """
    return path.replace("\\", "/")


def _path_entry_current(dropin_dir, plugin, enforcer):
    """True iff this plugin's own drop-in entry already names `enforcer`."""
    existing = _read(_path_entry_file(dropin_dir, plugin))
    return existing is not None and existing.strip() == enforcer


def _write_path_entry(dropin_dir, plugin, enforcer):
    """Best-effort (never fatal) write/refresh of this plugin's OWN
    `<plugin>.path` drop-in entry — the self-heal half of ADR-0014: a live
    host rewrites its own entry every SessionStart regardless of whether the
    shared shim itself needed any change, so a stale entry from a version
    bump never outlives one session on a live install."""
    shell_enforcer = _shell_path(enforcer)
    if _path_entry_current(dropin_dir, plugin, shell_enforcer):
        return True
    try:
        os.makedirs(dropin_dir, exist_ok=True)
        _hooklib.write_text_atomic(
            _path_entry_file(dropin_dir, plugin), shell_enforcer + "\n", newline="\n")
        return True
    except Exception as e:  # noqa: BLE001
        _warn(f"could not write drop-in enforcer entry for '{plugin}' at {dropin_dir}: {e}")
        return False


_TRUSTED_IDENTITY_FILE = "trusted-executables.identity"


def _identity_file(dropin_dir):
    return os.path.join(dropin_dir, _TRUSTED_IDENTITY_FILE)


def _read_trusted_identity(dropin_dir):
    text = _read(_identity_file(dropin_dir))
    if text is None:
        return None
    lines = text.splitlines()
    if len(lines) != 3 or not lines[2]:
        return None
    python_path, git_path, owner = lines
    if not os.path.isfile(python_path) or not os.path.isfile(git_path):
        return None
    return python_path, git_path, owner


def _refresh_trusted_identity(dropin_dir, plugin):
    """Persist trusted executables without permitting an identity-less host
    session to downgrade the shared shim back to PATH resolution."""
    trusted_git = trusted_git_executable()
    trusted_python = trusted_python_executable()
    existing = _read_trusted_identity(dropin_dir)
    if trusted_git is None and trusted_python is None:
        return True
    if trusted_git is None or trusted_python is None:
        if existing is not None:
            _warn("trusted executable refresh is incomplete; preserving the prior complete identity")
            return True
        raise RuntimeError("codeArbiter executable identity channel is incomplete")
    values = (_shell_path(trusted_python), _shell_path(trusted_git), plugin)
    if any("\n" in value or "\r" in value for value in values):
        raise RuntimeError("trusted executable identity contains a newline")
    payload = "\n".join(values) + "\n"
    try:
        os.makedirs(dropin_dir, exist_ok=True)
        _hooklib.write_text_atomic(_identity_file(dropin_dir), payload, newline="\n")
        return True
    except Exception as e:  # noqa: BLE001
        if existing is not None:
            _warn(f"could not refresh trusted identity; preserving prior complete identity: {e}")
            return True
        raise RuntimeError(
            f"could not persist trusted executable identity at {dropin_dir}: {e}") from e


def _shim(dropin_dir, phase):
    # Single-interpreter selection preserves stdin (pre-push) and the BLOCK
    # exit code. The shim is HOST-NEUTRAL (ADR-0014): it embeds no plugin-
    # specific enforcer path, only the shared drop-in directory. It iterates
    # every "*.path" entry there and runs EVERY enforcer that resolves. Any
    # non-zero verdict blocks, so an older live sibling can never mask a newer
    # guard. A dead entry from an uninstalled plugin is skipped. An unmatched
    # glob (dir absent or
    # empty) leaves `c` as the literal, un-expanded "$D/*.path" string in
    # POSIX `sh` — `[ -f "$c" ]` on that literal correctly fails too, so the
    # loop falls straight through to the same fail-closed tail with no special
    # case needed. When NOTHING resolves, this now FAILS CLOSED: a loud
    # stderr diagnostic and a non-zero exit, blocking the git operation,
    # rather than the old single-plugin era's `exit 0`. When the Pi bridge
    # provides trusted executable identities, install() persists them beside
    # the registry. Identity-less hosts preserve that set, so a later Claude or
    # Codex session cannot downgrade Pi's absolute executable boundary.
    def quote(value):
        return "'" + value.replace("'", "'\"'\"'") + "'"

    capture = ""
    invoke = f'"$PY" "$E" {phase}\n'
    if phase == "pre-push":
        capture = (
            "PUSH_INPUT=''\n"
            "while IFS= read -r L; do\n"
            "  PUSH_INPUT=\"${PUSH_INPUT}${L}\n\"\n"
            "done\n"
        )
        invoke = f'printf \'%s\' "$PUSH_INPUT" | "$PY" "$E" {phase}\n'
    return (
        "#!/bin/sh\n"
        f"{SENTINEL}\n"
        f"D={quote(_shell_path(dropin_dir))}\n"
        f'if [ -e "$D/{_TRUSTED_IDENTITY_FILE}" ] || [ -L "$D/{_TRUSTED_IDENTITY_FILE}" ]; then\n'
        f'  [ -f "$D/{_TRUSTED_IDENTITY_FILE}" ] || exit 1\n'
        f'  exec 3< "$D/{_TRUSTED_IDENTITY_FILE}" || exit 1\n'
        '  IFS= read -r PY <&3 || exit 1\n'
        '  IFS= read -r G <&3 || exit 1\n'
        '  IFS= read -r IDENTITY_OWNER <&3 || exit 1\n'
        "  IDENTITY_EXTRA=''\n"
        '  if IFS= read -r IDENTITY_EXTRA <&3 || [ -n "$IDENTITY_EXTRA" ]; then exit 1; fi\n'
        '  exec 3<&-\n'
        '  [ -n "$IDENTITY_OWNER" ] && [ -f "$PY" ] && [ -f "$G" ] || exit 1\n'
        '  export CODEARBITER_GIT_EXECUTABLE="$G"\n'
        '  export CODEARBITER_PYTHON_EXECUTABLE="$PY"\n'
        "else\n"
        '  if python3 -c "" 2>/dev/null; then PY=python3; else PY=python; fi\n'
        "fi\n"
        f"{capture}"
        "SEEN=0\n"
        'for c in "$D"/*.path; do\n'
        '  [ -f "$c" ] || continue\n'
        '  case "${c##*/}" in [0-9]*.[0-9]*.[0-9]*.path) continue ;; esac\n'
        '  IFS= read -r E < "$c" || continue\n'
        '  [ -f "$E" ] || continue\n'
        '  SEEN=1\n'
        f'  {invoke}'
        '  RC=$?\n'
        '  [ "$RC" -eq 0 ] || exit "$RC"\n'
        'done\n'
        '[ "$SEEN" -eq 0 ] || exit 0\n'
        'echo "codeArbiter: no registered git-enforce.py could be resolved from '
        '\\"$D\\" -- failing CLOSED (#161/#265 git backstop, ADR-0014). Reinstall '
        'codeArbiter, or check .git/codearbiter-hooksd/*.path entries." >&2\n'
        'exit 1\n'
    )


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def _local_config_paths(root):
    """git-config files that could define a LOCAL core.hooksPath override for
    `root` — `.git/config` (always checked, even if the file happens to be
    missing — see _confirmed_no_local_hooks_path) plus `.git/config.worktree`
    (extensions.worktreeConfig repos), when it exists. Deliberately excludes
    global/system config — see the module header's documented residual."""
    git_dir = os.path.join(root, ".git")
    return [os.path.join(git_dir, "config"), os.path.join(git_dir, "config.worktree")]


def _confirmed_no_local_hooks_path(root):
    """True ONLY if a direct, no-git-spawn read of the config file(s) that
    could set a LOCAL core.hooksPath for `root` positively confirms NONE of
    them could possibly do so.

    GRAMMAR-FREE by design (HIGH-severity fix, second spelling of the same
    skip -> backstop-unwire class): git's config grammar honors a variable on
    the SAME line as its section header (`[core] hooksPath = x`,
    `[core]hooksPath=x`, `[CORE]HooksPath=x` are all valid and honored by real
    git), plus quoting/continuation/case variations — a hand-rolled
    line-oriented section/key parser reliably misses some of these spellings.
    Rather than chase git's config grammar (an unbounded set of spellings),
    this check is a single case-insensitive SUBSTRING scan for `hookspath`
    anywhere in the file, plus a substring scan for an `[include`/`[includeif`
    directive (which could pull a hooksPath in from elsewhere, unfollowed by
    this check). Any occurrence of either substring — even inside a comment —
    or any read failure, returns False (not confirmed). This can never
    UNDER-detect a real hooksPath key (a real key always contains the
    substring "hookspath" case-insensitively, by definition of the git-config
    keyword), so it can only ever be OVER-cautious (an extra, harmless
    git-spawn fall-through on a false positive, e.g. a stray comment
    mentioning the word) — never falsely confirm an override is absent when
    one is actually present. That asymmetry is exactly the fail-direction the
    fast path requires: "install when unsure," never "skip when unsure." A
    simply-ABSENT `config.worktree` is not an error (most repos don't have
    one) and contributes no override, exactly like git itself.

    This is the fail-direction-critical check (CRITICAL/HIGH fix, post-#194):
    the fast path in install() must never trust a cached hooks_dir without
    this positive confirmation, or a later `core.hooksPath` change (husky /
    pre-commit-framework) would silently leave the NEW hooks dir unwired."""
    for path in _local_config_paths(root):
        if not os.path.isfile(path):
            continue  # absent -> no override possible from this file
        text = _read(path)
        if text is None:
            return False  # exists but unreadable -> can't confirm -> unsafe to skip
        lowered = text.lower()
        if "hookspath" in lowered:
            return False  # ANY spelling/placement/casing -> can't confirm absent
        if "[include" in lowered:
            return False  # could pull in a hooksPath from elsewhere -> can't confirm
    return True


def _xdg_git_config_path():
    """The XDG git global-config path git ALSO reads (lower precedence than
    ~/.gitconfig, but still consulted): `$XDG_CONFIG_HOME/git/config`, or
    `~/.config/git/config` when XDG_CONFIG_HOME is unset — matching git's own
    fallback."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "git", "config")


def _file_mtime_token(path):
    """A cheap cache-invalidation token for `path`: its mtime, or the literal
    'absent' if it doesn't exist."""
    try:
        return repr(os.stat(path).st_mtime)
    except OSError:
        return "absent"


def _global_gitconfig_mtime_token():
    """A cheap cache-invalidation token covering BOTH global git-config
    locations codeArbiter can cheaply stat by a fixed path: `~/.gitconfig` and
    the XDG `~/.config/git/config` (or `$XDG_CONFIG_HOME/git/config`).
    Included in the on-disk cache so a LATER edit to either (e.g. adding a
    global core.hooksPath) invalidates a previously-fast-pathable cache
    instead of silently going unnoticed. Does NOT cover a `$GIT_CONFIG_GLOBAL`/
    `$GIT_CONFIG_SYSTEM` env override repointing the file entirely, nor
    `/etc/gitconfig` — see the module header's documented residual."""
    return f"{_file_mtime_token(os.path.join(os.path.expanduser('~'), '.gitconfig'))}|" \
           f"{_file_mtime_token(_xdg_git_config_path())}"


def _cached_hooks_dir(root):
    """The last hooks_dir() a successful resolution used for `root`, read from
    the on-disk cache — NO git spawn. Returns None (cache miss) if the cache
    file is absent/unreadable/blank/malformed, if it names a directory that no
    longer exists (e.g. deleted between sessions), or if either global
    git-config location (~/.gitconfig, the XDG git config) has changed since
    the cache was written (see _global_gitconfig_mtime_token). A None return
    always falls the caller through to the real git-based hooks_dir() probe."""
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
        return None  # a covered global git-config location changed since this cache was written
    return hd


def _write_hooks_dir_cache(root, hd):
    """Best-effort persistence of the resolved hooks_dir (+ the global
    git-config invalidation token) so a LATER session can skip the
    git-config/rev-parse re-probe (performance-002) when nothing has changed.
    Any failure — including `.git` being a FILE, not a directory, for a linked
    worktree — is swallowed: this cache is a pure optimization and is never
    allowed to affect whether hooks actually get installed."""
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return
    try:
        payload = f"{hd}\n{_global_gitconfig_mtime_token()}\n"
        _hooklib.write_text_atomic(
            os.path.join(git_dir, _HOOKSDIR_CACHE_NAME), payload, newline="\n")
    except Exception:  # noqa: BLE001 — best-effort cache, never fatal
        pass


def _hooks_current(hd, dropin_dir):
    """True iff BOTH phase shims at `hd` already match what install() would
    write right now for `dropin_dir` — i.e. install() would be a complete
    no-op for the SHIM files themselves. Filesystem-only (no git spawn): this
    is exactly the check that lets install() skip the git-config/rev-parse
    re-probe when a prior session already installed current hooks. A foreign
    (non-sentinel) hook, a stale shim, or a missing file all correctly return
    False here, falling the caller through to the full probe (which then
    re-derives the right action: refresh, warn-and-preserve, or install
    fresh).

    Note (ADR-0014): the shim is host-neutral — it depends only on
    `dropin_dir` (repo-derived, stable across plugin versions), never on this
    plugin's own enforcer path. So a plugin-version bump that only changes
    `_enforcer_path()` does NOT make this return False; install() refreshes
    the plugin's OWN drop-in `.path` entry unconditionally every call,
    independent of whether this check short-circuits the shim-file rewrite."""
    for phase in PHASES:
        existing = _read(os.path.join(hd, phase))
        if existing is None or existing != _shim(dropin_dir, phase):
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
      4. the shims at that dir are already current for the drop-in dir
         (_hooks_current — ADR-0014: the shim depends only on `dropin_dir`,
         never on this plugin's own enforcer path).
    Any single miss/mismatch — including a genuine cold install, a foreign
    hook, a changed core.hooksPath, or ambiguity in the config read — falls
    through to the original git-based probe below, unchanged. Fail direction
    is "install when unsure," never "skip when unsure".

    ADR-0014: regardless of which path this function takes (fast path or full
    probe), THIS plugin's own drop-in `<plugin>.path` entry is refreshed
    every single call — a live host self-heals a stale entry (e.g. after a
    version bump moved `_enforcer_path()`) every SessionStart, independent of
    whether the shared shim FILE itself needed any rewrite."""
    plugin = _plugin_name()
    enforcer = _enforcer_path()
    dropin_dir = _dropin_dir(root)
    if dropin_dir is None:
        return []  # no resolvable git dir at all — nothing to install against
    _refresh_trusted_identity(dropin_dir, plugin)
    cached_hd = _cached_hooks_dir(root)
    if cached_hd is not None:
        default_hd = os.path.normcase(os.path.abspath(_default_hooks_dir(root)))
        cached_norm = os.path.normcase(os.path.abspath(cached_hd))
        if (cached_norm == default_hd
                and _confirmed_no_local_hooks_path(root)
                and _hooks_current(cached_hd, dropin_dir)):
            _write_path_entry(dropin_dir, plugin, enforcer)
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
        desired = _shim(dropin_dir, phase)
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
    # ADR-0014: refresh THIS plugin's own drop-in entry every call, whether or
    # not the shim files above needed a rewrite.
    if _write_path_entry(dropin_dir, plugin, enforcer):
        pass
    return actions


def uninstall(root):
    """Remove ONLY this plugin's OWN drop-in `<plugin>.path` entry (ADR-0014).

    Deliberately does NOT touch the shared shim file (.git/hooks/pre-commit /
    pre-push) — that shim is host-neutral and a sibling plugin may still
    depend on it. Leaving a genuinely EMPTY drop-in dir behind (every plugin
    uninstalled) is the intended fail-closed contract, not a bug: the next
    commit finds no resolvable enforcer and blocks with a clear diagnostic
    (see `_shim`'s tail), rather than the old single-plugin era silently
    passing. Returns the actions taken."""
    plugin = _plugin_name()
    dropin_dir = _dropin_dir(root)
    if dropin_dir is None:
        return []
    actions = []
    entry = _path_entry_file(dropin_dir, plugin)
    if os.path.isfile(entry):
        try:
            os.remove(entry)
            actions.append(f"{plugin}.path: removed")
        except Exception as e:  # noqa: BLE001
            _warn(f"could not remove {entry}: {e}")
    identity = _read_trusted_identity(dropin_dir)
    if identity is not None and identity[2] == plugin:
        path = _identity_file(dropin_dir)
        try:
            os.remove(path)
            actions.append(f"{plugin} trusted identity: removed")
        except Exception as e:  # noqa: BLE001
            _warn(f"could not remove {path}: {e}")
    return actions


if __name__ == "__main__":
    # Manual install/uninstall: `python _githooks.py [install|uninstall] [root]`.
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    where = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    done = uninstall(where) if cmd == "uninstall" else install(where)
    print(f"{cmd}: " + (", ".join(done) if done else "no changes"))
