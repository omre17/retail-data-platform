"""Full-refresh a small star schema from validated staging sales and lookups."""

import argparse
import csv
import json
import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
CUSTOMER_FIELDS = ("customer_id", "customer_name", "city")
PRODUCT_FIELDS = ("product_id", "product_name", "category")


def validate_lookup(records: list[dict], fields: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Reject incomplete or duplicate lookup IDs before changing the warehouse."""
    result = []
    seen = set()
    for number, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Lookup row {number} must be an object")
        values = []
        for field in fields:
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Lookup row {number} has missing or invalid {field}")
            values.append(value.strip())
        if values[0] in seen:
            raise ValueError(f"Duplicate {fields[0]}: {values[0]}")
        seen.add(values[0])
        result.append(tuple(values))
    if not result:
        raise ValueError("Lookup file cannot be empty")
    return sorted(result)


def read_customers(path: Path) -> list[tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or set(CUSTOMER_FIELDS) - set(reader.fieldnames):
            raise ValueError(f"Customer CSV needs columns: {', '.join(CUSTOMER_FIELDS)}")
        return validate_lookup(list(reader), CUSTOMER_FIELDS)


def read_products(path: Path) -> list[tuple[str, ...]]:
    with path.open(encoding="utf-8-sig") as source:
        records = json.load(source)
    if not isinstance(records, list):
        raise ValueError("Product JSON must be a list of objects")
    return validate_lookup(records, PRODUCT_FIELDS)


def check_references(
    sales_customers: set[str], sales_products: set[str],
    customers: list[tuple[str, ...]], products: list[tuple[str, ...]],
) -> None:
    missing_customers = sales_customers - {row[0] for row in customers}
    missing_products = sales_products - {row[0] for row in products}
    if missing_customers or missing_products:
        raise ValueError(
            f"Sales reference unknown customer IDs: {sorted(missing_customers)}; "
            f"product IDs: {sorted(missing_products)}"
        )


def run(customers_path: Path, products_path: Path) -> dict[str, int]:
    import psycopg
    from dotenv import load_dotenv

    customers = read_customers(customers_path)
    products = read_products(products_path)
    load_dotenv(ROOT / ".env")
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in the project .env file")

    # On error, psycopg rolls back the entire transaction, including the TRUNCATE.
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT customer_id, product_id, status FROM staging.sales_lines")
            sales = cursor.fetchall()
            if not sales:
                raise ValueError("staging.sales_lines is empty; run src.load_sales first")
            check_references(
                {row[0] for row in sales}, {row[1] for row in sales},
                customers, products,
            )
            expected_facts = sum(row[2] == "completed" for row in sales)

            cursor.execute((ROOT / "sql" / "warehouse.sql").read_text(encoding="utf-8"))
            cursor.execute(
                "TRUNCATE dwh.fact_sales, dwh.dim_date, dwh.dim_customer, "
                "dwh.dim_product RESTART IDENTITY"
            )
            cursor.executemany(
                "INSERT INTO dwh.dim_customer (customer_id, customer_name, city) "
                "VALUES (%s, %s, %s)", customers,
            )
            cursor.executemany(
                "INSERT INTO dwh.dim_product (product_id, product_name, category) "
                "VALUES (%s, %s, %s)", products,
            )
            cursor.execute("""
                INSERT INTO dwh.dim_date (date_key, full_date, year, month, day)
                SELECT TO_CHAR(order_date, 'YYYYMMDD')::integer, order_date,
                       EXTRACT(YEAR FROM order_date)::smallint,
                       EXTRACT(MONTH FROM order_date)::smallint,
                       EXTRACT(DAY FROM order_date)::smallint
                FROM staging.sales_lines
                WHERE status = 'completed'
                GROUP BY order_date
            """)
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
                WHERE s.status = 'completed'
            """)
            cursor.execute("SELECT COUNT(*) FROM dwh.fact_sales")
            actual_facts = cursor.fetchone()[0]
            if actual_facts != expected_facts:
                raise ValueError(
                    f"Expected {expected_facts} fact rows, got {actual_facts}"
                )

    counts = {"customers": len(customers), "products": len(products), "sales": actual_facts}
    LOGGER.info("Warehouse full refresh finished: %s", counts)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=Path, default=ROOT / "data/raw/customers.csv")
    parser.add_argument("--products", type=Path, default=ROOT / "data/raw/products.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.customers, args.products)
