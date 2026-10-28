# systemd

Root-owned unit configuration for the hive VM. Unlike `agents/`, nothing pulls
these automatically: `tools/hive-config-pull` runs unprivileged and only touches
`~/.claude`. These files are here so a rebuilt host is reproducible from the
repo rather than from memory, and so changes to them get the same PR review as
the agent instructions.

Installing is manual and needs root.

## `hive-friday.service.d/sudo.conf`

Lets `sudo` actually elevate inside the `hive-friday` unit.

`hive-friday.service` sets `NoNewPrivileges=true`. systemd applies that to the
service and every process below it, and it is a one-way flag: a child cannot
clear it. It disables the setuid bit, so `sudo` still runs and still passes the
sudoers check, but never reaches uid 0.

That means granting sudo takes two independent changes, and it is easy to make
only the first:

1. `/etc/sudoers.d/friday` (not in this repo, it grants privilege and belongs in
   the host's own configuration)
2. this drop-in

Friday is also in the `systemd-journal` group (`sudo usermod -aG systemd-journal
friday`, Paul, 2026-10-27), so it reads any unit's journal without sudo. The one
privileged action it may take without a prompt is `tools/sinclair-restart`,
allowed by exact path in `agents/friday/settings.json`; every other `sudo`
still asks.

Install:

    sudo install -m 0644 -D systemd/hive-friday.service.d/sudo.conf \
      /etc/systemd/system/hive-friday.service.d/sudo.conf
    sudo systemctl daemon-reload
    sudo systemctl restart hive-friday

`daemon-reload` alone is not enough. The running unit keeps the old value until
it is restarted, so the flag only takes effect on the next start.

Verify against the running unit, not the file on disk:

    systemctl show hive-friday -p NoNewPrivileges -p DropInPaths
    sudo id

Expect `NoNewPrivileges=no` and `uid=0(root)`. A clean exit from `sudo -n true`
is not sufficient evidence; check that the uid is actually 0.

### Why this is here

Friday administers this host: installing packages, managing units and timers,
and owning the `/srv/hive-memory` vault work. That needs real root, so the
confinement `NoNewPrivileges` provided has been traded away knowingly rather
than by accident.

What remains as a control is the permission prompt: `Bash(sudo *)` sits in
`permissions.ask` in the agent's `settings.json`, so every sudo invocation is
shown to Paul and needs his approval before it runs. That is an agent-level
control, not a kernel-level one, and it is the only thing standing between the
sudoers grant and unrestricted root.

## `hive-friday.service.d/vault-cwd.conf`

Starts Friday with her working directory inside her memory vault,
`/srv/hive-memory/friday`. obsidian-second-brain's SessionStart hook only injects
the vault manual for sessions started inside the vault, so this is what makes
the product run as designed rather than in a degraded "read `_CLAUDE.md` by
hand" mode. Install like `sudo.conf`; a service restart is required, and unlike
`sudo.conf` this one changes runtime behaviour.

## `hive-memory-sync.service`, `hive-memory-housekeeping.{service,timer}`

The shared agent memory vault at `/srv/hive-memory`: an Obsidian Sync client and
a once-a-minute job that hands each agent's folder back to it and commits the
vault to local git history.

Install these with `tools/hive-memory-setup` rather than by hand; it also creates
the vault, the per-agent folders and the history repo, which the units assume
already exist. Full runbook in `tools/MEMORY-INSTALL.md`.

## `hive-vault-nightly@.{service,timer}`, `hive-vault-health@.{service,timer}`

obsidian-second-brain ships four "scheduled agents" as prompts for Claude
Code's `/schedule`. That mechanism runs in Anthropic's cloud and cannot see
`/srv/hive-memory`, so on this host two of them run as systemd timers instead,
using the product's documented headless recipe (`claude -p` fed the prompt on
stdin). The prompts in `tools/vault-jobs/` are the product's wording; the
health prompt additionally counts open conflict notes so the weekly human
review knows whether `/obsidian-reconcile` is due.

| Timer | When (Eastern) | Job |
|---|---|---|
| `hive-vault-nightly@<agent>.timer` | daily 03:30, up to 15 min late | close the day that just ended, flag contradictions (never resolves them), synthesize, heal links, rebuild `index.md` |
| `hive-vault-health@<agent>.timer` | Monday 04:30, up to 15 min late | `vault_health.py --json` into `Knowledge/Vault Health YYYY-MM-DD.md`, report only |

The product's defaults are 22:00 and Sunday 21:00. 03:30 is after Paul has
actually stopped working with an agent (the nightly writes the day's End of
Day summary, so running it mid-evening closes the day early), and the nightly's
`TODAY` is therefore the previous calendar date. Monday 04:30 puts the weekly
report ahead of Sunday's morning briefing.

After either job, `tools/vault-jobs/publish_status.py` publishes a retained
JSON status to `hive/status/vault-health/<agent>` (job, date, ok, note and
issue counts by severity, open `type: conflict` notes, report path). Sunday
watches `hive/status/vault-health/+` and her morning-briefing skill reads the
latest per agent; she cannot read the other vaults directly, the folders are
0700. Retained means she gets the latest even after a restart. The publish
uses the agent's own MQTT channel credentials and a publish failure is logged
but does not fail the job.

`morning` is not installed (Sunday owns the morning briefing) and `weekly` is
not yet (decide once the nightly has run for a while).

The service templates run as the agent user, in its vault, with
`OBSIDIAN_VAULT_PATH`, `HOME` and `PATH` set explicitly. The job uses the
agent's own Claude login, so an expired OAuth token fails the job, visibly, in
the journal. No MCP servers are loaded and the tool surface is filesystem plus
Bash (for `uv run`). Each run is a full Claude session; that is the cost to
watch, and `journalctl -u hive-vault-nightly@friday` shows the duration.

Install is part of `tools/hive-memory-setup` (re-run it with the agent names).
Test one without waiting for the clock, then check what is scheduled:

    sudo systemctl start hive-vault-health@friday
    journalctl -u hive-vault-health@friday -n 20
    systemctl list-timers 'hive-vault-*'

## `hive-friday.service`

The unit itself. Forking type: `ExecStart` opens a detached tmux session named
`claude` running `~/start-agent.sh`, which `tools/hive-config-pull` keeps
current from `tools/agent-start`. Memory and CPU limits live here; the drop-ins
above override single values and are hard to read without this file.

Install:

    sudo install -m 0644 systemd/hive-friday.service /etc/systemd/system/hive-friday.service
    sudo systemctl daemon-reload
    sudo systemctl restart hive-friday

## `hive-sunday.service`, `hive-sunday.service.d/vault-cwd.conf`

Sunday's unit, same shape as Friday's. Differences: `NoNewPrivileges=true`
stays in force because Sunday does not administer the host, so there is no
`sudo.conf` and no sudoers entry. Install with `tools/hive-agent-setup sunday`,
which also creates the user and her vault folder.

## Not here on purpose

`/etc/sudoers.d/friday` grants privilege and belongs in the host's own
configuration, not in a repo the agent can open PRs against.
