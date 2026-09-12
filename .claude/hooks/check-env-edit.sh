#!/usr/bin/env bash
# PreToolUse guard for Edit|Write: deny direct edits to .env* files (except .env.example).
# Retrace's .env will hold Nango/Respan/Lambda keys on a repo with a public GitHub remote.
set -euo pipefail

input=$(cat)
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[[ -z "$file" ]] && exit 0

base=$(basename -- "$file")
if [[ "$base" == .env* && "$base" != ".env.example" ]]; then
  reason="$file is a protected secrets file (Nango/Respan/Lambda API keys) on a repo with a public GitHub remote (github.com/ashishp03/retrace). Edit it by hand outside Claude Code, not via Edit/Write."
  jq -n --arg reason "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
fi
exit 0
