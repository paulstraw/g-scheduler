#!/usr/bin/env python3
"""Talk to Google Calendar through the gws CLI.

  gcal.py check [EMAIL]
      Check that gws works, and that working hours can be read (yours, and EMAIL's).
  gcal.py gather EMAIL... --start S --end E [--time-zone TZ] [--duration MIN]
                 [--optional EMAIL]... [--exclude-me]
      Print the input JSON for slots.py. Adds you as an attendee unless --exclude-me.
  gcal.py invite EVENT.json [--dry-run]
      Create the event on your primary calendar and email every attendee.

gws is called with argument lists, never through a shell, so JSON needs no
quoting on any platform.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slots  # noqa: E402

FREEBUSY_CHUNK = 50  # freebusy.query calendarExpansionMax


class GwsError(Exception):
    pass


def gws(*args):
    exe = shutil.which("gws")
    if not exe:
        raise GwsError("gws is not installed or not on PATH. Follow SETUP.md.")
    proc = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8")
    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if proc.returncode != 0 or "error" in data:
        error = data.get("error") or {}
        raise GwsError(
            error.get("reason") or error.get("message") or proc.stderr.strip()
            or f"gws exited with code {proc.returncode}"
        )
    return data


def get_calendar(calendar_id):
    return gws("calendar", "calendars", "get", "--params", json.dumps({"calendarId": calendar_id}))


def hours_status(calendar):
    return "set" if slots.read_hours(calendar.get("workingHours")) else "not set"


def check(args):
    me = get_calendar("primary")
    result = {"gws": shutil.which("gws"), "me": me["id"], "time_zone": me.get("timeZone"),
              "my_working_hours": hours_status(me)}
    if args.email:
        try:
            other = get_calendar(args.email)
            result["colleague"] = {"email": args.email, "time_zone": other.get("timeZone"),
                                   "working_hours": hours_status(other)}
        except GwsError as e:
            result["colleague"] = {"email": args.email, "error": str(e)}
    return result


def gather(args):
    me = get_calendar("primary")
    my_email = me["id"].lower()
    tz_name = args.time_zone or me["timeZone"]
    anchor = ZoneInfo(tz_name)
    start = slots.parse_instant(args.start, anchor)
    end = slots.parse_instant(args.end, anchor, is_end=True)
    optional = {e.strip().lower() for e in args.optional}
    emails = list(dict.fromkeys(e.strip().lower() for e in args.emails))
    if not args.exclude_me and my_email not in emails:
        emails.insert(0, my_email)

    attendees = {}
    for email in emails:
        entry = {"email": email}
        if email in optional:
            entry["optional"] = True
        try:
            calendar = me if email == my_email else get_calendar(email)
            entry["time_zone"] = calendar.get("timeZone")
            entry["working_hours"] = calendar.get("workingHours")
        except GwsError as e:
            entry["calendar_error"] = str(e)
        attendees[email] = entry

    for i in range(0, len(emails), FREEBUSY_CHUNK):
        chunk = emails[i:i + FREEBUSY_CHUNK]
        body = {"timeMin": slots.utc_text(start), "timeMax": slots.utc_text(end),
                "items": [{"id": e} for e in chunk]}
        calendars = gws("calendar", "freebusy", "query", "--json", json.dumps(body)).get("calendars", {})
        for email in chunk:
            found = calendars.get(email)
            if found is None or found.get("errors"):
                reasons = [e.get("reason", "unknown") for e in (found or {}).get("errors", [])]
                attendees[email]["busy_error"] = ", ".join(reasons) or "missing from response"
            else:
                attendees[email]["busy"] = found.get("busy", [])

    return {"time_zone": tz_name, "range": {"start": args.start, "end": args.end},
            "duration_minutes": args.duration, "attendees": list(attendees.values())}


def invite(args):
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    command = ["calendar", "events", "insert",
               "--params", json.dumps({"calendarId": "primary", "sendUpdates": "all"}),
               "--json", json.dumps(event)]
    if args.dry_run:
        command.append("--dry-run")
    created = gws(*command)
    if args.dry_run:
        return created
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink"),
            "start": created.get("start"), "end": created.get("end"),
            "attendees": [a.get("email") for a in created.get("attendees", [])]}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("check")
    p.add_argument("email", nargs="?")
    p.set_defaults(run=check)
    p = commands.add_parser("gather")
    p.add_argument("emails", nargs="+")
    p.add_argument("--start", required=True, help="date (YYYY-MM-DD) or RFC3339 time")
    p.add_argument("--end", required=True, help="date (inclusive) or RFC3339 time")
    p.add_argument("--time-zone", help="IANA zone for dates and ranking; default: your calendar's")
    p.add_argument("--duration", type=int, default=60, help="minutes; default 60")
    p.add_argument("--optional", action="append", default=[], help="an attendee who may miss it")
    p.add_argument("--exclude-me", action="store_true", help="don't add yourself as an attendee")
    p.set_defaults(run=gather)
    p = commands.add_parser("invite")
    p.add_argument("event", help="path to an Events resource JSON file")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(run=invite)
    args = parser.parse_args(argv[1:])

    try:
        ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        print(slots.TZDATA_HINT, file=sys.stderr)
        return 2
    try:
        result = args.run(args)
    except GwsError as e:
        print(f"gws failed: {e}", file=sys.stderr)
        return 1
    except (ValueError, KeyError) as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
