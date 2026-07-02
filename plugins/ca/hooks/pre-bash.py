#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Bash|PowerShell) guard. Branch/push/staging +
# security gate. Python port of pre-bash.sh (issues #24, #25): no jq, fails
# loud, blocks via exit 2. Adds H-09b/H-10b — a BLOCKING crypto/secret commit
# gate (#24): the prior post-write reminder was advisory only, so a routine
# commit could ship crypto/secret changes without the gate ever running.
#
# All guards run only in arbiter-enabled repos (the plugin.json activation
# contract); elsewhere this exits 0 immediately.
#
# Ambiguity resolves CLOSED here. Some patterns below block a harmless
# spelling (e.g. `cp overrides.log backup` copies FROM the log) because the
# destructive spelling is indistinguishable without a full shell parse;
# /ca:override is the sanctioned escape hatch, and a false allow on the audit
# trail is unrecoverable after the fact.

import os
import re
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    AUDIT_LOG_NAMES, CRYPTO_RE, DECISIONS_DIR_RE, GATE_MARKER_NAMES, SECRET_RE,
    arbiter_active, block, content_digest, is_migration_path, line_digest,
    marker_fresh, project_root, read_input, tool_input, utf8_stdio,
)

# The most recent git-read failure, surfaced in the H-01/H-09b/H-14 fail-closed
# block message. "git unavailable or timed out" alone cost a session of root-
# causing (2026-07-01: the real error was a pathspec-parse artifact, visible in
# one look at git's stderr); a fail-closed message must carry its evidence.
# Defined ahead of current_branch/head_on_protected_tip (moved up from its
# original spot beside added_lines/_names) now that H-01's git reads use it too.
_READ_ERRS = []


def _note_read_err(argv, detail):
    _READ_ERRS.append(f"`{' '.join(argv)}` -> {(detail or '').strip()[:200]}")


def _read_err_hint():
    return f" Underlying git error: {_READ_ERRS[-1]}" if _READ_ERRS else ""

# `git` followed by any run of global options (-C <dir>, -c k=v, --git-dir=…,
# --no-pager, …) before the subcommand — `git -C ../x commit` must not slip
# past a bare `git\s+commit` match.
# appsec-002 (#175): a literal `--no-verify` / `-n` on `git commit`/`git push`
# skips `.git/hooks` entirely — the documented "spelling-proof backstop"
# (git-enforce.py) never runs for that operation, voiding H-01/H-02/H-09b/
# H-10b/H-14 for it. `-n` is git-commit's short spelling of --no-verify; `git
# push` has NO short spelling (its own `-n` is `--dry-run`, an unrelated flag),
# so only the long form is checked there. Token-equality (not substring) so a
# commit MESSAGE merely quoting the text ('-m "explain --no-verify"') is never
# misclassified — the quoted phrase tokenizes as one whole argument, never
# equal to the bare flag. The deeper shell-indirection spelling (`g=git; $g
# commit --no-verify`) defeats this lexical check same as it defeats COMMIT_RE
# itself; that residual is documented separately, out of scope for this guard.
COMMIT_NO_VERIFY_FLAGS = frozenset({"--no-verify", "-n"})
PUSH_NO_VERIFY_FLAGS = frozenset({"--no-verify"})


def _has_literal_flag(args, flags):
    """True iff `args` contains one of `flags` as its own token — quote-aware
    (a fully-quoted token, e.g. a `-m "..."` message, tokenizes as ONE token
    and is compared whole, so it can never equal a single bare flag)."""
    for raw in re.findall(r'"[^"]+"|\'[^\']+\'|\S+', args):
        if raw.strip("\"'") in flags:
            return True
    return False


