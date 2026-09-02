#!/usr/bin/env python3
"""Unit and live tests for the canonical command-catalog guard."""

import unittest
from pathlib import Path

import check_command_catalog as catalog


REPO_ROOT = Path(__file__).resolve().parents[2]


class CommandCatalogGuardTest(unittest.TestCase):
    def test_exact_catalog_passes(self):
        self.assertEqual(
            catalog.consistency_errors({"feature", "task"}, {"feature", "task"}),
            [],
        )

    def test_missing_catalog_route_fails(self):
        errors = catalog.consistency_errors({"feature", "task"}, {"feature"})
        self.assertEqual(len(errors), 1)
        self.assertIn("task", errors[0])

    def test_extra_catalog_route_fails(self):
        errors = catalog.consistency_errors({"feature"}, {"feature", "task"})
        self.assertEqual(len(errors), 1)
        self.assertIn("task", errors[0])

    def test_live_generated_catalog_is_exact(self):
        self.assertEqual(catalog.check(REPO_ROOT), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
