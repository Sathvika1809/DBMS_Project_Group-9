-- ============================================================================
-- CS F212 Database Systems — Project Schema Definition
-- File: db/01_schema.sql
-- ============================================================================

DROP TABLE IF EXISTS "ORDER" CASCADE;
DROP TABLE IF EXISTS PRICE_BAR CASCADE;
DROP TABLE IF EXISTS POSITION CASCADE;
DROP TABLE IF EXISTS OPTION CASCADE;
DROP TABLE IF EXISTS BOND CASCADE;
DROP TABLE IF EXISTS INSTRUMENT CASCADE;
DROP TABLE IF EXISTS ACCOUNT CASCADE;
DROP TABLE IF EXISTS "USER" CASCADE;

-- 1. Master User Entity
CREATE TABLE "USER" (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'TRADER' CHECK (role IN ('TRADER', 'ADMIN', 'HOUSE')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. User Financial Account Entity
CREATE TABLE ACCOUNT (
    account_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES "USER"(user_id) ON DELETE CASCADE,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('HOUSE', 'RETAIL', 'INSTITUTIONAL')),
    cash_balance DECIMAL(15, 2) NOT NULL DEFAULT 100000.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Master Instrument Registry
CREATE TABLE INSTRUMENT (
    instrument_id SERIAL PRIMARY KEY,
    symbol VARCHAR(30) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL CHECK (instrument_type IN ('STOCK', 'BOND', 'OPTION')),
    sector VARCHAR(50),
    multiplier DECIMAL(10, 2) DEFAULT 1.0,
    tick_size DECIMAL(10, 4) DEFAULT 0.05,
    lot_size INT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'ACTIVE'
);

-- 4. EER Subclass: Bond
CREATE TABLE BOND (
    instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    face_value DECIMAL(12, 2) NOT NULL,
    coupon_rate DECIMAL(7, 4) NOT NULL, -- Allows up to 999.9999 (e.g., 0.0754)
    coupon_frequency INT CHECK (coupon_frequency IN (1, 2, 4, 12)), -- Integer values per report spec
    issue_date DATE NOT NULL,
    maturity_date DATE NOT NULL
);

-- 5. EER Subclass: Option
CREATE TABLE OPTION (
    instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    underlying_id INT REFERENCES INSTRUMENT(instrument_id),
    strike DECIMAL(12, 2) NOT NULL,
    expiry DATE NOT NULL,
    option_type VARCHAR(4) CHECK (option_type IN ('CALL', 'PUT'))
);

-- 6. Weak Entity: Historical Price Bars
CREATE TABLE PRICE_BAR (
    instrument_id INT REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL(12, 2) NOT NULL,
    high DECIMAL(12, 2) NOT NULL,
    low DECIMAL(12, 2) NOT NULL,
    close DECIMAL(12, 2) NOT NULL,
    volume BIGINT NOT NULL,
    PRIMARY KEY (instrument_id, timestamp)
);

-- 7. Account Holdings & Inventory Entity
CREATE TABLE POSITION (
    position_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES ACCOUNT(account_id) ON DELETE CASCADE,
    instrument_id INT NOT NULL REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    quantity DECIMAL(15, 4) NOT NULL,
    average_buy_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT unique_account_instrument UNIQUE (account_id, instrument_id)
);

-- 8. Active & Historical Order Registry
CREATE TABLE "ORDER" (
    order_id SERIAL PRIMARY KEY,
    account_id INT REFERENCES ACCOUNT(account_id) ON DELETE CASCADE,
    instrument_id INT REFERENCES INSTRUMENT(instrument_id) ON DELETE CASCADE,
    side VARCHAR(4) CHECK (side IN ('BUY', 'SELL')),
    price DECIMAL(12, 2) NOT NULL,
    qty DECIMAL(12, 4) NOT NULL,
    filled_qty DECIMAL(12, 4) DEFAULT 0.0,
    status VARCHAR(20) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);