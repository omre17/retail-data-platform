"""Run the full local CSV-to-warehouse pipeline in one command."""

import argparse
import csv
import logging
from pathlib import Path

from src import build_warehouse, clean_sales, load_sales


LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def run(input_path: Path, output_dir: Path) -> dict[str, int]:
    LOGGER.info("Pipeline started: %s", input_path)
    counts = clean_sales.run(input_path, output_dir)
    customers_path = ROOT / "data/raw/customers.csv"
    products_path = ROOT / "data/raw/products.json"
    with (output_dir / "clean_sales.csv").open(newline="", encoding="utf-8") as source:
        sales = list(csv.DictReader(source))
    build_warehouse.check_references(
        {row["customer_id"] for row in sales},
        {row["product_id"] for row in sales},
        build_warehouse.read_customers(customers_path),
        build_warehouse.read_products(products_path),
    )
    staging_count = load_sales.run(output_dir / "clean_sales.csv")
    if staging_count != counts["clean"]:
        raise ValueError("Staging row count does not match the cleaned CSV")

    warehouse = build_warehouse.run(customers_path, products_path)
    if warehouse["sales"] != counts["completed"]:
        raise ValueError("Warehouse row count does not match completed sales")

    LOGGER.info("Pipeline finished: %s", counts)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/sales_100.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/output/sales_100")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(args.input, args.output_dir)
    except Exception:
        LOGGER.exception("Pipeline failed")
        raise SystemExit(1)
