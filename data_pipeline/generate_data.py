# Primary data pipeline for the Paper-Trading Exchange (CS F212, Group 9)
#
#   * Real NSE daily bars (RELIANCE, TCS, INFY) via yfinance
#   * Option bars: Black-Scholes on the real RELIANCE OHLC, with rolling
#     historical volatility and a strike derived from the latest spot price
#   * Bond bars: clean price from a mean-reverting yield-to-maturity path
#     (coupon schedule + discounting), i.e. a simple yield-curve model
#   * House-account starting inventory (positions.csv) for the POSITION table
#
# Output: data_pipeline/seed_csvs/*.csv   (commit the generated CSVs so the
# seed is reproducible; yfinance returns different data on every run)
#
# Usage:  pip install -r data_pipeline/requirements.txt
#         python data_pipeline/generate_data.py

import calendar
import csv
import math
import os
import random
from datetime import date, datetime

import yfinance as yf

random.seed(42)  # reproducible synthetic parts (bond path, option volumes)

# ============================================================================
# 0. CONFIGURATION
# ============================================================================

RISK_FREE_RATE = 0.07        # annual, continuously compounded
DEFAULT_SIGMA = 0.22         # fallback until enough history for rolling vol
VOL_WINDOW = 30              # trading days for rolling historical volatility
TRADING_DAYS = 252
STRIKE_STEP = 50             # strike = next multiple of 50 at/above spot
OPTION_EXPIRY = date(2026, 11, 26)
OPTION_MIN_PRICE = 0.05      # minimum tick

# Bond: 7.54% GOI 2032, semi-annual coupons, face value 1000, quoted per 100
BOND_FACE = 1000.00
BOND_COUPON = 0.0754         # stored as a fraction (fits DECIMAL(5,4))
BOND_FREQ = 2
BOND_ISSUE = date(2022, 4, 15)
BOND_MATURITY = date(2032, 4, 15)
YTM_START = 0.068
YTM_LONG_RUN = 0.068
YTM_REVERSION = 0.05
YTM_DAILY_VOL = 0.0003
YTM_MIN, YTM_MAX = 0.060, 0.076

STOCK_TICKERS = {1: "RELIANCE.NS", 2: "TCS.NS", 3: "INFY.NS"}

HOUSE_ACCOUNT_ID = 101
HOUSE_STOCK_QTY = 10000
HOUSE_BOND_QTY = 5000
HOUSE_OPTION_QTY = 1000

# ============================================================================
# 1. MATHEMATICAL MODELS
# ============================================================================


def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def black_scholes(S, K, T, r, sigma, option_type="CALL"):
    """European option price. S spot, K strike, T years, r rate, sigma vol."""
    if T <= 0:
        intrinsic = max(0.0, S - K) if option_type == "CALL" else max(0.0, K - S)
        return max(OPTION_MIN_PRICE, round(intrinsic, 2))

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "CALL":
        price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm_cdf(-d2) + S * norm_cdf(-d1)

    return max(OPTION_MIN_PRICE, round(price, 2))


def rolling_volatility(closes, i):
    """Annualised std-dev of log returns over the last VOL_WINDOW bars up to i."""
    if i < 5:
        return DEFAULT_SIGMA
    window = closes[max(0, i - VOL_WINDOW): i + 1]
    rets = [math.log(window[k] / window[k - 1]) for k in range(1, len(window))]
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
    sigma = math.sqrt(var) * math.sqrt(TRADING_DAYS)
    return min(max(sigma, 0.10), 0.60)


