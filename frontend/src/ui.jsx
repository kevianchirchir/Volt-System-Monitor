import { useRef } from "react";
import { useDisplayValue, useStats } from "./context/StatsContext.jsx";
import { clamp, speed } from "./lib.js";

export function Gauge({ id, title, caption }) {
  const arc = useRef(null), num = useRef(null);
  useDisplayValue(id, (raw) => {
    const v = clamp(raw, 0, 100);
    arc.current.setAttribute("stroke-dasharray", `${v * 0.9999} 100`);
    num.current.textContent = v.toFixed(0);
  });
  return (
    <div className="card">
      <div className="h">{title}</div>
      <div className="gauge">
        <svg viewBox="0 0 120 120">
          <circle className="t" cx="60" cy="60" r="46" />
          <circle ref={arc} className="a" cx="60" cy="60" r="46" pathLength="100" />
        </svg>
        <b><span><i ref={num} /><small>%</small></span></b>
      </div>
      <div className="cap" style={{ marginTop: 2 }}>{caption}</div>
    </div>
  );
}

export function Speed({ k, className }) {
  const ref = useRef(null);
  useDisplayValue(k, (v) => { ref.current.textContent = speed(v); });
  return <div ref={ref} className={className} />;
}

export function Rows({ group, keys, tight }) {
  const { info } = useStats();
  return (
    <div className={tight ? "rows tight" : "rows"}>
      {keys.map((k) => (
        <div key={k}><span>{k}</span><em>{info[`${group}.${k}`] ?? "-"}</em></div>
      ))}
    </div>
  );
}
