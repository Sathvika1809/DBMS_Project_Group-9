"use client";

export default function PriceChart({ bars }: { bars: any[] }) {
  if (!bars.length) return <p className="muted">No price history.</p>;
  const closes = bars.map((b) => Number(b.close));
  const lo = Math.min(...closes), hi = Math.max(...closes);
  const W = 400, H = 140, pad = 4;
  const x = (i: number) => pad + (i / Math.max(1, closes.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / Math.max(1e-9, hi - lo)) * (H - 2 * pad);
  const d = closes.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Daily closing price">
        <path d={d} fill="none" stroke="var(--focus)" strokeWidth="1.5" />
      </svg>
      <div className="row"><span className="muted">Low {lo.toFixed(2)}</span><span className="muted">High {hi.toFixed(2)}</span></div>
    </div>
  );
}
