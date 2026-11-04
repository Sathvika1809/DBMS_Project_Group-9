# CS F212 Database Systems — Project Submission
## Group 9: Paper-Trading Exchange
**Institution:** BITS Pilani, Hyderabad Campus
**Course:** CS F212 Database Systems

---

## 1. What this is

A mini stock exchange with fake money, built to put the database at the centre. Users place **limit orders** on stocks, bonds and options; matching and settlement run **inside PostgreSQL as one atomic transaction**; cash, positions and the order book stay correct even when many users trade at once.

Why a trading engine for a DBMS course: money and shares must never be created or lost, which is exactly what transactions, locking, constraints and triggers exist for.

The focus of this repository is formal database modelling (ER/EER, BCNF), integrity constraints, and application architecture.

---

## 2. Team Members & Task Distribution

| Name | Student ID | Mid-Semester Responsibilities |
|---|---|---|
| **Devansh Rupesh Anadkat** | 2024ADPS0198H | Conceptual ER/EER modeling (Chen notation), EER disjoint specialization (`BOND`/`OPTION`), 9-step relational schema mapping, and stored procedure matching engine design (`match_and_settle`). |
| **Akarsh Ramadugu** | 2024ADPS0196H | BCNF normalization verification, performance denormalization trade-offs, non-trivial analytical SQL queries, partial indexing strategy, and database views. |
| **Shashank Bodala** | 2024ADPS0186H | Domain integrity constraints (`CHECK`, `UNIQUE`, `NOT NULL`) and trigger specifications (audit log, subtype disjointness, fill quantity synchronization). |
| **Druhin Sourya Datta Bommisetti** | 2024ADPS0182H | Application architecture, core workflow definitions, and FastAPI/psycopg3 interface specification. |
| **Hakimkari Sathvika** | 2024ADPS0192H | Data population pipeline (PostgreSQL `COPY`), market data seeding logic, concurrency stress test, and repository organization. |

---

## 3. Repository Layout

```
.
├── MidsemSubmissions/        # report, ER and schema diagrams
├── backend/                  # FastAPI + psycopg3 API
│   ├── routers/              # orders, portfolio
│   └── tests/                # concurrency stress test
├── data_pipeline/
│   ├── generate_data.py      # builds every seed CSV (see section 6)
│   ├── requirements.txt
│   └── seed_csvs/            # generated CSVs (committed for reproducibility)
├── db/                       # DDL, views/indexes, triggers, procedures, seed
├── frontend/
└── docker-compose.yml
```

---

## 4. Design Decisions

| Decision | Why |
|---|---|
| **Limit orders only** | A limit order has a price cap, so cost is bounded and buying power can be checked up front. Market orders need book-walking, unknown cost and price protection, which add edge cases without adding DBMS concepts. |
| **Matching engine is a PL/pgSQL procedure** | Match, trade, fills, positions, ledger and balances happen in one transaction, so a failure rolls everything back. The business logic lives in the DBMS. |
| **Row locking with `SELECT ... FOR UPDATE`** | Two orders touching the same account or position must not read the same balance at once. The stress test demonstrates this (section 7). |
| **Instrument supertype with `BOND` and `OPTION` subtypes (EER, option 8A)** | Orders, trades and positions reference only `instrument_id`, so they work for every type. 8A avoids the many NULLs that single-table designs would put on stocks. Stocks need no extra columns, so they have no subtype table (partial, disjoint specialization). |
| **Deliberate denormalization** | `ACCOUNT.cash_balance`, `POSITION` quantity and average cost, and `ORDER.filled_qty` are derivable from `CASH_LEDGER`, `TRADE` and `ORDER_FILL`. They are stored for speed and kept correct inside the same transaction that writes the source rows. |
| **`AUDIT_LOG` has no foreign keys** | Audit history must survive deletions. |
| **Weak entities `PRICE_BAR` and `ORDER_FILL`** | A price bar only exists for an instrument, and a fill only exists for an order; both are identified by owner key plus partial key. |
| **Raw SQL, no ORM** | The queries are the thing being assessed, and an ORM would hide them. |

Full reasoning, BCNF analysis and the ER/EER diagrams are in `MidsemSubmissions/`.

---

## 5. Mid-Semester Deliverables

