# Installing the config pull path

No root required. Everything runs as the agent's own user.

## 1. Read credential

The pull reads a GitHub token from Vault at `hive/agents/<name>`, key
`_GITHUB_PAT`. The leading underscore keeps it out of `~/.claude/.env`, so it
is never exported into the agent's environment or inherited by MCP child
processes; the script reads it from Vault on each run instead.

A read-only fine-grained token scoped to this repository is sufficient for
every agent except Friday, whose token is read and write so she can open PRs
against this repo (see README, Read credential).

## 2. First pull, by hand

    ~/src/hive/tools/hive-config-pull friday

Expect a clone, then `installed ~/.claude/CLAUDE.md` and the agents file.

## 3. Wire it into startup

The pull is called from `~/refresh-from-vault.sh`, which the pull itself
installs (see below). On a fresh host, copy the three startup scripts into place
once by hand so the first boot has something to run:

    install -m 700 tools/agent-start          ~/start-agent.sh
    install -m 700 tools/refresh-from-vault   ~/refresh-from-vault.sh
    install -m 700 tools/dev-channels-watcher ~/dev-channels-watcher.sh

From then on every start refreshes them from git.

## 4. Clean up, after a restart confirms the agent is healthy

Delete `CLAUDE_MD` and `AGENT_MD` from `hive/agents/<name>`, then revoke the
migration PAT and remove `_GITHUB_PAT`.

## What gets installed

Per agent, from `agents/<name>/`:

| Repo file | Installed to | Mode |
|---|---|---|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | 600 |
| `AGENT.md` | `~/.claude/agents/<name>.md` | 600 |
| `settings.json` | `~/.claude/settings.json` | 600 |
| `skills/<skill>/*` | `~/.claude/skills/<skill>/` | 644 |

Skills in `~/.claude/skills` that are not in the repo are left alone; the
obsidian-second-brain product installs some of its own there.

Generic, from `tools/`, parameterised by the unix user (the agent name):

| Repo file | Installed to | Mode |
|---|---|---|
| `agent-start` | `~/start-agent.sh` | 700 |
| `refresh-from-vault` | `~/refresh-from-vault.sh` | 700 |
| `dev-channels-watcher` | `~/dev-channels-watcher.sh` | 700 |

The names under `~` are fixed because the systemd unit's `ExecStart` points at
`~/start-agent.sh`. A change to any of these takes effect on the restart after
the one that pulled it: the running start script is the old one, the pull
replaces the file by rename, and the next start runs the new one.

`settings.json` is a full overwrite, like `CLAUDE.md`. Anything changed through
`/config` or by the CLI at runtime lasts until the next restart; make the change
in the repo instead.

## Checking the log

Every run logs to stdout and to syslog under the tag `hive-config-pull`. The
syslog copy is written by the agent's own uid, so the agent can read its own
pull history back without belonging to `adm` or `systemd-journal`:

    journalctl -t hive-config-pull -n 20
    journalctl -t hive-config-pull -p err --since -1d

Messages are prefixed with the agent name, so one tag covers every agent on the
host. Rotation is handled by journald and logrotate; the script writes no files
of its own.

## How this is secured

Git is the durable source of truth and reaching `main` requires a reviewed PR.
The pull is `reset --hard`, an unconditional overwrite, so a local edit to
`~/.claude/CLAUDE.md` survives only until the next restart and cannot block the
pull with a conflict. File ownership is deliberately not used as a boundary:
`~/.claude` is owned by the agent, and replacing a file there needs write
permission on the directory rather than on the file, so a root-owned config
file would offer no protection.

A failed fetch or clone leaves the existing config in place and exits 0. A
GitHub outage must not stop an agent from starting.

## Rollback

`archive/pre-migration` holds the pre-migration repo state, and Vault KV keeps
version history of `CLAUDE_MD`. To fall back, restore the Vault keys and put
the two `jq` lines back in `refresh-from-vault.sh`.

## Adding an agent to the host (Sunday, 2026-09)

Root part, once:

    sudo tools/hive-agent-setup sunday

That creates the user, installs the startup scripts and the unit, enables it
without starting it, and creates `/srv/hive-memory/sunday`.

Paul's part: create the Vault AppRole for `sunday` with read on
`hive/agents/sunday` and `hive/shared`, and write `role_id` and `secret_id`
into `/home/sunday/.vault-creds/`. Add `_GITHUB_PAT` (read-only, this repo) to
`hive/agents/sunday`. Her existing keys (`DISCORD_BOT_TOKEN`, `HA_URL`,
`HA_TOKEN`, MQTT credentials) stay where they are.

