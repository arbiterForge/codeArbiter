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

import concurrent.futures
import copy
import datetime
import json
import os
import re
import subprocess
import sys
import time

from _gitexec import git_executable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011): plugin root + capability flags
from _durabilitylib import is_ephemeral_path  # noqa: E402
from _hooklib import (  # noqa: E402
    frontmatter_enabled, get_host, marker_root, project_root, set_host,
    utf8_stdio, write_text_atomic,
)
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
import _taskboardlib  # noqa: E402 — shared task-board count/staleness logic
import _provenancelib  # noqa: E402 — shared provenance drift detection (T-16)
import _updatelib  # noqa: E402 — update-available notifier (cache read + notice text)
# T-06 (#437): the write-ahead audit-close ledger moved to _modelib.py — see
# that module's docstring. `_DEV_PENDING_CLOSE_MAX` is re-imported because a
# pre-existing test reads it off this module's namespace. T-42/T-47 (#437,
# mode-plane-deterministic-flip): the mode plane itself (MODES, current_mode,
# write_mode, the audit-line builder) is imported as a module so every call
# site stays explicit about which layer it is calling into.
from _modelib import _DEV_PENDING_CLOSE_MAX, _settle_dev_close  # noqa: E402,F401
import _modelib  # noqa: E402

INITIALIZED_RE = re.compile(r"<!--\s*INITIALIZED\s*-->")
STAGE_RE = re.compile(r"^stage:\s*([0-9]+)", re.I | re.M)
CONFIRM_RE = re.compile(r"CONFIRM-[0-9]+")

# reliability-007 (#190): project_root() is now _hooklib.project_root — imported
# above, not a local copy. The prior local copy ran `git rev-parse
# --show-toplevel` from the hook's own cwd and fell back to os.getcwd(),
# skipping the CLAUDE_PROJECT_DIR-first read _hooklib.project_root() exists
# for. session-start is the linchpin hook (installs git-enforce hooks, writes
# standup/dev markers, appends overrides.log) — a wrong root there silently
# targeted the wrong repository.


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
OFFER_LINE_TEMPLATE = "codeArbiter: hygiene items pending — run {standup}"
OFFER_LINE = OFFER_LINE_TEMPLATE.format(standup="/ca:standup")


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
        [git_executable(), "-C", root, *args],
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
    return subprocess.Popen([git_executable(), "-C", root, *args], **kw)


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


