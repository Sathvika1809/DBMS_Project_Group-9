-- ============================================================================
-- CS F212 Database Systems — Project Schema Definition (all 12 relations)
-- File: db/01_schema.sql
-- ============================================================================

DROP TABLE IF EXISTS AUDIT_LOG CASCADE;
DROP TABLE IF EXISTS CASH_LEDGER CASCADE;
DROP TABLE IF EXISTS ORDER_FILL CASCADE;
DROP TABLE IF EXISTS TRADE CASCADE;
DROP TABLE IF EXISTS "ORDER" CASCADE;
DROP TABLE IF EXISTS PRICE_BAR CASCADE;
DROP TABLE IF EXISTS POSITION CASCADE;
DROP TABLE IF EXISTS OPTION CASCADE;
DROP TABLE IF EXISTS BOND CASCADE;
DROP TABLE IF EXISTS INSTRUMENT CASCADE;
DROP TABLE IF EXISTS ACCOUNT CASCADE;
DROP TABLE IF EXISTS "USER" CASCADE;

-- 1. USER
CREATE TABLE "USER" (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'TRADER' CHECK (role IN ('TRADER', 'ADMIN', 'HOUSE')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. ACCOUNT (OWNS: total participation -> user_id NOT NULL)
CREATE TABLE ACCOUNT (
    account_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES "USER"(user_id) ON DELETE CASCADE,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('HOUSE', 'RETAIL', 'INSTITUTIONAL')),
    cash_balance DECIMAL(15, 2) NOT NULL DEFAULT 100000.00 CHECK (cash_balance >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. INSTRUMENT (supertype)
CREATE TABLE INSTRUMENT (
    instrument_id SERIAL PRIMARY KEY,
    symbol VARCHAR(30) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL CHECK (instrument_type IN ('STOCK', 'BOND', 'OPTION')),
    sector VARCHAR(50),
    multiplier DECIMAL(10, 2) NOT NULL DEFAULT 1.0 CHECK (multiplier > 0),
    tick_size DECIMAL(10, 4) NOT NULL DEFAULT 0.05 CHECK (tick_size > 0),
    lot_size INT NOT NULL DEFAULT 1 CHECK (lot_size > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'HALTED', 'EXPIRED'))
);

-- 4. BOND (EER subclass, option 8A)
CREATE TABLE BOND (
    instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    face_value DECIMAL(12, 2) NOT NULL CHECK (face_value > 0),
    coupon_rate DECIMAL(7, 4) NOT NULL CHECK (coupon_rate >= 0),  -- fraction, e.g. 0.0754
    coupon_frequency INT NOT NULL CHECK (coupon_frequency IN (1, 2, 4, 12)),
    issue_date DATE NOT NULL,
    maturity_date DATE NOT NULL,
    CHECK (maturity_date > issue_date)
);

-- 5. OPTION (EER subclass, option 8A)
CREATE TABLE OPTION (
    instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    underlying_id INT NOT NULL REFERENCES INSTRUMENT(instrument_id),
    strike DECIMAL(12, 2) NOT NULL CHECK (strike > 0),
    expiry DATE NOT NULL,
    option_type VARCHAR(4) NOT NULL CHECK (option_type IN ('CALL', 'PUT')),
    CHECK (underlying_id <> instrument_id)
);

-- 6. PRICE_BAR (weak entity; partial key = trade_date)
CREATE TABLE PRICE_BAR (
    instrument_id INT NOT NULL REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    open DECIMAL(12, 2) NOT NULL CHECK (open > 0),
    high DECIMAL(12, 2) NOT NULL,
    low DECIMAL(12, 2) NOT NULL,
    close DECIMAL(12, 2) NOT NULL CHECK (close > 0),
    volume BIGINT NOT NULL CHECK (volume >= 0),
    PRIMARY KEY (instrument_id, trade_date),
    CHECK (high >= low)
);

-- 7. POSITION (M:N HOLDS; PK = both FKs, as in the report)
CREATE TABLE POSITION (
    account_id INT NOT NULL REFERENCES ACCOUNT(account_id) ON DELETE CASCADE,
    instrument_id INT NOT NULL REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    quantity DECIMAL(15, 4) NOT NULL CHECK (quantity >= 0),          -- report: Qty
    average_buy_price DECIMAL(12, 2) NOT NULL CHECK (average_buy_price >= 0),  -- report: Avg_cost
    PRIMARY KEY (account_id, instrument_id)
);

-- 8. ORDER
CREATE TABLE "ORDER" (
    order_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES ACCOUNT(account_id) ON DELETE CASCADE,
    instrument_id INT NOT NULL REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
    qty DECIMAL(12, 4) NOT NULL CHECK (qty > 0),
    filled_qty DECIMAL(12, 4) NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'PARTIAL', 'FILLED', 'CANCELLED')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (filled_qty >= 0 AND filled_qty <= qty)
);

-- 9. TRADE (BUY_SIDE / SELL_SIDE both reference ORDER)
CREATE TABLE TRADE (
    trade_id SERIAL PRIMARY KEY,
    buy_order_id INT NOT NULL REFERENCES "ORDER"(order_id),
    sell_order_id INT NOT NULL REFERENCES "ORDER"(order_id),
    price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
    qty DECIMAL(12, 4) NOT NULL CHECK (qty > 0),
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (buy_order_id <> sell_order_id)
);

-- 10. ORDER_FILL (weak entity; PK = owner key + partial key)
CREATE TABLE ORDER_FILL (
    order_id INT NOT NULL REFERENCES "ORDER"(order_id) ON DELETE CASCADE,
    fill_seq INT NOT NULL CHECK (fill_seq > 0),
    trade_id INT NOT NULL REFERENCES TRADE(trade_id),
    qty DECIMAL(12, 4) NOT NULL CHECK (qty > 0),
    price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
    filled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id, fill_seq)
);

-- 11. CASH_LEDGER
CREATE TABLE CASH_LEDGER (
    ledger_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES ACCOUNT(account_id) ON DELETE CASCADE,
    trade_id INT REFERENCES TRADE(trade_id),
    instrument_id INT REFERENCES INSTRUMENT(instrument_id),
    entry_type VARCHAR(20) NOT NULL CHECK (entry_type IN
        ('DEPOSIT', 'WITHDRAWAL', 'BUY', 'SELL', 'FEE', 'COUPON', 'REDEMPTION', 'EXERCISE')),
    amount DECIMAL(15, 2) NOT NULL CHECK (amount <> 0),
    value_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (NOT (trade_id IS NOT NULL AND instrument_id IS NOT NULL)),
    -- idempotence: no double coupon/redemption payout
    UNIQUE (account_id, instrument_id, entry_type, value_date)
);

-- 12. AUDIT_LOG (deliberately no FKs so history survives deletes)
CREATE TABLE AUDIT_LOG (
    log_id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    row_id BIGINT,
    action VARCHAR(10) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);