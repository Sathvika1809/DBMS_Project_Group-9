"use client";
import { useState } from "react";
import { api, money, num } from "@/lib/api";

export default function MyOrders({ orders, accountId, onDone }: { orders: any[]; accountId: number; onDone: () => void }) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPrice, setEditPrice] = useState("");
  const [editQty, setEditQty] = useState("");

  async function cancel(id: number) {
    try {
      await api(`/orders/${id}/cancel`, { method: "POST", body: JSON.stringify({ account_id: accountId }) });
    } catch (e: any) {
      alert(e.message);
    }
    onDone();
  }

  function startEdit(o: any) {
    setEditingId(o.order_id);
    setEditPrice(String(o.price));
    setEditQty(String(o.qty));
  }

  async function saveEdit(id: number) {
    try {
      await api(`/orders/${id}/modify`, {
        method: "POST",
        body: JSON.stringify({ account_id: accountId, price: Number(editPrice), qty: Number(editQty) }),
      });
      setEditingId(null);
    } catch (e: any) {
      alert(e.message);
    }
    onDone();
  }

  return (
    <div className="panel">
      <h2>My orders</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Order</th>
            <th>Filled</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => {
            const isOpen = o.status === "OPEN" || o.status === "PARTIAL";
            const isEditing = editingId === o.order_id;
            return (
              <tr key={o.order_id}>
                <td>{o.order_id}</td>
                <td>
                  <span className={o.side === "BUY" ? "buy" : "sell"}>{o.side}</span> {o.symbol} @{" "}
                  {isEditing ? (
                    <input
                      style={{ width: 76, padding: "2px 4px", display: "inline" }}
                      value={editPrice}
                      onChange={(e) => setEditPrice(e.target.value)}
                    />
                  ) : (
                    money(o.price)
                  )}
                </td>
                <td>
                  {num(o.filled_qty)}/
                  {isEditing ? (
                    <input
                      style={{ width: 52, padding: "2px 4px", display: "inline" }}
                      value={editQty}
                      onChange={(e) => setEditQty(e.target.value)}
                    />
                  ) : (
                    num(o.qty)
                  )}
                </td>
                <td>{o.status}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {isOpen && !isEditing && (
                    <>
                      <button className="ghost" style={{ marginRight: 4 }} onClick={() => startEdit(o)}>
                        Edit
                      </button>
                      <button className="ghost" onClick={() => cancel(o.order_id)}>
                        Cancel
                      </button>
                    </>
                  )}
                  {isEditing && (
                    <>
                      <button className="ghost" style={{ marginRight: 4 }} onClick={() => saveEdit(o.order_id)}>
                        Save
                      </button>
                      <button className="ghost" onClick={() => setEditingId(null)}>
                        X
                      </button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!orders.length && <p className="muted">No orders yet.</p>}
    </div>
  );
}