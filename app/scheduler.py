"""
Date/name math for Rivendell logs, and the rdlogmanager subprocess wrapper.

Kept DB-free, mirroring importer.py's separation from db.py: callers
(main.py) combine this module's pure functions with db.py's query
functions themselves.
"""
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from .config import RDLOGMANAGER_BIN, SCHEDULER_TIMEOUT_SECONDS


def render_log_name(name_template: str, d: date) -> str:
    """Renders a Rivendell LOGS.NAME for a date from a service's
    NAME_TEMPLATE (a strftime-compatible template, e.g. '7EDG-%d%m%Y')."""
    return d.strftime(name_template)


def day_offset(target: date, today: Optional[date] = None) -> int:
    """
    rdlogmanager's -d value is a day offset ADDED TO TOMORROW, not today:
    -d 0 = tomorrow, -d -1 = today, -d 1 = day after tomorrow.
    """
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    return (target - tomorrow).days


@dataclass
class DayResult:
    date: date
    command: List[str] = field(default_factory=list)
    returncode: int = -1
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0


@dataclass
class BatchResult:
    days: List[DayResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(d.success for d in self.days)


# Grace period given to a timed-out rdlogmanager to exit cleanly after
# SIGTERM before we escalate to SIGKILL. A bare SIGKILL gives it no chance
# to release its own database-level lock on the log row, which then blocks
# every future attempt to (re)generate that day until the stale lock is
# manually cleared.
TERMINATE_GRACE_SECONDS = 15


def run_rdlogmanager_for_date(
    service: str,
    target_date: date,
    import_traffic: bool,
    today: Optional[date] = None,
    timeout_seconds: Optional[int] = None,
) -> DayResult:
    """
    Invokes rdlogmanager to generate (and optionally traffic-merge) the log
    for a single date. Mirrors the station's own cron script, which
    combines -g and -t in one invocation per day.

    -P (protect/no-overwrite) is intentionally never passed — overwrite
    confirmation is a UI-only concern (see main.py), not a CLI flag; this
    always (re)generates.
    """
    if timeout_seconds is None:
        timeout_seconds = SCHEDULER_TIMEOUT_SECONDS

    offset = day_offset(target_date, today)
    cmd = [RDLOGMANAGER_BIN, "-g"]
    if import_traffic:
        cmd.append("-t")
    cmd += ["-s", service, "-d", str(offset)]

    # subprocess failures (timeout, missing binary, etc.) must surface as a
    # per-day result, not an unhandled exception — an uncaught exception
    # here would bubble up through run_batch into the FastAPI endpoint and
    # produce a non-JSON 500 response, breaking the client's res.json().
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except OSError as e:
        return DayResult(
            date=target_date,
            command=cmd,
            returncode=-1,
            stdout="",
            stderr=f"Failed to run rdlogmanager: {e}",
        )

    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return DayResult(
            date=target_date,
            command=cmd,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        pass

    # It timed out. Ask nicely first (SIGTERM) and give it a chance to
    # clean up — e.g. release its own lock on the log row — before
    # force-killing.
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=TERMINATE_GRACE_SECONDS)
        timeout_note = (
            f"rdlogmanager did not finish within {timeout_seconds}s — "
            "terminated (SIGTERM)"
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            # SIGKILL guarantees the process itself dies, but communicate()
            # still blocks until its stdout/stderr pipes see EOF — if it
            # left behind a child of its own that inherited those same
            # pipe fds, communicate() would hang until THAT process exits
            # too. Bound this wait so we can never block indefinitely.
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        timeout_note = (
            f"rdlogmanager did not finish within {timeout_seconds}s and did "
            f"not exit within {TERMINATE_GRACE_SECONDS}s of SIGTERM — "
            "force-killed (SIGKILL). It may not have released its lock on "
            "this log; check for a stale lock if the next attempt reports "
            "'log in use'."
        )

    return DayResult(
        date=target_date,
        command=cmd,
        returncode=-1,
        stdout=stdout or "",
        stderr=f"{stderr or ''}\n{timeout_note}".strip(),
    )


def run_batch(
    service: str,
    dates: List[date],
    import_traffic: bool,
    timeout_seconds: Optional[int] = None,
) -> BatchResult:
    """Runs rdlogmanager once per date, sequentially, continuing through
    any individual day's failure (matches the reference cron script,
    which doesn't abort the loop on error)."""
    today = date.today()
    results = [
        run_rdlogmanager_for_date(service, d, import_traffic, today, timeout_seconds)
        for d in sorted(dates)
    ]
    return BatchResult(days=results)