def add_months(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def coupon_dates(issue, maturity, freq):
    """All coupon dates, generated backwards from maturity, after issue."""
    step = 12 // freq
    dates, k = [], 0
    while True:
        cd = add_months(maturity, -step * k)
        if cd <= issue:
            break
        dates.append(cd)
        k += 1
    return sorted(dates)


BOND_COUPON_DATES = coupon_dates(BOND_ISSUE, BOND_MATURITY, BOND_FREQ)


def bond_clean_price(on_date, ytm):
    """Clean price per 100 face: discounted coupons + principal - accrued."""
    f = BOND_FREQ
    cpn = BOND_COUPON * 100.0 / f
    future = [cd for cd in BOND_COUPON_DATES if cd > on_date]
    if not future:
        return 100.0
    dirty = 0.0
    for cd in future:
        t = (cd - on_date).days / 365.0
        dirty += cpn / (1 + ytm / f) ** (f * t)
    t_mat = (BOND_MATURITY - on_date).days / 365.0
    dirty += 100.0 / (1 + ytm / f) ** (f * t_mat)

    next_cd = future[0]
    past = [cd for cd in BOND_COUPON_DATES if cd <= on_date]
    prev_cd = past[-1] if past else BOND_ISSUE
    accrued = cpn * (on_date - prev_cd).days / max(1, (next_cd - prev_cd).days)
    return dirty - accrued


# ============================================================================
# 2. REAL MARKET DATA
# ============================================================================


def fetch_stock_bars(inst_id, symbol):
    df = yf.Ticker(symbol).history(period="1y", interval="1d")
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    bars = []
    for ts, row in df.iterrows():
        o, h, l, c = (round(float(row[k]), 2) for k in ("Open", "High", "Low", "Close"))
        if min(o, h, l, c) <= 0:
            continue
        h = max(h, o, c)          # keep the OHLC invariants after rounding
        l = min(l, o, c)
        bars.append((inst_id, ts.strftime("%Y-%m-%d"), o, h, l, c, int(row["Volume"])))
    return bars


print("Fetching 1 year of real NSE data...")
price_bars = []
stock_bars = {}
for inst_id, symbol in STOCK_TICKERS.items():
    stock_bars[inst_id] = fetch_stock_bars(inst_id, symbol)
    price_bars.extend(stock_bars[inst_id])
    print(f"  {symbol}: {len(stock_bars[inst_id])} bars")

reliance = stock_bars[1]  # (id, date, o, h, l, c, v)
spot = reliance[-1][5]
STRIKE = int(math.ceil(spot / STRIKE_STEP) * STRIKE_STEP)
print(f"RELIANCE latest close = {spot}; option strike set to {STRIKE}")

# ============================================================================
# 3. MASTER ENTITY DATA (Group 9 schema)
# ============================================================================

users = [
    (1, "House Admin", "admin@exchange.com", "hash_admin_123", "ADMIN", "2026-01-01 00:00:00"),
    (2, "Devansh Rupesh Anadkat", "devansh@exchange.com", "hash_dev_123", "TRADER", "2026-01-02 00:00:00"),
    (3, "Akarsh Ramadugu", "akarsh@exchange.com", "hash_ak_123", "TRADER", "2026-01-02 00:00:00"),
    (4, "Shashank Bodala", "shashank@exchange.com", "hash_sh_123", "TRADER", "2026-01-02 00:00:00"),
    (5, "Druhin Sourya Datta", "druhin@exchange.com", "hash_dr_123", "TRADER", "2026-01-02 00:00:00"),
    (6, "Hakimkari Sathvika", "sathvika@exchange.com", "hash_sat_123", "TRADER", "2026-01-02 00:00:00"),
]

# Account_type matches db/01_schema.sql: CHECK IN ('HOUSE', 'RETAIL', 'INSTITUTIONAL')
accounts = [
    (101, 1, "HOUSE", 10000000.00, "2026-01-01 00:00:00"),   # House account (inventory pool)
    (102, 2, "RETAIL", 500000.00, "2026-01-02 00:00:00"),
    (103, 3, "RETAIL", 500000.00, "2026-01-02 00:00:00"),
    (104, 4, "RETAIL", 500000.00, "2026-01-02 00:00:00"),
    (105, 5, "RETAIL", 500000.00, "2026-01-02 00:00:00"),
    (106, 6, "RETAIL", 500000.00, "2026-01-02 00:00:00"),
]

OPTION_SYMBOL = f"REL_CALL_{STRIKE}"
instruments = [
    (1, "RELIANCE", "Reliance Industries Ltd", "STOCK", "Energy", 1.0, 0.05, 1, "ACTIVE"),
    (2, "TCS", "Tata Consultancy Services", "STOCK", "Technology", 1.0, 0.05, 1, "ACTIVE"),
    (3, "INFY", "Infosys Limited", "STOCK", "Technology", 1.0, 0.05, 1, "ACTIVE"),
    (4, "GOI754_2032", "7.54% GOI Sovereign Bond 2032", "BOND", "Government", 10.0, 0.01, 100, "ACTIVE"),
    (5, OPTION_SYMBOL, f"RELIANCE Nov {STRIKE} Call", "OPTION", "Derivatives", 250.0, 0.05, 250, "ACTIVE"),
]

bonds = [
    (4, BOND_FACE, BOND_COUPON, BOND_FREQ, BOND_ISSUE.isoformat(), BOND_MATURITY.isoformat()),
]

options = [
    (5, 1, float(STRIKE), OPTION_EXPIRY.isoformat(), "CALL"),  # Underlying_id -> RELIANCE (1)
]

# ============================================================================
# 4. DERIVATIVE & BOND PRICE BARS
# ============================================================================

# 4a. Option bars: Black-Scholes at the stock's real open/high/low/close.
# A call is monotone increasing in S, so High >= max(Open, Close) and
# Low <= min(Open, Close) hold automatically.
reliance_closes = [b[5] for b in reliance]
option_bars = []
for i, (_, d, s_o, s_h, s_l, s_c, _) in enumerate(reliance):
    current = datetime.strptime(d, "%Y-%m-%d").date()
    if current > OPTION_EXPIRY:
        continue
    T = max(1 / 365.0, (OPTION_EXPIRY - current).days / 365.0)
    sigma = rolling_volatility(reliance_closes, i)
    px = {k: black_scholes(S, STRIKE, T, RISK_FREE_RATE, sigma, "CALL")
          for k, S in (("o", s_o), ("h", s_h), ("l", s_l), ("c", s_c))}
    option_bars.append((5, d, px["o"], px["h"], px["l"], px["c"], random.randint(5000, 40000)))
price_bars.extend(option_bars)

# 4b. Bond bars: mean-reverting YTM -> clean price via coupon schedule.
bond_bars = []
ytm = YTM_START
for _, d, *_ in reliance:
    current = datetime.strptime(d, "%Y-%m-%d").date()
    prev_ytm = ytm
    ytm += YTM_REVERSION * (YTM_LONG_RUN - ytm) + random.gauss(0, YTM_DAILY_VOL)
    ytm = min(max(ytm, YTM_MIN), YTM_MAX)
    o = round(bond_clean_price(current, prev_ytm), 2)
    c = round(bond_clean_price(current, ytm), 2)
    h = round(max(o, c) + 0.05, 2)
    l = round(min(o, c) - 0.05, 2)
    bond_bars.append((4, d, o, h, l, c, random.randint(500, 5000)))
price_bars.extend(bond_bars)

price_bars.sort(key=lambda r: (r[0], r[1]))

# ============================================================================
# 5. HOUSE INVENTORY (feeds the POSITION table once it exists)
# ============================================================================

positions = [
    (HOUSE_ACCOUNT_ID, 1, HOUSE_STOCK_QTY, stock_bars[1][-1][5]),
    (HOUSE_ACCOUNT_ID, 2, HOUSE_STOCK_QTY, stock_bars[2][-1][5]),
    (HOUSE_ACCOUNT_ID, 3, HOUSE_STOCK_QTY, stock_bars[3][-1][5]),
    (HOUSE_ACCOUNT_ID, 4, HOUSE_BOND_QTY, bond_bars[-1][5]),
    (HOUSE_ACCOUNT_ID, 5, HOUSE_OPTION_QTY, option_bars[-1][5]),
]

# ============================================================================
# 6. SANITY CHECKS
# ============================================================================

opt_closes = [b[5] for b in option_bars]
print(f"Option close range: {min(opt_closes)} - {max(opt_closes)}")
if max(opt_closes) <= OPTION_MIN_PRICE:
    print("WARNING: option prices are flat at the minimum tick; check the strike/spot.")
bnd_closes = [b[5] for b in bond_bars]
print(f"Bond close range:   {min(bnd_closes)} - {max(bnd_closes)}")

for b in price_bars:
    assert b[5] > 0 and b[2] > 0, b
    assert b[3] >= b[4] and b[3] >= max(b[2], b[5]) and b[4] <= min(b[2], b[5]), b
assert len({(b[0], b[1]) for b in price_bars}) == len(price_bars), "duplicate PK in price_bars"

# ============================================================================
# 7. CSV OUTPUT
# ============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "seed_csvs")
os.makedirs(output_dir, exist_ok=True)


def write_csv(filename, headers, rows):
    path = os.path.join(output_dir, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"Generated '{path}' ({len(rows)} records).")


write_csv("users.csv", ["User_id", "Name", "Email", "Password_hash", "Role", "Created_at"], users)
write_csv("accounts.csv", ["Account_id", "User_id", "Account_type", "Cash_balance", "Created_at"], accounts)
write_csv("instruments.csv", ["Instrument_id", "Symbol", "Name", "Instrument_type", "Sector",
                              "Multiplier", "Tick_size", "Lot_size", "Status"], instruments)
write_csv("bonds.csv", ["Instrument_id", "Face_value", "Coupon_rate", "Coupon_frequency",
                        "Issue_date", "Maturity_date"], bonds)
write_csv("options.csv", ["Instrument_id", "Underlying_id", "Strike", "Expiry", "Option_type"], options)
write_csv("price_bars.csv", ["Instrument_id", "Trade_date", "Open", "High", "Low", "Close", "Volume"], price_bars)
write_csv("positions.csv", ["Account_id", "Instrument_id", "Qty", "Avg_cost"], positions)

print(f"\nDone. CSVs are in '{output_dir}'. Commit them so everyone seeds identical data.")