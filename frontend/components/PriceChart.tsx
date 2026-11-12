"use client";
import { useState } from "react";

export default function PriceChart({ bars }: { bars: any[] }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!bars.length) return <p className="muted">No price history.</p>;

  const closes = bars.map((b) => Number(b.close));
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const first = closes[0];
  const last = closes[closes.length - 1];
  const isUp = last >= first;
  const strokeColor = isUp ? "var(--buy)" : "var(--sell)";

  const W = 400;
  const H = 156;
  const padX = 6;
  const padY = 12;

  const x = (i: number) => padX + (i / Math.max(1, closes.length - 1)) * (W - 2 * padX);
  const y = (v: number) => H - padY - ((v - lo) / Math.max(1e-9, hi - lo)) * (H - 2 * padY);

  const linePath = closes
    .map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");

  const areaPath = `${linePath} L${x(closes.length - 1).toFixed(1)},${(H - padY).toFixed(1)} L${x(0).toFixed(1)},${(H - padY).toFixed(1)} Z`;

  const activeIdx = hoverIdx !== null && bars[hoverIdx] ? hoverIdx : bars.length - 1;
  const activeBar = bars[activeIdx];
  const activeClose = Number(activeBar.close);
  const changePct = first > 0 ? ((activeClose - first) / first) * 100 : 0;

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.round(relX * (bars.length - 1));
    setHoverIdx(idx);
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <div>
          <strong style={{ fontSize: 16 }}>{activeClose.toFixed(2)}</strong>{" "}
          <span className={changePct >= 0 ? "buy" : "sell"} style={{ fontSize: 12 }}>
            {changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%
          </span>
        </div>
        <span className="muted" style={{ fontSize: 12 }}>
          {activeBar.trade_date}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ display: "block", cursor: "crosshair", overflow: "visible" }}
        role="img"
        aria-label="Daily closing price"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="priceAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Horizontal reference lines */}
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={padX}
            y1={padY + t * (H - 2 * padY)}
            x2={W - padX}
            y2={padY + t * (H - 2 * padY)}
            stroke="var(--line)"
            strokeDasharray="3 3"
            strokeWidth="0.75"
          />
        ))}

        <path d={areaPath} fill="url(#priceAreaGrad)" />
        <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinejoin="round" />

        {/* Crosshair and active point */}
        <line
          x1={x(activeIdx)}
          y1={padY}
          x2={x(activeIdx)}
          y2={H - padY}
          stroke="var(--muted)"
          strokeDasharray="2 2"
          strokeWidth="1"
        />
        <circle
          cx={x(activeIdx)}
          cy={y(activeClose)}
          r="3.5"
          fill="#ffffff"
          stroke={strokeColor}
          strokeWidth="2"
        />
      </svg>

      <div className="row" style={{ marginTop: 4, fontSize: 12 }}>
        <span className="muted">Low {lo.toFixed(2)}</span>
        {activeBar.volume != null && <span className="muted">Vol {Number(activeBar.volume).toLocaleString()}</span>}
        <span className="muted">High {hi.toFixed(2)}</span>
      </div>
    </div>
  );
}