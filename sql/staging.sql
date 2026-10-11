CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.sales_lines (
    order_id TEXT NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    order_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    status TEXT NOT NULL CHECK (status IN ('completed', 'canceled')),
    PRIMARY KEY (order_id, line_number)
);
