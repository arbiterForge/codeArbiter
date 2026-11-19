#!/usr/bin/env python3
"""Select and report the exact source and CI build a release run publishes.

release.yml's preflight is the only caller. Selection policy (unchanged):

  * workflow_run: the completed CI run's own head commit and run id, even if
    main has moved on (a later merge may start no CI run or fail CI);
  * workflow_dispatch: the newest main push commit with a SUCCESSFUL CI run,
    which is not necessarily main's head (a newer failed head is skipped).

What this owner adds (R-02 / C-F02): the selection is stated, not implied.
Every run writes the selected source, the CI run that built it, main's head,
whether they are equal, and whether that run's release artifacts are still
retained. A dispatch may name `expected-source`/`expected-run`; then the
selection must equal them exactly, or nothing publishes. That is how a
major-release operator binds publication to the approved final candidate
instead of whatever later (or older) successful run happens to be newest.

Refusals: no successful CI run; a source not on main; an expected source or
run that differs from the selection; a hosted publication whose CI artifacts
expired (re-running CI rebuilds new bytes that need fresh qualification).

Subcommands:
  select   --event E [--run-sha S --run-id N] [--runs FILE]
           -> `source=` and `ci-run-id=` lines for the selected build.
  report   --source S --ci-run-id N --head H --ancestor true|false
           --artifacts FILE [--expected-source S] [--expected-run N]
           [--output FILE] [--summary FILE]
           -> validates the selection and writes outputs plus a summary table.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
RUN_ID = re.compile(r"[1-9][0-9]*")
# The CI artifacts a hosted (packaged) target downloads from the selected run.
HOSTED_ARTIFACTS = ("artifact-host-payloads-{sha}", "artifact-release-packages-{sha}")


class SelectionError(ValueError):
    """The run cannot name an exact, publishable source and build."""


def select(event: str, *, run_sha: str = "", run_id: str = "", runs=None) -> tuple[str, str, str]:
    """Return (source, ci_run_id, selection rule)."""
    if event == "workflow_run":
        if SHA.fullmatch(run_sha or "") is None or RUN_ID.fullmatch(run_id or "") is None:
            raise SelectionError("workflow_run event lacks a full head SHA and run id")
        return run_sha, run_id, "this successful main-push CI run's own commit"
    if event != "workflow_dispatch":
        raise SelectionError(f"unsupported release event {event!r}")
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise SelectionError("successful-CI lookup returned no workflow_runs list")
    candidates = runs["workflow_runs"]
    if not candidates:
        raise SelectionError("no successful push CI run on main; re-run CI on main first")
    newest = candidates[0]
    sha, number = newest.get("head_sha"), str(newest.get("id", ""))
    if (SHA.fullmatch(sha or "") is None or RUN_ID.fullmatch(number) is None
            or newest.get("conclusion") not in (None, "success")):
        raise SelectionError("successful-CI lookup returned a malformed run")
    return sha, number, "newest main-push commit whose CI succeeded (not necessarily main's head)"


def artifact_state(artifacts, source: str) -> str:
    """retained | expired | missing for the hosted CI artifacts of `source`."""
    pages = artifacts if isinstance(artifacts, list) else [artifacts]
    items = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
            raise SelectionError("CI artifact listing is unavailable or malformed")
        items.extend(item for item in page["artifacts"] if isinstance(item, dict))
    found = {item.get("name"): item for item in items}
    states = []
    for pattern in HOSTED_ARTIFACTS:
        item = found.get(pattern.format(sha=source))
        if item is None:
            states.append("missing")
        elif item.get("expired") is True:
            states.append("expired")
        elif item.get("expired") is False:
            states.append("retained")
        else:
            raise SelectionError("CI artifact listing has no expiry state")
    for state in ("missing", "expired"):
        if state in states:
            return state
    return "retained"


def report(*, source: str, ci_run_id: str, head: str, ancestor: bool, artifacts,
           expected_source: str = "", expected_run: str = "", rule: str = "") -> dict[str, str]:
    for name, value in (("source", source), ("main head", head)):
        if SHA.fullmatch(value or "") is None:
            raise SelectionError(f"{name} is not a full lowercase commit id")
    if RUN_ID.fullmatch(ci_run_id or "") is None:
        raise SelectionError("CI run id is missing")
    if not ancestor:
        raise SelectionError(f"{source} is not on main")
    if expected_source and expected_source != source:
        raise SelectionError(
            f"selected source {source} (CI run {ci_run_id}) is not the approved source "
            f"{expected_source}; nothing publishes. A later or older successful run never "
            "substitutes for the approved candidate")
    if expected_run and expected_run != ci_run_id:
        raise SelectionError(
            f"selected CI run {ci_run_id} is not the approved build run {expected_run}; "
            "rebuilt bytes are new identities that need their own qualification")
    return {
        "source": source, "ci-run-id": ci_run_id, "head": head,
        "source-is-head": "true" if source == head else "false",
        "artifacts": artifact_state(artifacts, source),
        "rule": rule,
    }


def summary(result: dict[str, str], repository: str) -> str:
    run_url = f"https://github.com/{repository}/actions/runs/{result['ci-run-id']}"
    lines = [
        "### Release source", "",
        "| Field | Value |", "|---|---|",
        f"| Selected source | `{result['source']}` |",
        f"| CI build run | [{result['ci-run-id']}]({run_url}) |",
        f"| main head | `{result['head']}` |",
        f"| Source is main head | {result['source-is-head']} |",
        f"| Hosted CI artifacts | {result['artifacts']} |",
        f"| Selection rule | {result['rule']} |", "",
    ]
    if result["artifacts"] != "retained":
        lines.append("Hosted targets cannot publish from this run: its CI artifacts are "
                     f"{result['artifacts']}. Re-running CI builds new bytes, which need "
                     "fresh qualification before publication.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("select")
    s.add_argument("--event", required=True); s.add_argument("--run-sha", default="")
    s.add_argument("--run-id", default=""); s.add_argument("--runs")
    r = sub.add_parser("report")
    for name in ("source", "ci-run-id", "head", "artifacts"):
        r.add_argument("--" + name, required=True)
    r.add_argument("--ancestor", choices=("true", "false"), required=True)
    r.add_argument("--expected-source", default=""); r.add_argument("--expected-run", default="")
    r.add_argument("--rule", default=""); r.add_argument("--repository", default="")
    r.add_argument("--output"); r.add_argument("--summary")
    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            runs = json.loads(Path(args.runs).read_text(encoding="utf-8")) if args.runs else None
            source, run, rule = select(args.event, run_sha=args.run_sha, run_id=args.run_id,
                                       runs=runs)
            print(f"source={source}\nci-run-id={run}\nrule={rule}")
            return 0
        result = report(
            source=args.source, ci_run_id=args.ci_run_id, head=args.head,
            ancestor=args.ancestor == "true",
            artifacts=json.loads(Path(args.artifacts).read_text(encoding="utf-8")),
            expected_source=args.expected_source.strip(),
            expected_run=args.expected_run.strip(), rule=args.rule)
        lines = "".join(f"{key}={value}\n" for key, value in result.items())
        sys.stdout.write(lines)
        if args.output:
            with open(args.output, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(lines)
        if args.summary:
            with open(args.summary, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(summary(result, args.repository))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
