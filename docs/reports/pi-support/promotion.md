# Pi support promotion evidence

Status: final hosted evidence bound to commit `54080beadc8ff1fe6c8a5e0da81ad699c3ad0920`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 69246 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 398000 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 80000 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 130000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 68678 | NONE |
| 0.80.6 | windows | x64 | PI-HOSTED-SUPPORTED | true | 360000 | NONE |
| 0.80.6 | linux | x64 | PI-HOSTED-SUPPORTED | true | 88000 | NONE |
| 0.80.6 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 118000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 59000 | NONE |
| 0.80.9 | windows-local | x64 | PI-LATEST-CANARY | false | 15143 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
