"""_configlib unit tests — registry schema, resolution precedence, validation,
settings.json round-trips, and doctor. Temp-dir settings files throughout;
nothing touches the real ~/.claude."""

import json
import os
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HOOKS_DIR)
import _configlib  # noqa: E402


def _paths(tmp):
    return {
        "user": os.path.join(tmp, "user", "settings.json"),
        "project": os.path.join(tmp, "proj", ".claude", "settings.json"),
        "local": os.path.join(tmp, "proj", ".claude", "settings.local.json"),
    }


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


REG = _configlib.load_registry()
BY_NAME = _configlib.entries_by_name(REG)


class TestRegistry(unittest.TestCase):
    def test_shipped_registry_is_valid(self):
        # load_registry already schema-validates; loading without raising IS
        # the assertion. Sanity-check breadth on top.
        self.assertGreaterEqual(len(REG["settings"]), 50)
        self.assertIn("prune", REG["groups"])

    def test_every_entry_names_a_known_group_and_type(self):
        for e in REG["settings"]:
            self.assertIn(e["group"], REG["groups"], e["name"])
            self.assertIn(e["type"], _configlib.VALID_TYPES, e["name"])
            self.assertTrue(e["description"].strip(), e["name"])

    def test_requires_reference_registered_names(self):
        for e in REG["settings"]:
            for dep in (e.get("requires") or {}):
                self.assertIn(dep, BY_NAME, "%s requires unknown %s" % (e["name"], dep))

    def test_sensitive_inventory(self):
        sensitive = {e["name"] for e in REG["settings"] if e.get("sensitive")}
        self.assertEqual(sensitive, {"FARM_API_KEY"})

    def test_malformed_registry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "registry.json")
            bad = {"version": 1, "groups": {"g": "x"},
                   "settings": [{"name": "A", "group": "g", "type": "enum",
                                 "values": ["a"], "default": "a", "description": "d"}]}
            _write(p, bad)  # enum with <2 values
            with self.assertRaises(_configlib.RegistryError):
                _configlib.load_registry(p)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.entry = BY_NAME["CODEARBITER_BABYSIT"]

    def test_default_when_nothing_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _configlib.resolve(self.entry, {}, _configlib.env_layers(_paths(tmp)))
            self.assertEqual((r["effective"], r["source"]), ("off", "default"))
            self.assertFalse(r["pending"])

    def test_layer_precedence_local_over_project_over_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["user"], {"env": {"CODEARBITER_BABYSIT": "off"}})
            _write(paths["project"], {"env": {"CODEARBITER_BABYSIT": "on"}})
            layers = _configlib.env_layers(paths)
            r = _configlib.resolve(self.entry, {}, layers)
            self.assertEqual((r["effective"], r["source"]), ("on", "project"))
            _write(paths["local"], {"env": {"CODEARBITER_BABYSIT": "off"}})
            r = _configlib.resolve(self.entry, {}, _configlib.env_layers(paths))
            self.assertEqual((r["effective"], r["source"]), ("off", "local"))

    def test_session_env_is_ground_truth_and_flags_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["user"], {"env": {"CODEARBITER_BABYSIT": "on"}})
            r = _configlib.resolve(self.entry, {"CODEARBITER_BABYSIT": "off"},
                                   _configlib.env_layers(paths))
            self.assertEqual((r["effective"], r["source"]), ("off", "session"))
            self.assertTrue(r["pending"])

    def test_agreeing_session_and_settings_is_not_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["user"], {"env": {"CODEARBITER_BABYSIT": "on"}})
            r = _configlib.resolve(self.entry, {"CODEARBITER_BABYSIT": "on"},
                                   _configlib.env_layers(paths))
            self.assertFalse(r["pending"])


class TestValidate(unittest.TestCase):
    def _v(self, name, raw):
        return _configlib.validate(BY_NAME[name], raw)

    def test_enum_normalizes_case_and_rejects_unknown(self):
        self.assertEqual(self._v("CODEARBITER_PRUNE", "DRY"), (True, "dry", None))
        ok, _, msg = self._v("CODEARBITER_PRUNE", "sideways")
        self.assertFalse(ok)
        self.assertIn("off, dry, on", msg)

    def test_bool_canonicalizes_to_1_0(self):
        for raw in ("on", "TRUE", "1", "yes"):
            self.assertEqual(self._v("CODEARBITER_DEV", raw)[1], "1")
        for raw in ("off", "false", "0", "no"):
            self.assertEqual(self._v("CODEARBITER_DEV", raw)[1], "0")
        self.assertFalse(self._v("CODEARBITER_DEV", "maybe")[0])

    def test_int_bounds(self):
        self.assertEqual(self._v("CODEARBITER_PRUNE_KEEP_RECENT", "5"), (True, "5", None))
        self.assertFalse(self._v("CODEARBITER_PRUNE_KEEP_RECENT", "0")[0])   # min 1
        self.assertFalse(self._v("CODEARBITER_PRUNE_KEEP_RECENT", "ten")[0])

    def test_float_bounds(self):
        self.assertEqual(self._v("CODEARBITER_COMPACT_AT", "88.5"), (True, "88.5", None))
        self.assertFalse(self._v("CODEARBITER_COMPACT_AT", "101")[0])  # max 100

    def test_empty_value_points_at_unset(self):
        ok, _, msg = self._v("CODEARBITER_PRUNE", "  ")
        self.assertFalse(ok)
        self.assertIn("unset", msg)


