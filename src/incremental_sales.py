"""Apply a small CSV batch to existing staging and warehouse sales atomically."""

import argparse
import csv
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from src import build_warehouse, clean_sales


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)


def run(
    input_path: Path, output_dir: Path, products_path: Path | None = None,
    source_watermark: tuple[str, int] | None = None,
) -> dict[str, int]:
    counts = clean_sales.run(input_path, output_dir)
    if counts["clean"] == 0:
        raise ValueError("The batch has no valid sales lines")

    with (output_dir / "clean_sales.csv").open(newline="", encoding="utf-8") as source:
        sales = list(csv.DictReader(source))
    customers = build_warehouse.read_customers(ROOT / "data/raw/customers.csv")
    products = build_warehouse.read_products(products_path or ROOT / "data/raw/products.json")
    build_warehouse.check_references(
        {row["customer_id"] for row in sales},
        {row["product_id"] for row in sales},
        customers, products,
    )

    load_dotenv(ROOT / ".env")
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in the project .env file")

    # The database commits staging, dimensions, and facts together. A failed
    # statement rolls the whole batch back, including an updated order line.
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM staging.sales_lines")
            if cursor.fetchone()[0] == 0:
                raise ValueError("Load the historical sales with src.run_pipeline first")

            # Existing business IDs keep their dimension keys. Lookup changes
            # update names/categories without rebuilding the warehouse.
            cursor.executemany("""
                INSERT INTO dwh.dim_customer (customer_id, customer_name, city)
                VALUES (%s, %s, %s)
                ON CONFLICT (customer_id) DO UPDATE SET
                    customer_name = EXCLUDED.customer_name, city = EXCLUDED.city
            """, customers)
            cursor.executemany("""
                INSERT INTO dwh.dim_product (product_id, product_name, category)
                VALUES (%s, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    product_name = EXCLUDED.product_name,
                    category = EXCLUDED.category
            """, products)

            for row in sales:
                key = (row["order_id"], int(row["line_number"]))
                order_date = date.fromisoformat(row["order_date"])
                cursor.execute("""
                    INSERT INTO staging.sales_lines (
                        order_id, line_number, order_date, customer_id,
                        product_id, quantity, unit_price, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (order_id, line_number) DO UPDATE SET
                        order_date = EXCLUDED.order_date,
                        customer_id = EXCLUDED.customer_id,
                        product_id = EXCLUDED.product_id,
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        status = EXCLUDED.status
                """, (
                    *key, order_date, row["customer_id"], row["product_id"],
                    int(row["quantity"]), Decimal(row["unit_price"]), row["status"],
                ))

                if row["status"] == "canceled":
                    cursor.execute(
                        "DELETE FROM dwh.fact_sales WHERE order_id = %s AND line_number = %s",
                        key,
                    )
                    continue

                cursor.execute("""
                    INSERT INTO dwh.dim_date (date_key, full_date, year, month, day)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (date_key) DO NOTHING
                """, (
                    int(order_date.strftime("%Y%m%d")), order_date,
                    order_date.year, order_date.month, order_date.day,
                ))
                cursor.execute("""
                    INSERT INTO dwh.fact_sales (
                        order_id, line_number, date_key, customer_key, product_key,
                        quantity, unit_price, revenue_ils
                    )
                    SELECT s.order_id, s.line_number, d.date_key,
                           c.customer_key, p.product_key,
                           s.quantity, s.unit_price, s.quantity * s.unit_price
                    FROM staging.sales_lines AS s
                    JOIN dwh.dim_date AS d ON d.full_date = s.order_date
                    JOIN dwh.dim_customer AS c ON c.customer_id = s.customer_id
                    JOIN dwh.dim_product AS p ON p.product_id = s.product_id
                    WHERE s.order_id = %s AND s.line_number = %s
                      AND s.status = 'completed'
                    ON CONFLICT (order_id, line_number) DO UPDATE SET
                        date_key = EXCLUDED.date_key,
                        customer_key = EXCLUDED.customer_key,
                        product_key = EXCLUDED.product_key,
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        revenue_ils = EXCLUDED.revenue_ils
                """, key)
                if cursor.rowcount != 1:
                    raise ValueError(f"Could not load sale {key}")

            cursor.execute("SELECT COUNT(*) FROM staging.sales_lines")
            staging_total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM dwh.fact_sales")
            facts_total = cursor.fetchone()[0]

            # Commit the warehouse rows and source progress together. If this
            # transaction fails, the next run replays the same source events.
            if source_watermark is not None:
                cursor.execute("""
                    INSERT INTO control.source_watermarks (source_name, last_event_id)
                    VALUES (%s, %s)
                    ON CONFLICT (source_name) DO UPDATE SET
                        last_event_id = EXCLUDED.last_event_id
                """, source_watermark)

    result = {**counts, "staging_total": staging_total, "facts_total": facts_total}
    LOGGER.info("Incremental batch finished: %s", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(args.input, args.output_dir)
    except Exception:
        LOGGER.exception("Incremental batch failed")
        raise SystemExit(1)
