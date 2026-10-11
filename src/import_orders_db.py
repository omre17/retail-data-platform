"""Import new order events from the operational source schema."""

import argparse
import csv
import json
import logging
import os
from pathlib import Path

import pandas as pd

from src import clean_sales


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
SOURCE_NAME = "source_orders"


def latest_lines(events: list[dict]) -> list[dict]:
    """Keep the final version of each line while retaining source event order."""
    latest = {}
    for event in events:
        key = (event["order_id"], event["line_number"])
        latest[key] = event
    return [{field: event[field] for field in clean_sales.REQUIRED}
            for event in latest.values()]


def validated_lines(events: list[dict]) -> list[dict]:
    """Reject a bad source batch before loading rows or advancing progress."""
    clean, rejected = clean_sales.validate_sales(pd.DataFrame(latest_lines(events)))
    if len(rejected):
        raise ValueError(
            f"Source database supplied {len(rejected)} invalid order lines: "
            f"{rejected.iloc[0]['rejection_reason']}"
        )
    return clean.to_dict("records")


def run(output_dir: Path) -> dict[str, int]:
    import psycopg
    from dotenv import load_dotenv
    from psycopg.rows import dict_row

    from src import incremental_sales

    load_dotenv(ROOT / ".env")
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in the project .env file")

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
    ) as target:
        with target.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS control")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS control.source_watermarks (
                    source_name TEXT PRIMARY KEY,
                    last_event_id BIGINT NOT NULL CHECK (last_event_id >= 0)
                )
            """)
            cursor.execute(
                "SELECT last_event_id FROM control.source_watermarks WHERE source_name = %s",
                (SOURCE_NAME,),
            )
            record = cursor.fetchone()
            last_event_id = record[0] if record else 0

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="retail", user="retail", password=password,
        row_factory=dict_row,
    ) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute("""
                SELECT event_id, order_id, line_number, order_date,
                       customer_id, product_id, quantity, unit_price, status
                FROM source.order_events
                WHERE event_id > %s
                ORDER BY event_id
            """, (last_event_id,))
            events = cursor.fetchall()

    if not events:
        result = {"new_events": 0, "last_event_id": last_event_id}
        LOGGER.info("No new source database events: %s", result)
        return result

    lines = validated_lines(events)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_events.json").write_text(
        json.dumps(events, indent=2, default=str), encoding="utf-8",
    )
    input_path = output_dir / "source_lines.csv"
    with input_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=clean_sales.REQUIRED)
        writer.writeheader()
        writer.writerows(lines)

    newest_event_id = events[-1]["event_id"]
    loaded = incremental_sales.run(
        input_path, output_dir, source_watermark=(SOURCE_NAME, newest_event_id),
    )
    result = {**loaded, "new_events": len(events), "last_event_id": newest_event_id}
    LOGGER.info("Source database import finished: %s", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/output/source_db")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(args.output_dir)
    except Exception:
        LOGGER.exception("Source database import failed")
        raise SystemExit(1)
