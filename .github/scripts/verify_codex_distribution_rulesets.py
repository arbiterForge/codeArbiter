#!/usr/bin/env python3
"""Fail closed unless live GitHub rulesets protect Codex distribution refs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def verify(
    policy: dict[str, Any], rulesets: list[dict[str, Any]],
    publisher_actor_id: int, verifier_actor_id: int,
) -> None:
    if type(publisher_actor_id) is not int or publisher_actor_id <= 0 or publisher_actor_id == 15368:
        raise ValueError("Codex publisher must be a dedicated GitHub App, not the general Actions integration")
    if type(verifier_actor_id) is not int or verifier_actor_id <= 0 or verifier_actor_id == 15368:
        raise ValueError("Codex ruleset verifier must be a dedicated GitHub App")
    if verifier_actor_id == publisher_actor_id:
        raise ValueError("Codex publisher and ruleset verifier must be distinct GitHub Apps")
    expected = policy.get("rulesets")
    if not isinstance(expected, list) or len(expected) != 2:
        raise ValueError("Codex distribution policy has no closed ruleset contract")
    for requirement in expected:
        matches = [item for item in rulesets if item.get("name") == requirement.get("name")]
        if len(matches) != 1:
            raise ValueError(f"required active ruleset is absent or ambiguous: {requirement.get('name')}")
        observed = matches[0]
        if observed.get("enforcement") != "active" or observed.get("target") != requirement.get("target"):
            raise ValueError(f"required ruleset is not active on the expected target: {requirement['name']}")
        refs = (observed.get("conditions") or {}).get("ref_name") or {}
        if refs.get("include") != requirement.get("include") or refs.get("exclude") not in ([], None):
            raise ValueError(f"required ruleset ref condition drifted: {requirement['name']}")
        rule_types = {item.get("type") for item in observed.get("rules", []) if isinstance(item, dict)}
        if not set(requirement.get("rules", [])).issubset(rule_types):
            raise ValueError(f"required ruleset controls drifted: {requirement['name']}")
        publisher_contract = requirement.get("publisher")
        if not isinstance(publisher_contract, dict) or publisher_contract.get("actor_id_source") != "CODEX_DISTRIBUTION_APP_ID":
            raise ValueError("Codex distribution policy does not require its dedicated App identity")
        publisher = {
            "actor_type": publisher_contract.get("actor_type"),
            "actor_id": publisher_actor_id,
            "bypass_mode": publisher_contract.get("bypass_mode"),
        }
        bypass = observed.get("bypass_actors")
        if not isinstance(bypass, list) or bypass != [publisher]:
            raise ValueError(f"required ruleset publisher bypass drifted or is not observable: {requirement['name']}")


def fetch_live(repository: str) -> list[dict[str, Any]]:
    summary = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/rulesets?includes_parents=true&targets=branch,tag&per_page=100"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    pages = json.loads(summary.stdout)
    rows = [row for page in pages for row in page]
    details = []
    for row in rows:
        url = ((row.get("_links") or {}).get("self") or {}).get("href")
        if not isinstance(url, str) or not url.startswith("https://api.github.com/"):
            raise ValueError("GitHub ruleset summary omitted its authoritative API URL")
        result = subprocess.run(
            ["gh", "api", url], check=True, capture_output=True,
            text=True, encoding="utf-8",
        )
        details.append(json.loads(result.stdout))
    return details


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=Path(".github/codex-distribution-policy.json"))
    parser.add_argument("--publisher-actor-id", type=int, required=True)
    parser.add_argument("--verifier-actor-id", type=int, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repository")
    source.add_argument("--rulesets", type=Path)
    args = parser.parse_args(argv)
    policy = _load(args.policy)
    rulesets = fetch_live(args.repository) if args.repository else _load(args.rulesets)
    if not isinstance(rulesets, list):
        raise ValueError("GitHub ruleset response is not an array")
    verify(policy, rulesets, args.publisher_actor_id, args.verifier_actor_id)
    print("Codex distribution rulesets are active and publisher-restricted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
