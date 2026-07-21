# Task 13 preclosure report - supported-version promotion evidence

Date: 2026-07-16
Status: local preclosure complete; hosted six-cell matrix and CodeQL explicitly pending
Owns: PI-AC-35

## Outcome

The provisional promotion envelope is sanitized and structurally complete for the accepted two-phase sequence. Isolated local Windows runs passed for Pi 0.80.5 and 0.80.6. The separately reported latest canary resolved to Pi 0.80.9 and was rejected by the exact supported-version boundary, as intended; that canary is nonblocking.

No global Pi install, operator auth path, provider credential, prompt, task text, raw JSONL, stdout, stderr, environment value, or repository payload entered the evidence. Every npm install used a disposable prefix and isolated home that was removed after the run.

## Bounded results

- Pi 0.80.5, Windows x64: `PI-LOCAL-SUPPORTED`, PASS, 69,246 ms.
- Pi 0.80.6, Windows x64: `PI-LOCAL-SUPPORTED`, PASS, 68,678 ms.
- Pi latest (resolved 0.80.9), Windows x64: `PI-LATEST-CANARY`, nonblocking FAIL, 15,143 ms, `VERSION_UNSUPPORTED`.
- Windows/macOS/Linux x Pi 0.80.5/0.80.6: `PI-HOSTED-PENDING` until PR CI runs on a committed SHA.
- GitHub CodeQL: `PI-CODEQL-PENDING` until PR CI runs on the same committed SHA.

## Evidence

- `docs/reports/pi-support/promotion.json` contains exactly ten bounded rows and a null preclosure commit.
- `docs/reports/pi-support/promotion.md` is the human-readable rendering of those bounded fields.
- `docs/parity.md` links the evidence while labeling it provisional and hosted-pending.

## Verification

- `python .github/scripts/test_pi_security.py --evidence docs/reports/pi-support/promotion.json` - PASS.
- `python .github/scripts/test_public_pi_docs.py` - 11 passed.
- `python .github/scripts/test_pi_platform_contract.py --fixtures-only` - PASS, including the descriptor and real write-idempotency suites.
- Isolated Pi 0.80.5 platform contract - all 14 live/local steps passed.
- Isolated Pi 0.80.6 platform contract - all 14 live/local steps passed.

## Remaining terminal gate

Task 13 remains `IN_PROGRESS` and PI-AC-35 remains `OPEN`. After the governed checkpoint commit and PR, replace only the pending hosted rows with actual six-cell and CodeQL results bound to the committed SHA, rerun the evidence gates, and obtain the required independent reproduction before acceptance.
