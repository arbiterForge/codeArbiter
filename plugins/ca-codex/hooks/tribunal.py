#!/usr/bin/env python3
# codeArbiter — local Tribunal run helper.
# Thin JSON CLI. No issue filing, telemetry sending, arbitrary execution or
# product mutation. A disposition records an already authorized caller action.
# Public API: main(argv=None) -> int (0 success, 1 refusal, 2 invalid CLI).

import argparse
import json
import sys

import _tribunalinventorylib as inventory
import _tribunalrunlib as runs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Persist and inspect source-bound Tribunal runs.")
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("inventory")
    collect.add_argument("--scope", default=".")
    collect.add_argument("--format", choices=("json", "markdown"), default="json")
    collect.add_argument("--max-file-bytes", type=int, default=1048576)
    collect.add_argument("--max-total-bytes", type=int, default=8388608)
    collect.add_argument("--history-limit", type=int, default=100)
    profile = commands.add_parser("profile")
    profile.add_argument("profile", choices=("deep", "standard", "extract"))
    profile.add_argument("--capabilities", type=json.loads, required=True)
    estimate = commands.add_parser("estimate")
    estimate.add_argument("--packet-bytes", type=int, required=True)
    estimate.add_argument("--profiles", type=json.loads, required=True)
    estimate.add_argument("--verification-candidates", type=int, default=0)
    estimate.add_argument("--concurrency", type=int, default=1)
    estimate.add_argument("--extraction-bytes", type=int, default=0)
    start = commands.add_parser("start")
    start.add_argument("--scope", default=".")
    start.add_argument("--untracked", action="append", default=None)
    start.add_argument("--no-untracked", action="store_true")
    start.add_argument("--target-digest")
    start.add_argument("--evidence-path", action="append", default=None)
    start.add_argument("--detail", type=json.loads)
    resume = commands.add_parser("resume-status")
    resume.add_argument("run")
    resume.add_argument("--scope")
    resume.add_argument("--target-digest")
    resume.add_argument("--evidence-path", action="append", default=None)
    read = commands.add_parser("read-run")
    read.add_argument("run")
    event = commands.add_parser("event")
    event.add_argument("run")
    event.add_argument("event")
    event.add_argument("--data", type=json.loads, default={})
    lead = commands.add_parser("lead")
    lead.add_argument("run")
    lead.add_argument("--record", type=json.loads)
    lead.add_argument("--id")
    lead.add_argument("--disposition")
    lead.add_argument("--rationale")
    triage = commands.add_parser("triage")
    triage.add_argument("run")
    eligibility = commands.add_parser("eligibility")
    for command in (triage, eligibility):
        command.add_argument("--finding", type=json.loads, required=True)
        command.add_argument("--record", type=json.loads, required=True)
        command.add_argument("--verification", type=json.loads)
    args = parser.parse_args(argv)
    if args.command == "inventory":
        result = inventory.collect_inventory(args.root, args.scope,
            max_file_bytes=args.max_file_bytes, max_total_bytes=args.max_total_bytes,
            history_limit=args.history_limit)
        output = (inventory.render_inventory_md(result) if args.format == "markdown"
                  else inventory.canonical_inventory_json(result))
        print(output, end="")
        return 0 if result["status"] in {"ok", "partial"} else 1
    if args.command == "profile":
        result = inventory.resolve_profile(args.profile, args.capabilities)
    elif args.command == "estimate":
        result = inventory.estimate_cost(args.packet_bytes, args.profiles,
            verification_candidates=args.verification_candidates,
            concurrency=args.concurrency, extraction_bytes=args.extraction_bytes)
    elif args.command == "start":
        if args.no_untracked and args.untracked:
            parser.error("--no-untracked cannot be combined with --untracked")
        result = runs.start_run(args.root, args.scope, [] if args.no_untracked else args.untracked, args.target_digest, args.detail, args.evidence_path)
    elif args.command == "resume-status":
        result = runs.resume_status(args.root, args.run, args.scope, args.target_digest, args.evidence_path)
    elif args.command == "read-run":
        result = runs.read_run(args.root, args.run)
    elif args.command == "event":
        if not isinstance(args.data, dict):
            parser.error("--data must be a JSON object")
        result = runs.append_event(args.root, args.run, args.event, **args.data)
    elif args.command == "lead":
        if args.record is not None:
            if args.id or args.disposition or args.rationale:
                parser.error("--record cannot be combined with disposition arguments")
            result = runs.write_lead(args.root, args.run, args.record)
        elif args.id and args.disposition and args.rationale:
            result = runs.dispose_lead(args.root, args.run, args.id, args.disposition, args.rationale)
        elif args.id or args.disposition or args.rationale:
            parser.error("lead disposition requires --id, --disposition and --rationale")
        else:
            result = runs.read_leads(args.root, args.run)
    elif args.command == "eligibility":
        result = runs.triage_eligibility(args.finding, args.record, args.verification)
    else:
        result = runs.append_triage(args.root, args.run, args.finding, args.record, args.verification)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    success = result.get("ok") if "ok" in result else result.get("status") in {"ok", "limited", "estimated"}
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
