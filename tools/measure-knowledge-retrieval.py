#!/usr/bin/env python3
"""Measure whole-document Markdown context reads against scoped HTML knowledge reads.

Builds the same synthetic project twice per size (small, large): once as the
five Markdown context documents an agent reads in full, once as HTML knowledge
records read through `knowledge.py relevant <path>`. It reports returned bytes,
an estimated token count (characters / 4; no tokenizer is bundled), helper
process counts, cold and warm latency, and what the scoped read left out.

This is a measurement, not a gate: it asserts no percentage or threshold.
It needs a built native candidate in ARTIFACT_TEST_INSTALLATION, like the
candidate-backed suites:

    ARTIFACT_TEST_INSTALLATION=<candidate> python tools/measure-knowledge-retrieval.py
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".github" / "scripts"))
from test_artifact_authoring import build_installation  # noqa: E402

DOCS = ("project", "tech-stack", "coding-standards", "security-controls", "code-map")
LEGACY = {"project": "CONTEXT.md", "tech-stack": "tech-stack.md", "coding-standards": "coding-standards.md",
          "security-controls": "security-controls.md", "code-map": "code-map.md"}
SIZES = {"small": (4, 8), "large": (40, 60)}  # (areas, records per document)
TARGET = "src/area-001/session.ts"


def record(doc, area, index):
    """One record; every fourth (offset from the area cycle) is repository-wide."""
    kind = {"tech-stack": "fact", "coding-standards": "convention", "security-controls": "constraint",
            "code-map": "component", "project": "scope"}[doc]
    scoped = index % 4 != 1
    return {"type": kind, "title": f"{doc} rule {index} for area {area:03d}",
            "statement": (f"Area {area:03d} {doc} statement {index}: the module keeps its own boundary, "
                          "validates input at the edge and reports failures with a stable error code."),
            "basis": "user-reported",
            "scope": {"paths": [f"src/area-{area:03d}/**"] if scoped else []},
            "related_refs": [], "source_refs": []}


def markdown(doc, records):
    lines = [f"# {doc}", ""]
    for item in records:
        lines += [f"## {item['title']}", "", item["statement"]]
        if item["scope"]["paths"]:
            lines += ["", "Applies to: " + ", ".join(item["scope"]["paths"])]
        lines.append("")
    return "\n".join(lines)


def load_knowledge(plugin):
    spec = importlib.util.spec_from_file_location("knowledge_cli", plugin / "hooks" / "knowledge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(plugin, root, *arguments):
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "CLAUDE_PROJECT_DIR": str(root)}
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-B", str(plugin / "hooks" / arguments[0]), *arguments[1:]],
                            cwd=root, env=env, capture_output=True, encoding="utf-8", timeout=300)
    elapsed = time.perf_counter() - started
    if result.returncode:
        raise SystemExit(f"{arguments} failed: {result.stderr}")
    return result.stdout, elapsed


def measure(plugin, knowledge, size):
    areas, per_doc = SIZES[size]
    with tempfile.TemporaryDirectory(prefix=f"ca-measure-{size}-") as directory:
        root = Path(directory).resolve()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        run(plugin, root, "init-codearbiter.py", "--root", str(root))
        run(plugin, root, "knowledge.py", "create-missing")
        client = knowledge._client(str(root))
        corpus = {doc: [record(doc, 1 + i % areas, i) for i in range(per_doc)] for doc in DOCS}
        for doc, records in corpus.items():
            for start in range(0, len(records), 20):
                changes = [{"op": "record.add", "collection": "records", "record": item}
                           for item in records[start:start + 20]]
                knowledge._apply(client, knowledge._doc_id(doc), changes, "measure-add")
        # Old: the agent reads all five Markdown documents in full.
        legacy = root / "legacy"
        legacy.mkdir()
        old_bytes = 0
        for doc, records in corpus.items():
            path = legacy / LEGACY[doc]
            path.write_text(markdown(doc, records), encoding="utf-8")
        started = time.perf_counter()
        for doc in DOCS:
            old_bytes += len((legacy / LEGACY[doc]).read_bytes())
        old_latency = time.perf_counter() - started
        # New: one scoped helper call for the touched path.
        cold_out, cold = run(plugin, root, "knowledge.py", "relevant", TARGET)
        warm_out, warm = run(plugin, root, "knowledge.py", "relevant", TARGET)
        result = json.loads(warm_out)
        total = sum(len(records) for records in corpus.values())
        returned = len(result["knowledge"])
        return {
            "size": size, "records_total": total, "target_path": TARGET,
            "old_full_documents": {"bytes": old_bytes, "estimated_tokens": old_bytes // 4,
                                   "file_reads": len(DOCS), "helper_processes": 0,
                                   "latency_seconds": round(old_latency, 4)},
            "new_scoped_relevant": {"bytes": len(warm_out.encode("utf-8")),
                                    "estimated_tokens": len(warm_out) // 4,
                                    "helper_processes": 1, "engine_requests": 1,
                                    "cold_latency_seconds": round(cold, 3),
                                    "warm_latency_seconds": round(warm, 3),
                                    "records_returned": returned,
                                    "records_left_out": total - returned,
                                    "unrelated_records_counted": result["knowledge_unmatched_records"],
                                    "omitted_for_budget": len(result["knowledge_omitted"]),
                                    "unreadable_documents": len(result["knowledge_unreadable"])},
            "cold_output_matches_warm": cold_out == warm_out,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size", choices=tuple(SIZES), action="append")
    args = parser.parse_args()
    if not os.environ.get("ARTIFACT_TEST_INSTALLATION"):
        raise SystemExit("ARTIFACT_TEST_INSTALLATION must name a built native candidate")
    owner, installation = build_installation()
    try:
        plugin = installation.parent.parent
        knowledge = load_knowledge(plugin)
        report = [measure(plugin, knowledge, size) for size in (args.size or list(SIZES))]
    finally:
        if owner is not None:
            owner.cleanup()
    print(json.dumps({"kind": "knowledge-retrieval-measurement", "token_estimate": "characters / 4",
                      "results": report}, indent=2))


if __name__ == "__main__":
    main()
