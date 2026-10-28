---
name: process-meeting
description: Process meeting recordings from Omi into context-aware meeting minutes. Triggered automatically over MQTT when Home Assistant reports a finished Omi conversation, or when Sunday asks ("process my meeting", "minutes for the X call"). Fetches the transcript from Omi, correlates it to Paul's calendar, pulls context from the vault, drafts structured minutes, sends them to Sunday, and writes to Notion only after Paul approves.
---

# Process Meeting

Turns a raw Omi transcript into minutes that know why the meeting happened.

## Prerequisites

- `OMI_API_KEY` in the environment (from Vault)
- `sinclair-gws` for the calendar (`agenda`, `search`)
- Your vault for context (`Contacts/`, `Negotiations/`)
- Notion MCP for the final page (write is tier 2: approval first)

## Triggers

- **Automatic:** an MQTT message with `sender: ha` naming an Omi conversation id and
  title. If no id, fetch the most recent conversation.
- **From Sunday:** "process the AWS meeting", "minutes for yesterday's call". Match by
  title, attendee or time. If ambiguous, list the candidates and ask.

## Workflow

1. **`date`.** Sessions are long-running; know when now is.
2. **Fetch the conversation** (`/v1/dev/user/conversations/<id>?include_transcript=true`,
   or the recent list with `limit=5`). Omi timestamps are UTC; display in Eastern.
3. **Correlate to the calendar.** `agenda("paul", 1)` around the conversation's start and
   end, or `search` for the invite. The event gives the real title, attendees, location
   and any agenda in the description. No match: say "no calendar event found,
   unscheduled conversation" in the minutes.
4. **Pull context from the vault.** Open the `Contacts/` note for each attendee and any
   `Negotiations/` note that names them or the topic. That is the "why". Only what Paul
   has said or what is plainly factual; never an outsider's claims as Paul's view.
5. **Draft the minutes** in this shape:

   ```
   **Meeting Minutes: [Title]**
   Date: [Eastern]   Attendees: [names, roles, companies]   Duration: [from start/end]
   Source: Omi transcript, [N] segments

   **Context:** one or two sentences on why this meeting happened.

   **Key Outcomes:** numbered, concrete: numbers, names, dates, commitments.

   **Action Items:**
   | Action | Owner | Priority | Status |
   Every commitment or follow-up, owner = who said they would, Medium unless urgency was voiced.

   **Connections to Active Work:** only genuine links to open threads, projects, other
   agents' work, upcoming meetings. Do not force any.

   **Notable Quotes:** optional, verbatim, only if something would not survive summary.
   ```

6. **Send to Sunday** for Paul's review. Tier 2. Do not touch Notion yet.
7. **On approval, write the Notion page** where Paul says (default: his Meeting Notes
   section), title `[Date] - [Title]`, all sections.
8. **Offer action items as to-dos** after Paul confirms which ones he wants tracked.
9. **Save what is worth keeping to the vault:** a new contact, a stated decision, a
   deadline, a preference, into `Contacts/` or the relevant `Negotiations/` note. Not
   the minutes themselves; Notion has those.

## Speakers

Omi labels Paul "User" and others "Speaker N". Map speakers to names from the calendar
attendee list where you can; otherwise keep the label and say the mapping is uncertain.

## Edge Cases

- **No transcript segments:** work from `structured.overview` and say the transcript
  was unavailable.
- **Under 2 minutes or under 10 segments:** probably not a meeting. Ask Sunday first.
- **Legal, HR or financial meetings:** flag them as sensitive in the message to Sunday.
- **Several Omi conversations overlapping one calendar event:** it split one meeting.
  Combine them.
- **"Process my meetings" (plural):** list the day's conversations with times and
  titles, ask which, then one set of minutes each.
