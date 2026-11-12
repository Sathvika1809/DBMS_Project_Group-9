-- ============================================================================
-- db/04_procedures.sql : the matching engine and end-of-day processing
--
--   match_and_settle(order_id)         SAFE: advisory book lock + FOR UPDATE
--   match_and_settle_unsafe(order_id)  same logic, NO locks (concurrency demo only)
--   cancel_order(order_id, account_id)
--   end_of_day(date)                   coupons, bond redemption, option expiry
--   approx_ytm(...)                    bond yield-to-maturity approximation
--
-- Everything runs inside the caller's transaction: if any statement fails, the
-- order insert, trades, fills, ledger rows, positions and balances all roll back.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- One side of a settlement: apply a cash delta and a quantity delta to one account.
-- Deliberately a read-modify-write. In SAFE mode the caller already holds
-- FOR UPDATE locks on the ACCOUNT and POSITION rows, so the read cannot be
-- stale. In UNSAFE mode there are no locks and pg_sleep widens the race window,
-- which produces lost updates (cash and shares silently appear or vanish).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _settle_leg(
    p_account    INT,
    p_instrument INT,
    p_cash_delta NUMERIC,
    p_qty_delta  NUMERIC,
    p_price      NUMERIC,
    p_safe       BOOLEAN
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_cash    NUMERIC;
    v_qty     NUMERIC;
    v_avg     NUMERIC;
    v_new_qty NUMERIC;
    v_new_avg NUMERIC;
BEGIN
    SELECT cash_balance INTO v_cash FROM ACCOUNT WHERE account_id = p_account;
    SELECT quantity, average_buy_price INTO v_qty, v_avg
      FROM POSITION WHERE account_id = p_account AND instrument_id = p_instrument;
    IF NOT FOUND THEN
        v_qty := 0;
        v_avg := 0;
    END IF;

    IF NOT p_safe THEN
        PERFORM pg_sleep(0.005);
    END IF;

    v_new_qty := v_qty + p_qty_delta;
    IF p_qty_delta > 0 THEN   -- buying: weighted-average cost
        v_new_avg := ROUND((v_qty * v_avg + p_qty_delta * p_price) / v_new_qty, 2);
    ELSE
        v_new_avg := v_avg;
    END IF;

    UPDATE ACCOUNT SET cash_balance = v_cash + p_cash_delta WHERE account_id = p_account;

    INSERT INTO POSITION (account_id, instrument_id, quantity, average_buy_price)
    VALUES (p_account, p_instrument, v_new_qty, v_new_avg)
    ON CONFLICT (account_id, instrument_id)
    DO UPDATE SET quantity = EXCLUDED.quantity, average_buy_price = EXCLUDED.average_buy_price;
END $$;

-- ---------------------------------------------------------------------------
-- Core matching loop (price-time priority, trades execute at the resting
-- order's price).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _match_core(p_order_id INT, p_safe BOOLEAN)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_ord        "ORDER"%ROWTYPE;
    v_rest       "ORDER"%ROWTYPE;
    v_mult       NUMERIC;
    v_cash       NUMERIC;
    v_held       NUMERIC;
    v_reserved   NUMERIC;
    v_remaining  NUMERIC;
    v_fill       NUMERIC;
    v_amount     NUMERIC;
    v_trade_id   INT;
    v_buy_order  INT;
    v_sell_order INT;
    v_buyer      INT;
    v_seller     INT;
BEGIN
    SELECT * INTO v_ord FROM "ORDER" WHERE order_id = p_order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % does not exist', p_order_id;
    END IF;

    IF p_safe THEN
        -- One matcher per book at a time (the way real exchanges run one engine
        -- per symbol). Released automatically at COMMIT/ROLLBACK.
        PERFORM pg_advisory_xact_lock(1, v_ord.instrument_id);
        SELECT * INTO v_ord FROM "ORDER" WHERE order_id = p_order_id FOR UPDATE;
        -- Serialize everything this account does with its cash and holdings.
        PERFORM 1 FROM ACCOUNT WHERE account_id = v_ord.account_id FOR UPDATE;
    END IF;

    IF v_ord.status NOT IN ('OPEN', 'PARTIAL') THEN
        RAISE EXCEPTION 'Order % is % and cannot be matched', p_order_id, v_ord.status;
    END IF;

    SELECT multiplier INTO v_mult FROM INSTRUMENT WHERE instrument_id = v_ord.instrument_id;
    v_remaining := v_ord.qty - v_ord.filled_qty;

    -- ---- buying power / holdings check (net of the account's other open orders)
    IF v_ord.side = 'BUY' THEN
        SELECT cash_balance INTO v_cash FROM ACCOUNT WHERE account_id = v_ord.account_id;
        SELECT COALESCE(SUM((o.qty - o.filled_qty) * o.price * i.multiplier), 0) INTO v_reserved
          FROM "ORDER" o JOIN INSTRUMENT i ON i.instrument_id = o.instrument_id
         WHERE o.account_id = v_ord.account_id AND o.side = 'BUY'
           AND o.status IN ('OPEN', 'PARTIAL') AND o.order_id <> v_ord.order_id;
        IF v_cash - v_reserved < v_remaining * v_ord.price * v_mult THEN
            RAISE EXCEPTION 'Insufficient buying power: cash %, reserved by open buy orders %, this order needs up to %',
                v_cash, v_reserved, ROUND(v_remaining * v_ord.price * v_mult, 2)
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        SELECT quantity INTO v_held FROM POSITION
         WHERE account_id = v_ord.account_id AND instrument_id = v_ord.instrument_id;
        v_held := COALESCE(v_held, 0);
        SELECT COALESCE(SUM(o.qty - o.filled_qty), 0) INTO v_reserved
          FROM "ORDER" o
         WHERE o.account_id = v_ord.account_id AND o.instrument_id = v_ord.instrument_id
           AND o.side = 'SELL' AND o.status IN ('OPEN', 'PARTIAL') AND o.order_id <> v_ord.order_id;
        IF v_held - v_reserved < v_remaining THEN
            RAISE EXCEPTION 'Insufficient holdings: own %, already committed to open sell orders %, this order sells %',
                v_held, v_reserved, v_remaining
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- ---- matching loop
    LOOP
        EXIT WHEN v_remaining <= 0;

        IF v_ord.side = 'BUY' THEN
            SELECT * INTO v_rest FROM "ORDER"
             WHERE instrument_id = v_ord.instrument_id AND side = 'SELL'
               AND status IN ('OPEN', 'PARTIAL') AND price <= v_ord.price
               AND account_id <> v_ord.account_id          -- no self-trades
             ORDER BY price ASC, created_at ASC, order_id ASC
             LIMIT 1;
        ELSE
            SELECT * INTO v_rest FROM "ORDER"
             WHERE instrument_id = v_ord.instrument_id AND side = 'BUY'
               AND status IN ('OPEN', 'PARTIAL') AND price >= v_ord.price
               AND account_id <> v_ord.account_id
             ORDER BY price DESC, created_at ASC, order_id ASC
             LIMIT 1;
        END IF;
        EXIT WHEN NOT FOUND;

        v_fill := LEAST(v_remaining, v_rest.qty - v_rest.filled_qty);
        EXIT WHEN v_fill <= 0;

        IF v_ord.side = 'BUY' THEN
            v_buy_order := v_ord.order_id;  v_sell_order := v_rest.order_id;
            v_buyer := v_ord.account_id;    v_seller := v_rest.account_id;
        ELSE
            v_buy_order := v_rest.order_id; v_sell_order := v_ord.order_id;
            v_buyer := v_rest.account_id;   v_seller := v_ord.account_id;
        END IF;

        IF p_safe THEN
            -- Lock both counterparties in account_id order to avoid deadlocks.
            PERFORM 1 FROM ACCOUNT
             WHERE account_id IN (v_buyer, v_seller) ORDER BY account_id FOR UPDATE;
            PERFORM 1 FROM POSITION
             WHERE instrument_id = v_ord.instrument_id AND account_id IN (v_buyer, v_seller)
             ORDER BY account_id FOR UPDATE;
        END IF;

        v_amount := ROUND(v_rest.price * v_fill * v_mult, 2);

        INSERT INTO TRADE (buy_order_id, sell_order_id, price, qty)
        VALUES (v_buy_order, v_sell_order, v_rest.price, v_fill)
        RETURNING trade_id INTO v_trade_id;

        -- One fill per side. The AFTER INSERT trigger on ORDER_FILL updates
        -- ORDER.filled_qty and ORDER.status.
        INSERT INTO ORDER_FILL (order_id, fill_seq, trade_id, qty, price)
        SELECT o,
               COALESCE((SELECT MAX(f.fill_seq) FROM ORDER_FILL f WHERE f.order_id = o), 0) + 1,
               v_trade_id, v_fill, v_rest.price
          FROM unnest(ARRAY[v_buy_order, v_sell_order]) AS o;

        INSERT INTO CASH_LEDGER (account_id, trade_id, entry_type, amount)
        VALUES (v_buyer,  v_trade_id, 'BUY',  -v_amount),
               (v_seller, v_trade_id, 'SELL',  v_amount);

        PERFORM _settle_leg(v_buyer,  v_ord.instrument_id, -v_amount,  v_fill, v_rest.price, p_safe);
        PERFORM _settle_leg(v_seller, v_ord.instrument_id,  v_amount, -v_fill, v_rest.price, p_safe);

        v_remaining := v_remaining - v_fill;
    END LOOP;
END $$;

CREATE OR REPLACE PROCEDURE match_and_settle(p_order_id INT)
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM _match_core(p_order_id, TRUE);
END $$;

-- Same logic with locking switched off. For the concurrency demo ONLY.
CREATE OR REPLACE PROCEDURE match_and_settle_unsafe(p_order_id INT)
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM _match_core(p_order_id, FALSE);
END $$;

-- ---------------------------------------------------------------------------
-- Cancel an open order (takes the same book lock as the matcher).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE cancel_order(p_order_id INT, p_account_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_instrument INT;
BEGIN
    SELECT instrument_id INTO v_instrument
      FROM "ORDER" WHERE order_id = p_order_id AND account_id = p_account_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found for account %', p_order_id, p_account_id;
    END IF;

    PERFORM pg_advisory_xact_lock(1, v_instrument);

    UPDATE "ORDER" SET status = 'CANCELLED'
     WHERE order_id = p_order_id AND status IN ('OPEN', 'PARTIAL');
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % is not open (already filled or cancelled)', p_order_id;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Bond yield-to-maturity approximation: (C + (100 - P) / years) / ((100 + P) / 2)
-- P = clean price per 100 face, C = annual coupon per 100. Returns a fraction.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION approx_ytm(p_price NUMERIC, p_coupon_rate NUMERIC, p_maturity DATE, p_on DATE)
RETURNS NUMERIC LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_maturity <= p_on THEN NULL
                ELSE ROUND((p_coupon_rate * 100 + (100 - p_price) / ((p_maturity - p_on) / 365.0))
                           / ((100 + p_price) / 2.0), 4) END
$$;

-- ---------------------------------------------------------------------------
-- End-of-day processing for p_date:
--   1. pay coupons to bond holders on coupon dates (idempotent through the
--      UNIQUE constraint on CASH_LEDGER)
--   2. redeem matured bonds at face value
--   3. cash-settle expired options at intrinsic value, paid by the HOUSE account
--   Expired instruments get status EXPIRED and their open orders are cancelled.
-- Coupons and redemptions are issuer payments, so total cash in the system grows
-- by exactly the amounts in the COUPON/REDEMPTION ledger rows. Option payouts are
-- zero-sum (HOUSE pays the holders).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE end_of_day(p_date DATE DEFAULT CURRENT_DATE)
LANGUAGE plpgsql AS $$
DECLARE
    r           RECORD;
    v_house     INT;
    v_spot      NUMERIC;
    v_intrinsic NUMERIC;
    v_total     NUMERIC;
BEGIN
    SELECT account_id INTO v_house FROM ACCOUNT WHERE account_type = 'HOUSE';
    IF v_house IS NULL THEN
        RAISE EXCEPTION 'No HOUSE account exists';
    END IF;

    -- 1. coupons
    FOR r IN
        SELECT b.instrument_id, b.face_value * b.coupon_rate / b.coupon_frequency AS per_unit
          FROM BOND b JOIN INSTRUMENT i ON i.instrument_id = b.instrument_id
         WHERE i.status = 'ACTIVE' AND b.coupon_rate > 0
           AND p_date > b.issue_date AND p_date <= b.maturity_date
           AND EXISTS (SELECT 1
                         FROM generate_series(b.maturity_date::timestamp, b.issue_date::timestamp,
                                              make_interval(months => -(12 / b.coupon_frequency))) AS cd
                        WHERE cd::date = p_date)
    LOOP
        WITH paid AS (
            INSERT INTO CASH_LEDGER (account_id, instrument_id, entry_type, amount, value_date)
            SELECT p.account_id, r.instrument_id, 'COUPON', ROUND(r.per_unit * p.quantity, 2), p_date
              FROM POSITION p
             WHERE p.instrument_id = r.instrument_id AND ROUND(r.per_unit * p.quantity, 2) <> 0
            ON CONFLICT (account_id, instrument_id, entry_type, value_date) DO NOTHING
            RETURNING account_id, amount
        )
        UPDATE ACCOUNT a SET cash_balance = a.cash_balance + paid.amount
          FROM paid WHERE a.account_id = paid.account_id;
    END LOOP;

    -- 2. bond redemption
    FOR r IN
        SELECT b.instrument_id, b.face_value
          FROM BOND b JOIN INSTRUMENT i ON i.instrument_id = b.instrument_id
         WHERE i.status = 'ACTIVE' AND b.maturity_date <= p_date
    LOOP
        WITH paid AS (
            INSERT INTO CASH_LEDGER (account_id, instrument_id, entry_type, amount, value_date)
            SELECT p.account_id, r.instrument_id, 'REDEMPTION', ROUND(r.face_value * p.quantity, 2), p_date
              FROM POSITION p
             WHERE p.instrument_id = r.instrument_id AND ROUND(r.face_value * p.quantity, 2) <> 0
            ON CONFLICT (account_id, instrument_id, entry_type, value_date) DO NOTHING
            RETURNING account_id, amount
        )
        UPDATE ACCOUNT a SET cash_balance = a.cash_balance + paid.amount
          FROM paid WHERE a.account_id = paid.account_id;

        UPDATE POSITION SET quantity = 0 WHERE instrument_id = r.instrument_id;
        UPDATE "ORDER" SET status = 'CANCELLED'
         WHERE instrument_id = r.instrument_id AND status IN ('OPEN', 'PARTIAL');
        UPDATE INSTRUMENT SET status = 'EXPIRED' WHERE instrument_id = r.instrument_id;
    END LOOP;

    -- 3. option expiry (cash-settled, European)
    FOR r IN
        SELECT o.instrument_id, o.underlying_id, o.strike, o.option_type, i.multiplier
          FROM OPTION o JOIN INSTRUMENT i ON i.instrument_id = o.instrument_id
         WHERE i.status = 'ACTIVE' AND o.expiry <= p_date
    LOOP
        SELECT close INTO v_spot FROM PRICE_BAR
         WHERE instrument_id = r.underlying_id AND trade_date <= p_date
         ORDER BY trade_date DESC LIMIT 1;

        v_intrinsic := COALESCE(
            CASE WHEN r.option_type = 'CALL' THEN GREATEST(v_spot - r.strike, 0)
                 ELSE GREATEST(r.strike - v_spot, 0) END, 0);

        SELECT COALESCE(SUM(ROUND(v_intrinsic * r.multiplier * p.quantity, 2)), 0) INTO v_total
          FROM POSITION p
         WHERE p.instrument_id = r.instrument_id AND p.account_id <> v_house;

        IF v_total > 0 THEN
            WITH paid AS (
                INSERT INTO CASH_LEDGER (account_id, instrument_id, entry_type, amount, value_date)
                SELECT p.account_id, r.instrument_id, 'EXERCISE',
                       ROUND(v_intrinsic * r.multiplier * p.quantity, 2), p_date
                  FROM POSITION p
                 WHERE p.instrument_id = r.instrument_id AND p.account_id <> v_house
                   AND ROUND(v_intrinsic * r.multiplier * p.quantity, 2) <> 0
                ON CONFLICT (account_id, instrument_id, entry_type, value_date) DO NOTHING
                RETURNING account_id, amount
            )
            UPDATE ACCOUNT a SET cash_balance = a.cash_balance + paid.amount
              FROM paid WHERE a.account_id = paid.account_id;

            INSERT INTO CASH_LEDGER (account_id, instrument_id, entry_type, amount, value_date)
            VALUES (v_house, r.instrument_id, 'EXERCISE', -v_total, p_date);
            UPDATE ACCOUNT SET cash_balance = cash_balance - v_total WHERE account_id = v_house;
        END IF;

        UPDATE POSITION SET quantity = 0 WHERE instrument_id = r.instrument_id;
        UPDATE "ORDER" SET status = 'CANCELLED'
         WHERE instrument_id = r.instrument_id AND status IN ('OPEN', 'PARTIAL');
        UPDATE INSTRUMENT SET status = 'EXPIRED' WHERE instrument_id = r.instrument_id;
    END LOOP;
END $$;
