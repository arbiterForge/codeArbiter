#!/usr/bin/env python3
# codeArbiter — provenance store for per-doc source evidence and drift detection.
#
# Captures the scout evidence that backs each derived `.codearbiter/` doc
# (tech-stack.md, coding-standards.md, security-controls.md, CONTEXT.md,
# code-map.md) as a per-doc JSON file at `.codearbiter/.provenance/<doc>.json`.
# When a tracked source file changes, drift detection (compute_drift) finds the
# gap; commit-gate auto-heals it (pillar 3 of context-drift-provenance spec).
#
# Design invariants (mirroring _taskboardlib.py / _metricslib.py):
#   - Stdlib only; no third-party imports ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O on import.
#   - Pure functions are fully testable with synthetic data (no real file
#     needed). write_provenance() and read_provenance() are the ONLY functions
#     that touch the filesystem.
#   - Never raise on malformed input — degrade gracefully (this runs on the
#     SessionStart linchpin path).
#   - Hashing uses git hash-object via an injectable runner (batch_hash);
#     raw byte sha256 is intentionally NOT used — git honors .gitattributes
#     EOL normalization so an LF<->CRLF flip (documented Edit hazard on
#     Windows) never false-flags as drift.
#
# Schema (per-doc provenance file, v1):
#   {
#     "schema": 1,
#     "doc": "tech-stack",
#     "created": "2026-06-26",
#     "interview_derived": false,
#     "entries": [
#       {
#         "path": "plugins/ca/tools/package.json",
#         "hash": "<git oid or null>",
#         "drift_trigger": true,
#         "claims": [
#           {
#             "lines": "12-40",
#             "claim": "Node 20 runtime declared in package.json",
#             "confidence": "strong"
#           }
#         ]
#       }
#     ]
#   }
#
# Files live at: .codearbiter/.provenance/<doc>.json
# JSON format: pretty-printed, sorted keys, trailing newline, utf-8, LF endings.
#
# Public API:
#   new_record(doc, *, interview_derived=False, entries=None, created=None)
#                                        -> dict   canonical record with schema=1
#   write_provenance(path, record)       -> None   pretty JSON; creates parent dirs
#   read_provenance(path)                -> dict | None  None on missing/corrupt
#   batch_hash(paths, runner)            -> dict[str, str]  one git hash-object --stdin-paths
#                                                            call; input-order-preserving; {}
#                                                            on empty paths or runner failure
#   classify_source(path)                -> bool   True iff path is drift_trigger
#                                                  (config/manifest/schema/security-entry);
#                                                  False for general source; never raises
#   compute_drift(provenance_map, current_hashes)
#                                        -> dict   {doc: [{"path":…,"kind":"changed"|"missing"}]}
#                                                  kind="changed": path present, hash diverged.
#                                                  kind="missing": path absent from current_hashes
#                                                  (source renamed/deleted — AC-05/T-06).
#                                                  Both kinds filtered to drift_trigger:true only
#                                                  (AC-09/T-05). Docs with no drift omitted (→ {}).
#   load_provenance_dir(provenance_dir)  -> dict   {doc: record}; {} on missing/corrupt dir
#   startup_drift_line(root, runner=None)
#                                        -> str    "" when clean (AC-06);
#                                                  "context drift: N stale source(s) across M doc(s) -- run /ca:context-check"
#                                                  when drift > 0 (AC-07). ASCII-only, exactly one line.
#   changed_scope(doc_provenance, drift) -> list[str]  drifted paths for this doc only (both
#                                                       changed+missing kinds), in drift order;
#                                                       [] when the doc has no drift entry or
#                                                       any input is malformed/None (never raises)
#   rebaseline(provenance, current_hashes) -> dict  new record with each drift_trigger
#                                                    entry's hash set to current_hashes[path];
#                                                    absent paths left as-is; never raises
#   heal_worklist(staged_paths, provenance, current_hashes) -> list[str]
#                                        commit-gate worklist: staged paths that are
#                                        drift_trigger:true with a diverged or absent
#                                        current hash; [] when no staged file is tracked
#                                        (cost guarantee — ordinary commits pay nothing, AC-13)
#   lint_code_map(text)                  -> list[str]  cap / multi-line violations
#   write_stub(path, doc, *, interview_derived=True, created=None) -> None
#                                        write greenfield stub: interview_derived=True, entries=[]

