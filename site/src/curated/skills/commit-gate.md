---
entity: skills/commit-gate
related: [commands/commit, tdd]
gates:
  - gate: permission
    when: every invocation
    effect: an explicit instruction to commit must be on record; "looks good" does not count
  - gate: verification
    when: after classification
    effect: tests, lint, and a secrets scan must all come back clean, plus crypto/secret/migration/CI review where the diff touches those areas, before anything else runs
  - gate: behavioral proof
    when: after verification passes
    effect: inspected current command output must prove the criterion; reuse a matching prior result or run the missing or affected check
  - gate: diff review
    when: before staging
    effect: the full staged diff is read for stray files, secrets, incomplete work, and scope creep; any finding unstages the offending files and stops
---

## Plan tasks and receipts

Unfinished plan tasks stay visible in the report without blocking an otherwise valid scoped
commit. Read the selected typed plan through its engine and distinguish implementation progress
from verification. Ordinary authorized commits do not require an artifact acceptance receipt;
explicit commit permission, applicable tests, secrets scanning and specialized security/migration
controls still apply.

## Phases

1. Confirm explicit authorization to commit.
2. Confirm the branch is not a protected one.
3. Classify the staged change into a single commit type and flag any database migration.
4. Establish current tests and lint, and scan the staged files for secrets. Reuse applicable
   observed results and specialized reviews; run missing or affected work. Required markers
   must still cover the actual staged content.
5. Match current evidence to the claimed behavior. A criterion already proved on unchanged
   relevant inputs needs no repeated command solely because this phase began.
5.5. Select changed claims intersecting staged sources. Reinspect that slice, then
   refresh managed v2 pairs through native preview/apply, or use the legacy v1
   re-baseline where applicable. Changed claims enter diff review. Unknown evidence
   defers the affected document's maintenance without blocking independent work.
6. Read the complete staged diff for stray files, secrets, unfinished work, or scope creep.
7. Run the follow-up harvest, then stage exactly the intended files by explicit path.
8. Compose a Conventional Commits message with a body explaining why.
9. Commit, capturing the resulting SHA, and confirm the tree is clean afterward.

## Exits

A clean run ends in a commit SHA, a clean working tree, and a report of what each gate found. A
BLOCK identifies the affected condition to resolve. Rerun its affected checks and preserve
unrelated current evidence.
