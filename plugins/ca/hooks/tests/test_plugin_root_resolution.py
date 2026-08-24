"""Fail-closed installed-adapter root resolution (ADR-0031).

The production mutation each test kills is named beside it.  The fixtures are
real, minimal plugin layouts; expected roots are hand-derived from each
fixture's ``hooks/`` directory rather than from resolver helpers.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest


HOOKS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS)))
CODEX_HOOKS = os.path.join(REPO, "plugins", "ca-codex", "hooks")

if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import hostapi


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _package(base, adapter="ca", version="1.2.3", manifest=None):
    """Create a hand-derived ``<root>/hooks/hostapi.py`` package layout."""
    root = os.path.join(base, "installed", adapter)
    _write(os.path.join(root, "hooks", "hostapi.py"), "# anchor\n")
    if manifest is not None:
        relpath, data = manifest
        _write(os.path.join(root, relpath), json.dumps(data))
    else:
        relpath = ".claude-plugin/plugin.json"
        _write(os.path.join(root, relpath), json.dumps({
            "name": adapter, "version": version,
        }))
    return root


def _load_codex_host():
    """Load the actual Codex seam without retaining another adapter's module."""
    old_path = list(sys.path)
    prior = sys.modules.pop("hostapi", None)
    sys.path.insert(0, CODEX_HOOKS)
    try:
        spec = importlib.util.spec_from_file_location(
            "codex_root_adapter_under_test", os.path.join(CODEX_HOOKS, "_host.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.HOST
    finally:
        sys.path[:] = old_path
        sys.modules.pop("hostapi", None)
        if prior is not None:
            sys.modules["hostapi"] = prior


class ResolverContractTests(unittest.TestCase):
    def test_codex_native_root_cannot_redirect_execution(self):
        # Mutation killed: returning PLUGIN_ROOT before the executing adapter's
        # root redirects a real hook into another valid-looking package.
        foreign = tempfile.TemporaryDirectory()
        old_native = os.environ.get("PLUGIN_ROOT")
        old_legacy = os.environ.get("CLAUDE_PLUGIN_ROOT")
        try:
            os.environ["PLUGIN_ROOT"] = foreign.name
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            with self.assertRaises(RuntimeError):
                _load_codex_host().plugin_root()
        finally:
            foreign.cleanup()
            if old_native is None:
                os.environ.pop("PLUGIN_ROOT", None)
            else:
                os.environ["PLUGIN_ROOT"] = old_native
            if old_legacy is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old_legacy

    def test_file_root_is_authoritative_when_no_optional_signal_is_set(self):
        # Mutation killed: consulting an unset/ambient value instead of the
        # executing module's package layout loses the valid installed root.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            got = hostapi.resolve_plugin_root(
                os.path.join(root, "hooks", "hostapi.py"),
                adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                anchor_relpath="hooks/hostapi.py", environment={},
            )
            self.assertEqual(got, os.path.realpath(root))

    def test_matching_signal_is_corroboration_not_a_redirect(self):
        # Mutation killed: rejecting a realpath-equivalent native signal.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            got = hostapi.resolve_plugin_root(
                os.path.join(root, "hooks", "hostapi.py"),
                adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                anchor_relpath="hooks/hostapi.py",
                environment={"CLAUDE_PLUGIN_ROOT": os.path.join(root, "hooks", "..")},
                signal_names=("CLAUDE_PLUGIN_ROOT",),
            )
            self.assertEqual(got, os.path.realpath(root))

    def test_mismatch_reports_both_root_signals_and_fails_closed(self):
        # Mutation killed: silently preferring either valid-looking root.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            foreign = _package(temporary, adapter="foreign")
            with self.assertRaises(hostapi.PluginRootError) as caught:
                hostapi.resolve_plugin_root(
                    os.path.join(root, "hooks", "hostapi.py"),
                    adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py",
                    environment={"CLAUDE_PLUGIN_ROOT": foreign},
                    signal_names=("CLAUDE_PLUGIN_ROOT",),
                )
            self.assertIn(os.path.realpath(root), str(caught.exception))
            self.assertIn(os.path.realpath(foreign), str(caught.exception))

    def test_traversal_manifest_path_is_rejected_before_it_can_escape(self):
        # Mutation killed: joining ../ paths lets a manifest outside the
        # adapter authenticate an untrusted directory.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    os.path.join(root, "hooks", "hostapi.py"),
                    adapter_name="ca", manifest_relpath="../plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )

    def test_symlinked_anchor_cannot_escape_the_adapter(self):
        # Mutation killed: lexical containment accepts hooks/hostapi.py when
        # the file is a symlink to an external anchor.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            external = os.path.join(temporary, "external-hostapi.py")
            _write(external, "# external\n")
            anchor = os.path.join(root, "hooks", "hostapi.py")
            os.remove(anchor)
            try:
                os.symlink(external, anchor)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    anchor, adapter_name="ca",
                    manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )

    def test_wrong_adapter_or_version_is_not_an_installed_adapter(self):
        # Mutation killed: accepting a manifest with another adapter identity
        # or an unparseable version as an authenticated package.
        with tempfile.TemporaryDirectory() as temporary:
            wrong_name = _package(temporary, adapter="wrong")
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    os.path.join(wrong_name, "hooks", "hostapi.py"),
                    adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )
            wrong_version = _package(temporary, adapter="ca-bad", version="not-a-version",
                                     manifest=(".claude-plugin/plugin.json",
                                               {"name": "ca", "version": "not-a-version"}))
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    os.path.join(wrong_version, "hooks", "hostapi.py"),
                    adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )

    def test_missing_manifest_or_anchor_is_not_accepted(self):
        # Mutation killed: treating file-relative parent directories as roots
        # even when the adapter boundary is incomplete.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary)
            os.remove(os.path.join(root, ".claude-plugin", "plugin.json"))
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    os.path.join(root, "hooks", "hostapi.py"),
                    adapter_name="ca", manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )
            root = _package(temporary, adapter="anchorless")
            os.remove(os.path.join(root, "hooks", "hostapi.py"))
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    os.path.join(root, "hooks", "hostapi.py"),
                    adapter_name="anchorless",
                    manifest_relpath=".claude-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py", environment={},
                )

    def test_codex_legacy_alias_is_matching_only_and_warns(self):
        # Mutation killed: making the legacy alias authoritative or silently
        # retaining it without the required non-disruptive diagnostic.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(
                temporary, adapter="ca-codex",
                manifest=(".codex-plugin/plugin.json",
                          {"name": "ca-codex", "version": "0.7.3"}),
            )
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                got = hostapi.resolve_plugin_root(
                    os.path.join(root, "hooks", "hostapi.py"),
                    adapter_name="ca-codex", manifest_relpath=".codex-plugin/plugin.json",
                    anchor_relpath="hooks/hostapi.py",
                    environment={"PLUGIN_ROOT": root, "CLAUDE_PLUGIN_ROOT": root},
                    signal_names=("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"),
                    required_signal_names=("PLUGIN_ROOT",),
                    legacy_signal_names=("CLAUDE_PLUGIN_ROOT",),
                )
            self.assertEqual(got, os.path.realpath(root))
            self.assertIn("CLAUDE_PLUGIN_ROOT is deprecated", err.getvalue())

    def test_required_native_signal_and_out_of_package_anchor_fail_closed(self):
        # Mutation killed: allowing a Codex hook without PLUGIN_ROOT, or an
        # arbitrary file outside the installed adapter, to claim a root.
        with tempfile.TemporaryDirectory() as temporary:
            root = _package(temporary, adapter="ca-codex",
                            manifest=(".codex-plugin/plugin.json",
                                      {"name": "ca-codex", "version": "0.7.3"}))
            kwargs = dict(
                adapter_name="ca-codex", manifest_relpath=".codex-plugin/plugin.json",
                anchor_relpath="hooks/hostapi.py", environment={},
                required_signal_names=("PLUGIN_ROOT",),
            )
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(os.path.join(root, "hooks", "hostapi.py"),
                                            **kwargs)
            outside = os.path.join(temporary, "outside", "hooks", "hostapi.py")
            _write(outside, "# outside\n")
            with self.assertRaises(hostapi.PluginRootError):
                hostapi.resolve_plugin_root(
                    outside, **dict(kwargs, environment={"PLUGIN_ROOT": root}))


if __name__ == "__main__":
    unittest.main()
