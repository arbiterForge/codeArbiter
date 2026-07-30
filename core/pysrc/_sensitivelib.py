#!/usr/bin/env python3
# codeArbiter - the H-09b/H-10b sensitive-line scan: crypto/TLS and secret
# detection, the pinned security diff argv, the path-aware diff walk, and the
# digests that bind a recorded gate pass to the exact lines it reviewed.
#
# Extracted from _hooklib (issue #321, architecture-002) as the first slice.
# Chosen first because it was the cleanest seam in the module, measured rather
# than guessed: the cluster referenced exactly ONE symbol from the rest of
# _hooklib (norm_path, now the _pathnorm floor), and NOTHING in the rest of
# _hooklib referenced the cluster. A one-way edge with no back-reference is
# what makes this safe to move without touching a single consumer.
#
# _hooklib re-exports every name below, so all 59 consuming files are
# unchanged and the pre-existing hook suites prove behavioural parity - which
# is the only proof that means anything for a refactor (the `refactor` skill's
# Phase 2 rule: parity comes from tests that did not move).
#
# WHY THESE BELONG TOGETHER: they are one concern with one failure mode. The
# regexes decide what counts as sensitive, the pinned argv decides what the
# diff even looks like, the walk decides which FILE a line belongs to, and the
# digests decide what a pass covered. #279 showed they fail as a unit: a
# greedy header parse in the walk un-exempted an unrelated file, and an
# unpinned prefix config silently re-opened it. Splitting them across modules
# would let one move without the others.

from __future__ import annotations

import hashlib
import re

from _pathnorm import norm_path


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