GIT = r"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?|-\w+))*"
# The args capture stops at an unquoted `|`, `;`, or `&` (the next shell command
# is not this git command's business) but consumes quoted strings whole — a
# `;` inside `-m "scoped; and true"` is message content, not a separator.
# Truncating inside the quoted message left an unterminated `$(cat <<'EOF'`
# fragment whose words were then parsed as pathspecs, and a token like
# `/ca:checkpoint)` made `git diff HEAD -- …` fatal ("outside repository"),
# failing the H-09b scan CLOSED on a clean commit.
ARGS = r"(?P<args>(?:\"[^\"]*\"|'[^']*'|[^|;&])*)"
COMMIT_RE = re.compile(GIT + r"\s+commit\b" + ARGS)
PUSH_RE = re.compile(GIT + r"\s+push\b" + ARGS)
ADD_RE = re.compile(GIT + r"\s+add\b" + ARGS)
GIT_C_DIR_RE = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
# Force-push in any spelling: --force, --force-with-lease[=…], -f as its own
# token (not a ref like `fix-f`), or a forcing `+refspec`.
FORCE_RE = re.compile(r"(?:^|\s)(?:--force(?:-with-lease|-if-includes)?(?:=\S+)?|-f)(?=\s|$)")
FORCE_REFSPEC_RE = re.compile(r"\s\+[\w./:~^-]+")
# Bulk-push flags that publish protected refs with no refspec token to inspect:
# `--all` pushes every local branch (main included); `--mirror` pushes every ref
# and can force-update/delete them. Neither names a destination the
# PROTECTED_DEST scan can see, so they slip the refspec check — block on sight.
PUSH_ALL_RE = re.compile(r"(?:^|\s)(?:--all|--mirror)(?=\s|$)")
# Flag spellings that stage a non-explicit file set. `-u/--update` joins
# -A/--all/. : it stages every tracked modification — wildcard in behavior
# even though no glob appears in the command.
WILDCARD_ADD_RE = re.compile(r"(?:^|\s)(?:-A|--all|-u|--update|\.)(?=\s|$)")
COMMIT_ALL_RE = re.compile(r"(?:^|\s)(?:-[a-zA-Z]*a[a-zA-Z]*|--all)(?=\s|$)")
GLOB_RE = re.compile(r"[*?\[]")
# A push destination that resolves to a protected branch, in any spelling:
# `main`, `HEAD:main`, `feature:main`, `:main` (deletion), `refs/heads/main`.
# Matched with fullmatch against each non-flag token, so `feature-main` and
# `main-fix` never trip it.
PROTECTED_DEST_RE = re.compile(r"(?:\S+:|:)?(?:refs/heads/)?(?:main|master)")
# Truncation (`>` but not `>>`) or destructive verbs aimed at an audit log
# (overrides.log, triage.log — both append-only). The verb list includes
# every common rewrite-in-place spelling (truncate, tee, dd, sed, sponge,
# cp/copy onto the log); PowerShell's Add-Content is deliberately absent —
# appending is the one sanctioned write.
# N-3: Known limitations — this regex catches the common `> file` and `>| file`
# (force-clobber) truncation forms but NOT every shell spelling that produces a
# new file descriptor on the log. Specific gaps: triple-chevron (`>>>`, treated
# as append by some shells), file-descriptor forms like
# `exec 3>.codearbiter/overrides.log`, and verb-with-VARIABLE-target spellings
# where the literal log name never appears adjacent to the verb (appsec-003):
# e.g. `f=.codearbiter/overrides.log; rm "$f"` or PowerShell `$f='overrides.log';
# rm $f` — the guard is purely lexical and anchored on the literal name, so an
# indirected target defeats it. These are difficult to close with a single regex
# and represent an accepted residual risk. The sanctioned bypass for legitimate
# log management is /ca:override.
# The optional `\|?` admits `>|` (clobber even under `set -o noclobber`); the
# leading `(?!>)` still excludes the append form `>>`.
# `sprint-log.md` joins overrides.log/triage.log as an append-only audit artifact
# (the /sprint decision record). The bare-name alternation is centralized in
# _hooklib.AUDIT_LOG_NAMES so the Write/Edit and shell flanks never drift.
LOG_NAMES = AUDIT_LOG_NAMES
LOG_TRUNC_RE = re.compile(r"(?<!>)>(?!>)\|?\s*\S*" + LOG_NAMES)
LOG_DESTROY_RE = re.compile(
    r"\b(rm|del|mv|cp|copy|dd|tee|sed|truncate|sponge"
    r"|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content|Out-File)\b"
    r"[^|;&]*" + LOG_NAMES, re.I,
)
# H-11's shell flank: ADRs are authored only via /adr (pre-write/pre-edit
# guard the Write/Edit tools; this guards redirection and file verbs). Any
# redirect into .codearbiter/decisions/, or any write/delete verb naming it,
# blocks — `cat`/`ls`/`grep` reads pass untouched.
DECISIONS = DECISIONS_DIR_RE + r"\b"
# `>>?\|?` covers `>`, `>>`, and the `>|` force-clobber form into decisions/.
DECISIONS_REDIRECT_RE = re.compile(r">>?\|?\s*\S*" + DECISIONS, re.I)
DECISIONS_WRITE_RE = re.compile(
    r"\b(rm|del|mv|cp|copy|dd|tee|sed|touch|truncate|ni"
    r"|New-Item|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content"
    r"|Out-File|Add-Content)\b[^|;&]*" + DECISIONS, re.I,
)

