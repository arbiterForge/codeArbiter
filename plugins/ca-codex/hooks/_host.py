#!/usr/bin/env python3
# codeArbiter — the Codex CLI host definition for THIS plugin (ADR-0011, M2).
#
# Per-plugin, deliberately NOT part of the shared core (core/pysrc/): each
# plugin ships its own _host.py naming the host it targets, and
# hostapi.load_host() loads it by file path from the hooks directory. This is
# the ONE file that differs from the ca (Claude Code) sibling — every other
# .py here is a byte-identical vendored copy of core/pysrc/ (sync-core.py).
#
# Codex CLI contracts (source-verified against openai/codex rust-v0.143.0,
# spike: .codearbiter/spikes/codex-extension-surface.md; minimum supported
# Codex: rust-v0.134.0):
#   * exec tool is canonically named "Bash", tool_input {"command": ...}
#     (core/src/tools/hook_names.rs) — same canonical shape as Claude Code.
#   * ALL file writes/edits arrive as "apply_patch", tool_input
#     {"command": "<patch envelope>"} (core/tests/suite/hooks.rs:
#     pre_tool_use_blocks_apply_patch_before_execution asserts
#     tool_input["command"] == patch). "Write" and "Edit" are matcher-only
#     aliases — the payload stays the apply_patch envelope.
#   * There is NO read tool (reads happen via shell) and NO statusline.
#   * Hooks receive PLUGIN_ROOT and CLAUDE_PLUGIN_ROOT (compat alias) but NO
#     project-dir env var — they run in the session cwd and get `cwd` in the
#     hook payload (hooks/src/engine/discovery.rs). CLAUDE_PROJECT_DIR must
#     NOT be consulted here: if it leaks into a Codex session's environment
#     (e.g. a nested/adjacent Claude session), it names the WRONG project.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402

# The apply_patch envelope grammar, verbatim from openai/codex
# codex-rs/prompts/templates/apply_patch_tool_instructions.md (and enforced by
# codex-rs/apply-patch/src/parser.rs):
#
#   Patch      := Begin { FileOp } End
#   Begin      := "*** Begin Patch" NEWLINE
#   End        := "*** End Patch" NEWLINE
#   FileOp     := AddFile | DeleteFile | UpdateFile
#   AddFile    := "*** Add File: " path NEWLINE { "+" line NEWLINE }
#   DeleteFile := "*** Delete File: " path NEWLINE
#   UpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] { Hunk }
#   MoveTo     := "*** Move to: " newPath NEWLINE
#   Hunk       := "@@" [ header ] NEWLINE { HunkLine } [ "*** End of File" NEWLINE ]
#   HunkLine   := (" " | "-" | "+") text NEWLINE
_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
_ADD = "*** Add File: "
_DELETE = "*** Delete File: "
_UPDATE = "*** Update File: "
_MOVE = "*** Move to: "
_EOF = "*** End of File"


def _op(file_path, kind, content, added_lines):
    added_text = "\n".join(added_lines) + ("\n" if added_lines else "")
    return {"file_path": file_path, "kind": kind, "content": content,
            "added_text": added_text, "added_lines": list(added_lines)}


