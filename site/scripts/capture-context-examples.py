#!/usr/bin/env python3
"""Observe the shipped read/provenance helpers in disposable local fixtures.

No coding host or typed-artifact approval is simulated. Files and dedup markers
exist only in a temporary directory. Output is deterministic for these inputs
and exact helper bytes; --check compares the checked-in teaching capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "aebee1bb753d29e34030ee22c98c9eb8fabb1752"
SOURCES = ["core/pysrc/_readinjectlib.py", "core/pysrc/_provenancelib.py",
           "core/pysrc/pre-read.py", "core/pysrc/_hooklib.py"]
sys.path.insert(0, str(ROOT / "core/pysrc"))
import _provenancelib as provenance  # noqa: E402
import _readinjectlib as injection  # noqa: E402


def capture() -> dict:
    """Use actual git hashing and helper output, never a hand-authored verdict."""
    with tempfile.TemporaryDirectory(prefix="ca-context-example-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
        files = {
            "src/auth/session.py": "def active_session():\n    return True\n",
            "package.json": '{"type":"module"}\n',
            "src/ui/view.py": "def title():\n    return 'Saved searches'\n",
            ".codearbiter/security-controls.md": "# Security controls\nReview session boundaries.\n",
            ".codearbiter/decisions/0042-session-boundary.md": "---\ntitle: Session boundary\nstatus: accepted\ngoverns: src/auth/*\n---\nKeep session checks explicit.\n",
            ".codearbiter/specs/session.md": "# Session\n**Status:** approved\n**Governs:** src/auth/*\nRetain session behavior.\n",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        calls: list[list[str]] = []

        def runner(args, stdin_text):
            calls.append(list(args))
            return subprocess.run(["git", *args], input=stdin_text, text=True,
                                  encoding="utf-8", cwd=root, capture_output=True,
                                  check=True, timeout=10).stdout

        hashes = provenance.batch_hash(["src/auth/session.py", "package.json"], runner)
        records = {
            "standards": provenance.new_record("standards", entries=[{
                "path": "src/auth/session.py", "hash": hashes["src/auth/session.py"],
                "drift_trigger": True, "claims": [{"claim": "Session checks are explicit.", "lines": "1-2"}],
            }], created="2026-09-24"),
            "tech-stack": provenance.new_record("tech-stack", entries=[{
                "path": "package.json", "hash": hashes["package.json"],
                "drift_trigger": True, "claims": [{"claim": "The package declares module syntax.", "lines": "1"}],
            }], created="2026-09-24"),
        }
        for name, record in records.items():
            provenance.write_provenance(str(root / ".codearbiter/.provenance" / f"{name}.json"), record)

        def observe(identifier: str, relative: str) -> dict:
            calls.clear()
            index = injection.build_index(str(root))
            pointers = injection.governing_docs(relative, index, runner)
            calls.clear()
            emitted = injection.compute_injection(str(root), identifier, relative, runner)
            first_calls = len(calls)
            calls.clear()
            repeated = injection.compute_injection(str(root), identifier, relative, runner)
            return {"id": identifier, "path": relative, "candidate_pointers": pointers,
                    "emitted": emitted, "estimated_tokens": injection.token_estimate(emitted),
                    "hash_calls": first_calls, "repeated_emitted": repeated,
                    "repeat_hash_calls": len(calls)}

        cases = [observe("overlap", "src/auth/session.py"), observe("fresh", "package.json")]
        (root / "package.json").write_text('{"type":"commonjs"}\n', encoding="utf-8")
        cases.append(observe("changed", "package.json"))
        current = provenance.batch_hash(list(hashes), runner)
        drift = provenance.compute_drift(records, current)
        cases.append(observe("unmapped", "src/ui/view.py"))
        # Exercise the self-read early return itself; governing_docs is not a hook.
        calls.clear()
        self_read = injection.compute_injection(str(root), "self", ".codearbiter/security-controls.md", runner)
        budget_input = [{"tier": "decisions", "text": "Review this governing decision. " * 35}]
        budget_output = injection.assemble_context(budget_input)
        return {"schema_version": 1, "source_revision": SOURCE_REVISION,
                "evidence_kind": "disposable-helper-observation",
                "boundary": "Actual Python helper output over fixed local fixtures, not an installed-host run, approval, or validation of your repository.",
                "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES},
                "fixture_files": files, "provenance_records": records,
                "cases": cases, "changed_source_hashes": current, "drift_after_change": drift,
                "self_read": {"emitted": self_read, "hash_calls": len(calls)},
                "budget": {"proxy": "ceil(character_count / 4)", "limit": 150,
                           "input": budget_input, "emitted": budget_output,
                           "estimated_tokens": injection.token_estimate(budget_output)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = capture()
    if args.check:
        stored = ROOT / "site/src/data/context-examples.json"
        if json.loads(stored.read_text(encoding="utf-8")) != value:
            print("Context helper capture differs: inspect the source and regenerate intentionally.", file=sys.stderr)
            return 1
        print("Context helper capture matches exact sources and all disposable observations.")
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2) + "\n", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
