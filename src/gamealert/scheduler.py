"""Run the summary at fixed times each day (default 09:00 and 21:00)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .discord import send_failure
from .runner import run_once, secret_values

log = logging.getLogger("gamealert")


def _safe(
    job: Callable[[], object], on_error: Callable[[Exception], None] | None = None
) -> Callable[[], None]:
    """Wrap a job so that an error is logged and never stops the scheduler."""

    def wrapper() -> None:
        try:
            job()
        except Exception as exc:
            log.exception("Scheduled run failed")
            if on_error:
                try:
                    on_error(exc)
                except Exception:
                    log.exception("Could not report the failure")

    return wrapper


def build_scheduler(settings: Settings, job: Callable[[], object] | None = None) -> BlockingScheduler:
    """Create the scheduler with one cron job per run time. Raise ValueError on bad settings."""
    tz = ZoneInfo(settings.timezone)  # raises ZoneInfoNotFoundError (a KeyError) if unknown
    run = job or (lambda: run_once(settings))

    def notify(exc: Exception) -> None:
        if settings.discord_webhook_url:
            send_failure(settings.discord_webhook_url, exc, secret_values(settings))
    scheduler = BlockingScheduler(timezone=tz)
    for hour, minute in settings.parsed_run_times():
        scheduler.add_job(
            _safe(run, notify),
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=f"summary-{hour:02d}{minute:02d}",
            coalesce=True,  # if several runs were missed, run once
            misfire_grace_time=3600,  # still run if the Pi was busy for up to 1 hour
            max_instances=1,
        )
    return scheduler


def serve(settings: Settings) -> None:
    scheduler = build_scheduler(settings)
    for job in scheduler.get_jobs():
        log.info("Scheduled %s (%s)", job.id, job.trigger)
    log.info("Timezone %s. Waiting for the next run. Press Ctrl+C to stop.", settings.timezone)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopped")