As `sunday` (`sudo -iu sunday`), once:

    curl -fsSL https://claude.ai/install.sh | bash
    ~/.local/bin/claude login                     # or /login inside tmux later
    ~/refresh-from-vault.sh                       # first pull: clone + install
    ~/.local/bin/claude plugin install discord@claude-plugins-official
    ~/.local/bin/claude mcp add -s user mqtt -- bun /opt/claude-code-mqtt/server.ts
    ~/.local/bin/claude mcp add -s user ha-voice -- node /opt/ha-voice/ha-voice.js

`ha-voice` reads `HA_URL`, `HA_TOKEN` and `HA_VOICE_PORT` from the environment
`start-agent.sh` exports, so no `-e` flags. Its source is `paulmona/thehive`
(`ha-voice/`); install it once as root to `/opt/ha-voice` with `npm ci`, next
to `/opt/claude-code-mqtt`.

Discord channel state (`~/.claude/channels/discord/access.json`, the allowlist)
is restored from the Unraid backup, not generated.

First start is without channels. Paul stops the Unraid container first; the two
must never run at once (same Discord bot, same MQTT session). Then:

    sudo systemctl set-environment HIVE_NO_CHANNELS=1   # or a drop-in Environment= line
    sudo systemctl start hive-sunday

Attach with `tmux attach -t claude` as `sunday` for the first-run prompts and
work through the verification list in the migration plan. When the basics hold,
clear the variable and restart to bring up Discord, MQTT and voice:

    sudo systemctl unset-environment HIVE_NO_CHANNELS
    sudo systemctl restart hive-sunday

Rollback at any point: `systemctl stop hive-sunday`, then `docker start
hive-sunday` on Unraid.

## Adding an agent to the host (Oddjob, 2026-09)

Same shape as Sunday, with a browser bolted on. Oddjob is MQTT-only: no
Discord, no voice, no `ha-voice`.

Root part, once:

    sudo tools/hive-agent-setup oddjob
    sudo tools/hive-chrome-setup /home/friday/src/thehive

`hive-chrome-setup` installs Chrome, Xvfb, curl-impersonate, the Playwright
library (no bundled browser) and the `chrome-start` / `chrome-challenge.js`
helpers, then verifies each one. It does not start Chrome; the agent does that
on demand.

Paul's part: create the Vault AppRole for `oddjob` with read on
`hive/agents/oddjob` and `hive/shared`, write `role_id` and `secret_id` into
`/home/oddjob/.vault-creds/`, and add `_GITHUB_PAT` (read-only, this repo) to
`hive/agents/oddjob`. Add the PAT only after the Unraid container is stopped:
the old entrypoint exports every key in the path into the container's
environment, leading underscore or not.

As `oddjob` (`sudo -iu oddjob`), once:

    curl -fsSL https://claude.ai/install.sh | bash
    ~/.local/bin/claude login
    ~/refresh-from-vault.sh
    ~/.local/bin/claude mcp add -s user mqtt -- bun /opt/claude-code-mqtt/server.ts

No `sunday-memory` MCP server. It is retired, and his memory is the vault at
`/srv/hive-memory/oddjob`. Notion reaches him as a claude.ai account connector,
not a local MCP server, so it follows the login and needs nothing here.

The Chrome profile is restored from the Unraid backup, not generated:

    sudo -u oddjob tar -xzf <backup> -C /home/oddjob ./chrome-profile
    sudo -u oddjob rm -f /home/oddjob/chrome-profile/Singleton{Lock,Cookie,Socket}

Those `Singleton*` entries are a symlink named `<hostname>-<pid>` from the
container. `chrome-start` clears a stale one on its own, but removing them at
restore time keeps the first start boring. The profile carries Paul's live
logged-in sessions; treat it as the payload of this migration, not as a cache.

First start is without channels, after Paul stops the Unraid container:

    sudo systemctl set-environment HIVE_NO_CHANNELS=1
    sudo systemctl start hive-oddjob

Verify in this order, because each step depends on the last: `/context` shows
CLAUDE.md and the Oddjob agent; the vault MCP answers; `chrome-start` prints
CDP version JSON; a Playwright `connectOverCDP` reaches a logged-in page on one
of the sites in the restored profile. Then bring up MQTT:

    sudo systemctl unset-environment HIVE_NO_CHANNELS
    sudo systemctl restart hive-oddjob

Acceptance is a real research task sent from Sunday over MQTT that lands as a
Notion page.

Rollback at any point: `systemctl stop hive-oddjob`, then `docker start
hive-oddjob` on Unraid.
