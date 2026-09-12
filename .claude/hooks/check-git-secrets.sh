#!/usr/bin/env bash
# PreToolUse guard for Bash: block `git add`/`git commit` from staging/committing
# .env* (secrets) or staging/photos dirs (local document images) on a public repo.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[[ -z "$cmd" ]] && exit 0

echo "$cmd" | grep -Eq '(^|[;&|]|[[:space:]])git[[:space:]]+(add|commit)([[:space:]]|$)' || exit 0

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$repo_root" || exit 0

candidates=()

if echo "$cmd" | grep -Eq '(^|[;&|]|[[:space:]])git[[:space:]]+add([[:space:]]|$)'; then
  add_args=$(echo "$cmd" | sed -n 's/.*git add \(.*\)/\1/p')
  if echo "$add_args" | grep -Eq -- '(^|[[:space:]])(-A|--all|\.)([[:space:]]|$)'; then
    while IFS= read -r f; do [[ -n "$f" ]] && candidates+=("$f"); done < <(git status --porcelain --untracked-files=normal 2>/dev/null | awk '{print $2}')
  else
    for tok in $add_args; do
      [[ "$tok" == -* ]] && continue
      candidates+=("$tok")
    done
  fi
fi

if echo "$cmd" | grep -Eq '(^|[;&|]|[[:space:]])git[[:space:]]+commit([[:space:]]|$)'; then
  while IFS= read -r f; do [[ -n "$f" ]] && candidates+=("$f"); done < <(git diff --cached --name-only 2>/dev/null)
  if echo "$cmd" | grep -Eq -- '[[:space:]]git[[:space:]]+commit[[:space:]]+.*-[a-zA-Z]*a'; then
    while IFS= read -r f; do [[ -n "$f" ]] && candidates+=("$f"); done < <(git diff --name-only 2>/dev/null)
  fi
fi

matches=()
for f in "${candidates[@]:-}"; do
  [[ -z "$f" ]] && continue
  base=$(basename -- "$f")
  if [[ "$base" == .env* && "$base" != ".env.example" ]]; then
    matches+=("$f")
    continue
  fi
  if echo "$f" | grep -Eiq '(^|/)(staging|photos)(/|$)'; then
    matches+=("$f")
  fi
done

if [[ ${#matches[@]} -gt 0 ]]; then
  list=$(printf '%s, ' "${matches[@]}")
  list=${list%, }
  reason="Blocked: this command would stage/commit protected paths ($list) — secrets (.env) or local document images (staging/photos dirs) must not land in git history on a public repo (github.com/ashishp03/retrace)."
  jq -n --arg reason "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
fi
exit 0
