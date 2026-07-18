#!/usr/bin/env python3
"""Acceptance tests for descriptor-driven governance-host generation.

Run: python .github/scripts/test_host_descriptors.py

PI-AC-01..04 cover the canonical three-host registry, strict schema,
idempotent generation, byte-identical shared Python, canonical role charters,
and the absence of a handwritten Pi governance surface.
"""
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DESCRIPTORS_TOOL = REPO / "tools" / "host_descriptors.py"

_MARKER = re.compile(r"\{\{(IF:([a-z][a-z0-9-]*)|ELSE|END)\}\}")
_COMMAND = re.compile(r"\{\{CMD:([a-z][a-z0-9-]*)\}\}")
_COMMAND_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/commands/([a-z0-9-]+)\.md")
_SKILLS_PATH = re.compile(r"\{\{PLUGIN_ROOT\}\}/skills/(?!ca-)")
_PI_ONLY_AGENT_FRONTMATTER = re.compile(
    r"^(?:classification|pi-skills):[^\n]*\n", re.MULTILINE
)

# Exact non-policy artifact classes admitted at the Task 1 boundary. Built
# extension artifacts are intentionally empty until a later task defines and
# validates concrete output paths; no tools/** or dist/** prefix is trusted.
_PI_OPTIONAL_ARTIFACTS = frozenset({
    "hooks/_host.py",
    "hooks/pi-bridge.py",
    "package.json",
})
_PI_BUILT_EXTENSION_ARTIFACTS = frozenset()

_TASK_2_NON_POLICY_ARTIFACTS = frozenset({
    "CHANGELOG.md",
    "package.json",
    "extensions/codearbiter.js",
    "extensions/codearbiter-child.js",
    "tools/build.mjs",
    "tools/package.json",
    "tools/package-lock.json",
    "tools/tsconfig.json",
    "tools/vitest.config.ts",
    "tools/src/pi-api.d.ts",
    "tools/src/extension.ts",
    "tools/src/child-extension.ts",
    "tools/src/compatibility.ts",
    "tools/src/runtime-resolver.ts",
    "tools/test/package.test.ts",
})

_TASK_3_NON_POLICY_ARTIFACTS = frozenset({
    "tools/src/activation.ts",
    "tools/src/commands.ts",
    "tools/src/contracts.ts",
    "tools/src/status.ts",
    "tools/test/activation.test.ts",
    "tools/test/commands.test.ts",
    "tools/test/status.test.ts",
})

_TASK_4_NON_POLICY_ARTIFACTS = frozenset({
    "tools/src/bridge.ts",
    "tools/src/redaction.ts",
    "tools/src/tool-guard.ts",
    "tools/test/bridge.test.ts",
    "tools/test/tool-guard.test.ts",
})

_TASK_5_NON_POLICY_ARTIFACTS = frozenset({
    "tools/src/doctor.ts",
    "tools/src/notices.ts",
    "tools/test/doctor.test.ts",
    "tools/test/notices.test.ts",
})

# Exact implementation and test artifacts approved by Tasks 6 through 10.
# Keep these path-exact: an unlisted file under tools/ must still fail closed.
_TASK_6_THROUGH_10_NON_POLICY_ARTIFACTS = frozenset({
    "generated/roles.json",
    "helpers/windows-supervisor.js",
    "tools/src/attestation.ts",
    "tools/src/child-env.ts",
    "tools/src/compaction.ts",
    "tools/src/dispatch.ts",
    "tools/src/farm.ts",
    "tools/src/process-tree.ts",
    "tools/src/roles.ts",
    "tools/src/runner.ts",
    "tools/src/windows-supervisor.ts",
    "tools/test/child-env.test.ts",
    "tools/test/compaction.test.ts",
    "tools/test/dispatch.test.ts",
    "tools/test/farm.test.ts",
    "tools/test/final-arguments.test.ts",
    "tools/test/fixtures/pi-0.80.5-help.txt",
    "tools/test/fixtures/pi-0.80.6-help.txt",
    "tools/test/process-tree.test.ts",
    "tools/test/runner-isolation.test.ts",
    "tools/test/runtime-resolver.test.ts",
    "tools/test/security.test.ts",
    "tools/test/windows-supervisor.test.ts",
    "tools/test/benchmark-boundary.ts",
})


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _descriptors():
    if not DESCRIPTORS_TOOL.is_file():
        raise AssertionError("tools/host_descriptors.py does not exist")
    return _load_module("host_descriptors_acceptance", DESCRIPTORS_TOOL)


