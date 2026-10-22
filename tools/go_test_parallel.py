#!/usr/bin/env python3
"""Run a Go module's complete test population in bounded parallel processes.

`go test ./...` runs packages concurrently but each package's top-level tests
serially. Several artifact-engine fixtures call `t.Setenv`, so they cannot use
`t.Parallel`; on a hosted runner the slowest package then waits on Git child
processes while the remaining cores sit idle. This runner compiles every test
binary once, splits each package's top-level tests into exact-name chunks, and
runs those chunks as separate processes, so process-global state stays isolated.

Discovery owns membership: every test, example and fuzz seed target listed by
each binary must report exactly one top-level pass or skip, and none may be
missing, repeated or failed. Timing hints only order and balance the chunks;
an absent or stale hint can never remove a test.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HINTS = Path(__file__).with_name("go-test-timings.json")
TERMINAL = {"pass", "fail", "skip"}
TARGET_CHUNK_SECONDS = 20.0
# `-test.timeout` starts only inside the test binary; these bound the steps
# around it (compiling, listing, and a binary that hangs before m.Run).
BUILD_TIMEOUT_SECONDS = 1800.0
LIST_TIMEOUT_SECONDS = 600.0
CHUNK_MARGIN_SECONDS = 120.0


def go(args: list[str], cwd: Path, env: dict[str, str]) -> str:
    return subprocess.run(["go", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=BUILD_TIMEOUT_SECONDS).stdout


def duration_seconds(value: str) -> float:
    """Seconds in a Go duration such as `20m`, `90s` or `1h30m`."""
    parts = re.findall(r"(\d+(?:\.\d+)?)(h|m|s)", value)
    if not parts or "".join(number + unit for number, unit in parts) != value:
        raise ValueError(f"unsupported Go duration: {value!r}")
    return sum(float(number) * {"h": 3600, "m": 60, "s": 1}[unit] for number, unit in parts)


def load_hints(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format") != "codearbiter.go-test-timings/1":
        raise ValueError(f"invalid Go timing hint file: {path}")
    tests = document.get("tests")
    if not isinstance(tests, dict) or not all(
            isinstance(k, str) and type(v) in (int, float) and math.isfinite(v) and v >= 0
            for k, v in tests.items()):
        raise ValueError(f"invalid Go timing hints in {path}")
    return {k: float(v) for k, v in tests.items()}


def discover(binary: Path, package_dir: Path, env: dict[str, str]) -> list[str]:
    listed = subprocess.run([str(binary), "-test.list", ".*"], cwd=package_dir, env=env, check=True,
                            capture_output=True, text=True, encoding="utf-8",
                            timeout=LIST_TIMEOUT_SECONDS).stdout.split()
    return [name for name in listed if re.match(r"^(Test|Example|Fuzz)", name)]


def chunk(package: str, names: list[str], hints: dict[str, float], workers: int) -> list[tuple[list[str], float]]:
    """Longest-first balance of one package's tests into enough chunks to use the workers."""
    cost = {name: hints.get(f"{package}.{name}", 0.05) for name in names}
    total = sum(cost.values())
    count = max(1, min(len(names), workers, math.ceil(total / TARGET_CHUNK_SECONDS)))
    bins: list[list[str]] = [[] for _ in range(count)]
    totals = [0.0] * count
    for name in sorted(names, key=lambda n: (-cost[n], n)):
        index = totals.index(min(totals))
        bins[index].append(name)
        totals[index] += cost[name]
    return [(sorted(b), t) for b, t in zip(bins, totals) if b]


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def run_chunk(binary: Path, package: str, package_dir: Path, names: list[str],
              extra: list[str], env: dict[str, str],
              timeout: float | None = None) -> tuple[dict[str, str], str, int, float]:
    pattern = "^(" + "|".join(re.escape(name) for name in names) + ")$"
    # The test binary is the direct child so a timeout kills the process that
    # holds the pipes; its test2json stream is converted afterwards.
    command = [str(binary), "-test.v=test2json", "-test.count=1", "-test.run", pattern, *extra]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=package_dir, env=env, capture_output=True, timeout=timeout)
        raw, stderr, code = completed.stdout, _text(completed.stderr), completed.returncode
    except subprocess.TimeoutExpired as expired:
        # A wedged chunk fails with whatever it reported before being killed.
        raw, code = expired.stdout or b"", -1
        stderr = _text(expired.stderr) + f"\nchunk exceeded {timeout:.0f}s and was terminated\n"
    stdout = subprocess.run(["go", "tool", "test2json", "-t", "-p", package], input=raw,
                            cwd=package_dir, env=env, capture_output=True, check=True,
                            timeout=LIST_TIMEOUT_SECONDS).stdout.decode("utf-8", "replace")
    outcomes: dict[str, str] = {}
    output: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            output.append(line)
            continue
        test, action = event.get("Test"), event.get("Action")
        if action == "output":
            output.append(event.get("Output", "").rstrip("\n"))
        elif test and "/" not in test and action in TERMINAL:
            if test in outcomes:
                outcomes[test] = "repeated"
            else:
                outcomes[test] = action
    return outcomes, "\n".join(output) + stderr, code, time.monotonic() - started


