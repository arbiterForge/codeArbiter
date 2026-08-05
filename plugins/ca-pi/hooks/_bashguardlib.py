#!/usr/bin/env python3
# codeArbiter — PreToolUse(Bash|PowerShell) guard logic (issue #320). Extracted
# verbatim from pre-bash.py: command parsing/tokenization, heredoc/executor
# detection, git -C composition, and the H-01/H-02/H-03/H-05/H-09b/H-10b/H-11/
# H-14/H-18/H-19/H-20 check functions, composed by run_guards() into the same
# scan pre-bash.py used to run inline. pre-bash.py is now a thin entry point:
# read stdin, call run_guards(), exit.
#
# Branch/push/staging + security gate. Python port of pre-bash.sh (issues #24,
# #25): no jq, fails loud, blocks via exit 2. Includes H-09b/H-10b — a BLOCKING
# crypto/secret commit gate (#24). All guards run only in arbiter-enabled repos
# (the plugin.json activation contract) — pre-bash.py's main() checks that
# before ever calling run_guards().
#
# Ambiguity resolves CLOSED here. Some patterns below block a harmless
# spelling (e.g. `cp overrides.log backup` copies FROM the log) because the
# destructive spelling is indistinguishable without a full shell parse;
# /ca:override is the sanctioned escape hatch, and a false allow on the audit
# trail is unrecoverable after the fact.
#
# Zero import-time side effects; the only filesystem/git access is inside the
# named readers below (current_branch, head_on_protected_tip, added_lines,
# _names, read_worktree) — each fails CLOSED (returns None) on a git-read
# error rather than raising, per this repo's "never raise on malformed input"
# invariant; the caller (run_guards / _require_branch / _require_tip) decides
# how to fail closed.
#
# Public API:
#   run_guards(payload, root) -> None    parse the Bash/PowerShell tool_input
#                                         from `payload`, run every H-NN gate
#                                         against it, block() (exit 2) on a
#                                         violation, else sys.exit(0)
#   git_cwd(cmd, root) -> str            the `-C <dir>` target a git invocation
#                                         actually runs against, else `root`
#   current_branch(cwd) -> str|None      current branch, "" if detached, None
#                                         on a git-read failure
#   is_protected_branch(branch) -> bool  True iff branch is main/master
#                                         (case-insensitive)
#   head_on_protected_tip(cwd) -> bool|None  True iff detached HEAD sits on a
#                                         protected branch's tip
#   added_lines(cwd, ref, paths=None) -> str|None  added ('+') diff lines,
#                                         narrowed to the H-09b/H-10b candidate
#                                         set, or None on a git-read failure
#   staged_paths(cwd) -> set|None        index paths (`git diff --cached
#                                         --name-only`), or None on failure
#   worktree_paths(cwd) -> set|None      tracked-modified + untracked paths,
#                                         or None on failure
#   read_worktree(cwd, rel) -> str|None  worktree content of `rel`, or None if
#                                         absent/oversize
#   add_violation(args, cwd) -> str|None  the reason a `git add` argument set
#                                         is not explicit-file staging, or None
#   commit_pathspecs(args) -> list[str]  worktree paths a `git commit` names
#                                         as pathspecs
#   _strip_heredoc_bodies(args) -> str   remove heredoc operator+body+delimiter
#                                         from a git-commit arg string (kept
#                                         underscore-named + re-exported from
#                                         pre-bash.py — .github/scripts/
#                                         test_hook_guards.py imports it by
#                                         this exact name)
#   _state_write_res(basename) -> (redirect_re, write_re, git_restore_re,
#                                         interp_re)   H-22's per-entry
#                                         shell-flank regex TEMPLATE for one
#                                         protected-state registry entry's
#                                         bare filename (T-08, #564; the
#                                         git-restore and interpreter legs
#                                         added per findings F5/F6)
#   _build_state_write_res(registry) -> tuple[(rel_path, policy, redirect_re,
#                                         write_re, git_restore_re,
#                                         interp_re), ...]   the compiled set
#                                         for every entry in `registry`;
#                                         `_STATE_WRITE_RES` is this, built
#                                         once at import from the live
#                                         `_protectedstatelib.REGISTRY`
#   _check_h22_state(cmd, root) -> None  H-22's run_guards() gate — block()s
#                                         on a shell mutation of a registered
#                                         protected-state file

import os
import re
import subprocess
import sys

from _hooklib import (
    AUDIT_LOG_BASENAMES, AUDIT_LOG_NAMES, CRYPTO_RE, DECISION_LOG_BASENAME, DECISIONS_DIR_RE,
    GATE_MARKER_NAMES, SECRET_RE, SECURITY_DIFF_GIT_ARGS, block, content_digest,
    is_migration_path, line_digest, marker_fresh, sensitive_scan_added_lines,
)
from _gitexec import git_executable
import _gitlib  # reused for its spawn-free, worktree-aware (.git-as-a-FILE /
                # gitdir: pointer) project_root() climb (#223)
from hostapi import git_worktree_main_root  # noqa: #604 marker-root escalation
import _protectedstatelib  # H-22's shell flank (T-08, #564) — imported as a
                            # module (not `from ... import REGISTRY`) so
                            # _STATE_WRITE_RES below is built from a live
                            # attribute lookup at import time, never a
                            # snapshotted name binding.
from _protectedstatelib import ProtectedPolicy, marker_gated_write_admitted

# The most recent git-read failure, surfaced in the H-01/H-09b/H-14 fail-closed
# block message. "git unavailable or timed out" alone cost a session of root-
# causing (2026-07-01: the real error was a pathspec-parse artifact, visible in
# one look at git's stderr); a fail-closed message must carry its evidence.
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
# H-10b/H-14 for it. `-n` is git-commit's short spelling of --no-verify — but
# NOT only as its own token: git bundles short flags into one cluster
# (`-nm "x"` = `-n` + `-m x`, the everyday spelling), including with an
# attached value (`-nm=x`, `-nm123`), so the exact-token check alone missed it
# (security-reviewer HIGH x2: the bare cluster case, then the attached-value
# cluster case — see `_commit_no_verify_in_cluster`). `git push` has NO short
# spelling for this (its own `-n` is `--dry-run`, an unrelated flag), so only
# the long form is checked there, and it never clusters this way in practice
# for our purposes.
# Token-equality (not substring) so a commit MESSAGE merely quoting the text
# ('-m "explain --no-verify"') is never misclassified — the quoted phrase
# tokenizes as one whole argument, never equal to the bare flag. Scanning
# stops at a bare `--` token (end-of-options): `git commit -- --no-verify`
# passes `--no-verify` as a pathspec, not a flag, and must not be misblocked.
# The deeper shell-indirection spelling (`g=git; $g commit --no-verify`)
# defeats this lexical check same as it defeats COMMIT_RE itself; that
# residual is documented separately, out of scope for this guard.
COMMIT_NO_VERIFY_FLAGS = frozenset({"--no-verify", "-n"})
PUSH_NO_VERIFY_FLAGS = frozenset({"--no-verify"})
# `git commit` short options that consume the REST of their cluster as a
# value (bundled short-flag form, e.g. `-mMSG`, `-Cref`): once one of these is
# hit while scanning a cluster left-to-right, every character after it is that
# option's value, not a further flag — so a `-mn` cluster's trailing `n` is
# the MESSAGE "n", not `-n`/--no-verify, and must not block.
COMMIT_SHORT_VALUE_CHARS = frozenset("mcCFtSu")


def _has_literal_flag(args, flags):
    """True iff `args` contains one of `flags` as its own token — quote-aware
    (a fully-quoted token, e.g. a `-m "..."` message, tokenizes as ONE token
    and is compared whole, so it can never equal a single bare flag).
    Scanning stops at a bare `--` (end-of-options): anything after it is a
    pathspec/value, never a flag."""
    for raw in re.findall(r'"[^"]+"|\'[^\']+\'|\S+', args):
        tok = raw.strip("\"'")
        if tok == "--":
            break
        if tok in flags:
            return True
    return False


