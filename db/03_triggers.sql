-- ============================================================================
-- db/03_triggers.sql
--   1. Audit logging (generic)
--   2. Subtype disjointness (EER specialization)
--   3. Order validation (status, tick size, lot size, expiry)
--   4. Trade validation
--   5. ORDER_FILL validation + ORDER.filled_qty/status synchronization
--   6. Append-only ledger and trades
-- ============================================================================

-- 1. AUDIT ------------------------------------------------------------------
-- TG_ARGV[0] names the PK column to store in AUDIT_LOG.row_id (omit for composite PKs).
CREATE OR REPLACE FUNCTION fn_audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_new JSONB := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
    v_old JSONB := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
BEGIN
    IF TG_OP = 'UPDATE' AND v_old = v_new THEN
        RETURN NULL;
    END IF;
    INSERT INTO AUDIT_LOG (table_name, row_id, action, old_values, new_values)
    VALUES (TG_TABLE_NAME,
            CASE WHEN TG_NARGS > 0 THEN (COALESCE(v_new, v_old) ->> TG_ARGV[0])::BIGINT END,
            TG_OP, v_old, v_new);
    RETURN NULL;
END $$;

CREATE TRIGGER trg_audit_account    AFTER INSERT OR UPDATE OR DELETE ON ACCOUNT
    FOR EACH ROW EXECUTE FUNCTION fn_audit('account_id');
CREATE TRIGGER trg_audit_order      AFTER INSERT OR UPDATE OR DELETE ON "ORDER"
    FOR EACH ROW EXECUTE FUNCTION fn_audit('order_id');
CREATE TRIGGER trg_audit_trade      AFTER INSERT OR UPDATE OR DELETE ON TRADE
    FOR EACH ROW EXECUTE FUNCTION fn_audit('trade_id');
CREATE TRIGGER trg_audit_position   AFTER INSERT OR UPDATE OR DELETE ON POSITION
    FOR EACH ROW EXECUTE FUNCTION fn_audit();
CREATE TRIGGER trg_audit_instrument AFTER INSERT OR UPDATE OR DELETE ON INSTRUMENT
    FOR EACH ROW EXECUTE FUNCTION fn_audit('instrument_id');

-- 2. SUBTYPE DISJOINTNESS ----------------------------------------------------
-- A BOND row must belong to an INSTRUMENT of type BOND (likewise OPTION), and an
-- option's underlying must be a STOCK.
CREATE OR REPLACE FUNCTION fn_check_subtype() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_type TEXT;
BEGIN
    SELECT instrument_type INTO v_type FROM INSTRUMENT WHERE instrument_id = NEW.instrument_id;
    IF v_type IS DISTINCT FROM TG_ARGV[0] THEN
        RAISE EXCEPTION 'Instrument % has type %, so it cannot have a % subtype row',
            NEW.instrument_id, COALESCE(v_type, 'NULL'), TG_ARGV[0]
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_ARGV[0] = 'OPTION' THEN
        PERFORM 1 FROM INSTRUMENT WHERE instrument_id = NEW.underlying_id AND instrument_type = 'STOCK';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Underlying instrument % must be a STOCK', NEW.underlying_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_bond_subtype   BEFORE INSERT OR UPDATE ON BOND
    FOR EACH ROW EXECUTE FUNCTION fn_check_subtype('BOND');
CREATE TRIGGER trg_option_subtype BEFORE INSERT OR UPDATE ON OPTION
    FOR EACH ROW EXECUTE FUNCTION fn_check_subtype('OPTION');

-- ...and the reverse: INSTRUMENT.instrument_type cannot change under an existing subtype row.
CREATE OR REPLACE FUNCTION fn_guard_instrument_type() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.instrument_type <> OLD.instrument_type
       AND (EXISTS (SELECT 1 FROM BOND   WHERE instrument_id = OLD.instrument_id)
         OR EXISTS (SELECT 1 FROM OPTION WHERE instrument_id = OLD.instrument_id)) THEN
        RAISE EXCEPTION 'Cannot change type of instrument %: a subtype row exists', OLD.instrument_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_guard_instrument_type BEFORE UPDATE OF instrument_type ON INSTRUMENT
    FOR EACH ROW EXECUTE FUNCTION fn_guard_instrument_type();

