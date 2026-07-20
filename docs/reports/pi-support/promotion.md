# Pi support promotion evidence

Status: final hosted evidence bound to commit `6a766a019a79899be581cd1e66e3a28641142b7e`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 118937 | NONE |
| 0.80.10 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 117196 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 127000 | NONE |
| 0.80.10 | windows | x64 | PI-HOSTED-SUPPORTED | true | 491000 | NONE |
| 0.80.10 | linux | x64 | PI-HOSTED-SUPPORTED | true | 122000 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 510000 | NONE |
| 0.80.10 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 142000 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 150000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 96000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LATEST-CANARY | false | 780 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
