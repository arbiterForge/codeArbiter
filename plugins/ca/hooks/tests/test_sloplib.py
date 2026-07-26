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

    def test_tilde_fence_is_exempt(self):
        # _FENCE_RE matches both ``` and ~~~; the tilde fence was untested.
        text = f"Intro.\n~~~\ncode {EM} here\n~~~\nOutro.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_html_tag_or_comment_dash_is_exempt(self):
        # The <[^>]*> branch of _URL_RE: a dash inside an HTML tag/comment is code.
        text = f"Before <!-- note {EM} here --> after.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_markdown_link_target_dash_is_exempt(self):
        # The \]\([^)]*\) branch of _URL_RE: a dash inside a []() link target.
        text = f"See [the docs]({EM}path) for detail.\n"
        self.assertEqual(S.find_prose_separator_dashes(text), [])

    def test_multiple_lines_each_flagged_with_line_numbers(self):
        text = f"First {EM} sep.\nclean middle line\nthird {EN} sep.\n"
        findings = S.find_prose_separator_dashes(text)
        self.assertEqual([f["line"] for f in findings], [1, 3])


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

    def test_leading_dot_slash_is_normalized(self):
        # "./README.md" is the repo root; the leading ./ must be stripped.
        self.assertTrue(S.in_antislop_doc_scope("./README.md"))
        self.assertTrue(S.in_antislop_doc_scope("./docs/hooks.md"))
        self.assertFalse(S.in_antislop_doc_scope("./plugins/ca/ORCHESTRATOR.md"))

    def test_empty_or_falsy_path_out_of_scope(self):
        self.assertFalse(S.in_antislop_doc_scope(""))
        self.assertFalse(S.in_antislop_doc_scope(None))




class TestSitePoseScope(unittest.TestCase):
    """#338 - site/VOICE.md has banned em-dashes as sentence separators since
    2026-07-02, and nothing enforced it: `in_antislop_doc_scope` covered
    repo-root docs and docs/**, never site/. A rule with no gate, violated in 16
    of its own 36 authored files, is worse than no rule - reviewers cite it and
    it is wrong.

    The scope is AUTHORED site prose only. Everything generated is excluded, by
    path, because the generator would otherwise be flagged for output nobody
    writes by hand and nobody can fix in place."""

    def test_authored_site_docs_in_scope(self):
        for p in (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/guides/uninstalling.md",
            "site/src/content/docs/concepts/hardening-history.md",
            "site/src/content/docs/getting-started/install.md",
            "site/src/content/docs/feature-forge/index.md",
        ):
            self.assertTrue(S.in_antislop_doc_scope(p), p)

    def test_generated_reference_pages_out_of_scope(self):
        # 91 of the 128 files under content/docs are generated into reference/
        # on every build. They are not authored, not committed, and not fixable
        # in place.
        for p in (
            "site/src/content/docs/reference/commands.md",
            "site/src/content/docs/reference/agents/backend-author.md",
        ):
            self.assertFalse(S.in_antislop_doc_scope(p), p)

    def test_generated_changelog_page_out_of_scope(self):
        # Verbatim pass-through of the repo CHANGELOG, which is payload prose
        # under a different voice.
        self.assertFalse(S.in_antislop_doc_scope("site/src/content/docs/changelog.md"))

    def test_curated_plugin_mirrors_out_of_scope(self):
        # site/src/curated/** mirrors plugins/ca bodies. Those are framework
        # prose governed by the plugin's own register, already excluded via
        # plugins/ - mirroring them into site must not smuggle them back in.
        for p in (
            "site/src/curated/agents/backend-author.md",
            "site/src/curated/commands/fix.md",
        ):
            self.assertFalse(S.in_antislop_doc_scope(p), p)

    def test_site_source_that_is_not_docs_prose_out_of_scope(self):
        for p in ("site/README.md", "site/VOICE.md", "site/src/components/Thing.md"):
            self.assertFalse(S.in_antislop_doc_scope(p), p)

    def test_mdx_authored_pages_are_in_scope_too(self):
        # Two authored pages are .mdx. The predicate keyed on ".md" only, so
        # they were invisible to a rule that is about prose, not file format.
        self.assertTrue(S.in_antislop_doc_scope("site/src/content/docs/index.mdx"))




class TestDefinitionListDashExempt(unittest.TestCase):
    """#338 - the rule is about SENTENCE separators. A definition-list dash is
    structural, and site/VOICE.md's own Terminology anchors are written in that
    exact form, so flagging it would make the gate contradict the guide."""

    def test_definition_list_dash_is_not_a_finding(self):
        for line in (
            "- **gate** — a phase exit condition (STOP/BLOCK).",
            "* **lane** — a sanctioned path through the system.",
            "**skill** — an orchestrator routine with phases.",
        ):
            self.assertEqual(S.find_prose_separator_dashes(line), [], line)

    def test_a_real_separator_after_a_definition_is_still_caught(self):
        # Only the definition DASH is dropped, never the term before it. A
        # second dash on the same line is still a separator and must not ride in
        # behind the exemption.
        line = "- **gate** — a phase exit condition — and it blocks the call."
        self.assertEqual(len(S.find_prose_separator_dashes(line)), 1)

    def test_definition_exemption_survives_inline_code_after_it(self):
        # The regression this exemption first shipped with, and the reason the
        # test above was not enough: dropping the whole `- **term**` lead-in left
        # the NEXT dash with no word character on its left once
        # _INLINE_CODE_RE blanked the backticks, so a real separator vanished.
        # Verbatim from site/src/content/docs/getting-started/compatibility.md,
        # which the detector scored 1 before the exemption and 0 after.
        line = "- **The gate-enforcement hooks** — `pre-bash.py`, `pre-write.py` — make **zero** network calls."
        self.assertEqual(len(S.find_prose_separator_dashes(line)), 1)

    def test_definition_term_is_preserved_for_downstream_checks(self):
        # Stated as a property, not an implementation detail: whatever the
        # exemption does, the term's own words must survive into the analysed
        # text, or any later dash on the line loses its left-hand context.
        self.assertIn("gate", S._prose_only("- **gate** — a phase exit condition"))

    def test_bold_mid_sentence_is_not_treated_as_a_definition(self):
        # The exemption is anchored to the start of the line, so an ordinary
        # sentence containing bold text keeps its finding.
        line = "The **commit gate** runs nine checks — every one must be green."
        self.assertEqual(len(S.find_prose_separator_dashes(line)), 1)


if __name__ == "__main__":
    unittest.main()
