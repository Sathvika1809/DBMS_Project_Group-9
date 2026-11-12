"use client";
import { useState } from "react";
import { api, money } from "@/lib/api";

export default function OrderForm({ accountId, instrument, onDone }: { accountId: number; instrument: any; onDone: () => void }) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("1");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api("/orders", {
        method: "POST",
        body: JSON.stringify({ account_id: accountId, instrument_id: instrument.instrument_id, side, price: Number(price), qty: Number(qty) }),
      });
      const fills = r.fills.length ? ` Filled ${r.filled_qty} at ${r.fills.map((f: any) => money(f.price)).join(", ")}.` : " Resting on the book.";
      setMsg({ ok: true, text: `Order #${r.order_id} is ${r.status}.${fills}` });
      onDone();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Place a limit order: {instrument?.symbol}</h2>
      <div className="seg">
        <button className={`side-buy ${side === "BUY" ? "on" : ""}`} onClick={() => setSide("BUY")}>Buy</button>
        <button className={`side-sell ${side === "SELL" ? "on" : ""}`} onClick={() => setSide("SELL")}>Sell</button>
      </div>
      <div className="field">
        <label htmlFor="price">Limit price (multiple of {instrument?.tick_size})</label>
        <input id="price" inputMode="decimal" value={price} placeholder={instrument?.last_price ? money(instrument.last_price) : ""} onChange={(e) => setPrice(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="qty">Quantity (lot size {instrument?.lot_size})</label>
        <input id="qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
      </div>
      <button onClick={submit} disabled={busy || !price || !qty} style={{ width: "100%" }}>
        {busy ? "Placing..." : `${side === "BUY" ? "Buy" : "Sell"} ${instrument?.symbol ?? ""}`}
      </button>
      {msg && <div className={`msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
    </div>
  );
}
