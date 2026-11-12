"use client";
import { useCallback, useEffect, useState } from "react";
import { api, money } from "@/lib/api";
import PriceChart from "@/components/PriceChart";
import OrderBook from "@/components/OrderBook";
import OrderForm from "@/components/OrderForm";
import Portfolio from "@/components/Portfolio";
import MyOrders from "@/components/MyOrders";
import CashLedger from "@/components/CashLedger";

type RightTab = "portfolio" | "orders" | "ledger";

export default function Trade() {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [instruments, setInstruments] = useState<any[]>([]);
  const [instId, setInstId] = useState<number | null>(null);
  const [bars, setBars] = useState<any[]>([]);
  const [book, setBook] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [ledger, setLedger] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("portfolio");

  useEffect(() => {
    Promise.all([api("/accounts"), api("/instruments")])
      .then(([a, i]) => {
        setAccounts(a);
        setInstruments(i);
        setAccountId((a.find((x: any) => x.account_type === "RETAIL") ?? a[0])?.account_id ?? null);
        setInstId(i[0]?.instrument_id ?? null);
      })
      .catch((e) => setError(e.message));
  }, []);

  const refresh = useCallback(async () => {
    if (accountId == null || instId == null) return;
    try {
      const [b, t, o, p, l, i] = await Promise.all([
        api(`/instruments/${instId}/book`),
        api(`/instruments/${instId}/trades`),
        api(`/orders?account_id=${accountId}`),
        api(`/accounts/${accountId}/portfolio`),
        api(`/accounts/${accountId}/ledger?limit=15`),
        api("/instruments"),
      ]);
      setBook(b);
      setTrades(t);
      setOrders(o);
      setPortfolio(p);
      setLedger(l);
      setInstruments(i);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }, [accountId, instId]);

  useEffect(() => {
    if (instId != null) api(`/instruments/${instId}/bars`).then(setBars).catch(() => {});
  }, [instId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  const inst = instruments.find((i) => i.instrument_id === instId);
  const filteredInstruments = instruments.filter(
    (i) =>
      i.symbol.toLowerCase().includes(search.toLowerCase()) ||
      i.instrument_type.toLowerCase().includes(search.toLowerCase())
  );
  const openOrderCount = orders.filter((o) => o.status === "OPEN" || o.status === "PARTIAL").length;

  return (
    <div className="kite-shell">
      {error && <div className="msg err" style={{ margin: "8px 12px 0" }}>Cannot reach the API: {error}</div>}

      {/* Top Market Tape & Account Bar */}
      <div className="kite-subbar">
        <div className="ticker-strip">
          {instruments.map((item) => {
            const active = item.instrument_id === instId;
            return (
              <button
                key={item.instrument_id}
                type="button"
                className={`ticker-chip ${active ? "on" : ""}`}
                onClick={() => setInstId(item.instrument_id)}
              >
                <span className="ticker-sym">{item.symbol}</span>
                <span className="ticker-ltp">{item.last_price ? money(item.last_price) : "—"}</span>
              </button>
            );
          })}
        </div>

        <div className="account-strip">
          {portfolio && (
            <div className="margin-pill">
              <span className="muted">AVAILABLE FUNDS</span>
              <strong className="buy">
                ₹{money(portfolio.cash_balance ?? portfolio.cash ?? portfolio.available_cash ?? 0)}
              </strong>
            </div>
          )}
          <div className="acct-select-wrap">
            <label htmlFor="acct" className="muted">CLIENT</label>
            <select
              id="acct"
              value={accountId ?? ""}
              onChange={(e) => setAccountId(Number(e.target.value))}
            >
              {accounts.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name} ({a.account_type}) • #{a.account_id}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 3-Pane Zerodha Kite Terminal Cockpit */}
      <div className="kite-grid">
        {/* LEFT PANE: Marketwatch & Contract Specs */}
        <aside className="kite-sidebar">
          <div className="panel kite-watchlist">
            <div className="mw-search-wrap">
              <input
                type="text"
                className="mw-search"
                placeholder="Search eg: reliance, tcs, bond, option..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <span className="mw-count">{filteredInstruments.length} / {instruments.length}</span>
            </div>

            <div className="mw-list">
              {filteredInstruments.map((i) => (
                <button
                  key={i.instrument_id}
                  type="button"
                  className={`mw-row ${i.instrument_id === instId ? "on" : ""}`}
                  onClick={() => setInstId(i.instrument_id)}
                >
                  <div className="mw-left">
                    <span className="mw-sym">{i.symbol}</span>
                    <span className={`badge badge-${i.instrument_type.toLowerCase()}`}>
                      {i.instrument_type === "STOCK" ? "NSE EQ" : i.instrument_type}
                    </span>
                  </div>
                  <div className="mw-right">
                    <span className="mw-price">{i.last_price ? money(i.last_price) : "-"}</span>
                    <span className="mw-tick">Tick {i.tick_size}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {inst && (
            <div className="panel kite-specs">
              <h2>
                <span>Contract Info</span>
                <span className="badge badge-stock">{inst.instrument_type}</span>
              </h2>
              <div className="row"><span className="muted">Status</span><span className="buy">{inst.status}</span></div>
              <div className="row"><span className="muted">Lot / Tick Size</span><span>{inst.multiplier}x / {inst.tick_size}</span></div>
              {inst.instrument_type === "BOND" && (
                <>
                  <div className="row"><span className="muted">Face / Coupon</span><span>{money(inst.face_value)} @ {(Number(inst.coupon_rate) * 100).toFixed(2)}%</span></div>
                  <div className="row"><span className="muted">Maturity</span><span>{inst.maturity_date}</span></div>
                  <div className="row"><span className="muted">Approx. YTM</span><span className="buy">{inst.approx_ytm ? `${(Number(inst.approx_ytm) * 100).toFixed(2)}%` : "-"}</span></div>
                </>
              )}
              {inst.instrument_type === "OPTION" && (
                <>
                  <div className="row"><span className="muted">Underlying</span><span>{inst.underlying_symbol}</span></div>
                  <div className="row"><span className="muted">Type / Strike</span><span>{inst.option_type} @ {money(inst.strike)}</span></div>
                  <div className="row"><span className="muted">Expiry</span><span>{inst.expiry}</span></div>
                </>
              )}
            </div>
          )}
        </aside>

        {/* CENTER PANE: Dominant Chart + Market Depth & Time/Sales */}
        <section className="kite-center">
          <div className="panel kite-chart-panel">
            <div className="chart-header">
              <div>
                <span className="chart-title">{inst?.symbol ?? "—"}</span>
                <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                  {inst?.instrument_type} • DAILY CLOSE
                </span>
              </div>
              {inst?.last_price && (
                <div className="chart-ltp">
                  <span className="muted" style={{ fontSize: 11, marginRight: 6 }}>LTP</span>
                  <strong>₹{money(inst.last_price)}</strong>
                </div>
              )}
            </div>
            <PriceChart bars={bars} />
          </div>

          <div className="kite-bottom-split">
            <OrderBook book={book} last={inst?.last_price} />

            <div className="panel">
              <h2>
                <span>Time & Sales (Recent Trades)</span>
                <span className="muted">{trades.length} fills</span>
              </h2>
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Price</th>
                    <th>Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.trade_id}>
                      <td className="muted">{new Date(t.executed_at).toLocaleTimeString()}</td>
                      <td className="buy">{money(t.price)}</td>
                      <td>{Number(t.qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!trades.length && <p className="muted" style={{ marginTop: 12 }}>No trades executed on {inst?.symbol} yet.</p>}
            </div>
          </div>
        </section>

        {/* RIGHT PANE: Kite Order Ticket + Tabbed Holdings / Orders / Ledger */}
        <aside className="kite-right">
          {inst && accountId != null && (
            <OrderForm accountId={accountId} instrument={inst} onDone={refresh} />
          )}

          <div className="kite-tabs-wrap">
            <div className="kite-tabs">
              <button
                type="button"
                className={`kite-tab ${rightTab === "portfolio" ? "on" : ""}`}
                onClick={() => setRightTab("portfolio")}
              >
                Holdings
              </button>
              <button
                type="button"
                className={`kite-tab ${rightTab === "orders" ? "on" : ""}`}
                onClick={() => setRightTab("orders")}
              >
                Orders {openOrderCount > 0 && <span className="tab-pill">{openOrderCount}</span>}
              </button>
              <button
                type="button"
                className={`kite-tab ${rightTab === "ledger" ? "on" : ""}`}
                onClick={() => setRightTab("ledger")}
              >
                Funds Ledger
              </button>
            </div>

            <div className="kite-tab-body">
              {rightTab === "portfolio" && <Portfolio data={portfolio} />}
              {rightTab === "orders" && accountId != null && (
                <MyOrders orders={orders} accountId={accountId} onDone={refresh} />
              )}
              {rightTab === "ledger" && <CashLedger entries={ledger} />}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}