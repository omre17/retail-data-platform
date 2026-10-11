"""Fetch products and orders from a separate REST service and upsert sales."""

import argparse
import csv
import json
import logging
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from src import build_warehouse, clean_sales

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)


def fetch_json(base_url: str, resource: str) -> list[dict]:
    url = f"{base_url.rstrip('/')}/{resource}"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=10) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not fetch {resource} from source API: {exc}") from exc
    if not isinstance(result, list) or not result:
        raise ValueError(f"{resource} response must be a nonempty JSON list")
    return result


def flatten_orders(orders: list[dict], product_ids: set[str]) -> list[dict]:
    lines = []
    for order in orders:
        if not isinstance(order, dict) or not isinstance(order.get("items"), list) or not order["items"]:
            raise ValueError("Each order must contain a nonempty items list")
        for number, item in enumerate(order["items"], 1):
            if not isinstance(item, dict):
                raise ValueError("Order item must be an object")
            if item.get("product_id") not in product_ids:
                raise ValueError(f"Order references unknown product {item.get('product_id')}")
            lines.append({
                "order_id": order.get("order_id"),
                "line_number": str(number),
                "order_date": order.get("order_date"),
                "customer_id": order.get("customer_id"),
                "product_id": item.get("product_id"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "status": order.get("status"),
            })
    clean, rejected = clean_sales.validate_sales(pd.DataFrame(lines))
    if len(rejected):
        raise ValueError(f"API supplied {len(rejected)} invalid order lines: {rejected.iloc[0]['rejection_reason']}")
    return clean.to_dict("records")


def run(output_dir: Path) -> dict[str, int]:
    from src import incremental_sales

    base_url = os.getenv("SOURCE_API_BASE_URL", "http://source_api:8000")
    products = fetch_json(base_url, "products")
    orders = fetch_json(base_url, "orders")
    product_rows = build_warehouse.validate_lookup(products, build_warehouse.PRODUCT_FIELDS)
    lines = flatten_orders(orders, {row[0] for row in product_rows})

    output_dir.mkdir(parents=True, exist_ok=True)
    products_path = output_dir / "products.json"
    products_path.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "orders.json").write_text(json.dumps(orders, indent=2, ensure_ascii=False), encoding="utf-8")
    input_path = output_dir / "orders_flat.csv"
    with input_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=clean_sales.REQUIRED)
        writer.writeheader()
        writer.writerows(lines)

    result = incremental_sales.run(input_path, output_dir, products_path=products_path)
    LOGGER.info("REST orders import finished: %s", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/output/api")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(args.output_dir)
    except Exception:
        LOGGER.exception("REST orders import failed")
        raise SystemExit(1)
