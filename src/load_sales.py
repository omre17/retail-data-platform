"""Replace the PostgreSQL staging table with validated historical sales."""

import argparse
import csv
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from src.clean_sales import REQUIRED


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
INSERT = """
    INSERT INTO staging.sales_lines (
        order_id, line_number, order_date, customer_id,
        product_id, quantity, unit_price, status
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def run(input_path: Path) -> int:
    load_dotenv(ROOT / ".env")
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in the project .env file")

    with input_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or set(REQUIRED) - set(reader.fieldnames):
            raise ValueError("Input must be the clean_sales.csv produced by src.clean_sales")
        rows = [
            (
                row["order_id"], int(row["line_number"]),
                date.fromisoformat(row["order_date"]), row["customer_id"],
                row["product_id"], int(row["quantity"]),
                Decimal(row["unit_price"]), row["status"],
            )
            for row in reader
        ]
    if not rows:
        raise ValueError("Refusing to replace staging.sales_lines with an empty file")

    # Both the replacement and inserts commit together; a failure rolls them back.
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute((ROOT / "sql" / "staging.sql").read_text(encoding="utf-8"))
            cursor.execute("TRUNCATE TABLE staging.sales_lines")
            cursor.executemany(INSERT, rows)

    LOGGER.info("Full load finished: %d rows in staging.sales_lines", len(rows))
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.input)
