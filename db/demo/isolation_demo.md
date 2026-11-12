# Isolation / locking demo (two psql sessions)

Open two terminals: `docker exec -it paper_trading_db psql -U postgres -d papertrading`

## A. Row lock blocks a concurrent writer
```sql
-- Session 1                                   -- Session 2
BEGIN;
SELECT cash_balance FROM ACCOUNT
 WHERE account_id = 102 FOR UPDATE;
                                               BEGIN;
                                               SELECT cash_balance FROM ACCOUNT
                                                WHERE account_id = 102 FOR UPDATE;   -- blocks
UPDATE ACCOUNT SET cash_balance = cash_balance - 100 WHERE account_id = 102;
COMMIT;                                        -- session 2 unblocks and sees the NEW balance
                                               ROLLBACK;
```

## B. Lost update without the lock (READ COMMITTED)
```sql
-- Session 1                                   -- Session 2
BEGIN;                                         BEGIN;
SELECT cash_balance FROM ACCOUNT WHERE account_id=102;   -- both read 500000
                                               SELECT cash_balance FROM ACCOUNT WHERE account_id=102;
UPDATE ACCOUNT SET cash_balance = 500000-100 WHERE account_id=102;
COMMIT;
                                               UPDATE ACCOUNT SET cash_balance = 500000-200 WHERE account_id=102;
                                               COMMIT;   -- result 499800, session 1's -100 is lost
```
Fix: add `FOR UPDATE` to both SELECTs (A), or use `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`
(session 2's UPDATE then fails with "could not serialize access due to concurrent update").

## C. Whole-engine demo
`python backend/tests/stress_test_concurrency.py` (all invariants pass) vs `--unsafe` (invariants break).
After either run: `SELECT * FROM integrity_report;`