def _run_generator(path):
    result = subprocess.run(
        [sys.executable, str(REPO / path)], cwd=REPO,
        text=True, encoding="utf-8", capture_output=True, check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"{path} failed ({result.returncode})\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


def _snapshot_generated_trees():
    paths = {}
    for root in ("plugins/ca", "plugins/ca-codex", "plugins/ca-pi"):
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(REPO).as_posix()
            paths[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths


def _valid_document():
    return json.loads((REPO / "core" / "hosts.json").read_text(encoding="utf-8"))


def _span_owns_line(text, start, end):
    return (start == 0 or text[start - 1] == "\n") and text[end:end + 1] == "\n"


def _resolve_conditionals_independently(text, host, host_names, where):
    """Test-only implementation of the documented single-level grammar."""
    out = []
    pos = 0
    keeping = True
    in_region = False
    matched = False
    for marker in _MARKER.finditer(text):
        if keeping:
            out.append(text[pos:marker.start()])
        kind = marker.group(1)
        if kind.startswith("IF:"):
            if in_region or marker.group(2) not in host_names:
                raise AssertionError(f"{where}: invalid independent condition")
            in_region = True
            matched = marker.group(2) == host
            keeping = matched
        elif kind == "ELSE":
            if not in_region:
                raise AssertionError(f"{where}: independent ELSE outside IF")
            keeping = not matched
        else:
            if not in_region:
                raise AssertionError(f"{where}: independent END outside IF")
            in_region = False
            keeping = True
        pos = marker.end()
        if keeping and _span_owns_line(text, marker.start(), marker.end()):
            pos += 1
    if in_region:
        raise AssertionError(f"{where}: independent unclosed condition")
    if keeping:
        out.append(text[pos:])
    return "".join(out)


def _independent_output_path(rel, descriptor):
    for rule in descriptor.surface_rules:
        if not rel.startswith(rule.source_prefix):
            continue
        if rel in rule.exclude:
            return None, rule
        relative = rel[len(rule.source_prefix):]
        basename = Path(relative or rel).name
        stem = Path(basename).stem
        return rule.output_pattern.format(
            relative=relative, stem=stem, name=stem
        ), rule
    return None, None


def _yaml_safe_scalar_independently(value):
    if value.startswith('"'):
        try:
            if isinstance(json.loads(value), str):
                return value
        except json.JSONDecodeError:
            return json.dumps(value, ensure_ascii=False)
    if value.startswith(("[", "{")) or ": " in value or " | " in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def _add_skill_frontmatter_independently(text, command_name, where):
    if not text.startswith("---\n"):
        raise AssertionError(f"{where}: command lacks frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise AssertionError(f"{where}: unterminated frontmatter")
    lines = []
    for line in text[4:end].split("\n"):
        if line.startswith(("description:", "argument-hint:")):
            key, value = line.split(":", 1)
            line = f"{key}: {_yaml_safe_scalar_independently(value.strip())}"
        lines.append(line)
    return f"---\nname: ca-{command_name}\n" + "\n".join(lines) + text[end:]


def _independent_expected_surfaces(descriptor, descriptors):
    """Map canonical sources to host output without importing the generator."""
    surface = REPO / "core" / "surface"
    host_names = frozenset(item.name for item in descriptors)
    command_names = frozenset(path.stem for path in (surface / "commands").glob("*.md"))
    expected = {}
    command_catalog = []
    for source in sorted(path for path in surface.rglob("*") if path.is_file()):
        rel = source.relative_to(surface).as_posix()
        dst, rule = _independent_output_path(rel, descriptor)
        if dst is None:
            continue
        where = f"core/surface/{rel}"
        text = _resolve_conditionals_independently(
            source.read_text(encoding="utf-8"), descriptor.name, host_names, where
        )
        if rel.startswith("agents/") and descriptor.name != "pi":
            text = _PI_ONLY_AGENT_FRONTMATTER.sub("", text)

        def rewrite_command_path(match):
            command_rel = f"commands/{match.group(1)}.md"
            output, _ = _independent_output_path(command_rel, descriptor)
            if output is None:
                raise AssertionError(f"{where}: excluded command path escaped condition")
            return "{{PLUGIN_ROOT}}/" + output

        text = _COMMAND_PATH.sub(rewrite_command_path, text)
        skill_rule = next(
            (item for item in descriptor.surface_rules
             if item.source_prefix == "skills/"), None
        )
        if skill_rule and "{relative}" in skill_rule.output_pattern:
            prefix = skill_rule.output_pattern.format(relative="", stem="", name="")
            if prefix != "skills/":
                text = _SKILLS_PATH.sub("{{PLUGIN_ROOT}}/" + prefix, text)

        def rewrite_command(match):
            name = match.group(1)
            if name not in command_names:
                raise AssertionError(f"{where}: unknown canonical command {name}")
            output, _ = _independent_output_path(f"commands/{name}.md", descriptor)
            if output is None:
                raise AssertionError(f"{where}: excluded command escaped condition")
            return descriptor.command_form.format(name=name)

        text = _COMMAND.sub(rewrite_command, text)
        unresolved = set(re.findall(r"\{\{[^}]+\}\}", text)) - {
            "{{PLUGIN_ROOT}}", "{{PROJECT_DIR}}",
        }
        if unresolved:
            raise AssertionError(
                f"{where}: unresolved independent template token(s): {sorted(unresolved)}"
            )
        if rule.add_skill_frontmatter:
            text = _add_skill_frontmatter_independently(text, source.stem, where)
            frontmatter_end = text.find("\n---\n", 4)
            description = next(
                line.split(":", 1)[1].strip()
                for line in text[4:frontmatter_end].split("\n")
                if line.startswith("description:")
            )
            if description.startswith('"'):
                description = json.loads(description)
            command_catalog.append({
                "name": source.stem,
                "description": description,
                "skillPath": f"skills/ca-{source.stem}/SKILL.md",
            })
        if dst in expected:
            raise AssertionError(f"{where}: independent output collision at {dst}")
        expected[dst] = text
    if descriptor.command_form == "/ca-{name}":
        expected["generated/command-catalog.json"] = (
            json.dumps(sorted(command_catalog, key=lambda item: item["name"]),
                       ensure_ascii=False, indent=2) + "\n"
        )
    return expected


def _normalize_host_tokens_independently(data, descriptor):
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    for token, value in sorted(
        descriptor.tokens.items(), key=lambda item: len(item[1]), reverse=True
    ):
        text = text.replace(value, "{{" + token + "}}")
    return text


def _pi_policy_surfaces_from_disk(pi_host):
    plugin = REPO / pi_host.plugin_dir
    shared_hooks = {
        f"hooks/{path.name}" for path in (REPO / "core" / "pysrc").glob("*.py")
    }
    exact_exemptions = (
        set(_PI_OPTIONAL_ARTIFACTS)
        | set(_TASK_2_NON_POLICY_ARTIFACTS)
        | set(_TASK_3_NON_POLICY_ARTIFACTS)
        | set(_TASK_4_NON_POLICY_ARTIFACTS)
        | set(_TASK_5_NON_POLICY_ARTIFACTS)
        | set(_TASK_6_THROUGH_10_NON_POLICY_ARTIFACTS)
        | shared_hooks
        | ({pi_host.catalog} if pi_host.catalog else set())
    )
    actual = {}
    visible = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", pi_host.plugin_dir],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    for repo_relative in sorted(visible):
        path = REPO / repo_relative
        if not path.is_file():
            continue
        rel = path.relative_to(plugin).as_posix()
        if rel in exact_exemptions:
            continue
        actual[rel] = _normalize_host_tokens_independently(path.read_bytes(), pi_host)
    return actual, exact_exemptions


def _assert_pi_policy_matches_core(actual, expected):
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise AssertionError(f"Pi policy path drift; missing={missing}, extra={extra}")
    for rel in sorted(expected):
        if actual[rel] != expected[rel]:
            raise AssertionError(f"Pi policy body differs from canonical source: {rel}")


def _host_descriptor_ci_contract_violations(ci):
    """Return missing path-filter, execution, and aggregate-gate requirements."""
    violations = []
    required_filter_paths = (
        "core/hosts.json",
        "core/surface/**",
        "plugins/ca-pi/**",
        "tools/host_descriptors.py",
        "tools/build-surface.py",
        "tools/sync-core.py",
        "tools/build-host-packages.py",
        ".github/scripts/test_host_descriptors.py",
        ".github/workflows/ci.yml",
    )
    filter_match = re.search(
        r"(?ms)^            host-descriptors:\n(?P<body>.*?)(?=^            [a-z][a-z0-9-]*:\n)",
        ci,
    )
    filter_body = filter_match.group("body") if filter_match else ""
    for path in required_filter_paths:
        if f"- '{path}'" not in filter_body:
            violations.append(f"host-descriptors filter missing {path}")

    job_match = re.search(
        r"(?ms)^  host-descriptors:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n)",
        ci,
    )
    job_body = job_match.group("body") if job_match else ""
    if "if: needs.changes.outputs.host-descriptors == 'true'" not in job_body:
        violations.append("host-descriptors job is not scoped to its path output")
    if "run: python .github/scripts/test_host_descriptors.py" not in job_body:
        violations.append("host-descriptors job does not run the complete suite")

    aggregate_match = re.search(
        r"(?ms)^  ci-passed:\n(?P<body>.*)\Z",
        ci,
    )
    aggregate_body = aggregate_match.group("body") if aggregate_match else ""
    if re.search(r"(?m)^      - host-descriptors$", aggregate_body) is None:
        violations.append("ci-passed.needs does not require host-descriptors")
    return violations


class DescriptorContractTest(unittest.TestCase):
    def test_pi_decision_0018_oracle_is_exact_versioned_and_descriptor_owned(self):
        module = _descriptors()
        pi = module.host_descriptor("pi", str(REPO))
        fingerprints = dict(pi.package["skill_expansion_fingerprints"])
        self.assertEqual(set(fingerprints), {"0.80.5", "0.80.10"})
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{64}", value) for value in fingerprints.values()))
        doctor_source = (REPO / "plugins/ca-pi/tools/src/doctor.ts").read_text(encoding="utf-8")
        for fingerprint in fingerprints.values():
            self.assertNotIn(fingerprint, doctor_source)

    def test_pi_ac_01_three_governance_hosts_are_data_not_binary_switches(self):
        module = _descriptors()
        hosts = module.load_host_descriptors(str(REPO))
        self.assertEqual([host.name for host in hosts], ["claude", "codex", "pi"])
        self.assertEqual(
            [host.plugin_dir for host in hosts],
            ["plugins/ca", "plugins/ca-codex", "plugins/ca-pi"],
        )
        for path in ("tools/build-surface.py", "tools/sync-core.py"):
            text = (REPO / path).read_text(encoding="utf-8")
            self.assertNotIn('host == "claude"', text)
            self.assertNotIn('host == "codex"', text)
            self.assertNotIn('host == "pi"', text)

    def test_pi_ac_01_descriptor_objects_are_deeply_immutable(self):
        module = _descriptors()
        host = module.host_descriptor("pi", str(REPO))
        with self.assertRaises((AttributeError, TypeError)):
            host.name = "changed"
        with self.assertRaises(TypeError):
            host.tokens["PROJECT_DIR"] = "changed"
        with self.assertRaises(TypeError):
            host.capabilities["statusline"] = True
        with self.assertRaises(TypeError):
            host.tool_classes["rogue"] = "READ"
        self.assertIsInstance(host.surface_rules[0].exclude, frozenset)

    def test_pi_ac_01_schema_rejects_invalid_documents(self):
        module = _descriptors()
        cases = []

        unknown = _valid_document()
        unknown["hosts"][0]["surprise"] = True
        cases.append(("unknown key", unknown))

        duplicate_name = _valid_document()
        duplicate_name["hosts"][1]["name"] = duplicate_name["hosts"][0]["name"]
        cases.append(("duplicate name", duplicate_name))

        duplicate_path = _valid_document()
        duplicate_path["hosts"][1]["plugin_dir"] = duplicate_path["hosts"][0]["plugin_dir"]
        cases.append(("duplicate path", duplicate_path))

        escaping = _valid_document()
        escaping["hosts"][0]["hooks_dir"] = "../outside"
        cases.append(("escaping path", escaping))

        malformed_command = _valid_document()
        malformed_command["hosts"][0]["command_form"] = "/ca:fixed"
        cases.append(("malformed command template", malformed_command))

        malformed_capability = _valid_document()
        malformed_capability["hosts"][0]["capabilities"]["condition_tags"] = ["ghost"]
        cases.append(("non-boolean capability", malformed_capability))

        noncanonical_tool = _valid_document()
        first_tool = next(iter(noncanonical_tool["hosts"][0]["tool_classes"]))
        noncanonical_tool["hosts"][0]["tool_classes"][first_tool] = "SHELL"
        cases.append(("noncanonical tool class", noncanonical_tool))

        for label, document in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as repo:
                core = Path(repo) / "core"
                core.mkdir()
                (core / "hosts.json").write_text(
                    json.dumps(document), encoding="utf-8", newline="\n"
                )
                with self.assertRaises(module.DescriptorError):
                    module.load_host_descriptors(repo)

    def test_pi_ac_01_schema_rejects_unknown_or_malformed_condition_tags(self):
        module = _descriptors()
        for token in (
            "{{IF:ghost}}unknown{{END}}",
            "{{IF:Ghost}}case variant{{END}}",
            "{{IF:ghost!}}malformed{{END}}",
            "{{IF:ghost unclosed",
        ):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as repo:
                core = Path(repo) / "core"
                surface = core / "surface"
                surface.mkdir(parents=True)
                (core / "hosts.json").write_text(
                    json.dumps(_valid_document()), encoding="utf-8", newline="\n"
                )
                (surface / "bad.md").write_text(
                    token + "\n", encoding="utf-8", newline="\n"
                )
                with self.assertRaises(module.DescriptorError):
                    module.load_host_descriptors(repo)


class GenerationContractTest(unittest.TestCase):
    def test_pi_ac_02_generation_is_clean_on_second_run(self):
        _run_generator("tools/build-surface.py")
        _run_generator("tools/sync-core.py")
        first = _snapshot_generated_trees()
        self.assertTrue(
            any(path.startswith("plugins/ca-pi/") for path in first),
            "generators did not create the Pi target",
        )
        surface_out = _run_generator("tools/build-surface.py")
        core_out = _run_generator("tools/sync-core.py")
        self.assertEqual(_snapshot_generated_trees(), first)
        self.assertIn("0 file(s) changed", surface_out)
        self.assertIn("0 file(s) written", core_out)

    def test_pi_ac_03_shared_python_is_byte_identical_for_every_host(self):
        module = _descriptors()
        sources = sorted((REPO / "core" / "pysrc").glob("*.py"))
        self.assertTrue(sources)
        for host in module.load_host_descriptors(str(REPO)):
            for source in sources:
                if source.name == "_host.py":
                    continue
                target = REPO / host.hooks_dir / source.name
                self.assertTrue(target.is_file(), target)
                self.assertEqual(target.read_bytes(), source.read_bytes(), target)

    def test_pi_ac_04_charters_are_canonical_and_claude_bytes_are_unchanged(self):
        module = _descriptors()
        descriptors = module.load_host_descriptors(str(REPO))
        claude_host = next(item for item in descriptors if item.name == "claude")
        pi_host = next(item for item in descriptors if item.name == "pi")
        canonical = REPO / "core" / "surface" / "agents"
        claude = REPO / claude_host.plugin_dir / "agents"
        pi = REPO / pi_host.plugin_dir / "agents"
        source_names = sorted(p.name for p in canonical.glob("*.md"))
        self.assertEqual(source_names, sorted(p.name for p in claude.glob("*.md")))
        self.assertEqual(source_names, sorted(p.name for p in pi.glob("*.md")))
        expected = _independent_expected_surfaces(claude_host, descriptors)
        for name in source_names:
            text = expected[f"agents/{name}"]
            for token, value in claude_host.tokens.items():
                text = text.replace("{{" + token + "}}", value)
            self.assertEqual(text.encode("utf-8"), (claude / name).read_bytes())

    def test_pi_ac_04_pi_governance_bodies_are_generated_only(self):
        module = _descriptors()
        descriptors = module.load_host_descriptors(str(REPO))
        pi_host = next(item for item in descriptors if item.name == "pi")
        expected = _independent_expected_surfaces(pi_host, descriptors)
        actual, exemptions = _pi_policy_surfaces_from_disk(pi_host)
        _assert_pi_policy_matches_core(actual, expected)
        self.assertNotIn("tools/rogue.js", exemptions)
        self.assertNotIn("dist/rogue.js", exemptions)

    def test_pi_ac_04_exact_task_2_through_10_non_policy_files_are_the_only_new_exemptions(self):
        module = _descriptors()
        descriptors = module.load_host_descriptors(str(REPO))
        pi_host = next(item for item in descriptors if item.name == "pi")
        expected = _independent_expected_surfaces(pi_host, descriptors)
        actual, exemptions = _pi_policy_surfaces_from_disk(pi_host)
        _assert_pi_policy_matches_core(actual, expected)
        for rel in (_TASK_2_NON_POLICY_ARTIFACTS | _TASK_3_NON_POLICY_ARTIFACTS
                    | _TASK_4_NON_POLICY_ARTIFACTS | _TASK_5_NON_POLICY_ARTIFACTS
                    | _TASK_6_THROUGH_10_NON_POLICY_ARTIFACTS):
            with self.subTest(rel=rel):
                self.assertIn(rel, exemptions)
        self.assertFalse(any(item.startswith("tools/") and item.endswith("/**") for item in exemptions))
        self.assertFalse(any(item.startswith("extensions/") and item.endswith("/**") for item in exemptions))

    def test_pi_ac_04_unlisted_tools_and_governance_mutations_fail_closed(self):
        module = _descriptors()
        descriptors = module.load_host_descriptors(str(REPO))
        pi_host = next(item for item in descriptors if item.name == "pi")
        expected = _independent_expected_surfaces(pi_host, descriptors)
        actual, exemptions = _pi_policy_surfaces_from_disk(pi_host)
        for rogue in ("tools/rogue.js", "tools/rogue.ts", "tools/rogue.md"):
            with self.subTest(rogue=rogue):
                self.assertNotIn(rogue, exemptions)
                mutated = copy.deepcopy(actual)
                mutated[rogue] = "non-policy-looking payload\n"
                with self.assertRaisesRegex(AssertionError, re.escape(rogue)):
                    _assert_pi_policy_matches_core(mutated, expected)
        governance = "unlisted/handwritten-policy.md"
        mutated = copy.deepcopy(actual)
        mutated[governance] = "H-99 blocks all mutations. Reviewer policy: BLOCK.\n"
        with self.assertRaisesRegex(AssertionError, re.escape(governance)):
            _assert_pi_policy_matches_core(mutated, expected)

    def test_descriptor_suite_is_a_required_path_scoped_ci_job(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertEqual(_host_descriptor_ci_contract_violations(ci), [])
        for needle, replacement in (
            ("              - 'core/hosts.json'\n", ""),
            ("              - 'tools/host_descriptors.py'\n", ""),
            (
                "              - 'tools/sync-core.py'\n"
                "              - 'tools/build-host-packages.py'\n",
                "              - 'tools/sync-core.py'\n",
            ),
            ("        run: python .github/scripts/test_host_descriptors.py\n", ""),
            ("      - host-descriptors\n", ""),
        ):
            with self.subTest(needle=needle):
                mutated = ci.replace(needle, replacement, 1)
                self.assertTrue(
                    _host_descriptor_ci_contract_violations(mutated),
                    f"CI mutation unexpectedly escaped: {needle.strip()}",
                )

    def test_pi_ac_04_independent_oracle_rejects_hardcoded_pi_governance(self):
        module = _descriptors()
        descriptors = module.load_host_descriptors(str(REPO))
        pi_host = next(item for item in descriptors if item.name == "pi")
        expected = _independent_expected_surfaces(pi_host, descriptors)
        actual, _ = _pi_policy_surfaces_from_disk(pi_host)
        mutated = copy.deepcopy(actual)
        target = "skills/ca-commit/SKILL.md"
        mutated[target] += "\nPi-only hardcoded governance paragraph.\n"
        with self.assertRaisesRegex(AssertionError, re.escape(target)):
            _assert_pi_policy_matches_core(mutated, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
