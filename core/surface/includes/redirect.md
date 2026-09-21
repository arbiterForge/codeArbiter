# Redirect

Clarification support for §6 **tiers 2 and 3**, loaded only when the intended outcome, a material
fact, or required authority is unresolved. Tier 1 does not use this file: select the existing
owner and preserve its gates without asking the user to retype or approve an internal route.

## Tier 2 — probable intent, or a required destructive confirmation

Inspect available context before asking. A second plausible implementation method is not a missing
user decision. Ask about the missing outcome or fact, with a recommendation and its strongest
counter-consideration; do not ask the user to select a command that expresses an understood request.

For irreversible or gate-bypassing operations, obtain the existing confirmation even when intent
is clear: `{{CMD:override}}`, merge to the default branch, branch or worktree deletion, and release
and tag publication. Name the exact operation and target, state the consequence, then ask for its
confirmation. A generic approval of a route is not authority for an unspecified destructive action.
A deterministic mode-token flip is not in this set; its existing mode contract still applies.

## Tier 3 — genuinely unclear outcome

Ask one focused question after checking the available evidence:

> The missing decision is <outcome or constraint>. I recommend <option> because <reason>;
> <strongest counter-consideration> favors <alternative>. Which outcome is intended?

When even the intended task is unknown, ask what result the user wants. Do not repeat a command
catalog when the user restates the goal in ordinary language. Resolve the actual uncertainty and
then select the owner; lack of slash syntax is not itself uncertainty.

## Questions and restricted requests

Use the requested outcome, not punctuation alone. "Explain this commit" and "draft the message,
but do not commit" authorize no staging, commit, task-board write, or other persistent mutation.
"Can you commit these changes?" can request an action; it still needs its owning gate. Answer an
informational question directly using read-only evidence as needed. If a relevant procedure has a
writing terminal step, do not enter that step for a report-only request.

## Never

A genuinely missing owner is a **routing gap**, not an override case. Surface the precise missing
capability; never steer the user toward `{{CMD:override}}` to get past a coverage hole. Do not invent
an ungoverned procedure, resolve a `[CONFIRM-NN]`, or broaden scope merely to avoid asking.

## Exception — local runtime work

The existing `mode --ops` contract in `{{PLUGIN_ROOT}}/includes/ops-mode.md` owns local runtime
work that leaves tracked files and Git history unchanged. In `arbiter` mode, a runtime operation without an owner remains a routing gap;
this clarification card does not select or activate another mode. Tracked-file, index, Git-history,
and published-state mutations still require their ordinary governing workflow, `ops` or not.
