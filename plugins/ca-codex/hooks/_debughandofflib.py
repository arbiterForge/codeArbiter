# codeArbiter — finite debug handoff shape and primitive validation.
# This pure library owns bounded byte decoding, the closed model, exact scalar
# rules, finite reference/check semantics, and T-011 outcome semantics.
# Schema/reference projections are pure; process output remains separate.
#
# JsonNumber(lexeme) -> JsonNumber: retain an exact JSON numeric token.
# decode_packet(raw) -> tuple[object, str | None]: decode bounded JSON bytes.
# valid_primitive(kind, value) -> bool: check one decoded scalar profile.
# validate_primitives(packet) -> list[tuple[str, str]]: closed model errors.
# project_schema() -> bytes: deterministic JSON Schema shape projection.
# project_reference() -> bytes: deterministic field reference projection.
# validate_semantics_bounded(packet, ceiling=16) -> tuple[list, bool]: bounded errors.

import datetime
from decimal import Decimal
import json
import re


PROTOCOL = "codearbiter.debug-handoff/1.0.0"


class JsonNumber:
    """An exact JSON numeric token supplied by the future bounded decoder."""

    __slots__ = ("lexeme",)

    def __init__(self, lexeme):
        self.lexeme = lexeme


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result


def _reject_constant(_token):
    raise ValueError()


def _within_depth(text):
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                return False
        elif char in "]}":
            depth -= 1
    return True


def _has_surrogate(value):
    if type(value) is str:
        return any(0xd800 <= ord(char) <= 0xdfff for char in value)
    if type(value) is dict:
        return any(_has_surrogate(key) or _has_surrogate(child)
                   for key, child in value.items())
    if type(value) is list:
        return any(_has_surrogate(child) for child in value)
    return False


def decode_packet(raw):
    """Decode a complete bounded UTF-8 JSON value without repairing input."""
    if type(raw) is not bytes:
        return None, "INVALID_JSON"
    if len(raw) > 65536:
        return None, "INPUT_LIMIT"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "INVALID_UTF8"
    if text.startswith("\ufeff"):
        return None, "INVALID_UTF8"
    if not _within_depth(text):
        return None, "DEPTH_LIMIT"
    try:
        value = json.loads(text, parse_int=JsonNumber, parse_float=JsonNumber,
                           parse_constant=_reject_constant,
                           object_pairs_hook=_object_without_duplicates)
    except _DuplicateKey:
        return None, "DUPLICATE_KEY"
    except (ValueError, RecursionError):
        return None, "INVALID_JSON"
    if _has_surrogate(value):
        return None, "INVALID_JSON"
    return value, None


_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?", re.ASCII)
_TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,9})?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
    re.ASCII,
)
_PATTERNS = {
    "case_id": re.compile(r"DBG-[A-Za-z0-9][A-Za-z0-9_-]{2,63}", re.ASCII),
    "snapshot_id": re.compile(r"S-[0-9]{2,4}", re.ASCII),
    "evidence_id": re.compile(r"E-[0-9]{2,4}", re.ASCII),
    "hypothesis_id": re.compile(r"H-[0-9]{2,4}", re.ASCII),
    "check_id": re.compile(r"C-[0-9]{2,4}", re.ASCII),
    "git_oid": re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", re.ASCII),
    "sha256": re.compile(r"sha256:[0-9a-f]{64}", re.ASCII),
    "recipe_name": re.compile(r"[a-z][a-z0-9-]{0,63}/[1-9][0-9]{0,3}", re.ASCII),
}
_WHITESPACE = frozenset({*range(0x09, 0x0e), 0x20, 0x85, 0xa0, 0x1680,
                         *range(0x2000, 0x200b), 0x2028, 0x2029, 0x202f,
                         0x205f, 0x3000})


def _valid_text(value, limit):
    return (type(value) is str and 0 < len(value) <= limit
            and all(not 0xd800 <= ord(char) <= 0xdfff for char in value)
            and any(ord(char) not in _WHITESPACE for char in value))


def _bounded_exponent(digits, ceiling):
    value = 0
    for digit in digits:
        value = min(ceiling, value * 10 + ord(digit) - 48)
    return value


