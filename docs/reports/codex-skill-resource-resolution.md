# Codex skill-resource resolution characterization

Date: 2026-08-22

## Result

The four required backend cells passed against the same tracked fixture bytes:

- Codex CLI 0.143.0
- Codex CLI 0.145.0
- Codex app-server 0.143.0
- Codex app-server 0.145.0

Each required receipt reports `evidence_class: supported`, `verdict: PASS`,
`desktop_shell_proven: false`, requested and effective `read-only` sandboxing,
`never` approval, ChatGPT authentication, and the exact three successful direct
resource reads. The separate Codex CLI 0.149.0 advisory cell failed closed with
`read-only-policy-rejection`; that result is drift evidence and does not satisfy
or change the supported four-cell matrix.

This is backend evidence only. It does **not** prove behavior in the ChatGPT
desktop UI shell, its bundled Codex runtime, or an exact release candidate.

## Contract bindings

- Fixture: [`.github/fixtures/codex-skill-resources`](../../.github/fixtures/codex-skill-resources)
- Matrix: [`.github/fixtures/codex-skill-resources/matrix.json`](../../.github/fixtures/codex-skill-resources/matrix.json)
- Checker: [`.github/scripts/check_codex_skill_resources.py`](../../.github/scripts/check_codex_skill_resources.py)
- Fixture SHA-256: `a7cb361b93992a3d1d64f87d77650db82847f8a8dc931a1bba01094a63068ec1`
- Evidence-contract SHA-256: `d7fee53403b48b14ffc5dcf86acaebbff72944ecb25bd0ffbdf4aac11db1d302`
- Environment: `Windows-11-10.0.26200-SP0`, `AMD64`, isolated clean homes
- Authentication: fresh one-use ChatGPT device login per cell; no API key
- Network policy: `model-api-only; tool-network-disabled`

Every one-use authentication root was removed after evidence capture without
opening, printing, hashing, or persisting credential contents. The absolute
paths below name the ephemeral roots used by the receipts; they are historical
evidence and no longer exist.

## Required receipts

| Surface | Version | Receipt | Receipt SHA-256 | Native executable SHA-256 | Canonical operation-evidence SHA-256 |
|---|---:|---|---|---|---|
| CLI | 0.143.0 | [`cli-0.143.0.json`](evidence/codex-skill-resource-resolution/cli-0.143.0.json) | `e52b14da53e0d05ffce7bfb152d5a2fed62d9dd350b0856d64da857348c50d51` | `5728e3ddf1480103bad235560e95cf7764ea3069f06029f9b2f39eb74a8066f6` | `0ff78740e60b0088e1a96cdada7dc8b60469990c16404a4837ab9a13339bc5b7` |
| CLI | 0.145.0 | [`cli-0.145.0.json`](evidence/codex-skill-resource-resolution/cli-0.145.0.json) | `890ed8e440e5b6a6b17f69dd947e9d3e4c9aeb23afd8f67edc6d2f11db95e37d` | `83751f15cb6a0a7b97df67752c001e3fe1c20e18ffbfec3ff63567296205eb6c` | `6f914fed4e1a9cd4d01131602d96ab18dfcb15351f57f61f78be563cfd2ac680` |
| app-server | 0.143.0 | [`app-server-0.143.0.json`](evidence/codex-skill-resource-resolution/app-server-0.143.0.json) | `15aedd195376a5e85b2c938f61d51a29d9c59e4ad7d06a8cf0e711b2945bdfec` | `5728e3ddf1480103bad235560e95cf7764ea3069f06029f9b2f39eb74a8066f6` | `3923c5c9a6ff9264dbe52c788b2e30908dc2ac0b9ea4190684a36428ae8a52ff` |
| app-server | 0.145.0 | [`app-server-0.145.0.json`](evidence/codex-skill-resource-resolution/app-server-0.145.0.json) | `c414cedca8d0635d94cb7397d3a47ac073d22320be5f8c77b095bbfe456eda99` | `83751f15cb6a0a7b97df67752c001e3fe1c20e18ffbfec3ff63567296205eb6c` | `bc49404fce386fd7df75af9c13e6948ff0b8455b36085da560d5dd9d9984db01` |

Pinned npm provenance and integrity are recorded in each receipt and match the
tracked matrix. Both 0.143.0 cells bind integrity
`sha512-6h53sNtESIYncWVwU7zEjdVajwcad/0H94MOrgGqhwBMa9RRUDVG6DU9E9euC7yRdtrsKDAkJkz/m5moZ6MU3A==`.
Both 0.145.0 cells bind integrity
`sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ==`.

