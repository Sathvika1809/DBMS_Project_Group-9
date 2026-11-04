-- ============================================================================
-- db/02_views_indexes.sql  (starter: portfolio_view + order-book index)
-- Add order_book_view and the analytical queries here.
-- ============================================================================

-- Live positions with latest close and unrealized P&L (needed by /api/portfolio)
CREATE OR REPLACE VIEW portfolio_view AS
SELECT
    p.account_id,
    i.symbol,
    i.instrument_type,
    p.quantity,
    p.average_buy_price AS avg_buy_price,
    COALESCE(lp.close, p.average_buy_price) AS current_price,
    (COALESCE(lp.close, p.average_buy_price) - p.average_buy_price)
        * p.quantity * i.multiplier AS unrealized_pnl
FROM POSITION p
JOIN INSTRUMENT i ON i.instrument_id = p.instrument_id
LEFT JOIN LATERAL (
    SELECT pb.close
    FROM PRICE_BAR pb
    WHERE pb.instrument_id = p.instrument_id
    ORDER BY pb.trade_date DESC
    LIMIT 1
) lp ON TRUE;

-- Partial index for fast order-book lookups on resting orders
CREATE INDEX idx_order_open_book
    ON "ORDER" (instrument_id, side, price, created_at)
    WHERE status IN ('OPEN', 'PARTIAL');

-- Note: PRICE_BAR's PK (instrument_id, trade_date) already serves
-- "latest bar per instrument" via a backward index scan, so a separate
-- (instrument_id, trade_date DESC) index would be redundant.