def _valid_integer(value):
    if type(value) is int:
        return True
    if isinstance(value, Decimal):
        return value.is_finite() and value == value.to_integral_value()
    if type(value) is not JsonNumber or type(value.lexeme) is not str:
        return False
    match = _NUMBER.fullmatch(value.lexeme)
    if match is None:
        return False
    token = value.lexeme
    coefficient = token.split("e", 1)[0].split("E", 1)[0].lstrip("-")
    whole, dot, fraction = coefficient.partition(".")
    digits = whole + fraction
    if not any(char != "0" for char in digits):
        return True
    exponent_text = match.group(2)
    ceiling = len(digits) + len(fraction) + 1
    if exponent_text is None:
        exponent = 0
    else:
        negative = exponent_text.startswith("-")
        magnitude = exponent_text.lstrip("+-")
        exponent = _bounded_exponent(magnitude, ceiling)
        if negative:
            exponent = -exponent
    scale = exponent - len(fraction)
    if scale >= 0:
        return True
    return -scale <= len(digits) - len(digits.rstrip("0"))


def _valid_timestamp(value):
    if type(value) is not str:
        return False
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        return False
    try:
        datetime.date(*(int(part) for part in match.groups()))
    except ValueError:
        return False
    return True


def valid_primitive(kind, value):
    """Validate a scalar without coercing or repairing it."""
    if kind == "timestamp":
        return _valid_timestamp(value)
    if kind in ("integer", "integer_lexeme"):
        return _valid_integer(value)
    if kind == "text":
        return (type(value) is tuple and len(value) == 2
                and type(value[1]) is int and _valid_text(*value))
    if kind in _PATTERNS:
        return type(value) is str and _PATTERNS[kind].fullmatch(value) is not None
    if kind == "boolean":
        return type(value) is bool
    raise ValueError("unknown primitive kind")


# Field descriptors are inert finite data: (kind, arguments...).
def _text(limit):
    return ("text", limit)


def _nullable(child):
    return ("nullable", child)


def _array(child, low, high):
    return ("array", child, low, high)


def _refs(namespace, high):
    return ("refs", namespace, high)


def _enum(*values):
    return ("enum", values)


def _object(name):
    return ("object", name)


