# Paper-Trading Exchange: CS F212 Database Systems, Group 9
BITS Pilani, Hyderabad Campus

A mini stock exchange with fake money, built around the database. Users place **limit orders** on stocks, bonds and options. Matching and settlement run **inside PostgreSQL as one atomic transaction**, so cash, positions and the order book stay correct under concurrent trading.

## Quick start
```bash
docker compose down -v        # only needed when re-seeding
docker compose up --build
# UI        http://localhost:3000
# API docs  http://localhost:8000/docs
```
Check the seed: `docker exec -it paper_trading_db psql -U postgres -d papertrading -c "SELECT * FROM integrity_report;"` (all zeros).

## Architecture
```
Next.js (React)  ->  FastAPI + psycopg3 (raw SQL, no ORM)  ->  PostgreSQL 16
 thin UI              validation, calls procedures              12 tables, triggers, views,
                                                                 matching engine, end-of-day
```

## Database features (the point of the project)
| Feature | Where |
|---|---|
| 12 relations in BCNF, EER specialization (INSTRUMENT -> BOND / OPTION, option 8A), 2 weak entities, 1 M:N | `db/01_schema.sql` |
| Matching engine: price-time priority, partial fills, buying-power and holdings checks, one atomic transaction | `match_and_settle` in `db/04_procedures.sql` |
| Locking: per-book advisory lock + `SELECT ... FOR UPDATE` on accounts and positions (sorted order to avoid deadlocks) | `_match_core` |
| Unlocked variant to demonstrate lost updates | `match_and_settle_unsafe` |
| Triggers: audit log, subtype disjointness, order validation (tick, lot, status, expiry), trade validation, fill sync, append-only ledger | `db/03_triggers.sql` |
| Views: `portfolio_view`, `order_book_view`, `last_price_view`, `integrity_report` | `db/02_views_indexes.sql` |
| Partial indexes, one per book side, in price-time order | `db/02_views_indexes.sql` |
| End of day: coupons, bond redemption, option cash settlement (idempotent through a UNIQUE constraint) | `end_of_day` |
| 7 analytical queries (CTE, window functions, LATERAL, correlated subquery, FILTER) | `db/analytics_queries.sql` |

## Design decisions
| Decision | Why |
|---|---|
| Limit orders only | Cost is bounded by the limit price, so buying power can be checked up front. Market orders add edge cases without adding DBMS concepts. |
| Matching in PL/pgSQL | Trade, fills, ledger, positions and balances commit or roll back together. |
| Buying power is net of open orders | Each order is checked against cash minus what the account's other open buys reserve (same for holdings and sells). Resting orders therefore never become unfundable. |
| One matcher per instrument | `pg_advisory_xact_lock` serializes a book, like a real exchange's single-threaded engine. Account and position rows are still locked with `FOR UPDATE` because accounts trade several instruments. |
| Trades execute at the resting order's price | Standard price-time priority. |
| Deliberate denormalization | `ACCOUNT.cash_balance`, `POSITION`, `ORDER.filled_qty` are derivable from `CASH_LEDGER`, `TRADE` and `ORDER_FILL`. They are updated in the same transaction and verified by `integrity_report`. |
| `AUDIT_LOG` has no foreign keys | History must survive deletes. |
| Ledger and trades are append-only | Enforced by trigger. |
| Raw SQL, no ORM | The queries are what is assessed. |

## Demos for the viva
1. **Constraints:** `docker exec -i paper_trading_db psql -U postgres -d papertrading < db/demo/constraint_demo.sql` (nine rejections).
2. **Locking and isolation:** two psql sessions, see `db/demo/isolation_demo.md`.
3. **Concurrency stress test:**
   ```bash
   pip install requests "psycopg[binary]"
   python backend/tests/stress_test_concurrency.py            # all invariants PASS
   python backend/tests/stress_test_concurrency.py --unsafe   # invariants break or requests abort
   ```
   Then open http://localhost:3000/integrity and show the integrity report.

## Data pipeline
`data_pipeline/generate_data.py` builds the seed CSVs: real NSE bars via yfinance, Black-Scholes bars for the option, yield-curve bars for the bond. yfinance output changes on every run, so **commit the CSVs and regenerate only deliberately**.

## Team
| Name | Student ID | Responsibilities |
|---|---|---|
| Devansh Rupesh Anadkat | 2024ADPS0198H | ER/EER modelling, schema mapping, matching engine design |
| Akarsh Ramadugu | 2024ADPS0196H | BCNF verification, denormalization trade-offs, analytical SQL, indexes, views |
| Shashank Bodala | 2024ADPS0186H | Integrity constraints, trigger specifications |
| Druhin Sourya Datta Bommisetti | 2024ADPS0182H | Application architecture, workflows, API |
| Hakimkari Sathvika | 2024ADPS0192H | Data pipeline, seeding, stress test, repository |

Report, ER and schema diagrams: `MidsemSubmissions/`.
