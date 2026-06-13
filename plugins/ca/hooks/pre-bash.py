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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, arbiter_active, block, line_digest, marker_fresh,
    project_root, read_input, tool_input, utf8_stdio,
)

# `git` followed by any run of global options (-C <dir>, -c k=v, --git-dir=…,
# --no-pager, …) before the subcommand — `git -C ../x commit` must not slip
# past a bare `git\s+commit` match.
GIT = r"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?|-\w+))*"
COMMIT_RE = re.compile(GIT + r"\s+commit\b(?P<args>[^|;&]*)")
PUSH_RE = re.compile(GIT + r"\s+push\b(?P<args>[^|;&]*)")
ADD_RE = re.compile(GIT + r"\s+add\b(?P<args>[^|;&]*)")
GIT_C_DIR_RE = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
# Force-push in any spelling: --force, --force-with-lease[=…], -f as its own
# token (not a ref like `fix-f`), or a forcing `+refspec`.
FORCE_RE = re.compile(r"(?:^|\s)(?:--force(?:-with-lease|-if-includes)?(?:=\S+)?|-f)(?=\s|$)")
FORCE_REFSPEC_RE = re.compile(r"\s\+[\w./:~^-]+")
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
# N-3: Known limitations — this regex catches the common `> file` truncation
# form but NOT every shell spelling that produces a new file descriptor on the
# log. Specific gaps: triple-chevron (`>>>`, treated as append by some shells),
# and file-descriptor forms like `exec 3>.codearbiter/overrides.log`. These are
# difficult to close with a single regex and represent an accepted residual risk.
# The sanctioned bypass for legitimate log management is /ca:override.
LOG_TRUNC_RE = re.compile(r"(?<!>)>(?!>)\s*\S*(?:overrides|triage)\.log")
LOG_DESTROY_RE = re.compile(
    r"\b(rm|del|mv|cp|copy|dd|tee|sed|truncate|sponge"
    r"|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content|Out-File)\b"
    r"[^|;&]*(?:overrides|triage)\.log", re.I,
)
# H-11's shell flank: ADRs are authored only via /adr (pre-write/pre-edit
# guard the Write/Edit tools; this guards redirection and file verbs). Any
# redirect into .codearbiter/decisions/, or any write/delete verb naming it,
# blocks — `cat`/`ls`/`grep` reads pass untouched.
DECISIONS = r"\.codearbiter[\\/]+decisions\b"
DECISIONS_REDIRECT_RE = re.compile(r">>?\s*\S*" + DECISIONS, re.I)
DECISIONS_WRITE_RE = re.compile(
    r"\b(rm|del|mv|cp|copy|dd|tee|sed|touch|truncate|ni"
    r"|New-Item|Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content"
    r"|Out-File|Add-Content)\b[^|;&]*" + DECISIONS, re.I,
)


def git_cwd(cmd, root):
    """The directory a `git -C <dir>` invocation actually targets."""
    m = GIT_C_DIR_RE.search(cmd)
    if not m:
        return root
    return m.group(1).strip("\"'")


def current_branch(cwd):
    try:
        out = subprocess.run(
            ["git", "branch", "--show-current"], cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def added_lines(cwd, ref):
    """The added (`+`) lines of a diff — what a commit would introduce.
    Decoded as UTF-8 with replacement: `text=True` alone uses the locale code
    page (cp1252 on stock Windows), where a non-cp1252 byte in the diff raised
    UnicodeDecodeError into the bare except below and the security gate
    silently failed OPEN on exactly the platform this layer protects."""
    try:
        out = subprocess.run(
            ["git", "diff", ref], cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if out.returncode != 0:
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(
        line[1:] for line in out.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


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


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    cmd = tool_input(read_input()).get("command", "") or ""

    commit = COMMIT_RE.search(cmd)
    cwd = git_cwd(cmd, root)

    # H-01: no commit directly to main/master
    if commit:
        branch = current_branch(cwd)
        if branch in ("main", "master"):
            block("H-01", f"Direct commit to {branch} is prohibited (ORCHESTRATOR §3). "
                          f"Create a feature branch.")

    push = PUSH_RE.search(cmd)
    if push:
        pargs = push.group("args")

        # H-02: no force-push — any spelling, including --force-with-lease and +refspec
        if FORCE_RE.search(pargs) or FORCE_REFSPEC_RE.search(pargs):
            block("H-02", "Force-push is prohibited (ORCHESTRATOR §3).")

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
        # Bare `git push` (no refspec) publishes the current branch.
        if len(toks) < 2 and current_branch(cwd) in ("main", "master"):
            block("H-01", "Bare `git push` from main/master publishes the protected "
                          "branch (ORCHESTRATOR §3) — main moves only via a merged PR.")

    # H-03: no wildcard git staging — stage explicitly (commit-gate). Both the
    # flag spellings (-A/--all/-u/.) and the argument spellings (globs,
    # directories, pathspec magic) — `git add src/` stages everything beneath
    # src/ just as surely as `git add -A` does.
    add = ADD_RE.search(cmd)
    if add:
        if WILDCARD_ADD_RE.search(add.group("args")):
            block("H-03", "'git add -A' / 'git add .' / 'git add --all' / 'git add -u' "
                          "are prohibited. Stage files explicitly (commit-gate skill).")
        why = add_violation(add.group("args"), cwd)
        if why:
            block("H-03", f"Wildcard staging is prohibited — {why} stages a "
                          f"non-explicit file set. Stage files explicitly, one path "
                          f"per file (commit-gate skill).")

    # H-05: the audit trail is append-only — block truncation/removal of
    # overrides.log via shell verbs (Write/Edit are guarded separately).
    if ("overrides.log" in cmd or "triage.log" in cmd) and (
            LOG_TRUNC_RE.search(cmd) or LOG_DESTROY_RE.search(cmd)):
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log) are append-only "
                      "(ORCHESTRATOR §7). Truncating, overwriting, or deleting the audit trail "
                      "is prohibited; append with '>>' only.")

    # H-11: ADRs exist only via /adr — the Write/Edit tools are guarded by
    # pre-write/pre-edit, and this closes the shell flank (`echo > decisions/…`,
    # `touch`, `cp`, `rm`, `sed -i`, …). Reads are untouched.
    if DECISIONS_REDIRECT_RE.search(cmd) or DECISIONS_WRITE_RE.search(cmd):
        block("H-11", "ADR files under .codearbiter/decisions/ are authored only via "
                      "/adr and are immutable history (ORCHESTRATOR §6) — shell writes, "
                      "edits, and deletions there are prohibited.")

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
        added = added_lines(cwd, "--cached")
        if COMMIT_ALL_RE.search(commit.group("args")) or add:
            added += "\n" + added_lines(cwd, "HEAD")
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

    sys.exit(0)


if __name__ == "__main__":
    main()
