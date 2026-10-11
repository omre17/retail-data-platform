import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.clean_sales import run, validate_sales


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/sales_sample.csv"


class CleanSalesTests(unittest.TestCase):
    def test_sample_rejects_bad_rows_and_excludes_canceled_revenue(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            counts = run(FIXTURE, output)
            self.assertEqual(counts, {"source": 7, "clean": 5, "completed": 4, "rejected": 2})
            fact = pd.read_csv(output / "fact_sales_preview.csv")
            self.assertEqual(round(fact["revenue_ils"].sum(), 2), 642.0)
            rejected = pd.read_csv(output / "rejected_sales.csv")
            self.assertTrue(rejected["rejection_reason"].str.contains("duplicate order line").any())
            self.assertTrue(rejected["rejection_reason"].str.contains("invalid quantity").any())

    def test_rerun_replaces_outputs_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run(FIXTURE, output)
            before = (output / "fact_sales_preview.csv").read_bytes()
            run(FIXTURE, output)
            self.assertEqual(before, (output / "fact_sales_preview.csv").read_bytes())

    def test_missing_column_fails_fast(self):
        with self.assertRaisesRegex(ValueError, "Missing columns"):
            validate_sales(pd.DataFrame({"order_id": ["1"]}))

    def test_missing_field_has_one_specific_reason(self):
        source = pd.read_csv(FIXTURE, dtype=str, keep_default_na=False)
        source.loc[0, "line_number"] = ""
        _, rejected = validate_sales(source)
        self.assertEqual(rejected.iloc[0]["rejection_reason"], "missing line_number")

    def test_date_requires_two_digit_month_and_day(self):
        source = pd.read_csv(FIXTURE, dtype=str, keep_default_na=False).iloc[:1].copy()
        source.loc[0, "order_date"] = "2026-9-1"
        clean, rejected = validate_sales(source)
        self.assertTrue(clean.empty)
        self.assertEqual(rejected.iloc[0]["rejection_reason"], "invalid order_date")

    def test_conflicting_duplicate_is_reported_separately(self):
        source = pd.read_csv(FIXTURE, dtype=str, keep_default_na=False).iloc[:1].copy()
        conflicting = source.copy()
        conflicting.loc[0, "quantity"] = "3"
        _, rejected = validate_sales(pd.concat([source, conflicting], ignore_index=True))
        self.assertEqual(rejected.iloc[0]["rejection_reason"], "conflicting duplicate order line")


if __name__ == "__main__":
    unittest.main()
