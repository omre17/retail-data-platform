CREATE SCHEMA IF NOT EXISTS api_orders;
CREATE TABLE IF NOT EXISTS api_orders.products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    catalog_price NUMERIC(12,2) NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_orders.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_orders.order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES api_orders.orders(order_id),
    product_id INTEGER NOT NULL REFERENCES api_orders.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL,
    line_total NUMERIC(14,2) NOT NULL
);
CREATE OR REPLACE VIEW api_orders.order_value AS
SELECT o.order_id, o.status, o.placed_at, o.currency,
       COUNT(*) AS product_lines, SUM(i.line_total) AS items_total
FROM api_orders.orders AS o
JOIN api_orders.order_items AS i ON i.order_id = o.order_id
GROUP BY o.order_id, o.status, o.placed_at, o.currency;
