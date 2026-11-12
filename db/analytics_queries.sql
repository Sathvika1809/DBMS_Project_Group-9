-- ============================================================================
-- db/analytics_queries.sql : the 7 non-trivial analytical queries
-- Run:  docker exec -i paper_trading_db psql -U postgres -d papertrading < db/analytics_queries.sql
-- ============================================================================

-- Q1. Order book depth: price levels with running total (window function)
SELECT i.symbol, b.side, b.price, b.total_qty, b.num_orders, b.cumulative_qty
FROM order_book_view b JOIN INSTRUMENT i USING (instrument_id)
ORDER BY i.symbol, b.side, CASE WHEN b.side = 'BUY' THEN -b.price ELSE b.price END;

-- Q2. Total account value by instrument type: cash + market value (CTE + view with LATERAL-style lookup)
WITH holdings AS (
    SELECT account_id, instrument_type, SUM(market_value) AS mv, SUM(unrealized_pnl) AS pnl
    FROM portfolio_view GROUP BY account_id, instrument_type
)
SELECT a.account_id, u.name, a.cash_balance, h.instrument_type, h.mv, h.pnl,
       a.cash_balance + SUM(h.mv) OVER (PARTITION BY a.account_id) AS total_equity
FROM ACCOUNT a
JOIN "USER" u USING (user_id)
LEFT JOIN holdings h ON h.account_id = a.account_id
ORDER BY a.account_id, h.instrument_type;

-- Q3. Realized P&L per account and instrument (average-cost estimate from trade history)
WITH fills AS (
    SELECT o.account_id, o.instrument_id, o.side, f.qty, f.price, i.multiplier
    FROM ORDER_FILL f
    JOIN "ORDER" o     ON o.order_id = f.order_id
    JOIN INSTRUMENT i  ON i.instrument_id = o.instrument_id
), agg AS (
    SELECT account_id, instrument_id, MAX(multiplier) AS multiplier,
           SUM(qty)         FILTER (WHERE side = 'BUY')  AS bought_qty,
           SUM(qty * price) FILTER (WHERE side = 'BUY')  AS bought_value,
           SUM(qty)         FILTER (WHERE side = 'SELL') AS sold_qty,
           SUM(qty * price) FILTER (WHERE side = 'SELL') AS sold_value
    FROM fills GROUP BY account_id, instrument_id
)
SELECT account_id, instrument_id, bought_qty, sold_qty,
       ROUND(CASE WHEN bought_qty IS NULL OR sold_qty IS NULL THEN 0
                  ELSE LEAST(sold_qty, bought_qty)
                       * (sold_value / sold_qty - bought_value / bought_qty) * multiplier END, 2) AS realized_pnl_est
FROM agg ORDER BY account_id, instrument_id;

-- Q4. Rolling 30-bar return and running drawdown per instrument (LAG, MAX OVER)
WITH bars AS (
    SELECT instrument_id, trade_date, close,
           LAG(close, 30) OVER w AS close_30_ago,
           MAX(close) OVER (PARTITION BY instrument_id ORDER BY trade_date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_peak
    FROM PRICE_BAR
    WINDOW w AS (PARTITION BY instrument_id ORDER BY trade_date)
)
SELECT i.symbol,
       MIN(b.close / b.running_peak - 1)                                   AS max_drawdown,
       (ARRAY_AGG(b.close / b.close_30_ago - 1 ORDER BY b.trade_date DESC))[1] AS latest_30_bar_return
FROM bars b JOIN INSTRUMENT i USING (instrument_id)
GROUP BY i.symbol ORDER BY i.symbol;

-- Q5. Daily VWAP of trades executed on the exchange
SELECT i.symbol, t.executed_at::date AS day,
       ROUND(SUM(t.price * t.qty) / SUM(t.qty), 2) AS vwap,
       SUM(t.qty) AS volume, COUNT(*) AS trades
FROM TRADE t
JOIN "ORDER" o    ON o.order_id = t.buy_order_id
JOIN INSTRUMENT i ON i.instrument_id = o.instrument_id
GROUP BY i.symbol, t.executed_at::date ORDER BY i.symbol, day;

-- Q6. Accounts whose holdings are worth more than their cash (correlated subquery)
SELECT a.account_id, u.name, a.cash_balance,
       (SELECT COALESCE(SUM(pv.market_value), 0) FROM portfolio_view pv WHERE pv.account_id = a.account_id) AS holdings_value
FROM ACCOUNT a JOIN "USER" u USING (user_id)
WHERE (SELECT COALESCE(SUM(pv.market_value), 0) FROM portfolio_view pv WHERE pv.account_id = a.account_id) > a.cash_balance;

-- Q7. Bond yield-to-maturity approximation from the latest price bar (stored function)
SELECT i.symbol, pb.trade_date, pb.close AS clean_price,
       approx_ytm(pb.close, b.coupon_rate, b.maturity_date, pb.trade_date) AS approx_ytm
FROM BOND b
JOIN INSTRUMENT i ON i.instrument_id = b.instrument_id
JOIN LATERAL (SELECT * FROM PRICE_BAR p WHERE p.instrument_id = b.instrument_id
              ORDER BY p.trade_date DESC LIMIT 1) pb ON TRUE;
