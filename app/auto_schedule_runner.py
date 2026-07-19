"""
Entry point for the rd-auto-schedule systemd timer (see
install-service.sh). Invoked every CHECK_WINDOW_MINUTES; does nothing
unless the Auto Scheduling rule saved from the Scheduler tab is enabled
and due right now, in which case it runs rdlogmanager for the configured
rolling window, same as a manual Scheduler tab run.

Run as `python -m app.auto_schedule_runner` with WorkingDirectory set to
the project root (matches how the main uvicorn service is invoked), so
that `app` resolves as a package without extra sys.path setup.
"""
from datetime import datetime

from . import scheduler
from .auto_schedule import compute_dates, is_due, load_config, record_run


def main() -> None:
    config = load_config()
    now = datetime.now()
    if not is_due(config, now):
        return

    dates = compute_dates(now.date(), config.days_ahead)
    timeout_seconds = config.timeout_minutes * 60 if config.timeout_minutes else None
    result = scheduler.run_batch(config.service, dates, config.import_traffic, timeout_seconds)

    failed_days = sum(1 for d in result.days if not d.success)
    record_run(
        success=result.success,
        days_run=len(result.days),
        failed_days=failed_days,
        when=now.date(),
    )


if __name__ == "__main__":
    main()
