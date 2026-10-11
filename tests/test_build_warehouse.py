import unittest

from src.build_warehouse import check_references, validate_lookup


class WarehouseValidationTests(unittest.TestCase):
    def test_rejects_duplicate_customer_id(self):
        rows = [
            {"customer_id": "C001", "customer_name": "First", "city": "Tira"},
            {"customer_id": "C001", "customer_name": "Second", "city": "Haifa"},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate customer_id"):
            validate_lookup(rows, ("customer_id", "customer_name", "city"))

    def test_rejects_unknown_sales_reference(self):
        with self.assertRaisesRegex(ValueError, "P999"):
            check_references(
                {"C001"}, {"P999"},
                [("C001", "Customer 001", "Tira")],
                [("P001", "Mug", "Home")],
            )


if __name__ == "__main__":
    unittest.main()
