# Pi support promotion evidence

Status: final hosted evidence bound to commit `98e770566252723af862a8802a0b9c7773629a59`.

| Version | Platform | Architecture | Result | Passed | Timing (ms) | Diagnostic |
|---|---|---|---|---:|---:|---|
| 0.80.5 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 118937 | NONE |
| 0.80.10 | windows-local | x64 | PI-LOCAL-SUPPORTED | true | 117196 | NONE |
| 0.80.5 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 193000 | NONE |
| 0.80.10 | macos | arm64 | PI-HOSTED-SUPPORTED | true | 138000 | NONE |
| 0.80.5 | linux | x64 | PI-HOSTED-SUPPORTED | true | 130000 | NONE |
| 0.80.10 | linux | x64 | PI-HOSTED-SUPPORTED | true | 108000 | NONE |
| 0.80.10 | windows | x64 | PI-HOSTED-SUPPORTED | true | 482000 | NONE |
| 0.80.5 | windows | x64 | PI-HOSTED-SUPPORTED | true | 493000 | NONE |
| codeql | github | x64 | PI-CODEQL-HIGH | true | 113000 | NONE |
| 0.80.6 | windows-local | x64 | PI-LATEST-CANARY | false | 780 | VERSION_UNSUPPORTED |

This document is generated only from the bounded fields in [promotion.json](./promotion.json). It contains no prompts, task text, provider responses, environment values, auth paths, raw JSONL, stdout, stderr, or repository payloads.
