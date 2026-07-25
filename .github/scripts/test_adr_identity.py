#!/usr/bin/env python3
"""codeArbiter - ADR identity + supersession-resolution contract (#416).

Two ADR files in this repository carry the number 0014
(`0014-githook-shim-dropin-fail-closed` and
`0014-pi-host-authentication-and-fail-closed-tool-boundary`), and two later
ADRs supersede *different* ones of them. A bare `supersedes: 0014` therefore
names two documents at once, and every consumer that derived an ADR id with
`filename.split("-")[0]` collapsed the pair into one indistinguishable id.

The contract this file pins:

  1. The filename STEM is the ADR identifier - `0014-githook-shim-dropin-
     fail-closed`, not `0014`. Both hook-side indexers derive it that way, and
     they derive it identically.
  2. Filename stems are unique, and an ADR number resolves to exactly one stem
     apart from the one grandfathered historical collision. A NEW file taking
     an already-used number is a contract violation, so the collision cannot
     recur.
  3. Every `supersedes:` value resolves to exactly ONE ADR. A stem always
     resolves. A bare number resolves only while it is unambiguous; once it
     names more than one stem it is an error, never a guess.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)
sys.path.insert(0, HERE)

import _readinjectlib as ril  # noqa: E402 - needs the sys.path mutation above

# Guarded so a missing checker module does not abort collection of the hook
# derivation tests above it - every obligation then fails loudly on its own.
try:
    import check_adr_identity as cai
except ImportError:  # pragma: no cover - only before the module exists
    cai = None


def _load_post_write_edit():
    """Import post-write-edit.py by path (its name is not a valid identifier)."""
    spec = importlib.util.spec_from_file_location(
        "post_write_edit_for_adr_identity",
        os.path.join(HOOKS, "post-write-edit.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pwe = _load_post_write_edit()


def _write_adr(ddir, filename, status="accepted", title="T", governs="src/**"):
    lines = ["---", "status: %s" % status, "title: %s" % title]
    if governs:
        lines.append("governs: %s" % governs)
    lines.append("---")
    lines.append("# Body")
    with open(os.path.join(ddir, filename), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines) + "\n")


class HookIdDerivationTest(unittest.TestCase):
    """Clause 1 - both hook indexers key an ADR by its full filename stem."""

    GITHOOK = "0014-githook-shim-dropin-fail-closed"
    PIAUTH = "0014-pi-host-authentication-and-fail-closed-tool-boundary"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ddir = os.path.join(self.root, ".codearbiter", "decisions")
        os.makedirs(self.ddir)
        _write_adr(self.ddir, self.GITHOOK + ".md", title="Git-hook shim")
        _write_adr(self.ddir, self.PIAUTH + ".md", title="Pi host auth")

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepted_adr_index_keys_two_same_numbered_adrs_apart(self):
        ids = sorted(e["adr"] for e in ril.accepted_adr_index(self.root))
        self.assertEqual(ids, sorted([self.GITHOOK, self.PIAUTH]))

    def test_governs_index_keys_two_same_numbered_adrs_apart(self):
        ids = sorted(e["adr"] for e in pwe.governs_index(self.root))
        self.assertEqual(ids, sorted([self.GITHOOK, self.PIAUTH]))

    def test_both_indexers_derive_the_same_identifier_for_the_same_file(self):
        """The defect was duplicated derivation logic; pin the two together."""
        left = {e["adr"] for e in ril.accepted_adr_index(self.root)}
        right = {e["adr"] for e in pwe.governs_index(self.root)}
        self.assertEqual(left, right)

    def test_pointer_text_names_the_stem_so_a_reader_can_tell_them_apart(self):
        index = ril.accepted_adr_index(self.root)
        texts = [p["text"] for p in ril.adr_pointers("src/x.py", index)]
        self.assertEqual(len(texts), 2, texts)
        self.assertTrue(any("ADR-" + self.GITHOOK in t for t in texts), texts)
        self.assertTrue(any("ADR-" + self.PIAUTH in t for t in texts), texts)


class CheckerPresentMixin:
    def setUp(self):
        if cai is None:
            self.fail(
                "check_adr_identity is not importable - the ADR identity "
                "contract has no implementation yet"
            )
        super().setUp()


class ResolveSupersedesTest(CheckerPresentMixin, unittest.TestCase):
    """Clause 3 - one `supersedes:` value resolves to exactly one ADR."""

    STEMS = [
        "0013-add-ca-pi-sibling-governance-plugin",
        "0014-githook-shim-dropin-fail-closed",
        "0014-pi-host-authentication-and-fail-closed-tool-boundary",
        "0015-all-live-git-enforcers-and-persistent-trusted-identity",
    ]

    def test_a_stem_resolves_to_itself(self):
        self.assertEqual(
            cai.resolve_supersedes(
                "0014-githook-shim-dropin-fail-closed", self.STEMS),
            "0014-githook-shim-dropin-fail-closed",
        )

    def test_the_other_stem_resolves_to_the_other_document(self):
        self.assertEqual(
            cai.resolve_supersedes(
                "0014-pi-host-authentication-and-fail-closed-tool-boundary",
                self.STEMS),
            "0014-pi-host-authentication-and-fail-closed-tool-boundary",
        )

    def test_an_unambiguous_bare_number_still_resolves(self):
        """Backward compatibility: 0009/0017/0018/0019 name a number today."""
        self.assertEqual(
            cai.resolve_supersedes("0013", self.STEMS),
            "0013-add-ca-pi-sibling-governance-plugin",
        )

    def test_an_ambiguous_bare_number_raises_instead_of_guessing(self):
        """THE defect: `0014` names two documents. Erroring is the fix."""
        with self.assertRaises(cai.AmbiguousADRReference) as caught:
            cai.resolve_supersedes("0014", self.STEMS)
        message = str(caught.exception)
        self.assertIn("0014-githook-shim-dropin-fail-closed", message)
        self.assertIn(
            "0014-pi-host-authentication-and-fail-closed-tool-boundary", message)

    def test_an_ambiguous_bare_number_never_returns_a_stem(self):
        """Guard against a 'helpful' fallback that picks the first match."""
        try:
            resolved = cai.resolve_supersedes("0014", self.STEMS)
        except cai.AmbiguousADRReference:
            return
        self.fail("ambiguous 0014 resolved to %r instead of erroring" % resolved)

    def test_none_resolves_to_no_predecessor(self):
        for spelling in ("none", "None", "  none  ", "", None):
            self.assertIsNone(cai.resolve_supersedes(spelling, self.STEMS),
                              "spelling %r" % (spelling,))

    def test_an_unknown_reference_raises(self):
        with self.assertRaises(cai.UnknownADRReference):
            cai.resolve_supersedes("0099", self.STEMS)
        with self.assertRaises(cai.UnknownADRReference):
            cai.resolve_supersedes("0014-no-such-slug", self.STEMS)


class UniquenessContractTest(CheckerPresentMixin, unittest.TestCase):
    """Clause 2 - a NEW file may not take an already-used ADR number."""

    def test_a_third_file_taking_the_grandfathered_number_is_rejected(self):
        stems = [
            "0014-githook-shim-dropin-fail-closed",
            "0014-pi-host-authentication-and-fail-closed-tool-boundary",
            "0014-a-third-decision-sneaking-in",
        ]
        errors = cai.identity_errors(stems, {})
        self.assertTrue(errors, "a third 0014 must violate the contract")
        self.assertTrue(any("0014" in e for e in errors), errors)

    def test_a_new_duplicate_of_an_unrelated_number_is_rejected(self):
        stems = ["0009-relicense-agplv3-dual-licensing",
                 "0009-a-second-decision-on-the-same-number"]
        errors = cai.identity_errors(stems, {})
        self.assertTrue(errors, "a duplicate 0009 must violate the contract")

    def test_the_historical_pair_alone_is_grandfathered(self):
        stems = ["0014-githook-shim-dropin-fail-closed",
                 "0014-pi-host-authentication-and-fail-closed-tool-boundary"]
        self.assertEqual(cai.identity_errors(stems, {}), [])

    def test_duplicate_stems_are_rejected(self):
        """Clause 1 stated as a contract, not left to the filesystem."""
        stems = ["0020-a-decision", "0020-a-decision"]
        errors = cai.identity_errors(stems, {})
        self.assertTrue(errors, "a duplicate stem must violate the contract")

    def test_an_ambiguous_supersedes_is_reported_not_resolved(self):
        stems = ["0014-githook-shim-dropin-fail-closed",
                 "0014-pi-host-authentication-and-fail-closed-tool-boundary",
                 "0015-later"]
        errors = cai.identity_errors(stems, {"0015-later": "0014"})
        self.assertTrue(errors, "an ambiguous supersedes must be an error")
        self.assertTrue(any("0015-later" in e for e in errors), errors)

    def test_a_disambiguated_supersedes_passes(self):
        stems = ["0014-githook-shim-dropin-fail-closed",
                 "0014-pi-host-authentication-and-fail-closed-tool-boundary",
                 "0015-later"]
        errors = cai.identity_errors(
            stems, {"0015-later": "0014-githook-shim-dropin-fail-closed"})
        self.assertEqual(errors, [])


class LiveRepositoryContractTest(CheckerPresentMixin, unittest.TestCase):
    """The contract applied to this repository's real decision record."""

    def test_this_repository_satisfies_the_adr_identity_contract(self):
        errors = cai.check(REPO)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_the_two_0014_files_are_both_still_present_and_distinct(self):
        """Pin the premise: the fix disambiguates, it does not delete or rename."""
        stems = cai.adr_stems(
            os.path.join(REPO, ".codearbiter", "decisions"))
        self.assertIn("0014-githook-shim-dropin-fail-closed", stems)
        self.assertIn(
            "0014-pi-host-authentication-and-fail-closed-tool-boundary", stems)

    def test_every_live_supersedes_names_exactly_one_predecessor(self):
        ddir = os.path.join(REPO, ".codearbiter", "decisions")
        stems = cai.adr_stems(ddir)
        for stem in stems:
            value = cai.read_supersedes(os.path.join(ddir, stem + ".md"))
            try:
                cai.resolve_supersedes(value, stems)
            except cai.ADRReferenceError as exc:
                self.fail("%s: supersedes: %r -> %s" % (stem, value, exc))


if __name__ == "__main__":
    unittest.main()
