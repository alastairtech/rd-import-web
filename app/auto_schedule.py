"""
Persistence and due-check logic for the Scheduler tab's Auto Scheduling
rule.

Kept DB-free and subprocess-free, like scheduler.py — this module only
reads/writes AUTO_SCHEDULE_CONFIG_PATH and does date/time math. Both the
web app (app/main.py, for the UI) and the systemd timer's entry point
(app/auto_schedule_runner.py) import this module as their single source
of truth for the saved rule and its "did today's run already happen"
state, so the two can never disagree about what's configured.
"""
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from datetime import time as dtime
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

from .config import AUTO_SCHEDULE_CONFIG_PATH

WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]

# How often the systemd timer invokes the runner (see install-service.sh).
# A saved time is "due" if `now` falls in [time, time + this window) on the
# configured weekday, so a match can't be missed between two ticks.
CHECK_WINDOW_MINUTES = 15


@dataclass
class LastRun:
    date: str  # ISO date the run happened on
    success: bool
    days_run: int
    failed_days: int


@dataclass
class AutoScheduleConfig:
    enabled: bool = False
    service: str = ""
    weekday: int = 0  # Monday=0 .. Sunday=6, matches date.weekday()
    time: str = "03:00"  # 24-hour "HH:MM"
    days_ahead: int = 14
    import_traffic: bool = False
    timeout_minutes: Optional[int] = None
    last_run: Optional[LastRun] = None

    def target_time(self) -> dtime:
        hh, mm = self.time.split(":")
        return dtime(int(hh), int(mm))


def load_config(path: Optional[str] = None) -> AutoScheduleConfig:
    p = Path(path or AUTO_SCHEDULE_CONFIG_PATH)
    if not p.exists():
        return AutoScheduleConfig()

    data = json.loads(p.read_text())
    last_run_data = data.get("last_run")
    return AutoScheduleConfig(
        enabled=data.get("enabled", False),
        service=data.get("service", ""),
        weekday=data.get("weekday", 0),
        time=data.get("time", "03:00"),
        days_ahead=data.get("days_ahead", 14),
        import_traffic=data.get("import_traffic", False),
        timeout_minutes=data.get("timeout_minutes"),
        last_run=LastRun(**last_run_data) if last_run_data else None,
    )


def save_config(config: AutoScheduleConfig, path: Optional[str] = None) -> None:
    p = Path(path or AUTO_SCHEDULE_CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(config), indent=2))


def record_run(
    success: bool,
    days_run: int,
    failed_days: int,
    when: Optional[date] = None,
    path: Optional[str] = None,
) -> None:
    """Called by the runner after a due rule actually fires, so the next
    tick's is_due() check sees today as already handled, and the UI can
    show the result."""
    config = load_config(path)
    config.last_run = LastRun(
        date=(when or date.today()).isoformat(),
        success=success,
        days_run=days_run,
        failed_days=failed_days,
    )
    save_config(config, path)


def compute_dates(today: date, days_ahead: int) -> List[date]:
    """The rolling window a due run generates: the next `days_ahead` days
    starting tomorrow — mirrors rdlogmanager's own -d convention, where
    -d 0 is tomorrow (see scheduler.day_offset), so each run keeps a
    constant N-day buffer built ahead of today regardless of when it
    fires."""
    return [today + timedelta(days=n) for n in range(1, days_ahead + 1)]


def is_due(config: AutoScheduleConfig, now: datetime) -> bool:
    """True if `now` falls on the configured weekday, inside the
    configured time's check window, and today's run hasn't already
    happened — the last_run guard stops a second nearby timer tick (or a
    Persistent=true catch-up run after downtime) from firing twice in one
    day."""
    if not config.enabled or not config.service:
        return False
    if now.weekday() != config.weekday:
        return False
    if config.last_run and config.last_run.date == now.date().isoformat():
        return False

    target_dt = datetime.combine(now.date(), config.target_time())
    window_end = target_dt + timedelta(minutes=CHECK_WINDOW_MINUTES)
    return target_dt <= now < window_end
