"""Run with:  python -m unittest discover -s tests"""

import unittest
from datetime import date

from subtracker.core import Subscription, add_cycle, roll_forward, summarize
from subtracker.importer import detect_recurring


class TestBillingMath(unittest.TestCase):
    def test_monthly_normalization(self):
        self.assertEqual(Subscription("A", 12, cycle="monthly").monthly_cost, 12.0)
        self.assertEqual(Subscription("B", 120, cycle="yearly").monthly_cost, 10.0)
        self.assertEqual(Subscription("C", 30, cycle="quarterly").monthly_cost, 10.0)
        weekly = Subscription("D", 10, cycle="weekly").monthly_cost
        self.assertAlmostEqual(weekly, 43.33, places=2)

    def test_yearly_cost(self):
        self.assertEqual(Subscription("A", 9.99, cycle="monthly").yearly_cost, 119.88)

    def test_add_cycle_month_end_clamp(self):
        # Jan 31 + 1 month should clamp to Feb 28 (2025 is not a leap year).
        self.assertEqual(add_cycle(date(2025, 1, 31), "monthly"), date(2025, 2, 28))
        self.assertEqual(add_cycle(date(2024, 1, 31), "monthly"), date(2024, 2, 29))

    def test_add_cycle_weekly_and_yearly(self):
        self.assertEqual(add_cycle(date(2025, 3, 1), "weekly"), date(2025, 3, 8))
        self.assertEqual(add_cycle(date(2025, 3, 1), "yearly"), date(2026, 3, 1))

    def test_roll_forward_past_date(self):
        result = roll_forward(date(2025, 1, 1), "monthly", today=date(2025, 3, 15))
        self.assertEqual(result, date(2025, 4, 1))

    def test_days_until_and_due_soon(self):
        today = date(2025, 6, 1)
        s = Subscription("X", 5, next_charge=date(2025, 6, 4), cycle="monthly")
        self.assertEqual(s.days_until(today), 3)
        self.assertTrue(s.is_due_soon(today=today))
        far = Subscription("Y", 5, next_charge=date(2025, 6, 25), cycle="monthly")
        self.assertFalse(far.is_due_soon(today=today))

    def test_invalid_cycle_rejected(self):
        with self.assertRaises(ValueError):
            Subscription("Bad", 5, cycle="daily")


class TestSummary(unittest.TestCase):
    def test_per_currency_totals(self):
        subs = [
            Subscription("A", 10, currency="USD", cycle="monthly"),
            Subscription("B", 120, currency="USD", cycle="yearly"),
            Subscription("C", 5, currency="EUR", cycle="monthly"),
            Subscription("D", 9, currency="USD", active=False),  # excluded
        ]
        s = summarize(subs, today=date(2025, 6, 1))
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["monthly_total"]["USD"], 20.0)
        self.assertEqual(s["monthly_total"]["EUR"], 5.0)


class TestRecurringDetection(unittest.TestCase):
    def test_detects_monthly_subscription(self):
        csv_text = (
            "date,description,amount\n"
            "2025-01-03,NETFLIX.COM 8829,-9.99\n"
            "2025-02-03,NETFLIX.COM 1021,-9.99\n"
            "2025-03-03,NETFLIX.COM 7766,-9.99\n"
            "2025-01-15,LOCAL COFFEE SHOP,-4.20\n"  # one-off, should be ignored
        )
        candidates = detect_recurring(csv_text, today=date(2025, 3, 10))
        self.assertTrue(candidates)
        top = candidates[0]
        self.assertIn("netflix", top.name.lower())
        self.assertEqual(top.cycle, "monthly")
        self.assertEqual(top.amount, 9.99)
        self.assertGreaterEqual(top.next_charge, date(2025, 3, 10))

    def test_handles_eu_number_format(self):
        csv_text = (
            "date,description,amount\n"
            "03.01.2025,SPOTIFY AB,-1.099,99\n"  # weird but exercises parser
            "03.02.2025,SPOTIFY AB,-1.099,99\n"
        )
        candidates = detect_recurring(csv_text)
        self.assertTrue(candidates)


if __name__ == "__main__":
    unittest.main()
