"""
Read-only queries against the Rivendell MySQL database.

We deliberately keep this app's DB footprint tiny and read-only: it never
writes to Rivendell's tables directly. All actual imports are delegated
to rdimport itself, which is the supported way to mutate the database.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

import pymysql
import pymysql.cursors

from .rdconf import DbCreds


@dataclass
class Group:
    name: str
    description: str
    low_cart: int
    high_cart: int


def _connect(creds: DbCreds):
    return pymysql.connect(
        host=creds.host,
        port=creds.port,
        user=creds.user,
        password=creds.password,
        database=creds.database,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def list_groups(creds: DbCreds) -> List[Group]:
    sql = (
        "SELECT NAME, DESCRIPTION, DEFAULT_LOW_CART, DEFAULT_HIGH_CART "
        "FROM GROUPS ORDER BY NAME"
    )
    conn = _connect(creds)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        Group(
            name=row["NAME"],
            description=row.get("DESCRIPTION") or "",
            low_cart=row["DEFAULT_LOW_CART"],
            high_cart=row["DEFAULT_HIGH_CART"],
        )
        for row in rows
    ]


@dataclass
class SchedCode:
    code: str
    description: str


def list_scheduler_codes(creds: DbCreds) -> List[SchedCode]:
    sql = "SELECT CODE, DESCRIPTION FROM SCHED_CODES ORDER BY CODE"
    conn = _connect(creds)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SchedCode(code=row["CODE"], description=row.get("DESCRIPTION") or "")
        for row in rows
    ]


@dataclass
class Service:
    name: str
    description: str
    name_template: str


def list_services(creds: DbCreds) -> List[Service]:
    sql = "SELECT NAME, DESCRIPTION, NAME_TEMPLATE FROM SERVICES ORDER BY NAME"
    conn = _connect(creds)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        Service(
            name=row["NAME"],
            description=row.get("DESCRIPTION") or "",
            name_template=row.get("NAME_TEMPLATE") or "",
        )
        for row in rows
    ]


@dataclass
class LogStatus:
    traffic_linked: bool
    chained: bool


def log_statuses(creds: DbCreds, service: str, names: List[str]) -> Dict[str, LogStatus]:
    """Given a service and a list of candidate LOGS.NAME values, returns a
    dict of the subset that already exist (LOG_EXISTS='Y') to their
    traffic-merge and chain-to-next-log state. Rivendell has no date column
    on LOGS — the date is baked into NAME via the service's own
    NAME_TEMPLATE — so callers render dates to names themselves (see
    scheduler.render_log_name).

    Traffic-merge state reads LOGS.TRAFFIC_LINKED directly. "Chained to
    next log" has no dedicated column: Rivendell represents it as a
    LOG_LINES row with TYPE=5 and SOURCE=3 (its LABEL holds the next log's
    name) — confirmed against a reference DB dump, where 933 of 934 real
    generated logs carried exactly one such row as their final line.
    """
    if not names:
        return {}
    placeholders = ",".join(["%s"] * len(names))

    conn = _connect(creds)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT NAME, TRAFFIC_LINKED FROM LOGS WHERE SERVICE=%s "
                f"AND LOG_EXISTS='Y' AND NAME IN ({placeholders})",
                [service, *names],
            )
            log_rows = cur.fetchall()

            cur.execute(
                f"SELECT DISTINCT LOG_NAME FROM LOG_LINES WHERE TYPE=5 "
                f"AND SOURCE=3 AND LOG_NAME IN ({placeholders})",
                names,
            )
            chained_names = {row["LOG_NAME"] for row in cur.fetchall()}
    finally:
        conn.close()

    return {
        row["NAME"]: LogStatus(
            traffic_linked=row["TRAFFIC_LINKED"] == "Y",
            chained=row["NAME"] in chained_names,
        )
        for row in log_rows
    }


def cart_exists(creds: DbCreds, cart_number: int) -> Optional[str]:
    """Returns the cart's group name if it exists, else None."""
    sql = "SELECT GROUP_NAME FROM CART WHERE NUMBER = %s"
    conn = _connect(creds)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (cart_number,))
            row = cur.fetchone()
    finally:
        conn.close()

    return row["GROUP_NAME"] if row else None
