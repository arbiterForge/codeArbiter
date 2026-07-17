severity: medium

page: getting-started/install.md

user_goal: Install codeArbiter in Claude Code and know it's actually working before moving on.

gap: The Claude Code install section has no analog to Codex's explicit trust/consent step ("Open /hooks, trust the handlers, and start a fresh thread"). It's unclear from the docs whether Claude Code requires any first-run permission approval for plugin hooks to fire, or whether install is truly "hooks load automatically" with zero user action. A first-time user who hits an unexpected permission prompt has no guidance for what it is or whether to approve it.

remediation: State explicitly whether Claude Code prompts for hook/tool permission on first use, and what to click/approve; if genuinely automatic, say so as a positive confirmation rather than silence.
