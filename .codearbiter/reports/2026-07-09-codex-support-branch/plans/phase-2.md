# Phase-2 plan — wave 2 (secrets-supply, test-fidelity)

No kept work. Both lenses returned zero findings after full-unit reads.

- **secrets-supply (0):** secret/crypto detection is git-level (`pre-bash.py` H-09b/H-10b scanning `git diff` at commit time via `_hooklib.SECRET_RE`/`CRYPTO_RE`), so Claude's Write/Edit route and Codex's apply_patch route converge on the same scan surface — no patch shape (context lines, rename fan-out, opaque envelope) lets a secret land unscanned. Gate-event logging writes only fixed tag strings, never payload/content. No dependency manifests changed; hooks remain stdlib-only. No hardcoded secrets in the diff.
- **test-fidelity (0):** `test_codex_adapter.py` fixtures match the documented Codex producer contracts and the real `CodexHost`/`parse_apply_patch` code; blocked-verdict parity tests spawn real subprocess invocations rather than mocking; the M1-refactored suites invoke hooks via real subprocess through the real file-adjacent `_host.py` load path (no monkeypatched Host). The suite's un-wiredness in CI is filed by the architecture lens (architecture-003), not here.

Note carried forward: test-fidelity confirms fixture fidelity but NOT that the risk paths are all covered — coverage-lens territory (wave 3) assesses gaps like the untested load_host fallback and opaque-op paths.
