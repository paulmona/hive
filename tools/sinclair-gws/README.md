# sinclair-gws

Sinclair's Google Workspace **write** layer. An MCP server, run as the `sinclair` user,
whose tool signatures make three observed failures unrepresentable:

- replies sent as the wrong identity: `draft_reply` derives the sender from the mailbox that holds the thread and has no identity parameter
- bare `From:` addresses: every From header comes from the identity map in `config.py`, never from an argument
- a reviewed draft discarded for a fresh compose: `send_draft(draft_id)` is the only send tool

`gws` stays for reads (the triage sweep). Design: Notion, *Sinclair v1 on thehive - Design*.

## Auth

Service-account domain-wide delegation, the same mechanism as the `gws-as` wrapper this
replaces: one key, a short-lived token minted with `subject=<user>` per identity. The
identity map **is** the allowlist; a third identity is a code change.

    SINCLAIR_GWS_SA_KEY_PATH   path to the SA JSON key (default ~/.config/sinclair-gws/sa.json)

## Run

    uv run --directory tools/sinclair-gws sinclair-gws          # stdio MCP server
    uv run --directory tools/sinclair-gws pytest                # tests, no key needed

Register for an agent:

    claude mcp add -s user sinclair-gws -- uv run --directory ~/src/hive/tools/sinclair-gws sinclair-gws

## Tools

| Tool | Status |
|---|---|
| `whoami` | done (VIE-69) |
| `search`, `read` | done (VIE-70) |
| `draft_reply`, `draft_new` | done (VIE-71) |
| `send_draft` | done (VIE-72) |
| `forward` | done (VIE-73) |
| `freebusy`, `agenda`, `create_event`, `update_event`, `delete_event` | done (VIE-74) |

End to end, the real server over MCP against Google: `uv run --directory tools/sinclair-gws python scripts/e2e.py [--send]` (VIE-75).
