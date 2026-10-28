#!/bin/bash
# PreToolUse guard: Sunday must never announce the absence of a package.
#
# Paul banned "no package" in doorbell announcements on 2026-10-17. Sunday
# relapsed on 10-18 and four times on 10-27 despite the rule being in her
# prompt and her memory, so this enforces it outside her control.
# Scope: what she says aloud (ha/tts/speak) and what she posts to Discord.
#
# Fails OPEN on any internal error: a broken hook must cost enforcement,
# never Sunday's ability to speak.
set -uo pipefail

IN=$(cat)
TOOL=$(jq -r '.tool_name // ""' <<<"$IN" 2>/dev/null) || exit 0

case "$TOOL" in
  mcp__mqtt__publish|mcp__mqtt__reply)
    TOPIC=$(jq -r '.tool_input.topic // ""' <<<"$IN" 2>/dev/null) || exit 0
    [[ "$TOPIC" == "ha/tts/speak" ]] || exit 0 ;;
  mcp__plugin_discord_discord__reply|mcp__plugin_discord_discord__edit_message) ;;
  *) exit 0 ;;
esac

BODY=$(jq -r '.tool_input | tostring' <<<"$IN" 2>/dev/null) || exit 0
grep -qiE "\bno (packages?|parcels?|deliver(y|ies)|boxe?s?)\b|\bnothing (was )?delivered\b" <<<"$BODY" || exit 0

jq -n --arg r "Blocked: this message announces that there is NO package or delivery. Paul has banned that. If there is a bag, box or package, announce it. If there is none, say nothing about packages at all: delete that part and send the rest. This check is enforced outside your control; rewording the same idea will not get past Paul." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
exit 0
