#!/usr/bin/env python3
# codeArbiter v2 — SessionStart activation hook (the linchpin).
# Python port of session-start.sh (#25): no awk/grep/find, cross-platform, and
# fails LOUD — if CONTEXT.md exists but its frontmatter is malformed, it now
# prints a stderr breadcrumb instead of going silently dormant (the worst
# failure shape for a plugin whose whole job is to be active).
#
# Detects an arbiter-enabled repo and injects the orchestrator persona + startup
# state into context. A plugin has no CLAUDE.md to load an always-on persona, so
# the SessionStart hook does it: in a repo whose `.codearbiter/CONTEXT.md`
# frontmatter sets `arbiter: enabled`, this prints ORCHESTRATOR.md (+ live state)
# to stdout, which Claude Code adds to context.
#
# Injection is via PLAIN STDOUT, not hookSpecificOutput.additionalContext:
# additionalContext from a plugin-scoped hook is unreliable (claude-code #16538),
# whereas plain stdout is added to context dependably.
#
# In any repo WITHOUT the flag, the hook exits silently (dormant) — the plugin
# can be installed globally and stays out of the way everywhere else.

import datetime
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import frontmatter_enabled, utf8_stdio  # noqa: E402
from _standuplib import (  # noqa: E402
    any_actionable,
    ff_pull_eligible,
    merged_branch_candidates,
    parse_ahead_behind,
    parse_porcelain,
    parse_stash_count,
    parse_worktrees,
    stale_worktree_candidates,
)

INITIALIZED_RE = re.compile(r"<!--\s*INITIALIZED\s*-->")
STAGE_RE = re.compile(r"^stage:\s*([0-9]+)", re.I | re.M)
CONFIRM_RE = re.compile(r"CONFIRM-[0-9]+")


def project_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


# --- First-of-day standup briefing gating (sprint: session-hygiene, SH-1) ---
# The decision is a PURE function of (root, local-date-as-ISO-string). The date
# is INJECTED as a parameter — never read via datetime.date.today() inside these
# helpers — so the gating is deterministic and unit-testable from fixtures. The
# only caller that supplies "real today" is main(), at the I/O edge.


def local_date_iso(today=None):
    """ISO `YYYY-MM-DD` for the local date. `today` may be injected (a
    datetime.date) for determinism; defaults to the real local date at the
    I/O edge (main())."""
    d = today if today is not None else datetime.date.today()
    return d.isoformat()


def standup_marker_path(root, date_iso):
    """Path of the first-of-day presence marker for `date_iso`:
    `<root>/.codearbiter/.markers/standup-<YYYY-MM-DD>`."""
    return os.path.join(root, ".codearbiter", ".markers", f"standup-{date_iso}")


def should_emit_briefing(root, date_iso):
    """True iff NO first-of-day marker exists for `date_iso` — i.e. this is the
    first session of the local day, so the full briefing should be emitted.
    A marker already present for the date → False (suppress)."""
    return not os.path.isfile(standup_marker_path(root, date_iso))


# The later-session offer (SH-2) is a SINGLE concise line — never a full
# briefing. Keep it one physical line (no embedded newlines): the emission must
# stay exactly one line.
OFFER_LINE = "codeArbiter: hygiene items pending — run /ca:standup"


def briefing_mode(marker_present, actionable):
    """Choose the first-vs-later-session briefing mode (SH-2). PURE: a function
    of (marker_present, actionable) so it is testable without git or a clock.

    Three-mode contract:
      - no marker                         -> "full"  (first session of the day:
                                             emit the full daily briefing — SH-1)
      - marker present AND actionable     -> "offer" (later session today with at
                                             least one actionable condition: emit
                                             exactly ONE concise offer line)
      - marker present AND not actionable -> "none"  (later session today, nothing
                                             to do: emit nothing additive)
    """
    if not marker_present:
        return "full"
    return "offer" if actionable else "none"


def write_standup_marker(root, date_iso):
    """Write the first-of-day presence marker for `date_iso`, creating the
    `.markers/` dir lazily. Content is a timestamp (presence is what matters)."""
    path = standup_marker_path(root, date_iso)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{time.time()}\n")
    return path


# --- Read-only git invocation layer (SH-4 / content assembly) ---------------
# Every git call the briefing makes is READ-ONLY. The hook NEVER mutates the
# repo here (the only write in this whole hook is the standup marker). The
# invocation layer is a thin wrapper that runs a read-only git command and
# returns its stdout text, returning "" on ANY failure (missing git, timeout,
# non-zero exit). PARSING stays in _standuplib (pure). The wrapper takes an
# injectable `runner` so unit tests feed fake command outputs instead of
# shelling out to real git.

