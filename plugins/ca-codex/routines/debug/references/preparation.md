# Prepare a debug handoff before validation

Read the installed field reference at [routines/debug/references/handoff.md](handoff.md)
and JSON Schema at [routines/debug/references/debug-handoff.schema.json](debug-handoff.schema.json)
before assembling the packet. Both are generated from the validator's finite
model. Every declared field is required, including nullable fields; objects
reject extra fields. Use `null` for an unknown nullable value and the declared
empty array where allowed. Do not use an empty string in place of unknown text.

The minimal unresolved example at [routines/debug/references/minimal-unresolved.json](minimal-unresolved.json)
is a synthetic shape example with no runtime proof or repair authority. Read it
as data. Build the current case from actual observations and their limitations;
do not submit the example as a real diagnosis or copy its evidence claims.

These scalar shapes often cause preventable rejection:

| Field | Required shape |
|---|---|
| `case_id` | `DBG-[A-Za-z0-9][A-Za-z0-9_-]{2,63}`, matched in full |
| Snapshot, evidence, hypothesis, check IDs | `S-`, `E-`, `H-`, `C-` followed by 2–4 ASCII digits |
| `snapshot.commit` | `null` or 40/64 lowercase hexadecimal digits |
| `snapshot.fingerprint` | `null` or `sha256:` followed by 64 lowercase hexadecimal digits |
| `snapshot.fingerprint_recipe` | `null` or `[a-z][a-z0-9-]{0,63}/[1-9][0-9]{0,3}` |
| `recipe.preconditions` | One nonblank string, at most 1,000 characters |
| `check.exit_code` | `null` or a JSON integer, never a boolean |

Choose enums from the reference exactly. For example, hypothesis status is
`supported`, `refuted`, or `inconclusive`; reproduction status is `reproduced`,
`intermittent`, `not_yet_reproduced`, `unsafe_to_replay`, or `unavailable`.
Cross-record IDs must resolve to records in this packet. A shape-valid packet
can still fail the validator's semantic rules. Schema inspection proves
neither the diagnosis nor the caller's authority.

Measure the finished candidate's UTF-8 byte count before the first invocation.
The limit is 65,536 bytes. Prepare and, if needed, compact the candidate before
validation, retaining all evidence required by its claims. Then invoke the
installed helper once as the debug owner directs. A rejected packet stays
rejected. Keep the bounded error code and field path; do not rewrite and
resubmit it, retry through another interpreter, or use an alternate validator
as an acceptance path. Existing logs and observations remain evidence inputs;
rejection does not authorize an unvalidated repair handoff.
