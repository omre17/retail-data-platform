CREATE SCHEMA IF NOT EXISTS dwh;

CREATE TABLE IF NOT EXISTS dwh.dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    day SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.fact_sales (
    order_id TEXT NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    date_key INTEGER NOT NULL REFERENCES dwh.dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dwh.dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dwh.dim_product(product_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    revenue_ils NUMERIC(14, 2) NOT NULL CHECK (revenue_ils >= 0),
    PRIMARY KEY (order_id, line_number)
);
