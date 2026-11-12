-- ============================================================================
-- db/02_views_indexes.sql : views and indexes
-- ============================================================================

-- ---------------------------------------------------------------- INDEXES ---
-- The order book is a query, not a table. Two partial indexes (one per side)
-- hold only resting orders, already in price-time priority. One index cannot
-- serve both sides: bids need price DESC but created_at ASC, and a backward
-- scan would flip both.
CREATE INDEX idx_open_bids ON "ORDER" (instrument_id, price DESC, created_at, order_id)
    WHERE side = 'BUY'  AND status IN ('OPEN', 'PARTIAL');
CREATE INDEX idx_open_asks ON "ORDER" (instrument_id, price ASC,  created_at, order_id)
    WHERE side = 'SELL' AND status IN ('OPEN', 'PARTIAL');

CREATE INDEX idx_order_account    ON "ORDER" (account_id, created_at DESC);
CREATE INDEX idx_order_instrument ON "ORDER" (instrument_id);
CREATE INDEX idx_trade_buy        ON TRADE (buy_order_id);
CREATE INDEX idx_trade_sell       ON TRADE (sell_order_id);
CREATE INDEX idx_fill_trade       ON ORDER_FILL (trade_id);
CREATE INDEX idx_ledger_account   ON CASH_LEDGER (account_id, created_at DESC);
CREATE INDEX idx_audit_lookup     ON AUDIT_LOG (table_name, row_id, changed_at DESC);

-- At most one HOUSE account (end_of_day() uses it as the counterparty for payouts).
CREATE UNIQUE INDEX uq_single_house_account ON ACCOUNT (account_type) WHERE account_type = 'HOUSE';

-- PRICE_BAR's PK (instrument_id, trade_date) already serves "latest bar per
-- instrument" through a backward index scan, so no extra index is needed.

-- ------------------------------------------------------------------ VIEWS ---
-- Last traded price on the exchange; falls back to the latest daily close.
CREATE OR REPLACE VIEW last_price_view AS
SELECT i.instrument_id,
       COALESCE(
           (SELECT t.price
              FROM TRADE t JOIN "ORDER" o ON o.order_id = t.buy_order_id
             WHERE o.instrument_id = i.instrument_id
             ORDER BY t.executed_at DESC, t.trade_id DESC LIMIT 1),
           (SELECT pb.close FROM PRICE_BAR pb
             WHERE pb.instrument_id = i.instrument_id
             ORDER BY pb.trade_date DESC LIMIT 1)
       ) AS last_price
FROM INSTRUMENT i;

-- Live positions with market value and unrealized P&L.
CREATE OR REPLACE VIEW portfolio_view AS
SELECT p.account_id,
       p.instrument_id,
       i.symbol,
       i.instrument_type,
       p.quantity,
       p.average_buy_price AS avg_buy_price,
       COALESCE(lp.last_price, p.average_buy_price) AS current_price,
       ROUND(COALESCE(lp.last_price, p.average_buy_price) * p.quantity * i.multiplier, 2) AS market_value,
       ROUND((COALESCE(lp.last_price, p.average_buy_price) - p.average_buy_price)
             * p.quantity * i.multiplier, 2) AS unrealized_pnl
FROM POSITION p
JOIN INSTRUMENT i ON i.instrument_id = p.instrument_id
LEFT JOIN last_price_view lp ON lp.instrument_id = p.instrument_id
WHERE p.quantity > 0;

-- Order book aggregated by price level, with cumulative depth from the best price.
CREATE OR REPLACE VIEW order_book_view AS
SELECT instrument_id,
       side,
       price,
       SUM(qty - filled_qty) AS total_qty,
       COUNT(*)              AS num_orders,
       SUM(SUM(qty - filled_qty)) OVER (
           PARTITION BY instrument_id, side
           ORDER BY CASE WHEN side = 'BUY' THEN -price ELSE price END
       ) AS cumulative_qty
FROM "ORDER"
WHERE status IN ('OPEN', 'PARTIAL')
GROUP BY instrument_id, side, price;

-- Consistency checker: every row should show 0 violations. Used by the API and
-- the UI to prove the denormalized columns are correct.
CREATE OR REPLACE VIEW integrity_report AS
SELECT 'ACCOUNT.cash_balance = SUM(CASH_LEDGER.amount)'::TEXT AS check_name, COUNT(*) AS violations
FROM (SELECT a.account_id
        FROM ACCOUNT a LEFT JOIN CASH_LEDGER l ON l.account_id = a.account_id
       GROUP BY a.account_id, a.cash_balance
      HAVING a.cash_balance <> COALESCE(SUM(l.amount), 0)) x
UNION ALL
SELECT 'ORDER.filled_qty = SUM(ORDER_FILL.qty)', COUNT(*)
FROM (SELECT o.order_id
        FROM "ORDER" o LEFT JOIN ORDER_FILL f ON f.order_id = o.order_id
       GROUP BY o.order_id, o.filled_qty
      HAVING o.filled_qty <> COALESCE(SUM(f.qty), 0)) x
UNION ALL
SELECT 'every TRADE has exactly two fills (buy side + sell side)', COUNT(*)
FROM (SELECT t.trade_id
        FROM TRADE t LEFT JOIN ORDER_FILL f ON f.trade_id = t.trade_id
       GROUP BY t.trade_id HAVING COUNT(f.order_id) <> 2) x
UNION ALL
SELECT 'BOND/OPTION rows match INSTRUMENT.instrument_type', COUNT(*)
FROM (SELECT b.instrument_id FROM BOND b   JOIN INSTRUMENT i USING (instrument_id) WHERE i.instrument_type <> 'BOND'
      UNION ALL
      SELECT o.instrument_id FROM OPTION o JOIN INSTRUMENT i USING (instrument_id) WHERE i.instrument_type <> 'OPTION') x
UNION ALL
SELECT 'no open orders on non-ACTIVE instruments', COUNT(*)
FROM "ORDER" o JOIN INSTRUMENT i USING (instrument_id)
WHERE o.status IN ('OPEN', 'PARTIAL') AND i.status <> 'ACTIVE';
