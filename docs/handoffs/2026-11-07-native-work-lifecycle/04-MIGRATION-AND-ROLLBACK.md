# 04. Migration, safety and rollback

## Preflight requirements

- Re-read current repository owner, work schema, adapter manifests, project owner marker, board and archive path protections.
- Work only in an isolated temporary repository when exercising a *real-shaped* user board. Create source hashes of the active board, archive and any touched canonical HTML. Preserve all originals.
- A preview is read-only. Never silently adopt during `status`, `work list`, startup, a statusline repaint, project opening or a docs build.
- The authorizing action is an explicit selected adoption, under the existing repository and host authority. An adoption decision must not become repeated per-task approval prompts.

## Cutover invariants

1. Exactly one writable owner before and after the cutover. The old board is a source/snapshot, not a second writer.
2. Every distinct eligible legacy block is either mapped once or produces a named refusal. No text, date, explicit ID, alias or source origin disappears unreported.
3. Preserve original `.codearbiter/legacy/open-tasks.md` and `done-tasks.md` bytes and source-line/block digest pointers.
4. Native work is portable across clones. Local journals are recovery metadata, not the only portable backlog.
5. The native engine independently validates the source, count, row identity, field normalization, CAS and edit set. Never trust only a Python preview.
6. Existing crash-recovery/transaction operation IDs are reused for exact retries; a lost response is never treated as proof no mutation occurred.
7. A real duplicate, changed source, unreadable archive, symlink, corrupt journal, invalid schema or ambiguous binding fails closed without partial cutover.
8. A source version/schema change is compatibility work, not license to rewrite old histories or force older clients to misread newer artifacts.

## If things fail

| Condition | Required behavior |
|---|---|
| Preview refuses a malformed row | Report board and line plus actionable reason; leave source untouched |
| Board changes between preview and cutover | Revision/CAS refusal; collect new preview, do not apply stale row mapping |
| Crash before durable commit | Recover with original operation ID and exact request, then inspect outcome |
| Lost response after commit | Replay/readback original outcome; never mint new work IDs and resubmit blindly |
| Snapshot/legacy source changed after adoption | Preserve native and historical state; report stale provenance; do not overwrite it |
| Actual later native edits exist | **Forward recover**. Do not restore old board as writer or replace newer canonical files with before-images |
| Old installed adapter sees unsupported schema | Fail closed with upgrade guidance; no automatic downgraded write |
| Remote issue/Project update outcome uncertain | Local work stays true; reconcile remote intent before any new send, no automatic duplicate creation |

## Compatibility and release

- Regenerate all derived Python, Go schema, shared surface and Claude/Codex/Pi packages from their canonical owners.
- Re-check host-specific exceptions. Keep Pi publication distinct from Claude and Codex, and keep Academy's declared compatibility pinned to exact versions.
- Verify deployed and distributed behavior only from exact candidate/package bytes with recorded SHA-256s and installed paths.
- Publishing, marketplace promotion, website changes and any live repository adoption are **separate** decisions. No release is authorized by this handoff.
- If only source suites pass, report source tested, installed behavior unknown. If live canary fails, preserve logs/evidence and leave PR draft.

## Security boundaries

The current H-20 issue #1088 describes a shell-variable recognition gap and an approved-bypass procedure that does not complete. Do not reproduce the bypass or use `--no-verify` to work around it. Diagnose a blocked sanctioned change; correct the security issue separately if authorized. A normal task may proceed only through existing real permissions and repository controls.

## Branches and rollback

The handoff branch contains **only packet documents**, and is never merged as implementation code. Create implementation branch from fresh `main`. For code corrections, keep conventional reversible commits. For persisted work-state format changes, document migration, old-client refusal, exact backups, journal readback and forward recovery; a Git revert is not a general state rollback. For remote effects, a Git revert cannot undo already-sent actions.
