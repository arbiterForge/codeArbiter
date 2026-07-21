severity: medium

page: reference/commands/doctor.md

user_goal: Run /ca:doctor and interpret its output.

gap: Internal inconsistency: the worked example output says "OK all 6 hook scripts present" while the "Flow" section (sourced from plugins/ca/commands/doctor.md) says the static check covers "all five hook scripts." A user comparing their own doctor output against the docs' example can't tell if 5 or 6 is correct.

remediation: Reconcile the count in the generated example against the actual hook-script count and keep both in sync (likely a generator/fixture staleness issue).
