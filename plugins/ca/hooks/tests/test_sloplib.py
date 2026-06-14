import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sloplib as S  # noqa: E402

EM = "—"
EN = "–"


class TestProseSeparatorDashes(unittest.TestCase):
    # Regression for #60: user-facing docs shipped with em-dash prose separators
    # (the core 3.A tell) because nothing flagged them. The detector is the guard.

    def test_flags_em_dash_separator_in_prose(self):
        findings = S.find_prose_separator_dashes(f"The gate blocks {EM} the human resolves.\n")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["line"], 1)

    def test_flags_en_dash_separator_in_prose(self):
        findings = S.find_prose_separator_dashes(f"One thing {EN} then another.\n")
        self.assertEqual(len(findings), 1)

    def test_clean_prose_has_no_findings(self):
        findings = S.find_prose_separator_dashes("Plain prose. Two sentences. No dashes.\n")
        self.assertEqual(findings, [])

    def test_fenced_code_block_is_exempt(self):
        text = f"Intro line.\n```\nfoo {EM} bar (this is code)\n```\nOutro line.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_inline_code_is_exempt(self):
        self.assertEqual(S.find_prose_separator_dashes(f"Use `a {EM} b` literally.\n"), [])

    def test_numeric_and_date_range_en_dash_is_exempt(self):
        # core 3.A: numeric/date ranges with an en-dash are correct typography.
        text = f"Active 2019{EN}2024, pp. 12{EN}18.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_url_with_dash_is_exempt(self):
        text = f"See https://example.com/a{EM}b for detail.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_lone_dash_table_cell_is_exempt(self):
        # An em-dash as a standalone table-cell value (an N/A marker) is not a
        # prose sentence separator — it joins nothing.
        text = f"| `SessionStart` | {EM} | runs | no |\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_real_separator_inside_table_cell_is_flagged(self):
        text = f"| col | it blocks {EM} then resolves | end |\n"
        self.assertEqual(len(S.find_prose_separator_dashes(text)), 1)

    def test_reports_correct_line_number(self):
        text = f"Line one is clean.\nLine two has {EM} a separator.\n"
        findings = S.find_prose_separator_dashes(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["line"], 2)


class TestAntiSlopDocScope(unittest.TestCase):
    def test_root_community_docs_in_scope(self):
        for p in ("README.md", "PRIVACY.md", "SECURITY.md", "CONTRIBUTING.md",
                  "CODE_OF_CONDUCT.md", "CHANGELOG.md"):
            self.assertTrue(S.in_antislop_doc_scope(p), p)

    def test_docs_dir_in_scope(self):
        self.assertTrue(S.in_antislop_doc_scope("docs/hooks.md"))
        self.assertTrue(S.in_antislop_doc_scope("docs/guide/intro.md"))

    def test_framework_bodies_out_of_scope(self):
        # The bundle excludes codeArbiter's own framework docs — all under plugins/.
        for p in ("plugins/ca/ORCHESTRATOR.md", "plugins/ca/commands/chore.md",
                  "plugins/ca/agents/scout.md",
                  "plugins/ca/includes/anti-slop-design/core.md"):
            self.assertFalse(S.in_antislop_doc_scope(p), p)

    def test_codearbiter_state_out_of_scope(self):
        self.assertFalse(S.in_antislop_doc_scope(".codearbiter/CONTEXT.md"))

    def test_non_markdown_out_of_scope(self):
        self.assertFalse(S.in_antislop_doc_scope("README.txt"))
        self.assertFalse(S.in_antislop_doc_scope("src/main.py"))

    def test_windows_separators_normalized(self):
        self.assertFalse(S.in_antislop_doc_scope("plugins\\ca\\ORCHESTRATOR.md"))
        self.assertTrue(S.in_antislop_doc_scope("docs\\hooks.md"))


if __name__ == "__main__":
    unittest.main()
