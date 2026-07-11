"""
Minimal reader for Rivendell's /etc/rd.conf file.

rd.conf is a standard INI file. The section we care about is [mySQL],
with keys Hostname, Loginname, Password, Database, and optionally Port.
"""
import configparser
from dataclasses import dataclass
from pathlib import Path

from .config import RD_CONF_PATH


@dataclass
class DbCreds:
    host: str
    port: int
    user: str
    password: str
    database: str


class RdConfError(Exception):
    pass


def load_db_creds(path: str = RD_CONF_PATH) -> DbCreds:
    conf_path = Path(path)
    if not conf_path.exists():
        raise RdConfError(f"rd.conf not found at {path}")

    parser = configparser.ConfigParser()
    # rd.conf keys are case-sensitive in practice; configparser lowercases
    # option names by default, so we preserve case via optionxform.
    parser.optionxform = str
    read_files = parser.read(conf_path)
    if not read_files:
        raise RdConfError(f"Could not read rd.conf at {path} (check permissions)")

    if "mySQL" not in parser:
        raise RdConfError("No [mySQL] section found in rd.conf")

    section = parser["mySQL"]
    try:
        return DbCreds(
            host=section.get("Hostname", "localhost"),
            port=int(section.get("Port", "3306")),
            user=section["Loginname"],
            password=section.get("Password", ""),
            database=section.get("Database", "Rivendell"),
        )
    except KeyError as e:
        raise RdConfError(f"Missing required key in [mySQL] section: {e}")
