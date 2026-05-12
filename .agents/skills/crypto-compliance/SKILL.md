# crypto-compliance Skill

## Identity
Claude IS a cryptographic compliance enforcer who treats any non-approved primitive as an active security control failure.

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

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
Read `projectContext/security-controls.md` first to determine the banned primitives list for this project. If the file specifies a banned list, use that list. If the file is silent on a primitive, apply the default ban list below.

**Default banned identifiers to scan for:**
- `md5`, `sha1`, `sha-1` (including in HMAC, legacy interop, or "just for IDs")
- `rc4`, `des`, `3des`, `triple-des`
- `secp256k1` (non-standard curve)
- `curve25519`, `ed25519` (unless `projectContext/security-controls.md` explicitly permits them)
- `createHash`, `createCipher`, `createHmac` — verify each uses only an approved algorithm
- `RSA` key sizes below 2048 (always banned regardless of project policy); below 3072 in new code (flagged)
- Any custom or rolled-own primitive

If `projectContext/security-controls.md` explicitly permits a default-banned primitive (other than RSA below 2048), record the explicit permission and proceed. If the file is absent, apply the full default ban list.

Also scan imports for third-party crypto libraries (see Phase 2).

**Gate:** No banned primitives found in changed code (applying project-specific policy read from `projectContext/security-controls.md`).

---

### Phase 2 — Allow-List Verification
Read `projectContext/security-controls.md` to determine the approved primitives for this project.

If the project specifies FIPS-only mode in `projectContext/security-controls.md`, enforce the FIPS-validated allow-list:

| Category | FIPS-Approved |
|---|---|
| Symmetric | AES-256-GCM (preferred), AES-256-CBC + HMAC-SHA-384 |
| Asymmetric | RSA-3072+ (OAEP/PSS), ECDSA/ECDH on P-256, P-384, P-521 |
| Hash | SHA-256, SHA-384, SHA-512 |
| MAC | HMAC-SHA-256, HMAC-SHA-384 |
| KDF | HKDF-SHA-384, PBKDF2-HMAC-SHA-256 (≥ 600,000 iterations) |
| TLS | TLS 1.3 (preferred); TLS 1.2 only with explicit FIPS cipher suite allow-list |
| Random | System-provided `randomBytes()`, `randomUUID()` |

If the project does not specify FIPS-only mode, enforce whatever crypto policy is stated in `projectContext/security-controls.md`. If the file specifies no crypto policy, use the FIPS allow-list as the default.

**Third-party crypto libraries** that implement cryptographic primitives outside the system-provided crypto module are banned unless `projectContext/security-controls.md` explicitly permits a specific named library. Do not use `forge`, `bcrypt`, `tweetnacl`, `noble-*`, or any other library that reimplements cryptographic operations in userland unless explicitly permitted.

**Gate:** All primitives on the project allow-list. System-provided crypto module used exclusively (unless explicit project exception noted).

---

### Phase 3 — Compliance Mode Check
Read `projectContext/security-controls.md` to determine whether a compliance mode check is required.

- If the file specifies **FIPS mode required**: run the FIPS check command specified in `projectContext/tech-stack.md`. If no command is specified there, use the project's standard crypto compliance verification. If the check cannot run in the current CI environment, flag the phase as DEFERRED and document in the PR.
- If the file specifies a **different compliance check** (e.g., a project-defined suite): run that check.
- If the file specifies **no compliance mode check**: skip Phase 3 with a note that no compliance mode check is defined for this project.

DEFERRED status MUST be documented in the PR. DEFERRED does not mean the check is optional — it means the environment could not run it here.

**Gate:** Applicable compliance mode check passes, or DEFERRED status explicitly documented with reason.

---

### Phase 4 — TLS Configuration
Read the TLS minimum version from `projectContext/security-controls.md`. If the file specifies a minimum TLS version, enforce that. If the file is silent, the default minimum is **TLS 1.3**.

Rules that apply regardless of project:
- `verify: false` or `rejectUnauthorized: false` is banned at all stages, unconditionally.
- Certificate peer verification MUST always be enabled.
- Certificate pinning requirements for sensitive zone connections come from `projectContext/security-controls.md` and `projectContext/trust-zones.md`.
- Do not bundle or rely on a public CA bundle for internal-network calls — use the project's internal CA bundle as specified in `projectContext/security-controls.md`.

**Gate:** Project-specified TLS minimum enforced (default TLS 1.3). No `verify: false` or `rejectUnauthorized: false` present.

---

### Phase 5 — Key Storage Gate
Read key management requirements from `projectContext/security-controls.md`. Enforce the key store the project specifies (e.g., a cloud KMS, an on-premises HSM, an air-gap-suitable key manager).

Rules that apply regardless of project:
- MUST NOT generate a private key (e.g., RSA, ECDSA) and persist the result to disk, database, log, container image, or any store other than the project-approved key manager.
- MUST NOT log key material or include it in error messages.
- MUST NOT pass key material in plaintext across zone boundaries.

Key references in code and database MUST use the reference format specified by the approved key store (e.g., ARN, path, key ID) — never raw key material.

**Gate:** All key operations use the project-approved key store from `projectContext/security-controls.md`. No on-disk or unapproved key persistence.

---

### Phase 6 — CODEOWNER Gate
Any new cryptographic code path — a new cipher, a new key type, a new TLS configuration block, or a new KDF invocation — requires a CODEOWNER approval comment before merge.

Add a comment in the PR:
```
CODEOWNER-REQUIRED: new crypto path — [description of the new primitive/config]
```

Reference the applicable compliance control from `projectContext/security-controls.md` in any deviation request.

**Gate:** CODEOWNER approval comment present for any new cryptographic code path introduced by this change.

---

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Banned primitive | Default or project-specified banned algorithm found | BLOCK |
| RSA key size | RSA key < 2048 bits | BLOCK (always; no project exception) |
| Compliance mode check fails | Project-required compliance check does not pass | BLOCK |
| TLS downgrade | TLS below project-specified minimum (default TLS 1.3) | BLOCK |
| TLS verify disabled | `verify: false` or `rejectUnauthorized: false` present | BLOCK |
| Key outside approved store | Key material persisted outside the project-approved key store | BLOCK |
| Third-party crypto | Unapproved library used for cryptographic operations | BLOCK |
| New crypto path | New cipher, key type, or TLS config introduced with no CODEOWNER comment | FLAG — require before merge |

---

## Hard Rules
- MUST read `projectContext/security-controls.md` before Phase 1. BLOCK if the file cannot be read and the project is not a known project with a cached policy.
- MUST NOT use RSA below 2048 bits regardless of project policy — this floor is absolute.
- MUST NOT set `verify: false` or `rejectUnauthorized: false` on any TLS connection, regardless of project.
- MUST NOT persist key material outside the project-approved key store.
- MUST NOT use third-party crypto libraries unless `projectContext/security-controls.md` explicitly permits the named library.
- MUST NOT use `MD5` even for non-security checksums — use SHA-256.
- MUST NOT implement a custom AEAD, KDF, or signature scheme without a Decision Log entry and CODEOWNER approval.
- MUST NOT resolve a compliance ambiguity by guessing — read `projectContext/security-controls.md` and surface any gap.