GIT_READ_TIMEOUT = 2.5  # seconds: a read must never stall session startup


def _default_git_runner(args, root):
    """Run `git -C <root> <args...>` read-only and return stdout text. Mirrors the
    safe invocation style of project_root()'s existing rev-parse call: captured
    output, text mode, explicit utf-8 with replacement, a timeout. Raises on any
    failure — git_read() is what turns failure into "" so callers degrade."""
    out = subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=GIT_READ_TIMEOUT,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {args} exited {out.returncode}")
    return out.stdout


def git_read(args, root, runner=None):
    """Run a READ-ONLY git command and return its stdout text, or "" on ANY error.

    `runner(args, root) -> str` is injectable (tests pass a fake; production uses
    the default subprocess runner). A None return or any raised exception degrades
    to "" so a single failing read never crashes the hook."""
    run = runner or _default_git_runner
    try:
        out = run(args, root)
    except Exception:  # noqa: BLE001 — any read failure degrades silently
        return ""
    return out or ""


# --- Non-blocking background fetch (SH-4) -----------------------------------
# The briefing's ahead/behind reflects the LAST COMPLETED fetch (current local
# refs); it is annotated as such. To keep that data fresh for NEXT time without
# blocking THIS hook's stdout/return, we spawn a fully DETACHED `git fetch` that
# we never await. The hook returns immediately even if the network hangs.

STALE_REFS_NOTE = "(ahead/behind as of last fetch — refs may be stale)"


def _detached_fetch_spawner(args, root):
    """Default spawner: launch `git -C <root> <args...>` fully DETACHED. Child
    stdout/stderr go to DEVNULL; the process is decoupled from the hook so it
    outlives this process and is never awaited. POSIX: start_new_session=True
    (new session, no controlling terminal). Windows: DETACHED_PROCESS |
    CREATE_NO_WINDOW so no console window flashes and the child is detached."""
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kw["creationflags"] = flags
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(["git", "-C", root, *args], **kw)


def spawn_background_fetch(root, spawner=None):
    """Kick a DETACHED `git fetch` that does NOT block the hook. Returns the spawned
    process handle (for tests to inspect) or None if the spawn failed.

    The returned handle is NEVER awaited (.wait()/.communicate() are not called),
    so a hanging fetch cannot stall the hook. `spawner(args, root) -> proc` is
    injectable; the default detaches per-platform. Any spawn failure (git missing,
    OSError) is swallowed — offline is tolerated silently."""
    spawn = spawner or _detached_fetch_spawner
    try:
        # --quiet --no-tags: read-only refresh of remote-tracking refs only.
        return spawn(["fetch", "--quiet", "--no-tags"], root)
    except Exception:  # noqa: BLE001 — offline / missing git tolerated silently
        return None


# --- Statusline reuse (display-only governance line) ------------------------
# The full briefing shows a DISPLAY-ONLY governance line — overrides-since-
# checkpoint, aging CONFIRM count, open-tasks count, stage — computed by
# statusline.py. We REUSE those computations rather than reimplement them:
# statusline.arbiter_state(root) and statusline.head_branch(root). Import is
# lazy + guarded so a statusline import problem never crashes the hook.


def _statusline():
    """Import statusline.py (same dir) lazily, returning the module or None. The
    module is importable via the sys.path entry added at file top; on any failure
    we degrade (the governance line is simply omitted)."""
    try:
        import statusline  # noqa: PLC0415 — lazy by design
        return statusline
    except Exception:  # noqa: BLE001
        return None


def head_branch(root):
    """Current branch name, reusing statusline.head_branch (reads .git/HEAD).
    None on any problem."""
    sl_mod = _statusline()
    if sl_mod is None:
        return None
    try:
        return sl_mod.head_branch(root)
    except Exception:  # noqa: BLE001
        return None


def governance_line(root):
    """Display-only governance summary reused from statusline.arbiter_state:
    `stage:N tasks:N q:N over:N`. Returns "" when arbiter isn't enabled or on any
    failure. DISPLAY ONLY — never acts on these counts."""
    sl_mod = _statusline()
    if sl_mod is None:
        return ""
    try:
        st = sl_mod.arbiter_state(root)
    except Exception:  # noqa: BLE001
        return ""
    if not st:
        return ""
    return (f"governance: stage:{st['stage']} tasks:{st['tasks']} "
            f"q:{st['q']} over:{st['over']}")


