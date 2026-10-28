#!/bin/bash
# UserPromptSubmit hook. Whatever this prints is injected into context right
# after the user's message, on every turn.
#
# Why a hook and not another CLAUDE.md line: Anthropic's Opus 5 prompting guide
# says visible response length does not respond to effort, only to prompting,
# and pairs the conciseness rule with a short reminder placed near the END of
# the prompt. CLAUDE.md is a user message that sits far from the end of a long
# context. This puts the reminder at the end, every time. About 30 tokens a turn.
cat <<'EOF'
<tone_preference>
Keep this reply concise: lead with the answer, drop anything that does not change what Paul does next, and mention a correction only if it changes his conclusions.
</tone_preference>
EOF
