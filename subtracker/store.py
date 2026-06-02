"""SQLite persistence. Single file, no ORM, no dependencies."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from .core import Subscription

DEFAULT_DB = os.environ.get("SUBTRACKER_DB", "data/subtracker.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    amount      REAL    NOT NULL,
    currency    TEXT    NOT NULL DEFAULT 'USD',
    cycle       TEXT    NOT NULL DEFAULT 'monthly',
    next_charge TEXT,
    category    TEXT    NOT NULL DEFAULT 'other',
    active      INTEGER NOT NULL DEFAULT 1
);
"""


class Store:
    def __init__(self, path: str = DEFAULT_DB) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _row_to_sub(self, row: sqlite3.Row) -> Subscription:
        return Subscription(
            id=row["id"],
            name=row["name"],
            amount=row["amount"],
            currency=row["currency"],
            cycle=row["cycle"],
            next_charge=date.fromisoformat(row["next_charge"]) if row["next_charge"] else None,
            category=row["category"],
            active=bool(row["active"]),
        )

    def all(self) -> list[Subscription]:
        rows = self._conn.execute("SELECT * FROM subscriptions ORDER BY name").fetchall()
        return [self._row_to_sub(r) for r in rows]

    def add(self, sub: Subscription) -> Subscription:
        cur = self._conn.execute(
            """INSERT INTO subscriptions
               (name, amount, currency, cycle, next_charge, category, active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sub.name,
                sub.amount,
                sub.currency,
                sub.cycle,
                sub.next_charge.isoformat() if sub.next_charge else None,
                sub.category,
                int(sub.active),
            ),
        )
        self._conn.commit()
        sub.id = cur.lastrowid
        return sub

    def delete(self, sub_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def set_active(self, sub_id: int, active: bool) -> bool:
        cur = self._conn.execute(
            "UPDATE subscriptions SET active = ? WHERE id = ?", (int(active), sub_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
