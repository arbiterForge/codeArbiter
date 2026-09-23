"""Executable examples of the three contract boundaries; no provider calls."""
import csv
import io
import unittest
from export_csv import export_saved_searches

class TestExport(unittest.TestCase):
    def parse(self, records):
        result = export_saved_searches(records)
        self.assertIsInstance(result, str, "Non-empty searches must produce CSV text")
        return list(csv.reader(io.StringIO(result)))

    def test_rows(self):
        rows = self.parse([{"name": "Open", "query": "state:open"}, {"name": "Mine", "query": "owner:me"}])
        self.assertEqual(rows, [["name", "query"], ["Open", "state:open"], ["Mine", "owner:me"]])

    def test_round_trip(self):
        record = {"name": 'Commas, "quotes" and café', "query": "first\nsecond"}
        self.assertEqual(self.parse([record]), [["name", "query"], [record["name"], record["query"]]])

    def test_empty(self):
        self.assertIsNone(export_saved_searches([]))

if __name__ == "__main__":
    unittest.main()