def main() -> int:
    try:
        return run()
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        detail = getattr(error, "stderr", None) or ""
        print(f"go-test-parallel: FAILED before running tests: {error}\n{detail}"[-20000:], flush=True)
        return 1


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    parser.add_argument("--timeout", default="20m")
    parser.add_argument("--build-flag", action="append", default=[], help="extra `go test -c` flag, e.g. -race")
    parser.add_argument("--hints", type=Path, default=HINTS)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 64:
        raise SystemExit("--jobs must be between 1 and 64")
    module = args.module.resolve()
    chunk_timeout = duration_seconds(args.timeout) + CHUNK_MARGIN_SECONDS
    env = dict(os.environ)
    hints = load_hints(args.hints)
    packages = json.loads("[" + ",".join(
        go(["list", "-json=ImportPath,Dir,TestGoFiles,XTestGoFiles", "./..."], module, env)
        .replace("}\n{", "}\x00{").split("\x00")) + "]")
    with tempfile.TemporaryDirectory(prefix="go-test-parallel-") as raw:
        bin_dir = Path(raw)
        tested = [p for p in packages if p.get("TestGoFiles") or p.get("XTestGoFiles")]
        go(["test", "-c", "-buildvcs=false", *args.build_flag, "-o", str(bin_dir) + os.sep,
            *[p["ImportPath"] for p in tested]], module, env)
        work: list[tuple[float, Path, str, Path, list[str]]] = []
        expected: dict[tuple[str, str], None] = {}
        for package in tested:
            name = package["ImportPath"].rsplit("/", 1)[-1] + ".test" + (".exe" if os.name == "nt" else "")
            binary = bin_dir / name
            if not binary.is_file():
                raise SystemExit(f"missing compiled test binary for {package['ImportPath']}")
            names = discover(binary, Path(package["Dir"]), env)
            for test in names:
                expected[(package["ImportPath"], test)] = None
            for names_chunk, cost in chunk(package["ImportPath"], names, hints, args.jobs):
                work.append((cost, binary, package["ImportPath"], Path(package["Dir"]), names_chunk))
        work.sort(key=lambda item: -item[0])
        print(f"go-test-parallel: {len(expected)} top-level tests in {len(tested)} packages, "
              f"{len(work)} chunks on {args.jobs} workers", flush=True)
        seen: dict[tuple[str, str], str] = {}
        failed = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(run_chunk, binary, package, directory, names,
                                   [f"-test.timeout={args.timeout}"], env, chunk_timeout): (package, names)
                       for _, binary, package, directory, names in work}
            for future in concurrent.futures.as_completed(futures):
                package, names = futures[future]
                outcomes, output, code, seconds = future.result()
                bad = [n for n in names if outcomes.get(n) not in ("pass", "skip")]
                stray = sorted(set(outcomes) - set(names))
                for name, outcome in outcomes.items():
                    seen[(package, name)] = outcome
                status = "ok" if code == 0 and not bad and not stray else "FAIL"
                print(f"{status:4} {package} [{len(names)} tests] {seconds:.1f}s", flush=True)
                if status == "FAIL":
                    failed = True
                    print(output[-20000:], flush=True)
                    if bad:
                        print(f"  not passed: {bad}", flush=True)
                    if stray:
                        print(f"  unexpected top-level results: {stray}", flush=True)
        missing = sorted(set(expected) - set(seen))
        if missing:
            failed = True
            print(f"go-test-parallel: listed tests without a result: {missing}", flush=True)
        skipped = sum(1 for outcome in seen.values() if outcome == "skip")
        print(f"go-test-parallel: {sum(1 for o in seen.values() if o == 'pass')} passed, {skipped} skipped, "
              f"{'FAILED' if failed else 'all complete'}", flush=True)
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
