---
name: g-scheduler
description: Find good meeting times for a group of Google Workspace users, inside each person's Google Calendar working hours and time zone, and optionally send the invite. Use when the user asks to find a time, schedule or book a meeting, or check when several people are free. Attendees can come from anywhere, such as a Slack message's reactions, a list of names, or a doc. Needs a shell and the gws CLI.
---

# g-scheduler

Find meeting slots where every attendee is free and inside their own working hours, then (only if asked) create the invite. Two bundled scripts do the Google calls and the time math. Never do time-zone or DST arithmetic yourself: use their output.

Run the scripts with `python3` (on Windows, `python` or `py`) from this skill's directory: `scripts/gcal.py` and `scripts/slots.py`. They need Python 3.10+.

## 1. Check access

Run `python3 scripts/gcal.py check`.

- If it fails because `gws` is missing or not signed in, or a Python error asks for `tzdata`, stop and walk the user through [SETUP.md](SETUP.md), one step at a time. There is no way to continue without it.
- If it succeeds, continue. `my_working_hours: "not set"` is fine.

## 2. Collect the inputs

- **Attendees:** resolve everyone to Google Workspace email addresses with whatever tools you have (Slack, a directory, the user's message). If an email is missing, ambiguous, or looks outside the user's organization, ask. The user is added automatically; pass `--exclude-me` only if they say they won't attend.
- **Date range:** keep it simple. "Next 2 weeks" means today through about 18 days out (sooner slots already rank first). A specific day means just that day. Dates are `YYYY-MM-DD`; the end date is inclusive.
- **Length:** default 60 minutes. Don't ask; say you assumed it.
- **Optional people:** don't ask up front. Treat everyone as required.

## 3. Find slots

```bash
python3 scripts/gcal.py gather a@example.com b@example.com --start 2026-11-10 --end 2026-11-27 \
  | python3 scripts/slots.py
```

`gather` options: `--duration MIN`, `--optional EMAIL` (repeatable), `--exclude-me`, `--time-zone TZ` (defaults to the user's calendar zone, which is also used to rank and display).

The output has `slots` (up to 5, at most 2 per day, earliest first), `all_required_free`, `attendees`, and `warnings`. Each slot has `local` times for every attendee and the user's zone, `missing`, `missing_optional`, and `at_day_edge` (people for whom it's in the first or last 30 minutes of their day).

## 4. Present the results

- List the slots in the user's time zone, with each attendee's local time when zones differ.
- Repeat every warning in plain words. Name people whose working hours were assumed (09:00-17:00 weekdays in their zone) and anyone who was left out because their calendar couldn't be read.
- State the assumed length if the user didn't give one.
- If `all_required_free` is false, say who is missing from each slot and offer to rerun with those people as `--optional`.
- If `slots` is empty, say so and suggest a wider range or a shorter meeting.

## 5. Create the invite (only when asked)

1. Draft a title from context, and a short description that includes the source link (for example, the Slack thread) if there is one.
2. Ask whether to add a video conferencing link. If given, put it in `location` and in the description. Don't create Meet or Zoom meetings.
3. Show the exact event (title, local time, attendees, description, location) and wait for an explicit "yes, send it". Sending emails everyone and can't be undone.
4. Write the event to a temporary JSON file as a Calendar `Events` resource, with times in the user's zone:

   ```json
   {
     "summary": "Project kickoff",
     "description": "Scheduled from https://example.slack.com/archives/...",
     "location": "https://zoom.us/j/123",
     "start": {"dateTime": "2026-11-18T10:00:00", "timeZone": "America/Los_Angeles"},
     "end": {"dateTime": "2026-11-18T11:00:00", "timeZone": "America/Los_Angeles"},
     "attendees": [{"email": "a@example.com"}, {"email": "b@example.com"}]
   }
   ```

5. Run `python3 scripts/gcal.py invite EVENT.json`. It always sends invitations to all attendees. Use `--dry-run` first if you want to check the request.
6. Give the user the `htmlLink` from the output, and delete the temporary file.

## Rules

- Everything except `invite` is read-only. Never change anyone's calendar or working hours.
- Never send an invite without the user's explicit confirmation of the previewed event.
- If times for a zone look an hour off, the machine's time zone data is probably old (zone rules change, as British Columbia's did in 2026). See Troubleshooting in SETUP.md.
