"""PI-D07 explicit first-POSIX public-parent TUI fixture (not a report importer).

No installed-author qualification follows from this module's pure tests. The
owning authenticated coordinator supplies production payloads and its existing
reviewed Pi acquisition; this module never acquires or substitutes a runtime.
"""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

CAP = 4 * 1024 * 1024
BODY_SECONDS = 90
REQUEST_CAP = 1024 * 1024
PROFILE = "trusted-host-exact-operation-v1"
PROVIDER_RECORDS = 12
INSPECTION_ROLES = ("backend-author", "coverage-auditor")
INSPECTION_REDACTION = "[REDACTED — secret-pattern match removed before transmission]"
EFFECT_COUNTS = ("requested", "completed", "failed", "refused", "unknown", "unsettled", "containmentUnverified")

def decode(raw, limit=REQUEST_CAP):
    require(type(raw) is bytes and len(raw) <= limit, "json-cap")
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate-json-key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "json-number"))

def read_document(path):
    import stat
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info,"st_file_attributes",0)&0x400, "linked-config")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 16 * 1024 * 1024, "bounded-config")
    raw = path.read_bytes()
    after = path.stat()
    require((info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns) == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
            and len(raw) == info.st_size, "config-drift")
    return decode(raw,16*1024*1024)

def readable(raw):
    """Projection of actual terminal bytes, never a replacement TUI owner."""
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return text.replace("\r", "")

def dialog_text(raw):
    # Pi's full-screen renderer positions the cursor and clears each text row.
    return readable(re.sub(rb"\x1b\[[1-9][0-9]*;1H\x1b\[2K", b"\n", raw))

def require(value, code):
    if not value:
        raise ValueError(code)

def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def sha(value):
    return hashlib.sha256(value).hexdigest()

def operations(nonce):
    require(type(nonce) is str and re.fullmatch(r"[0-9a-f]{16}", nonce), "fixture-nonce")
    path = "effect-" + nonce + ".txt"
    return [
        {"tool": "write", "params": {"path": path, "content": "before-" + nonce}},
        {"tool": "edit", "params": {"path": path, "edits": [{"oldText": "before-" + nonce, "newText": "after-" + nonce}]}},
        {"tool": "bash", "params": {"command": "printf 'command-" + nonce + "\\n' >> command-" + nonce + ".txt", "timeout": 15}},
    ]

def declined_write(nonce):
    require(type(nonce) is str and re.fullmatch(r"[0-9a-f]{16}", nonce), "fixture-nonce")
    return {"tool": "write", "params": {"path": "declined-" + nonce + ".txt", "content": "declined-" + nonce}}

class PromptGate:
    def __init__(self, nonce):
        self.nonce = nonce
        self.ops = [*operations(nonce), declined_write(nonce)]
        self.index = 0
        self.raw = bytearray()
        self.consumed = 0
        self.events = []
        self.pending_decline = None

    def feed(self, chunk):
        require(type(chunk) is bytes and len(self.raw) + len(chunk) <= CAP, "terminal-cap")
        self.raw.extend(chunk)

    def consent(self, cwd):
        if self.index == len(self.ops):
            return None
        if self.pending_decline is not None:
            event = self.pending_decline
            redraw = dialog_text(bytes(self.raw[event["new_output_end"]:]))
            if not re.search(r"(?m)^ *→ No *$", redraw):
                return None
            self.events.append({**event, "input_hex": "6a0d", "decision": "declined",
                                "no_selected_output_end": len(self.raw), "no_selected_sha256": sha(redraw.encode())})
            self.pending_decline = None
            self.consumed = len(self.raw)
            self.index += 1
            return b"\r"
        operation = self.ops[self.index]
        exact = compact(operation["params"])
        digest = sha(exact.encode())
        # The consumed raw-byte boundary plus a different tool/exact digest for
        # each step prevents old dialog redraws from authorizing a later effect.
        text = dialog_text(bytes(self.raw[self.consumed:]))
        title = "Allow governed operation?"
        if title not in text:
            return None
        text = text[text.rfind(title):]
        required = ("Delegated " + operation["tool"] + " in " + cwd, exact,
                    "SHA-256: " + digest, "The parent executes this exact request", "Yes", "No")
        if not all(value in text for value in required):
            return None
        event = {"operation": self.index, "tool": operation["tool"], "params_sha256": digest,
                 "new_output_start": self.consumed, "new_output_end": len(self.raw),
                 "rendered_sha256": sha(text.encode()), "consent": "scripted-fixture-key-on-public-parent-dialog"}
        if self.index == len(self.ops) - 1:
            if not re.search(r"(?m)^ *→ Yes *$", text):
                return None
            self.pending_decline = event
            return b"j"  # Pi 1.5.0's public selector moves one row down.
        self.events.append({**event, "input_hex": "0d"})
        self.consumed = len(self.raw)
        self.index += 1
        return b"\r"

