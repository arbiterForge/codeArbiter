"""Deterministic T-036 qualification record and evaluator-side oracle checks.

These checks validate local records only. They confer no provider, network,
spending, host, model, or native workflow authority.
"""
import base64
import binascii
import copy
import hashlib
import inspect
import json
import math
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / ".github" / "fixtures" / "debug"
NORMATIVE = "b87fe432639d9a512981c412b2ea38ebf2a07fe8a321ee96cb89fb75cf3ad62e"
D1_CASES_SHA256 = "a6d954ebbdbba797fac8efdece329b5d1ec1fb8d18cc41ea3e9976b0d868c33b"
CASES_SHA256 = "4be10579b809ad8dd378b9c6e23eed55ec5a6efd6d7738650dd1165f976761e9"
PAIRED = {"V01", "V07", "V08", "V11", "V12", "V15", "V17", "V18", "V21", "V23", "V24", "V25", "V26", "V31"}
SAFETY = {"V05", "V06", "V22"}
CRITERION_OBLIGATIONS = {
    "AC-001": {"V01": "M"}, "AC-002": {"V02": "M"}, "AC-003": {"V03": "MH"},
    "AC-004": {"V04": "MH", "V05": "MH"}, "AC-005": {"V06": "MH"},
    "AC-006": {"V07": "M", "V08": "M"},
    "AC-007": {"V09": "MD", "V10": "M", "V39": "D"},
    "AC-008": {"V11": "M"}, "AC-009": {"V12": "M"},
    "AC-010": {"V13": "DM", "V14": "MD", "V37": "DM"},
    "AC-011": {"V15": "MH", "V16": "M"}, "AC-012": {"V17": "MH"},
    "AC-013": {"V18": "M", "V37": "DM"}, "AC-014": {"V19": "DH", "V40": "DH"},
    "AC-015": {"V20": "D", "V38": "DH", "V39": "D"},
    "AC-016": {"V21": "DM", "V22": "DM", "V37": "DM"},
    "AC-017": {"V23": "MH", "V36": "SHM"}, "AC-018": {"V24": "MH", "V38": "DH"},
    "AC-019": {"V25": "MH"}, "AC-020": {"V26": "MH", "V27": "MH"},
    "AC-021": {"V28": "H"}, "AC-022": {"V29": "DH"},
    "AC-023": {"V30": "MD"}, "AC-024": {"V31": "MH", "V36": "SHM"},
    "AC-025": {"V32": "S", "V36": "SHM"}, "AC-026": {"V33": "SDH"},
    "AC-027": {"V34": "DHM", "V41": "DHM"},
    "AC-028": {"V35": "MS", "V41": "DHM"},
}
EXPECTED_EXAMPLE_SHA256 = {'valid-unresolved': 'd56741bbc10c1ac5ae8f58e3f41cc814dfc6d95b1d1c7a1638e67a61e0830f2d', 'valid-code-defect-causal-trace': '17c28b59a2ce1e91c3053a9c7e528c8b68da5ef4016dccb1d38be5e26e5a55bd', 'valid-code-defect-existing-red': '84b5a65d52e44642883ce6f5da8c129bd04f35e53c9cc7c5db9b8c370a32323f', 'valid-noncode-with-authority-blocker': '98fcfbea95b6d0206292e6e3dfbb29f78570aeb22e36c7578dc5f1d953511a38', 'valid-design-question': 'fe0b0bb6d0e36392b874cd294d77895e793a7cb25455314f3bcdf5a3a4a7fe61', 'valid-no-action': '81621fdd52cba8ba9efe7237bba6368d4ea9eef94b1ccd563852583cd7a01f67', 'invalid-unknown-authority-field': '4f52577f08d1861b7a85559fd9a2c105abfb0bd3289d8ef5bd0a97b6180b9659', 'invalid-protocol': '3db9ca34a1ebf963a1d30f92749897d16507b98e3a77111110b2869011983b31', 'invalid-no-action-task': '42ce7970891474209410cbc5a4a07579cf2366cf201ffa879d580150e9747010', 'invalid-boolean-exit-code': '96c259668d97c7f1a56ff47018c27715a39934067da8a60a7b1269e02bfc19f1', 'invalid-dangling-evidence': 'c7b1292cac1343779e5145648748bb456bee1eaf87a1f411bec6a6d0474227e0', 'invalid-duplicate-evidence-id': '0db283f2105c468d4d044d1f372765b70882d3f6cc257e2288f85f09572b90d1', 'invalid-planned-check-as-reproduction': '84389fffb474ec8567aaf021f7449cf628ce2ac3cd0ae7be37814c5275ba4554', 'invalid-conflicting-evidence-reference': '7e73e173272953fc806143d9737fc01e2a6a19cc6679adf8cff367450dc22227'}


def _exact_keys(value, keys):
    return isinstance(value, dict) and set(value) == set(keys)


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value, size):
    return isinstance(value, str) and len(value) == size and all(ch in "0123456789abcdef" for ch in value)


_SYNTHETIC_SESSION_SEQUENCE = 0


def _bounded_nonempty(value, limit=256):
    return isinstance(value, str) and 0 < len(value) <= limit and bool(value.strip())


def _fresh_session(session):
    return (_exact_keys(session, ("id", "launch_id", "initial_turn_count", "resumed_from"))
            and _bounded_nonempty(session["id"])
            and _bounded_nonempty(session["launch_id"])
            and type(session["initial_turn_count"]) is int
            and session["initial_turn_count"] == 0
            and session["resumed_from"] is None)


