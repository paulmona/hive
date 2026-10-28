---
name: morning-briefing
description: >
  Generate a concise morning briefing for Paul covering health/recovery, today's calendar,
  and active development work. Use this skill whenever Paul says anything like "morning briefing",
  "good morning", "start my day", "what's my day look like", "daily briefing", "morning summary",
  "what do I have on today", or any phrase indicating he wants an overview of his day first thing.
  Also trigger when Paul says "brief me" or "what's on my plate today".
  Always use this skill rather than pulling data ad hoc — it ensures consistent format and
  pulls from all sources in a single structured pass.
---

# Morning Briefing

---

> ## ⛔ MANDATORY RULE -- ALL NOTION WRITES REQUIRE EXPLICIT APPROVAL
>
> **Before writing ANYTHING to ANY Notion database, you MUST show Paul a confirmation summary
> and wait for his explicit approval. No exceptions. This applies to:**
> - Creating a new Training Log entry
> - Updating an existing Training Log entry (sleep data, status changes, any field)
> - Creating or updating To-Do entries
> - Any other Notion write operation
>
> **Show a table or clear summary of exactly what will be written and to which database.
> Do not proceed until Paul says yes, ok, go ahead, or equivalent.
> If there is any ambiguity in his response -- ask again. Never assume approval.**

---

## Overview

Generate a structured morning briefing covering Health & Recovery, Today's Schedule, Upcoming
To-Dos, and (conditionally) any new bills requiring attention. Pull all data sources in parallel
where possible, then render a clean summary.

---

## Step 1: Pull All Data in Parallel

Fetch from all sources simultaneously:

### 1a. Garmin Recovery Snapshot
Call `Garmin:get_recovery_snapshot` for HRV, sleep score, morning readiness, and stress.

> ⛔ **Resting HR does NOT come from the snapshot.** Always call
> `Garmin:get_resting_hr_trend` (n=1) and take the entry dated today.
>
> Observed 2026-09-10: the snapshot's resting HR field is named `resting_hr_yesterday` and
> holds **yesterday's** figure, while the payload's top-level `date` is today. The whole
> response therefore reads as current when one field is not, and taking the value without the
> qualifier is the natural misread, not a careless one. That morning it produced a false
> anomaly (reported 53 bpm, flagged as 6-10 above baseline; the real overnight figure was 45,
> his normal) and the phantom cardiac signal then contaminated the day's prescription. The
> spike to 53 was real on the 9th and had already resolved.

If `get_recovery_snapshot` is unavailable, fall back to:
- `Garmin:get_hrv_trend` for HRV
- `Garmin:get_sleep_history` (n=1) for last night's sleep

Do NOT fetch Body Battery -- it is temporarily disabled due to a data issue.

**Sleep data handling:** If both `sleep_score` and `sleep_duration_hours` come back null from
the recovery snapshot (or sleep history fallback), do NOT show those rows in the Health table.
Instead, add this note below the table:
> ⚠️ Sleep data unavailable -- please sync your Garmin watch and re-run if needed.

### 1b. Today's Calendar
Call `Google Calendar:gcal_list_events` for today's date (start = midnight, end = 11:59pm local).
Include all calendars. Filter out all-day events that are just holidays or birthdays unless
they seem meaningful (e.g. a deadline, a trip, a recurring personal event).

### 1c. Upcoming To-Dos
Query the **My To Dos** Notion database (`collection://<TODOS_DS_ID>`)
and fetch all entries where `Reminder Date` is not null. Filter client-side for entries where
the `Reminder Date` is either:
- In the past (overdue), OR
- Within the next 48 hours from now

Also fetch the `Status` field for each entry. Exclude any entries with Status = "Done" or
"Skipped" -- they do not need to appear in the briefing.

Use the `date:Reminder Date:start` property for date comparison. Do NOT use `createdTime`.

### 1d. Non-Autopay Bills
Query the **Bills** Notion database (`collection://<BILLS_DS_ID>`) and
fetch all entries where `Auto-Pay` is `__NO__` (unchecked). Collect the `Bill Name`,
`Billing Day`, `Typical Amount`, and `Amount Known` fields for use in Step 5.

