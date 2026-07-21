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
from _hooklib import (  # noqa: E402
    frontmatter_enabled, get_host, project_root, set_host, utf8_stdio,
    write_text_atomic,
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
    our now-stale snapshot) — a later session's heal simply retries."""
    try:
        ws = (loader or _load_wire_statusline)(plugin)
        if ws is None:
            return False
        spath = settings_path or ws.settings_path(None)
        script_abs = os.path.join(plugin, "hooks", "statusline.py")
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


def clear_dev_marker(root, host_name=None, session_id=None, now=None):
    """Clear the per-session /dev statusline marker on startup. If the marker is
    LIVE (a prior session entered /ca:dev and ended without /ca:arbiter), append a
    synthetic DEV: exit line to overrides.log BEFORE removing it
    (observability-001) — otherwise the audit trail keeps an orphaned DEV: enter
    with no matching close. Append-only (it never rewrites); best-effort — a write
    or remove failure must never brick session startup.

    `host_name` (observability-001/ADR-0012) is the resolved host's `.name`
    ("claude"/"codex"/"unknown"), so the synthetic close line is attributable to
    the host that wrote it now that three hosts share one overrides.log
    (ADR-0011). Optional and defaults to resolving it here via `get_host()`
    (#257) — main() already holds a Host instance and passes its `.name`
    through to avoid a second resolution, but any other caller (tests
    included) may omit it.

    `session_id` (#271 C-5) is THIS invocation's own session id from the
    SessionStart hook payload, when the host supplies one. See the module
    comment above `DEV_SESSION_LIVENESS_WINDOW` for the full session-scoping
    contract: a live marker is only force-closed when there is no reason to
    believe a DIFFERENT, still-running session currently owns it — and the
    ownership record's timestamp is refreshed ONLY by the owner itself (never
    by an unrelated session merely observing the marker), so the liveness
    window is anchored to the owner's last activity, not reset by every
    passerby SessionStart. `now` (epoch seconds) is injectable for
    deterministic tests; defaults to `time.time()`."""
    now = time.time() if now is None else now
    prev_sid, prev_ts = _read_dev_session_owner(root)

    marker = os.path.join(root, ".codearbiter", ".markers", "dev-active")
    marker_live = os.path.isfile(marker)

    if not marker_live:
        # No live marker: this record is purely "who could next enter /dev" —
        # any session refreshing it is harmless and correct. Nothing else to
        # do — there is no marker to clear and no close to log.
        if session_id:
            _write_dev_session_owner(root, session_id, now)
        return

    if session_id and prev_sid:
        if prev_sid == session_id:
            # The owner itself, resuming/compacting mid-dev — refresh ITS OWN
            # heartbeat (this is the only case where a write is safe while the
            # marker is live) and leave the marker untouched.
            _write_dev_session_owner(root, session_id, now)
            return
        if (now - prev_ts) < DEV_SESSION_LIVENESS_WINDOW:
            # A different session, and the OWNER's own clock hasn't elapsed
            # yet — do NOT touch the record (an unrelated observer must never
            # reset a clock it doesn't own) and do not clobber the marker.
            return
        # Different session AND the owner's own record is stale beyond the
        # window: proceed to the force-close below. Deliberately do not write
        # a fresh record here either — there is no live owner left to anchor
        # a new one to; the write happens naturally next time /dev is entered.

    if session_id and not prev_sid:
        # No prior record at all (first session ever, or a dropped record) —
        # no signal to protect a concurrent owner; seed the record for next
        # time and fall through to the pre-#271 unconditional-clear behavior.
        _write_dev_session_owner(root, session_id, now)

    # Force-close: either no session_id/no prior record (unconditional-clear
    # fallback), or a genuinely stale owner beyond the window.
    if host_name is None:
        try:
            # get_host() (#257), not a direct hostapi.load_host(): resolves
            # the SAME Host run(host) injected instead of a second load.
            host_name = get_host().name
        except Exception:  # noqa: BLE001 — must never brick session startup
            host_name = "unknown"
    try:
        arbiter_ref = get_host().cmd_ref("arbiter")
    except Exception:  # noqa: BLE001 — must never brick session startup
        arbiter_ref = "/ca:arbiter"
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (f"[{ts}] | BY: session-cleanup | HOST: {host_name} | DEV: exit | NOTE: cleared by "
            f"SessionStart (prior session ended mid-dev without {arbiter_ref})\n")
    try:
        with open(os.path.join(root, ".codearbiter", "overrides.log"),
                  "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    try:
        os.remove(marker)
    except OSError:
        pass


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
        if sys.stdin.isatty():
            return ""
        raw = sys.stdin.read()
        if not raw.strip():
            return ""
        data = json.loads(raw)
        return str(data.get("session_id") or "") if isinstance(data, dict) else ""
    except Exception:  # noqa: BLE001 — must never brick session startup
        return ""


def main():
    utf8_stdio()
    # get_host() (#257): resolves the SAME Host run(host) already primed via
    # set_host(), instead of a second hostapi.load_host() disk/probe.
    host = get_host()
    root = project_root()
    plugin = host.plugin_root()
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")
    session_id = _session_id_from_stdin()

    # /dev developer-override is per-session: clear its statusline marker on
    # startup — a new session restores orchestration. A live marker means a prior
    # session never ran /ca:arbiter, so close the DEV audit pair before clearing.
    # session_id (#271 C-5) lets this distinguish "the same session resuming"
    # and "a different, possibly still-live session" from a genuinely
    # abandoned marker — see clear_dev_marker's docstring.
    clear_dev_marker(root, host.name, session_id)

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
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _githooks import install as _install_git_hooks
        _install_git_hooks(root)
    except Exception:  # noqa: BLE001
        # Legacy hosts retain the historical best-effort startup contract.
        # Pi supplies an authenticated absolute executable pair; losing that
        # boundary must surface to the bridge so activation remains fail closed.
        if (os.environ.get("CODEARBITER_GIT_EXECUTABLE")
                or os.environ.get("CODEARBITER_PYTHON_EXECUTABLE")):
            raise

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
    # observability-004 (#268): name the RESOLVED host so a dormant/broken
    # host (FailClosedHost -> name "unknown", #255) is visible right in the
    # banner instead of being indistinguishable from a working install.
    print(f"host: {getattr(host, 'name', 'unknown')}")

    ctx_text = read_text(ctx) or ""
    if not INITIALIZED_RE.search(ctx_text):
        if has_source(root):
            print(f"NOT INITIALIZED: source exists but .codearbiter/CONTEXT.md is a stub. "
                  f"Run {host.cmd_ref('create-context')} before any other command.")
        else:
            print(f"NOT INITIALIZED: empty project. Run {host.cmd_ref('decompose')} to begin.")
        print(f"Type {host.cmd_ref('commands')} for the catalog.")
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
        # Shared helper: in-flight count (excludes done) + a stale-in-progress
        # nudge + undated/malformed warnings. Oversize boards degrade to a
        # one-line notice. Guarded: the task board must never take down the
        # linchpin hook — on any unexpected parse error, fail LOUD (stderr
        # breadcrumb) and fall back to the raw count, never go dormant.
        try:
            for _line in _taskboardlib.startup_summary(ot_text, datetime.date.today()):
                print(_line)
        except Exception as _e:  # noqa: BLE001 — never crash session startup
            n = sum(1 for ln in ot_text.splitlines()
                    if ln.startswith("- ") and not ln.startswith("- [x]"))
            print(f"in-flight tasks: {n}")
            print(f"codeArbiter: task-board summary degraded ({_e}); "
                  f"check .codearbiter/open-tasks.md", file=sys.stderr)

    # --- Passive provenance drift notice (T-16, spec pillar 4) ---
    # ONE line emitted only when drift > 0; silent when docs are fresh or on any
    # degrade (wrapper swallows all exceptions — never crashes the linchpin hook).
    _drift = provenance_drift_line(root)
    if _drift:
        print(_drift)

    # --- Update-available notice (AC-1/AC-2/AC-3) --------------------------
    # ONE line, read from the cache only (no network here); silent when the
    # installed version is current or the cache is absent/stale/corrupt.
    _update = update_notice_line(plugin)
    if _update:
        print(_update)

    print(f"Present this state, then await a {host.command_noun}. "
          f"Type {host.cmd_ref('commands')} for the catalog.")

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
    spawn_background_update_refresh(plugin)  # detached; never awaited (AC-3/AC-4)

    mode = briefing_mode(marker_present, any_actionable(summary))
    if mode == "full":
        print()
        print(f"=== codeArbiter daily briefing ({date_iso}) ===")
        print("First session of the day. Daily standup briefing (read-only).")
        # performance-003 (#194): ctx_text/ot_text/oq_text were already read
        # above for the startup-state block — thread them through so
        # governance_line's arbiter_state() call doesn't re-read the same three
        # files a second time in this same invocation.
        render_full_briefing(root, summary, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
        try:
            write_standup_marker(root, date_iso)
        except Exception:  # noqa: BLE001 — must never brick session startup
            pass
    elif mode == "offer":
        print(OFFER_LINE_TEMPLATE.format(standup=get_host().cmd_ref("standup")))

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
