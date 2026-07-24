#!/usr/bin/env python3
"""Read-only aggregate verifier for the two-phase Pi support promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED = ("0.80.5", "0.80.10")
PLATFORMS = ("windows", "linux", "macos")
ARCHITECTURES = {"x64", "arm64", "pending"}
ROW_KEYS = {"version", "platform", "architecture", "resultCode", "passed", "timingMs", "diagnosticCode"}
OBLIGATIONS = tuple(f"PI-AC-{number:02d}" for number in range(1, 39))
OBLIGATION_BINDINGS = {
    "PI-AC-01": ("host-descriptors",), "PI-AC-02": ("surface-idempotency",),
    "PI-AC-03": ("host-descriptors", "sync-core-check"), "PI-AC-04": ("host-descriptors",),
    "PI-AC-05": ("pi-package",), "PI-AC-06": ("pi-package", "package-inventory"),
    "PI-AC-07": ("pi-package",), "PI-AC-08": ("pi-package",),
    "PI-AC-09": ("pi-package", "pi-parity"), "PI-AC-10": ("pi-package", "public-pi-docs"),
    "PI-AC-11": ("pi-tools", "pi-parity"), "PI-AC-12": ("pi-parity",),
    "PI-AC-13": ("pi-tools", "pi-security"), "PI-AC-14": ("pi-tools", "pi-parity"),
    "PI-AC-15": ("pi-tools", "pi-parity"), "PI-AC-16": ("hook-guards", "hook-unittest"),
    "PI-AC-17": ("pi-package", "pi-security"), "PI-AC-18": ("pi-tools", "pi-platform-fixtures"),
    "PI-AC-19": ("pi-process-tree", "pi-platform-fixtures"), "PI-AC-20": ("pi-package", "pi-security"),
    "PI-AC-21": ("pi-tools", "pi-parity"), "PI-AC-22": ("pi-tools", "pi-parity"),
    "PI-AC-23": ("pi-compaction", "prune-policy-parity"), "PI-AC-24": ("pi-compaction",),
    "PI-AC-25": ("prune-policy-parity", "pi-parity"), "PI-AC-26": ("pi-tools", "pi-parity"),
    "PI-AC-27": ("pi-shared-store", "pi-parity"), "PI-AC-28": ("pi-doctor", "pi-package"),
    "PI-AC-29": ("pi-security", "pi-package"), "PI-AC-30": ("pi-security",),
    "PI-AC-31": ("pi-benchmark-tests", "pi-benchmark"), "PI-AC-32": ("pi-platform-fixtures", "promotion"),
    "PI-AC-33": ("pi-package", "host-packages-idempotency"), "PI-AC-34": ("public-pi-docs", "plugin-refs-pi"),
    "PI-AC-35": ("promotion", "promotion-security", "promotion-markdown", "hosted-attestation"), "PI-AC-36": ("pi-security",),
    "PI-AC-37": ("repository-gates", "diff-check"), "PI-AC-38": ("branch", "statuses", "promotion"),
}
SAFE_TOKEN = re.compile(r"^[A-Z0-9_.-]{1,96}$")
META_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
FORBIDDEN_TEXT = re.compile(r"(?:[A-Za-z]:[/\\]Users[/\\]|/home/|/Users/|BEGIN [A-Z ]*PRIVATE|(?:api[_-]?key|token|secret|password)\s*[:=])", re.I)
REQUIRED_HOSTED_CHECKS = frozenset(
    {
        f"[CHECK] | [PI  ] | Adapter contract  <os: {os_name} · runtime: Pi {version}>"
        for os_name in ("ubuntu-latest", "windows-latest", "macos-latest")
        for version in SUPPORTED
    }
    | {
        "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>",
        "[GATE ] | [REPO] | Merge readiness",
    }
)
FINAL_EVIDENCE_PATHS = frozenset({
    ".codearbiter/gate-events.log",
    ".codearbiter/plans/hackathon-pr313-consolidation.md",
    ".codearbiter/plans/pi-support.md",
    ".codearbiter/reports/2026-07-20-hackathon-pr313/integration.md",
    ".codearbiter/sprint-log.md",
    "docs/parity.md",
    "docs/reports/pi-support/promotion.json",
    "docs/reports/pi-support/promotion.md",
})
FINAL_EVIDENCE_PREFIXES = (".codearbiter/reports/2026-07-14-pi-support-handoff/",)


class Verdict:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def add(self, passed: bool, code: str, detail: str) -> None:
        self.rows.append((passed, code, detail))

    def emit(self) -> int:
        for passed, code, detail in self.rows:
            print(f"[{'PASS' if passed else 'FAIL'}] {code}: {detail}")
        return 0 if all(row[0] for row in self.rows) else 1


def strict_promotion(document: Any, mode: str) -> tuple[bool, str]:
    if not isinstance(document, dict) or set(document) != {"schema", "mode", "commit", "rows"}:
        return False, "promotion envelope"
    if document.get("schema") != "codearbiter-pi-promotion-v1" or document.get("mode") not in {"preclosure", "final"}:
        return False, "promotion schema"
    commit = document.get("commit")
    if commit is not None and (not isinstance(commit, str) or COMMIT.fullmatch(commit) is None):
        return False, "promotion commit"
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        return False, "promotion rows"
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            return False, "promotion row shape"
        if not all(isinstance(row[key], str) for key in ("version", "platform", "architecture", "resultCode", "diagnosticCode")):
            return False, "promotion row types"
        if not isinstance(row["passed"], bool) or not isinstance(row["timingMs"], (int, float)) or isinstance(row["timingMs"], bool) or not math.isfinite(row["timingMs"]) or row["timingMs"] < 0:
            return False, "promotion row types"
        if any(META_TOKEN.fullmatch(row[key]) is None for key in ("version", "platform", "architecture")):
            return False, "promotion token"
        if any(SAFE_TOKEN.fullmatch(row[key]) is None for key in ("resultCode", "diagnosticCode")):
            return False, "promotion diagnostic"
        if row["architecture"] not in ARCHITECTURES:
            return False, "promotion architecture"
    serialized = json.dumps(document, separators=(",", ":"))
    if FORBIDDEN_TEXT.search(serialized):
        return False, "promotion sanitization"

    def matching(version: str, platform: str, code: str | None = None) -> list[dict[str, Any]]:
        return [row for row in rows if row["version"] == version and row["platform"] == platform and (code is None or row["resultCode"] == code)]

    for version in SUPPORTED:
        local = matching(version, "windows-local", "PI-LOCAL-SUPPORTED")
        if (
            len(local) != 1
            or local[0]["passed"] is not True
            or local[0]["diagnosticCode"] != "NONE"
            or local[0]["architecture"] not in {"x64", "arm64"}
            or local[0]["timingMs"] <= 0
        ):
            return False, f"local supported {version}"
    hosted = {(version, platform): matching(version, platform) for version in SUPPORTED for platform in PLATFORMS}
    if any(len(cells) != 1 for cells in hosted.values()):
        return False, "hosted six-cell matrix"
    codeql = matching("codeql", "github")
    if len(codeql) != 1:
        return False, "hosted CodeQL"
    canary = [row for row in rows if row["resultCode"] == "PI-LATEST-CANARY"]
    if (
        len(canary) != 1
        or SEMVER.fullmatch(canary[0]["version"]) is None
        or canary[0]["version"] in SUPPORTED
        or canary[0]["platform"] != "windows-local"
        or canary[0]["architecture"] not in {"x64", "arm64"}
        or canary[0]["timingMs"] <= 0
        or (
            canary[0]["diagnosticCode"] != "NONE"
            if canary[0]["passed"]
            else canary[0]["diagnosticCode"] not in {"VERSION_UNSUPPORTED", "CANARY_FAILED", "NONBLOCKING_CANARY"}
        )
    ):
        return False, "latest canary"
    expected_cells = (
        {(version, "windows-local") for version in SUPPORTED}
        | {(version, platform) for version in SUPPORTED for platform in PLATFORMS}
        | {("codeql", "github"), (canary[0]["version"], "windows-local")}
    )
    if len(rows) != 10 or {(row["version"], row["platform"]) for row in rows} != expected_cells:
        return False, "promotion exact row inventory"

    if mode == "preclosure" and document["mode"] == "preclosure":
        for cells in hosted.values():
            row = cells[0]
            if (
                (row["resultCode"], row["passed"], row["diagnosticCode"]) != ("PI-HOSTED-PENDING", False, "HOSTED_PENDING")
                or row["architecture"] != "pending"
                or row["timingMs"] != 0
            ):
                return False, "preclosure hosted pending"
        if (
            (codeql[0]["resultCode"], codeql[0]["passed"], codeql[0]["diagnosticCode"]) != ("PI-CODEQL-PENDING", False, "HOSTED_PENDING")
            or codeql[0]["architecture"] != "pending"
            or codeql[0]["timingMs"] != 0
        ):
            return False, "preclosure CodeQL pending"
        if commit is not None:
            return False, "preclosure uncommitted"
        return True, "local green; hosted six-cell and CodeQL explicitly pending"

    if document["mode"] != "final" or not isinstance(commit, str):
        return False, "hosted final evidence"
    for cells in hosted.values():
        row = cells[0]
        if (row["resultCode"], row["passed"], row["diagnosticCode"]) != ("PI-HOSTED-SUPPORTED", True, "NONE"):
            return False, "hosted final matrix"
        if row["architecture"] == "pending" or row["timingMs"] <= 0:
            return False, "hosted final architecture"
    if (
        (codeql[0]["resultCode"], codeql[0]["passed"], codeql[0]["diagnosticCode"]) != ("PI-CODEQL-HIGH", True, "NONE")
        or codeql[0]["architecture"] == "pending"
        or codeql[0]["timingMs"] <= 0
    ):
        return False, "hosted final CodeQL"
    return True, f"hosted matrix and CodeQL bound to {commit[:12]}"


def render_promotion_markdown(document: dict[str, Any]) -> str:
    """Render the public evidence surface only from the strict JSON envelope."""
    if document["mode"] == "preclosure":
        status = "provisional preclosure; hosted six-cell matrix and CodeQL explicitly pending"
    else:
        status = f"final hosted evidence bound to commit `{document['commit']}`"
    lines = [
        "# Pi support promotion evidence",
        "",
        f"Status: {status}.",
        "",
        "| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in document["rows"]:
        lines.append(
            f"| {row['version']} | {row['platform']} | {row['architecture']} | "
            f"{row['resultCode']} | {str(row['passed']).lower()} | {row['timingMs']} | "
            f"{row['diagnosticCode']} |"
        )
    lines.extend((
        "",
        "This document is generated only from the bounded fields in "
        "[promotion.json](./promotion.json). It contains no prompts, task text, provider "
        "responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.",
        "",
    ))
    return "\n".join(lines)


def parse_plan(path: Path) -> tuple[dict[int, str], dict[str, str], dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    tasks: dict[int, str] = {}
    headers = list(re.finditer(r"^### Task (\d+):", text, re.M))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        status = re.search(r"^\*\*Status:\*\*\s*([^\r\n]+)", text[header.end():end], re.M)
        if status:
            tasks[int(header.group(1))] = re.split(r"\s+[—-]\s+", status.group(1).strip(), maxsplit=1)[0]
    obligations = {match.group(1): match.group(2) for match in re.finditer(r"^\|\s*(PI-AC-\d{2})\b[^|]*\|[^|]*\|[^|]*\|\s*([A-Z]+)", text, re.M)}
    owners = {code: len(re.findall(rf"\b{re.escape(code)}\b", "\n".join(re.findall(r"^\*\*Owns:\*\*.*$", text, re.M)))) for code in OBLIGATIONS}
    return tasks, obligations, owners


def fixture_checks(root: Path, verdict: Verdict) -> tuple[dict[str, tuple[str, ...]], dict[str, bool]]:
    config = json.loads((root / ".pi-support-fixture.json").read_text(encoding="utf-8"))
    verdict.add(config.get("branch") == "feat/pi-support", "branch", "feat/pi-support required")
    pairs_ok = True
    for source, generated in config.get("generatedPairs", []):
        pairs_ok = pairs_ok and (root / source).read_bytes() == (root / generated).read_bytes()
    verdict.add(pairs_ok, "generated surface", "generated pairs byte-identical")
    for key, label in (("localChecks", "local evidence"), ("runtimeTreeAbsent", "Pi runtime tree"), ("packageInventoryClean", "package inventory"), ("forbiddenDuplicationAbsent", "policy duplication")):
        verdict.add(config.get(key) is True, label, "fixture contract")
    bindings = {key: tuple(value) for key, value in config.get("bindings", {}).items()}
    labels = {label: True for values in bindings.values() for label in values}
    return bindings, labels


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _commit_is_ancestor(root: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=root, capture_output=True, check=False,
    ).returncode == 0


def _promotion_commit_is_valid(root: Path, document: dict[str, Any], fixture_mode: bool) -> bool:
    if document.get("mode") != "final" or fixture_mode:
        return True
    commit = document.get("commit")
    return (
        isinstance(commit, str)
        and _commit_is_ancestor(root, commit)
        and _descendant_is_evidence_only(root, commit)
    )


def _descendant_is_evidence_only(root: Path, commit: str) -> bool:
    changed = subprocess.run(
        ["git", "diff", "--name-only", "-z", commit, "--"],
        cwd=root, capture_output=True, check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=False,
    )
    if changed.returncode != 0 or untracked.returncode != 0:
        return False
    try:
        paths = {
            item.decode("utf-8", "strict").replace("\\", "/")
            for raw in (changed.stdout, untracked.stdout)
            for item in raw.split(b"\0")
            if item
        }
    except UnicodeDecodeError:
        return False
    return all(
        path in FINAL_EVIDENCE_PATHS or any(path.startswith(prefix) for prefix in FINAL_EVIDENCE_PREFIXES)
        for path in paths
    )


def _hosted_checks_match(check_runs: Any, commit: str) -> bool:
    """Require one successful completed check for every exact hosted gate on the evidence SHA."""
    if not isinstance(check_runs, list):
        return False
    successful: set[str] = set()
    for item in check_runs:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if (
            name in REQUIRED_HOSTED_CHECKS
            and item.get("head_sha") == commit
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
        ):
            successful.add(name)
    return successful == REQUIRED_HOSTED_CHECKS


def _load_hosted_checks(root: Path, commit: str) -> bool:
    gh = shutil.which("gh")
    if gh is None:
        return False
    completed = subprocess.run(
        [
            gh, "api", "--method", "GET",
            "-H", "Accept: application/vnd.github+json",
            f"repos/{{owner}}/{{repo}}/commits/{commit}/check-runs",
            "-f", "per_page=100",
        ],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )
    if completed.returncode != 0:
        return False
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(document, dict) and _hosted_checks_match(document.get("check_runs"), commit)


def _generation_idempotency(root: Path) -> bool:
    """Run the real generators twice in an isolated copy and compare bytes."""
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in {"node_modules", ".git", "__pycache__"}}
    with tempfile.TemporaryDirectory(prefix="ca-pi-generation-") as raw:
        isolated = Path(raw)
        for name in ("core", "plugins", "tools"):
            shutil.copytree(root / name, isolated / name, ignore=ignore)
        if (root / "package.json").is_file():
            shutil.copy2(root / "package.json", isolated / "package.json")
        commands = (
            [sys.executable, "tools/build-surface.py"],
            [sys.executable, "tools/build-host-packages.py"],
        )
        for command in commands:
            if subprocess.run(command, cwd=isolated, capture_output=True, check=False).returncode != 0:
                return False
        first = _tree_digest(isolated)
        for command in commands:
            if subprocess.run(command, cwd=isolated, capture_output=True, check=False).returncode != 0:
                return False
        return _tree_digest(isolated) == first


def _npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _gate_commands() -> tuple[tuple[str, tuple[str, ...]], ...]:
    py, npm = sys.executable, _npm()
    scripts = (
        ("hook-guards", "test_hook_guards.py"), ("hooks-cold-install", "test_hooks_cold_install.py"),
        ("preview-lib", "test_preview_lib.py"), ("ux-conversion", "test_ux_conversion.py"),
        ("prune-nudge", "test_prune_nudge.py"), ("migration-backstop", "test_migration_backstop.py"),
        ("metrics-lib", "test_metrics_lib.py"), ("taskboard-lib", "test_taskboardlib.py"),
        ("taskwriter", "test_taskwriter.py"), ("release-lib", "test_release_lib.py"),
        ("board-sync", "test_board_sync.py"), ("provenance-lib", "test_provenancelib.py"),
        ("provenance-wiring", "test_provenance_wiring.py"), ("readinject-lib", "test_readinjectlib.py"),
        ("pre-read", "test_pre_read.py"), ("hooklib", "test_hooklib.py"),
        ("host-descriptors", "test_host_descriptors.py"), ("pi-package", "test_pi_package.py"),
        ("pi-parity", "test_pi_parity.py"), ("public-pi-docs", "test_public_pi_docs.py"),
        ("public-codex-docs", "test_public_codex_docs.py"),
        ("pi-security", "test_pi_security.py"), ("pi-doctor", "test_pi_doctor.py"),
        ("pi-compaction", "test_pi_compaction_surface.py"), ("prune-policy-parity", "test_prune_policy_parity.py"),
        ("pi-process-tree", "test_pi_process_tree.py", "--fixture-only"),
        ("pi-shared-store", "test_pi_shared_store.py"), ("pi-benchmark-tests", "test_pi_benchmark.py"),
        ("pi-platform-fixtures", "test_pi_platform_contract.py", "--fixtures-only"),
    )
    commands: list[tuple[str, tuple[str, ...]]] = [
        (label, (py, f".github/scripts/{filename}", *args))
        for label, filename, *args in scripts
    ]
    commands.extend((
        ("hook-unittest", (py, "-m", "unittest", "discover", "-s", "plugins/ca/hooks/tests", "-p", "test_*.py")),
        ("ca-tools-typecheck", (npm, "--prefix", "plugins/ca/tools", "run", "typecheck")),
        ("ca-tools", (npm, "--prefix", "plugins/ca/tools", "test")),
        ("pi-tools-typecheck", (npm, "--prefix", "plugins/ca-pi/tools", "run", "typecheck")),
        ("pi-tools", (npm, "--prefix", "plugins/ca-pi/tools", "test")),
        ("sync-core-check", (py, "tools/sync-core.py", "--check")),
        ("surface-check", (py, "tools/build-surface.py", "--check")),
        ("host-packages-check", (py, "tools/build-host-packages.py", "--check")),
        ("plugin-refs-ca", (py, ".github/scripts/check-plugin-refs.py", "ca")),
        ("plugin-refs-codex", (py, ".github/scripts/check-plugin-refs.py", "ca-codex")),
        ("plugin-refs-pi", (py, ".github/scripts/check-plugin-refs.py", "ca-pi")),
        ("license-consistency", (py, ".github/scripts/check_license_consistency.py", ".")),
        ("pi-benchmark", (py, ".github/scripts/pi_benchmark.py", "--samples", "100")),
        ("diff-check", ("git", "diff", "--check")),
    ))
    return tuple(commands)


def real_checks(root: Path, verdict: Verdict) -> tuple[dict[str, tuple[str, ...]], dict[str, bool]]:
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=root, text=True, encoding="utf-8", capture_output=True, check=False).stdout.strip()
    verdict.add(branch == "feat/pi-support", "branch", "feat/pi-support required")
    results: dict[str, bool] = {}
    for label, command in _gate_commands():
        print(f"[RUN] {label}", flush=True)
        completed = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=600, check=False)
        results[label] = completed.returncode == 0
        verdict.add(results[label], label, f"exit {completed.returncode}")
        print(f"[{'PASS' if results[label] else 'FAIL'}] {label}: exit {completed.returncode}", flush=True)

    forbidden_runtime = tuple(root / "plugins" / "ca-pi" / name for name in ("node_modules", "dependencies", "vendor"))
    runtime_clean = all(not path.exists() for path in forbidden_runtime)
    verdict.add(runtime_clean, "Pi runtime tree", "no shipped dependency/runtime tree")
    inventory_clean = all((root / path).is_file() for path in (
        "plugins/ca-pi/extensions/codearbiter.js", "plugins/ca-pi/extensions/codearbiter-child.js",
        "plugins/ca-pi/helpers/windows-supervisor.js", "plugins/ca-pi/generated/roles.json",
    )) and results.get("pi-package", False) and results.get("host-descriptors", False)
    verdict.add(inventory_clean, "package inventory", "exact package/orphan gates")
    verdict.add(results.get("host-descriptors", False), "policy duplication", "descriptor-owned oracle")
    parity = (root / "docs" / "parity.md").read_text(encoding="utf-8")
    unresolved = [line for line in parity.splitlines()
                  if re.search(r"\|\s*(?:OPEN|PENDING|TODO)\s*\|", line, re.I)
                  and "HOSTED_PENDING" not in line]
    parity_clean = not unresolved and results.get("public-pi-docs", False)
    verdict.add(parity_clean, "parity ledger", "only explicit HOST-IMPOSSIBLE/DEGRADED exceptions")
    results["surface-idempotency"] = _generation_idempotency(root)
    results["host-packages-idempotency"] = results["surface-idempotency"]
    verdict.add(results["surface-idempotency"], "generation idempotency", "real generators wrote twice in an isolated tree")
    results["package-inventory"] = inventory_clean
    verdict.add(all(results.values()), "repository-gates", f"{len(results)} canonical gates")
    results["repository-gates"] = all(results.values())
    return {key: tuple(value) for key, value in OBLIGATION_BINDINGS.items()}, results


def verify(root: Path, mode: str, fixture_mode: bool) -> int:
    verdict = Verdict()
    try:
        bindings, check_results = fixture_checks(root, verdict) if fixture_mode else real_checks(root, verdict)
        tasks, obligations, owners = parse_plan(root / ".codearbiter" / "plans" / "pi-support.md")
        if mode == "preclosure":
            tasks_ok = all(tasks.get(number) == "ACCEPTED" for number in range(1, 13)) and tasks.get(13) in {"IN_PROGRESS", "ACCEPTED"} and tasks.get(14) == "IN_PROGRESS"
            task_13_phase_ok = (
                (tasks.get(13) == "IN_PROGRESS" and obligations.get("PI-AC-35") == "OPEN")
                or (tasks.get(13) == "ACCEPTED" and obligations.get("PI-AC-35") == "COVERED")
            )
            obligations_ok = (
                all(obligations.get(f"PI-AC-{number:02d}") == "COVERED" for number in range(1, 35))
                and obligations.get("PI-AC-36") == "COVERED"
                and task_13_phase_ok
                and all(obligations.get(code) == "OPEN" for code in ("PI-AC-37", "PI-AC-38"))
            )
        else:
            tasks_ok = all(tasks.get(number) == "ACCEPTED" for number in range(1, 15))
            obligations_ok = all(obligations.get(code) == "COVERED" for code in OBLIGATIONS)
        verdict.add(tasks_ok, "task statuses", mode)
        verdict.add(obligations_ok, "obligation statuses", mode)
        check_results["statuses"] = tasks_ok and obligations_ok
        check_results["branch"] = True if fixture_mode else subprocess.run(
            ["git", "branch", "--show-current"], cwd=root, text=True, capture_output=True, check=False
        ).stdout.strip() == "feat/pi-support"
        verdict.add(all(owners.get(code) == 1 for code in OBLIGATIONS), "owner inventory", "each obligation owned once")
        document = json.loads((root / "docs" / "reports" / "pi-support" / "promotion.json").read_text(encoding="utf-8"))
        promotion_ok, promotion_detail = strict_promotion(document, mode)
        if promotion_ok and not _promotion_commit_is_valid(root, document, fixture_mode):
            promotion_ok = False
            promotion_detail = promotion_detail if promotion_ok else "promotion commit is not an ancestor of HEAD"
        verdict.add(promotion_ok, "promotion evidence", promotion_detail)
        markdown_path = root / "docs" / "reports" / "pi-support" / "promotion.md"
        markdown_ok = (
            promotion_ok
            and markdown_path.is_file()
            and markdown_path.read_text(encoding="utf-8") == render_promotion_markdown(document)
        )
        verdict.add(markdown_ok, "promotion Markdown", "exact rendering of sanitized promotion.json")
        if not promotion_ok:
            hosted_ok = False
            hosted_detail = "promotion envelope invalid"
        elif document["mode"] == "preclosure":
            hosted_ok = True
            hosted_detail = "explicitly pending until checkpoint PR"
        elif fixture_mode:
            hosted_ok = True
            hosted_detail = "fixture-hosted attestation"
        else:
            hosted_ok = _load_hosted_checks(root, document["commit"])
            hosted_detail = "eight exact successful check runs on evidence commit"
        verdict.add(hosted_ok, "hosted attestation", hosted_detail)
        check_results["promotion"] = promotion_ok
        check_results["promotion-markdown"] = markdown_ok
        check_results["hosted-attestation"] = hosted_ok
        check_results["promotion-security"] = promotion_ok and markdown_ok and hosted_ok
        for code in OBLIGATIONS:
            labels = bindings.get(code, ())
            binding_ok = bool(labels) and all(check_results.get(label) is True for label in labels)
            verdict.add(binding_ok, code, ",".join(labels) if labels else "missing test binding")
        verdict.add(set(bindings) == set(OBLIGATIONS), "binding inventory", "exactly PI-AC-01..38")
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        verdict.add(False, "verifier input", type(error).__name__)
    return verdict.emit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--mode", choices=("preclosure", "final"), required=True)
    parser.add_argument("--fixture-mode", action="store_true")
    args = parser.parse_args()
    return verify(args.root.resolve(), args.mode, args.fixture_mode)


if __name__ == "__main__":
    raise SystemExit(main())
