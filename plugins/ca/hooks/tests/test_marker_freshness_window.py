"""Issue #567: the H-11 authoring-marker freshness window used to be five
independent hardcoded `30` literals (pre-write.py, pre-edit.py,
_bashguardlib.py, git-enforce.py, _protectedstatelib.py) with no import
relationship and no test asserting they agreed. A mutation campaign showed
`MARKER_FRESHNESS_MINUTES = 1000` passing the whole suite, because the
freshness tests computed their expected ages FROM the implementation
constant rather than pinning a literal — the widening drift was invisible.

`_hooklib.MARKER_FRESHNESS_MINUTES` is now the single declaration; every
flank imports it. This file pins TWO independent properties, because either
alone is gameable:

  1. Every flank's imported name resolves to the SAME VALUE as
     `_hooklib.MARKER_FRESHNESS_MINUTES` (catches a flank importing the
     right name from the WRONG place, or re-declaring it under the same
     name with a different value).
  2. Every flank's `marker_fresh(...)` call site passes the CONSTANT NAME as
     its second argument, not a literal (catches a flank that still imports
     the constant but quietly reintroduces `marker_fresh(marker, 30)` at the
     call site — property 1 alone cannot see this, since the imported name
     would still resolve correctly even though it goes unused there).

Property 2 is checked by parsing each flank's SOURCE with `ast`, not by
running the flank and observing behavior: a literal `30` and the imported
`MARKER_FRESHNESS_MINUTES` (== 30 today) are behaviorally identical, so no
runtime assertion can tell them apart. Only reading what the call site
actually WROTE can.
"""
import ast
import importlib.util as _ilu
import os
import sys
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)
import _hooklib  # noqa: E402
import _bashguardlib  # noqa: E402
import _protectedstatelib  # noqa: E402

PRE_WRITE = os.path.join(HOOKS, "pre-write.py")
PRE_EDIT = os.path.join(HOOKS, "pre-edit.py")
GIT_ENFORCE = os.path.join(HOOKS, "git-enforce.py")

# The five flanks issue #567 named, each paired with the source file that
# carries its `marker_fresh(...)` call site.
FLANK_SOURCE_PATHS = {
    "pre-write.py": PRE_WRITE,
    "pre-edit.py": PRE_EDIT,
    "_bashguardlib.py": os.path.join(HOOKS, "_bashguardlib.py"),
    "git-enforce.py": GIT_ENFORCE,
}


def _load(path, name):
    """Load a (possibly hyphenated) hook script as an in-process module,
    mirroring test_pre_write.py's `_load_pre_write` pattern. Each caller
    supplies a distinct `name` so concurrently-loaded flanks never collide
    in `sys.modules`."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MarkerFreshnessSingleSourceValueTest(unittest.TestCase):
    """Every flank's imported `MARKER_FRESHNESS_MINUTES` resolves to
    `_hooklib`'s value — the single-source property, checked by VALUE."""

    def test_hooklib_declares_the_canonical_thirty_minute_window(self):
        # A direct value pin: if this drifts, every assertion below moves
        # with it, which is the single-source property working as intended
        # rather than a test that silently stopped checking anything.
        self.assertEqual(_hooklib.MARKER_FRESHNESS_MINUTES, 30)

    def test_protectedstatelib_reexports_the_same_object(self):
        self.assertEqual(
            _protectedstatelib.MARKER_FRESHNESS_MINUTES,
            _hooklib.MARKER_FRESHNESS_MINUTES)

    def test_bashguardlib_module_namespace_resolves_the_same_value(self):
        # _bashguardlib imports MARKER_FRESHNESS_MINUTES into its own module
        # namespace (`from _hooklib import (..., MARKER_FRESHNESS_MINUTES,
        # ...)`), so it is reachable as an attribute of the loaded module —
        # exactly the shape a reintroduced independent declaration would
        # also satisfy, which is why this alone is not sufficient (see the
        # AST test below for the property this one cannot see).
        self.assertEqual(
            _bashguardlib.MARKER_FRESHNESS_MINUTES,
            _hooklib.MARKER_FRESHNESS_MINUTES)

    def test_pre_write_module_namespace_resolves_the_same_value(self):
        mod = _load(PRE_WRITE, "marker_freshness_test_pre_write")
        self.assertEqual(
            mod.MARKER_FRESHNESS_MINUTES, _hooklib.MARKER_FRESHNESS_MINUTES)

    def test_pre_edit_module_namespace_resolves_the_same_value(self):
        mod = _load(PRE_EDIT, "marker_freshness_test_pre_edit")
        self.assertEqual(
            mod.MARKER_FRESHNESS_MINUTES, _hooklib.MARKER_FRESHNESS_MINUTES)

    def test_git_enforce_module_namespace_resolves_the_same_value(self):
        mod = _load(GIT_ENFORCE, "marker_freshness_test_git_enforce")
        self.assertEqual(
            mod.MARKER_FRESHNESS_MINUTES, _hooklib.MARKER_FRESHNESS_MINUTES)


