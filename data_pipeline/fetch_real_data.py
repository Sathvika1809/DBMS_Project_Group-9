# Standalone Utility Script: Fetches real historical NSE stock data
import csv
import os
import pandas as pd
import yfinance as yf

# 1. Real NSE Tickers (Yahoo Finance uses '.NS' for National Stock Exchange of India)
tickers = {
    1: "RELIANCE.NS",
    2: "TCS.NS",
    3: "INFY.NS"
}

price_bars = []

print("Fetching 1 year of real historical stock market data from NSE...")

for inst_id, symbol in tickers.items():
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

# 2. Path Handling: Ensure CSV is saved in data_pipeline/seed_csvs/
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "seed_csvs")
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "price_bars.csv")

# 3. Write Output
with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Instrument_id", "Trade_date", "Open", "High", "Low", "Close", "Volume"])
    writer.writerows(price_bars)

print(f"Done! Successfully saved {len(price_bars)} real historical price records to '{output_file}'.")