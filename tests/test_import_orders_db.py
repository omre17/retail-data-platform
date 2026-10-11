import unittest

from src.import_orders_db import validated_lines


class SourceDatabaseTests(unittest.TestCase):
    def test_later_event_replaces_same_order_line(self):
        original = {
            "event_id": 1, "order_id": "3001", "line_number": 1,
            "order_date": "2026-10-11", "customer_id": "C001",
            "product_id": "P002", "quantity": 2,
            "unit_price": "65.00", "status": "completed",
        }
        changed = {**original, "event_id": 3, "quantity": 3, "status": "canceled"}
        other = {**original, "event_id": 2, "order_id": "3002"}

        lines = validated_lines([original, other, changed])

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["quantity"], 3)
        self.assertEqual(lines[0]["status"], "canceled")
        self.assertEqual(lines[1]["order_id"], "3002")

    def test_invalid_change_is_rejected_before_loading(self):
        event = {
            "event_id": 5, "order_id": "3001", "line_number": 1,
            "order_date": "2026-10-11", "customer_id": "C001",
            "product_id": "P002", "quantity": 0,
            "unit_price": "65.00", "status": "completed",
        }
        with self.assertRaisesRegex(ValueError, "invalid quantity"):
            validated_lines([event])


if __name__ == "__main__":
    unittest.main()
