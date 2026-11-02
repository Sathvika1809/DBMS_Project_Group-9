import os
import random
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# Set fixed seeds for full reproducibility
random.seed(42)
np.random.seed(42)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def calculate_black_scholes(S, K, T, r, sigma, option_type='call'):
    """Calculate Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
    return max(0.05, round(float(price), 2))

def calculate_bond_price(face_value, coupon_rate, ytm, years_to_maturity, freq=2):
    """Calculate bond clean price via discounted cash flow matching yield curve."""
    periods = int(years_to_maturity * freq)
    if periods == 0:
        return round(face_value, 2)
    
    coupon = (coupon_rate * face_value) / freq
    discount_rate = ytm / freq
    
    t = np.arange(1, periods + 1)
    pv_coupons = np.sum(coupon / (1 + discount_rate)**t)
    pv_face = face_value / (1 + discount_rate)**periods
    return round(float(pv_coupons + pv_face), 2)

def main():
    print("Fetching historical RELIANCE data via yfinance...")
    stock_df = yf.download("RELIANCE.NS", period="1y", interval="1d")
    
    if stock_df.empty:
        raise ValueError("Failed to fetch yfinance data for RELIANCE.NS")
        
    # Flatten MultiIndex columns if present
    if isinstance(stock_df.columns, pd.MultiIndex):
        stock_df.columns = stock_df.columns.get_level_values(0)
        
    stock_df = stock_df.dropna().reset_index()

    # Calculate 30-day annualized rolling volatility
    log_returns = np.log(stock_df['Close'] / stock_df['Close'].shift(1))
    historical_sigma = float(log_returns.std() * np.sqrt(252))
    print(f"Calculated Historical Volatility: {historical_sigma:.4f}")

    # Generate Price Bars for RELIANCE (Instrument ID 1)
    price_bars = []
    for idx, row in stock_df.iterrows():
        dt_str = row['Date'].strftime('%Y-%m-%d %H:%M:%S')
        open_p = round(float(row['Open']), 2)
        high_p = round(float(row['High']), 2)
        low_p = round(float(row['Low']), 2)
        close_p = round(float(row['Close']), 2)
        vol = int(row['Volume'])
        
        price_bars.append({
            "instrument_id": 1,
            "timestamp": dt_str,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": vol
        })

    latest_spot = price_bars[-1]["close"]
    # Set strike near current spot price (round up to nearest 50)
    strike_price = float(np.ceil(latest_spot * 1.02 / 50.0) * 50.0)
    print(f"Latest Spot Price: {latest_spot}, Selected Option Strike: {strike_price}")

    risk_free_rate = 0.065
    total_days = len(price_bars)

    # Generate Option (ID 5) & Bond (ID 2) Bars aligned with stock timestamps
    for i, bar in enumerate(price_bars):
        spot = bar["close"]
        days_left = max(1, total_days - i)
        T = days_left / 365.0
        
        # 1. Option Pricing
        bs_close = calculate_black_scholes(spot, strike_price, T, risk_free_rate, historical_sigma, 'call')
        bs_open = round(max(0.05, bs_close * np.random.uniform(0.98, 1.02)), 2)
        bs_high = round(max(bs_open, bs_close) * np.random.uniform(1.00, 1.03), 2)
        bs_low = round(max(0.05, min(bs_open, bs_close) * np.random.uniform(0.97, 1.00)), 2)
        
        price_bars.append({
            "instrument_id": 5,
            "timestamp": bar["timestamp"],
            "open": bs_open,
            "high": bs_high,
            "low": bs_low,
            "close": bs_close,
            "volume": random.randint(100, 5000)
        })

        # 2. Bond Pricing (DCF with small YTM random walk)
        ytm = 0.071 + np.random.normal(0, 0.0005)
        bond_close = calculate_bond_price(100.0, 0.0754, ytm, years_to_maturity=5.0)
        
        price_bars.append({
            "instrument_id": 2,
            "timestamp": bar["timestamp"],
            "open": round(bond_close + np.random.uniform(-0.05, 0.05), 2),
            "high": round(bond_close + np.random.uniform(0.01, 0.10), 2),
            "low": round(bond_close - np.random.uniform(0.01, 0.10), 2),
            "close": bond_close,
            "volume": random.randint(500, 10000)
        })

    # Save Price Bars CSV
    pd.DataFrame(price_bars).to_csv(os.path.join(OUTPUT_DIR, "price_bars.csv"), index=False)

    # Save Options metadata CSV
    options_data = [{
        "option_id": 1,
        "instrument_id": 5,
        "underlying_instrument_id": 1,
        "option_type": "CALL",
        "strike_price": strike_price,
        "expiration_date": "2026-12-31"
    }]
    pd.DataFrame(options_data).to_csv(os.path.join(OUTPUT_DIR, "options.csv"), index=False)

    # Save Instruments CSV
    instruments_data = [
        {"instrument_id": 1, "ticker": "RELIANCE", "name": "Reliance Industries Ltd", "instrument_type": "STOCK", "coupon_rate": None, "coupon_frequency": None, "maturity_date": None},
        {"instrument_id": 2, "ticker": "GS2031", "name": "7.54% GOI 2031", "instrument_type": "BOND", "coupon_rate": 0.0754, "coupon_frequency": 2, "maturity_date": "2031-05-23"},
        {"instrument_id": 5, "ticker": f"RELIANCE26DEC{int(strike_price)}CE", "name": f"RELIANCE Call {int(strike_price)}", "instrument_type": "OPTION", "coupon_rate": None, "coupon_frequency": None, "maturity_date": "2026-12-31"}
    ]
    pd.DataFrame(instruments_data).to_csv(os.path.join(OUTPUT_DIR, "instruments.csv"), index=False)

    # Save Users CSV
    users_data = [
        {"user_id": 1, "username": "house_desk", "email": "house@exchange.com"},
        {"user_id": 2, "username": "trader_joe", "email": "joe@trader.com"}
    ]
    pd.DataFrame(users_data).to_csv(os.path.join(OUTPUT_DIR, "users.csv"), index=False)

    # Save Accounts CSV
    accounts_data = [
        {"account_id": 1, "user_id": 1, "account_type": "HOUSE", "balance": 100000000.00},
        {"account_id": 2, "user_id": 2, "account_type": "RETAIL", "balance": 500000.00}
    ]
    pd.DataFrame(accounts_data).to_csv(os.path.join(OUTPUT_DIR, "accounts.csv"), index=False)

    # Save Positions CSV (House Account Inventory)
    positions_data = [
        {"position_id": 1, "account_id": 1, "instrument_id": 1, "quantity": 10000, "average_buy_price": latest_spot},
        {"position_id": 2, "account_id": 1, "instrument_id": 2, "quantity": 50000, "average_buy_price": 100.00},
        {"position_id": 3, "account_id": 1, "instrument_id": 5, "quantity": 100000, "average_buy_price": 45.00}
    ]
    pd.DataFrame(positions_data).to_csv(os.path.join(OUTPUT_DIR, "positions.csv"), index=False)

    print("Successfully generated all pipeline CSV files in data_pipeline/")

if __name__ == "__main__":
    main()