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
#   - Pure comparisons are testable with synthetic data. The v1 reader/writer,
#     strict v2 store reader, and live T-008 snapshot probe are explicit I/O
#     boundaries.
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
# Schema v2 is a closed per-document record: canonical Markdown raw identity,
# stable field/claim IDs, raw-content and bounded-membership evidence methods,
# and separate stored semantic-review and owner references. Those references
# are inert; storage validation never grants approval or semantic authority.
#
# Files live at: .codearbiter/.provenance/<doc>.json
# JSON format: pretty-printed, sorted keys, trailing newline, utf-8, LF endings.
#
# Public API:
#   new_record(doc, *, interview_derived=False, entries=None, created=None)
#                                        -> dict   canonical record with schema=1
#   write_provenance(path, record)       -> None   pretty JSON; creates parent dirs
#   valid_provenance_record(record)      -> bool   v1 top-level or closed v2 shape
#   read_provenance(path)                -> dict | None  None on missing/corrupt
#                                                  — including valid JSON whose
#                                                  shape is not a known record
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
#   load_provenance_dir(provenance_dir, skipped=None)
#                                        -> dict   {doc: record}; {} on missing/corrupt dir.
#                                                  Per-FILE error boundary: one bad record
#                                                  never suppresses a later valid one.
#                                                  `skipped` (optional list) collects up to
#                                                  MAX_SKIPPED_REPORTED rejected basenames.
#   startup_drift_line(root, runner=None, cmd_ref=None, unknown=None)
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
#   lint_code_map(text, root=None)       -> list[str]  bounded map/path diagnostics
#   write_stub(path, doc, *, interview_derived=True, created=None) -> None
#                                        write greenfield stub: interview_derived=True, entries=[]
#   assess_context_provenance(provenance_dir, expected_docs, snapshot, snapshot_probe=None)
#                                        -> dict   conservative v2 identity/coverage status;
#                                                  semantic authority always remains separate
#   startup_context_coverage_line(root, cmd_ref=None)
#                                        -> str    bounded record-coverage diagnostic;
#                                                  does not hash source or claim freshness

import datetime
import glob
import hashlib
import json
import ntpath
import os
import posixpath
import re
import subprocess

from _gitexec import git_executable

import _hooklib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
V2_SCHEMA_VERSION = 2
V2_CONTRACT = "provenance-v2/1"
# The store is shared by all three governance hosts. A v2 write needs an
# observation from the owning integration for every installed consumer.
V2_HOSTS = ("ca", "ca-codex", "ca-pi")
V2_DOCUMENTS = {
    "CONTEXT": ".codearbiter/CONTEXT.md",
    "tech-stack": ".codearbiter/tech-stack.md",
    "coding-standards": ".codearbiter/coding-standards.md",
    "security-controls": ".codearbiter/security-controls.md",
    "code-map": ".codearbiter/code-map.md",
}
# Match the native context writer's 8 MiB canonical input ceiling. The same
# ceiling bounds the entire startup scan, including unusable JSON bytes.
MAX_CONTEXT_RECORD_BYTES = 8 * 1024 * 1024
MAX_CONTEXT_STORE_BYTES = 8 * 1024 * 1024
MAX_CONTEXT_STORE_FILES = 256
_V2_ID_RE = re.compile(r"(?:FIELD|CLAIM)-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_V2_MEMBERSHIP_PREDICATES = frozenset({
    "manifests", "instructions", "configuration", "tests",
    "infrastructure", "security", "data",
})

# Maximum seconds allowed for a single git read call.  A hung git process must
# never stall the SessionStart linchpin hook indefinitely; timeout degrades to
# the existing except-Exception degrade paths (batch_hash → {}, startup_drift_line → "").
GIT_TIMEOUT = 5  # seconds; a git read must never stall SessionStart

# Tunable cap for code-map entry count.  50 enforces module/concern granularity
# (coarse index only); raise it only when a project legitimately has more top-level
# concerns than this.  The lint is the guard against the code map drifting into
# a full file index — never allow it to grow past this without deliberate review.
CODE_MAP_MAX_ENTRIES = 50

# Bound actual UTF-8 content, including a single oversized role or heading.
# This is an advisory lint budget, never permission to truncate human content.
CODE_MAP_MAX_BYTES = 20 * 1024

# Regex matching a column-0 entry bullet: starts with '- `' (dash, space, backtick).
# Concern '## heading' lines are NOT entries.  Captures the path between backticks.
_ENTRY_RE = re.compile(r"^- `([^`]+)`")
_CODE_MAP_ROLE_RE = re.compile(r"^- `[^`]+`\s+(?:--|—)\s+(.+)$")

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