MODEL = {
    "packet": {
        "protocol": ("protocol",), "case_id": ("case_id",),
        "request": _object("request"), "snapshots": _array(_object("snapshot"), 0, 4),
        "symptom": _object("symptom"), "reproduction": _object("reproduction"),
        "hypotheses": _array(_object("hypothesis"), 0, 16),
        "checks": _array(_object("check"), 0, 24),
        "evidence": _array(_object("evidence"), 1, 32),
        "disposition": _object("disposition"), "next_step": _object("next_step"),
        "regression": _nullable(_object("regression")),
    },
    "request": {
        "intent": _enum("diagnosis_only", "repair_requested"),
        "request_ref": _text(512), "scope": _text(2000),
        "restrictions": _array(_text(500), 0, 12),
    },
    "snapshot": {
        "id": ("snapshot_id",), "repository": _text(512),
        "worktree": _text(512), "commit": _nullable(("git_oid",)),
        "dirty_state": _enum("clean", "dirty", "unknown"),
        "fingerprint": _nullable(("sha256",)),
        "fingerprint_recipe": _nullable(("recipe_name",)),
        "runtime_identity": _nullable(_text(500)),
        "limitations": _nullable(_text(1500)),
    },
    "symptom": {
        "observed": _text(1500), "expected": _nullable(_text(1500)),
        "expected_evidence_ids": _refs("evidence_id", 32),
    },
    "recipe": {
        "steps": _array(_text(500), 1, 8), "cwd": _text(512),
        "preconditions": _text(1000), "failure_signature": _text(1000),
    },
    "reproduction": {
        "status": _enum("reproduced", "intermittent", "not_yet_reproduced",
                        "unsafe_to_replay", "unavailable"),
        "recipe": _nullable(_object("recipe")),
        "evidence_ids": _refs("evidence_id", 32),
        "limitations": _nullable(_text(1500)),
    },
    "hypothesis": {
        "id": ("hypothesis_id",), "mechanism": _text(2000),
        "discriminator": _text(1500),
        "status": _enum("supported", "refuted", "inconclusive"),
        "supporting_evidence_ids": _refs("evidence_id", 32),
        "opposing_evidence_ids": _refs("evidence_id", 32),
        "limitations": _nullable(_text(1500)),
    },
    "check": {
        "id": ("check_id",), "operation": _text(2000),
        "cwd": _nullable(_text(512)),
        "status": _enum("planned", "completed", "not_run", "interrupted"),
        "exit_code": _nullable(("integer",)),
        "expectation": _text(1500), "observed": _nullable(_text(1500)),
        "evidence_ids": _refs("evidence_id", 32),
        "authorization_basis": _nullable(_text(1000)),
        "side_effects": _text(1500),
    },
    "evidence": {
        "id": ("evidence_id",),
        "kind": _enum("source", "observation", "user_report", "command_result", "contract"),
        "snapshot_id": _nullable(("snapshot_id",)),
        "locator": _text(1000), "observation": _text(2000),
        "observed_at": _nullable(("timestamp",)),
        "check_id": _nullable(("check_id",)),
        "coverage": _enum("complete_for_claim", "partial", "unknown"),
        "limitations": _nullable(_text(1500)),
    },
    "blocker": {
        "kind": _enum("access", "evidence", "authority", "capability",
                      "safety", "scope", "budget", "input"),
        "missing": _text(1500), "owner": _nullable(_text(300)),
        "resume_condition": _text(1500),
    },
    "disposition": {
        "kind": _enum("confirmed_code_defect", "confirmed_noncode_cause",
                      "design_question", "no_action", "unresolved"),
        "rationale": _text(2000), "evidence_ids": _refs("evidence_id", 32),
        "cause_ids": _refs("hypothesis_id", 16),
        "blockers": _array(_object("blocker"), 0, 8),
    },
    "next_step": {
        "target": _enum("none", "fix", "adr", "existing_owner", "evidence"),
        "owner": _nullable(_text(300)), "action": _nullable(_text(1500)),
        "completion_evidence": _nullable(_text(1500)),
    },
    "regression": {
        "basis": _enum("reproduction", "causal_trace"),
        "snapshot_id": ("snapshot_id",), "obligation": _text(2000),
        "oracle": _text(1500), "candidate_test_id": _nullable(_text(500)),
        "reuse_existing": ("boolean",), "evidence_ids": _refs("evidence_id", 32),
    },
}


def project_schema():
    """Return the finite model's JSON Schema projection as UTF-8 bytes."""
    definitions = {}
    for name, fields in sorted(MODEL.items()):
        definitions[name] = {
            "type": "object",
            "properties": {field: _schema_for(spec)
                           for field, spec in sorted(fields.items())},
            "required": sorted(fields),
            "additionalProperties": False,
        }
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/packet",
        "$defs": definitions,
    }
    return (json.dumps(document, ensure_ascii=True, sort_keys=True,
                       indent=2) + "\n").encode("utf-8")


def project_reference():
    """Return the finite model's field reference as UTF-8 bytes."""
    lines = [
        "# Debug handoff field reference",
        "",
        "Generated from the finite `_debughandofflib.MODEL` definitions.",
        "The JSON Schema projects shape and scalar profiles. Cross-record SEM",
        "rules, strict byte decoding, causal truth, freshness, and authority remain",
        "separate obligations of the validator and its consumers.",
        "",
        f"Protocol: `{PROTOCOL}`.",
        "",
    ]
    for name, fields in sorted(MODEL.items()):
        lines.extend((f"## {name}", "", "| Field | Profile |",
                      "|---|---|"))
        for field, spec in sorted(fields.items()):
            lines.append(f"| `{name}.{field}` | `{_reference_for(spec)}` |")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _full_string_pattern(pattern):
    """Use an absolute-end lookahead; `$` permits a final newline."""
    return r"^(?:" + pattern + r")(?![\s\S])"


