# Claude Code hook payload fixtures

Claude Code 2.1.281 hook payloads recorded 2026-09-24 (identifiers and paths replaced; every key and value shape kept).

The two SubagentStop files are one agent stopping twice: the second fired under the parent's next prompt with `stop_hook_active: true` and a different final message.

`2.1.286/` holds Claude Code 2.1.286 payloads recorded 2026-10-02 for one background `ca:authority-reviewer` launch from a 1M-context Opus parent, same scrubbing. Two host changes since 2.1.281: `resolvedModel` carries the context tag (`claude-opus-5-5[1m]`), and the child reports through a `SubagentHandback` tool call (Pre/PostToolUse with the child's `agent_id`), so its `SubagentStop` has no `last_assistant_message`. SubagentStart fired before the Agent PostToolUse.
