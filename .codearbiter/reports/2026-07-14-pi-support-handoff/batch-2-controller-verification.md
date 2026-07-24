# Pi support Batch 2 controller verification

Date: 2026-07-15
Branch: `feat/pi-support`
Result: GREEN

This verification was run by the controller after all seven remediation blocks and their review loops were complete. It covers the current cumulative Tasks 3-5 workspace, not an earlier per-block snapshot.

## Behavioral and package suites

| Suite | Result |
|---|---:|
| Pi TypeScript/Vitest | 8 files, 123/123 |
| TypeScript typecheck | PASS |
| Real package/RPC process | 17/17 |
| Isolated command RPC rerun | 1/1 |
| Three-host Pi parity | 19/19 |
| Pi doctor/backstop | 7/7 |
| Shared hook/security helpers | 69/69 |
| Host descriptors | 13/13 |
| Shared-core generator tests | 13 tests, 1 expected platform skip |
| Surface generator tests | 34/34 |

The package/RPC suite includes real isolated Pi command discovery, enforcement-registration failure, model-visible READ context, process-tree termination, package isolation/pinning, metadata, and release-resource checks.

## Clean generation checks

- `python tools/sync-core.py --check`: PASS, 42 core files x 3 plugins byte-identical.
- `python tools/build-surface.py --check`: PASS, Claude/Codex/Pi surfaces in sync.
- `python tools/build-host-packages.py --check`: PASS, root/package/descriptor metadata consistent.
- `git diff --check`: PASS.

## Deterministic build evidence

Two consecutive controller rebuilds produced identical bytes:

| Artifact | SHA-256 |
|---|---|
| Pi parent bundle | `4DF7A73C7E681E463B3C64B4A75E81B2F0075E6C7DE7D3ECD1210C847799F535` |
| Pi child placeholder | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| Pi dependency lock | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child and dependency lock remain unchanged from the reboot boundary. The parent hash changed only with the accepted doctor-redaction and lifecycle-generation remediation and its rejection/cancellation follow-up.

## Workspace invariants

- Branch remains `feat/pi-support`.
- `git diff --cached --name-only` is empty.
- No commit, push, publish, branch switch, stash, reset, or clean occurred.
- Existing user-owned dirty governance files and the unrelated scratch artifact remain present.

## Known limitation retained

The Pi doctor remains honestly `DEGRADED` for `active-dispatch`. PI-AC-28 and Task 5 remain BLOCKED pending Task 13 real-host/promotion evidence; no controller evidence relabels the stored-wrapper self-test as active-dispatch live fire.

## Post-review remediation verification — 2026-07-15

The controller reran the cumulative verification after closing the two integration findings, the CRITICAL/MEDIUM/LOW security findings, and the activation-overlap observation. This supersedes the earlier counts and parent-bundle hash above for the current workspace.

| Command / suite | Fresh controller result |
|---|---:|
| Pi TypeScript/Vitest | 8 files, 134/134 |
| TypeScript typecheck | PASS |
| Real package/RPC process | 19/19 |
| Isolated command RPC rerun | 1/1 |
| Three-host Pi parity | 19/19 |
| Pi doctor/backstop | 7/7 |
| Shared hook/security helpers | 69/69 |
| Host descriptors | 13/13 |
| Shared-core generator tests | 13 tests, 1 expected Windows skip |
| Surface generator tests | 34/34 |
| `tools/sync-core.py --check` | PASS, 43 core files x 3 plugins byte-identical |
| `tools/build-surface.py --check` | PASS |
| `tools/build-host-packages.py --check` | PASS |

The 19-test package run includes the authentic Windows installed-package poison canary: enabled startup did not execute project-local `git.exe`, and the real managed pre-commit hook succeeded with PATH restricted to the poisoned project while carrying absolute external Python and Git identities. The structural direct-bare-Git subprocess audit also passed.

Two more consecutive controller builds were byte-identical:

| Artifact | Post-fix SHA-256 |
|---|---|
| Pi parent bundle | `51C3861E74DC79F143D8CDE22DC7E11E78F06B27859833AEAA77555121C7B0E8` |
| Pi child placeholder | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

Final controller integrity checks remained clean: `git diff --check` passed, the index was empty, and the branch remained `feat/pi-support`. Tasks 6–9 were not started; Task 5/PI-AC-28 remains blocked exactly as documented above.

## Trust-boundary residual verification — 2026-07-15

After the security rereview identified repository-aware Git activity before affirmative project trust, the controller accepted the strong SMARTS choice recorded in `batch-2-trust-config-fix-brief.md`: global extension load is discovery, and only current affirmative Pi trust authorizes repository-aware startup.

Fresh controller results on the resulting bytes:

| Command / suite | Result |
|---|---:|
| Pi TypeScript/Vitest | 8 files, 138/138 |
| TypeScript typecheck | PASS |
| Real package/RPC process | 20/20 |
| Three-host Pi parity | 19/19 |
| Pi doctor/backstop | 7/7 |
| `tools/sync-core.py --check` | PASS, 43 core files x 3 plugins |
| `tools/build-surface.py --check` | PASS |
| `tools/build-host-packages.py --check` | PASS |

The 20-test package run independently reproduced both sides of the boundary: enabled-untrusted global startup performs no repository-aware bridge/Git/hook/fetch work, while trusted startup still passes the absolute Git/Python identity and real managed-hook canary.

Current deterministic artifacts:

| Artifact | SHA-256 |
|---|---|
| Pi parent bundle | `FE70C2B22E5925D4A5E6A7CC3026930E5E87EA36822F632C5BFBB611A31C9973` |
| Pi child placeholder | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| Pi dependency lock | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The branch remains `feat/pi-support`, the index remains empty, `git diff --check` remains clean, and Tasks 6–14 were untouched by this residual fix.