def _text_pattern():
    whitespace = "".join(f"\\u{code:04X}" for code in sorted(_WHITESPACE))
    return (r"^(?=[\s\S]*[^" + whitespace + r"])(?![\s\S]*"
            r"[\uD800-\uDFFF])")


def _schema_for(spec):
    kind = spec[0]
    if kind == "nullable":
        return {"anyOf": [_schema_for(spec[1]), {"type": "null"}]}
    if kind == "object":
        return {"$ref": f"#/$defs/{spec[1]}"}
    if kind == "array":
        return {"type": "array", "items": _schema_for(spec[1]),
                "minItems": spec[2], "maxItems": spec[3]}
    if kind == "refs":
        return {"type": "array", "items": _schema_for((spec[1],)),
                "minItems": 0, "maxItems": spec[2], "uniqueItems": True}
    if kind == "text":
        return {"type": "string", "minLength": 1, "maxLength": spec[1],
                "pattern": _text_pattern()}
    if kind == "enum":
        return {"type": "string", "enum": list(spec[1])}
    if kind == "protocol":
        return {"type": "string", "const": PROTOCOL}
    if kind == "boolean":
        return {"type": "boolean"}
    if kind == "integer":
        return {"type": "integer"}
    if kind == "timestamp":
        return {"type": "string", "pattern": _full_string_pattern(
            _TIMESTAMP.pattern), "format": "date-time"}
    if kind in _PATTERNS:
        return {"type": "string", "pattern": _full_string_pattern(
            _PATTERNS[kind].pattern)}
    raise ValueError("unknown finite field kind")


def _reference_for(spec):
    kind = spec[0]
    if kind == "nullable":
        return f"nullable({_reference_for(spec[1])})"
    if kind == "object":
        return f"object({spec[1]})"
    if kind == "array":
        return f"array({_reference_for(spec[1])}, {spec[2]}..{spec[3]})"
    if kind == "refs":
        return f"refs({spec[1]}, 0..{spec[2]}, unique)"
    if kind == "text":
        return f"text({spec[1]})"
    if kind == "enum":
        return "enum(" + ", ".join(spec[1]) + ")"
    if kind == "protocol":
        return f"const({PROTOCOL})"
    if kind in ("boolean", "integer", "timestamp", *_PATTERNS):
        return kind
    raise ValueError("unknown finite field kind")


def _check(value, spec, path, errors):
    kind = spec[0]
    if kind == "nullable":
        if value is not None:
            _check(value, spec[1], path, errors)
        return
    if kind == "object":
        if type(value) is not dict:
            errors.append(("TYPE", path))
            return
        fields = MODEL[spec[1]]
        for name, child in fields.items():
            if name not in value:
                errors.append(("REQUIRED_FIELD", path + "." + name))
            else:
                _check(value[name], child, path + "." + name, errors)
        if any(name not in fields for name in value):
            errors.append(("UNKNOWN_FIELD", path))
        return
    if kind == "array":
        if type(value) is not list:
            errors.append(("TYPE", path))
            return
        if not spec[2] <= len(value) <= spec[3]:
            errors.append(("VALUE", path))
            return
        for index, child in enumerate(value):
            _check(child, spec[1], path + "[" + str(index) + "]", errors)
        return
    if kind == "refs":
        if type(value) is not list:
            errors.append(("TYPE", path))
            return
        if len(value) > spec[2]:
            errors.append(("VALUE", path))
            return
        seen = set()
        for index, item in enumerate(value):
            _check(item, (spec[1],), path + "[" + str(index) + "]", errors)
            if type(item) is str:
                if item in seen:
                    errors.append(("VALUE", path))
                    return
                seen.add(item)
        return
    if kind == "text":
        if type(value) is not str:
            errors.append(("TYPE", path))
        elif not _valid_text(value, spec[1]):
            errors.append(("VALUE", path))
        return
    if kind == "enum":
        if type(value) is not str:
            errors.append(("TYPE", path))
        elif value not in spec[1]:
            errors.append(("VALUE", path))
        return
    if kind == "protocol":
        if type(value) is not str:
            errors.append(("TYPE", path))
        elif value != PROTOCOL:
            errors.append(("UNSUPPORTED_PROTOCOL", path))
        return
    if kind == "boolean":
        if type(value) is not bool:
            errors.append(("TYPE", path))
        return
    if kind == "integer":
        if not _valid_integer(value):
            errors.append(("TYPE", path))
        return
    if type(value) is not str:
        errors.append(("TYPE", path))
    elif not valid_primitive(kind, value):
        errors.append(("VALUE", path))