### 1e. Fleet Vault Health
Every agent's vault (Friday, Sunday, Oddjob) runs a nightly consolidation job at 03:30 and a
weekly health report on Monday 04:30. Each job publishes a retained status to
`hive/status/vault-health/<agent>`. Read them with the MQTT `inbox` tool, one call per topic:
`hive/status/vault-health/friday`, `hive/status/vault-health/sunday`, `hive/status/vault-health/oddjob`.
Each message is `[timestamp] vault-job/<agent>: {json}`; take the **latest** message per topic
and read the JSON: `job`, `date`, `ok`, `health.notes`, `health.issues`, `health.by_severity`,
`open_conflicts`, `conflict_notes`, `report`. Pass `clear: true` so old ones do not pile up.

If `inbox` says the topic is not watched or the buffer is empty, run the MQTT `watch` tool with
pattern `hive/status/vault-health/+` (it persists; this only needs to happen once) and note in
the briefing that vault status will appear from tomorrow. Do not block the briefing on this.

---

## Step 2: Prescribe Today's Session

After pulling the data but before rendering the briefing, **decide the session and state it.
Do not ask Paul what he is planning.** This implements the Standing Rule "Coach, don't ask" in
`CLAUDE.md`; that rule wins, and this step is written to match it.

Prescribe from, in order:
1. The recovery data pulled in Step 1 (HRV, sleep, resting HR from `get_resting_hr_trend`, stress)
2. The current training approach in your vault
3. His injury constraints
4. What he has already done this week, and what is coming (races, trips, travel days)

State it as a prescription with the reason in one line, for example:

> "Zone 2 ride, 60 minutes. HRV is flat and that's your third hard day running."

**Name the actual signal you used.** If a number moved your prescription, it must be a number
you verified this morning, not one inferred from a payload (see the resting HR rule in Step 1a).
A wrong premise gets reused; a right call for a stated wrong reason is worse than no reason.

He can overrule, and stating it rather than asking is what makes overruling cheap. Keep him
honest if he is slacking, but the prescription is a recommendation, not a gate.

**Once the session is settled (he accepts the prescription, or names his own):**
First, check Notion for an existing entry for today using a database query filtered by the `Date`
property. Use `Notion:notion-fetch` or the appropriate Notion database query tool to filter the
Training Log database (`<TRAINING_LOG_DS_ID>`) where `Date` equals today's date
(formatted as `YYYY-MM-DD`).

> ⛔ **ABSOLUTE RULE -- DATE LOOKUP:** You MUST filter by the `Date` property (the workout date
> column) when querying the Training Log. You MUST NOT use `last_edited_time`, `createdTime`,
> page timestamps, or any metadata field as a proxy for workout date -- under any circumstances.
> These fields reflect when a record was last touched, not when the workout occurred. Read the
> actual table data and use the `Date` column. No exceptions.

**Handling existing entries by Status:**

- **Status = "Scheduled" or "Done"**: Skip creation and note it in the briefing. Do not modify.

- **Status = "Planned"**: STOP. Do NOT create a new entry and do NOT modify the existing one yet.
  Ask Paul explicitly before taking any action:

  > "I found an existing entry for today with Status **Planned** ([entry name]). Do you want me
  > to update that entry, or create a separate new one?"

  Wait for his explicit answer before proceeding. If he says update -- modify the existing page.
  If he says create a new one -- proceed with creation. If he is ambiguous -- ask again. Do not
  guess or default. **No writes to the Training Log happen until Paul confirms.**

- **No entry exists**: Create a Notion Training Log entry with:
  - `Notion:notion-create-pages` to data source `<TRAINING_LOG_DS_ID>`
  - Status: `"Planned"`
  - Date: today
  - Workout Type: the settled session, mapped to one of Run, CrossFit, Snowboarding, Snowboard Touring, Hyrox Sim
  - Name: emoji prefix + Workout Type (e.g. `🏃 Run`, `🏋️ CrossFit`)
  - If there is extra detail, from your prescription or from him (e.g. "10km run", "zone 2, 60 min"), put it in a Notes or Description field if available

**If he says rest day or skips:** Create a Notion Training Log entry for today with:
- `Notion:notion-create-pages` to data source `<TRAINING_LOG_DS_ID>`
- Status: `"Done"`
- Date: today
- Workout Type: `"Rest"`
- Name: `"😴 Rest"`

Rest days ARE now logged so that sleep and nutrition data can be attached to them.