def write_provenance(path, record, *, capability_probe=None, ownership_probe=None,
                     expected_previous_sha256=None):
    """Write `record` as pretty JSON to `path`, atomically.

    Format: indent=2, sorted keys, ensure_ascii=False, trailing newline, utf-8,
    LF line endings (canonical EOL for this repo). Creates the parent directory
    if it does not exist. Routed through _hooklib.write_text_atomic (sibling
    temp file + os.replace) so a crash mid-write leaves the previous provenance
    record intact instead of a truncated/corrupt file (reliability-016).
    """
    if isinstance(record, dict) and record.get("schema") == V2_SCHEMA_VERSION:
        if not valid_provenance_record(record):
            raise ValueError("INVALID_V2_RECORD")
        if os.path.basename(os.fspath(path)) != record["doc"] + ".json":
            raise ValueError("V2_WRONG_RECORD_PATH")
        # The probe is a trusted integration seam, not a record field or an
        # approval adapter. Current installed consumers supply no such probe,
        # so source-only deployments cannot enroll v2 accidentally.
        if not callable(capability_probe) or not callable(ownership_probe):
            raise ValueError("V2_CAPABILITY_UNAVAILABLE")
        try:
            capability = capability_probe(V2_CONTRACT, V2_HOSTS)
        except Exception:
            raise ValueError("V2_CAPABILITY_UNAVAILABLE") from None
        if not _v2_capability_supported(capability):
            raise ValueError("V2_CAPABILITY_UNAVAILABLE")
        text = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        candidate_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        field_ids = tuple(field["id"] for field in record["fields"])
        try:
            ownership = ownership_probe(candidate_digest, record["doc"], field_ids)
        except Exception:
            raise ValueError("V2_OWNERSHIP_UNVERIFIED") from None
        if (type(ownership) is not dict or set(ownership) != {
                "status", "record_digest", "doc", "field_ids"} or
                ownership["status"] != "accepted" or
                ownership["record_digest"] != candidate_digest or
                ownership["doc"] != record["doc"] or
                ownership["field_ids"] != list(field_ids)):
            raise ValueError("V2_OWNERSHIP_UNVERIFIED")
        if expected_previous_sha256 != "absent" and not _sha256(expected_previous_sha256):
            raise ValueError("V2_PREIMAGE_REQUIRED")
        try:
            with open(path, "rb") as prior_file:
                prior = prior_file.read()
        except FileNotFoundError:
            prior = None
        except OSError:
            raise ValueError("V2_PREIMAGE_UNKNOWN") from None
        if prior is None:
            if expected_previous_sha256 != "absent":
                raise ValueError("V2_PREIMAGE_CHANGED")
        else:
            if hashlib.sha256(prior).hexdigest() != expected_previous_sha256:
                raise ValueError("V2_PREIMAGE_CHANGED")
            existing = read_provenance(path)
            if existing is None or existing.get("doc") != record["doc"]:
                raise ValueError("V2_UNSUPPORTED_PREVIOUS_RECORD")
    else:
        # Legacy creation and supported v1 updates retain their contract.
        # An unreadable or unsupported existing record is not an absent slot;
        # preserve it for explicit reconciliation even through an older caller.
        existing = read_provenance(path)
        if existing is None and os.path.lexists(path):
            raise ValueError("UNSUPPORTED_PREVIOUS_RECORD")
        if existing is not None and existing.get("schema") == V2_SCHEMA_VERSION:
            raise ValueError("V2_DOWNGRADE_UNSUPPORTED")
        text = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _hooklib.write_text_atomic(path, text, newline="\n")


def _sha256(value):
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _v2_capability_supported(value):
    if type(value) is not dict or set(value) != {"contract", "producer", "consumers"}:
        return False
    if value["contract"] != V2_CONTRACT:
        return False
    producer = value["producer"]
    consumers = value["consumers"]
    if type(producer) is not dict or set(producer) != {"status", "contract"}:
        return False
    if producer != {"status": "supported", "contract": V2_CONTRACT}:
        return False
    if type(consumers) is not dict or set(consumers) != set(V2_HOSTS):
        return False
    return all(type(cell) is dict and cell == {
        "status": "supported", "contract": V2_CONTRACT}
        for cell in consumers.values())


def _v2_text(value):
    return (type(value) is str and 0 < len(value) <= 256 and
            not any(ord(char) < 32 or ord(char) == 127 for char in value))


