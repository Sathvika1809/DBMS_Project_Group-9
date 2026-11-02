-- ============================================================================
-- CS F212 Database Systems — Project Seed Script
-- File: db/05_seed_data.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Seed Master Users
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_users (
    user_id INT,
    name VARCHAR(100),
    email VARCHAR(150),
    password_hash VARCHAR(255),
    role VARCHAR(20)
);

\copy temp_users FROM 'data_pipeline/users.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO "USER" (user_id, name, email, password_hash, role)
SELECT user_id, name, email, '$2b$12$eImiTXuWVxfM37uY4JANjO5E/805.A2xTzT86vS8P9YtA3G6M.qS6', role 
FROM temp_users;

-- ----------------------------------------------------------------------------
-- 2. Seed Accounts
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_accounts (
    account_id INT,
    user_id INT,
    account_type VARCHAR(20),
    cash_balance DECIMAL(15, 2)
);

\copy temp_accounts FROM 'data_pipeline/accounts.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO ACCOUNT (account_id, user_id, account_type, cash_balance)
SELECT account_id, user_id, account_type, cash_balance 
FROM temp_accounts;

-- ----------------------------------------------------------------------------
-- 3. Seed Instruments
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_instruments (
    instrument_id INT,
    symbol VARCHAR(30),
    name VARCHAR(100),
    instrument_type VARCHAR(20),
    sector VARCHAR(50),
    multiplier DECIMAL(10, 2),
    tick_size DECIMAL(10, 4),
    lot_size INT,
    status VARCHAR(20)
);

\copy temp_instruments FROM 'data_pipeline/instruments.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO INSTRUMENT (instrument_id, symbol, name, instrument_type, sector, multiplier, tick_size, lot_size, status)
SELECT instrument_id, symbol, name, instrument_type, sector, multiplier, tick_size, lot_size, status 
FROM temp_instruments;

-- ----------------------------------------------------------------------------
-- 4. Seed Subclass: Bonds
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_bonds (
    instrument_id INT,
    face_value DECIMAL(12, 2),
    coupon_rate DECIMAL(7, 4),
    coupon_frequency INT,
    issue_date DATE,
    maturity_date DATE
);

\copy temp_bonds FROM 'data_pipeline/bonds.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO BOND (instrument_id, face_value, coupon_rate, coupon_frequency, issue_date, maturity_date)
SELECT instrument_id, face_value, coupon_rate, coupon_frequency, issue_date, maturity_date 
FROM temp_bonds;

-- ----------------------------------------------------------------------------
-- 5. Seed Subclass: Options
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_options (
    instrument_id INT,
    underlying_id INT,
    strike DECIMAL(12, 2),
    expiry DATE,
    option_type VARCHAR(4)
);

\copy temp_options FROM 'data_pipeline/options.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO OPTION (instrument_id, underlying_id, strike, expiry, option_type)
SELECT instrument_id, underlying_id, strike, expiry, option_type 
FROM temp_options;

-- ----------------------------------------------------------------------------
-- 6. Seed Weak Entity: Price Bars
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_price_bars (
    instrument_id INT,
    timestamp TIMESTAMP,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT
);

\copy temp_price_bars FROM 'data_pipeline/price_bars.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO PRICE_BAR (instrument_id, timestamp, open, high, low, close, volume)
SELECT instrument_id, timestamp, open, high, low, close, volume 
FROM temp_price_bars;

-- ----------------------------------------------------------------------------
-- 7. Seed Positions (Initial House Inventory & User Portfolios)
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE temp_positions (
    position_id INT,
    account_id INT,
    instrument_id INT,
    quantity DECIMAL(15, 4),
    average_buy_price DECIMAL(12, 2)
);

\copy temp_positions FROM 'data_pipeline/positions.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO POSITION (position_id, account_id, instrument_id, quantity, average_buy_price)
SELECT position_id, account_id, instrument_id, quantity, average_buy_price 
FROM temp_positions;

-- ----------------------------------------------------------------------------
-- 8. Synchronize Auto-Increment Sequences
-- ----------------------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('"USER"', 'user_id'), COALESCE((SELECT MAX(user_id) FROM "USER"), 1));
SELECT setval(pg_get_serial_sequence('ACCOUNT', 'account_id'), COALESCE((SELECT MAX(account_id) FROM ACCOUNT), 1));
SELECT setval(pg_get_serial_sequence('INSTRUMENT', 'instrument_id'), COALESCE((SELECT MAX(instrument_id) FROM INSTRUMENT), 1));
SELECT setval(pg_get_serial_sequence('POSITION', 'position_id'), COALESCE((SELECT MAX(position_id) FROM POSITION), 1));

COMMIT;