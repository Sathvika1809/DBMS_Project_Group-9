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
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- 1. Master user entities
\copy "USER"(User_id, Name, Email, Password_hash, Role, Created_at) FROM '/data_pipeline/seed_csvs/users.csv' WITH (FORMAT csv, HEADER true);

-- 2. User financial accounts
\copy ACCOUNT(Account_id, User_id, Cash_balance, Is_house, Created_at) FROM '/data_pipeline/seed_csvs/accounts.csv' WITH (FORMAT csv, HEADER true);

-- 3. Master instrument registry
\copy INSTRUMENT(Instrument_id, Symbol, Name, Instrument_type, Sector, Multiplier, Tick_size, Lot_size, Status) FROM '/data_pipeline/seed_csvs/instruments.csv' WITH (FORMAT csv, HEADER true);

-- 4. EER 8A subclass tables
\copy BOND(Instrument_id, Face_value, Coupon_rate, Coupon_frequency, Issue_date, Maturity_date) FROM '/data_pipeline/seed_csvs/bonds.csv' WITH (FORMAT csv, HEADER true);
\copy OPTION(Instrument_id, Underlying_id, Strike, Expiry, Option_type) FROM '/data_pipeline/seed_csvs/options.csv' WITH (FORMAT csv, HEADER true);

-- 5. Weak entity: historical market data (~1,250 rows: 3 stocks + 1 option + 1 bond)
\copy PRICE_BAR(Instrument_id, Trade_date, Open, High, Low, Close, Volume) FROM '/data_pipeline/seed_csvs/price_bars.csv' WITH (FORMAT csv, HEADER true);

-- 6. House inventory (enable once the POSITION table exists in 01_schema.sql)
-- \copy POSITION(Account_id, Instrument_id, Qty, Avg_cost) FROM '/data_pipeline/seed_csvs/positions.csv' WITH (FORMAT csv, HEADER true);

-- 7. Advance SERIAL sequences past the explicit IDs loaded above, otherwise the
--    next app-created row collides with ID 1 (duplicate key).
SELECT setval(pg_get_serial_sequence('"USER"', 'user_id'),          (SELECT MAX(user_id) FROM "USER"));
SELECT setval(pg_get_serial_sequence('account', 'account_id'),      (SELECT MAX(account_id) FROM account));
SELECT setval(pg_get_serial_sequence('instrument', 'instrument_id'),(SELECT MAX(instrument_id) FROM instrument));

COMMIT;

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
SELECT 'PRICE_BAR', COUNT(*) FROM PRICE_BAR;