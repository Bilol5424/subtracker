"""Core domain logic: the Subscription model and all billing math.

This module has no dependencies on storage or the web layer so it stays
trivially testable.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, asdict
from datetime import date, timedelta

# Supported billing cycles and how many months each spans. Weekly is handled
# separately because it does not map cleanly onto months.
CYCLES = ("weekly", "monthly", "quarterly", "yearly")

# How many days ahead counts as "due soon" by default.
DUE_SOON_DAYS = 5


def add_cycle(start: date, cycle: str) -> date:
    """Return the next charge date one billing cycle after ``start``."""
    if cycle == "weekly":
        return start + timedelta(days=7)
    months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(cycle)
    if months is None:
        raise ValueError(f"unknown cycle: {cycle!r}")
    return _add_months(start, months)


def _add_months(d: date, months: int) -> date:
    """Add whole months to a date, clamping the day to the month's length."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def roll_forward(next_charge: date, cycle: str, today: date | None = None) -> date:
    """Advance a past charge date forward until it is today or in the future."""
    today = today or date.today()
    guard = 0
    while next_charge < today and guard < 600:
        next_charge = add_cycle(next_charge, cycle)
        guard += 1
    return next_charge


@dataclass
class Subscription:
    name: str
    amount: float
    currency: str = "USD"
    cycle: str = "monthly"
    next_charge: date | None = None
    category: str = "other"
    active: bool = True
    id: int | None = None

    def __post_init__(self) -> None:
        if self.cycle not in CYCLES:
            raise ValueError(f"cycle must be one of {CYCLES}, got {self.cycle!r}")
        if self.amount < 0:
            raise ValueError("amount must be non-negative")
        if isinstance(self.next_charge, str):
            self.next_charge = date.fromisoformat(self.next_charge)

    @property
    def monthly_cost(self) -> float:
        """Amount normalized to a per-month figure for fair comparison."""
        factors = {
            "weekly": 52 / 12,
            "monthly": 1,
            "quarterly": 1 / 3,
            "yearly": 1 / 12,
        }
        return round(self.amount * factors[self.cycle], 2)

    @property
    def yearly_cost(self) -> float:
        return round(self.monthly_cost * 12, 2)

    def days_until(self, today: date | None = None) -> int | None:
        if self.next_charge is None:
            return None
        today = today or date.today()
        upcoming = roll_forward(self.next_charge, self.cycle, today)
        return (upcoming - today).days

    def is_due_soon(self, within: int = DUE_SOON_DAYS, today: date | None = None) -> bool:
        d = self.days_until(today)
        return d is not None and 0 <= d <= within

    def to_dict(self, today: date | None = None) -> dict:
        data = asdict(self)
        data["next_charge"] = self.next_charge.isoformat() if self.next_charge else None
        data["monthly_cost"] = self.monthly_cost
        data["yearly_cost"] = self.yearly_cost
        data["days_until"] = self.days_until(today)
        data["due_soon"] = self.is_due_soon(today=today)
        return data


def summarize(subs: list[Subscription], today: date | None = None) -> dict:
    """Aggregate active subscriptions into totals and an upcoming-charges list.

    Totals are grouped per currency so we never silently add euros to dollars.
    """
    today = today or date.today()
    active = [s for s in subs if s.active]

    monthly: dict[str, float] = {}
    yearly: dict[str, float] = {}
    for s in active:
        monthly[s.currency] = round(monthly.get(s.currency, 0) + s.monthly_cost, 2)
        yearly[s.currency] = round(yearly.get(s.currency, 0) + s.yearly_cost, 2)

    upcoming = sorted(
        (s for s in active if s.days_until(today) is not None),
        key=lambda s: s.days_until(today),
    )

    return {
        "count": len(active),
        "monthly_total": monthly,
        "yearly_total": yearly,
        "upcoming": [s.to_dict(today) for s in upcoming[:10]],
    }