* **[Midsem_Submission.pdf](MidsemSubmissions/Midsem_Submission.pdf)**: Complete mid-semester submission report.
* **[Midsem_Submission.md](MidsemSubmissions/Midsem_Submission.md)**: Markdown source for the report.
* **[er_diagram.png](MidsemSubmissions/er_diagram.png)** / **[er_diagram.gv](MidsemSubmissions/er_diagram.gv)**: Chen-notation ER/EER diagram (Elmasri & Navathe 7th ed.).
* **[schema_diagram.png](MidsemSubmissions/schema_diagram.png)** / **[schema_diagram.gv](MidsemSubmissions/schema_diagram.gv)**: Relational schema diagram.

---

## 6. Data Pipeline

All seed data is produced by `data_pipeline/generate_data.py`:

| File | Content |
|---|---|
| `users.csv`, `accounts.csv` | 1 admin/house user + 5 traders; account 101 has `Account_type = 'HOUSE'` and holds the inventory pool, the others are `'RETAIL'` |
| `instruments.csv` | 3 NSE stocks (RELIANCE, TCS, INFY), 1 GOI bond, 1 RELIANCE call option |
| `bonds.csv`, `options.csv` | EER subclass rows (option strike = next multiple of 50 above RELIANCE's latest close) |
| `price_bars.csv` | 1 year of daily OHLCV (about 1,240 rows): real NSE bars for stocks, Black-Scholes bars for the option (rolling 30-day historical volatility, 7% risk-free rate), yield-curve bars for the bond (mean-reverting YTM discounted over the coupon schedule) |
| `positions.csv` | House-account starting inventory for the `POSITION` table |

**Regenerate the CSVs** (needs internet for `yfinance`):

```bash
pip install -r data_pipeline/requirements.txt
python data_pipeline/generate_data.py
```

`yfinance` returns different data on every run, so **commit the generated CSVs** and only regenerate deliberately. Teammates should pull, not regenerate.

**Seed / re-seed the database:**

```bash
docker compose down -v      # drops the old volume so init scripts run again
docker compose up --build
```

On first start, PostgreSQL runs `db/01_schema.sql` … `db/05_seed_data.sql` in order. `05_seed_data.sql` loads the CSVs with `\copy` in FK-safe order, advances the `SERIAL` sequences past the explicitly loaded IDs, and disables triggers during the load so seed rows do not flood `AUDIT_LOG`. The last query prints a row-count table: expect 6 users, 6 accounts, 5 instruments, 1 bond, 1 option, 1240 price bars, 5 positions.

---

## 7. Concurrency Stress Test

`backend/tests/stress_test_concurrency.py` fires 50 parallel limit orders at one instrument (the house account sells, accounts 102 to 106 buy), then reads the database and checks:

1. Total cash across all accounts is unchanged.
2. Total shares are unchanged.
3. No negative cash or shares.
4. No order is overfilled.
5. Total shares bought equals total shares sold.

```bash
pip install requests "psycopg[binary]"
python backend/tests/stress_test_concurrency.py             # safe mode: all checks should PASS
python backend/tests/stress_test_concurrency.py --unsafe    # locking off: at least one check should FAIL
```

`--unsafe` sends `?unsafe=true`, which needs the orders endpoint to call a lock-free `match_and_settle_unsafe` procedure. Showing the checks break without `FOR UPDATE` is the demonstration of why the locking exists.

---

## 8. Current Implementation Status
* **Design (report):** 12 normalized relations in BCNF with 16 foreign keys; attribute-defined, disjoint, partial specialization of `INSTRUMENT` into `BOND` and `OPTION`; weak entities `PRICE_BAR` (owner `INSTRUMENT`) and `ORDER_FILL` (owner `ORDER`).
* **Implemented in `db/01_schema.sql` so far:** `USER`, `ACCOUNT`, `INSTRUMENT`, `BOND`, `OPTION`, `PRICE_BAR`, `POSITION`, `ORDER` (8 of 12). Still to add: `TRADE`, `ORDER_FILL`, `CASH_LEDGER`, `AUDIT_LOG`.
* **Data pipeline:** complete for all implemented tables; seed CSVs regenerated against the current schema.
* **Stress test:** written with invariant checks and an `--unsafe` mode; needs `match_and_settle` (and the unsafe variant) to run end to end.
* **Backend:** order placement and portfolio endpoints are written; they depend on the `match_and_settle` procedure and `portfolio_view`, which are not implemented yet (`db/02` to `04` are empty).
* **Planned:** stored procedures for order matching, triggers for audit logging and domain constraints, partial indexes for open limit orders, opening ledger entries and demo orders in the seed.