#!/usr/bin/env python3
# codeArbiter — deterministic, inert Tribunal inventory and host sizing.
#
# Repository content is evidence, never instructions. Only bounded regular-file
# reads and fixed read-only Git commands run. No project imports, scripts,
# configuration evaluation, external parsers, installs, or network requests.
# Importing this module has no filesystem/process side effects. Collection does
# not write: the caller persists JSON and its Markdown projection in its run.
#
# Public API:
#   collect_inventory(repo_root, scope='.', *, max_file_bytes=1048576,
#       max_total_bytes=8388608, history_limit=100) -> dict
#   canonical_inventory_json(inventory) -> str
#   render_inventory_md(inventory) -> str
#   resolve_profile(profile, capabilities) -> dict
#   estimate_cost(packet_bytes, profile_counts, *, verification_candidates=0,
#       concurrency=1, extraction_bytes=0) -> dict

from collections import Counter, defaultdict
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import threading

from _gitexec import git_executable, root_bound_git_env

try:
    import tomllib
except ImportError:  # Python 3.10: do not install a parser to fill this gap.
    tomllib = None


_GIT_BYTES = 8 * 1024 * 1024
_GIT_TIMEOUT = 10
_RELATIONSHIP_LIMIT = 10000
_LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".cs": "C#", ".c": "C", ".h": "C/C++", ".cpp": "C++",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".sh": "Shell", ".ps1": "PowerShell", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".json": "JSON", ".toml": "TOML",
    ".yml": "YAML", ".yaml": "YAML", ".md": "Markdown",
}
_MANIFESTS = {"package.json", "composer.json", "pyproject.toml", "Cargo.toml",
              "go.mod", "setup.py", "setup.cfg", "Pipfile", "Gemfile",
              "pom.xml", "build.gradle", "build.gradle.kts", "mix.exs"}
_LOCKFILES = {"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
              "bun.lock", "bun.lockb", "Cargo.lock", "poetry.lock", "uv.lock",
              "Pipfile.lock", "Gemfile.lock", "composer.lock", "go.sum"}
_PROFILE_WEIGHTS = {"deep": 6, "standard": 3, "extract": 1}


class _Unavailable(Exception):
    """A fixed reason code, without untrusted command output or source content."""


def _positive_int(value, maximum):
    return type(value) is int and 0 < value <= maximum


