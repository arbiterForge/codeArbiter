#!/usr/bin/env bash
which jq > /dev/null 2>&1 || exit 0
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // ""')

# H-06: projectContext file modified — remind doc-review-gate
if echo "$FPATH" | grep -qE '\.agents/projectContext/'; then
  echo "REMINDER [H-06]: projectContext file modified. Run doc-review-gate Phase 2 (freshness check) and Phase 3 (conflict detection) before committing." >&2
fi

# H-07: dependency file changed — remind dependency-reviewer
if echo "$FPATH" | grep -qE '(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$'; then
  echo "REMINDER [H-07]: Dependency file changed. Invoke dependency-reviewer agent before committing (AGENTS.md §5)." >&2
fi

# H-09: crypto pattern detected
# Default conservative list; refine once .agents/projectContext/security-controls.md is populated
if echo "$CONTENT" | grep -qiE '(createHash|createCipher|createHmac|\bmd5\b|\bsha1\b|\brc4\b|\bdes\b|3des|\bRSA\b|\bTLS\b|\.ssl\b|x509|bcrypt|crypto\.)'; then
  echo "REMINDER [H-09]: Cryptographic pattern detected. Invoke crypto-compliance skill and auth-crypto-reviewer agent (AGENTS.md §5). Verify against ${PROJECT_ROOT}/.agents/projectContext/security-controls.md." >&2
fi

# H-10: possible hardcoded secret
if echo "$CONTENT" | grep -qiE '\b(password|secret|token|api_key|apikey|private_key|passphrase|credential)\s*=\s*["'"'"'][^"'"'"']{4,}'; then
  echo "REMINDER [H-10]: Possible hardcoded secret detected. Invoke secret-handling skill (${FRAMEWORK_ROOT}/.agents/skills/secret-handling/SKILL.md Phase 1-2)." >&2
fi

exit 0
