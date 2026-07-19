"""
Configuration for the Rivendell import web app.

All values can be overridden via environment variables so this can be
deployed without editing source. Sensible defaults assume a typical
Rivendell host.
"""
import os
from pathlib import Path

# Path to Rivendell's own config file, where DB credentials live under [mySQL]
RD_CONF_PATH = os.environ.get("RD_CONF_PATH", "/etc/rd.conf")

# The ONLY directory tree the web UI is allowed to browse/import from.
# This is a hard safety boundary — never let the browse/import endpoints
# escape this root, since this app runs with DB credentials loaded.
IMPORT_ROOT = Path(os.environ.get("RD_IMPORT_ROOT", "/home/rd/import")).resolve()

# rdimport binary — assumed on PATH unless overridden
RDIMPORT_BIN = os.environ.get("RDIMPORT_BIN", "rdimport")

# rdlogmanager binary — assumed on PATH unless overridden
RDLOGMANAGER_BIN = os.environ.get("RDLOGMANAGER_BIN", "rdlogmanager")

# File extensions treated as importable audio when walking a folder
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aif", ".aiff"}

# How long a single rdimport invocation is allowed to run before we give up
# and report a timeout (seconds). Large folders may need this raised.
IMPORT_TIMEOUT_SECONDS = int(os.environ.get("RD_IMPORT_TIMEOUT", "1800"))

# How long a single rdlogmanager invocation (one day's -g[/-t] run) is
# allowed to run before we give up (seconds). A schedule batch runs one
# call per selected date sequentially, so this bounds each step. This is
# just the server-side fallback — the Scheduler tab's Advanced options let
# the user override it per run (in minutes) from the UI. Generous default
# since a full generate+traffic-merge can be slow against a remote DB on
# modest hardware (e.g. a Raspberry Pi host).
SCHEDULER_TIMEOUT_SECONDS = int(os.environ.get("RD_SCHEDULER_TIMEOUT", str(30 * 60)))

# Where the Scheduler tab's Auto Scheduling rule (weekday/time/days-ahead,
# plus its last-run result) is persisted as JSON. Both the web app and the
# rd-auto-schedule systemd timer's entry point (app/auto_schedule_runner.py)
# read/write this file, so it must be reachable by whatever user runs each
# of those (install-service.sh runs both under the same service user).
AUTO_SCHEDULE_CONFIG_PATH = os.environ.get(
    "RD_AUTO_SCHEDULE_CONFIG_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "auto_schedule.json"),
)
