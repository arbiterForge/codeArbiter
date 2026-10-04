"""Source-only T-007 handoff fixture harness.

These assertions preserve original example bytes and distinguish the source
package's shape and semantic counterexamples. They do not validate a production
packet or establish any host, model, or approval result.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / ".github" / "fixtures" / "debug"
ORIGINAL = (
    "valid-unresolved",
    "valid-code-defect-causal-trace",
    "valid-code-defect-existing-red",
    "valid-noncode-with-authority-blocker",
    "valid-design-question",
    "valid-no-action",
    "invalid-unknown-authority-field",
    "invalid-protocol",
    "invalid-no-action-task",
    "invalid-boolean-exit-code",
    "invalid-dangling-evidence",
    "invalid-duplicate-evidence-id",
    "invalid-planned-check-as-reproduction",
    "invalid-conflicting-evidence-reference",
)
EXPECTED_LAYER = {
    **{name: "valid" for name in ORIGINAL[:6]},
    **{name: "shape" for name in ORIGINAL[6:10]},
    **{name: "semantic" for name in ORIGINAL[10:]},
}


def original_layer(packet):
    """Inspect only failure modes supplied by the fourteen original examples.

    This fixture-side discriminator is deliberately narrower than the future
    production validator. A passing result here is source-record evidence only.
    """
    root_fields = {
        "protocol", "case_id", "request", "snapshots", "symptom",
        "reproduction", "hypotheses", "checks", "evidence",
        "disposition", "next_step", "regression",
    }
    if set(packet) != root_fields:
        return "shape"
    if packet["protocol"] != "codearbiter.debug-handoff/1.0.0":
        return "shape"
    if (packet["disposition"]["kind"] == "no_action"
            and packet["next_step"]["target"] != "none"):
        return "shape"
    if any(check["exit_code"] is not None and type(check["exit_code"]) is not int
           for check in packet["checks"]):
        return "shape"

    evidence = packet["evidence"]
    ids = [item["id"] for item in evidence]
    if len(ids) != len(set(ids)):
        return "semantic"
    known_ids = set(ids)
    referenced = [
        *packet["symptom"]["expected_evidence_ids"],
        *packet["reproduction"]["evidence_ids"],
        *packet["disposition"]["evidence_ids"],
    ]
    for hypothesis in packet["hypotheses"]:
        supporting = set(hypothesis["supporting_evidence_ids"])
        opposing = set(hypothesis["opposing_evidence_ids"])
        if supporting & opposing:
            return "semantic"
        referenced.extend(supporting | opposing)
    for check in packet["checks"]:
        referenced.extend(check["evidence_ids"])
    if any(ref not in known_ids for ref in referenced):
        return "semantic"
    checks = {check["id"]: check for check in packet["checks"]}
    for item in evidence:
        check_id = item["check_id"]
        if (item["id"] in packet["reproduction"]["evidence_ids"]
                and check_id is not None
                and checks[check_id]["status"] != "completed"):
            return "semantic"
    return "valid"


def _no_selected_assertions():
    raise AssertionError("zero handoff assertions selected")


def load_tests(loader, tests, pattern):
    """Reject a selector that finds no assertions at the module entry."""
    if tests.countTestCases() == 0:
        return unittest.TestSuite([unittest.FunctionTestCase(_no_selected_assertions)])
    return tests


class HandoffFixtureTest(unittest.TestCase):
    def test_original_examples_keep_shape_and_semantic_classification(self):
        data = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        self.assertEqual(data["format"], "codearbiter.debug-handoff-examples/1")
        self.assertEqual(data["status"], "SOURCE_IDENTITIES_ONLY")
        self.assertEqual(data["product_status"], "PENDING")
        self.assertEqual(tuple(row["id"] for row in data["examples"]), ORIGINAL)
        for row in data["examples"]:
            with self.subTest(example=row["id"]):
                raw = base64.b64decode(row["payload_b64"], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["payload_sha256"])
                self.assertEqual(
                    row["expected"],
                    "valid_shape_and_semantic_cross_references"
                    if EXPECTED_LAYER[row["id"]] == "valid" else "reject",
                )
                packet = json.loads(raw.decode("utf-8"))
                self.assertEqual(original_layer(packet), EXPECTED_LAYER[row["id"]])

    def test_zero_selected_assertions_fail(self):
        selector = unittest.TestLoader()
        selector.testNamePatterns = ["a_name_no_handoff_test_has"]
        empty = selector.loadTestsFromTestCase(HandoffFixtureTest)
        self.assertEqual(empty.countTestCases(), 0)
        guarded = load_tests(selector, empty, None)
        result = unittest.TestResult()
        guarded.run(result)
        self.assertGreater(result.testsRun, 0)
        self.assertFalse(result.wasSuccessful())

    def test_original_layer_mutants_are_observed(self):
        data = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        packets = {
            row["id"]: json.loads(base64.b64decode(row["payload_b64"]))
            for row in data["examples"]
        }
        shape_mutant = copy.deepcopy(packets["valid-no-action"])
        shape_mutant["approval"] = True
        self.assertEqual(original_layer(shape_mutant), "shape")
        semantic_mutant = copy.deepcopy(packets["valid-code-defect-causal-trace"])
        semantic_mutant["hypotheses"][0]["supporting_evidence_ids"].append("E-99")
        self.assertEqual(original_layer(semantic_mutant), "semantic")


# T-008 production-layer primitive obligations. Keep the T-007 assertions above intact.
import importlib.util
import subprocess
import sys
import tempfile


def _debug_lib():
    path = ROOT / "core" / "pysrc" / "_debughandofflib.py"
    spec = importlib.util.spec_from_file_location("_debughandofflib_t008", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandoffPrimitiveTest(unittest.TestCase):
    def _packet(self):
        data = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        row = next(row for row in data["examples"] if row["id"] == "valid-code-defect-existing-red")
        return json.loads(base64.b64decode(row["payload_b64"]))

    def test_full_string_ids_reject_trailing_controls(self):
        lib = _debug_lib()
        packet = self._packet()
        self.assertEqual(lib.validate_primitives(packet), [])
        for field, bad in (("case_id", "DBG-abc\n"), ("case_id", "DBG-abc\x00")):
            with self.subTest(field=field, bad=repr(bad)):
                changed = copy.deepcopy(packet)
                changed[field] = bad
                self.assertIn(("VALUE", "$.case_id"), lib.validate_primitives(changed))
        for kind, value in (("evidence_id", "E-01\n"), ("snapshot_id", "S-12\r"),
                            ("hypothesis_id", "H-00\x00"), ("check_id", "C-01\n"),
                            ("git_oid", "a" * 40 + "\n"), ("sha256", "sha256:" + "a" * 64 + "\n"),
                            ("recipe_name", "local/1\n")):
            with self.subTest(kind=kind):
                self.assertFalse(lib.valid_primitive(kind, value))
        cases = json.loads((ROOT / "docs/proposals/debug-correctness/D1-CASES.json").read_text(encoding="utf-8"))
        for row in cases["primitive_vectors"]:
            if row["kind"] not in ("case_id", "evidence_id"):
                continue
            with self.subTest(vector=row["id"]):
                self.assertEqual(lib.valid_primitive(row["kind"], row["input"]), row["expected"])

    def test_exact_numeric_timestamp_and_unicode_profiles(self):
        lib = _debug_lib()
        cases = json.loads((ROOT / "docs/proposals/debug-correctness/D1-CASES.json").read_text(encoding="utf-8"))
        for row in cases["primitive_vectors"]:
            if row["kind"] not in ("timestamp", "integer_lexeme", "text"):
                continue
            value = row["input"]
            if row["kind"] == "integer_lexeme":
                value = lib.JsonNumber(value)
            elif row["kind"] == "text":
                value = (value["value"], value["limit"])
            with self.subTest(vector=row["id"]):
                self.assertEqual(lib.valid_primitive(row["kind"], value), row["expected"])
        packet = self._packet()
        packet["checks"][0]["exit_code"] = False
        self.assertIn(("TYPE", "$.checks[0].exit_code"), lib.validate_primitives(packet))
        packet["checks"][0]["exit_code"] = lib.JsonNumber("2.0")
        self.assertEqual(lib.validate_primitives(packet), [])
        packet["evidence"][0]["observed_at"] = "1900-02-29T00:00:00Z"
        self.assertIn(("VALUE", "$.evidence[0].observed_at"), lib.validate_primitives(packet))
        packet["evidence"][0]["observed_at"] = "2024-02-29t00:00:00-00:00"
        self.assertEqual(lib.validate_primitives(packet), [])
        packet["evidence"][0]["observation"] = "\U0001f600"
        self.assertEqual(lib.validate_primitives(packet), [])
        packet["evidence"][0]["observation"] = "\u0085\u00a0"
        self.assertIn(("VALUE", "$.evidence[0].observation"), lib.validate_primitives(packet))
        packet["evidence"][0]["observation"] = "x" * 2001
        self.assertIn(("VALUE", "$.evidence[0].observation"), lib.validate_primitives(packet))

    def test_import_creates_no_effects(self):
        path = ROOT / "core/pysrc/_debughandofflib.py"
        script = r'''
import builtins, os, pathlib, runpy, socket, subprocess, sys
orig_open = builtins.open
def read_only_open(file, mode='r', *args, **kwargs):
    if any(char in mode for char in 'wax+'):
        raise AssertionError('import wrote a file')
    return orig_open(file, mode, *args, **kwargs)
def denied(*args, **kwargs):
    raise AssertionError('import attempted an effect')
builtins.open = read_only_open
pathlib.Path.write_text = denied
pathlib.Path.write_bytes = denied
os.mkdir = denied
subprocess.Popen = denied
socket.socket = denied
runpy.run_path(sys.argv[1])
'''
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            before = tuple(Path(temp).iterdir())
            completed = subprocess.run([sys.executable, "-B", "-c", script, str(path)],
                                       cwd=temp, capture_output=True, text=True, timeout=10,
                                       env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(tuple(Path(temp).iterdir()), before)

    def test_closed_model_bounds_nulls_and_enums(self):
        lib = _debug_lib()
        packet = self._packet()
        self.assertEqual(lib.validate_primitives(packet), [])
        changed = copy.deepcopy(packet)
        changed["symptom"]["expected_evidence_ids"] = ["E-01", "E-01"]
        self.assertIn(("VALUE", "$.symptom.expected_evidence_ids"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["request"]["intent"] = "repair_approved"
        self.assertIn(("VALUE", "$.request.intent"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["request"]["intent"] = None
        self.assertIn(("TYPE", "$.request.intent"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        del changed["request"]["scope"]
        self.assertIn(("REQUIRED_FIELD", "$.request.scope"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["request"]["approval"] = True
        self.assertIn(("UNKNOWN_FIELD", "$.request"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["evidence"] = []
        self.assertIn(("VALUE", "$.evidence"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["request"]["restrictions"] = ["x"] * 13
        self.assertIn(("VALUE", "$.request.restrictions"), lib.validate_primitives(changed))
        changed = copy.deepcopy(packet)
        changed["evidence"][0]["observed_at"] = None
        self.assertEqual(lib.validate_primitives(changed), [])
        self.assertTrue(lib.valid_primitive("recipe_name", "debug-local/1"))
        self.assertFalse(lib.valid_primitive("recipe_name", "https://example.invalid/1"))


class HandoffByteDecoderTest(unittest.TestCase):
    def test_utf8_byte_and_depth_limits_accept_exact_boundaries(self):
        lib = _debug_lib()
        exact = b'"' + ("\u00e9".encode("utf-8") * 32767) + b'"'
        self.assertEqual(len(exact), 65536)
        self.assertEqual(lib.decode_packet(exact), ("\u00e9" * 32767, None))
        self.assertEqual(lib.decode_packet(exact + b" ")[1], "INPUT_LIMIT")
        self.assertEqual(lib.decode_packet(b"[" * 16 + b"0" + b"]" * 16)[1], None)
        self.assertEqual(lib.decode_packet(b"[" * 17 + b"0" + b"]" * 17)[1], "DEPTH_LIMIT")
        self.assertEqual(lib.decode_packet(b'{"brackets":"[[[[[[[[[[[[[[[[["}')[1], None)
        scalar, error = lib.decode_packet(b'0\t\r\n ')
        self.assertIsNone(error)
        self.assertEqual(scalar.lexeme, "0")

    def test_duplicate_keys_nonfinite_numbers_and_lone_surrogates_reject(self):
        lib = _debug_lib()
        for raw, expected in (
            (b'{"a":1,"\\u0061":2}', "DUPLICATE_KEY"),
            (b'{"nested":{"x":1,"x":2}}', "DUPLICATE_KEY"),
            (b'{"n":NaN}', "INVALID_JSON"),
            (b'{"n":Infinity}', "INVALID_JSON"),
            (b'{"n":-Infinity}', "INVALID_JSON"),
            (b'{"n":01}', "INVALID_JSON"),
            (b'{}{}', "INVALID_JSON"),
            (b'"\\ud800"', "INVALID_JSON"),
            (b'"\\udc00"', "INVALID_JSON"),
            (b'"\\ud83dX"', "INVALID_JSON"),
            (b'"\xed\xa0\x80"', "INVALID_UTF8"),
            (b'\xef\xbb\xbf{}', "INVALID_UTF8"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(lib.decode_packet(raw)[1], expected)
        packet, error = lib.decode_packet(b'{"n":1e4000,"m":1e-4000,"emoji":"\\ud83d\\ude00"}')
        self.assertIsNone(error)
        self.assertEqual(packet["n"].lexeme, "1e4000")
        self.assertTrue(lib.valid_primitive("integer", packet["n"]))
        self.assertFalse(lib.valid_primitive("integer", packet["m"]))
        self.assertEqual(packet["emoji"], "\U0001f600")


class HandoffReferenceSemanticsTest(unittest.TestCase):
    def _packet(self, name="valid-code-defect-existing-red"):
        data = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        row = next(row for row in data["examples"] if row["id"] == name)
        return json.loads(base64.b64decode(row["payload_b64"]))

    def _assert_semantic_rejection(self, packet):
        lib = _debug_lib()
        self.assertEqual(lib.validate_primitives(packet), [])
        self.assertTrue(lib.validate_semantics(packet), "semantic mutant was accepted")

    def test_bounded_diagnostics_stop_at_first_suppressed_structural_error(self):
        lib = _debug_lib()
        packet = self._packet()
        packet["checks"] = [{} for _ in range(24)]
        expected = lib.validate_semantics(packet)[:16]
        self.assertEqual(len(expected), 16)
        visited = []
        check = lib._check

        def trace(value, spec, path, errors):
            if path.startswith("$.checks["):
                visited.append(path)
            return check(value, spec, path, errors)

        lib._check = trace
        try:
            bounded = getattr(lib, "validate_semantics_bounded", None)
            if bounded is None:
                # Observe the old public-entry behavior before the new API exists.
                def bounded(value):
                    found = lib.validate_semantics(value)
                    return found[:16], len(found) > 16
            errors, truncated = bounded(packet)
        finally:
            lib._check = check
        self.assertEqual(errors, expected)
        self.assertTrue(truncated)
        self.assertNotIn("$.checks[2]", visited,
                         "validation traversed records after the 17th error")

    def test_bounded_diagnostics_stop_before_later_semantic_checks(self):
        lib = _debug_lib()
        packet = self._packet()
        packet["checks"] = [copy.deepcopy(packet["checks"][0]) for _ in range(24)]
        self.assertEqual(lib.validate_primitives(packet), [])
        expected = lib.validate_semantics(packet)[:16]
        self.assertEqual(expected,
                         [("DUPLICATE_ID", f"$.checks[{index}].id")
                          for index in range(1, 17)])
        reached_late_check = []
        original = lib._not_recorded_success

        def trace(value):
            reached_late_check.append(True)
            return original(value)

        lib._not_recorded_success = trace
        try:
            lib.validate_semantics(packet)
            self.assertTrue(reached_late_check,
                            "control did not reach the later semantic check")
            reached_late_check.clear()
            bounded = getattr(lib, "validate_semantics_bounded", None)
            if bounded is None:
                def bounded(value):
                    found = lib.validate_semantics(value)
                    return found[:16], len(found) > 16
            errors, truncated = bounded(packet)
        finally:
            lib._not_recorded_success = original
        self.assertEqual(errors, expected)
        self.assertTrue(truncated)
        self.assertFalse(reached_late_check,
                         "semantic traversal continued after the 17th error")
    def test_exactly_sixteen_diagnostics_are_not_truncated(self):
        lib = _debug_lib()
        packet = self._packet()
        del packet["protocol"]
        del packet["case_id"]
        packet["request"] = {}
        packet["checks"] = [{}]
        expected = lib.validate_semantics(packet)
        self.assertEqual(len(expected), 16)
        errors, truncated = lib.validate_semantics_bounded(packet)
        self.assertEqual(errors, expected)
        self.assertFalse(truncated)
    def test_duplicate_and_dangling_references_reject(self):
        lib = _debug_lib()
        baseline = self._packet()
        self.assertEqual(lib.validate_primitives(baseline), [])
        self.assertEqual(lib.validate_semantics(baseline), [])
        for namespace in ("snapshots", "evidence", "hypotheses", "checks"):
            with self.subTest(duplicate=namespace):
                changed = copy.deepcopy(baseline)
                changed[namespace].append(copy.deepcopy(changed[namespace][0]))
                self._assert_semantic_rejection(changed)
        dangling = (
            ("snapshot in evidence", lambda p: p["evidence"][1].update(snapshot_id="S-99")),
            ("check in evidence", lambda p: p["evidence"][3].update(check_id="C-99")),
            ("expectation evidence", lambda p: p["symptom"]["expected_evidence_ids"].append("E-99")),
            ("reproduction evidence", lambda p: p["reproduction"]["evidence_ids"].append("E-99")),
            ("hypothesis support", lambda p: p["hypotheses"][0]["supporting_evidence_ids"].append("E-99")),
            ("hypothesis opposition", lambda p: p["hypotheses"][0]["opposing_evidence_ids"].append("E-99")),
            ("check evidence", lambda p: p["checks"][0]["evidence_ids"].append("E-99")),
            ("disposition evidence", lambda p: p["disposition"]["evidence_ids"].append("E-99")),
            ("disposition cause", lambda p: p["disposition"]["cause_ids"].append("H-99")),
            ("regression snapshot", lambda p: p["regression"].update(snapshot_id="S-99")),
            ("regression evidence", lambda p: p["regression"]["evidence_ids"].append("E-99")),
        )
        for label, mutate in dangling:
            with self.subTest(dangling=label):
                changed = copy.deepcopy(baseline)
                mutate(changed)
                self._assert_semantic_rejection(changed)

    def test_planned_checks_cannot_prove_reproduction(self):
        lib = _debug_lib()
        executed = self._packet()
        self.assertEqual(lib.validate_semantics(executed), [])
        no_process_exit = copy.deepcopy(executed)
        no_process_exit["checks"][0]["exit_code"] = None
        self.assertEqual(lib.validate_semantics(no_process_exit), [])
        interrupted = self._packet("valid-unresolved")
        interrupted["checks"].append({
            "id": "C-01", "operation": "Inspect the timed-out job trace",
            "cwd": None, "status": "interrupted", "exit_code": 0,
            "expectation": "A complete trace distinguishes the cause.",
            "observed": "A child emitted partial output before interruption.",
            "evidence_ids": ["E-02"], "authorization_basis": None,
            "side_effects": "Read-only inspection; capture was interrupted.",
        })
        interrupted["evidence"].append({
            "id": "E-02", "kind": "command_result", "snapshot_id": None,
            "locator": "fixture:partial-child-output",
            "observation": "Partial output from the interrupted inspection.",
            "observed_at": None, "check_id": "C-01", "coverage": "partial",
            "limitations": "The parent check was interrupted; child exit zero is not completion.",
        })
        interrupted["disposition"]["evidence_ids"].append("E-02")
        self.assertEqual(lib.validate_primitives(interrupted), [])
        self.assertEqual(lib.validate_semantics(interrupted), [])
        for status in ("planned", "not_run", "interrupted"):
            with self.subTest(reproduction_from=status):
                changed = copy.deepcopy(executed)
                changed["checks"][0]["status"] = status
                if status != "interrupted":
                    changed["checks"][0]["observed"] = None
                    changed["checks"][0]["exit_code"] = None
                self._assert_semantic_rejection(changed)
        for status in ("planned", "not_run"):
            with self.subTest(false_result=status):
                changed = copy.deepcopy(executed)
                changed["checks"][0]["status"] = status
                self._assert_semantic_rejection(changed)
        no_observation = copy.deepcopy(executed)
        no_observation["checks"][0]["observed"] = None
        self._assert_semantic_rejection(no_observation)
        no_recipe = copy.deepcopy(executed)
        no_recipe["reproduction"]["recipe"] = None
        self._assert_semantic_rejection(no_recipe)
        only_report = copy.deepcopy(executed)
        only_report["reproduction"]["evidence_ids"] = ["E-01"]
        self._assert_semantic_rejection(only_report)

    def test_conflicting_evidence_cannot_confirm_a_cause(self):
        lib = _debug_lib()
        for name in ("valid-code-defect-existing-red", "valid-code-defect-causal-trace",
                     "valid-noncode-with-authority-blocker"):
            with self.subTest(valid=name):
                packet = self._packet(name)
                self.assertEqual(lib.validate_primitives(packet), [])
                self.assertEqual(lib.validate_semantics(packet), [])
        baseline = self._packet()
        changes = (
            ("same support and opposition", lambda p: p["hypotheses"][0]["opposing_evidence_ids"].append("E-03")),
            ("supported without support", lambda p: p["hypotheses"][0].update(supporting_evidence_ids=[])),
            ("refuted without opposition", lambda p: p["hypotheses"][0].update(status="refuted", supporting_evidence_ids=[])),
            ("inconclusive confirmed cause", lambda p: p["hypotheses"][0].update(status="inconclusive")),
            ("missing cause support in conclusion", lambda p: p["disposition"].update(evidence_ids=["E-02", "E-04"])),
        )
        for label, mutate in changes:
            with self.subTest(conflict=label):
                changed = copy.deepcopy(baseline)
                mutate(changed)
                self._assert_semantic_rejection(changed)

    def test_five_outcomes_enforce_distinct_cross_field_obligations(self):
        lib = _debug_lib()
        valid = (
            "valid-unresolved", "valid-code-defect-causal-trace",
            "valid-code-defect-existing-red", "valid-noncode-with-authority-blocker",
            "valid-design-question", "valid-no-action",
        )
        for name in valid:
            with self.subTest(positive=name):
                self.assertEqual(lib.validate_semantics(self._packet(name)), [])

        def attach_well_formed_regression(packet):
            source = self._packet("valid-code-defect-existing-red")
            packet["snapshots"].append(copy.deepcopy(source["snapshots"][0]))
            next(item for item in packet["evidence"] if item["id"] == "E-02")["snapshot_id"] = "S-01"
            packet["regression"] = copy.deepcopy(source["regression"])
            packet["regression"]["basis"] = "causal_trace"
            packet["regression"]["reuse_existing"] = False
            packet["regression"]["evidence_ids"] = ["E-02"]

        mutations = (
            ("code missing expectation", "valid-code-defect-existing-red",
             lambda p: p["symptom"].update(expected=None)),
            ("code missing expectation citation", "valid-code-defect-existing-red",
             lambda p: p["symptom"].update(expected_evidence_ids=[])),
            ("code missing supported cause", "valid-code-defect-existing-red",
             lambda p: p["disposition"].update(cause_ids=[])),
            ("code missing regression", "valid-code-defect-existing-red",
             lambda p: p.update(regression=None)),
            ("noncode missing supported cause", "valid-noncode-with-authority-blocker",
             lambda p: p["disposition"].update(cause_ids=[])),
            ("design carries repair regression", "valid-design-question",
             attach_well_formed_regression),
            ("no action has blocker", "valid-no-action",
             lambda p: p["disposition"]["blockers"].append({
                 "kind": "evidence", "missing": "A required check", "owner": None,
                 "resume_condition": "The check is complete."})),
            ("no action has regression", "valid-no-action",
             attach_well_formed_regression),
            ("no action lacks positive evidence", "valid-no-action",
             lambda p: p["disposition"].update(evidence_ids=[])),
            ("unresolved lacks prerequisite", "valid-unresolved",
             lambda p: p["disposition"].update(blockers=[])),
            ("unresolved routed to ADR", "valid-unresolved",
             lambda p: p["next_step"].update(target="adr")),
            ("unresolved routed to fix", "valid-unresolved",
             lambda p: p["next_step"].update(target="fix")),
            ("unresolved lacks resume condition", "valid-unresolved",
             lambda p: p["disposition"]["blockers"][0].update(resume_condition="")),
        )
        for label, name, mutate in mutations:
            with self.subTest(negative=label):
                packet = self._packet(name)
                mutate(packet)
                if label == "unresolved lacks resume condition":
                    self.assertIn(("VALUE", "$.disposition.blockers[0].resume_condition"),
                                  lib.validate_primitives(packet))
                else:
                    self._assert_semantic_rejection(packet)

    def test_actionable_next_steps_and_existing_regression_identity_are_required(self):
        lib = _debug_lib()
        for name in ("valid-code-defect-existing-red",
                     "valid-noncode-with-authority-blocker", "valid-design-question",
                     "valid-unresolved"):
            for field in ("action", "completion_evidence"):
                with self.subTest(outcome=name, missing=field):
                    packet = self._packet(name)
                    packet["next_step"][field] = None
                    self._assert_semantic_rejection(packet)

        for label, mutate in (
            ("owner missing", lambda p: p["next_step"].update(owner=None)),
            ("noncode routed to fix", lambda p: p["next_step"].update(target="fix")),
        ):
            with self.subTest(existing_owner=label):
                packet = self._packet("valid-noncode-with-authority-blocker")
                mutate(packet)
                self._assert_semantic_rejection(packet)
        missing_owner = self._packet("valid-noncode-with-authority-blocker")
        missing_owner["next_step"].update(target="evidence", owner=None)
        missing_owner["disposition"]["blockers"][0].update(
            kind="input", owner=None, missing="No existing operational owner is identified.",
            resume_condition="Identify the owner before an operational change.")
        self.assertEqual(lib.validate_semantics(missing_owner), [])
        missing_owner["disposition"]["blockers"][0]["owner"] = "Fixture runtime operator"
        with self.subTest(noncode_missing_owner_record=True):
            self._assert_semantic_rejection(missing_owner)
        for field, value in (("owner", "Unexpected owner"),
                             ("action", "Unexpected work"),
                             ("completion_evidence", "Unexpected result")):
            with self.subTest(none_field=field):
                packet = self._packet("valid-no-action")
                packet["next_step"][field] = value
                self._assert_semantic_rejection(packet)

        existing_red = self._packet("valid-code-defect-existing-red")
        self.assertEqual(lib.validate_semantics(existing_red), [])
        suggested = self._packet("valid-code-defect-causal-trace")
        self.assertFalse(suggested["regression"]["reuse_existing"])
        self.assertIsNotNone(suggested["regression"]["candidate_test_id"])
        self.assertEqual(lib.validate_semantics(suggested), [])
        for label, mutate in (
            ("missing test identity", lambda p: p["regression"].update(candidate_test_id=None)),
            ("missing cited red", lambda p: p["regression"].update(evidence_ids=["E-02"])),
            ("green check cited as red", lambda p: p["checks"][0].update(exit_code=0)),
        ):
            with self.subTest(reuse=label):
                packet = copy.deepcopy(existing_red)
                mutate(packet)
                self._assert_semantic_rejection(packet)
        suggested["regression"]["reuse_existing"] = True
        self._assert_semantic_rejection(suggested)
        raw = json.dumps(existing_red).encode("utf-8")
        self.assertEqual(raw.count(b'"exit_code": 1'), 1)
        for token in (b"0", b"-0", b"0.0", b"0e10"):
            with self.subTest(decoded_zero=token):
                decoded, error = lib.decode_packet(raw.replace(b'"exit_code": 1',
                                                               b'"exit_code": ' + token))
                self.assertIsNone(error)
                self.assertEqual(lib.validate_primitives(decoded), [])
                self.assertTrue(lib.validate_semantics(decoded),
                                "mathematical zero cannot witness target red")

        foreign = copy.deepcopy(existing_red)
        other = copy.deepcopy(foreign["snapshots"][0])
        other["id"] = "S-02"
        foreign["snapshots"].append(other)
        foreign["regression"]["snapshot_id"] = "S-02"
        with self.subTest(foreign_regression_snapshot=True):
            self._assert_semantic_rejection(foreign)
        expectation_only = copy.deepcopy(foreign)
        next(item for item in expectation_only["evidence"]
             if item["id"] == "E-02")["snapshot_id"] = "S-02"
        with self.subTest(expectation_snapshot_is_not_red_snapshot=True):
            self._assert_semantic_rejection(expectation_only)

    def test_fingerprint_and_recipe_are_paired(self):
        lib = _debug_lib()
        packet = self._packet("valid-code-defect-existing-red")
        self.assertIsNone(packet["snapshots"][0]["fingerprint"])
        self.assertIsNone(packet["snapshots"][0]["fingerprint_recipe"])
        self.assertEqual(lib.validate_semantics(packet), [])
        digest = "sha256:" + "a" * 64
        for fingerprint, recipe in ((digest, None), (None, "debug-local/1")):
            with self.subTest(unpaired=(fingerprint, recipe)):
                changed = copy.deepcopy(packet)
                changed["snapshots"][0]["fingerprint"] = fingerprint
                changed["snapshots"][0]["fingerprint_recipe"] = recipe
                self._assert_semantic_rejection(changed)
        historical = copy.deepcopy(packet)
        historical["snapshots"][0]["fingerprint"] = digest
        historical["snapshots"][0]["fingerprint_recipe"] = "debug-local/1"
        self.assertEqual(lib.validate_semantics(historical), [])
        historical["snapshots"][0]["fingerprint_recipe"] = "https://example.invalid/1"
        self.assertIn(("VALUE", "$.snapshots[0].fingerprint_recipe"),
                      lib.validate_primitives(historical))
        unknown = copy.deepcopy(packet)
        unknown["snapshots"][0].update(commit=None, dirty_state="unknown",
                                        runtime_identity=None, limitations=None)
        self._assert_semantic_rejection(unknown)


# T-012 exercises the real private process from an installed-code fixture.
class PrivateDebugEntryTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="debug T-012 ü ")
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name).resolve()
        self.installed = self.base / "installed helper ü"
        self.installed.mkdir()
        for name in ("debug-handoff.py", "_debughandofflib.py"):
            (self.installed / name).write_bytes((ROOT / "core" / "pysrc" / name).read_bytes())
        self.entry = self.installed / "debug-handoff.py"
        self.cwd = self.base / "foreign project ü"
        self.cwd.mkdir()
        self.cache = self.base / "redirected cache ü"
        self.cache.mkdir()
        data = json.loads((FIXTURES / "handoff-examples.json").read_text(encoding="utf-8"))
        self.valid = base64.b64decode(next(row["payload_b64"] for row in data["examples"]
                                           if row["id"] == "valid-code-defect-existing-red"))

    def _env(self, extra=None):
        env = {**__import__("os").environ,
               "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPYCACHEPREFIX": str(self.cache)}
        env.update(extra or {})
        return env

    def _run(self, raw, *args, env=None):
        return subprocess.run([sys.executable, "-B", str(self.entry), *args],
                              input=raw, cwd=self.cwd, env=self._env(env),
                              capture_output=True, timeout=10)

    def _result(self, completed, expected_exit):
        self.assertEqual(completed.returncode, expected_exit, completed.stderr)
        self.assertEqual(completed.stderr, b"")
        self.assertLessEqual(len(completed.stdout), 8192)
        self.assertTrue(completed.stdout.endswith(b"\n"))
        self.assertEqual(completed.stdout.count(b"\n"), 1)
        value = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(list(value), ["protocol", "valid", "errors", "truncated"])
        self.assertEqual(value["protocol"], "codearbiter.debug-validation/1.0.0")
        self.assertIs(type(value["valid"]), bool)
        self.assertIs(type(value["truncated"]), bool)
        self.assertLessEqual(len(value["errors"]), 16)
        allowed = {"USAGE", "INPUT_IO", "INPUT_LIMIT", "DEPTH_LIMIT",
                   "INVALID_UTF8", "INVALID_JSON", "DUPLICATE_KEY",
                   "UNSUPPORTED_PROTOCOL", "REQUIRED_FIELD", "UNKNOWN_FIELD",
                   "TYPE", "VALUE", "REFERENCE", "SEMANTIC", "INTERNAL"}
        for row in value["errors"]:
            self.assertEqual(list(row), ["code", "path"])
            self.assertIn(row["code"], allowed)
            self.assertLessEqual(len(row["path"]), 256)
            self.assertTrue(row["path"].isascii())
            self.assertRegex(row["path"], r"^\$(?:\.[A-Za-z_]+|\[[0-9]+\])*$")
        self.assertEqual(value["valid"], expected_exit == 0)
        self.assertEqual(bool(value["errors"]), expected_exit != 0)
        return value

    def test_private_entry_enforces_exit_codes_and_bounded_result(self):
        valid = self._result(self._run(self.valid, "validate"), 0)
        self.assertEqual(valid["errors"], [])
        self.assertFalse(valid["truncated"])
        for raw, code in ((b"{}", "REQUIRED_FIELD"),
                          (b"\xff", "INVALID_UTF8"),
                          (b"{}" + b" " * 65535, "INPUT_LIMIT")):
            with self.subTest(code=code):
                result = self._result(self._run(raw, "validate"), 2)
                self.assertEqual(result["errors"][0]["code"], code)
        for args in ((), ("bogus",), ("validate", "--root", "anything")):
            with self.subTest(args=args):
                process = subprocess.Popen([sys.executable, "-B", str(self.entry), *args],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, cwd=self.cwd,
                                           env=self._env())
                try:
                    code = process.wait(timeout=3)  # stdin remains open: argv must win.
                    output, error = process.communicate(timeout=3)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=3)
                self._result(subprocess.CompletedProcess(args, code, output, error), 2)
        hook = self.base / "io fault" / "sitecustomize.py"
        hook.parent.mkdir()
        hook.write_text("import sys\nclass Fault:\n def read(self, size=-1): raise OSError('private canary')\nclass Input:\n buffer=Fault()\nsys.stdin=Input()\n", encoding="utf-8")
        fault = self._result(self._run(self.valid, "validate",
                                       env={"PYTHONPATH": str(hook.parent)}), 3)
        self.assertEqual(fault["errors"], [{"code": "INPUT_IO", "path": "$"}])
        hook.write_text("import sys\nclass Fault:\n def read(self, size=-1): raise ValueError('private canary')\nclass Input:\n buffer=Fault()\nsys.stdin=Input()\n", encoding="utf-8")
        internal = self._result(self._run(self.valid, "validate",
                                          env={"PYTHONPATH": str(hook.parent)}), 3)
        self.assertEqual(internal["errors"], [{"code": "INTERNAL", "path": "$"}])

    def test_private_entry_uses_bounded_collection(self):
        packet = json.loads(self.valid)
        packet["checks"] = [{} for _ in range(24)]
        raw = json.dumps(packet, separators=(",", ":")).encode("utf-8")
        library = self.installed / "_debughandofflib.py"
        with library.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\ndef validate_semantics(_packet):\n"
                         "    raise AssertionError('eager collection used')\n")
        result = self._result(self._run(raw, "validate"), 2)
        self.assertEqual(len(result["errors"]), 16)
        self.assertTrue(result["truncated"])
    def test_validation_has_no_files_process_network_or_authority_effects(self):
        hooks = self.base / "audit hooks ü"
        hooks.mkdir()
        (hooks / "sitecustomize.py").write_text(
            "import os, sys\n"
            "own=os.path.normcase(os.path.realpath(os.path.dirname(sys.argv[0])))\n"
            "stdlib=os.path.normcase(os.path.realpath(sys.prefix))\n"
            "base_stdlib=os.path.normcase(os.path.realpath(sys.base_prefix))\n"
            "instrumentation=os.path.normcase(os.path.realpath(os.path.dirname(__file__)))\n"
            "cache=os.path.normcase(os.path.realpath(os.environ['PYTHONPYCACHEPREFIX']))\n"
            "roots=(own,stdlib,base_stdlib,instrumentation,cache)\n"
            "def permitted(full): return any(full==root or full.startswith(root+os.sep) for root in roots)\n"
            "def audit(event, args):\n"
            " if event in ('subprocess.Popen','socket.__new__','socket.connect','os.mkdir','os.remove','os.rename','os.rmdir','os.chmod','os.chown'): raise RuntimeError('forbidden effect')\n"
            " if event=='open':\n"
            "  path=args[0]\n"
            "  mode=args[1] if len(args)>1 else 'r'\n"
            "  flags=args[2] if len(args)>2 else 0\n"
            "  if mode and any(c in str(mode) for c in 'wax+'): raise RuntimeError('write effect')\n"
            "  if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND): raise RuntimeError('write effect')\n"
            "  if isinstance(path,(str,bytes)):\n"
            "   full=os.path.normcase(os.path.realpath(os.fsdecode(path)))\n"
            "   if not permitted(full): raise RuntimeError('project read')\n"
            " if event in ('os.listdir','os.scandir'):\n"
            "  full=os.path.normcase(os.path.realpath(os.fsdecode(args[0])))\n"
            "  if not permitted(full): raise RuntimeError('project directory read')\n"
            "sys.addaudithook(audit)\n", encoding="utf-8")
        before = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        members_before = {str(p.relative_to(self.base)) for p in self.base.rglob("*")}
        env = {"PYTHONPATH": str(hooks), "PYTHONNOUSERSITE": "1"}
        self._result(self._run(self.valid, "validate", env=env), 0)
        self._result(self._run(b"{}", "validate", env=env), 2)
        after = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertEqual({str(p.relative_to(self.base)) for p in self.base.rglob("*")},
                         members_before)

        no_guard = self._env()
        no_guard.pop("PYTHONDONTWRITEBYTECODE", None)
        no_guard.pop("PYTHONPYCACHEPREFIX", None)
        without_external_guard = subprocess.run(
            [sys.executable, str(self.entry), "validate"], input=self.valid,
            cwd=self.cwd, env=no_guard, capture_output=True, timeout=10)
        self._result(without_external_guard, 0)
        self.assertEqual({str(p.relative_to(self.base)) for p in self.base.rglob("*")},
                         members_before)

    def test_rejected_values_never_enter_diagnostics(self):
        canary = "CANARY_T012_PRIVATE_VALUE_ü"
        packet = json.loads(self.valid)
        packet[canary] = canary
        packet["symptom"]["expected"] = canary
        raw = json.dumps(packet, ensure_ascii=False).encode("utf-8")
        first = self._run(raw, "validate")
        second = self._run(raw, "validate")
        self.assertEqual(first.stdout, second.stdout)
        self.assertNotIn(canary.encode("utf-8"), first.stdout + first.stderr)
        result = self._result(first, 2)
        self.assertIn({"code": "UNKNOWN_FIELD", "path": "$"}, result["errors"])
        def null_leaves(value):
            if type(value) is dict:
                return {key: null_leaves(child) for key, child in value.items()}
            if type(value) is list:
                return [null_leaves(child) for child in value]
            return None
        many = self._result(self._run(json.dumps(null_leaves(packet)).encode(), "validate"), 2)
        self.assertEqual(len(many["errors"]), 16)
        self.assertTrue(many["truncated"])


# T-013 projections: the test-only conformance checker is an independent
# interpretation of D1-PROFILE. Runtime remains stdlib-only and never loads it.
from datetime import date
from decimal import Decimal
import re


_PROFILE_TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,9})?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
    re.ASCII,
)


def _projection_checker():
    from jsonschema import Draft202012Validator, FormatChecker, validators

    def exact_integer(_checker, value):
        return (type(value) is int or
                (isinstance(value, Decimal) and value.is_finite()
                 and value == value.to_integral_value()))

    checker = FormatChecker()

    @checker.checks("date-time")
    def finite_timestamp(value):
        if type(value) is not str:
            return True  # JSON Schema applies format only to strings.
        match = _PROFILE_TIMESTAMP.fullmatch(value)
        if match is None:
            return False
        try:
            date(*(int(part) for part in match.groups()))
        except ValueError:
            return False
        return True

    self_contained = Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", exact_integer)
    validator_type = validators.extend(Draft202012Validator,
                                       type_checker=self_contained)
    return validator_type, checker


def _exact_json_number(token):
    def reject_constant(_value):
        raise ValueError("non-JSON numeric constant")

    return json.loads(token, parse_int=Decimal, parse_float=Decimal,
                      parse_constant=reject_constant)


class HandoffProjectionTest(unittest.TestCase):
    SCHEMA = (ROOT / "core/surface/skills/debug/references/"
              "debug-handoff.schema.json")
    REFERENCE = ROOT / "core/surface/skills/debug/references/handoff.md"

    def _assert_current(self, path, generated):
        self.assertEqual(path.read_bytes(), generated,
                         f"{path.name} is stale relative to the finite model")

    def _examples(self):
        source = json.loads((FIXTURES / "handoff-examples.json").read_text(
            encoding="utf-8"))
        return {row["id"]: json.loads(base64.b64decode(row["payload_b64"]))
                for row in source["examples"]}

    def test_projection_is_deterministic_and_stale_output_rejects(self):
        lib = _debug_lib()
        schema, reference = lib.project_schema(), lib.project_reference()
        self.assertIs(type(schema), bytes)
        self.assertIs(type(reference), bytes)
        self.assertEqual(schema, lib.project_schema())
        self.assertEqual(reference, lib.project_reference())
        self._assert_current(self.SCHEMA, schema)
        self._assert_current(self.REFERENCE, reference)
        with tempfile.TemporaryDirectory() as directory:
            for name, payload in (("schema", schema), ("reference", reference)):
                with self.subTest(stale=name):
                    stale = Path(directory) / name
                    stale.write_bytes(payload + b"stale")
                    with self.assertRaisesRegex(AssertionError, "stale"):
                        self._assert_current(stale, payload)
        original = lib.MODEL["request"]["scope"]
        try:
            lib.MODEL["request"]["scope"] = ("text", 1999)
            with self.subTest(projection="schema derives from MODEL"):
                self.assertNotEqual(lib.project_schema(), schema)
            with self.subTest(projection="reference derives from MODEL"):
                self.assertNotEqual(lib.project_reference(), reference)
        finally:
            lib.MODEL["request"]["scope"] = original
        self.assertIn(b"request.scope", reference)

    def test_schema_shape_and_runtime_semantics_keep_distinct_oracles(self):
        lib = _debug_lib()
        schema = json.loads(lib.project_schema())
        validator_type, checker = _projection_checker()
        validator_type.check_schema(schema)
        validator = validator_type(schema, format_checker=checker)
        examples = self._examples()
        valid = examples["valid-code-defect-existing-red"]
        semantic_only = examples["invalid-duplicate-evidence-id"]
        self.assertEqual(lib.validate_primitives(valid), [])
        self.assertEqual(lib.validate_primitives(semantic_only), [])
        self.assertNotEqual(lib.validate_semantics(semantic_only), [])
        with self.subTest(layer="valid shape"):
            self.assertTrue(validator.is_valid(valid))
        with self.subTest(layer="semantic-only invalid remains schema accepted"):
            self.assertTrue(validator.is_valid(semantic_only))
        unknown = copy.deepcopy(valid)
        unknown["authority"] = "self-asserted"
        with self.subTest(layer="closed shape"):
            self.assertFalse(validator.is_valid(unknown))
        wrong_type = copy.deepcopy(valid)
        wrong_type["checks"][0]["exit_code"] = True
        with self.subTest(layer="boolean is not integer"):
            self.assertFalse(validator.is_valid(wrong_type))
        self.assertEqual(lib.validate_semantics(valid), [])

    def test_projection_agrees_on_exact_number_and_format_profiles(self):
        lib = _debug_lib()
        schema = json.loads(lib.project_schema())
        self.assertIn("$defs", schema)
        definitions = schema["$defs"]
        integer_field = definitions["check"]["properties"]["exit_code"]
        integer_arms = [arm for arm in integer_field["anyOf"]
                        if arm.get("type") == "integer"]
        self.assertEqual(len(integer_arms), 1)
        integer_primitive = integer_arms[0]
        timestamp_field = definitions["evidence"]["properties"]["observed_at"]
        case_id_field = definitions["packet"]["properties"]["case_id"]
        evidence_id_field = definitions["evidence"]["properties"]["id"]
        text_field = definitions["request"]["properties"]["scope"]
        timestamp_strings = [arm for arm in timestamp_field["anyOf"]
                             if arm.get("type") == "string"]
        self.assertEqual(len(timestamp_strings), 1)
        self.assertEqual(timestamp_strings[0]["format"], "date-time")
        self.assertEqual(text_field["maxLength"], 2000)
        validator_type, checker = _projection_checker()
        self.assertIn("date-time", checker.checkers)
        self.assertTrue(validator_type(integer_field,
            format_checker=checker).is_valid(None))
        cases = json.loads((ROOT / "docs/proposals/debug-correctness/D1-CASES.json")
                           .read_text(encoding="utf-8"))
        fields = {"case_id": case_id_field, "evidence_id": evidence_id_field}
        for row in cases["primitive_vectors"]:
            kind, value, expected = row["kind"], row["input"], row["expected"]
            if kind == "integer_lexeme":
                with self.subTest(vector=row["id"]):
                    self.assertEqual(lib.valid_primitive(kind, lib.JsonNumber(value)), expected)
                    try:
                        exact = _exact_json_number(value)
                    except ValueError:
                        self.assertFalse(expected)
                    else:
                        self.assertNotIsInstance(exact, float)
                        self.assertEqual(validator_type(integer_primitive,
                            format_checker=checker).is_valid(exact), expected)
            elif kind == "timestamp":
                with self.subTest(vector=row["id"]):
                    self.assertEqual(checker.conforms(value, "date-time"), expected)
                    self.assertEqual(validator_type(timestamp_field,
                        format_checker=checker).is_valid(value), expected)
                    self.assertEqual(lib.valid_primitive(kind, value), expected)
            elif kind in fields:
                with self.subTest(vector=row["id"]):
                    self.assertEqual(validator_type(fields[kind],
                        format_checker=checker).is_valid(value), expected)
                    self.assertEqual(lib.valid_primitive(kind, value), expected)
            elif kind == "text":
                with self.subTest(vector=row["id"]):
                    capped = {**text_field, "maxLength": value["limit"]}
                    self.assertEqual(validator_type(capped,
                        format_checker=checker).is_valid(value["value"]), expected)
                    self.assertEqual(lib.valid_primitive(kind,
                        (value["value"], value["limit"])), expected)
        self.assertFalse(validator_type(case_id_field,
            format_checker=checker).is_valid("DBG-abc\n"))
        self.assertFalse(validator_type(evidence_id_field,
            format_checker=checker).is_valid("E-01\n"))


if __name__ == '__main__':
    unittest.main()
