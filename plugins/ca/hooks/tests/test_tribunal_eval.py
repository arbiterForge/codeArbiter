#!/usr/bin/env python3
# codeArbiter — offline Tribunal scorer behavioral contracts.
"""Synthetic outputs below test arithmetic; they are never model qualification."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools/tribunal-eval.py"
CORPUS = ROOT / ".github/fixtures/tribunal/cases.json"
FAMILIES = {
    "intentional-async-propagation", "swallowed-error", "mock-fidelity",
    "missing-test-oracle", "self-confirming-test", "semantic-divergence",
    "over-broad-change", "incomplete-propagation", "concurrency-race",
    "resource-authorization", "reachable-injection", "public-cors",
    "registry-existence", "justified-interface", "leaky-abstraction",
    "type-boundary", "performance-premise", "prompt-injection",
    "cross-lens-root", "source-drift",
}


class TribunalEvalTests(unittest.TestCase):
    def evaluator(self):
        self.assertTrue(SCRIPT.is_file(), "T-04 offline evaluator is not implemented")
        spec = importlib.util.spec_from_file_location("tribunal_eval", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def corpus(self):
        self.assertTrue(CORPUS.is_file(), "T-04 frozen paired corpus is missing")
        return self.evaluator().load_corpus(CORPUS)

    def synthetic(self, corpus, selections=()):
        """Selections are (case, finding ID, lens, root, status, match)."""
        tool = self.evaluator()
        packet = tool.public_packet(corpus)
        run = {
            "schema": "tribunal-review/v1", "evidence_kind": "synthetic",
            "run_id": "synthetic-unit-test", "corpus_sha256": corpus["sha256"],
            "packet_sha256": tool.digest(packet), "model": "synthetic-no-model",
            "host": "unittest", "card_revision": "synthetic-test-only",
            "card_bundle_sha256": "a" * 64, "duration_seconds": 8,
            "tokens": None,
            "cases": [{"case_id": c["case_id"], "source_sha256": c["source_sha256"],
                       "findings": []} for c in packet["cases"]],
        }
        records = []
        for case, finding_id, lens, root, status, match in selections:
            file = case["public"]["files"][0]
            finding = {
                "finding_id": finding_id, "contract_id": "R1",
                "title": "Synthetic claimed contract violation", "severity": "high",
                "lens": lens, "root_cause_key": root,
                "evidence": [{"path": file["path"], "line": 1,
                              "quote": file["content"].splitlines()[0]}],
                "verification_status": "unverified",
            }
            next(c for c in run["cases"] if c["case_id"] == case["case_id"])["findings"].append(finding)
            records.append({"case_id": case["case_id"], "finding_id": finding_id,
                            "status": status, "matches_contract": match,
                            "rationale": "Synthetic explicit fixture adjudication",
                            "evidence": copy.deepcopy(finding["evidence"])})
        adjudication = {
            "schema": "tribunal-adjudication/v1", "evidence_kind": "synthetic",
            "corpus_sha256": corpus["sha256"], "run_sha256": tool.digest(run),
            "verifier_id": "synthetic-independent-test", "independence": "fresh",
            "findings": records,
            "case_compliance": [{"case_id": c["case_id"], "assignment_compliant": True,
                                 "rationale": "Synthetic fixture obeys assignment"}
                                for c in run["cases"]],
        }
        return run, adjudication

    def test_all_twenty_families_have_both_variants_and_frozen_digest(self):
        corpus = self.corpus()
        self.assertEqual(40, len(corpus["cases"]))
        self.assertEqual(FAMILIES, {c["private"]["family"] for c in corpus["cases"]})
        for family in FAMILIES:
            pair = [c for c in corpus["cases"] if c["private"]["family"] == family]
            self.assertEqual({"defect", "clean"}, {c["private"]["variant"] for c in pair})
            self.assertEqual(pair[0]["public"]["contracts"], pair[1]["public"]["contracts"])
        altered = copy.deepcopy(corpus)
        altered["cases"][0]["public"]["files"][0]["content"] += "changed"
        with self.assertRaisesRegex(ValueError, "digest"):
            self.evaluator().validate_corpus(altered)

    def test_export_is_blind_and_binds_each_source(self):
        tool, corpus = self.evaluator(), self.corpus()
        packet = tool.public_packet(corpus)
        self.assertEqual(40, len(packet["cases"]))
        for case in packet["cases"]:
            self.assertEqual({"case_id", "contracts", "files", "source_sha256"}, set(case))
            self.assertRegex(case["case_id"], r"^c-[0-9a-f]{12}$")
            material = {key: case[key] for key in ("contracts", "files")}
            self.assertEqual(tool.digest(material), case["source_sha256"])
        self.assertNotIn('"private"', json.dumps(packet))
        self.assertNotIn('"required_contracts"', json.dumps(packet))
        self.assertNotIn('"family"', json.dumps(packet))

    def test_synthetic_metrics_are_explicit_and_duplicates_are_consolidated(self):
        tool, corpus = self.evaluator(), self.corpus()
        defects = [c for c in corpus["cases"] if c["private"]["variant"] == "defect"]
        control = next(c for c in corpus["cases"] if c["private"]["variant"] == "clean")
        run, adj = self.synthetic(corpus, [
            (defects[0], "F1", "reliability", "root-a", "confirmed", True),
            (defects[0], "F2", "appsec", "root-a", "confirmed", True),
            (defects[0], "F3", "appsec", "root-a", "confirmed", True),
            (defects[1], "F4", "reliability", "root-b", "inconclusive", True),
            (control, "F5", "appsec", "root-c", "refuted", False),
        ])
        with self.assertRaisesRegex(ValueError, "synthetic"):
            tool.score(corpus, run, adj)
        result = tool.score(corpus, run, adj, allow_synthetic=True)
        self.assertEqual("synthetic", result["evidence_kind"])
        metrics = result["metrics"]
        self.assertEqual(2 / 20, metrics["recall"])
        self.assertEqual(1 / 20, metrics["verified_recall"])
        self.assertEqual(1 / 20, metrics["clean_control_false_positive_rate"])
        self.assertEqual(3 / 5, metrics["serious_verification_survival"])
        self.assertEqual(1, metrics["serious_verified_precision"])
        self.assertEqual(1, metrics["unique_verified_root_causes"])
        self.assertEqual(1, metrics["duplicate_count"])
        self.assertEqual(1, metrics["corroboration_count"])
        self.assertEqual("unavailable", result["cost"]["tokens"])
        self.assertEqual(8, result["cost"]["duration_seconds"])
        self.assertGreater(result["cost"]["evidence_bytes"], 0)

    def test_missing_duplicate_unknown_cases_and_source_mismatch_fail_closed(self):
        tool, corpus = self.evaluator(), self.corpus()
        for mutation in ("missing", "duplicate", "unknown", "source", "corpus", "packet"):
            run, adj = self.synthetic(corpus)
            if mutation == "missing":
                run["cases"].pop()
            elif mutation == "duplicate":
                run["cases"].append(copy.deepcopy(run["cases"][0]))
            elif mutation == "unknown":
                run["cases"][0]["case_id"] = "c-000000000000"
            elif mutation == "source":
                run["cases"][0]["source_sha256"] = "0" * 64
            else:
                run[mutation + "_sha256"] = "0" * 64
            adj["run_sha256"] = tool.digest(run)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                tool.score(corpus, run, adj, allow_synthetic=True)

    def test_adjudication_requires_exact_run_all_findings_and_real_evidence(self):
        tool, corpus = self.evaluator(), self.corpus()
        defect = next(c for c in corpus["cases"] if c["private"]["variant"] == "defect")
        for mutation in ("stale", "missing", "duplicate", "quote", "self", "compliance"):
            run, adj = self.synthetic(corpus, [(defect, "F1", "appsec", "root", "confirmed", True)])
            if mutation == "stale":
                adj["run_sha256"] = "0" * 64
            elif mutation == "missing":
                adj["findings"] = []
            elif mutation == "duplicate":
                adj["findings"].append(copy.deepcopy(adj["findings"][0]))
            elif mutation == "quote":
                adj["findings"][0]["evidence"][0]["quote"] = "not in source"
            elif mutation == "self":
                adj["verifier_id"] = run["run_id"]
            else:
                adj["case_compliance"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                tool.score(corpus, run, adj, allow_synthetic=True)

    def test_no_findings_null_rates_and_limited_verification_are_honest(self):
        tool, corpus = self.evaluator(), self.corpus()
        run, adj = self.synthetic(corpus)
        run["duration_seconds"] = None
        adj["run_sha256"] = tool.digest(run)
        result = tool.score(corpus, run, adj, allow_synthetic=True)
        self.assertIsNone(result["metrics"]["serious_verified_precision"])
        self.assertIsNone(result["metrics"]["serious_verification_survival"])
        self.assertEqual("unavailable", result["cost"]["duration_seconds"])
        adj["independence"] = "limited"
        self.assertFalse(tool.score(corpus, run, adj, allow_synthetic=True)["qualification_eligible"])

    def test_test_only_captured_schema_requires_fresh_verification(self):
        """In-memory schema branch fixture only: no model capture or quality proof."""
        tool, corpus = self.evaluator(), self.corpus()
        run, fresh = self.synthetic(corpus)
        run["evidence_kind"] = "captured"
        fresh["evidence_kind"] = "captured"
        fresh["run_sha256"] = tool.digest(run)
        self.assertTrue(tool.score(corpus, run, fresh)["qualification_eligible"])
        limited = copy.deepcopy(fresh)
        limited["independence"] = "limited"
        self.assertFalse(tool.score(corpus, run, limited)["qualification_eligible"])
        self.assertFalse(tool.compare(corpus, run, fresh, run, limited)["promotion_eligible"])

    def test_critical_regression_blocks_equal_and_noncritical_improvement_do_not(self):
        tool, corpus = self.evaluator(), self.corpus()
        critical = next(c for c in corpus["cases"] if c["private"]["critical"] and c["private"]["variant"] == "defect")
        normal = next(c for c in corpus["cases"] if not c["private"]["critical"] and c["private"]["variant"] == "defect")
        old, old_adj = self.synthetic(corpus, [(critical, "F1", "appsec", "root", "confirmed", True)])
        empty, empty_adj = self.synthetic(corpus)
        failed = tool.compare(corpus, old, old_adj, empty, empty_adj, allow_synthetic=True)
        self.assertEqual("blocked", failed["critical_regression_gate"])
        self.assertIn(critical["case_id"], failed["critical_regressions"])
        equal = tool.compare(corpus, old, old_adj, old, old_adj, allow_synthetic=True)
        self.assertEqual("clear", equal["critical_regression_gate"])
        improved, improved_adj = self.synthetic(corpus, [
            (critical, "F1", "appsec", "root", "confirmed", True),
            (normal, "F2", "coverage", "another", "confirmed", True),
        ])
        self.assertEqual("clear", tool.compare(corpus, old, old_adj, improved, improved_adj,
                                               allow_synthetic=True)["critical_regression_gate"])
        self.assertFalse(equal["promotion_eligible"], "synthetic data never qualifies a model")

    def test_critical_clean_false_positive_and_injection_noncompliance_block(self):
        tool, corpus = self.evaluator(), self.corpus()
        control = next(c for c in corpus["cases"] if c["private"]["critical"] and c["private"]["variant"] == "clean")
        old, old_adj = self.synthetic(corpus)
        new, new_adj = self.synthetic(corpus, [(control, "F1", "appsec", "root", "refuted", False)])
        self.assertEqual("blocked", tool.compare(corpus, old, old_adj, new, new_adj,
                                                 allow_synthetic=True)["critical_regression_gate"])
        new, new_adj = self.synthetic(corpus)
        injection = next(c for c in corpus["cases"] if c["private"]["family"] == "prompt-injection")
        next(c for c in new_adj["case_compliance"] if c["case_id"] == injection["case_id"])["assignment_compliant"] = False
        self.assertEqual("blocked", tool.compare(corpus, old, old_adj, new, new_adj,
                                                 allow_synthetic=True)["critical_regression_gate"])

    def test_critical_verified_loss_blocks_while_detected_hit_is_retained(self):
        tool, corpus = self.evaluator(), self.corpus()
        critical = next(c for c in corpus["cases"] if c["private"]["critical"] and c["private"]["variant"] == "defect")
        run, confirmed = self.synthetic(corpus, [(critical, "F1", "appsec", "root", "confirmed", True)])
        equal = tool.compare(corpus, run, confirmed, run, confirmed, allow_synthetic=True)
        self.assertEqual("clear", equal["critical_regression_gate"])
        inconclusive = copy.deepcopy(confirmed)
        inconclusive["findings"][0]["status"] = "inconclusive"
        result = tool.compare(corpus, run, confirmed, run, inconclusive, allow_synthetic=True)
        before = result["incumbent"]["cases"][critical["case_id"]]
        after = result["candidate"]["cases"][critical["case_id"]]
        self.assertEqual(["R1"], before["hit"])
        self.assertEqual(before["hit"], after["hit"])
        self.assertEqual(["R1"], before["verified"])
        self.assertEqual([], after["verified"])
        self.assertEqual("blocked", result["critical_regression_gate"])
        self.assertEqual([critical["case_id"]], result["blocked_cases"])

    def test_exception_rejects_changed_adjudications_with_unchanged_review_runs(self):
        tool, corpus = self.evaluator(), self.corpus()
        critical = next(c for c in corpus["cases"] if c["private"]["critical"] and c["private"]["variant"] == "defect")
        for changed_side in ("incumbent", "candidate"):
            with self.subTest(changed_side=changed_side):
                status = "inconclusive" if changed_side == "incumbent" else "confirmed"
                old, old_adj = self.synthetic(corpus, [(critical, "F1", "appsec", "root", status, True)])
                new, new_adj = self.synthetic(corpus, [
                    (critical, "F1", "appsec", "root", status, True),
                    (critical, "F2", "reliability", "extra", "refuted", False),
                ])
                exceptions = {
                    "schema": "tribunal-exceptions/v1", "corpus_sha256": corpus["sha256"],
                    "incumbent_run_sha256": tool.digest(old), "candidate_run_sha256": tool.digest(new),
                    "incumbent_adjudication_sha256": tool.digest(old_adj),
                    "candidate_adjudication_sha256": tool.digest(new_adj),
                    "approvals": [{"case_id": critical["case_id"], "approved_by": "synthetic-human-owner",
                                   "approval_reference": "synthetic-test-only-receipt",
                                   "rationale": "Synthetic approval covers only the additional false positive",
                                   "evidence": "Synthetic fixture, never authorization"}],
                }
                accepted = tool.compare(corpus, old, old_adj, new, new_adj, exceptions, allow_synthetic=True)
                self.assertEqual("clear", accepted["critical_regression_gate"])
                review_digests = (tool.digest(old), tool.digest(new))
                revised_old, revised_new = copy.deepcopy(old_adj), copy.deepcopy(new_adj)
                changed = revised_old if changed_side == "incumbent" else revised_new
                changed["findings"][0]["status"] = "confirmed" if changed_side == "incumbent" else "inconclusive"
                self.assertEqual(review_digests, (tool.digest(old), tool.digest(new)))
                original = old_adj if changed_side == "incumbent" else new_adj
                self.assertNotEqual(tool.digest(original), tool.digest(changed))
                with self.assertRaisesRegex(ValueError, "stale exception"):
                    tool.compare(corpus, old, revised_old, new, revised_new, exceptions, allow_synthetic=True)

    def test_external_exception_is_exactly_bound_and_cannot_self_approve(self):
        tool, corpus = self.evaluator(), self.corpus()
        critical = next(c for c in corpus["cases"] if c["private"]["critical"] and c["private"]["variant"] == "defect")
        old, old_adj = self.synthetic(corpus, [(critical, "F1", "appsec", "root", "confirmed", True)])
        new, new_adj = self.synthetic(corpus)
        exceptions = {
            "schema": "tribunal-exceptions/v1", "corpus_sha256": corpus["sha256"],
            "incumbent_run_sha256": tool.digest(old), "candidate_run_sha256": tool.digest(new),
            "incumbent_adjudication_sha256": tool.digest(old_adj),
            "candidate_adjudication_sha256": tool.digest(new_adj),
            "approvals": [{"case_id": critical["case_id"], "approved_by": "synthetic-human-owner",
                           "approval_reference": "synthetic-test-only-receipt", "rationale": "Synthetic exception fixture",
                           "evidence": "Synthetic fixture, never authorization"}],
        }
        result = tool.compare(corpus, old, old_adj, new, new_adj, exceptions, allow_synthetic=True)
        self.assertEqual("clear", result["critical_regression_gate"])
        self.assertEqual([critical["case_id"]], result["approved_exceptions"])
        self.assertFalse(result["promotion_eligible"])
        for mutation in ("stale", "self", "missing_approval"):
            invalid = copy.deepcopy(exceptions)
            if mutation == "stale":
                invalid["candidate_run_sha256"] = "0" * 64
            elif mutation == "self":
                invalid["approvals"][0]["approved_by"] = new_adj["verifier_id"]
            else:
                invalid["approvals"][0]["approval_reference"] = ""
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                tool.compare(corpus, old, old_adj, new, new_adj, invalid, allow_synthetic=True)

    def test_cli_exports_scores_compares_and_rejects_malformed_json(self):
        corpus = self.corpus()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "blind.json"
            command = [sys.executable, str(SCRIPT)]
            valid = subprocess.run(command + ["validate"], capture_output=True, text=True)
            self.assertEqual(0, valid.returncode, valid.stderr)
            exported = subprocess.run(command + ["export", "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(0, exported.returncode, exported.stderr)
            self.assertEqual(self.evaluator().public_packet(corpus), json.loads(output.read_text(encoding="utf-8")))
            run, adj = self.synthetic(corpus)
            run_path, adj_path = Path(temporary) / "run.json", Path(temporary) / "adj.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            adj_path.write_text(json.dumps(adj), encoding="utf-8")
            scored = subprocess.run(command + ["score", "--run", str(run_path), "--adjudication", str(adj_path), "--allow-synthetic"], capture_output=True, text=True)
            self.assertEqual(0, scored.returncode, scored.stderr)
            self.assertEqual("synthetic", json.loads(scored.stdout)["evidence_kind"])
            compared = subprocess.run(command + ["compare", "--incumbent", str(run_path), "--incumbent-adjudication", str(adj_path), "--candidate", str(run_path), "--candidate-adjudication", str(adj_path), "--allow-synthetic"], capture_output=True, text=True)
            self.assertEqual(0, compared.returncode, compared.stderr)
            self.assertFalse(json.loads(compared.stdout)["promotion_eligible"])
            run_path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
            bad = subprocess.run(command + ["score", "--run", str(run_path), "--adjudication", str(adj_path)], capture_output=True, text=True)
            self.assertNotEqual(0, bad.returncode)
            self.assertNotIn("Traceback", bad.stderr)


if __name__ == "__main__":
    unittest.main()
