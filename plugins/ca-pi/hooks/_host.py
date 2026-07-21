#!/usr/bin/env python3
"""Thin Pi payload adapter for the shared codeArbiter Python core."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402


class PiHost(hostapi.Host):
    name = "pi"
    command_noun = "command"
    has_statusline = False
    has_read_tool = True
    has_prunable_transcript = True

    TOOL_MAP = {
        "bash": "EXEC",
        "codearbiter_dispatch": "EXEC",
        "codearbiter_farm_preview": "EXEC",
        "write": "WRITE",
        "edit": "EDIT",
        "read": "READ",
    }

    def __init__(self, project_dir=None):
        self._project_dir = project_dir

    def cmd_ref(self, name):
        return "/ca-" + name

    def project_root(self, payload=None):
        if self._project_dir and os.path.isdir(self._project_dir):
            return self._project_dir
        if isinstance(payload, dict):
            cwd = payload.get("cwd")
            if isinstance(cwd, str) and os.path.isdir(cwd):
                return hostapi.git_toplevel(cwd) or cwd
        return hostapi.git_toplevel() or os.getcwd()

    def plugin_root(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def manifest_relpath(self):
        return "package.json"

    def normalize_tool_input(self, tool_name, tool_input):
        value = tool_input if isinstance(tool_input, dict) else {}
        if tool_name == "read":
            return {"file_path": value.get("path", value.get("file_path", ""))}
        if tool_name == "write":
            return {"file_path": value.get("path", ""), "content": value.get("content", "")}
        if tool_name == "edit":
            edits = value.get("edits", [])
            if not edits and isinstance(value.get("oldText"), str) and isinstance(value.get("newText"), str):
                edits = [{"oldText": value["oldText"], "newText": value["newText"]}]
            return {
                "file_path": value.get("path", ""),
                "edits": [
                    {"old_string": item.get("oldText", ""), "new_string": item.get("newText", "")}
                    for item in edits if isinstance(item, dict)
                ],
            }
        return value

    def iter_file_ops(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        tool = payload.get("tool_name", "")
        native = payload.get("tool_input", {})
        value = self.normalize_tool_input(tool, native)
        if tool == "edit":
            fpath = value.get("file_path", "")
            edits = value.get("edits", [])
            batched = len(edits) > 1
            return [
                {
                    "file_path": fpath,
                    "kind": "edit",
                    "content": None,
                    "added_text": item.get("new_string", ""),
                    "added_lines": item.get("new_string", "").splitlines(),
                    "old_string": item.get("old_string", ""),
                    "replace_all": False,
                    "batched": batched,
                    "notebook": False,
                }
                for item in edits
            ]
        if tool == "write":
            content = value.get("content", "")
            return [{
                "file_path": value.get("file_path", ""),
                "kind": "write",
                "content": content,
                "added_text": content,
                "added_lines": content.splitlines(),
                "old_string": "",
                "replace_all": False,
                "batched": False,
                "notebook": False,
            }]
        return []


HOST = PiHost()
