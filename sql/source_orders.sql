-- Simulated operational source, separate from staging and DWH by schema.
CREATE SCHEMA IF NOT EXISTS source;

CREATE TABLE IF NOT EXISTS source.order_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id TEXT NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    order_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    status TEXT NOT NULL CHECK (status IN ('completed', 'canceled')),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rerunning setup does not append the four sample events again.
INSERT INTO source.order_events (
    order_id, line_number, order_date, customer_id, product_id,
    quantity, unit_price, status
)
SELECT order_id, line_number, order_date::date, customer_id, product_id,
       quantity, unit_price, status
FROM (VALUES
    ('3001', 1, '2026-10-11', 'C001', 'P002', 2, 65.00, 'completed'),
    ('3001', 2, '2026-10-11', 'C001', 'P004', 1, 50.00, 'completed'),
    ('3002', 1, '2026-10-11', 'C006', 'P003', 3, 80.00, 'completed'),
    ('3003', 1, '2026-10-11', 'C011', 'P001', 1, 120.00, 'canceled')
) AS seed(order_id, line_number, order_date, customer_id, product_id,
          quantity, unit_price, status)
WHERE NOT EXISTS (SELECT 1 FROM source.order_events);
