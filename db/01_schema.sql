-- ============================================================================
-- CS F212 Database Systems — Project Schema Definition (Minimal Core)
-- File: db/01_schema.sql
-- ============================================================================

DROP TABLE IF EXISTS PRICE_BAR CASCADE;
DROP TABLE IF EXISTS OPTION CASCADE;
DROP TABLE IF EXISTS BOND CASCADE;
DROP TABLE IF EXISTS INSTRUMENT CASCADE;
DROP TABLE IF EXISTS ACCOUNT CASCADE;
DROP TABLE IF EXISTS "USER" CASCADE;

-- 1. Master User Entity
CREATE TABLE "USER" (
    User_id SERIAL PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Email VARCHAR(150) UNIQUE NOT NULL,
    Password_hash VARCHAR(255) NOT NULL,
    Role VARCHAR(20) CHECK (Role IN ('TRADER', 'ADMIN', 'HOUSE')),
    Created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. User Financial Account Entity
CREATE TABLE ACCOUNT (
    Account_id SERIAL PRIMARY KEY,
    User_id INT REFERENCES "USER"(User_id) ON DELETE CASCADE,
    Cash_balance DECIMAL(15, 2) NOT NULL DEFAULT 100000.00,
    Is_house BOOLEAN DEFAULT FALSE,
    Created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Master Instrument Registry
CREATE TABLE INSTRUMENT (
    Instrument_id SERIAL PRIMARY KEY,
    Symbol VARCHAR(20) UNIQUE NOT NULL,
    Name VARCHAR(100) NOT NULL,
    Instrument_type VARCHAR(20) CHECK (Instrument_type IN ('STOCK', 'EQUITY', 'BOND', 'OPTION')),
    Sector VARCHAR(50),
    Multiplier DECIMAL(10, 2) DEFAULT 1.0,
    Tick_size DECIMAL(10, 4) DEFAULT 0.05,
    Lot_size INT DEFAULT 1,
    Status VARCHAR(20) DEFAULT 'ACTIVE'
);

-- 4. EER Subclass: Bond
CREATE TABLE BOND (
    Instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(Instrument_id) ON DELETE CASCADE,
    Face_value DECIMAL(12, 2) NOT NULL,
    Coupon_rate DECIMAL(5, 4) NOT NULL,
    Coupon_frequency VARCHAR(20) DEFAULT 'ANNUAL',
    Issue_date DATE NOT NULL,
    Maturity_date DATE NOT NULL
);

-- 5. EER Subclass: Option
CREATE TABLE OPTION (
    Instrument_id INT PRIMARY KEY REFERENCES INSTRUMENT(Instrument_id) ON DELETE CASCADE,
    Underlying_id INT REFERENCES INSTRUMENT(Instrument_id),
    Strike DECIMAL(12, 2) NOT NULL,
    Expiry DATE NOT NULL,
    Option_type VARCHAR(4) CHECK (Option_type IN ('CALL', 'PUT'))
);

-- 6. Weak Entity: Historical Price Bars
CREATE TABLE PRICE_BAR (
    Instrument_id INT REFERENCES INSTRUMENT(Instrument_id) ON DELETE CASCADE,
    Trade_date DATE NOT NULL,
    Open DECIMAL(12, 2) NOT NULL,
    High DECIMAL(12, 2) NOT NULL,
    Low DECIMAL(12, 2) NOT NULL,
    Close DECIMAL(12, 2) NOT NULL,
    Volume BIGINT NOT NULL,
    PRIMARY KEY (Instrument_id, Trade_date)
);
-- 7. Active & Historical Order Registry
DROP TABLE IF EXISTS "ORDER" CASCADE;

CREATE TABLE "ORDER" (
    Order_id SERIAL PRIMARY KEY,
    Account_id INT REFERENCES ACCOUNT(Account_id) ON DELETE CASCADE,
    Instrument_id INT REFERENCES INSTRUMENT(Instrument_id) ON DELETE CASCADE,
    Side VARCHAR(4) CHECK (Side IN ('BUY', 'SELL')),
    Price DECIMAL(12, 2) NOT NULL,
    Qty DECIMAL(12, 4) NOT NULL,
    Filled_qty DECIMAL(12, 4) DEFAULT 0.0,
    Status VARCHAR(20) DEFAULT 'OPEN',
    Created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);