def parse_apply_patch(text):
    """Canonical per-file ops (hostapi.Host.iter_file_ops shape) for one
    apply_patch envelope, or [] when `text` is not an envelope at all.

    Line handling mirrors Codex's LENIENT parser (apply-patch/src/parser.rs,
    PARSE_IN_STRICT_MODE = false): Rust runs `patch.trim().lines()` — which
    strips one trailing "\\r" per line — and trims whitespace around marker
    lines, so a CRLF or whitespace-indented envelope that Codex accepts and
    APPLIES must parse identically here. Marker detection therefore works on
    the whitespace-stripped line; "+" content lines keep their exact text
    (only the CRLF "\\r" is removed), because added_lines feed content guards.

    A string with no "*** Begin Patch" marker returns no ops (the guard
    treats the call as OTHER; Codex's parser rejects marker-less input before
    any file is touched). When a marker IS present but this parse yields zero
    ops, iter_file_ops fails CLOSED with a single "opaque" op that pre-write
    blocks outright — an envelope the adapter cannot decompose must never
    pass unguarded. An unrecognized "*** " DIRECTIVE inside a recognized
    envelope (e.g. "*** Copy File:", a mis-positioned "*** Move to:") aborts
    the parse and returns a single "opaque" op: Codex's lenient parser may
    still apply such an envelope, so emitting the PARTIAL op list collected so
    far would silently drop that directive's file and un-guard it (appsec-001).
    Non-directive unrecognized lines (context " " and removal "-" hunk lines)
    are still skipped — they carry no file operation to guard.

    Op mapping:
      * Add File    -> one "write" op; the + lines ARE the file's full content.
      * Update File -> one "edit" op whose added_lines are the hunks' + lines
        (context " " and removal "-" lines are not added content). A Move to
        rename touches TWO paths, so it fans out: the source becomes a
        "delete" op and the destination an "edit" op carrying the added
        lines — both sides of the rename get guarded.
      * Delete File -> one "delete" op.
    """
    if not isinstance(text, str) or _BEGIN not in text:
        return []
    ops = []
    cur = None       # (path, kind, added_lines, move_to)
    in_patch = False

    def _flush():
        nonlocal cur
        if cur is None:
            return
        path, kind, added, move_to = cur
        cur = None
        if kind == "write":
            ops.append(_op(path, "write", "\n".join(added) + ("\n" if added else ""),
                           added))
        elif kind == "delete":
            ops.append(_op(path, "delete", None, []))
        elif move_to:
            ops.append(_op(path, "delete", None, []))
            ops.append(_op(move_to, "edit", None, added))
        else:
            ops.append(_op(path, "edit", None, added))

    for raw in text.split("\n"):
        # Mirror Rust str::lines(): strip ONE trailing "\r" (CRLF input).
        line = raw[:-1] if raw.endswith("\r") else raw
        # Markers are matched whitespace-stripped, mirroring the lenient
        # parser's trim(); content extraction below uses `line` verbatim.
        marker = line.strip()
        if not in_patch:
            if marker == _BEGIN:
                in_patch = True
            continue
        if marker == _END:
            break
        if marker.startswith(_ADD):
            _flush()
            cur = (marker[len(_ADD):].strip(), "write", [], None)
        elif marker.startswith(_DELETE):
            _flush()
            cur = (marker[len(_DELETE):].strip(), "delete", [], None)
        elif marker.startswith(_UPDATE):
            _flush()
            cur = (marker[len(_UPDATE):].strip(), "edit", [], None)
        elif marker.startswith(_MOVE) and cur is not None and cur[1] == "edit":
            cur = (cur[0], cur[1], cur[2], marker[len(_MOVE):].strip())
        elif marker == _EOF or marker.startswith("@@"):
            continue  # hunk boundary / end-of-file marker — never content
        elif cur is not None and line.startswith("+"):
            cur[2].append(line[1:])
        elif marker.startswith("*** "):
            # An unrecognized "*** " directive inside a recognized envelope —
            # e.g. "*** Copy File:", a mis-positioned "*** Move to:" (the _MOVE
            # branch above requires an open edit op), or a malformed
            # "*** Add File:x" (no trailing space). The recognized markers were
            # all matched above, and a "+" content line was consumed above, so
            # reaching here means a structural directive this mirror does not
            # model. Codex's LENIENT parser may still APPLY such an envelope, so
            # returning the PARTIAL op list collected so far would silently DROP
            # this directive's file operation and un-guard it (appsec-001). The
            # whole-envelope backstop in iter_file_ops only fires on ZERO ops,
            # so it cannot catch a partial parse. Fail CLOSED: discard the
            # partial ops and return the single "opaque" op, which pre-write
            # blocks (H-21). (A hunk content line whose text begins "*** " is
            # matched here too, exactly as the recognized markers above already
            # match a stripped content line — this mirrors Codex's own
            # trim-then-match leniency, so it is parity-preserving, not a new
            # divergence; the safe resolution of that ambiguity is to block.)
            return [_op("", "opaque", None, [])]
        # " "/"-" hunk lines and anything else unrecognized: skipped (docstring)
    _flush()
    return ops


