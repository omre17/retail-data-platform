"""Check that completed staged order lines match their warehouse facts."""

import logging
import os

import psycopg


LOGGER = logging.getLogger(__name__)


def run() -> dict[str, int]:
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD")

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM staging.sales_lines WHERE status = 'completed'),
                    (SELECT COUNT(*) FROM dwh.fact_sales),
                    (SELECT COUNT(*) FROM dwh.fact_sales AS f
                     FULL JOIN staging.sales_lines AS s
                       ON (s.order_id, s.line_number) = (f.order_id, f.line_number)
                     WHERE (f.order_id IS NULL AND s.status = 'completed')
                        OR (f.order_id IS NOT NULL AND
                            (s.order_id IS NULL OR s.status <> 'completed'
                             OR f.quantity <> s.quantity
                             OR f.unit_price <> s.unit_price
                             OR f.revenue_ils <> s.quantity * s.unit_price)))
            """)
            completed, facts, mismatched = cursor.fetchone()
    if completed == 0 or completed != facts or mismatched:
        raise ValueError(
            f"Warehouse check failed: completed={completed}, facts={facts}, mismatched={mismatched}"
        )
    result = {"completed": completed, "facts": facts, "mismatched": mismatched}
    LOGGER.info("Warehouse check passed: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run()
