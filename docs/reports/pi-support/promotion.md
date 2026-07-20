# Pi support promotion evidence

Status: final hosted evidence bound to commit `394f5f311f47624c1826d8e6ad03e26adbef4a36`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 122521 | NONE |
| 0.80.10 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 107780 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 551000 | NONE |
| 0.80.10 | windows | x64 | PI-HOSTED-SUPPORTED | true | 417000 | NONE |
| 0.80.10 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 208000 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 174000 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 134000 | NONE |
| 0.80.10 | linux | x64 | PI-HOSTED-SUPPORTED | true | 123000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 114000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LATEST-CANARY | false | 780 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