**If he is uncertain or non-committal** (e.g. "not sure yet", "depends on how I feel", "waiting to hear", "maybe", or any response that doesn't commit to a specific workout or rest): Create a Rest Day placeholder entry with:
- `Notion:notion-create-pages` to data source `<TRAINING_LOG_DS_ID>`
- Status: `"Done"`
- Date: today
- Workout Type: `"Rest"`
- Name: `"🛋️ Rest Day (placeholder)"`

Note it in the briefing as: `🛋️ Rest Day (placeholder -- update after workout)`

**Rule: Never skip entry creation.** If Paul does not respond to the prescription, gives an ambiguous answer, or cannot commit -- default to creating a Rest Day placeholder entry. A placeholder can always be updated later; a missing entry loses the sleep and recovery data permanently. Always log something. Always proceed to Step 2b regardless of which branch was taken.

After handling the workout entry (rest day, placeholder, or named workout), proceed to **Step 2b** before rendering the briefing.

---

## Step 2b: Sleep Sync and Logging

After the workout entry has been created (always -- no exceptions), prompt Paul:

> "⌚ Please stop your sleep tracking on your Garmin now if you haven't already -- it needs to sync before I can pull the data. Let me know when you're done."

Wait for Paul's confirmation. Any affirmative response ("done", "ok", "ready", "synced", etc.) is sufficient to proceed.

Once confirmed:

1. **Fetch fresh sleep data** by calling `Garmin:get_sleep_history` with `n=1`. This fetches last night's sleep after the sync has completed. Extract:
   - Sleep score
   - Total sleep duration (hours + minutes)
   - Sleep stages breakdown (Deep, REM, Light, Awake) if available
   - HRV (overnight average) if available in the result

2. **Update the Notion Training Log entry for today** (the one just created in Step 2, whether a workout or rest day entry) using `Notion:notion-update-page`. Map Garmin fields to Notion properties as follows:

   | Garmin field | Notion property | Transform |
   |---|---|---|
   | `sleep_score` | `Sleep Score` | direct |
   | `total_sleep_seconds` | `Sleep Duration (hrs)` | divide by 3600, round to 2 decimal places |
   | `deep_sleep_seconds` | `Deep Sleep (min)` | divide by 60, round to nearest integer |
   | `light_sleep_seconds` | `Light Sleep (min)` | divide by 60, round to nearest integer |
   | `rem_sleep_seconds` | `REM Sleep (min)` | divide by 60, round to nearest integer |
   | `awake_seconds` | `Awake During Sleep (min)` | divide by 60, round to nearest integer |

   Only set fields that are non-null in the Garmin response.

3. **Confirm inline** -- do NOT re-render the full briefing:
   > ✅ Sleep logged to [entry name] -- Score: XX | Xh Xm

If Paul says the watch was already synced and he didn't need to stop tracking, skip the wait step and proceed directly to fetching.

If Garmin sleep data comes back null or unavailable after the sync, note it inline and continue:
> ⚠️ Sleep data still unavailable after sync -- you can re-run later if needed.

After completing Step 2b, proceed to render the briefing. Note the planned workout in the Health section.

---

## Step 3: Determine Today's Date and Greeting

Use the current date. Select greeting based on time of day:
- Before 12pm: "Good morning"
- 12–5pm: "Good afternoon"
- After 5pm: "Good evening"

---

## Step 4: Render the Briefing

Output in this exact structure. Keep each section tight — this is a scan, not a report.

---

```
## 🌅 [Greeting], Paul — [Day, Month Date]

---

### 💪 Health & Recovery

| Metric | Value | Signal |
|--------|-------|--------|
| Sleep Score | XX | 🟢/🟡/🔴 |
| Sleep Duration | X.Xh | 🟢/🟡/🔴 |
| HRV (overnight) | XX ms | 🟢/🟡/🔴 |
| Resting HR | XX bpm | 🟢/🟡/🔴 |
| Morning Readiness | XX/100 | 🟢/🟡/🔴 |
| Today's Plan | 🏃 Run / 🏋️ CrossFit / Rest | — |

[If sleep data is null: omit Sleep Score and Sleep Duration rows, and add:]
> ⚠️ Sleep data unavailable -- please sync your Garmin watch and re-run if needed.

**Training recommendation:** [1 sentence based on the data and today's planned workout type --
e.g. "HRV looks strong -- good day for a hard effort." or
"Recovery signals are mixed -- consider dialing back intensity today."]

---

### 📅 Today's Schedule

[If no events]: Nothing scheduled — clear runway today.

[If events, list as]:
- **HH:MM** — [Event title] ([duration or "all day"])
- **HH:MM** — [Event title]

---

### 📋 Upcoming To-Dos

[If nothing overdue or within 48h after filtering out Done/Skipped]: Nothing urgent -- you're clear.

[If items exist, group by urgency. Show Description and current Status for each item]:

**⚠️ Overdue**
- [Description] _(was [Reminder Date])_ · `To Do`

**📅 Due Today**
- [Description] _(today)_ · `To Do`

**🔜 Next 48 Hours**
- [Description] _([Reminder Date, e.g. "Mar 11"])_ · `To Do`

Each item shows Description and Status only. Omit Notes from this view -- keep it scannable.
If a group is empty, omit that group entirely.

[After rendering the To-Dos section, if there are any Overdue or Due Today items with
Status = "To Do", proceed to Step 4b before the closing note.]

---

### 🧠 Fleet Memory

[One line per agent, from Step 1e. Omit the section only if no status has ever been received.]

- **Friday** — [date] · [notes] notes · [issues] issues ([critical] 🔴 / [warning] 🟡) · [N open conflicts → "reconcile due" | "no conflicts"]
- **Sunday** — ...
- **Oddjob** — ...

Rules: if `ok` is false, lead the line with ⚠️ and say the [job] job failed on [date]. If
`open_conflicts` > 0, add "reconcile due" -- that means Paul should ask that agent to run
`/obsidian-reconcile`. On Mondays, when `job` is `health`, add the report path. If an agent's
status is more than 2 days old, say "stale since [date]" instead of the numbers.

---
[Optional 1-line closing note if anything stands out -- e.g. a big meeting, a recovery warning,
or overdue items needing attention. Otherwise omit.]

---

> ⛔ **PRE-CLOSE CHECKLIST -- DO NOT SKIP**
> Before considering the briefing complete, confirm:
> - [ ] Step 5 (Bills Scan) has been executed -- even if the conversation was interrupted
>
> Do not close the briefing or hand off to Paul until this box is checked.
> Interruptions do not excuse skipping Step 5.
```

---

## Step 4b: To-Do Completion Check

Run this step only if there are any **Overdue** or **Due Today** items with Status = "To Do".
Skip entirely if all such items are already marked Done or Skipped.

Present a concise prompt after the briefing:

> "Any of these done or can be skipped?"
>
> - [ ] [Description] _(was [date] / today)_
> - [ ] [Description] _(today)_

Wait for Paul's response. He can reply with item numbers, names, or "all done". Interpret
naturally -- e.g. "1 and 3 are done" or "skip the Bell one".

Valid status values to set:
- **Done** -- task was completed
- **Skipped** -- no longer relevant / not going to happen

For each item Paul marks, use `Notion:notion-update-page` to update the `Status` field on
that page to "Done" or "Skipped" respectively.

After updating, confirm inline -- do NOT re-render the full briefing:
> ✅ Updated: [Description] → Done
> ✅ Updated: [Description] → Skipped

If Paul says nothing needs updating, or if there are no overdue/due-today items, skip silently.

---

## Step 4c: Spoken Summary (Bedroom Only)

After the briefing is posted to Discord, publish a short spoken summary (three or four
sentences) to MQTT topic `ha/tts/briefing` with payload `{"message": "..."}`. HA plays it on
the master bedroom speaker only, and drops it when guest mode is on or Paul is away.

**Never** send any part of the briefing to `ha/tts/speak`, and never use `HassBroadcast`.
Those play through the whole house, and the briefing contains health data. `ha/tts/speak`
is only for follow-ups to voice requests that arrive through ha-voice.

---

## Signal Legend

Use these thresholds for 🟢/🟡/🔴 indicators:

| Metric | 🟢 Good | 🟡 OK | 🔴 Low |
|--------|---------|-------|--------|
| Sleep Score | ≥ 75 | 55–74 | < 55 |
| Sleep Duration | ≥ 7h | 6–7h | < 6h |
| HRV (vs baseline) | At or above 7-day avg | Within 10ms below | > 10ms below avg |
| Resting HR | At or below 7-day avg | 1–5 bpm above | > 5 bpm above |
| Morning Readiness | ≥ 70 | 50–69 | < 50 |

If a metric is unavailable, omit its row from the table rather than showing null.

---

## Step 5: Bills Scan (Conditional)

Run this step after rendering the briefing. Using the non-autopay bills list from Step 1d:

> **RULE: Search Gmail for ALL non-autopay suppliers without exception.** Do not skip a supplier
> because a To-Do already exists for them -- a new bill email may have arrived regardless.
> The Gmail search and the To-Do check are independent steps.

1. **Search Gmail** for each supplier using `Gmail:gmail_search_messages`. Search for emails
   from or mentioning each `Bill Name` received in the **last 7 days**. Use a combined query
   like: `from:([supplier domain or name]) newer_than:7d` or search by bill name keyword.


2. **Identify new bill emails**: Look for emails that appear to be a bill, invoice, or statement
   notification. Extract, if available:
   - Amount owing / amount due
   - Due date / payment date

3. **If no new bill emails are found for any supplier**: Suppress this entire section -- do not
   mention it in the briefing at all.

4. **If one or more new bills are found**: After the briefing is rendered, present a summary of
   what was found:

   > "Found new bill(s) -- I'll add these to your To-Dos. When would you like to be reminded
   > for each?"
   >
   > - **[Bill Name]** — $[amount or "amount unknown"] due [due date or "unknown"]
   >   Reminder date? (suggest: [due date - 2 days, or billing day - 2 days if known])

   Wait for Paul's response with reminder date(s). He can give one date for all, or per-bill.

5. **Create To-Do entries** in My To Dos (`collection://<TODOS_DS_ID>`)
   for each confirmed bill, with NO additional confirmation step:
   - `Description` (title): "[Bill Name] bill"
   - `Status`: "To Do"
   - `date:Reminder Date:start`: the reminder date Paul provided (or inferred default)
   - `date:Reminder Date:is_datetime`: 0
   - `Notes`: "Amount: $[X] | Due: [due date]" (include only fields that are known;
     omit amount or due date lines if not available)

6. **Report silently inline** after creation:
   > ✅ Added to To-Dos: [Bill Name] — remind [Reminder Date]

   Do not re-render the full briefing. Just append this confirmation.

---

## Edge Cases

- **Garmin data missing**: If recovery snapshot is fully unavailable, note "Garmin data unavailable"
  in the Health section and proceed with Calendar.
- **No calendar events**: State "Clear schedule today" -- don't show an empty list.
- **Weekend**: Still run the full briefing -- Paul may have workouts or personal calendar items.
- **Workout already in Notion**: If a Scheduled or Done entry already exists for today's date and matching type (e.g. Paul already ran the briefing once), skip creating a duplicate and note "Workout already scheduled in Notion." If an entry exists with Status = "Planned", stop and ask Paul whether to update it or create a new one -- no writes until he explicitly confirms. For rest days, if a "Rest Day" entry already exists for today, skip creation and proceed directly to Step 2b to handle sleep logging.
- **Date lookup**: ALWAYS use the `Date` property (workout date column) when querying the Training Log. NEVER use `last_edited_time`, `createdTime`, or any page metadata timestamp as a proxy for workout date.
- **Rest day entry**: Rest days (and uncertain/TBD entries) are logged with Workout Type `"Rest"` and Status `"Done"` so that sleep and nutrition data can be attached. Placeholder entries use the name `"🛋️ Rest Day (placeholder)"` and can be updated later via log-garmin-workout.
- **No upcoming To-Dos**: If nothing is overdue or within 48h, show "Nothing urgent -- you're clear."
- **To-Do with no Reminder Date**: Ignore entries with no date set -- they are not time-sensitive.
- **Bills scan finds no emails**: Suppress the Bills section entirely -- don't mention it.
- **Bill already in To-Dos**: Before creating a new To-Do for a bill, check if an entry with the
  same `Description` (e.g. "Enbridge Gas bill") already exists with a future Reminder Date and
  Status = "To Do". If so, skip creation and do not mention it. If it exists but is marked Done
  or Skipped, create a fresh entry for the new bill.
- **Gmail unavailable**: Skip the bills scan silently. Do not note it in the briefing.

---

## Notes

- Do not add commentary or filler -- the briefing should be scannable in under 60 seconds.
- Times should be in Paul's local timezone (Barrie, Ontario -- Eastern Time).
