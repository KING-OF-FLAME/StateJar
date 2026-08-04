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
#
# WHAT THIS FILE GOT WRONG, and why it is longer now.
# It used to skip `backend/tests/*` entirely, reasoning that the tree holds
# fixtures. GitGuardian then found two secrets in a new test file on a PR while
# this script reported "clean" on the same tree. The directory skip was the bug:
# a real `sk-or-v1-` key staged under backend/tests/ was demonstrated to pass.
# A scanner that reports clean on a tree that has findings is worse than no
# scanner, because it manufactures confidence exactly when someone is relying on
# it. The test tree is scanned now; known-inert fixtures are allowlisted by
# value instead of by location.

set -uo pipefail

# Each prefix must be followed by a real run of key characters. Matching a bare
# "sk-or-" would flag every masked example in the docs ("sk-or-••••…1234"), and
# a hook that cries wolf gets bypassed.
#
# Detector classes. The generic-password and generic-secret rows are here
# because GitGuardian caught a class this script had no pattern for at all:
#   provider keys     sk-, AIza, ghp_/gho_/…, github_pat_, xox[baprs]-, AKIA
#   private keys      PEM headers, any flavour
#   our own env vars  JWT_SECRET=, AES_KEY=
#   generic password  "password": "..."          <- the class that was missed
#   generic secret    api_key / token / secret assignments
#   credentialled URL  scheme://user:password@host
PATTERNS='sk-[A-Za-z0-9_-]{16,}'
PATTERNS="$PATTERNS"'|AIza[0-9A-Za-z_-]{16,}'
PATTERNS="$PATTERNS"'|(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}'
PATTERNS="$PATTERNS"'|github_pat_[A-Za-z0-9_]{20,}'
PATTERNS="$PATTERNS"'|xox[baprs]-[A-Za-z0-9-]{10,}'
PATTERNS="$PATTERNS"'|AKIA[0-9A-Z]{16}'
PATTERNS="$PATTERNS"'|-----BEGIN [A-Z ]*PRIVATE KEY-----'
PATTERNS="$PATTERNS"'|(JWT_SECRET|AES_KEY)=[^[:space:]"'"'"'#]{12,}'
PATTERNS="$PATTERNS"'|"password"[[:space:]]*:[[:space:]]*"[^"]{6,}"'
PATTERNS="$PATTERNS"'|(api_key|apikey|secret|token|passwd|password)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{12,}["'"'"']'
PATTERNS="$PATTERNS"'|://[^/[:space:]:]+:[^/[:space:]@]{6,}@'

# Values that must never trip the hook. Two kinds, kept apart on purpose:
#
#   placeholders  nothing was ever secret about them.
#   known inert   a real-looking value that authenticates against nothing. Each
#                 is listed individually and mirrored in .gitguardian.yaml.
#                 Never a path and never a directory — the point of this rewrite
#                 is that "it lives in tests/" stopped being an excuse.
ALLOW='replace-with-a-long-random-secret|change-me|your-|example|placeholder'
ALLOW="$ALLOW"'|not-a-real-key|on purpose|PATTERNS=|ALLOW=|<REDACTED'
# EVERY allowlisted value below is split across a '' seam so that this file
# never contains the literal it is exempting. The first version of this list
# spelled them out, and GitGuardian promptly reported the same incident twice
# more -- against this file. An allowlist that restates the value it excuses
# is a second copy of it. The seam costs nothing: bash concatenates adjacent
# quoted strings, so the pattern is identical at runtime and absent at rest.
# It is the same trick conftest.py::fake_key() and test_audit.py already use.
#
# fixture account password: in-memory SQLite only (see .gitguardian.yaml)
ALLOW="$ALLOW"'|s3cret''pass'
# audit-scrubber negative fixture, assembled at runtime so it is never a literal
ALLOW="$ALLOW"'|"sk''-" \+ "ant-'
# masked display formats in the docs, and the provider-card input placeholders
ALLOW="$ALLOW"'|sk-or-v1-…|AIza…|••••'
# negative-test fixtures: each is a value its test asserts is REJECTED, so it
# authenticates against nothing by construction.
ALLOW="$ALLOW"'|secret="att''acker-'     # JWT signed with the wrong secret
ALLOW="$ALLOW"'|wrong''pass1'             # login expected to fail
ALLOW="$ALLOW"'|bad key sk''-'            # mocked upstream 401 body
# variable references, not literals: Railway and GitHub Actions substitute
# these at deploy time, so the credential is never in the file.
ALLOW="$ALLOW"'|\$\{\{'

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
    # Only two exemptions remain, and neither is a source directory:
    # .env.example exists to hold placeholders, and these two files are the
    # pattern lists themselves.
    *.env.example|*/.env.example) continue ;;
    .gitguardian.yaml|scripts/check-secrets.sh) continue ;;
  esac
  [ -f "$file" ] || continue

  hits=$(grep -nEI "$PATTERNS" -- "$file" 2>/dev/null | grep -vE "$ALLOW" || true)
  if [ -n "$hits" ]; then
    if [ "$status" -eq 0 ]; then
      echo "BLOCKED: credential-shaped strings found in $mode." >&2
      echo >&2
    fi
    while IFS= read -r hit; do
      # report the location, never the match: a CI log is not a safe place to
      # reprint the thing we are objecting to
      echo "  $file:${hit%%:*}: credential-shaped string (value withheld)" >&2
    done <<< "$hits"
    status=1
  fi
done

if [ "$status" -ne 0 ]; then
  cat >&2 <<'EOF'

Move the value into an environment variable read through app/config.py, and
put a placeholder in backend/.env.example instead.

If this is genuinely a fixture, build it by concatenation the way
backend/tests/conftest.py does — a fixture that is not key-shaped needs no
exemption at all. If it must stay a literal, add that one value to ALLOW above
AND to .gitguardian.yaml, with a comment saying what it authenticates against.
Do not add a path: a directory exemption is how the test tree went unscanned.

To bypass once (you should not need to):  git commit --no-verify
EOF
else
  echo "check-secrets: clean ($(echo "$files" | grep -c . ) $mode scanned)"
fi

exit "$status"