def _commit_no_verify_in_cluster(args):
    """True iff a `git commit` bundled short-flag cluster token (e.g. `-nm`,
    `-vn`, `-nm=x`, `-nm123`) carries `-n` (no-verify) BEFORE any
    argument-taking short option — or any attached-value byte — in that same
    token ends the flag-cluster portion. Walks each token that starts with
    `-`+letter (and is not `--...`) left-to-right past the leading `-`:

      * `n`   seen first  -> no-verify -> BLOCK.
      * a COMMIT_SHORT_VALUE_CHARS member seen first -> that flag consumes the
        REST of the token as its value (e.g. `-mn` is `-m` with value "n") ->
        stop scanning this token, not a match.
      * the first NON-ALPHABETIC character (`=`, a digit, `.`, `"`, …) seen
        first -> an attached value has begun (e.g. `-nm=x`, `-nm123`) -> stop
        scanning this token's REMAINDER, but everything scanned so far still
        counts — this is what closes `-nm=x`/`-nm123` (the `n` before the
        `m`/`=`/digit still blocks) while never mis-reading the attached value
        itself as more flag letters.

    security-reviewer HIGH (second pass): a `re.fullmatch(r"-[A-Za-z]+", tok)`
    gate previously skipped the whole token whenever ANY character after the
    dashes wasn't a letter — so `-nm=x`/`-nm123`/`-vnm=y` (a leading `-n`
    immediately followed by an attached value) were never even inspected,
    silently letting `-n`/no-verify through. Matching on `-[A-Za-z]` (just the
    first character after `-`) instead of requiring the WHOLE token to be
    letters fixes this at the root: every token that OPENS a short-flag
    cluster is now walked, and the walk itself (not the initial token shape)
    decides where the flag portion ends.

    Complements the exact-token `-n`/`--no-verify` case in
    COMMIT_NO_VERIFY_FLAGS, which only catches `-n` as its OWN whole token.
    Scanning stops at a bare `--` (end-of-options)."""
    for raw in re.findall(r'"[^"]+"|\'[^\']+\'|\S+', args):
        tok = raw.strip("\"'")
        if tok == "--":
            break
        if tok.startswith("--") or not re.match(r"-[A-Za-z]", tok):
            continue  # a long flag, a value, a pathspec, or not a flag at all
        for ch in tok[1:]:
            if ch == "n":
                return True
            if ch in COMMIT_SHORT_VALUE_CHARS:
                break  # rest of THIS token is that flag's value; stop here
            if not ch.isalpha():
                break  # an attached value (=, digit, ., "…) has begun; stop here
    return False


GIT_OPTION_VALUE = r'(?:"[^"]+"|\'[^\']+\'|\S+)'
# Git's path/namespace/executable/config global options accept both
# `--flag=value` and `--flag value`. The generic long-option leg covers the
# equals form and valueless flags; this explicit leg keeps a separated value
# from being mistaken for the subcommand (#335 coverage review).
GIT_LONG_VALUE_OPTION = (
    r"--(?:git-dir|work-tree|namespace|exec-path|super-prefix|config-env)"
)
GIT_GLOBAL_OPTION = (
    r"(?:-[Cc]\s+" + GIT_OPTION_VALUE
    + r"|" + GIT_LONG_VALUE_OPTION + r"\s+" + GIT_OPTION_VALUE
    + r"|--[\w-]+(?:=\S+)?|-\w+)"
)
GIT = r"\bgit(?:\s+" + GIT_GLOBAL_OPTION + r")*"
# The args capture stops at an unquoted `|`, `;`, or `&` (the next shell command
# is not this git command's business) but consumes quoted strings whole — a
# `;` inside `-m "scoped; and true"` is message content, not a separator.
# Truncating inside the quoted message left an unterminated `$(cat <<'EOF'`
# fragment whose words were then parsed as pathspecs, and a token like
# `/ca:checkpoint)` made `git diff HEAD -- …` fatal ("outside repository"),
# failing the H-09b scan CLOSED on a clean commit.
ARGS = r"(?P<args>(?:\"[^\"]*\"|'[^']*'|[^|;&])*)"
# The `commit` SUBCOMMAND, not every verb starting with it (#485). A word
# boundary sits between `commit` and `-`, so a bare `commit\b` matched
# `git commit-graph write` and gated object-database maintenance as though it
# were a commit — pointing the operator at the crypto-compliance gate for a
# command that writes no objects and creates no commit, whose only escapes were
# a pass certifying nothing or an override covering a coverage hole (the habit
# ADR-0022 and #308 exist to prevent). It bit at the worst moment too: a stale
# graph is what a batch of `--delete-branch` merges leaves behind.
#
# The exclusion is an explicit ALLOW of one proven-safe verb rather than an
# allowlist of gated ones, so the failure direction stays closed — a `commit-*`
# name this matcher has never seen is still gated. `commit-tree` deliberately
# stays in scope: it creates a commit object, and a crafted commit plus
# `update-ref` is a real path around H-01.
COMMIT_SUBCOMMAND = r"commit(?:-(?!graph(?![-\w]))[\w-]+)?(?![-\w])"
COMMIT_RE = re.compile(GIT + r"\s+" + COMMIT_SUBCOMMAND + ARGS)
PUSH_RE = re.compile(GIT + r"\s+push\b" + ARGS)
ADD_RE = re.compile(GIT + r"\s+add\b" + ARGS)
# #485 AC-4, the audit of the sibling matchers. Neither needs the same
# treatment, and both were left alone deliberately:
#
#   push  — git has no `push-*` subcommand, so `push\b` has nothing to
#           over-match onto. If one ever ships, it is gated until reviewed.
#   add   — `git add--interactive` is a real plumbing helper and it DOES stage,
#           so `add\b` reaching it is correct, not a false positive.
#
# What the audit DID surface is a different shape, and it is knowingly not
# fixed here: these matchers scan the command TEXT, so a git command quoted
# inside another command's arguments is gated as if it were being run — a
# `grep "git add"` trips H-03. Skipping quoted occurrences would be wrong, not
# merely conservative: `sh -c "git add ."` executes what it quotes, so the
# exemption would be a real bypass of the staging gate. Distinguishing the two
# needs actual shell tokenization, which is a larger change with a worse
# failure direction; over-blocking a mention is the fail-CLOSED side of that
# trade (ORCHESTRATOR §2: security before velocity). Tracked separately rather
# than half-fixed.
# reliability-004 (#190): GIT_C_DIR_RE previously matched `-C` ONLY as the
# FIRST token after `git`, so a global option in front of it (`--no-pager`,
# `-c k=v`, `--git-dir=…`) hid the -C target entirely and git_cwd() fell back
# to `root` — while COMMIT_RE/PUSH_RE (built on the same GIT global-options
# prefix as below) still matched, so the guards fired against the WRONG repo.
# GIT_OPTS_RUN_RE captures the exact same global-options run GIT already
# tolerates (group 1); GIT_C_IN_RUN_RE then finds every `-C <dir>` WITHIN that
# captured run via findall, so a -C preceded by other global options is found
# regardless of position.
GIT_OPTS_RUN_RE = re.compile(
    r"\bgit((?:\s+" + GIT_GLOBAL_OPTION + r")*)")
