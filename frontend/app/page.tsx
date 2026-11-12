"use client";
import { useCallback, useEffect, useState } from "react";
import { api, money } from "@/lib/api";
import PriceChart from "@/components/PriceChart";
import OrderBook from "@/components/OrderBook";
import OrderForm from "@/components/OrderForm";
import Portfolio from "@/components/Portfolio";
import MyOrders from "@/components/MyOrders";

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
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/accounts"), api("/instruments")])
      .then(([a, i]) => {
        setAccounts(a); setInstruments(i);
        setAccountId((a.find((x: any) => x.account_type === "RETAIL") ?? a[0])?.account_id ?? null);
        setInstId(i[0]?.instrument_id ?? null);
      })
      .catch((e) => setError(e.message));
  }, []);

  const refresh = useCallback(async () => {
    if (accountId == null || instId == null) return;
    try {
      const [b, t, o, p, i] = await Promise.all([
        api(`/instruments/${instId}/book`), api(`/instruments/${instId}/trades`),
        api(`/orders?account_id=${accountId}`), api(`/accounts/${accountId}/portfolio`), api("/instruments"),
      ]);
      setBook(b); setTrades(t); setOrders(o); setPortfolio(p); setInstruments(i); setError("");
    } catch (e: any) { setError(e.message); }
  }, [accountId, instId]);

  useEffect(() => { if (instId != null) api(`/instruments/${instId}/bars`).then(setBars).catch(() => {}); }, [instId]);
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, [refresh]);

  const inst = instruments.find((i) => i.instrument_id === instId);

  return (
    <>
      {error && <div className="msg err">Cannot reach the API: {error}</div>}
      <div className="panel" style={{ marginBottom: 14, display: "flex", gap: 12, alignItems: "center" }}>
        <label htmlFor="acct" className="muted">Trading as</label>
        <select id="acct" style={{ maxWidth: 360 }} value={accountId ?? ""} onChange={(e) => setAccountId(Number(e.target.value))}>
          {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.name} ({a.account_type}), account {a.account_id}</option>)}
        </select>
      </div>
      <div className="grid">
        <div className="col">
          <div className="panel">
            <h2>Instruments</h2>
            {instruments.map((i) => (
              <button key={i.instrument_id} className={`inst ${i.instrument_id === instId ? "on" : ""}`} onClick={() => setInstId(i.instrument_id)}>
                <span><strong>{i.symbol}</strong> <span className="muted">{i.instrument_type}</span></span>
                <span>{i.last_price ? money(i.last_price) : "-"}</span>
              </button>
            ))}
          </div>
          <div className="panel"><h2>Daily close, {inst?.symbol}</h2><PriceChart bars={bars} /></div>
        </div>
        <div className="col">
          <OrderBook book={book} last={inst?.last_price} />
          <div className="panel">
            <h2>Recent trades</h2>
            <table>
              <thead><tr><th>Time</th><th>Price</th><th>Qty</th></tr></thead>
              <tbody>{trades.map((t) => (
                <tr key={t.trade_id}><td>{new Date(t.executed_at).toLocaleTimeString()}</td><td>{money(t.price)}</td><td>{Number(t.qty)}</td></tr>
              ))}</tbody>
            </table>
            {!trades.length && <p className="muted">No trades yet on this instrument.</p>}
          </div>
        </div>
        <div className="col">
          {inst && accountId != null && <OrderForm accountId={accountId} instrument={inst} onDone={refresh} />}
          <Portfolio data={portfolio} />
          {accountId != null && <MyOrders orders={orders} accountId={accountId} onDone={refresh} />}
        </div>
      </div>
    </>
  );
}
