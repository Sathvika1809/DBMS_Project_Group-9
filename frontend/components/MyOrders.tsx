"use client";
import { api, money, num } from "@/lib/api";

export default function MyOrders({ orders, accountId, onDone }: { orders: any[]; accountId: number; onDone: () => void }) {
  async function cancel(id: number) {
    try {
      await api(`/orders/${id}/cancel`, { method: "POST", body: JSON.stringify({ account_id: accountId }) });
    } catch (e: any) {
      alert(e.message);
    }
    onDone();
  }
  return (
    <div className="panel">
      <h2>My orders</h2>
      <table>
        <thead><tr><th>#</th><th>Order</th><th>Filled</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_id}>
              <td>{o.order_id}</td>
              <td><span className={o.side === "BUY" ? "buy" : "sell"}>{o.side}</span> {o.symbol} @ {money(o.price)}</td>
              <td>{num(o.filled_qty)}/{num(o.qty)}</td>
              <td>{o.status}</td>
              <td>{(o.status === "OPEN" || o.status === "PARTIAL") && <button className="ghost" onClick={() => cancel(o.order_id)}>Cancel</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!orders.length && <p className="muted">No orders yet.</p>}
    </div>
  );
}
