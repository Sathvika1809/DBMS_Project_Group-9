# Primary script: Fetches real NSE stocks + computes Black-Scholes options & bonds

import csv
import math
import os
import random
from datetime import datetime
import yfinance as yf

# Fixed seed for any auxiliary noise for strict reproducibility
random.seed(42)

# ============================================================================
# 1. QUANT MATHEMATICAL MODEL (Black-Scholes for European Options)
# ============================================================================

def norm_cdf(x):
    """Cumulative distribution function for standard normal distribution."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def black_scholes(S, K, T, r, sigma, option_type="CALL"):
    """
    Black-Scholes European Option Pricing Model.
    S: Current Underlying Stock Price (Real NSE Close)
    K: Strike Price (2500.0)
    T: Time to Expiry in Years
    r: Risk-free Interest Rate (7.0% -> 0.07)
    sigma: Historical Volatility (22.0% -> 0.22)
    """
    if T <= 0:
        return max(0.0, S - K) if option_type == "CALL" else max(0.0, K - S)
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    if option_type == "CALL":
        price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm_cdf(-d2) + S * norm_cdf(-d1)
    
    return max(0.05, round(price, 2))  # Minimum tick price threshold

# ============================================================================
# 2. MASTER ENTITY DATA DEFINITIONS (Group 9 Schema)
# ============================================================================

users = [
    (1, "House Admin", "admin@exchange.com", "hash_admin_123", "ADMIN", "2026-01-01 00:00:00"),
    (2, "Devansh Rupesh Anadkat", "devansh@exchange.com", "hash_dev_123", "TRADER", "2026-01-02 00:00:00"),
    (3, "Akarsh Ramadugu", "akarsh@exchange.com", "hash_ak_123", "TRADER", "2026-01-02 00:00:00"),
    (4, "Shashank Bodala", "shashank@exchange.com", "hash_sh_123", "TRADER", "2026-01-02 00:00:00"),
    (5, "Druhin Sourya Datta", "druhin@exchange.com", "hash_dr_123", "TRADER", "2026-01-02 00:00:00"),
    (6, "Hakimkari Sathvika", "sathvika@exchange.com", "hash_sat_123", "TRADER", "2026-01-02 00:00:00")
]

accounts = [
    (101, 1, 10000000.00, True, "2026-01-01 00:00:00"),   # House Account (Inventory pool)
    (102, 2, 500000.00, False, "2026-01-02 00:00:00"),
    (103, 3, 500000.00, False, "2026-01-02 00:00:00"),
    (104, 4, 500000.00, False, "2026-01-02 00:00:00"),
    (105, 5, 500000.00, False, "2026-01-02 00:00:00"),
    (106, 6, 500000.00, False, "2026-01-02 00:00:00")
]

instruments = [
    (1, "RELIANCE", "Reliance Industries Ltd", "STOCK", "Energy", 1.0, 0.05, 1, "ACTIVE"),
    (2, "TCS", "Tata Consultancy Services", "STOCK", "Technology", 1.0, 0.05, 1, "ACTIVE"),
    (3, "INFY", "Infosys Limited", "STOCK", "Technology", 1.0, 0.05, 1, "ACTIVE"),
    (4, "GOI754_2032", "7.54% GOI Sovereign Bond 2032", "BOND", "Government", 10.0, 0.01, 100, "ACTIVE"),
    (5, "REL_CALL_2500", "RELIANCE Nov 2500 Call", "OPTION", "Derivatives", 250.0, 0.05, 250, "ACTIVE")
]

bonds = [
    (4, 1000.00, 7.54, 2, "2022-04-15", "2032-04-15")
]

options = [
    (5, 1, 2500.00, "2026-11-26", "CALL")  # Foreign key Underlying_id points to RELIANCE (ID: 1)
]

# ============================================================================
# 3. REAL MARKET DATA FETCHING & DERIVATIVE PRICING
# ============================================================================

stock_tickers = {
    1: "RELIANCE.NS",
    2: "TCS.NS",
    3: "INFY.NS"
}

price_bars = []
reliance_dates_and_closes = []

print("Fetching 1 year of real historical stock market data from NSE...")

for inst_id, symbol in stock_tickers.items():
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="1y", interval="1d")
    
    for date, row in df.iterrows():
        trade_date = date.strftime("%Y-%m-%d")
        open_p = round(float(row['Open']), 2)
        high_p = round(float(row['High']), 2)
        low_p = round(float(row['Low']), 2)
        close_p = round(float(row['Close']), 2)
        volume = int(row['Volume'])
        
        price_bars.append((inst_id, trade_date, open_p, high_p, low_p, close_p, volume))
        
        if inst_id == 1:
            reliance_dates_and_closes.append((trade_date, close_p))

print(f"Loaded real stock bars. Processing derivatives and bond pricing...")

# 4. Generate OPTION price bars based on real RELIANCE stock prices via Black-Scholes
expiry_dt = datetime(2026, 11, 26)

for trade_date_str, rel_close in reliance_dates_and_closes:
    current_dt = datetime.strptime(trade_date_str, "%Y-%m-%d")
    time_to_expiry_years = max(0.001, (expiry_dt - current_dt).days / 365.0)
    
    # Calculate exact Black-Scholes theoretical value
    bs_close = black_scholes(S=rel_close, K=2500.0, T=time_to_expiry_years, r=0.07, sigma=0.22, option_type="CALL")
    
    open_p = bs_close
    close_p = bs_close
    high_p = round(close_p * 1.015, 2)
    low_p = round(max(0.05, close_p * 0.985), 2)
    volume = random.randint(5000, 40000)
    
    price_bars.append((5, trade_date_str, open_p, high_p, low_p, close_p, volume))

# 5. Generate BOND price bars aligned with the trading calendar
bond_price = 99.50
for trade_date_str, _ in reliance_dates_and_closes:
    change = random.uniform(-0.10, 0.10)
    close_p = round(bond_price + change, 2)
    open_p = round(bond_price, 2)
    high_p = round(max(open_p, close_p) + 0.05, 2)
    low_p = round(min(open_p, close_p) - 0.05, 2)
    volume = random.randint(500, 5000)
    
    price_bars.append((4, trade_date_str, open_p, high_p, low_p, close_p, volume))
    bond_price = close_p

# ============================================================================
# 4. CSV OUTPUT GENERATION WITH AUTOMATIC FOLDER RESOLUTION
# ============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "seed_csvs")
os.makedirs(output_dir, exist_ok=True)

def write_csv(filename, headers, rows):
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Generated '{filepath}' successfully ({len(rows)} records).")

write_csv("users.csv", ["User_id", "Name", "Email", "Password_hash", "Role", "Created_at"], users)
write_csv("accounts.csv", ["Account_id", "User_id", "Cash_balance", "Is_house", "Created_at"], accounts)
write_csv("instruments.csv", ["Instrument_id", "Symbol", "Name", "Instrument_type", "Sector", "Multiplier", "Tick_size", "Lot_size", "Status"], instruments)
write_csv("bonds.csv", ["Instrument_id", "Face_value", "Coupon_rate", "Coupon_frequency", "Issue_date", "Maturity_date"], bonds)
write_csv("options.csv", ["Instrument_id", "Underlying_id", "Strike", "Expiry", "Option_type"], options)
write_csv("price_bars.csv", ["Instrument_id", "Trade_date", "Open", "High", "Low", "Close", "Volume"], price_bars)

print(f"\nPipeline execution complete! All CSV files are saved in '{output_dir}'.")