"""Release-time rules for data/release_calendar.json: when each report is published and which data date the newest
published release carries. Used by pipelines/watchdog.py and by release-timed pipelines (e.g. pipelines/oncall/scrape.py).

Rule types (times are US Eastern):
  weekly          weekday (0 = Mon), time, data_offset_days (data date relative to the scheduled release day),
                  shift: on_day (holiday on the day -> next business day), week_to_friday (a holiday Mon..release day ->
                  one business day later), week_to_monday (a holiday Mon..Fri of the release week -> following Monday),
                  optional months (release months only, e.g. crop progress Apr-Nov)
  dates           explicit release dates (WASDE): {"dates": [...], "time": "12:00"}; data date = release date
  business_daily  every business day at time; data_offset_bd (0 = same day, -1 = previous business day);
                  calendar "ice" or "federal"
  age             no fixed release: late when the source's age is over its data-status limit
Only the standard library is used, so the per-repo catch-up jobs can run it without installing anything.
"""
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CAL_PATH = Path(__file__).resolve().parent.parent / "data" / "release_calendar.json"


def load_calendar(path=CAL_PATH):
    return json.loads(Path(path).read_text())


class Cal:
    def __init__(self, cal):
        self.fed = {date.fromisoformat(d) for d in cal["holidays"]["us_federal"]}
        self.ice = {date.fromisoformat(d) for d in cal["holidays"]["ice_us_softs"]}

    def is_bd(self, d, which="federal"):
        return d.weekday() < 5 and d not in (self.ice if which == "ice" else self.fed)

    def next_bd(self, d, which="federal"):
        d += timedelta(days=1)
        while not self.is_bd(d, which):
            d += timedelta(days=1)
        return d

    def add_bd(self, d, n, which="federal"):
        step = 1 if n > 0 else -1
        while n:
            d += timedelta(days=step)
            if self.is_bd(d, which):
                n -= step
        return d


def _at(d, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), ET)


def releases(rule, cal, now, back_days=70):
    """Releases from back_days ago up to a week ahead: list of (release_datetime_ET, data_date), oldest first."""
    t = rule["type"]
    out = []
    today = now.astimezone(ET).date()
    if t == "weekly":
        wd, months = rule["weekday"], rule.get("months")
        d = today - timedelta(days=back_days)
        d += timedelta(days=(wd - d.weekday()) % 7)
        while d <= today + timedelta(days=7):
            if not months or d.month in months:
                rel, shift = d, rule.get("shift", "on_day")
                monday = d - timedelta(days=d.weekday())
                if shift == "on_day":
                    while not cal.is_bd(rel):
                        rel = cal.next_bd(rel)
                elif shift == "week_to_friday":
                    if any(monday + timedelta(days=k) in cal.fed for k in range(d.weekday() + 1)):
                        rel = cal.next_bd(rel)
                    while not cal.is_bd(rel):
                        rel = cal.next_bd(rel)
                elif shift == "week_to_monday":
                    if any(monday + timedelta(days=k) in cal.fed for k in range(5)):
                        rel = monday + timedelta(days=7)
                        while not cal.is_bd(rel):
                            rel = cal.next_bd(rel)
                out.append((_at(rel, rule["time"]), d + timedelta(days=rule.get("data_offset_days", 0))))
            d += timedelta(days=7)
    elif t == "dates":
        for s in rule["dates"]:
            d = date.fromisoformat(s)
            if today - timedelta(days=back_days * 2) <= d <= today + timedelta(days=40):
                out.append((_at(d, rule["time"]), d))
    elif t == "business_daily":
        which = rule.get("calendar", "federal")
        d = today - timedelta(days=back_days)
        while d <= today + timedelta(days=3):
            if cal.is_bd(d, which):
                off = rule.get("data_offset_bd", 0)
                out.append((_at(d, rule["time"]), cal.add_bd(d, off, which) if off else d))
            d += timedelta(days=1)
    return sorted(out)


def expected(entry, cal, now):
    """Newest release that should be in the data by now (release time + late_after_hours passed).
    Returns dict(release, data_date, late_since) or None for rules without fixed releases."""
    rule = entry["release"]
    if rule["type"] not in ("weekly", "dates", "business_daily"):
        return None
    grace = timedelta(hours=entry.get("late_after_hours", 6))
    past = [(r, dd) for r, dd in releases(rule, cal, now) if r + grace <= now]
    if not past:
        return None
    r, dd = past[-1]
    return {"release": r.isoformat(timespec="minutes"), "data_date": dd.isoformat(), "late_since": (r + grace).isoformat(timespec="minutes")}


def latest_due(entry, cal, now):
    """Newest release already out (no grace): (release_datetime, data_date) or None."""
    rule = entry["release"]
    if rule["type"] not in ("weekly", "dates", "business_daily"):
        return None
    past = [(r, dd) for r, dd in releases(rule, cal, now) if r <= now]
    return past[-1] if past else None


def entry(cal, eid):
    return next(e for e in cal["reports"] if e["id"] == eid)
