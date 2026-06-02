"""Detect recurring subscriptions from a bank-statement CSV.

This is the feature that makes the project worth using: instead of typing
every subscription by hand, drop in an exported statement and let the tool
surface the charges that look recurring. It only *suggests* candidates --
the user confirms before anything is saved.
"""

from __future__ import annotations

import csv
import io
import re
import statistics
from dataclasses import dataclass
from datetime import date


@dataclass
class Candidate:
    name: str
    amount: float
    currency: str
    cycle: str
    next_charge: date
    occurrences: int
    confidence: float  # 0..1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "amount": self.amount,
            "currency": self.currency,
            "cycle": self.cycle,
            "next_charge": self.next_charge.isoformat(),
            "occurrences": self.occurrences,
            "confidence": round(self.confidence, 2),
        }


# Map a typical gap between charges (in days) to a billing cycle.
_GAP_TO_CYCLE = [
    (7, "weekly", 4),
    (30, "monthly", 8),
    (91, "quarterly", 20),
    (365, "yearly", 30),
]

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d")


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return _strptime(value, fmt)
        except ValueError:
            continue
    return None


def _strptime(value: str, fmt: str) -> date:
    from datetime import datetime

    return datetime.strptime(value, fmt).date()


def _parse_amount(value: str) -> float | None:
    value = value.strip().replace(" ", "")
    # Handle "1.234,56" (EU) vs "1,234.56" (US) and stray currency symbols.
    value = re.sub(r"[^\d,.\-]", "", value)
    if not value:
        return None
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _normalize_name(desc: str) -> str:
    """Reduce a noisy transaction memo to a stable merchant key."""
    desc = desc.lower()
    desc = re.sub(r"[*#]\w+", " ", desc)            # ref codes like *A1B2
    desc = re.sub(r"\b\d[\d.\-/]*\b", " ", desc)     # bare numbers and dates
    desc = re.sub(r"[^a-z\s]", " ", desc)            # punctuation
    tokens = [t for t in desc.split() if len(t) > 1]
    return " ".join(tokens[:3]).strip()


def _classify_gap(median_gap: float) -> tuple[str, float] | None:
    best = None
    for target, cycle, tolerance in _GAP_TO_CYCLE:
        if abs(median_gap - target) <= tolerance:
            score = 1 - abs(median_gap - target) / target
            if best is None or score > best[1]:
                best = (cycle, score)
    return best


def detect_recurring(
    csv_text: str,
    *,
    currency: str = "USD",
    today: date | None = None,
) -> list[Candidate]:
    """Parse a CSV and return likely recurring charges, best guesses first.

    Expected columns (case-insensitive, flexible order): a date column, a
    description/memo column, and an amount column. Outflows may be negative.
    """
    today = today or date.today()
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return []

    cols = {f.lower().strip(): f for f in reader.fieldnames}
    date_col = _find(cols, ("date", "posted", "transaction date"))
    desc_col = _find(cols, ("description", "memo", "details", "name", "merchant"))
    amount_col = _find(cols, ("amount", "value", "debit", "sum"))
    if not (date_col and desc_col and amount_col):
        return []

    groups: dict[str, list[tuple[date, float]]] = {}
    for row in reader:
        d = _parse_date(row.get(date_col, ""))
        amt = _parse_amount(row.get(amount_col, ""))
        if d is None or amt is None or amt == 0:
            continue
        amt = abs(amt)  # treat outflows uniformly
        key = _normalize_name(row.get(desc_col, ""))
        if not key:
            continue
        groups.setdefault(key, []).append((d, amt))

    candidates: list[Candidate] = []
    for key, txns in groups.items():
        if len(txns) < 2:
            continue
        txns.sort(key=lambda t: t[0])
        dates = [t[0] for t in txns]
        amounts = [t[1] for t in txns]

        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        median_gap = statistics.median(gaps)
        classified = _classify_gap(median_gap)
        if classified is None:
            continue
        cycle, gap_score = classified

        # Recurring charges have stable amounts; penalise wild variance.
        median_amt = round(statistics.median(amounts), 2)
        spread = (max(amounts) - min(amounts)) / median_amt if median_amt else 1
        amount_score = max(0.0, 1 - spread)
        confidence = round(0.5 * gap_score + 0.3 * amount_score + 0.2 * min(len(txns) / 4, 1), 3)

        from .core import add_cycle

        next_charge = add_cycle(dates[-1], cycle)
        while next_charge < today:
            next_charge = add_cycle(next_charge, cycle)

        candidates.append(
            Candidate(
                name=key.title(),
                amount=median_amt,
                currency=currency,
                cycle=cycle,
                next_charge=next_charge,
                occurrences=len(txns),
                confidence=confidence,
            )
        )

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def _find(cols: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in cols:
            return cols[c]
    # fall back to substring match
    for key, original in cols.items():
        if any(c in key for c in candidates):
            return original
    return None
