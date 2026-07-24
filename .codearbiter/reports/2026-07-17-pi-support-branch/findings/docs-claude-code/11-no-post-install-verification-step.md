severity: low

page: getting-started/install.md

user_goal: Verify the install succeeded right after running the two /plugin commands.

gap: Step 1 says "Hooks, commands, and agents load automatically" and only mentions /ca:doctor for a repo already opted in — there's no "did the plugin install correctly at all" check before step 2 (scaffold the repo). A user whose marketplace-add or plugin-install silently failed has no signal until they're deep into /ca:init.

remediation: Add a one-line install-verification step right after the /plugin install ca@codearbiter command (e.g., /plugin list or equivalent) before moving to repo activation.
