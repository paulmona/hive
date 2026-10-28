#!/bin/bash
# PreToolUse budget enforcement for Oddjob's research.
#
# Why this exists. The budget in his CLAUDE.md is per-agent, but the spend is
# aggregate. Measured 2026-09-05 from his own transcripts: one request fanned out
# to 27 subagents and cost 683 searches / 1477 fetches against a stated budget of
# 10/25. Every subagent was individually "within budget". Prose cannot fix that.
#
# The key fact, verified by experiment on 2026-09-05 rather than assumed: a
# subagent's PreToolUse payload carries the PARENT's prompt_id. So prompt_id
# identifies one inbound request across the parent and every subagent beneath it,
# and keying the ledger on it gives an exact per-request budget that resets by
# itself and that fan-out cannot multiply. (An earlier draft used a rolling time
# window because I had assumed subagents got their own prompt_id. They do not.)
#
# Fails OPEN on any internal error. A broken hook must never stop the agent
# working; it should cost us enforcement, never availability.
set -uo pipefail

DIR=/home/oddjob/.cache/research-budget
LEDGER="$DIR/ledger"
LOG="$DIR/hook.log"
MAX_SEARCH=${BUDGET_MAX_SEARCH:-30}
MAX_FETCH=${BUDGET_MAX_FETCH:-60}
MAX_AGENT=${BUDGET_MAX_AGENT:-4}
RETAIN=${BUDGET_RETAIN:-86400}     # prune ledger rows older than this
OBSERVE=$(cat "$DIR/observe-only" 2>/dev/null || echo 0)

mkdir -p "$DIR" 2>/dev/null
IN=$(cat)

TOOL=$( jq -r '.tool_name        // ""'       <<<"$IN" 2>/dev/null) || exit 0
CMD=$(  jq -r '.tool_input.command // ""'     <<<"$IN" 2>/dev/null)
ATYPE=$(jq -r '.agent_type       // "main"'   <<<"$IN" 2>/dev/null)
PROMPT=$(jq -r '.prompt_id       // "none"'   <<<"$IN" 2>/dev/null)

case "$TOOL" in
  WebSearch)  KIND=search ;;
  WebFetch)   KIND=fetch  ;;
  Task|Agent) KIND=agent  ;;
  Bash)       [[ "$CMD" == *curl_chrome* ]] && KIND=fetch || exit 0 ;;
  *)          exit 0 ;;
esac

NOW=$(date +%s)
# Hold the lock across prune, count and append. Parallel subagents are exactly
# the population this constrains, so a read/write race here would undercount the
# only case that matters.
exec 9>"$DIR/.lock" 2>/dev/null || exit 0
flock -w 5 9 2>/dev/null || exit 0

[[ -f "$LEDGER" ]] || : > "$LEDGER"
awk -v cut=$((NOW-RETAIN)) '$1 >= cut' "$LEDGER" > "$LEDGER.tmp" 2>/dev/null && mv "$LEDGER.tmp" "$LEDGER"

# Count only this request. Field 3 is the prompt_id shared by parent + subagents.
count() { awk -v k="$1" -v p="$PROMPT" '$2==k && $3==p' "$LEDGER" 2>/dev/null | wc -l; }
S=$(count search); F=$(count fetch); A=$(count agent)

echo "$(date -Is) tool=$TOOL kind=$KIND agent=$ATYPE prompt=${PROMPT:0:8} req_counts=s${S}/f${F}/a${A} observe=$OBSERVE" >> "$LOG"

OVER=""
case "$KIND" in
  search) (( S >= MAX_SEARCH )) && OVER="Search budget spent for this request: ${S}/${MAX_SEARCH} web searches, counted across you and every subagent you started." ;;
  fetch)  (( F >= MAX_FETCH ))  && OVER="Fetch budget spent for this request: ${F}/${MAX_FETCH} page fetches, counted across you and every subagent you started." ;;
  agent)  (( A >= MAX_AGENT ))  && OVER="Subagent limit reached for this request: ${A}/${MAX_AGENT}. Do the rest yourself, or deliver what you have." ;;
esac

if [[ -n "$OVER" && "$OBSERVE" != "1" ]]; then
  echo "$(date -Is) DENIED $KIND prompt=${PROMPT:0:8}" >> "$LOG"
  jq -n --arg r "${OVER}

This limit is enforced outside your control. You cannot raise it and retrying will not work. Deliver now: publish the Notion page with Status \"Partial\", state plainly what you did not get to, and ask over MQTT whether to continue with a bigger budget. A good brief that arrives is worth more than a perfect one that does not." \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
fi

echo "$NOW $KIND $PROMPT $ATYPE" >> "$LEDGER"
exit 0
