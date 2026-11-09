import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import os
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "g-scheduler" / "scripts" / "slots.py"
sys.path.insert(0, str(SCRIPT.parent))
import slots  # noqa: E402

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def hours(start_hour, end_hour, days=WEEKDAYS):
    return {
        "workingHoursEnabled": True,
        "availableTimes": [
            {"dayOfWeek": d, "periodStart": start_hour * 60, "periodEnd": end_hour * 60} for d in days
        ],
    }


def person(email, tz, working_hours=None, busy=(), **extra):
    return {"email": email, "time_zone": tz, "working_hours": working_hours,
            "busy": [{"start": s, "end": e} for s, e in busy], **extra}


def run(attendees, start, end, **options):
    data = {"time_zone": "America/Los_Angeles", "range": {"start": start, "end": end},
            "now": "2026-10-01T00:00:00Z", "duration_minutes": 60, "attendees": attendees}
    data.update(options)
    return slots.find_slots(data)


def starts(result):
    return [s["start"] for s in result["slots"]]


class FindSlotsTest(unittest.TestCase):
    def test_prefers_earlier_days_and_avoids_the_first_half_hour(self):
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17))], "2026-11-10", "2026-11-11")
        # Los Angeles is UTC-8 in November: 09:30 local is 17:30Z.
        self.assertEqual(starts(result)[:3],
                         ["2026-11-10T17:30:00Z", "2026-11-10T18:30:00Z", "2026-11-11T17:30:00Z"])
        self.assertTrue(result["all_required_free"])

    def test_working_hours_follow_dst(self):
        # US DST ends Sunday 2026-11-01: Los Angeles goes from UTC-7 to UTC-8.
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17))],
                     "2026-10-30", "2026-11-02", max_per_day=1)
        self.assertEqual(starts(result), ["2026-10-30T16:30:00Z", "2026-11-02T17:30:00Z"])

    def test_split_hours_leave_a_gap(self):
        split = {"workingHoursEnabled": True, "availableTimes": [
            {"dayOfWeek": "tuesday", "periodStart": 540, "periodEnd": 720},
            {"dayOfWeek": "tuesday", "periodStart": 780, "periodEnd": 1020}]}
        busy = [("2026-11-10T17:00:00Z", "2026-11-10T19:00:00Z"),  # 09:00-11:00 local
                ("2026-11-10T22:00:00Z", "2026-11-11T01:00:00Z")]  # 14:00-17:00 local
        result = run([person("a@example.com", "America/Los_Angeles", split, busy)],
                     "2026-11-10", "2026-11-10", max_per_day=5)
        # Only 11:00-12:00 and 13:00-14:00 fit; 11:30 and 12:00 would cross the lunch gap.
        self.assertEqual(starts(result), ["2026-11-10T19:00:00Z", "2026-11-10T21:00:00Z"])

    def test_attendees_in_different_time_zones(self):
        result = run([person("la@example.com", "America/Los_Angeles", hours(9, 17)),
                      person("hfx@example.com", "America/Halifax", hours(10, 19))],
                     "2026-11-10", "2026-11-10", max_per_day=5)
        # Los Angeles 17:00Z-01:00Z, Halifax (UTC-4) 14:00Z-23:00Z: overlap 17:00Z-23:00Z.
        first = result["slots"][0]
        self.assertEqual(first["start"], "2026-11-10T17:30:00Z")
        self.assertEqual(first["local"]["hfx@example.com"], "Tue 2026-11-10 13:30-14:30 America/Halifax")
        for s in result["slots"]:
            self.assertGreaterEqual(s["start"], "2026-11-10T17:00:00Z")
            self.assertLessEqual(s["end"], "2026-11-10T23:00:00Z")

    def test_no_shared_hours_falls_back_to_fewest_missing(self):
        # Los Angeles 17:00Z-01:00Z and Brussels (UTC+1) 08:00Z-16:00Z never overlap.
        result = run([person("la@example.com", "America/Los_Angeles", hours(9, 17)),
                      person("bru@example.com", "Europe/Brussels", hours(9, 17))],
                     "2026-11-10", "2026-11-11")
        self.assertFalse(result["all_required_free"])
        self.assertTrue(result["slots"])
        for s in result["slots"]:
            self.assertEqual(len(s["missing"]), 1)

    def test_nobody_free_returns_no_slots(self):
        busy = [("2026-11-01T00:00:00Z", "2026-11-20T00:00:00Z")]
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17), busy),
                      person("b@example.com", "America/Los_Angeles", hours(9, 17), busy)],
                     "2026-11-10", "2026-11-12")
        self.assertEqual(result["slots"], [])
        self.assertFalse(result["all_required_free"])

    def test_unset_hours_assume_nine_to_five_in_their_zone(self):
        stale = hours(6, 8)
        stale["workingHoursEnabled"] = False
        empty = {"workingHoursEnabled": True, "availableTimes": []}
        people = [person("missing@example.com", "America/Sao_Paulo"),
                  person("disabled@example.com", "America/Sao_Paulo", stale),
                  person("empty@example.com", "America/Sao_Paulo", empty)]
        result = run(people, "2026-11-10", "2026-11-10")
        self.assertEqual([a["hours"] for a in result["attendees"]], ["assumed"] * 3)
        self.assertIn("missing@example.com, disabled@example.com, empty@example.com", " ".join(result["warnings"]))
        # Sao Paulo is UTC-3: assumed 09:30 local is 12:30Z, not the stale 06:00-08:00.
        self.assertEqual(starts(result)[0], "2026-11-10T12:30:00Z")

    def test_optional_attendee_can_be_missing(self):
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17)),
                      person("b@example.com", "America/Los_Angeles", hours(9, 17),
                             [("2026-11-10T00:00:00Z", "2026-11-11T08:00:00Z")], optional=True)],
                     "2026-11-10", "2026-11-10")
        self.assertTrue(result["all_required_free"])
        self.assertEqual(result["slots"][0]["missing_optional"], ["b@example.com"])

    def test_unreadable_busy_is_left_out_and_warned(self):
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17)),
                      person("gone@example.com", "America/Los_Angeles", busy_error="notFound")],
                     "2026-11-10", "2026-11-10")
        self.assertTrue(result["all_required_free"])
        self.assertIn("gone@example.com: free/busy unreadable (notFound)", " ".join(result["warnings"]))

    def test_unreadable_calendar_uses_organizer_zone_and_assumed_hours(self):
        result = run([{"email": "ext@example.org", "calendar_error": "notFound", "busy": []}],
                     "2026-11-10", "2026-11-10")
        self.assertIn("ext@example.org: calendar unreadable (notFound); using America/Los_Angeles.",
                      result["warnings"])
        self.assertEqual(result["attendees"][0]["hours"], "assumed")
        self.assertEqual(starts(result)[0], "2026-11-10T17:30:00Z")

    def test_slots_never_start_before_now(self):
        result = run([person("a@example.com", "America/Los_Angeles", hours(9, 17))],
                     "2026-11-10", "2026-11-10", now="2026-11-10T19:50:00Z")
        self.assertEqual(starts(result)[0], "2026-11-10T20:00:00Z")


class CommandLineTest(unittest.TestCase):
    def test_reads_stdin_and_writes_json(self):
        data = {"time_zone": "America/Los_Angeles", "range": {"start": "2026-11-10", "end": "2026-11-10"},
                "now": "2026-10-01T00:00:00Z", "attendees": [person("a@example.com", "America/Los_Angeles", hours(9, 17))]}
        out = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(data),
                             capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout)["slots"][0]["start"], "2026-11-10T17:30:00Z")

    @unittest.skipIf(importlib.util.find_spec("tzdata"), "tzdata is installed")
    def test_missing_time_zone_data_prints_install_hint(self):
        with tempfile.TemporaryDirectory() as empty:
            env = dict(os.environ, PYTHONTZPATH=empty)
            out = subprocess.run([sys.executable, str(SCRIPT)], input="{}", env=env,
                                 capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("pip install tzdata", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