GIT_C_IN_RUN_RE = re.compile(r"-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
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
    # #528: `New-Item -Force` TRUNCATES an existing file (verified in PowerShell:
    # a 20-byte file becomes 0). H-11 already covered this family, so the
    # arbitration log lost it on the way to H-05 — and the flat logs never had
    # it. `touch` and `Add-Content` are deliberately NOT here: neither truncates,
    # and Add-Content is the sanctioned append for exactly these files.
    r"|ni|New-Item"
    r"|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content|Out-File)\b"
    r"[^|;&]*" + LOG_NAMES, re.I,
)
# #335: checkout/restore rewrite tracked worktree files through Git itself, so
# they bypass every filesystem verb above. Keep the match bounded to one shell
# command and require a literal audit-log basename in that Git invocation.
# This intentionally does not guess what a pathless `stash apply` or broad
# checkout/restore pathspec might touch; H-05's shell flank remains lexical.
LOG_GIT_RESTORE_RE = re.compile(
    GIT + r"\s+(?:checkout|restore)\b[^|;&]*" + LOG_NAMES, re.I,
)
# H-11's shell flank: ADRs are authored only via /adr (pre-write/pre-edit
# guard the Write/Edit tools; this guards redirection and file verbs). Any
# redirect into .codearbiter/decisions/, or any write/delete verb naming it,
# blocks — `cat`/`ls`/`grep` reads pass untouched.
DECISIONS = DECISIONS_DIR_RE + r"\b"
# #528: the one path under decisions/ that H-11 must NOT claim — see
# _check_h11_decisions. Matched on the raw command, so both separators.
#
# DELIBERATELY CASE-SENSITIVE. H-05, which takes over for this file, is itself
# case-sensitive on both flanks: _check_h05_audit_log pre-filters with a plain
# `in` test over AUDIT_LOG_BASENAMES, and LOG_TRUNC_RE carries no re.I. An re.I
# here therefore stripped `Decision-Log.md` out of H-11's view and handed it to a
# guard that could not see it — and on Windows/NTFS and default macOS/APFS that
# spelling resolves to the real file, so `rm …/Decision-Log.md` destroyed the
# append-only log with nothing firing at all. The two flanks must agree on case.
#
# The right edge is anchored so this path cannot SHIELD a sibling token: without
# it, `touch …/decision-log.md.evil.md` was stripped to a harmless remainder and
# H-11 stopped seeing a decisions/ write at all.
DECISION_LOG_SHELL_RE = re.compile(
    DECISIONS_DIR_RE + r"[\\/]+" + re.escape(DECISION_LOG_BASENAME) + r"""(?=$|[\s>|;&"'])""",
)
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
# #237: an arbitrary interpreter invocation is a flank the verb list above
# cannot see — `python -c "open('.markers/security-gate-passed','w')..."`
# reuses the sanctioned producer's own public helpers to self-compute valid
# digests, and no mv/cp/tee/sed spelling ever appears on the command line.
# Interpreter one-liners get their OWN, wider regex rather than joining the
# verb list above: the payload is a single quoted string handed to the
# interpreter, and that string may itself contain `;` as a statement
# separator (`python -c "x=1; open(...security-gate-passed...)"`). The
# `[^|;&]*` bound on GATE_MARKER_WRITE_RE exists to keep a write verb from
# reaching across an UNRELATED shell-chained command; applying that same
# bound here would stop scanning at the interpreter's OWN internal `;` and
# silently reopen exactly the hole this closes. There is no reliable way to
# tell a chained shell command from a `;`-separated statement inside an
# opaque interpreter string without full shell/language tokenization, so
# this guard fails CLOSED: any command line invoking one of these
# interpreters that ALSO names a gate marker anywhere on the line is
# blocked, whether the marker is written or merely read. A read of a gate
# marker has no legitimate reason to go through a raw interpreter one-liner
# either (cat/grep already pass the audit-log flanks above untouched).
#
# review finding (post-B-2): a `-c`/`-e` payload is ordinary multi-line
# source — the interpreter token and the marker path can sit on different
# physical lines of the SAME invocation (`python -c "\nopen('...security-
# gate-passed'...)\n"`). `[^\n]*` cannot cross that newline, leaving the
# identical attack open in its multi-line spelling. `[\s\S]*` (DOTALL-
# equivalent) closes it. This regex is applied to the heredoc-stripped
# `git_view` at the call site below, gated on `heredoc_shell_fallback` for
# the raw-`cmd` leg exactly like the commit/push/add guards already are —
# scanning the raw, unstripped `cmd` unconditionally would make crossing
# newlines here false-trip on inert PROSE inside a heredoc body fed to a
# non-shell consumer (`gh pr create --body "$(cat <<EOF … a python -c
# one-liner wrote .markers/security-gate-passed … EOF)"` — a PR/issue body
# merely DESCRIBING this very fix), the same D-3 (#223) distinction the
# other guards already draw.
# The interpreter alternation, shared by H-19's gate-marker leg below and
# H-22's per-entry `interp_re` (~line 560). ONE list, because the
# workstream-B adversary's cross-guard parity probe showed the same
# omission reaching every guard that carries an interpreter leg: the
# previous `python3?|node|perl|ruby|sh` missed `py` -- THE canonical
# Python launcher on Windows, this repo's primary dev host -- and
# `powershell`/`pwsh` entirely, so `py -c "open('…','w')"` and
# `powershell -Command "[IO.File]::WriteAllText(…)"` both walked past a
# guard whose docs affirmatively claimed interpreter coverage.
#
# `python2` is spelled out because `python3?` does not match it.
_INTERP_TOKENS = (r"python3?|python2|py|node|deno|bun|perl|ruby|php"
                  r"|sh|bash|zsh|pwsh|powershell")

# The inline-code switch that makes an interpreter EXECUTE A STRING rather
# than run a file. `-c` (python/py/sh/bash/zsh/pwsh), `-e`/`-E` (perl,
# ruby, node, bun), `-r` (php), `-p`/`--print`/`--eval` (node), and
# `eval` as a SUBCOMMAND (deno) rather than a flag.
#
# The nested-optional `c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?` spells the
# prefix family of PowerShell's `-Command`: PowerShell accepts any
# unambiguous abbreviation, so `-Comm`, `-Co` and `-C` are all valid and a
# literal `-Command|-c` alternation would miss them.
#
# Residual, stated rather than left to fall out of the regex: a script
# piped into an interpreter on stdin (`echo … | python3`) puts the
# filename BEFORE the interpreter token and is not reached here, and
# `deno eval` is covered only in its subcommand spelling.
_INTERP_INLINE_CODE = (
    r"(?:-{1,2}(?:c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?|e|E|r|p"
    r"|eval|print|encodedcommand|ec)\b|\beval\b)"
)

# H-19 widens its interpreter list (above) but deliberately does NOT take
# the inline-code requirement H-22 adds below. Narrowing an existing
# security guard is not this sprint's scope, and the argument that makes
# the requirement correct for H-22 does not transfer: handing a
# gate-marker path to a script as argv is itself the suspicious act,
# whereas handing a board filename to `taskwrite.py` is the sanctioned
# call.
GATE_MARKER_INTERP_RE = re.compile(
    r"\b(" + _INTERP_TOKENS + r")\b[\s\S]*" + GATE_MARKER, re.I,
)

# #574: H-05/H-11/H-18 carried NO interpreter leg at all — an inline-code
# one-liner (`python3 -c "open('.codearbiter/overrides.log','w')..."`) walks
# past LOG_TRUNC_RE/LOG_DESTROY_RE, DECISIONS_REDIRECT_RE/DECISIONS_WRITE_RE,
# and CONTEXT_REDIRECT_RE/CONTEXT_WRITE_RE alike, since none of those regexes
# ever look for an interpreter token. Each of the three below takes the SAME
# token-only shape as GATE_MARKER_INTERP_RE just above, not H-22's narrower
# `_state_write_res.interp_re` (which additionally requires
# `_INTERP_INLINE_CODE`): H-22's inline-code requirement exists ONLY because a
# sanctioned caller invokes an interpreter against the protected file's own
# name (`python3 "…/taskwrite.py" add -- "fix open-tasks.md schema"`, HIGH-1),
# and H-05/H-11/H-18 have no equivalent sanctioned interpreter caller to
# spare — narrowing them the same way would reopen exactly the gap this
# closes for no offsetting benefit. `[\s\S]*` (not `[^\n]*`), for the same
# reason GATE_MARKER_INTERP_RE carries it: the interpreter token and the
# target name may sit on different physical lines of the SAME multi-line
# `-c`/`-e` payload.
LOG_INTERP_RE = re.compile(
    r"\b(" + _INTERP_TOKENS + r")\b[\s\S]*" + LOG_NAMES, re.I,
)
DECISIONS_INTERP_RE = re.compile(
    r"\b(" + _INTERP_TOKENS + r")\b[\s\S]*" + DECISIONS, re.I,
)
CONTEXT_INTERP_RE = re.compile(
    r"\b(" + _INTERP_TOKENS + r")\b[\s\S]*" + CONTEXT_MD, re.I,
)

# H-22's shell flank: the protected-state registry (B1/#564) — Write/Edit are
# guarded via classify_protected's "state" class (pre-write.py/pre-edit.py,
# T-05a/T-06/T-07); this closes the shell flank the SAME way the four
# pre-existing classes already do above: a redirect into a registered file,
# or a write/delete verb naming it, blocks.
#
# ONE (redirect_re, write_re) pair PER REGISTRY ENTRY, not a single
# alternation over every registered basename (T-08 design ruling): a regex
# defect in one entry's pattern then stays isolated to that entry — and is
# pinned by that entry's own test — instead of one opaque pattern smearing a
# failure across every consumer. `_state_write_res` is the per-entry
# TEMPLATE, called once per registry entry by `_build_state_write_res`.
#
# BARE basename anchor, deliberately WITHOUT a `.codearbiter/` directory
# prefix the way CONTEXT_MD carries one: the redirect-operator prefix
# (`>>?\|?\s*\S*`) and the verb-then-bounded-window shape
# (`\b(verb-list)\b[^|;&]*`) below are copied verbatim from
# CONTEXT_REDIRECT_RE/CONTEXT_WRITE_RE (above, ~line 355), but the NAME
# fragment itself mirrors AUDIT_LOG_NAMES/LOG_TRUNC_RE/LOG_DESTROY_RE's
# bare-filename anchor instead. This is not a stylistic choice: B-07/B-08's
# own non-regression cases, and the T-08b lexical residual, both name the
# protected file with NO `.codearbiter/` prefix at all — `taskwrite add --
# "fix open-tasks.md schema"` and the false-blocking `taskwrite add -- "…tee
# open-tasks.md"` both carry the bare filename inside free-text argv. A
# directory-anchored pattern could neither reproduce the documented residual
# nor catch a real `tee open-tasks.md` run with a cwd already inside
# `.codearbiter/` (where no directory prefix appears in the command text
# either) — it would under-scan exactly the attack this guard exists for.
# The right-edge lookahead DECISION_LOG_SHELL_RE (#528, ~line 355) already
# carries. H-22's bare-basename anchor inherited the over-match closing it
# fixes without it: `rm .codearbiter/open-tasks.md.bak` matched, because the
# basename is a literal PREFIX-substring of the ".bak" spelling and nothing
# required the basename text to END where it should. Requires end-of-string,
# whitespace, a redirect/pipe/separator, or a quote-close immediately after
# the basename — never a bare `\b` word boundary alone, which cannot do this
# job here (a hyphen is a non-word character on BOTH its sides, so `\b` sits
# at a hyphen exactly as readily as at a `/`; it cannot distinguish
# "…/open-tasks.md" from "my-open-tasks.md").
#
# This closes only the RIGHT-side over-match. The mirror-image LEFT-side one
# (a longer filename that happens to END with the registered basename, e.g.
# `my-open-tasks.md`, `> my-open-tasks.md`) is a KNOWN, ACCEPTED residual of
# the bare-basename anchor design itself (finding F4, #564 follow-up) — a
# left anchor would require knowing the basename is not itself part of a
# longer name, which the bare-anchor design (see the module comment above)
# deliberately does not have enough context to tell apart from a legitimate
# no-directory-prefix spelling. Declared, not merely implicit: see
# security-controls.md's "Protected-state registry (H-22)" section.
_STATE_NAME_RIGHT_EDGE = r"""(?=$|[\s>|;&"'])"""

