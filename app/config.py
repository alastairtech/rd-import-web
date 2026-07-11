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

# File extensions treated as importable audio when walking a folder
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aif", ".aiff"}

# How long a single rdimport invocation is allowed to run before we give up
# and report a timeout (seconds). Large folders may need this raised.
IMPORT_TIMEOUT_SECONDS = int(os.environ.get("RD_IMPORT_TIMEOUT", "1800"))
