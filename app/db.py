"""
Read-only queries against the Rivendell MySQL database.

We deliberately keep this app's DB footprint tiny and read-only: it never
writes to Rivendell's tables directly. All actual imports are delegated
to rdimport itself, which is the supported way to mutate the database.
"""
from dataclasses import dataclass
from typing import List, Optional

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