# The write-verb list, extended past the CONTEXT_WRITE_RE/DECISIONS_WRITE_RE
# baseline it was copied from (finding F6, #564 follow-up) with verbs
# present in this file's own cited precedents but missing here: `sponge`
# (already in LOG_DESTROY_RE, ~line 317), plus `ln` (a hardlinked/symlinked
# name overwrites whatever sits there with `ln -f`), `install` (coreutils'
# copy-with-permissions — a genuine overwrite verb), `patch` (rewrites a
# file in place from a diff), and `shred` (secure-delete, the ultimate
# destroy). `install`/`ln` both carry a real false-positive cost of their
# own (`npm install`/`pip install` are common phrases; `ln` is a short,
# common token) — accepted under the SAME "ambiguity resolves CLOSED"
# stance this file states at its own top (module docstring) and applies
# throughout (e.g. `cp overrides.log backup`, a mere READ, blocks anyway);
# declared in security-controls.md rather than left an undeclared gap.
_STATE_WRITE_VERBS = (
    r"rm|del|mv|cp|copy|dd|tee|sed|sponge|ln|install|patch|shred|truncate|ni"
    r"|New-Item|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content"
    r"|Out-File|Add-Content"
    # workstream-B adversary MEDIUM-5: `unlink` is `rm`'s direct sibling and
    # this list already carries `shred`/`truncate`; `ex`/`vim -es` are
    # editors driven as batch WRITERS (`-c wq`), which is the same act as
    # `sed -i` by another name; `rsync` overwrites a destination path the
    # way `cp` does.
    #
    # `ex`/`vim` consequently block an INTERACTIVE open too, which is
    # intended rather than tolerated: `helper-only` exists to make the
    # sanctioned helper the only writer, and opening the board in an editor
    # is the hand-composed-markdown path the policy prevents — the likelier
    # spelling of it than `vim -es -c wq`. Reading stays open (`cat`,
    # `grep`, `view`, `git log`), pinned by
    # `test_reads_of_a_helper_only_file_still_pass`. `\b` keeps the
    # two-letter `ex` from matching inside `export`/`eslint`/`extract`.
    r"|unlink|ex|vim|rsync"
)

# #575: `install` above exists for coreutils' `install` (a genuine
# copy-with-permissions overwrite verb) — but a PACKAGE MANAGER's `install`
# SUBCOMMAND (`pip install -r requirements.txt`, `npm install`, `cargo
# install`, `apt install`, `brew install`, …) is a different verb entirely
# wearing the same word, and the T-08b same-line window then reaches a
# protected basename mentioned anywhere later on that line (a trailing
# comment, a free-text description) — false-blocking a routine dependency
# install. A PRECEDING-TOKEN check, not a smarter parser: this pattern
# recognizes the KNOWN package-manager-subcommand spelling specifically, so
# `_check_h22_state` can blank JUST that phrase out of the text `write_re`
# scans, leaving the bare coreutils spelling (nothing package-manager-shaped
# immediately before `install`) to block exactly as before.
_PKG_MANAGER_INSTALL_RE = re.compile(
    r"\b(?:pip3?|npm|pnpm|yarn|cargo|apt(?:-get)?|brew|conda|gem|composer"
    r"|dnf|yum|choco|winget)\s+install\b", re.I,
)


def _strip_pkg_manager_install(cmd):
    """#575: blank out every `<package manager> install` phrase in `cmd` so
    H-22's write-verb leg (`write_re`, built by `_state_write_res` below)
    never mistakes the SUBCOMMAND spelling for the coreutils overwrite verb
    it exists to catch. Mirrors `_check_h11_decisions`'s
    `DECISION_LOG_SHELL_RE.sub(" ", cmd)` — a narrow, single-purpose strip
    applied only where the verb leg runs; every other guard (redirect,
    git-restore, interpreter, and every OTHER H-NN check) still sees the
    unmodified `cmd`."""
    return _PKG_MANAGER_INSTALL_RE.sub(" ", cmd)


