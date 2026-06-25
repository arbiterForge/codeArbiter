#!/usr/bin/env python3
# codeArbiter — shared hook helpers (issues #24, #25).
#
# Replaces the bash+jq hook layer with a cross-platform, fail-LOUD Python
# implementation. The bash hooks began with `which jq > /dev/null || exit 0`,
# so on any machine without jq (e.g. a stock Windows install) EVERY safety gate
# silently evaporated with no signal — the plugin appeared installed but was
# inert. Python is already a plugin dependency (statusline, scaffolder), needs
# no jq, and lets a hook fail loud instead of fail open.
#
# Blocking contract: a PreToolUse hook BLOCKS the tool call by exiting 2 (its
# stderr is fed back to Claude). Exit 0 allows. The prior bash hooks used
# exit 1 — a NON-blocking error under Claude Code's hook contract — so their
# "BLOCKED" gates may not have been stopping the tool at all; this port closes
# that latent gap.
#
# Interpreter launch: hooks.json registers every hook TWICE — `python3 <script>`
# plus a fallback `python3 -c "" || python <script>`. Stock Windows often has no
# real python3 (the Microsoft Store stub exits 9009), which would make every
# gate fail OPEN; the fallback entry probes for python3 and runs `python` only
# when it is absent. A single `python3 x || python x` entry would be wrong: when
# python3 exists and the script BLOCKS (exit 2), `||` would re-run it against a
# drained stdin and the rerun's exit 0 would swallow the block. Separate hook
# entries each receive their own stdin, so the block survives.
#
# Public API:
#   utf8_stdio() -> None                 force UTF-8 on stdout/stderr
#   norm_path(p) -> str                  normalize path separators to forward-slash
#   frontmatter_enabled(ctx_path) -> tuple[bool, bool]   (enabled, malformed)
#   arbiter_active(root) -> bool         True iff repo opted in via CONTEXT.md frontmatter
#   read_input() -> dict                 parse hook JSON from stdin; fail-open on error
#   tool_input(data) -> dict             extract tool_input sub-dict from hook payload
#   project_root() -> str                git repo root, or cwd as fallback
#   repo_rel(fpath, root) -> str         repo-relative POSIX path, or "" if outside root
#   line_digest(line) -> str             sha256 hex of one diff line (H-09b/H-10b gate)
#   content_digest(text) -> str          sha256 hex of a whole file's content (H-14 gate)
#   migration_globs(root) -> tuple[list, list]   (includes, excludes) for migration detection
#   scope_globs(root, defaults, decl_re) -> tuple[list, list]   generic glob scope resolver
#   path_in_globs(rel, root, defaults, decl_re) -> bool         True iff path matches scope
#   is_migration_path(rel, root) -> bool  True iff rel is a DB migration (H-14)
#   is_ci_path(rel, root) -> bool         True iff rel is a CI/CD workflow (H-15)
#   is_deploy_path(rel, root) -> bool     True iff rel is a deployment/IaC manifest (H-16)
#   marker_fresh(path, minutes) -> bool   True iff marker file exists and is recent
#   block(tag, msg) -> None              BLOCK tool call: print to stderr and exit 2
#   remind(tag, msg) -> None             non-blocking nudge to stderr
#   warn(msg) -> None                    loud degradation breadcrumb to stderr

import hashlib
import json
import os
import re
import subprocess
import sys
import time