def transport_length(method, path, headers, nonce):
    require(method == "POST" and path == "/v1/chat/completions", "provider-route")
    require(headers.get("Authorization") == "Bearer dummy-" + nonce
            and headers.get("Origin") is None and headers.get("Transfer-Encoding") is None, "provider-auth")
    length = headers.get("Content-Length", "")
    require(type(length) is str and re.fullmatch(r"[1-9][0-9]{0,6}", length) and int(length) <= REQUEST_CAP, "provider-framing")
    return int(length)

def tool_call(name, params, call_id):
    return {"role": "assistant", "tool_calls": [{"index": 0, "id": call_id, "type": "function",
            "function": {"name": name, "arguments": compact(params)}}]}, "tool_calls"


class InspectionChain:
    """One inspection-only author, then one reviewer, through the installed dispatcher."""

    def __init__(self, nonce, snapshot):
        self.nonce = nonce
        self.snapshot = snapshot
        self.before = snapshot()
        require(not self.before["declined_target_present"], "inspection-effect-drift")
        self.call_id = "fixture-inspection-parent-" + nonce
        self.task = "Inspect existing PI-D07 fixture results without changing them " + nonce
        self.canary = "synthetic secret marker " + nonce
        self.author_summary = "Observed prior command output.\n" + self.canary + "\nInspection only; no changes made."
        self.reviewer_summary = "Read the prior author file. No changes made."
        self.turn = 0
        self.read_sha256 = {}
        self.prior_sha256 = None
        self.receipt = None

    def dispatch(self):
        return tool_call("codearbiter_dispatch", {"mode": "chain", "roles": list(INSPECTION_ROLES),
                         "task": self.task, "limits": {"maxChildOutputBytes": 512, "maxAggregateOutputBytes": 1024}},
                         self.call_id)

    def child(self, names, messages, results):
        require(self.turn < 4, "inspection-route")
        reviewer = self.turn >= 2
        role = INSPECTION_ROLES[1] if reviewer else INSPECTION_ROLES[0]
        tools = {"read", "bash"} if reviewer else {"read", "bash", "write", "edit"}
        require(len(names) == len(tools) and set(names) == tools, "inspection-role-tools")
        users = [m.get("content") for m in messages if type(m) is dict and m.get("role") == "user"]
        require(len(users) == 1, "inspection-task")
        content = users[0]
        if type(content) is list:
            require(len(content) == 1 and type(content[0]) is dict and content[0].get("type") == "text", "inspection-task")
            content = content[0].get("text")
        require(type(content) is str, "inspection-task")
        task = decode(content.encode(), 2048)
        keys = {"protocol", "task", "response"}
        require(type(task) is dict and set(task) == (keys | {"prior"} if reviewer else keys)
                and task["protocol"] == "codearbiter-dispatch-v1" and task["task"] == self.task, "inspection-task")
        if reviewer:
            redacted = self.author_summary.replace(self.canary, INSPECTION_REDACTION)
            require(task["prior"] == {"role": INSPECTION_ROLES[0], "state": "accepted", "summary": redacted},
                    "inspection-redacted-prior")
            self.prior_sha256 = sha(task["prior"]["summary"].encode())
        call_id = "fixture-inspection-read-" + role + "-" + self.nonce
        if self.turn % 2 == 0:
            require(not results, "inspection-read-start")
            path = ("effect-" if reviewer else "command-") + self.nonce + ".txt"
            reply = tool_call("read", {"path": path}, call_id)
        else:
            expected = ("after-" + self.nonce) if reviewer else ("command-" + self.nonce + "\n")
            require(len(results) == 1 and results[0].get("tool_call_id") == call_id
                    and results[0].get("content") == expected, "inspection-read-result")
            self.read_sha256[role] = sha(results[0]["content"].encode())
            summary = self.reviewer_summary if reviewer else self.author_summary
            reply = {"content": compact({"state": "accepted", "summary": summary})}, "stop"
        self.turn += 1
        return reply

    def finish(self, results, original_call_id):
        require(self.turn == 4 and [m.get("tool_call_id") for m in results] == [original_call_id, self.call_id],
                "inspection-route")
        raw = results[-1].get("content")
        require(type(raw) is str, "inspection-parent-result")
        result = decode(raw.encode(), 4096)
        require(type(result) is dict and set(result) == {"state", "children"} and result["state"] == "accepted"
                and type(result["children"]) is list and len(result["children"]) == 2, "inspection-parent-result")
        for child, role, expected in zip(result["children"], INSPECTION_ROLES, (self.author_summary, self.reviewer_summary)):
            require(type(child) is dict and child.get("role") == role and child.get("state") == "accepted"
                    and child.get("summary") == expected, "inspection-role-result")
        author, reviewer = result["children"]
        effect = author.get("effects")
        require(type(effect) is dict and set(effect) == {"profile", "observation", *EFFECT_COUNTS}
                and effect["profile"] == PROFILE and effect["observation"] == "parent-recorded"
                and all(type(effect[k]) is int and effect[k] == 0 for k in EFFECT_COUNTS)
                and "effects" not in reviewer, "inspection-zero-effects")
        after = self.snapshot()
        require(self.before == after, "inspection-effect-drift")
        self.receipt = {"roles": list(INSPECTION_ROLES), "read_sha256": dict(self.read_sha256),
                        "prior_redacted_sha256": self.prior_sha256, "parent_result_sha256": sha(raw.encode()),
                        "author_effects": effect, "before": self.before, "after": after}
        self.turn += 1


