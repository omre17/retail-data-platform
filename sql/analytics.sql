-- Revenue by product. The rank is calculated after aggregation.
WITH product_revenue AS (
    SELECT p.product_id, p.product_name, p.category,
           SUM(f.quantity) AS units_sold,
           SUM(f.revenue_ils) AS revenue_ils
    FROM dwh.fact_sales AS f
    JOIN dwh.dim_product AS p ON p.product_key = f.product_key
    GROUP BY p.product_id, p.product_name, p.category
), ranked AS (
    SELECT *, DENSE_RANK() OVER (ORDER BY revenue_ils DESC) AS revenue_rank
    FROM product_revenue
)
SELECT * FROM ranked ORDER BY revenue_rank, product_id;