# Crypto/TLS and secret patterns — shared by the post-write reminder (H-09/H-10)
# and the blocking pre-commit gate (H-09b/H-10b) so the two never drift.
# Deliberately NOT matched: crypto.randomUUID / crypto.getRandomValues (benign
# ID generation tripped the gate on routine commits) — the bare `crypto\.`
# catch-all is narrowed to the members that actually sign, encrypt, derive
# keys, or produce security-relevant randomness. bcrypt stays: approved or
# not, a password-hashing change is exactly what crypto-compliance reviews.
CRYPTO_RE = re.compile(
    r"(createHash|createCipher|createHmac|\bmd5\b|\bsha1\b|\brc4\b|\bdes\b|3des"
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
SECRET_RE = re.compile(
    r"\b(?:password|secret|token|api_key|apikey|private_key|passphrase|credential"
    r"|aws_secret_access_key|client_secret)"
    r"""["']?\s*[:=]\s*["'][^"']{4,}"""
    r"|AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{36}"
    r"|sk-ant-[A-Za-z0-9_-]{16,}",
    re.I,
)


ARBITER_RE = re.compile(r"^\s*arbiter:\s*enabled\s*$", re.I)


def utf8_stdio():
    """Force UTF-8 on stdout/stderr. Windows pipes default to the locale code
    page (cp1252), and ORCHESTRATOR.md contains non-cp1252 glyphs — without this
    the SessionStart injection dies with UnicodeEncodeError."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def norm_path(p):
    """Normalize separators so guard regexes match Windows backslash paths."""
    return (p or "").replace("\\", "/")


def frontmatter_enabled(ctx_path):
    """Return (enabled, malformed). `enabled` iff `arbiter: enabled` appears in a
    properly-closed leading YAML frontmatter block. `malformed` iff a block opens
    (`---` on line 1) but never closes — the fail-loud case. A file with no
    frontmatter at all is simply dormant (not malformed)."""
    try:
        with open(ctx_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        return (False, False)
    lines = text.split("\n")
    if not lines:
        return (False, False)
    first = lines[0].lstrip("﻿")  # tolerate a leading UTF-8 BOM
    if first.strip() != "---":
        return (False, False)  # no opening delimiter — dormant, not malformed
    found = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            return (found, False)  # closing delimiter — decision is final
        if ARBITER_RE.match(ln):
            found = True
    return (False, True)  # opened but never closed — malformed


def arbiter_active(root):
    """True iff this repo opted in (`arbiter: enabled` in CONTEXT.md frontmatter).
    Every enforcement hook gates on this so the plugin is genuinely dormant in
    repos that never opted in — the plugin.json activation contract."""
    enabled, _ = frontmatter_enabled(os.path.join(root, ".codearbiter", "CONTEXT.md"))
    return enabled


def read_input():
    """Parse the hook JSON from stdin.

    Deliberately fail-open on parse error: a malformed stdin input must NOT
    brick the session by blocking every subsequent tool call. This is an
    explicit, documented exception to the fail-loud principle — the correct
    behaviour here is warn + allow, not warn + block.
    """
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:  # noqa: BLE001 — any malformed input
        warn(f"hook input unparseable ({e}); proceeding without enforcement")
        return {}


def tool_input(data):
    return (data or {}).get("tool_input", {}) or {}


def project_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def repo_rel(fpath, root):
    """Repo-relative POSIX path for `fpath`, or "" when it lies outside `root`.

    realpath BOTH sides before relpath: `git rev-parse --show-toplevel`
    (project_root) canonicalizes symlinks and 8.3 short names, but the
    `file_path` in a hook payload may not — so on macOS (TMPDIR `/var` ->
    `/private/var`) and Windows (`RUNNER~1` -> `runneradmin`) the two name the
    same repo via divergent forms. A purely lexical relpath on those forms
    yields a bogus `..`-prefixed path, which silently suppressed every
    path-scoped reminder (#125 CI: H-12/H-15/H-16/H-13 dropped on macOS +
    Windows runners while ubuntu passed)."""
    if not fpath:
        return ""
    rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(root))
    rel = rel.replace(os.sep, "/")
    return "" if rel == ".." or rel.startswith("../") else rel


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


# Migration-path detection (H-14). Shared by migration-pass.py (the producer)
# and pre-bash.py (the backstop) so the two never drift on what counts as a
# migration. Default globs cover the common ORM/migration ecosystems; a project
# extends or narrows the set via a `migration-paths` block in
# security-controls.md. `**` matches any run of path segments (including none);
# `*`/`?` stay within one segment.
MIGRATION_DEFAULT_GLOBS = (
    "**/migrations/**",
    "**/migrate/**",
    "**/db/migrate/**",
    "**/alembic/versions/*.py",
    "**/prisma/migrations/**",
)
_MIG_DECL_RE = re.compile(
    r"<!--\s*migration-paths\s*-->(.*?)<!--\s*/migration-paths\s*-->", re.S | re.I)

# CI/CD workflow detection (H-15, #73). Advisory only — no commit gate; the
# defaults cover the common CI ecosystems and a project extends/narrows them via
# a `ci-paths` block in security-controls.md (same `+`/`-` grammar as migrations).
CI_DEFAULT_GLOBS = (
    ".github/workflows/**",
    ".circleci/**",
    "**/.gitlab-ci.yml",
    "**/Jenkinsfile",
    "**/azure-pipelines.yml",
    "**/bitbucket-pipelines.yml",
)
_CI_DECL_RE = re.compile(
    r"<!--\s*ci-paths\s*-->(.*?)<!--\s*/ci-paths\s*-->", re.S | re.I)

# Deployment / IaC detection (H-16, #73). Advisory only. Defaults cover the
# common container/orchestration/IaC manifests; extend/narrow via a
# `deploy-paths` block in security-controls.md.
DEPLOY_DEFAULT_GLOBS = (
    "**/Dockerfile",
    "**/Dockerfile.*",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/*.tf",
    "**/*.tfvars",
    "**/k8s/**",
    "**/helm/**",
    "**/kustomization.yaml",
    "**/kustomization.yml",
    "**/Procfile",
)
_DEPLOY_DECL_RE = re.compile(
    r"<!--\s*deploy-paths\s*-->(.*?)<!--\s*/deploy-paths\s*-->", re.S | re.I)


def _glob_to_re(glob):
    """Compile a forward-slash glob into a full-path regex. `**/` is an optional
    run of leading segments, `**` is any chars, `*`/`?` stay within a segment."""
    g = norm_path(glob)
    out, i = ["^"], 0
    while i < len(g):
        if g[i:i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif g[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        elif g[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


# performance-002: the DEFAULT glob tuples are module constants, so compile each
# to a regex ONCE at module load instead of per glob per path_in_globs() call.
# A single post-write-edit.py invocation otherwise recompiled up to 44 regexes
# (5 migration + 6 CI + 11 deploy x the calls that hit them). These compiled
# tuples line up 1:1 with their string tuples; the matcher uses them directly
# for the defaults and only compiles the per-controls custom globs on demand.
_MIGRATION_DEFAULT_RES = tuple(_glob_to_re(g) for g in MIGRATION_DEFAULT_GLOBS)
_CI_DEFAULT_RES = tuple(_glob_to_re(g) for g in CI_DEFAULT_GLOBS)
_DEPLOY_DEFAULT_RES = tuple(_glob_to_re(g) for g in DEPLOY_DEFAULT_GLOBS)

# Map each default string tuple to its precompiled regex tuple, so the matcher
# can look up the right precompiled set from the `defaults` argument alone
# (preserving the existing public signatures of scope_globs/path_in_globs).
_DEFAULT_RES_BY_GLOBS = {
    MIGRATION_DEFAULT_GLOBS: _MIGRATION_DEFAULT_RES,
    CI_DEFAULT_GLOBS: _CI_DEFAULT_RES,
    DEPLOY_DEFAULT_GLOBS: _DEPLOY_DEFAULT_RES,
}


# performance-001: hooks are EPHEMERAL single-shot processes (one invocation
# then exit), so a module-level cache lives for exactly one invocation — there
# is NO cross-invocation persistence. Within that one process, scope_globs reads
# security-controls.md on every is_migration_path/is_ci_path/is_deploy_path call
# (2-3 reads per hook). Cache the controls text keyed by (root, mtime) so a hit
# skips the read; the mtime key keeps it correct even on an intra-process change
# (the file is re-read when its mtime moves), and keys the absent-file state too.
_CONTROLS_CACHE = {}


def _controls_mtime(root):
    """mtime of `root`'s security-controls.md, or None when absent/unreadable.
    The cache key — distinct mtimes (and the None absent-state) bust the cache."""
    try:
        return os.path.getmtime(
            os.path.join(root, ".codearbiter", "security-controls.md"))
    except Exception:  # noqa: BLE001 — no controls file -> None (defaults only)
        return None


def _read_controls(root):
    """The repo's security-controls.md text, or "" when absent/unreadable.

    Process-cached keyed by (root, mtime): a cache hit skips the file read, and
    the mtime component invalidates the entry whenever the file changes (or is
    created/removed), so verdicts are unchanged. Single-shot hook process only —
    no cross-invocation persistence."""
    mtime = _controls_mtime(root)
    key = (root, mtime)
    cached = _CONTROLS_CACHE.get(key)
    if cached is not None:
        return cached[0]
    try:
        with open(os.path.join(root, ".codearbiter", "security-controls.md"),
                  encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001 — no controls file -> defaults only
        text = ""
    # Cache the text AND the compiled custom globs per scope (filled lazily by
    # scope_globs) under the same mtime key, so a custom-glob set compiles at
    # most once per (root, mtime) instead of once per path_in_globs() call.
    _CONTROLS_CACHE[key] = (text, {})
    return text


def _custom_re_cache(root):
    """The per-(root, mtime) dict that caches compiled custom-glob regexes for
    this controls revision. Populated lazily by scope_globs. Returns a throwaway
    dict only if the controls entry is somehow missing (defensive; the read
    above always seeds it first)."""
    entry = _CONTROLS_CACHE.get((root, _controls_mtime(root)))
    return entry[1] if entry is not None else {}


def scope_globs(root, defaults, decl_re):
    """(includes, excludes) for one scope category: the built-in `defaults` plus
    any declaration block matched by `decl_re` in security-controls.md
    (`+ glob` extends, `- glob` excludes). Shared by every path-glob scope
    detector (migration/CI/deploy) so they never drift on the grammar."""
    includes, excludes = list(defaults), []
    m = decl_re.search(_read_controls(root))
    if not m:
        return includes, excludes
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if ln.startswith("+ "):
            includes.append(ln[2:].strip())
        elif ln.startswith("- "):
            excludes.append(ln[2:].strip())
    return includes, excludes


def _scope_res(root, defaults, decl_re):
    """(include_res, exclude_res) as compiled regexes for one scope category.
    Default globs use the module-precompiled regexes (zero per-call compilation);
    any per-controls custom globs are compiled at most once per (root, mtime) and
    cached. Equivalent to compiling each string from scope_globs() — verdicts are
    identical; only the regex work is amortised."""
    includes, excludes = scope_globs(root, defaults, decl_re)
    default_res = _DEFAULT_RES_BY_GLOBS.get(defaults)
    if default_res is None:
        # Unknown defaults set (no precompiled tuple) — compile everything.
        return ([_glob_to_re(g) for g in includes],
                [_glob_to_re(g) for g in excludes])
    # Defaults occupy the head of `includes` (scope_globs builds list(defaults)
    # then appends customs); reuse the precompiled regexes for that head and
    # compile only the trailing customs. Excludes are all custom.
    custom_cache = _custom_re_cache(root)

    def _compile(g):
        r = custom_cache.get(g)
        if r is None:
            r = _glob_to_re(g)
            custom_cache[g] = r
        return r

    n = len(defaults)
    include_res = list(default_res) + [_compile(g) for g in includes[n:]]
    exclude_res = [_compile(g) for g in excludes]
    return include_res, exclude_res


def path_in_globs(rel, root, defaults, decl_re):
    """True iff `rel` (a repo-relative path) matches an include glob and no
    exclude glob for the given scope category. Excludes win — the false-positive
    escape hatch. The one matcher behind is_migration_path/is_ci_path/
    is_deploy_path."""
    rel = norm_path(rel).lstrip("/")
    include_res, exclude_res = _scope_res(root, defaults, decl_re)
    if any(r.match(rel) for r in exclude_res):
        return False
    return any(r.match(rel) for r in include_res)


def migration_globs(root):
    """(includes, excludes) for migration detection: defaults plus any
    `migration-paths` declaration in security-controls.md."""
    return scope_globs(root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_migration_path(rel, root):
    """True iff `rel` is a database migration (H-14). Excludes win — the
    escape hatch for a project whose `migrations/` dir holds non-DB files."""
    return path_in_globs(rel, root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_ci_path(rel, root):
    """True iff `rel` is a CI/CD workflow file (H-15, advisory)."""
    return path_in_globs(rel, root, CI_DEFAULT_GLOBS, _CI_DECL_RE)


def is_deploy_path(rel, root):
    """True iff `rel` is a deployment / IaC manifest (H-16, advisory)."""
    return path_in_globs(rel, root, DEPLOY_DEFAULT_GLOBS, _DEPLOY_DECL_RE)


def marker_fresh(path, minutes):
    """True if the marker file exists and was touched within `minutes`."""
    try:
        return os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < minutes * 60
    except Exception:  # noqa: BLE001
        return False


def block(tag, msg):
    """BLOCK the tool call: stderr is surfaced to Claude, exit 2."""
    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)
    sys.exit(2)


def remind(tag, msg):
    """Non-blocking nudge to stderr."""
    print(f"REMINDER [{tag}]: {msg}", file=sys.stderr)


def warn(msg):
    """Loud degradation/diagnostic breadcrumb — never silent."""
    print(f"codeArbiter hook: {msg}", file=sys.stderr)
