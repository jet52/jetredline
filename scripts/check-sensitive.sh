#!/usr/bin/env bash
# check-sensitive.sh — scan pushed commits for likely confidential ND-court data.
# Invoked by .githooks/pre-push; bypass with `git push --no-verify`.

set -euo pipefail

ZERO="0000000000000000000000000000000000000000"
errors=0

# Placeholders used in our own docs; do not flag.
PLACEHOLDER_DOCKETS='20990001|20990002|20990003|20990004|20000000|12345678|99999999'
PLACEHOLDER_DC='00-0000-CV-00000'

# Allow repo-local additions: one literal regex per line in .sensitive-check-allow
ALLOW_FILE=".sensitive-check-allow"
allow_grep() {
  if [ -f "$ALLOW_FILE" ]; then
    grep -vE "$(paste -sd '|' "$ALLOW_FILE")" || true
  else
    cat
  fi
}

# Arguments are git-log revision arguments, passed separately: a new ref is
# scanned as `<sha> --not --remotes`, which git rejects if quoted as one word.
# That is how every new branch and tag once went unscanned — git log failed,
# its error was discarded, and an empty diff passed. A git failure now fails
# the push instead.
scan_range() {
  local log
  if ! log=$(git log --format='' -p "$@" -- . ":(exclude)$ALLOW_FILE" 2>&1); then
    echo "[pre-push] could not read the commits being pushed ($*):"
    echo "$log" | sed 's/^/  /'
    errors=$((errors+1))
    return
  fi

  # Added lines only (diff +...), excluding the allow file itself: it is the
  # rulebook, so every pattern it lists reads as a hit against its own rules
  # and a new exemption can never be pushed.
  local added
  added=$(echo "$log" | grep -E '^\+' || true)

  # 1. ND Supreme Court docket 2000-2026 series
  local sc_hits
  sc_hits=$(echo "$added" \
    | grep -oE '(^|[^0-9])20(0[0-9]|1[0-9]|2[0-6])[0-9]{4}([^0-9]|$)' \
    | grep -oE '20[0-9]{6}' \
    | grep -vE "^($PLACEHOLDER_DOCKETS)$" \
    | allow_grep | sort -u || true)
  if [ -n "$sc_hits" ]; then
    echo "[pre-push] possible real Supreme Court docket(s):"
    echo "$sc_hits" | sed 's/^/  /'
    errors=$((errors+1))
  fi

  # 2. ND district-court docket NN-YYYY-XX-NNNNN
  local dc_hits
  dc_hits=$(echo "$added" \
    | grep -oE '(^|[^0-9-])[0-9]{1,2}-20(0[0-9]|1[0-9]|2[0-6])-[A-Z]{2}-[0-9]{1,5}([^0-9]|$)' \
    | grep -oE '[0-9]{1,2}-20[0-9]{2}-[A-Z]{2}-[0-9]{1,5}' \
    | grep -vE "^$PLACEHOLDER_DC\$" \
    | allow_grep | sort -u || true)
  if [ -n "$dc_hits" ]; then
    echo "[pre-push] possible real district-court docket(s):"
    echo "$dc_hits" | sed 's/^/  /'
    errors=$((errors+1))
  fi

  # 3. Confidential-case captions
  local cap_hits
  cap_hits=$(echo "$added" \
    | grep -iE 'Adoption[- ]of[- ][A-Z]{2,5}\b|\bIn re [A-Z]{2,5}\b|Interest of [A-Z]\.|Termination[- ]of[- ]Parental' \
    | grep -vE 'Example|Sample|Placeholder' \
    | allow_grep | head -5 || true)
  if [ -n "$cap_hits" ]; then
    echo "[pre-push] possible confidential-case caption(s):"
    echo "$cap_hits" | sed 's/^/  /'
    errors=$((errors+1))
  fi

  # 4. Binary documents being added
  local bins
  bins=$(git log --format='' --diff-filter=A --name-only "$@" \
    | grep -iE '\.(pdf|docx|doc|rtf|xlsx|pptx)$' \
    | allow_grep || true)
  if [ -n "$bins" ]; then
    echo "[pre-push] binary document(s) being added:"
    echo "$bins" | sed 's/^/  /'
    errors=$((errors+1))
  fi
}

while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "$ZERO" ] && continue  # branch deletion
  if [ "$remote_sha" = "$ZERO" ]; then
    # New branch or tag: scan local commits not reachable from any existing remote
    scan_range "$local_sha" --not --remotes
  else
    scan_range "$remote_sha..$local_sha"
  fi
done

if [ $errors -gt 0 ]; then
  echo
  echo "[pre-push] $errors sensitive-content check(s) failed."
  echo "[pre-push] Review above, or bypass once with: git push --no-verify"
  exit 1
fi
