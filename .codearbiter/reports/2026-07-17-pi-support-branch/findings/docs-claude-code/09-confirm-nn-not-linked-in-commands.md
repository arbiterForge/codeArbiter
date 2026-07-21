severity: medium

page: reference/commands/feature.md and other generated command pages (review.md, task.md)

user_goal: Understand SMARTS and CONFIRM-NN before hitting them in daily use (e.g. during /ca:feature's brainstorming phase, which can raise [CONFIRM-NN]).

gap: feature.md's generated reference explicitly states "Genuinely-unresolved unknowns become [CONFIRM-NN]" but a first-time reader following overview -> install -> quickstart -> feature.md never encounters a definition of CONFIRM-NN until they either already hit it live or independently visit glossary.md (which isn't linked from feature.md's body — only "Related" links to fix/refactor/brainstorming/writing-plans/tdd, not glossary).

remediation: Link CONFIRM-NN inline to /glossary/#confirm-nn the first time it appears in each generated command page that uses the term (feature.md, review.md, task.md's "harvest" reference, etc.), not just glossary.md itself.