def render_full_briefing(root, summary):
    """Print the read-only daily briefing body: git hygiene state (with the
    last-fetch staleness note) and the display-only governance line. No mutation."""
    print(f"  working tree: {'dirty' if summary['dirty'] else 'clean'} "
          f"(staged:{summary['staged']} unstaged:{summary['unstaged']} "
          f"untracked:{summary['untracked']})")
    if summary.get("upstream", True):
        print(f"  upstream: behind {summary['behind']}, ahead {summary['ahead']} "
              f"{STALE_REFS_NOTE}")
    else:
        print("  upstream: none (no tracking branch)")
    if summary.get("ff_pull_eligible"):
        print("  ff-pull available: clean tree, behind upstream — /ca:standup to fast-forward")
    if summary["prune_candidates"]:
        print(f"  merged-branch prune candidates: "
              f"{', '.join(summary['prune_candidates'])}")
    if summary["stashes"]:
        print(f"  stashes: {summary['stashes']}")
    gov = governance_line(root)
    if gov:
        print(f"  {gov}")


# --- Briefing content assembly (read-only) ----------------------------------


def assemble_summary(root, runner=None, current=None, default="main", path_exists=os.path.exists):
    """Assemble the briefing `summary` from READ-ONLY git reads, parsed by the pure
    _standuplib functions. Each read is independent: a failure in one degrades that
    field (absent/zero/empty) without crashing the hook.

    Reads: `status --porcelain=v1`, `rev-list --left-right --count @{u}...HEAD`
    (empty when no upstream -> behind/ahead 0), `branch -vv`, `worktree list
    --porcelain`, `stash list`. Returns keys consumed by any_actionable(): dirty,
    behind, ahead, unpushed, prune_candidates, stale_worktrees, stashes.

    `stale_worktrees` is the NON-MAIN worktrees that are stale (branch gone/merged
    OR path missing on disk). The gone/merged set is derived from the SAME
    `branch -vv` text via merged_branch_candidates (the `: gone]` branches). The
    disk check uses an injectable `path_exists` so the field is deterministic in
    tests. Read-only: identifies candidates only — never removes a worktree."""
    porcelain = git_read(["status", "--porcelain=v1"], root, runner)
    p = parse_porcelain(porcelain)

    revlist = git_read(["rev-list", "--left-right", "--count", "@{u}...HEAD"], root, runner)
    behind, ahead = parse_ahead_behind(revlist)
    # No tracking branch -> git errors -> git_read returns "". Distinguish that from
    # an in-sync upstream (which returns "0\t0") so the briefing can suppress the
    # misleading "behind 0, ahead 0 (as of last fetch)" line when no upstream exists.
    has_upstream = bool(revlist.strip())

    branch_vv = git_read(["branch", "-vv"], root, runner)
    prune = merged_branch_candidates(branch_vv, current=current, default=default)

    # Stale-worktree candidates: parse `worktree list --porcelain`, derive the
    # gone/merged branch set from the same branch -vv text, classify. A read error
    # degrades to [] (parse_worktrees("") -> []), so the field never crashes.
    worktrees = parse_worktrees(
        git_read(["worktree", "list", "--porcelain"], root, runner), root
    )
    gone = set(merged_branch_candidates(branch_vv, current=current, default=default))
    stale_worktrees = stale_worktree_candidates(worktrees, gone, path_exists=path_exists)

    stashes = parse_stash_count(git_read(["stash", "list"], root, runner))

    return {
        "dirty": p["dirty"],
        "staged": p["staged"],
        "unstaged": p["unstaged"],
        "untracked": p["untracked"],
        "behind": behind,
        "ahead": ahead,
        "upstream": has_upstream,
        # SH-6: the canonical ff-pull gate (clean tree AND behind>0), computed by
        # the same pure helper /ca:standup acts on — no re-derivation in prose.
        "ff_pull_eligible": ff_pull_eligible(porcelain, behind),
        "unpushed": ahead,  # alias: ahead == commits not yet pushed upstream
        "prune_candidates": prune,
        "stale_worktrees": stale_worktrees,
        "stashes": stashes,
    }


def has_source(root):
    """True if the repo contains any file that isn't arbiter/scaffold cruft —
    distinguishes brownfield (adopt existing code) from greenfield. Returns on the
    first match, so it does not walk a large tree."""
    excl_top = {".git", ".codearbiter", ".claude", "legacy"}
    excl_names = {"README.md", "LICENSE", ".gitignore", "AGENTS.md", "CLAUDE.md", ".gitmodules"}
    for cur, dirs, files in os.walk(root):
        if cur == root:
            dirs[:] = [d for d in dirs if d not in excl_top]
        else:
            dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            if fn not in excl_names:
                return True
    return False