def _v2_path(value, *, root=False):
    if not _v2_text(value):
        return False
    if root and value == ".":
        return True
    if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _valid_v2_evidence(evidence):
    if type(evidence) is not dict or evidence.get("kind") not in ("content", "membership"):
        return False
    if evidence["kind"] == "content":
        return (set(evidence) == {"kind", "path", "digest_method", "digest"} and
                _v2_path(evidence["path"]) and
                evidence["digest_method"] == "sha256-raw" and
                _sha256(evidence["digest"]))
    scopes = evidence.get("scope_paths")
    return (set(evidence) == {"kind", "predicate", "scope_paths", "digest_method", "digest"} and
            evidence["predicate"] in _V2_MEMBERSHIP_PREDICATES and
            type(scopes) is list and 0 < len(scopes) <= 32 and
            len(scopes) == len(set(scopes)) and
            all(_v2_path(scope, root=True) for scope in scopes) and
            evidence["digest_method"] == "sha256-membership-v1" and
            _sha256(evidence["digest"]))


def _valid_v2_record(record):
    """Closed storage shape; review labels and references are inert data."""
    if set(record) != {"schema", "doc", "created", "document", "fields"}:
        return False
    doc = record["doc"]
    if doc not in V2_DOCUMENTS or not _v2_text(record["created"]):
        return False
    document = record["document"]
    if (type(document) is not dict or
            set(document) != {"path", "digest_method", "digest"} or
            document["path"] != V2_DOCUMENTS[doc] or
            document["digest_method"] != "sha256-raw" or
            not _sha256(document["digest"])):
        return False
    fields = record["fields"]
    if type(fields) is not list or not 0 < len(fields) <= 128:
        return False
    ids = set()
    for field in fields:
        if type(field) is not dict or set(field) != {"id", "owner_ref", "claims"}:
            return False
        field_id = field["id"]
        if (type(field_id) is not str or not _V2_ID_RE.fullmatch(field_id) or
                not field_id.startswith("FIELD-") or field_id in ids or
                not _v2_text(field["owner_ref"])):
            return False
        ids.add(field_id)
        claims = field["claims"]
        if type(claims) is not list or not 0 < len(claims) <= 128:
            return False
        for claim in claims:
            if type(claim) is not dict or set(claim) != {
                    "id", "semantic_review", "evidence", "effective_authority_refs"}:
                return False
            claim_id = claim["id"]
            if (type(claim_id) is not str or not _V2_ID_RE.fullmatch(claim_id) or
                    not claim_id.startswith("CLAIM-") or claim_id in ids):
                return False
            ids.add(claim_id)
            review = claim["semantic_review"]
            if (type(review) is not dict or set(review) != {"state", "reference"} or
                    review["state"] not in ("unreviewed", "reviewed", "identity_acknowledged") or
                    (review["reference"] is not None and not _v2_text(review["reference"])) or
                    (review["state"] == "reviewed" and not _v2_text(review["reference"]))):
                return False
            evidence = claim["evidence"]
            if type(evidence) is not list or not 0 < len(evidence) <= 128:
                return False
            if not all(_valid_v2_evidence(item) for item in evidence):
                return False
            refs = claim["effective_authority_refs"]
            if (type(refs) is not list or len(refs) > 32 or
                    not all(_v2_text(ref) for ref in refs) or len(refs) != len(set(refs))):
                return False
    return True


# Top-level provenance-record contract (v1). Each required key maps to the
# type(s) a canonical record — the one new_record() builds — always carries.
# `bool` is excluded from the `schema` check explicitly because in Python
# `True == 1`, and a record whose schema is literally `true` is corrupt, not v1.
_RECORD_FIELD_TYPES = (
    ("doc", str),
    ("created", str),
    ("interview_derived", bool),
    ("entries", list),
)


def valid_provenance_record(record):
    """True iff `record` is a known v1 or closed v2 provenance record.

    For legacy v1, check the top-level frame only. Entry-level tolerance stays
    where it already lives — compute_drift and read-inject skip malformed
    entries without dropping a record. V2 is closed at every nested level.

    Unknown versions are rejected rather than best-effort parsed. Adding a
    version requires a deliberate new branch; v1 never becomes v2 by rehashing.
    Never raises.
    """
    if not isinstance(record, dict):
        return False
    schema = record.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int):
        return False
    if schema == V2_SCHEMA_VERSION:
        try:
            return _valid_v2_record(record)
        except (KeyError, TypeError, ValueError):
            return False
    if schema == SCHEMA_VERSION:
        for key, want in _RECORD_FIELD_TYPES:
            if key not in record or not isinstance(record[key], want):
                return False
        return True
    return False


def read_provenance(path):
    """Read provenance JSON from `path`; return the dict, or None if missing/corrupt.

    Never raises — mirrors read_board() in _taskboardlib.py. A missing file,
    a permission error, or malformed JSON all return None; the caller degrades
    gracefully.

    #410: "corrupt" includes SYNTACTICALLY VALID JSON of the wrong shape.
    The documented return type is `dict | None`, but the raw json.load result
    was handed straight back — so a file containing `[]` was admitted to the
    store as a list and the first `.get()` downstream raised AttributeError.
    Honouring the documented type here is what lets every caller treat a
    non-None result as a usable record.
    """
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    return record if valid_provenance_record(record) else None


