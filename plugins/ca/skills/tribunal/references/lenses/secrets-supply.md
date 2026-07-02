# secrets-supply — lens mandate

Executed by `tribunal-secrets-supply-reviewer`. Write contract + evidence discipline: `finding-record.md`.

## Checklist
- Literal secrets in source or `.env.example` — JWT/signing keys, API keys, DB connection strings, OAuth secrets, passwords (CWE-798). `.env.example` populated with real values is a common AI regression.
- Weak/misused crypto (CWE-327): MD5/SHA-1 for password hashing; `Math.random()` for tokens instead of a CSPRNG.
- Cleartext transmission: HTTP where HTTPS is required; credentials in query strings or bodies.
- Secrets/PII in logs; debug flags active without an environment gate.
- Supply chain: hallucinated/slopsquatted package names; dependency overuse (large trees from small features); pins current at training time but now deprecated or vulnerable.

## Exposure
Count of dependencies examined + config/secret-bearing files scanned.

## Out of scope
Injection/authz (appsec).
