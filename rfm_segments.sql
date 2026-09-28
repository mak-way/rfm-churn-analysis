-- RFM segmentation (SQLite / works with minor edits in PostgreSQL, SQL Server, BigQuery)
-- Snapshot date = 2026-09-28. Table: orders(customer_id, order_id, order_date, sales)
WITH base AS (
    SELECT customer_id,
           CAST(julianday('2026-09-28') - julianday(MAX(order_date)) AS INTEGER) AS recency,
           COUNT(DISTINCT order_id) AS frequency,
           SUM(sales)               AS monetary
    FROM orders
    GROUP BY customer_id
),
scored AS (
    SELECT *,
           NTILE(5) OVER (ORDER BY recency DESC)  AS r,   -- 5 = most recent
           NTILE(5) OVER (ORDER BY frequency)     AS f,
           NTILE(5) OVER (ORDER BY monetary)      AS m
    FROM base
)
SELECT customer_id, recency, frequency, ROUND(monetary, 2) AS monetary, r, f, m,
       CASE WHEN r >= 4 AND f >= 4 THEN 'Champions'
            WHEN r <= 2 AND f >= 4 THEN 'Can''t lose'
            WHEN r <= 2 AND f = 3  THEN 'At risk'
            WHEN r >= 3 AND f >= 3 THEN 'Loyal'
            WHEN r >= 4 AND f <= 2 THEN 'New / promising'
            WHEN r <= 2            THEN 'Hibernating'
            ELSE 'Needs attention' END AS segment
FROM scored;
