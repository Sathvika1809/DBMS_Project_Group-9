"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Integrity() {
  const [report, setReport] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [vwap, setVwap] = useState<any[]>([]);
  const [dd, setDd] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      Promise.all([api("/analytics/integrity"), api("/analytics/audit"), api("/analytics/vwap"), api("/analytics/drawdown")])
        .then(([r, a, v, d]) => { setReport(r); setAudit(a); setVwap(v); setDd(d); setError(""); })
        .catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="col" style={{ maxWidth: 900 }}>
      {error && <div className="msg err">{error}</div>}
      <div className="panel">
        <h2>Integrity report {report && <span className={report.ok ? "buy" : "sell"}>{report.ok ? "all checks pass" : "violations found"}</span>}</h2>
        {report?.checks.map((c: any) => (
          <div className="check" key={c.check_name}>
            <span>{c.check_name}</span><strong className={c.violations === 0 ? "buy" : "sell"}>{c.violations} violations</strong>
          </div>
        ))}
        <p className="muted">Cash balances, positions and filled quantities are stored for speed. This view recomputes them from the ledger and fills and compares.</p>
      </div>
      <div className="panel">
        <h2>Daily VWAP of exchange trades</h2>
        <table>
          <thead><tr><th>Symbol</th><th>Day</th><th>VWAP</th><th>Volume</th><th>Trades</th></tr></thead>
          <tbody>{vwap.map((r, i) => <tr key={i}><td>{r.symbol}</td><td>{r.day}</td><td>{r.vwap}</td><td>{r.volume}</td><td>{r.trades}</td></tr>)}</tbody>
        </table>
        {!vwap.length && <p className="muted">Trade something first.</p>}
      </div>
      <div className="panel">
        <h2>Max drawdown and 30-bar return (window functions)</h2>
        <table>
          <thead><tr><th>Symbol</th><th>Max drawdown</th><th>30-bar return</th></tr></thead>
          <tbody>{dd.map((r) => <tr key={r.symbol}><td>{r.symbol}</td><td>{(Number(r.max_drawdown) * 100).toFixed(2)}%</td><td>{r.latest_30_bar_return == null ? "-" : (Number(r.latest_30_bar_return) * 100).toFixed(2) + "%"}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Audit log (written by triggers)</h2>
        {audit.map((a) => (
          <div className="row" key={a.log_id}>
            <span>{a.action} {a.table_name} #{a.row_id ?? "-"}</span>
            <span className="muted">{new Date(a.changed_at).toLocaleTimeString()}</span>
          </div>
        ))}
        {!audit.length && <p className="muted">No audit rows yet.</p>}
      </div>
    </div>
  );
}