def governance_line(root, ctx_text=None, ot_text=None, oq_text=None):
    """Display-only governance summary reused from statusline.arbiter_state:
    `stage:N tasks:N q:N over:N`. Returns "" when arbiter isn't enabled or on any
    failure. DISPLAY ONLY — never acts on these counts.

    performance-003 (#194): ctx_text/ot_text/oq_text let the caller (main(),
    which already read CONTEXT.md/open-tasks.md/open-questions.md earlier in
    the SAME invocation) thread that content through so arbiter_state doesn't
    re-read those three files a second time. None (the default) preserves the
    original behavior (arbiter_state reads them itself)."""
    sl_mod = _statusline()
    if sl_mod is None:
        return ""
    try:
        st = sl_mod.arbiter_state(root, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
    except Exception:  # noqa: BLE001
        return ""
    if not st:
        return ""
    return (f"governance: stage:{st['stage']} tasks:{st['tasks']} "
            f"q:{st['q']} over:{st['over']}")


def render_full_briefing(root, summary, ctx_text=None, ot_text=None, oq_text=None):
    """Print the read-only daily briefing body: git hygiene state (with the
    last-fetch staleness note) and the display-only governance line. No mutation.

    ctx_text/ot_text/oq_text (performance-003) are threaded straight through to
    governance_line — see its docstring."""
    print(f"  working tree: {'dirty' if summary['dirty'] else 'clean'} "
          f"(staged:{summary['staged']} unstaged:{summary['unstaged']} "
          f"untracked:{summary['untracked']})")
    if summary.get("upstream", True):
        print(f"  upstream: behind {summary['behind']}, ahead {summary['ahead']} "
              f"{STALE_REFS_NOTE}")
    else:
        print("  upstream: none (no tracking branch)")
    if summary.get("ff_pull_eligible"):
        print(f"  ff-pull available: clean tree, behind upstream — "
              f"{get_host().cmd_ref('standup')} to fast-forward")
    if summary["prune_candidates"]:
        print(f"  merged-branch prune candidates: "
              f"{', '.join(summary['prune_candidates'])}")
    if summary["stashes"]:
        print(f"  stashes: {summary['stashes']}")
    gov = governance_line(root, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
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
    tests. Read-only: identifies candidates only — never removes a worktree.

    performance-002 (#194): the five reads above are independent (each degrades
    its own field on failure; none depends on another's output), so they fan out
    across a small thread pool instead of running strictly sequentially — on
    Windows especially, process-creation overhead for `git` compounds when five
    spawns block one after another. Results are gathered before any parsing runs,
    so the parsed values are byte-identical to the sequential form."""
    reads = {
        "porcelain": ["status", "--porcelain=v1"],
        "revlist": ["rev-list", "--left-right", "--count", "@{u}...HEAD"],
        "branch_vv": ["branch", "-vv"],
        "worktree_raw": ["worktree", "list", "--porcelain"],
        "stash_raw": ["stash", "list"],
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(reads)) as ex:
        futures = {name: ex.submit(git_read, args, root, runner) for name, args in reads.items()}
        out = {name: f.result() for name, f in futures.items()}

    porcelain = out["porcelain"]
    p = parse_porcelain(porcelain)

    revlist = out["revlist"]
    behind, ahead = parse_ahead_behind(revlist)
    # No tracking branch -> git errors -> git_read returns "". Distinguish that from
    # an in-sync upstream (which returns "0\t0") so the briefing can suppress the
    # misleading "behind 0, ahead 0 (as of last fetch)" line when no upstream exists.
    has_upstream = bool(revlist.strip())

    branch_vv = out["branch_vv"]
    prune = merged_branch_candidates(branch_vv, current=current, default=default)

    # Stale-worktree candidates: parse `worktree list --porcelain`, derive the
    # gone/merged branch set from the same branch -vv text, classify. A read error
    # degrades to [] (parse_worktrees("") -> []), so the field never crashes.
    worktrees = parse_worktrees(out["worktree_raw"], root)
    gone = set(merged_branch_candidates(branch_vv, current=current, default=default))
    stale_worktrees = stale_worktree_candidates(worktrees, gone, path_exists=path_exists)

    stashes = parse_stash_count(out["stash_raw"])

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


# --- Statusline pin self-heal (SessionStart) -------------------------------
# A plugin cannot own a statusLine and ${CLAUDE_PLUGIN_ROOT} is NOT expanded in
# settings.json, so wire-statusline.py writes an ABSOLUTE, version-pinned path.
# Nothing re-ran it after a plugin update, so an updated install kept invoking the
# OLD version's statusline.py — stale, and eventually broken when that cache dir
# is pruned. We heal it here every SessionStart: refresh a ca-OWNED pin to the
# current renderer path, persisting ONLY on a real change (no steady-state churn),
# and degrade silently on ANY failure — a wiring refresh must never crash startup.


def _load_wire_statusline(plugin):
    """Load wire-statusline.py (hyphenated filename) from <plugin>/hooks/ as a
    module, or None on any failure."""
    try:
        import importlib.util  # noqa: PLC0415 — lazy by design
        path = os.path.join(plugin, "hooks", "wire-statusline.py")
        spec = importlib.util.spec_from_file_location("wire_statusline", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001
        return None


def heal_statusline_wiring(plugin, settings_path=None, interp=None, loader=None):
    """Refresh a stale ca-OWNED statusLine pin to the current renderer path.
    Returns True iff settings.json was rewritten. Fully guarded: any failure —
    including a corrupt settings.json (which wire-statusline raises SystemExit on)
    — degrades to False so it never crashes session startup.

    reliability-009: settings.json is the user's WHOLE host configuration, not
    a ca-owned file — a full read-modify-write of it must not clobber a change
    made by a concurrent session (or the user) between our load and our save.
    Narrow that window by reloading the file fresh immediately before writing:
    if it differs from what we loaded, some other writer touched it in the
    interim, so we SKIP this heal entirely (never overwrite that write with
    our now-stale snapshot) — a later session's heal simply retries.

    NON-DURABLE ROOTS ARE INERT (found in-session 2026-07-25, after it broke the
    maintainer's statusline three times in one day). This hook runs on EVERY
    SessionStart and pins an ABSOLUTE path into the user's GLOBAL settings.json.
    A session started inside a git worktree (subagents run in
    `<repo>/.claude/worktrees/<id>/`) resolves `plugin` to that worktree, and the
    heal pinned the global config at a directory whose entire purpose is to be
    pruned. When the root is not durable we leave the existing pin exactly as it
    is — not healed, not cleared, no error.

    wire-statusline.refresh_if_stale enforces the same rule (it is the producer,
    and also reachable by a human running `--plugin-root <worktree>`), so this
    check is deliberately REDUNDANT — but not decoratively so. `_load_wire_
    statusline` loads that producer OUT OF `plugin` itself: a worktree cut from a
    pre-fix branch supplies a pre-fix, unguarded producer, while THIS file may
    have been loaded from somewhere else entirely (main() honours
    $CLAUDE_PLUGIN_ROOT independently of where session-start.py came from). The
    highest-consequence write on the machine gets to refuse on its own account
    rather than on the good behaviour of whatever version it happened to load.
    Both call sites share the one predicate, so there is no second policy to
    drift."""
    try:
        script_abs = os.path.join(plugin, "hooks", "statusline.py")
        if is_ephemeral_path(script_abs):
            return False
        ws = (loader or _load_wire_statusline)(plugin)
        if ws is None:
            return False
        spath = settings_path or ws.settings_path(None)
        interp = interp or ws.default_interp(None)
        settings, exists = ws.load_settings(spath)
        if not exists:
            return False
        original = copy.deepcopy(settings)
        if not ws.refresh_if_stale(settings, script_abs, interp):
            return False
        fresh, fresh_exists = ws.load_settings(spath)
        if not fresh_exists or fresh != original:
            return False  # changed underneath us — skip, retry next session
        ws.save_settings(spath, settings)
        return True
    except (Exception, SystemExit):  # noqa: BLE001 — heal is best-effort, never fatal
        return False


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


# #271 C-5 — session-scoping the repo-global dev marker. The marker itself
# carries no owner: it is dropped by /dev's own prose (dev.md), which has no
# reliable way to stamp a real session_id into its content (slash-command
# prose never receives the hook JSON payload — only actual HOOKS do). So
# ownership is tracked SEPARATELY, by SessionStart itself: every invocation
# records (its OWN session_id, now) as "the last session known to have
# started in this repo" BEFORE deciding what to do with the dev marker.
#
# This is a heuristic, not true liveness detection (there is no SessionEnd
# signal this hook can rely on) — documented tradeoff, not a defect. The
# record's timestamp is ANCHORED TO THE OWNER, not to "whatever session
# started most recently" — that distinction is load-bearing (a review caught
# an earlier draft that refreshed it unconditionally on every invocation,
# which meant an unrelated session B/C/D/... starting in an otherwise-active
# repo kept sliding the window forward forever and the marker became
# immortal). The write is therefore CONDITIONAL, decided AFTER checking the
# marker, not before:
#   - no live marker at all: refresh freely — "the session that could next
#     enter /dev is me" is exactly the fact this record exists to hold.
#   - live marker AND session_id == prev_sid: refresh. This is the owner
#     heartbeating through a resume/compaction, and it's what keeps a
#     genuinely long /ca:dev sitting from being force-closed at the 6h mark.
#   - live marker AND a DIFFERENT session_id: do NOT write. `prev_ts` stays
#     anchored to the OWNER's last known activity — a different session
#     merely observing the marker must not reset that clock, or it would
#     never elapse in any repo that sees regular unrelated activity.
#
# Net effect: a marker owned by a session that crashed is left alone by every
# later, unrelated session (they cannot know it is dead) but self-heals
# DEV_SESSION_LIVENESS_WINDOW after the OWNER's own last recorded activity —
# not after the most recent unrelated SessionStart. Symmetric residual: a
# genuinely live /ca:dev sitting untouched (no resume/compaction of its own)
# for longer than the window can still be force-closed by a later session,
# same as the pre-#271 behavior would have done immediately. No session_id
# available on this invocation/host (Codex parity unverified), or no prior
# record at all, degrades to the original unconditional clear — a marker that
# can NEVER be cleared is a worse failure mode than one cleared too eagerly.
DEV_SESSION_LIVENESS_WINDOW = 6 * 3600  # 6h: generous single-sitting bound


def _dev_session_owner_path(root):
    return os.path.join(root, ".codearbiter", ".markers", "dev-session-owner.json")


def _read_dev_session_owner(root):
    """(session_id, ts) last recorded by ANY SessionStart invocation in this
    repo, or (None, None) on an absent/corrupt/malformed record. Never
    raises."""
    try:
        with open(_dev_session_owner_path(root), encoding="utf-8") as f:
            data = json.load(f)
        sid = data.get("session_id")
        ts = data.get("ts")
        if isinstance(sid, str) and sid and isinstance(ts, (int, float)):
            return sid, float(ts)
    except Exception:  # noqa: BLE001 — corrupt/absent record -> no signal
        pass
    return None, None


def _write_dev_session_owner(root, session_id, ts):
    """Best-effort refresh of the last-known-active-session record. Never
    raises — a write failure just means the NEXT SessionStart degrades to the
    conservative no-prior-record fallback, exactly as if this were the first
    session ever."""
    try:
        path = _dev_session_owner_path(root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomic(path, json.dumps({"session_id": session_id, "ts": ts}))
    except Exception:  # noqa: BLE001 — must never brick session startup
        pass


def _mode_session_seen_path(root):
    return os.path.join(root, ".codearbiter", ".markers", "mode-session-seen.json")


def _read_mode_session_seen(root):
    """True iff `session_id`'s SessionStart has run in this repo before.

    KEYED BY SESSION, exactly as the mode marker is. An earlier form stored a
    single repo-global scalar — the id of whichever session started last — and
    two live sessions then erased each other's record: A starts, B starts, A
    compacts and reads "not seen", so the compaction clears A's live mode and
    mints an `exit` row for a mode A never left. That is the SAME observable
    failure this record was introduced to fix, merely moved from "a concurrent
    session owns the legacy marker" to "a concurrent session exists at all".
    A per-session question cannot be answered by a repo-global answer.

    DELIBERATELY SEPARATE from `dev-session-owner.json`. That record anchors the
    legacy `dev-active` marker's force-close and is guarded by a liveness window
    — a bystander session must NOT overwrite it, or it would force-close a
    concurrent owner's marker early. The mode plane needs a different question
    answered ("has THIS session's SessionStart run before?"), and overloading one
    record with both meanings is what let a compaction clear a live mode: when a
    different live session owned the legacy marker, `clear_mode_marker` returned
    early to protect that record, leaving the mode plane with no anchor at all.

    Never raises; an absent or corrupt record reads as "not seen", which routes
    to the conservative branch (clear), never to a silent retain.
    """
    return _read_mode_session_seen_map(root)


def _read_mode_session_seen_map(root):
    """`{session_id: ts}` for every session seen in this repo, or `{}`.

    Never raises; an absent or corrupt record reads as "nothing seen", which
    routes to the conservative branch (clear), never to a silent retain."""
    try:
        with open(_mode_session_seen_path(root), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and not isinstance(data.get("session_id"), str):
            return {k: v for k, v in data.items() if isinstance(k, str)}
        # Legacy single-session record ({"session_id": …, "ts": …}) written by
        # an earlier build. Read it forward rather than discarding it: dropping
        # it would clear a live mode on the very first compaction after an
        # upgrade, which is the failure this whole record exists to prevent.
        if isinstance(data, dict) and isinstance(data.get("session_id"), str):
            return {data["session_id"]: data.get("ts")}
    except Exception:  # noqa: BLE001 — absent/corrupt record -> no signal
        pass
    return {}


def _write_mode_session_seen(root, session_id, ts):
    """Record that `session_id`'s SessionStart has run, WITHOUT disturbing any
    other session's entry. Never raises — a write failure degrades to "not
    seen", i.e. the next compaction clears the mode. That is the safe
    direction: it restores `arbiter` (gates ON) rather than silently retaining
    a gates-off posture on unproven state.

    The read-modify-write here is not serialized, so two simultaneous starts
    can lose one entry. That fails toward clearing a mode rather than retaining
    one, which is the direction ADR-0030 requires; the mode marker's own
    concurrency is tracked separately."""
    try:
        path = _mode_session_seen_path(root)
        seen = _read_mode_session_seen_map(root)
        seen[str(session_id)] = ts
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomic(path, json.dumps(seen))
    except Exception:  # noqa: BLE001 — must never brick session startup
        pass


# --- #396/T-06: write-ahead ledger machinery extracted to _modelib ----------
# `_settle_dev_close` and its pending-close record (the durable, retryable
# exit machinery) moved to `_modelib.py` (mode-plane-deterministic-flip #437,
# imported at module top) — that module now owns the mode plane's audit-close
# ledger generally; `clear_mode_marker` below is its SessionStart-specific
# caller. Pure move, no behavior change to the ledger itself — see
# `_modelib.py`'s module docstring.
#
# T-42/T-47 (#437): `clear_mode_marker` is now the SINGLE SessionStart-time
# settlement pass over BOTH the mode plane's session-keyed entries (T-42/
# AC-4) and the legacy repo-global `dev-active` marker (T-47/AC-41) — merged
# into one function DELIBERATELY, not left as two. An earlier draft split
# them; both independently called `_read_dev_session_owner`/
# `_write_dev_session_owner`, and because main() had to run one before the
# other, the FIRST function's write leaked into the SECOND function's read
# within the same invocation — a first-ever session with an orphaned legacy
# marker was wrongly recognised as "the confirmed owner, resuming" (self-
# defeating T-47's own force-close-when-abandoned contract). One function,
# one read of the owner record per invocation, removes the seam entirely.
#
# The owner-liveness heuristic (prev_sid/prev_ts, DEV_SESSION_LIVENESS_WINDOW)
# is VERBATIM the pre-#437 `clear_dev_marker`'s own contract (see the module
# comment above DEV_SESSION_LIVENESS_WINDOW) — this function is that
# function's direct successor, not a new mechanism. Its `is_owner` branch has
# ONE new consequence: when the confirmed owner resumes and the legacy
# marker is STILL live, this is exactly when T-47's conversion fires — write
# a `dangerous` mode entry for the owner and remove the legacy marker,
# instead of leaving it untouched forever. No audit row is minted for that
# conversion: the historical `DEV: enter` row already on the trail keeps
# backing `dangerous` via `_modelib.ledger_backs`'s legacy acceptance
# (AC-11) — minting a fresh `MODE: dangerous enter` would misrepresent a
# storage-format migration as a new operator-initiated transition. Everything
# ELSE (force-close on an abandoned marker, the liveness window, the
# unconditional-clear degrade with no session_id/no prior record) is
# unchanged and is exercised by the SAME test corpus the pre-#437 code was:
# `TestDevExitAudit` and `TestDevExitRetryablePendingClose`
# (plugins/ca/hooks/tests/test_session_start.py) — repointed at this
# function's new name, with exactly two assertions updated where the
# observable OUTCOME changed (the owner-resume case now converts+removes
# instead of leaving the marker untouched — see that file for the reasoning
# on each).
#
# A session_id that is NOT recognised as the current owner clears only ITS
# OWN prior mode-plane entry (T-42), never a different session's — a force-
# close-other-sessions engine over the MODE PLANE is out of scope (residual:
# an abandoned foreign session's mode entry can linger indefinitely; nothing
# UNSAFE follows, since no live session ever reads a dead session_id's mode
# again). The LEGACY marker's force-close is the one exception, inherited
# unchanged from the pre-#437 contract: it has no session identity of its
# own to preserve, so an abandoned marker is safe to close on any session's
# behalf once the liveness window has genuinely elapsed.
#
# CROSS-LANE NOTE for Lane B (prompt-submit.py, AC-23/24/25): this function
# treats a SessionStart re-fire for the SAME session_id as a "resume/compact
# heartbeat" and does NOT clear mode-plane state in that case — i.e. mode is
# designed to SURVIVE compaction for the owning session. No `source` field
# (startup vs. resume vs. compact) is read from the hook payload anywhere in
# this repo today (verified by grep before writing this) — the owner-
# liveness heuristic is a durable proxy for it, not the real signal, so it
# is imprecise in the same documented way the pre-#437 heuristic always was.
# If Lane B's AC-25 test seeds a DIFFERENT session_id per "turn" rather than
# reusing one across a simulated compaction, that test will observe mode
# reset to arbiter here — please confirm your fixture reuses session_id.


def clear_mode_marker(root, host_name=None, session_id=None, now=None):
    """The single SessionStart-time mode-plane + legacy-dev-active
    settlement pass. See the module comment above for the full contract and
    why this was merged from two functions into one. `now` (epoch seconds)
    is injectable for deterministic tests; defaults to `time.time()`. Never
    raises."""
    now = time.time() if now is None else now
    prev_sid, prev_ts = _read_dev_session_owner(root)
    marker = os.path.join(root, ".codearbiter", ".markers", "dev-active")
    marker_live = os.path.isfile(marker)
    is_owner = bool(session_id) and prev_sid == session_id

    # The mode plane's OWN "have I seen this session" anchor, read before
    # anything below can return, and re-stamped unconditionally afterwards so
    # every exit path records it (several of the branches below return early).
    # It must not be derived from `is_owner`: that answers a different question
    # (does this session own the legacy dev-active marker?), and a bystander
    # session is deliberately NOT allowed to claim that record — which used to
    # leave the mode plane with no anchor and let a compaction clear a live
    # mode. See _read_mode_session_seen.
    mode_seen = bool(session_id) and str(session_id) in _read_mode_session_seen(root)
    if session_id:
        _write_mode_session_seen(root, session_id, now)

    if is_owner:
        # The confirmed owner, resuming/compacting: heartbeat, and
        # opportunistically CONVERT a still-live legacy marker (T-47) — but
        # ONLY where there is nothing to convert over.
        #
        # An unconditional write here contradicted the claim it sat under. The
        # marker removal below is best-effort, so a marker that survives one
        # pass is still live on the next: an owner who flipped back to
        # `arbiter` mid-session had gates turned OFF again by the next
        # compaction, with no operator action and no audit row — the exact
        # unaudited gates-off transition ADR-0030 forbids. Gating on the
        # arbiter default keeps this a MIGRATION (legacy marker, no mode-plane
        # opinion yet) instead of an override of the user's live choice, and is
        # what actually lets AC-25 re-inject the SAME mode after a compaction.
        _write_dev_session_owner(root, session_id, now)
        # "No opinion yet" is the ABSENCE of an entry, not the arbiter VALUE:
        # `current_mode` answers `arbiter` for both "never flipped" and
        # "deliberately flipped back", and only the first may be migrated over.
        # The raw state map is the only place that distinction survives.
        mode_state, _diag = _modelib._read_mode_state(root)
        unconverted = str(session_id) not in mode_state
        if marker_live and unconverted and _modelib.write_mode(session_id, "dangerous", root=root):
            try:
                os.remove(marker)
            except OSError:
                # The conversion landed; a leftover legacy file is harmless
                # — the NEXT is_owner pass just retries the removal (write_
                # mode(session_id, "dangerous") is idempotent).
                pass
        return

    # Not the recognised owner. Two independent settlements follow.

    # (1) T-42/AC-4: clear session_id's OWN mode-plane entry, if any — never
    # a different session's (see the module comment's force-close-scope
    # note). Independent of the legacy marker's liveness window below.
    #
    # `not mode_seen` is what distinguishes a NEW session from this session
    # resuming or compacting. AC-4 is in fact satisfied structurally — the mode
    # file is keyed by session_id, so a genuinely new session has no entry and
    # already reads `arbiter` — which means this clear can only ever fire for a
    # session that previously flipped. Without the guard that is exactly the
    # compaction AC-25 exists to preserve, and the mode would be cleared out
    # from under a live session.
    if session_id and not mode_seen:
        mode, _diag = _modelib.current_mode(session_id, root=root)
        if mode != _modelib.MODES[0]:
            if host_name is None:
                try:
                    # get_host() (#257): resolves the SAME Host run(host)
                    # injected instead of a second load.
                    host_name = get_host().name
                except Exception:  # noqa: BLE001 — must never brick session startup
                    host_name = "unknown"
            # T-43/AC-35: this line names NO command — unlike the retired
            # clear_dev_marker's `cmd_ref("arbiter")` (which stamped a
            # permanent dangling reference into overrides.log once
            # `/ca:arbiter` was deleted), _modelib._mode_audit_line's NOTE
            # is a bare "—".
            line = _modelib._mode_audit_line("exit", mode, host_name=host_name, now=now)
            # #396: stage-then-append BEFORE the state mutation below, so an
            # interruption between them leaves the row owed and replayable
            # rather than silently lost.
            _settle_dev_close(root, new_line=line, host_name=host_name)
            _modelib.write_mode(session_id, _modelib.MODES[0], root=root)

    # (2) T-47/legacy: the dev-active marker's owner-liveness-gated
    # force-close — verbatim the pre-#437 `clear_dev_marker` contract.
    if not marker_live:
        # No live marker: replay anything already owed from an earlier
        # crash (#396), and record this session as a candidate future owner
        # — harmless, and exactly what let a later invocation recognise it.
        _settle_dev_close(root, host_name=host_name)
        if session_id:
            _write_dev_session_owner(root, session_id, now)
        return

    if session_id and prev_sid:
        # is_owner was already False above, so prev_sid != session_id here:
        # a DIFFERENT, possibly still-live session owns this marker.
        if (now - prev_ts) < DEV_SESSION_LIVENESS_WINDOW:
            # The owner's own clock hasn't elapsed yet — do not touch the
            # record or the marker.
            return
        # Stale beyond the window: proceed to force-close below. Deliberately
        # do not write a fresh owner record here either — there is no live
        # owner left to anchor a new one to.

    if session_id and not prev_sid:
        # No prior record at all — no signal to protect a concurrent owner;
        # seed the record for next time and fall through to force-close.
        _write_dev_session_owner(root, session_id, now)

    # Force-close: either no session_id/no prior record (unconditional-clear
    # fallback), or a genuinely stale owner beyond the window.
    if host_name is None:
        try:
            host_name = get_host().name
        except Exception:  # noqa: BLE001 — must never brick session startup
            host_name = "unknown"
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (f"[{ts}] | BY: session-cleanup | HOST: {host_name} | DEV: exit | NOTE: cleared by "
            f"SessionStart (prior session ended mid-dev with no live owner)\n")
    # #396: stage-then-append-then-clear, all inside one settlement step.
    _settle_dev_close(root, marker=marker, new_line=line, host_name=host_name)


def provenance_drift_line(root, runner=None):
    """One-line SessionStart drift notice, or "" when clean/degraded.

    Wraps _provenancelib.startup_drift_line; any failure degrades to "" so the
    linchpin hook never crashes (mirrors the task-board guard). `runner` is
    injectable so tests are deterministic/offline; production passes None which
    lets the lib bind its default `git -C root hash-object` runner. (T-16)"""
    try:
        return _provenancelib.startup_drift_line(
            root, runner=runner, cmd_ref=get_host().cmd_ref)
    except Exception:  # noqa: BLE001 — never crash session startup
        return ""


# --- Update-available notifier (spec: update-available-notifier.md) ---------
# codeArbiter ships via a third-party marketplace, which Claude Code does NOT
# auto-update by default. This surfaces a single line when the cached "latest"
# GitHub release exceeds the installed plugin.json version — reading ONLY the
# user-global cache (one file read, AC-3: no synchronous network call added to
# this hot path). The cache itself is refreshed off-path by a DETACHED spawn of
# update-refresh.py (below), mirroring spawn_background_fetch's git-fetch
# pattern; that refresh is separately gated to at most once per day by
# _updatelib.refresh_if_stale's own checked_at check (AC-4).


def update_notice_line(plugin):
    """The single-line update-available notice (AC-1/AC-2), or "" when no update
    is due or on ANY degrade (missing/corrupt cache, missing/corrupt plugin.json)
    — never raises (AC-3). Reads the cache and the installed version only; makes
    no network call itself."""
    try:
        state = _updatelib.read_state(_updatelib.state_path())
        latest = state.get("latest") if isinstance(state, dict) else None
        installed = _updatelib.installed_version(plugin)
        return _updatelib.notice_line(installed, latest) or ""
    except Exception:  # noqa: BLE001 — never crash session startup
        return ""


def _detached_update_refresh_spawner(plugin):
    """Default spawner: launch `<python> <plugin>/hooks/update-refresh.py` fully
    DETACHED — same decoupling as _detached_fetch_spawner (child stdout/stderr to
    DEVNULL, new session/process group so it outlives this process and is never
    awaited)."""
    script = os.path.join(plugin, "hooks", "update-refresh.py")
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kw["creationflags"] = flags
    else:
        kw["start_new_session"] = True
    return subprocess.Popen([sys.executable, script], **kw)


def spawn_background_update_refresh(plugin, spawner=None):
    """Kick a DETACHED update-refresh.py that does NOT block the hook (AC-3: the
    network call this eventually makes is entirely off SessionStart's hot path).
    Returns the spawned process handle (for tests) or None on any spawn failure —
    NEVER awaited, so a hung or unreachable network cannot stall SessionStart.
    `spawner(plugin) -> proc` is injectable; the default detaches per-platform."""
    spawn = spawner or _detached_update_refresh_spawner
    try:
        return spawn(plugin)
    except Exception:  # noqa: BLE001 — spawn failure tolerated silently
        return None


_STDIN_PAYLOAD = None  # None = not read yet; a dict once read (possibly empty)


def _stdin_payload():
    """The SessionStart hook's raw JSON payload as a dict, read AT MOST ONCE.

    stdin is a stream: whoever reads it first consumes it, so the session_id
    reader and the `marker_root` payload cannot each do their own read. This
    caches the parsed dict and both callers share it.

    Why `marker_root` needs the payload at all (#437 regression): its host
    delegate resolves a linked worktree by SPAWNING GIT when it has no payload
    to resolve from. An argument-less call therefore adds a git subprocess to
    every session start, and on Windows a bare `git` can resolve from the
    current directory — so a repository containing its own `git.exe` gets that
    one executed. When that spawn misbehaves, startup dies BEFORE the
    git-enforcer install below, and the repo silently loses the H-01/H-02
    backstop that closes `--no-verify` (ADR-0015).

    Returns {} on any failure, absence, or malformed payload — the same silent
    degradation `_session_id_from_stdin` has always had, for the same reason:
    a host that supplies no payload is a normal condition, not an error worth
    a breadcrumb on every session start."""
    global _STDIN_PAYLOAD
    if _STDIN_PAYLOAD is not None:
        return _STDIN_PAYLOAD
    _STDIN_PAYLOAD = {}
    try:
        if sys.stdin.isatty():
            return _STDIN_PAYLOAD
        raw = sys.stdin.read()
        if not raw.strip():
            return _STDIN_PAYLOAD
        data = json.loads(raw)
        if isinstance(data, dict):
            _STDIN_PAYLOAD = data
    except Exception:  # noqa: BLE001 — must never brick session startup
        pass
    return _STDIN_PAYLOAD


def _session_id_from_stdin():
    """Best-effort session_id from the SessionStart hook's own JSON payload
    (#271 C-5) — session-start.py has never read its stdin before this. Reads
    directly rather than via `_hooklib.read_input()` so an absent/empty
    session_id degrades SILENTLY (it is a normal, expected condition on a host
    that doesn't supply one — not a parse error worth a `warn()` breadcrumb on
    every single session start). Guards against a blocking read on an
    interactive stdin the same way statusline.py's `main()` does (`isatty()`
    check) — this hook must never hang session startup waiting for input that
    will never arrive. Returns "" on any failure, absence, or malformed
    payload; the caller treats an empty session_id as "unavailable" and
    degrades to the pre-#271 unconditional-clear behavior."""
    try:
        return str(_stdin_payload().get("session_id") or "")
    except Exception:  # noqa: BLE001 — must never brick session startup
        return ""


# --------------------------------------------------------------------------- #
# T-44 (#437): startup-state emitters. `session-start.py:1091-1195` (pre-#437)
# printed everything after the persona unconditionally, gated only on
# frontmatter — SMARTS ruled (strength `strong`, plan alternatives-considered)
# against wholesale mode-based suppression and FOR decomposing into per-mode
# COMPOSABLE emitters instead: the block is eight independent things with
# different audiences (banner, stage:, CONFIRM-NN, task summary, provenance
# drift, update notice, trailer, daily briefing), and the lines wholesale
# suppression would remove are precisely the ones a gates-off session most
# needs (Securable).
#
# Each emitter below is INDIVIDUALLY CALLABLE (AC-30) with its own explicit
# inputs — no hidden env/global/clock reads inside any of them (a `today`/
# `now` argument is always accepted for injection) — and prints directly,
# mirroring this file's pre-existing style (`render_full_briefing` already
# printed rather than returning lines; T-44 does not change that convention,
# only names and isolates each piece so it can be exercised alone).
# --------------------------------------------------------------------------- #


def emit_banner(host_name, mode):
    """AC-32: host + active mode — emitted in EVERY mode, unconditionally."""
    print(f"host: {host_name}")
    print(f"mode: {mode}")


def emit_not_initialized(root, host, mode):
    """The NOT-INITIALIZED early-exit banner — mode-aware TEXT, not an
    unconditional print (a non-arbiter mode has no commands, so instructing
    the user to run {create-context}/{decompose}/{commands} would name a
    surface that mode cannot use)."""
    if mode != _modelib.MODES[0]:
        print("NOT INITIALIZED: this repo has not opted into codeArbiter's "
              "governance workflow. No commands are available in this mode.")
        return
    if has_source(root):
        print(f"NOT INITIALIZED: source exists but .codearbiter/CONTEXT.md is a stub. "
              f"Run {host.cmd_ref('create-context')} before any other command.")
    else:
        print(f"NOT INITIALIZED: empty project. Run {host.cmd_ref('decompose')} to begin.")
    print(f"Type {host.cmd_ref('commands')} for the catalog.")


def emit_stage(ctx_text):
    """AC-32: 'stage: N' — emitted in EVERY mode, unconditionally."""
    m = STAGE_RE.search(ctx_text)
    print(f"stage: {m.group(1) if m else '—'}")


def emit_confirm_nn(oq_text):
    """[CONFIRM-NN] surfacing — pinned ON in every mode (never gated on mode:
    SMARTS's decisive Securable finding is that this is precisely what a
    gates-off session most needs). `oq_text` of None (file unreadable/absent)
    emits nothing, matching the pre-#437 behavior."""
    if oq_text is None:
        return
    confirms = CONFIRM_RE.findall(oq_text)
    if confirms:
        print(f"BLOCKING questions (CONFIRM-NN): {len(confirms)} — must resolve before "
              f"dependent work proceeds:")
        for ln in oq_text.splitlines():
            if CONFIRM_RE.search(ln):
                print(f"  {ln}")
    else:
        print("open questions: 0")


def emit_task_summary(ot_text, today=None):
    """The open-tasks summary. `today` is injectable for deterministic tests;
    defaults to the real local date at the I/O edge. `ot_text` of None
    (file unreadable/absent) emits nothing, matching the pre-#437 behavior."""
    if ot_text is None:
        return
    today = today if today is not None else datetime.date.today()
    try:
        for _line in _taskboardlib.startup_summary(ot_text, today):
            print(_line)
    except Exception as _e:  # noqa: BLE001 — never crash session startup
        n = sum(1 for ln in ot_text.splitlines()
                if ln.startswith("- ") and not ln.startswith("- [x]"))
        print(f"in-flight tasks: {n}")
        print(f"codeArbiter: task-board summary degraded ({_e}); "
              f"check .codearbiter/open-tasks.md", file=sys.stderr)


def emit_provenance_drift(drift_line):
    """The passive provenance-drift notice — ONE line, or none."""
    if drift_line:
        print(drift_line)


def emit_update_notice(update_line):
    """The update-available notice — ONE line, or none."""
    if update_line:
        print(update_line)


def emit_trailer(host):
    """AC-32: the await-a-command trailer + catalog reference. ARBITER-ONLY —
    the caller omits this emitter entirely for a non-arbiter startup (a mode
    with no commands has nothing to 'await')."""
    print(f"Present this state, then await a {host.command_noun}. "
          f"Type {host.cmd_ref('commands')} for the catalog.")


def emit_daily_briefing(root, summary, date_iso, marker_present, ctx_text=None,
                         ot_text=None, oq_text=None, host=None):
    """The daily standup briefing (full/offer/none). AC-32: ARBITER-ONLY —
    the caller omits this emitter entirely for a non-arbiter startup (every
    variant of it references {standup}, a command that mode does not have).

    Returns the resolved kind ("full"/"offer"/"none") so the caller knows
    whether to persist the standup marker — writing that marker is a state
    mutation kept OUT of this function so its printed output stays a pure
    function of its inputs (AC-30)."""
    kind = briefing_mode(marker_present, any_actionable(summary))
    if kind == "full":
        print()
        print(f"=== codeArbiter daily briefing ({date_iso}) ===")
        print("First session of the day. Daily standup briefing (read-only).")
        render_full_briefing(root, summary, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
    elif kind == "offer":
        print(OFFER_LINE_TEMPLATE.format(standup=(host or get_host()).cmd_ref("standup")))
    return kind


def main():
    utf8_stdio()
    # get_host() (#257): resolves the SAME Host run(host) already primed via
    # set_host(), instead of a second hostapi.load_host() disk/probe.
    host = get_host()
    root = project_root()
    # [[NEEDS-TRIAGE root-resolution split]] (#437, found by Lane A, closed
    # here by Lane E): `_modelib.flip()` (prompt-submit.py, Lane B) resolves
    # BOTH the mode marker and the `MODE: … enter` audit row through
    # `marker_root`, not `project_root` — `marker_root` exists precisely
    # because `project_root` splits marker state across linked worktrees
    # (#604). The close/exit half written by THIS file must resolve the
    # SAME way, or an `enter` row and its matching `exit` row can land in
    # two DIFFERENT overrides.log files when this hook runs inside a linked
    # worktree. `mode_root` is therefore used for every mode-plane read/write
    # below (clear_mode_marker, current_mode) — `root` (project_root) stays
    # the source-tree root for everything else (has_source, the task board,
    # provenance, git hygiene).
    plugin = host.plugin_root()
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")

    # T-42/T-47 (#437): the single mode-plane settlement pass — see the
    # module comment above clear_mode_marker for the full contract
    # (owner-liveness heuristic, the merged dev-active migration, the
    # cross-lane note for Lane B's compaction test).
    #
    # The whole mode-plane resolution is guarded because NOTHING here may cost
    # the repository its git-level enforcement backstop. The enforcer install
    # below is what closes `--no-verify` (ADR-0015, H-01/H-02), and it runs
    # AFTER this block — so an exception raised here removes that backstop
    # silently, which is a far worse outcome than an unresolved mode. The raise
    # is not hypothetical: `marker_root` reaches `hostapi.git_toplevel`, whose
    # very first statement calls `git_executable()` OUTSIDE its own try, and
    # `_gitexec._trusted_environment_path` raises RuntimeError on a
    # CODEARBITER_GIT_EXECUTABLE that is relative or no longer a file.
    #
    # The fallback is `arbiter` — gates ON — per ADR-0030's fail direction: a
    # failed transition INTO dangerous mode is safe, a failed transition out of
    # it is not, so unresolvable state resolves to the governed posture. The
    # breadcrumb goes to stderr rather than being swallowed, so a mode plane
    # that is quietly broken on this host is visible instead of merely absent.
    mode_root, session_id = root, ""
    mode, _mode_diag = _modelib.MODES[0], None
    try:
        mode_root = marker_root(_stdin_payload())
        session_id = _session_id_from_stdin()
        clear_mode_marker(mode_root, host.name, session_id)
        if session_id:
            mode, _mode_diag = _modelib.current_mode(session_id, root=mode_root)
    except Exception as exc:  # noqa: BLE001 — startup must survive this
        print(f"codeArbiter: mode plane unavailable this session ({type(exc).__name__}: "
              f"{exc}); continuing as '{_modelib.MODES[0]}' with every gate enforced.",
              file=sys.stderr)

    # Self-heal a stale ca-owned statusLine pin before the dormant gate: the
    # statusline is wired GLOBALLY in ~/.claude/settings.json, so a plugin update
    # must re-point it in every session, not only in arbiter-enabled repos.
    # Gated on the host capability (ADR-0011): a host with no statusline surface
    # (Codex) has nothing to heal.
    if host.has_statusline:
        heal_statusline_wiring(plugin)

    enabled, malformed = frontmatter_enabled(ctx)
    if not enabled:
        if malformed:
            print("codeArbiter: .codearbiter/CONTEXT.md is present but its frontmatter is "
                  "malformed (opening '---' with no closing '---'). The plugin is DORMANT — "
                  "fix the frontmatter to activate.", file=sys.stderr)
        sys.exit(0)

    # #161: arbiter is active — ensure the git-level enforcement backstop
    # (pre-commit/pre-push) is installed and points at the CURRENT plugin path.
    # Idempotent and best-effort: a foreign existing hook is preserved, and any
    # failure here must never break session startup.
    #
    # #441: the enforcer entry install() refreshes lives in the git COMMON dir,
    # shared with every linked worktree — so a session started inside a worktree
    # writes the MAIN repository's entry. _githooks._write_path_entry refuses an
    # ephemeral enforcer on its own account (it is the producer), and this check
    # is deliberately redundant for the same reason heal_statusline_wiring's is:
    # _githooks is imported OUT OF this plugin root, so a worktree cut from a
    # pre-fix branch supplies a pre-fix, unguarded producer. Losing git-level
    # enforcement is silent, so the caller refuses on its own account too. Both
    # sites share the one predicate, so there is no second policy to drift.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _githooks import install as _install_git_hooks
        if is_ephemeral_path(os.path.join(plugin, "hooks", "git-enforce.py")):
            print("codeArbiter: this session's plugin root will not outlive the session "
                  "(linked worktree); leaving the repository's git-level enforcement "
                  "wiring as it is.", file=sys.stderr)
        else:
            _install_git_hooks(root)
    except Exception:  # noqa: BLE001
        # Legacy hosts retain the historical best-effort startup contract.
        # Pi supplies an authenticated absolute executable pair; losing that
        # boundary must surface to the bridge so activation remains fail closed.
        if (os.environ.get("CODEARBITER_GIT_EXECUTABLE")
                or os.environ.get("CODEARBITER_PYTHON_EXECUTABLE")):
            raise

    # T-41 (#437, AC-27): persona injection REMOVED from SessionStart. It
    # moves to the per-turn prompt seam (Lane B, prompt-submit.py) — the
    # persona is now `safety-core.md` + the active mode's body, composed and
    # deduped per (session, mode, compaction generation). SessionStart fires
    # once per session boundary (and on compact), so it cannot react to a
    # mid-session mode flip; the per-turn seam can. This hook still emits the
    # startup-state block below, unconditionally of mode (AC-27: "injects no
    # persona and still emits the startup-state block").

    # --- Startup-state block: per-mode composable emitters (T-44) ---------
    # AC-30: each emitter below is individually callable with only its own
    # explicit inputs. AC-32: host/stage/active-mode are unconditional in
    # every mode; the await-a-command trailer and the daily briefing (which
    # references {standup}) are ARBITER-ONLY.
    print("=== codeArbiter startup state ===")
    # observability-004 (#268): name the RESOLVED host so a dormant/broken
    # host (FailClosedHost -> name "unknown", #255) is visible right in the
    # banner instead of being indistinguishable from a working install.
    emit_banner(getattr(host, "name", "unknown"), mode)

    ctx_text = read_text(ctx) or ""
    if not INITIALIZED_RE.search(ctx_text):
        emit_not_initialized(root, host, mode)
        sys.exit(0)

    emit_stage(ctx_text)

    oq = os.path.join(root, ".codearbiter", "open-questions.md")
    oq_text = read_text(oq)
    emit_confirm_nn(oq_text)

    ot = os.path.join(root, ".codearbiter", "open-tasks.md")
    ot_text = read_text(ot)
    emit_task_summary(ot_text)

    # --- Passive provenance drift notice (T-16, spec pillar 4) ---
    _drift = provenance_drift_line(root)
    emit_provenance_drift(_drift)

    # --- Update-available notice (AC-1/AC-2/AC-3) --------------------------
    _update = update_notice_line(plugin)
    emit_update_notice(_update)

    if mode == _modelib.MODES[0]:
        emit_trailer(host)

        # --- Standup briefing (SH-1 full / SH-2 offer) ---------------------
        # Additive, AFTER the startup-state block. Read-only: no git mutation
        # here. ARBITER-ONLY (AC-32): every variant references {standup}, a
        # command a non-arbiter mode does not have.
        #   first session of the day (no marker)  -> full briefing + drop marker
        #   later session today, actionable       -> exactly ONE offer line
        #   later session today, nothing to do    -> emit nothing
        date_iso = local_date_iso()
        marker_present = not should_emit_briefing(root, date_iso)

        # Read-only git assembly. ahead/behind comes from the LAST COMPLETED
        # fetch (current local refs); we annotate it as possibly stale and
        # kick a DETACHED fetch to refresh for NEXT time without blocking
        # this hook's return.
        current = head_branch(root)
        default = os.environ.get("CODEARBITER_BASE_BRANCH") or "main"
        summary = assemble_summary(root, current=current, default=default)
        spawn_background_fetch(root)  # detached; never awaited
        spawn_background_update_refresh(plugin)  # detached; never awaited (AC-3/AC-4)

        # performance-003 (#194): ctx_text/ot_text/oq_text were already read
        # above for the startup-state block — thread them through so
        # governance_line's arbiter_state() call doesn't re-read the same
        # three files a second time in this same invocation.
        briefing_kind = emit_daily_briefing(
            root, summary, date_iso, marker_present,
            ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text, host=host)
        if briefing_kind == "full":
            try:
                write_standup_marker(root, date_iso)
            except Exception:  # noqa: BLE001 — must never brick session startup
                pass

    sys.exit(0)


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so main()'s `get_host()` call resolves
    to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    set_host(host)
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
