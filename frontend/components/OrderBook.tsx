"use client";
import { money, num } from "@/lib/api";

function Side({ rows, kind }: { rows: any[]; kind: "b" | "s" }) {
  const max = Math.max(1, ...rows.map((r) => Number(r.cumulative_qty)));
  return (
    <>
      {rows.map((r) => (
        <tr key={`${kind}${r.price}`} className="depth">
          <td className={kind === "b" ? "buy" : "sell"} style={{ position: "relative" }}>
            <span className={`bar ${kind}`} style={{ width: `${(Number(r.cumulative_qty) / max) * 100}%` }} />
            <span style={{ position: "relative" }}>{money(r.price)}</span>
          </td>
          <td>{num(r.total_qty)}</td>
          <td>{r.num_orders}</td>
        </tr>
      ))}
    </>
  );
}

export default function OrderBook({ book, last }: { book: any; last: any }) {
  const asks = [...(book?.asks ?? [])].reverse(); // best ask nearest the middle
  const bids = book?.bids ?? [];
  return (
    <div className="panel">
      <h2>Order book</h2>
      <table>
        <thead><tr><th>Price</th><th>Qty</th><th>Orders</th></tr></thead>
        <tbody>
          <Side rows={asks} kind="s" />
          <tr><td colSpan={3} className="big" style={{ textAlign: "center" }}>{last ? money(last) : "-"}</td></tr>
          <Side rows={bids} kind="b" />
        </tbody>
      </table>
      {!asks.length && !bids.length && <p className="muted">No open orders. Place one to start the book.</p>}
    </div>
  );
}