class ProviderProtocol:
    """One original author and a bounded inspection chain share the original fixture endpoint."""
    def __init__(self, nonce):
        self.ops = [*operations(nonce), declined_write(nonce)]
        self.nonce = nonce
        self.parent_call_id = "fixture-parent-" + nonce
        self.parent_turns = 0
        self.child_turns = 0
        self.records = []
        self.complete = False
        self.declined_result = None
        self.inspection_snapshot = None
        self.inspection = None
        self.bytes = 0
        self.failed = False

    def record(self, value):
        if len(self.records) < PROVIDER_RECORDS + 1:
            self.records.append(value)
        else:
            self.failed = True
        self.failed = self.failed or value.get("refused") is True

    def response(self, body):
        require(type(body) is dict and body.get("model") == "gpt-fixture" and body.get("stream") is True
                and type(body.get("messages")) is list and 0 < len(body["messages"]) <= 128
                and type(body.get("tools")) is list and 0 < len(body["tools"]) <= 128, "provider-shape")
        size = len(compact(body).encode())
        require(size <= REQUEST_CAP and self.bytes + size <= CAP, "provider-body-cap")
        names = []
        for tool in body["tools"]:
            require(type(tool) is dict and type(tool.get("function")) is dict
                    and type(tool["function"].get("name")) is str, "provider-tools")
            names.append(tool["function"]["name"])
        results = [m for m in body["messages"] if type(m) is dict and m.get("role") == "tool"]
        parent = "codearbiter_dispatch" in names
        require(not self.complete, "parent-turn-cap")
        if self.inspection is not None:
            if parent:
                self.inspection.finish(results, self.parent_call_id)
                self.complete = True
                reply = {"content": "PI-D07 fixture completed " + self.nonce}, "stop"
            else:
                reply = self.inspection.child(names, body["messages"], results)
            self.bytes += size
            return reply
        if parent:
            if self.parent_turns == 0:
                require(not results and self.child_turns == 0, "parent-start")
                name = "codearbiter_dispatch"
                params = {"mode": "single", "roles": ["backend-author"], "task": "Run only the deterministic owned PI-D07 fixture " + self.nonce + "."}
                call_id = self.parent_call_id
            else:
                require(self.child_turns == len(self.ops) + 1 and self.declined_result is not None
                        and [m.get("tool_call_id") for m in results] == [self.parent_call_id], "parent-result")
                require(callable(self.inspection_snapshot), "inspection-snapshot-owner")
                self.inspection = InspectionChain(self.nonce, self.inspection_snapshot)
                self.parent_turns += 1
                self.bytes += size
                return self.inspection.dispatch()
            self.parent_turns += 1
        else:
            require(self.parent_turns == 1, "parent-before-child")
            require(self.child_turns <= len(self.ops), "child-turn-cap")
            if self.child_turns:
                require(results and results[-1].get("tool_call_id") == "fixture-child-" + str(self.child_turns - 1) + "-" + self.nonce, "child-result")
            else:
                require(not results, "child-start")
            if self.child_turns == len(self.ops):
                self.declined_result = read_declined_result(results[-1].get("content"))
                self.child_turns += 1
                self.bytes += size
                return {"content": compact({"state": "accepted", "summary": "Owned fixture " + self.nonce
                                            + ": three approved effects and one declined write observed"})}, "stop"
            operation = self.ops[self.child_turns]
            name, params = operation["tool"], operation["params"]
            require(name in names, "child-tool-missing")
            call_id = "fixture-child-" + str(self.child_turns) + "-" + self.nonce
            self.child_turns += 1
        self.bytes += size
        return tool_call(name, params, call_id)

def read_declined_result(content):
    expected = {"v": 1, "admission": "denied", "execution": "not-started", "containment": "not-applicable",
                "observation": "unavailable", "recovery": "new-operation-required", "reason": "permission-denied"}
    require(type(content) is str and len(content) <= 1024, "declined-write-result")
    try:
        value = decode(content.encode())
    except (ValueError, UnicodeError) as error:
        raise ValueError("declined-write-result") from error
    require(type(value) is dict and set(value) == {*expected, "requestId"}
            and type(value["v"]) is int and all(value[key] == wanted for key, wanted in expected.items())
            and type(value["requestId"]) is str
            and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value["requestId"]),
            "declined-write-result")
    return value

def runtime_entry(manifest):
    require(type(manifest) is dict and manifest.get("name") == "@earendil-works/pi-coding-agent"
            and manifest.get("version") == "1.5.0", "supported-Pi-1.5-required")
    bins = manifest.get("bin", {})
    entry = bins.get("pi") if type(bins) is dict else bins
    require(entry == "dist/bundle/cli.js", "reviewed-Pi-cli-required")
    return entry

