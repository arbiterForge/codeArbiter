# Pi support promotion evidence

Status: final hosted evidence bound to commit `11df92889cb64c9ce3af41580111acec01b46555`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 70747 | NONE |
| 0.80.10 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 70887 | NONE |
| 0.80.10 | linux | x64 | PI-HOSTED-SUPPORTED | true | 107000 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 96000 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 438000 | NONE |
| 0.80.10 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 131000 | NONE |
| 0.80.10 | windows | x64 | PI-HOSTED-SUPPORTED | true | 366000 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 187000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 114000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LATEST-CANARY | false | 780 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
