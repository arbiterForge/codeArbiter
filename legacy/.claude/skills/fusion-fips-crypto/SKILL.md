---
name: fusion-fips-crypto
description: Use whenever code involves cryptography, hashing, signing, encryption, key derivation, random generation, TLS configuration, or certificate handling in the FUSION codebase. Tells the agent which primitives are FIPS 140-3 approved, which are banned, and how to verify the FIPS provider is active.
---

# FUSION FIPS-Validated Crypto

FUSION runs on UBI9 with the OpenSSL FIPS provider active. Every cryptographic
operation MUST go through that provider. Using Python's stock `hashlib` with
the wrong algorithm, or `cryptography`'s defaults without checking the
backend, will produce code that fails ATO review.

## Allow-List (FIPS 140-3 approved)

- **Symmetric:** AES-256-GCM (preferred), AES-256-CBC + HMAC-SHA-384
- **Asymmetric:** RSA-3072 or higher, ECDSA P-256, ECDSA P-384
- **Hash:** SHA-256, SHA-384, SHA-512
- **MAC:** HMAC-SHA-256, HMAC-SHA-384
- **KDF:** HKDF-SHA-384, PBKDF2-HMAC-SHA-256 (≥ 600,000 iterations)
- **TLS:** TLS 1.3 (preferred), TLS 1.2 with FIPS cipher suites only

## Banned (do not use, ever)

- MD5, SHA-1 (including in HMAC, in legacy interop, in "just for IDs")
- RC4, 3DES, DES
- RSA < 2048 (and < 3072 in new code)
- Curve25519 / Ed25519 (NOT FIPS-validated as of FIPS 140-3)
- Any custom or "rolled-our-own" primitive

## Required Library Choices

```python
# YES — uses system OpenSSL FIPS provider
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# NO — pure-Python implementations, NOT FIPS validated
import hashlib  # AVOID for security purposes; stdlib falls back to non-FIPS
# Specifically banned: hashlib.md5, hashlib.sha1, hashlib.new("md5"|"sha1")
```

When `cryptography` is built against a FIPS-mode OpenSSL, calling a non-FIPS
algorithm raises `InternalError`. That is the desired behavior. Do NOT catch
and fall back.

## Verification

Before using any new crypto code, run:

```bash
make fips-check
# Equivalent to:
openssl list -providers
# MUST show: fips (active)
```

In Python, verify at runtime:

```python
from cryptography.hazmat.backends.openssl.backend import backend
assert backend._fips_enabled, "FIPS mode is not active in OpenSSL backend"
```

This assert MUST exist in the application startup path (`backend/main.py` or
equivalent) and MUST cause the process to exit non-zero if FIPS is not active.

## TLS Configuration

For `httpx`, `aiohttp`, `requests`:

```python
import ssl
ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_3   # MUST be 1.3; 1.2 only with explicit allow-list
ctx.set_ciphers("TLS_AES_256_GCM_SHA384:TLS_AES_128_GCM_SHA256:TLS_CHACHA20_POLY1305_SHA256")
# Then pass ctx to the client
```

Note: `TLS_CHACHA20_POLY1305_SHA256` is FIPS-approved as of FIPS 140-3.
Validate against the cert in use.

## Certificate Handling

- MUST verify peer certificates. `verify=False` is BANNED — Bandit B501 set to error.
- MUST pin to the internal CA bundle (`/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem` on UBI9) for internal calls.
- MUST NOT bundle `cacert.pem` from `certifi` for internal-network calls (it's the public Mozilla bundle).

## Key Storage

- Keys MUST live in AWS KMS (FIPS endpoint) or AWS Secrets Manager (FIPS endpoint).
- MUST NOT `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(...)` and persist the result to disk.
- For signing: prefer cosign with `--key=kms://...` or AWS KMS Sign API.

## Hard Stops

If you find yourself:

- Using `hashlib.md5` for "just a checksum, not security" — STOP. Use SHA-256.
- Using `secrets.token_hex` — OK (uses `os.urandom`, FIPS-acceptable).
- Using `random.random` for anything security-related — STOP. Use `secrets.SystemRandom`.
- Importing `pycryptodome` or `pycryptodomex` — STOP. Not FIPS-validated. Use `cryptography`.
- Implementing your own AEAD, KDF, or signature scheme — STOP. This needs a Decision Log entry and CODEOWNER approval per `docs/agent-policy.md` item 14.

Cite control: SC-13 (cryptographic protection) for any deviation request.
