# CS F212 Database Systems — Project Submission
## Group 9: Paper-Trading Exchange
**Institution:** BITS Pilani, Hyderabad Campus  
**Course:** CS F212 Database Systems  

---

## 1. Project Description
This repository contains the database design and application architecture for a simulated paper-trading exchange supporting multiple financial instruments (stocks, bonds, and options), limit-order matching, settlement, and portfolio tracking. The primary focus of this submission is on formal database modeling, schema normalization, integrity constraints, and application architecture.

---

## 2. Team Members & Task Distribution

| Name | Student ID | Mid-Semester Responsibilities |
|---|---|---|
| **Devansh Rupesh Anadkat** | 2024ADPS0198H | Conceptual ER/EER modeling (Chen notation), EER disjoint specialization (`BOND`/`OPTION`), 9-step relational schema mapping, and stored procedure matching engine design (`match_and_settle`). |
| **Akarsh Ramadugu** | 2024ADPS0196H | BCNF normalization verification, performance denormalization trade-offs, non-trivial analytical SQL queries, partial indexing strategy, and database views. |
| **Shashank Bodala** | 2024ADPS0186H | Domain integrity constraints (`CHECK`, `UNIQUE`, `NOT NULL`) and trigger specifications (audit log, subtype disjointness, fill quantity synchronization). |
| **Druhin Sourya Datta Bommisetti** | 2024ADPS0182H | Application architecture, core workflow definitions, and FastAPI/psycopg3 interface specification. |
| **Hakimkari Sathvika** | 2024ADPS0192H | Data population pipeline (PostgreSQL `COPY`), market data seeding logic, and repository organization. |

---

## 3. Repository Layout

```
.
├── MidsemSubmissions/        # report, ER and schema diagrams
├── backend/                  # FastAPI + psycopg3 API
│   ├── routers/              # orders, portfolio
│   └── tests/                # concurrency stress test
├── data_pipeline/
│   ├── generate_data.py      # builds every seed CSV (see section 5)
│   ├── requirements.txt
│   └── seed_csvs/            # generated CSVs (committed for reproducibility)
├── db/                       # DDL, views/indexes, triggers, procedures, seed
├── frontend/
└── docker-compose.yml
```

---

## 4. Mid-Semester Deliverables

* **[Midsem_Submission.pdf](MidsemSubmissions/Midsem_Submission.pdf)**: Complete 5-page mid-semester submission report.
* **[Midsem_Submission.md](MidsemSubmissions/Midsem_Submission.md)**: Markdown source for the submission report.
* **[er_diagram.png](MidsemSubmissions/er_diagram.png)** / **[er_diagram.gv](MidsemSubmissions/er_diagram.gv)**: Chen-notation ER/EER diagram (Elmasri & Navathe 7th ed.) including entity types, relationships, weak entities, and specialization hierarchy.
* **[schema_diagram.png](MidsemSubmissions/schema_diagram.png)** / **[schema_diagram.gv](MidsemSubmissions/schema_diagram.gv)**: Relational schema diagram illustrating table structures, primary keys, foreign keys, and referential constraints.

---

## 5. Data Pipeline

All seed data is produced by `data_pipeline/generate_data.py`:

| File | Content |
|---|---|
| `users.csv`, `accounts.csv` | 1 admin/house user + 5 traders; account 101 has `Account_type = 'HOUSE'` and holds the inventory pool, the others are `'RETAIL'` |
| `instruments.csv` | 3 NSE stocks (RELIANCE, TCS, INFY), 1 GOI bond, 1 RELIANCE call option |
| `bonds.csv`, `options.csv` | EER subclass rows (option strike = next multiple of 50 above RELIANCE's latest close) |
| `price_bars.csv` | 1 year of daily OHLCV: real NSE bars for stocks, Black-Scholes bars for the option (rolling 30-day historical volatility, 7% risk-free rate), yield-curve bars for the bond (mean-reverting YTM discounted over the coupon schedule) |
| `positions.csv` | House-account starting inventory for the `POSITION` table (loaded by `05_seed_data.sql`) |

**Regenerate the CSVs** (needs internet for `yfinance`):

```bash
pip install -r data_pipeline/requirements.txt
python data_pipeline/generate_data.py
```

`yfinance` returns different data on every run, so **commit the generated CSVs** and only regenerate deliberately.

**Seed / re-seed the database:**

```bash
docker compose down -v      # drops the old volume so init scripts run again
docker compose up --build
```

On first start, PostgreSQL runs `db/01_schema.sql` … `db/05_seed_data.sql` in order. `05_seed_data.sql` loads the CSVs with `\copy` in FK-safe order and then advances the `SERIAL` sequences past the explicitly loaded IDs.

**Concurrency stress test** (with the stack running; needs `pip install requests`):

```bash
python backend/tests/stress_test_concurrency.py
```

---

## 6. Current Implementation Status
* **Design (report):** 12 normalized relations in BCNF with 16 foreign keys; attribute-defined, disjoint, partial specialization of `INSTRUMENT` into `BOND` and `OPTION`; weak entities `PRICE_BAR` (owner `INSTRUMENT`) and `ORDER_FILL` (owner `ORDER`).
* **Implemented in `db/01_schema.sql` so far:** `USER`, `ACCOUNT`, `INSTRUMENT`, `BOND`, `OPTION`, `PRICE_BAR`, `POSITION`, `ORDER` (8 of 12). Still to add: `TRADE`, `ORDER_FILL`, `CASH_LEDGER`, `AUDIT_LOG`.
* **Data pipeline:** complete for all implemented tables (`USER`, `ACCOUNT`, `INSTRUMENT`, `BOND`, `OPTION`, `PRICE_BAR`, `POSITION`); verified by loading the CSVs into PostgreSQL 16 against the current `01_schema.sql`.
* **Backend:** order placement and portfolio endpoints are written; they depend on the `match_and_settle` procedure and `portfolio_view`, which are not implemented yet (`db/02`–`04` are empty).
* **Planned Features:** Stored procedures for order matching, triggers for audit logging and domain constraints, and partial indexes for open limit orders.