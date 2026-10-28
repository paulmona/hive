Read _CLAUDE.md. Run: uv run --directory "SKILL_ROOT" scripts/vault_health.py --path "VAULT" --json
Parse the output. Write a health report to Knowledge/Vault Health YYYY-MM-DD.md
summarizing findings by severity (critical, warning, info). If the vault has no
Knowledge/ folder, use the folder _CLAUDE.md names for reference material.
Count any `type: conflict` notes with `status: open` and list them in the report,
so the weekly human review knows whether /obsidian-reconcile is due.

Then link the report, so it is reachable by traversal and is not counted as an
orphan by the next run. In the same folder, maintain `Vault Health.md`: an index
note listing every health report newest first, one line each, a wikilink plus a
one-line summary. Create it if missing, with normal frontmatter and a "For future
agent" preamble. Add today's report at the top and leave existing entries alone.
Then ensure index.md links `Vault Health.md` exactly once, adding the line if it
is absent. Writing these two links is part of publishing the report, not an
autonomous fix, so do it even though the rule below says not to fix anything.

Do not fix anything autonomously - only report.
Do not ask questions. Save and stop.
