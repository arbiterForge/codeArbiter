#!/usr/bin/env python3
"""Pure ADR-0033 lifecycle validation and verified-only export helpers."""

import datetime as dt
import hashlib
import json
import os
import re

ADR_RE = re.compile(r"^(\d{4}-.+)\.md$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
FRONTMATTER_LINE_RE = re.compile(r"^([a-z][a-z0-9-]*):(?: (.*))?$")
H1_RE = re.compile(r"^# ADR-\d{4} (?:—|-) .+$")
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
STATUS_VALUES = {"draft", "proposed", "accepted", "superseded", "rejected"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _normalized_text(blob):
    return bytes(blob).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def parse_adr(blob):
    """Strictly parse one ADR and return status, sections, and bound bytes."""
    text = _normalized_text(blob)
    if not text.startswith("---\n"):
        raise ValueError("ADR has no opening frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("ADR has no closing frontmatter delimiter")
    front_text = text[4:end]
    body = text[end + 5:]
    fields = {}
    retained_front = []
    for line in front_text.split("\n"):
        if not line:
            raise ValueError("blank or malformed frontmatter line")
        match = FRONTMATTER_LINE_RE.fullmatch(line)
        if not match:
            raise ValueError("malformed frontmatter line %r" % line)
        key, value = match.groups()
        if key in fields:
            raise ValueError("duplicate frontmatter key %s" % key)
        fields[key] = value or ""
        if key == "status":
            retained_front.append("status: <mutable-status>")
        else:
            retained_front.append(line)
    for required in ("status", "date", "title", "decided-by", "supersedes"):
        if not fields.get(required):
            raise ValueError("missing frontmatter key %s" % required)
    if fields["status"].lower() not in STATUS_VALUES:
        raise ValueError("unsupported ADR status %r" % fields["status"])

    # Both separators are present in accepted history. Bind the exact heading
    # bytes, but fail closed unless there is exactly one recognized ADR H1.
    h1_matches = re.findall(r"(?m)^# ADR-\d{4} (?:—|-) .+$", body)
    if len(h1_matches) != 1 or not H1_RE.fullmatch(h1_matches[0]):
        raise ValueError("ADR has malformed or missing H1 heading")
    heading_matches = list(H2_RE.finditer(body))
    headings = [match.group(1) for match in heading_matches]
    duplicates = sorted({heading for heading in headings if headings.count(heading) > 1})
    if duplicates:
        raise ValueError("duplicate ADR section heading(s): %s" % ", ".join(duplicates))
    for required in ("Status", "Context", "Decision"):
        if required not in headings:
            raise ValueError("ADR has no ## %s section" % required)

    sections = {}
    status_value_span = None
    for index, match in enumerate(heading_matches):
        content_start = match.end()
        if content_start < len(body) and body[content_start] == "\n":
            content_start += 1
        content_end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(body)
        sections[match.group(1)] = body[content_start:content_end].encode("utf-8")
        if match.group(1) == "Status":
            status_text = body[content_start:content_end]
            status_match = re.match(r"\s*([A-Za-z]+)(?=$|[\s—-])", status_text)
            if status_match is None or status_match.group(1).lower() not in STATUS_VALUES:
                raise ValueError("ADR Status section has no recognized status value")
            if status_match.group(1).lower() != fields["status"].lower():
                raise ValueError("ADR Status section disagrees with frontmatter status")
            status_value_span = (
                content_start + status_match.start(1),
                content_start + status_match.end(1),
            )
    if status_value_span is None or not sections["Status"].strip():
        raise ValueError("ADR Status section is empty")

    status_start, status_end = status_value_span
    immutable_text = (
        "---\n" + "\n".join(retained_front) + "\n---\n" +
        body[:status_start] + "<mutable-status>" + body[status_end:]
    )
    return {"status": fields["status"].lower(), "fields": fields,
            "sections": sections, "immutable": immutable_text.encode("utf-8")}


def immutable_body(blob):
    """Complete normalized ADR bytes excluding only its parsed status values."""
    return parse_adr(blob)["immutable"]


def obligation_set_digest(obligations):
    encoded = json.dumps(obligations, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return _sha(encoded)


def read_jsonl(path):
    events = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except (TypeError, ValueError) as exc:
                events.append({"event": "invalid", "_error": "line %d: %s" % (number, exc)})
    return events


def read_adrs(root, errors=None):
    directory = os.path.join(root, ".codearbiter", "decisions")
    result = {}
    for name in sorted(os.listdir(directory)):
        match = ADR_RE.match(name)
        if not match:
            continue
        path = os.path.join(directory, name)
        with open(path, "rb") as handle:
            blob = handle.read()
        try:
            parse_adr(blob)
        except (UnicodeError, ValueError) as exc:
            if errors is not None:
                errors.append("%s: %s" % (match.group(1), exc))
            continue
        result[match.group(1)] = blob
    return result


def read_accepted_adrs(root, errors=None):
    return {adr: blob for adr, blob in read_adrs(root, errors=errors).items()
            if parse_adr(blob)["status"] == "accepted"}


def append_only_error(base, current):
    if bytes(current).startswith(bytes(base)):
        return None
    return "adr-lifecycle ledger rewrites or truncates base history"


def _parse_time(value):
    moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp has no timezone")
    return moment


def _binding_errors(event, blob):
    errors = []
    adr = event.get("adr", "<missing>")
    try:
        parsed = parse_adr(blob)
        body = _sha(parsed["immutable"])
    except (UnicodeError, ValueError) as exc:
        errors.append("%s: immutable content unavailable: %s" % (adr, exc))
        parsed = {"sections": {}}
    else:
        if body != event.get("body_sha256"):
            errors.append("%s: immutable-body digest does not match" % adr)
    try:
        _parse_time(event.get("recorded_at"))
    except (TypeError, ValueError):
        errors.append("%s: binding has invalid recorded_at" % adr)
    obligations = event.get("obligations")
    if not isinstance(obligations, list):
        errors.append("%s: obligations must be a list" % adr)
        obligations = []
    if obligation_set_digest(obligations) != event.get("obligations_sha256"):
        errors.append("%s: obligation-set digest does not match sealed content" % adr)
    seen = set()
    for obligation in obligations:
        oid = obligation.get("id") if isinstance(obligation, dict) else None
        if not isinstance(oid, str) or not oid.startswith(adr + "."):
            errors.append("%s: obligation id %r is not stem-scoped" % (adr, oid))
            continue
        if oid in seen:
            errors.append("%s: duplicate obligation id %s" % (adr, oid))
        seen.add(oid)
        section = obligation.get("section")
        section_bytes = parsed["sections"].get(section) if isinstance(section, str) else None
        if section_bytes is None:
            errors.append("%s: obligation %s section binding is absent" % (adr, oid))
        text = obligation.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append("%s: obligation %s has no bound text" % (adr, oid))
            continue
        encoded = text.encode("utf-8")
        if _sha(encoded) != obligation.get("text_sha256"):
            errors.append("%s: obligation %s text digest does not match" % (adr, oid))
        if section_bytes is not None and encoded not in section_bytes:
            errors.append("%s: obligation %s text violates its section binding" % (adr, oid))
    return errors


def validate_source_blobs(events, source_blobs):
    """Validate acceptance and migration bindings against committed Git bytes."""
    errors = []
    for event in events:
        if not isinstance(event, dict) or event.get("event") not in ("acceptance", "baseline"):
            continue
        adr = event.get("adr")
        kind = event.get("event")
        label = "source-commit" if kind == "acceptance" else "migration-snapshot"
        field = "source_commit" if kind == "acceptance" else "observed_commit"
        commit = event.get(field)
        if not isinstance(commit, str) or not isinstance(adr, str):
            errors.append("%s: %s binding identity is malformed" % (adr, label))
            continue
        blob = source_blobs.get((commit, adr))
        if blob is None:
            errors.append("%s: %s ADR blob is unavailable" % (adr, label))
            continue
        if _sha(blob) != event.get("blob_sha256"):
            errors.append("%s: %s blob digest does not match" % (adr, label))
        try:
            parsed = parse_adr(blob)
            body_digest = _sha(parsed["immutable"])
        except (UnicodeError, ValueError) as exc:
            errors.append("%s: %s immutable content unavailable: %s" % (adr, label, exc))
        else:
            if body_digest != event.get("body_sha256"):
                errors.append("%s: %s immutable-body digest does not match" % (adr, label))
            if parsed["status"] != "accepted":
                errors.append("%s: %s ADR status must be accepted" % (adr, label))
    return errors


def _evidence_errors(event, index):
    errors = []
    if not isinstance(event.get("event_id"), str) or not event["event_id"].strip():
        errors.append("line %d: evidence has no event_id" % index)
    if not HEX40.fullmatch(str(event.get("source_commit", ""))):
        errors.append("line %d: evidence source_commit must be a 40-character Git id" % index)
    digests = event.get("input_digests")
    if not isinstance(digests, dict) or not digests:
        errors.append("line %d: evidence has no input digests" % index)
    elif any(not isinstance(path, str) or not path or not HEX64.fullmatch(str(digest))
             for path, digest in digests.items()):
        errors.append("line %d: evidence input digests must map paths to SHA-256 values" % index)
    kind = event.get("event")
    if kind == "implemented":
        if not isinstance(event.get("evidence"), str) or not event["evidence"].strip():
            errors.append("line %d: implementation evidence is missing" % index)
    if kind == "verified":
        for field in ("proof_contract", "producer", "command", "observed_at",
                      "valid_until", "claim"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                errors.append("line %d: verified evidence has no %s" % (index, field))
        if event.get("claim_scope") != "repository":
            errors.append("line %d: verified evidence claim_scope must be repository" % index)
        try:
            observed = _parse_time(event.get("observed_at"))
            valid_until = _parse_time(event.get("valid_until"))
            if observed > valid_until:
                errors.append("line %d: observed_at is after valid_until" % index)
        except (TypeError, ValueError) as exc:
            errors.append("line %d: verified evidence timestamp/timezone is invalid: %s" %
                          (index, exc))
    return errors


def validate_events(events, adr_blobs, require_all_accepted=False):
    errors = []
    bindings = {}
    obligations = {}
    event_ids = {}
    implementations = {}
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("_error"):
            errors.append("invalid lifecycle event at line %d" % index)
            continue
        if event.get("schema") != "adr-lifecycle/v1":
            errors.append("line %d: unsupported schema" % index)
        kind = event.get("event")
        adr = event.get("adr")
        if kind in ("acceptance", "baseline"):
            if not isinstance(adr, str) or not adr:
                errors.append("line %d: binding has malformed ADR identity" % index)
                continue
            if adr in bindings:
                errors.append("%s: second acceptance/baseline binding is forbidden" % adr)
                continue
            blob = adr_blobs.get(adr)
            if blob is None:
                errors.append("%s: binding names no valid ADR" % adr)
                continue
            bindings[adr] = event
            errors.extend(_binding_errors(event, blob))
            sealed = event.get("obligations_sealed") is True
            if kind == "acceptance":
                if not sealed:
                    errors.append("%s: acceptance obligation set is not sealed" % adr)
                if sealed and not (isinstance(event.get("obligations"), list)
                                   and event["obligations"]):
                    errors.append("%s: sealed acceptance obligation set is empty" % adr)
                if not HEX40.fullmatch(str(event.get("source_commit", ""))):
                    errors.append("%s: acceptance source_commit must be a 40-character Git id" % adr)
                if "observed_commit" in event:
                    errors.append("%s: acceptance must not use observed_commit" % adr)
            else:
                if sealed:
                    errors.append("%s: legacy baseline must remain unsealed" % adr)
                if "source_commit" in event:
                    errors.append("%s: legacy baseline must not fabricate an acceptance commit" % adr)
                if not HEX40.fullmatch(str(event.get("observed_commit", ""))):
                    errors.append("%s: baseline observed_commit must be a 40-character Git id" % adr)
            raw_obligations = event.get("obligations")
            for item in raw_obligations if isinstance(raw_obligations, list) else []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    oid = item["id"]
                    if oid in obligations:
                        errors.append("%s: duplicate obligation id %s" % (adr, oid))
                    obligations[oid] = adr
        elif kind in ("implemented", "verified"):
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                errors.append("line %d: evidence has no event_id" % index)
            elif event_id in event_ids:
                errors.append("line %d: duplicate event_id %r" % (index, event_id))
            else:
                event_ids[event_id] = kind
            oid = event.get("obligation")
            if not isinstance(oid, str):
                errors.append("line %d: evidence has malformed obligation identity" % index)
                continue
            if oid not in obligations:
                errors.append("line %d: evidence names undeclared obligation %r" % (index, oid))
            elif adr != obligations[oid]:
                errors.append("line %d: evidence ADR does not own obligation %r" % (index, oid))
            key = (adr, oid)
            if kind == "implemented":
                implementations.setdefault(key, []).append(event)
            else:
                prior = implementations.get(key, [])
                if not prior:
                    errors.append("line %d: verified evidence appears before implementation for %r" %
                                  (index, oid))
                elif event.get("input_digests") != prior[-1].get("input_digests"):
                    errors.append("line %d: verification input set differs from implementation input digest boundary for %r" %
                                  (index, oid))
            errors.extend(_evidence_errors(event, index))
        elif kind == "invalidated":
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                errors.append("line %d: invalidation has no event_id" % index)
            elif event_id in event_ids:
                errors.append("line %d: duplicate event_id %r" % (index, event_id))
            else:
                event_ids[event_id] = kind
            target = event.get("target_event_id")
            if (not isinstance(target, str) or target not in event_ids or
                    event_ids.get(target) not in ("implemented", "verified")):
                errors.append("line %d: invalidation target is missing or not prior evidence" % index)
            if not isinstance(event.get("reason"), str) or not event["reason"].strip():
                errors.append("line %d: invalidation has no reason" % index)
            try:
                _parse_time(event.get("recorded_at"))
            except (TypeError, ValueError):
                errors.append("line %d: invalidation has invalid recorded_at" % index)
        else:
            errors.append("line %d: unknown event %r" % (index, kind))
    if require_all_accepted:
        for adr in sorted(set(adr_blobs) - set(bindings)):
            errors.append("%s: accepted ADR has no lifecycle binding" % adr)
    return errors


def validate_evidence_sources(events, source_inputs):
    """Recompute every evidence path digest from its committed Git bytes."""
    errors = []
    for event in events:
        if not isinstance(event, dict) or event.get("event") not in ("implemented", "verified"):
            continue
        commit = event.get("source_commit")
        event_id = event.get("event_id", "<missing>")
        digests = event.get("input_digests")
        if not isinstance(digests, dict):
            continue
        for path, expected in digests.items():
            if not isinstance(path, str) or not isinstance(commit, str):
                errors.append("%s: Git input binding is malformed" % event_id)
                continue
            blob = source_inputs.get((commit, path))
            if blob is None:
                errors.append("%s: Git input %s is unavailable at %s" % (event_id, path, commit))
            elif _sha(blob) != expected:
                errors.append("%s: Git input digest does not match for %s" % (event_id, path))
    return errors


def _inputs_current(event, current_blobs):
    digests = event.get("input_digests")
    if not isinstance(digests, dict) or not digests:
        return False
    return all(path in current_blobs and current_blobs[path] is not None and
               _sha(current_blobs[path]) == digest
               for path, digest in digests.items())


def verified_export(events, adr_blobs, current_blobs, now):
    errors = validate_events(events, adr_blobs)
    if errors:
        return [], errors
    try:
        moment = _parse_time(now)
    except (TypeError, ValueError) as exc:
        return [], ["export time/timezone is invalid: %s" % exc]
    bindings = {event.get("adr"): event for event in events
                if event.get("event") in ("acceptance", "baseline")}
    invalidated = {event.get("target_event_id") for event in events
                   if event.get("event") == "invalidated"}
    exported = []
    suppressed = set()
    for adr, binding in sorted(bindings.items()):
        if not binding.get("obligations_sealed"):
            errors.append("%s: obligation set is unsealed; no Verified export" % adr)
            suppressed.add(adr)
            continue
        for obligation in binding.get("obligations", []):
            oid = obligation["id"]
            impls = [event for event in events if event.get("event") == "implemented"
                     and event.get("adr") == adr and event.get("obligation") == oid
                     and event.get("event_id") not in invalidated]
            proofs = [event for event in events if event.get("event") == "verified"
                      and event.get("adr") == adr and event.get("obligation") == oid
                      and event.get("event_id") not in invalidated]
            implementation = next(
                (event for event in reversed(impls) if _inputs_current(event, current_blobs)), None)
            proof = next(
                (event for event in reversed(proofs)
                 if _inputs_current(event, current_blobs)
                 and _parse_time(event["observed_at"]) <= moment <= _parse_time(event["valid_until"])),
                None)
            if implementation is None:
                errors.append("%s: no current implementation evidence; implementation input digest is missing or stale" % oid)
                suppressed.add(adr)
                continue
            if proof is None:
                current_proofs = [event for event in proofs
                                  if _inputs_current(event, current_blobs)]
                if current_proofs and all(
                        moment > _parse_time(event["valid_until"])
                        for event in current_proofs):
                    errors.append("%s: no current verification evidence; all current-input evidence expired or was invalidated" % oid)
                elif current_proofs and all(
                        moment < _parse_time(event["observed_at"])
                        for event in current_proofs):
                    errors.append("%s: verification evidence is not yet observable" % oid)
                else:
                    errors.append("%s: no current verification evidence; verification input digest is missing or stale" % oid)
                suppressed.add(adr)
                continue
            if proof.get("input_digests") != implementation.get("input_digests"):
                errors.append("%s: implementation/verification input boundary differs" % oid)
                suppressed.add(adr)
                continue
            exported.append({
                "adr": adr, "obligation": oid, "claim": proof["claim"],
                "claim_scope": proof["claim_scope"], "source_commit": proof["source_commit"],
                "input_digests": proof["input_digests"],
                "proof_contract": proof["proof_contract"], "producer": proof["producer"],
                "command": proof["command"], "observed_at": proof["observed_at"],
                "valid_until": proof["valid_until"],
            })
    # A verified report is aggregate per ADR over that ADR's complete sealed set.
    # Never leak a partial set for one ADR or let it hide another complete ADR.
    return [row for row in exported if row["adr"] not in suppressed], errors
