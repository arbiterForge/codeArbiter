severity: low

page: reference/commands (general — review.md, task.md, feature.md, doctor.md)

user_goal: Trust that command docs are current.

gap: No systematic staleness found beyond finding 05 — feature.md, doctor.md, review.md, and task.md's generated bodies matched plugins/ca/commands/*.md byte-for-byte in the sampled pages, which is a positive signal for the generator's fidelity. But it also means any drift (like finding 05) is a generator/fixture bug rather than hand-edit drift, worth root-causing once rather than treating as isolated content gaps.

remediation: No content fix needed per page; flag the generator/fixture pipeline for a consistency check between example outputs and source flow text.
