"""Validate historical sales and produce staging and fact-preview CSVs."""

import argparse
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


REQUIRED = [
    "order_id", "line_number", "order_date", "customer_id", "product_id",
    "quantity", "unit_price", "status",
]
LOGGER = logging.getLogger(__name__)


def _whole_positive(value: str) -> int:
    number = int(value)
    if number <= 0 or str(number) != value:
        raise ValueError("must be a positive whole number")
    return number


def validate_sales(source: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return clean and rejected rows; the first valid occurrence of a key wins."""
    missing = set(REQUIRED) - set(source.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

    clean, rejected, seen = [], [], {}
    for raw in source[REQUIRED].fillna("").to_dict("records"):
        row = {key: str(value).strip() for key, value in raw.items()}
        reasons = []
        for key in REQUIRED:
            if not row[key]:
                reasons.append(f"missing {key}")

        numbers = {}
        for field in ("line_number", "quantity"):
            if not row[field]:
                continue  # The missing-field check has already explained this.
            try:
                numbers[field] = _whole_positive(row[field])
            except ValueError:
                reasons.append(f"invalid {field}")

        price = None
        if row["unit_price"]:
            try:
                price = Decimal(row["unit_price"])
                if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
                    raise ValueError
            except (InvalidOperation, ValueError):
                reasons.append("invalid unit_price")

        date = pd.to_datetime(row["order_date"], format="%Y-%m-%d", errors="coerce")
        if row["order_date"] and (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["order_date"]) or pd.isna(date)
        ):
            reasons.append("invalid order_date")
        if row["status"] and row["status"] not in {"completed", "canceled"}:
            reasons.append("invalid status")

        key = (row["order_id"], row["line_number"])
        if key in seen:
            reason = "duplicate order line" if row == seen[key] else "conflicting duplicate order line"
            reasons.append(reason)

        if reasons:
            rejected.append({**row, "rejection_reason": "; ".join(reasons)})
            continue

        seen[key] = row
        clean.append({
            **row,
            "line_number": numbers["line_number"],
            "order_date": date.strftime("%Y-%m-%d"),
            "quantity": numbers["quantity"],
            "unit_price": f"{price:.2f}",
        })

    return (
        pd.DataFrame(clean, columns=REQUIRED),
        pd.DataFrame(rejected, columns=REQUIRED + ["rejection_reason"]),
    )


def run(input_path: Path, output_dir: Path) -> dict[str, int]:
    source = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    clean, rejected = validate_sales(source)
    completed = clean.loc[clean["status"] == "completed"].copy()
    completed["revenue_ils"] = completed.apply(
        lambda row: f"{Decimal(row['unit_price']) * int(row['quantity']):.2f}", axis=1
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    clean.to_csv(output_dir / "clean_sales.csv", index=False)
    completed.to_csv(output_dir / "fact_sales_preview.csv", index=False)
    rejected.to_csv(output_dir / "rejected_sales.csv", index=False)
    counts = {"source": len(source), "clean": len(clean), "completed": len(completed), "rejected": len(rejected)}
    LOGGER.info("Sales processing finished: %s", counts)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.input, args.output_dir)