# H-18's shell flank: .codearbiter/CONTEXT.md is the activation switch every hook
# gates on (#159). The Write/Edit tools are guarded by pre-write/pre-edit; this
# guards the shell — a redirect into CONTEXT.md, or a write/delete verb naming
# it, would flip `arbiter: enabled` off (or corrupt the frontmatter) and make
# every gate dormant. Init writes CONTEXT.md via the Write tool, never the shell,
# so no legitimate path is blocked; `cat`/`grep` reads pass untouched. Same
# lexical limitation as the audit-log/decisions flanks (N-3): the Write/Edit
# guard is the primary boundary, this is defense in depth.
CONTEXT_MD = r"\.codearbiter[\\/]+CONTEXT\.md"
CONTEXT_REDIRECT_RE = re.compile(r">>?\|?\s*\S*" + CONTEXT_MD, re.I)
CONTEXT_WRITE_RE = re.compile(
    r"\b(rm|del|mv|cp|copy|dd|tee|sed|truncate|ni"
    r"|New-Item|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content"
    r"|Out-File|Add-Content)\b[^|;&]*" + CONTEXT_MD, re.I,
)

# H-19's shell flank: the two gate-pass markers (#160) are recorded ONLY by the
# python producers (security-pass.py / migration-pass.py), which write via
# os.replace and NEVER name the marker on the command line. So blocking any shell
# command that names a gate marker as a redirect or write/move/copy target closes
# the `echo <digest> > .markers/security-gate-passed` (and `cp goodmarker
# security-gate-passed`) forge without touching the sanctioned producers.
# adr-authoring-active is intentionally excluded: /adr legitimately `touch`es it,
# and an empty/forged gate marker fails H-09b/H-14's digest-coverage check anyway
# — only a marker carrying valid digests forges a pass, which shell verbs against
# the marker name are how you'd inject.
GATE_MARKER = r"\.markers[\\/]+" + GATE_MARKER_NAMES
GATE_MARKER_REDIRECT_RE = re.compile(r">>?\|?\s*\S*" + GATE_MARKER, re.I)
GATE_MARKER_WRITE_RE = re.compile(
    r"\b(mv|cp|copy|dd|tee|sed|truncate"
    r"|Move-Item|Copy-Item|Clear-Content|Set-Content|Out-File|Add-Content)\b"
    r"[^|;&]*" + GATE_MARKER, re.I,
)


def git_cwd(cmd, root):
    """The directory a `git -C <dir>` invocation actually targets."""
    m = GIT_C_DIR_RE.search(cmd)
    if not m:
        return root
    return m.group(1).strip("\"'")


def current_branch(cwd):
    """The current branch name, "" for a legitimate detached HEAD, or None when
    git could not answer (nonzero exit / spawn failure / timeout). reliability-001
    (#189): the None sentinel lets H-01 fail CLOSED on a git-read error instead of
    silently treating "unknown" the same as "detached, not on a protected tip" —
    the prior `except: return ""` collapsed those two states and let a commit
    through when branch state genuinely could not be determined."""
    argv = ["git", "branch", "--show-current"]
    try:
        out = subprocess.run(
            argv, cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        if out.returncode != 0:
            _note_read_err(argv, out.stderr or f"exit {out.returncode}")
            return None
        return out.stdout.strip()
    except Exception as e:  # noqa: BLE001
        _note_read_err(argv, repr(e))
        return None


def is_protected_branch(branch):
    """Case-insensitive: `Main`/`MASTER` are the default branch on a case-folding
    ref store and must be treated as protected, just like `main`/`master`."""
    return branch.lower() in ("main", "master")


def head_on_protected_tip(cwd):
    """True when HEAD (typically detached) points at the commit a protected
    branch tips — a commit there still writes onto main/master's history even
    though `git branch --show-current` reports no branch name.

    One spawn (performance-006): `git show-ref --head refs/heads/main
    refs/heads/master` lists `<sha> HEAD` plus a `<sha> refs/heads/<branch>` line
    for each protected branch that EXISTS — a missing branch is simply omitted
    (exit 0), with no fatal. (`git rev-parse HEAD main master` cannot be used: it
    stops at the first unresolvable arg, so a missing `main` would hide a present
    `master` tip and silently allow a commit onto it.) HEAD sits on a protected
    tip iff its sha matches a listed main/master tip. A non-repo / unborn HEAD
    lists no HEAD sha -> False.

    reliability-001 (#189): returns None (not False) when git could not answer
    (spawn failure/timeout, or an exit code outside the two legitimate outcomes)
    so H-01 fails CLOSED on a git-read error instead of concluding "not on a
    protected tip" from a failed read."""
    argv = ["git", "show-ref", "--head", "refs/heads/main", "refs/heads/master"]
    try:
        out = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
        )
    except Exception as e:  # noqa: BLE001
        _note_read_err(argv, repr(e))
        return None
    if out.returncode not in (0, 1):
        _note_read_err(argv, out.stderr or f"exit {out.returncode}")
        return None
    head_sha, protected = None, set()
    for ln in out.stdout.splitlines():
        parts = ln.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == "HEAD":
            head_sha = sha
        elif ref in ("refs/heads/main", "refs/heads/master"):
            protected.add(sha)
    return head_sha is not None and head_sha in protected