def main():
    utf8_stdio()
    root = project_root()
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")

    # /dev developer-override is per-session: clear its statusline marker on
    # startup — a new session restores orchestration.
    try:
        os.remove(os.path.join(root, ".codearbiter", ".markers", "dev-active"))
    except OSError:
        pass

    enabled, malformed = frontmatter_enabled(ctx)
    if not enabled:
        if malformed:
            print("codeArbiter: .codearbiter/CONTEXT.md is present but its frontmatter is "
                  "malformed (opening '---' with no closing '---'). The plugin is DORMANT — "
                  "fix the frontmatter to activate.", file=sys.stderr)
        sys.exit(0)

    # --- Arbiter active: inject persona ---
    orch = os.path.join(plugin, "ORCHESTRATOR.md")
    orch_text = read_text(orch)
    if orch_text is not None:
        sys.stdout.write(orch_text)
        print()
    else:
        print(f"codeArbiter: ORCHESTRATOR.md not found at {orch} — persona not injected. "
              f"Check CLAUDE_PLUGIN_ROOT.", file=sys.stderr)

    # --- Inject live startup state ---
    print("=== codeArbiter startup state ===")

    ctx_text = read_text(ctx) or ""
    if not INITIALIZED_RE.search(ctx_text):
        if has_source(root):
            print("NOT INITIALIZED: source exists but .codearbiter/CONTEXT.md is a stub. "
                  "Run /ca:create-context before any other command.")
        else:
            print("NOT INITIALIZED: empty project. Run /ca:decompose to begin.")
        print("Type /ca:commands for the catalog.")
        sys.exit(0)

    m = STAGE_RE.search(ctx_text)
    print(f"stage: {m.group(1) if m else '—'}")

    oq = os.path.join(root, ".codearbiter", "open-questions.md")
    oq_text = read_text(oq)
    if oq_text is not None:
        confirms = CONFIRM_RE.findall(oq_text)
        if confirms:
            print(f"BLOCKING questions (CONFIRM-NN): {len(confirms)} — must resolve before "
                  f"dependent work proceeds:")
            for ln in oq_text.splitlines():
                if CONFIRM_RE.search(ln):
                    print(f"  {ln}")
        else:
            print("open questions: 0")

    ot = os.path.join(root, ".codearbiter", "open-tasks.md")
    ot_text = read_text(ot)
    if ot_text is not None:
        tn = sum(1 for ln in ot_text.splitlines() if ln.startswith("- "))
        print(f"in-flight tasks: {tn}")

    print("Present this state, then await a slash command. Type /ca:commands for the catalog.")

    # --- Standup briefing (SH-1 full / SH-2 offer) ---
    # Additive, AFTER the startup-state block. Read-only: no git mutation here.
    #   first session of the day (no marker)  -> full briefing + drop marker
    #   later session today, actionable       -> exactly ONE offer line
    #   later session today, nothing to do    -> emit nothing
    # The git-derived `summary` (dirty/behind/ahead/prune candidates/worktrees/
    # stashes) is assembled below from read-only git reads; any_actionable(summary)
    # then decides whether a later same-day session emits its single offer line. A
    # clean repo yields an all-quiet summary, so later sessions stay silent — the
    # conservative default.
    date_iso = local_date_iso()
    marker_present = not should_emit_briefing(root, date_iso)

    # Read-only git assembly. ahead/behind comes from the LAST COMPLETED fetch
    # (current local refs); we annotate it as possibly stale and kick a DETACHED
    # fetch to refresh for NEXT time without blocking this hook's return.
    current = head_branch(root)
    default = os.environ.get("CODEARBITER_BASE_BRANCH") or "main"
    summary = assemble_summary(root, current=current, default=default)
    spawn_background_fetch(root)  # detached; never awaited

    mode = briefing_mode(marker_present, any_actionable(summary))
    if mode == "full":
        print()
        print(f"=== codeArbiter daily briefing ({date_iso}) ===")
        print("First session of the day. Daily standup briefing (read-only).")
        render_full_briefing(root, summary)
        write_standup_marker(root, date_iso)
    elif mode == "offer":
        print(OFFER_LINE)

    sys.exit(0)


if __name__ == "__main__":
    main()
