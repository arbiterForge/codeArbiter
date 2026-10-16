"""Prepare explicit whole-document context previews from bounded source evidence.

This convenience layer writes nothing. The native writer owns validation,
preview retention, compare-and-swap, paired writes and recovery. Content hashes
record what was inspected; they never attest a semantic review or user approval.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import stat

import _artifactlib
import _contextsnapshotlib


def _read_file(path: Path, limit: int) -> bytes:
    try:
        fd = _artifactlib._open_pinned_regular(path)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "context input is not a bounded regular file")
            raw = os.read(fd, limit + 1)
        finally:
            os.close(fd)
        if len(raw) > limit or len(raw) != info.st_size:
            raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "context input is oversized or changed during acquisition")
        return raw
    except OSError as exc:
        raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "context input is unavailable or unsafe") from exc


def prepare_document_preview(root: str | Path, document_id: str,
                             draft_file: str | Path, source_paths: list[str]) -> dict:
    """Select the entire named document and preserve exact current identities."""
    root = _artifactlib._trusted_directory(root, "UNSAFE_ROOT")
    target = _artifactlib._CONTEXT_TARGETS.get(document_id)
    if target is None or not source_paths or len(source_paths) > 64:
        raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "select one context document and 1-64 source paths")
    provenance_path = f".codearbiter/.provenance/{document_id}.json"
    if any(path in {target, provenance_path} for path in source_paths):
        raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "context cannot use its own output as source evidence")
    draft = Path(draft_file)
    if not draft.is_absolute():
        draft = root / draft
    raw = _read_file(draft, 128 * 1024)
    try:
        markdown = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "context draft must be UTF-8") from exc
    evidence = []
    for path in sorted(set(source_paths)):
        try:
            acquired = _contextsnapshotlib.digest_file(root, path)
        except _contextsnapshotlib.DigestError as exc:
            raise _artifactlib.ArtifactError("INVALID_CONTEXT_SOURCE", str(exc)) from exc
        evidence.append({"kind": "content", **{key: acquired[key] for key in
                                              ("path", "digest_method", "digest")}})
    existing = _read_file(root / target, 128 * 1024) if os.path.lexists(root / target) else None
    prior = _read_file(root / provenance_path, 1 << 20) if os.path.lexists(root / provenance_path) else None
    mode = "create" if existing is None else "adopt"
    if prior is not None:
        try:
            record = _artifactlib._decode(prior, max_bytes=1 << 20)
        except _artifactlib.ArtifactError as exc:
            raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "preserve malformed existing provenance for review") from exc
        if not isinstance(record, dict) or record.get("doc") != document_id or record.get("schema") not in (1, 2):
            raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "preserve unsupported existing provenance for review")
        if existing is None:
            raise _artifactlib.ArtifactError("INVALID_CONTEXT_REQUEST", "existing provenance has no document; inspect recovery before creating")
        if record["schema"] == 2:
            mode = "update"
    digest = lambda value: hashlib.sha256(value).hexdigest() if value is not None else None
    request = {
        "mode": mode, "document_id": document_id, "target_path": target,
        "typed": {"format": "codearbiter.repository-context/0.1.0", "document_id": document_id,
                  "entries": [{"id": "FIELD-DOCUMENT", "kind": "document", "markdown": markdown,
                               "evidence_refs": ["CLAIM-DOCUMENT"]}]},
        "selections": [{"entry_id": "FIELD-DOCUMENT", "anchor": "document"}],
        "expected_document_sha256": digest(existing), "expected_provenance_sha256": digest(prior),
        "proposed_provenance": {
            "schema": 2, "doc": document_id, "created": datetime.date.today().isoformat(),
            "document": {"path": target, "digest_method": "sha256-raw", "digest": digest(raw)},
            "fields": [{"id": "FIELD-DOCUMENT", "owner_ref": "document", "claims": [{
                "id": "CLAIM-DOCUMENT", "semantic_review": {"state": "unreviewed", "reference": None},
                "evidence": evidence, "effective_authority_refs": [],
            }]}],
        },
    }
    identity = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    request["operation_id"] = "context-refresh-" + identity[:32]
    return request
