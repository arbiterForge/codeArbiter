"""MCP write-gap visibility (#270 / tribunal appsec-002).

MCP server tools (``mcp__<server>__<tool>``) escape every write-path guard:
on Claude they miss the ``Write``/``Edit`` matchers, and on Codex they
normalize to ``OTHER`` (no ``TOOL_MAP`` entry) so they match neither the
``apply_patch|Write|Edit`` write hooks nor the ``Bash`` exec hook. That gap is
ACCEPTED residual risk under ADR-0010 — these tests pin the *visibility* the
acceptance is conditioned on, not a default-deny.

The risk is carried by CONSUMERS: this repo is where codeArbiter is BUILT, so
a build-time check here would never fire. ``/ca:doctor`` is the surface that
lands in a consumer's own project, so the gap has to be reportable there.

Contract pinned here:
  * ``hostapi.Host.mcp_config_sources(project_root)`` is the host seam — each
    host answers where IT declares MCP servers. An empty list means the
    surface is unknown, and doctor must stay silent rather than guess.
  * ``doctor.check_mcp(host)`` WARNs when servers are configured, OKs when the
    host's sources are readable and declare none, and emits NOTHING when the
    configuration cannot be read.
  * The WARN reports a COUNT only. Server names, commands, and arguments are
    never echoed (#449: doctor output is already redaction-sensitive).

stdlib unittest only; no subprocess, no network, nothing written outside a
TemporaryDirectory.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_HOOKS_DIR, os.path.dirname(os.path.abspath(__file__))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor  # noqa: E402
import hostapi  # noqa: E402
import _hooklib  # noqa: E402


def _lines():
    return [line for _, line in doctor.results]


def _levels():
    return [lvl for lvl, _ in doctor.results]


@contextlib.contextmanager
def _env(**pairs):
    saved = {k: os.environ.get(k) for k in pairs}
    try:
        for k, v in pairs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _FakeHost:
    """A host whose MCP sources and project root are fully test-controlled."""

    name = "fake"

    def __init__(self, sources, root="."):
        self._sources = sources
        self._root = root

    def project_root(self, payload=None):
        return self._root

    def mcp_config_sources(self, project_root):
        return list(self._sources)


class HostSeamTest(unittest.TestCase):
    """The seam itself: each host answers for its OWN configuration surface."""

    def test_claude_default_declares_the_project_scoped_mcp_json(self):
        sources = hostapi.Host().mcp_config_sources(os.path.join("X", "proj"))
        paths = [p for p, _ in sources]
        self.assertIn(os.path.join("X", "proj", ".mcp.json"), paths)

    def test_claude_default_declares_the_mcpservers_key(self):
        sources = hostapi.Host().mcp_config_sources(os.path.join("X", "proj"))
        for path, key in sources:
            if path.endswith(".mcp.json"):
                self.assertEqual(key, "mcpServers")
                return
        self.fail(f"no .mcp.json source in {sources!r}")

    def test_claude_default_covers_the_user_scope_file(self):
        # `claude mcp add -s user` writes to ~/.claude.json, not the project
        # file — a check that reads only .mcp.json would report "none" on the
        # commonest real configuration.
        with tempfile.TemporaryDirectory() as home:
            with _env(HOME=home, USERPROFILE=home):
                paths = [p for p, _ in hostapi.Host().mcp_config_sources(home)]
            self.assertTrue(
                any(os.path.basename(p) == ".claude.json" for p in paths),
                f"user-scope ~/.claude.json missing from {paths!r}")

    def test_fail_closed_host_declares_no_sources(self):
        # Host identity is unknown, so no config path can be claimed; doctor
        # must degrade to silence rather than guess Claude's layout.
        self.assertEqual(hostapi.FailClosedHost().mcp_config_sources("."), [])


class CodexHostSeamTest(unittest.TestCase):
    """Loads the REAL ca-codex _host.py, as test_host_cmdref.py does."""

    @classmethod
    def setUpClass(cls):
        codex_hooks = os.path.abspath(os.path.join(
            _HOOKS_DIR, "..", "..", "ca-codex", "hooks"))
        cls.host = hostapi.load_host(codex_hooks)

    def test_codex_reads_its_own_config_toml_not_claudes(self):
        with tempfile.TemporaryDirectory() as codex_home:
            with _env(CODEX_HOME=codex_home):
                sources = self.host.mcp_config_sources(os.getcwd())
        paths = [p for p, _ in sources]
        self.assertEqual(paths, [os.path.join(codex_home, "config.toml")])

    def test_codex_declares_the_mcp_servers_key(self):
        with tempfile.TemporaryDirectory() as codex_home:
            with _env(CODEX_HOME=codex_home):
                sources = self.host.mcp_config_sources(os.getcwd())
        self.assertEqual([k for _, k in sources], ["mcp_servers"])

    def test_codex_falls_back_to_the_default_codex_home(self):
        with tempfile.TemporaryDirectory() as home:
            with _env(CODEX_HOME=None, HOME=home, USERPROFILE=home):
                sources = self.host.mcp_config_sources(os.getcwd())
        self.assertEqual([p for p, _ in sources],
                         [os.path.join(home, ".codex", "config.toml")])


class PiHostSeamTest(unittest.TestCase):
    """ca-pi's MCP configuration surface is not source-verified in this repo,
    so the Pi host must claim NO sources — inheriting Claude's ~/.claude.json
    would make doctor report another host's configuration as Pi's."""

    @classmethod
    def setUpClass(cls):
        pi_hooks = os.path.abspath(os.path.join(
            _HOOKS_DIR, "..", "..", "ca-pi", "hooks"))
        cls.host = hostapi.load_host(pi_hooks)

    def test_pi_declares_no_sources(self):
        self.assertEqual(self.host.name, "pi")
        self.assertEqual(self.host.mcp_config_sources(os.getcwd()), [])


class CheckMcpTest(unittest.TestCase):
    def setUp(self):
        doctor.results.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        doctor.results.clear()
        self.tmp.cleanup()

    def _write_mcp_json(self, doc):
        path = os.path.join(self.root, ".mcp.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f)
        return path

    def _host(self, *paths):
        return _FakeHost([(p, "mcpServers") for p in paths], self.root)

    def test_configured_servers_produce_a_warn(self):
        path = self._write_mcp_json(
            {"mcpServers": {"fs": {"command": "npx", "args": ["-y", "fs"]}}})
        doctor.check_mcp(self._host(path))
        self.assertIn("WARN", _levels(), f"expected a WARN; got {doctor.results!r}")

    def test_warn_names_the_write_gate_gap(self):
        path = self._write_mcp_json({"mcpServers": {"fs": {"command": "npx"}}})
        doctor.check_mcp(self._host(path))
        warns = [line for lvl, line in doctor.results if lvl == "WARN"]
        self.assertTrue(any("MCP" in line for line in warns), warns)
        self.assertTrue(any("write gate" in line for line in warns), warns)

    def test_warn_reports_a_count_never_the_server_names_or_args(self):
        # #449: doctor output is redaction-sensitive. Reporting only that MCP
        # tools are CONFIGURED keeps server identity and arguments out of the
        # transcript entirely.
        path = self._write_mcp_json({"mcpServers": {
            "acme-filesystem": {"command": "/opt/acme/mcp-fs",
                                "args": ["--root", "/srv/private"],
                                "env": {"ACME_TOKEN": "tok-abc123"}}}})
        doctor.check_mcp(self._host(path))
        blob = "\n".join(_lines())
        for leak in ("acme-filesystem", "/opt/acme/mcp-fs", "/srv/private",
                     "ACME_TOKEN", "tok-abc123"):
            self.assertNotIn(leak, blob, f"{leak!r} leaked into doctor output")
        self.assertIn("1 MCP server", blob)

    def test_two_sources_are_summed(self):
        a = self._write_mcp_json({"mcpServers": {"one": {}}})
        b = os.path.join(self.root, "user.json")
        with open(b, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"mcpServers": {"two": {}, "three": {}}}, f)
        doctor.check_mcp(self._host(a, b))
        warns = [line for lvl, line in doctor.results if lvl == "WARN"]
        self.assertTrue(any("3 MCP servers" in line for line in warns), warns)

    def test_project_scoped_servers_nested_under_projects_are_counted(self):
        # ~/.claude.json declares user-scope servers at the top level and
        # local-scope ones under projects.<path>.mcpServers; both bypass the
        # write gate, so both have to be seen.
        b = os.path.join(self.root, "user.json")
        with open(b, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"projects": {"/somewhere/else": {
                "mcpServers": {"nested": {}}}}}, f)
        doctor.check_mcp(self._host(b))
        self.assertIn("WARN", _levels(), f"got {doctor.results!r}")

    def test_no_servers_configured_is_ok_not_warn(self):
        path = self._write_mcp_json({"mcpServers": {}})
        doctor.check_mcp(self._host(path))
        self.assertEqual(_levels(), ["OK"], f"got {doctor.results!r}")

    def test_absent_config_file_is_ok_not_warn(self):
        doctor.check_mcp(self._host(os.path.join(self.root, "nope.json")))
        self.assertEqual(_levels(), ["OK"], f"got {doctor.results!r}")

    def test_unreadable_config_degrades_to_silence(self):
        # "A diagnostic that errors is worse than one that is quiet" —
        # /ca:doctor is the tool of last resort when enforcement misbehaves.
        path = os.path.join(self.root, ".mcp.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("{ not json at all ,,,")
        doctor.check_mcp(self._host(path))
        self.assertEqual(doctor.results, [], f"got {doctor.results!r}")

    def test_host_without_the_seam_degrades_to_silence(self):
        class _Ancient:
            def project_root(self, payload=None):
                return "."

        doctor.check_mcp(_Ancient())
        self.assertEqual(doctor.results, [], f"got {doctor.results!r}")

    def test_host_with_no_sources_degrades_to_silence(self):
        doctor.check_mcp(_FakeHost([], self.root))
        self.assertEqual(doctor.results, [], f"got {doctor.results!r}")

    def test_exploding_host_never_raises(self):
        class _Exploding:
            def project_root(self, payload=None):
                raise RuntimeError("boom")

            def mcp_config_sources(self, project_root):
                raise RuntimeError("boom")

        doctor.check_mcp(_Exploding())
        self.assertEqual(doctor.results, [])

    def test_oversize_config_degrades_to_silence(self):
        path = os.path.join(self.root, ".mcp.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("x" * (doctor.MCP_CONFIG_MAX_BYTES + 1))
        doctor.check_mcp(self._host(path))
        self.assertEqual(doctor.results, [], f"got {doctor.results!r}")

    @unittest.skipIf(sys.version_info < (3, 11), "tomllib is 3.11+")
    def test_toml_sources_are_counted(self):
        path = os.path.join(self.root, "config.toml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write('[mcp_servers.fs]\ncommand = "npx"\n'
                    '[mcp_servers.db]\ncommand = "uvx"\n')
        doctor.check_mcp(_FakeHost([(path, "mcp_servers")], self.root))
        warns = [line for lvl, line in doctor.results if lvl == "WARN"]
        self.assertTrue(any("2 MCP servers" in line for line in warns),
                        doctor.results)

    def test_malformed_toml_degrades_to_silence(self):
        path = os.path.join(self.root, "config.toml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("[mcp_servers.fs\ncommand = ")
        doctor.check_mcp(_FakeHost([(path, "mcp_servers")], self.root))
        self.assertEqual(doctor.results, [], f"got {doctor.results!r}")


class MainWiringTest(unittest.TestCase):
    """The check has to be WIRED into the report, not merely importable."""

    def setUp(self):
        doctor.results.clear()
        _hooklib.reset_host()

    def tearDown(self):
        doctor.results.clear()
        _hooklib.reset_host()

    def test_main_runs_the_mcp_check(self):
        seen = []
        original = doctor.check_mcp
        doctor.check_mcp = lambda host: seen.append(host)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    doctor.run(hostapi.Host())
                except SystemExit:
                    pass
        finally:
            doctor.check_mcp = original
        self.assertEqual(len(seen), 1, "main() never called check_mcp")


if __name__ == "__main__":
    unittest.main()