def _relative(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _Unavailable("invalid-path")
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise _Unavailable("invalid-path")
    return path.as_posix()


def _git(root, *args):
    """Bound stdout while it is read, not after an unbounded capture finishes."""
    env = root_bound_git_env()
    for key in tuple(env):
        if key.startswith("GIT_TRACE") or key in {
            "GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS", "GIT_ASKPASS", "GIT_EXEC_PATH",
            "GIT_NAMESPACE", "GIT_PAGER",
        }:
            env.pop(key, None)
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_LAZY_FETCH": "1", "GIT_PROTOCOL_FROM_USER": "0"})
    # Keep the user's safe.directory decision; never add a trust override.
    argv = [git_executable(), "--no-pager", "--no-replace-objects", "--no-lazy-fetch",
            "--no-optional-locks", "--literal-pathspecs", "-C", str(root),
            "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "-c", "protocol.allow=never", *args]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env, shell=False)
    except (OSError, RuntimeError):
        raise _Unavailable("git-unavailable") from None
    output = []

    def read_bounded():
        output.append(process.stdout.read(_GIT_BYTES + 1))

    worker = threading.Thread(target=read_bounded, daemon=True)
    worker.start()
    worker.join(_GIT_TIMEOUT)
    try:
        if worker.is_alive() or not output:
            raise _Unavailable("git-timeout")
        if len(output[0]) > _GIT_BYTES:
            raise _Unavailable("git-output-limit")
        try:
            code = process.wait(timeout=_GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise _Unavailable("git-timeout") from None
        if code:
            raise _Unavailable("git-unavailable")
        return output[0]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        worker.join(_GIT_TIMEOUT)
        process.stdout.close()


def _note(result, field, reason, path=None):
    item = {"field": field, "reason": reason}
    if path is not None:
        item["path"] = path
    if item not in result["unavailable"]:
        result["unavailable"].append(item)


def _regular_file(root, relative):
    """Reject links/reparse points in every component, including directories."""
    relative = _relative(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise _Unavailable("non-regular-file")
    if not stat.S_ISREG(info.st_mode):
        raise _Unavailable("non-regular-file")
    if not path.resolve().is_relative_to(root):
        raise _Unavailable("outside-repository")
    return path, info


def _read_manifest(root, relative, result, limits):
    path, before = _regular_file(root, relative)
    if before.st_size > limits["file"]:
        raise _Unavailable("file-byte-limit")
    remaining = limits["total"] - limits["read"]
    if before.st_size > remaining:
        raise _Unavailable("total-byte-limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        _, current = _regular_file(root, relative)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise _Unavailable("file-changed-during-read")
        if not stat.S_ISREG(opened.st_mode):
            raise _Unavailable("non-regular-file")
        data = stream.read(min(limits["file"], remaining) + 1)
    limits["read"] += len(data)
    if len(data) > limits["file"]:
        raise _Unavailable("file-byte-limit")
    if len(data) > remaining:
        raise _Unavailable("total-byte-limit")
    return data.decode("utf-8-sig")


def _dependency(result, manifest, ecosystem, group, name, version):
    if not isinstance(name, str) or not name:
        _note(result, "dependencies", "malformed-dependency", manifest)
        return
    declared = isinstance(version, str) and bool(version)
    result["dependencies"].append({"manifest": manifest, "ecosystem": ecosystem,
                                   "group": group, "name": name,
                                   "version": version if declared else None,
                                   "version_status": "declared" if declared else "not-declared"})


def _dependency_table(result, path, ecosystem, data, groups):
    for group in groups:
        table = data.get(group, {})
        if not isinstance(table, dict):
            _note(result, "dependencies", "malformed-dependency-group", path)
            continue
        for name, declaration in sorted(table.items()):
            if not isinstance(declaration, str) and not (ecosystem == "cargo" and isinstance(declaration, dict)):
                _note(result, "dependencies", "malformed-dependency", path)
                continue
            version = declaration.get("version") if isinstance(declaration, dict) else declaration
            _dependency(result, path, ecosystem, group, name, version)


def _requirement(result, path, group, text):
    if not isinstance(text, str):
        _note(result, "dependencies", "unsupported-requirement", path)
        return
    # Only a named PEP-508-style requirement. Includes, URLs, editable installs
    # and options are surfaced as unavailable, never followed or executed.
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[A-Za-z0-9_,.-]+\])?"
                         r"\s*((?:[<>=!~].*|;.*)?)", text.strip())
    if not match or "\\" in text:
        _note(result, "dependencies", "unsupported-requirement", path)
        return
    version = match.group(2).split(";", 1)[0].strip() or None
    _dependency(result, path, "python", group, match.group(1), version)


def _declared_path(manifest, value):
    if not isinstance(value, str):
        raise _Unavailable("unsupported-declared-path")
    return _relative((PurePosixPath(manifest).parent / _relative(value)).as_posix())


def _entry(result, manifest, kind, value):
    try:
        path = _declared_path(manifest, value)
    except _Unavailable:
        _note(result, "entry_points", "unsupported-declared-path", manifest)
        return
    result["entry_points"].append({"path": path, "declared_in": manifest, "basis": kind})


def _generation(result, manifest, source, outputs, basis):
    try:
        source = _declared_path(manifest, source)
        outputs = sorted({_declared_path(manifest, value) for value in outputs})
    except _Unavailable:
        _note(result, "generated_relationships", "unsupported-declared-path", manifest)
        return
    if outputs:
        result["generated_relationships"].append({"declared_in": manifest, "source": source,
                                                  "outputs": outputs, "basis": basis})


def _parse_manifest(result, path, text):
    name = PurePosixPath(path).name
    if name in {"package.json", "composer.json", "tsconfig.json"} or path == "core/hosts.json":
        data = json.loads(text)
    elif name in {"pyproject.toml", "Cargo.toml"}:
        if tomllib is None:
            raise _Unavailable("stdlib-toml-unavailable")
        data = tomllib.loads(text)
    elif name.startswith("requirements") and name.endswith(".txt"):
        for line in text.splitlines():
            line = line.split(" #", 1)[0].strip()
            if line and not line.startswith("#"):
                _requirement(result, path, "requirements", line)
        return
    elif name == "go.mod":
        in_require = False
        for line in text.splitlines():
            stripped = line.split("//", 1)[0].strip()
            if stripped == "require (":
                in_require = True
            elif stripped == ")":
                in_require = False
            elif stripped.startswith("require ") or in_require:
                if "// indirect" in line:
                    continue
                parts = stripped.removeprefix("require ").split()
                if len(parts) == 2:
                    _dependency(result, path, "go", "require", *parts)
                elif stripped:
                    _note(result, "dependencies", "unsupported-requirement", path)
            elif stripped.startswith("module "):
                result["package_metadata"].append({"manifest": path, "name": stripped[7:].strip()})
        return
    else:
        raise _Unavailable("unsupported-format")
    if not isinstance(data, dict):
        raise _Unavailable("malformed-manifest")

    if path == "core/hosts.json":
        _host_surface_rules(result, path, data)
    elif name == "package.json":
        _metadata(result, path, data)
        _dependency_table(result, path, "npm", data,
                          ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"))
        for key in ("main", "module", "types", "browser"):
            if isinstance(data.get(key), str):
                _entry(result, path, key, data[key])
        binaries = data.get("bin", {})
        if isinstance(binaries, str):
            binaries = {"bin": binaries}
        if isinstance(binaries, dict):
            for value in binaries.values():
                _entry(result, path, "bin", value)
        if "source" in data:
            _generation(result, path, data["source"],
                        [data[key] for key in ("main", "module", "types") if isinstance(data.get(key), str)],
                        "package-source-output")
        if "exports" in data:
            _note(result, "entry_points", "export-map-not-resolved", path)
    elif name == "composer.json":
        _metadata(result, path, data)
        _dependency_table(result, path, "composer", data, ("require", "require-dev"))
    elif name == "Cargo.toml":
        _metadata(result, path, data.get("package", {}))
        _dependency_table(result, path, "cargo", data,
                          ("dependencies", "dev-dependencies", "build-dependencies"))
        if "target" in data or "workspace" in data:
            _note(result, "dependencies", "target-or-workspace-dependencies-not-resolved", path)
    elif name == "pyproject.toml":
        project = data.get("project", {})
        if not isinstance(project, dict):
            raise _Unavailable("malformed-manifest")
        _metadata(result, path, project)
        dependencies = project.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise _Unavailable("malformed-manifest")
        for declaration in dependencies:
            _requirement(result, path, "dependencies", declaration)
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group, declarations in optional.items():
                if isinstance(declarations, list):
                    for declaration in declarations:
                        _requirement(result, path, "optional:" + group, declaration)
                else:
                    _note(result, "dependencies", "malformed-dependency-group", path)
        for group in ("scripts", "gui-scripts"):
            entries = project.get(group, {})
            if isinstance(entries, dict):
                for entry_name, target in sorted(entries.items()):
                    if isinstance(target, str):
                        result["entry_points"].append({"declared_in": path, "name": entry_name,
                                                       "target": target, "basis": group})
        if project.get("dynamic") or "tool" in data:
            _note(result, "dependencies", "dynamic-or-tool-dependencies-not-resolved", path)
    elif name == "tsconfig.json":
        options = data.get("compilerOptions", {})
        if isinstance(options, dict) and "rootDir" in options and "outDir" in options:
            _generation(result, path, options["rootDir"], [options["outDir"]], "compiler-root-out-dir")
        if "extends" in data or "references" in data:
            _note(result, "generated_relationships", "extended-config-not-resolved", path)


def _host_surface_rules(result, path, data):
    """Read the existing host descriptor convention as data, never a generator."""
    hosts = data.get("hosts")
    if not isinstance(hosts, list):
        raise _Unavailable("malformed-manifest")
    for host in hosts:
        try:
            if not isinstance(host, dict) or not isinstance(host.get("surface"), dict):
                raise _Unavailable("unsupported-host-surface-rule")
            plugin = _relative(host.get("plugin_dir"))
            rules = host["surface"].get("rules")
            if not isinstance(rules, list):
                raise _Unavailable("unsupported-host-surface-rule")
            for rule in rules:
                if not isinstance(rule, dict):
                    raise _Unavailable("unsupported-host-surface-rule")
                source = _relative("core/surface/" + _relative(rule.get("source_prefix")))
                output = _relative(plugin + "/" + _relative(rule.get("output_pattern")))
                excludes = rule.get("exclude", [])
                if not isinstance(excludes, list) or not all(isinstance(value, str) for value in excludes):
                    raise _Unavailable("unsupported-host-surface-rule")
                result["generated_relationships"].append({"declared_in": path, "source": source,
                                                          "outputs": [output], "excludes": sorted(excludes),
                                                          "basis": "host-surface-rule"})
        except _Unavailable as exc:
            _note(result, "generated_relationships", str(exc), path)


def _metadata(result, path, data):
    if not isinstance(data, dict):
        raise _Unavailable("malformed-manifest")
    row = {"manifest": path}
    for key in ("name", "version", "license", "description", "homepage", "private"):
        if isinstance(data.get(key), (str, bool)):
            row[key] = data[key]
    result["package_metadata"].append(row)


def _path_facts(result):
    sources = defaultdict(list)
    tests = []
    languages = defaultdict(lambda: {"files": 0, "bytes": 0, "unknown_sizes": 0})
    for row in result["files"]:
        path = row["path"]
        pure = PurePosixPath(path)
        name = pure.name
        lower = path.lower()
        language = languages[row["language"]]
        language["files"] += 1
        if row["bytes"] is None:
            language["unknown_sizes"] += 1
        else:
            language["bytes"] += row["bytes"]
        stem = pure.stem
        test_stem = re.sub(r"(?:[._](?:test|spec))$", "", stem.removeprefix("test_"))
        is_test = test_stem != stem or any(part in {"test", "tests", "__tests__"} for part in pure.parts)
        if is_test:
            tests.append((path, test_stem, pure.suffix))
        else:
            sources[(stem, pure.suffix)].append(path)
        if name in {"__main__.py", "main.py", "main.go", "main.rs", "index.js", "index.ts", "Program.cs"}:
            result["entry_points"].append({"path": path, "basis": "path-convention"})
        surfaces = result["surfaces"]
        if path.startswith((".github/workflows/", ".circleci/")) or name in {
            ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
        }:
            surfaces["ci"].append(path)
        if any(word in lower for word in ("release", "publish", "changelog")):
            surfaces["release"].append(path)
        if "deploy" in lower or name.startswith(("Dockerfile", "docker-compose")):
            surfaces["deploy"].append(path)
        if pure.suffix in {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"} or name in {
            ".gitattributes", ".gitignore", "Dockerfile", "Makefile",
        }:
            surfaces["config"].append(path)
    result["languages"] = [{"language": language, **counts} for language, counts in sorted(languages.items())]
    for test, stem, suffix in tests:
        for source in sources[(stem, suffix)]:
            if len(result["test_source_relationships"]) >= _RELATIONSHIP_LIMIT:
                _note(result, "test_source_relationships", "relationship-limit")
                return
            result["test_source_relationships"].append({"test": test, "source": source,
                                                        "basis": "filename-convention"})


def _git_facts(result, root, scope, history_limit):
    git = result["git"]
    try:
        git["head"] = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    except _Unavailable as exc:
        _note(result, "git.head", str(exc))
    try:
        status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                      "--ignore-submodules=all", "--no-renames", "--", scope)
        for row in status.split(b"\0"):
            if row:
                git["dirty_paths"].append({"path": os.fsdecode(row[3:]),
                                           "index": chr(row[0]), "worktree": chr(row[1])})
        git["status"] = "ok"
    except _Unavailable as exc:
        _note(result, "git.dirty_paths", str(exc))
    try:
        commits = _git(root, "rev-list", "--max-count=" + str(history_limit), "HEAD", "--", scope)
        paths = _git(root, "log", "--max-count=" + str(history_limit), "--format=", "--name-only", "-z",
                     "--no-show-signature", "--no-renames", "--no-ext-diff", "--no-textconv", "HEAD", "--", scope)
        counts = Counter(os.fsdecode(value) for value in paths.split(b"\0") if value)
        git["churn"] = {"status": "ok", "commit_limit": history_limit,
                         "commits_observed": len(commits.splitlines()),
                         "by_path": [{"path": path, "changes": count} for path, count in sorted(counts.items())]}
    except _Unavailable as exc:
        _note(result, "git.churn", str(exc))


def collect_inventory(repo_root, scope=".", *, max_file_bytes=1048576,
                      max_total_bytes=8388608, history_limit=100):
    """Collect scoped tracked-worktree facts; untracked content is never parsed.

    Missing/unsupported fields stay explicit. Sizes describe current regular
    worktree files, while membership comes from Git's index. Naming conventions
    are labelled as such, not promoted to semantic relationships. Parser support
    is deliberately bounded; empty results never establish semantic absence.
    """
    result = {"schema_version": 1, "status": "unavailable", "scope": None, "repository_root": None,
              "judgment": "not-performed", "files": [], "languages": [], "manifests": [],
              "lockfiles": [], "dependencies": [], "package_metadata": [], "entry_points": [],
              "generated_relationships": [], "test_source_relationships": [],
              "surfaces": {"ci": [], "release": [], "deploy": [], "config": []},
              "git": {"head": None, "status": "unavailable", "dirty_paths": [],
                      "churn": {"status": "unavailable", "commit_limit": None,
                                "commits_observed": None, "by_path": []}},
              "unavailable": [], "parsed_bytes": 0}
    try:
        scope = _relative(scope)
        if not (_positive_int(max_file_bytes, 16 * 1024 * 1024)
                and _positive_int(max_total_bytes, 64 * 1024 * 1024)
                and _positive_int(history_limit, 1000)):
            raise _Unavailable("invalid-limits")
        root = Path(repo_root).resolve(strict=True)
        if not root.is_dir():
            raise _Unavailable("invalid-repository")
        reported = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        if Path(reported).resolve() != root:
            raise _Unavailable("repository-root-mismatch")
        result.update({"scope": scope, "repository_root": str(root), "status": "ok"})
        rows = _git(root, "ls-files", "--stage", "-z", "--", scope)
    except (OSError, TypeError, ValueError, RuntimeError, _Unavailable) as exc:
        _note(result, "inventory", str(exc) if isinstance(exc, _Unavailable) else "invalid-repository")
        result["status"] = "unavailable"
        return result
    limits = {"file": max_file_bytes, "total": max_total_bytes, "read": 0}
    members = {}
    for row in rows.split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            mode, _, stage = metadata.split()
            members[os.fsdecode(path)] = (mode, stage)
    for path, (mode, stage) in sorted(members.items()):
        pure = PurePosixPath(path)
        name = pure.name
        item = {"path": path, "bytes": None, "language": _LANGUAGES.get(pure.suffix.lower(), "unknown"),
                "kind": "file", "size_status": "unavailable"}
        manifest = name in _MANIFESTS or (name.startswith("requirements") and name.endswith(".txt"))
        parsed_config = name == "tsconfig.json" or path == "core/hosts.json"
        if name in _LOCKFILES:
            result["lockfiles"].append(path)
        record = {"path": path, "parse_status": "unavailable"}
        if manifest:
            result["manifests"].append(record)
        try:
            if mode not in {b"100644", b"100755"}:
                item["kind"] = "symlink" if mode == b"120000" else "submodule-or-special"
                raise _Unavailable("non-regular-file")
            _, info = _regular_file(root, path)
            item.update({"bytes": info.st_size, "size_status": "ok"})
            if stage != b"0":
                raise _Unavailable("unmerged-index-entry")
            if manifest or parsed_config:
                if not parsed_config and name not in {"package.json", "composer.json", "pyproject.toml", "Cargo.toml",
                                 "go.mod", "tsconfig.json"} and not name.startswith("requirements"):
                    raise _Unavailable("unsupported-format")
                text = _read_manifest(root, path, result, limits)
                _parse_manifest(result, path, text)
                record["parse_status"] = "parsed"
        except _Unavailable as exc:
            _note(result, "manifest" if manifest or parsed_config else "files", str(exc), path)
        except (UnicodeError, ValueError, RecursionError):
            reason = "unsupported-jsonc-or-malformed" if name == "tsconfig.json" else "malformed-manifest"
            _note(result, "manifest", reason, path)
        except OSError:
            _note(result, "files", "file-unavailable", path)
        result["files"].append(item)
    result["parsed_bytes"] = limits["read"]
    _path_facts(result)
    _git_facts(result, root, scope, history_limit)
    _note(result, "import_call_graph", "no-inert-language-parser-selected")
    for key in ("dependencies", "entry_points", "generated_relationships", "unavailable"):
        result[key].sort(key=lambda row: json.dumps(row, sort_keys=True))
    result["status"] = "partial" if result["unavailable"] else "ok"
    return result


def canonical_inventory_json(inventory):
    """Stable UTF-8-safe JSON; collection excludes clocks and model judgment."""
    return json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def render_inventory_md(inventory):
    """Readable projection. Escape repository-controlled text as inert text."""
    def text(value):
        plain = str(value).replace("\n", " ").replace("\r", " ")
        # Escape original characters once, never punctuation in generated entities.
        return re.sub(r"""[&<>"'\\`*_{}\[\]()#+!|~-]""",
                      lambda match: html.escape(match[0], quote=True)
                      if match[0] in "&<>\"'" else "&#%d;" % ord(match[0]), plain)

    lines = ["# Tribunal inventory", "", "Mechanical facts; model judgment has not been performed.", "",
             "Scope: " + text(inventory.get("scope")), "Status: " + text(inventory.get("status")), "",
             "| Tracked path | Bytes | Language |", "|---|---:|---|"]
    for row in inventory.get("files", []):
        lines.append("| %s | %s | %s |" % (text(row["path"]), text(row["bytes"]), text(row["language"])))
    for label, field in (("Direct dependencies", "dependencies"), ("Package metadata", "package_metadata"),
                         ("Entry points", "entry_points"), ("Generated relationships", "generated_relationships"),
                         ("Test/source naming relationships", "test_source_relationships")):
        lines.extend(["", "## " + label, ""])
        lines.extend("- " + text(json.dumps(row, sort_keys=True)) for row in inventory.get(field, []))
        if not inventory.get(field):
            lines.append("None found in supported, scoped declarations; this is not a semantic absence claim.")
    lines.extend(["", "## Git and surfaces", "", text(json.dumps(inventory.get("git", {}), sort_keys=True)), "",
                  text(json.dumps(inventory.get("surfaces", {}), sort_keys=True)), "", "## Unavailable", ""])
    lines.extend("- " + text(json.dumps(row, sort_keys=True)) for row in inventory.get("unavailable", []))
    return "\n".join(lines) + "\n"


def resolve_profile(profile, capabilities):
    """Resolve only caller-observed capabilities, never a provider model table.

    capabilities: fresh_threads, model_override, reasoning_override booleans;
    models/reasoning_levels lists; profiles maps deep/standard/extract to model
    and reasoning settings. Missing capability is unavailable, never inferred
    from native plugin-agent registration (`agents`). Empty settings inherit.
    """
    caps = capabilities if isinstance(capabilities, dict) else {}
    fresh = caps.get("fresh_threads") is True
    result = {"profile": profile if isinstance(profile, str) else None, "status": "ok", "settings": {},
              "model_source": "inherited", "execution": "fresh-thread" if fresh else "inline",
              "independence": "fresh-context" if fresh else "limited-shared-context", "limitations": []}
    if not fresh:
        result["limitations"].append("Fresh threads unavailable or unconfirmed; inline review shares context and has limited verification independence.")
    if not isinstance(profile, str) or profile not in _PROFILE_WEIGHTS:
        result["status"] = "unavailable"
        result["limitations"].append("Unknown review profile.")
        return result
    profiles = caps.get("profiles", {})
    desired = profiles.get(profile, {}) if isinstance(profiles, dict) else {}
    desired = desired if isinstance(desired, dict) else {}
    for setting, available in (("model", "models"), ("reasoning", "reasoning_levels")):
        value = desired.get(setting)
        choices = caps.get(available, [])
        if (caps.get(setting + "_override") is True and isinstance(value, str)
                and isinstance(choices, list) and value in choices):
            result["settings"][setting] = value
        else:
            result["limitations"].append("No supported %s override for %s; inherit the configured setting." % (setting, profile))
    if "model" in result["settings"]:
        result["model_source"] = "host-profile"
    if result["limitations"]:
        result["status"] = "limited"
    return result


def estimate_cost(packet_bytes, profile_counts, *, verification_candidates=0,
                  concurrency=1, extraction_bytes=0):
    """Broad heuristic token band, not usage or a monetary quote.

    packet_bytes is the SUM of selected packet bytes across active lenses (a
    repeated packet counts again); extraction_bytes is inventory handed to the
    model, not bytes scanned by Python. Profile multipliers 6/3/1, a 1,000-token
    per-lens allowance and a half-to-double band are disclosed assumptions, not
    measured calibration. Verification uses the average packet plus allowance.
    """
    result = {"status": "unavailable", "basis": "heuristic-not-usage", "token_band": None,
              "measured_usage": None, "price": None, "inputs": {}, "limitations": []}
    if (not isinstance(profile_counts, dict)
            or any(key not in _PROFILE_WEIGHTS or type(value) is not int or not 0 <= value <= 1000
                   for key, value in profile_counts.items())
            or any(type(value) is not int or not 0 <= value <= 10**12
                   for value in (packet_bytes, extraction_bytes, verification_candidates))
            or not _positive_int(concurrency, 1000)):
        result["limitations"].append("Invalid cost inputs; no estimate produced.")
        return result
    count = sum(profile_counts.values())
    if not count and (packet_bytes or verification_candidates):
        result["limitations"].append("Packet and verification work require active profile counts.")
        return result
    weighted = sum(_PROFILE_WEIGHTS[key] * value for key, value in profile_counts.items())
    packet_tokens = math.ceil(packet_bytes / 4)
    point = math.ceil(packet_tokens * weighted / max(count, 1) + 1000 * count + extraction_bytes / 4
                      + verification_candidates * (1000 + packet_tokens / max(count, 1)))
    result.update({"status": "estimated", "token_band": {"low": math.floor(point / 2), "high": point * 2},
                   "inputs": {"packet_bytes": packet_bytes, "profile_counts": dict(sorted(profile_counts.items())),
                              "active_lenses": count, "verification_candidates": verification_candidates,
                              "extraction_bytes": extraction_bytes},
                   "assumptions": {"bytes_per_token": 4, "profile_multipliers": dict(_PROFILE_WEIGHTS),
                                   "per_lens_allowance": 1000, "band_multipliers": [0.5, 2]},
                   "concurrency": {"requested": concurrency, "in_flight": min(count, concurrency),
                                   "affects": ["elapsed-time", "peak-resource"], "reduces_total_tokens": False},
                   "limitations": ["Heuristic only; historical calibration and actual usage are unavailable."]})
    return result
