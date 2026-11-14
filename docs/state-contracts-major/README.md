# codeArbiter major implementation corpus

Start with START-HERE.md. Open index.html for the readable guide, complete task specifications and all baseline state/event/effect rows. PROMPT.txt is the starting instruction for the receiving CLI agent.

The intake is anchored to arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf. It contains 82 planned tasks, all 70 audit records, 287 machine families, 1,748 baseline transitions, and 31 proposed composed acceptance scenarios. Every owner task additionally contains its focused acceptance/failure/recovery cases.

Run python3 tools/validate_packet.py from this directory. Add --initial-handoff to verify original unexecuted statuses; optional --repo /absolute/source/checkout checks existing source paths. This is a structural packet check, never product verification.

Preserve the intake and use execution/ for actual progress and new evidence. Follow EXECUTION-RECORDS.md. The checksum manifest binds the delivered intake; new execution files are intentionally outside that frozen manifest.

The original audit JSON, HTML and evidence ZIP remain unchanged under audit/. Raw diagnostic/read coverage files are also extracted under audit-work/ for the exact paths used in domain designs. New handoff reviews, CI inventory and live metadata observations are under evidence/. Full operating/voice policy context read during this handoff is under project-context/.

Only arbiterForge/codeArbiter is the implementation target. No source branch, remote branch, tag or Release was changed while preparing this corpus. The separate integration branch and eventual major release are instructions for the receiving CLI workflow.