def validate_primitives(packet):
    """Check finite closed structure and scalar profiles; no semantic claims."""
    errors = []
    _check(packet, _object("packet"), "$", errors)
    return errors


def _not_recorded_success(value):
    """Reject explicit mathematical zero without treating a missing exit as success."""
    if value is None:
        return True
    if type(value) is int or isinstance(value, Decimal):
        return value != 0
    if type(value) is JsonNumber:
        coefficient = value.lexeme.split("e", 1)[0].split("E", 1)[0]
        return any("1" <= digit <= "9" for digit in coefficient)
    return False


class _TooManyDiagnostics(Exception):
    pass


class _BoundedErrors(list):
    """Stop at the first suppressed row without retaining it."""

    def __init__(self, ceiling):
        super().__init__()
        self.ceiling = ceiling

    def append(self, error):
        if len(self) == self.ceiling:
            raise _TooManyDiagnostics()
        super().append(error)


def validate_semantics(packet):
    """Check packet claims without reading locators or executing checks."""
    return _validate_semantics(packet, [])


def validate_semantics_bounded(packet, ceiling=16):
    """Collect at most ceiling errors; flag the first suppressed error."""
    if type(ceiling) is not int or not 1 <= ceiling <= 16:
        raise ValueError("invalid diagnostic ceiling")
    errors = _BoundedErrors(ceiling)
    try:
        _validate_semantics(packet, errors)
    except _TooManyDiagnostics:
        return list(errors), True
    return list(errors), False