def _read_context_store(provenance_dir, expected_docs):
    """Read bounded v2 candidates, preserving valid neighbors on bad records.

    The returned completeness flag covers every JSON in the store, including
    unsupported extra files. Per-document faults remain distinguishable from
    absent files; neither can become a verified current identity.
    """
    records = {}
    faults = {}
    complete = True
    truncated = False
    total_bytes = 0

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        with os.scandir(provenance_dir) as listing:
            for count, entry in enumerate(listing, 1):
                if count > MAX_CONTEXT_STORE_FILES:
                    complete = False
                    truncated = True
                    break
                if not entry.name.endswith(".json"):
                    continue
                stem = entry.name[:-5]
                try:
                    if not entry.is_file(follow_symlinks=False):
                        raise ValueError("non-file provenance entry")
                    remaining = MAX_CONTEXT_STORE_BYTES - total_bytes
                    if remaining <= 0:
                        faults[stem] = "oversize"
                        complete = False
                        truncated = True
                        break
                    limit = min(MAX_CONTEXT_RECORD_BYTES, remaining)
                    with open(entry.path, "rb") as source:
                        raw = source.read(limit + 1)
                    total_bytes += len(raw)
                    if len(raw) > limit:
                        faults[stem] = "oversize"
                        complete = False
                        if len(raw) > remaining:
                            truncated = True
                            break
                        continue
                    record = json.loads(raw.decode("utf-8"),
                                        object_pairs_hook=unique_object)
                except (OSError, UnicodeError, ValueError, RecursionError):
                    complete = False
                    faults[stem] = "corrupt"
                    continue
                if not valid_provenance_record(record):
                    complete = False
                    faults[stem] = "unsupported" if (type(record) is dict and
                                                         record.get("schema") not in
                                                         (SCHEMA_VERSION, V2_SCHEMA_VERSION)) else "corrupt"
                    continue
                doc = record["doc"]
                if doc in V2_DOCUMENTS and entry.name != doc + ".json":
                    complete = False
                    faults[stem] = "corrupt"
                    continue
                if doc in records:
                    complete = False
                    faults[doc] = "corrupt"
                    records.pop(doc, None)
                    continue
                records[doc] = record
    except FileNotFoundError:
        return {}, True, {}
    except (OSError, TypeError, ValueError):
        return {}, False, {doc: "store_unreadable" for doc in expected_docs}
    if truncated:
        for doc in expected_docs:
            if doc not in records and doc not in faults:
                faults[doc] = "store_unreadable"
    return {doc: records.get(doc) for doc in expected_docs}, complete, faults


def _first_manifest_after_interview_stub(provenance_dir, record, snapshot):
    """Return currently observed manifest paths, or [] without a safe handoff.

    This is an advisory first-input acquisition for the empty greenfield stack
    stub. It neither reads manifest content nor writes guidance or provenance.
    The stub's empty entries mean no acquired source facts, not proof that the
    repository was empty. A complete prior empty snapshot or a fresh nonempty
    one can initiate acquisition. Worktree, membership and target are rechecked
    before reporting actual current paths.
    """
    if (record.get("schema") != SCHEMA_VERSION or
            record.get("doc") != "tech-stack" or
            record.get("interview_derived") is not True or
            record.get("entries") != []):
        return []
    try:
        import _contextsnapshotlib
        root = snapshot["worktree"]["root"]
        if (type(root) is not str or
                os.path.normcase(os.path.realpath(provenance_dir)) !=
                os.path.normcase(os.path.realpath(os.path.join(
                    root, ".codearbiter", ".provenance")))):
            return []
        saved = next(item for item in snapshot["source"]["membership"]
                     if item["predicate"] == "manifests" and
                     item["scope_paths"] == ["."])
        if saved["status"] != "complete":
            return []
        checked = _contextsnapshotlib.compare_context_dependencies(
            snapshot, membership=(("manifests", (".",)),),
            target_paths=(".codearbiter/tech-stack.md",))
        if not checked["targets_current"]:
            return []
        current = _contextsnapshotlib.membership_snapshot(root, "manifests")
        if current["status"] != "complete" or not current["matches"]:
            return []
        return current["matches"]
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration,
            OSError, _contextsnapshotlib.SnapshotError,
            _contextsnapshotlib.MembershipError):
        return []


