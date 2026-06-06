#!/usr/bin/env bash
# codeArbiter v2 — PostToolUse(Write|Edit) reminders. Scope-touch nudges.
# No-op without jq.
#
# v2 prune: dropped H-06 (doc-review-gate skill cut). Kept H-07 (dependency
# review), H-09 (crypto — now points at the slim crypto check), H-10 (secret).

which jq > /dev/null 2>&1 || exit 0
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // ""')

# H-07: dependency manifest changed — review before committing.
if echo "$FPATH" | grep -qE '(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements\.txt|pyproject\.toml|go\.mod|Cargo\.toml)$'; then
  echo "REMINDER [H-07]: Dependency manifest changed. Dispatch dependency-reviewer before committing (ORCHESTRATOR §5)." >&2
fi

# H-09: crypto pattern — run the slim banned-primitive check + auth-crypto-reviewer.
if echo "$CONTENT" | grep -qiE '(createHash|createCipher|createHmac|\bmd5\b|\bsha1\b|\brc4\b|\bdes\b|3des|\bRSA\b|x509|bcrypt|crypto\.|InsecureSkipVerify|verify=False)'; then
  echo "REMINDER [H-09]: Crypto/TLS pattern detected. Run the crypto-compliance check + dispatch auth-crypto-reviewer (no MD5/SHA1/DES/RC4; do not disable TLS verification)." >&2
fi

# H-10: possible hardcoded secret.
if echo "$CONTENT" | grep -qiE '\b(password|secret|token|api_key|apikey|private_key|passphrase|credential)\s*=\s*["'"'"'][^"'"'"']{4,}'; then
  echo "REMINDER [H-10]: Possible hardcoded secret. Run the secret-handling check before committing." >&2
fi

exit 0
