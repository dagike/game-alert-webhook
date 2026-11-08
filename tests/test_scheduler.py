from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gamealert.config import Settings
from gamealert.scheduler import _safe, build_scheduler

TZ = ZoneInfo("America/Toronto")


def jobs(scheduler):
    # Jobs added before start() wait in pending_jobs, so read them from there.
    return [p[0] for p in scheduler._pending_jobs]


def fire_times(scheduler, now):
    return sorted(j.trigger.get_next_fire_time(None, now) for j in jobs(scheduler))


def test_two_daily_jobs_in_toronto_time():
    s = build_scheduler(Settings(), job=lambda: None)
    now = datetime(2026, 11, 7, 10, 0, tzinfo=TZ)
    times = fire_times(s, now)
    assert [t.strftime("%Y-%m-%d %H:%M") for t in times] == ["2026-11-07 21:00", "2026-11-08 09:00"]
    assert all(t.tzinfo is not None and t.utcoffset().total_seconds() == -5 * 3600 for t in times)


def test_custom_times_and_timezone():
    s = build_scheduler(Settings(timezone="UTC", run_times=["07:30"]), job=lambda: None)
    (job,) = jobs(s)
    t = job.trigger.get_next_fire_time(None, datetime(2026, 11, 7, 8, 0, tzinfo=ZoneInfo("UTC")))
    assert t.strftime("%H:%M") == "07:30" and t.day == 8


def test_bad_run_time_raises():
    with pytest.raises(ValueError):
        build_scheduler(Settings(run_times=["25:00"]), job=lambda: None)


def test_bad_timezone_raises():
    with pytest.raises(KeyError):
        build_scheduler(Settings(timezone="Mars/Base"), job=lambda: None)


def test_failing_job_does_not_raise(caplog):
    def boom():
        raise RuntimeError("x")

    _safe(boom)()
    assert "Scheduled run failed" in caplog.text
