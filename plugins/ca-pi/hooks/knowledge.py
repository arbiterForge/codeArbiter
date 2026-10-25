#!/usr/bin/env python3
# codeArbiter — read and update repository knowledge (context and decomposition).
#
# Thin command-line front for the native artifact engine's knowledge kinds,
# invoked by skill prose as:
#   "$PY" "<plugin>/hooks/knowledge.py" <verb> ...
#
# Verbs:
#   format                         active format and the five narrative paths
#   relevant PATH [PATH ...]       knowledge records relevant to these paths
#   read DOC [RECORD ...]          outline of a document, or exact records
#   commands [--purpose P]         declared command records (stored unrun)
#   add DOC --record JSON [--collection records|sources|notes]
#                                  add one entry; an identical one is reused
#   update DOC RECORD --fields JSON
#   retire DOC RECORD --reason TEXT
#   create-missing                 create any absent knowledge document, empty
#   initialize                     record structural initialization (HTML format)
#   convert [--finish TOKEN]       prepare HTML knowledge, then cut over after
#                                  the agent has recorded the Markdown content
#   promote RECORD                 add a decomposition work item to the task board
#   stale [DOC ...]                records whose scoped or cited paths changed since
#                                  their document's baseline commit (advisory)
#   rebaseline DOC                 set a document's baseline to the current commit
#                                  after its records were checked
#   merge-conflict PATH            resolve a Git conflict in one knowledge page
#                                  record by record (writes only when clean)
#
# DOC is one of project, tech-stack, coding-standards, security-controls,
# code-map, or decomposition. JSON arguments are inline text or @file.
# Every verb prints one JSON object. Nothing here grants permission to act:
# results are information, and host permissions and user stops still apply.

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _artifactlib  # noqa: E402
import _knowledgelib as kl  # noqa: E402
from _gitexec import git_executable  # noqa: E402
import hostapi  # noqa: E402
from _hooklib import project_root, set_host, utf8_stdio  # noqa: E402

DOC_CHOICES = (*kl.DOCUMENTS, "decomposition")
TITLES = {
    "project": ("Project", "Identity, purpose, users, scope and exclusions."),
    "tech-stack": ("Tech stack", "Runtime, frameworks, tooling and declared commands."),
    "coding-standards": ("Coding standards", "Structural and style conventions."),
    "security-controls": ("Security controls", "Trust boundaries, authentication, secret handling and prohibited primitives. Operative scope blocks stay in security-controls.md."),
    "code-map": ("Code map", "Observed components, interfaces and ownership."),
    "decomposition": ("Project decomposition", "Interview answers, intended architecture, phases and proposed work."),
}


def _doc_id(doc):
    return "DECOMP-PROJECT" if doc == "decomposition" else kl.artifact_id(doc)


def _client(root):
    # The installation-pinned binary only; never PATH or a caller-chosen one.
    return _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))


def _json_arg(value):
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(value)


def _op_id(prefix, *parts):
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"{prefix}-{digest[:40]}"


def _identity(client, doc_id):
    return client.call("identity", {"artifact_id": doc_id})


def _records(client, doc_id, collection="records"):
    ids = [r["id"] for r in client.outline(doc_id) if r.get("kind") == collection and not r.get("retired")]
    out = []
    model = _identity(client, doc_id)["model_sha256"]
    for start in range(0, len(ids), 32):
        offset = 0
        while True:
            page = client.call("read-batch", {"artifact_id": doc_id, "symbols": ids[start:start + 32],
                                              "model_sha256": model, "offset": offset, "budget": 65536})
            out.extend(item["record"] for item in page["records"])
            if page.get("next_offset") is None:
                break
            offset = page["next_offset"]
    return out


def _apply(client, doc_id, changes, purpose):
    current = _identity(client, doc_id)
    expected = {"revision": current["revision"], "model_sha256": current["model_sha256"]}
    # The same change against the same revision is the same operation, so a
    # retry after a lost response replays instead of applying twice.
    return client.call("apply", {"artifact_id": doc_id, "operation_id": _op_id(purpose, doc_id, expected, changes),
                                 "expected": expected, "changes": changes})


def _create(client, doc):
    doc_id = _doc_id(doc)
    title, summary = TITLES[doc]
    return client.call("create", {"operation_id": _op_id("knowledge-create", doc_id), "artifact_id": doc_id,
                                  "kind": "decomposition" if doc == "decomposition" else "knowledge",
                                  "slug": "project" if doc == "decomposition" else doc,
                                  "title": title, "summary": summary})


