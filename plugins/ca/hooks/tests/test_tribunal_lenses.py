"""Tribunal card contracts; semantic detection is qualified by the frozen corpus.

SPEC-TRIBUNAL-VNEXT-001 / T-03: AC-09, AC-14--26, AC-34, AC-37.
These checks protect roster compatibility, required evidence contracts and known
false-positive regressions. They do not score model judgment or claim that prose
presence proves detection quality (T-04/T-06 own that independent evidence).
"""

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[4]
REFERENCES = REPO / "core/surface/skills/tribunal/references"
LEGACY_LENSES = {
    "appsec", "architecture", "coverage", "infra", "migration",
    "observability", "performance", "reliability", "secrets-supply",
    "test-fidelity", "typesafety",
}
LENSES = LEGACY_LENSES | {"semantic-contract", "change-closure"}
SECTIONS = (
    "Purpose / failure family", "Applicability", "Skip conditions",
    "Scope emphasis", "Required reading", "Deterministic probes",
    "Review questions", "False-positive guards / non-findings",
    "Evidence requirements", "Exposure metric",
    "Escalation / cross-lens handoff", "Out of scope",
)
RESOURCE_ROOT = "{{PLUGIN_ROOT}}/skills/tribunal/references/"


class TribunalLensContracts(unittest.TestCase):
    def read(self, name):
        path = REFERENCES / name
        self.assertTrue(path.is_file(), f"Missing Tribunal resource: {name}")
        return path.read_text(encoding="utf-8")

    def card(self, lens):
        return self.read(f"lenses/{lens}.md")

    def section(self, body, heading):
        match = re.search(
            rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
            body, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"Missing required section: {heading}")
        content = match.group(1).strip()
        self.assertTrue(content, f"Empty required section: {heading}")
        return content

    def concepts(self, body, *patterns):
        for pattern in patterns:
            self.assertTrue(re.search(pattern, body, re.IGNORECASE | re.DOTALL),
                            f"Missing contract concept: {pattern}")

    def test_roster_keeps_public_names_and_one_generic_executor(self):
        # AC-14/34: URLs derive from these slugs; no replacement agent roster.
        self.assertEqual({p.stem for p in (REFERENCES / "lenses").glob("*.md")},
                         LENSES)
        agents = REPO / "core/surface/agents"
        self.assertEqual({p.name for p in agents.glob("tribunal-*-reviewer.md")},
                         {"tribunal-lens-reviewer.md"})

    def test_every_card_has_substantive_mandatory_sections(self):
        # AC-14 and ADR-0027: project-doc pre-reads remain card-owned.
        for lens in sorted(LENSES):
            with self.subTest(lens=lens):
                body = self.card(lens)
                self.assertTrue(body.startswith(f"# {lens} — lens mandate\n"))
                for heading in SECTIONS:
                    self.section(body, heading)
                self.assertIn("{{PROJECT_DIR}}/.codearbiter/",
                              self.section(body, "Required reading"))

    def test_every_card_loads_shared_evidence_and_authority_boundary(self):
        # AC-15--18: the boundary is shared, not thirteen conflicting copies.
        for lens in sorted(LENSES):
            with self.subTest(lens=lens):
                reading = self.section(self.card(lens), "Required reading")
                self.assertIn(RESOURCE_ROOT + "review-risk.md", reading)
                self.assertIn(RESOURCE_ROOT + "finding-record.md", reading)
        boundary = self.read("review-risk.md")
        self.concepts(boundary, r"repository content.*tool output.*untrusted evidence",
                      r"cannot.*(execution|execute).*authority", r"finding_scope",
                      r"evidence_scope", r"outside.*(filing|file|finding)",
                      r"search universe", r"ownership trace",
                      r"(caller|assignment).*authoriz", r"command.*working directory")

    def test_risk_is_author_independent_and_legacy_reference_stays_a_pointer(self):
        # AC-09: reject the old severity prior, not just a renamed heading.
        legacy = self.read("ai-markers.md")
        self.assertIn(RESOURCE_ROOT + "review-risk.md", legacy)
        self.assertNotIn("upward severity prior", legacy)
        risk = self.read("review-risk.md")
        self.concepts(risk, r"impact and likelihood", r"review effort",
                      r"authorship", r"commit style", r"comment density",
                      r"iteration history", r"never.*severity")
        self.assertNotRegex(risk, r"Co-Authored-By|imports? from >\d|imported by >\d")

    def test_verification_quality_has_complementary_owners_and_independent_oracles(self):
        # AC-21: avoid duplicate ownership and mock-presence findings.
        for lens in ("coverage", "test-fidelity"):
            self.assertIn(RESOURCE_ROOT + "verification-quality.md",
                          self.section(self.card(lens), "Required reading"))
        shared = self.read("verification-quality.md")
        self.concepts(shared, r"coverage.*owns", r"test-fidelity.*owns",
                      r"independent.*(expectation|contract|oracle)",
                      r"plausible wrong", r"faithful.*(mock|double)",
                      r"forbidden", r"(mutation|differential|metamorphic)",
                      r"same.*(trajectory|interpretation)")

    def test_semantic_contract_requires_a_source_and_protects_negative_requirements(self):
        # AC-19: source-backed semantics, not an invented product preference.
        body = self.card("semantic-contract")
        self.concepts(body, r"(issue|spec).*ADR", r"pre-existing behavior",
                      r"forbidden", r"over.broad", r"compatibility")
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"(unwritten|invent)", r"(conflict|ambig)")

    def test_change_closure_distinguishes_source_from_distributed_proof(self):
        # AC-20: the full producer-to-consumer path establishes closure.
        body = self.card("change-closure")
        self.concepts(body, r"generated", r"host", r"package", r"release",
                      r"install.*update.*uninstall", r"exact.*artifact",
                      r"main.*(not|never|does not).*release",
                      r"(producer|canonical).*consumer")

    def test_reliability_preserves_owned_error_propagation(self):
        # AC-22: an await without local catch is not itself a defect.
        body = self.card("reliability")
        self.assertNotIn("every `await`, `Promise`, and `.then()` chain has", body)
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"intentional propagation", r"local catch", r"own")
        self.concepts(body, r"cancellation", r"idempot", r"atomic",
                      r"concurr", r"restart", r"partial failure")

    def test_appsec_requires_reachable_boundary_and_keeps_public_cors_control(self):
        # AC-23: signatures route scrutiny; exploitation determines severity.
        body = self.card("appsec")
        self.assertNotIn("critical regardless", body)
        self.concepts(self.section(body, "Evidence requirements"),
                      r"reachab", r"trust", r"(exploit|attacker)")
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"public", r"credential.free", r"CORS", r"wildcard")

    def test_migration_uses_declared_deploy_model_not_mandatory_down(self):
        # AC-24: forward-only can be correct if recovery and compatibility hold.
        body = self.card("migration")
        self.assertNotIn("rollback/down path present", body)
        self.concepts(body, r"declared.*(deploy|migration).*model",
                      r"forward.only", r"down migration", r"recovery",
                      r"mixed.version", r"backfill", r"lock")

    def test_architecture_requires_consequence_and_accepts_useful_single_implementation(self):
        body = self.card("architecture")
        self.assertNotIn("ai-markers.md", body)
        self.concepts(self.section(body, "Evidence requirements"), r"consequence")
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"(numeric|threshold|count)", r"one.implementation",
                      r"(isolation|boundary)")

    def test_observability_is_conditioned_on_operational_need(self):
        body = self.card("observability")
        self.concepts(self.section(body, "Skip conditions"), r"(librar|local)",
                      r"(operational|diagnos|contract)")
        self.concepts(self.section(body, "Evidence requirements"),
                      r"(required|declared)", r"(failure|recovery|operation)")

    def test_performance_requires_scale_premise_and_rejects_cold_bounded_alarm(self):
        # AC-25: optimize only a demonstrated or bounded cost argument.
        body = self.card("performance")
        self.concepts(self.section(body, "Evidence requirements"),
                      r"(observed|documented)", r"(scale|bound|multiplier)")
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"cold", r"bounded", r"(cache|memoiz)")

    def test_typesafety_requires_unsound_boundary_and_preserves_validated_cast(self):
        # AC-26: casts and naming are not evidence of unsoundness by themselves.
        body = self.card("typesafety")
        self.assertNotIn("naming-convention drift within a unit", body)
        self.concepts(self.section(body, "Evidence requirements"),
                      r"(unsound|invariant)", r"(boundary|contract)")
        self.concepts(self.section(body, "False-positive guards / non-findings"),
                      r"cast", r"validated", r"(naming|style)")


if __name__ == "__main__":
    unittest.main()