def assess_context_provenance(provenance_dir, expected_docs, snapshot,
                              snapshot_probe=None):
    """Report bounded v2 coverage and current identities, never semantic approval.

    Reads the bounded on-disk JSON store and flags malformed/unsupported files
    without losing valid neighbors. The legacy loader intentionally skips bad
    records for advisory availability; task-time reliance must not call that
    omission complete coverage.
    `snapshot` is the T-008 source/target snapshot; the default probe reacquires
    it at an action boundary. An integration may supply an equivalent trusted
    probe, but a stored record or source snapshot alone is never live truth.
    The result cannot authorize the future native repository-context kind.
    """
    result = {"coverage": "incomplete", "identity": "unknown",
              "semantic": "unverified", "verified_fresh": False,
              "documents": {}, "first_input": {}}
    if (not isinstance(provenance_dir, (str, os.PathLike)) or
            type(expected_docs) not in (list, tuple) or
            not expected_docs):
        return result
    try:
        if (len(expected_docs) != len(set(expected_docs)) or
                any(doc not in V2_DOCUMENTS for doc in expected_docs)):
            return result
    except TypeError:
        return result
    records, store_complete, faults = _read_context_store(provenance_dir, expected_docs)
    for doc in expected_docs:
        record = records.get(doc)
        if doc in faults:
            result["documents"][doc] = faults[doc]
        elif record is None:
            result["documents"][doc] = "missing"
        elif not valid_provenance_record(record) or record.get("doc") != doc:
            result["documents"][doc] = "unsupported"
        elif record["schema"] == SCHEMA_VERSION:
            result["documents"][doc] = "legacy_unverified"
            if doc == "tech-stack" and snapshot_probe is None:
                paths = _first_manifest_after_interview_stub(
                    provenance_dir, record, snapshot)
                if paths:
                    result["documents"][doc] = "first_input_pending"
                    result["first_input"][doc] = {
                        "paths": paths, "refresh_docs": ["tech-stack"]}
        else:
            result["documents"][doc] = "v2_unchecked"
    eligible = [doc for doc in expected_docs
                if result["documents"][doc] == "v2_unchecked"]
    if not eligible:
        return result
    probes = {}
    if snapshot_probe is None:
        # A provenance store belongs to one worktree. Its own JSON and marker
        # writes are output effects, never source dependencies for a new scout.
        try:
            import _contextsnapshotlib
            root = snapshot["worktree"]["root"]
            if (type(root) is not str or
                    os.path.normcase(os.path.realpath(provenance_dir)) !=
                    os.path.normcase(os.path.realpath(os.path.join(
                        root, ".codearbiter", ".provenance")))):
                return result
        except (KeyError, TypeError, ValueError, OSError):
            return result
        for doc in eligible:
            record = records[doc]
            evidence = [item for field in record["fields"]
                        for claim in field["claims"] for item in claim["evidence"]]
            paths = sorted({item["path"] for item in evidence
                            if item["kind"] == "content"})
            members = sorted({(item["predicate"], tuple(item["scope_paths"]))
                              for item in evidence if item["kind"] == "membership"})
            try:
                probes[doc] = _contextsnapshotlib.compare_context_dependencies(
                    snapshot, source_paths=paths, membership=members,
                    target_paths=(record["document"]["path"],))
            except Exception:
                # Missing/unreadable inputs or a changed worktree cannot be
                # promoted to current by another document's successful check.
                continue
    else:
        try:
            probe = snapshot_probe(snapshot)
            if (type(probe) is not dict or
                    type(probe.get("source_current")) is not bool or
                    type(probe.get("targets_current")) is not bool):
                return result
        except Exception:
            return result
        probes = {doc: probe for doc in eligible}
        if not probe["source_current"] or not probe["targets_current"]:
            if store_complete and len(eligible) == len(expected_docs):
                result["coverage"] = "complete"
            result["identity"] = "stale"
            for doc in eligible:
                result["documents"][doc] = "v2_stale"
            return result
    try:
        files = snapshot["source"]["files"]
        membership = snapshot["source"]["membership"]
        targets = snapshot["targets"]
        if type(files) is not dict or type(membership) is not list or type(targets) is not dict:
            return result
        membership_by_key = {
            (item["predicate"], tuple(item["scope_paths"])): item
            for item in membership if type(item) is dict
        }
        for doc in eligible:
            probe = probes.get(doc)
            if probe is None:
                continue
            if not probe["source_current"] or not probe["targets_current"]:
                result["identity"] = "stale"
                result["documents"][doc] = "v2_stale"
                continue
            record = records[doc]
            document = record["document"]
            target = targets.get(document["path"])
            if target is None:
                continue
            if (target.get("status") != "file" or
                    target.get("digest_method") != document["digest_method"] or
                    target.get("digest") != document["digest"]):
                result["identity"] = "stale"
                result["documents"][doc] = "v2_stale"
                continue
            unresolved = False
            for field in record["fields"]:
                for claim in field["claims"]:
                    for evidence in claim["evidence"]:
                        if evidence["kind"] == "content":
                            current = files.get(evidence["path"])
                        else:
                            key = (evidence["predicate"], tuple(evidence["scope_paths"]))
                            current = membership_by_key.get(key)
                        if current is None:
                            unresolved = True
                            continue
                        if (current.get("digest_method") != evidence["digest_method"] or
                                current.get("digest") != evidence["digest"]):
                            result["identity"] = "stale"
                            result["documents"][doc] = "v2_stale"
            if result["documents"][doc] == "v2_unchecked" and not unresolved:
                result["documents"][doc] = "v2_current"
    except (KeyError, TypeError, AttributeError, ValueError):
        return result
    if store_complete and all(result["documents"][doc] in
                              ("v2_current", "v2_stale") for doc in expected_docs):
        result["coverage"] = "complete"
    if result["coverage"] == "complete" and result["identity"] != "stale":
        result["identity"] = "current"
    return result