def _state_write_res(basename, rel_path=None):
    r"""`(redirect_re, write_re, git_restore_re, interp_re)` for ONE
    protected-state registry entry's bare filename — the compiled set
    `_build_state_write_res` returns one of, per entry. See the module
    comment above for why this is bare-basename, not directory-anchored,
    and `_STATE_NAME_RIGHT_EDGE`/`_STATE_WRITE_VERBS` above for the
    right-anchor and extended verb list (finding F4/F6).

    `rel_path` (#575, optional — every existing caller that passes only
    `basename` keeps working unchanged) supplies the registry entry's full
    path so `git_restore_re` can ALSO cover a directory-level restore; see
    the git_restore_re docstring section below.

    `git_restore_re` (finding F5, #564 follow-up): mirrors H-05's
    LOG_GIT_RESTORE_RE (#335) — `git checkout`/`git restore` rewrite a
    TRACKED worktree file through git itself, bypassing every filesystem
    verb above entirely (all three planned registry entries are tracked
    files, so this is not a hypothetical). A SEPARATE pattern, not folded
    into the write-verb list: `checkout`/`restore` are git SUBCOMMANDS, not
    shell verbs, and matching them needs the `GIT` global-options-tolerant
    prefix the write-verb list has no business carrying. Deliberately does
    NOT match `git add` — B-07's non-regression (commit-gate Phase 7 runs
    `git add open-tasks.md` on every retained board flip, which must never
    trip H-22) — and structurally cannot: the subcommand alternation here is
    only `checkout|restore`.

    #575 (the non-package-manager half of the lexical-residual issue):
    `git checkout HEAD -- .codearbiter/` restores the file's ENCLOSING
    DIRECTORY without naming the file itself — rewriting it (and every
    sibling tracked file under that directory) through git while matching
    no basename at all, so the bare-basename alternative above never fires.
    When `rel_path` carries a directory component, `git_restore_re` gains
    one alternative PER ANCESTOR DIRECTORY, each anchored (via the SAME
    `_STATE_NAME_RIGHT_EDGE`, after an optional single trailing slash) to
    match ONLY the directory itself — never a file living inside it, which
    stays the basename alternative's job and would otherwise let this leg
    swallow every sibling path as a substring of the directory name.

    `interp_re` (finding F6, #564 follow-up): mirrors GATE_MARKER_INTERP_RE
    (#237) — an arbitrary interpreter one-liner
    (`python -c "open('open-tasks.md','w')..."`) reuses `helper-only`'s own
    sanctioned Python file-I/O route while naming the target file lexically,
    a flank no verb-list spelling above can see. `[\s\S]*` (not `[^\n]*`,
    per the #237 follow-up) so the inline-code switch and the filename may
    sit on different physical lines of the SAME multi-line `-c`/`-e`
    payload — `[^\n]*` cannot cross that newline and would silently reopen
    the identical hole in its multi-line spelling.

    An INLINE-CODE SWITCH is required between the interpreter and the
    filename (`_INTERP_INLINE_CODE`), and this is the load-bearing half of
    the pattern, not a refinement. Without it the leg matched any command
    line carrying an interpreter token and the basename in any order --
    which is the shape of the SANCTIONED CALL: `python3
    "…/hooks/taskwrite.py" add -- "fix open-tasks.md schema"`. The
    workstream-B adversary drove the real `pre-bash.py` and found every
    such invocation BLOCKED, including `done` and `archive` on an ID-less
    task whose own title names the file -- where the target IS the title,
    so there is no rewording available and no sanctioned route left at
    all. That inverted the enrolment's entire premise.

    The discriminator is EXECUTES-A-STRING versus RUNS-A-FILE. `python3
    script.py <basename>` passes the name as argv DATA to a file this
    lexical guard could never see inside anyway; `python3 -c "…<basename>…"`
    puts the write in the command line itself, where the guard can see it.
    Declared residual, unchanged by this fix and unchanged in kind: a
    script FILE that writes a registered path is not reachable lexically,
    which is what ADR-0024's cooperative, friction-grade grading says."""
    name = re.escape(basename)
    redirect_re = re.compile(
        r">>?\|?\s*\S*" + name + _STATE_NAME_RIGHT_EDGE, re.I)
    # `[^|;&\n]*`, NOT the `[^|;&]*` this was copied from: a shell verb and
    # the file it targets sit on ONE line, so letting the window cross
    # newlines buys no coverage and costs real false blocks. The window ran
    # from a `sed -i` on line 12 of this branch's own commit 063b0b4 to a
    # `done-tasks.md` on line 15 — meaning the commit that ENROLLED the
    # board files carries a message the guard it installs would refuse
    # (workstream-B adversary MEDIUM-3), with no escape: commit-gate
    # permits `-m` or a heredoc, and `_check_h22_state` scans raw `cmd`
    # without heredoc stripping (the declared LOW-5 residual), so both
    # routes hit it. Also caught `pip install -r reqs.txt  # then read
    # open-tasks.md`.
    #
    # The same-line residual (T-08b) is UNCHANGED and still pinned: a write
    # verb and the basename on one line stay indistinguishable from a real
    # redirect at this guard's lexical level.
    write_re = re.compile(
        r"\b(" + _STATE_WRITE_VERBS + r")\b[^|;&\n]*" + name + _STATE_NAME_RIGHT_EDGE, re.I,
    )
    # `[^|;&\n]*` for the SAME reason `write_re` above carries it: a git
    # subcommand and its pathspec sit on one line, so crossing newlines buys
    # no coverage and costs false blocks on multi-line commit bodies. This
    # leg was left on the old unbounded window when `write_re` was fixed --
    # a sibling two lines away, with the identical defect, missed because the
    # fix was applied to the reported pattern rather than to the class.
    #
    # #575: one alternative per ANCESTOR DIRECTORY of `rel_path`, alongside
    # the bare basename — see the docstring section above. `dir_alts` is
    # empty (no directory component) when `rel_path` is omitted or bare, so
    # `restore_target` degrades to exactly the old basename-only pattern.
    restore_target = name
    if rel_path:
        parts = [p for p in rel_path.replace("\\", "/").split("/") if p not in ("", ".")]
        dir_alts = ["/".join(parts[:i]) for i in range(1, len(parts))]
        if dir_alts:
            dir_pattern = "|".join(
                re.escape(d).replace("/", r"[\\/]+") for d in dir_alts)
            restore_target = "(?:" + name + r"|(?:" + dir_pattern + r")[\\/]?)"
    git_restore_re = re.compile(
        GIT + r"\s+(?:checkout|restore)\b[^|;&\n]*" + restore_target
        + _STATE_NAME_RIGHT_EDGE, re.I,
    )
    interp_re = re.compile(
        r"\b(" + _INTERP_TOKENS + r")\b[^\n]*?" + _INTERP_INLINE_CODE
        + r"[\s\S]*" + name + _STATE_NAME_RIGHT_EDGE, re.I,
    )
    return redirect_re, write_re, git_restore_re, interp_re


def _build_state_write_res(registry):
    """`(rel_path, policy, redirect_re, write_re, git_restore_re,
    interp_re)` for every entry in `registry`, keyed on each entry's bare
    basename via `_state_write_res`. An explicit `registry` PARAMETER (not a
    bare comprehension over the module-level default) so a test can rebuild
    this exact tuple against a SYNTHETIC registry — the real one ships EMPTY
    at this slice (T-01–T-08; T-33/T-65/T-66 enroll the three named
    consumers later) — the same `registry=`-parameter shape
    `_protectedstatelib.lookup_policy` already uses for the identical
    reason."""
    built = []
    for rel_path, policy in registry.items():
        basename = rel_path.replace("\\", "/").rsplit("/", 1)[-1]
        redirect_re, write_re, git_restore_re, interp_re = _state_write_res(basename, rel_path)
        built.append((rel_path, policy, redirect_re, write_re, git_restore_re, interp_re))
    return tuple(built)


# performance-002/_scopelib.py:109-117 precedent: compiled ONCE at import
# from the live (code-constant, never disk-loaded — #564 design ruling)
# registry, not recompiled per call. Empty at this slice, so
# `_check_h22_state` is correctly a no-op against every command until a
# consumer is registered. A test exercises the real logic by rebuilding this
# EXACT tuple against a synthetic registry (`_build_state_write_res`), never
# by mutating `_protectedstatelib.REGISTRY` after the fact — this tuple
# would not see that (it is a one-time import-time snapshot, by design).
_STATE_WRITE_RES = _build_state_write_res(_protectedstatelib.REGISTRY)


def git_cwd(cmd, root):
    """The directory a `git -C <dir>` invocation actually targets, or `root`
    when there is no `-C` (reliability-004, #190).

    Scans the SAME global-options run GIT/COMMIT_RE/PUSH_RE already tolerate
    before the subcommand (GIT_OPTS_RUN_RE), so a `-C` preceded by other
    global options (`git --no-pager -C ../x commit`, `git -c k=v -C ../x
    commit`) is found exactly where the guards themselves look, instead of
    only matching `-C` as the first token.

    Git allows REPEATED `-C` and COMPOSES them sequentially, not
    last-wins: each `-C` is resolved relative to the ACCUMULATED result of
    every preceding `-C` (an absolute value REPLACES the accumulator; a
    relative value is joined onto it) — see `git --help`'s `-C <path>`. A
    naive "take the last -C, resolve if relative against root" is wrong for a
    mixed run: `git -C /abs/main -C . commit` must resolve to `/abs/main`
    (the `.` is relative to `/abs/main`, not to root), and `git -C feat -C
    /abs/main commit` must resolve to `/abs/main` (the later absolute value
    resets the accumulator, discarding the earlier relative one entirely) —
    a last-wins-only implementation fails OPEN on exactly these spellings
    (security-reviewer MEDIUM, #190 follow-up).

    The accumulator is seeded with `root` (project_root), not the hook
    process's own cwd — the hook's cwd is not guaranteed to be the project
    dir (mirrors _hooklib.project_root's own rationale), so the FIRST
    relative `-C` in a run resolves against `root`, exactly as a bare
    relative `-C` (no preceding `-C`) already did."""
    m = GIT_OPTS_RUN_RE.search(cmd)
    if not m:
        return root
    c_matches = GIT_C_IN_RUN_RE.findall(m.group(1))
    if not c_matches:
        return root
    acc = root
    for raw in c_matches:
        val = raw.strip("\"'")
        acc = val if os.path.isabs(val) else os.path.join(acc, val)
    return acc


def _effective_exec_root(payload, root):
    """The git root that a `-C`-less git command in THIS Bash call actually
    runs against — the command's effective cwd — rather than always the
    pinned `root` (CLAUDE_PROJECT_DIR) (#223).

    #223's bug: `root` is pinned to CLAUDE_PROJECT_DIR (the MAIN checkout),
    so a `git commit` fired from a LINKED WORKTREE was judged against the
    main checkout's branch — both a false positive (worktree on a feature
    branch, main checkout on main -> wrongly blocked) and a false negative
    (worktree on main/master, main checkout on a feature branch -> H-01
    silently sidestepped, the more serious direction).

    D-2 (spec pre-release-hardening): this function governs BRANCH/DIFF
    resolution (git_cwd's seed) ONLY. Gate MARKERS always keep reading from
    the pinned `root` regardless of this function's answer — a linked
    worktree has `.codearbiter/` (tracked) but not `.codearbiter/.markers/`
    (gitignored), so marker paths must stay anchored at the main checkout.
    This split existed accidentally before #223 (pre-bash.py:769,828 already
    read markers from `root` while everything else read from `cwd`); this is
    now the intentional, documented contract.

    Resolution reuses `_gitlib.project_root` — the existing linked-worktree-
    aware precedent (`_gitlib.head_branch` already parses a `.git` FILE's
    `gitdir:` pointer for exactly this case) — rather than a fresh
    `git rev-parse --show-toplevel` spawn. It climbs from the hook payload's
    own `cwd` (a trusted-harness input, same footing as CLAUDE_PROJECT_DIR
    itself — see security-controls.md's Repo resolution section) or, absent
    one, the hook process's own cwd, stopping at the nearest ancestor with a
    `.git` (dir OR file) or a `.codearbiter` directory — a linked worktree's
    `.git` is a FILE, and it also carries its own `.codearbiter/`, so either
    check alone stops the climb at the worktree root, never the main
    checkout.

    When that climb lands on the SAME root as `root`, this returns `root`
    unchanged — the overwhelmingly common (non-worktree) case sees zero
    behavioral difference. It returns the climbed root only when it names a
    genuinely DIFFERENT filesystem location."""
    exec_root = _gitlib.project_root(payload if isinstance(payload, dict) else {})
    if os.path.normpath(os.path.abspath(exec_root)) == os.path.normpath(os.path.abspath(root)):
        return root
    return exec_root


