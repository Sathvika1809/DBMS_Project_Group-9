-- ============================================================================
-- CS F212 Database Systems — Project Data Population Pipeline
-- File: db/05_seed_data.sql
-- Author: Hakimkari Sathvika (Group 9)
-- Purpose: Bulk data ingestion using PostgreSQL COPY (FK-safe order)
--
-- Paths are absolute because docker-compose mounts the CSVs at
-- /data_pipeline/seed_csvs inside the container. To run this by hand on the
-- host, replace /data_pipeline/seed_csvs with your local path.
-- Regenerate the CSVs with:  python data_pipeline/generate_data.py
-- Re-seed from scratch with:  docker compose down -v && docker compose up
--
-- Column lists follow db/01_schema.sql. The CSV header row is skipped, so the
-- lists below map to the CSV columns by position.
-- ============================================================================

\set ON_ERROR_STOP on

-- Seed rows must not fire the audit trigger (03_triggers.sql), otherwise
-- AUDIT_LOG fills with one INSERT row per seeded record. 'replica' skips
-- user triggers (and FK checks, which is fine: the load order below is FK-safe
-- and the verification counts at the end confirm every table loaded).
-- Needs superuser, which the docker 'postgres' user is.
SET session_replication_role = replica;

BEGIN;

-- 1. Master user entities
\copy "USER"(user_id, name, email, password_hash, role, created_at) FROM '/data_pipeline/seed_csvs/users.csv' WITH (FORMAT csv, HEADER true);

-- 2. User financial accounts (CSV: Account_id, User_id, Account_type, Cash_balance, Created_at)
\copy ACCOUNT(account_id, user_id, account_type, cash_balance, created_at) FROM '/data_pipeline/seed_csvs/accounts.csv' WITH (FORMAT csv, HEADER true);

-- 3. Master instrument registry
\copy INSTRUMENT(instrument_id, symbol, name, instrument_type, sector, multiplier, tick_size, lot_size, status) FROM '/data_pipeline/seed_csvs/instruments.csv' WITH (FORMAT csv, HEADER true);

-- 4. EER 8A subclass tables
\copy BOND(instrument_id, face_value, coupon_rate, coupon_frequency, issue_date, maturity_date) FROM '/data_pipeline/seed_csvs/bonds.csv' WITH (FORMAT csv, HEADER true);
\copy OPTION(instrument_id, underlying_id, strike, expiry, option_type) FROM '/data_pipeline/seed_csvs/options.csv' WITH (FORMAT csv, HEADER true);

-- 5. Weak entity: historical market data (~1,240 rows: 3 stocks + 1 option + 1 bond, 248 trading days each)
--    The schema's PRICE_BAR date column is named "timestamp" (the report says Trade_date).
\copy PRICE_BAR(instrument_id, "timestamp", open, high, low, close, volume) FROM '/data_pipeline/seed_csvs/price_bars.csv' WITH (FORMAT csv, HEADER true);

-- 6. House inventory (CSV: Account_id, Instrument_id, Qty, Avg_cost); position_id is auto-generated
\copy POSITION(account_id, instrument_id, quantity, average_buy_price) FROM '/data_pipeline/seed_csvs/positions.csv' WITH (FORMAT csv, HEADER true);

-- 7. Advance SERIAL sequences past the explicit IDs loaded above, otherwise the
--    next app-created row collides with ID 1 (duplicate key).
SELECT setval(pg_get_serial_sequence('"USER"', 'user_id'),           (SELECT MAX(user_id) FROM "USER"));
SELECT setval(pg_get_serial_sequence('account', 'account_id'),       (SELECT MAX(account_id) FROM account));
SELECT setval(pg_get_serial_sequence('instrument', 'instrument_id'), (SELECT MAX(instrument_id) FROM instrument));

COMMIT;

-- Back to normal behaviour for everything after the seed.
SET session_replication_role = DEFAULT;

-- Ingestion verification summary
SELECT 'USER' AS Relation, COUNT(*) AS Total_Rows FROM "USER"
UNION ALL
SELECT 'ACCOUNT', COUNT(*) FROM ACCOUNT
UNION ALL
SELECT 'INSTRUMENT', COUNT(*) FROM INSTRUMENT
UNION ALL
SELECT 'BOND', COUNT(*) FROM BOND
UNION ALL
SELECT 'OPTION', COUNT(*) FROM OPTION
UNION ALL
SELECT 'PRICE_BAR', COUNT(*) FROM PRICE_BAR
UNION ALL
SELECT 'POSITION', COUNT(*) FROM POSITION;