import datetime
import glob
import json
import os
import re
import subprocess

import _hooklib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# Maximum seconds allowed for a single git read call.  A hung git process must
# never stall the SessionStart linchpin hook indefinitely; timeout degrades to
# the existing except-Exception degrade paths (batch_hash → {}, startup_drift_line → "").
GIT_TIMEOUT = 5  # seconds; a git read must never stall SessionStart

# Tunable cap for code-map entry count.  50 enforces module/concern granularity
# (coarse index only); raise it only when a project legitimately has more top-level
# concerns than this.  The lint is the guard against the code map drifting into
# a full file index — never allow it to grow past this without deliberate review.
CODE_MAP_MAX_ENTRIES = 50

# Regex matching a column-0 entry bullet: starts with '- `' (dash, space, backtick).
# Concern '## heading' lines are NOT entries.  Captures the path between backticks.
_ENTRY_RE = re.compile(r"^- `([^`]+)`")

# ---------------------------------------------------------------------------
# classify_source constants
# ---------------------------------------------------------------------------

# Fixed filenames that are always drift_trigger — exact case match (no lowering).
# These are canonical ecosystem names that do not vary in capitalisation except
# for Cargo.toml / Gemfile / Gemfile.lock (capital-first by convention).
_DRIFT_FIXED_NAMES = frozenset({
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "Gemfile.lock",
})