# D-3 (spec pre-release-hardening, #223): the raw-`cmd` fallback below (used
# when a heredoc is present) must fire ONLY when the heredoc body can
# genuinely reach a shell — via EITHER of two independent routes, checked by
# the two functions below (`_heredoc_fed_to_shell` and `_has_shell_executor`,
# OR'd together at the call site): (1) the heredoc's DIRECT consumer is
# itself a shell-like program whose stdin is executed as code (`bash <<EOF`),
# or (2) some OTHER token in the command is a shell/interpreter executor that
# runs a command-substitution result carrying the heredoc's output
# (`bash -c "$(cat <<EOF … EOF)"` — the heredoc's direct consumer is `cat`,
# route (1) says no, but `bash -c` EXECUTES what `cat` produced, so route (2)
# must say yes). A heredoc handed to a non-shell consumer with NO executor
# anywhere in the command (`gh pr create --body "$(cat <<EOF … EOF)"`) is
# inert prose to this guard even though it is substituted into another
# command's argument — neither route fires, so the fallback correctly stays
# off and a PR/issue body merely QUOTING "git commit" does not false-trip.
SHELL_HEREDOC_CONSUMERS = frozenset({
    "bash", "sh", "zsh", "dash", "ksh",
    "python", "python2", "python3", "perl", "ruby", "node", "nodejs",
})


def _heredoc_fed_to_shell(cmd):
    """True iff at least one `<<` heredoc operator in `cmd` attaches to a
    shell-like consumer (SHELL_HEREDOC_CONSUMERS) — a program whose stdin IS
    executed, not merely read as inert text.

    The consumer is the FIRST token of the "simple command" the heredoc
    operator sits at the end of: scan backward from the operator to the
    nearest unquoted `|`, `;`, `&`, or `(` (or the start of the string) —
    that is where the current simple command began — then take its first
    token. This correctly finds `bash` in `bash <<EOF` and `cat` (not `gh`)
    in `gh pr create --body "$(cat <<EOF … EOF)"` (the `(` from `$(` bounds
    the segment)."""
    for m in re.finditer(r"<<", cmd):
        start = m.start()
        seg_start = 0
        in_dq = in_sq = False
        for i in range(start - 1, -1, -1):
            ch = cmd[i]
            if ch == '"' and not in_sq:
                in_dq = not in_dq
            elif ch == "'" and not in_dq:
                in_sq = not in_sq
            elif not in_dq and not in_sq and ch in "|;&(":
                seg_start = i + 1
                break
        segment = cmd[seg_start:start]
        tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', segment)
        if not tokens:
            continue
        head = os.path.basename(tokens[0].strip("\"'"))
        if head in SHELL_HEREDOC_CONSUMERS:
            return True
    return False


# security-reviewer finding (post-A-4): `_heredoc_fed_to_shell` alone answers
# "is the heredoc's DIRECT consumer a shell" — that is NOT the same question
# as "does the heredoc's body reach a shell." `bash -c "$(cat <<EOF … EOF)"`
# has `cat` as the heredoc's direct consumer (correctly classified non-shell
# by the check above), but `bash -c` then EXECUTES the substituted result of
# that `cat` — the body reaches a shell by a route the direct-consumer check
# cannot see (same hole for `eval "$(cat <<EOF … EOF)"`, `sh -c "$(…)"`, and
# any command-substitution chain ending in a shell/interpreter executor).
# This second check asks the complementary question: does ANY token in the
# whole command invoke something that executes a string as code, regardless
# of where the heredoc sits relative to it. FAILS CLOSED on uncertainty —
# `eval` and `xargs` (which can forward its input straight into an executor)
# are treated as always-executor, no flag required.
SHELL_C_PROGRAMS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
INTERP_C_PROGRAMS = frozenset({"python", "python2", "python3"})
INTERP_E_PROGRAMS = frozenset({"perl", "ruby", "node", "nodejs"})
ALWAYS_EXECUTOR_PROGRAMS = frozenset({"eval", "xargs"})


