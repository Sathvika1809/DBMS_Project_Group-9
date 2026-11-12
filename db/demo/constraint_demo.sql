-- ============================================================================
-- Constraint-enforcement demo. Every block must print "REJECTED".
-- Run: docker exec -i paper_trading_db psql -U postgres -d papertrading < db/demo/constraint_demo.sql
-- Each DO block rolls back its own changes when the error is caught.
-- ============================================================================
\set ON_ERROR_STOP off

-- 1. Overspend: account 102 (500,000 cash) tries to buy 1,000 RELIANCE at ~1,300
DO $$ DECLARE v INT; BEGIN
    INSERT INTO "ORDER"(account_id, instrument_id, side, price, qty) VALUES (102, 1, 'BUY', 1300.00, 1000) RETURNING order_id INTO v;
    CALL match_and_settle(v);
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '1 overspend -> REJECTED: %', SQLERRM; END $$;

-- 2. Oversell: account 102 owns no RELIANCE
DO $$ DECLARE v INT; BEGIN
    INSERT INTO "ORDER"(account_id, instrument_id, side, price, qty) VALUES (102, 1, 'SELL', 1300.00, 5) RETURNING order_id INTO v;
    CALL match_and_settle(v);
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '2 oversell -> REJECTED: %', SQLERRM; END $$;

-- 3. Bad tick size (RELIANCE tick = 0.05)
DO $$ BEGIN
    INSERT INTO "ORDER"(account_id, instrument_id, side, price, qty) VALUES (102, 1, 'BUY', 1300.03, 1);
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '3 tick size -> REJECTED: %', SQLERRM; END $$;

-- 4. Order on a halted/expired instrument
DO $$ BEGIN
    UPDATE INSTRUMENT SET status = 'HALTED' WHERE instrument_id = 2;
    INSERT INTO "ORDER"(account_id, instrument_id, side, price, qty) VALUES (102, 2, 'BUY', 2400.00, 1);
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '4 halted instrument -> REJECTED: %', SQLERRM; END $$;

-- 5. Wrong subtype: a BOND row for a STOCK
DO $$ BEGIN
    INSERT INTO BOND VALUES (1, 1000, 0.07, 2, '2024-01-01', '2030-01-01');
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '5 wrong subtype -> REJECTED: %', SQLERRM; END $$;

-- 6. Double coupon payout (UNIQUE on CASH_LEDGER)
DO $$ BEGIN
    INSERT INTO CASH_LEDGER(account_id, instrument_id, entry_type, amount, value_date) VALUES (101, 4, 'COUPON', 100, '2026-10-15');
    INSERT INTO CASH_LEDGER(account_id, instrument_id, entry_type, amount, value_date) VALUES (101, 4, 'COUPON', 100, '2026-10-15');
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '6 double coupon -> REJECTED: %', SQLERRM; END $$;

-- 7. Negative cash
DO $$ BEGIN
    UPDATE ACCOUNT SET cash_balance = -1 WHERE account_id = 102;
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '7 negative cash -> REJECTED: %', SQLERRM; END $$;

-- 8. Tampering with the ledger
DO $$ BEGIN
    UPDATE CASH_LEDGER SET amount = 1 WHERE ledger_id = 1;
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '8 ledger tampering -> REJECTED: %', SQLERRM; END $$;

-- 9. Status and filled_qty disagreeing
DO $$ DECLARE v INT; BEGIN
    INSERT INTO "ORDER"(account_id, instrument_id, side, price, qty, filled_qty, status) VALUES (102, 1, 'BUY', 1300.00, 1, 0, 'FILLED') RETURNING order_id INTO v;
    RAISE NOTICE 'NOT REJECTED (bug)';
EXCEPTION WHEN OTHERS THEN RAISE NOTICE '9 status/filled mismatch -> REJECTED: %', SQLERRM; END $$;
