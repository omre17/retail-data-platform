import io
import unittest
from unittest.mock import patch

from src.import_orders_api import fetch_json, flatten_orders
from src.mock_store_api import ROUTES


class OrdersApiTests(unittest.TestCase):
    def test_product_and_order_responses_form_valid_sales_lines(self):
        requested = []

        def fake_open(request, timeout):
            resource = request.full_url.rsplit("/", 1)[-1]
            requested.append(resource)
            return io.BytesIO(ROUTES[f"/{resource}"].read_bytes())

        with patch("src.import_orders_api.urlopen", side_effect=fake_open):
            products = fetch_json("http://source_api:8000", "products")
            orders = fetch_json("http://source_api:8000", "orders")
        lines = flatten_orders(orders, {p["product_id"] for p in products})
        self.assertEqual(requested, ["products", "orders"])
        self.assertEqual(len(lines), 4)
        self.assertEqual(sum(line["status"] == "completed" for line in lines), 3)
        self.assertEqual(lines[0]["product_id"], "P001")

    def test_unknown_product_is_rejected_before_database_write(self):
        orders = [{"order_id": "1", "order_date": "2026-10-08", "customer_id": "C001",
                   "status": "completed", "items": [{"product_id": "P999", "quantity": 1,
                                                   "unit_price": "10.00"}]}]
        with self.assertRaisesRegex(ValueError, "unknown product P999"):
            flatten_orders(orders, {"P001"})


if __name__ == "__main__":
    unittest.main()
