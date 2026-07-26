#!/usr/bin/env python3
"""Unit tests for the fail-safe CI impact planner.

Run: python .github/scripts/test_ci_impact.py

The planner is intentionally stdlib-only.  These tests keep its classification
contract deterministic and, most importantly, prove that an unrecognised file
selects the broad validation lane instead of silently predicting a skip.
"""
import importlib.util
import json
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "ci-impact.py"
_DESCRIPTORS_TOOL = REPO_ROOT / "tools" / "host_descriptors.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docs.yml"
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
# The one audit threshold every dependency graph in this repo is gated at.
NPM_AUDIT_GATE = "npm audit --omit=dev --audit-level=high"
# Issue #434: the tools graphs declare zero production dependencies, so the
# `--omit=dev` gate above audits an empty graph there. This one covers the build
# toolchain that actually exists - the dev dependencies that produce farm.js,
# sandbox.js, and the ca-pi extension bundles. Same threshold, by contract.
NPM_AUDIT_DEV_GATE = "npm audit --audit-level=high"
PI_PROMOTION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pi-promotion.yml"
PI_TEST_DIR = REPO_ROOT / "plugins" / "ca-pi" / "tools" / "test"
PI_PLATFORM_CONTRACT = REPO_ROOT / ".github" / "scripts" / "test_pi_platform_contract.py"
SANDBOX_LAYERS_TOOL = REPO_ROOT / ".github" / "scripts" / "check_sandbox_docker_layers.py"

# Issue #406: a ca-sandbox suite that spins REAL containers used to carry its
# own private `dockerAvailable()` probe and degrade to `describe.skip` when the
# probe failed - on the REQUIRED CI job too.  The only sanctioned spelling is
# now the shared `dockerGate("<layer>")` helper, which fails hard in required
# mode and records an execution sentinel.  These two shapes are what a
# re-introduced private self-skip looks like.
_PRIVATE_DOCKER_PROBE = re.compile(
    r"(?m)^\s*(?:(?:async\s+)?function\s+dockerAvailable\b"
    r"|const\s+\w+\s*=\s*(?:HAS_DOCKER|dockerAvailable\(\))\s*\?)"
)
# A `docker info` PROBE, as an executed shell command - not the word "docker
# info" inside a YAML comment, which is all the job used to contain.
_DOCKER_PREFLIGHT = re.compile(r"(?m)^\s+(?:if\s+!\s+)?docker info\b")

# `needs.<id>.result` and `needs['<id>'].result` are the two spellings GitHub
# accepts; the aggregate gate uses both depending on whether the job id has a
# hyphen in it.
_NEEDS_RESULT = re.compile(r"needs(?:\.([A-Za-z0-9_-]+)|\['([^']+)'\])\.result")
_JOB_TIMEOUT = re.compile(r"(?m)^    timeout-minutes: (\d+)$")
# GitHub-hosted runners hard-stop a job at 6 hours; a repository-defined bound
# is only meaningful well under that.
HOSTED_JOB_MAXIMUM_MINUTES = 360

# A Pi Vitest file is HOST-DEPENDENT when it compares the *live* process
# platform against a literal.  Two shapes matter and both make a lane on the
# wrong OS unable to attest the file:
#   test.skipIf(process.platform !== "win32")(...)   - the whole test never runs
#   process.platform === "win32" ? "junction" : "dir" - a different OS primitive
# Deliberately NOT matched: an *injected* platform (`buildChildEnv({ platform:
# "win32", ... })`) or one merely forwarded into a pure function
# (`platform: process.platform`).  Those exercise the same code on every host,
# which is exactly what makes them safe to run once on the canonical lane.
_LIVE_PLATFORM_SELECTOR = re.compile(r"(?:process|os)\.platform\s*(?:===|!==)")
# The three-OS fan-out that makes a job able to attest a host-dependent file.
_PLATFORM_MATRIX = "os: [ubuntu-latest, windows-latest, macos-latest]"
# Vitest declaration heads, with their modifier chain (`.skipIf`, `.each`, ...).
_TEST_DECLARATION = re.compile(
    r"(?m)^\s*(?P<kind>describe|test|it)(?P<modifier>(?:\.[A-Za-z]+)*)\s*(?=[(`])"
)
# Modifiers that disable tests unconditionally - at *static* time, with no host
# predicate to satisfy.  `.only` belongs here because it silently disables every
# sibling in the file.  A committed suite carrying any of these is "assigned" to
# a required job while contributing no verdict (issue #405, one level down).
# `.fails` is deliberately absent: it still executes the body and asserts it
# throws, so it is a real verdict.
_STATICALLY_DISABLED = frozenset({"skip", "todo", "only"})


def workflow_jobs(text: str) -> dict[str, str]:
    """Split a workflow's top-level `jobs:` mapping into {job id: raw block}.

    Deliberately textual, like the rest of this repo's workflow contracts - the
    scripts stay stdlib-only, so there is no YAML parser to lean on.
    """
    lines = text.splitlines(keepends=True)
    try:
        start = next(index for index, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:
        return {}
    jobs: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in lines[start + 1:]:
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if header is not None:
            if current is not None:
                jobs[current] = "".join(body)
            current, body = header.group(1), [line]
        elif current is not None:
            body.append(line)
    if current is not None:
        jobs[current] = "".join(body)
    return jobs


def push_trigger_paths(workflow: str) -> list[str]:
    """Quoted globs under the workflow's `on.push.paths:` block.

    Textual like every other contract here.  The block ends at the first line
    that is not a `      - "<glob>"` entry, which is what makes this sensitive
    to a deleted path rather than merely to the block's existence.
    """
    match = re.search(
        r'(?ms)^  push:\n(?:.*?)^    paths:\n(?P<body>(?:      (?:- "[^"\n]+"[^\n]*|#[^\n]*)\n)+)',
        workflow,
    )
    if match is None:
        return []
    return _globs(match.group("body"), '"')


def paths_filter(ci: str, name: str) -> list[str]:
    """Single-quoted globs under one `filters:` entry of the changes job."""
    match = re.search(
        rf"(?ms)^            {re.escape(name)}:\n"
        rf"(?P<body>(?:              (?:- '[^'\n]+'[^\n]*|#[^\n]*)\n)+)",
        ci,
    )
    if match is None:
        return []
    return _globs(match.group("body"), "'")


def _globs(body: str, quote: str) -> list[str]:
    """Quoted list entries in a YAML block, ignoring interleaved comments.

    The value is read out of the quotes rather than by stripping the line,
    because an entry may carry a TRAILING comment - `- "plugins/ca/**" # the
    reference is generated from the plugin` is a real line in docs.yml, and
    stripping quotes off that returns the comment along with the glob.
    """
    found: list[str] = []
    for line in body.splitlines():
        entry = re.match(rf"-\s*{re.escape(quote)}([^{re.escape(quote)}]*){re.escape(quote)}",
                         line.strip())
        if entry is not None:
            found.append(entry.group(1))
    return found


def npm_audit_invocations(workflow: str) -> list[str]:
    """Every `npm audit ...` command line in a workflow, whitespace-normalised."""
    return [
        " ".join(match.group("command").split())
        for match in re.finditer(
            r"(?m)^\s*(?:-\s+)?(?P<command>(?:run: )?npm audit[^\n]*)$", workflow
        )
    ]


def event_trigger_paths(workflow: str, event: str) -> list[str]:
    """Double-quoted globs under `on.<event>.paths` of a workflow."""
    match = re.search(
        rf'(?ms)^  {re.escape(event)}:\n(?:.*?)^    paths:\n'
        rf'(?P<body>(?:      (?:- "[^"\n]+"[^\n]*|#[^\n]*)\n)+)',
        workflow,
    )
    if match is None:
        return []
    return _globs(match.group("body"), '"')


def npm_install_jobs(workflow: str) -> dict[str, str]:
    """Every job that runs `npm ci`, mapped to the directory it installs into.

    Derived from the workflow rather than listed by hand: a hardcoded job list
    is exactly how a newly added graph slips in unaudited, which is the defect
    #403 was.  The directory comes from the job's `defaults.run.working-
    directory`, which is how every npm job in this repo scopes itself.
    """
    installs: dict[str, str] = {}
    for job_id, body in workflow_jobs(workflow).items():
        if not re.search(r"(?m)^\s*(?:-\s+)?(?:run: )?npm ci\b", body):
            continue
        directory = re.search(
            r"(?ms)^    defaults:\n      run:\n        working-directory: (?P<dir>\S+)", body
        )
        installs[job_id] = directory.group("dir") if directory else "."
    return installs


def unaudited_npm_graphs(workflow: str) -> list[str]:
    """Every `npm ci` job whose dependency graph no job in `workflow` audits.

    A job may skip the audit itself - what it may NOT do is install a graph
    nothing audits.  `ca-pi-tools` and docs.yml's `build` are both in that
    first category today: they run `npm ci` with no audit step, and are benign
    only because `ca-pi-checks` and `site-check` audit the very same
    directory.  Deriving the rule this way keeps that fact CHECKED instead of
    asserted in a comment, and makes a brand-new graph fail on arrival.
    """
    jobs = workflow_jobs(workflow)
    installs = npm_install_jobs(workflow)
    audited = {
        directory
        for job_id, directory in installs.items()
        if f"run: {NPM_AUDIT_GATE}" in jobs[job_id]
    }
    return [
        f"{job_id} installs {directory}, which nothing audits"
        for job_id, directory in sorted(installs.items())
        if directory not in audited
    ]


def _fold_keys(value: object, collisions: list[str]) -> object:
    """Lower-case every mapping key, the way gitleaks' own config reader does.

    gitleaks loads this file through viper, whose key lookup is case-
    INSENSITIVE.  Measured against the pinned image: `Paths = ['''.''']`
    reports `scanned ~0 bytes` exactly as `paths` does, `RegexTarget` rebinds
    the waiver exactly as `regexTarget` does, and `DISABLEDRULES` deletes a
    rule exactly as `disabledRules` does.  Every ban below is therefore
    written against folded keys, so a capitalisation cannot walk past it.

    A fold COLLISION (`paths` and `Paths` in one table) is reported rather
    than silently resolved: which spelling the scanner would honour is not
    something this contract should guess at.
    """
    if isinstance(value, dict):
        folded: dict[str, object] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in folded:
                collisions.append(lowered)
            folded[lowered] = _fold_keys(item, collisions)
        return folded
    if isinstance(value, list):
        return [_fold_keys(item, collisions) for item in value]
    return value


def parse_gitleaks_config(config: str) -> tuple[dict, list[str]]:
    """The gitleaks config as gitleaks itself reads it - PARSED, keys folded.

    Reading this file as text was the defect this function exists to end.  A
    regex has to guess at TOML's spellings and it guessed wrong eleven times:
    an indented key, an indented table header, a basic string instead of a
    literal one, a `]` inside a value, a capitalised key.  Every one of those
    was measured GUARD-GREEN while the pinned scanner swallowed a planted
    high-entropy key.  TOML has exactly one meaning per document, so the
    contract now reads that meaning instead of the characters around it.

    Returns the folded document and any key-fold collisions.  Raises
    `tomllib.TOMLDecodeError` on input gitleaks itself could not load.
    """
    collisions: list[str] = []
    document = _fold_keys(tomllib.loads(config), collisions)
    assert isinstance(document, dict)
    return document, collisions


def gitleaks_allowlist_blocks(config: str) -> list[dict]:
    """Every `[[allowlists]]` table in the gitleaks config, keys case-folded."""
    document, _ = parse_gitleaks_config(config)
    blocks = document.get("allowlists") or []
    return [block for block in blocks if isinstance(block, dict)]


def gitleaks_allowlist_regexes(config: str) -> list[str]:
    """Every value inside an allowlist table's `regexes`.

    These are the PARSED values, so the single-entry, multi-line-array,
    embedded-newline, and alternate-quoting spellings all reduce to the same
    list - a waiver cannot hide from the narrowness contract by reformatting.
    The embedded-newline case is real: the one multi-line secret this repo
    waives is a PEM block whose detected value spans five source lines.
    """
    found: list[str] = []
    for block in gitleaks_allowlist_blocks(config):
        entries = block.get("regexes")
        if isinstance(entries, str):
            entries = [entries]
        if isinstance(entries, list):
            found += [entry for entry in entries if isinstance(entry, str)]
    return found


# The characters that would let an anchored waiver match more than the single
# fixed value it spells out.  `\` is in the set because an escape sequence is a
# pattern, and this contract admits no patterns at all.
_REGEX_METACHARACTERS = frozenset(".*+?()[]{}|^$\\")
# `\A<body>\z` - Go RE2's spelling of "the WHOLE target is exactly <body>".
_ANCHORED_WAIVER = re.compile(r"(?s)\A\\A(?P<body>.*)\\z\Z")
# Keys that un-scan a file or a commit rather than waiving one value.
_UNSCANNING_KEYS = ("paths", "commits", "stopwords")
# The only keys a waiver in this file may carry.  DEFAULT-DENY: gitleaks keeps
# adding allowlist knobs, and the next one to widen the haystack must fail this
# contract on the day it is typed, not on the day someone remembers to ban it.
_ALLOWED_ALLOWLIST_KEYS = frozenset({"description", "regexes"})
# `[extend]` selects which rules run.  This file only ever SUBTRACTS fixture
# values from the default ruleset, so `useDefault` is the only key it may set:
# `disabledRules` deletes a rule outright, and `path`/`url` pull in allowlists
# that are not in this file and therefore not covered by anything below.
_ALLOWED_EXTEND_KEYS = frozenset({"usedefault"})


def gitleaks_waiver_violations(config: str) -> list[str]:
    """Every way `config`'s allowlist could waive more than one fixed value.

    Empty means the allowlist is narrow.  Kept a pure function of the config
    text so the contract can be exercised against adversarial configs that are
    never written to disk.

    Each rejected shape below was MEASURED against the pinned scanner image,
    scanning this repo's tracked tree with a high-entropy key planted in
    `plugins/ca/tools/.env.example` (the shipped config reports `leaks found: 1`
    there; every shape below returns it to `no leaks found`):

    * `paths` / `commits` un-scan a whole file or commit rather than waiving a
      value, leaving a permanent blind spot.  `stopwords` is the same class.
    * `regexTarget = "line"` widens the haystack to the entire source line, and
      `regexTarget = "match"` to the rule's whole match text - so a short common
      substring like `API_KEY` waives every line or match containing it.
    * an UNANCHORED literal is the deeper bug, and the reason constraining
      `regexTarget` alone is NOT sufficient: gitleaks tests allowlist regexes
      with Go's `FindString`, a SUBSTRING search, so even against the default
      (secret) target the literal `sk-` waives every secret beginning `sk-`.

    Anchoring is what actually buys narrowness: `\\A<literal>\\z` matches only
    when the ENTIRE detected secret is that exact fixture value.

    The checks run against the PARSED document, not the config text.  Reading
    it as text is what let eleven measured shapes through - see
    test_a_broad_secret_scan_waiver_is_rejected_by_the_narrowness_contract for
    each one and the evidence it swallowed a planted key.
    """
    try:
        document, collisions = parse_gitleaks_config(config)
    except tomllib.TOMLDecodeError as error:
        # Not "narrow" - unreadable.  gitleaks exits FTL on the same input, so
        # reporting no violations here would call a config that cannot scan
        # anything a config that scans everything.
        return [f"the config is not parseable TOML ({error}), so gitleaks cannot load it"]

    problems: list[str] = []
    for key in sorted(set(collisions)):
        problems.append(
            f"`{key}` is spelled two ways in one table; gitleaks reads keys "
            "case-insensitively, so which one applies is unknowable from the file"
        )
    extend = document.get("extend")
    if isinstance(extend, dict):
        for key in sorted(set(extend) - _ALLOWED_EXTEND_KEYS):
            problems.append(
                f"`[extend] {key}` changes which rules run instead of waiving one value; "
                "`useDefault` is the only key this config may set there"
            )
    if document.get("rules"):
        problems.append(
            "a `[[rules]]` block re-declares the ruleset - one whose id matches a default "
            "rule REPLACES it - and this file only ever subtracts fixture values"
        )
    for position, block in enumerate(document.get("allowlists") or [], start=1):
        if not isinstance(block, dict):
            problems.append(f"allowlist #{position} is not a table")
            continue
        description = block.get("description")
        head = str(description).strip().splitlines()[0] if str(description).strip() else ""
        head = head or f"#{position}"
        for key in _UNSCANNING_KEYS:
            if key in block:
                problems.append(
                    f"`{key}` un-scans whole files or commits instead of waiving a value"
                )
        if "regextarget" in block:
            problems.append(
                f"`regexTarget = {block['regextarget']!r}` binds the waiver to surrounding "
                "source text rather than to the detected secret"
            )
        unmodelled = set(block) - _ALLOWED_ALLOWLIST_KEYS - {"regextarget"} - set(_UNSCANNING_KEYS)
        for key in sorted(unmodelled):
            problems.append(
                f"allowlist block at {head!r} sets `{key}`, which this contract cannot "
                "reason about; a waiver may carry only `description` and `regexes`"
            )
        if not str(description or "").strip():
            problems.append(f"allowlist block at {head!r} carries no rationale")
        entries = block.get("regexes")
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, list) or not entries:
            problems.append(f"allowlist block at {head!r} names no value, so it is unbounded")
            continue
        for literal in entries:
            if not isinstance(literal, str):
                problems.append(
                    f"allowlist block at {head!r} waives {literal!r}, which is not a string"
                )
                continue
            anchored = _ANCHORED_WAIVER.match(literal)
            if anchored is None:
                problems.append(
                    f"{literal!r} is not anchored `\\A...\\z`; gitleaks matches allowlist "
                    "regexes as substrings, so it waives anything merely containing it"
                )
                continue
            stray = sorted(set(anchored.group("body")) & _REGEX_METACHARACTERS)
            if stray:
                problems.append(
                    f"{literal!r} carries regex metacharacter(s) {''.join(stray)!r}; "
                    "a waiver must spell out one fixed value"
                )
    return problems


