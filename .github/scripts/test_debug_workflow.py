"""Finite source checks for the debug owner boundary.

These checks corroborate generated behavior. They do not grant integration
authority or stand in for current GitHub and native workflow observations.
"""

import importlib.util
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "core/surface/skills/debug/SKILL.md"
COMMAND = ROOT / "core/surface/commands/debug.md"
HISTORICAL = ROOT / "docs/proposals/debug-correctness/D1-OWNERSHIP.json"
PROJECTIONS = {
    "claude": ("plugins/ca", "commands/debug.md", "skills/debug/SKILL.md",
               "skills/INDEX.md", "| [debug](debug/SKILL.md) |"),
    "codex": ("plugins/ca-codex", "skills/ca-debug/SKILL.md", "routines/debug/SKILL.md",
              "skills/INDEX.md", "| `$ca-debug` |"),
    "pi": ("plugins/ca-pi", "skills/ca-debug/SKILL.md", "routines/debug/SKILL.md",
           "SKILLS.md", "| `/ca-debug` |"),
}
PHASES = tuple(f"## Phase {number}" for number in range(1, 6))

tool = ROOT / "tools/build-surface.py"
spec = importlib.util.spec_from_file_location("build_surface_for_debug_owner", tool)
build_surface = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_surface)


def body(text):
    """Return a rendered owner's full procedure after its YAML header."""
    return text.split("\n---\n", 1)[1]


def validate_host_trace_record(trace, *, fixture, observed_packet,
                               observed_exit, observed_result):
    """Check a retained D-layer caller/validator/TDD trace for contradictions.

    The caller and TDD observations must be acquired independently by a later
    host exercise. This function neither authenticates them nor runs a model.
    """
    if trace.get("layer") != "D" or trace.get("status") != "RECORD_INPUT_ONLY_HOST_PENDING":
        raise ValueError("record cannot claim host/model qualification")
    if trace.get("caller") != fixture["caller"] or trace.get("entry") != "fix":
        raise ValueError("caller scope differs from retained actual caller input")
    if (trace.get("packet") != observed_packet or
            trace.get("validator_exit") != observed_exit or
            trace.get("validator_result") != observed_result):
        raise ValueError("record differs from actual validator subprocess return")
    if (trace.get("diagnostic_calls") != 1 or
            trace.get("diagnostic_return") != "same_fix_call" or
            trace.get("public_recursion") is not False):
        raise ValueError("diagnosis must return once to original fix call")
    result = trace.get("validator_result")
    if (trace.get("validator_exit") != fixture["validator_return"]["exit_code"] or
            not isinstance(result, dict) or
            result.get("valid") is not fixture["validator_return"]["valid"] or
            result.get("protocol") != "codearbiter.debug-validation/1.0.0" or
            result.get("truncated") is not False):
        raise ValueError("validator return differs from real helper result")
    packet = trace.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("missing validated packet")
    authorized = trace["caller"].get("scope") == "repair_authorized"
    if not authorized or trace["validator_exit"] != 0 or result["valid"] is not True:
        if trace.get("tdd") is not None:
            raise ValueError("packet intent cannot grant repair authority")
        return True
    if result.get("errors") != [] or packet.get("next_step", {}).get("target") != "fix":
        raise ValueError("validated fix disposition missing")
    regression = packet.get("regression")
    if not isinstance(regression, dict) or not regression.get("oracle"):
        raise ValueError("validated bug-origin regression obligation missing")
    tdd = trace.get("tdd")
    if not isinstance(tdd, dict):
        raise ValueError("authorized repair requires target-red record")
    target = tdd.get("target_test_id")
    red = tdd.get("target_red")
    green = tdd.get("target_green")
    if (not isinstance(target, str) or not target or
            not isinstance(red, dict) or not isinstance(green, dict) or
            red.get("test_id") != target or green.get("test_id") != target or
            red.get("kind") != "assertion_failure" or
            not red.get("cause") or green.get("kind") != "pass" or
            green.get("assertions_unchanged") is not True or
            tdd.get("unrelated_failures_retained") is not True):
        raise ValueError("target RED/GREEN correspondence or setup distinction missing")
    return True


class CollectorCompatibleTestCase(unittest.TestCase):
    """Keep verbose unittest results on one line for the installed collector."""

    def shortDescription(self):
        return None


