#!/usr/bin/env bash
# Refuse a commit that stages anything credential-shaped.
#
# Install once:
#     ln -sf ../../scripts/check-secrets.sh .git/hooks/pre-commit
#     chmod +x scripts/check-secrets.sh
#
# Run over everything already committed:
#     ./scripts/check-secrets.sh --all
#
# .env.example is exempt: it exists to carry placeholders.

set -uo pipefail

# Each prefix must be followed by a real run of key characters. Matching a
# bare "sk-or-" would flag every masked example in the docs ("sk-or-••••…1234"),
# and a hook that cries wolf gets bypassed.
PATTERNS='sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{16,}|(JWT_SECRET|AES_KEY)=[^[:space:]"'"'"'#]{12,}'

# Placeholders that must never trip the hook.
ALLOW='replace-with-a-long-random-secret|change-me|your-|example|placeholder|not-a-real-key|on purpose|PATTERNS=|ALLOW='

if [ "${1:-}" = "--all" ]; then
  files=$(git ls-files)
  mode="tracked files"
else
  files=$(git diff --cached --name-only --diff-filter=ACM)
  mode="staged files"
fi

status=0
for file in $files; do
  case "$file" in
    *.env.example|*/.env.example|.gitguardian.yaml|scripts/check-secrets.sh) continue ;;
    backend/tests/*) continue ;;   # fixtures — see .gitguardian.yaml
  esac
  [ -f "$file" ] || continue

  hits=$(grep -nEI "$PATTERNS" -- "$file" 2>/dev/null | grep -vE "$ALLOW" || true)
  if [ -n "$hits" ]; then
    if [ "$status" -eq 0 ]; then
      echo "BLOCKED: credential-shaped strings found in $mode." >&2
      echo >&2
    fi
    while IFS= read -r hit; do
      echo "  $file:$hit" >&2
    done <<< "$hits"
    status=1
  fi
done

if [ "$status" -ne 0 ]; then
  cat >&2 <<'EOF'

Move the value into an environment variable read through app/config.py, and
put a placeholder in backend/.env.example instead.

If this is genuinely a fixture, build it by concatenation the way
backend/tests/conftest.py does, or add the path to the exemptions above.

To bypass once (you should not need to):  git commit --no-verify
EOF
else
  echo "check-secrets: clean ($(echo "$files" | grep -c . ) $mode scanned)"
fi

exit "$status"
