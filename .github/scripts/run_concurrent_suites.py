#!/usr/bin/env python3
"""Run independent unittest suite scripts concurrently on one runner.

Usage: run_concurrent_suites.py SCRIPT... [--interpreter-env VAR SCRIPT...]

Each script runs as its own process with the inherited environment, so
fixtures stay isolated while the runner's cores are used. A script after
`--interpreter-env VAR` runs under the interpreter named by that environment
variable (for example the locked conformance virtualenv). Every suite's full
output is printed as its own group. The run fails unless every suite exits 0,
reports `OK` and ran at least one test; a suite that exceeds the timeout is
terminated and reported with its partial output.
"""
from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RAN = re.compile(r"(?m)^Ran (\d+) tests? in ")
RESULT_OK = re.compile(r"(?m)^OK(?: \(.*\))?\s*$")
TIMEOUT_SECONDS = float(os.environ.get("CONCURRENT_SUITE_TIMEOUT_SECONDS", "1800"))


def parse(argv: list[str]) -> list[tuple[str, str]]:
    """Return (interpreter, script) pairs in declaration order."""
    suites: list[tuple[str, str]] = []
    interpreter = sys.executable
    index = 0
    while index < len(argv):
        if argv[index] == "--interpreter-env":
            if index + 1 >= len(argv):
                raise ValueError("--interpreter-env needs a variable name")
            name = argv[index + 1]
            interpreter = os.environ.get(name, "")
            if not interpreter:
                raise ValueError(f"interpreter variable {name} is unset")
            index += 2
            continue
        suites.append((interpreter, argv[index]))
        index += 1
    scripts = [script for _, script in suites]
    if not suites or len(set(scripts)) != len(scripts):
        raise ValueError("name each suite script once")
    missing = [script for script in scripts if not Path(script).is_file()]
    if missing:
        raise ValueError(f"suite scripts not found: {missing}")
    return suites


def run(interpreter: str, script: str) -> tuple[int, str]:
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([interpreter, script], stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code = -1
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
    if code == -1:
        output += "\nsuite timed out and was terminated\n"
    return code, output


def problems(code: int, output: str) -> list[str]:
    found = []
    if code != 0:
        found.append(f"exited {code}")
    ran = RAN.findall(output)
    if not ran or int(ran[-1]) == 0:
        found.append("ran no tests")
    if not RESULT_OK.search(output):
        found.append("did not report OK")
    return found


def main(argv: list[str]) -> int:
    try:
        suites = parse(argv)
    except ValueError as error:
        print(f"concurrent suites: {error}", flush=True)
        return 2
    workers = min(len(suites), max(2, os.cpu_count() or 2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda pair: run(*pair), suites))
    failed = []
    for (_, script), (code, output) in zip(suites, results):
        found = problems(code, output)
        print(f"::group::{script} ({'ok' if not found else 'FAILED: ' + ', '.join(found)})", flush=True)
        print(output, flush=True)
        print("::endgroup::", flush=True)
        if found:
            failed.append(f"{script}: {', '.join(found)}")
    for line in failed:
        print(f"concurrent suites FAILED: {line}", flush=True)
    print(f"concurrent suites: {len(suites) - len(failed)} of {len(suites)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