def startup_context_coverage_line(root, cmd_ref=None):
    """Summarize bounded record coverage without doing startup source hashing.

    This is a record-presence diagnostic, never a current-identity or semantic
    verdict. Task-time reliance uses assess_context_provenance with a fresh
    action-boundary snapshot instead.
    """
    try:
        context = os.path.join(root, ".codearbiter", "CONTEXT.md")
        if not os.path.isfile(context):
            return ""
        expected = tuple(V2_DOCUMENTS)
        store = os.path.join(root, ".codearbiter", ".provenance")
        records, complete, faults = _read_context_store(store, expected)
        counts = {"v2": 0, "legacy": 0, "missing": 0,
                  "corrupt": 0, "unsupported": 0, "oversize": 0,
                  "unreadable": 0}
        for doc in expected:
            if doc in faults:
                kind = faults[doc]
                counts["unreadable" if kind == "store_unreadable" else kind] += 1
            elif records.get(doc) is None:
                counts["missing"] += 1
            elif records[doc]["schema"] == V2_SCHEMA_VERSION:
                counts["v2"] += 1
            else:
                counts["legacy"] += 1
        ref = cmd_ref("context-check") if cmd_ref else "/ca:context-check"
        if complete and counts["v2"] == len(expected):
            return ("context coverage: {}/{} v2 records; identities and semantics "
                    "unchecked at startup -- run {}").format(
                        counts["v2"], len(expected), ref)
        details = ["v2 {}/{}".format(counts["v2"], len(expected))]
        details.extend("{} {}".format(key, counts[key]) for key in
                       ("legacy", "missing", "corrupt", "unsupported",
                        "oversize", "unreadable")
                       if counts[key])
        if not complete and not faults:
            details.append("store incomplete")
        return "context coverage: incomplete ({}); identities and semantics unchecked -- run {}".format(
            "; ".join(details), ref)
    except Exception:
        return "context coverage: unknown -- run /ca:context-check"


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
        [git_executable()] + list(args),
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
                    # A removed map target invalidates orientation even for old
                    # records whose source was classified as ordinary code.
                    if entry.get("drift_trigger") is not True and doc_name != "code-map":
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
                    if entry.get("drift_trigger") is not True:
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

    A staged path is excluded only when it has no enabled dependency or ALL
    enabled document baselines match. Preserves staged_paths order; deduplicates.
    Empty staged_paths, or no staged file tracked → [] (cost guarantee: ordinary
    commits touching no provenance source do zero re-scout work, AC-13).

    Never raises — malformed map/None → [].
    """
    try:
        if not staged_paths:
            return []

        # Keep every enrolled document baseline until divergence is evaluated.
        # Reducing to the legacy path-only worklist must not hide a later stale doc.
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
                        drift_trigger_map.setdefault(path, []).append(entry.get("hash"))
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
                stored_hashes = drift_trigger_map[path]
                # A mismatch in ANY dependent document schedules this source.
                # compute_drift/changed_scope retain the per-document detail.
                if path not in hashes or any(hashes[path] != stored for stored in stored_hashes):
                    result.append(path)
            except Exception:
                continue

        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Provenance directory loader + SessionStart drift line
# ---------------------------------------------------------------------------


MAX_SKIPPED_REPORTED = 5   # bounded corruption diagnostic (#410)


def load_provenance_dir(provenance_dir, skipped=None):
    """Load all provenance records from provenance_dir into {doc: record}.

    Globs <provenance_dir>/*.json, calls read_provenance on each file, and
    skips any that return None (missing, unreadable, or corrupt JSON — which
    since #410 includes valid JSON of the wrong shape). Each surviving record
    is keyed by its 'doc' field; if 'doc' is absent or empty, falls back to the
    filename stem so the dict never loses an entry. A missing or non-directory
    provenance_dir returns {}.

    #410: the per-file work sits inside its OWN error boundary. The whole glob
    loop used to share one try/except, so the first record that raised aborted
    the scan and every LATER valid record vanished with no diagnostic —
    SessionStart drift reporting and commit-gate auto-heal then ran against a
    silently truncated map. One bad file now costs exactly itself.

    `skipped`, when a list is passed, collects the BASENAMES of rejected files
    (at most MAX_SKIPPED_REPORTED) so a caller that has somewhere to put a
    warning can name the corrupt record. Names only — never file contents, which
    may hold paths or claims that do not belong in a log line.

    NO PRODUCTION CALLER PASSES `skipped` TODAY, and that is deliberate rather
    than an oversight. The two real call sites cannot carry the diagnostic:
    startup_drift_line is bound by AC-08 ("degrade to silence" — an all-corrupt
    provenance dir MUST return '', pinned by test_degrade_corrupt_json), and
    build_index runs on every PreToolUse:Read, where a per-call warning would be
    noise on the hottest path in the hook layer. Surfacing corruption to a user
    therefore belongs to /ca:context-check or /ca:doctor, which are surface
    prose and out of this module's reach. The channel exists, is bounded, and is
    tested; anything reading it is a follow-up.

    Never raises — filesystem errors and malformed records are skipped (this
    runs on the SessionStart linchpin path).
    """
    result = {}

    def note(fpath):
        if skipped is None or len(skipped) >= MAX_SKIPPED_REPORTED:
            return
        try:
            skipped.append(os.path.basename(fpath))
        except Exception:  # noqa: BLE001 — a diagnostic must never break the load
            pass

    try:
        if not os.path.isdir(provenance_dir):
            return {}
        paths = glob.glob(os.path.join(provenance_dir, "*.json"))
    except Exception:  # noqa: BLE001 — an unreadable dir is an empty map
        return {}

    for fpath in paths:
        try:
            record = read_provenance(fpath)
            if record is None:
                note(fpath)
                continue
            doc = record.get("doc") or os.path.splitext(os.path.basename(fpath))[0]
            result[str(doc)] = record
        except Exception:  # noqa: BLE001 — per-file boundary: skip THIS file only
            note(fpath)
    return result


def _make_root_runner(root):
    """Return a batch_hash-compatible runner bound to root via git -C.

    The default runner used by startup_drift_line resolves repo-relative
    paths from <root> rather than the process cwd.  T-16 injects its own
    runner; tests inject a fake to avoid real git calls.
    """
    def runner(args, stdin_text):
        result = subprocess.run(
            [git_executable(), "-C", root] + list(args),
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT,
        )
        return result.stdout
    return runner


def _is_confined_provenance_path(root, path):
    """Return whether path is a safe, non-root descendant of root.

    Provenance JSON is repository data, so treat its paths as untrusted before
    feeding them to git's newline-delimited ``--stdin-paths`` protocol.  Check
    both POSIX and Windows absolute/drive syntax so a record remains safe when
    a checkout moves between hosts, then resolve on the current host to catch
    traversal and symlink escapes.
    """
    try:
        if not isinstance(path, str) or not path:
            return False
        if any(char in path for char in ("\x00", "\n", "\r")):
            return False
        if posixpath.isabs(path) or ntpath.isabs(path) or ntpath.splitdrive(path)[0]:
            return False

        portable_path = posixpath.normpath(path.replace("\\", "/"))
        if portable_path in (".", "..") or portable_path.startswith("../"):
            return False

        confined_root = os.path.realpath(os.path.abspath(root))
        candidate = os.path.realpath(os.path.join(confined_root, path))
        return (
            candidate != confined_root
            and os.path.commonpath((confined_root, candidate)) == confined_root
        )
    except (OSError, TypeError, ValueError):
        return False


def startup_drift_line(root, runner=None, cmd_ref=None, unknown=None):
    """Return a one-line drift summary for SessionStart, or '' when clean (AC-06).

    Pipeline:
      1. Load all provenance records from <root>/.codearbiter/.provenance/.
      2. If the map is empty, return '' immediately (nothing to check).
      3. Reject unsafe drift-trigger paths, then collect the safe set across all
         docs. Rejected entries are also excluded from drift comparison so they
         cannot become false missing-file alarms.
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

    `unknown`, when a list is supplied, receives a bounded diagnostic on an
    incomplete hash batch. The legacy string result remains fail-soft.
    Never raises — all errors degrade to '' (safe for the SessionStart path).
    """
    try:
        if runner is None:
            runner = _make_root_runner(root)
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        pm = load_provenance_dir(provenance_dir)
        if not pm:
            return ""

        # Collect safe drift_trigger:true paths across all docs (deduped,
        # order-stable). Build a filtered in-memory map at the same time so a
        # rejected path cannot reappear as a false missing-file drift result.
        drift_trigger_paths = []
        code_map_existing = {}
        safe_pm = {}
        seen = set()
        for doc, record in pm.items():
            try:
                entries = record.get("entries") or []
                safe_entries = []
                for entry in entries:
                    try:
                        if entry.get("drift_trigger") is True or doc == "code-map":
                            path = entry.get("path")
                            if not _is_confined_provenance_path(root, path):
                                continue
                            if entry.get("drift_trigger") is True and path not in seen:
                                drift_trigger_paths.append(path)
                                seen.add(path)
                            elif doc == "code-map" and os.path.exists(os.path.join(root, path)):
                                # Ordinary source only needs a lifecycle check;
                                # its changed contents do not ring the old drift
                                # trigger. Preserve its stored hash for comparison.
                                code_map_existing[path] = entry.get("hash")
                        safe_entries.append(entry)
                    except Exception:
                        continue
                safe_record = dict(record)
                safe_record["entries"] = safe_entries
                safe_pm[doc] = safe_record
            except Exception:
                continue
        pm = safe_pm

        if not pm:
            return ""

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
            if isinstance(unknown, list):
                unknown.append("partial hash")
            return ""

        for path, stored_hash in code_map_existing.items():
            current_hashes.setdefault(path, stored_hash)

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


def lint_code_map(text, root=None):
    """Diagnose a coarse code map without rewriting it or reading source files.

    Code-map format: markdown where entries are column-0 '- `path` -- role'
    bullets.  Concern '## <name>' headings are structural labels, NOT entries.

    Checks applied:
      0. UTF-8 byte length > CODE_MAP_MAX_BYTES -> one advisory warning.
         Invalid Unicode/text is diagnosed, never silently called clean.
      1. Entry count > CODE_MAP_MAX_ENTRIES  ->  one warning naming count and cap.
         The cap enforces module/concern granularity: the code map must stay a
         coarse index, never a full file listing.
      2. For each entry whose immediately-following physical line starts with
         whitespace (an indented continuation — the role spilled onto a second
         line)  ->  one warning per offending entry, naming the entry number and
         path.  Column-0 '- ' bullets and '## ' headings do NOT start with
         whitespace so are excluded automatically.

    Returns a list of human-readable ASCII warning strings; [] means clean.
    When root is supplied, check each safe target's existence on demand. A
    malformed optional map remains human-owned; warnings never block source
    inspection. Empty or None text -> [].
    Never raises.
    """
    if not text:
        return []
    try:
        size = len(text.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return ["code map is not valid UTF-8 text"]
    byte_warnings = []
    if size > CODE_MAP_MAX_BYTES:
        byte_warnings.append(
            "code map has {} UTF-8 bytes (cap {}) -- coarsen without truncating guidance".format(
                size, CODE_MAP_MAX_BYTES
            )
        )
    try:
        lines = text.splitlines()
        entry_paths = []       # ordered list of extracted paths (one per entry)
        multi_warnings = []    # per-entry multi-line-role warnings (built inline)
        path_warnings = []

        for i, line in enumerate(lines):
            m = _ENTRY_RE.match(line)
            if not m:
                continue
            entry_path = m.group(1)
            entry_num = len(entry_paths) + 1   # 1-indexed
            entry_paths.append(entry_path)

            role = _CODE_MAP_ROLE_RE.match(line)
            if role is None or not role.group(1).strip():
                path_warnings.append("invalid one-line role at entry {}".format(entry_num))
            parts = entry_path.split("/")
            if parts[-1] == "" and len(parts) > 1:
                parts = parts[:-1]  # directory concern
            safe = (entry_path == entry_path.strip() and "\\" not in entry_path
                    and all(part not in ("", ".", "..") for part in parts)
                    and not entry_path.startswith("/")
                    and not ntpath.splitdrive(entry_path)[0]
                    and not any(ord(char) < 32 or ord(char) == 127 for char in entry_path))
            if not safe or root is not None and not _is_confined_provenance_path(root, entry_path):
                path_warnings.append("unsafe code map path at entry {}".format(entry_num))
            elif root is not None and not os.path.exists(os.path.join(root, entry_path)):
                path_warnings.append("missing code map target at entry {} (path {})".format(
                    entry_num, entry_path))

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

        result = list(byte_warnings)
        count = len(entry_paths)
        if count > CODE_MAP_MAX_ENTRIES:
            result.append(
                "code map has {} entries (cap {}) -- coarsen to module/concern granularity".format(
                    count, CODE_MAP_MAX_ENTRIES
                )
            )
        result.extend(multi_warnings)
        result.extend(path_warnings)
        return result
    except Exception:
        return ["code map could not be inspected"]


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
