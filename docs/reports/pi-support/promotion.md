# Pi support promotion evidence

Status: final hosted evidence bound to commit `f764929e02fbb67b43a3b828686c0007445a0316`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 104547 | NONE |
| 0.80.10 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 103745 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 446000 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 123000 | NONE |
| 0.80.10 | windows | x64 | PI-HOSTED-SUPPORTED | true | 418000 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 198000 | NONE |
| 0.80.10 | linux | x64 | PI-HOSTED-SUPPORTED | true | 138000 | NONE |
| 0.80.10 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 185000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 113000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LATEST-CANARY | false | 780 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