def _context_digest(root):
    with open(os.path.join(root, ".codearbiter", kl.CONTEXT_FILE), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main(argv=None):
    utf8_stdio()
    p = argparse.ArgumentParser(prog="knowledge")
    sub = p.add_subparsers(dest="verb", required=True)
    sub.add_parser("format")
    pr = sub.add_parser("relevant")
    pr.add_argument("paths", nargs="+")
    prd = sub.add_parser("read")
    prd.add_argument("doc", choices=DOC_CHOICES)
    prd.add_argument("records", nargs="*")
    pc = sub.add_parser("commands")
    pc.add_argument("--purpose")
    pa = sub.add_parser("add")
    pa.add_argument("doc", choices=DOC_CHOICES)
    pa.add_argument("--record", required=True)
    pa.add_argument("--collection", choices=("records", "sources", "notes"), default="records")
    pu = sub.add_parser("update")
    pu.add_argument("doc", choices=DOC_CHOICES)
    pu.add_argument("record")
    pu.add_argument("--fields", required=True)
    pt = sub.add_parser("retire")
    pt.add_argument("doc", choices=DOC_CHOICES)
    pt.add_argument("record")
    pt.add_argument("--reason", required=True)
    sub.add_parser("create-missing")
    sub.add_parser("initialize")
    pi = sub.add_parser("convert")
    pi.add_argument("--finish", metavar="TOKEN")
    pi.add_argument("--coverage", help="JSON section-to-record checklist, or @file, required with --finish")
    pp = sub.add_parser("promote")
    pp.add_argument("record")
    ps = sub.add_parser("stale")
    ps.add_argument("docs", nargs="*", choices=DOC_CHOICES)
    pb = sub.add_parser("rebaseline")
    pb.add_argument("doc", choices=DOC_CHOICES)
    pm = sub.add_parser("merge-conflict")
    pm.add_argument("path")
    args = p.parse_args(argv)

    root = project_root()
    if args.verb == "format":
        print(json.dumps({"format": kl.context_format(root), "paths": kl.narrative_paths(root),
                          "decomposition": kl.DECOMPOSITION_PATH if kl.context_format(root) == "html" else None}))
        return 0
    try:
        client = _client(root)
        result = _dispatch(args, client, root)
    except (_artifactlib.ArtifactError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _dispatch(args, client, root):
    if args.verb == "relevant":
        return client.call("knowledge-context", {"paths": args.paths, "budget": 65536})
    if args.verb == "read":
        doc_id = _doc_id(args.doc)
        if not args.records:
            return {"artifact_id": doc_id, "records": list(client.outline(doc_id))}
        return {"artifact_id": doc_id, "records": [
            client.call("read", {"artifact_id": doc_id, "symbol": rid, "mode": "exact"})["record"] for rid in args.records]}
    if args.verb == "commands":
        records = [r for r in _records(client, "CTX-TECH-STACK") if r.get("type") == "command"
                   and (not args.purpose or r["command"]["purpose"] == args.purpose)]
        return {"commands": records, "note": "Declared commands; run_state records what was reported, not a verified result."}
    if args.verb == "add":
        doc_id = _doc_id(args.doc)
        supplied = _json_arg(args.record)
        batch = isinstance(supplied, list)
        records = supplied if batch else [supplied]
        if not records or len(records) > 32 or any(not isinstance(record, dict) for record in records):
            raise ValueError("add accepts one record or a list of 1 to 32 records")
        existing = _records(client, doc_id, args.collection)
        pending = []
        selected = []
        for record in records:
            match = next((item for item in existing
                          if (item if "id" in record else {k: v for k, v in item.items() if k != "id"}) == record), None)
            if match is not None:
                selected.append({"record": match["id"], "reused": True})
                continue
            same_pending = next((i for i, item in enumerate(pending) if item == record), None)
            if same_pending is not None:
                selected.append({"pending": same_pending, "reused": True})
                continue
            selected.append({"pending": len(pending), "reused": False})
            pending.append(record)
        revision = None
        if pending:
            before = {r["id"] for r in client.outline(doc_id)}
            changes = [{"op": "record.add", "collection": args.collection, "record": record} for record in pending]
            result = _apply(client, doc_id, changes, "knowledge-add")
            created = [r["id"] for r in client.outline(doc_id) if r["id"] not in before]
            if len(created) != len(pending):
                raise ValueError("native add response did not identify every new record")
            revision = result["revision"]
            for item in selected:
                if "pending" in item:
                    item["record"] = created[item.pop("pending")]
        if batch:
            return {"artifact_id": doc_id, "records": selected, "revision": revision}
        return {"artifact_id": doc_id, **selected[0], "revision": revision}
    if args.verb == "update":
        doc_id = _doc_id(args.doc)
        result = _apply(client, doc_id, [{"op": "record.update", "symbol": args.record, "fields": _json_arg(args.fields)}], "knowledge-update")
        return {"artifact_id": doc_id, "record": args.record, "revision": result["revision"]}
    if args.verb == "retire":
        doc_id = _doc_id(args.doc)
        result = _apply(client, doc_id, [{"op": "record.retire", "symbol": args.record, "reason": args.reason}], "knowledge-retire")
        return {"artifact_id": doc_id, "record": args.record, "revision": result["revision"]}
    if args.verb == "create-missing":
        present = {e["artifact_id"] for kind in ("knowledge", "decomposition") for e in client.index(kind)}
        created = []
        for doc in DOC_CHOICES:
            if _doc_id(doc) not in present:
                _create(client, doc)
                created.append(_doc_id(doc))
        return {"created": created}
    if args.verb == "initialize":
        return client.call("knowledge-initialize", {"operation_id": _op_id("knowledge-init", _context_digest(root)),
                                                    "expected": {kl.LEGACY_PATHS["project"]: _context_digest(root)}})
    if args.verb == "convert":
        return _convert(client, root, args.finish, args.coverage)
    if args.verb == "promote":
        return _promote(client, root, args.record)
    if args.verb == "merge-conflict":
        return _merge_conflict(client, root, args.path)
    if args.verb == "stale":
        return _stale(client, root, args.docs or list(DOC_CHOICES))
    if args.verb == "rebaseline":
        return _rebaseline(client, root, args.doc)
    raise ValueError(f"unknown verb {args.verb}")


def _source_token(sources):
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def _convert(client, root, finish, coverage_arg):
    """One-time Markdown to HTML conversion. The agent records the content by
    inference; the engine only checks coverage and switches over."""
    if kl.context_format(root) == "html":
        raise ValueError("already converted")
    if not finish:
        present = {e["artifact_id"] for kind in ("knowledge", "decomposition") for e in client.index(kind)}
        created = []
        for doc in DOC_CHOICES:
            if _doc_id(doc) not in present:
                _create(client, doc)
                created.append(_doc_id(doc))
        sources, sections, cursor = None, [], 0
        while True:
            inventory = client.call("knowledge-cutover", {"operation_id": "knowledge-cutover-sections",
                                                          "mode": "sections", "cursor": cursor})
            if sources is None:
                sources = inventory["sources"]
            elif inventory["sources"] != sources:
                raise ValueError("Markdown changed during section inventory; run convert again")
            sections.extend(inventory["sections"])
            next_cursor = inventory["next_cursor"]
            if next_cursor is None:
                break
            if next_cursor <= cursor:
                raise ValueError("section inventory did not advance")
            cursor = next_cursor
        return {"created": created, "read": sorted(sources),
                "sections": sections, "token": _source_token(sources),
                "next": "Read each file. Add records or notes for every meaningful section, in batches of at most 32. "
                        "Map every returned section ID to its saved record or note references in a JSON checklist "
                        "([{section, records}]); use [] only for sections marked content=false. Exclude secret values. "
                        "Then run knowledge.py convert --finish TOKEN --coverage @checklist.json."}
    if not coverage_arg:
        raise ValueError("--finish requires --coverage with one mapping per returned section")
    coverage = _json_arg(coverage_arg)
    preview = client.call("knowledge-cutover", {"operation_id": "knowledge-cutover-preview", "mode": "preview",
                                                "coverage": coverage})
    if finish != _source_token(preview["sources"]):
        raise ValueError("a Markdown file changed after it was read; record the change and run convert again")
    return client.call("knowledge-cutover", {"operation_id": _op_id("knowledge-cutover", finish), "mode": "apply",
                                             "expected": preview["expected"], "coverage": coverage})


def _promote(client, root, record_id):
    """Add a decomposition work item to the task board once.

    The board owns task state; the work item only keeps the back-reference.
    Board first, then the reference: a crash between the two leaves the task,
    and a retry finds it by origin instead of adding it again."""
    record = client.call("read", {"artifact_id": "DECOMP-PROJECT", "symbol": record_id, "mode": "exact"})["record"]
    if record.get("type") != "work_item":
        raise ValueError("only decomposition work items are promoted")
    origin = f"DECOMP-PROJECT#{record_id}"
    taskwrite = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taskwrite.py")
    done = subprocess.run([sys.executable, taskwrite, "add", record["title"], "--from", origin],
                          cwd=root, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise ValueError(f"task board refused the promotion: {done.stderr.strip() or done.stdout.strip()}")
    board_line = done.stdout.strip()
    if record.get("promotion") is None:
        _apply(client, "DECOMP-PROJECT", [{"op": "record.update", "symbol": record_id,
                                           "fields": {"promotion": {"board_id": record["title"][:40], "origin": origin}}}],
               "knowledge-promote")
    return {"record": record_id, "origin": origin, "board": board_line}


def _git_out(root, *arguments):
    result = subprocess.run([git_executable(), *arguments], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise ValueError(f"git {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout


def _stale(client, root, docs):
    """Advisory freshness: which records may need a look, never a verdict.

    A record is listed when a path it is scoped to, or a source it cites,
    changed since its document's baseline commit. Unrelated edits list
    nothing, and nothing here blocks work or resets other records."""
    from _scopelib import _glob_to_re
    head = _git_out(root, "rev-parse", "HEAD").strip()
    report = []
    for doc in docs:
        doc_id = _doc_id(doc)
        identity = _identity(client, doc_id)
        baseline = _baseline(client, doc_id)
        if not baseline:
            report.append({"artifact_id": doc_id, "baseline": None,
                           "note": "no baseline commit; run rebaseline after checking the records"})
            continue
        if baseline == head:
            report.append({"artifact_id": doc_id, "baseline": baseline, "stale": []})
            continue
        changed = [p for p in _git_out(root, "diff", "--name-only", f"{baseline}..HEAD").splitlines() if p]
        changed += [p for p in _git_out(root, "diff", "--name-only").splitlines() if p and p not in changed]
        sources = {s["id"]: s.get("locator", "") for s in _records(client, doc_id, "sources")}
        stale = []
        for record in _records(client, doc_id):
            patterns = [_glob_to_re(g) for g in record["scope"]["paths"]]
            cited = [sources.get(ref, "") for ref in record.get("source_refs", [])]
            hits = sorted({p for p in changed
                           if any(rx.match(p) for rx in patterns) or any(c and (p == c or p.startswith(c.rstrip("/") + "/")) for c in cited)})
            if hits:
                stale.append({"record": record["id"], "title": record["title"], "changed_paths": hits[:20]})
        report.append({"artifact_id": doc_id, "baseline": baseline, "revision": identity["revision"], "stale": stale})
    return {"head": head, "documents": report,
            "note": "Advisory: listed records cite or govern changed paths. Check them; unlisted records are unaffected."}


def _baseline(client, doc_id):
    page = client.call("outline", {"artifact_id": doc_id, "budget": 4096})
    return (page.get("baseline") or {}).get("commit")


def _rebaseline(client, root, doc):
    doc_id = _doc_id(doc)
    head = _git_out(root, "rev-parse", "HEAD").strip()
    import datetime
    baseline = {"repository": None, "commit": head, "observed_date": datetime.date.today().isoformat()}
    result = _apply(client, doc_id, [{"op": "header.update", "fields": {"baseline": baseline}}], "knowledge-rebaseline")
    return {"artifact_id": doc_id, "baseline": head, "revision": result["revision"]}


def _stage(root, number, path):
    """One Git index stage of a conflicted file, or "" when that stage is absent."""
    result = subprocess.run([git_executable(), "show", f":{number}:{path}"], cwd=root, capture_output=True)
    if result.returncode != 0:
        if number == 1:
            return ""
        raise ValueError(f"no conflict stage {number} for {path}; is the merge still in progress?")
    return result.stdout.decode("utf-8")


def _merge_conflict(client, root, path):
    path = path.replace("\\", "/")
    if path not in kl.HTML_PATHS.values() and path != kl.DECOMPOSITION_PATH:
        raise ValueError("merge-conflict resolves knowledge pages only")
    with open(os.path.join(root, path), "rb") as handle:
        current = hashlib.sha256(handle.read()).hexdigest()
    base, ours, theirs = (_stage(root, n, path) for n in (1, 2, 3))
    return client.call("knowledge-merge", {
        "operation_id": _op_id("knowledge-merge", path, current), "path": path, "base": base,
        "ours": ours, "theirs": theirs, "expected_current_sha256": current})


def run(host, argv=None):
    """Host-seam entry point (ADR-0011)."""
    set_host(host)
    return main(argv)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