-- 3. ORDER VALIDATION --------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validate_order() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_inst   INSTRUMENT%ROWTYPE;
    v_expiry DATE;
BEGIN
    SELECT * INTO v_inst FROM INSTRUMENT WHERE instrument_id = NEW.instrument_id;
    IF v_inst.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Instrument % is %: orders are rejected', v_inst.symbol, v_inst.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_inst.instrument_type = 'OPTION' THEN
        SELECT expiry INTO v_expiry FROM OPTION WHERE instrument_id = NEW.instrument_id;
        IF v_expiry < CURRENT_DATE THEN
            RAISE EXCEPTION 'Option % expired on %', v_inst.symbol, v_expiry
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF MOD(NEW.price, v_inst.tick_size) <> 0 THEN
        RAISE EXCEPTION 'Price % is not a multiple of the tick size % for %',
            NEW.price, v_inst.tick_size, v_inst.symbol USING ERRCODE = 'check_violation';
    END IF;
    IF MOD(NEW.qty, v_inst.lot_size) <> 0 THEN
        RAISE EXCEPTION 'Quantity % is not a multiple of the lot size % for %',
            NEW.qty, v_inst.lot_size, v_inst.symbol USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_validate_order BEFORE INSERT ON "ORDER"
    FOR EACH ROW EXECUTE FUNCTION fn_validate_order();

-- 4. TRADE VALIDATION --------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validate_trade() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    b "ORDER"%ROWTYPE;
    s "ORDER"%ROWTYPE;
BEGIN
    SELECT * INTO b FROM "ORDER" WHERE order_id = NEW.buy_order_id;
    SELECT * INTO s FROM "ORDER" WHERE order_id = NEW.sell_order_id;
    IF b.side <> 'BUY' OR s.side <> 'SELL' THEN
        RAISE EXCEPTION 'Trade must pair a BUY order with a SELL order' USING ERRCODE = 'check_violation';
    END IF;
    IF b.instrument_id <> s.instrument_id THEN
        RAISE EXCEPTION 'Trade orders are for different instruments' USING ERRCODE = 'check_violation';
    END IF;
    IF b.account_id = s.account_id THEN
        RAISE EXCEPTION 'Self-trade: both orders belong to account %', b.account_id USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.price > b.price OR NEW.price < s.price THEN
        RAISE EXCEPTION 'Trade price % is outside the limits of the two orders', NEW.price
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_validate_trade BEFORE INSERT ON TRADE
    FOR EACH ROW EXECUTE FUNCTION fn_validate_trade();

-- 5. ORDER_FILL: validation + synchronization of the denormalized ORDER columns
CREATE OR REPLACE FUNCTION fn_fill_validate() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    t TRADE%ROWTYPE;
BEGIN
    SELECT * INTO t FROM TRADE WHERE trade_id = NEW.trade_id;
    IF NEW.order_id NOT IN (t.buy_order_id, t.sell_order_id) THEN
        RAISE EXCEPTION 'Order % is not a party to trade %', NEW.order_id, NEW.trade_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.qty <> t.qty OR NEW.price <> t.price THEN
        RAISE EXCEPTION 'Fill must match its trade (qty %, price %)', t.qty, t.price
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION fn_fill_sync() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE "ORDER"
       SET filled_qty = filled_qty + NEW.qty,
           status     = CASE WHEN filled_qty + NEW.qty >= qty THEN 'FILLED' ELSE 'PARTIAL' END
     WHERE order_id = NEW.order_id;
    RETURN NULL;
END $$;

CREATE TRIGGER trg_fill_validate BEFORE INSERT ON ORDER_FILL
    FOR EACH ROW EXECUTE FUNCTION fn_fill_validate();
CREATE TRIGGER trg_fill_sync     AFTER  INSERT ON ORDER_FILL
    FOR EACH ROW EXECUTE FUNCTION fn_fill_sync();

-- 6. APPEND-ONLY TABLES ------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_append_only() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END $$;

CREATE TRIGGER trg_ledger_append_only BEFORE UPDATE OR DELETE ON CASH_LEDGER
    FOR EACH ROW EXECUTE FUNCTION fn_append_only();
CREATE TRIGGER trg_trade_append_only  BEFORE UPDATE OR DELETE ON TRADE
    FOR EACH ROW EXECUTE FUNCTION fn_append_only();
