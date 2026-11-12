-- ============================================================================
-- db/05_seed_data.sql : bulk data ingestion with COPY (FK-safe order)
--
-- docker-compose mounts the CSVs at /data_pipeline/seed_csvs. To run this by
-- hand on the host, replace that path with your local one.
-- Regenerate CSVs:   python data_pipeline/generate_data.py
-- Re-seed from zero: docker compose down -v && docker compose up --build
-- ============================================================================

\set ON_ERROR_STOP on

-- 'replica' skips user triggers during the load, so AUDIT_LOG is not flooded
-- with one row per seeded record. FK checks are skipped too, but the load order
-- is FK-safe and the integrity report at the bottom verifies the result.
-- Needs superuser (the docker 'postgres' user is).
SET session_replication_role = replica;

BEGIN;

\copy "USER"(user_id, name, email, password_hash, role, created_at) FROM '/data_pipeline/seed_csvs/users.csv' WITH (FORMAT csv, HEADER true);
\copy ACCOUNT(account_id, user_id, account_type, cash_balance, created_at) FROM '/data_pipeline/seed_csvs/accounts.csv' WITH (FORMAT csv, HEADER true);
\copy INSTRUMENT(instrument_id, symbol, name, instrument_type, sector, multiplier, tick_size, lot_size, status) FROM '/data_pipeline/seed_csvs/instruments.csv' WITH (FORMAT csv, HEADER true);

-- EER 8A subclass tables
\copy BOND(instrument_id, face_value, coupon_rate, coupon_frequency, issue_date, maturity_date) FROM '/data_pipeline/seed_csvs/bonds.csv' WITH (FORMAT csv, HEADER true);
\copy OPTION(instrument_id, underlying_id, strike, expiry, option_type) FROM '/data_pipeline/seed_csvs/options.csv' WITH (FORMAT csv, HEADER true);

-- Weak entity: ~1,240 daily bars (3 stocks + 1 option + 1 bond)
\copy PRICE_BAR(instrument_id, trade_date, open, high, low, close, volume) FROM '/data_pipeline/seed_csvs/price_bars.csv' WITH (FORMAT csv, HEADER true);

-- House inventory (CSV: Account_id, Instrument_id, Qty, Avg_cost)
\copy POSITION(account_id, instrument_id, quantity, average_buy_price) FROM '/data_pipeline/seed_csvs/positions.csv' WITH (FORMAT csv, HEADER true);

-- Opening balances as DEPOSIT ledger rows, so cash_balance = SUM(ledger) holds from day one.
INSERT INTO CASH_LEDGER (account_id, entry_type, amount, value_date, created_at)
SELECT account_id, 'DEPOSIT', cash_balance, created_at::date, created_at
  FROM ACCOUNT WHERE cash_balance > 0;

-- Advance SERIAL sequences past the explicitly loaded IDs.
SELECT setval(pg_get_serial_sequence('"USER"', 'user_id'),           (SELECT MAX(user_id) FROM "USER"));
SELECT setval(pg_get_serial_sequence('account', 'account_id'),       (SELECT MAX(account_id) FROM account));
SELECT setval(pg_get_serial_sequence('instrument', 'instrument_id'), (SELECT MAX(instrument_id) FROM instrument));

COMMIT;

SET session_replication_role = DEFAULT;

-- Ingestion verification: expect 6 / 6 / 5 / 1 / 1 / 1240 / 5 / 6
SELECT 'USER' AS relation, COUNT(*) AS total_rows FROM "USER"
UNION ALL SELECT 'ACCOUNT',     COUNT(*) FROM ACCOUNT
UNION ALL SELECT 'INSTRUMENT',  COUNT(*) FROM INSTRUMENT
UNION ALL SELECT 'BOND',        COUNT(*) FROM BOND
UNION ALL SELECT 'OPTION',      COUNT(*) FROM OPTION
UNION ALL SELECT 'PRICE_BAR',   COUNT(*) FROM PRICE_BAR
UNION ALL SELECT 'POSITION',    COUNT(*) FROM POSITION
UNION ALL SELECT 'CASH_LEDGER', COUNT(*) FROM CASH_LEDGER;

-- Every row must show 0 violations (this also validates the rows loaded with triggers off).
SELECT * FROM integrity_report;