def authenticated_roles(expected, payloads, physical):
    require(type(payloads) is dict and type(physical) is dict, "authenticated-payloads")
    result = {}
    for role, prefix in (("promoted-stage", "artifact-host-payloads-"), ("release-packages", "artifact-release-packages-")):
        name = prefix + expected.get("source_commit", "")
        value = payloads.get(name, {})
        require(type(value) is dict and type(value.get("artifact_id")) is int and value["artifact_id"] > 0
                and type(value.get("archive_sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", value["archive_sha256"])
                and type(value.get("members")) is list, "authenticated-payloads")
        rows = value["members"]
        require(0 < len(rows) <= 4096, "authenticated-payloads")
        members = {}
        for row in rows:
            require(type(row) is dict and set(row) == {"path", "sha256"}, "authenticated-payloads")
            path = row["path"]
            require(type(path) is str and str(PurePosixPath(path)) == path and not PurePosixPath(path).is_absolute()
                    and ".." not in PurePosixPath(path).parts and ":" not in path and "\\" not in path
                    and path not in members and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "authenticated-payloads")
            members[path] = row["sha256"]
        require(members == physical.get(role), "authenticated-physical-payload")
        result[role] = {"artifact_name": name, **{k: value[k] for k in ("artifact_id", "archive_sha256", "members")}}
    require(result["promoted-stage"]["artifact_id"] != result["release-packages"]["artifact_id"], "distinct-artifact-roles")
    return result

def private_layout(workspace, output, protected):
    owned = [Path(workspace), Path(output)]
    require(all(p.is_absolute() for p in owned), "absolute-private-paths")
    require(not owned[0].is_relative_to(owned[1]) and not owned[1].is_relative_to(owned[0]), "owned-output-boundary")
    for target in owned:
        for source in map(Path, protected):
            require(source.is_absolute() and not target.is_relative_to(source) and not source.is_relative_to(target), "read-only-input-overlap")

def check_effects(nonce, stored, effects):
    expected = operations(nonce)
    require(effects == {"file": ("after-" + nonce).encode(), "command": ("command-" + nonce + "\n").encode()}, "exact-effects")
    require(type(stored) is list and len(stored) == 7, "journal-population")
    rows = [v.get("record", {}) for v in stored]
    groups = {}
    for row in rows:
        require(row.get("profile") == PROFILE and row.get("consentSource") == "parent-human-confirmation"
                and type(row.get("permissionCorrelation")) is str, "journal-authority")
        groups.setdefault(row.get("operationId"), []).append(row)
    require(len(groups) == 3, "journal-operations")
    tools = []
    for group in groups.values():
        tool = group[0].get("tool")
        phases = [row.get("phase") for row in group]
        require(sorted(phases) == sorted(["claimed", "observed"] + (["started"] if tool == "bash" else [])), "journal-phases")
        require(all(row.get("tool") == tool and row.get("digest") == group[0].get("digest")
                    and row.get("requestId") == group[0].get("requestId") for row in group), "journal-identity")
        observed = next(row for row in group if row["phase"] == "observed")
        operation = next((v for v in expected if v["tool"] == tool), None)
        require(operation is not None and group[0].get("digest") == sha(compact({"profile": PROFILE, **operation}).encode()), "journal-request-digest")
        require(observed.get("execution") == "completed"
                and observed.get("containment") == ("verified-stopped" if tool == "bash" else "not-applicable"), "journal-completion")
        tools.append(tool)
    require(sorted(tools) == sorted(v["tool"] for v in expected), "journal-tools")

def check_decline(protocol, cwd, stored, audit):
    import os
    request = protocol.declined_result
    require(request is not None, "declined-write-result")
    operation = declined_write(protocol.nonce)
    target = operation["params"]["path"]
    require(not os.path.lexists(cwd / target), "declined-write-target")
    digest = sha(compact({"profile": PROFILE, **operation}).encode())
    require(all(row["record"].get("requestId") != request["requestId"] and row["record"].get("digest") != digest
                for row in stored), "declined-write-journal")
    correlation = sha((protocol.parent_call_id + ":" + request["requestId"]).encode())
    identity = f" | HOST: pi | RULE: PI-PERMISSION | CORRELATION: {correlation} | "
    rows = [row for row in audit.decode().splitlines(keepends=True) if identity in row]
    expected = identity + "TOOL_CLASS: WRITE | ACTION_CLASSES: source-write | DECISION: cancelled\n"
    require(len(rows) == 1 and re.fullmatch(r"\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z\]" + re.escape(expected), rows[0]),
            "declined-write-audit")
    return {"target": target, "target_present": False, "journal_claim_present": False, "operation_sha256": digest,
            "result": request, "permission_audit": rows[0].removesuffix("\n")}

def effect_observation(nonce, work, read):
    import os
    journal_root = work/".git/codearbiter/pi-delegation/v1"
    paths = sorted(journal_root.glob("*.json"))
    require(len(paths) <= 16, "journal-file-cap")
    journal = {path.name: read(path, 64*1024) for path in paths}
    effects = {"file": read(work/operations(nonce)[0]["params"]["path"], 4096),
               "command": read(work/("command-"+nonce+".txt"), 4096)}
    canary = work/declined_write(nonce)["params"]["path"]
    snapshot = {"journal": {name: sha(raw) for name, raw in journal.items()},
                "effects": {name: sha(raw) for name, raw in effects.items()},
                "declined_target_present": os.path.lexists(canary)}
    return [decode(raw) for raw in journal.values()], effects, snapshot

def bounded_process(argv, cwd, env, deadline, *, terminal=False, gate=None, protocol=None, budget=None):
    """Only the fixed setup commands/public parent use this POSIX process owner."""
    import errno
    import os
    import selectors
    import signal
    import subprocess
    import time
    require(os.name == "posix", "POSIX-PTY-required")
    master = slave = None
    if terminal:
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 240, 0, 0))
    process = None
    owned_group = None
    completed_observation = None
    output = bytearray()
    selector = selectors.DefaultSelector()
    timed_out = False
    forced_cleanup = False
    exit_input = False
    failed_observation = None
    if budget is None:
        budget = [CAP]
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave if terminal else subprocess.DEVNULL,
                                   stdout=slave if terminal else subprocess.PIPE,
                                   stderr=slave if terminal else subprocess.STDOUT, start_new_session=True,
                                   close_fds=True, shell=False)
        # Successful Popen(start_new_session=True) minted this group before
        # returning. Retain it before live-leader diagnostics: an exited/reaped
        # leader can disappear while its same-group descendants keep the pipe.
        require(type(process.pid) is int and process.pid > 1
                and process.pid != os.getpgrp(), "owned-process-group")
        owned_group = process.pid
        for lookup in (os.getpgid, os.getsid):
            try:
                actual = lookup(process.pid)
            except ProcessLookupError:
                continue  # not evidence that the minted group is absent
            if actual != owned_group:
                owned_group = None  # observed foreign ownership forbids killpg
                require(False, "owned-process-group")
        if slave is not None:
            os.close(slave); slave = None
        fd = master if terminal else process.stdout.fileno()
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_READ)
        while selector.get_map():
            require(protocol is None or not protocol.failed, "provider-refused")
            if time.monotonic() >= deadline:
                timed_out = True
                raise TimeoutError("owned-process-deadline")
            for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                try:
                    block = os.read(key.fd, min(65536, budget[0] + 1))
                except OSError as error:
                    if terminal and error.errno == errno.EIO:
                        block = b""
                    else:
                        raise
                if not block:
                    selector.unregister(key.fd)
                    continue
                require(len(block) <= budget[0], "process-output-cap")
                budget[0] -= len(block)
                output.extend(block)
                if terminal:
                    gate.feed(block)
                    key_bytes = gate.consent(str(cwd))
                    if key_bytes is not None:
                        # The fixture must still be at the pre-effect state when
                        # each genuine public parent confirmation is answered.
                        index = gate.index if gate.pending_decline is not None else gate.index - 1
                        target = Path(cwd) / gate.ops[0]["params"]["path"]
                        expected = None if index == 0 else ("before-" if index == 1 else "after-") + gate.nonce
                        require((not target.exists()) if expected is None else target.read_text(encoding="utf-8") == expected, "effect-before-consent")
                        command = Path(cwd) / ("command-" + gate.nonce + ".txt")
                        if index < len(gate.ops) - 1:
                            require(not command.exists(), "command-before-consent")
                        else:
                            canary = Path(cwd) / declined_write(gate.nonce)["params"]["path"]
                            require(not os.path.lexists(canary), "declined-write-target-before-consent")
                            expected_command = ("command-" + gate.nonce + "\n").encode()
                            require(not command.is_symlink() and command.stat().st_size == len(expected_command)
                                    and command.read_bytes() == expected_command, "command-before-decline")
                        os.write(master, key_bytes)
                    if protocol.complete and gate.index == len(gate.ops) and not exit_input:
                        marker = "PI-D07 fixture completed " + gate.nonce
                        if marker in readable(bytes(output[gate.consumed:])):
                            os.write(master, b"\x04")  # public empty-editor exit
                            exit_input = True
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        completed_observation = {"argv": argv, "returncode": process.returncode, "timed_out": False,
                "pid": process.pid, "forced_cleanup": False, "exit_key_sent": exit_input, "output": bytes(output)}
        return completed_observation
    except BaseException as error:
        timed_out = timed_out or isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
        failed_observation = {"argv": argv, "pid":None if process is None else process.pid,"returncode": None if process is None else process.returncode,
                              "timed_out": timed_out, "forced_cleanup": False, "exit_key_sent": exit_input,
                              "output": bytes(output)}
        error.owned_process_observation = failed_observation
        raise
    finally:
        group_cleanup = "not-started"
        if process is not None:
            # The leader's exit/reap does not mean its same-group descendants
            # released their inherited pipe/PTY. Always clean the saved group.
            if owned_group is not None and owned_group > 1 and owned_group != os.getpgrp():
                try:
                    os.killpg(owned_group, signal.SIGKILL)
                    forced_cleanup = True
                    group_cleanup = "signalled"
                except ProcessLookupError:
                    group_cleanup = "already-gone"
                except OSError:
                    forced_cleanup = True
                    group_cleanup = "unverified"
            else:
                # Ownership validation failed: only the original Popen child
                # may be killed, never an unverified process group.
                forced_cleanup = True
                group_cleanup = "unverified"
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                forced_cleanup = True
                group_cleanup = "unverified"
        for observation in (completed_observation, failed_observation):
            if observation is not None:
                observation.update(forced_cleanup=forced_cleanup, group_cleanup=group_cleanup,
                                   returncode=None if process is None else process.returncode)
        selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        for fd in (master, slave):
            if fd is not None:
                os.close(fd)
        if group_cleanup == "unverified" and failed_observation is None:
            error = ValueError("owned-process-cleanup-unverified")
            error.owned_process_observation = completed_observation
            raise error