def added_lines(cwd, ref, paths=None):
    """The added (`+`) lines of a diff — what a commit would introduce — or None
    when git could not produce the diff (nonzero exit / timeout / error). The
    None return (not "") lets the H-09b/H-10b security scan fail CLOSED on a read
    error rather than silently passing — an empty diff and an unreadable diff are
    NOT the same thing. `paths`, when given, scopes the diff to the pathspec(s) a
    `git commit <path>` names (whose worktree content the --cached scan misses).
    Decoded as UTF-8 with replacement: `text=True` alone uses the locale code
    page (cp1252 on stock Windows), where a non-cp1252 byte in the diff raised
    UnicodeDecodeError into the bare except below and the security gate
    silently failed OPEN on exactly the platform this layer protects."""
    argv = ["git", "diff", ref] + (["--", *paths] if paths else [])
    try:
        out = subprocess.run(
            argv, cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if out.returncode != 0:
            _note_read_err(argv, out.stderr or f"exit {out.returncode}")
            return None
    except Exception as e:  # noqa: BLE001
        _note_read_err(argv, repr(e))
        return None
    return "\n".join(
        line[1:] for line in out.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _names(cwd, args):
    """A set of repo-relative paths from a `git ... --name-only` style query, or
    None when git could not answer (nonzero / timeout / error). None (not an
    empty set) lets the H-14 migration scan fail CLOSED on a read error rather
    than concluding "no migrations staged" from a failed read."""
    try:
        out = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        if out.returncode != 0:
            _note_read_err(["git"] + args, out.stderr or f"exit {out.returncode}")
            return None
    except Exception as e:  # noqa: BLE001
        _note_read_err(["git"] + args, repr(e))
        return None
    return {p for p in out.stdout.splitlines() if p.strip()}


def staged_paths(cwd):
    """Paths in the index — what a plain `git commit` would record. None on a
    git-read failure (caller fails closed)."""
    return _names(cwd, ["diff", "--cached", "--name-only"])


def worktree_paths(cwd):
    """Tracked worktree modifications (what `git commit -a` sweeps in) plus
    untracked files. None if either underlying query failed (caller fails
    closed)."""
    tracked = _names(cwd, ["diff", "--name-only"])
    untracked = _names(cwd, ["ls-files", "--others", "--exclude-standard"])
    if tracked is None or untracked is None:
        return None
    return tracked | untracked


def read_worktree(cwd, rel):
    """Worktree content of `rel`, or None if absent/oversize. The H-14 producer
    digests worktree content too, so the backstop's view matches the marker."""
    p = rel if os.path.isabs(rel) else os.path.join(cwd, rel)
    try:
        if os.path.getsize(p) > 1_000_000:
            return None
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def add_violation(args, cwd):
    """The reason a `git add` argument set is not explicit-file staging, or
    None. Each path token is checked best-effort against the repo the command
    targets: a glob, a pathspec-magic prefix, or a directory blocks (staging
    must name files); a token that resolves to nothing is allowed — git will
    reject it anyway."""
    for raw in re.findall(r'"[^"]+"|\'[^\']+\'|\S+', args):
        tok = raw.strip("\"'")
        if not tok or tok == "--" or tok.startswith("-"):
            continue  # flag spellings are WILDCARD_ADD_RE's job
        if tok.startswith(":"):
            return f"pathspec magic ('{tok}')"
        if GLOB_RE.search(tok):
            return f"a glob pattern ('{tok}')"
        p = tok if os.path.isabs(tok) else os.path.join(cwd, tok)
        if os.path.isdir(p):
            return f"a directory ('{tok}')"
    return None


# Flags whose NEXT token is a value, not a pathspec — so `git commit -m "msg" f`
# names `f`, not `msg`. (`--flag=value` is self-contained; a short bundle ending
# in one of these chars takes the next token, e.g. `-am msg`.)
COMMIT_VALUE_FLAGS = frozenset({
    "-m", "--message", "-F", "--file", "-C", "--reuse-message",
    "-c", "--reedit-message", "--author", "--date", "-t", "--template",
    "--fixup", "--squash", "--trailer",
})


# A redirect operator token (`>`, `>>`, `2>`, `<`, `<<`, `<<'EOF'`, …). Never a
# git pathspec — feeding one to `git diff -- <op>` can ERROR (not "diff to
# nothing"), which is what failed the H-09b/H-14 scan CLOSED on heredoc commits.
REDIRECT_RE = re.compile(r"\d*[<>]")


# A heredoc: `<<` (optional `-`), optional quote, a word delimiter, optional
# matching quote, the rest of that line, then body lines, up to a line that is
# the delimiter alone. The body is stdin content (the commit message via `-F -`),
# never git arguments — parsing it as pathspecs failed H-09b/H-10b/H-14 CLOSED on
# the recommended `git commit -F - <<EOF` form.
# Group 3 captures the REST OF THE OPERATOR LINE after `<<WORD` — `git commit -F
# - <<EOF realfile.py` passes `realfile.py` to git as a pathspec (only the body
# is stdin), so that tail is re-emitted, not swallowed with the body, or the
# worktree-union scan would under-scan it (errs open).
HEREDOC_RE = re.compile(
    r"<<-?[ \t]*([\"']?)(\w+)\1([^\n]*)\n(?:.*?\n)?[ \t]*\2[ \t]*(?:\n|$)",
    re.DOTALL)


def _strip_heredoc_bodies(args):
    """Remove heredoc operator+body+delimiter from a git-commit arg string so the
    body is never parsed as flags/pathspecs (it false-blocked H-09b/H-10b/H-14 on
    `git commit -F - <<EOF`). `\\`-newline continuations are joined first; the
    operator-line tail (group 3) is preserved.

    CRITICALLY nothing but the heredoc body is cut. An earlier attempt bounded to
    the first newline (`split("\\n", 1)[0]`), which also truncated at a literal
    newline inside a quoted `-m "subject\\n\\nbody"` message and dropped a trailing
    pathspec — silently under-scanning a pathspec-scoped commit and reopening the
    v2.rev.0015 worktree-union bypass. Stripping only the heredoc (and keeping the
    operator-line tail) leaves a multi-line message and any real pathspec intact."""
    joined = re.sub(r"\\\r?\n", " ", args)   # honor line-continuations
    return HEREDOC_RE.sub(r"\3 ", joined)


def commit_pathspecs(args):
    """The worktree paths a `git commit` names as pathspecs. A `git commit <path>`
    records the WORKTREE content of <path>, bypassing the index — content the
    index-only `--cached` scan never sees — so the security/migration gates must
    union the worktree diff for these paths. Best-effort parse: everything after
    a `--` separator is a pathspec; otherwise bare tokens that are neither a flag,
    a value-taking flag's value, nor a redirect operator. Bias is to OVER-include
    — a non-path token diffs to nothing (harmless), whereas under-including would
    reopen the bypass, so any ambiguity is treated as a pathspec. Callers pass a
    `_strip_heredoc_bodies`-cleaned string so a heredoc body never reaches here."""
    toks = [t.strip("\"'") for t in re.findall(r'"[^"]+"|\'[^\']+\'|\S+', args)]
    if "--" in toks:
        return [t for t in toks[toks.index("--") + 1:] if t]
    out, expect_value = [], False
    for t in toks:
        if expect_value:
            expect_value = False
            continue
        if REDIRECT_RE.match(t):  # a redirect operator, not a pathspec
            continue
        if t.startswith("-"):
            if "=" in t:  # --message=... carries its own value
                continue
            if t in COMMIT_VALUE_FLAGS or (
                    re.fullmatch(r"-[A-Za-z]+", t) and t[-1] in "mFCct"):
                expect_value = True  # next token is this flag's value, not a path
            continue
        if t:
            out.append(t)
    return out


def _require_branch(cwd):
    """current_branch(cwd), or fail-closed BLOCK on H-01 when git could not
    answer. reliability-001 (#189): ambiguity resolves CLOSED here exactly as
    H-09b/H-14 already do on a git-read failure — an unreadable branch state
    must not silently evaluate as "not protected"."""
    branch = current_branch(cwd)
    if branch is None:
        block("H-01", "branch state could not be determined (git unavailable or timed "
                      "out) — failing closed (ORCHESTRATOR §2). Retry, or verify you are "
                      "not on main/master before committing/pushing." + _read_err_hint())
    return branch


def _require_tip(cwd):
    """head_on_protected_tip(cwd), or fail-closed BLOCK on H-01 when git could
    not answer (reliability-001, #189)."""
    tip = head_on_protected_tip(cwd)
    if tip is None:
        block("H-01", "HEAD's protected-branch-tip state could not be determined (git "
                      "unavailable or timed out) — failing closed (ORCHESTRATOR §2). "
                      "Retry, or verify HEAD before committing." + _read_err_hint())
    return tip


def _run(root):
    cmd = tool_input(read_input()).get("command", "") or ""

    # Heredoc bodies are stdin text, not arguments — match the git command over
    # a body-stripped view so message content (which may contain `;`/`|`/`&`,
    # or mention `git -C`) never truncates the args capture, poisons the cwd
    # extraction, or leaks words into the pathspec parse. The RAW command stays
    # as a fallback matcher: a heredoc fed TO a shell (`bash <<EOF … EOF`)
    # executes its body, so a commit/push/add visible only in the raw text must
    # still be guarded — ambiguity resolves CLOSED, so the fallback over-blocks
    # (e.g. a message QUOTING a force-push) rather than under-scans.
    git_view = _strip_heredoc_bodies(cmd) if "<<" in cmd else cmd

    commit = COMMIT_RE.search(git_view) or COMMIT_RE.search(cmd)
    cwd = git_cwd(git_view, root)

    # H-20: block a literal --no-verify / -n on `git commit` — it skips
    # .git/hooks (the git-enforce backstop) entirely, voiding every enforcement
    # hook for that commit (appsec-002, #175).
    if commit and _has_literal_flag(commit.group("args"), COMMIT_NO_VERIFY_FLAGS):
        block("H-20", "'--no-verify' / '-n' on git commit skips the .git/hooks "
                      "git-enforce backstop entirely (appsec-002) — every commit-time "
                      "gate (H-01/H-02/H-09b/H-10b/H-14) would go unenforced for this "
                      "commit. Remove the flag; use /override for a sanctioned bypass.")

    # H-01: no commit directly to main/master — case-insensitive, and a detached
    # HEAD sitting on a protected branch's tip counts (the commit lands on its
    # history regardless of the absent branch name).
    if commit:
        branch = _require_branch(cwd)
        if is_protected_branch(branch) or (not branch and _require_tip(cwd)):
            target = branch or "main/master (detached HEAD)"
            block("H-01", f"Direct commit to {target} is prohibited (ORCHESTRATOR §3). "
                          f"Create a feature branch.")

    push = PUSH_RE.search(git_view) or PUSH_RE.search(cmd)
    if push:
        pargs = push.group("args")

        # H-20: block a literal --no-verify on `git push` (same rationale as
        # the commit flank above). `git push` has no short `-n` spelling for
        # this — its own `-n` is `--dry-run`, an unrelated flag — so only the
        # long form is checked here.
        if _has_literal_flag(pargs, PUSH_NO_VERIFY_FLAGS):
            block("H-20", "'--no-verify' on git push skips the .git/hooks git-enforce "
                          "backstop entirely (appsec-002) — every push-time gate would "
                          "go unenforced for this push. Remove the flag; use /override "
                          "for a sanctioned bypass.")

        # H-02: no force-push — any spelling, including --force-with-lease and +refspec
        if FORCE_RE.search(pargs) or FORCE_REFSPEC_RE.search(pargs):
            block("H-02", "Force-push is prohibited (ORCHESTRATOR §3).")

        # H-01: `--all` / `--mirror` publish protected refs (main included) with
        # no inspectable destination token — block regardless of current branch.
        if PUSH_ALL_RE.search(pargs):
            block("H-01", "'git push --all' / '--mirror' publish every local ref "
                          "(including main) (ORCHESTRATOR §3) — main moves only via a "
                          "merged PR. Push an explicit feature refspec.")

        # H-01: no push whose destination is a protected branch. H-01's branch
        # check alone left `git push origin HEAD:main` (and `feature:main`,
        # `:main`) as a refspec-shaped hole — a direct write to main from any
        # branch with no commit involved.
        toks = [t.strip("\"'").lstrip("+") for t in pargs.split()
                if t and not t.startswith("-")]
        for tok in toks:
            if PROTECTED_DEST_RE.fullmatch(tok):
                block("H-01", f"Pushing to a protected branch ('{tok}') is prohibited "
                              f"(ORCHESTRATOR §3) — main moves only via a merged PR.")
        # Bare `git push` (no refspec) publishes the current branch. A git-read
        # failure here fails CLOSED (reliability-001, #189) — a bare push whose
        # branch state is unknown must not be waved through as "not protected".
        if len(toks) < 2 and is_protected_branch(_require_branch(cwd)):
            block("H-01", "Bare `git push` from main/master publishes the protected "
                          "branch (ORCHESTRATOR §3) — main moves only via a merged PR.")

    # H-03: no wildcard git staging — stage explicitly (commit-gate). Both the
    # flag spellings (-A/--all/-u/.) and the argument spellings (globs,
    # directories, pathspec magic) — `git add src/` stages everything beneath
    # src/ just as surely as `git add -A` does.
    add = ADD_RE.search(git_view) or ADD_RE.search(cmd)
    if add:
        if WILDCARD_ADD_RE.search(add.group("args")):
            block("H-03", "'git add -A' / 'git add .' / 'git add --all' / 'git add -u' "
                          "are prohibited. Stage files explicitly (commit-gate skill).")
        why = add_violation(add.group("args"), cwd)
        if why:
            block("H-03", f"Wildcard staging is prohibited — {why} stages a "
                          f"non-explicit file set. Stage files explicitly, one path "
                          f"per file (commit-gate skill).")

    # H-05: the audit trail is append-only — block truncation/removal of the
    # audit logs via shell verbs (Write/Edit are guarded separately).
    if ("overrides.log" in cmd or "triage.log" in cmd or "sprint-log.md" in cmd) and (
            LOG_TRUNC_RE.search(cmd) or LOG_DESTROY_RE.search(cmd)):
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, sprint-log.md) "
                      "are append-only (ORCHESTRATOR §7). Truncating, overwriting, or deleting "
                      "the audit trail is prohibited; append with '>>' only.")

    # H-11: ADRs exist only via /adr — the Write/Edit tools are guarded by
    # pre-write/pre-edit, and this closes the shell flank (`echo > decisions/…`,
    # `touch`, `cp`, `rm`, `sed -i`, …). Reads are untouched.
    if DECISIONS_REDIRECT_RE.search(cmd) or DECISIONS_WRITE_RE.search(cmd):
        block("H-11", "ADR files under .codearbiter/decisions/ are authored only via "
                      "/adr and are immutable history (ORCHESTRATOR §6) — shell writes, "
                      "edits, and deletions there are prohibited.")

    # H-18: CONTEXT.md is the activation switch (#159) — shell flank. A shell
    # rewrite/delete of it would make every gate dormant; init writes it via the
    # Write tool, so nothing legitimate is blocked. Reads pass.
    if CONTEXT_REDIRECT_RE.search(cmd) or CONTEXT_WRITE_RE.search(cmd):
        block("H-18", ".codearbiter/CONTEXT.md is the activation switch every enforcement "
                      "hook reads (#159) — shell rewrites, edits, or deletions that could flip "
                      "`arbiter: enabled` off or corrupt its frontmatter are prohibited. Edit it "
                      "through the sanctioned init path.")

    # H-19: the gate-pass markers (#160) are recorded only by the sanctioned
    # python producers — shell flank against `echo <digest> > security-gate-passed`
    # and `cp`/`sed`/`tee` forges naming a gate marker.
    if GATE_MARKER_REDIRECT_RE.search(cmd) or GATE_MARKER_WRITE_RE.search(cmd):
        block("H-19", "The .codearbiter/.markers/ security-gate-passed / migration-gate-passed "
                      "tokens are recorded only by the sanctioned gate producers (#160) — a shell "
                      "redirect or write verb naming a gate marker forges a security/migration "
                      "gate pass and is prohibited.")

    # H-09b / H-10b: BLOCK a commit that introduces crypto/secret changes without
    # a recorded security-gate pass. The crypto-compliance / secret-handling skills
    # record the pass via hooks/security-pass.py — a marker holding the digest of
    # every sensitive line the gate approved. Two checks, both required:
    # freshness (< 30 min) AND coverage (every sensitive line being committed is
    # in the approved set). Coverage is what closes the TOCTOU window: a pass
    # minted for one diff can no longer launder a different diff committed inside
    # the freshness window. Scans the staged diff, plus the worktree diff when
    # the commit uses -a/--all or the same command stages files.
    if commit:
        cargs = _strip_heredoc_bodies(commit.group("args"))
        # Scan the staged diff, plus the worktree diff when the commit pulls in
        # worktree content: -a/--all (whole tree), an in-command `git add`, OR a
        # `git commit <pathspec>` (the named paths only — a pathspec commit
        # records worktree content the --cached scan never sees). A None from
        # added_lines means git could not read the diff -> fail CLOSED.
        parts = [added_lines(cwd, "--cached")]
        if COMMIT_ALL_RE.search(cargs) or add:
            parts.append(added_lines(cwd, "HEAD"))
        else:
            pathspecs = commit_pathspecs(cargs)
            if pathspecs:
                parts.append(added_lines(cwd, "HEAD", pathspecs))
        if any(p is None for p in parts):
            block("H-09b", "the diff for the crypto/secret security scan could not be "
                           "read (git unavailable or timed out) — failing closed "
                           "(ORCHESTRATOR §2). Retry, or run the crypto-compliance / "
                           "secret-handling gate, then commit." + _read_err_hint())
        added = "\n".join(parts)
        sensitive = [ln for ln in added.splitlines()
                     if CRYPTO_RE.search(ln) or SECRET_RE.search(ln)]
        if sensitive:
            touches_crypto = bool(CRYPTO_RE.search(added))
            kind = "crypto/TLS" if touches_crypto else "secret"
            tag = "H-09b" if touches_crypto else "H-10b"
            skill = "crypto-compliance" if touches_crypto else "secret-handling"
            marker = os.path.join(root, ".codearbiter", ".markers", "security-gate-passed")
            if not marker_fresh(marker, 30):
                block(tag, f"This commit introduces {kind} changes, but no security-gate pass is "
                           f"recorded (.codearbiter/.markers/security-gate-passed). Run the "
                           f"{skill} gate (it records the pass), then commit. To bypass a "
                           f"security gate, /override requires its heavier "
                           f"security-acknowledgement path.")
            try:
                with open(marker, encoding="utf-8") as f:
                    approved = set(f.read().split())
            except Exception:  # noqa: BLE001
                approved = set()
            uncovered = [ln for ln in sensitive if line_digest(ln) not in approved]
            if uncovered:
                block(tag, f"{len(uncovered)} {kind} line(s) in this commit are not covered "
                           f"by the recorded security-gate pass — the pass is bound to the "
                           f"exact lines it reviewed, and these changed (or appeared) after "
                           f"it ran. Re-run the {skill} gate so it reviews the current diff "
                           f"and re-records the binding, then commit.")

    # H-14: BLOCK a commit that stages a database migration without a recorded
    # migration-review pass. commit-gate (and /review, /pr, /checkpoint, sprint)
    # dispatch migration-reviewer and run hooks/migration-pass.py on PASS — a
    # marker holding the content digest of every migration file the reviewer
    # approved. Coverage is by content digest, no freshness window: an immutable
    # migration stays approved while unchanged, and any edit changes the digest
    # -> uncovered -> BLOCK (closes the TOCTOU window and enforces migration
    # immutability at commit time). This closes the narrow #77 gap — a migration
    # committed via bare /commit or the /feature small lane, where no lane
    # dispatched the reviewer and no hook fired. A missing/unreadable marker is
    # treated as no coverage (fail-closed), consistent with this layer's
    # "ambiguity resolves CLOSED" stance.
    if commit:
        cargs = _strip_heredoc_bodies(commit.group("args"))
        # Index paths, plus worktree paths when the commit pulls them in: -a/add
        # (whole tree) or a `git commit <pathspec>` (named paths only). A None
        # from any path query means git could not read the file list -> fail
        # CLOSED, consistent with this layer's "ambiguity resolves CLOSED" stance.
        staged = staged_paths(cwd)
        failed = staged is None
        extra = set()
        if COMMIT_ALL_RE.search(cargs) or add:
            wt = worktree_paths(cwd)
            failed = failed or wt is None
            extra = wt or set()
        else:
            pathspecs = commit_pathspecs(cargs)
            if pathspecs:
                ps = _names(cwd, ["diff", "HEAD", "--name-only", "--", *pathspecs])
                failed = failed or ps is None
                extra = ps or set()
        if failed:
            block("H-14", "the file list for the migration scan could not be read "
                          "(git unavailable or timed out) — failing closed "
                          "(ORCHESTRATOR §2). Retry, or run the migration-review gate, "
                          "then commit." + _read_err_hint())
        staged |= extra
        migs = sorted(p for p in staged if is_migration_path(p, root))
        if migs:
            marker = os.path.join(root, ".codearbiter", ".markers", "migration-gate-passed")
            try:
                with open(marker, encoding="utf-8") as f:
                    approved = set(f.read().split())
            except Exception:  # noqa: BLE001 — missing/unreadable marker -> no coverage
                approved = set()
            uncovered = []
            for rel in migs:
                text = read_worktree(cwd, rel)
                if text is None or content_digest(text) not in approved:
                    uncovered.append(rel)
            if uncovered:
                block("H-14", f"{len(uncovered)} staged migration file(s) lack a recorded "
                              f"migration-review pass: {', '.join(uncovered)}. commit-gate "
                              f"dispatches migration-reviewer and records the pass via "
                              f"hooks/migration-pass.py; run that review, then commit. To "
                              f"bypass a migration gate, /override logs the exception.")

    sys.exit(0)


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    # reliability-002 (#189): everything past this point runs only in an
    # arbiter-enabled repo, so a dormant/non-codeArbiter repo can never be
    # bricked by a crash here. An uncaught exception in the scan path below
    # (H-01/H-03/H-05/H-09b/H-10b/H-11/H-14/H-18/H-19/H-20) must fail CLOSED (exit 2,
    # a BLOCK) rather than exit 1 — a non-2 exit is a NON-blocking error under
    # the Claude Code hook contract (_hooklib.py:11-15), which would silently
    # ALLOW the very tool call this guard exists to scan. read_input()'s
    # documented fail-OPEN behavior on malformed stdin is unaffected: it catches
    # its own parse errors internally and returns {} before this wrapper is
    # ever reached.
    try:
        _run(root)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — the fail-closed backstop of last resort
        traceback.print_exc(file=sys.stderr)
        block("H-00", "pre-bash guard crashed while scanning this command — failing "
                      "closed (ORCHESTRATOR §2) rather than silently allowing an "
                      "unscanned command. See the traceback above; retry, or report it.")


if __name__ == "__main__":
    main()
