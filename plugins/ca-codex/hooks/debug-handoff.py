# codeArbiter — private bounded debug handoff validation entry.
# Read only stdin and the installed validator; emit closed, redacted diagnostics.
# Bytecode suppression precedes the local import and no project state is touched.
#
# main(argv) -> int: validate one bounded packet and write one result envelope.
import sys

sys.dont_write_bytecode = True

import json
import re

import _debughandofflib as handoff


PROTOCOL = "codearbiter.debug-validation/1.0.0"
DIRECT_CODES = frozenset({
    "INPUT_LIMIT", "DEPTH_LIMIT", "INVALID_UTF8", "INVALID_JSON",
    "DUPLICATE_KEY", "UNSUPPORTED_PROTOCOL", "REQUIRED_FIELD",
    "UNKNOWN_FIELD", "TYPE", "VALUE",
})
REFERENCE_CODES = frozenset({"DUPLICATE_ID", "DANGLING_REFERENCE"})
PATH = re.compile(r"\$(?:\.[A-Za-z_]+|\[[0-9]+\])*\Z", re.ASCII)


def _result(valid, errors, truncated=False):
    return {"protocol": PROTOCOL, "valid": valid,
            "errors": errors, "truncated": truncated}


def _diagnostic(code, path="$"):
    if code in DIRECT_CODES or code in ("USAGE", "INPUT_IO", "INTERNAL"):
        public_code = code
    elif code in REFERENCE_CODES:
        public_code = "REFERENCE"
    else:
        public_code = "SEMANTIC"
    if type(path) is not str or len(path) > 256 or not PATH.fullmatch(path):
        return {"code": "INTERNAL", "path": "$"}
    return {"code": public_code, "path": path}


def _write(result):
    raw = (json.dumps(result, ensure_ascii=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    if len(raw) > 8192:
        result = _result(False, [{"code": "INTERNAL", "path": "$"}])
        raw = (json.dumps(result, separators=(",", ":")) + "\n").encode("utf-8")
        exit_code = 3
    else:
        exit_code = 0 if result["valid"] else 2
        if result["errors"] and result["errors"][0]["code"] in ("INPUT_IO", "INTERNAL"):
            exit_code = 3
    try:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    except OSError:
        return 3
    return exit_code


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv != ["validate"]:
        return _write(_result(False, [_diagnostic("USAGE")]))
    try:
        raw = sys.stdin.buffer.read(65537)
    except OSError:
        return _write(_result(False, [_diagnostic("INPUT_IO")]))
    except Exception:
        return _write(_result(False, [_diagnostic("INTERNAL")]))
    try:
        packet, error = handoff.decode_packet(raw)
        if error is not None:
            return _write(_result(False, [_diagnostic(error)]))
        found, truncated = handoff.validate_semantics_bounded(packet, ceiling=16)
        errors = [_diagnostic(code, path) for code, path in found]
        return _write(_result(not found, errors, truncated))
    except Exception:
        return _write(_result(False, [_diagnostic("INTERNAL")]))


if __name__ == "__main__":
    raise SystemExit(main())