def _validate_semantics(packet, errors):
    _check(packet, _object("packet"), "$", errors)
    if errors:
        return errors

    records = {}
    for field in ("snapshots", "evidence", "hypotheses", "checks"):
        records[field] = {}
        for index, item in enumerate(packet[field]):
            identifier = item["id"]
            path = f"$.{field}[{index}].id"
            if identifier in records[field]:
                errors.append(("DUPLICATE_ID", path))
            else:
                records[field][identifier] = item

    def reference(identifier, field, path):
        if identifier is not None and identifier not in records[field]:
            errors.append(("DANGLING_REFERENCE", path))

    def references(identifiers, field, path):
        for index, identifier in enumerate(identifiers):
            reference(identifier, field, f"{path}[{index}]")

    references(packet["symptom"]["expected_evidence_ids"], "evidence",
               "$.symptom.expected_evidence_ids")
    reproduction = packet["reproduction"]
    references(reproduction["evidence_ids"], "evidence", "$.reproduction.evidence_ids")
    for index, hypothesis in enumerate(packet["hypotheses"]):
        path = f"$.hypotheses[{index}]"
        supporting = hypothesis["supporting_evidence_ids"]
        opposing = hypothesis["opposing_evidence_ids"]
        references(supporting, "evidence", path + ".supporting_evidence_ids")
        references(opposing, "evidence", path + ".opposing_evidence_ids")
        if set(supporting) & set(opposing):
            errors.append(("CONFLICTING_EVIDENCE", path))
        if hypothesis["status"] == "supported" and not supporting:
            errors.append(("MISSING_SUPPORT", path))
        if hypothesis["status"] == "refuted" and not opposing:
            errors.append(("MISSING_OPPOSITION", path))

    for index, check in enumerate(packet["checks"]):
        path = f"$.checks[{index}]"
        references(check["evidence_ids"], "evidence", path + ".evidence_ids")
        if check["status"] == "completed" and check["observed"] is None:
            errors.append(("MISSING_OBSERVATION", path + ".observed"))
        if check["status"] in ("planned", "not_run"):
            if check["observed"] is not None:
                errors.append(("UNEXECUTED_RESULT", path + ".observed"))
            if check["exit_code"] is not None:
                errors.append(("UNEXECUTED_RESULT", path + ".exit_code"))

    for index, evidence in enumerate(packet["evidence"]):
        path = f"$.evidence[{index}]"
        reference(evidence["snapshot_id"], "snapshots", path + ".snapshot_id")
        check_id = evidence["check_id"]
        reference(check_id, "checks", path + ".check_id")
        if evidence["kind"] == "command_result":
            if check_id is None or (check_id in records["checks"] and
                                    records["checks"][check_id]["status"]
                                    not in ("completed", "interrupted")):
                errors.append(("UNEXECUTED_COMMAND_RESULT", path + ".check_id"))
        if check_id in records["checks"]:
            check = records["checks"][check_id]
            if evidence["id"] not in check["evidence_ids"]:
                errors.append(("CHECK_EVIDENCE_MISMATCH", path + ".check_id"))
            if evidence["kind"] == "observation" and check["status"] in ("planned", "not_run"):
                errors.append(("UNEXECUTED_OBSERVATION", path + ".check_id"))

    disposition = packet["disposition"]
    references(disposition["evidence_ids"], "evidence", "$.disposition.evidence_ids")
    references(disposition["cause_ids"], "hypotheses", "$.disposition.cause_ids")
    if disposition["kind"] in ("confirmed_code_defect", "confirmed_noncode_cause"):
        cited = set(disposition["evidence_ids"])
        for index, identifier in enumerate(disposition["cause_ids"]):
            cause = records["hypotheses"].get(identifier)
            if cause is None:
                continue
            path = f"$.disposition.cause_ids[{index}]"
            if cause["status"] != "supported":
                errors.append(("CAUSE_NOT_SUPPORTED", path))
            if not set(cause["supporting_evidence_ids"]) <= cited:
                errors.append(("CAUSE_EVIDENCE_MISSING", path))

    regression = packet["regression"]
    if regression is not None:
        reference(regression["snapshot_id"], "snapshots", "$.regression.snapshot_id")
        references(regression["evidence_ids"], "evidence", "$.regression.evidence_ids")

    if reproduction["status"] == "reproduced":
        if reproduction["recipe"] is None:
            errors.append(("MISSING_RECIPE", "$.reproduction.recipe"))
        executed = False
        for identifier in reproduction["evidence_ids"]:
            evidence = records["evidence"].get(identifier)
            if evidence is None or evidence["kind"] not in ("observation", "command_result"):
                continue
            check_id = evidence["check_id"]
            if check_id is None and evidence["kind"] == "observation":
                executed = True
            elif (check_id in records["checks"] and
                  records["checks"][check_id]["status"] == "completed"):
                executed = True
        if not executed:
            errors.append(("REPRODUCTION_NOT_OBSERVED", "$.reproduction.evidence_ids"))

    for index, snapshot in enumerate(packet["snapshots"]):
        if ((snapshot["fingerprint"] is None)
                != (snapshot["fingerprint_recipe"] is None)):
            errors.append(("FINGERPRINT_RECIPE_MISMATCH", f"$.snapshots[{index}].fingerprint_recipe"))
        if (snapshot["commit"] is None or snapshot["dirty_state"] == "unknown"
                or snapshot["fingerprint"] is None or snapshot["runtime_identity"] is None):
            if snapshot["limitations"] is None:
                errors.append(("MISSING_IDENTITY_LIMITATION", f"$.snapshots[{index}].limitations"))

    next_step = packet["next_step"]
    target = next_step["target"]
    if target == "none":
        for field in ("owner", "action", "completion_evidence"):
            if next_step[field] is not None:
                errors.append(("UNEXPECTED_NEXT_STEP", "$.next_step." + field))
    else:
        for field in ("action", "completion_evidence"):
            if next_step[field] is None:
                errors.append(("INCOMPLETE_NEXT_STEP", "$.next_step." + field))
        if target == "existing_owner" and next_step["owner"] is None:
            errors.append(("MISSING_OWNER", "$.next_step.owner"))

    outcome = disposition["kind"]
    if outcome in ("confirmed_code_defect", "confirmed_noncode_cause"):
        if not disposition["cause_ids"]:
            errors.append(("MISSING_CAUSE", "$.disposition.cause_ids"))

    if outcome == "confirmed_code_defect":
        if packet["symptom"]["expected"] is None:
            errors.append(("MISSING_EXPECTATION", "$.symptom.expected"))
        if not packet["symptom"]["expected_evidence_ids"]:
            errors.append(("MISSING_EXPECTATION_EVIDENCE", "$.symptom.expected_evidence_ids"))
        if target != "fix":
            errors.append(("WRONG_NEXT_STEP", "$.next_step.target"))
        if regression is None:
            errors.append(("MISSING_REGRESSION", "$.regression"))
    elif regression is not None:
        errors.append(("UNEXPECTED_REGRESSION", "$.regression"))

    if outcome == "confirmed_noncode_cause":
        if target not in ("existing_owner", "evidence"):
            errors.append(("WRONG_NEXT_STEP", "$.next_step.target"))
        if (target == "evidence" and next_step["owner"] is None
                and not any(blocker["owner"] is None for blocker in disposition["blockers"])):
            errors.append(("MISSING_OWNER_ABSENCE", "$.disposition.blockers"))
    elif outcome == "design_question":
        if target not in ("adr", "evidence"):
            errors.append(("WRONG_NEXT_STEP", "$.next_step.target"))
    elif outcome == "no_action":
        if not disposition["evidence_ids"]:
            errors.append(("MISSING_POSITIVE_EVIDENCE", "$.disposition.evidence_ids"))
        if disposition["blockers"]:
            errors.append(("UNEXPECTED_BLOCKER", "$.disposition.blockers"))
        if target != "none":
            errors.append(("WRONG_NEXT_STEP", "$.next_step.target"))
    elif outcome == "unresolved":
        if not disposition["blockers"]:
            errors.append(("MISSING_BLOCKER", "$.disposition.blockers"))
        if target not in ("evidence", "existing_owner"):
            errors.append(("WRONG_NEXT_STEP", "$.next_step.target"))

    if regression is not None and outcome == "confirmed_code_defect":
        if regression["basis"] == "reproduction" and reproduction["status"] != "reproduced":
            errors.append(("REGRESSION_BASIS_MISMATCH", "$.regression.basis"))
        if not regression["evidence_ids"]:
            errors.append(("MISSING_REGRESSION_EVIDENCE", "$.regression.evidence_ids"))
        if regression["basis"] == "reproduction":
            relevant_ids = set(reproduction["evidence_ids"])
            relevant_kinds = ("observation", "command_result")
        else:
            relevant_ids = set(regression["evidence_ids"])
            relevant_kinds = ("source", "observation", "command_result")
        if not any(
            identifier in relevant_ids
            and (evidence := records["evidence"].get(identifier)) is not None
            and evidence["kind"] in relevant_kinds
            and evidence["snapshot_id"] == regression["snapshot_id"]
            for identifier in regression["evidence_ids"]
        ):
            errors.append(("FOREIGN_REGRESSION_SNAPSHOT", "$.regression.snapshot_id"))
        if regression["reuse_existing"]:
            if regression["candidate_test_id"] is None:
                errors.append(("MISSING_EXISTING_TEST_ID", "$.regression.candidate_test_id"))
            # A completed check with no recorded successful exit is only a
            # structural prerequisite. A missing exit may be a direct
            # observation; the host must verify the exact target-red result,
            # not a setup or unrelated failure, against the current baseline.
            cited_completed_check = any(
                evidence["id"] in regression["evidence_ids"]
                and evidence["kind"] in ("observation", "command_result")
                and evidence["coverage"] == "complete_for_claim"
                and evidence["check_id"] in records["checks"]
                and records["checks"][evidence["check_id"]]["status"] == "completed"
                and _not_recorded_success(records["checks"][evidence["check_id"]]["exit_code"])
                for evidence in packet["evidence"]
            )
            if not cited_completed_check:
                errors.append(("MISSING_RECORDED_FAILED_CHECK", "$.regression.evidence_ids"))

    return errors
