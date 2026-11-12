"use client";
import { money, num } from "@/lib/api";

export default function Portfolio({ data }: { data: any }) {
  if (!data) return null;
  return (
    <div className="panel">
      <h2>Portfolio</h2>
      <div className="row"><span className="muted">Cash</span><span>{money(data.cash_balance)}</span></div>
      <div className="row"><span className="muted">Holdings value</span><span>{money(data.market_value)}</span></div>
      <div className="row"><strong>Total equity</strong><strong>{money(data.total_equity)}</strong></div>
      <div className="row"><span className="muted">Unrealized P&amp;L</span>
        <span className={Number(data.unrealized_pnl) >= 0 ? "buy" : "sell"}>{money(data.unrealized_pnl)}</span></div>
      <table style={{ marginTop: 8 }}>
        <thead><tr><th>Symbol</th><th>Qty</th><th>Avg cost</th><th>Last</th><th>P&amp;L</th></tr></thead>
        <tbody>
          {data.holdings.map((h: any) => (
            <tr key={h.instrument_id}>
              <td>{h.symbol}</td><td>{num(h.quantity)}</td><td>{money(h.avg_buy_price)}</td><td>{money(h.current_price)}</td>
              <td className={Number(h.unrealized_pnl) >= 0 ? "buy" : "sell"}>{money(h.unrealized_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!data.holdings.length && <p className="muted">No holdings yet. A filled buy order shows up here.</p>}
    </div>
  );
}
