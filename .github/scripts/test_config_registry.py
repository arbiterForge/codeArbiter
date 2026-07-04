"""Registry anti-drift gate — config/registry.json vs the code.

Three guarantees, so the registry stays the single source of truth instead of
one more copy that rots:

  1. COVERAGE — every plugin-prefixed env var (CODEARBITER_* / FARM_* /
     CA_SANDBOX_*) referenced in shipped code is registered. A new knob added
     without a registry entry fails CI here.
  2. PYTHON DEFAULTS — the values the hooks actually resolve with an empty
     environment (injectable from_env/babysit_config, plus regex-extracted
     inline literals) equal the registry's declared defaults.
  3. TS DEFAULTS — the numEnv(...) / `process.env.X ?? <literal>` defaults in
     farm.ts, mutation.ts, and the ca-sandbox tools equal the registry's.

Comparison rules: an empty-string inline default is a normalize-later
sentinel, not a real default — skipped. SENTINEL_UNSET maps code sentinels
that mean "unset" (e.g. FARM_MAX_TOKENS=0 -> provider default) to registry
default null. Identifier right-hand sides are skipped by extraction, but the
one that matters (DEFAULT_API_BASE_URL) is asserted directly.
"""

import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOKS = os.path.join(ROOT, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _babysitlib  # noqa: E402
import _configlib  # noqa: E402
import _prunelib  # noqa: E402

REG = _configlib.load_registry(os.path.join(ROOT, "plugins", "ca", "config", "registry.json"))
BY_NAME = _configlib.entries_by_name(REG)

# The trailing [A-Z0-9] keeps prose wildcards like "FARM_MUTATION_*" from
# matching as a bare "FARM_MUTATION_".
NAME_RE = re.compile(r"\b((?:CODEARBITER|FARM|CA_SANDBOX)_[A-Z0-9_]*[A-Z0-9])\b")

# Env vars the plugin injects into its own subprocesses — real, but never
# user-set, so they are deliberately not registry entries.
EXEMPT = _configlib.KNOWN_INTERNAL

# Code sentinels that mean "unset / provider default", paired with a registry
# default of null.
SENTINEL_UNSET = {"FARM_MAX_TOKENS": 0.0}


def _code_files():
    out = []
    for fname in os.listdir(HOOKS):
        if fname.endswith(".py"):
            out.append(os.path.join(HOOKS, fname))
    for d in (os.path.join(ROOT, "plugins", "ca", "tools"),
              os.path.join(ROOT, "plugins", "ca-sandbox", "tools")):
        for fname in os.listdir(d):
            if fname.endswith(".ts") and ".test." not in fname:
                out.append(os.path.join(d, fname))
    return out


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _eval_num(expr):
    """Evaluate a numeric literal expression a default may be written as:
    120_000, 1 << 20, 1024 * 1024, 5 * 60_000, 0.5. Anything else -> None."""
    s = expr.replace("_", "").strip()
    if not re.fullmatch(r"[0-9.\s*+<>()]+", s):
        return None
    try:
        return float(eval(s))  # noqa: S307 — input shape guarded by the regex above
    except Exception:  # noqa: BLE001
        return None


# (name, value) extraction — value is str, float, or None (explicit null).
_PY_STR = re.compile(r"""\.get\(\s*"((?:CODEARBITER|FARM|CA_SANDBOX)_[A-Z0-9_]+)"\s*,\s*"([^"]*)"\s*\)""")
_PY_OR_STR = re.compile(r"""\.get\(\s*"((?:CODEARBITER|FARM|CA_SANDBOX)_[A-Z0-9_]+)"\s*\)\s*or\s*"([^"]+)\"""")
_PY_NUM = re.compile(r"""num\(\s*"((?:CODEARBITER|FARM|CA_SANDBOX)_[A-Z0-9_]+)"\s*,\s*([0-9_.\s<]+?)\s*\)""")
_PY_COMPACT_AT = re.compile(r"""\.get\("CODEARBITER_COMPACT_AT"\)\s*,\s*([0-9.]+)\s*\)""")
_TS_NUMENV = re.compile(r"""numEnv\(\s*"([A-Z0-9_]+)"\s*,\s*([0-9_.]+)""")
# Numeric branch must START with a digit so an identifier RHS (e.g.
# `?? DEFAULT_API_BASE_URL`) is skipped instead of matched as whitespace.
_TS_NULLISH = re.compile(r"""process\.env\.([A-Z0-9_]+)\s*\?\?\s*(null|"[^"]*"|\d[\d_.\s*+]*)""")


def _extract_defaults(text, is_ts):
    found = []
    if is_ts:
        for name, num in _TS_NUMENV.findall(text):
            found.append((name, _eval_num(num)))
        for name, rhs in _TS_NULLISH.findall(text):
            rhs = rhs.strip()
            if rhs == "null":
                found.append((name, None))
            elif rhs.startswith('"'):
                found.append((name, rhs[1:-1]))
            else:
                found.append((name, _eval_num(rhs)))
    else:
        for name, val in _PY_STR.findall(text) + _PY_OR_STR.findall(text):
            found.append((name, val))
        for name, num in _PY_NUM.findall(text):
            found.append((name, _eval_num(num)))
        for num in _PY_COMPACT_AT.findall(text):
            found.append(("CODEARBITER_COMPACT_AT", _eval_num(num)))
    return [(n, v) for n, v in found if n.startswith(("CODEARBITER_", "FARM_", "CA_SANDBOX_"))]


def _assert_matches(tc, name, code_value, where):
    entry = BY_NAME.get(name)
    tc.assertIsNotNone(entry, "%s (%s) is not in the registry" % (name, where))
    if isinstance(code_value, str) and code_value == "":
        return  # normalize-later sentinel, not a default
    reg_default = _configlib.default_str(entry)
    if reg_default is None:
        if code_value is None:
            return
        tc.assertEqual(SENTINEL_UNSET.get(name), code_value,
                       "%s: code default %r but registry says unset (%s)" % (name, code_value, where))
        return
    if entry["type"] in ("int", "float"):
        tc.assertIsNotNone(code_value, "%s: registry default %s but code has none (%s)" % (name, reg_default, where))
        tc.assertEqual(float(reg_default), float(code_value),
                       "%s: registry %s != code %s (%s)" % (name, reg_default, code_value, where))
    else:
        tc.assertEqual(reg_default, str(code_value),
                       "%s: registry %r != code %r (%s)" % (name, reg_default, code_value, where))


class TestCoverage(unittest.TestCase):
    def test_every_referenced_var_is_registered(self):
        missing = {}
        for path in _code_files():
            for name in set(NAME_RE.findall(_read(path))):
                if name not in BY_NAME and name not in EXEMPT:
                    missing.setdefault(name, os.path.relpath(path, ROOT))
        self.assertEqual(missing, {},
                         "unregistered env vars found in code — add them to "
                         "plugins/ca/config/registry.json (or the exempt list "
                         "in _configlib.KNOWN_INTERNAL if plugin-internal)")

    def test_every_registered_var_appears_in_code(self):
        # The registry must not accumulate ghosts either: a renamed/removed
        # knob's entry has to go.
        referenced = set()
        for path in _code_files():
            referenced.update(NAME_RE.findall(_read(path)))
        ghosts = sorted(set(BY_NAME) - referenced)
        self.assertEqual(ghosts, [], "registry entries no shipped code reads")


class TestPythonDefaults(unittest.TestCase):
    def test_prune_config_from_empty_env(self):
        cfg = _prunelib.Config.from_env({})
        for var, actual in [
            ("CODEARBITER_PRUNE_TIER", cfg.tier),
            ("CODEARBITER_PRUNE_MAXBYTES", cfg.max_bytes),
            ("CODEARBITER_PRUNE_KEEP_RECENT", cfg.keep_recent),
            ("CODEARBITER_PRUNE_MIN_SIZE", cfg.min_size),
            ("CODEARBITER_PRUNE_MIN_GROWTH", cfg.min_growth),
            ("CODEARBITER_PRUNE_BACKUPS", cfg.backups),
            ("CODEARBITER_PRUNE_LIVE_SECS", cfg.live_secs),
        ]:
            _assert_matches(self, var, float(actual) if isinstance(actual, int) else actual,
                            "_prunelib.Config.from_env({})")

    def test_babysit_resolves_off_and_propose_from_empty_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _babysitlib.babysit_config({}, tmp, arbiter_active=lambda r: True)
        self.assertFalse(cfg["enabled"], "CODEARBITER_BABYSIT must default off")
        self.assertEqual(cfg["on_red"], _configlib.default_str(BY_NAME["CODEARBITER_BABYSIT_ONRED"]))

    def test_inline_python_literals_match_registry(self):
        for fname in os.listdir(HOOKS):
            if not fname.endswith(".py"):
                continue
            for name, value in _extract_defaults(_read(os.path.join(HOOKS, fname)), is_ts=False):
                _assert_matches(self, name, value, fname)


class TestTsDefaults(unittest.TestCase):
    def test_ts_literals_match_registry(self):
        for path in _code_files():
            if not path.endswith(".ts"):
                continue
            for name, value in _extract_defaults(_read(path), is_ts=True):
                _assert_matches(self, name, value, os.path.relpath(path, ROOT))

    def test_farm_default_endpoint_constant(self):
        text = _read(os.path.join(ROOT, "plugins", "ca", "tools", "farm.ts"))
        m = re.search(r'DEFAULT_API_BASE_URL = "([^"]+)"', text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1),
                         _configlib.default_str(BY_NAME["FARM_DEFAULT_API_BASE_URL"]))

    def test_extraction_is_not_silently_empty(self):
        # If a refactor changes the env-read idiom, the regexes must fail loud
        # here rather than quietly asserting nothing.
        total = 0
        for path in _code_files():
            if path.endswith(".ts"):
                total += len(_extract_defaults(_read(path), is_ts=True))
        self.assertGreaterEqual(total, 20, "TS default extraction collapsed — update the regexes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