def _marker_fresh_second_args(path):
    """Parse `path` and return the AST node for the second argument of every
    top-level-reachable `marker_fresh(...)` call in it (a list, since a
    source file may call it more than once)."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    args = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "marker_fresh"
                and len(node.args) >= 2):
            args.append(node.args[1])
    return args


class MarkerFreshnessNoReintroducedLiteralTest(unittest.TestCase):
    """A flank could import `MARKER_FRESHNESS_MINUTES` correctly (satisfying
    the tests above) and STILL pass a hardcoded `30` at its own
    `marker_fresh(marker, 30)` call site — the constant would sit unused,
    imported but ignored. This is exactly the shape a future edit could
    reintroduce by accident (e.g. a copy-pasted call site from before this
    fix). Only reading the call site's actual source distinguishes it from
    the fixed form, since both evaluate to the identical int today."""

    def test_every_flank_passes_the_named_constant_not_a_literal(self):
        for label, path in FLANK_SOURCE_PATHS.items():
            with self.subTest(flank=label):
                call_args = _marker_fresh_second_args(path)
                self.assertTrue(
                    call_args,
                    f"{label} calls marker_fresh(...) at least once in the "
                    f"H-11/H-09b/H-10b guard this test covers; none found — "
                    f"has the call site moved or been renamed?")
                for arg in call_args:
                    self.assertIsInstance(
                        arg, ast.Name,
                        f"{label}'s marker_fresh(...) second argument is "
                        f"not a bare name (it is {ast.dump(arg)!r}) — issue "
                        f"#567 requires every flank to resolve the window "
                        f"by import, not restate it as a literal")
                    self.assertEqual(
                        arg.id, "MARKER_FRESHNESS_MINUTES",
                        f"{label}'s marker_fresh(...) second argument is "
                        f"the name {arg.id!r}, not MARKER_FRESHNESS_MINUTES "
                        f"— issue #567's single-source constant")

    def test_protectedstatelib_default_parameter_is_also_the_named_constant(self):
        # _protectedstatelib.marker_gated_write_admitted's `minutes=` default
        # is the fifth site issue #567 named — a *default parameter value*,
        # not a `marker_fresh(...)` call argument, so it needs its own AST
        # check rather than reusing `_marker_fresh_second_args`.
        path = os.path.join(HOOKS, "_protectedstatelib.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "marker_gated_write_admitted":
                found = True
                defaults = node.args.defaults
                self.assertTrue(defaults, "marker_gated_write_admitted has no default args")
                default = defaults[-1]  # `minutes` is the last positional-or-keyword param
                self.assertIsInstance(
                    default, ast.Name,
                    f"marker_gated_write_admitted's `minutes` default is not a bare "
                    f"name (it is {ast.dump(default)!r})")
                self.assertEqual(default.id, "MARKER_FRESHNESS_MINUTES")
        self.assertTrue(found, "marker_gated_write_admitted not found in _protectedstatelib.py")


if __name__ == "__main__":
    unittest.main()
