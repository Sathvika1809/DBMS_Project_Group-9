"use client";
import { useEffect, useState } from "react";
import { api, money } from "@/lib/api";

export default function OrderForm({
  accountId,
  instrument,
  onDone,
}: {
  accountId: number;
  instrument: any;
  onDone: () => void;
}) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("1");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const lotSize = Number(instrument?.lot_size ?? 1);
  const multiplier = Number(instrument?.multiplier ?? 1);

  // Reset default quantity to 1 lot and clear stale status when switching instruments
  useEffect(() => {
    setQty(String(lotSize));
    setMsg(null);
  }, [instrument?.instrument_id, lotSize]);

  const numPrice = Number(price);
  const numQty = Number(qty);
  const estTotal =
    numPrice > 0 && numQty > 0 ? numPrice * numQty * multiplier : 0;

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api("/orders", {
        method: "POST",
        body: JSON.stringify({
          account_id: accountId,
          instrument_id: instrument.instrument_id,
          side,
          price: numPrice,
          qty: numQty,
        }),
      });
      const fills = r.fills.length
        ? ` Filled ${r.filled_qty} at ${r.fills.map((f: any) => money(f.price)).join(", ")}.`
        : " Resting on the book.";
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
        <button
          type="button"
          className={`side-buy ${side === "BUY" ? "on" : ""}`}
          onClick={() => setSide("BUY")}
        >
          Buy
        </button>
        <button
          type="button"
          className={`side-sell ${side === "SELL" ? "on" : ""}`}
          onClick={() => setSide("SELL")}
        >
          Sell
        </button>
      </div>

      <div className="field">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <label htmlFor="price" style={{ margin: 0 }}>
            Limit price (tick {instrument?.tick_size})
          </label>
          {instrument?.last_price && (
            <button
              type="button"
              className="ghost"
              style={{ fontSize: 11, padding: "2px 6px" }}
              onClick={() => setPrice(String(instrument.last_price))}
            >
              Use Last ({money(instrument.last_price)})
            </button>
          )}
        </div>
        <input
          id="price"
          inputMode="decimal"
          value={price}
          placeholder={instrument?.last_price ? String(instrument.last_price) : ""}
          onChange={(e) => setPrice(e.target.value)}
        />
      </div>

      <div className="field">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <label htmlFor="qty" style={{ margin: 0 }}>
            Quantity (lot {lotSize})
          </label>
          <div style={{ display: "flex", gap: 4 }}>
            {[1, 5, 10, 25].map((mult) => {
              const preset = mult * lotSize;
              return (
                <button
                  key={mult}
                  type="button"
                  className="ghost"
                  style={{ fontSize: 11, padding: "2px 6px" }}
                  onClick={() => setQty(String(preset))}
                >
                  {preset}
                </button>
              );
            })}
          </div>
        </div>
        <input
          id="qty"
          inputMode="decimal"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
        />
      </div>

      <div className="row" style={{ marginBottom: 12, fontSize: 12.5 }}>
        <span className="muted">
          Est. order value {multiplier > 1 ? `(${multiplier}x mult)` : ""}
        </span>
        <strong>{estTotal > 0 ? money(estTotal) : "-"}</strong>
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={busy || !price || !qty || numPrice <= 0 || numQty <= 0}
        style={{
          width: "100%",
          background: side === "BUY" ? "var(--buy)" : "var(--sell)",
          borderColor: side === "BUY" ? "var(--buy)" : "var(--sell)",
        }}
      >
        {busy ? "Placing..." : `${side === "BUY" ? "Buy" : "Sell"} ${instrument?.symbol ?? ""}`}
      </button>

      {msg && <div className={`msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
    </div>
  );
}