def aggregate_needs(ci: str) -> list[str]:
    """Job ids listed in ci-passed's `needs:` block."""
    aggregate = workflow_jobs(ci).get("ci-passed", "")
    match = re.search(r"(?ms)^    needs:\s*\n(?P<body>(?:      - [A-Za-z0-9_-]+\n)+)", aggregate)
    if match is None:
        return []
    return [line.strip()[2:].strip() for line in match.group("body").splitlines()]


def aggregate_required_results(ci: str) -> list[str]:
    """Job ids whose result the ci-passed gate actually enforces."""
    aggregate = workflow_jobs(ci).get("ci-passed", "")
    match = re.search(r'(?m)^\s+required_results="(?P<body>[^"\n]*)"\s*$', aggregate)
    if match is None:
        return []
    return [first or second for first, second in _NEEDS_RESULT.findall(match.group("body"))]


def unassigned_pi_test_files(ci: str, committed: set[str]) -> set[str]:
    """Committed ca-pi Vitest files no *required* merge-gate job executes.

    A bare `npm test` in a required Pi job covers the whole suite; a filtered
    `npm test -- test/a.test.ts ...` covers only the files it names.  Anything
    left over is a file that can regress with every required check green
    (issue #405).
    """
    jobs = workflow_jobs(ci)
    covered: set[str] = set()
    for job_id in aggregate_required_results(ci):
        if not job_id.startswith("ca-pi"):
            continue
        for match in re.finditer(r"(?m)^\s+run: npm test(?P<rest>[^\n]*)$", jobs.get(job_id, "")):
            rest = match.group("rest").strip()
            if not rest:
                covered |= set(committed)
                continue
            covered |= {
                token.rsplit("/", 1)[-1] for token in rest.split() if token.endswith(".test.ts")
            }
    return set(committed) - covered


def platform_sensitive_pi_test_files() -> set[str]:
    """Committed ca-pi Vitest files whose behaviour is selected by the live OS.

    File-granular assignment (``unassigned_pi_test_files`` above) proves every
    suite runs *somewhere*.  It cannot prove the suite runs where its own
    platform gate opens: a ``test.skipIf(process.platform !== "win32")`` case is
    reported as "assigned" by a Linux-only lane that skips it.  This is the
    second half of the #405 contract.
    """
    return {
        path.name
        for path in PI_TEST_DIR.glob("*.test.ts")
        if _LIVE_PLATFORM_SELECTOR.search(path.read_text(encoding="utf-8"))
    }


def platform_contract_vitest_files() -> set[str]:
    """Vitest files ``test_pi_platform_contract.py`` re-runs inside a matrix cell.

    Read out of the script rather than duplicated here, so moving a file between
    its fixture groups cannot silently desynchronise this contract.
    """
    source = PI_PLATFORM_CONTRACT.read_text(encoding="utf-8")
    return {
        name.rsplit("/", 1)[-1]
        for name in re.findall(r'"(test/[A-Za-z0-9._-]+\.test\.ts)"', source)
    }


def os_matrix_pi_test_files(ci: str, committed: set[str]) -> set[str]:
    """Vitest files a required Pi job executes on *every* supported OS.

    Only a job that fans out over ``_PLATFORM_MATRIX`` counts: a job pinned to
    one runner can never execute the other hosts' gated cases.
    """
    jobs = workflow_jobs(ci)
    covered: set[str] = set()
    for job_id in aggregate_required_results(ci):
        block = jobs.get(job_id, "")
        if not job_id.startswith("ca-pi") or _PLATFORM_MATRIX not in block:
            continue
        for match in re.finditer(r"(?m)^\s+run: npm test(?P<rest>[^\n]*)$", block):
            rest = match.group("rest").strip()
            if not rest:
                covered |= set(committed)
                continue
            covered |= {
                token.rsplit("/", 1)[-1] for token in rest.split() if token.endswith(".test.ts")
            }
        if "test_pi_platform_contract.py" in block:
            covered |= platform_contract_vitest_files()
    return covered


def statically_disabled_pi_tests() -> dict[str, list[str]]:
    """{file: [disabled declarations]} for `.skip` / `.todo` / `.only`.

    These disable a case with no host predicate to satisfy, so the file stays
    "assigned" to a required job while contributing nothing.  A genuine platform
    gate must use ``.skipIf`` / ``.runIf``, which the OS-matrix contract above
    then holds to running somewhere the gate opens.
    """
    disabled: dict[str, list[str]] = {}
    for path in sorted(PI_TEST_DIR.glob("*.test.ts")):
        found = [
            f"{match.group('kind')}{match.group('modifier')}"
            for match in _TEST_DECLARATION.finditer(path.read_text(encoding="utf-8"))
            if _STATICALLY_DISABLED & set(match.group("modifier").split(".")[1:])
        ]
        if found:
            disabled[path.name] = found
    return disabled


_spec = importlib.util.spec_from_file_location("ci_impact", _TOOL)
module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = module
_spec.loader.exec_module(module)


