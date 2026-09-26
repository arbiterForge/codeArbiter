#!/usr/bin/env python3
"""Exercise the actual artifact CLI and retain native statement coverage.

The instrumented executable is a disposable test build, never an installed or
release-qualified candidate. Production bridge environment isolation is intact.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "core/artifacts"
PROTOCOL = "codearbiter.artifact-api/0.1.0"
BINARY: Path | None = None
COUNTERS: Path | None = None


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-cli-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve(strict=True)

    def invoke(self, operation="capabilities", request=None, *, raw=None, flags=()):
        self.assertIsNotNone(BINARY, "run this suite through its script entry point")
        arguments = [str(BINARY)]
        if operation is not None:
            arguments.append(operation)
            arguments.extend(["--root", str(self.root)])
        if request is not None:
            raw = json.dumps({"protocol": PROTOCOL, **request}).encode()
        if raw is not None:
            arguments.extend(["--request", "-"])
        arguments.extend(flags)
        # Only the test executable receives this explicit coverage destination.
        environment = {"GOCOVERDIR": str(COUNTERS)}
        for name in ("SystemRoot", "WINDIR"):
            if name in os.environ:
                environment[name] = os.environ[name]
        result = subprocess.run(arguments, input=raw, capture_output=True,
                                cwd=self.root, env=environment, timeout=30)
        self.assertLessEqual(len(result.stdout), 65536)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["protocol"], PROTOCOL)
        return result, envelope

    def assert_error(self, result, envelope, code):
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], code)
        self.assertIn(code.encode(), result.stderr)

    def test_default_and_help_report_capabilities(self):
        for operation in (None, "capabilities", "--version", "--help", "help"):
            with self.subTest(operation=operation):
                result, envelope = self.invoke(operation)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(envelope["ok"])
                self.assertEqual(envelope["operation"], "capabilities")
                self.assertTrue(envelope["result"]["repository_operations_available"])
                self.assertEqual(envelope["result"]["public_registrations_added"], 0)

    def test_invalid_requests_preserve_the_repository(self):
        cases = [
            (b"{", "INVALID_JSON"),
            (b"[]", "INVALID_REQUEST"),
            (b'{} {}', "TRAILING_JSON"),
        ]
        for raw, code in cases:
            with self.subTest(code=code):
                result, envelope = self.invoke(raw=raw)
                self.assert_error(result, envelope, code)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_argument_and_request_file_errors_are_structured(self):
        cases = [
            (("--unknown",), "INVALID_ARGUMENT"),
            (("unexpected-positional",), "INVALID_ARGUMENT"),
            (("--request", str(self.root / "missing.json")), "REQUEST_UNAVAILABLE"),
        ]
        for flags, code in cases:
            with self.subTest(code=code, flags=flags):
                result, envelope = self.invoke(flags=flags)
                self.assert_error(result, envelope, code)
        result, envelope = self.invoke("not-an-operation")
        self.assert_error(result, envelope, "UNKNOWN_OPERATION")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_request_file_and_stdin_have_the_same_protocol_result(self):
        request = self.root / "request.json"
        request.write_text(json.dumps({"protocol": PROTOCOL}), encoding="utf-8")
        file_result, file_envelope = self.invoke(flags=("--request", str(request)))
        stdin_result, stdin_envelope = self.invoke(request={})
        self.assertEqual(file_result.returncode, 0, file_result.stderr)
        self.assertEqual(stdin_result.returncode, 0, stdin_result.stderr)
        self.assertEqual(file_envelope, stdin_envelope)

    def test_draft_creation_and_validation_exit_status(self):
        result, envelope = self.invoke("create", {
            "operation_id": "cli-draft-fixture", "artifact_id": "SPEC-CLI-FIXTURE",
            "kind": "spec", "slug": "cli-fixture", "title": "CLI fixture",
            "summary": "Disposable unapproved draft for executable tests.",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(envelope["ok"])
        result, envelope = self.invoke("validate", {
            "artifact_id": "SPEC-CLI-FIXTURE", "gate": "structural",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(envelope["ok"])
        self.assertTrue(envelope["result"]["valid"])
        result, envelope = self.invoke("validate", {
            "artifact_id": "SPEC-CLI-FIXTURE", "gate": "approved",
        })
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(envelope["ok"])
        self.assertFalse(envelope["result"]["valid"])


def main() -> int:
    global BINARY, COUNTERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.coverage_output.absolute()
    if output.exists() or output.with_suffix(output.suffix + ".json").exists():
        parser.error("coverage output and sidecar must be new files")
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("artifact_coverage", REPO / "tools/artifact-coverage.py")
    assert spec is not None and spec.loader is not None
    coverage = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = coverage
    spec.loader.exec_module(coverage)
    identity = coverage.source_identity(MODULE)
    environment = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off",
                       GOWORK="off", GOENV="off", GOFLAGS="", CGO_ENABLED="0")
    with tempfile.TemporaryDirectory(prefix="ca-cli-coverage-") as directory:
        scratch = Path(directory).resolve(strict=True)
        BINARY = scratch / ("ca-artifact.exe" if os.name == "nt" else "ca-artifact")
        COUNTERS = scratch / "counters"
        COUNTERS.mkdir()
        subprocess.run([
            "go", "build", "-buildvcs=false", "-cover", "-covermode=atomic",
            "-coverpkg=./...", "-o", str(BINARY), "./cmd/ca-artifact",
        ], cwd=MODULE, env=environment, check=True)
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(CliTests))
        if not result.wasSuccessful():
            return 1
        subprocess.run([
            "go", "tool", "covdata", "textfmt", "-i=" + str(COUNTERS), "-o=" + str(output),
        ], cwd=MODULE, env=environment, check=True)
    metadata = coverage.integration_metadata(MODULE, output, identity)
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"integration_profile": str(output), "tests": result.testsRun}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