class DebugOwnerBoundaryTest(CollectorCompatibleTestCase):
    def assert_canonical_declaration(self, declaration):
        self.assertEqual(declaration, "{{SKILL_ENTRY:debug}}\n")

    def assert_complete_entry(self, entry):
        for phase in PHASES:
            self.assertIn(phase, entry)
        self.assertIn("taskwrite.py", entry)
        self.assertNotIn("{{SKILL_ENTRY:", entry)

    def assert_debug_index(self, index, prefix):
        rows = [line for line in index.splitlines() if line.startswith(prefix)]
        self.assertEqual(len(rows), 1, f"expected one debug discovery row: {prefix}")
        self.assertIn("Investigate", rows[0])

    def assert_debug_metadata(self, record):
        self.assertEqual(record["visibility"], "advanced")
        self.assertEqual(record["workflow"], "change")

    def owner_section(self, heading, next_heading):
        owner = OWNER.read_text(encoding="utf-8")
        self.assertIn(heading, owner)
        self.assertIn(next_heading, owner)
        return owner.split(heading, 1)[1].split(next_heading, 1)[0].lower()

    def test_unknown_trigger_enters_scoped_investigation_without_invented_repro(self):
        """V01: the actual debug owner permits evidence-led unknown-trigger entry."""
        entry = self.owner_section("## Entry boundaries", "## Pre-flight")
        capture = self.owner_section("## Phase 1", "## Phase 2")
        self.assertRegex(entry, r"(failure|symptom).{0,160}(unknown|not yet known).{0,160}(investigat|enter)")
        self.assertIn("not_yet_reproduced", capture)
        self.assertRegex(capture, r"(unknown|not yet known).{0,160}trigger")
        self.assertRegex(capture, r"(cited|source).{0,160}(failure|evidence|trace)")
        self.assertRegex(capture, r"(do not|never).{0,160}(invent|fabricat).{0,160}(repro|trigger|cause)")
        self.assertRegex(capture, r"(diagnos|investigat).{0,160}(only|scope)")
        self.assertNotIn("if no minimal repro exists, derive one with the user before continuing", capture)

    def test_current_expectation_and_optional_context_map_are_used(self):
        """V02: use current contract and optional map without demanding new setup."""
        preflight = self.owner_section("## Pre-flight", "## Phase 1")
        capture = self.owner_section("## Phase 1", "## Phase 2")
        self.assertRegex(capture, r"(current|existing|available).{0,120}(contract|spec|expectation)")
        self.assertRegex(capture, r"(without|do not).{0,160}(re.ask|ask again)")
        self.assertRegex(capture, r"conflict.{0,160}(expectation|contract|source|decision)")
        self.assertRegex(preflight, r"optional.{0,160}(coarse|context).{0,40}map")
        self.assertRegex(preflight, r"(absent|missing|unavailable).{0,160}map")
        self.assertNotIn("if the user cannot state expected behavior", capture)

    def test_missing_context_blocks_dependent_action_without_onboarding(self):
        """V03: missing resources block only dependent work and never scaffold."""
        preflight = self.owner_section("## Pre-flight", "## Phase 1")
        self.assertRegex(preflight, r"missing.{0,160}(resource|context|capability)")
        self.assertRegex(preflight, r"(block|stop).{0,160}depend")
        self.assertRegex(preflight, r"(safe|available).{0,160}(read|fact|evidence)")
        self.assertRegex(preflight, r"(do not|never).{0,160}(guess|invent).{0,160}(command|log|tool)")
        self.assertRegex(preflight, r"(do not|never).{0,160}(onboard|scaffold|marker|install)")
        self.assertRegex(preflight, r"(do not|never).{0,160}(claim|report).{0,80}(ready|readiness)")
        self.assert_canonical_declaration(COMMAND.read_text(encoding="utf-8"))

    def test_owner_gate_requires_current_integration_or_explicit_bounded_decision(self):
        """Current source and every generated host entry retain one owner.

        The separate review records the real integration decision and ancestry.
        This source test cannot create that decision or validate a live PR.
        """
        self.assert_canonical_declaration(COMMAND.read_text(encoding="utf-8"))
        owner = OWNER.read_text(encoding="utf-8")
        self.assertIn("name: debug", owner.split("\n---\n", 1)[0])
        self.assertNotIn("disable-model-invocation", owner.split("\n---\n", 1)[0])
        for phase in PHASES:
            self.assertIn(phase, owner)

        registry = json.loads((ROOT / "core/surface/command-routes.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["commands"]["debug"]["canonical"], "debug")
        self.assert_debug_metadata(registry["commands"]["debug"])
        self.assertNotIn("new-skill", registry["commands"])
        self.assertFalse((ROOT / "core/surface/commands/new-skill.md").exists())
        self.assertFalse((ROOT / "core/surface/skills/skill-author").exists())
        canonical_index = (ROOT / "core/surface/skills/INDEX.md").read_text(encoding="utf-8")
        self.assert_debug_index(canonical_index, "| [debug](debug/SKILL.md) |")

        for host, (plugin, public, private, index_path, row_prefix) in PROJECTIONS.items():
            with self.subTest(host=host):
                rendered = build_surface.render_all(ROOT, host)
                entry = rendered[public].decode("utf-8")
                resource = rendered[private].decode("utf-8")
                self.assertEqual((ROOT / plugin / public).read_bytes(), rendered[public])
                self.assertEqual((ROOT / plugin / private).read_bytes(), rendered[private])
                self.assertEqual((ROOT / plugin / index_path).read_bytes(), rendered[index_path])
                self.assert_debug_index(rendered[index_path].decode("utf-8"), row_prefix)
                self.assert_complete_entry(entry)
                for phase in PHASES:
                    self.assertIn(phase, resource)
                catalog = json.loads(rendered["generated/command-catalog.json"])
                record = catalog["commands"]["debug"]
                self.assertEqual(record["commandPath" if host == "claude" else "skillPath"], public)
                self.assert_debug_metadata(record)
                self.assertNotIn("new-skill", catalog["commands"])
                self.assertNotIn("commands/new-skill.md", rendered)
                self.assertNotIn("skills/ca-new-skill/SKILL.md", rendered)
                self.assertFalse(any("/skill-author/" in path for path in rendered))
                if host == "claude":
                    self.assertIn("disable-model-invocation: true", entry.split("\n---\n", 1)[0])
                    self.assertNotIn("disable-model-invocation", resource.split("\n---\n", 1)[0])
                    self.assertEqual(body(entry), body(resource))
                else:
                    self.assertIn("name: ca-debug", entry.split("\n---\n", 1)[0])
                    self.assertNotIn("disable-model-invocation", entry.split("\n---\n", 1)[0])
                    self.assertNotIn("skills/debug/SKILL.md", rendered)

    def test_owner_gate_rejects_open_pr_or_historical_bytes_as_authority(self):
        """An unchanged old owner blob cannot excuse a procedural wrapper.

        D1-OWNERSHIP records an open PR at its original observation date. Its
        bytes are kept as history; a current decision needs separate evidence.
        """
        historical = json.loads(HISTORICAL.read_text(encoding="utf-8"))
        self.assertFalse(historical["pr854"]["merged"])
        self.assertEqual(historical["p854"], "pending-accepted-integration-no-extraction-authorized")
        owner_before = OWNER.read_bytes()
        old_wrapper = (
            "---\ndescription: Historical independent debug wrapper.\n"
            "argument-hint: symptom\n---\n\n# debug\nRead the owner later.\n"
        )
        with self.assertRaises(AssertionError):
            self.assert_canonical_declaration(old_wrapper)
        with self.assertRaises(AssertionError):
            self.assert_canonical_declaration("{{SKILL_ENTRY:debug}}\nDuplicate policy.\n")

        original_read = build_surface._read_template

        def historical_wrapper(path, where):
            if where == "core/surface/commands/debug.md":
                return old_wrapper
            return original_read(path, where)

        # Exercise the production renderer with the old independent command
        # and unchanged owner bytes. It can render this legacy arrangement;
        # the full-entry regression must discriminate against it.
        with mock.patch.object(build_surface, "_read_template", side_effect=historical_wrapper):
            rendered = build_surface.render_all(ROOT, "claude")
        with self.assertRaises(AssertionError):
            self.assert_complete_entry(rendered["commands/debug.md"].decode("utf-8"))
        self.assertEqual(OWNER.read_bytes(), owner_before)
        self.assert_canonical_declaration(COMMAND.read_text(encoding="utf-8"))

    def test_owner_resource_link_uses_generated_entry_location(self):
        """A future owner resource link resolves from Codex's public entry."""
        original_read = build_surface._read_template
        owner_with_link = OWNER.read_text(encoding="utf-8") + (
            "\nSee {{PLUGIN_ROOT}}/skills/tdd/SKILL.md.\n"
        )

        def linked_owner(path, where):
            if where == "core/surface/commands/debug.md: owner debug":
                return owner_with_link
            return original_read(path, where)

        with mock.patch.object(build_surface, "_read_template", side_effect=linked_owner):
            rendered = build_surface.render_all(ROOT, "codex")
        entry = rendered["skills/ca-debug/SKILL.md"].decode("utf-8")
        self.assertIn("[routines/tdd/SKILL.md](../../routines/tdd/SKILL.md)", entry)

    def test_missing_debug_discovery_or_metadata_is_detected(self):
        """Source mutations exercise the real renderer and fail the gate."""
        original_read = build_surface._read_template

        def without_debug_row(path, where):
            text = original_read(path, where)
            if where == "core/surface/skills/INDEX.md":
                return "\n".join(
                    line for line in text.splitlines()
                    if not line.startswith("| [debug](debug/SKILL.md) |")
                ) + "\n"
            return text

        with mock.patch.object(build_surface, "_read_template", side_effect=without_debug_row):
            rendered = build_surface.render_all(ROOT, "claude")
        with self.assertRaises(AssertionError):
            self.assert_debug_index(rendered["skills/INDEX.md"].decode("utf-8"),
                                    "| [debug](debug/SKILL.md) |")

        original_registry = build_surface._load_command_registry

        def wrong_debug_visibility(*args, **kwargs):
            registry = original_registry(*args, **kwargs)
            registry["commands"]["debug"]["visibility"] = "core"
            return registry

        with mock.patch.object(build_surface, "_load_command_registry",
                               side_effect=wrong_debug_visibility):
            rendered = build_surface.render_all(ROOT, "codex")
        catalog = json.loads(rendered["generated/command-catalog.json"])
        with self.assertRaises(AssertionError):
            self.assert_debug_metadata(catalog["commands"]["debug"])


class DebugDiscriminatorSourceTest(CollectorCompatibleTestCase):
    """Finite checks of the owning instructions, not model-behavior proof."""

    def section(self, heading, next_heading):
        owner = OWNER.read_text(encoding="utf-8")
        self.assertIn(heading, owner)
        self.assertIn(next_heading, owner)
        return owner.split(heading, 1)[1].split(next_heading, 1)[0].lower()

    def test_hypothesis_breadth_follows_real_discriminators(self):
        """AC-006: narrow and wide cases both have an evidence-led path."""
        owner = OWNER.read_text(encoding="utf-8").lower()
        hypotheses = self.section("## Phase 2", "## Phase 3")
        evidence = self.section("## Phase 3", "## Phase 4")
        self.assertRegex(hypotheses, r"narrow.{0,160}(one|single).{0,160}discriminator")
        self.assertRegex(hypotheses, r"(more|additional).{0,160}(plausible|justified).{0,160}mechanisms")
        self.assertRegex(hypotheses, r"no.{0,80}(fixed|arbitrary).{0,80}(minimum|maximum|cap|count)")
        self.assertNotRegex(owner, r"(at least three|three or more distinct|fewer than three)")
        self.assertRegex(hypotheses, r"recency.{0,160}(priorit|rank)")
        self.assertRegex(hypotheses, r"recency.{0,160}(not|never|cannot).{0,100}(caus|confirm|proof)")
        self.assertRegex(evidence, r"(multiple|more than one).{0,160}(supported|contribut).{0,120}cause")
        self.assertRegex(evidence, r"(do not|never).{0,120}repeat.{0,120}unchanged")

    def test_partial_capture_cannot_refute_an_expected_event(self):
        """AC-007: an absent event needs adequate observation coverage."""
        evidence = self.section("## Phase 3", "## Phase 4")
        self.assertRegex(evidence, r"capture.{0,100}(window|range|limit)")
        self.assertRegex(evidence, r"(sampling|instrumentation).{0,120}(coverage|limit)")
        self.assertRegex(evidence, r"(absen|missing).{0,100}(expected|predicted).{0,80}event")
        self.assertRegex(evidence, r"(partial|incomplete).{0,180}inconclusive")
        self.assertRegex(evidence, r"refut.{0,180}(sufficient|complete|adequate).{0,120}(coverage|instrumentation|range)")

    def test_source_and_runtime_binding_detects_relevant_drift(self):
        """AC-007: retained evidence must bind to the investigated runtime."""
        capture = self.section("## Phase 1", "## Phase 2")
        evidence = self.section("## Phase 3", "## Phase 4")
        self.assertRegex(capture, r"source.{0,80}(revision|commit|identity)")
        self.assertRegex(capture, r"(runtime|build|artifact).{0,100}identity")
        self.assertRegex(evidence, r"(trace|evidence).{0,120}(source|build|runtime).{0,100}identity")
        self.assertRegex(evidence, r"(candidate|current).{0,120}(source|build|runtime).{0,100}identity")
        self.assertRegex(evidence, r"(mismatch|drift).{0,180}(revalidat|applicability|block)")
        self.assertRegex(evidence, r"(unknown|unavailable).{0,160}(identity|limitation)")
        self.assertRegex(evidence, r"(local head|checkout).{0,160}(not|never|cannot).{0,100}(deploy|runtime)")

    def test_diagnostic_actions_require_assessed_effects_and_authority(self):
        """AC-004: a diagnostic command has an explicit bounded action decision."""
        evidence = " ".join(self.section("## Phase 3", "## Phase 4").split())
        for field in ("target", "effects", "resources", "authority"):
            self.assertIn(field, evidence)
        self.assertRegex(evidence, r"(scratch|temporary).{0,120}(owned|cleanup)")
        self.assertRegex(evidence, r"(time|timeout).{0,100}(output|size|byte)")
        self.assertRegex(evidence, r"(unsafe|stateful).{0,120}(replay|script|action)")
        self.assertRegex(evidence, r"(do not|never|refuse).{0,120}(execute|run)")
        self.assertRegex(evidence, r"(safer|read.only).{0,120}(observ|alternative)")

    def test_untrusted_logs_and_secret_canaries_stay_outside_model_actions(self):
        """AC-005: logs are bounded data, never commands or secret output."""
        evidence = " ".join(self.section("## Phase 3", "## Phase 4").split())
        for source in ("logs", "tool output", "recorded commands"):
            self.assertIn(source, evidence)
        self.assertRegex(evidence, r"(untrusted|data).{0,120}(instruction|authority)")
        self.assertRegex(evidence, r"(saniti[sz]|redact).{0,120}(model|shared|output)")
        self.assertRegex(evidence, r"(secret|canar).{0,120}(raw|echo|expos)")
        self.assertRegex(evidence, r"(unbounded|bounded).{0,120}(log|collection)")
        self.assertRegex(evidence, r"(request|block).{0,120}(saniti[sz]|safe).{0,120}(input|excerpt)")

    def test_needed_instrumentation_does_not_confirm_a_cause(self):
        """AC-009: a proposed experiment cannot serve as confirming evidence."""
        evidence = " ".join(self.section("## Phase 3", "## Phase 4").split())
        self.assertRegex(evidence, r"(instrumentation|experiment).{0,160}(inconclusive|unconfirmed)")
        self.assertRegex(evidence, r"(isolated|bounded).{0,120}(experiment|instrumentation)")
        self.assertRegex(evidence, r"(authority|approval).{0,120}(prerequisite|required)")
        self.assertRegex(evidence, r"(do not|never).{0,140}(edit|instrument|spike)")
        self.assertNotIn("hypothesis testable only by changing code becomes a phase 4 finding (exit (a)", evidence)

    def test_diagnostic_action_preflight_and_scratch_are_explicit(self):
        """REQ-005: effects, controls, retries and scratch need a decision."""
        evidence = " ".join(self.section("## Phase 3", "## Phase 4").split())
        self.assertRegex(evidence, r"expected observation.{0,100}stop condition.{0,100}before (execution|running)")
        self.assertRegex(evidence, r"inspect.{0,100}(script|hook).{0,100}(hook|script)")
        for effect in ("fetch", "external tools", "checkout"):
            self.assertRegex(evidence, rf"git.{{0,160}}{effect}.{{0,160}}(not|never).{{0,30}}(read.only|harmless|safe)")
        self.assertRegex(evidence, r"supported.{0,80}(time|timeout).{0,80}output.{0,80}resource")
        self.assertRegex(evidence, r"(inadequate|unavailable).{0,100}controls.{0,100}(blocker|block)")
        self.assertRegex(evidence, r"inspect.{0,100}uncertain action.{0,80}before retry")
        self.assertRegex(evidence, r"report.{0,80}(permitted|allowed) scratch effects")
        self.assertRegex(evidence, r"clean only owned scratch")
        self.assertRegex(evidence, r"never reset.{0,30}(user|working) (tree|worktree)")

    def test_existing_data_requires_access_and_disclosure_authority(self):
        """REQ-005/006: permission to read does not imply permission to disclose."""
        evidence = " ".join(self.section("## Phase 3", "## Phase 4").split())
        self.assertRegex(evidence, r"(existing.data|logs).{0,100}existing access and disclosure authority")
        self.assertRegex(evidence, r"(no|without).{0,100}disclosure authority.{0,100}(block|request)")


class DebugTransportSourceTest(CollectorCompatibleTestCase):
    """Finite source and real-helper checks; no model or host run is inferred.

    The producer and fix consumer are instruction resources. A passing source
    check can corroborate their contract, not prove that a model followed it.
    """

    @classmethod
    def setUpClass(cls):
        fixture_dir = ROOT / ".github/fixtures/debug"
        cls.cases = json.loads((fixture_dir / "cases.json").read_text(encoding="utf-8"))
        cls.handoffs = json.loads(
            (fixture_dir / "handoff-examples.json").read_text(encoding="utf-8")
        )
        cls.qualification = json.loads(
            (fixture_dir / "qualification-cells.json").read_text(encoding="utf-8")
        )
        cls.calls = {case["id"]: case for case in cls.cases["transport_calls"]}
        cls.examples = {example["id"]: example for example in cls.handoffs["examples"]}

    def validate_example(self, name):
        """Send the archived payload bytes through the production private entry."""
        example = self.examples[name]
        raw = base64.b64decode(example["payload_b64"], validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), example["payload_sha256"])
        self.assertEqual(
            self.handoffs["transport_fixture_contract"]["entry"],
            "core/pysrc/debug-handoff.py validate",
        )
        entry = ROOT / "core/pysrc/debug-handoff.py"
        self.assertTrue(entry.is_file(), f"missing actual helper: {entry}")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            [sys.executable, "-B", str(entry), "validate"], input=raw,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=env,
            check=False,
        )
        self.assertEqual(completed.stderr, b"")
        self.assertLessEqual(len(completed.stdout), 8192)
        result = json.loads(completed.stdout)
        self.assertEqual(result["protocol"], "codearbiter.debug-validation/1.0.0")
        self.assertEqual(set(result), {"protocol", "valid", "errors", "truncated"})
        return json.loads(raw), completed.returncode, result

    def test_host_trace_records_real_consumer_call_return_and_tdd_obligations(self):
        """Validate D-layer inputs, without claiming a Claude/Codex model journey."""
        call = self.calls["V23/direct_fix_diagnostic_prerequisite"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        trace = {
            "layer": "D", "status": "RECORD_INPUT_ONLY_HOST_PENDING",
            "caller": dict(call["caller"]),
            "entry": "fix", "diagnostic_calls": 1,
            "diagnostic_return": "same_fix_call", "public_recursion": False,
            "validator_exit": exit_code, "validator_result": result,
            "packet": packet,
            "tdd": {"target_test_id": "tests/test_boundary.py::test_limit",
                    "target_red": {"test_id": "tests/test_boundary.py::test_limit",
                                   "kind": "assertion_failure", "cause": "boundary defect"},
                    "target_green": {"test_id": "tests/test_boundary.py::test_limit",
                                     "kind": "pass", "assertions_unchanged": True},
                    "unrelated_failures_retained": True},
        }
        self.assertTrue(validate_host_trace_record(
            trace, fixture=call, observed_packet=packet,
            observed_exit=exit_code, observed_result=result))
        for bad_tdd in (
            {**trace["tdd"], "target_red": {**trace["tdd"]["target_red"],
                                               "kind": "setup_failure"}},
            {**trace["tdd"], "target_green": {**trace["tdd"]["target_green"],
                                                 "test_id": "other::test"}},
            {**trace["tdd"], "unrelated_failures_retained": False},
        ):
            with self.subTest(bad_tdd=bad_tdd), self.assertRaises(ValueError):
                validate_host_trace_record(
                    {**trace, "tdd": bad_tdd}, fixture=call,
                    observed_packet=packet, observed_exit=exit_code,
                    observed_result=result)

    def test_host_trace_cannot_claim_authority_from_packet_intent(self):
        call = self.calls["V22/invalid_handoff_diagnosis_only"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        trace = {
            "layer": "D", "status": "RECORD_INPUT_ONLY_HOST_PENDING",
            "caller": dict(call["caller"]), "entry": "fix",
            "diagnostic_calls": 1, "diagnostic_return": "same_fix_call",
            "public_recursion": False, "validator_exit": exit_code,
            "validator_result": result, "packet": packet,
            "tdd": None,
        }
        for changed in (
            {**trace, "caller": {**trace["caller"], "scope": "repair_authorized"}},
            {**trace, "validator_exit": 0},
            {**trace, "status": "HOST_PASSED"},
            {**trace, "tdd": {"target_test_id": "tests/test_boundary.py::test_limit"}},
            {**trace, "public_recursion": True},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_host_trace_record(
                    changed, fixture=call, observed_packet=packet,
                    observed_exit=exit_code, observed_result=result)

    def assert_source_pattern(self, source, pattern, requirement):
        self.assertTrue(
            re.search(pattern, source, re.DOTALL) is not None,
            f"missing {requirement}: {pattern}",
        )

    def outcome_sections(self):
        owner = OWNER.read_text(encoding="utf-8")
        decision = owner.split("## Phase 4", 1)[1].split("## Phase 5", 1)[0]
        handoff = owner.split("## Phase 5", 1)[1].split("## Hard rules", 1)[0]
        hard_rules = owner.split("## Hard rules", 1)[1]
        return (owner.lower(), *(" ".join(section.lower().split())
                                 for section in (decision, handoff, hard_rules)))

    def test_each_outcome_preserves_its_evidence_and_continuation_boundary(self):
        """AC-010/012/013: the five real packet forms have distinct owner routes.

        These source and fixture checks cannot prove that a model diagnoses a
        case correctly or that a recommended operation was authorized or run.
        """
        owner, decision, handoff, hard_rules = self.outcome_sections()
        examples = (
            ("valid-code-defect-causal-trace", "confirmed_code_defect", "fix"),
            ("valid-noncode-with-authority-blocker", "confirmed_noncode_cause", "existing_owner"),
            ("valid-design-question", "design_question", "evidence"),
            ("valid-no-action", "no_action", "none"),
            ("valid-unresolved", "unresolved", "evidence"),
        )
        for name, outcome, target in examples:
            with self.subTest(outcome=outcome):
                packet, exit_code, result = self.validate_example(name)
                self.assertEqual((exit_code, result["valid"], result["errors"]),
                                 (0, True, []))
                self.assertEqual(packet["disposition"]["kind"], outcome)
                self.assertEqual(packet["next_step"]["target"], target)
                self.assertIn(f"`{outcome}`", decision)
                self.assertIn(f"`{outcome}`", handoff)
                self.assertTrue(packet["disposition"]["evidence_ids"])
        code, _, _ = self.validate_example("valid-code-defect-causal-trace")
        noncode, _, _ = self.validate_example("valid-noncode-with-authority-blocker")
        self.assertEqual(code["reproduction"]["status"], "not_yet_reproduced")
        self.assertEqual(code["regression"]["basis"], "causal_trace")
        self.assertEqual(noncode["disposition"]["blockers"][0]["kind"], "authority")
        self.assertRegex(decision, r"(multiple|more than one).{0,180}(supported|contributing).{0,100}(cause|mechanism)")
        self.assertRegex(decision, r"(supported|confirmed).{0,180}(cause|diagnosis).{0,180}(authority|permission).{0,120}(blocker|prerequisite)")
        self.assertRegex(decision, r"(source|causal).{0,180}(evidence|trace).{0,180}(without|before).{0,100}(replay|runtime)")
        self.assertRegex(handoff, r"(diagnosis.only|caller).{0,180}(scope|authority)")
        self.assertRegex(handoff, r"(propos|recommend|handoff).{0,180}(not|never|cannot).{0,120}(authoriz|execut)")
        self.assertIn("confirmed_noncode_cause", hard_rules)
        self.assertIn("design_question", hard_rules)
        self.assertIn("unresolved", hard_rules)
        self.assertNotIn("debug.note", owner)

    def test_failed_replay_cannot_become_no_action(self):
        """AC-011: a failed replay is bounded evidence, not closure proof."""
        owner, decision, handoff, _ = self.outcome_sections()
        no_action, exit_code, result = self.validate_example("valid-no-action")
        self.assertEqual((exit_code, result["valid"]), (0, True))
        cited = set(no_action["disposition"]["evidence_ids"])
        support = [e for e in no_action["evidence"] if e["id"] in cited]
        self.assertEqual({e["kind"] for e in support}, {"contract", "observation"})
        self.assertEqual(no_action["next_step"]["target"], "none")
        self.assertRegex(decision, r"(failed replay|non.reproduction).{0,220}(not|never|cannot).{0,160}no.action")
        self.assertRegex(decision, r"no_action.{0,300}(positive|affirmative).{0,160}evidence")
        self.assertRegex(handoff, r"no_action.{0,260}(no|without|never).{0,160}(board|task|state).{0,100}(write|mutation|change)")
        self.assertNotIn("no-action close uses the board helper", owner)

    def test_unavailable_discriminator_returns_actionable_unresolved(self):
        """AC-008/012: stop a blocked inquiry with a resumable action."""
        _, decision, handoff, hard_rules = self.outcome_sections()
        packet, exit_code, result = self.validate_example("valid-unresolved")
        self.assertEqual((exit_code, result["valid"]), (0, True))
        self.assertEqual(packet["disposition"]["kind"], "unresolved")
        self.assertEqual(packet["next_step"]["target"], "evidence")
        blocker = packet["disposition"]["blockers"][0]
        self.assertEqual(blocker["kind"], "access")
        for field in ("missing", "owner", "resume_condition"):
            self.assertTrue(blocker[field])
        for field in ("action", "completion_evidence"):
            self.assertTrue(packet["next_step"][field])
        self.assertRegex(decision, r"(unavailable|inaccessible).{0,240}(discriminator|evidence).{0,220}unresolved")
        for field in ("known facts", "discriminator", "owner", "resume condition"):
            self.assertIn(field, decision + handoff)
        self.assertRegex(decision, r"unresolved.{0,300}(no|without|never).{0,160}(forced|automatic).{0,80}adr")
        self.assertRegex(hard_rules, r"(do not|never|must not).{0,160}(force|convert).{0,120}(adr|design)")

    def fix_transport_section(self):
        """Read the canonical fix owner's one debug handoff section."""
        source = (ROOT / "core/surface/commands/fix.md").read_text(encoding="utf-8")
        headings = list(re.finditer(r"(?m)^## [^\n]*(debug|diagnos|handoff)[^\n]*$",
                                    source, re.IGNORECASE))
        self.assertEqual(len(headings), 1, "fix.md needs one debug handoff section")
        start = headings[0].start()
        next_heading = re.search(r"(?m)^## ", source[headings[0].end():])
        end = headings[0].end() + next_heading.start() if next_heading else len(source)
        return source[start:end].lower()

    def test_real_consumer_receives_actual_validated_handoff_fields(self):
        """V21: check validated bytes and both canonical instruction owners.

        This is intentionally red until T19 wires the producer and T20 wires
        the real fix consumer; it does not execute a model as the consumer.
        """
        call = self.calls["V21/validated_handoff_to_fix"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        self.assertEqual(exit_code, call["validator_return"]["exit_code"])
        self.assertIs(result["valid"], call["validator_return"]["valid"])
        self.assertEqual((exit_code, result["valid"]), (0, True))
        self.assertEqual(result["errors"], [])
        self.assertEqual(call["caller"]["scope"], "repair_authorized")
        for path in call["expected_fields"]:
            value = packet
            for component in path.split("."):
                value = value[component]
            self.assertTrue(value, f"empty handoff field: {path}")

        producer = OWNER.read_text(encoding="utf-8").lower()
        with self.subTest(owner="producer"):
            self.assert_source_pattern(producer, r"debug-handoff\.py", "real validator invocation")
            self.assert_source_pattern(producer, r"validat(e|ion).{0,240}(packet|handoff)",
                                       "validated producer handoff")
        with self.subTest(owner="fix consumer"):
            consumer = self.fix_transport_section()
            self.assert_source_pattern(consumer, r"debug-handoff\.py", "real validator invocation")
            for field in ("symptom", "expected", "evidence", "regression", "oracle"):
                self.assert_source_pattern(consumer, rf"\b{field}\b", f"consume {field}")
            self.assert_source_pattern(
                consumer, r"(current|fresh).{0,240}(evidence|worktree|snapshot)",
                "fresh evidence recheck",
            )
            self.assert_source_pattern(
                consumer, r"caller.{0,240}authorit", "caller authority recheck",
            )

    def test_direct_fix_diagnostic_prerequisite_returns_once(self):
        """V23: check the direct-fix source contract; live call count stays pending."""
        call = self.calls["V23/direct_fix_diagnostic_prerequisite"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        self.assertEqual(
            (exit_code, result["valid"]),
            (call["validator_return"]["exit_code"], call["validator_return"]["valid"]),
        )
        self.assertEqual((exit_code, result["valid"]), (0, True))
        self.assertEqual(packet["next_step"]["target"], "fix")
        self.assertEqual(call["prior_internal_diagnostic_calls"], 0)
        self.assertEqual(call["maximum_internal_diagnostic_calls"], 1)
        self.assertEqual(call["caller"]["scope"], "repair_authorized")
        consumer = self.fix_transport_section()
        with self.subTest(requirement="internal bounded prerequisite"):
            self.assert_source_pattern(consumer, r"(one|once|single|bounded).{0,240}diagnos",
                                       "one diagnostic prerequisite")
            self.assert_source_pattern(consumer, r"internal.{0,240}(diagnos|investigat)",
                                       "internal diagnostic route")
        with self.subTest(requirement="same caller return"):
            self.assert_source_pattern(
                consumer, r"return.{0,240}(same|original|existing).{0,240}fix",
                "return to original fix",
            )
            self.assert_source_pattern(
                consumer, r"(no|without|never).{0,240}public.{0,240}(recurs|re.typ|re-invok|route)",
                "no public command recursion",
            )
            self.assert_source_pattern(consumer, r"(no|without|never).{0,240}feature artifact",
                                       "no fabricated feature artifact")

    def test_malformed_handoff_cannot_fall_back_to_unvalidated_repair(self):
        """V22: a rejected packet plus diagnosis-only caller blocks repair."""
        call = self.calls["V22/invalid_handoff_diagnosis_only"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        self.assertEqual(exit_code, call["validator_return"]["exit_code"])
        self.assertIs(result["valid"], call["validator_return"]["valid"])
        self.assertEqual((exit_code, result["valid"]), (2, False))
        self.assertEqual(result["errors"], [{"code": "UNKNOWN_FIELD", "path": "$"}])
        self.assertFalse(result["truncated"])
        control, control_exit, control_result = self.validate_example(
            "valid-code-defect-causal-trace"
        )
        self.assertEqual((control_exit, control_result["valid"]), (0, True))
        self.assertIs(packet.pop("approval"), True)
        self.assertEqual(packet, control)
        self.assertEqual(packet["request"]["intent"], call["claimed_packet_intent"])
        self.assertEqual(call["caller"]["scope"], "diagnosis_only")
        consumer = self.fix_transport_section()
        with self.subTest(requirement="rejected packet stops"):
            self.assert_source_pattern(
                consumer, r"(invalid|reject|fail).{0,240}(handoff|packet).{0,240}(stop|block)",
                "invalid packet stops",
            )
            self.assert_source_pattern(
                consumer, r"(no|never|without).{0,240}unvalidated.{0,240}repair",
                "no unvalidated repair",
            )
        with self.subTest(requirement="packet label cannot grant repair"):
            self.assert_source_pattern(consumer,
                                       r"(actual|original).{0,240}caller.{0,240}(authorit|scope)",
                                       "actual caller authority")
            self.assert_source_pattern(
                consumer, r"(intent|repair_requested).{0,240}(not|never|cannot).{0,240}authori",
                "packet intent cannot grant authority",
            )

    def test_real_fix_rechecks_caller_authority_and_current_evidence(self):
        """T020/V21: validated content informs fix only in the current caller context."""
        call = self.calls["V21/validated_handoff_to_fix"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        self.assertEqual((exit_code, result["valid"], result["errors"]),
                         (0, True, []))
        self.assertEqual(call["caller"]["scope"], "repair_authorized")
        self.assertEqual(packet["reproduction"]["status"], "not_yet_reproduced")
        self.assertEqual(packet["regression"]["basis"], "causal_trace")
        self.assertEqual(packet["next_step"]["target"], "fix")
        consumer = " ".join(self.fix_transport_section().lower().split())
        for field in ("symptom", "expectation", "reproduction", "evidence",
                      "regression", "oracle"):
            self.assertIn(field, consumer)
        self.assert_source_pattern(consumer, r"actual caller.{0,160}(authority|scope)",
                                   "real caller authority")
        self.assert_source_pattern(consumer, r"worktree.{0,240}(source|runtime)",
                                   "current worktree and source binding")
        self.assert_source_pattern(consumer, r"dirty.{0,180}(fingerprint|index|source)",
                                   "same-commit dirty/index/source freshness")
        self.assert_source_pattern(consumer, r"(drift|mismatch|changed).{0,180}(revalidat|block)",
                                   "changed evidence blocks stale transfer")
        self.assert_source_pattern(consumer, r"(do not|never).{0,140}(re.ask|repeat).{0,160}(known|answered)",
                                   "no duplicate answered questions")

    def test_bug_origin_carries_regression_obligation_without_feature_artifacts(self):
        """T021/V23/V33: the real fix handoff reaches the author TDD ledger.

        This checks the instruction seam and a validated example, not a live
        author receipt or permission to repair.
        """
        packet, exit_code, result = self.validate_example("valid-code-defect-causal-trace")
        self.assertEqual((exit_code, result["valid"], result["errors"]), (0, True, []))
        self.assertEqual(packet["disposition"]["kind"], "confirmed_code_defect")
        self.assertEqual(packet["next_step"]["target"], "fix")
        self.assertEqual(packet["regression"]["basis"], "causal_trace")
        self.assertTrue(packet["symptom"]["expected_evidence_ids"])
        self.assertTrue(packet["regression"]["oracle"])
        self.assertTrue(packet["regression"]["evidence_ids"])

        consumer = " ".join(self.fix_transport_section().lower().split())
        self.assertIn("existing ledger", consumer)
        self.assertIn("original caller", consumer)
        self.assertIn("no feature artifact", consumer)

        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        preflight = tdd.split("## Pre-flight", 1)[1].split("## Phase 1", 1)[0].lower()
        scan = tdd.split("## Phase 1", 1)[1].split("## Phase 2", 1)[0].lower()
        author = (ROOT / "core/surface/includes/author-tdd-workflow.md").read_text(
            encoding="utf-8").lower()
        for source in (preflight, scan, author):
            self.assertIn("bug-origin", source)
            self.assertIn("regression", source)
            self.assertIn("expectation", source)
        self.assertIn("source binding", preflight)
        self.assertIn("caller authority", preflight)
        self.assertIn("evidence", scan)
        self.assertIn("oracle", scan)
        self.assertIn("existing ledger", scan)
        self.assertIn("feature artifact", scan)
        self.assertIn("red for the right reason", author)
        self.assertIn("before", author)
        for name in ("backend-author", "frontend-author", "infra-author"):
            charter = (ROOT / f"core/surface/agents/{name}.md").read_text(
                encoding="utf-8").lower()
            with self.subTest(author=name):
                self.assertIn("includes/author-tdd-workflow.md", charter)
                self.assertIn("tdd", charter)
        infra = (ROOT / "core/surface/agents/infra-author.md").read_text(
            encoding="utf-8").lower()
        self.assertIn("bug-origin", infra)
        self.assertIn("regression", infra)

    def test_feature_refactor_and_adr_authority_remain_intact(self):
        """T021: bug-origin entry must not authorize new behavior or decisions."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        preflight = tdd.split("## Pre-flight", 1)[1].split("## Phase 1", 1)[0].lower()
        scan = tdd.split("## Phase 1", 1)[1].split("## Phase 2", 1)[0].lower()
        author = (ROOT / "core/surface/includes/author-tdd-workflow.md").read_text(
            encoding="utf-8").lower()
        self.assertIn("approved spec", preflight)
        self.assertIn("approved spec", scan)
        self.assertIn("acceptance criterion", scan)
        self.assertIn("refactor", preflight)
        self.assertIn("surface table", preflight)
        self.assertIn("parity", preflight)
        self.assertIn("adr", scan)
        self.assertIn("user", scan)
        self.assertIn("feature", author)
        self.assertIn("refactor", author)
        self.assertIn("adr", author)

    def test_adequate_existing_target_red_is_named_and_reused(self):
        """T022/V24/V38: an adequate existing target failure keeps its identity."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        red = " ".join(tdd.split("## Phase 2", 1)[1].split("## Phase 3", 1)[0].lower().split())
        author = " ".join((ROOT / "core/surface/includes/author-tdd-workflow.md")
                          .read_text(encoding="utf-8").lower().split())
        for source in (red, author):
            self.assertRegex(source, r"existing.{0,100}(test|regression).{0,120}target.{0,50}red")
            self.assertRegex(source, r"(name|identify).{0,100}(test|regression).{0,100}(id|identity|name)")
            self.assertRegex(source, r"(oracle|assertion).{0,160}(adequate|matches|target)")
            self.assertRegex(source, r"reuse.{0,160}(existing|named|test|regression)")
            self.assertRegex(source, r"(no|do not|never).{0,100}duplicate.{0,160}(age|predat)")
            self.assertRegex(source, r"(add|write).{0,80}(tests?|regressions?).{0,100}(only|for).{0,100}(uncovered|missing)")

    def test_unrelated_and_setup_failures_cannot_count_as_target_red(self):
        """T022/V25: baseline and setup failures remain visible and block gates."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        red = " ".join(tdd.split("## Phase 2", 1)[1].split("## Phase 3", 1)[0].lower().split())
        author = " ".join((ROOT / "core/surface/includes/author-tdd-workflow.md")
                          .read_text(encoding="utf-8").lower().split())
        for source in (red, author):
            self.assertRegex(source, r"(record|report|preserve).{0,100}(unrelated|pre.existing).{0,100}(failure|red)")
            self.assertRegex(source, r"(unrelated|pre.existing).{0,120}(failure|red).{0,160}(not|never|cannot).{0,70}target red")
            self.assertRegex(source, r"(import|setup).{0,100}(error|failure).{0,160}(not|never|cannot).{0,70}target red")
            self.assertRegex(source, r"(required|commit).{0,100}(gate|check).{0,120}(block|fail|remain red)")
            self.assertRegex(source, r"(do not|never).{0,100}(skip|suppress|waive).{0,100}(test|failure|gate)")

    def test_repair_requires_target_red_then_fresh_green_with_unchanged_assertions(self):
        """T023/V26: the same target goes red before repair and green on repaired source."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        red = " ".join(tdd.split("## Phase 2", 1)[1].split("## Phase 3", 1)[0].lower().split())
        green = " ".join(tdd.split("## Phase 3", 1)[1].split("## Phase 4", 1)[0].lower().split())
        author = " ".join((ROOT / "core/surface/includes/author-tdd-workflow.md")
                          .read_text(encoding="utf-8").lower().split())
        self.assertRegex(red, r"(target|regression).{0,140}red.{0,160}(before|prior).{0,80}(repair|implementation)")
        for source in (green, author):
            self.assertRegex(source, r"(same|named).{0,80}(target|regression|test).{0,140}(fresh|rerun|re.run).{0,80}green")
            self.assertRegex(source, r"assertions?.{0,100}unchanged.{0,140}(red|green)")
            self.assertRegex(source, r"(fresh|rerun|re.run).{0,120}(affected|impact.bounded).{0,100}(test|contract)")

    def test_material_fixture_changes_require_renewed_red(self):
        """T023/V27: material fixture or setup changes invalidate earlier target red."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        red_green = " ".join(tdd.split("## Phase 2", 1)[1].split("## Phase 4", 1)[0].lower().split())
        author = " ".join((ROOT / "core/surface/includes/author-tdd-workflow.md")
                          .read_text(encoding="utf-8").lower().split())
        for source in (red_green, author):
            self.assertRegex(source, r"material.{0,100}(fixture|setup).{0,160}(change|alter)")
            self.assertRegex(source, r"(renew|repeat|re.observe|rerun|re.run).{0,100}(target.)?red.{0,140}(broken|before|prior)")
            self.assertRegex(source, r"(earlier|previous|prior).{0,100}red.{0,100}(invalid|no longer|cannot|not)")

    def test_intermittent_oracles_retain_stochastic_limits(self):
        """T023/V27: timing evidence has a finite oracle and an honest limit."""
        tdd = (ROOT / "core/surface/skills/tdd/SKILL.md").read_text(encoding="utf-8")
        red = " ".join(tdd.split("## Phase 2", 1)[1].split("## Phase 3", 1)[0].lower().split())
        author = " ".join((ROOT / "core/surface/includes/author-tdd-workflow.md")
                          .read_text(encoding="utf-8").lower().split())
        for source in (red, author):
            self.assertRegex(source, r"(intermittent|timing).{0,200}(deterministic|finite)")
            self.assertRegex(source, r"(finite|bounded).{0,100}(trial|repeat)")
            self.assertRegex(source, r"stochastic.{0,120}(limit|sample|claim)")
            self.assertRegex(source, r"(no|never|do not).{0,100}(deterministic|unbounded|retry)")

    def test_internal_debug_prerequisite_returns_without_public_recursion(self):
        """T020/V23: direct fix takes at most one diagnostic return."""
        call = self.calls["V23/direct_fix_diagnostic_prerequisite"]
        self.assertEqual(call["prior_internal_diagnostic_calls"], 0)
        self.assertEqual(call["maximum_internal_diagnostic_calls"], 1)
        self.assertEqual(call["caller"]["scope"], "repair_authorized")
        consumer = " ".join(self.fix_transport_section().lower().split())
        self.assert_source_pattern(consumer, r"(one|once|single).{0,140}internal diagnos",
                                   "one internal diagnostic prerequisite")
        self.assert_source_pattern(consumer, r"return.{0,140}(original|same).{0,100}fix",
                                   "return to the original fix")
        self.assert_source_pattern(consumer, r"(no|without|never).{0,160}public.{0,160}(recurs|re.typ|re-invok|route)",
                                   "no public route recursion")
        self.assert_source_pattern(consumer, r"(no|without|never).{0,120}feature artifact",
                                   "no fake feature artifact")

    def test_diagnosis_only_intent_never_authorizes_repair(self):
        """T020/V22/V31: neither packet intent nor malformed input grants repair."""
        call = self.calls["V22/invalid_handoff_diagnosis_only"]
        packet, exit_code, result = self.validate_example(call["handoff_example"])
        self.assertEqual((exit_code, result["valid"]), (2, False))
        self.assertEqual(result["errors"], [{"code": "UNKNOWN_FIELD", "path": "$"}])
        self.assertEqual(call["caller"]["scope"], "diagnosis_only")
        self.assertEqual(packet["request"]["intent"], "repair_requested")
        consumer = " ".join(self.fix_transport_section().lower().split())
        self.assert_source_pattern(consumer, r"(invalid|rejected).{0,160}(packet|handoff).{0,160}(stop|block)",
                                   "rejected packet stops")
        self.assert_source_pattern(consumer, r"diagnosis.only.{0,160}(stop|no repair)",
                                   "diagnosis-only stops before repair")
        self.assert_source_pattern(consumer, r"(intent|repair_requested).{0,160}(cannot|never|not).{0,160}authori",
                                   "intent field cannot authorize repair")

    def test_valid_nonrepair_dispositions_stop_at_fix_consumer(self):
        """T020/V31: valid packets need a disposition gate after validation."""
        for name, kind, target in (
            ("valid-design-question", "design_question", "evidence"),
            ("valid-no-action", "no_action", "none"),
        ):
            with self.subTest(packet=name):
                packet, exit_code, result = self.validate_example(name)
                self.assertEqual((exit_code, result["valid"], result["errors"]),
                                 (0, True, []))
                self.assertEqual(packet["disposition"]["kind"], kind)
                self.assertEqual(packet["next_step"]["target"], target)
                self.assertIsNone(packet["regression"])

        consumer = " ".join(self.fix_transport_section().lower().split())
        self.assert_source_pattern(
            consumer, r"only.{0,120}`confirmed_code_defect`.{0,160}`next_step.target`.{0,100}`fix`",
            "code-defect and fix target are both required to resume repair",
        )
        self.assert_source_pattern(
            consumer, r"supported.{0,120}regression.{0,180}(original|actual).{0,120}caller",
            "supported regression retains original caller authority",
        )
        for kind in ("design_question", "no_action"):
            self.assert_source_pattern(
                consumer, rf"`{kind}`.{{0,180}}(report|return).{{0,180}}stop",
                f"{kind} returns without repair",
            )

    def test_validated_transfer_preserves_evidence_without_duplicate_questions(self):
        """T019/V19/V21: the producer carries real validated fields onward.

        Source checks cannot prove that the future fix consumer or model obeys
        these instructions; the actual private validator checks the packet.
        """
        packet, exit_code, result = self.validate_example("valid-code-defect-causal-trace")
        self.assertEqual((exit_code, result["valid"], result["errors"]),
                         (0, True, []))
        self.assertTrue(packet["symptom"]["observed"])
        self.assertTrue(packet["symptom"]["expected"])
        self.assertTrue(packet["symptom"]["expected_evidence_ids"])
        self.assertEqual(packet["reproduction"]["status"], "not_yet_reproduced")
        self.assertTrue(packet["reproduction"]["limitations"])
        self.assertTrue(packet["disposition"]["evidence_ids"])
        self.assertTrue(packet["regression"]["oracle"])
        self.assertTrue(packet["regression"]["evidence_ids"])
        self.assertTrue(packet["regression"]["snapshot_id"])

        handoff = self.outcome_sections()[2]
        self.assertIn("debug-handoff.py", handoff)
        self.assertRegex(handoff, r"(absolute|installed).{0,140}helper.{0,180}validat")
        self.assertRegex(handoff, r"(stdin|packet bytes).{0,180}(validat|helper)")
        self.assertRegex(handoff, r"(valid|exit 0).{0,180}(handoff|transfer)")
        for field in ("symptom", "expectation", "reproduction", "evidence",
                      "regression", "oracle", "source binding"):
            self.assertIn(field, handoff)
        self.assertRegex(handoff, r"(do not|never).{0,140}(re.ask|repeat).{0,140}(known|answered)")
        self.assertRegex(handoff, r"(invalid|reject).{0,180}(stop|block).{0,180}(transfer|handoff)")
        self.assertRegex(handoff, r"(diagnosis.only|caller scope).{0,180}(stop|authority)")

    def test_capacity_and_lost_context_are_reported_without_silent_evidence_loss(self):
        """T019/V20/V30: bounded transport exposes capacity and resume gaps."""
        entry = ROOT / "core/pysrc/debug-handoff.py"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            [sys.executable, "-B", str(entry), "validate"],
            input=b"x" * 65537, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, env=env, check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, b"")
        self.assertEqual(json.loads(completed.stdout)["errors"],
                         [{"code": "INPUT_LIMIT", "path": "$"}])
        handoff = self.outcome_sections()[2]
        self.assertRegex(handoff, r"(65,536|65536).{0,180}(byte|capacity|limit)")
        self.assertRegex(handoff, r"(400).{0,100}word.{0,180}summary")
        self.assertRegex(handoff, r"(compact|capacity).{0,220}(cited|citation|locator)")
        self.assertRegex(handoff, r"(never|do not).{0,160}(silently drop|hide).{0,120}evidence")
        self.assertRegex(handoff, r"(lost|missing) context.{0,220}(admit|state|report)")
        self.assertRegex(handoff, r"(reconstruct|recover).{0,180}(accessible|available).{0,100}evidence")
        self.assertRegex(handoff, r"(retained|available) (packet|identity).{0,200}(fresh|current|revalidat)")
        self.assertRegex(handoff, r"(no|without|never).{0,180}(new|default|persistent).{0,120}(store|case directory)")
        self.assertRegex(handoff, r"(do not|never).{0,160}(automatically|by default).{0,100}(display|print).{0,100}(whole|full).{0,80}json")

    def test_legacy_summary_normalization_never_invents_facts_or_state(self):
        """T019/V30: prose is cited input, never an approved packet or memory."""
        _, exit_code, result = self.validate_example("invalid-protocol")
        self.assertEqual(exit_code, 2)
        self.assertIs(result["valid"], False)
        self.assertEqual(result["errors"],
                         [{"code": "UNSUPPORTED_PROTOCOL", "path": "$.protocol"}])
        handoff = self.outcome_sections()[2]
        self.assertRegex(handoff, r"legacy.{0,180}(summary|prose).{0,180}(citation|evidence)")
        self.assertRegex(handoff, r"normali[sz].{0,180}in.memory")
        self.assertRegex(handoff, r"missing.{0,160}(fact|field|detail).{0,160}unknown")
        self.assertRegex(handoff, r"(do not|never).{0,180}(invent|assume).{0,100}(confirm|fact|repro)")
        self.assertRegex(handoff, r"(do not|never).{0,180}(rewrite|migrate).{0,140}(historical|existing).{0,80}(record|note)")
        self.assertRegex(handoff, r"(malformed|invalid).{0,180}packet.{0,180}(input error|stop|block)")
        self.assertRegex(handoff, r"(changed|drift).{0,180}(source|snapshot|evidence).{0,180}(revalidat|block)")

    def test_transport_fixtures_remain_pending_and_source_scoped(self):
        """Finite call records must not become counterfeit product results."""
        self.assertEqual(len(self.calls), len(self.cases["transport_calls"]))
        for call in self.calls.values():
            self.assertIn(call["handoff_example"], self.examples)
            self.assertEqual(call["product_status"], "PENDING")
        contract = self.handoffs["transport_fixture_contract"]
        self.assertEqual(contract["consumer"], "core/surface/commands/fix.md")
        self.assertEqual(contract["producer"], "core/surface/skills/debug/SKILL.md")
        self.assertIn("no model or host", contract["proof_boundary"])
        self.assertEqual(self.handoffs["product_status"], "PENDING")
        self.assertEqual(self.qualification["transport_source_check"]["state"], "PENDING")
        self.assertEqual(self.qualification["live_cells"], [])
        self.assertEqual(self.qualification["observations"], [])


class DebugTerminalBoardTest(CollectorCompatibleTestCase):
    def board_module(self):
        path = ROOT / ".github/scripts/test_board_sync.py"
        spec = importlib.util.spec_from_file_location("board_sync_for_debug_t024", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_no_action_and_design_results_do_not_write_tasks_or_adrs(self):
        owner = OWNER.read_text(encoding="utf-8")
        fix = (ROOT / "core/surface/commands/fix.md").read_text(encoding="utf-8")
        decision = owner.split("## Phase 4", 1)[1].split("## Phase 5", 1)[0]
        handoff = owner.split("## Phase 5", 1)[1].split("## Hard rules", 1)[0]
        self.assertIn("five dispositions", decision)
        self.assertIn("no default board or state write", owner)
        self.assertIn("do not create or route to one automatically", decision)
        self.assertIn("Make no default board write, task transition, index/history/ADR mutation", handoff)
        self.assertIn("stop without a board write or other state mutation", fix)
        self.assertIn("do not create an ADR automatically", fix)
        self.assertIn("separately authorized concrete follow-up", fix)
        route = (ROOT / "core/surface/includes/routing-table.md").read_text(encoding="utf-8")
        index = (ROOT / "core/surface/skills/INDEX.md").read_text(encoding="utf-8")
        for text in (route, index):
            for outcome in ("confirmed_code_defect", "confirmed_noncode_cause",
                            "design_question", "no_action", "unresolved"):
                self.assertIn(outcome, text)
            self.assertIn("caller authority", text)

    def test_authorized_followups_use_the_real_writer_once(self):
        owner = OWNER.read_text(encoding="utf-8")
        handoff = " ".join(owner.split("## Phase 5", 1)[1].split("## Hard rules", 1)[0].split())
        self.assertRegex(
            handoff,
            r"separately authorized concrete follow-up.{0,300}/task.{0,140}taskwrite.py",
        )
        self.assertIn("taskwrite.py", handoff)
        self.assertIn("--desc", handoff)
        task_owner = (ROOT / "core/surface/commands/task.md").read_text(encoding="utf-8")
        self.assertIn("helper-invocation.md", task_owner)
        self.assertIn("Keep every option before `--`", task_owner)
        self.assertIn("pass user text as one literal argument", task_owner)
        self.assertIn("selected installed `taskwrite.py` helper", handoff)
        self.assertIn("Python interpreter", handoff)
        self.assertIn("helper-invocation.md", handoff)
        self.assertRegex(
            handoff,
            r"--desc.{0,120}options before `--`.{0,120}literal task description after `--`",
        )
        self.assertNotIn('taskwrite.py add "<description>" --desc "<reason>"', handoff)
        self.assertIn("never by appending to the file", handoff)
        self.assertIn("once per authorized item", handoff)
        self.assertIn("action, provenance, and completion evidence", handoff)
        self.assertIn("the debug disposition itself never calls that helper", handoff)

    def test_board_sync_unittest_exposure_preserves_existing_cli_checks(self):
        import contextlib
        import io

        board = self.board_module()
        expected = [fn.__name__ for fn in board.TESTS]
        self.assertEqual(len(expected), 11)
        self.assertTrue(hasattr(board, "BoardSyncUnittest"), "ordinary unittest exposure missing")
        suite = unittest.TestLoader().loadTestsFromTestCase(board.BoardSyncUnittest)
        actual = [test._testMethodName for test in suite]
        self.assertEqual(actual, sorted(expected))
        board._failures.clear()
        output = io.StringIO()
        with mock.patch.object(board.sys, "argv", ["test_board_sync.py"]), contextlib.redirect_stdout(output):
            cli_exit = board.main()
        cli_results = {}
        for line in output.getvalue().splitlines():
            match = re.fullmatch(r"(PASS|FAIL)  (test_\w+)(?: \(\d+ assertion\(s\)\))?", line)
            if match:
                self.assertNotIn(match.group(2), cli_results)
                cli_results[match.group(2)] = match.group(1)
        self.assertEqual(set(cli_results), set(expected))
        board._failures.clear()
        suite = unittest.TestLoader().loadTestsFromTestCase(board.BoardSyncUnittest)
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 11)
        failed = {test._testMethodName for test, _ in result.failures + result.errors}
        self.assertEqual(
            cli_results,
            {name: ("FAIL" if name in failed else "PASS") for name in expected},
        )
        self.assertEqual(cli_exit, int(bool(failed)))

        with mock.patch.object(board, "read_repo", return_value=""):
            board._failures.clear()
            with mock.patch.object(board.sys, "argv", ["test_board_sync.py", "-k", "test_task_doc_states_commit_colocation"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(board.main(), 1)
            board._failures.clear()
            result = unittest.TestResult()
            board.BoardSyncUnittest("test_task_doc_states_commit_colocation").run(result)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("task.md: must name commit-gate", result.failures[0][1])

        with mock.patch.object(board, "read_repo", side_effect=RuntimeError("probe exception")):
            board._failures.clear()
            with mock.patch.object(board.sys, "argv", ["test_board_sync.py", "-k", "test_task_doc_states_commit_colocation"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(board.main(), 1)
            board._failures.clear()
            result = unittest.TestResult()
            board.BoardSyncUnittest("test_task_doc_states_commit_colocation").run(result)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("probe exception", result.errors[0][1])

    def test_board_sync_cli_rejects_empty_selection(self):
        import contextlib
        import io

        board = self.board_module()
        board._failures.clear()
        for argv, message in (
            (["test_board_sync.py", "-k"], "-k requires a pattern"),
            (["test_board_sync.py", "-k", "missing_t024_pattern"], "selected no checks"),
        ):
            output = io.StringIO()
            with mock.patch.object(board.sys, "argv", argv), contextlib.redirect_stdout(output):
                self.assertEqual(board.main(), 2)
            self.assertIn(message, output.getvalue())
        output = io.StringIO()
        with mock.patch.object(board.sys, "argv", ["test_board_sync.py", "-k", "done_flip"]), contextlib.redirect_stdout(output):
            self.assertEqual(board.main(), 0)
        self.assertIn("OK: 1 check(s) green", output.getvalue())
        self.assertIn("PASS  test_done_flip_retained", output.getvalue())
        with mock.patch.object(board, "ROOT", ROOT / ".missing-t024-required-root"):
            output = io.StringIO()
            with mock.patch.object(board.sys, "argv", ["test_board_sync.py"]), contextlib.redirect_stdout(output):
                self.assertEqual(board.main(), 2)
            self.assertIn("FATAL: missing file", output.getvalue())

if __name__ == "__main__":
    unittest.main()