def _has_shell_executor(cmd):
    """True iff `cmd` invokes ANYWHERE a program that executes a string as
    code: `bash -c`/`sh -c`/`zsh -c`/`dash -c`/`ksh -c`, `python[23]? -c`,
    `perl -e`/`ruby -e`/`node[js]? -e`, or a bare `eval`/`xargs` (both can
    hand an arbitrary string straight to an executor — `xargs bash -c '...'`,
    `eval "$var"` — so both are treated as executors unconditionally, no
    flag needed, per the fail-closed mandate).

    Scans the RAW command (heredoc bodies included) — a heredoc body that
    happens to mention one of these tokens as prose causes a conservative
    over-block, never an under-scan, matching this file's established
    ambiguity-resolves-CLOSED stance (D-3)."""
    tokens = [t.strip("\"'") for t in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', cmd)]
    basenames = [os.path.basename(t) for t in tokens]
    if any(b in ALWAYS_EXECUTOR_PROGRAMS for b in basenames):
        return True
    if "-c" in tokens and any(
            b in SHELL_C_PROGRAMS or b in INTERP_C_PROGRAMS for b in basenames):
        return True
    if "-e" in tokens and any(b in INTERP_E_PROGRAMS for b in basenames):
        return True
    return False


def current_branch(cwd):
    """The current branch name, "" for a legitimate detached HEAD, or None when
    git could not answer (nonzero exit / spawn failure / timeout). reliability-001
    (#189): the None sentinel lets H-01 fail CLOSED on a git-read error instead of
    silently treating "unknown" the same as "detached, not on a protected tip" —
    the prior `except: return ""` collapsed those two states and let a commit
    through when branch state genuinely could not be determined."""
    argv = [git_executable(), "branch", "--show-current"]
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
    argv = [git_executable(), "show-ref", "--head", "refs/heads/main", "refs/heads/master"]
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
    silently failed OPEN on exactly the platform this layer protects.

    Excludes gate-events.log (#279): `sensitive_scan_added_lines` walks the
    diff path-aware, dropping lines that belong to the crypto/secret gate's
    own machine-written audit sink — see its docstring in `_hooklib`. Reads
    the diff via SECURITY_DIFF_GIT_ARGS (pinned a/ b/ prefixes, no external
    diff) so a hostile `diff.mnemonicPrefix`/`diff.noprefix`/external-diff
    config can never break that attribution (#279 review MEDIUM-1)."""
    argv = [git_executable(), *SECURITY_DIFF_GIT_ARGS, ref] + (
        ["--", *paths] if paths else [])
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
    return "\n".join(sensitive_scan_added_lines(out.stdout))


def _names(cwd, args):
    """A set of repo-relative paths from a `git ... --name-only` style query, or
    None when git could not answer (nonzero / timeout / error). None (not an
    empty set) lets the H-14 migration scan fail CLOSED on a read error rather
    than concluding "no migrations staged" from a failed read."""
    try:
        out = subprocess.run(
            [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
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


def _check_h20_commit_no_verify(commit):
    """H-20: block a literal --no-verify / -n on `git commit` — it skips
    .git/hooks (the git-enforce backstop) entirely, voiding every enforcement
    hook for that commit (appsec-002, #175). Checks BOTH the exact-token
    spelling (`-n` / `--no-verify` on its own) and the bundled short-flag
    cluster spelling (`-nm "x"`) — the everyday way `-n` actually gets typed
    alongside `-m`, missed by an exact-token-only check (security-reviewer
    HIGH, first pass)."""
    if commit and (_has_literal_flag(commit.group("args"), COMMIT_NO_VERIFY_FLAGS)
                   or _commit_no_verify_in_cluster(commit.group("args"))):
        block("H-20", "'--no-verify' / '-n' on git commit skips the .git/hooks "
                      "git-enforce backstop entirely (appsec-002) — every commit-time "
                      "gate (H-01/H-02/H-09b/H-10b/H-14) would go unenforced for this "
                      "commit. Remove the flag; use /override for a sanctioned bypass.")


def _check_h01_commit_protected_branch(commit, cwd):
    """H-01: no commit directly to main/master — case-insensitive, and a detached
    HEAD sitting on a protected branch's tip counts (the commit lands on its
    history regardless of the absent branch name)."""
    if commit:
        branch = _require_branch(cwd)
        if is_protected_branch(branch) or (not branch and _require_tip(cwd)):
            target = branch or "main/master (detached HEAD)"
            block("H-01", f"Direct commit to {target} is prohibited (ORCHESTRATOR §3). "
                          f"Create a feature branch.")


def _check_push_gates(push, cwd):
    """H-20/H-02/H-01: the push-time gate cluster — no-verify, force-push, bulk
    (--all/--mirror), protected-destination refspec, and bare push from a
    protected branch."""
    if not push:
        return
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


def _check_h03_wildcard_add(add, cwd):
    """H-03: no wildcard git staging — stage explicitly (commit-gate). Both the
    flag spellings (-A/--all/-u/.) and the argument spellings (globs,
    directories, pathspec magic) — `git add src/` stages everything beneath
    src/ just as surely as `git add -A` does."""
    if not add:
        return
    if WILDCARD_ADD_RE.search(add.group("args")):
        block("H-03", "'git add -A' / 'git add .' / 'git add --all' / 'git add -u' "
                      "are prohibited. Stage files explicitly (commit-gate skill).")
    why = add_violation(add.group("args"), cwd)
    if why:
        block("H-03", f"Wildcard staging is prohibited — {why} stages a "
                      f"non-explicit file set. Stage files explicitly, one path "
                      f"per file (commit-gate skill).")


def _check_h05_audit_log(cmd):
    """H-05: the audit trail is append-only — block truncation/removal of the
    audit logs via shell verbs (Write/Edit are guarded separately). The
    substring pre-filter is a cheap short-circuit before the two regexes
    below (avoids running them against every command); it is DERIVED from
    _hooklib.AUDIT_LOG_BASENAMES (the single authoritative name list)
    instead of a hand-copied literal list, so a future audit log added there
    can never silently skip this shell flank (the exact drift
    security-controls.md § Audit trail centralization exists to prevent)."""
    # #574: LOG_INTERP_RE closes the interpreter-one-liner flank
    # (`python3 -c "open('.codearbiter/overrides.log','w')..."`) — the
    # verb-list and redirect legs above never look for an interpreter token
    # at all, so this shape walked past both.
    if any(n in cmd for n in AUDIT_LOG_BASENAMES) and (
            LOG_TRUNC_RE.search(cmd) or LOG_DESTROY_RE.search(cmd)
            or LOG_GIT_RESTORE_RE.search(cmd) or LOG_INTERP_RE.search(cmd)):
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, sprint-log.md, "
                      "gate-events.log, decisions/decision-log.md) are append-only "
                      "(ORCHESTRATOR §7). Truncating, overwriting, or deleting the audit "
                      "trail is prohibited; append with '>>' only.")


def _check_h11_decisions(cmd):
    """H-11: ADRs exist only via /adr — the Write/Edit tools are guarded by
    pre-write/pre-edit, and this closes the shell flank (`echo > decisions/…`,
    `touch`, `cp`, `rm`, `sed -i`, …). Reads are untouched.

    #528: decisions/decision-log.md is the append-only arbitration log, not an
    ADR, and belongs to H-05 — which already covers it, since LOG_NAMES is
    composed from the same _hooklib alternation. Blank its path out of the
    string H-11 scans so an append to it is not read as an ADR write. Only that
    exact path is removed, so a directory-level operation
    (`rm -rf .codearbiter/decisions`) still carries a decisions/ reference and
    still blocks."""
    # #574: DECISIONS_INTERP_RE closes the interpreter-one-liner flank the
    # same way LOG_INTERP_RE does for H-05 — scanned against the SAME
    # decision-log-stripped `cmd` as the two legs above, so an interpreter
    # append to decisions/decision-log.md stays the #528 carve-out's to
    # police (via H-05's own LOG_INTERP_RE), not a false H-11 block.
    cmd = DECISION_LOG_SHELL_RE.sub(" ", cmd)
    if (DECISIONS_REDIRECT_RE.search(cmd) or DECISIONS_WRITE_RE.search(cmd)
            or DECISIONS_INTERP_RE.search(cmd)):
        block("H-11", "ADR files under .codearbiter/decisions/ are authored only via "
                      "/adr and are immutable history (ORCHESTRATOR §6) — shell writes, "
                      "edits, and deletions there are prohibited.")


def _check_h18_context_md(cmd):
    """H-18: CONTEXT.md is the activation switch (#159) — shell flank. A shell
    rewrite/delete of it would make every gate dormant; init writes it via the
    Write tool, so nothing legitimate is blocked. Reads pass.

    #574: CONTEXT_INTERP_RE closes the interpreter-one-liner flank the same
    way LOG_INTERP_RE/DECISIONS_INTERP_RE do for H-05/H-11."""
    if (CONTEXT_REDIRECT_RE.search(cmd) or CONTEXT_WRITE_RE.search(cmd)
            or CONTEXT_INTERP_RE.search(cmd)):
        block("H-18", ".codearbiter/CONTEXT.md is the activation switch every enforcement "
                      "hook reads (#159) — shell rewrites, edits, or deletions that could flip "
                      "`arbiter: enabled` off or corrupt its frontmatter are prohibited. Edit it "
                      "through the sanctioned init path.")


def _check_h19_gate_marker(git_view, cmd, heredoc_shell_fallback):
    """H-19: the gate-pass markers (#160) are recorded only by the sanctioned
    python producers — shell flank against `echo <digest> > security-gate-passed`
    and `cp`/`sed`/`tee` forges naming a gate marker, plus an interpreter
    one-liner (#237).

    review finding (post-B-2): scan `git_view` (heredoc bodies stripped),
    with the raw-`cmd` leg gated on `heredoc_shell_fallback` — mirroring
    how commit/push/add already work post-D-3 (#223). Scanning raw `cmd`
    unconditionally, as this used to, means a heredoc body fed to a
    NON-shell consumer that merely QUOTES a gate-marker path (a PR/issue
    body describing this very fix) false-trips H-19; scanning only
    `git_view` would miss the genuine case where the heredoc's body DOES
    reach an executor (`bash -c "$(cat <<EOF … EOF)"`)."""
    def _gate_marker_hit(view):
        return (GATE_MARKER_REDIRECT_RE.search(view)
                or GATE_MARKER_WRITE_RE.search(view)
                or GATE_MARKER_INTERP_RE.search(view))

    if _gate_marker_hit(git_view) or (heredoc_shell_fallback and _gate_marker_hit(cmd)):
        block("H-19", "The .codearbiter/.markers/ security-gate-passed / migration-gate-passed "
                      "tokens are recorded only by the sanctioned gate producers (#160) — a shell "
                      "redirect, write verb, or interpreter invocation (python/node/perl/ruby/sh) "
                      "naming a gate marker forges a security/migration gate pass and is "
                      "prohibited.")


def _check_h22_state(cmd, root):
    """H-22: the protected-state registry's shell flank (B-04/B1, #564).
    Walks the precompiled per-entry pairs (`_STATE_WRITE_RES`); a command
    that redirects into, or runs a write/delete verb against, a registered
    basename either admits (marker-gated, under a FRESH authoring marker —
    `_protectedstatelib.marker_gated_write_admitted`, the H-11 pattern) or
    blocks outright (helper-only/append-only — flank-IDENTICAL: the
    distinction between them lives entirely in what the sanctioned helper's
    OWN append verb is allowed to do, never in this shell guard, which has
    no marker path for either).

    Marker checks read from the pinned `root` (project_root), never `cwd` —
    the SAME split `_check_h09b_h10b_crypto_secret`/`_check_h14_migration`
    already draw (D-2, `_effective_exec_root`'s own docstring): a linked
    worktree has `.codearbiter/` (tracked) but not `.codearbiter/.markers/`
    (gitignored), so marker paths must stay anchored at the main checkout.

    Git verbs are deliberately ABSENT from the write-verb list (the same
    list `CONTEXT_WRITE_RE`/`DECISIONS_WRITE_RE` already use) — `git add
    open-tasks.md` (commit-gate Phase 7, run on every retained board flip)
    must never reach a block here (B-07), or commit-gate would block itself
    on its own sanctioned board-flip staging. `git checkout`/`git restore`
    ARE covered, but via the separate `git_restore_re` leg (finding F5,
    #564 follow-up) — never the general write-verb list — precisely so that
    isolation holds: `git_restore_re`'s subcommand alternation is only
    `checkout|restore`, so it structurally cannot also catch `git add`.

    #575: `write_re` is matched against `_strip_pkg_manager_install(cmd)`,
    not raw `cmd` -- every OTHER leg (redirect/git-restore/interp) still
    scans the unmodified command text; only the write-verb leg needs the
    strip, since `install` is the one verb in `_STATE_WRITE_VERBS` that is
    also a common package-manager subcommand."""
    verb_scan_cmd = _strip_pkg_manager_install(cmd)
    for rel_path, policy, redirect_re, write_re, git_restore_re, interp_re in _STATE_WRITE_RES:
        if not (redirect_re.search(cmd) or write_re.search(verb_scan_cmd)
                or git_restore_re.search(cmd) or interp_re.search(cmd)):
            continue
        if policy == ProtectedPolicy.MARKER_GATED and marker_gated_write_admitted(rel_path, root):
            continue
        if policy == ProtectedPolicy.MARKER_GATED:
            block("H-22", f"'{rel_path}' is marker-gated protected project state (#564) — a "
                          f"shell redirect or write/delete verb naming it is admitted only "
                          f"under a fresh authoring marker. Mint the marker via the sanctioned "
                          f"authoring lane, or /override.")
        else:
            block("H-22", f"'{rel_path}' is protected project state (#564, "
                          f"policy={policy.value}) — shell redirects and write/delete verbs "
                          f"naming it are prohibited outright; there is no marker path for "
                          f"this policy. Use the sanctioned helper.")


def _marker_root(root):
    """`root`, escalated to the MAIN checkout when `root` itself names a
    LINKED git worktree's own checkout (#604) — see
    `hostapi.git_worktree_main_root`'s docstring.

    `root` (this file's own `project_root()`-derived parameter, D-2) already
    names the main checkout in the common case: the harness sets
    `CLAUDE_PROJECT_DIR` once at session start, before a session's cwd ever
    moves into a linked worktree, so this is a no-op for the reported bug's
    own scenario. It matters only when THIS hook process ALSO ran without
    `CLAUDE_PROJECT_DIR` set (uncommon for a registered hook subprocess, but
    possible) — without this, that edge case would have the guard read from
    the worktree while `security-pass.py`'s `marker_root()` (hostapi.py)
    writes to the main checkout, reopening the exact split this closes."""
    return git_worktree_main_root(root) or root


def _check_h09b_h10b_crypto_secret(commit, add, cwd, root):
    """H-09b / H-10b: BLOCK a commit that introduces crypto/secret changes without
    a recorded security-gate pass. The crypto-compliance / secret-handling skills
    record the pass via hooks/security-pass.py — a marker holding the digest of
    every sensitive line the gate approved. Two checks, both required:
    freshness (< 30 min) AND coverage (every sensitive line being committed is
    in the approved set). Coverage is what closes the TOCTOU window: a pass
    minted for one diff can no longer launder a different diff committed inside
    the freshness window. Scans the staged diff, plus the worktree diff when
    the commit uses -a/--all or the same command stages files."""
    if not commit:
        return
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
        marker = os.path.join(_marker_root(root), ".codearbiter", ".markers", "security-gate-passed")
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


def _check_h14_migration(commit, add, cwd, root):
    """H-14: BLOCK a commit that stages a database migration without a recorded
    migration-review pass. commit-gate (and /review, /pr, /checkpoint, sprint)
    dispatch migration-reviewer and run hooks/migration-pass.py on PASS — a
    marker holding the content digest of every migration file the reviewer
    approved. Coverage is by content digest, no freshness window: an immutable
    migration stays approved while unchanged, and any edit changes the digest
    -> uncovered -> BLOCK (closes the TOCTOU window and enforces migration
    immutability at commit time). This closes the narrow #77 gap — a migration
    committed via bare /commit or the /feature small lane, where no lane
    dispatched the reviewer and no hook fired. A missing/unreadable marker is
    treated as no coverage (fail-closed), consistent with this layer's
    "ambiguity resolves CLOSED" stance."""
    if not commit:
        return
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
        marker = os.path.join(_marker_root(root), ".codearbiter", ".markers", "migration-gate-passed")
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


def run_guards(payload, root, ti):
    """Run every H-NN gate against `ti` (the already host-normalized Bash/
    PowerShell tool_input — see pre-bash.py's `_run`, which resolves it via
    `get_host().normalize_tool_input(...)` before calling here) and `payload`
    (the raw hook JSON dict, needed for `_effective_exec_root`'s worktree
    climb). block()-ing (stderr + exit 2) on the first violation found, else
    sys.exit(0). This is the composed body pre-bash.py's `_run` used to run
    inline (issue #320) — moved here verbatim, split into one function per
    gate, each still carrying its H-NN ID."""
    cmd = ti.get("command", "") or ""

    # Heredoc bodies are stdin text, not arguments — match the git command over
    # a body-stripped view so message content (which may contain `;`/`|`/`&`,
    # or mention `git -C`) never truncates the args capture, poisons the cwd
    # extraction, or leaks words into the pathspec parse. The RAW command stays
    # as a fallback matcher, but ONLY when the heredoc's consumer is a shell
    # (D-3, #223, `_heredoc_fed_to_shell` above): a heredoc fed TO a shell
    # (`bash <<EOF … EOF`) genuinely executes its body, so a commit/push/add
    # visible only in the raw text must still be guarded there — ambiguity
    # resolves CLOSED. A heredoc fed to a non-shell consumer (`gh`, `cat`, …)
    # is inert prose and must NOT fall back to the raw-text scan, or a PR/issue
    # body merely QUOTING "git commit" false-trips H-01/H-09b/H-14.
    git_view = _strip_heredoc_bodies(cmd) if "<<" in cmd else cmd
    # Both legs are OR'd: the heredoc's direct consumer being a shell
    # (`bash <<EOF`) is one route to execution; a shell/interpreter executor
    # appearing ANYWHERE in the command (`bash -c "$(cat <<EOF … EOF)"`,
    # `eval "$(cat <<EOF … EOF)"`) is another that the direct-consumer check
    # alone cannot see (security-reviewer finding, post-A-4) — either is
    # sufficient to keep the fallback closed.
    heredoc_shell_fallback = "<<" in cmd and (
        _heredoc_fed_to_shell(cmd) or _has_shell_executor(cmd))

    commit = COMMIT_RE.search(git_view) or (
        heredoc_shell_fallback and COMMIT_RE.search(cmd))
    push_probe = PUSH_RE.search(git_view) or (
        heredoc_shell_fallback and PUSH_RE.search(cmd))

    # #223: -C-less git commands run against the command's EFFECTIVE cwd, not
    # unconditionally CLAUDE_PROJECT_DIR — see _effective_exec_root's
    # docstring (D-2: gate MARKERS stay pinned to `root` regardless; only
    # branch/diff resolution follows the command's real cwd).
    exec_root = _effective_exec_root(payload, root)
    cwd = git_cwd(git_view, exec_root)

    # reliability-004 (#190): fail CLOSED for commit/push when the `-C` target
    # git_cwd() resolved does not exist as a directory — an unresolvable -C
    # target must not silently fall through to scanning some OTHER directory
    # (or crash mid-scan); ambiguity resolves CLOSED here exactly as the
    # git-read failures elsewhere in this file do.
    if (commit or push_probe) and not os.path.isdir(cwd):
        block("H-01", f"'git -C {cwd}' does not resolve to an existing directory — "
                      f"failing closed (ORCHESTRATOR §2). Verify the -C target exists "
                      f"before committing/pushing.")

    _check_h20_commit_no_verify(commit)
    _check_h01_commit_protected_branch(commit, cwd)

    push = PUSH_RE.search(git_view) or (
        heredoc_shell_fallback and PUSH_RE.search(cmd))
    _check_push_gates(push, cwd)

    add = ADD_RE.search(git_view) or (
        heredoc_shell_fallback and ADD_RE.search(cmd))
    _check_h03_wildcard_add(add, cwd)
    _check_h05_audit_log(cmd)
    _check_h11_decisions(cmd)
    _check_h18_context_md(cmd)
    _check_h19_gate_marker(git_view, cmd, heredoc_shell_fallback)
    _check_h22_state(cmd, root)
    _check_h09b_h10b_crypto_secret(commit, add, cwd, root)
    _check_h14_migration(commit, add, cwd, root)

    sys.exit(0)