class CodexHost(hostapi.Host):
    """OpenAI Codex CLI (>= rust-v0.134.0) — the second host (ADR-0011)."""

    name = "codex"
    command_noun = "command"
    has_statusline = False   # no statusline surface exists on Codex
    has_read_tool = False    # no read tool; file reads happen via shell
    has_prunable_transcript = False  # Codex transcripts are not the pruner's
                                     # JSONL format; staleness-warn still runs

    def cmd_ref(self, name):
        # Codex has no plugin command namespace: every governance command
        # ships as a `ca-`-prefixed skill (ADR-0011 §5, M3), mentioned as
        # $ca-<name>. Must agree with CMD_FORM["codex"] in build-surface.py.
        return "$ca-" + name

    # Native tool name -> canonical category. "Write"/"Edit" are Codex
    # matcher-only ALIASES for apply_patch (the payload is still the patch
    # envelope), so they normalize to WRITE, not EDIT — the per-file kind
    # (write/edit/delete) comes from the parsed patch ops, not the tool name.
    # "Read" is alias safety only (no read tool exists). mcp__* and anything
    # else unlisted falls through to OTHER via the base normalize_tool.
    TOOL_MAP = {
        "Bash": "EXEC",
        "apply_patch": "WRITE",
        "Write": "WRITE",
        "Edit": "WRITE",
        "Read": "READ",
    }

    _PATCH_TOOLS = frozenset({"apply_patch", "Write", "Edit"})

    def project_root(self, payload=None):
        """The project root. Codex sets NO project-dir env var (spike §6) —
        and CLAUDE_PROJECT_DIR is deliberately NOT consulted (a leaked value
        from an adjacent Claude session would name the wrong project). Order:

          1. the hook payload's `cwd`, when given and an existing directory —
             the harness's own signal (Codex runs hooks in the session cwd
             and repeats that cwd in every hook payload) — climbed to the git
             TOPLEVEL from that cwd (hostapi.git_toplevel), falling back to
             the cwd itself when that climb fails. A session started in a
             repo SUBDIRECTORY must still resolve the repo ROOT, not that
             subdirectory verbatim (reliability-005, #260) — `.codearbiter/`
             state lives at the root, not wherever the session happened to
             start.
          2. `git rev-parse --show-toplevel` from the process cwd.
          3. the process cwd.
        """
        if payload and isinstance(payload, dict):
            cwd = payload.get("cwd")
            if cwd and os.path.isdir(cwd):
                return hostapi.git_toplevel(cwd) or cwd
        top = hostapi.git_toplevel()
        if top:
            return top
        return os.getcwd()

    def plugin_root(self):
        """CLAUDE_PLUGIN_ROOT (Codex sets it as an explicit compat alias,
        discovery.rs L227-235) -> PLUGIN_ROOT (the native name) ->
        file-relative fallback (<root>/hooks/_host.py -> <root>)."""
        for var in ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
            env = os.environ.get(var)
            if env:
                return env
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def manifest_relpath(self):
        """ca-codex ships its manifest at `.codex-plugin/plugin.json` ONLY
        (module header above) — never `.claude-plugin/`, so doctor.py and
        _updatelib.py must resolve THIS path under Codex (#263)."""
        return os.path.join(".codex-plugin", "plugin.json")

    def normalize_tool_input(self, tool_name, tool_input):
        """Codex's exec payload ({command}) already IS the canonical EXEC
        shape, and the apply_patch envelope cannot be represented as ONE
        canonical file dict (it batches many files) — its per-file translation
        is iter_file_ops' job. So this stays a pass-through dict."""
        return tool_input if isinstance(tool_input, dict) else {}

    def iter_file_ops(self, payload):
        """Canonical per-file ops for a Codex write payload: parse the
        apply_patch envelope out of tool_input["command"] (the source-verified
        payload shape — see module header). Defensive fallback: if a payload
        ever arrives Claude-shaped ({file_path, ...}) instead, defer to the
        base mapping so the file is still guarded rather than silently
        unhandled."""
        payload = payload if isinstance(payload, dict) else {}
        tool = payload.get("tool_name", "") or ""
        ti = payload.get("tool_input", {}) or {}
        if not isinstance(ti, dict):
            return []
        if tool in self._PATCH_TOOLS:
            cmd = ti.get("command")
            if isinstance(cmd, str) and _BEGIN in cmd:
                ops = parse_apply_patch(cmd)
                if ops:
                    return ops
                # An envelope marker is present but nothing decomposed: this
                # is a shape Codex may still APPLY (its parser is lenient) —
                # fail CLOSED. pre-write blocks the "opaque" kind outright.
                return [{"file_path": "", "kind": "opaque", "content": None,
                         "added_text": "", "added_lines": []}]
            if "file_path" in ti or "notebook_path" in ti:
                return super().iter_file_ops(payload)
            return []  # not an envelope, nothing path-shaped: fail open to OTHER
        # Non-write tools carry no file ops on Codex; guard a path-shaped
        # payload defensively (base mapping), else report none.
        if "file_path" in ti or "notebook_path" in ti:
            return super().iter_file_ops(payload)
        return []


HOST = CodexHost()
