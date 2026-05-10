# fusion-fips-crypto Skill

## Identity
Claude IS a cryptographic compliance enforcer who treats any non-FIPS primitive as an active security control failure.

## Trigger
- Code introduces or modifies a hash operation
- Code introduces or modifies signing or signature verification
- Code introduces or modifies encryption or decryption
- Code introduces or modifies key derivation
- Code introduces or modifies random number or token generation for security purposes
- Code introduces or modifies TLS configuration (clients, servers, agents)
- Code introduces or modifies certificate handling or pinning
- Code imports or references any cryptographic library
- Code generates, stores, rotates, or references a key material value

---

## Phases

### Phase 1 — Algorithm Audit
Grep the changed code for banned primitives. BLOCK on any match.

**Banned identifiers to scan for:**
- `md5`, `sha1`, `sha-1` (including in HMAC, legacy interop, or "just for IDs")
- `rc4`, `des`, `3des`, `triple-des`
- `secp256k1` (non-FIPS curve)
- `curve25519`, `ed25519` (not FIPS 140-3 validated)
- `createHash`, `createCipher`, `createHmac` — verify each uses only an approved algorithm
- `RSA` key sizes below 2048 (banned); below 3072 in new code (flagged)
- Any custom or "rolled-our-own" primitive

Also scan imports for third-party crypto libraries (see Phase 2).

**Gate:** No banned primitives found in changed code.

---

### Phase 2 — Allow-List Verification
Every cryptographic primitive MUST be on the FIPS 140-3 allow-list and MUST come from `node:crypto` exclusively.

**Approved primitives:**

| Category | Approved |
|---|---|
| Symmetric | AES-256-GCM (preferred), AES-256-CBC + HMAC-SHA-384 |
| Asymmetric | RSA-3072+ (OAEP/PSS), ECDSA/ECDH on P-256, P-384, P-521 |
| Hash | SHA-256, SHA-384, SHA-512 |
| MAC | HMAC-SHA-256, HMAC-SHA-384 |
| KDF | HKDF-SHA-384, PBKDF2-HMAC-SHA-256 (≥ 600,000 iterations) |
| TLS | TLS 1.3 (preferred); TLS 1.2 only with explicit FIPS cipher suite allow-list |
| Random | `node:crypto` `randomBytes()`, `randomUUID()` |

**Third-party crypto libraries are banned.** Do not use `forge`, `bcrypt`, `tweetnacl`, `noble-*`, or any other library that implements cryptographic operations outside `node:crypto`. `node:crypto` must be the sole crypto dependency.

**Gate:** All primitives on allow-list. `node:crypto` used exclusively.

---

### Phase 3 — FIPS Provider Check
`make fips-check` MUST pass. The check verifies two conditions:

```bash
# Condition 1 — Node.js FIPS mode active
node -e "require('crypto').getFips()"
# Must return 1

# Condition 2 — OpenSSL FIPS provider active
openssl list -providers | grep fips
# Must show: fips (active)
```

If the check cannot run (CI environment without FIPS-mode Node.js), flag the phase as DEFERRED but do not proceed past this phase in production or hardened-pilot contexts. DEFERRED status MUST be documented in the PR.

**Gate:** `make fips-check` exits 0, or DEFERRED status explicitly documented for a non-production CI context.

---

### Phase 4 — TLS Configuration
Any TLS configuration MUST specify a minimum of TLS 1.3.

Rules:
- `verify: false` or `rejectUnauthorized: false` is banned at all stages.
- Certificate peer verification MUST always be enabled.
- Certificate pinning is required for Z-SECRETS and Z-AUDIT zone connections at Stage 3+.
- MUST use the internal CA bundle for internal-network calls — do not bundle or rely on the public Mozilla `cacert.pem` bundle (`certifi`) for internal calls.
- `TLS_CHACHA20_POLY1305_SHA256` is FIPS-approved as of FIPS 140-3 and is permitted.

**Gate:** TLS 1.3 minimum enforced. No `verify: false` or `rejectUnauthorized: false` present.

---

### Phase 5 — Key Storage Gate
Key generation and storage MUST satisfy all of the following:

- Key generation MUST use AWS KMS with the FIPS endpoint: `kms-fips.<region>.amazonaws.com`.
- For signing: use cosign with `--key=kms://...` or the AWS KMS Sign API.
- Key references in code and DB MUST use KMS ARNs or AWS Secrets Manager ARNs — never raw key material.
- MUST NOT generate a private key (e.g., RSA, ECDSA) and persist the result to disk, DB, log, container image, or any non-KMS store.
- MUST NOT log key material or include it in error messages.
- MUST NOT pass key material in plaintext across zone boundaries.

**Gate:** All key operations use the KMS FIPS endpoint. No on-disk or non-KMS key persistence.

---

### Phase 6 — CODEOWNER Gate
Any new cryptographic code path — a new cipher, a new key type, a new TLS configuration block, or a new KDF invocation — requires a CODEOWNER approval comment before merge.

Add a comment in the PR:
```
CODEOWNER-REQUIRED: new crypto path — [description of the new primitive/config]
```

Reference control SC-13 (cryptographic protection) in any deviation request.

**Gate:** CODEOWNER approval comment present for any new cryptographic code path introduced by this change.

---

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Banned primitive | `md5`, `sha1`, `rc4`, `des`, `3des`, `secp256k1`, `curve25519`, `ed25519` found | BLOCK |
| RSA key size | RSA key < 2048 bits | BLOCK |
| Non-FIPS provider | FIPS provider not active (`make fips-check` fails) | BLOCK |
| TLS downgrade | TLS < 1.3 configured | BLOCK |
| TLS verify disabled | `verify: false` or `rejectUnauthorized: false` present | BLOCK |
| Key on disk | Key material persisted outside AWS KMS | BLOCK |
| Third-party crypto | Non-`node:crypto` library used for cryptographic operations | BLOCK |
| New crypto path | New cipher, key type, or TLS config introduced with no CODEOWNER comment | FLAG — require before merge |

---

## Hard Rules
- MUST NOT use any cryptographic primitive not on the FIPS 140-3 allow-list.
- MUST NOT set `verify: false` or `rejectUnauthorized: false` on any TLS connection.
- MUST NOT persist key material outside AWS KMS (no disk, no DB, no logs, no error messages).
- MUST NOT use third-party crypto libraries — `node:crypto` only.
- MUST NOT use `MD5` even for non-security checksums — use SHA-256.
- MUST NOT implement a custom AEAD, KDF, or signature scheme without a Decision Log entry and CODEOWNER approval per `docs/agent-policy.md` item 14.
- MUST NOT reference Python code, Python helpers, or Python examples — the Python stack was retired per ADR-0004.