def sandbox_layers_module():
    """The ca-sandbox docker-layer sentinel verifier, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "check_sandbox_docker_layers_ci_impact", SANDBOX_LAYERS_TOOL
    )
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def privately_gated_sandbox_suites() -> dict[str, list[str]]:
    """ca-sandbox test files that still hand-roll their own docker self-skip."""
    layers = sandbox_layers_module()
    offenders: dict[str, list[str]] = {}
    for path in layers.sandbox_test_files(REPO_ROOT):
        found = [
            match.group(0).strip()
            for match in _PRIVATE_DOCKER_PROBE.finditer(path.read_text(encoding="utf-8"))
        ]
        if found:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = found
    return offenders


def hosts():
    spec = importlib.util.spec_from_file_location("host_descriptors_ci_impact", _DESCRIPTORS_TOOL)
    descriptors = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = descriptors
    spec.loader.exec_module(descriptors)
    return descriptors.load_host_descriptors(str(REPO_ROOT))


def map_document():
    return {
        "schema": 1,
        "checks": [
            {
                "id": "broad-lane",
                "lane": "CHECK",
                "scope": "REPO",
                "contract": "Broad validation",
            },
            {
                "id": "pi-adapter",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Adapter contract",
            },
            {
                "id": "pi-latest",
                "lane": "WATCH",
                "scope": "PI",
                "contract": "Upstream compatibility",
            },
            {
                "id": "ca-surface",
                "lane": "CHECK",
                "scope": "CA",
                "contract": "Generated surface",
            },
            {
                "id": "codex-surface",
                "lane": "CHECK",
                "scope": "CDX",
                "contract": "Generated surface",
            },
            {
                "id": "pi-surface",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Generated surface",
            },
        ],
        "edges": [
            {"glob": "plugins/ca-pi/**", "checks": ["pi-adapter", "pi-latest"]},
            {"glob": "core/pysrc/**", "checks": ["broad-lane"]},
            {
                "kind": "descriptor_surface",
                "source_prefix": "core/surface/",
                "checks": {
                    "claude": "ca-surface",
                    "codex": "codex-surface",
                    "pi": "pi-surface",
                },
            },
        ],
    }


def valid_map():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "impact-map.json"
        path.write_text(json.dumps(map_document()), encoding="utf-8")
        return module.load_map(path)


class CheckNameTest(unittest.TestCase):
    def test_render_check_name_uses_the_fixed_tag_grammar(self):
        check = module.Check(
            id="pi-adapter",
            lane="CHECK",
            scope="PI",
            contract="Adapter contract",
            dimensions=("os: Windows", "runtime: Pi 0.80.5"),
        )
        self.assertEqual(
            module.render_check_name(check),
            "[CHECK] | [PI  ] | Adapter contract  <os: Windows · runtime: Pi 0.80.5>",
        )


class EvaluationTest(unittest.TestCase):
    def test_unknown_path_expands_to_the_broad_lane(self):
        result = module.evaluate(
            valid_map(), ["unclassified/new-file.txt"], hosts=()
        )
        self.assertTrue(result.fallback)
        self.assertEqual(result.reason, "unmapped path: unclassified/new-file.txt")
        self.assertEqual([check.id for check in result.selected], ["broad-lane"])

    def test_pi_plugin_change_selects_adapter_and_advisory_contracts(self):
        result = module.evaluate(
            valid_map(), ["plugins/ca-pi/tools/src/index.ts"], hosts=()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )

    def test_multiple_paths_have_a_deterministic_deduplicated_selection(self):
        result = module.evaluate(
            valid_map(),
            ["plugins/ca-pi/tools/src/index.ts", "plugins/ca-pi/extensions/a.ts"],
            hosts=(),
        )
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )


class MapValidationTest(unittest.TestCase):
    def load(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "impact-map.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return module.load_map(path)

    def test_rejects_duplicate_check_ids(self):
        document = map_document()
        document["checks"].append(document["checks"][0].copy())
        with self.assertRaisesRegex(module.ImpactMapError, "duplicate check id"):
            self.load(document)

    def test_rejects_unknown_edge_target(self):
        document = map_document()
        document["edges"][0]["checks"] = ["missing"]
        with self.assertRaisesRegex(module.ImpactMapError, "unknown check"):
            self.load(document)

    def test_rejects_missing_broad_lane(self):
        document = map_document()
        document["checks"] = document["checks"][1:]
        with self.assertRaisesRegex(module.ImpactMapError, "broad-lane"):
            self.load(document)


class DescriptorSurfaceTest(unittest.TestCase):
    def test_codex_host_note_selects_only_codex_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/includes/codex-host-notes.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual([check.id for check in result.selected], ["codex-surface"])

    def test_shared_surface_template_selects_every_host_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/ORCHESTRATOR.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            {check.scope for check in result.selected}, {"CA", "CDX", "PI"}
        )


class WorkflowContractTest(unittest.TestCase):
    def test_every_third_party_action_is_pinned_to_a_commit_sha(self):
        """A `uses:` on a movable tag re-points under us.

        `@v4` and `@main` are branch/tag refs the upstream owner can move at any
        time, so a compromised or merely careless upstream silently changes what
        runs against this repo's checkout with write-capable tokens in scope.
        The repo pins every action by SHA, but nothing asserted it — the
        convention was held up by dependabot plus human review, and a
        hand-edited `@v7` would have passed CI. Local `./...` composites are
        exempt: they are this repo's own tracked files.
        """
        floating = []
        for workflow in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
            for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
                match = re.search(r"^\s*(?:-\s*)?uses:\s*(\S+)", line)
                if match is None:
                    continue
                ref = match.group(1)
                if ref.startswith("./"):
                    continue
                # `- uses: security-extended` inside a `config: |` literal is a
                # CodeQL query-suite entry, not an Actions reference. An Actions
                # `uses:` always names owner/repo; a bare word never does.
                if "/" not in ref:
                    continue
                if re.search(r"@[0-9a-f]{40}$", ref):
                    continue
                floating.append(f"{workflow.name}:{number}: {ref}")
        self.assertEqual(
            floating, [],
            "every third-party `uses:` must pin a 40-hex commit SHA, never a movable tag",
        )

    def test_every_plugin_tools_install_disables_lifecycle_scripts(self):
        """A bare `npm ci` lets any dependency run arbitrary code at install time.

        It matters most where the dev graph's OUTPUT is the product. The
        `plugins/*/tools` trees build the committed `farm.js`, `sandbox.js`,
        and ca-pi extension bundles, so a build-time compromise lands inside a
        reviewed artifact - the blast radius `tech-stack.md`'s CVE gate is
        written about, and the reason those trees are audited dev-inclusive.

        `ca-pi-checks` already passed `--ignore-scripts`; the two jobs that
        actually emit committed bundles did not, and nothing asserted it. The
        convention was held up by whoever wrote the newest job last.

        `site/` is deliberately out of scope: its build output is a static site
        republished from source on every deploy, not a committed artifact, and
        it is excluded from the dev-inclusive audit gate for the same reason.

        Derived from the workflow rather than listed by hand, for exactly the
        reason `npm_install_jobs` is: a hardcoded list is how the next tree
        slips in unguarded.
        """
        scripted = []
        for path in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
            workflow = path.read_text(encoding="utf-8")
            jobs = workflow_jobs(workflow)
            for job_id, directory in sorted(npm_install_jobs(workflow).items()):
                if not directory.startswith("plugins/"):
                    continue
                for line in re.findall(r"(?m)^.*\bnpm ci\b.*$", jobs[job_id]):
                    if "--ignore-scripts" not in line:
                        scripted.append(f"{path.name}: {job_id} ({directory}): {line.strip()}")
        self.assertEqual(
            scripted, [],
            "every `npm ci` installing a plugins/*/tools graph must pass --ignore-scripts",
        )

    def test_ci_runs_impact_planner_without_replacing_existing_job_conditions(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            ci,
        )
        self.assertIn("cancel-in-progress: true", ci)
        self.assertIn("id: impact", ci)
        self.assertIn("python tools/ci-impact.py", ci)
        self.assertIn("list-files: shell", ci)
        self.assertIn("impact: ${{ steps.filter.outputs.impact }}", ci)
        self.assertIn("needs.changes.outputs.impact == 'true'", ci)
        self.assertIn("needs.changes.outputs.ca-pi == 'true'", ci)

    def test_ci_uses_the_typed_check_name_schema_for_every_owned_job(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        expected = (
            "[CHECK] | [REPO] | Impact selection",
            "[CHECK] | [REPO] | Impact planner contract",
            "[CHECK] | [CORE] | Host descriptor contract",
            "[CHECK] | [CA  ] | Farm dispatcher contract",
            "[CHECK] | [SBX ] | Sandbox driver contract",
            "[CHECK] | [PI  ] | Host-independent adapter contract",
            "[CHECK] | [PI  ] | Adapter contract  <os: ${{ matrix.os }} · runtime: Pi ${{ matrix.pi-version }}>",
            "[WATCH] | [PI  ] | Upstream compatibility  <runtime: npm latest>",
            "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>",
            "[CHECK] | [CORE] | Hook contract  <os: ${{ matrix.os }}>",
            "[GATE ] | [CA  ] | Payload version",
            "[GATE ] | [SBX ] | Payload version",
            "[GATE ] | [CDX ] | Payload version",
            "[GATE ] | [PI  ] | Payload version",
            "[CHECK] | [CA  ] | Reference graph",
            "[CHECK] | [CA  ] | Documentation consistency",
            "[CHECK] | [SBX ] | Reference graph",
            "[CHECK] | [REPO] | Manifest contract",
            "[CHECK] | [REPO] | License consistency",
            "[CHECK] | [CORE] | Generated surface",
            "[CHECK] | [CDX ] | Reference graph",
            "[CHECK] | [REPO] | Secret scan",
            "[GATE ] | [REPO] | Merge readiness",
        )
        for name in expected:
            self.assertIn(f'name: "{name}"', ci)

    def test_the_required_sandbox_job_fails_when_docker_is_unavailable(self):
        # Issue #406 AC-1/AC-2.  ca-sandbox is the driver that clones UNTRUSTED
        # repositories, and every real-container suite used to convert a failed
        # `docker info` probe into `describe.skip` - on the required merge-gate
        # job too.  A runner Docker outage therefore removed the ONLY isolation,
        # mount, network, lifecycle and teardown evidence while the board went
        # green off pure argv-builder tests.  The required job must now (a)
        # preflight the daemon BEFORE the suite and exit non-zero without it,
        # and (b) run the suite in docker-REQUIRED mode so a daemon that dies
        # mid-run fails the file instead of skipping it.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ca-sandbox-tools", aggregate_required_results(ci))
        job = workflow_jobs(ci)["ca-sandbox-tools"]
        suite = job.find("run: npm test")
        self.assertNotEqual(suite, -1, "the sandbox job no longer runs `npm test`")
        probe = _DOCKER_PREFLIGHT.search(job)
        self.assertIsNotNone(probe, "the sandbox job runs no `docker info` preflight command")
        self.assertLess(
            probe.start(), suite, "the docker preflight must run BEFORE the sandbox suite"
        )
        self.assertIn(
            "exit 1",
            job[probe.start():suite],
            "the docker preflight does not fail the job when the daemon is unavailable",
        )
        self.assertIn(
            'CA_SANDBOX_REQUIRE_DOCKER: "1"',
            job,
            "the required sandbox suite does not run in docker-REQUIRED mode",
        )

    def test_the_required_sandbox_job_asserts_a_real_container_execution_sentinel(self):
        # Issue #406 AC-3.  A preflight only proves the daemon answered once.
        # The required job must additionally prove that every docker-gated
        # layer actually EXECUTED, so a suite that silently stops registering
        # (a bad filter, a renamed file, a gate left inert) cannot pass.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = workflow_jobs(ci)["ca-sandbox-tools"]
        suite = job.find("run: npm test")
        self.assertIn(
            "CA_SANDBOX_DOCKER_SENTINEL",
            job,
            "the sandbox suite records no machine-checkable execution sentinel",
        )
        verifier = job.find("check_sandbox_docker_layers.py")
        self.assertNotEqual(verifier, -1, "the sandbox job never asserts the layer sentinel")
        self.assertGreater(
            verifier, suite, "the layer sentinel must be asserted AFTER the suite runs"
        )

    def test_every_real_container_sandbox_suite_routes_through_the_shared_docker_gate(self):
        # The contract above is only worth as much as the gate's reach: a suite
        # keeping its own `dockerAvailable()` + `describe.skip` pair opts itself
        # back out of required mode AND contributes no sentinel line, which is
        # exactly the #406 hole one file at a time.
        self.assertEqual(
            privately_gated_sandbox_suites(),
            {},
            "ca-sandbox suites still self-skipping outside the shared docker gate",
        )
        layers = sandbox_layers_module().declared_layers(REPO_ROOT)
        self.assertTrue(layers, "no dockerGate() layers found - the scan is wrong")
        # The containment guarantees the sandbox actually advertises. Each is a
        # real-container suite, so each must be a sentinel-bearing layer.
        for required in ("isolation", "lifecycle", "network", "run"):
            self.assertIn(
                required,
                layers,
                f"the {required!r} real-container layer is not behind the shared docker gate",
            )

    def test_every_committed_pi_test_file_runs_in_a_required_merge_gate_job(self):
        # Issue #405: the six-cell matrix named 6 of the 23 committed Vitest
        # files, so a PR could regress policy/plan-mode/dispatch/background-jobs/
        # windows-supervisor with every required check green.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        self.assertTrue(committed, "no ca-pi Vitest files found - the glob is wrong")
        self.assertEqual(
            sorted(unassigned_pi_test_files(ci, committed)),
            [],
            "committed ca-pi test files that no required merge-gate job executes",
        )

    def test_the_pi_suite_partition_contract_fails_when_the_full_suite_run_is_removed(self):
        # AC-2 of #405: the contract above must BITE, not merely pass because
        # one job happens to run everything.  Neutering the unfiltered run has
        # to leave test files unassigned.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        jobs = workflow_jobs(ci)
        mutated, neutered_jobs = ci, []
        for job_id in aggregate_required_results(ci):
            if not job_id.startswith("ca-pi"):
                continue
            block = jobs[job_id]
            neutered = re.sub(r"(?m)^(\s+)run: npm test$", r"\1run: echo npm test", block)
            if neutered != block:
                mutated = mutated.replace(block, neutered, 1)
                neutered_jobs.append(job_id)
        self.assertNotEqual(
            neutered_jobs, [], "no required ca-pi job runs the unfiltered `npm test` suite"
        )
        self.assertTrue(
            unassigned_pi_test_files(mutated, committed),
            "removing the full-suite run left every Pi test file still assigned",
        )

    def test_every_platform_gated_pi_test_file_runs_on_every_supported_os(self):
        # Issue #405, second half / issue #390 AC-2.  File-granular assignment
        # is blind to a test's own platform gate: a Linux-only lane reports
        # activation.test.ts as "assigned" while
        # `test.skipIf(process.platform !== "win32")` at line 388 silently skips
        # the only case that reads the fixed user-global update cache.  Any file
        # that branches on the LIVE platform must therefore run in a job that
        # fans out over all three operating systems, or its Windows/macOS branch
        # is attested by nothing.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        sensitive = platform_sensitive_pi_test_files()
        self.assertTrue(sensitive, "no platform-gated Pi test files found - the scan is wrong")
        self.assertLessEqual(
            sensitive,
            committed,
            "the platform scan drifted off the committed Vitest set",
        )
        self.assertEqual(
            sorted(sensitive - os_matrix_pi_test_files(ci, committed)),
            [],
            "Pi test files that branch on the live platform but run on one OS only",
        )

    def test_the_platform_gate_contract_binds_to_the_three_os_fan_out(self):
        # The contract above must BITE on each way it can be broken.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        committed = {path.name for path in PI_TEST_DIR.glob("*.test.ts")}
        covered = os_matrix_pi_test_files(ci, committed)
        self.assertTrue(covered, "no required Pi job fans out over the OS matrix")
        # (a) A host-INDEPENDENT suite is not credited with OS coverage, so a
        #     future win32-gated test added to one would be caught.
        self.assertNotIn("policy.test.ts", covered)
        self.assertNotIn("policy.test.ts", platform_sensitive_pi_test_files())
        # (b) Collapsing the fan-out to a single runner uncovers everything.
        collapsed = ci.replace(_PLATFORM_MATRIX, "os: [ubuntu-latest]", 1)
        self.assertEqual(os_matrix_pi_test_files(collapsed, committed), set())
        # (c) Dropping one file from the matrix step uncovers exactly that file.
        without = ci.replace(" test/activation.test.ts", "", 1)
        self.assertEqual(
            covered - os_matrix_pi_test_files(without, committed), {"activation.test.ts"}
        )

    def test_no_committed_pi_test_is_disabled_by_a_static_skip_todo_or_only(self):
        # Issue #405, the "assigned but inert" hole: `npm test` makes every file
        # a required gate, but a `test.skip` / `test.todo` inside one - or a
        # single `test.only`, which mutes every sibling - keeps the board green
        # with no verdict behind it.  A platform gate must be expressed as
        # `.skipIf` / `.runIf` so the OS-matrix contract above can hold it.
        self.assertEqual(
            statically_disabled_pi_tests(),
            {},
            "ca-pi Vitest declarations disabled with no host predicate to satisfy",
        )

    def test_host_independent_pi_job_is_registered_in_both_needs_and_required_results(self):
        # Issue #390 CRITICAL: `ci-passed` enforces jobs through TWO
        # independent registrations - the `needs:` list (which makes it wait)
        # and the `required_results` string (which makes it care).  Adding a
        # job to one and not the other silently drops the verdict and nothing
        # else in CI notices.  This asserts both exist AND that they agree for
        # every job, with exactly one sanctioned exception: the advisory
        # ca-pi-latest canary is intentionally awaited but not enforced.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ca-pi-checks", sorted(workflow_jobs(ci)))
        needs = aggregate_needs(ci)
        required = aggregate_required_results(ci)
        self.assertIn("ca-pi-checks", needs, "ci-passed.needs is missing ca-pi-checks")
        self.assertIn(
            "ca-pi-checks", required, "ci-passed.required_results is missing ca-pi-checks"
        )
        self.assertEqual(
            sorted(set(needs) - set(required)),
            ["ca-pi-latest"],
            "awaited but unenforced jobs (only the advisory Pi canary may appear here)",
        )
        self.assertEqual(
            sorted(set(required) - set(needs)),
            [],
            "enforced jobs the aggregate never waits for",
        )

    def test_host_independent_pi_checks_run_once_outside_the_platform_matrix(self):
        # Issue #390: every one of these consumes neither matrix.os nor
        # matrix.pi-version, so six cells produced six identical verdicts.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        self.assertIn("ca-pi-checks", sorted(jobs))
        canonical, matrix = jobs["ca-pi-checks"], jobs["ca-pi-tools"]
        self.assertNotIn("strategy:", canonical, "the canonical Pi job must not fan out")
        self.assertIn("runs-on: ubuntu-latest", canonical)
        for token in (
            "run: python tools/build-host-packages.py --check",
            "run: npm run typecheck",
            "run: npm run build",
            "run: python .github/scripts/test_pi_security.py",
            "run: python .github/scripts/test_pi_parity.py",
            "run: python .github/scripts/pi_benchmark.py --samples 100",
        ):
            with self.subTest(token=token):
                self.assertIn(token, canonical, f"ca-pi-checks must own `{token}`")
                self.assertNotIn(token, matrix, f"ca-pi-tools still repeats `{token}` per cell")
        # Everything whose verdict genuinely depends on the installed Pi
        # version or the host OS stays in the six-cell matrix.
        for token in (
            "os: [ubuntu-latest, windows-latest, macos-latest]",
            "npm install --global @earendil-works/pi-coding-agent@${{ matrix.pi-version }}",
            "run: npm test -- test/package.test.ts",
            "run: python .github/scripts/test_pi_package.py --rpc-commands",
            "--pi-version ${{ matrix.pi-version }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, matrix, f"ca-pi-tools must keep `{token}`")

    def test_every_pi_ci_and_promotion_job_declares_a_bounded_timeout(self):
        # Issue #399: a wedged npm install or leaked process otherwise holds a
        # hosted runner until GitHub's platform maximum.
        missing: list[str] = []
        unbounded: list[str] = []
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        candidates = [
            (".github/workflows/ci.yml", job_id, block)
            for job_id, block in workflow_jobs(ci).items()
            if "[PI  ]" in block
        ]
        promotion = PI_PROMOTION_WORKFLOW.read_text(encoding="utf-8")
        candidates += [
            (".github/workflows/pi-promotion.yml", job_id, block)
            for job_id, block in workflow_jobs(promotion).items()
        ]
        self.assertGreaterEqual(len(candidates), 8, "the Pi job scan found too few jobs")
        for workflow, job_id, block in candidates:
            declared = _JOB_TIMEOUT.search(block)
            if declared is None:
                missing.append(f"{workflow}:{job_id}")
                continue
            if not 0 < int(declared.group(1)) < HOSTED_JOB_MAXIMUM_MINUTES:
                unbounded.append(f"{workflow}:{job_id}={declared.group(1)}")
        self.assertEqual(missing, [], "Pi jobs with no timeout-minutes")
        self.assertEqual(unbounded, [], "Pi job timeouts at or above the hosted maximum")

    def test_pi_upstream_canary_concludes_advisory_rather_than_failed(self):
        # Issue #381: the WATCH lane reports upstream incompatibility; that is
        # its signal, not its failure.  Expected incompatibility is absorbed at
        # STEP level so the check concludes green, while a break in the canary
        # HARNESS still turns it red - which is why there is no job-level
        # continue-on-error to swallow it.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        canary = workflow_jobs(ci)["ca-pi-latest"]
        self.assertIsNone(
            re.search(r"(?m)^    continue-on-error: true$", canary),
            "job-level continue-on-error hides canary harness failures",
        )
        for probe in ("id: admission", "id: platform-contract"):
            self.assertIn(probe, canary, f"the canary must address its probe step: {probe}")
        self.assertEqual(
            len(re.findall(r"(?m)^        continue-on-error: true$", canary)),
            2,
            "exactly the two upstream-compatibility probes absorb their own failure",
        )
        # The harness (toolchain + latest-Pi install) must NOT be absorbed.
        harness = re.search(
            r"(?ms)^      - name: Install reviewed toolchain and external latest Pi.*?(?=^      - name: )",
            canary,
        )
        self.assertIsNotNone(harness, "canary harness install step is missing")
        self.assertNotIn("continue-on-error", harness.group(0))
        self.assertIn("if: always()", canary, "the advisory receipt must always publish")
        self.assertIn("GITHUB_STEP_SUMMARY", canary, "the advisory verdict must be visible")
        # And the aggregate gate stays independent of the advisory result.
        self.assertNotIn("ca-pi-latest", aggregate_required_results(ci))

    def test_codex_parity_fixture_edits_reach_their_own_test(self):
        # Issue #384: `.github/scripts/test_codex_parity_fixture.py` runs inside
        # the path-scoped `hooks` job, but neither the push trigger nor the
        # `hooks` filter listed the generator it tests.  A PR editing only
        # tools/codex-parity-fixture.py therefore skipped its own test, and the
        # merged push started no workflow at all.  Three registrations must
        # agree: push trigger, `hooks` filter, and the test invocation.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        generator = "tools/codex-parity-fixture.py"
        push = push_trigger_paths(ci)
        self.assertIn(
            "tools/sync-core.py", push, "the push-trigger scan drifted off the real block"
        )
        self.assertIn(generator, push, "a push of the fixture generator starts no CI run")
        hooks = paths_filter(ci, "hooks")
        self.assertIn(
            ".github/scripts/**", hooks, "the hooks-filter scan drifted off the real block"
        )
        self.assertIn(
            generator, hooks, "a PR touching only the fixture generator skips the hooks job"
        )
        self.assertIn(
            "run: python .github/scripts/test_codex_parity_fixture.py",
            workflow_jobs(ci)["hooks"],
            "the hooks job no longer runs the fixture generator's own test",
        )

    def test_the_version_gates_ask_payload_scope_not_the_whole_plugin_directory(self):
        """Issue #435 AC-3, workflow half.

        `test_payload_scope.py` pins the RULE; this pins that the gates actually
        USE it. A version gate that quietly reverts to `git diff -- plugins/ca`
        would pass every test in that file while reinstating the tax."""
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        for job_id, plugin in (("version-bump", "plugins/ca"),
                               ("version-bump-sandbox", "plugins/ca-sandbox")):
            with self.subTest(job=job_id):
                body = jobs[job_id]
                self.assertIn(
                    f"payload_scope.py --plugin {plugin}",
                    body,
                    f"{job_id} no longer asks payload_scope.py what shipped",
                )
                self.assertNotIn(
                    f'git diff --quiet "origin/$BASE"...HEAD -- {plugin};',
                    body,
                    f"{job_id} reverted to the wholesale pre-#435 scope",
                )
        # ca-pi's gate lives in build-host-packages.py rather than inline shell,
        # so the same exclusion is asserted at its source.
        guard = (REPO_ROOT / "tools" / "build-host-packages.py").read_text(encoding="utf-8")
        self.assertIn('":(exclude)plugins/ca-pi/tools"', guard)

    def test_every_declared_shipped_artifact_has_a_staleness_gate(self):
        """Issues #377 / #407: a committed bundle that nothing rebuild-checks rots.

        Derived from payload_scope's declaration rather than a hardcoded list, so
        adding a third shipped artifact fails HERE until its gate exists, instead
        of shipping unchecked. That declaration is already the thing the payload
        gate keys on, so the two cannot disagree about what ships."""
        sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))
        import payload_scope

        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        for plugin, artifacts in payload_scope.SHIPPED_TOOLS_ARTIFACTS.items():
            for artifact in artifacts:
                name = artifact.rsplit("/", 1)[-1]
                with self.subTest(artifact=artifact):
                    self.assertIn(
                        f'git diff --quiet -- "$artifact"' if name != "farm.js" else "git diff --quiet -- farm.js",
                        ci,
                        f"{artifact} has no staleness gate in ci.yml",
                    )
                    self.assertIn(
                        name, ci, f"{name} is never named in ci.yml, so nothing rebuild-checks it"
                    )

    def test_every_npm_audit_gate_fails_the_build_on_a_high_advisory(self):
        # Issue #403: site/package-lock.json - the ONLY graph in this repo that
        # declares production dependencies (astro, starlight, markdown-remark) -
        # was audited by nothing, and #400's three HIGH advisories all lived
        # there.
        #
        # Issue #434 closed the other half.  `--omit=dev` on the three tools
        # graphs audits an EMPTY graph: each declares zero production
        # dependencies, so that gate saw nothing at any threshold.  Every
        # package in those trees is a dev dependency, and they are the ones that
        # build farm.js, sandbox.js, and the ca-pi extension bundles - committed,
        # shipped artifacts.  GHSA-r28c-9q8g-f849 (postcss, HIGH) sat in
        # plugins/ca/tools reported as zero vulnerabilities by the omit-dev gate
        # against both the vulnerable AND the fixed lockfile; it surfaced only
        # because dependabot happened to file the bump.
        #
        # So each tools graph now carries TWO audits: the durability gate for
        # the day it takes on a runtime dependency, and the dev-inclusive gate
        # that covers the toolchain actually present.  ONE THRESHOLD across all
        # of them - that is the invariant this asserts.
        invocations: list[tuple[str, str]] = []
        for workflow in (CI_WORKFLOW, DOCS_WORKFLOW):
            invocations += [
                (workflow.name, command)
                for command in npm_audit_invocations(workflow.read_text(encoding="utf-8"))
            ]
        self.assertEqual(
            sorted(command for _, command in invocations),
            sorted(
                # farm, sandbox, ca-pi: production-durability gate ...
                [f"run: {NPM_AUDIT_GATE}"] * 3
                # ... plus the dev-inclusive gate that covers the real toolchain
                + [f"run: {NPM_AUDIT_DEV_GATE}"] * 3
                # site: the one graph with production dependencies (docs.yml)
                + [f"run: {NPM_AUDIT_GATE}"]
            ),
            "expected a production and a dev-inclusive audit on each tools graph, "
            "plus the site production audit",
        )
        for name, command in invocations:
            with self.subTest(workflow=name, command=command):
                self.assertRegex(
                    command,
                    r"--audit-level=high$",
                    "every audit gate in the repo must use the SAME threshold",
                )

    def test_each_plugin_tools_graph_is_audited_with_dev_dependencies_included(self):
        """Issue #434 AC-1: a HIGH advisory in a `plugins/*/tools` DEV dependency
        must fail CI.

        Asserted per job rather than by counting lines, so a dev gate that is
        deleted from one graph - or a fourth tools graph added without one -
        fails here rather than passing on an unchanged total."""
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        installs = npm_install_jobs(ci)
        tools_graphs = {
            job_id: directory
            for job_id, directory in installs.items()
            if re.fullmatch(r"plugins/[^/]+/tools", directory)
        }
        self.assertTrue(tools_graphs, "no plugins/*/tools graph found in ci.yml")
        # Every tools graph must be dev-audited by SOME job (ca-pi-tools installs
        # the same directory ca-pi-checks audits, exactly as the omit-dev rule
        # above already allows).
        dev_audited = {
            directory
            for job_id, directory in installs.items()
            if f"run: {NPM_AUDIT_DEV_GATE}" in jobs[job_id]
        }
        for job_id, directory in sorted(tools_graphs.items()):
            with self.subTest(job=job_id, directory=directory):
                self.assertIn(
                    directory,
                    dev_audited,
                    f"{job_id} installs {directory}, whose dev dependencies build a "
                    f"committed artifact, but nothing audits them",
                )
        # EVERY GRAPH THIS REPO INSTALLS IS AUDITED SOMEWHERE.  This used to
        # iterate the hardcoded triple ("tools", "ca-sandbox-tools",
        # "ca-pi-checks") under a comment claiming "every job that installs a
        # lockfile must also audit it" - a claim three job names cannot make.
        # It was already false: `ca-pi-tools` is a required gate that runs
        # `npm ci` and never audits, and so does docs.yml's `build`.  Both are
        # benign only because a SIBLING job audits the same lockfile, and
        # nothing checked that.  So the list is now DERIVED and the rule is the
        # one that actually matters: a job may skip the audit only when another
        # job in the same workflow audits the very directory it installs.  A
        # genuinely new graph has no such sibling and fails here on arrival -
        # which is precisely what did not happen when site/package-lock.json
        # went unguarded through #400 and #403.
        for workflow in (CI_WORKFLOW, DOCS_WORKFLOW):
            with self.subTest(workflow=workflow.name):
                text = workflow.read_text(encoding="utf-8")
                self.assertTrue(
                    npm_install_jobs(text), f"{workflow.name} installs no lockfile at all"
                )
                self.assertEqual(
                    [],
                    unaudited_npm_graphs(text),
                    "a job installs a dependency graph nothing in this workflow audits",
                )
        # And the rule BITES.  A derived check that merely happens to be
        # satisfied is indistinguishable from one that checks nothing, so put
        # the diff it exists to stop in front of it: a new job installing a
        # graph no sibling audits.  This is the shape #403 shipped as.
        newcomer = CI_WORKFLOW.read_text(encoding="utf-8") + (
            "\n  brand-new-graph:\n"
            "    name: newcomer\n"
            "    runs-on: ubuntu-latest\n"
            "    defaults:\n"
            "      run:\n"
            "        working-directory: plugins/ca-brand-new/tools\n"
            "    steps:\n"
            "      - run: npm ci\n"
        )
        self.assertTrue(
            unaudited_npm_graphs(newcomer),
            "a job installing an entirely new graph is accepted without an audit",
        )

    def test_docs_workflow_gates_the_site_dependency_graph_before_publishing(self):
        # Issue #403: site-check ran npm ci/typecheck/test and build ran
        # build/link-audit, but nothing ever audited site/package-lock.json - a
        # known-vulnerable production dependency could build and deploy to
        # GitHub Pages with the whole workflow green.
        docs = DOCS_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(docs)
        self.assertIn("site-check", sorted(jobs))
        site_check = jobs["site-check"]
        self.assertIn("run: npm ci", site_check)
        self.assertIn("run: npm audit --omit=dev --audit-level=high", site_check)
        # The audit is only a gate if the publish step waits on the job that
        # runs it.  `deploy` needs BOTH build and site-check today; assert the
        # site-check edge specifically so dropping it is caught.
        deploy = jobs["deploy"]
        self.assertRegex(
            deploy,
            r"(?m)^    needs: \[[^\]]*\bsite-check\b[^\]]*\]",
            "deploy no longer waits on the audited site-check job",
        )

    def test_the_docs_workflow_runs_on_changes_to_the_docs_workflow(self):
        # The SAME defect class this branch exists to fix, one file over.
        # docs.yml triggered on `site/**` and `plugins/ca/**` only, so it never
        # ran on itself: the audit step added above did NOT execute in this
        # PR's own CI - there was no `Site |` check among the 37 that reported.
        # A PR that deletes the audit step, breaks the deploy edge, or drops a
        # permission touches docs.yml and nothing else, which is exactly the
        # diff its own jobs could not see.  #384 and the .gitleaks.toml gap are
        # the same bug; a workflow that gates something must be reachable by a
        # change to itself.
        docs = DOCS_WORKFLOW.read_text(encoding="utf-8")
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                paths = event_trigger_paths(docs, event)
                self.assertIn(
                    "site/**", paths, f"the {event} trigger scan drifted off the real block"
                )
                self.assertIn(
                    ".github/workflows/docs.yml",
                    paths,
                    f"a {event} touching only docs.yml never runs docs.yml",
                )

    def test_ci_runs_a_pinned_read_only_secret_scan_wired_into_the_merge_gate(self):
        # Issue #404: the repository had NO independent secret scanner - only a
        # manual staged-diff sweep and the cooperative local H-10b hook, neither
        # of which a bot, a fork, or a direct push ever runs.  The hosted
        # backstop must be pinned (no floating tag can be swapped under us),
        # read-only, and enforced by the aggregate gate.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        self.assertIn("secret-scan", sorted(jobs), "ci.yml has no secret-scan job")
        job = jobs["secret-scan"]
        self.assertIn('name: "[CHECK] | [REPO] | Secret scan"', job)
        # Pinned by image digest, not by a mutable tag.
        self.assertRegex(
            job,
            r"ghcr\.io/gitleaks/gitleaks@sha256:[0-9a-f]{64}",
            "the scanner image is not pinned by digest",
        )
        self.assertNotRegex(
            job,
            r"ghcr\.io/gitleaks/gitleaks:[^@\s]",
            "a floating image tag defeats the pin",
        )
        # Read-only: the repository is mounted `:ro` and the scanner gets no
        # network, so a supply-chain compromise of the image cannot rewrite the
        # tree it is auditing or exfiltrate what it finds.
        self.assertIn(":/repo:ro", job, "the scanned tree is not mounted read-only")
        self.assertIn("--network none", job, "the scanner is not network-isolated")
        self.assertIn("--redact", job, "a finding would print the credential in public logs")
        self.assertIn("--exit-code 1", job, "a finding would not fail the job")
        self.assertIn("--config /repo/.gitleaks.toml", job)
        # ACTIONABLE WITHOUT LEAKING.  `--redact` alone prints only
        # `leaks found: N` - no file, no line, no rule id - so a red job tells a
        # maintainer nothing and the only way to triage it is to re-run the
        # scanner unredacted.  Measured against the pinned image: adding
        # `--verbose` prints `File:`/`Line:`/`RuleID:`/`Fingerprint:` (and
        # `Commit:` in git mode) while still printing `Secret: REDACTED`.  Every
        # scan step must carry BOTH, so neither mode is a dead end.
        scan_steps = [step for step in job.split("\n      - name: ") if '"$GITLEAKS_IMAGE"' in step]
        self.assertEqual(
            len(scan_steps), 2, "expected exactly the tree scan and the commit-range scan"
        )
        for step in scan_steps:
            with self.subTest(step=step.splitlines()[0]):
                self.assertIn("--redact", step, "this scan would print credentials in public logs")
                self.assertIn(
                    "--verbose",
                    step,
                    "a failing scan would print only `leaks found: N` - no file, line, or rule",
                )
        # Enforced through BOTH aggregate registrations (the #390 contract).
        self.assertIn("secret-scan", aggregate_needs(ci), "ci-passed.needs omits secret-scan")
        self.assertIn(
            "secret-scan",
            aggregate_required_results(ci),
            "ci-passed.required_results omits secret-scan",
        )

    def test_the_secret_scan_allowlist_stays_narrow_and_value_scoped(self):
        # A broad ignore defeats the whole job, and in gitleaks the broad ignore
        # is `paths`: a global `paths = [...]` entry does not waive a finding,
        # it drops the file from the scan entirely.  Measured against the pinned
        # image - a config whose sole waiver was
        # `paths = ['''^test_hooklib\\.py$''']` (condition = "AND", plus a regex
        # matching nothing) reported `scanned ~189 bytes` and missed a freshly
        # planted `aws_secret_access_key = "kR3m..."` in that file.  So every
        # waiver here must be a VALUE waiver naming one fixed adversarial
        # literal, which leaves every file fully scanned.
        self.assertTrue(GITLEAKS_CONFIG.is_file(), "no .gitleaks.toml in the repo root")
        config = GITLEAKS_CONFIG.read_text(encoding="utf-8")
        document, collisions = parse_gitleaks_config(config)
        self.assertEqual([], collisions, "a key is spelled two ways in one table")
        # Read from the PARSE, not from the text: `assertIn("useDefault = true")`
        # is satisfied by that string appearing in a comment and defeated by a
        # different spacing, and neither has anything to do with what gitleaks
        # loads.
        self.assertIs(
            document.get("extend", {}).get("usedefault"),
            True,
            "the config must extend the default ruleset",
        )
        blocks = gitleaks_allowlist_blocks(config)
        self.assertEqual(
            len(blocks),
            len(re.findall(r"(?m)^\s*\[\[\s*allowlists\s*\]\]\s*$", config)),
            # Text and parse must agree on how many waivers exist.  They can
            # disagree: `allowlists = [{...}]` is a valid TOML array-of-tables
            # that a header count cannot see - and, measured against the pinned
            # image, one gitleaks silently IGNORES.  A waiver the scanner does
            # not honour and the reader believes in is its own kind of hole.
            "the allowlist block count disagrees with the table headers in the file",
        )
        self.assertTrue(blocks, "no allowlist blocks found")
        regexes = gitleaks_allowlist_regexes(config)
        self.assertTrue(regexes, "the allowlist waives no concrete value")
        # NARROWNESS ITSELF.  Being a fixed literal is NOT enough - that was the
        # hole in the first version of this contract.  gitleaks substring-matches
        # allowlist regexes, so the fixed literal `sk-` waives every secret that
        # starts with it, and `regexTarget = "line"` makes any short literal a
        # substring test against every scanned line.  Each waiver must be
        # `\A<literal>\z`, true only when the WHOLE detected secret is that exact
        # fixture value.  The adversarial shapes this rejects - and the measured
        # evidence that each one really does swallow a planted credential - are
        # in test_a_broad_secret_scan_waiver_is_rejected_by_the_narrowness_contract.
        self.assertEqual(
            gitleaks_waiver_violations(config),
            [],
            "the allowlist can waive more than the fixture values it names",
        )
        # The two credential-shaped-but-benign payload files the audit named are
        # covered by the literals they carry, and named in the rationale so a
        # reviewer can check the claim.
        self.assertIn("plugins/ca/hooks/secret-detection-corpus.json", config)
        self.assertIn("plugins/ca/tools/.env.example", config)
        corpus = json.loads(
            (REPO_ROOT / "plugins/ca/hooks/secret-detection-corpus.json").read_text(
                encoding="utf-8"
            )
        )
        # Every waiver is `\A<value>\z`; compare on the anchored body so what is
        # being checked is "this exact value", not "something resembling it".
        waived = {_ANCHORED_WAIVER.match(literal).group("body") for literal in regexes}
        self.assertTrue(
            {literal for literal in waived if any(literal in row for row in corpus["must_match"])},
            "no corpus literal is waived - the rationale claims otherwise",
        )
        self.assertIn(
            "sk-REPLACE_ME",
            waived,
            "the .env.example placeholder is not the waived value, so the file is waived by "
            "something broader",
        )

    def test_a_broad_secret_scan_waiver_is_rejected_by_the_narrowness_contract(self):
        # A contract only means something if it FAILS on the diffs it exists to
        # stop.  Every adversarial config below was measured against the pinned
        # scanner image over this repo's tracked tree, with a high-entropy key
        # planted in plugins/ca/tools/.env.example.  The shipped config reports
        # `leaks found: 1` there; each shape below returns it to `no leaks
        # found`, i.e. each one really does swallow a live credential.
        quote = "'" * 3
        shipped = GITLEAKS_CONFIG.read_text(encoding="utf-8")
        self.assertEqual(
            gitleaks_waiver_violations(shipped), [], "the shipped allowlist is not narrow"
        )

        def waiver(body: str, *, target: str | None = None) -> str:
            block = ["", "[[allowlists]]", 'description = "adversarial"']
            if target is not None:
                block.append(f'regexTarget = "{target}"')
            block.append(f"regexes = [{quote}{body}{quote}]")
            return shipped + "\n".join(block) + "\n"

        # 1. `regexTarget = "line"`: the haystack becomes the whole source line,
        #    so a short literal is a substring test against every scanned line.
        #    This is the shape that passed the first version of this contract.
        self.assertTrue(
            [p for p in gitleaks_waiver_violations(waiver("API_KEY", target="line")) if "regexTarget" in p],
            "a line-targeted waiver is accepted - it matches against the entire source line",
        )
        # Anchoring does not rescue a `line` target either: the anchors would
        # then bind to the whole line rather than to the secret.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(waiver(r"\AAPI_KEY\z", target="line"))
                if "regexTarget" in p
            ],
            "an anchored line-targeted waiver is accepted",
        )
        # 2. `regexTarget = "match"` is no better - measured: `API_KEY` is a
        #    substring of the rule's own match text (`FARM_API_KEY=<secret>`).
        self.assertTrue(
            [p for p in gitleaks_waiver_violations(waiver("API_KEY", target="match")) if "regexTarget" in p],
            "a match-targeted waiver is accepted",
        )
        # 3. The deeper bug, and the reason constraining `regexTarget` ALONE is
        #    insufficient: with the target omitted (the detected secret) an
        #    unanchored literal is still a SUBSTRING search.  Measured: `sk-`
        #    waives the planted key outright.
        self.assertTrue(
            [p for p in gitleaks_waiver_violations(waiver("sk-")) if "not anchored" in p],
            "an unanchored waiver is accepted - it waives every secret containing it",
        )
        # 4. A pattern smuggled inside the anchors.
        self.assertTrue(
            [p for p in gitleaks_waiver_violations(waiver(r"\Ask-.*\z")) if "metacharacter" in p],
            "a wildcard waiver is accepted",
        )
        # 5. The blind-spot directives: these un-scan a whole file or commit.
        for directive in ("paths", "commits", "stopwords"):
            with self.subTest(directive=directive):
                blinded = shipped + f"\n[[allowlists]]\n{directive} = [{quote}x{quote}]\n"
                self.assertTrue(
                    [p for p in gitleaks_waiver_violations(blinded) if directive in p],
                    f"a `{directive}` waiver is accepted - it un-scans whole files",
                )
        # 6. A waiver with no rationale, and one with no value at all.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    shipped + f"\n[[allowlists]]\nregexes = [{quote}\\Ax\\z{quote}]\n"
                )
                if "no rationale" in p
            ],
            "a waiver with no description is accepted",
        )
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    shipped + '\n[[allowlists]]\ndescription = "x"\n'
                )
                if "names no value" in p
            ],
            "a waiver naming no value is accepted",
        )

        # ---- SPELLING BYPASSES OF THE CONTRACT ITSELF -----------------------
        # Everything above bypasses the RULES.  Every shape below bypassed the
        # CONTRACT: each was measured GUARD-GREEN against the first version of
        # this file while the pinned image reported `no leaks found` (exit 0)
        # over a tree carrying a freshly planted high-entropy key that the
        # shipped config reports as `leaks found: 1` (exit 1).  They are one
        # defect with eleven faces - the contract read the config as TEXT, and
        # TOML (plus viper's case-insensitive key lookup) admits far more
        # spellings than a regex anticipates.  The contract now PARSES.
        def block(*lines: str) -> str:
            return shipped + "\n[[allowlists]]\n" + "\n".join(lines) + "\n"

        # 7. An INDENTED `regexes` key.  `  regexes = [...]` is valid TOML; the
        #    extractor was anchored at column 0 so it pulled ZERO literals from
        #    this block, while the `"regexes = [" in block` substring test still
        #    reported the block as bounded.  Zero literals, zero violations.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    block('description = "adversarial"', f"  regexes = [{quote}sk-{quote}]")
                )
                if "not anchored" in p
            ],
            "an indented `regexes` key hides its literals from the contract",
        )
        # 8. `disabledRules` under `[extend]` turns the highest-value rule off
        #    outright.  Asserting `useDefault = true` is present says nothing
        #    about what sits beside it.  Only `useDefault` may live there.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    shipped.replace(
                        "useDefault = true",
                        'useDefault = true\ndisabledRules = ["generic-api-key"]',
                        1,
                    )
                )
                if "disabledrules" in p.lower()
            ],
            "`[extend] disabledRules` is accepted - it deletes the rule outright",
        )
        # 9. A SINGLE-QUOTED `regexTarget`.  The ban matched double quotes only.
        #    Measured: `regexTarget = 'match'` plus a whole-match-anchored,
        #    metacharacter-free literal clears every other check and swallows
        #    the planted key.
        #
        #    The value below is a LOW-ENTROPY stand-in, deliberately.  The
        #    measurement used a real high-entropy key, but this assertion is a
        #    pure function of the config TEXT - `regexTarget` is rejected on
        #    sight, whatever it is paired with - so the entropy buys the test
        #    nothing and costs it a finding.  Committing the measured key here
        #    made the secret-scan job red on its own contract, which is the job
        #    working: a credential-shaped literal in a tracked file is exactly
        #    what it exists to catch, and the answer to that is to stop
        #    committing one, never to widen the allowlist around it.
        planted = "FARM_API_KEY=sk-NOT-A-REAL-KEY"
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    block(
                        'description = "adversarial"',
                        "regexTarget = 'match'",
                        f"regexes = [{quote}\\A{planted}\\z{quote}]",
                    )
                )
                if "regexTarget" in p
            ],
            "a single-quoted `regexTarget` evades the ban",
        )
        # 10. Any TOML string spelling other than `'''...'''`.  The literal
        #     extractor matched triple-quoted strings only, so a basic or a
        #     single-quoted literal string yielded ZERO literals to check.
        for spelling in ('regexes = ["sk-"]', "regexes = ['sk-']"):
            with self.subTest(spelling=spelling):
                self.assertTrue(
                    [
                        p
                        for p in gitleaks_waiver_violations(
                            block('description = "adversarial"', spelling)
                        )
                        if "not anchored" in p
                    ],
                    "a waiver spelled with other quotes hides from the contract",
                )
        # 11. An INDENTED `[[allowlists]]` header.  The block scan was anchored
        #     at column 0, so an indented block - and every waiver in it - was
        #     invisible to every per-block check at once.
        first_header = re.search(r"(?m)^\[\[allowlists\]\]$", shipped)
        self.assertIsNotNone(first_header, "the shipped config has no allowlist header")
        indented = (
            shipped[: first_header.start()]
            + f'  [[allowlists]]\n  description = "adversarial"\n  regexes = [{quote}sk-{quote}]\n\n'
            + shipped[first_header.start() :]
        )
        self.assertTrue(
            [p for p in gitleaks_waiver_violations(indented) if "not anchored" in p],
            "an indented `[[allowlists]]` header hides a whole block",
        )
        # 12. CASE-VARIED KEYS.  gitleaks reads its config through viper, whose
        #     key lookup is case-INSENSITIVE, while every ban here was
        #     case-sensitive.  Measured: `Paths = ['''.''']` reported
        #     `scanned ~0 bytes` - the entire repository went unread - with the
        #     guard green.
        for line, needle in (
            (f"Paths = [{quote}.{quote}]", "paths"),
            ('RegexTarget = "match"', "regexTarget"),
        ):
            with self.subTest(line=line):
                self.assertTrue(
                    [
                        p
                        for p in gitleaks_waiver_violations(
                            block(
                                'description = "adversarial"',
                                line,
                                f"regexes = [{quote}\\Aunused\\z{quote}]",
                            )
                        )
                        if needle in p
                    ],
                    "a case-varied key evades the ban that names it",
                )
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    shipped.replace(
                        "useDefault = true",
                        'useDefault = true\nDISABLEDRULES = ["generic-api-key"]',
                        1,
                    )
                )
                if "disabledrules" in p.lower()
            ],
            "a case-varied `disabledRules` evades the ban",
        )
        # 13. A `]` INSIDE a literal.  The array capture was non-greedy to the
        #     first `]`, so one waiver containing a bracket truncated the scan
        #     and every later literal in the same array went unchecked.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    block(
                        'description = "adversarial"',
                        f"regexes = [{quote}\\Ax]y\\z{quote}, {quote}sk-{quote}]",
                    )
                )
                if "not anchored" in p
            ],
            "a `]` in one waiver hides every later waiver in the same array",
        )
        # 14. A `[[rules]]` BLOCK.  The contract only ever looked at
        #     `[[allowlists]]`.  Measured: re-declaring the id `generic-api-key`
        #     with a never-matching regex REPLACES the default rule, and the
        #     planted key goes unreported.  This file subtracts fixture values
        #     from the default ruleset; it declares no rules of its own.
        self.assertTrue(
            [
                p
                for p in gitleaks_waiver_violations(
                    shipped
                    + '\n[[rules]]\nid = "generic-api-key"\ndescription = "adversarial"\n'
                    + f"regex = {quote}zzzzz-never-matches-zzzzz{quote}\n"
                )
                if "rules" in p
            ],
            "a `[[rules]]` block is accepted - it can replace a default rule",
        )
        # 15. A config gitleaks cannot load is not a passing config.  The
        #     contract must not silently report "narrow" on TOML it failed to
        #     read; the scanner exits FTL on the same input.
        self.assertTrue(
            [p for p in gitleaks_waiver_violations("regexes = [") if "TOML" in p],
            "an unparseable config is reported as narrow",
        )

    def test_secret_scan_config_edits_reach_the_guard_that_constrains_them(self):
        # The narrowness contract above lives in THIS file, which runs only in
        # the path-scoped `ci-impact` job.  `.gitleaks.toml` matched no filter
        # and no push trigger, so a PR whose ONLY change was to widen the
        # allowlist skipped the single job that guards it - the same defect
        # class as #384, which this branch fixes for the parity fixture.
        # `.github/workflows/docs.yml` had the identical gap: it is guarded by
        # test_docs_workflow_gates_the_site_dependency_graph_before_publishing
        # (issue #403 AC-3), and a PR deleting the site audit step touches only
        # docs.yml - exactly the diff the guard could not see.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        impact = paths_filter(ci, "impact")
        self.assertIn(
            "tools/ci-impact.py", impact, "the impact-filter scan drifted off the real block"
        )
        push = push_trigger_paths(ci)
        self.assertIn(
            "tools/sync-core.py", push, "the push-trigger scan drifted off the real block"
        )
        for guarded in (".gitleaks.toml", ".github/workflows/docs.yml"):
            with self.subTest(path=guarded):
                self.assertIn(
                    guarded, impact, "a PR touching only this file skips its own contract test"
                )
                self.assertIn(guarded, push, "a push of this file starts no CI run")

    def test_gate_command_subjects_reach_the_guard_that_constrains_them(self):
        # Issue #507, same defect class as the test above and as #384/#403/#404.
        # GateCommandTest lives in THIS file, which runs only in the path-scoped
        # `ci-impact` job. Its two subjects are the gate prose and the file that
        # prose points at - and neither matched a filter, so a PR whose ONLY
        # change was deleting the coverage section from tech-stack.md, or
        # rewording the phrase the guard keys on, skipped the single job that
        # would have caught it. The guard was green on the PR that introduced it
        # purely because that PR also edited this file.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        impact = paths_filter(ci, "impact")
        push = push_trigger_paths(ci)
        self.assertIn(
            "tools/ci-impact.py", impact, "the impact-filter scan drifted off the real block"
        )
        for guarded in (
            ".codearbiter/tech-stack.md",
            "plugins/ca/skills/**",
            "plugins/ca/agents/**",
            "core/surface/skills/**",
            "core/surface/agents/**",
        ):
            with self.subTest(path=guarded):
                self.assertIn(
                    guarded, impact, "a PR touching only this path skips its own contract test"
                )
        # The prose side is already covered for pushes by `plugins/ca/**` and
        # `core/**`; tech-stack.md is under neither and needs its own entry.
        self.assertIn(
            ".codearbiter/tech-stack.md", push, "a push of this file starts no CI run"
        )

    def test_the_allowlist_guard_also_runs_unconditionally_in_the_secret_scan_job(self):
        # Belt AND braces.  A path filter is a promise that has already been
        # broken twice in this repo (#384, and the .gitleaks.toml gap above), so
        # registering the config with the filter is necessary but not durable -
        # a later edit can drop it again.  The `secret-scan` job carries no
        # `needs: changes` gate, so hosting the narrowness contract there makes
        # it unskippable: any PR that reaches CI at all re-proves the allowlist
        # before the scan is allowed to trust it.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = workflow_jobs(ci)["secret-scan"]
        # Job-level keys sit at four spaces; a step's own `if:` is deeper, so
        # this reads the job's own gating and not the range step's event guard.
        self.assertNotRegex(job, r"(?m)^    needs:", "the secret scan became path-scoped")
        self.assertNotRegex(job, r"(?m)^    if:", "the secret scan became conditional")
        for guard in (
            "test_the_secret_scan_allowlist_stays_narrow_and_value_scoped",
            "test_a_broad_secret_scan_waiver_is_rejected_by_the_narrowness_contract",
        ):
            with self.subTest(guard=guard):
                self.assertIn(
                    f"test_ci_impact.WorkflowContractTest.{guard}",
                    job,
                    "the always-on job does not re-prove its own allowlist",
                )

    def test_the_secret_scan_covers_the_pull_requests_commit_range(self):
        # Issue #404 AC-1 asks for a scan over the relevant commit RANGE.  A
        # `gitleaks dir` scan of the merge-result tree cannot meet it, and the
        # gap is not theoretical - measured on a scratch repo, a credential
        # added in one commit and deleted in the next left the tree scan
        # reporting `no leaks found` (exit 0) while `gitleaks git --log-opts
        # <base>..HEAD` reported it with its file, line, rule, and commit sha
        # (exit 1).  This repository allows merge and rebase merges as well as
        # squash, so those commits reach main's history verbatim.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = workflow_jobs(ci)["secret-scan"]
        # The `git` subcommand (as opposed to `dir`) is what reads history.
        self.assertRegex(
            job, r"(?m)^\s+git \. \\$", "the secret scan never inspects commit history"
        )
        self.assertIn("--log-opts", job, "the history scan is not scoped to the PR's range")
        # History is only there to scan if the checkout actually fetched it.
        self.assertRegex(
            job, r"(?m)^          fetch-depth: 0$", "a shallow checkout leaves no range to scan"
        )
        # The range scan is a pull_request concern - it is the only event with a
        # base to diff against, and PR checks are main's enforcement point.
        self.assertIn(
            "if: github.event_name == 'pull_request'",
            job,
            "the range scan is not scoped to the event that has a base to diff against",
        )

    def test_documentation_contract_is_always_required_by_merge_readiness(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("  documentation-contract:\n", ci)
        self.assertIn('name: "[CHECK] | [REPO] | Documentation contract"', ci)
        aggregate = ci.split("  ci-passed:\n", 1)[1]
        self.assertIn("      - documentation-contract\n", aggregate)
        self.assertIn("${{ needs['documentation-contract'].result }}", aggregate)

    def test_ci_reports_under_the_merge_group_event_that_tests_the_real_base(self):
        # Issue #383.  main's ONLY required context is this workflow's
        # `[GATE ] | [REPO] | Merge readiness` aggregate, and the live
        # protection response carries `required_status_checks.strict=false`.
        # A green aggregate computed against an OLDER base is therefore enough
        # to merge, so two individually green pull requests can interact after
        # one of them lands while the second keeps a valid required check from
        # its stale merge base.  The ruling was a merge queue, which
        # synthesises and tests the exact prospective merge commit - strictly
        # stronger than mere up-to-dateness, because it catches interactions
        # that currency alone does not.
        #
        # SEQUENCING, and the reason this contract exists in the repository
        # rather than in the settings UI: a queue whose required context never
        # reports under `merge_group` stalls EVERY queued merge, with nothing
        # able to satisfy the gate.  The trigger has to be live on main first.
        # This test is what keeps it there once it is.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        triggers = ci.split("\njobs:\n", 1)[0]
        self.assertRegex(
            triggers,
            r"(?m)^  merge_group:\n    types: \[checks_requested\]$",
            "ci.yml never runs on merge_group, so an enabled merge queue would "
            "have nothing to satisfy the required merge-readiness context",
        )

    def test_every_enforced_job_is_reachable_and_correctly_based_in_a_merge_group(self):
        # Issue #383, the half of it a trigger alone does NOT fix.  `ci-passed`
        # accepts `skipped` as success - that is exactly what ADR-0007 path
        # scoping needs - so an enforced job gated to `github.event_name ==
        # 'pull_request'` does not turn a merge group red.  It silently drops
        # its verdict and the aggregate still reports green on the merge commit,
        # which is a WEAKER gate than the stale-base one this issue set out to
        # replace.  The four payload-version guards are the sharpest case:
        # whether a bump is required is a question about the BASE, so they are
        # precisely the jobs a merge queue exists to re-run.
        #
        # The second scan catches the subtler shape.  A job that RUNS but reads
        # its base out of a pull_request-only context is worse than one that
        # skips: `github.base_ref` and `github.event.pull_request.*` are both
        # EMPTY under merge_group, so the guard would compare against nothing
        # and conclude green having verified nothing.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        jobs = workflow_jobs(ci)
        enforced = aggregate_required_results(ci)
        self.assertIn("version-bump", enforced, "the aggregate scan found no payload guard")
        unreachable: list[str] = []
        misbased: list[str] = []
        for job_id in enforced:
            block = jobs.get(job_id, "")
            # Job-level AND step-level conditions: a step gated to
            # pull_request drops its evidence just as quietly as a job does,
            # and the secret scan's commit-range step is one of those.
            for condition in re.findall(r"(?m)^\s+if: (?P<test>[^\n]+)$", block):
                if "github.event_name" not in condition:
                    continue
                if "merge_group" not in condition:
                    unreachable.append(f"{job_id}: if: {condition}")
            for expression in re.findall(r"\$\{\{(?P<body>[^}]*)\}\}", block):
                if (
                    "github.base_ref" not in expression
                    and "github.event.pull_request." not in expression
                ):
                    continue
                if "github.event.merge_group." not in expression:
                    misbased.append(f"{job_id}: ${{{{{expression}}}}}")
        self.assertEqual(
            unreachable,
            [],
            "enforced jobs a merge queue would silently skip while ci-passed reports green",
        )
        self.assertEqual(
            misbased,
            [],
            "enforced jobs whose base context is empty under merge_group",
        )


class ReceiptCommandTest(unittest.TestCase):
    def test_cli_writes_deterministic_json_and_a_markdown_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(REPO_ROOT / ".github/ci-impact-map.json"),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                # `pi-checks` is the canonical host-independent job added by
                # issue #390.  A Pi payload edit now predicts all three Pi
                # contracts; omitting it made the receipt under-report the
                # required jobs a reviewer must wait on.
                ["pi-adapter", "pi-checks", "pi-latest"],
            )
            self.assertEqual(
                receipt["predicted_not_selected"],
                ["ca-surface", "codex-surface", "pi-surface"],
            )
            self.assertEqual(
                receipt["selected"][0]["reproduce"],
                "python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.10",
            )
            self.assertEqual(
                receipt["selected"][1]["reproduce"],
                "npm --prefix plugins/ca-pi/tools test",
            )
            self.assertEqual(
                receipt["selected"][0]["reason"],
                "matched path: plugins/ca-pi/tools/src/extension.ts",
            )
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)
            self.assertIn("Predicted not selected", markdown)
            self.assertIn("advisory", markdown)

    def test_a_malformed_map_falls_back_to_broad_validation_without_failing(self):
        # main()'s documented fail-safe contract (tools/ci-impact.py ~422-448):
        # any planner error (ImpactMapError/OSError/ValueError) degrades to the
        # broad-lane receipt rather than propagating, and the exit code stays 0
        # so a planner bug can never fail-closed the merge gate itself.
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            malformed_map = temporary_path / "impact-map.json"
            malformed_map.write_text("not valid json", encoding="utf-8")
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(malformed_map),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                ["broad-lane"],
            )
            self.assertTrue(receipt["reason"].startswith("planner error:"))
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)



class NoOrphanedSuiteTest(unittest.TestCase):
    """Every test suite in .github/scripts must actually RUN somewhere.

    `test_public_pi_docs.py` existed, asserted a real contract, and was invoked
    by no workflow at all - so it had never executed on a merge gate, and the
    counts it guards drifted by one on all three plugins without a word. Four
    more suites were in the same state, each guarding a script CI itself depends
    on (pi_promotion, check_sandbox_docker_layers, check_license_consistency,
    _planfilelib).

    A suite nobody runs is not a gate, it is a file. This is the guard that keeps
    the next one from going quiet the same way.

    A suite counts as reachable if a workflow names it, OR if another script in
    this directory invokes it - several Pi suites run only through
    `verify_pi_support.py` and `test_pi_platform_contract.py`, which is a
    deliberate composition rather than an oversight."""

    #: Suites that legitimately run nowhere, with the reason. Empty by design -
    #: an entry here is a documented exemption, not a place to park a new orphan.
    EXEMPT: dict = {}

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Drop whole-line `#` comments.

        A suite named in PROSE is not a suite that runs. The first version of
        this guard counted any occurrence, so the comment block documenting the
        wiring - and then this class's own docstring - made un-wired suites look
        reachable. Both were caught by mutation, which is the only reason this
        distinction is here."""
        return "\n".join(line for line in text.splitlines()
                          if not line.lstrip().startswith("#"))

    def _corpus(self):
        workflows = "\n".join(
            self._strip_comments(p.read_text(encoding="utf-8"))
            for p in (REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        # This module is excluded from the sibling corpus on purpose: it is the
        # one file guaranteed to name every suite it discusses, so counting it
        # would let this guard vouch for orphans by describing them.
        scripts = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (REPO_ROOT / ".github" / "scripts").glob("*.py")
            if p.name != "test_ci_impact.py")
        return workflows, scripts

    def test_every_suite_is_reachable(self):
        workflows, scripts = self._corpus()
        orphans = []
        for path in sorted((REPO_ROOT / ".github" / "scripts").glob("test_*.py")):
            name = path.name
            if name in self.EXEMPT:
                continue
            # An INVOCATION, not a mention. Matching bare presence was the
            # first cut and it was vacuous: the comment documenting these
            # very steps names each file, so deleting the `run:` line left
            # the suite looking reachable via its own explanatory prose.
            # Caught by mutation - un-wiring test_planfilelib.py did not
            # turn the first version red.
            invocation = re.compile(
                r"\s\.github/scripts/" + re.escape(name))
            if invocation.search(workflows):
                continue
            # Or invoked by a sibling script, excluding its own source:
            # several Pi suites run only through verify_pi_support.py and
            # test_pi_platform_contract.py, which is composition rather
            # than oversight.
            others = scripts.replace(path.read_text(encoding="utf-8"), "")
            if name in others or name[:-3] in others:
                continue
            orphans.append(name)
        self.assertEqual(
            orphans, [],
            "these suites are invoked by no workflow and no sibling script, so "
            "they never run: " + ", ".join(orphans))

class GateCommandTest(unittest.TestCase):
    """A gate that reads its command from tech-stack.md needs that command to exist.

    Issue #507: `tdd` Phase 5 and `refactor` Phase 2/6 instructed "run the
    coverage command from tech-stack.md", and tech-stack.md contained the word
    "coverage" zero times.  Both skills forbid guessing the command, so every
    run reached the phase, found nothing to run, and passed through on a gap.
    A BLOCK gate that cannot execute is worse than an absent one: it reads as
    satisfied in every lane, which is the same failure shape as #501's suites
    that ran on nothing and #506's assertion that agreed with the bug.

    Enforced from THIS repo's own tech-stack.md, which is correct even though
    the skills ship to other projects: the file is project state, so this
    asserts that codeArbiter satisfies the contract its own gates impose.
    """

    # token -> proof tech-stack.md DEFINES it, not merely discusses it. This map
    # is checked in BOTH directions below: a token demanded by gate prose with no
    # entry here fails, and an entry here with no demander fails. A one-directional
    # map is how a guard rots into decoration - the first cut of this test carried
    # a `typecheck` entry that matched no prose and therefore asserted nothing,
    # while the live `test` demander was absent from the map entirely.
    DEFINITIONS = {
        # `coverage` is the only entry backed by RESOLUTION as well as text:
        # test_every_npm_script_named_by_tech_stack_actually_exists proves the
        # named script exists in the named manifest. The other two are text
        # patterns, and that asymmetry is deliberate rather than an oversight -
        # neither names an npm script there is anything to resolve against.
        "coverage": re.compile(r"(?m)^\s*npm\b.*\brun coverage\b"),
        # Requires an EXECUTABLE line inside the fence, not merely a non-empty
        # one: replacing the whole section body with a single `:` satisfied the
        # first cut while deleting every real invocation. A missing test command
        # is loud in a way a missing coverage command was not - every lane runs
        # it - so this is a weaker guarantee for a lower-stakes token.
        # The `(?:(?!^## )[\s\S])*?` temper is load-bearing: a plain `.*?` under
        # DOTALL scans PAST the Test section to any later ```sh fence containing
        # a command, so gutting this section still matched via `## Coverage`'s
        # block. Caught by mutation - the tightened-but-untempered version was
        # green on a `## Test` body reduced to a bare `:`.
        "test": re.compile(
            r"(?ms)^## Test\b(?:(?!^## )[\s\S])*?```sh\n[^`]*?^\s*(?:python|npm|npx|pytest)\b"),
        # `dependency-reviewer` reads this one. It was found by the
        # no-dead-entry check below on the first run, which is the point of
        # checking both directions - a one-way map had no way to notice.
        "audit": re.compile(r"npm audit\b[^\n]*--audit-level=high"),
    }

    # Deliberately keyed on the canonical phrasing the gates use. Tokens named
    # only in list form ("run lint, the type-check ..., and coverage, all from
    # tech-stack.md") are NOT discovered, and that limit is recorded rather than
    # papered over: widening the pattern to prose-match those would produce
    # false demanders, which is worse than a known gap.
    DEMAND = re.compile(r"\b([a-z][a-z-]*) command from `tech-stack\.md`")

    def _gate_docs(self):
        """Skills AND agents. `coverage-auditor` reads the same command a skill does."""
        root = REPO_ROOT / "plugins" / "ca"
        return sorted([*root.glob("skills/*/SKILL.md"), *root.glob("agents/*.md")])

    def _demanded(self):
        found: dict[str, set[str]] = {}
        for path in self._gate_docs():
            label = path.parent.name if path.name == "SKILL.md" else path.stem
            for token in self.DEMAND.findall(path.read_text(encoding="utf-8")):
                found.setdefault(token, set()).add(label)
        return found

    def test_every_gate_command_read_from_tech_stack_is_defined_there(self):
        tech_stack = (REPO_ROOT / ".codearbiter" / "tech-stack.md").read_text(encoding="utf-8")
        missing = []
        for token, who in sorted(self._demanded().items()):
            names = ", ".join(sorted(who))
            proof = self.DEFINITIONS.get(token)
            if proof is None:
                missing.append(
                    f"{token}: demanded by {names}, but this test has no definition "
                    f"check for it - add one to DEFINITIONS rather than leaving it unguarded")
            elif proof.search(tech_stack) is None:
                missing.append(
                    f"{token}: demanded by {names}, but .codearbiter/tech-stack.md "
                    f"defines no such command")
        self.assertEqual(
            missing, [],
            "a gate cannot run a command its tech-stack.md never defines: " + "; ".join(missing))

    def test_no_definition_check_is_dead(self):
        """An entry matching no prose asserts nothing while looking like protection."""
        dead = sorted(set(self.DEFINITIONS) - set(self._demanded()))
        self.assertEqual(
            dead, [],
            "these DEFINITIONS entries have no demander, so they guard nothing - either "
            "the prose was reworded (fix DEMAND) or the entry is stale (delete it): "
            + ", ".join(dead))

    # `--prefix X` and `--prefix=X` are both valid, and `run` may precede or
    # follow the flag. The first cut matched only `npm --prefix X run Y`, so
    # `npm run coverage --prefix plugins/ca/tools` - a working invocation -
    # parsed to nothing and the check passed vacuously.
    NPM_LINE = re.compile(r"(?m)^\s*npm\b[^\n]*")
    NPM_PREFIX = re.compile(r"--prefix[= ]\s*(\S+)")
    NPM_RUN = re.compile(r"\brun\s+([\w:-]+)")

    def _npm_invocations(self, tech_stack):
        """Every `(prefix, script)` tech-stack.md names, in any argument order."""
        found = set()
        for line in self.NPM_LINE.findall(tech_stack):
            prefix = self.NPM_PREFIX.search(line)
            script = self.NPM_RUN.search(line)
            if prefix and script:
                found.add((prefix.group(1).rstrip("/"), script.group(1)))
        return found

    def test_every_npm_script_named_by_tech_stack_actually_exists(self):
        """The command must RESOLVE, not merely appear.

        Checking that tech-stack.md mentions `npm --prefix X run Y` proves only
        that the prose is self-consistent. Deleting `Y` from `X/package.json`
        leaves the gate pointing at nothing while every text assertion still
        passes - #507 reachable straight through the fix for #507.
        """
        tech_stack = (REPO_ROOT / ".codearbiter" / "tech-stack.md").read_text(encoding="utf-8")
        pairs = self._npm_invocations(tech_stack)
        # Non-vacuity. An empty scan produces an empty finding list and a green
        # test - the same fail-open shape this whole class exists to close, and
        # the exact way a reworded invocation would silently disarm the check.
        self.assertTrue(
            pairs,
            "no `npm --prefix <dir> run <script>` invocation parsed out of tech-stack.md; "
            "either the file stopped naming one or the parser drifted off its phrasing")
        broken = []
        for prefix, script in sorted(pairs):
            manifest = REPO_ROOT / prefix / "package.json"
            if not manifest.exists():
                broken.append(f"{prefix}/package.json does not exist (named for `run {script}`)")
                continue
            scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts", {})
            if script not in scripts:
                broken.append(f"{prefix}/package.json defines no `{script}` script")
        self.assertEqual(
            broken, [],
            "tech-stack.md names npm scripts that do not exist: " + "; ".join(broken))

    def test_every_tree_with_a_coverage_script_is_documented(self):
        """Completeness, driven by the filesystem rather than by the prose.

        The resolution check above verifies whatever it happens to parse and is
        blind to what the document omits. A new `plugins/<x>/tools` tree, or one
        documented in a phrasing the parser misses, would be unguarded
        invisibly. Deriving the expected set from the manifests instead means a
        tree cannot be added without its command being named.
        """
        tech_stack = (REPO_ROOT / ".codearbiter" / "tech-stack.md").read_text(encoding="utf-8")
        documented = {prefix for prefix, script in self._npm_invocations(tech_stack) if script == "coverage"}
        undocumented = []
        for manifest in sorted(REPO_ROOT.glob("plugins/*/tools/package.json")):
            scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts", {})
            if "coverage" not in scripts:
                continue
            tree = manifest.parent.relative_to(REPO_ROOT).as_posix()
            if tree not in documented:
                undocumented.append(tree)
        self.assertEqual(
            undocumented, [],
            "these trees define a `coverage` script that tech-stack.md never names, so the "
            "gates cannot run it there: " + ", ".join(undocumented))


if __name__ == "__main__":
    unittest.main()
