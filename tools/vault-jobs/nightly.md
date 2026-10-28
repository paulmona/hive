Read _CLAUDE.md. This is a sleeptime consolidation pass - the vault should be smarter when the user wakes up.

Phase 1 - Close the day:
- Read today's daily note. Append a ## End of Day section with a 3-5 bullet summary.
  If the note already has an End of Day section (the agent may have closed the day itself), leave it and do not add a second.
- Move any completed kanban tasks to Done.

Phase 2 - Reconcile:
- First resolve the entities, concepts, and decisions folders per references/folder-map.md: the vault's _CLAUDE.md Folder Map wins,
  else wiki-style wiki/entities/ + wiki/concepts/ + wiki/decisions/, else Obsidian-style People/ + Knowledge/ (and Ideas/) + Knowledge/.
  A resolved folder that does not exist is a skip, not an error. Never scan a hardcoded wiki/ path on a vault with no wiki/ folder -
  unattended, that is three tool failures a night with nothing to show for them.
- Scan the entities folder for outdated roles, companies, or descriptions that conflict with newer daily notes.
- Scan the concepts folder for claims contradicted by recently ingested sources.
- Flag EVERY contradiction as a `type: conflict` note with `status: open` in the decisions folder. Do NOT rewrite any existing page.
  (Resolving a contradiction means rewriting the outdated note, which is destructive and irreversible while the user sleeps. It also
  contradicts the constraint below. Leave the resolve step to an interactive /obsidian-reconcile run, matching the health agent's
  report-only posture.)

Phase 3 - Synthesize:
- Scan sources ingested today and yesterday. Find concepts that appear in 2+ unrelated sources.
- If patterns found: create `Synthesis - Title.md` in the concepts folder resolved in Phase 2, with evidence and interpretation.

Phase 4 - Heal:
- Find notes created today with no incoming links. Add links from relevant existing pages.
- Check if any entity pages reference old timeline entries without an "until" date that should be closed.
- Rebuild index.md to reflect today's changes.

Phase 5 - Log:
- Append an operation-log entry: if `Logs/` exists write `**HH:MM** - nightly | End of day + X flagged, Y synthesized, Z orphans linked` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] nightly | ...` to `log.md`

Do not ask questions. Do not fix anything destructive - only add, update, link. Save and stop.