## Selected paths and contained reads

The selected skill was `codex-skill-resource-probe:probe`. Each required cell
reported its installed absolute entry path and the following exact contained
resource chain beneath its receipt-specific `installed_plugin_root`:

1. `skills/probe/SKILL.md` — `skill-probe-nonce-7f4d`
2. `routines/nested.md` — `nested-routine-nonce-2ca1`
3. `agents/probe.md` — `agent-probe-nonce-91be`

The exact selected entry paths were:

- CLI 0.143.0: `C:\Users\brenn\AppData\Local\Temp\codearbiter-stage1-oauth\cli-0143-auth-20260822T1928Z\plugins\cache\codex-skill-resource-characterization\codex-skill-resource-probe\0.0.0\skills\probe\SKILL.md`
- CLI 0.145.0: `C:\Users\brenn\AppData\Local\Temp\codearbiter-stage1-oauth\cli-0145-auth-20260822T1946Z\plugins\cache\codex-skill-resource-characterization\codex-skill-resource-probe\0.0.0\skills\probe\SKILL.md`
- app-server 0.143.0: `C:\Users\brenn\AppData\Local\Temp\codearbiter-stage1-oauth\app-server-0143-auth-20260822T2012Z\plugins\cache\codex-skill-resource-characterization\codex-skill-resource-probe\0.0.0\skills\probe\SKILL.md`
- app-server 0.145.0: `C:\Users\brenn\AppData\Local\Temp\codearbiter-stage1-oauth\app-server-0145-auth-20260822T2015Z\plugins\cache\codex-skill-resource-characterization\codex-skill-resource-probe\0.0.0\skills\probe\SKILL.md`

The CLI receipts derive skill invocation evidence from the exact successful
entry read because these pinned JSONL versions do not emit a native typed
skill-invocation event. The app-server receipts bind the exact skill object and
absolute selected path returned by `skills/list`. In all four cells, the
validated operation events independently prove exactly three successful direct
reads and no cache search, glob, enumeration, network tool, failed command, or
path escape. The durable `operation_transcript_sha256` field hashes only the
reconstructed allowlisted path/nonce/method facts; it never hashes raw runtime
stdout, stderr, protocol messages, or transcript bytes.

## Preserved failures and advisory drift

The first authenticated app-server 0.143.0 run returned nonce strings instead
of the required path/nonce objects. That receipt remained a failure; it was not
reinterpreted. Its non-secret hashes were:

- errors: `b3f047adc32ac5bd49d07b1dc5299d265bd26763a73bc886352ed7be4cb7f91a`
- operation transcript: `961be4b453de9d0c5d5957c31cb789f6e2b1f6b415997e1cb5011144b30e314b`
- stdout: `4194b105489726093bd4cb424648b3abdc49e31ae089c777c1fc8bf92f597f50`
- stderr: `7d2f4da22f5825bccd18f46139e1dd88532a73fb7b86ec4f2c8cedbfacd73d22`

The prompt contract was then repaired test-first to require the selected
absolute entry path and exactly three path/nonce-only objects. The complete
resource suite passed 96 tests, and an independent Phase 4 review passed 21
focused app-server/observation tests before the fresh required rerun.

The advisory receipt is
[`cli-0.149.0-advisory.json`](evidence/codex-skill-resource-resolution/cli-0.149.0-advisory.json)
(SHA-256 `2d600104c84b41bc9c7875bb68f137eb005f4ce733dcdb3cef14b52f8bcecc9b`).
It binds npm integrity
`sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ==`,
native executable SHA-256
`14b7e6b2356e82d1d9275579eaa588757b4e0a501b65dcc19fccdf77bd83dc00`,
and the same fixture/evidence-contract hashes as the required cells. It records
`verdict: FAIL`, `evidence_class: advisory`, and
`failure.classification: read-only-policy-rejection`. No full-access diagnostic
is promoted into read-only support evidence.

## Conclusion

The tracked backend characterization prerequisite for ADR-0031 is satisfied:
both supported CLI versions and both supported app-server versions resolve the
absolute selected skill and follow the identical contained relative resource
chain under read-only/never policy. ADR-0031 was accepted on 2026-08-22 with its
decision content unchanged. The matrix's `durable_record.status: pending` is a
pre-ingestion declaration by design; the checker derives the terminal
`durable_evidence.state: complete` result from the bound report and receipt
bytes without rewriting fixture metadata. After PR 1 lands, the next governed
implementation boundary is PR 2's root normalization and complete Codex charter
resolution. Desktop-shell proof remains a separate exact-candidate release
gate and is still unproven.