def run(config, *, authenticated_payloads):
    """Explicit authenticated-coordinator seam; never installs Pi or imports receipts as authority.

    The supplied payload API facts must come from the original coordinator's
    authenticated current-job/source/upload checks. This prototype emits a
    standalone fixture result, not an admitted major-qualification profile.
    """
    import importlib.util
    import os
    import secrets
    import subprocess
    import sys
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    require(os.name == "posix", "POSIX-PTY-required")
    required = {"format", "repo", "workspace", "output", "stage", "packages", "installed", "expected", "acquisition",
                "python", "node", "git", "npm_launcher", "npm_cli", "npm_node"}
    require(type(config) is dict and set(config) == required and config["format"] == "codearbiter.pi-parent-tui-config/1", "closed-config")
    repo = Path(config["repo"])
    source = config["expected"].get("source_commit", "")
    require(re.fullmatch(r"[0-9a-f]{40}", source), "source-identity")
    # Reuse the exact current production owner, after literal source equality,
    # before any third-party or subject import/effect.
    owner_path = repo / ".github/scripts/observe_pi_installed_rpc.py"
    literal = subprocess.run([config["git"], "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), "show",
                              source + ":.github/scripts/observe_pi_installed_rpc.py"], capture_output=True,
                             check=True, timeout=15, env={"GIT_CONFIG_NOSYSTEM":"1", "GIT_CONFIG_GLOBAL":os.devnull}).stdout
    require(owner_path.is_file() and not owner_path.is_symlink() and owner_path.read_bytes() == literal, "immutable-production-owner")
    spec = importlib.util.spec_from_file_location("pi_tui_existing_owner", owner_path)
    owner = importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
    require(Path(__file__).resolve() == repo / ".github/scripts/pi_parent_tui_observation.py", "physical-harness-source")
    own_literal = subprocess.run([config["git"], "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), "show",
                                 source + ":.github/scripts/pi_parent_tui_observation.py"], capture_output=True, check=True, timeout=15).stdout
    require(owner.raw(Path(__file__)) == own_literal, "immutable-harness-source")
    workspace = Path(config["workspace"]).absolute(); output = Path(config["output"]).absolute()
    private_layout(workspace,output,[repo,Path(config["stage"]),Path(config["packages"]),Path(config["installed"]),Path(config["acquisition"]["prefix"])])
    for path in (workspace, output):
        owner.ordinary(path.parent)
        require(not path.exists() and not path.is_symlink(), "new-owned-path-required")
        path.mkdir(mode=0o700)
    started = time.monotonic()
    nonce = secrets.token_hex(8)
    protocol = ProviderProtocol(nonce); gate = PromptGate(nonce)
    outcome = {"format":"codearbiter.pi-parent-tui-fixture/1", "source_commit":source,
               "status":"not-yet-verified", "actual_case":"PENDING_OR_FAILED", "consent":"scripted-public-TUI-keys-not-human-consent"}
    server = None; thread = None
    phase = "admission"
    budget = [CAP]
    try:
        home = workspace / "home"
        env = owner.environment(home, config, config["acquisition"]["prefix"])
        env.update(PI_CODING_AGENT_DIR=str(home/"agent"), JITI_CACHE_DIR=str(home/"jiti"), TERM="xterm-256color", LANG="C.UTF-8")
        with owner.process_environment(env), owner.owners(repo, config["expected"], config["git"], home) as cold:
            before_source = owner.source_snapshot(cold, config)
            promotion = owner.sha(owner.raw(Path(config["stage"])/"artifact-promotion.json"))
            cold._verify_production(repo, Path(config["packages"]), Path(config["stage"]), config["expected"], promotion)
            physical = {role:cold.physical_members(Path(config[name]))["members"] for role,name in (("promoted-stage","stage"),("release-packages","packages"))}
            consumed = authenticated_roles(config["expected"], authenticated_payloads, physical)
            cohort = owner.load(Path(config["packages"])/"artifact-package-cohort.json")
            package_entry = cohort["packages"]["pi"]
            installed = owner.ordinary(config["installed"])
            before_installed = cold.physical_members(installed)["members"]
            require(before_installed == {p:v["sha256"] for p,v in package_entry["members"].items()}, "authentic-installed-members")
            package = installed / "package"
            acquisition = config["acquisition"]
            require(acquisition.get("format") == "codearbiter.pi-reviewed-acquisition/1" and acquisition.get("version") == "1.5.0"
                    and all(acquisition.get(k) == v for k,v in config["expected"].items())
                    and acquisition.get("fresh_prefix") == {"enumeration_succeeded":True,"present":False}
                    and owner.successful(acquisition.get("command",{})), "reviewed-acquisition")
            before_runtime = owner.runtime_snapshot(config)
            before_graph = owner.graph_snapshot(Path(acquisition["prefix"]))
            require(before_runtime == acquisition["runtime_before"] == acquisition["runtime_after"]
                    and before_graph == acquisition["graph_after"], "reviewed-runtime-graph")
            require(all(acquisition["source_locks"].get(name) == before_source["inputs"].get(".github/fixtures/pi-hosts/1.5.0/"+name)
                        for name in owner.LOCK_NAMES), "immutable-Pi-locks")
            sdk = Path(acquisition["prefix"])/"node_modules/@earendil-works/pi-coding-agent"
            cli = sdk / runtime_entry(owner.load(sdk/"package.json"))
            owner.ordinary(cli)
            require(cli.is_relative_to(Path(acquisition["prefix"])), "Pi-cli-boundary")
            owner.save(output/"input-before.json",{"source":before_source,"runtime":before_runtime,"graph":before_graph,
                                                   "installed":before_installed,"payloads":physical,"consumed_payloads":consumed})
            work = workspace / "project"; work.mkdir()
            deadline = started + BODY_SECONDS
            phase = "git-init"
            setup = bounded_process([config["git"], "init", "-q", "-b", "feature/pi-author-fixture"], work, env, min(deadline,time.monotonic()+15),budget=budget)
            (output/"git-init.output").write_bytes(setup.pop("output")); owner.save(output/"git-init.json",setup)
            require(setup["returncode"] == 0, "fixture-git-init")
            (work/".codearbiter").mkdir()
            (work/".codearbiter/CONTEXT.md").write_text("---\narbiter: enabled\n---\n<!--INITIALIZED-->\nstage: implementation\n",encoding="utf-8")
            agent = home/"agent"; agent.mkdir()
            (agent/"settings.json").write_text(compact({"npmCommand":["npm","--offline","--no-audit","--no-fund","--ignore-scripts"]})+"\n",encoding="utf-8")
            install_env = {k:v for k,v in env.items() if k != "PI_OFFLINE"}
            phase = "package-install"
            setup = bounded_process([config["node"],str(cli),"install",str(package),"--no-approve"],work,install_env,min(deadline,time.monotonic()+20),budget=budget)
            (output/"package-install.output").write_bytes(setup.pop("output"));owner.save(output/"package-install.json",setup)
            require(setup["returncode"] == 0 and len(owner.load(agent/"settings.json").get("packages",[])) == 1,"actual-local-package-install")
            protocol.inspection_snapshot = lambda: effect_observation(nonce, work, owner.raw)[2]
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args): pass
                def do_GET(self):
                    protocol.record({"refused":True,"method":"GET"})
                    self.send_error(400,"fixture refused")
                def do_POST(self):
                    self.connection.settimeout(2)
                    try:
                        length = transport_length(self.command,self.path,self.headers,nonce)
                        raw = self.rfile.read(length); require(len(raw)==length,"provider-body-short")
                        value, finish = protocol.response(decode(raw))
                        protocol.record({"request_sha256":sha(raw),"bytes":len(raw),"response_finish":finish})
                        chunk = lambda delta,reason: {"id":"fixture-"+nonce,"object":"chat.completion.chunk","created":1,"model":"gpt-fixture",
                                                      "choices":[{"index":0,"delta":delta,"finish_reason":reason}]}
                        data = ("data: "+compact(chunk(value,None))+"\n\ndata: "+compact(chunk({},finish))+"\n\ndata: [DONE]\n\n").encode()
                        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
                    except Exception as error:
                        protocol.record({"refused":True,"error_type_sha256":sha(type(error).__name__.encode())})
                        self.send_error(400,"fixture refused")
            class FixtureServer(HTTPServer):
                request_queue_size = 2
                def get_request(self):
                    connection, address = super().get_request()
                    connection.settimeout(2)  # bounds header reads before do_POST
                    return connection, address
            server = FixtureServer(("127.0.0.1",0),Handler)
            server.timeout = 0.2
            thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            (agent/"models.json").write_text(compact({"providers":{"openai":{"baseUrl":"http://127.0.0.1:"+str(server.server_port)+"/v1",
                "api":"openai-completions","apiKey":"$OPENAI_API_KEY","models":[{"id":"gpt-fixture","name":"fixture","reasoning":False,
                "input":["text"],"contextWindow":128000,"maxTokens":4096,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}}]}}})+"\n",encoding="utf-8")
            env["OPENAI_API_KEY"] = "dummy-" + nonce
            parent_argv = [config["node"],str(cli),"--offline","--no-session","--approve","--no-context-files","--provider","openai","--model","gpt-fixture",
                           "Run only the deterministic owned PI-D07 fixture " + nonce + "."]
            phase = "parent"
            actual = bounded_process(parent_argv,work,env,deadline,terminal=True,gate=gate,protocol=protocol,budget=budget)
            terminal_raw = actual.pop("output")
            (output/"parent.ansi").write_bytes(terminal_raw)
            (output/"parent.readable.txt").write_text(readable(terminal_raw),encoding="utf-8")
            owner.save(output/"parent-process.json",actual)
            stored, effects, final_effects = effect_observation(nonce, work, owner.raw)
            owner.save(output/"journal.json",stored)
            owner.save(output/"effects.json",{key:{"bytes":len(value),"sha256":sha(value),"utf8":value.decode()} for key,value in effects.items()})
            after_source = owner.source_snapshot(cold,config);after_runtime = owner.runtime_snapshot(config);after_graph = owner.graph_snapshot(Path(acquisition["prefix"]))
            after_installed = cold.physical_members(installed)["members"]
            after_payload = {role:cold.physical_members(Path(config[name]))["members"] for role,name in (("promoted-stage","stage"),("release-packages","packages"))}
            owner.save(output/"input-after.json",{"source":after_source,"runtime":after_runtime,"graph":after_graph,"installed":after_installed,"payloads":after_payload})
            outcome.update(actual_case="executed",process=actual,prompts=gate.events,provider=protocol.records,
                           declined_result=protocol.declined_result,
                           inspection_turn=None if protocol.inspection is None else protocol.inspection.turn,
                           consumed_payloads=consumed,source_before=before_source,source_after=after_source,runtime_before=before_runtime,runtime_after=after_runtime,
                           admitted_graph_before=before_graph,admitted_graph_after=after_graph,installed_before=before_installed,installed_after=after_installed,
                           payload_before=physical,payload_after=after_payload,
                           loaded_closure_limit="Complete admitted package/runtime graph captured; no unsupported claim of complete actual dynamic child import telemetry.")
            # Persist original observations before applying acceptance assertions.
            owner.save(output/"original-outcome.json",outcome)
            require(actual["returncode"] == 0 and actual["exit_key_sent"] and not actual["forced_cleanup"]
                    and len(gate.events) == len(gate.ops) and gate.events[-1].get("decision") == "declined"
                    and protocol.complete and len(protocol.records) == PROVIDER_RECORDS and not protocol.failed,
                    "parent-or-protocol-incomplete")
            require(before_source==after_source and before_runtime==after_runtime and before_graph==after_graph
                    and before_installed==after_installed and physical==after_payload,"input-drift")
            check_effects(nonce,stored,effects)
            audit = owner.raw(work/".codearbiter/gate-events.log", 64*1024)
            owner.save(output/"declined-write.json", check_decline(protocol, work, stored, audit))
            require(protocol.inspection.receipt["after"] == final_effects, "inspection-effect-drift")
            owner.save(output/"reviewer-chain.json", protocol.inspection.receipt)
            outcome["status"]="passed"
            owner.save(output/"verification.json",{"status":"passed","scope":"first POSIX scripted public-parent-TUI fixture only; not human/full PI-D07/major qualification"})
        return outcome
    except BaseException as error:
        process_observation = getattr(error,"owned_process_observation",None)
        if process_observation is not None:
            raw = process_observation.pop("output")
            (output/(phase+".partial-output")).write_bytes(raw)
            owner.save(output/(phase+".failure.json"),process_observation)
        if not (output/"original-outcome.json").exists():
            outcome.update(status="failed",phase=phase,prompts=gate.events,provider=protocol.records,
                           inspection_turn=None if protocol.inspection is None else protocol.inspection.turn,
                           error_type_sha256=sha(type(error).__name__.encode()))
            owner.save(output/"original-outcome.json",outcome)
        if not (output/"verification.json").exists():
            owner.save(output/"verification.json",{"status":"failed","phase":phase,"error_type_sha256":sha(type(error).__name__.encode())})
        if (output/"input-before.json").exists() and not (output/"input-after.json").exists():
            try:
                owner.save(output/"input-after.json",{"source":owner.source_snapshot(cold,config),"runtime":owner.runtime_snapshot(config),
                    "graph":owner.graph_snapshot(Path(config["acquisition"]["prefix"])),"installed":cold.physical_members(Path(config["installed"]))["members"],
                    "payloads":{role:cold.physical_members(Path(config[name]))["members"] for role,name in (("promoted-stage","stage"),("release-packages","packages"))}})
            except Exception as capture_error:
                owner.save(output/"input-after-unavailable.json",{"status":"unavailable","error_type_sha256":sha(type(capture_error).__name__.encode())})
        raise
    finally:
        if server is not None:
            server.shutdown();server.server_close()
        if thread is not None:
            thread.join(timeout=3)
        # Failed fixture contents remain private for diagnosis. The owning outer
        # coordinator removes its exact workspace only after process cleanup.
        owner.save(output/"cleanup.json",{"provider_thread_stopped":thread is None or not thread.is_alive(),"private_workspace_retained":True})

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--authenticated-payloads",type=Path,required=True,
                        help="original coordinator API/upload-authenticated payload projections, never a Boolean approval")
    args = parser.parse_args()
    # This standalone command produces a fixture receipt. Final report admission
    # must independently authenticate the originating current job/run/artifacts.
    run(read_document(args.config),authenticated_payloads=read_document(args.authenticated_payloads))

if __name__ == "__main__":
    main()
