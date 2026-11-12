"use client";
import { money } from "@/lib/api";

export default function CashLedger({ entries }: { entries: any[] }) {
  return (
    <div className="panel">
      <h2>Cash ledger (append-only)</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Type</th>
            <th>Ref</th>
            <th>Date</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.ledger_id}>
              <td>{e.ledger_id}</td>
              <td>{e.entry_type}</td>
              <td className="muted">
                {e.trade_id ? `Trade #${e.trade_id}` : e.instrument_id ? `Inst #${e.instrument_id}` : "-"}
              </td>
              <td className="muted">{e.value_date}</td>
              <td className={Number(e.amount) >= 0 ? "buy" : "sell"}>
                {Number(e.amount) >= 0 ? `+${money(e.amount)}` : money(e.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!entries.length && <p className="muted">No ledger entries yet.</p>}
    </div>
  );
}