def _oracle_boundary_tokens(cases):
    """Evaluator-owned finite boundary tokens; no semantic leak detector."""
    try:
        oracles = cases["oracles"]
        if not isinstance(oracles, dict) or not oracles:
            raise ValueError
        tokens = set()
        for oracle in oracles.values():
            if not isinstance(oracle, dict) or not _nonempty(oracle["ground_truth_basis"]):
                raise ValueError
            tokens.add(oracle["ground_truth_basis"])
            for indent in (None, 2):
                tokens.add(json.dumps(oracle, sort_keys=True, indent=indent))
            tokens.add(json.dumps(oracle, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return tokens
    except (KeyError, TypeError, ValueError):
        raise ValueError("invalid hidden oracle boundary")


def _reject_oracle_projection_text(value, tokens):
    if isinstance(value, str) and any(token and token in value for token in tokens):
        raise ValueError("private oracle content in solver projection")


def _check_oracle_projection_boundary(payload, tokens):
    for name, content in payload["files"].items():
        _reject_oracle_projection_text(name, tokens)
        _reject_oracle_projection_text(content, tokens)
    _reject_oracle_projection_text(payload["request"], tokens)
    for observation in payload["observations"]:
        for value in observation.values():
            _reject_oracle_projection_text(value, tokens)


def _tuple_fields(record):
    return {key: record[key] for key in (
        "cell_id", "host", "trial_arm", "normative_sha256", "case_input_sha256", "candidate", "baseline",
        "runtime", "os", "shell", "provider", "model", "settings", "session",
        "permissions", "case_scope", "repetition", "proof_layers")}


def tuple_identity(record):
    """Stable record identity; the hash is correspondence, not authentication."""
    import hashlib
    try:
        data = json.dumps(_tuple_fields(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (KeyError, TypeError, ValueError):
        return ""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def validate_record(record):
    keys = ("cell_id", "host", "trial_arm", "normative_sha256", "case_input_sha256", "candidate", "baseline",
            "runtime", "os", "shell", "provider", "model", "settings",
            "permissions", "case_scope", "repetition", "proof_layers", "session", "outcome",
            "timing_ms", "metering", "evidence")
    if not _exact_keys(record, keys):
        return False
    if not all(_nonempty(record[key]) for key in ("cell_id", "runtime", "os", "shell", "provider", "model")):
        return False
    if record["host"] not in ("claude", "codex") or record["trial_arm"] not in ("candidate", "baseline") or record["normative_sha256"] != NORMATIVE or not _sha(record["case_input_sha256"], 64):
        return False
    for arm in ("candidate", "baseline"):
        value = record[arm]
        if not _exact_keys(value, ("commit", "tree", "package_sha256")):
            return False
        if not (_sha(value["commit"], 40) and _sha(value["tree"], 40) and _sha(value["package_sha256"], 64)):
            return False
    if not isinstance(record["settings"], dict) or not record["settings"]:
        return False
    if not _fresh_session(record["session"]):
        return False
    permission = record["permissions"]
    if not _exact_keys(permission, ("tools", "targets", "network", "spending_usd", "timeout_seconds", "output_bytes")):
        return False
    if not all(isinstance(permission[key], list) and permission[key] and all(_nonempty(item) for item in permission[key]) for key in ("tools", "targets")):
        return False
    if type(permission["network"]) is not bool or type(permission["spending_usd"]) not in (int, float) or not math.isfinite(permission["spending_usd"]) or permission["spending_usd"] < 0:
        return False
    if type(permission["timeout_seconds"]) is not int or not (1 <= permission["timeout_seconds"] <= 3600):
        return False
    if type(permission["output_bytes"]) is not int or not (1 <= permission["output_bytes"] <= 1048576):
        return False
    scope = record["case_scope"]
    if not isinstance(scope, list) or not scope or not all(_nonempty(case) for case in scope) or len(scope) != len(set(scope)):
        return False
    if type(record["repetition"]) is not int or record["repetition"] not in (1, 2, 3):
        return False
    layers = record["proof_layers"]
    if not isinstance(layers, list) or not set(layers).issubset({"D", "H", "M", "S"}) or len(layers) != len(set(layers)) or not layers:
        return False
    if record["outcome"] not in ("passed", "failed", "cancelled", "pending"):
        return False
    timing = record["timing_ms"]
    if timing is not None and (type(timing) not in (int, float) or not math.isfinite(timing) or timing < 0):
        return False
    meter = record["metering"]
    if not (_exact_keys(meter, ("tokens", "cost_usd"))
            or _exact_keys(meter, ("tokens", "cost_usd", "availability"))):
        return False
    has_availability = "availability" in meter
    availability = meter.get("availability")
    if has_availability:
        if not _exact_keys(availability, ("tokens", "cost_usd")):
            return False
        if any(status not in ("observed", "unavailable") for status in availability.values()):
            return False
    for key in ("tokens", "cost_usd"):
        value = meter[key]
        if not has_availability:
            # Without correspondence metadata, zero remains an unknown measurement.
            if value == 0:
                return False
        elif availability[key] == "unavailable":
            if value is not None:
                return False
        elif value is None or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            return False
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            return False
    evidence = record["evidence"]
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if not _exact_keys(item, ("artifact", "layer", "status", "selected", "cancelled", "stale", "observed_at", "subject_sha256")):
            return False
        if not _nonempty(item["artifact"]) or item["layer"] not in ("D", "H", "M", "S") or not _sha(item["subject_sha256"], 64):
            return False
        if item["status"] not in ("passed", "failed", "cancelled", "pending") or type(item["selected"]) is not int or item["selected"] < 0:
            return False
        if type(item["cancelled"]) is not bool or type(item["stale"]) is not bool or not _nonempty(item["observed_at"]):
            return False
    return bool(tuple_identity(record))


def _utc(value):
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _current_cell_matches(record, current_cell):
    """Require the supplied current record to match the retained result."""
    if not validate_record(record) or not validate_record(current_cell):
        return False
    if tuple_identity(record) != tuple_identity(current_cell):
        return False
    return (record["outcome"] == current_cell["outcome"]
            and record["evidence"] == current_cell["evidence"]
            and record["metering"] == current_cell["metering"]
            and record["timing_ms"] == current_cell["timing_ms"])


def _assess_cell_at(record, current_cell, decision, required_scope, now):
    """Check correspondence of supplied records, never genuineness of provenance."""
    if not _current_cell_matches(record, current_cell):
        return False
    if not isinstance(required_scope, list) or not required_scope or record["case_scope"] != required_scope:
        return False
    if record["outcome"] != "passed":
        return False
    if not _exact_keys(decision, ("decision_id", "origin", "cell_id", "tuple_sha256", "case_scope", "permissions", "status", "observed_at", "expires_at")):
        return False
    if not _nonempty(decision["decision_id"]) or decision["origin"] != "observed_user_or_workflow" or decision["status"] != "approved":
        return False
    if decision["cell_id"] != record["cell_id"] or decision["tuple_sha256"] != tuple_identity(record):
        return False
    if decision["case_scope"] != required_scope or decision["permissions"] != record["permissions"]:
        return False
    now_at, observed_at, expiry = _utc(now), _utc(decision["observed_at"]), _utc(decision["expires_at"])
    if None in (now_at, observed_at, expiry) or not (observed_at <= now_at < expiry):
        return False
    evidence = record["evidence"]
    if len(evidence) != len(record["proof_layers"]) or len({item["artifact"] for item in evidence}) != len(evidence):
        return False
    if {item["layer"] for item in evidence} != set(record["proof_layers"]):
        return False
    return all(item["subject_sha256"] == tuple_identity(record) and item["status"] == "passed" and item["selected"] > 0 and not item["cancelled"] and not item["stale"]
               and (stamp := _utc(item["observed_at"])) is not None and observed_at <= stamp <= now_at for item in evidence)


def assess_cell(record, current_cell, decision, required_scope):
    """Use the actual current UTC clock for an individual record check."""
    observed_now_utc = datetime.now(timezone.utc).isoformat()
    return _assess_cell_at(record, current_cell, decision, required_scope, observed_now_utc)


def validate_fixture_bundle(cases=None, cells=None, examples=None):
    """Check the actual pending fixtures and embedded authentic example bytes."""
    try:
        frozen_cases_bytes = (FIXTURES / "cases.json").read_bytes()
        if hashlib.sha256(frozen_cases_bytes).hexdigest() != CASES_SHA256:
            return False
        frozen_cases = json.loads(frozen_cases_bytes.decode("utf-8"))
        if cases is None:
            cases = frozen_cases
        elif json.dumps(cases, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(frozen_cases, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
            return False
        cells = cells if cells is not None else json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
        examples = examples if examples is not None else json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        source_bytes = (ROOT / "docs/proposals/debug-correctness/D1-CASES.json").read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != D1_CASES_SHA256:
            return False
        source = json.loads(source_bytes.decode("utf-8"))
        if cases["format"] != "codearbiter.debug-qualification-cases/1" or cases["status"] != "PREPARATION_ONLY":
            return False
        if cases["paired_ids"] != source["paired_ids"] or cases["candidate_safety_ids"] != source["candidate_safety_ids"]:
            return False
        if cases["repetitions_per_arm_per_configuration"] != source["repetitions_per_arm_per_configuration"]:
            return False
        for scenario, variants in source["pretrial_classification"]["cases"].items():
            for variant, expected in variants.items():
                oracle = cases["oracles"][f"{scenario}/{variant}"]
                for field in ("classification", "expected_disposition", "ground_truth_basis", "product_status"):
                    if oracle[field] != expected[field]:
                        return False
        if [(row["id"], row["layers"], list(row["variants"])) for row in cases["scenario_inventory"]] != [(row["id"], row["layers"], list(row["variants"])) for row in source["scenarios"]]:
            return False
        if cases["independent_oracle_review"] != "PENDING" or cases["actual_trials"] != "PENDING":
            return False
        if set(cases["paired_ids"]) != PAIRED or len(cases["paired_ids"]) != 14 or set(cases["candidate_safety_ids"]) != SAFETY:
            return False
        if len(cases["oracles"]) != 17 or set(cases["oracles"]) != set(cases["solver_inputs"]):
            return False
        if any(item["product_status"] != "PENDING" for item in cases["oracles"].values()):
            return False
        inventory = {item["id"]: item["layers"] for item in cases["scenario_inventory"]}
        if len(inventory) != 41 or set(inventory["V35"]) != {"M", "S"}:
            return False
        for key, oracle in cases["oracles"].items():
            scenario = key.split("/", 1)[0]
            payload = cases["solver_inputs"][key]
            if hashlib.sha256(_input_bytes(payload)).hexdigest() != oracle["input_sha256"]:
                return False
            if set(oracle["required_proof_layers"]) != set(inventory[scenario]) | {"M", "S"}:
                return False
            visible_ids = {item["id"] for item in payload["observations"]}
            if not oracle["required_evidence_ids"] or not set(oracle["required_evidence_ids"]).issubset(visible_ids):
                return False
            if not evaluate_hidden(cases, key, sample_submission(cases, key)):
                return False
        first = cases["oracles"]["V25/supported_target_plus_unrelated_red"]["input_sha256"]
        second = cases["oracles"]["V25/setup_only_without_target_proof"]["input_sha256"]
        if first == second:
            return False
        safety_keys = {f"{item}/default" for item in SAFETY}
        if set(cases["candidate_safety_inputs"]) != safety_keys or set(cases["candidate_safety_sha256"]) != safety_keys:
            return False
        for key, payload in cases["candidate_safety_inputs"].items():
            scenario = key.split("/", 1)[0]
            if hashlib.sha256(_input_bytes(payload)).hexdigest() != cases["candidate_safety_sha256"][key]:
                return False
            if set(cases["candidate_safety_layers"][scenario]) != set(inventory[scenario]):
                return False
        if cells["format"] != "codearbiter.debug-qualification-cells/1" or cells["status"] != "PENDING" or cells["normative_sha256"] != NORMATIVE:
            return False
        if cells["declared_hosts"] != ["claude", "codex"] or cells["live_cells"] != [] or cells["decisions"] != [] or cells["observations"] != []:
            return False
        if set(cells["case_scope"]) != set(cases["oracles"]) or len(cells["case_scope"]) != 17 or set(cells["candidate_safety_scope"]) != SAFETY:
            return False
        if cells["required_repetitions_per_arm_per_configuration"] != 3 or cells["candidate_safety_repetitions"] != 3:
            return False
        if not _exact_keys(cells["permissions"], ("tools", "targets", "network", "spending_usd", "timeout_seconds", "output_bytes")):
            return False
        if any(value is not None for value in cells["permissions"].values()) or cells["timing_ms"] is not None:
            return False
        if cells["metering"] != {"tokens": None, "cost_usd": None}:
            return False
        if examples["format"] != "codearbiter.debug-handoff-examples/1" or examples["status"] != "SOURCE_IDENTITIES_ONLY" or examples["product_status"] != "PENDING":
            return False
        if examples["archive_sha256"] != "78329cd6a9abf2810eb4853b8068f0385837db9ec9d1cb2611662a04c9cf15b3" or examples["original_manifest_sha256"] != "3d42b8835fa7bd8bb8ce067ad24da15ec15b558c862fcf9d030634be48231556":
            return False
        original = ("valid-unresolved", "valid-code-defect-causal-trace", "valid-code-defect-existing-red",
                    "valid-noncode-with-authority-blocker", "valid-design-question", "valid-no-action",
                    "invalid-unknown-authority-field", "invalid-protocol", "invalid-no-action-task",
                    "invalid-boolean-exit-code", "invalid-dangling-evidence", "invalid-duplicate-evidence-id",
                    "invalid-planned-check-as-reproduction", "invalid-conflicting-evidence-reference")
        if tuple(item["id"] for item in examples["examples"]) != original:
            return False
        for item in examples["examples"]:
            if not _exact_keys(item, ("id", "payload_sha256", "expected", "archive_member", "payload_b64")):
                return False
            if item["archive_member"] != "codearbiter-debug-spec/examples/" + item["id"] + ".json":
                return False
            raw = base64.b64decode(item["payload_b64"], validate=True)
            if item["payload_sha256"] != EXPECTED_EXAMPLE_SHA256[item["id"]] or hashlib.sha256(raw).hexdigest() != item["payload_sha256"]:
                return False
            json.loads(raw.decode("utf-8"))
        return True
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, OSError):
        return False


def freeze_design():
    return json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))


def _input_bytes(payload):
    if not _exact_keys(payload, ("request", "files", "observations", "synthetic_only")) or payload["synthetic_only"] is not True:
        raise ValueError("invalid synthetic input")
    if not _nonempty(payload["request"]) or not isinstance(payload["files"], dict) or not payload["files"]:
        raise ValueError("missing synthetic repository")
    if not isinstance(payload["observations"], list) or not payload["observations"]:
        raise ValueError("missing synthetic observations")
    reserved = {"cases.json", "handoff-examples.json", "qualification-cells.json", "test_debug_qualification.py"}
    devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    devices |= {f"COM{index}" for index in range(1, 10)}
    devices |= {f"LPT{index}" for index in range(1, 10)}
    devices |= {"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
    canonical_paths = {}
    parent_spellings = {}
    for path, content in payload["files"].items():
        if not _nonempty(path) or "\\" in path or ":" in path or not isinstance(content, str):
            raise ValueError("invalid synthetic source path")
        normalized = PurePosixPath(path)
        parts = normalized.parts
        if normalized.is_absolute() or normalized.as_posix() != path or not parts or any(part in (".", "..") for part in parts):
            raise ValueError("invalid synthetic source path")
        if any(any(ord(character) < 32 or character in '<>"|?*' for character in part) for part in parts):
            raise ValueError("invalid synthetic source path")
        if any(part.endswith((" ", ".")) for part in parts):
            raise ValueError("invalid synthetic source path")
        for part in parts:
            short_stem, dot, short_extension = part.partition(".")
            if "~" in short_stem and short_stem.count("~") == 1:
                short_prefix, short_ordinal = short_stem.split("~")
                short_charset = "!#$%&'()-@^_`{}~"
                if (
                    len(short_stem) <= 8
                    and 1 <= len(short_prefix) <= 6
                    and 1 <= len(short_ordinal) <= 6
                    and short_ordinal.isascii()
                    and short_ordinal.isdecimal()
                    and all(character.isascii() and (character.isalnum() or character in short_charset)
                            for character in short_prefix)
                    and (not dot or (1 <= len(short_extension) <= 3
                                     and all(character.isascii() and (character.isalnum() or character in short_charset)
                                             for character in short_extension)))
                ):
                    raise ValueError("invalid synthetic source path")
            stem = part.rstrip(" .").split(".", 1)[0].rstrip(" ")
            if stem.casefold() in {item.casefold() for item in devices}:
                raise ValueError("invalid synthetic source path")
        if parts[0].rstrip(" .").lower() == "input.json":
            raise ValueError("projection metadata name in solver source")
        if parts[-1].rstrip(" .").casefold() in {item.casefold() for item in reserved}:
            raise ValueError("evaluator name in solver source")
        canonical = tuple(part.casefold() for part in parts)
        if canonical in canonical_paths:
            raise ValueError("invalid synthetic source path")
        canonical_paths[canonical] = path
        for index in range(1, len(parts)):
            parent_key = canonical[:index]
            spelling = tuple(parts[:index])
            prior = parent_spellings.get(parent_key)
            if prior is not None and prior != spelling:
                raise ValueError("invalid synthetic source path")
            parent_spellings[parent_key] = spelling
    canonical_set = set(canonical_paths)
    if any(any(canonical[:index] in canonical_set for index in range(1, len(canonical))) for canonical in canonical_set):
        raise ValueError("invalid synthetic source path")
    if len({item.get("id") for item in payload["observations"] if isinstance(item, dict)}) != len(payload["observations"]):
        raise ValueError("duplicate synthetic observation")
    for item in payload["observations"]:
        if not _exact_keys(item, ("id", "kind", "detail")) or not all(_nonempty(item[field]) for field in ("id", "kind", "detail")):
            raise ValueError("invalid synthetic observation")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def solver_projection(cases, destination):
    """Materialize only synthetic repository files and problem observations."""
    if set(cases["solver_inputs"]) != set(cases["oracles"]):
        raise ValueError("unpaired evaluator inputs")
    boundary_tokens = _oracle_boundary_tokens(cases)
    payloads = []
    for key in sorted(cases["solver_inputs"]):
        payload = cases["solver_inputs"][key]
        _input_bytes(payload)
        _check_oracle_projection_boundary(payload, boundary_tokens)
        payloads.append(payload)
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("solver destination must be an empty directory")
    written = []
    for number, payload in enumerate(payloads, 1):
        folder = destination / f"trial-{number:04d}"
        folder.mkdir()
        metadata = {"request": payload["request"], "observations": payload["observations"], "synthetic_only": True}
        input_path = folder / "input.json"
        input_path.write_text(json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        for name, content in payload["files"].items():
            file_path = folder.joinpath(*Path(name).parts)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8", newline="\n")
        written.append(input_path)
    return written


def evaluate_hidden(cases, case_key, submission):
    """Run finite evaluator controls; causal sufficiency still needs review."""
    oracle = cases["oracles"].get(case_key)
    payload = cases["solver_inputs"].get(case_key)
    if not oracle or oracle.get("product_status") != "PENDING" or not _exact_keys(submission, ("disposition", "evidence_ids", "action", "effects", "input_sha256")):
        return False
    try:
        input_sha256 = hashlib.sha256(_input_bytes(payload)).hexdigest()
    except (TypeError, ValueError, KeyError):
        return False
    if input_sha256 != oracle.get("input_sha256") or submission["input_sha256"] != input_sha256:
        return False
    observed = {item["id"]: item["kind"] for item in payload["observations"]}
    needed = oracle.get("required_evidence_ids")
    if not isinstance(needed, list) or not needed or any(item not in observed for item in needed):
        return False
    required_kind = oracle.get("required_observation_kind")
    required_id = oracle.get("required_observation_id")
    if required_kind is not None or required_id is not None:
        if not _nonempty(required_kind) or not _nonempty(required_id) or required_id not in needed or observed.get(required_id) != required_kind:
            return False
    if case_key.startswith("V25/"):
        if required_kind is None:
            return False
        kinds = set(observed.values())
        if ("target_assertion_failure" in kinds) == ("setup_import_error" in kinds):
            return False
    return (submission["disposition"] == oracle.get("expected_disposition")
            and submission["evidence_ids"] == needed
            and submission["action"] == oracle.get("permitted_action")
            and submission["effects"] == [])


def sample_submission(cases, key):
    """Synthetic positive control only; never a model or host observation."""
    oracle = cases["oracles"][key]
    return {"disposition": oracle["expected_disposition"], "evidence_ids": list(oracle["required_evidence_ids"]),
            "action": oracle["permitted_action"], "effects": [], "input_sha256": oracle["input_sha256"]}

def campaign_complete(samples, cases, configuration):
    """Require every declared arm and repetition for one exact configuration."""
    if not isinstance(samples, list) or not _exact_keys(configuration, ("host", "runtime", "provider", "model", "settings")):
        return False
    if set(cases.get("paired_ids", [])) != PAIRED or set(cases.get("candidate_safety_ids", [])) != SAFETY:
        return False
    if cases.get("repetitions_per_arm_per_configuration") != 3 or cases.get("candidate_safety_repetitions") != 3:
        return False
    paired_keys = set(cases.get("oracles", {}))
    if len(paired_keys) != 17 or {key.split("/")[0] for key in paired_keys} != PAIRED:
        return False
    expected = {(key, arm, repeat) for key in paired_keys for arm in ("baseline", "candidate") for repeat in (1, 2, 3)}
    expected |= {(f"{scenario}/default", "candidate", repeat) for scenario in SAFETY for repeat in (1, 2, 3)}
    inventory = {row["id"]: row["layers"] for row in cases.get("scenario_inventory", [])}
    if set(inventory.get("V35", [])) != {"M", "S"}:
        return False
    observed = set()
    session_ids = set()
    launch_ids = set()
    cohort_candidate = None
    cohort_baseline = None
    observation_time_utc = datetime.now(timezone.utc).isoformat()
    if len(samples) != len(expected):
        return False
    for item in samples:
        if not _exact_keys(item, ("case_key", "arm", "record", "current", "decision")):
            return False
        record = item["record"]
        if not isinstance(record, dict):
            return False
        case_key = item["case_key"]
        arm = item["arm"]
        repetition = record.get("repetition")
        if (type(case_key) is not str or type(arm) is not str
                or type(repetition) is not int or repetition not in (1, 2, 3)
                or arm not in ("baseline", "candidate")):
            return False
        if cohort_candidate is None:
            cohort_candidate, cohort_baseline = record.get("candidate"), record.get("baseline")
            if cohort_candidate == cohort_baseline:
                return False
        if record.get("candidate") != cohort_candidate or record.get("baseline") != cohort_baseline:
            return False
        session = record.get("session")
        if not _fresh_session(session):
            return False
        if session["id"] in session_ids or session["launch_id"] in launch_ids:
            return False
        session_ids.add(session["id"])
        launch_ids.add(session["launch_id"])
        if not isinstance(record, dict) or record.get("trial_arm") != arm or record.get("case_scope") != [case_key]:
            return False
        key = (case_key, arm, repetition)
        if key not in expected or key in observed:
            return False
        observed.add(key)
        scenario = case_key.split("/", 1)[0]
        if scenario not in inventory:
            return False
        expected_layers = set(inventory[scenario]) | ({"M", "S"} if item["case_key"] in paired_keys else set())
        configured_layers = (cases["oracles"][item["case_key"]]["required_proof_layers"]
                             if item["case_key"] in paired_keys else cases["candidate_safety_layers"][scenario])
        if set(configured_layers) != expected_layers or set(record["proof_layers"]) != expected_layers:
            return False
        if item["case_key"] in paired_keys:
            source_input = cases["solver_inputs"][item["case_key"]]
            expected_input_sha = cases["oracles"][item["case_key"]]["input_sha256"]
        else:
            source_input = cases["candidate_safety_inputs"][item["case_key"]]
            expected_input_sha = cases["candidate_safety_sha256"][item["case_key"]]
        if hashlib.sha256(_input_bytes(source_input)).hexdigest() != expected_input_sha or record["case_input_sha256"] != expected_input_sha:
            return False
        if any(record.get(field) != value for field, value in configuration.items()):
            return False
        if not _assess_cell_at(record, item["current"], item["decision"], [item["case_key"]], observation_time_utc):
            return False
    return observed == expected


def sample_record(host="claude", arm="candidate", layers=("D", "H", "M")):
    global _SYNTHETIC_SESSION_SEQUENCE
    _SYNTHETIC_SESSION_SEQUENCE += 1
    session_suffix = str(_SYNTHETIC_SESSION_SEQUENCE)
    candidate_identity = {"commit": "a" * 40, "tree": "b" * 40, "package_sha256": "c" * 64}
    baseline_identity = {"commit": "d" * 40, "tree": "e" * 40, "package_sha256": "f" * 64}
    record = {
        "cell_id": host + ":synthetic-1", "host": host, "trial_arm": arm, "normative_sha256": NORMATIVE,
        "case_input_sha256": freeze_design()["oracles"]["V01/default"]["input_sha256"],
        "candidate": copy.deepcopy(candidate_identity), "baseline": copy.deepcopy(baseline_identity),
        "runtime": "synthetic-runtime/1", "os": "windows", "shell": "pwsh/7",
        "provider": "synthetic-provider", "model": "synthetic-model",
        "settings": {"temperature": 0},
        "session": {"id": "synthetic-session:" + host + ":" + session_suffix,
                    "launch_id": "synthetic-launch:" + host + ":" + session_suffix,
                    "initial_turn_count": 0, "resumed_from": None},
        "permissions": {"tools": ["read"], "targets": ["synthetic-only"], "network": False, "spending_usd": 0, "timeout_seconds": 60, "output_bytes": 8192},
        "case_scope": ["V01/default"], "repetition": 1,
        "proof_layers": list(layers), "outcome": "passed",
        "timing_ms": None, "metering": {"tokens": None, "cost_usd": None},
        "evidence": [
            {"artifact": "synthetic-" + layer, "layer": layer, "status": "passed", "selected": 1,
             "cancelled": False, "stale": False, "observed_at": "2026-09-28T00:00:00Z"}
            for layer in layers
        ],
    }
    for item in record["evidence"]:
        item["subject_sha256"] = tuple_identity(record)
    return record


def sample_decision(record):
    return {
        "decision_id": "synthetic-external-decision", "origin": "observed_user_or_workflow",
        "cell_id": record["cell_id"], "tuple_sha256": tuple_identity(record),
        "case_scope": copy.deepcopy(record["case_scope"]),
        "permissions": copy.deepcopy(record["permissions"]),
        "status": "approved", "observed_at": "2026-09-28T00:00:00Z",
        "expires_at": "2030-09-29T00:00:00Z",
    }


def sample_campaign(cases, host="claude"):
    """Synthetic record controls; these are not executed host trials."""
    samples = []
    paired = ((key, arm, repeat) for key in cases["oracles"]
              for arm in ("baseline", "candidate") for repeat in (1, 2, 3))
    safety = ((f"{scenario}/default", "candidate", repeat)
              for scenario in sorted(SAFETY) for repeat in (1, 2, 3))
    for key, arm, repeat in (*paired, *safety):
        scenario = key.split("/", 1)[0]
        paired_case = key in cases["oracles"]
        layers = (cases["oracles"][key]["required_proof_layers"] if paired_case
                  else cases["candidate_safety_layers"][scenario])
        record = sample_record(host=host, arm=arm, layers=layers)
        record["cell_id"] = f"{host}:{key}:{arm}:{repeat}"
        record["case_scope"] = [key]
        record["case_input_sha256"] = (cases["oracles"][key]["input_sha256"] if paired_case
                                       else cases["candidate_safety_sha256"][key])
        record["repetition"] = repeat
        record["session"] = {
            "id": f"synthetic-session:{host}:{key}:{arm}:{repeat}",
            "launch_id": f"synthetic-launch:{host}:{key}:{arm}:{repeat}",
            "initial_turn_count": 0, "resumed_from": None,
        }
        for evidence in record["evidence"]:
            evidence["subject_sha256"] = tuple_identity(record)
        samples.append({"case_key": key, "arm": arm, "record": record,
                        "current": copy.deepcopy(record), "decision": sample_decision(record)})
    return samples


def record_binding(row):
    """Correspondence digest for supplied identities and records, not run authentication."""
    try:
        value = {key: row[key] for key in ("criterion", "case_key", "layer", "record",
                                            "run_id", "source_sha256", "tests_sha256",
                                            "artifact_sha256")}
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
    except (KeyError, TypeError, ValueError, UnicodeError):
        return ""


def criterion_records_ready(rows, cases, current_source, current_tests, current_head,
                            required_configurations, campaigns, required_ci, ci_results,
                            known_failures, artifact_bytes):
    """Reconcile supplied records only; execution and CI provenance require external verification."""
    if not isinstance(current_source, bytes) or not current_source or not isinstance(current_tests, bytes) or not current_tests:
        return False
    if not _sha(current_head, 40) or not validate_fixture_bundle(cases=cases):
        return False
    inventory = {item["id"]: item for item in cases["scenario_inventory"]}
    if len(inventory) != 41 or set(inventory) != {f"V{number:02d}" for number in range(1, 42)}:
        return False
    designated_input_sha256 = {
        key: hashlib.sha256(_input_bytes(payload)).hexdigest()
        for inputs in (cases["solver_inputs"], cases["candidate_safety_inputs"])
        for key, payload in inputs.items()
    }
    if len(CRITERION_OBLIGATIONS) != 28 or set(CRITERION_OBLIGATIONS) != {f"AC-{number:03d}" for number in range(1, 29)}:
        return False
    expected_base = set()
    for criterion, scenarios in CRITERION_OBLIGATIONS.items():
        for scenario, layers in scenarios.items():
            if scenario not in inventory or set(layers) != set(inventory[scenario]["layers"]) or len(layers) != len(set(layers)):
                return False
            for variant in inventory[scenario]["variants"] or ["default"]:
                expected_base.update((criterion, f"{scenario}/{variant}", layer) for layer in layers)
    if {scenario for scenarios in CRITERION_OBLIGATIONS.values() for scenario in scenarios} != set(inventory):
        return False
    expected_case_keys = {case_key for _, case_key, _ in expected_base}
    source_sha = hashlib.sha256(current_source).hexdigest()
    tests_sha = hashlib.sha256(current_tests).hexdigest()
    if not isinstance(required_ci, list) or not required_ci or not all(_nonempty(name) for name in required_ci) or len(required_ci) != len(set(required_ci)):
        return False
    if not isinstance(ci_results, list) or len(ci_results) != len(required_ci):
        return False
    seen_ci = set()
    for result in ci_results:
        if not _exact_keys(result, ("name", "status", "selected", "cancelled", "head", "source_sha256", "tests_sha256")):
            return False
        if result["name"] not in required_ci or result["name"] in seen_ci:
            return False
        seen_ci.add(result["name"])
        if (result["status"] != "passed" or type(result["selected"]) is not int or result["selected"] <= 0
                or result["cancelled"] is not False or result["head"] != current_head
                or result["source_sha256"] != source_sha or result["tests_sha256"] != tests_sha):
            return False
    if not isinstance(required_configurations, list) or not required_configurations or not isinstance(campaigns, list) or len(campaigns) != len(required_configurations):
        return False
    try:
        config_keys = [json.dumps(config, sort_keys=True, allow_nan=False) for config in required_configurations]
    except (TypeError, ValueError):
        return False
    if len(set(config_keys)) != len(config_keys) or {config.get("host") for config in required_configurations if isinstance(config, dict)} != {"claude", "codex"}:
        return False
    seen_campaigns = set()
    for campaign in campaigns:
        if not _exact_keys(campaign, ("configuration", "samples", "status")) or campaign["status"] != "passed":
            return False
        try:
            key = json.dumps(campaign["configuration"], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return False
        if key not in config_keys or key in seen_campaigns or not campaign_complete(campaign["samples"], cases, campaign["configuration"]):
            return False
        if any(item["record"]["candidate"]["commit"] != current_head for item in campaign["samples"]):
            return False
        seen_campaigns.add(key)
    expected = {(criterion, case_key, layer, config_key)
                for criterion, case_key, layer in expected_base
                for config_key in (config_keys if layer in ("H", "M") else ("source",))}
    if (not isinstance(rows, list) or not isinstance(artifact_bytes, dict)
            or not isinstance(known_failures, list) or not all(_nonempty(name) for name in known_failures)
            or len(known_failures) != len(set(known_failures))):
        return False
    seen_runs, failures, passes = set(), {}, set()
    observations = {}
    seen_artifacts = set()
    retained_failures = set()
    for row in rows:
        if not _exact_keys(row, ("criterion", "case_key", "layer", "record", "current", "decision",
                                 "run_id", "source_sha256", "tests_sha256", "artifact_sha256",
                                 "binding_sha256")):
            return False
        record = row["record"]
        if not _current_cell_matches(record, row["current"]):
            return False
        case_key = row["case_key"]
        if not _bounded_nonempty(case_key) or case_key not in expected_case_keys:
            return False
        expected_input_sha256 = designated_input_sha256.get(case_key)
        if (expected_input_sha256 is not None
                and record["case_input_sha256"] != expected_input_sha256):
            return False
        if row["layer"] in ("H", "M"):
            cell_configuration = {field: record[field] for field in ("host", "runtime", "provider", "model", "settings")}
            try:
                cell_key = json.dumps(cell_configuration, sort_keys=True, allow_nan=False)
            except (TypeError, ValueError):
                return False
        else:
            cell_key = "source"
        obligation = (row["criterion"], row["case_key"], row["layer"], cell_key)
        if (obligation not in expected or not _nonempty(row["run_id"]) or row["run_id"] in seen_runs
                or row["binding_sha256"] != record_binding(row)
                or not _sha(row["source_sha256"], 64) or not _sha(row["tests_sha256"], 64)
                or not _sha(row["artifact_sha256"], 64)
                or record["case_scope"] != [row["case_key"]] or record["proof_layers"] != [row["layer"]]):
            return False
        seen_runs.add(row["run_id"])
        stamps = [_utc(item["observed_at"]) for item in record["evidence"]]
        if len(stamps) != 1 or stamps[0] is None:
            return False
        evidence = record["evidence"][0]
        artifact = evidence["artifact"]
        raw = artifact_bytes.get(artifact)
        if artifact in seen_artifacts or type(raw) is not bytes or not raw or len(raw) > 4096:
            return False
        seen_artifacts.add(artifact)
        expected_proof = {"format": "codearbiter.debug-qualification-proof/1",
                          "run_id": row["run_id"], "criterion": row["criterion"],
                          "case_key": row["case_key"], "layer": row["layer"],
                          "cell_id": record["cell_id"], "artifact": artifact,
                          "head": record["candidate"]["commit"],
                          "source_sha256": row["source_sha256"],
                          "tests_sha256": row["tests_sha256"],
                          "outcome": record["outcome"], "observed_at": evidence["observed_at"]}
        try:
            proof = json.loads(raw.decode("utf-8"))
            canonical = json.dumps(proof, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            return False
        if (raw != canonical or hashlib.sha256(raw).hexdigest() != row["artifact_sha256"]
                or not _exact_keys(proof, (*expected_proof, "result"))
                or any(proof[key] != value for key, value in expected_proof.items())):
            return False
        body = proof["result"]
        body_subject = {"criterion": row["criterion"], "case_key": row["case_key"],
                        "layer": row["layer"], "cell_id": record["cell_id"],
                        "head": record["candidate"]["commit"],
                        "source_sha256": row["source_sha256"],
                        "tests_sha256": row["tests_sha256"]}
        if (not _exact_keys(body, (*body_subject, "selected_assertion_ids", "selected_count",
                                   "status", "exit_code", "cancelled", "output_b64"))
                or any(body[key] != value for key, value in body_subject.items())):
            return False
        selected_ids = body["selected_assertion_ids"]
        if (not isinstance(selected_ids, list) or not selected_ids
                or not all(_nonempty(value) for value in selected_ids)
                or len(selected_ids) != len(set(selected_ids))
                or type(body["selected_count"]) is not int
                or body["selected_count"] != len(selected_ids)
                or body["selected_count"] != evidence["selected"]
                or body["status"] != record["outcome"] or body["status"] != evidence["status"]
                or type(body["exit_code"]) is not int
                or (body["exit_code"] == 0) != (record["outcome"] == "passed")
                or body["cancelled"] is not False or evidence["cancelled"] is not False):
            return False
        try:
            output = base64.b64decode(body["output_b64"], validate=True)
        except (TypeError, ValueError, binascii.Error):
            return False
        if (not output or len(output) > 8192
                or base64.b64encode(output).decode("ascii") != body["output_b64"]):
            return False
        body_raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8")
        body_digest = hashlib.sha256(body_raw).hexdigest()
        output_digest = hashlib.sha256(output).hexdigest()
        observations.setdefault(obligation, []).append((stamps[0], body_digest, output_digest))
        if record["outcome"] == "failed":
            if record["evidence"][0]["status"] != "failed":
                return False
            retained_failures.add(row["run_id"])
            failures[obligation] = max(failures.get(obligation, stamps[0]), stamps[0])
        elif record["outcome"] == "passed":
            if (record["candidate"]["commit"] != current_head
                    or row["source_sha256"] != source_sha or row["tests_sha256"] != tests_sha
                    or not _assess_cell_at(record, row["current"], row["decision"],
                                           [row["case_key"]], datetime.now(timezone.utc).isoformat())):
                return False
            passes.add((obligation, stamps[0], body_digest, output_digest))
        else:
            return False
    if retained_failures != set(known_failures) or seen_artifacts != set(artifact_bytes):
        return False
    return all(any(key == obligation and (obligation not in failures or
                       (stamp > failures[obligation] and all(
                           prior_stamp > failures[obligation] or
                           (body_digest != prior_body and output_digest != prior_output)
                           for prior_stamp, prior_body, prior_output in observations[obligation])))
                   for key, stamp, body_digest, output_digest in passes) for obligation in expected)


def release_handoff_ready(handoff, qualification, smoke_bytes):
    """Check supplied handoff correspondence; an external owner must authenticate runs."""
    qualification_keys = ("rows", "cases", "current_source", "current_tests", "current_head",
                          "required_configurations", "campaigns", "required_ci", "ci_results",
                          "known_failures", "artifact_bytes")
    if not _exact_keys(qualification, qualification_keys):
        return False
    if not criterion_records_ready(*(qualification[key] for key in qualification_keys)):
        return False
    if not _exact_keys(handoff, ("candidate", "head", "source_sha256", "tests_sha256",
                                 "cells", "smoke_sha256")):
        return False
    candidate = handoff["candidate"]
    if not _exact_keys(candidate, ("commit", "tree", "package_sha256")):
        return False
    if not all(_sha(candidate[key], size) for key, size in (("commit", 40), ("tree", 40),
                                                             ("package_sha256", 64))):
        return False
    if (handoff["head"] != qualification["current_head"] or candidate["commit"] != handoff["head"]
            or handoff["source_sha256"] != hashlib.sha256(qualification["current_source"]).hexdigest()
            or handoff["tests_sha256"] != hashlib.sha256(qualification["current_tests"]).hexdigest()):
        return False
    rows = qualification["rows"]
    expected_cells = {row["run_id"]: {"cell_id": row["record"]["cell_id"],
                                      "tuple_sha256": tuple_identity(row["record"]),
                                      "artifact_sha256": row["artifact_sha256"]} for row in rows}
    if (not rows or any(row["record"]["candidate"] != candidate for row in rows)
            or handoff["cells"] != expected_cells):
        return False
    if (not isinstance(smoke_bytes, bytes) or not smoke_bytes or len(smoke_bytes) > 8192
            or hashlib.sha256(smoke_bytes).hexdigest() != handoff["smoke_sha256"]):
        return False
    try:
        smoke = json.loads(smoke_bytes.decode("utf-8"))
        canonical = json.dumps(smoke, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return False
    if (canonical != smoke_bytes or not _exact_keys(smoke, ("format", "candidate", "head",
                                                    "environment", "result"))
            or smoke["format"] != "codearbiter.debug-release-smoke/1"
            or smoke["candidate"] != candidate or smoke["head"] != handoff["head"]):
        return False
    environment = smoke["environment"]
    if not _exact_keys(environment, ("host", "runtime", "provider", "model", "settings", "os", "shell")):
        return False
    if (not all(_nonempty(environment[key]) for key in ("host", "runtime", "provider", "model", "os", "shell"))
            or not isinstance(environment["settings"], dict)):
        return False
    config = {key: environment[key] for key in ("host", "runtime", "provider", "model", "settings")}
    if (config not in qualification["required_configurations"]
            or not any(row["layer"] in ("H", "M") and
                       all(row["record"][key] == value for key, value in environment.items())
                       for row in rows)):
        return False
    result = smoke["result"]
    if not _exact_keys(result, ("status", "exit_code", "cancelled", "selected_assertion_ids",
                                "selected_count", "output_b64", "output_sha256")):
        return False
    selected = result["selected_assertion_ids"]
    if (result["status"] != "passed" or type(result["exit_code"]) is not int
            or result["exit_code"] != 0 or result["cancelled"] is not False
            or not isinstance(selected, list) or not selected
            or not all(_nonempty(name) for name in selected) or len(selected) != len(set(selected))
            or type(result["selected_count"]) is not int or result["selected_count"] != len(selected)):
        return False
    try:
        output = base64.b64decode(result["output_b64"], validate=True)
    except (TypeError, ValueError, binascii.Error):
        return False
    return (bool(output) and len(output) <= 8192
            and base64.b64encode(output).decode("ascii") == result["output_b64"]
            and hashlib.sha256(output).hexdigest() == result["output_sha256"])


def rollback_handoff_ready(plan):
    """Check a proposed coupled rollback without applying it or discarding history."""
    if not _exact_keys(plan, ("owned_changes", "rollback_changes", "historical_evidence_ids",
                              "preserved_evidence_ids", "independent_consolidation_paths",
                              "retired_wrapper_paths")):
        return False
    roles = ("producer", "validator", "consumer", "helper", "generated")
    owned, reverted = plan["owned_changes"], plan["rollback_changes"]
    if not _exact_keys(owned, roles) or not _exact_keys(reverted, roles) or owned != reverted:
        return False
    if not all(isinstance(owned[role], list) and owned[role] for role in roles):
        return False
    paths = [path for role in roles for path in owned[role]]
    protected = plan["independent_consolidation_paths"]
    retired = plan["retired_wrapper_paths"]
    history = plan["historical_evidence_ids"]
    preserved = plan["preserved_evidence_ids"]
    if not all(isinstance(items, list) and items and all(_nonempty(value) for value in items)
               and len(items) == len(set(items)) for items in (paths, protected, retired, history, preserved)):
        return False
    if any(PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts or ":" in path
           for path in (*paths, *protected, *retired)):
        return False
    return set(paths).isdisjoint(protected) and set(paths).isdisjoint(retired) and set(history) == set(preserved)


class QualificationTest(unittest.TestCase):
    def shortDescription(self):
        return None

    def _synthetic_proof_bytes(self, row, result_body):
        record = row["record"]
        evidence = record["evidence"][0]
        fields = {"format": "codearbiter.debug-qualification-proof/1",
                  "run_id": row["run_id"], "criterion": row["criterion"],
                  "case_key": row["case_key"], "layer": row["layer"],
                  "cell_id": record["cell_id"], "artifact": evidence["artifact"],
                  "head": record["candidate"]["commit"],
                  "source_sha256": row["source_sha256"],
                  "tests_sha256": row["tests_sha256"],
                  "outcome": record["outcome"], "observed_at": evidence["observed_at"],
                  "result": result_body}
        return json.dumps(fields, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def _criterion_control(self):
        cases = freeze_design()
        inventory = {item["id"]: item for item in cases["scenario_inventory"]}
        designated_inputs = {**cases["solver_inputs"], **cases["candidate_safety_inputs"]}
        source, tests, head = b"reviewed source A", b"reviewed tests A", "a" * 40
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        required = [dict(configuration), {**configuration, "host": "codex"}]
        rows = []
        artifacts = {}
        for criterion, scenarios in CRITERION_OBLIGATIONS.items():
            for scenario, layers in scenarios.items():
                for variant in inventory[scenario]["variants"] or ["default"]:
                    case_key = f"{scenario}/{variant}"
                    for layer in layers:
                        for index, config in enumerate(required if layer in ("H", "M") else required[:1]):
                            record = sample_record(host=config["host"], layers=[layer])
                            record.update(config)
                            record["cell_id"] = f"{criterion}:{case_key}:{layer}:{index}"
                            record["case_scope"] = [case_key]
                            if case_key in designated_inputs:
                                record["case_input_sha256"] = hashlib.sha256(
                                    _input_bytes(designated_inputs[case_key])).hexdigest()
                            for evidence in record["evidence"]:
                                evidence["artifact"] = f"synthetic:{record['cell_id']}:proof"
                                evidence["subject_sha256"] = tuple_identity(record)
                            row = {"criterion": criterion, "case_key": case_key, "layer": layer,
                                   "record": record, "current": copy.deepcopy(record),
                                   "decision": sample_decision(record), "run_id": record["cell_id"],
                                   "source_sha256": hashlib.sha256(source).hexdigest(),
                                   "tests_sha256": hashlib.sha256(tests).hexdigest()}
                            result_body = {"criterion": criterion, "case_key": case_key,
                                           "layer": layer, "cell_id": record["cell_id"],
                                           "head": head, "source_sha256": hashlib.sha256(source).hexdigest(),
                                           "tests_sha256": hashlib.sha256(tests).hexdigest(),
                                           "selected_assertion_ids": [f"SYNTH-{len(rows) + 1}"],
                                           "selected_count": 1, "status": "passed", "exit_code": 0,
                                           "cancelled": False,
                                           "output_b64": base64.b64encode(
                                               f"synthetic observed result {len(rows) + 1}".encode()).decode("ascii")}
                            proof = self._synthetic_proof_bytes(row, result_body)
                            artifacts[record["evidence"][0]["artifact"]] = proof
                            row["artifact_sha256"] = hashlib.sha256(proof).hexdigest()
                            row["binding_sha256"] = record_binding(row)
                            rows.append(row)
        campaigns = [{"configuration": item, "samples": sample_campaign(cases, item["host"]),
                      "status": "passed"} for item in required]
        ci = [{"name": "required-debug-suite", "status": "passed", "selected": 29,
               "cancelled": False, "head": head,
               "source_sha256": hashlib.sha256(source).hexdigest(),
               "tests_sha256": hashlib.sha256(tests).hexdigest()}]
        return cases, rows, source, tests, head, required, campaigns, ci, artifacts

    def test_every_criterion_has_current_evidence_at_each_required_layer(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        self.assertEqual(len(CRITERION_OBLIGATIONS), 28)
        self.assertEqual(sum(len(scenarios) for scenarios in CRITERION_OBLIGATIONS.values()), 48)
        self.assertTrue({("AC-013", "V37"), ("AC-015", "V39"), ("AC-016", "V37"),
                         ("AC-018", "V38"), ("AC-024", "V36"), ("AC-025", "V36"),
                         ("AC-028", "V41")}.issubset({(criterion, scenario)
                                                       for criterion, scenarios in CRITERION_OBLIGATIONS.items()
                                                       for scenario in scenarios}))
        self.assertEqual({scenario for mapping in CRITERION_OBLIGATIONS.values()
                          for scenario in mapping}, {f"V{number:02d}" for number in range(1, 42)})
        self.assertTrue(criterion_records_ready(rows, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        first_artifact = rows[0]["record"]["evidence"][0]["artifact"]
        for field, value in (("selected_assertion_ids", []), ("selected_count", 0),
                             ("status", "pending"), ("exit_code", 1), ("cancelled", True),
                             ("case_key", "V07/default"), ("head", "b" * 40),
                             ("source_sha256", "0" * 64), ("tests_sha256", "0" * 64),
                             ("output_b64", "")):
            with self.subTest(result_field=field):
                changed_rows = copy.deepcopy(rows)
                changed_artifacts = dict(artifacts)
                payload = json.loads(changed_artifacts[first_artifact].decode("utf-8"))
                payload["result"][field] = value
                changed_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False, allow_nan=False).encode("utf-8")
                changed_artifacts[first_artifact] = changed_bytes
                changed_rows[0]["artifact_sha256"] = hashlib.sha256(changed_bytes).hexdigest()
                changed_rows[0]["binding_sha256"] = record_binding(changed_rows[0])
                self.assertFalse(criterion_records_ready(changed_rows, cases, source, tests, head,
                                                         required, campaigns, ["required-debug-suite"], ci,
                                                         [], changed_artifacts))
        for criterion, scenarios in CRITERION_OBLIGATIONS.items():
            for scenario in scenarios:
                with self.subTest(criterion=criterion, scenario=scenario):
                    omitted = [row for row in rows if not (row["criterion"] == criterion
                               and row["case_key"].split("/", 1)[0] == scenario)]
                    self.assertFalse(criterion_records_ready(omitted, cases, source, tests, head,
                                                             required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        self.assertFalse(criterion_records_ready(rows[:-1], cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        codex_model = next(index for index, row in enumerate(rows)
                           if row["layer"] == "M" and row["record"]["host"] == "codex")
        self.assertFalse(criterion_records_ready(rows[:codex_model] + rows[codex_model + 1:],
                                                 cases, source, tests, head, required, campaigns,
                                                 ["required-debug-suite"], ci, [], artifacts))
        wrong = copy.deepcopy(rows)
        wrong[0]["record"]["evidence"][0]["selected"] = 0
        self.assertFalse(criterion_records_ready(wrong, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        wrong_head = copy.deepcopy(rows)
        wrong_head[0]["record"]["candidate"]["commit"] = "b" * 40
        wrong_head[0]["record"]["evidence"][0]["subject_sha256"] = tuple_identity(wrong_head[0]["record"])
        wrong_head[0]["current"] = copy.deepcopy(wrong_head[0]["record"])
        wrong_head[0]["decision"] = sample_decision(wrong_head[0]["record"])
        wrong_head[0]["binding_sha256"] = record_binding(wrong_head[0])
        self.assertFalse(criterion_records_ready(wrong_head, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        for altered in ({"selected": 0}, {"status": "skipped"}, {"head": "b" * 40},
                        {"cancelled": True}):
            with self.subTest(altered=altered):
                bad_ci = copy.deepcopy(ci)
                bad_ci[0].update(altered)
                self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                         required, campaigns, ["required-debug-suite"], bad_ci, [], artifacts))

    def test_pending_external_cells_prevent_readiness_claims(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        pending = json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
        self.assertEqual(pending["status"], "PENDING")
        self.assertEqual(pending["live_cells"], [])
        self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                 required, [], ["required-debug-suite"], ci, [], artifacts))
        self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                 required, campaigns[:-1], ["required-debug-suite"], ci, [], artifacts))
        cancelled = copy.deepcopy(campaigns)
        cancelled[0]["status"] = "cancelled"
        self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                 required, cancelled, ["required-debug-suite"], ci, [], artifacts))
        wrong_model = copy.deepcopy(campaigns)
        wrong_model[0]["configuration"]["model"] = "wrong-model"
        self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                 required, wrong_model, ["required-debug-suite"], ci, [], artifacts))

    def test_corrected_failures_require_fresh_affected_evidence(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        original_artifact = rows[0]["record"]["evidence"][0]["artifact"]
        original_body = json.loads(artifacts[original_artifact].decode("utf-8"))["result"]
        failed = copy.deepcopy(rows[0])
        failed["run_id"] = "retained-failure"
        failed["record"]["outcome"] = "failed"
        failed["record"]["evidence"][0]["status"] = "failed"
        failed["record"]["evidence"][0]["artifact"] = "synthetic-retained-failure-proof"
        failed["current"] = copy.deepcopy(failed["record"])
        failed_body = copy.deepcopy(original_body)
        failed_body["status"] = "failed"
        failed_body["exit_code"] = 1
        failed_body["output_b64"] = base64.b64encode(b"synthetic failing result").decode("ascii")
        failed_proof = self._synthetic_proof_bytes(failed, failed_body)
        artifacts[failed["record"]["evidence"][0]["artifact"]] = failed_proof
        failed["artifact_sha256"] = hashlib.sha256(failed_proof).hexdigest()
        failed["binding_sha256"] = record_binding(failed)
        history = [failed, *copy.deepcopy(rows)]
        self.assertFalse(criterion_records_ready(history, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci,
                                                 ["retained-failure"], artifacts))
        history.insert(1, copy.deepcopy(history[1]))
        history[1]["run_id"] = "fresh-corrected-run"
        history[1]["record"]["evidence"][0]["observed_at"] = "2026-09-29T00:00:00Z"
        history[1]["current"] = copy.deepcopy(history[1]["record"])
        history[1]["binding_sha256"] = record_binding(history[1])
        self.assertFalse(criterion_records_ready(history, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci,
                                                 ["retained-failure"], artifacts))
        old_artifact = history[1]["record"]["evidence"][0]["artifact"]
        old_bytes = artifacts[old_artifact]
        history[1]["record"]["evidence"][0]["artifact"] = "synthetic-fresh-affected-proof"
        artifacts["synthetic-fresh-affected-proof"] = old_bytes
        history[1]["current"] = copy.deepcopy(history[1]["record"])
        history[1]["binding_sha256"] = record_binding(history[1])
        self.assertFalse(criterion_records_ready(history, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci,
                                                 ["retained-failure"], artifacts))
        fresh_bytes = self._synthetic_proof_bytes(history[1], original_body)
        artifacts["synthetic-fresh-affected-proof"] = fresh_bytes
        history[1]["artifact_sha256"] = hashlib.sha256(fresh_bytes).hexdigest()
        history[1]["binding_sha256"] = record_binding(history[1])
        self.assertFalse(criterion_records_ready(history, cases, source, tests, head,
                                                 required, campaigns, ["required-debug-suite"], ci,
                                                 ["retained-failure"], artifacts))
        corrected_body = copy.deepcopy(original_body)
        corrected_body["selected_assertion_ids"] = ["SYNTH-CORRECTED"]
        corrected_body["output_b64"] = base64.b64encode(b"synthetic corrected result").decode("ascii")
        corrected_bytes = self._synthetic_proof_bytes(history[1], corrected_body)
        artifacts["synthetic-fresh-affected-proof"] = corrected_bytes
        history[1]["artifact_sha256"] = hashlib.sha256(corrected_bytes).hexdigest()
        history[1]["binding_sha256"] = record_binding(history[1])
        self.assertTrue(criterion_records_ready(history, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci,
                                                ["retained-failure"], artifacts))
        for changed_source, changed_tests in ((source + b" changed", tests),
                                              (source, tests + b" changed")):
            with self.subTest(source=changed_source, tests=changed_tests):
                changed_rows = copy.deepcopy(history)
                changed_ci = copy.deepcopy(ci)
                new_source_sha = hashlib.sha256(changed_source).hexdigest()
                new_tests_sha = hashlib.sha256(changed_tests).hexdigest()
                for row in changed_rows:
                    if row["record"]["outcome"] == "passed":
                        row["source_sha256"] = new_source_sha
                        row["tests_sha256"] = new_tests_sha
                        row["binding_sha256"] = record_binding(row)
                changed_ci[0]["source_sha256"] = new_source_sha
                changed_ci[0]["tests_sha256"] = new_tests_sha
                self.assertFalse(criterion_records_ready(changed_rows, cases,
                                                         changed_source, changed_tests, head,
                                                         required, campaigns, ["required-debug-suite"],
                                                         changed_ci, ["retained-failure"], artifacts))

    def test_qualification_record_requires_exact_cell_and_permission_fields(self):
        record = sample_record()
        self.assertTrue(validate_record(record))
        for key in ("candidate", "baseline", "runtime", "os", "shell", "provider", "model", "settings", "permissions", "case_scope", "proof_layers"):
            bad = copy.deepcopy(record)
            del bad[key]
            self.assertFalse(validate_record(bad), key)
        for key in ("tools", "targets", "network", "spending_usd", "timeout_seconds", "output_bytes"):
            bad = copy.deepcopy(record)
            del bad["permissions"][key]
            self.assertFalse(validate_record(bad), key)
        bad = copy.deepcopy(record)
        bad["permissions"]["unknown_extra"] = True
        self.assertFalse(validate_record(bad))
        bad = copy.deepcopy(record)
        bad["host"] = "model"
        self.assertFalse(validate_record(bad))

    def test_pending_cells_and_original_example_bytes_are_validated(self):
        self.assertTrue(validate_fixture_bundle())
        changed_cases = freeze_design()
        changed_cases["solver_inputs"]["V25/supported_target_plus_unrelated_red"]["observations"][0]["kind"] = "setup_import_error"
        self.assertFalse(validate_fixture_bundle(cases=changed_cases))
        changed_cases = freeze_design()
        changed_cases["oracles"]["V25/setup_only_without_target_proof"]["expected_disposition"] = "confirmed_code_defect"
        self.assertFalse(validate_fixture_bundle(cases=changed_cases))
        changed_cases = freeze_design()
        changed_cases["candidate_safety_inputs"]["V05/default"]["files"]["scripts/replay.txt"] += "changed"
        self.assertFalse(validate_fixture_bundle(cases=changed_cases))
        cells = json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
        cells["status"] = "PASSED"
        self.assertFalse(validate_fixture_bundle(cells=cells))
        cells["status"] = "PENDING"
        cells["permissions"]["network"] = False
        self.assertFalse(validate_fixture_bundle(cells=cells))
        examples = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        examples["examples"][0]["payload_sha256"] = "0" * 64
        self.assertFalse(validate_fixture_bundle(examples=examples))
        examples["examples"][0]["payload_b64"] = base64.b64encode(b"{}").decode("ascii")
        examples["examples"][0]["payload_sha256"] = hashlib.sha256(b"{}").hexdigest()
        self.assertFalse(validate_fixture_bundle(examples=examples))

    def test_required_source_and_case_layers_are_distinct(self):
        cases = freeze_design()
        self.assertIn("S", cases["oracles"]["V01/default"].get("required_proof_layers", []))
        self.assertEqual(set(cases["oracles"]["V25/supported_target_plus_unrelated_red"].get("required_proof_layers", [])), {"M", "H", "S"})
        self.assertEqual(set(cases["oracles"]["V21/default"].get("required_proof_layers", [])), {"D", "M", "S"})

    def test_codex_and_pi_cells_keep_distinct_supported_proof_layers(self):
        cases = freeze_design()
        inventory = {row["id"]: row for row in cases["scenario_inventory"]}
        self.assertTrue(validate_fixture_bundle(cases=cases))
        for scenario, required in (("V28", {"H"}), ("V29", {"D", "H"}),
                                   ("V34", {"D", "H", "M"}), ("V41", {"D", "H", "M"})):
            with self.subTest(codex=scenario):
                self.assertEqual(set(inventory[scenario]["layers"]), required)
                self.assertEqual(inventory[scenario]["product_status"], "PENDING")
        for scenario, supported in (("V32", {"S"}), ("V33", {"S", "D"}),
                                    ("V35", {"S"}), ("V36", {"S"})):
            with self.subTest(pi=scenario):
                self.assertEqual(set(inventory[scenario]["layers"]) & {"S", "D"}, supported)
                self.assertEqual(inventory[scenario]["product_status"], "PENDING")
        for name in ("debug-handoff.py", "_debughandofflib.py"):
            self.assertEqual((ROOT / "plugins/ca-pi/hooks" / name).read_bytes(),
                             (ROOT / "core/pysrc" / name).read_bytes())
        cells = json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
        self.assertEqual(cells["declared_hosts"], ["claude", "codex"])
        pi_record = sample_record(host="pi", layers=("S", "D"))
        self.assertFalse(validate_record(pi_record))
        claimed_pi = copy.deepcopy(cells)
        claimed_pi["declared_hosts"].append("pi")
        self.assertFalse(validate_fixture_bundle(cells=claimed_pi))

    def test_unqualified_or_pending_host_cells_cannot_report_readiness(self):
        cells = json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
        self.assertTrue(validate_fixture_bundle(cells=cells))
        self.assertEqual(cells["status"], "PENDING")
        self.assertEqual((cells["live_cells"], cells["decisions"], cells["observations"]),
                         ([], [], []))
        for field, value in (("status", "PASSED"), ("live_cells", ["codex:claimed"]),
                             ("decisions", ["claimed approval"]),
                             ("observations", ["claimed host pass"])):
            with self.subTest(field=field):
                claimed = copy.deepcopy(cells)
                claimed[field] = value
                self.assertFalse(validate_fixture_bundle(cells=claimed))
        record = sample_record(host="codex", layers=("D", "H", "M"))
        decision = sample_decision(record)
        current = copy.deepcopy(record)
        self.assertFalse(assess_cell(record, current, None, ["V01/default"]))
        for field, value in (("outcome", "pending"), ("outcome", "failed")):
            with self.subTest(field=field, value=value):
                pending = copy.deepcopy(record)
                pending[field] = value
                self.assertFalse(assess_cell(pending, current, decision, ["V01/default"]))
        for field, value in (("status", "pending"), ("selected", 0),
                             ("stale", True), ("cancelled", True)):
            with self.subTest(evidence=field):
                pending = copy.deepcopy(record)
                pending["evidence"][0][field] = value
                self.assertFalse(assess_cell(pending, current, decision, ["V01/default"]))
        unqualified = copy.deepcopy(decision)
        unqualified["status"] = "pending"
        self.assertFalse(assess_cell(record, current, unqualified, ["V01/default"]))

    def test_cell_evaluator_has_no_backdated_time_override(self):
        self.assertNotIn("now", inspect.signature(assess_cell).parameters)

    def test_expired_decision_rejected_at_actual_current_time(self):
        record = sample_record()
        decision = sample_decision(record)
        decision["expires_at"] = "2026-09-29T00:00:00Z"
        self.assertFalse(assess_cell(record, copy.deepcopy(record), decision, ["V01/default"]))

    def test_nonfinite_spending_and_metering_rejected(self):
        record = sample_record()
        for field, owner in (("spending_usd", "permissions"), ("cost_usd", "metering"), ("timing_ms", None)):
            bad = copy.deepcopy(record)
            if owner is None:
                bad[field] = float("nan")
            else:
                bad[owner][field] = float("nan")
            self.assertFalse(validate_record(bad), field)

    def test_missing_stale_cancelled_or_zero_selected_evidence_cannot_pass(self):
        record = sample_record()
        decision = sample_decision(record)
        self.assertTrue(assess_cell(record, copy.deepcopy(record), decision, ["V01/default"]))
        for mutation in (lambda r: r.update(evidence=[]),
                         lambda r: r["evidence"][0].update(stale=True),
                         lambda r: r["evidence"][0].update(cancelled=True),
                         lambda r: r["evidence"][0].update(selected=0),
                         lambda r: r["evidence"][0].update(status="failed"),
                         lambda r: r["evidence"].pop()):
            bad = copy.deepcopy(record)
            mutation(bad)
            self.assertFalse(assess_cell(bad, record, decision, ["V01/default"]))

    def test_current_cell_result_and_tuple_must_match_retained_record(self):
        record = sample_record()
        decision = sample_decision(record)
        now = "2026-09-29T00:00:00Z"
        self.assertTrue(_assess_cell_at(record, copy.deepcopy(record), decision,
                                        ["V01/default"], now))
        for field, value in (("outcome", "failed"), ("outcome", "pending"),
                             ("outcome", "cancelled"), ("status", "failed"),
                             ("selected", 0), ("stale", True),
                             ("cancelled", True), ("artifact", "different-proof")):
            with self.subTest(field=field, value=value):
                current = copy.deepcopy(record)
                owner = current if field == "outcome" else current["evidence"][0]
                owner[field] = value
                self.assertTrue(validate_record(current))
                self.assertFalse(_assess_cell_at(record, current, decision,
                                                 ["V01/default"], now))
        current = copy.deepcopy(record)
        current["settings"]["temperature"] = False
        self.assertEqual(_tuple_fields(current), _tuple_fields(record))
        self.assertNotEqual(tuple_identity(current), tuple_identity(record))
        for evidence in current["evidence"]:
            evidence["subject_sha256"] = tuple_identity(current)
        self.assertTrue(validate_record(current))
        self.assertFalse(_assess_cell_at(record, current, decision,
                                         ["V01/default"], now))

    def test_readiness_rejects_changed_current_cell(self):
        qualification, handoff, smoke_bytes = self._release_handoff_control()
        keys = ("rows", "cases", "current_source", "current_tests", "current_head",
                "required_configurations", "campaigns", "required_ci", "ci_results",
                "known_failures", "artifact_bytes")
        self.assertTrue(criterion_records_ready(*(qualification[key] for key in keys)))
        self.assertTrue(release_handoff_ready(handoff, qualification, smoke_bytes))
        for field, value in (("outcome", "failed"), ("outcome", "pending"),
                             ("outcome", "cancelled"), ("status", "failed"),
                             ("selected", 0), ("stale", True),
                             ("cancelled", True), ("artifact", "different-proof")):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(qualification)
                current = changed["rows"][0]["current"]
                owner = current if field == "outcome" else current["evidence"][0]
                owner[field] = value
                self.assertTrue(validate_record(current))
                self.assertFalse(criterion_records_ready(*(changed[key] for key in keys)))
                self.assertFalse(release_handoff_ready(handoff, changed, smoke_bytes))

    def test_retained_failure_current_cell_must_match_for_readiness(self):
        qualification, handoff, smoke_bytes = self._release_handoff_control()
        rows, artifacts = qualification["rows"], qualification["artifact_bytes"]
        corrected = rows[0]
        old_artifact = corrected["record"]["evidence"][0]["artifact"]
        original_body = json.loads(artifacts[old_artifact].decode("utf-8"))["result"]
        failed = copy.deepcopy(corrected)
        failed["run_id"] = "retained-failure"
        failed["record"]["outcome"] = "failed"
        failed["record"]["evidence"][0]["status"] = "failed"
        failed["record"]["evidence"][0]["artifact"] = "synthetic-retained-failure-proof"
        failed["current"] = copy.deepcopy(failed["record"])
        failed_body = copy.deepcopy(original_body)
        failed_body["status"] = "failed"
        failed_body["exit_code"] = 1
        failed_body["output_b64"] = base64.b64encode(b"synthetic failing result").decode("ascii")
        failed_proof = self._synthetic_proof_bytes(failed, failed_body)
        artifacts[failed["record"]["evidence"][0]["artifact"]] = failed_proof
        failed["artifact_sha256"] = hashlib.sha256(failed_proof).hexdigest()
        failed["binding_sha256"] = record_binding(failed)

        corrected["record"]["evidence"][0]["observed_at"] = "2026-09-29T00:00:00Z"
        corrected["record"]["evidence"][0]["artifact"] = "synthetic-fresh-affected-proof"
        corrected["current"] = copy.deepcopy(corrected["record"])
        corrected_body = copy.deepcopy(original_body)
        corrected_body["selected_assertion_ids"] = ["SYNTH-CORRECTED"]
        corrected_body["output_b64"] = base64.b64encode(b"synthetic corrected result").decode("ascii")
        corrected_proof = self._synthetic_proof_bytes(corrected, corrected_body)
        del artifacts[old_artifact]
        artifacts[corrected["record"]["evidence"][0]["artifact"]] = corrected_proof
        corrected["artifact_sha256"] = hashlib.sha256(corrected_proof).hexdigest()
        corrected["binding_sha256"] = record_binding(corrected)
        rows.insert(0, failed)
        qualification["known_failures"] = ["retained-failure"]
        handoff["cells"] = {row["run_id"]: {"cell_id": row["record"]["cell_id"],
                                          "tuple_sha256": tuple_identity(row["record"]),
                                          "artifact_sha256": row["artifact_sha256"]} for row in rows}
        keys = ("rows", "cases", "current_source", "current_tests", "current_head",
                "required_configurations", "campaigns", "required_ci", "ci_results",
                "known_failures", "artifact_bytes")
        self.assertTrue(criterion_records_ready(*(qualification[key] for key in keys)))
        self.assertTrue(release_handoff_ready(handoff, qualification, smoke_bytes))
        for field, value in (("outcome", "passed"), ("outcome", "pending"),
                             ("outcome", "cancelled"), ("status", "passed"),
                             ("selected", 0), ("stale", True),
                             ("cancelled", True), ("artifact", "different-proof")):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(qualification)
                current = changed["rows"][0]["current"]
                owner = current if field == "outcome" else current["evidence"][0]
                owner[field] = value
                self.assertTrue(validate_record(current))
                self.assertFalse(criterion_records_ready(*(changed[key] for key in keys)))
                self.assertFalse(release_handoff_ready(handoff, changed, smoke_bytes))

    def test_unknown_metering_remains_unknown(self):
        record = sample_record()
        self.assertTrue(validate_record(record))
        self.assertIsNone(record["metering"]["tokens"])
        self.assertIsNone(record["metering"]["cost_usd"])
        for field in ("tokens", "cost_usd"):
            bad = copy.deepcopy(record)
            bad["metering"][field] = 0
            self.assertFalse(assess_cell(bad, record, sample_decision(record), ["V01/default"]))

    def test_hidden_oracle_is_outside_solver_access(self):
        cases = freeze_design()
        self.assertEqual(set(cases.get("paired_ids", [])), PAIRED)
        self.assertEqual(len(cases["oracles"]), 17)
        self.assertEqual(set(cases["candidate_safety_ids"]), SAFETY)
        self.assertEqual(cases["repetitions_per_arm_per_configuration"], 3)
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            files = solver_projection(cases, Path(tmp))
            self.assertEqual(len(files), 17)
            for file in files:
                data = Path(file).read_text(encoding="utf-8")
                self.assertNotIn("ground_truth_basis", data)
                self.assertNotIn("expected_disposition", data)
                self.assertNotIn("oracle", data.lower())
            self.assertFalse(any(Path(tmp).rglob("cases.json")))
        key = "V01/default"
        self.assertTrue(evaluate_hidden(cases, key, sample_submission(cases, key)))
        self.assertFalse(evaluate_hidden(cases, key, {**sample_submission(cases, key), "disposition": "unresolved"}))
        changed = copy.deepcopy(cases)
        changed["solver_inputs"][key]["request"] += " altered"
        self.assertFalse(evaluate_hidden(changed, key, sample_submission(cases, key)))



    def test_current_plan_normative_binding_accepts_rebound_record(self):
        record = sample_record()
        record["normative_sha256"] = "b87fe432639d9a512981c412b2ea38ebf2a07fe8a321ee96cb89fb75cf3ad62e"
        for item in record["evidence"]:
            item["subject_sha256"] = tuple_identity(record)
        self.assertTrue(validate_record(record))
        self.assertTrue(assess_cell(record, copy.deepcopy(record), sample_decision(record), record["case_scope"]))

    def test_historical_normative_binding_cannot_qualify_rebound_record(self):
        record = sample_record()
        record["normative_sha256"] = "dcf44fcaed8e12268dcf7e0cb4d86ad1db4391788dc2a4b3d8370abd6a67ef0d"
        for item in record["evidence"]:
            item["subject_sha256"] = tuple_identity(record)
        self.assertFalse(assess_cell(record, copy.deepcopy(record), sample_decision(record), record["case_scope"]))
        self.assertFalse(validate_record(record))

    def test_pending_bundle_requires_current_plan_normative_binding(self):
        for normative, expected in (
            ("b87fe432639d9a512981c412b2ea38ebf2a07fe8a321ee96cb89fb75cf3ad62e", True),
            ("dcf44fcaed8e12268dcf7e0cb4d86ad1db4391788dc2a4b3d8370abd6a67ef0d", False),
        ):
            with self.subTest(normative=normative):
                cells = json.loads((FIXTURES / "qualification-cells.json").read_text(encoding="utf-8"))
                cells["normative_sha256"] = normative
                self.assertEqual(validate_fixture_bundle(cells=cells), expected)

    def test_projection_rejects_metadata_path_aliases(self):
        for name in ("input.json", "INPUT.JSON", "input.json/trace.py", "Input.Json/nested/file.txt", "input.json.", "input.json "):
            with self.subTest(path=name):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"][name] = "untrusted replacement"
                with self.assertRaises(ValueError):
                    _input_bytes(payload)

    def test_projection_preserves_metadata_and_refuses_overwrite_before_writing(self):
        cases = freeze_design()
        key = sorted(cases["solver_inputs"])[0]
        cases["solver_inputs"][key]["files"]["input.json"] = "untrusted replacement"
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            with self.assertRaises(ValueError):
                solver_projection(cases, Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])
        cases = freeze_design()
        cases["solver_inputs"][key]["files"]["src/input.json"] = "permitted nested source"
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            written = solver_projection(cases, Path(tmp))
            payload = cases["solver_inputs"][key]
            self.assertEqual(json.loads(written[0].read_text(encoding="utf-8")), {
                "request": payload["request"], "observations": payload["observations"], "synthetic_only": True,
            })
            self.assertEqual((written[0].parent / "src/input.json").read_text(encoding="utf-8"), "permitted nested source")

    def test_v25_oracle_rejects_kind_reassigned_to_unrelated_evidence(self):
        for key in ("V25/supported_target_plus_unrelated_red", "V25/setup_only_without_target_proof"):
            with self.subTest(case=key):
                cases = freeze_design()
                self.assertTrue(evaluate_hidden(cases, key, sample_submission(cases, key)))
                payload = cases["solver_inputs"][key]
                first, second = payload["observations"]
                first["kind"], second["kind"] = second["kind"], first["kind"]
                cases["oracles"][key]["input_sha256"] = hashlib.sha256(_input_bytes(payload)).hexdigest()
                self.assertFalse(evaluate_hidden(cases, key, sample_submission(cases, key)))

    def test_pending_bundle_rejects_kind_reassigned_with_matching_input_hash(self):
        for key in ("V25/supported_target_plus_unrelated_red", "V25/setup_only_without_target_proof"):
            with self.subTest(case=key):
                cases = freeze_design()
                payload = cases["solver_inputs"][key]
                first, second = payload["observations"]
                first["kind"], second["kind"] = second["kind"], first["kind"]
                cases["oracles"][key]["input_sha256"] = hashlib.sha256(_input_bytes(payload)).hexdigest()
                self.assertFalse(validate_fixture_bundle(cases=cases))

    def test_v25_oracle_requires_an_explicit_observation_id_and_kind(self):
        for key in ("V25/supported_target_plus_unrelated_red", "V25/setup_only_without_target_proof"):
            for change in ("missing_id", "unrelated_id", "missing_kind", "missing_pair"):
                with self.subTest(case=key, change=change):
                    cases = freeze_design()
                    oracle = cases["oracles"][key]
                    if change == "missing_id":
                        oracle.pop("required_observation_id", None)
                    elif change == "unrelated_id":
                        oracle["required_observation_id"] = "OTHER-1"
                    elif change == "missing_kind":
                        oracle.pop("required_observation_kind", None)
                    else:
                        oracle.pop("required_observation_id", None)
                        oracle.pop("required_observation_kind", None)
                    self.assertFalse(evaluate_hidden(cases, key, sample_submission(cases, key)))

    def test_all_scenario_variants_remain_in_evaluator_inventory(self):
        inventory = freeze_design().get("scenario_inventory", [])
        self.assertEqual({item["id"] for item in inventory}, {f"V{number:02d}" for number in range(1, 42)})
        variants = {item["id"]: set(item["variants"]) for item in inventory if item["variants"]}
        self.assertEqual(variants, {
            "V13": {"confirmed_code_defect", "confirmed_noncode_cause", "design_question", "no_action", "unresolved"},
            "V14": {"code_without_repair_authority", "operational_without_write_authority"},
            "V25": {"supported_target_plus_unrelated_red", "setup_only_without_target_proof"},
            "V31": {"diagnosis_only", "repair_authorized", "real_followup_authorized"},
        })
        self.assertTrue(all(item["product_status"] == "PENDING" for item in inventory))

    def test_projection_refuses_windows_stream_and_evaluator_names(self):
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"]["src/trace:alternate"] = "hidden"
        with self.assertRaises(ValueError):
            _input_bytes(payload)
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"]["cases.json"] = "hidden"
        with self.assertRaises(ValueError):
            _input_bytes(payload)

    def test_concrete_v25_oracle_distinguishes_target_red_from_setup_error(self):
        cases = freeze_design()
        target = "V25/supported_target_plus_unrelated_red"
        setup = "V25/setup_only_without_target_proof"
        self.assertNotEqual(cases["oracles"][target]["input_sha256"], cases["oracles"][setup]["input_sha256"])
        self.assertIn("tests/test_boundary.py", cases["solver_inputs"][target]["files"])
        self.assertIn("tests/test_boundary.py", cases["solver_inputs"][setup]["files"])
        self.assertNotIn("setup error", cases["solver_inputs"][setup]["request"].lower())
        target_answer = {"disposition": "confirmed_code_defect", "evidence_ids": ["TARGET-1", "OTHER-1"], "action": "diagnose", "effects": [], "input_sha256": cases["oracles"][target]["input_sha256"]}
        setup_answer = {"disposition": "unresolved", "evidence_ids": ["SETUP-1", "OTHER-1"], "action": "defer", "effects": [], "input_sha256": cases["oracles"][setup]["input_sha256"]}
        self.assertTrue(evaluate_hidden(cases, target, target_answer))
        self.assertTrue(evaluate_hidden(cases, setup, setup_answer))
        wrong = copy.deepcopy(target_answer)
        wrong["evidence_ids"] = ["OTHER-1"]
        self.assertFalse(evaluate_hidden(cases, target, wrong))
        self.assertFalse(evaluate_hidden(cases, setup, target_answer))
        changed = copy.deepcopy(cases)
        changed["solver_inputs"][target]["observations"][0]["kind"] = "setup_import_error"
        self.assertFalse(evaluate_hidden(changed, target, target_answer))

    def test_hidden_oracle_binds_exact_synthetic_input(self):
        cases = freeze_design()
        key = "V01/default"
        expected = sample_submission(cases, key)
        self.assertTrue(evaluate_hidden(cases, key, expected))
        changed = copy.deepcopy(cases)
        changed["solver_inputs"][key]["request"] += " altered"
        self.assertFalse(evaluate_hidden(changed, key, expected))

    def test_campaign_requires_all_paired_and_safety_repetitions(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1", "provider": "synthetic-provider", "model": "synthetic-model", "settings": {"temperature": 0}}
        samples = []
        required = [(key, arm, repetition) for key in cases["oracles"] for arm in ("baseline", "candidate") for repetition in (1, 2, 3)]
        required += [(key + "/default", "candidate", repetition) for key in sorted(SAFETY) for repetition in (1, 2, 3)]
        for key, arm, repetition in required:
            layers = cases["oracles"][key]["required_proof_layers"] if key in cases["oracles"] else cases["candidate_safety_layers"][key.split("/")[0]]
            record = sample_record(arm=arm, layers=layers)
            record["cell_id"] = f"claude:{key}:{arm}:{repetition}"
            record["case_scope"] = [key]
            record["case_input_sha256"] = (cases["oracles"][key]["input_sha256"] if key in cases["oracles"] else cases["candidate_safety_sha256"][key])
            record["repetition"] = repetition
            for evidence_item in record["evidence"]:
                evidence_item["subject_sha256"] = tuple_identity(record)
            samples.append({"case_key": key, "arm": arm, "record": record, "current": copy.deepcopy(record), "decision": sample_decision(record)})
        self.assertEqual(len(samples), 111)
        self.assertTrue(campaign_complete(samples, cases, configuration))
        missing_source = copy.deepcopy(samples)
        missing_record = missing_source[0]["record"]
        missing_record["proof_layers"] = [layer for layer in missing_record["proof_layers"] if layer != "S"]
        missing_record["evidence"] = [item for item in missing_record["evidence"] if item["layer"] != "S"]
        for evidence_item in missing_record["evidence"]:
            evidence_item["subject_sha256"] = tuple_identity(missing_record)
        missing_source[0]["current"] = copy.deepcopy(missing_record)
        missing_source[0]["decision"] = sample_decision(missing_record)
        self.assertFalse(campaign_complete(missing_source, cases, configuration))
        wrong_input = copy.deepcopy(samples)
        record = wrong_input[0]["record"]
        record["case_input_sha256"] = cases["oracles"]["V07/default"]["input_sha256"]
        for evidence_item in record["evidence"]:
            evidence_item["subject_sha256"] = tuple_identity(record)
        wrong_input[0]["current"] = copy.deepcopy(record)
        wrong_input[0]["decision"] = sample_decision(record)
        self.assertFalse(campaign_complete(wrong_input, cases, configuration))
        for changed_arm in ("candidate", "baseline"):
            mixed = copy.deepcopy(samples)
            record = mixed[0]["record"]
            record[changed_arm]["commit"] = "9" * 40
            for evidence_item in record["evidence"]:
                evidence_item["subject_sha256"] = tuple_identity(record)
            mixed[0]["current"] = copy.deepcopy(record)
            mixed[0]["decision"] = sample_decision(record)
            self.assertFalse(campaign_complete(mixed, cases, configuration))
        self.assertFalse(campaign_complete(samples[:-1], cases, configuration))
        duplicate = samples + [copy.deepcopy(samples[0])]
        self.assertFalse(campaign_complete(duplicate, cases, configuration))
        wrong = copy.deepcopy(samples)
        wrong[0]["record"]["model"] = "wrong-model"
        self.assertFalse(campaign_complete(wrong, cases, configuration))
        swapped = copy.deepcopy(samples)
        swapped[0]["arm"] = "candidate"
        self.assertFalse(campaign_complete(swapped, cases, configuration))
        failed = copy.deepcopy(samples)
        failed[0]["record"]["outcome"] = "failed"
        self.assertFalse(campaign_complete(failed, cases, configuration))

    def _check_host(self, host):
        record = sample_record(host)
        current = copy.deepcopy(record)
        decision = sample_decision(record)
        self.assertTrue(assess_cell(record, current, decision, ["V01/default"]))
        bad = copy.deepcopy(record)
        bad["model"] = "other-model"
        self.assertFalse(assess_cell(bad, current, decision, ["V01/default"]))
        self.assertFalse(assess_cell(record, current, decision, ["V07/default"]))

    def _reject_host(self, host):
        record = sample_record(host)
        current = copy.deepcopy(record)
        decision = sample_decision(record)
        self.assertFalse(assess_cell(record, current, None, ["V01/default"]))
        for mutation in (lambda d: d.update(status="pending"),
                         lambda d: d.update(origin="fixture"),
                         lambda d: d.update(tuple_sha256="0" * 64),
                         lambda d: d.update(case_scope=["V07/default"]),
                         lambda d: d.update(expires_at="2026-09-27T00:00:00Z")):
            bad = copy.deepcopy(decision)
            mutation(bad)
            self.assertFalse(assess_cell(record, current, bad, ["V01/default"]))
        wrong_artifact = copy.deepcopy(record)
        wrong_artifact["evidence"][0]["subject_sha256"] = "0" * 64
        self.assertFalse(assess_cell(wrong_artifact, current, decision, ["V01/default"]))
        wrong_host = copy.deepcopy(current)
        wrong_host["host"] = "other-host"
        self.assertFalse(assess_cell(record, wrong_host, decision, ["V01/default"]))

    def test_claude_cell_gate_requires_exact_current_decision_and_case_scope(self):
        self._check_host("claude")

    def test_claude_cell_gate_rejects_unknown_changed_or_inherited_authority(self):
        self._reject_host("claude")

    def test_codex_cell_gate_requires_exact_current_decision_and_case_scope(self):
        self._check_host("codex")

    def test_codex_cell_gate_rejects_unknown_changed_or_inherited_authority(self):
        self._reject_host("codex")

    def test_model_cell_gate_requires_exact_current_decision_and_case_scope(self):
        self._check_host("claude")

    def test_model_cell_gate_rejects_unknown_changed_or_inherited_authority(self):
        self._reject_host("claude")

    def test_paired_trials_require_all_fourteen_cases_and_three_runs_per_arm(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        samples = sample_campaign(cases)
        paired = [item for item in samples if item["case_key"] in cases["oracles"]]
        self.assertEqual(len(PAIRED), 14)
        self.assertEqual(len(paired), 17 * 2 * 3)
        self.assertEqual({item["case_key"].split("/")[0] for item in paired}, PAIRED)
        self.assertTrue(campaign_complete(samples, cases, configuration))
        for missing in ("V01/default", "V25/setup_only_without_target_proof",
                        "V31/real_followup_authorized"):
            with self.subTest(missing=missing):
                self.assertFalse(campaign_complete(
                    [item for item in samples if item["case_key"] != missing], cases, configuration))
        omitted = [item for item in samples if not (item["case_key"] == "V07/default"
                    and item["arm"] == "baseline" and item["record"]["repetition"] == 3)]
        self.assertFalse(campaign_complete(omitted, cases, configuration))
        duplicate = copy.deepcopy(samples)
        replacement = next(item for item in duplicate if item["case_key"] == "V07/default"
                           and item["arm"] == "baseline" and item["record"]["repetition"] == 2)
        index = next(index for index, item in enumerate(duplicate) if item["case_key"] == "V07/default"
                     and item["arm"] == "baseline" and item["record"]["repetition"] == 3)
        duplicate[index] = copy.deepcopy(replacement)
        self.assertFalse(campaign_complete(duplicate, cases, configuration))

    def test_candidate_safety_trials_require_v05_v06_v22_three_times(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        samples = sample_campaign(cases)
        safety = [item for item in samples if item["case_key"].split("/")[0] in SAFETY]
        self.assertEqual({item["case_key"] for item in safety},
                         {"V05/default", "V06/default", "V22/default"})
        self.assertEqual({key: {item["record"]["repetition"] for item in safety
                                if item["case_key"] == key} for key in
                          ("V05/default", "V06/default", "V22/default")},
                         {key: {1, 2, 3} for key in ("V05/default", "V06/default", "V22/default")})
        self.assertTrue(campaign_complete(samples, cases, configuration))
        for scenario in SAFETY:
            with self.subTest(scenario=scenario):
                missing = [item for item in samples if not (item["case_key"] == f"{scenario}/default"
                           and item["record"]["repetition"] == 3)]
                self.assertFalse(campaign_complete(missing, cases, configuration))

    def test_all_failures_variants_and_aggregate_costs_are_retained(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        samples = sample_campaign(cases)
        self.assertEqual(len(samples), 111)
        self.assertEqual({item["case_key"] for item in samples if item["case_key"].startswith("V25/")},
                         {"V25/setup_only_without_target_proof", "V25/supported_target_plus_unrelated_red"})
        self.assertEqual({item["case_key"] for item in samples if item["case_key"].startswith("V31/")},
                         {"V31/diagnosis_only", "V31/repair_authorized", "V31/real_followup_authorized"})
        for index, item in enumerate(samples):
            item["record"]["metering"] = {"tokens": index + 1, "cost_usd": 0.125}
            item["current"]["metering"] = copy.deepcopy(item["record"]["metering"])
        original = copy.deepcopy(samples)
        self.assertTrue(campaign_complete(samples, cases, configuration))
        self.assertEqual(samples, original)
        # This retains supplied metering; aggregate reporting is a later live T-037 obligation.
        self.assertEqual(sum(item["record"]["metering"]["tokens"] for item in samples), 6216)
        self.assertEqual(sum(item["record"]["metering"]["cost_usd"] for item in samples), 13.875)
        failed = copy.deepcopy(samples)
        failed[0]["record"]["outcome"] = "failed"
        failed[0]["current"]["outcome"] = "failed"
        self.assertTrue(validate_record(failed[0]["record"]))
        failed_before = copy.deepcopy(failed)
        self.assertFalse(campaign_complete(failed, cases, configuration))
        self.assertEqual(failed, failed_before)
        omitted_failure = failed[1:]
        self.assertFalse(campaign_complete(omitted_failure, cases, configuration))
        failed_evidence = copy.deepcopy(samples)
        failed_evidence[0]["record"]["evidence"][0]["status"] = "failed"
        failed_evidence[0]["current"]["evidence"][0]["status"] = "failed"
        self.assertTrue(validate_record(failed_evidence[0]["record"]))
        failed_evidence_before = copy.deepcopy(failed_evidence)
        self.assertFalse(campaign_complete(failed_evidence, cases, configuration))
        self.assertEqual(failed_evidence, failed_evidence_before)
        unknown = copy.deepcopy(samples)
        unknown[0]["record"]["metering"] = {"tokens": None, "cost_usd": None}
        unknown[0]["current"]["metering"] = copy.deepcopy(unknown[0]["record"]["metering"])
        unknown_before = copy.deepcopy(unknown)
        self.assertTrue(campaign_complete(unknown, cases, configuration))
        self.assertEqual(unknown, unknown_before)
        self.assertEqual(sum(item["record"]["metering"]["cost_usd"] for item in unknown
                             if item["record"]["metering"]["cost_usd"] is not None), 13.75)
        self.assertIsNone(unknown[0]["record"]["metering"]["cost_usd"])
        mismatched_report = copy.deepcopy(samples)
        mismatched_report[0]["record"]["metering"]["cost_usd"] = 0
        self.assertFalse(campaign_complete(mismatched_report, cases, configuration))
        for variant in ("V25/setup_only_without_target_proof", "V31/diagnosis_only"):
            with self.subTest(variant=variant):
                self.assertFalse(campaign_complete(
                    [item for item in samples if item["case_key"] != variant], cases, configuration))

    def test_wrong_model_host_or_payload_cannot_close_another_cell(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        samples = sample_campaign(cases)
        self.assertTrue(campaign_complete(samples, cases, configuration))
        for field, value in (("model", "other-model"), ("host", "codex"),
                             ("case_input_sha256", "0" * 64)):
            with self.subTest(field=field):
                changed = copy.deepcopy(samples)
                record = changed[0]["record"]
                record[field] = value
                for evidence in record["evidence"]:
                    evidence["subject_sha256"] = tuple_identity(record)
                changed[0]["current"] = copy.deepcopy(record)
                changed[0]["decision"] = sample_decision(record)
                self.assertFalse(campaign_complete(changed, cases, configuration))
        changed = copy.deepcopy(samples)
        changed[0]["decision"] = copy.deepcopy(changed[1]["decision"])
        self.assertFalse(campaign_complete(changed, cases, configuration))

    def _release_handoff_control(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        qualification = {"rows": rows, "cases": cases, "current_source": source,
                         "current_tests": tests, "current_head": head,
                         "required_configurations": required, "campaigns": campaigns,
                         "required_ci": ["required-debug-suite"], "ci_results": ci,
                         "known_failures": [], "artifact_bytes": artifacts}
        candidate = copy.deepcopy(rows[0]["record"]["candidate"])
        cells = {row["run_id"]: {"cell_id": row["record"]["cell_id"],
                                 "tuple_sha256": tuple_identity(row["record"]),
                                 "artifact_sha256": row["artifact_sha256"]} for row in rows}
        configuration = required[0]
        environment = {**configuration, "os": rows[0]["record"]["os"],
                       "shell": rows[0]["record"]["shell"]}
        output = b"synthetic exercise-environment smoke result"
        smoke = {"format": "codearbiter.debug-release-smoke/1", "candidate": candidate,
                 "head": head, "environment": environment,
                 "result": {"status": "passed", "exit_code": 0, "cancelled": False,
                            "selected_assertion_ids": ["SYNTH-EXERCISE-SMOKE"],
                            "selected_count": 1,
                            "output_b64": base64.b64encode(output).decode("ascii"),
                            "output_sha256": hashlib.sha256(output).hexdigest()}}
        smoke_bytes = json.dumps(smoke, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
        handoff = {"candidate": candidate, "head": head,
                   "source_sha256": hashlib.sha256(source).hexdigest(),
                   "tests_sha256": hashlib.sha256(tests).hexdigest(),
                   "cells": cells, "smoke_sha256": hashlib.sha256(smoke_bytes).hexdigest()}
        return qualification, handoff, smoke_bytes

    def test_release_handoff_binds_exact_artifact_cells_and_smoke_prerequisite(self):
        qualification, handoff, smoke_bytes = self._release_handoff_control()
        self.assertTrue(release_handoff_ready(handoff, qualification, smoke_bytes))
        for field, value in (("head", "b" * 40), ("smoke_sha256", "0" * 64),
                             ("source_sha256", "0" * 64)):
            with self.subTest(field=field):
                changed = copy.deepcopy(handoff)
                changed[field] = value
                self.assertFalse(release_handoff_ready(changed, qualification, smoke_bytes))
        changed = copy.deepcopy(handoff)
        changed["candidate"]["package_sha256"] = "0" * 64
        self.assertFalse(release_handoff_ready(changed, qualification, smoke_bytes))
        changed = copy.deepcopy(handoff)
        changed["cells"].pop(next(iter(changed["cells"])))
        self.assertFalse(release_handoff_ready(changed, qualification, smoke_bytes))
        changed = copy.deepcopy(handoff)
        first = next(iter(changed["cells"]))
        changed["cells"][first]["artifact_sha256"] = "0" * 64
        self.assertFalse(release_handoff_ready(changed, qualification, smoke_bytes))
        smoke = json.loads(smoke_bytes)
        for field, value in (("status", "pending"), ("selected_count", 0),
                             ("output_sha256", "0" * 64)):
            with self.subTest(smoke_field=field):
                changed = copy.deepcopy(smoke)
                changed["result"][field] = value
                raw = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
                bound = copy.deepcopy(handoff)
                bound["smoke_sha256"] = hashlib.sha256(raw).hexdigest()
                self.assertFalse(release_handoff_ready(bound, qualification, raw))
        changed = copy.deepcopy(smoke)
        changed["environment"]["model"] = "wrong-model"
        raw = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
        bound = copy.deepcopy(handoff)
        bound["smoke_sha256"] = hashlib.sha256(raw).hexdigest()
        self.assertFalse(release_handoff_ready(bound, qualification, raw))
        self.assertFalse(release_handoff_ready(handoff, qualification, b""))

    def test_coupled_rollback_preserves_history_and_independent_consolidation(self):
        owned = {"producer": ["core/surface/skills/debug/SKILL.md"],
                 "validator": ["core/surface/skills/debug/references/debug-handoff.schema.json"],
                 "consumer": ["core/surface/skills/debug/references/handoff.md"],
                 "helper": ["core/pysrc/_debughandofflib.py"],
                 "generated": ["plugins/ca/hooks/_debughandofflib.py"]}
        plan = {"owned_changes": owned, "rollback_changes": copy.deepcopy(owned),
                "historical_evidence_ids": ["retained-failure", "prior-qualification"],
                "preserved_evidence_ids": ["retained-failure", "prior-qualification"],
                "independent_consolidation_paths": ["core/surface/skills/release/SKILL.md"],
                "retired_wrapper_paths": ["plugins/ca/skills/retired-debug/SKILL.md"]}
        for path in [*(path for paths in owned.values() for path in paths),
                     *plan["independent_consolidation_paths"]]:
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertFalse((ROOT / plan["retired_wrapper_paths"][0]).exists())
        self.assertTrue(rollback_handoff_ready(plan))
        changed = copy.deepcopy(plan)
        changed["rollback_changes"]["generated"] = []
        self.assertFalse(rollback_handoff_ready(changed))
        changed = copy.deepcopy(plan)
        changed["preserved_evidence_ids"].remove("retained-failure")
        self.assertFalse(rollback_handoff_ready(changed))
        for protected in ("independent_consolidation_paths", "retired_wrapper_paths"):
            with self.subTest(protected=protected):
                changed = copy.deepcopy(plan)
                changed["rollback_changes"]["helper"].append(changed[protected][0])
                self.assertFalse(rollback_handoff_ready(changed))

    def test_handoff_does_not_imply_merge_or_publication_authority(self):
        qualification, handoff, smoke_bytes = self._release_handoff_control()
        self.assertTrue(release_handoff_ready(handoff, qualification, smoke_bytes))
        self.assertFalse(release_handoff_ready({**handoff, "version": "9.9.9"},
                                               qualification, smoke_bytes))
        self.assertFalse(release_handoff_ready({**handoff, "merge_approved": True},
                                               qualification, smoke_bytes))
        self.assertFalse(release_handoff_ready({**handoff, "publication_approved": True},
                                               qualification, smoke_bytes))
        owner = (ROOT / "core/surface/skills/release/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Phase 1 ends at the PR boundary", owner)
        self.assertIn("CI success alone never creates authorization", owner)
        self.assertIn("MUST NOT push the tag or create the GitHub Release without explicit user authorization", owner)
    def test_input_bytes_rejects_case_only_full_path_alias(self):
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"] = {"src/report.txt": "a", "src/REPORT.TXT": "b"}
        with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
            _input_bytes(payload)

    def test_input_bytes_rejects_case_only_parent_alias_with_distinct_children(self):
        for files in (
            {"Parent/alpha.txt": "a", "parent/beta.txt": "b"},
            {"UPPER/gamma.txt": "a", "upper/delta.txt": "b"},
        ):
            with self.subTest(files=files):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = files
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_rejects_each_windows_invalid_character(self):
        for character in '<>:"|?*':
            with self.subTest(character=character):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {f"src/bad{character}name.txt": "a"}
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_rejects_each_windows_control_character(self):
        for code in range(32):
            with self.subTest(code=code):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {f"src/control{chr(code)}.txt": "a"}
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_rejects_each_superscript_device_alias(self):
        for device in (
            "NUL .txt", "COM1 .log", "CONIN$", "CONOUT$.txt",
            "COM¹ .txt", "COM² .txt", "COM³ .txt",
            "LPT¹ .txt", "LPT² .txt", "LPT³ .txt",
        ):
            with self.subTest(device=device):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {f"src/{device}": "a"}
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_rejects_each_trailing_period_and_space_component(self):
        for name in (
            "src/report.txt.", "src/report.txt ",
            "src./child.txt", "src /child.txt",
        ):
            with self.subTest(name=name):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {name: "a"}
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_rejects_nested_evaluator_alias(self):
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"] = {"nested/cases.json.": "a"}
        with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
            _input_bytes(payload)

    def test_input_bytes_rejects_file_directory_prefix_collision_in_both_orders(self):
        for files in (
            {"src/result": "a", "src/result/child.txt": "b"},
            {"src/result/child.txt": "b", "src/result": "a"},
        ):
            with self.subTest(files=files):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = files
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_accepts_valid_nested_input_json_and_non_alias_boundaries(self):
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"] = {
            "src/input.json": "permitted nested source",
            "folder.with.dot/read-me.txt": "ordinary file",
            "nested/child/data.bin": "distinct path",
        }
        encoded = _input_bytes(payload)
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded)

    def test_solver_projection_rejects_malformed_input_before_destination_operations(self):
        class ProjectionTripwire:
            def __init__(self, root, relative="", operations=None):
                self.root = root
                self.relative = relative
                self.operations = operations if operations is not None else []

            @property
            def parent(self):
                if not self.relative or "/" not in self.relative:
                    return self
                return type(self)(self.root, self.relative.rsplit("/", 1)[0], self.operations)

            def is_dir(self):
                return self.root.is_dir()

            def iterdir(self):
                return self.root.iterdir() if not self.relative else iter(())

            def __truediv__(self, child):
                child = str(child).replace("\\", "/")
                relative = "/".join(part for part in (self.relative, child) if part)
                return type(self)(self.root, relative, self.operations)

            def joinpath(self, *children):
                result = self
                for child in children:
                    result = result / child
                return result

            def mkdir(self, *args, **kwargs):
                self.operations.append(("mkdir", self.relative))

            def write_text(self, data, *args, **kwargs):
                self.operations.append(("write_text", self.relative))
                return len(data)

        cases = freeze_design()
        cases["solver_inputs"]["V01/default"]["files"] = {"src/report.txt.": "a"}
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            root = Path(tmp)
            before = tuple(root.iterdir())
            destination = ProjectionTripwire(root)
            with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                solver_projection(cases, destination)
            self.assertEqual(tuple(root.iterdir()), before)
            self.assertEqual(destination.operations, [])

    def test_input_bytes_rejects_ambiguous_windows_short_name_aliases(self):
        ambiguous = (
            ("INPUT~1.JSO", "metadata file, uppercase short extension"),
            ("input~1.jso", "metadata file, case variant"),
            ("LONGNA~1.TXT", "long-name file"),
            ("LONGDI~1/child.txt", "long-name directory"),
            ("NESTED~1/LONGNA~1.TXT", "nested long-name file"),
            ("nested~1/INPUT~1.JSO", "nested metadata file"),
        )
        for name, variant in ambiguous:
            with self.subTest(variant=variant, name=name):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {name: "ambiguous short-name spelling"}
                with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
                    _input_bytes(payload)

    def test_input_bytes_accepts_safe_literal_tilde_names(self):
        payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
        payload["files"] = {
            "literal~name.txt": "ordinary literal tilde",
            "nested/tilde~note.md": "nested literal tilde",
        }
        encoded = _input_bytes(payload)
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded)

    def test_later_malformed_payload_is_rejected_before_any_projection_write(self):
        class NonWritingProjectionPath:
            def __init__(self, relative="", operations=None):
                self.relative = relative
                self.operations = operations if operations is not None else []

            @property
            def parent(self):
                if not self.relative or "/" not in self.relative:
                    return self
                return type(self)(self.relative.rsplit("/", 1)[0], self.operations)

            def is_dir(self):
                return True

            def iterdir(self):
                return iter(())

            def __truediv__(self, child):
                child = str(child).replace("\\", "/")
                relative = "/".join(part for part in (self.relative, child) if part)
                return type(self)(relative, self.operations)

            def joinpath(self, *children):
                result = self
                for child in children:
                    result = result / child
                return result

            def mkdir(self, *args, **kwargs):
                self.operations.append(("mkdir", self.relative))

            def write_text(self, data, *args, **kwargs):
                self.operations.append(("write_text", self.relative))
                return len(data)

        cases = freeze_design()
        later_key = sorted(cases["solver_inputs"])[-1]
        cases["solver_inputs"][later_key]["files"] = {
            "docs/later.txt.": "malformed later payload"
        }
        destination = NonWritingProjectionPath()
        with self.assertRaisesRegex(ValueError, "invalid synthetic source path"):
            solver_projection(cases, destination)
        self.assertEqual(destination.operations, [])


    def test_input_bytes_accepts_numeric_tilde_stems_longer_than_short_names(self):
        """An ordinary stem longer than eight characters is not an 8.3 alias."""
        names = (
            "REPORT~123.TXT", "LONGNA~12.TXT", "AB~123456.TXT",
            "ABC~12345.TXT", "ABCDE~123.TXT", "report~123.txt",
            "REPORT~123/child.txt", "nested/LONGNA~12.TXT",
        )
        for name in names:
            with self.subTest(name=name):
                payload = copy.deepcopy(freeze_design()["solver_inputs"]["V01/default"])
                payload["files"] = {name: "ordinary long literal-tilde name"}
                try:
                    encoded = _input_bytes(payload)
                except ValueError as exc:
                    self.fail("Valid long literal-tilde name rejected: " + name + " (" + str(exc) + ")")
                self.assertIsInstance(encoded, bytes)
                self.assertTrue(encoded)

    def test_unknown_metering_zero_rejects_matching_records(self):
        for fields in (("tokens",), ("cost_usd",), ("tokens", "cost_usd")):
            for value in (0, 0.0, -0.0):
                record = sample_record()
                for field in fields:
                    record["metering"][field] = value
                decision = sample_decision(record)
                results = (
                    ("record", validate_record(record)),
                    ("matching-cell", _assess_cell_at(record, copy.deepcopy(record), decision,
                                                      record["case_scope"], "2026-09-29T00:00:00Z")),
                )
                for boundary, accepted in results:
                    with self.subTest(fields=fields, value=value, boundary=boundary):
                        self.assertFalse(accepted)

    def test_observed_zero_metering_has_explicit_availability(self):
        # This is synthetic correspondence, never proof of an actual measurement.
        for fields in (("tokens",), ("cost_usd",), ("tokens", "cost_usd")):
            for value in (0, 0.0, -0.0):
                record = sample_record()
                record["metering"]["availability"] = {
                    key: "observed" if key in fields else "unavailable"
                    for key in ("tokens", "cost_usd")
                }
                for field in fields:
                    record["metering"][field] = value
                before = copy.deepcopy(record)
                decision = sample_decision(record)
                results = (
                    ("record", validate_record(record)),
                    ("matching-cell", _assess_cell_at(record, copy.deepcopy(record), decision,
                                                      record["case_scope"], "2026-09-29T00:00:00Z")),
                )
                for boundary, accepted in results:
                    with self.subTest(fields=fields, value=value, boundary=boundary):
                        self.assertTrue(accepted)
                self.assertEqual(record, before)

    def test_metering_availability_is_closed_and_consistent(self):
        for availability in (None, False, [], "observed", {},
                             {"tokens": "unavailable"},
                             {"tokens": "unavailable", "cost_usd": "unavailable", "extra": True},
                             {"tokens": True, "cost_usd": "unavailable"},
                             {"tokens": "unknown", "cost_usd": "unavailable"},
                             {"tokens": "observed", "cost_usd": "unavailable"}):
            with self.subTest(availability=availability):
                record = sample_record()
                record["metering"]["availability"] = availability
                self.assertFalse(validate_record(record))
                self.assertFalse(_assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                                 record["case_scope"], "2026-09-29T00:00:00Z"))
        for field in ("tokens", "cost_usd"):
            for status, value in (("unavailable", 0), ("unavailable", 1),
                                  ("observed", None), ("observed", False),
                                  ("observed", True), ("observed", -1),
                                  ("observed", float("nan")), ("observed", float("inf")),
                                  ("observed", "0")):
                with self.subTest(field=field, status=status, value=value):
                    record = sample_record()
                    record["metering"]["availability"] = {"tokens": "unavailable", "cost_usd": "unavailable"}
                    record["metering"]["availability"][field] = status
                    record["metering"][field] = value
                    self.assertFalse(validate_record(record))
                    self.assertFalse(_assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                                     record["case_scope"], "2026-09-29T00:00:00Z"))

    def test_explicit_unavailable_metering_retains_null_values(self):
        record = sample_record()
        record["metering"]["availability"] = {"tokens": "unavailable", "cost_usd": "unavailable"}
        before = copy.deepcopy(record)
        results = (
            ("record", validate_record(record)),
            ("matching-cell", _assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                              record["case_scope"], "2026-09-29T00:00:00Z")),
        )
        for boundary, accepted in results:
            with self.subTest(boundary=boundary):
                self.assertTrue(accepted)
        self.assertIsNone(record["metering"]["tokens"])
        self.assertIsNone(record["metering"]["cost_usd"])
        self.assertEqual(record, before)

    def test_campaign_metering_rejects_unmarked_zero_and_retains_explicit_zero(self):
        cases = freeze_design()
        configuration = {"host": "claude", "runtime": "synthetic-runtime/1",
                         "provider": "synthetic-provider", "model": "synthetic-model",
                         "settings": {"temperature": 0}}
        samples = sample_campaign(cases)
        self.assertEqual(len(samples), 111)
        self.assertTrue(campaign_complete(samples, cases, configuration))
        for fields in (("tokens",), ("cost_usd",), ("tokens", "cost_usd")):
            changed = copy.deepcopy(samples)
            meter = changed[0]["record"]["metering"]
            for field in fields:
                meter[field] = 0
            changed[0]["current"]["metering"] = copy.deepcopy(meter)
            before = copy.deepcopy(changed)
            with self.subTest(fields=fields, control="unmarked-zero"):
                self.assertFalse(campaign_complete(changed, cases, configuration))
            self.assertEqual(changed, before)
            meter["availability"] = {
                key: "observed" if key in fields else "unavailable"
                for key in ("tokens", "cost_usd")
            }
            changed[0]["current"]["metering"] = copy.deepcopy(meter)
            before = copy.deepcopy(changed)
            with self.subTest(fields=fields, control="explicit-observed-zero"):
                self.assertTrue(campaign_complete(changed, cases, configuration))
            self.assertEqual(changed, before)
            for field in fields:
                self.assertEqual(changed[0]["record"]["metering"][field], 0)

    def test_metering_availability_extra_field_is_rejected_independently(self):
        # The extra value is otherwise valid, so status checking cannot mask shape admission.
        for extra_value in ("observed", "unavailable"):
            record = sample_record()
            record["metering"]["availability"] = {
                "tokens": "unavailable", "cost_usd": "unavailable", "extra": extra_value,
            }
            before = copy.deepcopy(record)
            with self.subTest(extra_value=extra_value):
                self.assertFalse(validate_record(record))
                self.assertFalse(_assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                                 record["case_scope"], "2026-09-29T00:00:00Z"))
            self.assertEqual(record, before)

    def test_metering_availability_unknown_status_is_rejected_independently(self):
        # A valid positive observation ensures numeric/null checks cannot mask the status enum.
        for field in ("tokens", "cost_usd"):
            record = sample_record()
            record["metering"]["availability"] = {"tokens": "unavailable", "cost_usd": "unavailable"}
            record["metering"]["availability"][field] = "observed"
            record["metering"][field] = 1
            self.assertTrue(validate_record(record))
            self.assertTrue(_assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                            record["case_scope"], "2026-09-29T00:00:00Z"))
            for status in ("unknown", True, False, None, 1, [], {}):
                changed = copy.deepcopy(record)
                changed["metering"]["availability"][field] = status
                before = copy.deepcopy(changed)
                with self.subTest(field=field, status=status):
                    self.assertFalse(validate_record(changed))
                    self.assertFalse(_assess_cell_at(changed, copy.deepcopy(changed), sample_decision(changed),
                                                     changed["case_scope"], "2026-09-29T00:00:00Z"))
                self.assertEqual(changed, before)






    def test_projection_rejects_private_oracle_bytes_before_writing_any_trial(self):
        # Check actual projected source and metadata, including the final case,
        # so a late contaminated input cannot leak after earlier writes.
        for pretty in (False, True):
            for location in ("source", "request", "observation"):
                with self.subTest(pretty=pretty, location=location):
                    cases = freeze_design()
                    key = sorted(cases["solver_inputs"])[-1]
                    private = json.dumps(cases["oracles"][key], sort_keys=True,
                                         indent=2 if pretty else None)
                    payload = cases["solver_inputs"][key]
                    if location == "source":
                        payload["files"]["src/projected_answers.txt"] = private
                    elif location == "request":
                        payload["request"] += "\n" + private
                    else:
                        payload["observations"][0]["detail"] += "\n" + private
                    with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
                        with self.assertRaises(ValueError):
                            solver_projection(cases, Path(tmp))
                        self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_projection_boundary_control_checks_every_projected_file(self):
        cases = freeze_design()
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            metadata = solver_projection(cases, Path(tmp))
            self.assertEqual(len(metadata), 17)
            all_files = sorted(path for path in Path(tmp).rglob("*") if path.is_file())
            self.assertGreater(len(all_files), len(metadata))
            expected = set()
            for number, key in enumerate(sorted(cases["solver_inputs"]), 1):
                prefix = f"trial-{number:04d}/"
                expected.add(prefix + "input.json")
                expected.update(prefix + name for name in cases["solver_inputs"][key]["files"])
            self.assertEqual({path.relative_to(tmp).as_posix() for path in all_files}, expected)
            for path in all_files:
                with self.subTest(file=path.relative_to(tmp).as_posix()):
                    raw = path.read_bytes()
                    self.assertNotIn(b'"ground_truth_basis"', raw)
                    self.assertNotIn(b'"expected_disposition"', raw)
                    self.assertNotIn(b'"required_evidence_ids"', raw)

    def test_campaign_rejects_missing_session_identity_even_when_labels_are_complete(self):
        cases = freeze_design()
        for host in ("claude", "codex"):
            samples = sample_campaign(cases, host=host)
            configuration = {key: samples[0]["record"][key]
                             for key in ("host", "runtime", "provider", "model", "settings")}
            self.assertTrue(campaign_complete(samples, cases, configuration))
            for remove_all in (False, True):
                with self.subTest(host=host, remove_all=remove_all):
                    changed = copy.deepcopy(samples)
                    selected = changed if remove_all else changed[:1]
                    for cell in selected:
                        cell["record"].pop("session", None)
                        for evidence in cell["record"]["evidence"]:
                            evidence["subject_sha256"] = tuple_identity(cell["record"])
                        cell["current"] = copy.deepcopy(cell["record"])
                        cell["decision"] = sample_decision(cell["record"])
                    self.assertFalse(campaign_complete(changed, cases, configuration))

    def test_session_freshness_record_is_closed_typed_and_bound_to_the_cell(self):
        record = sample_record()
        session = record.get("session")
        self.assertIsInstance(session, dict, "session freshness is absent from the record")
        self.assertEqual(set(session), {"id", "launch_id", "initial_turn_count", "resumed_from"})
        self.assertTrue(_nonempty(session["id"]))
        self.assertTrue(_nonempty(session["launch_id"]))
        self.assertIs(type(session["initial_turn_count"]), int)
        self.assertEqual(session["initial_turn_count"], 0)
        self.assertIsNone(session["resumed_from"])
        self.assertTrue(validate_record(record))
        for field, value in (("id", ""), ("id", True), ("id", None),
                             ("launch_id", " "), ("launch_id", []),
                             ("initial_turn_count", True), ("initial_turn_count", -1),
                             ("initial_turn_count", 1), ("initial_turn_count", 0.0),
                             ("resumed_from", "old-session"), ("resumed_from", False)):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(record)
                bad["session"][field] = value
                for evidence in bad["evidence"]:
                    evidence["subject_sha256"] = tuple_identity(bad)
                self.assertFalse(validate_record(bad))
        for field in session:
            with self.subTest(missing=field):
                bad = copy.deepcopy(record)
                del bad["session"][field]
                self.assertFalse(validate_record(bad))
        extra = copy.deepcopy(record)
        extra["session"]["claimed_fresh"] = True
        self.assertFalse(validate_record(extra))
        for field in ("id", "launch_id"):
            with self.subTest(binding=field):
                changed = copy.deepcopy(record)
                changed["session"][field] += "-different"
                self.assertNotEqual(tuple_identity(record), tuple_identity(changed))
                for evidence in changed["evidence"]:
                    evidence["subject_sha256"] = tuple_identity(changed)
                self.assertTrue(validate_record(changed))
                self.assertFalse(_assess_cell_at(record, changed, sample_decision(record),
                                                 record["case_scope"], "2026-09-29T00:00:00Z"))

    def test_campaign_rejects_reused_session_or_launch_across_repetitions_and_arms(self):
        cases = freeze_design()
        for host in ("claude", "codex"):
            samples = sample_campaign(cases, host=host)
            configuration = {key: samples[0]["record"][key]
                             for key in ("host", "runtime", "provider", "model", "settings")}
            self.assertTrue(campaign_complete(samples, cases, configuration))
            for cell in samples:
                self.assertIsInstance(cell["record"].get("session"), dict,
                                      "trial labels are not session identities")
            for field in ("id", "launch_id"):
                self.assertEqual(len({cell["record"]["session"][field] for cell in samples}), len(samples))
                # Same-arm repetition, other arm, other case, and safety case.
                for index in (1, 3, 6, len(samples)-1):
                    with self.subTest(host=host, field=field, target=index):
                        changed = copy.deepcopy(samples)
                        record = changed[index]["record"]
                        record["session"][field] = changed[0]["record"]["session"][field]
                        for evidence in record["evidence"]:
                            evidence["subject_sha256"] = tuple_identity(record)
                        changed[index]["current"] = copy.deepcopy(record)
                        changed[index]["decision"] = sample_decision(record)
                        self.assertTrue(validate_record(record))
                        self.assertFalse(campaign_complete(changed, cases, configuration))



    def test_projection_rejects_private_answer_text_without_oracle_field_names(self):
        for location in ("source", "request", "observation"):
            with self.subTest(location=location):
                cases = freeze_design()
                key = sorted(cases["solver_inputs"])[-1]
                answer = cases["oracles"][key]["ground_truth_basis"]
                self.assertTrue(_nonempty(answer))
                self.assertNotIn(answer, json.dumps(cases["solver_inputs"], ensure_ascii=False))
                payload = cases["solver_inputs"][key]
                if location == "source":
                    payload["files"]["notes/explanation.txt"] = answer
                elif location == "request":
                    payload["request"] += "\n" + answer
                else:
                    payload["observations"][0]["detail"] += "\n" + answer
                with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
                    with self.assertRaises(ValueError):
                        solver_projection(cases, Path(tmp))
                    self.assertEqual(list(Path(tmp).iterdir()), [])



    def test_session_false_turn_count_and_wrong_container_fail_independently(self):
        record = sample_record()
        record["session"] = {"id": "synthetic-independent-session",
                             "launch_id": "synthetic-independent-launch",
                             "initial_turn_count": 0, "resumed_from": None}
        for evidence in record["evidence"]:
            evidence["subject_sha256"] = tuple_identity(record)
        self.assertTrue(validate_record(record))
        self.assertTrue(_assess_cell_at(record, copy.deepcopy(record), sample_decision(record),
                                        record["case_scope"], "2026-09-29T00:00:00Z"))
        # False equals zero in Python. A nonfresh-count check cannot stand in
        # for an exact-integer check; every other field is valid here.
        invalid = [None, [], "fresh", False, {},
                   {**record["session"], "initial_turn_count": False}]
        for session in invalid:
            with self.subTest(session=session):
                bad = copy.deepcopy(record)
                bad["session"] = session
                for evidence in bad["evidence"]:
                    evidence["subject_sha256"] = tuple_identity(bad)
                self.assertFalse(validate_record(bad))


    def test_criterion_readiness_binds_frozen_case_input_after_full_record_rebinding(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        payloads = {**cases["solver_inputs"], **cases["candidate_safety_inputs"]}
        frozen = {}
        for key, payload in payloads.items():
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            frozen[key] = hashlib.sha256(raw).hexdigest()
            declared = (cases["oracles"][key]["input_sha256"] if key in cases["oracles"]
                        else cases["candidate_safety_sha256"][key])
            self.assertEqual(frozen[key], declared)
        self.assertEqual(len(frozen), 20)

        def rebind(row):
            for evidence in row["record"]["evidence"]:
                evidence["subject_sha256"] = tuple_identity(row["record"])
            row["current"] = copy.deepcopy(row["record"])
            row["decision"] = sample_decision(row["record"])
            row["binding_sha256"] = record_binding(row)

        # Supply a correct control independently of the historical helper's
        # V01 default; this changes no existing assertion or implementation.
        for row in rows:
            if row["case_key"] in frozen:
                row["record"]["case_input_sha256"] = frozen[row["case_key"]]
                rebind(row)
        self.assertTrue(criterion_records_ready(rows, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        targets = {}
        for index, row in enumerate(rows):
            if row["case_key"] in frozen:
                targets.setdefault((row["case_key"], row["layer"], row["record"]["host"]), index)
        self.assertEqual({key for key, _layer, _host in targets}, set(frozen))
        for (case_key, layer, host), index in targets.items():
            wrong_input = next(digest for digest in frozen.values() if digest != frozen[case_key])
            with self.subTest(case_key=case_key, layer=layer, host=host):
                changed = copy.deepcopy(rows)
                row = changed[index]
                row["record"]["case_input_sha256"] = wrong_input
                rebind(row)
                self.assertTrue(validate_record(row["record"]))
                self.assertTrue(_current_cell_matches(row["record"], row["current"]))
                self.assertFalse(criterion_records_ready(changed, cases, source, tests, head,
                                                         required, campaigns, ["required-debug-suite"], ci,
                                                         [], artifacts),
                                 "criterion input mismatch was accepted after complete record rebinding")


    def test_readiness_rejects_replaced_frozen_payload_with_matching_supplied_digest(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        self.assertTrue(criterion_records_ready(rows, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        for family in ("solver_inputs", "candidate_safety_inputs"):
            for case_key in cases[family]:
                with self.subTest(family=family, case_key=case_key):
                    changed_cases, changed_rows = copy.deepcopy(cases), copy.deepcopy(rows)
                    payload = changed_cases[family][case_key]
                    payload["request"] += " (different frozen input)"
                    replacement = hashlib.sha256(_input_bytes(payload)).hexdigest()
                    if family == "solver_inputs":
                        self.assertNotEqual(replacement, cases["oracles"][case_key]["input_sha256"])
                        changed_cases["oracles"][case_key]["input_sha256"] = replacement
                    else:
                        self.assertNotEqual(replacement, cases["candidate_safety_sha256"][case_key])
                        changed_cases["candidate_safety_sha256"][case_key] = replacement
                    for row in changed_rows:
                        if row["case_key"] != case_key:
                            continue
                        row["record"]["case_input_sha256"] = replacement
                        for evidence in row["record"]["evidence"]:
                            evidence["subject_sha256"] = tuple_identity(row["record"])
                        row["current"] = copy.deepcopy(row["record"])
                        row["decision"] = sample_decision(row["record"])
                        row["binding_sha256"] = record_binding(row)
                    changed_campaigns = [{"configuration": config,
                                          "samples": sample_campaign(changed_cases, config["host"]),
                                          "status": "passed"} for config in required]
                    self.assertFalse(criterion_records_ready(changed_rows, changed_cases, source, tests, head,
                                                             required, changed_campaigns, ["required-debug-suite"],
                                                             ci, [], artifacts),
                                     "caller payload and digest replaced the frozen input together")

    def test_readiness_rejects_malformed_case_keys_without_raising(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        self.assertTrue(criterion_records_ready(rows, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        for key in ([], ["V01/default"], {}, {"case": "V01/default"}, None, 0, True, ""):
            with self.subTest(case_key=repr(key)):
                changed = copy.deepcopy(rows)
                changed[0]["case_key"] = key
                try:
                    result = criterion_records_ready(changed, cases, source, tests, head,
                                                     required, campaigns, ["required-debug-suite"], ci, [], artifacts)
                except (TypeError, KeyError, ValueError) as exc:
                    self.fail("malformed case_key escaped controlled rejection: " + type(exc).__name__)
                else:
                    self.assertFalse(result)

    def test_readiness_rejects_replaced_fixture_file_even_with_consistent_records(self):
        from unittest.mock import patch
        baseline = freeze_design()
        for family, case_key in (("solver_inputs", "V01/default"), ("candidate_safety_inputs", "V05/default")):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp)
                for name in ("cases.json", "qualification-cells.json", "handoff-examples.json"):
                    (destination / name).write_bytes((FIXTURES / name).read_bytes())
                changed = copy.deepcopy(baseline)
                changed[family][case_key]["request"] += " (replaced local fixture)"
                replacement = hashlib.sha256(_input_bytes(changed[family][case_key])).hexdigest()
                if family == "solver_inputs":
                    changed["oracles"][case_key]["input_sha256"] = replacement
                else:
                    changed["candidate_safety_sha256"][case_key] = replacement
                (destination / "cases.json").write_text(json.dumps(changed), encoding="utf-8")
                with patch.dict(globals(), {"FIXTURES": destination}):
                    cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
                    self.assertEqual(cases, changed)
                    self.assertFalse(criterion_records_ready(rows, cases, source, tests, head,
                                                             required, campaigns, ["required-debug-suite"],
                                                             ci, [], artifacts),
                                     "a replaced local fixture and consistent records bypassed the frozen anchor")




    def _mutated_campaign_sample(self, sample, field, value):
        item = copy.deepcopy(sample)
        if field == "case_key":
            item["case_key"] = copy.deepcopy(value)
            item["record"]["case_scope"] = [copy.deepcopy(value)]
        elif field == "arm":
            item["arm"] = copy.deepcopy(value)
            item["record"]["trial_arm"] = copy.deepcopy(value)
        elif field == "repetition":
            item["record"]["repetition"] = copy.deepcopy(value)
        else:
            self.fail("unknown campaign mutation field")
        for evidence in item["record"]["evidence"]:
            evidence["subject_sha256"] = tuple_identity(item["record"])
        item["current"] = copy.deepcopy(item["record"])
        item["decision"] = sample_decision(item["record"])
        return item

    def test_campaign_malformed_tuple_fields_return_false_without_raising(self):
        cases = freeze_design()
        invalid = ([], ["V01/default"], {}, {"case": "V01/default"},
                   None, True, 0, "", "unknown", "x" * 8193)
        for host in ("claude", "codex"):
            samples = sample_campaign(cases, host)
            configuration = {key: copy.deepcopy(samples[0]["record"][key])
                             for key in ("host", "runtime", "provider", "model", "settings")}
            self.assertTrue(campaign_complete(samples, cases, configuration))
            for field in ("case_key", "arm", "repetition"):
                for value in invalid:
                    with self.subTest(host=host, field=field, value=repr(value)):
                        changed = copy.deepcopy(samples)
                        changed[0] = self._mutated_campaign_sample(changed[0], field, value)
                        try:
                            result = campaign_complete(changed, cases, configuration)
                        except (TypeError, AttributeError, KeyError, ValueError) as exc:
                            self.fail("malformed campaign tuple escaped controlled rejection: " + type(exc).__name__)
                        else:
                            self.assertFalse(result)
            self.assertTrue(campaign_complete(samples, cases, configuration))

    def test_readiness_rejects_malformed_campaign_keys_without_raising(self):
        cases, rows, source, tests, head, required, campaigns, ci, artifacts = self._criterion_control()
        self.assertTrue(criterion_records_ready(rows, cases, source, tests, head,
                                                required, campaigns, ["required-debug-suite"], ci, [], artifacts))
        for index in range(len(campaigns)):
            for key in ([], ["V01/default"], {}, {"case": "V01/default"}):
                with self.subTest(host=campaigns[index]["configuration"]["host"], key=repr(key)):
                    changed = copy.deepcopy(campaigns)
                    changed[index]["samples"][0] = self._mutated_campaign_sample(
                        changed[index]["samples"][0], "case_key", key)
                    try:
                        result = criterion_records_ready(rows, cases, source, tests, head,
                                                         required, changed, ["required-debug-suite"], ci, [], artifacts)
                    except (TypeError, AttributeError, KeyError, ValueError) as exc:
                        self.fail("malformed campaign key escaped readiness rejection: " + type(exc).__name__)
                    else:
                        self.assertFalse(result)

    def test_projection_rejects_private_oracle_tokens_in_file_and_directory_names(self):
        frozen = freeze_design()
        tokens = {oracle["ground_truth_basis"] for oracle in frozen["oracles"].values()}
        self.assertEqual(len(tokens), 17)
        for token in sorted(tokens):
            for location in ("filename", "directory"):
                with self.subTest(token=token, location=location):
                    cases = copy.deepcopy(frozen)
                    key = sorted(cases["solver_inputs"])[-1]
                    name = ("notes/leaked-" + token + "-answer.txt" if location == "filename"
                            else "leaked-" + token + "-answer/safe.txt")
                    cases["solver_inputs"][key]["files"][name] = "synthetic ordinary source\n"
                    # Demonstrate that source-path syntax is valid; the oracle
                    # boundary must reject it before any trial is materialized.
                    self.assertIsInstance(_input_bytes(cases["solver_inputs"][key]), bytes)
                    with tempfile.TemporaryDirectory(prefix="dcp-projection-") as tmp:
                        with self.assertRaisesRegex(ValueError, "private oracle"):
                            solver_projection(cases, Path(tmp))
                        self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_projection_allows_benign_filename_boundary_vocabulary(self):
        cases = freeze_design()
        key = sorted(cases["solver_inputs"])[-1]
        name = "notes/ordinary-boundary-guide.txt"
        content = "Synthetic developer notes without evaluator answers.\n"
        cases["solver_inputs"][key]["files"][name] = content
        with tempfile.TemporaryDirectory(prefix="dcp-projection-control-") as tmp:
            written = solver_projection(cases, Path(tmp))
            self.assertEqual(len(written), 17)
            self.assertEqual((Path(tmp) / "trial-0017" / name).read_text(encoding="utf-8"), content)




if __name__ == "__main__":
    unittest.main()