class TestSetUnset(unittest.TestCase):
    def test_round_trip_creates_file_and_env_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            rep = _configlib.set_value(REG, "CODEARBITER_BABYSIT", "on", "user", paths, environ={})
            self.assertTrue(rep["changed"])
            self.assertIsNone(rep["prior"])
            with open(paths["user"], encoding="utf-8") as f:
                self.assertEqual(json.load(f)["env"]["CODEARBITER_BABYSIT"], "on")
            rep = _configlib.unset_value(REG, "CODEARBITER_BABYSIT", "user", paths)
            self.assertEqual(rep["prior"], "on")
            with open(paths["user"], encoding="utf-8") as f:
                self.assertNotIn("env", json.load(f))  # empty env dict dropped

    def test_set_preserves_unrelated_settings_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["user"], {"model": "opus", "env": {"OTHER": "1"}})
            _configlib.set_value(REG, "CODEARBITER_BABYSIT", "on", "user", paths, environ={})
            with open(paths["user"], encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["model"], "opus")
            self.assertEqual(data["env"]["OTHER"], "1")

    def test_no_change_write_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _configlib.set_value(REG, "CODEARBITER_BABYSIT", "on", "user", paths, environ={})
            before = os.stat(paths["user"]).st_mtime_ns
            rep = _configlib.set_value(REG, "CODEARBITER_BABYSIT", "on", "user", paths, environ={})
            self.assertFalse(rep["changed"])
            self.assertEqual(os.stat(paths["user"]).st_mtime_ns, before)

    def test_refuses_unparseable_settings_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            os.makedirs(os.path.dirname(paths["user"]), exist_ok=True)
            with open(paths["user"], "w", encoding="utf-8") as f:
                f.write("{not json")
            with self.assertRaises(SystemExit) as cm:
                _configlib.set_value(REG, "CODEARBITER_BABYSIT", "on", "user", paths, environ={})
            self.assertIn("REFUSING TO WRITE", str(cm.exception))

    def test_refuses_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                _configlib.set_value(REG, "FARM_API_KEY", "sk-x", "user", _paths(tmp), environ={})
            self.assertIn("sensitive", str(cm.exception))
            self.assertFalse(os.path.exists(_paths(tmp)["user"]))

    def test_unknown_key_suggests_closest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                _configlib.set_value(REG, "CODEARBITER_BABYSITT", "on", "user", _paths(tmp), environ={})
            self.assertIn("CODEARBITER_BABYSIT", str(cm.exception))

    def test_invalid_value_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                _configlib.set_value(REG, "CODEARBITER_PRUNE", "sideways", "user", _paths(tmp), environ={})

    def test_requires_note_when_prerequisite_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            rep = _configlib.set_value(REG, "CODEARBITER_PRUNE_TIER", "standard", "user",
                                       _paths(tmp), environ={})
            self.assertIn("CODEARBITER_PRUNE", rep["warning"])

    def test_requires_note_absent_when_prerequisite_met(self):
        with tempfile.TemporaryDirectory() as tmp:
            rep = _configlib.set_value(REG, "CODEARBITER_PRUNE_TIER", "standard", "user",
                                       _paths(tmp), environ={"CODEARBITER_PRUNE": "on"})
            self.assertIsNone(rep["warning"])


class TestDoctor(unittest.TestCase):
    def test_healthy_when_nothing_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_configlib.doctor(REG, {}, _paths(tmp)), [])

    def test_flags_typo_with_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = _configlib.doctor(REG, {"CODEARBITER_PRUNE_TEIR": "gentle"}, _paths(tmp))
            self.assertEqual(len(findings), 1)
            self.assertIn("CODEARBITER_PRUNE_TIER", findings[0]["message"])

    def test_flags_invalid_value_in_settings_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["project"], {"env": {"CODEARBITER_COMPACT_AT": "lots"}})
            findings = _configlib.doctor(REG, {}, paths)
            self.assertTrue(any(f["level"] == "error" for f in findings))

    def test_flags_persisted_sensitive_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            _write(paths["user"], {"env": {"FARM_API_KEY": "sk-x"}})
            findings = _configlib.doctor(REG, {}, paths)
            self.assertTrue(any("sensitive" in f["message"] for f in findings))

    def test_internal_farm_vars_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = _configlib.doctor(REG, {"FARM_MUTATION_FILES": "a.py"}, _paths(tmp))
            self.assertEqual(findings, [])


class TestSnapshot(unittest.TestCase):
    def test_sensitive_effective_is_masked(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = _configlib.snapshot(REG, {"FARM_API_KEY": "sk-secret"}, _paths(tmp))
            rec = [r for r in recs if r["name"] == "FARM_API_KEY"][0]
            self.assertEqual(rec["effective"], "********")
            self.assertNotIn("sk-secret", json.dumps(recs))

    def test_group_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = _configlib.snapshot(REG, {}, _paths(tmp), group="babysit")
            self.assertEqual({r["group"] for r in recs}, {"babysit"})


if __name__ == "__main__":
    unittest.main()
