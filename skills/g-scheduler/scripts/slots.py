#!/usr/bin/env python3
"""Rank meeting slots that fit inside every attendee's working hours.

Usage: python3 slots.py [input.json]   (reads stdin when no path is given)

Input and output are JSON; SKILL.md documents both. This script makes no
network calls: the agent fetches calendars and free/busy data with gws and
passes them in.
"""

import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_HOURS = {day: [(9 * 60, 17 * 60)] for day in DAYS[:5]}
EDGE = timedelta(minutes=30)
TZDATA_HINT = (
    "Python has no time zone data on this machine. "
    "Install it with: python -m pip install tzdata"
)


def parse_instant(value, tz, is_end=False):
    """Parse an RFC3339 time, or a date (start of that day in tz; end dates are inclusive)."""
    if len(value) == 10:
        day = date.fromisoformat(value)
        if is_end:
            day += timedelta(days=1)
        return datetime.combine(day, time(0), tzinfo=tz).astimezone(timezone.utc)
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return moment.astimezone(timezone.utc)


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def read_hours(working_hours):
    """Return {day: [(startMinute, endMinute)]}, or None when hours are not set."""
    if not working_hours or not working_hours.get("workingHoursEnabled"):
        return None
    days = {}
    for block in working_hours.get("availableTimes") or []:
        days.setdefault(block["dayOfWeek"].lower(), []).append(
            (int(block["periodStart"]), int(block["periodEnd"]))
        )
    return days or None


def expand(days, tz, start, end):
    """Turn weekly hours into UTC intervals covering [start, end)."""
    out = []
    day = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    while day <= last:
        midnight = datetime.combine(day, time(0), tzinfo=tz)
        for first, final in days.get(DAYS[day.weekday()], []):
            # Wall-clock arithmetic in the attendee's zone, so DST days keep 09:00 at 09:00.
            out.append((
                (midnight + timedelta(minutes=first)).astimezone(timezone.utc),
                (midnight + timedelta(minutes=final)).astimezone(timezone.utc),
            ))
        day += timedelta(days=1)
    return merge(out)


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def utc_text(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_text(start, end, tz):
    a, b = start.astimezone(tz), end.astimezone(tz)
    return f"{DAYS[a.weekday()][:3].title()} {a:%Y-%m-%d %H:%M}-{b:%H:%M}"


def load_attendee(raw, anchor, start, end, warnings):
    email = raw["email"]
    tz_name = raw.get("time_zone")
    try:
        tz = ZoneInfo(tz_name) if tz_name else None
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    if tz is None:
        reason = (f"calendar unreadable ({raw['calendar_error']})" if raw.get("calendar_error")
                  else f"time zone unknown ({tz_name!r})")
        warnings.append(f"{email}: {reason}; using {anchor.key}.")
        tz = anchor
    days = read_hours(raw.get("working_hours"))
    status = "set"
    if days is None:
        days, status = DEFAULT_HOURS, "assumed"
    busy = None
    if raw.get("busy_error"):
        warnings.append(f"{email}: free/busy unreadable ({raw['busy_error']}); left out of the search.")
    else:
        busy = merge(
            (parse_instant(b["start"], timezone.utc), parse_instant(b["end"], timezone.utc))
            for b in raw.get("busy") or []
        )
    return {
        "email": email,
        "optional": bool(raw.get("optional")),
        "tz": tz,
        "status": status,
        "days": days,
        "work": expand(days, tz, start, end),
        "busy": busy,
    }


def check(person, start, end):
    """Return (available, at_day_edge) for one attendee and one slot."""
    for work_start, work_end in person["work"]:
        if work_start <= start and end <= work_end:
            free = not any(b0 < end and start < b1 for b0, b1 in person["busy"])
            edge = start < work_start + EDGE or end > work_end - EDGE
            return free, free and edge
    return False, False


def find_slots(data):
    anchor = ZoneInfo(data["time_zone"])
    start = parse_instant(data["range"]["start"], anchor)
    end = parse_instant(data["range"]["end"], anchor, is_end=True)
    now = parse_instant(data["now"], anchor) if data.get("now") else datetime.now(timezone.utc)
    start = max(start, now)
    duration = timedelta(minutes=int(data.get("duration_minutes", 60)))
    step = int(data.get("step_minutes", 30))
    max_results = int(data.get("max_results", 5))
    max_per_day = int(data.get("max_per_day", 2))

    warnings = []
    people = [load_attendee(a, anchor, start, end, warnings) for a in data["attendees"]]
    assumed = [p["email"] for p in people if p["status"] == "assumed"]
    if assumed:
        warnings.append(
            "No working hours set, so 09:00-17:00 weekdays in their own time zone was assumed for: "
            + ", ".join(assumed) + "."
        )
    known = [p for p in people if p["busy"] is not None]
    required = [p for p in known if not p["optional"]]

    candidates = []
    epoch_minutes = int(start.timestamp() // 60)
    slot = start.replace(second=0, microsecond=0) + timedelta(minutes=-epoch_minutes % step)
    if slot < start:
        slot += timedelta(minutes=step)
    while slot + duration <= end:
        slot_end = slot + duration
        missing, missing_optional, edge = [], [], []
        for person in known:
            free, at_edge = check(person, slot, slot_end)
            if not free:
                (missing_optional if person["optional"] else missing).append(person["email"])
            elif at_edge:
                edge.append(person["email"])
        candidates.append((slot, slot_end, missing, missing_optional, edge))
        slot += timedelta(minutes=step)

    slots = []
    fewest = min((len(c[2]) for c in candidates), default=0)
    if candidates and fewest < len(required):
        pool = [c for c in candidates if len(c[2]) == fewest]
        # Earlier day first, then fewer optional people missing, then fewer people at the edge of their day.
        pool.sort(key=lambda c: (c[0].astimezone(anchor).date(), len(c[3]), len(c[4]), c[0]))
        per_day = {}
        for c in pool:
            day = c[0].astimezone(anchor).date()
            if per_day.get(day, 0) >= max_per_day:
                continue
            if any(c[0] < s[1] and s[0] < c[1] for s in slots):
                continue
            slots.append(c)
            per_day[day] = per_day.get(day, 0) + 1
            if len(slots) >= max_results:
                break
        slots.sort(key=lambda c: c[0])

    return {
        "time_zone": anchor.key,
        "duration_minutes": int(duration.total_seconds() // 60),
        "all_required_free": bool(slots) and fewest == 0,
        "slots": [
            {
                "start": utc_text(s),
                "end": utc_text(e),
                "local": {anchor.key: local_text(s, e, anchor)}
                | {p["email"]: f"{local_text(s, e, p['tz'])} {p['tz'].key}" for p in people},
                "missing": missing,
                "missing_optional": missing_optional,
                "at_day_edge": edge,
            }
            for s, e, missing, missing_optional, edge in slots
        ],
        "attendees": [
            {
                "email": p["email"],
                "time_zone": p["tz"].key,
                "optional": p["optional"],
                "hours": p["status"],
                "busy_readable": p["busy"] is not None,
                "working_hours": {
                    day: [f"{hhmm(a)}-{hhmm(b)}" for a, b in sorted(p["days"][day])]
                    for day in DAYS if day in p["days"]
                },
            }
            for p in people
        ],
        "warnings": warnings,
    }


def main(argv):
    try:
        ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        print(TZDATA_HINT, file=sys.stderr)
        return 2
    try:
        if len(argv) > 1:
            with open(argv[1], encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = sys.stdin.read()
        result = find_slots(json.loads(raw))
    except KeyError as e:
        print(f"Invalid input: missing or unknown value {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
