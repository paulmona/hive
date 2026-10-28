# Installing the shared agent memory vault

One Obsidian vault at `/srv/hive-memory`, one folder per agent, synced to Paul's
Mac and phone by Obsidian Sync, with a local git repository keeping permanent
history. Design and rationale are in the TRD, "Agent Memory in Obsidian".

Requires root. Steps 1 and 4 are Paul's because they need his Obsidian account.

## Where this diverges from the TRD

The TRD was written before anyone ran the headless client. Four corrections,
all verified against `obsidian-headless@0.0.14`:

1. **There is no `ob sync run --continuous`.** The real command is
   `ob sync --path <vault> --continuous`. `sync` is a top-level verb and the
   subcommands are hyphenated (`sync-setup`, `sync-config`, `sync-status`).
2. **The git directory lives outside the vault**, at `/var/lib/hive-memory.git`,
   driven by `--git-dir` and `--work-tree`. A `.git` inside the vault would be
   synced to Paul's Mac and phone, and would put the sync client and git's index
   in a race over the same files.
3. **`ob login` accepts `--email` and `--password`**, so the login is scriptable.
   It also accepts `--mfa`, but a code that has to be typed defeats unattended
   restarts, so the hive account must not have 2FA enabled.
4. **The agent `CLAUDE.md` change is not part of this step.** Pointing an agent's
   memory at files that do not exist yet is a gamble: Claude Code's documented
   behaviour for a missing `@` import is not specified anywhere, so it is not
   known whether it degrades quietly or breaks session startup. That change lands
   with the seeding work, once the files are real.

One more thing the TRD assumes that is no longer true: it says "Friday has no
sudo, so those steps are Paul's". Friday has sudo now. Only the Obsidian account
steps genuinely need Paul.

## 1. Paul: account and vault

- Create the hive-only Obsidian account. **Leave 2FA off** (see above).
- Subscribe it to Sync. Collaborators each need their own subscription.
- On Paul's own account, create the vault and invite the hive account.
- Put the credentials in Vault at `hive/agents/friday`. The keys already exist
  with the value `REPLACE_ME`; edit them in place rather than creating new ones:

      _OBSIDIAN_HIVE_EMAIL
      _OBSIDIAN_HIVE_PASSWORD

  Add `_OBSIDIAN_HIVE_ENCRYPTION_PASSWORD` only if the vault is end-to-end
  encrypted.

  **The leading underscore is load-bearing.** `refresh-from-vault.sh` filters out
  keys matching `^_` when it writes `~/.claude/.env`. Without it these would be
  exported into the agent's environment and inherited by every MCP child process,
  which is a poor place for the password to the vault that holds every agent's
  memory. Same reason `_GITHUB_PAT` is spelled that way. Nothing on the agent side
  needs these: the sync client is root's, and it stores its own credentials after
  `ob login`.

  Edit them with `vault kv patch`, never `vault kv put`. `put` replaces the entire
  secret, which would delete the MQTT, Omada, Home Assistant and GitHub keys and
  leave the agent unable to start.

## 2. Run the setup script

    sudo tools/hive-memory-setup friday

Idempotent. Re-run it with more agent names to add folders later. It installs
`obsidian-headless` pinned, creates the vault and each agent's 0700 folder,
initialises the history repo, installs the units, and starts the housekeeping
timer. It deliberately does not start sync: nothing has logged in yet.

## 3. Log in and connect the vault

    sudo -i
    ob login                                   # prompts; or --email/--password
    ob sync-list-remote                        # confirm the vault is visible
    ob sync-setup --path /srv/hive-memory --vault <remote-vault-name>
    ob sync-config --path /srv/hive-memory --conflict-strategy merge
    systemctl enable --now hive-memory-sync.service

Prefer the interactive prompt. Passing `--password` puts the secret in the
process list where any user on the host can read it with `ps`. If it has to be
scripted, feed it on stdin rather than as an argument.

Credentials are stored by the client under `/root/.config/obsidian-headless`.
That is why `hive-memory-sync.service` sets `HOME=/root` explicitly: systemd does
not set `HOME` for system services, and without it the client looks in `/` and
behaves as though it were never logged in.

## 4. Check it

    systemctl status hive-memory-sync.service
    systemctl list-timers hive-memory-housekeeping.timer
    sudo -i ob sync-status --path /srv/hive-memory
    sudo journalctl -t hive-memory-housekeeping -n 20
    sudo git --git-dir=/var/lib/hive-memory.git --work-tree=/srv/hive-memory log --oneline

Those last three need root, and not only for file access. Housekeeping logs to
syslog as root, so unlike `hive-config-pull` (which runs as the agent and is
readable by it) an agent cannot read its own housekeeping history without being
in `adm` or `systemd-journal`. `ob` needs root's `HOME` to find its credentials.

Then the TRD's acceptance tests: a fact written by an agent reaching the Mac, an
edit on the Mac reaching the agent, a simultaneous edit merging, sync surviving a
stop and start, one agent failing to read another's folder, and sync resuming
after a reboot with nobody logging in.

## How the pieces behave

**Ownership.** Sync runs as root and writes as root. The housekeeping timer hands
each agent's folder back every minute. Between a sync write and the next timer
run, a pulled file is root-owned: the agent can read it and can delete or replace
it (it owns the directory) but cannot edit it in place. One minute is the agreed
upper bound on that window.

Folders whose name does not match a real user are left alone, so a folder Paul
creates in Obsidian is never handed to an agent.

**History.** The timer commits only when something changed, so an idle vault
produces no commits. `.obsidian/workspace.json` and friends are excluded, because
they change constantly and would otherwise generate a commit every minute.

**Privacy.** `/srv/hive-memory` is 0755 root-owned so agents can traverse into
their own folder; each agent folder is 0700 owned by that agent. Friday cannot
read Sunday's memory because the filesystem refuses, not because Friday is asked
not to.

## When it breaks

| Symptom | Cause |
|---|---|
| `hive-memory-sync` restart-loops | Not logged in, or `sync-setup` never run. Check `ob sync-status`. |
| Client behaves as logged out under systemd but fine by hand | `HOME` missing from the unit. |
| Agent cannot write a file it can see | Housekeeping has not run since sync pulled it. Wait a minute, or check the timer. |
| A commit every minute, no real changes | Something churning is not in `/var/lib/hive-memory.git/info/exclude`. |
| `dubious ownership` from git | The system-wide `safe.directory` entry the setup script adds is missing. |

The headless client is an open beta and is not open source (`UNLICENSED` on npm).
If it proves unreliable, the fallback is the v1 git design, kept in the TRD's
page history.
