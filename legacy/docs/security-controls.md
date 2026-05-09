# Security Requirements (Mapped to Control Families)

Each rule cites the NIST 800-53 Rev. 5 control family it serves. Stage tags
indicate when each rule is enforcing.

## Authentication & Authorization

- MUST authenticate every API request via OIDC bearer token validated against the configured IdP. (IA-2, IA-8) [S1+]
- MUST require MFA for all human users [S2+]; phishing-resistant MFA (FIDO2/WebAuthn) [S3+]; PIV/CAC for privileged users [S4]. (IA-2(1), IA-2(2), IA-2(12))
- MUST enforce RBAC at the API layer with deny-by-default. (AC-3, AC-6) [S1+]
- MUST log every authn/authz decision with outcome to the audit sink. (AU-2, AU-12)

## Cryptography & Transit

- MUST use TLS 1.3 (TLS 1.2 minimum, FIPS-approved cipher suites only) for all inter-service traffic. (SC-8, SC-13) [S1+]
- MUST require mTLS between Z-API, Z-WORKER, Z-DB, Z-AUDIT. (SC-8(1), IA-9) [S3+]
- MUST encrypt data at rest with KMS CMK (FIPS endpoint). (SC-28, SC-28(1)) [S1+]

## Container & Workload

- MUST run all containers as non-root, read-only filesystem, drop ALL capabilities, seccomp `RuntimeDefault`. (CM-7, AC-6) [S2+]
- MUST isolate worker job execution: rootless container [S2+]; gVisor or Firecracker [S3+]. (SC-39, SI-3)
- MUST run STIG-hardened base images (UBI9 STIG profile). (CM-6, CM-7) [S3+]

## Network

- MUST default-deny egress; allow-list per zone in NetworkPolicy. (SC-7, SC-7(5)) [S2+]
- MUST validate Gitea webhooks via HMAC + source-IP allow-list + replay-window check. (SC-8, SI-10, IA-9) [S1+]

## Supply Chain

- MUST scan and sign every container image; deploy MUST verify signature with cosign + Kyverno admission policy. (SR-4, SR-11) [S2+ sign; S3+ verify]
- MUST achieve SLSA Build L2 [S2+], L3 [S4]. (SR-4, 800-218 PW.4)
- MUST emit an SBOM per build (CycloneDX). (SR-3, EO 14028) [S1+]

## Assessment

- MUST maintain a POA&M for any unresolved Medium+ finding. (CA-5) [S3+]
