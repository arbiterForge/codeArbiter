# Prepare a debug handoff before validation

Read the installed field reference at `<plugin-root>/routines/debug/references/handoff.md`
and JSON Schema at `<plugin-root>/routines/debug/references/debug-handoff.schema.json`
before assembling the packet. Both are generated from the validator's finite
model. Every declared field is required, including nullable fields; objects
reject extra fields. Use `null` for an unknown nullable value and the declared
empty array where allowed. Do not use an empty string in place of unknown text.

The minimal unresolved example at `<plugin-root>/routines/debug/references/minimal-unresolved.json`
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
rejected: keep the bounded error code and field path, never retry it through
another interpreter, and never use an alternate validator as an acceptance path.
Existing logs and observations remain evidence inputs; rejection does not
authorize an unvalidated repair handoff.

## Corrected resubmission

A corrected packet may be submitted again to the same installed validator. The
correction is a new validation of a changed packet, not a retry of the refused
one, and it changes no authority: valid shape is not causal proof, and passing
validation grants no code-writing, external access, or publication permission.
State what changed and why, keep the case history, and keep observed facts
distinct from proposed repairs. Match the remedy to the refusal:

- **Input or shape defect** (for example `INVALID_JSON`, `UNKNOWN_FIELD`,
  `REQUIRED_FIELD`, `TYPE`, `VALUE`, `INPUT_LIMIT`): correct the named field from
  facts already in hand, then validate the corrected packet.
- **Semantic-evidence refusal** (`REFERENCE`, `SEMANTIC`): the evidence does not
  support the claim. Changing labels, prose, IDs or the disposition name alone
  cannot cure it. Gather real new evidence, or choose the disposition the
  existing evidence supports (for example `unresolved`).
- **Stale binding**: refresh the source or runtime binding only from a new real
  observation; never edit a fingerprint or timestamp to match.
- **Operational failure** (exit 3, unavailable helper): once the operational
  cause has changed, retry with the identical packet bytes. Do not alter the
  payload to work around an I/O or interpreter failure.
- **Actual denial** by the host or user stays denied; a correction never lifts it.

An unchanged resubmission with no changed condition is not progress; stop and
report instead. Do not persist the rejected packet or echo it whole; any
recovery obligation carries only a sanitized follow-up.