# Path-pattern rules (applied to the separator-normalised path, case-insensitive):
#   • requirements*.txt  — basename wildcard for any requirements file
#   • .github/workflows/ — CI/pipeline yaml anywhere in the path
#   • *.prisma           — Prisma schema files
#   • *.sql              — SQL files (schema dumps, migrations)
#   • migrations/        — any path segment named "migrations"
#   • .env.example / .env.sample / .env.template — env templates
_DRIFT_PATH_RE = re.compile(
    r"""
    # requirements*.txt  (basename: starts with 'requirements', ends with '.txt')
    (?:^|/) requirements [^/]* \.txt $
    |
    # CI / pipeline yaml: under .github/workflows/
    (?:^|/) \.github/workflows/ [^/]+ \.ya?ml $
    |
    # Prisma schema files (any directory)
    [^/]+ \.prisma $
    |
    # SQL files (any directory)
    [^/]+ \.sql $
    |
    # Any path containing a 'migrations/' segment
    (?:^|/) migrations /
    |
    # Env templates: .env.example / .env.sample / .env.template
    (?:^|/) \.env\. (?:example|sample|template) $
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Tokeniser that splits a normalised path on separator characters AND camelCase
# transitions so security-entry keywords are matched as whole tokens, not as
# substrings.  Separator characters covered: / \ . _ -  (backslash is already
# normalised to / before classify_source calls split, but kept here for defence).
# camelCase boundary: (?<=[a-z])(?=[A-Z]) — e.g. "authMiddleware" → ["auth","Middleware"].
_SECURITY_TOKEN_SPLIT_RE = re.compile(r"[\\/._\-]|(?<=[a-z])(?=[A-Z])")

# Security-entry token keywords.  A path is a drift_trigger when any token in the
# tokenised, lowercased normalised path is an exact member of this set.
#   MATCH : auth.ts, src/middleware/cors.py, jwt.go, authMiddleware.ts, jwt_utils.py
#   NO-MATCH : author.py, AuthorCard.tsx, oauth.ts  (tokens are "author"/"Author"/"oauth")
_SECURITY_ENTRY_TOKENS = frozenset({"auth", "middleware", "jwt"})

# ---------------------------------------------------------------------------
# Constructor helper
# ---------------------------------------------------------------------------


def new_record(doc, *, interview_derived=False, entries=None, created=None):
    """Build a canonical provenance record dict with schema=SCHEMA_VERSION.

    `doc`              — short name of the derived doc, e.g. "tech-stack".
    `interview_derived`— True for greenfield stubs (no source files yet).
    `entries`          — list of entry dicts; defaults to [].
    `created`          — ISO date string; defaults to today (datetime.date).

    Never raises. Returns a new dict on every call; the caller owns it.
    """
    if created is None:
        created = datetime.date.today().isoformat()
    return {
        "schema": SCHEMA_VERSION,
        "doc": str(doc),
        "created": str(created),
        "interview_derived": bool(interview_derived),
        "entries": list(entries) if entries is not None else [],
    }


# ---------------------------------------------------------------------------
# Filesystem functions (the ONLY functions that touch the filesystem)
# ---------------------------------------------------------------------------


def write_provenance(path, record):
    """Write `record` as pretty JSON to `path`, atomically.

    Format: indent=2, sorted keys, ensure_ascii=False, trailing newline, utf-8,
    LF line endings (canonical EOL for this repo). Creates the parent directory
    if it does not exist. Routed through _hooklib.write_text_atomic (sibling
    temp file + os.replace) so a crash mid-write leaves the previous provenance
    record intact instead of a truncated/corrupt file (reliability-016).
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _hooklib.write_text_atomic(path, text, newline="\n")


def read_provenance(path):
    """Read provenance JSON from `path`; return the dict, or None if missing/corrupt.

    Never raises — mirrors read_board() in _taskboardlib.py. A missing file,
    a permission error, or malformed JSON all return None; the caller degrades
    gracefully.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Git hashing (injectable runner contract)
# ---------------------------------------------------------------------------


def _default_hash_runner(args, stdin_text):
    """Run `git <args>` feeding stdin_text on stdin; return stdout as str.

    Runner contract: runner(args, stdin_text) -> str

    Uses subprocess.run with capture_output=True, text=True, encoding="utf-8".
    Called only by batch_hash; never called at import time (zero side effects).
    """
    result = subprocess.run(
        ["git"] + list(args),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=GIT_TIMEOUT,
    )
    return result.stdout


def batch_hash(paths, runner=None):
    """Hash all paths in a single git hash-object --stdin-paths call.

    `paths`  — list of repo-relative file paths.
    `runner` — injectable; contract: runner(args, stdin_text) -> str.
               Default is _default_hash_runner (uses subprocess, offline-safe
               to inject a fake in tests).

    Issues exactly ONE runner call for any non-empty paths list.
    Returns {path: git_oid} preserving input order (insertion order = input
    order via dict(zip(paths, oids))).

    Degrade-not-fail: empty paths → {} with zero runner calls; a runner that
    raises or returns fewer oids than paths → {} (or safely-zippable subset);
    never raises.
    """
    if runner is None:
        runner = _default_hash_runner
    if not paths:
        return {}
    stdin_text = "\n".join(paths) + "\n"
    try:
        stdout = runner(["hash-object", "--stdin-paths"], stdin_text)
        oids = [line for line in stdout.splitlines() if line]
        return dict(zip(paths, oids))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Source classification (drift_trigger predicate)
# ---------------------------------------------------------------------------


def classify_source(path):
    """Return True iff path is a drift_trigger (config/manifest/schema/security-entry).

    drift_trigger: True  — low-churn, high-signal sources where derived-doc claims
                            live: package manifests, lockfiles, CI yaml, schema/
                            migration files, env templates, and auth/middleware/jwt
                            entry files.
    drift_trigger: False — general implementation source (ts, py, go, tsx, md, …)
                            that still feeds the code-map/audit but never rings the
                            drift alarm.

    Normalises path separators (backslash → forward slash) before matching, so a
    Windows path classifies identically to its POSIX equivalent.  Security-entry
    keywords (auth, middleware, jwt) are matched as whole tokens anywhere in the
    normalised path — the path is split on separators and camelCase transitions,
    then lowercased, so "author.py" and "AuthorCard.tsx" do NOT fire but
    "authMiddleware.ts" and "src/middleware/cors.py" do.  Extension matching is
    case-insensitive; fixed filenames (e.g. package.json, Cargo.toml) are exact.

    Never raises — a None or garbage path returns False.
    """
    if not path:
        return False
    try:
        norm = str(path).replace("\\", "/")
    except Exception:
        return False

    # Extract the basename (last path segment after normalization).
    basename = norm.rsplit("/", 1)[-1]

    # 1. Fixed filename exact match (case-sensitive, per spec).
    if basename in _DRIFT_FIXED_NAMES:
        return True

    # 2. Path-pattern rules (requirements*.txt, CI yaml, *.prisma, *.sql,
    #    migrations/, .env.*).
    if _DRIFT_PATH_RE.search(norm):
        return True

    # 3. Security-entry token match: any token in the full normalised path (split
    #    on separators + camelCase boundaries, then lowercased) must be an exact
    #    member of _SECURITY_ENTRY_TOKENS.  Whole-token matching prevents false
    #    positives from substrings such as "author" (contains "auth") or
    #    "AuthorCard" (camelCase token "Author", not "auth").  Matching the full
    #    path (not just the basename) catches path-segment entries like
    #    src/middleware/cors.py where "middleware" is a directory name.
    path_tokens = [t.lower() for t in _SECURITY_TOKEN_SPLIT_RE.split(norm) if t]
    if _SECURITY_ENTRY_TOKENS.intersection(path_tokens):
        return True

    return False


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def compute_drift(provenance_map, current_hashes):
    """Detect changed-hash and missing entries across all docs in provenance_map.

    provenance_map  — {doc_name: provenance_record} as returned by
                      new_record/read_provenance.  A None or malformed record
                      value is skipped without raising.
    current_hashes  — {path: git_oid} as returned by batch_hash.

    Returns {doc_name: [{"path": str, "kind": str}, ...]} containing only docs
    that have at least one diverged or missing entry.  A doc with no drift is
    OMITTED so that an empty result ({}) signals a fully clean state.

    Drift kinds:
      • "changed" — entry path IS present in current_hashes AND the stored
                    hash differs from current_hashes[path].
      • "missing" — entry path is ABSENT from current_hashes entirely
                    (the source file was renamed or deleted).

    Both kinds respect the drift_trigger filter (AC-09): only entries with
    drift_trigger == True are ever considered.  An absent or falsy
    drift_trigger is treated as False — the conservative default — so
    general architecture source captured for the code-map/audit never rings
    the drift alarm regardless of whether the path is present or absent.

    Never raises — malformed entries, None records, and unexpected structures
    are all skipped gracefully.
    """
    result = {}
    try:
        items = provenance_map.items()
    except Exception:
        return {}

    for doc_name, record in items:
        try:
            if record is None:
                continue
            entries = record.get("entries")
            if not entries:
                continue
            doc_drifts = []
            for entry in entries:
                try:
                    # AC-09: only explicit True fires drift; absent/falsy → skip.
                    if entry.get("drift_trigger") is not True:
                        continue
                    path = entry.get("path")
                    stored_hash = entry.get("hash")
                    if path is None:
                        continue
                    if path not in current_hashes:
                        # AC-05 (T-06): drift_trigger:true entry absent from
                        # current_hashes means the source was renamed/deleted.
                        doc_drifts.append({"path": path, "kind": "missing"})
                        continue
                    current_hash = current_hashes[path]
                    if current_hash != stored_hash:
                        doc_drifts.append({"path": path, "kind": "changed"})
                except Exception:
                    continue
            if doc_drifts:
                result[doc_name] = doc_drifts
        except Exception:
            continue

    return result


# ---------------------------------------------------------------------------
# Per-doc drift scope (commit-gate auto-heal / /ca:context-check locality)
# ---------------------------------------------------------------------------


def changed_scope(doc_provenance, drift):
    """Return drifted paths for this doc only — never another doc's paths (AC-11).

    doc_provenance — a single doc's provenance record (must have a 'doc' field).
    drift          — the full compute_drift output {doc_name: [{"path","kind"}, ...]}.

    Returns the list of path strings drifted for doc_provenance["doc"] in the
    order they appear under that doc in drift. Both "changed" and "missing" kinds
    are included. If the doc has no drift entry, returns []. If doc_provenance is
    malformed/None, or drift is malformed, returns [] without raising.
    """
    try:
        doc_name = doc_provenance.get("doc")
        if not doc_name:
            return []
        doc_drifts = drift.get(doc_name)
        if not doc_drifts:
            return []
        result = []
        for entry in doc_drifts:
            try:
                result.append(entry["path"])
            except Exception:
                continue
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Re-baseline (commit-gate auto-heal — "claim still holds" branch, AC-12)
# ---------------------------------------------------------------------------


def rebaseline(provenance, current_hashes):
    """Return a new record with each entry's hash updated to current_hashes[path].

    Functional style: returns a new dict (shallow copy of the record; each
    entry dict is also a new dict) so the caller's original is never mutated.
    Only the 'hash' field of matching entries changes — 'claims', 'drift_trigger',
    'path', and all top-level record fields ('doc', 'schema', 'created',
    'interview_derived') are left untouched.

    For entries whose path is absent from current_hashes the stored hash is kept
    unchanged — a genuinely-deleted file is a separate decision, not a silent
    re-baseline.

    Never raises — None or malformed input returns the input unchanged.
    """
    try:
        if provenance is None:
            return provenance
        # Shallow-copy the top-level record so we return a new object.
        result = dict(provenance)
        entries = provenance.get("entries")
        if not isinstance(entries, list):
            return result
        # Build a safe hash lookup; degrade to empty dict on None/malformed.
        try:
            hashes = dict(current_hashes) if current_hashes is not None else {}
        except Exception:
            hashes = {}
        new_entries = []
        for entry in entries:
            try:
                new_entry = dict(entry)
                path = new_entry.get("path")
                if path is not None and path in hashes:
                    new_entry["hash"] = hashes[path]
                new_entries.append(new_entry)
            except Exception:
                # Malformed entry: append as-is without crashing.
                new_entries.append(entry)
        result["entries"] = new_entries
        return result
    except Exception:
        return provenance


# ---------------------------------------------------------------------------
# Commit-gate auto-heal selector (AC-13)
# ---------------------------------------------------------------------------


def heal_worklist(staged_paths, provenance, current_hashes):
    """Return staged paths that are drift_trigger:true entries with diverged/absent hashes.

    staged_paths   — list of repo-relative paths staged for this commit.
    provenance     — {doc_name: record} map (same shape as compute_drift uses).
    current_hashes — {path: git_oid} for the staged paths.

    Returns the subset of staged_paths that are BOTH:
      (a) present as a drift_trigger:true entry in some doc's provenance, AND
      (b) diverged — current_hashes.get(path) differs from the stored hash,
          OR path is absent from current_hashes (staged deletion/rename).

    A staged path that is not a provenance entry, or is drift_trigger:false, or
    whose hash matches → excluded. Preserves staged_paths order; deduplicates.
    Empty staged_paths, or no staged file tracked → [] (cost guarantee: ordinary
    commits touching no provenance source do zero re-scout work, AC-13).

    Never raises — malformed map/None → [].
    """
    try:
        if not staged_paths:
            return []

        # Build {path: stored_hash} for every drift_trigger:true entry across all docs.
        # First occurrence wins for a path that appears in multiple docs.
        drift_trigger_map = {}
        try:
            items = provenance.items()
        except Exception:
            return []

        for _doc_name, record in items:
            try:
                if record is None:
                    continue
                entries = record.get("entries")
                if not entries:
                    continue
                for entry in entries:
                    try:
                        if entry.get("drift_trigger") is not True:
                            continue
                        path = entry.get("path")
                        if path is None:
                            continue
                        if path not in drift_trigger_map:
                            drift_trigger_map[path] = entry.get("hash")
                    except Exception:
                        continue
            except Exception:
                continue

        # Build a safe hash lookup; degrade to {} on None/malformed.
        try:
            hashes = dict(current_hashes) if current_hashes is not None else {}
        except Exception:
            hashes = {}

        # Filter staged_paths: include only drift_trigger:true paths that diverged.
        # Preserve order; deduplicate via a seen-set.
        seen = set()
        result = []
        for path in staged_paths:
            try:
                if path in seen:
                    continue
                seen.add(path)
                if path not in drift_trigger_map:
                    continue
                stored_hash = drift_trigger_map[path]
                # Include when absent from current_hashes (staged deletion/rename)
                # OR when the hash has diverged.
                if path not in hashes or hashes[path] != stored_hash:
                    result.append(path)
            except Exception:
                continue

        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Provenance directory loader + SessionStart drift line
# ---------------------------------------------------------------------------


def load_provenance_dir(provenance_dir):
    """Load all provenance records from provenance_dir into {doc: record}.

    Globs <provenance_dir>/*.json, calls read_provenance on each file, and
    skips any that return None (missing, unreadable, or corrupt JSON). Each
    surviving record is keyed by its 'doc' field; if 'doc' is absent or
    empty, falls back to the filename stem so the dict never loses an entry.
    A missing or non-directory provenance_dir returns {}.

    Never raises — filesystem errors and malformed records are silently skipped
    (this runs on the SessionStart linchpin path).
    """
    result = {}
    try:
        if not os.path.isdir(provenance_dir):
            return {}
        pattern = os.path.join(provenance_dir, "*.json")
        for fpath in glob.glob(pattern):
            record = read_provenance(fpath)
            if record is None:
                continue
            doc = record.get("doc") or os.path.splitext(os.path.basename(fpath))[0]
            result[str(doc)] = record
    except Exception:
        pass
    return result


def _make_root_runner(root):
    """Return a batch_hash-compatible runner bound to root via git -C.

    The default runner used by startup_drift_line resolves repo-relative
    paths from <root> rather than the process cwd.  T-16 injects its own
    runner; tests inject a fake to avoid real git calls.
    """
    def runner(args, stdin_text):
        result = subprocess.run(
            ["git", "-C", root] + list(args),
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT,
        )
        return result.stdout
    return runner


def startup_drift_line(root, runner=None, cmd_ref=None):
    """Return a one-line drift summary for SessionStart, or '' when clean (AC-06).

    Pipeline:
      1. Load all provenance records from <root>/.codearbiter/.provenance/.
      2. If the map is empty, return '' immediately (nothing to check).
      3. Collect the set of paths that have drift_trigger:true across all docs.
      4. Split into existing paths (os.path.exists(<root>/<path>)) and missing
         ones.  Hash only the existing ones via batch_hash — git hash-object
         errors on non-existent paths and would corrupt the batch.  Absent paths
         stay absent from current_hashes so compute_drift reports them as
         kind='missing' (a deleted drift_trigger source IS drift).
      4a. AC-08 degrade-to-silence on hash failure: if batch_hash returned
          fewer hashes than existing_paths (runner raised, git is unavailable,
          or git aborted mid-stream producing a partial stdout), the tooling
          has failed — not the source files.  Return '' rather than feeding
          a short hash map to compute_drift, which would falsely flag the
          un-hashed existing files as 'missing'.  A path that genuinely does
          not exist on disk is still reported as missing (it is not in
          existing_paths so the count comparison is unaffected).
      5. Call compute_drift(pm, current_hashes).
      6. Empty result → return '' (AC-06: silent when docs are fresh).
         Non-empty → return exactly one ASCII line (AC-07):
         "context drift: N stale source(s) across M doc(s) -- run /ca:context-check"
         where N = sum of all drifted entry paths and M = number of affected docs.

    runner: injectable; contract: runner(args, stdin_text) -> str.
    The default runner uses 'git -C root hash-object --stdin-paths' so
    provenance paths are resolved from root.  T-16 injects its own root-bound
    runner; tests inject a fake.

    Never raises — all errors degrade to '' (safe for the SessionStart path).
    """
    try:
        if runner is None:
            runner = _make_root_runner(root)
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        pm = load_provenance_dir(provenance_dir)
        if not pm:
            return ""

        # Collect drift_trigger:true paths across all docs (deduped, order-stable)
        drift_trigger_paths = []
        seen = set()
        for record in pm.values():
            try:
                entries = record.get("entries") or []
                for entry in entries:
                    try:
                        if entry.get("drift_trigger") is not True:
                            continue
                        path = entry.get("path")
                        if path and path not in seen:
                            drift_trigger_paths.append(path)
                            seen.add(path)
                    except Exception:
                        continue
            except Exception:
                continue

        # Existence-aware hashing: only hash files that exist on disk.
        # Non-existent paths are intentionally absent from current_hashes so
        # compute_drift reports them as kind='missing' (deleted source = drift).
        existing_paths = [
            p for p in drift_trigger_paths
            if os.path.exists(os.path.join(root, p))
        ]
        current_hashes = batch_hash(existing_paths, runner) if existing_paths else {}

        # AC-08: degrade-to-silence if the hash step did not return a hash for
        # every existing drift_trigger path (git unavailable, runner raised, or a
        # partial/aborted stdout). Feeding a short hash map to compute_drift would
        # falsely report the un-hashed files as 'missing'. Conservative: stay silent.
        if len(current_hashes) < len(existing_paths):
            return ""

        drift = compute_drift(pm, current_hashes)
        if not drift:
            return ""
        # AC-07: one ASCII line: stale-source count, affected-doc count, pointer.
        stale_count = sum(len(v) for v in drift.values())
        doc_count = len(drift)
        ref = cmd_ref("context-check") if cmd_ref else "/ca:context-check"
        return (
            "context drift: {} stale source(s) across {} doc(s)"
            " -- run {}".format(stale_count, doc_count, ref)
        )
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Code-map linter (AC-15)
# ---------------------------------------------------------------------------


def lint_code_map(text):
    """Lint a code-map.md string for entry-cap and multi-line-role violations.

    Code-map format: markdown where entries are column-0 '- `path` -- role'
    bullets.  Concern '## <name>' headings are structural labels, NOT entries.

    Checks applied:
      1. Entry count > CODE_MAP_MAX_ENTRIES  ->  one warning naming count and cap.
         The cap enforces module/concern granularity: the code map must stay a
         coarse index, never a full file listing.
      2. For each entry whose immediately-following physical line starts with
         whitespace (an indented continuation — the role spilled onto a second
         line)  ->  one warning per offending entry, naming the entry number and
         path.  Column-0 '- ' bullets and '## ' headings do NOT start with
         whitespace so are excluded automatically.

    Returns a list of human-readable ASCII warning strings; [] means clean.
    Empty or None text -> [] (a missing/empty code map has no violations).
    Never raises.
    """
    if not text:
        return []
    try:
        lines = text.splitlines()
        entry_paths = []       # ordered list of extracted paths (one per entry)
        multi_warnings = []    # per-entry multi-line-role warnings (built inline)

        for i, line in enumerate(lines):
            m = _ENTRY_RE.match(line)
            if not m:
                continue
            entry_path = m.group(1)
            entry_num = len(entry_paths) + 1   # 1-indexed
            entry_paths.append(entry_path)

            # Multi-line role: the next physical line starts with whitespace AND
            # contains non-whitespace content (a genuine continuation, not blank
            # vertical spacing).  Column-0 bullets ('- ') and headings ('## ')
            # do not start with whitespace and are excluded by this check.
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.strip() and next_line[0:1] in (" ", "\t"):
                    multi_warnings.append(
                        "multi-line role at entry {} (path {}) -- roles must be one line".format(
                            entry_num, entry_path
                        )
                    )

        result = []
        count = len(entry_paths)
        if count > CODE_MAP_MAX_ENTRIES:
            result.append(
                "code map has {} entries (cap {}) -- coarsen to module/concern granularity".format(
                    count, CODE_MAP_MAX_ENTRIES
                )
            )
        result.extend(multi_warnings)
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Greenfield stub writer (AC-18)
# ---------------------------------------------------------------------------


def write_stub(path, doc, *, interview_derived=True, created=None):
    """Write a greenfield provenance stub to `path` for `doc`.

    The stub record is new_record(doc, interview_derived=interview_derived,
    entries=[], created=created), written via write_provenance (which creates
    parent directories, pretty-prints JSON with LF endings, and does not raise
    beyond documented I/O errors).  interview_derived defaults to True — stubs
    are for greenfield docs where no source files exist yet.  created passes
    through to new_record; None means today (datetime.date.today()).

    Reuses new_record + write_provenance — contains no duplicated JSON logic.
    Never raises beyond what write_provenance already does.
    """
    record = new_record(doc, interview_derived=interview_derived, entries=[], created=created)
    write_provenance(path, record)
