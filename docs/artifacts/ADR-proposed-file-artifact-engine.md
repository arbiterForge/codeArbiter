# Archived package proposal — superseded by ADR-0037

**Status: superseded package input, not an accepted decision.** The repository
accepted `.codearbiter/decisions/0037-extensible-structured-artifact-engine.md`
instead.

Permit a shared Go utility and versioned file-artifact schemas for codeArbiter specifications and implementation plans. Each canonical artifact remains one checked-in human-readable HTML file with an authoritative structured model and derived presentation. No database, ORM, daemon or server is introduced. Python hooks remain standard-library-only and invoke a verified installed executable through existing governed execution.

The package originally proposed clarifying ADR-0004. That proposal was rejected:
ADR-0004's “schema layer” follows its database context and needs no amendment.
ADR-0037 records the actual structured-file architecture without modifying or
reinterpreting ADR-0004.

Do not add public slash commands, agents, skills or always-registered model tools. Shared source remains canonical; generated host copies must use existing build/sync mechanisms. The current candidate does not enable default HTML rollout and does not qualify farm or non-Linux writes.
