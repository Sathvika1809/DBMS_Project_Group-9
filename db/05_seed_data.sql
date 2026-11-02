-- ============================================================================
-- CS F212 Database Systems — Project Data Population Pipeline
-- File: db/05_seed_data.sql
-- Author: Hakimkari Sathvika (Group 9)
-- Purpose: Bulk Data Ingestion using PostgreSQL COPY (FK-Safe Sequence)
-- ============================================================================

BEGIN;

-- 1. Load Master User Entities
\copy "USER"(User_id, Name, Email, Password_hash, Role, Created_at) FROM 'data_pipeline/seed_csvs/users.csv' WITH (FORMAT csv, HEADER true);

-- 2. Load User Financial Accounts
\copy ACCOUNT(Account_id, User_id, Cash_balance, Is_house, Created_at) FROM 'data_pipeline/seed_csvs/accounts.csv' WITH (FORMAT csv, HEADER true);

-- 3. Load Master Instrument Registry
\copy INSTRUMENT(Instrument_id, Symbol, Name, Instrument_type, Sector, Multiplier, Tick_size, Lot_size, Status) FROM 'data_pipeline/seed_csvs/instruments.csv' WITH (FORMAT csv, HEADER true);

-- 4. Load EER 8A Subclass Specialization Tables
\copy BOND(Instrument_id, Face_value, Coupon_rate, Coupon_frequency, Issue_date, Maturity_date) FROM 'data_pipeline/seed_csvs/bonds.csv' WITH (FORMAT csv, HEADER true);
\copy OPTION(Instrument_id, Underlying_id, Strike, Expiry, Option_type) FROM 'data_pipeline/seed_csvs/options.csv' WITH (FORMAT csv, HEADER true);

-- 5. Load Weak Entity Historical Market Data (700+ Records)
\copy PRICE_BAR(Instrument_id, Trade_date, Open, High, Low, Close, Volume) FROM 'data_pipeline/seed_csvs/price_bars.csv' WITH (FORMAT csv, HEADER true);

COMMIT;

-- Ingestion Verification Summary
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